import io
import json
import logging
import os
import tempfile
import time
import zipfile
from datetime import datetime, timedelta, timezone

import requests
from shapely.geometry import box, mapping, MultiPolygon
from shapely.validation import make_valid
from shapely.ops import unary_union
import shapefile as pyshp

from config.geo_config import STATE_BOUNDS

IEM_WATCHWARN_URL = "https://mesonet.agron.iastate.edu/cgi-bin/request/gis/watchwarn.py"


def _split_antimeridian(geom):
    """Fix a geometry that crosses the antimeridian.

    Sub-polygons with a centroid in the eastern hemisphere (lon > 0) are
    shifted by -360 so the whole zone renders contiguously near Alaska.
    """
    from shapely import ops

    try:
        parts = list(geom.geoms) if isinstance(geom, MultiPolygon) else [geom]
        shifted = []
        for p in parts:
            if p.centroid.x > 0:
                p = ops.transform(lambda x, y, z=None: (x - 360, y), p)
            shifted.append(p)
        result = unary_union(shifted)
        return result if not result.is_empty else None
    except Exception:
        return None


_SIG_SUFFIX = {
    "W": "Warning",
    "A": "Watch",
    "Y": "Advisory",
    "S": "Statement",
}

_PHENOM_BASE = {
    # Convective
    "TO": "Tornado",
    "SV": "Severe Thunderstorm",
    "FF": "Flash Flood",
    "FL": "Flood",
    # Tropical
    "HU": "Hurricane",
    "TR": "Tropical Storm",
    "TY": "Typhoon",
    # Winter
    "BZ": "Blizzard",
    "WS": "Winter Storm",
    "WW": "Winter Weather",
    "LE": "Lake Effect Snow",
    "IS": "Ice Storm",
    "ZR": "Freezing Rain",
    "IP": "Sleet",
    # Wind
    "HW": "High Wind",
    "WI": "Wind",
    "BW": "Brisk Wind",
    # Heat/Cold
    "EH": "Extreme Heat",
    "HT": "Heat",
    "EC": "Extreme Cold",
    "FZ": "Freeze",
    "FR": "Frost",
    "CW": "Cold Weather",
    # Marine/Coastal
    "SU": "High Surf",
    "CF": "Coastal Flood",
    "LS": "Lakeshore Flood",
    "BH": "Beach Hazards",
    "MA": "Marine Weather",
    "SC": "Small Craft",
    "GL": "Gale",
    "SR": "Storm",
    "HF": "Hurricane Force Wind",
    "UP": "Freezing Spray",
    "SE": "Hazardous Seas",
    "SI": "Small Craft",
    "SW": "Small Craft",
    "RB": "Small Craft",
    "LO": "Low Water",
    "MF": "Dense Fog",
    "MS": "Marine Weather",
    "MH": "Marine Weather",
    # Fire
    "FW": "Fire Weather",
    "RF": "Red Flag",
    # Air quality
    "AQ": "Air Quality",
    # Additional VTEC phenomena
    "FA": "Flood",
    "LW": "Lake Wind",
    "SQ": "Snow Squall",
    "DS": "Dust Storm",
    "DU": "Blowing Dust",
    "SM": "Dense Smoke",
    "AS": "Air Stagnation",
    "AF": "Ashfall",
    "EW": "Extreme Wind",
    "SS": "Storm Surge",
    "TS": "Tsunami",
    "WC": "Wind Chill",
    "HZ": "Hard Freeze",
    "ZF": "Freezing Fog",
    "FG": "Dense Fog",
    "RP": "Rip Current",
}

_PHENOM_SIG_EVENT = {
    # Explicit mappings where base+suffix is insufficient or non-obvious.
    ("BW", "Y"): "Brisk Wind Advisory",
    ("CW", "Y"): "Cold Weather Advisory",
    ("UP", "W"): "Heavy Freezing Spray Warning",
    ("UP", "Y"): "Freezing Spray Advisory",
    ("MF", "Y"): "Dense Fog Advisory",
    ("RP", "S"): "Rip Current Statement",
    ("HF", "W"): "Hurricane Force Wind Warning",
    ("HF", "A"): "Hurricane Force Wind Watch",
    ("SE", "W"): "Hazardous Seas Warning",
    ("SE", "A"): "Hazardous Seas Watch",
    ("SI", "Y"): "Small Craft Advisory",
    ("SW", "Y"): "Small Craft Advisory",
    ("RB", "Y"): "Small Craft Advisory",
    ("LO", "Y"): "Low Water Advisory",
    ("MS", "S"): "Marine Weather Statement",
    ("MH", "S"): "Marine Weather Statement",
}

