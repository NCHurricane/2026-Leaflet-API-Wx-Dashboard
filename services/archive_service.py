"""Historical archive endpoint services."""

from datetime import datetime, timedelta, timezone
import json
import os
import shutil

from fastapi import HTTPException

from app_core.http import validate_archive_range
from config.geo_config import STATE_BOUNDS
from services.alerts_service import enrich_alert_features_geometry
from services.surface_service import (
    SURFACE_PRODUCTS,
    build_surface_stations,
    fetch_surface_archive_at_time,
    fetch_surface_archive_frames,
)

_ARCHIVE_JSON_DIR = os.path.join("cache", "archive", "json")
os.makedirs(_ARCHIVE_JSON_DIR, exist_ok=True)

_SURFACE_ARCHIVE_AUTO_SOURCES = {"auto", "iem"}
_SURFACE_SOURCE_ATTR = "surface_source"

_SURFACE_ARCHIVE_PRODUCT_MAP = {
    "station_plot": "Station Plot",
    "temperature": "Temperature",
    "feels_like": "Feels Like",
    "dew_point": "Dewpoint",
    "relative_humidity": "Relative Humidity",
    "wind_speed": "Wind Speed",
    "wind_gust": "Wind Gust",
    "altimeter": "Altimeter",
    "mslp": "MSLP",
    "visibility": "Visibility",
}


def _parse_archive_dt(value: str) -> datetime:
    """Parse ISO 8601 or YYYY-MM-DDTHH:MM string to UTC datetime."""
    normalized = str(value or "").strip()
    if normalized.endswith(("Z", "z")):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        pass

    for fmt in (
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(normalized, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError(
        f"Cannot parse date '{value}'. Use ISO 8601, e.g. 2026-04-16T18:00."
    )


def _archive_cache_path(prefix: str, **params) -> str:
    """Return a deterministic file path for an archive query."""
    import hashlib

    key = json.dumps(params, sort_keys=True, default=str)
    digest = hashlib.sha256(key.encode()).hexdigest()[:16]
    return os.path.join(_ARCHIVE_JSON_DIR, f"{prefix}_{digest}.json")


def _read_archive_cache(path: str) -> dict | None:
    """Return cached JSON dict or None."""
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None


def _write_archive_cache(path: str, data: dict) -> None:
    """Persist JSON dict to disk."""
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, separators=(",", ":"))
    except Exception:
        pass


def _surface_frame_source(df) -> str:
    source = getattr(df, "attrs", {}).get(_SURFACE_SOURCE_ATTR)
    return str(source or "unknown").strip().lower()


def get_archive_alerts(
    date_from: str = "",
    date_to: str = "",
    state: str = "",
) -> dict:
    if not date_from or not date_to:
        raise HTTPException(
            status_code=400, detail="date_from and date_to are required."
        )
    try:
        dt_from = _parse_archive_dt(date_from)
        dt_to = _parse_archive_dt(date_to)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if (dt_to - dt_from).total_seconds() > 30 * 24 * 3600:
        raise HTTPException(
            status_code=400, detail="Max alerts archive span is 30 days."
        )
    state_upper = state.upper() if state else ""
    cache_file = _archive_cache_path(
        "alerts",
        date_from=dt_from.isoformat(),
        date_to=dt_to.isoformat(),
        state=state_upper,
    )
    cached = _read_archive_cache(cache_file)
    if cached is not None:
        enrich_alert_features_geometry(cached.get("features", []))
        return cached
    try:
        features = _fetch_iem_alerts_range(dt_from, dt_to, state_upper or None)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"IEM fetch error: {exc}")
    enrich_alert_features_geometry(features)
    result = {
        "type": "FeatureCollection",
        "features": features,
        "count": len(features),
        "date_from": dt_from.isoformat(),
        "date_to": dt_to.isoformat(),
        "_source": "iem_watchwarn",
    }
    _write_archive_cache(cache_file, result)
    return result

def _fetch_iem_alerts_range(
    dt_from: datetime, dt_to: datetime, state: str | None
) -> list:
    """Call IEM WatchWarn with explicit start/end and return GeoJSON features."""
    import io
    import tempfile
    import zipfile
    from app_core.upstream_ledger import requests as _requests
    from alerts.alerts_iem_utils import IEM_WATCHWARN_URL, _event_name_from_attrs

    utc_from = dt_from.astimezone(timezone.utc)
    utc_to = dt_to.astimezone(timezone.utc)
    lookback = timedelta(hours=72)
    query_from = utc_from - lookback

    headers = {"User-Agent": "(NCHurricane.com Weather Suite, contact@nchurricane.com)"}

    def _build_url(with_state: bool) -> str:
        url = (
            f"{IEM_WATCHWARN_URL}"
            f"?year1={query_from.year}&month1={query_from.month}&day1={query_from.day}"
            f"&hour1={query_from.hour}&minute1={query_from.minute}"
            f"&year2={utc_to.year}&month2={utc_to.month}&day2={utc_to.day}"
            f"&hour2={utc_to.hour}&minute2={utc_to.minute}"
            f"&simple=yes&fmt=shp"
        )
        if with_state and state:
            url += f"&states={state}"
        return url

    resp = None
    for use_state in [True, False] if state else [False]:
        try:
            resp = _requests.get(
                _build_url(use_state), headers=headers, timeout=(5, 30)
            )
            resp.raise_for_status()
            break
        except Exception:
            resp = None
    if resp is None:
        return []

    tmpdir = tempfile.mkdtemp(prefix="iem_arc_")
    features = []
    try:
        with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
            z.extractall(tmpdir)
        shp_files = [f for f in os.listdir(tmpdir) if f.endswith(".shp")]
        if not shp_files:
            return []
        import cartopy.io.shapereader as shpreader

        reader = shpreader.Reader(os.path.join(tmpdir, shp_files[0]))
        for rec in reader.records():
            geom = rec.geometry
            if geom is None:
                continue
            try:
                geom_json = geom.__geo_interface__
            except Exception:
                continue
            attrs = rec.attributes
            event = _event_name_from_attrs(attrs) or str(attrs.get("PHENOM", ""))

            def _iem_to_iso(raw: str) -> str:
                text = str(raw or "").strip()
                if len(text) >= 12:
                    try:
                        dt = datetime(
                            int(text[0:4]),
                            int(text[4:6]),
                            int(text[6:8]),
                            int(text[8:10]),
                            int(text[10:12]),
                            tzinfo=timezone.utc,
                        )
                        return dt.isoformat()
                    except Exception:
                        pass
                return text

            features.append(
                {
                    "type": "Feature",
                    "geometry": geom_json,
                    "properties": {
                        "event": event,
                        "onset": _iem_to_iso(str(attrs.get("ISSUED", ""))),
                        "expires": _iem_to_iso(str(attrs.get("EXPIRED", ""))),
                        "areaDesc": str(attrs.get("AREA_DESC", "")),
                        "_source": "iem_archive",
                    },
                }
            )
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return features