_MARINE_PHENOMENA = {
    "SC",
    "GL",
    "MA",
    "MH",
    "UP",
    "SE",
    "SI",
    "SW",
    "RB",
    "BW",
    "SR",
    "HF",
    "LO",
    "MF",
    "MS",
    "BH",
    "RP",
}


def _configure_pyshp_logging() -> None:
    """Silence known non-fatal pyshp GeoJSON conversion warnings."""
    try:
        pyshp.VERBOSE = False
    except Exception:
        pass
    try:
        pyshp.logger.setLevel(logging.ERROR)
    except Exception:
        pass


def _iem_ts_to_dt(ts_str: str):
    if not ts_str or len(ts_str) < 12:
        return None
    try:
        # YYYYMMDDHHMM
        return datetime(
            int(ts_str[0:4]),
            int(ts_str[4:6]),
            int(ts_str[6:8]),
            int(ts_str[8:10]),
            int(ts_str[10:12]),
            tzinfo=timezone.utc,
        )
    except Exception:
        return None


def _event_name_from_attrs(attrs: dict) -> str | None:
    # Prefer an explicit EVENT field if present.
    for key in ("EVENT", "event", "Event"):
        val = attrs.get(key)
        if val:
            return str(val).strip()

    phenom = str(attrs.get("PHENOM", "") or attrs.get("phenomena", "") or "").strip()
    sig = str(attrs.get("SIG", "") or attrs.get("significance", "") or "").strip()

    if not phenom or not sig:
        return None

    override = _PHENOM_SIG_EVENT.get((phenom.upper(), sig.upper()))
    if override:
        return override

    base = _PHENOM_BASE.get(phenom.upper())
    suffix = _SIG_SUFFIX.get(sig.upper())
    if not base or not suffix:
        return None

    # Match the naming style used in alerts_config.py (e.g. "Tornado Warning")
    return f"{base} {suffix}".replace("  ", " ").strip()


def _state_bbox_filter(feature_geom, state_code: str | None) -> bool:
    if not state_code:
        return True
    bounds = STATE_BOUNDS.get(state_code.upper())
    if not bounds:
        return True
    lon0, lon1, lat0, lat1 = bounds
    bbox = box(lon0, lat0, lon1, lat1)
    try:
        return not feature_geom.intersection(bbox).is_empty
    except Exception:
        return True