def get_archive_surface(
    region: str = "NC",
    product: str = "temperature",
    date_from: str = "",
    date_to: str = "",
    max_frames: int = 120,
    source: str = "iem",
    network: str = "ASOS",
) -> dict:
    if not date_from or not date_to:
        raise HTTPException(
            status_code=400, detail="date_from and date_to are required."
        )
    if not 1 <= int(max_frames) <= 120:
        raise HTTPException(status_code=400, detail="max_frames must be 1-120.")

    try:
        dt_from = _parse_archive_dt(date_from)
        dt_to = _parse_archive_dt(date_to)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if dt_to <= dt_from:
        raise HTTPException(status_code=400, detail="date_to must be after date_from.")
    validate_archive_range("surface", dt_from, dt_to)

    product_key = str(product or "").strip().lower()
    if product_key not in SURFACE_PRODUCTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown product '{product}'. Valid: {list(SURFACE_PRODUCTS.keys())}",
        )

    region_upper = str(region or "NC").strip().upper()
    if region_upper not in STATE_BOUNDS:
        region_upper = "NC"

    requested_source = str(source or "iem").strip().lower()
    if requested_source not in _SURFACE_ARCHIVE_AUTO_SOURCES:
        raise HTTPException(
            status_code=400,
            detail="Surface archive source must be 'auto' or 'iem'.",
        )
    # Retain "iem" as a compatibility alias for the established AWC-first
    # selection with IEM fallback; provenance below reports the actual provider.
    source_key = "auto"

    if region_upper == "WORLD":
        raise HTTPException(
            status_code=400,
            detail="Historical WORLD surface archive is not supported.",
        )

    network_key = str(network or "ASOS").strip().upper()
    if network_key != "ASOS":
        raise HTTPException(
            status_code=400,
            detail="Only ASOS network is supported for surface archive.",
        )

    total = int(max_frames)
    frame_times = []
    cursor = dt_from
    while cursor <= dt_to and len(frame_times) < total:
        frame_times.append(cursor)
        cursor += timedelta(minutes=15)
    if not frame_times:
        frame_times = [dt_from]

    cache_file = _archive_cache_path(
        "surface",
        region=region_upper,
        product=product_key,
        date_from=dt_from.isoformat(),
        date_to=dt_to.isoformat(),
        max_frames=total,
        source=source_key,
    )
    cached = _read_archive_cache(cache_file)
    if cached is not None:
        return cached

    try:
        frame_dfs = fetch_surface_archive_frames(region_upper, frame_times, source_key)
    except Exception:
        frame_dfs = [None] * len(frame_times)

    frames = []
    for idx, ts in enumerate(frame_times):
        df = None
        try:
            df = frame_dfs[idx] if idx < len(frame_dfs) else None
            if df is None:
                df = fetch_surface_archive_at_time(region_upper, ts, source_key)
            stations = build_surface_stations(df, product_key)
        except Exception:
            stations = []

        frame_source = _surface_frame_source(df)

        frames.append(
            {
                "timestamp": ts.isoformat(),
                "stations": stations,
                "product": product_key,
                "unit": SURFACE_PRODUCTS[product_key]["unit"],
                "source": frame_source,
            }
        )

    frame_sources = {
        frame["source"] for frame in frames if frame["source"] != "unknown"
    }
    if len(frame_sources) == 1:
        result_source = next(iter(frame_sources))
    elif len(frame_sources) > 1:
        result_source = "mixed"
    else:
        result_source = "unknown"

    result = {
        "status": "success",
        "type": "surface_archive",
        "region": region_upper,
        "product": product_key,
        "product_label": _SURFACE_ARCHIVE_PRODUCT_MAP.get(product_key, product_key),
        "source": result_source,
        "network": "ASOS",
        "date_from": dt_from.isoformat(),
        "date_to": dt_to.isoformat(),
        "frame_count": len(frames),
        "frames": frames,
    }
    _write_archive_cache(cache_file, result)
    return result