def fetch_active_alerts_iem(
    state: str | None = None,
    lookback_hours: int = 168,
    cache_minutes: int = 5,
):
    """Fetch active alerts via IEM WatchWarn shapefile service.

    Returns a list of GeoJSON-like features compatible with alerts_utils.process_alerts():
    [{"properties": {"event": ...}, "geometry": {...}}, ...]

    Notes:
    - IEM doesn't always provide NWS-style JSON; we normalize into the NWS feature shape.
    - We keep the time window modest to avoid huge downloads.
    """

    base_path = os.path.dirname(os.path.abspath(__file__))
    region_key = state.upper() if state else "NATIONAL"
    cache_dir = os.path.join(base_path, "alert_data", region_key)
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, "alerts_iem.json")

    if os.path.exists(cache_file):
        age_sec = time.time() - os.path.getmtime(cache_file)
        if age_sec < cache_minutes * 60:
            try:
                with open(cache_file, "r") as f:
                    data = json.load(f)
                return data.get("features", [])
            except Exception:
                pass

    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=max(int(lookback_hours), 1))
    end = now + timedelta(hours=1)

    headers = {"User-Agent": "(NCHurricane.com Weather Suite, contact@nchurricane.com)"}

    def build_url(include_state_filter: bool) -> str:
        url = (
            f"{IEM_WATCHWARN_URL}"
            f"?year1={start.year}&month1={start.month}&day1={start.day}"
            f"&hour1={start.hour}&minute1={start.minute}"
            f"&year2={end.year}&month2={end.month}&day2={end.day}"
            f"&hour2={end.hour}&minute2={end.minute}"
            f"&simple=yes&fmt=shp"
        )
        # Some IEM endpoints accept a states= filter; if unsupported, request may fail.
        if include_state_filter and state:
            url += f"&states={state.upper()}"
        return url

    resp = None
    last_error = None
    attempts = [True, False] if state else [False]
    for include_state_filter in attempts:
        read_timeout = 12 if include_state_filter else 20
        try:
            resp = requests.get(
                build_url(include_state_filter),
                headers=headers,
                timeout=(5, read_timeout),
            )
            resp.raise_for_status()
            break
        except Exception as e:
            last_error = e
            resp = None

    if resp is None:
        print(f"[WARN] IEM live alert download failed: {last_error}")
        return []

    tmpdir = tempfile.mkdtemp(prefix="iem_live_ww_")
    features = []
    try:
        with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
            z.extractall(tmpdir)

        shp_files = [f for f in os.listdir(tmpdir) if f.endswith(".shp")]
        if not shp_files:
            return []

        import cartopy.io.shapereader as shpreader
        import warnings

        _configure_pyshp_logging()
        reader = shpreader.Reader(os.path.join(tmpdir, shp_files[0]))
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=".*Possible issue encountered.*")
            warnings.filterwarnings("ignore", message=".*polygon interior holes.*")
            records_iter = reader.records()

        for rec in records_iter:
            attrs = rec.attributes
            geom = rec.geometry
            if geom is None or geom.is_empty:
                continue

            issue_raw = str(attrs.get("ISSUED", "") or "")
            expire_raw = str(attrs.get("EXPIRED", "") or "")
            issue_dt = _iem_ts_to_dt(issue_raw)
            expire_dt = _iem_ts_to_dt(expire_raw)
            if not issue_dt or not expire_dt:
                continue

            if not (issue_dt <= now <= expire_dt):
                continue

            if state and not _state_bbox_filter(geom, state):
                continue

            event_name = _event_name_from_attrs(attrs)
            if not event_name:
                continue

            phenom = str(attrs.get("PHENOM", "") or attrs.get("phenomena", "")).upper()
            sig = str(attrs.get("SIG", "") or attrs.get("significance", "")).upper()
            gtype = str(attrs.get("GTYPE", "") or "").upper().strip()
            nws_ugc = str(attrs.get("NWS_UGC", "") or "").strip()
            status = str(attrs.get("STATUS", "") or "").upper().strip()
            is_marine = phenom in _MARINE_PHENOMENA

            if not geom.is_valid:
                try:
                    geom = make_valid(geom)
                except Exception:
                    try:
                        geom = geom.buffer(0)
                    except Exception:
                        continue
                if geom.is_empty:
                    continue

            bounds = geom.bounds
            lon_span = bounds[2] - bounds[0]
            if is_marine and lon_span > 100:
                geom = _split_antimeridian(geom)
                if geom is None or geom.is_empty:
                    continue

            wfo = str(attrs.get("WFO", "") or "").strip()
            props = {
                "event": event_name,
                "headline": event_name,
                "phenomena": phenom,
                "significance": sig,
                "isMarine": is_marine,
                "senderCode": wfo,
                "gtype": gtype,
                "nws_ugc": nws_ugc,
                "status": status,
                "parameters": {
                    "WFOidentifier": wfo,
                    "AWIPSidentifier": wfo,
                    "NWSidentifier": wfo,
                },
            }
            features.append(
                {"type": "Feature", "properties": props, "geometry": mapping(geom)}
            )

    except Exception as e:
        print(f"[WARN] Error parsing IEM live shapefile: {e}")
        features = []
    finally:
        import shutil

        shutil.rmtree(tmpdir, ignore_errors=True)

    try:
        with open(cache_file, "w") as f:
            json.dump({"_source": "IEM", "features": features}, f)
    except Exception:
        pass

    return features
