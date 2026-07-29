"""Radar metadata, tile proxy, and live-frame services."""

from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
import re
import threading

from fastapi import HTTPException
from fastapi.responses import FileResponse, Response

from app_core.http import parse_utc_datetime
from app_core.paths import BASE_DIR, CACHE_ROOT
from app_core.refresh_coordinator import get_refresh_coordinator

RADAR_SITE_ALIASES = {
    "KILM": "KLTX",
    "KRAH": "KRAX",
    "KRNK": "KFCX",
    "KABQ": "KABX",
    "KALY": "KENX",
    "KBOI": "KCBX",
    "KBOU": "KFTG",
    "KBTV": "KCXX",
    "KBYZ": "KBLX",
    "KCAR": "KCBW",
    "KCHS": "KCLX",
    "KCTP": "KCCX",
    "KEKA": "KBHX",
    "KFGF": "KMVX",
    "KFGZ": "KFSX",
    "KFWD": "KFWS",
    "KGID": "KUEX",
    "KGJT": "KGJX",
    "KHUN": "KHTX",
    "KJAN": "KDGX",
    "KKEY": "KBYX",
    "KLBF": "KLNX",
    "KLKN": "KLRX",
    "KLMK": "KLVX",
    "KLOX": "KVTX",
    "KLUB": "KLBB",
    "KMEG": "KNQA",
    "KMFL": "KAMX",
    "KMFR": "KMAX",
    "KMSO": "KMSX",
    "KMTR": "KMUX",
    "KOUN": "KTLX",
    "KPHI": "KDIX",
    "KPIH": "KSFX",
    "KPQR": "KRTX",
    "KPSR": "KIWA",
    "KPUB": "KPUX",
    "KREV": "KRGX",
    "KSEW": "KATX",
    "KSGX": "KNKX",
    "KSLC": "KMTX",
    "KSTO": "KDAX",
    "KTAE": "KTLH",
    "KTOP": "KTWX",
    "KTSA": "KINX",
    "KTWC": "KEMX",
    "KUNR": "KUDX",
    "KVEF": "KESX",
}


def normalize_radar_site_id(site: str) -> str:
    site_id = str(site or "").strip().upper()
    return RADAR_SITE_ALIASES.get(site_id, site_id)


def get_radar_sites_data() -> dict:
    try:
        sites_path = os.path.join(BASE_DIR, "radar", "radar_sites.json")
        with open(sites_path, "r", encoding="utf-8") as fh:
            raw_sites = json.load(fh)

        if not isinstance(raw_sites, dict):
            raise ValueError("radar_sites.json is not a key/value object")

        sites = [
            {"label": label, "value": value}
            for label, value in raw_sites.items()
            if isinstance(label, str) and isinstance(value, str)
        ]
        sites.sort(key=lambda entry: entry["label"])

        return {
            "status": "success",
            "sites": sites,
            "count": len(sites),
        }
    except Exception as exc:
        print(f"Radar sites endpoint error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


def get_radar_site_locations_data() -> dict:
    try:
        from pyart.io.nexrad_common import NEXRAD_LOCATIONS

        valid_prefixes = ("K", "P")
        valid_extras = {"TJUA"}

        sites = []
        seen = set()
        for site_id, info in NEXRAD_LOCATIONS.items():
            if not (site_id.startswith(valid_prefixes) or site_id in valid_extras):
                continue

            normalized_id = normalize_radar_site_id(site_id)
            if normalized_id in seen:
                continue

            lat = info.get("lat")
            lon = info.get("lon")
            if lat is None or lon is None:
                continue

            seen.add(normalized_id)
            sites.append(
                {
                    "site": normalized_id,
                    "lat": float(lat),
                    "lon": float(lon),
                }
            )

        sites.sort(key=lambda entry: entry["site"])
        return {
            "status": "success",
            "sites": sites,
            "count": len(sites),
        }
    except Exception as exc:
        print(f"Radar site locations endpoint error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


def _radar_live_catalog():
    from config.radar_config import LIVE_RADAR_PRODUCTS

    return dict(LIVE_RADAR_PRODUCTS)


def _radar_webgl_config() -> dict:
    from radar.webgl_artifact import feature_config

    return feature_config()


def _radar_webgl_artifact_metadata(
    frame: dict,
    site: str,
    product: str,
    requested_elevation: str,
) -> dict | None:
    from radar.webgl_artifact import artifact_metadata

    return artifact_metadata(
        CACHE_ROOT,
        site,
        product,
        frame.get("selected_elevation") or requested_elevation,
        frame.get("frame_key") or frame.get("source_data_key", ""),
    )


def _radar_live_product_metadata(product_key: str) -> dict:
    product_id = str(product_key or "").strip().upper()
    return dict(_radar_live_catalog().get(product_id) or {})


def normalize_radar_elevation(product_key: str, elevation: str | float | None) -> str:
    product_id = str(product_key or "").strip().upper()
    if not product_id.startswith("L2_"):
        return "auto"
    value = str(elevation or "auto").strip().lower()
    if not value or value == "auto":
        return "auto"
    try:
        angle = float(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Elevation must be 'auto' or a number.") from exc
    if angle < 0.0 or angle > 90.0:
        raise HTTPException(status_code=422, detail="Elevation must be between 0 and 90 degrees.")
    return f"{angle:.1f}"


def normalize_radar_srv_motion(
    product_key: str,
    storm_motion_speed_kt: str | float | None = None,
    storm_motion_to_degrees: str | float | None = None,
    storm_motion_source: str | None = None,
    storm_cell_id: str | None = None,
) -> dict | None:
    product_id = str(product_key or "").strip().upper()
    if product_id != "L2_SRV":
        return None
    if storm_motion_speed_kt in (None, "") or storm_motion_to_degrees in (None, ""):
        return None
    try:
        speed = round(float(storm_motion_speed_kt))
        direction = round(float(storm_motion_to_degrees)) % 360
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail="Storm motion speed/direction must be numeric.",
        ) from exc
    if speed < 0 or speed > 150:
        raise HTTPException(
            status_code=422,
            detail="Storm motion speed must be between 0 and 150 kt.",
        )
    source = str(storm_motion_source or "manual").strip().upper()
    source = re.sub(r"[^A-Z0-9]+", "_", source).strip("_")[:12] or "MANUAL"
    cell = str(storm_cell_id or "").strip().upper()
    cell = re.sub(r"[^A-Z0-9]+", "_", cell).strip("_")[:12]
    variant_parts = [source]
    if cell:
        variant_parts.append(f"CELL_{cell}")
    variant_parts.append(f"{speed:03d}KT_TO{direction:03d}")
    variant_parts.append("V1")
    return {
        "speed_kt": float(speed),
        "motion_to_degrees": float(direction),
        "source": source,
        "cell_id": cell,
        "cache_variant": "_".join(variant_parts).lower(),
    }


def _radar_product_metadata_with_motion(product_key: str, motion: dict | None) -> dict:
    metadata = _radar_live_product_metadata(product_key)
    if not motion:
        return metadata
    metadata["storm_motion_speed_kt"] = float(motion["speed_kt"])
    metadata["storm_motion_to_degrees"] = float(motion["motion_to_degrees"])
    metadata["cache_variant"] = motion["cache_variant"]
    metadata["motion_source"] = motion.get("source")
    metadata["storm_cell_id"] = motion.get("cell_id")
    return metadata


def radar_cache_product_key(
    product_key: str, elevation: str, motion: dict | None = None
) -> str:
    product_id = str(product_key or "").strip().upper()
    cache_variant = str(
        _radar_product_metadata_with_motion(product_id, motion).get("cache_variant")
        or ""
    ).strip().upper()
    if cache_variant:
        product_id = f"{product_id}__{cache_variant}"
    if not product_id.startswith("L2_"):
        return product_id
    suffix = "AUTO" if elevation == "auto" else elevation.replace(".", "P")
    return f"{product_id}__ELEV_{suffix}"


def _radar_live_sites():
    from config.radar_config import LIVE_RADAR_SITES

    return [normalize_radar_site_id(site) for site in LIVE_RADAR_SITES]


_RADAR_LIVE_FALLBACK_LOCKS: dict[tuple[str, str], threading.Lock] = {}
_RADAR_LIVE_FALLBACK_LOCKS_GUARD = threading.Lock()
_RADAR_EMPTY_CACHE_RESPONSE_SYNC_FRAMES = 1

_NWS_RADAR_STATUS_CACHE: dict | None = None
_NWS_RADAR_STATUS_CACHE_TS: float = 0.0
_NWS_RADAR_STATUS_CACHE_LOCK = threading.Lock()
_NWS_RADAR_STATUS_TTL_SEC = 300


def _fetch_nws_radar_status() -> dict:
    """Fetch and cache radar station status from NWS API."""
    import time
    import urllib.request as _ur

    global _NWS_RADAR_STATUS_CACHE, _NWS_RADAR_STATUS_CACHE_TS

    now = time.monotonic()
    with _NWS_RADAR_STATUS_CACHE_LOCK:
        if (
            _NWS_RADAR_STATUS_CACHE is not None
            and (now - _NWS_RADAR_STATUS_CACHE_TS) < _NWS_RADAR_STATUS_TTL_SEC
        ):
            return _NWS_RADAR_STATUS_CACHE

    try:
        req = _ur.Request(
            "https://api.weather.gov/radar/stations",
            headers={
                "User-Agent": "2026-Dashboard/1.0 (github.com/NCHurricane)",
                "Accept": "application/geo+json",
            },
        )
        from app_core.upstream_ledger import urlopen

        with urlopen(req, timeout=15) as resp:
            raw = json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as exc:
        print(f"[radar status] NWS fetch failed: {exc}")
        with _NWS_RADAR_STATUS_CACHE_LOCK:
            return _NWS_RADAR_STATUS_CACHE or {}

    status_map: dict = {}
    features = raw.get("features", []) if isinstance(raw, dict) else []
    for feat in features:
        props = feat.get("properties", {}) if isinstance(feat, dict) else {}
        site_id = str(props.get("id") or "").strip().upper()
        if not site_id:
            continue
        rda = props.get("rda") or {}
        rda_props = rda.get("properties") or {}
        latency = props.get("latency") or {}
        status_map[site_id] = {
            "operabilityStatus": rda_props.get("operabilityStatus", ""),
            "status": rda_props.get("status", ""),
            "alarmSummary": rda_props.get("alarmSummary", ""),
            "volumeCoveragePattern": rda_props.get("volumeCoveragePattern", ""),
            "mode": rda_props.get("mode", ""),
            "rdaTimestamp": rda.get("timestamp", ""),
            "levelTwoLastReceived": latency.get("levelTwoLastReceivedTime", ""),
        }

    with _NWS_RADAR_STATUS_CACHE_LOCK:
        _NWS_RADAR_STATUS_CACHE = status_map
        _NWS_RADAR_STATUS_CACHE_TS = now
    return status_map


def _is_conus_site(site: str) -> bool:
    """Check if a site is in CONUS based on its coordinates.

    CONUS bounds: lat 21-52°N, lon -140 to -65°W
    Returns False for Alaska, Hawaii, Puerto Rico, and overseas sites.
    """
    try:
        from pyart.io.nexrad_common import NEXRAD_LOCATIONS

        site_id = normalize_radar_site_id(site)

        # Check Py-ART first
        info = NEXRAD_LOCATIONS.get(site_id)
        if info:
            lat = info.get("lat")
            lon = info.get("lon")
            if lat is not None and lon is not None:
                return 21.0 <= lat <= 52.0 and -140.0 <= lon <= -65.0

        # Fall back to our comprehensive coordinates
        try:
            import importlib.util
            coords_path = os.path.join(BASE_DIR, "radar", "nexrad_coordinates.py")
            spec = importlib.util.spec_from_file_location("nexrad_coordinates", coords_path)
            nexrad_coords_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(nexrad_coords_module)
            coords = nexrad_coords_module.NEXRAD_SITE_COORDINATES.get(site_id)
            if coords:
                lat, lon = coords
                return 21.0 <= lat <= 52.0 and -140.0 <= lon <= -65.0
        except Exception:
            pass
    except Exception:
        pass

    return False


def _radar_live_site_supported(site: str) -> bool:
    try:
        from pyart.io.nexrad_common import NEXRAD_LOCATIONS

        site_id = normalize_radar_site_id(site)

        # Check Py-ART first
        info = NEXRAD_LOCATIONS.get(site_id)
        if info and info.get("lat") is not None and info.get("lon") is not None:
            return True

        # Fall back to our comprehensive coordinates mapping
        try:
            import importlib.util
            coords_path = os.path.join(BASE_DIR, "radar", "nexrad_coordinates.py")
            spec = importlib.util.spec_from_file_location("nexrad_coordinates", coords_path)
            nexrad_coords_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(nexrad_coords_module)
            return site_id in nexrad_coords_module.NEXRAD_SITE_COORDINATES
        except Exception:
            pass

        return False
    except Exception:
        return False


def _radar_live_product_supported(product_key: str) -> bool:
    return str(product_key or "").strip().upper() in _radar_live_catalog()


def _radar_live_fallback_lock(site: str, product_key: str) -> threading.Lock:
    key = (normalize_radar_site_id(site), str(product_key or "").strip().upper())
    with _RADAR_LIVE_FALLBACK_LOCKS_GUARD:
        lock = _RADAR_LIVE_FALLBACK_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _RADAR_LIVE_FALLBACK_LOCKS[key] = lock
        return lock


def _radar_live_render_on_demand(
    site: str,
    product_key: str,
    *,
    latest_only: bool = True,
    backfill_history: bool = True,
    newest_first: bool = False,
    max_render_frames: int | None = None,
    elevation: str = "auto",
    motion: dict | None = None,
    lookback_hours: float | None = None,
) -> int:
    from workers.radar_live_worker import run_radar_live_site_product
    from config.radar_config import normalize_live_radar_lookback_hours

    site_id = normalize_radar_site_id(site)
    product_id = str(product_key or "").strip().upper()
    requested_lookback = normalize_live_radar_lookback_hours(lookback_hours)

    lock = _radar_live_fallback_lock(site_id, product_id)
    with lock:
        cached = int(
            run_radar_live_site_product(
                site_id,
                product_id,
                force=True,
                latest_only=latest_only,
                newest_first=newest_first,
                max_render_frames=max_render_frames,
                elevation=elevation,
                storm_motion=motion,
                lookback_hours=requested_lookback,
            )
        )

    if not backfill_history:
        return cached
    if cached <= 0:
        return cached
    if not latest_only and max_render_frames is None:
        return cached

    _radar_live_render_in_background(
        site_id,
        product_id,
        elevation,
        motion,
        requested_lookback,
    )
    return cached


def _radar_live_render_bg_key(
    site_id: str, product_key: str, elevation: str, motion: dict | None
) -> tuple:
    motion_key = str((motion or {}).get("cache_variant") or "default")
    level_code = "L2" if product_key.startswith("L2_") else "L3"
    return (
        "radar-live",
        site_id,
        level_code,
        product_key,
        elevation,
        motion_key,
    )


def _radar_live_render_in_background(
    site_id: str,
    product_key: str,
    elevation: str = "auto",
    motion: dict | None = None,
    lookback_hours: float | None = None,
    *,
    urgent: bool = False,
) -> bool:
    """Renew selected-radar presence and progressively fill its frame window."""
    from config.radar_config import (
        LIVE_RADAR_BACKFILL_BATCH_FRAMES,
        LIVE_RADAR_L2_USE_CHUNKS,
        LIVE_RADAR_WORKER_INTERVAL_MIN,
    )

    key = _radar_live_render_bg_key(site_id, product_key, elevation, motion)
    is_l2_chunks = product_key.startswith("L2_") and LIVE_RADAR_L2_USE_CHUNKS
    interval_seconds = (
        45.0
        if is_l2_chunks
        else max(60.0, float(LIVE_RADAR_WORKER_INTERVAL_MIN or 5) * 60.0)
    )
    submission = get_refresh_coordinator().activate_presence_job(
        key=key,
        provider="nodd-radar",
        interval_seconds=interval_seconds,
        min_success_interval_seconds=0.0 if urgent else interval_seconds,
        function=lambda: _radar_live_render_on_demand(
            site_id,
            product_key,
            latest_only=False,
            backfill_history=False,
            newest_first=True,
            max_render_frames=LIVE_RADAR_BACKFILL_BATCH_FRAMES,
            elevation=elevation,
            motion=motion,
            lookback_hours=lookback_hours,
        ),
    )
    return submission.status in {"queued", "running"}


def _radar_live_render_still_filling(
    site_id: str, product_key: str, elevation: str, motion: dict | None
) -> bool:
    """True when a background fill for this site/product is already in flight.

    Lets a poll that didn't itself trigger a render (frames already exist,
    refresh not requested) still report accurate "still filling" status when an
    earlier request's background render is the one actually still running.
    """
    key = _radar_live_render_bg_key(site_id, product_key, elevation, motion)
    coordinator = get_refresh_coordinator()
    state = coordinator.describe(key) or {}
    return coordinator.is_lease_active(key) and state.get("status") in {
        "queued",
        "running",
    }


def _radar_live_is_configured(site: str, product_key: str) -> bool:
    return site in set(_radar_live_sites()) and product_key in _radar_live_catalog()


def _radar_live_latest_meta_dt(meta: dict | None) -> datetime | None:
    """Best-effort UTC datetime of a latest-frame meta dict, or None."""
    if not meta:
        return None

    dt = None
    ts = str(meta.get("timestamp") or "").strip()
    if ts:
        try:
            dt = parse_utc_datetime(ts)
        except Exception:
            dt = None

    if dt is None:
        frame_key = str(
            meta.get("frame_key") or meta.get("source_data_key") or ""
        ).strip()
        if frame_key:
            try:
                from cache.overlay_cache_utils import datetime_from_frame_key

                dt = datetime_from_frame_key(frame_key)
            except Exception:
                dt = None

    return dt


def _radar_live_filter_stale_latest_meta(
    meta: dict | None, *, max_age_hours: float
) -> dict | None:
    """Return latest-frame meta only when it is within the live lookback window."""
    dt = _radar_live_latest_meta_dt(meta)
    if dt is None:
        return None

    cutoff_dt = datetime.now(timezone.utc) - timedelta(
        hours=max(0.25, float(max_age_hours or 0.25))
    )
    return meta if dt >= cutoff_dt else None


_RADAR_COLORTABLE_PRODUCTS: dict[str, tuple[float, float]] = {
    "BR": (-30.0, 90.0),
    "BV": (-120.0, 120.0),
    "HCA": (0.0, 150.0),        # L3_N0H Hydrometeor Classification
    "DPA": (0.0, 8.0),          # L3_DPR Digital Precipitation Rate
    "DAA": (0.0, 4.0),          # L3_DAA One-Hour Accumulation
    "STP": (0.0, 18.0),         # L3_DTA Storm Total Accumulation
    "ET": (0.0, 70.0),          # L3_EET Echo Tops
    "VIL": (0.0, 80.0),         # L3_DVL Vertically Integrated Liquid
}


def get_radar_colortable_data(product: str = "BR") -> dict:
    """Return the legend color entries for a radar product colortable."""
    product_id = product.upper()
    product_metadata = _radar_live_product_metadata(product_id)
    palette = str(product_metadata.get("palette") or product_id).upper()
    if product_metadata:
        vmin = float(product_metadata["vmin"])
        vmax = float(product_metadata["vmax"])
    elif palette in _RADAR_COLORTABLE_PRODUCTS:
        vmin, vmax = _RADAR_COLORTABLE_PRODUCTS[palette]
    else:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No colortable for product '{product_id}'. "
                f"Valid palettes: {list(_RADAR_COLORTABLE_PRODUCTS)}"
            ),
        )
    raw_min_value = product_metadata.get("min_value") if product_metadata else None
    legend_vmin = float(raw_min_value) if raw_min_value is not None else None
    try:
        from config.radar_colortable_utils import get_legend_json

        entries = get_legend_json(palette, vmin, vmax, legend_vmin=legend_vmin)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {
        "product": product_id,
        "palette": palette,
        "vmin": vmin,
        "vmax": vmax,
        "legend_vmin": legend_vmin,
        "entries": entries,
    }


_RADAR_FRAME_LAYERS = {
    0: "nexrad-n0q-m20m",
    1: "nexrad-n0q-m15m",
    2: "nexrad-n0q-m10m",
    3: "nexrad-n0q-m05m",
    4: "nexrad-n0q",
}


def get_radar_alert_tile(z: str, x: str, y: str, frame: int = 4) -> Response:
    """Proxy IEM NEXRAD reflectivity tiles."""
    try:
        import urllib.request as ur

        layer = _RADAR_FRAME_LAYERS.get(frame, "nexrad-n0q")
        url = (
            "https://mesonet.agron.iastate.edu/cache/tile.py/1.0.0/"
            f"{layer}/{z}/{x}/{y}.png"
        )
        req = ur.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        from app_core.upstream_ledger import urlopen

        with urlopen(req, timeout=10) as resp:
            data = resp.read()
            return Response(
                content=data,
                media_type="image/png",
                headers={"Cache-Control": "public, max-age=3600, immutable"},
            )
    except Exception as exc:
        print(f"[radar tiles] Tile fetch error: {exc}")
        raise HTTPException(status_code=404, detail="Tile not found")


def head_radar_alert_tile() -> Response:
    """HEAD request for IEM NEXRAD radar tiles."""
    return Response(media_type="image/png")


def get_radar_tiles_freshness_data() -> dict:
    """Return Last-Modified header for current IEM nexrad-n0q tile."""
    try:
        import urllib.request as ur

        url = (
            "https://mesonet.agron.iastate.edu/cache/tile.py/1.0.0/"
            "nexrad-n0q/4/4/6.png"
        )
        req = ur.Request(url, headers={"User-Agent": "Mozilla/5.0"}, method="HEAD")
        from app_core.upstream_ledger import urlopen

        with urlopen(req, timeout=8) as resp:
            return {"last_modified": resp.headers.get("Last-Modified", "")}
    except Exception as exc:
        print(f"[radar tiles] Freshness check error: {exc}")
        return {"last_modified": ""}


def get_radar_status_data() -> dict:
    """Return NWS radar station operational status for all sites."""
    try:
        status = _fetch_nws_radar_status()
        return {
            "status": "success",
            "stations": status,
            "count": len(status),
        }
    except Exception as exc:
        print(f"[radar status] Endpoint error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


def get_radar_live_sites_data() -> dict:
    """Return radar sites with configured live-cache flag.

    Uses Py-ART's NEXRAD_LOCATIONS as the primary source, with fallback to
    a comprehensive NEXRAD coordinate mapping for sites not in Py-ART.
    """
    try:
        from pyart.io.nexrad_common import NEXRAD_LOCATIONS

        # Load fallback coordinates from the nexrad_coordinates module
        try:
            import sys
            import importlib.util
            coords_path = os.path.join(BASE_DIR, "radar", "nexrad_coordinates.py")
            spec = importlib.util.spec_from_file_location("nexrad_coordinates", coords_path)
            nexrad_coords_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(nexrad_coords_module)
            NEXRAD_SITE_COORDINATES = nexrad_coords_module.NEXRAD_SITE_COORDINATES
        except Exception as e:
            print(f"Warning: Could not load NEXRAD_SITE_COORDINATES: {e}")
            NEXRAD_SITE_COORDINATES = {}

        configured = set(_radar_live_sites())

        valid_prefixes = ("K", "P", "R")  # K=CONUS, P=Pacific/Alaska/Guam, R=Overseas military
        valid_extras = {"TJUA"}

        sites = []
        seen = set()

        # First pass: get sites from Py-ART
        for site_id, info in NEXRAD_LOCATIONS.items():
            if not (site_id.startswith(valid_prefixes) or site_id in valid_extras):
                continue
            normalized_id = normalize_radar_site_id(site_id)
            if normalized_id in seen:
                continue
            lat = info.get("lat")
            lon = info.get("lon")
            if lat is None or lon is None:
                continue
            seen.add(normalized_id)
            is_conus = _is_conus_site(normalized_id)
            sites.append(
                {
                    "site": normalized_id,
                    "lat": float(lat),
                    "lon": float(lon),
                    "configured": normalized_id in configured,
                    "conus": is_conus,
                }
            )

        # Second pass: add sites from fallback coordinates that aren't in Py-ART
        for site_id, (lat, lon) in NEXRAD_SITE_COORDINATES.items():
            normalized_id = normalize_radar_site_id(site_id)
            if normalized_id in seen:
                continue
            if not (normalized_id.startswith(valid_prefixes) or normalized_id in valid_extras):
                continue
            seen.add(normalized_id)
            is_conus = _is_conus_site(normalized_id)
            sites.append(
                {
                    "site": normalized_id,
                    "lat": float(lat),
                    "lon": float(lon),
                    "configured": normalized_id in configured,
                    "conus": is_conus,
                }
            )

        sites.sort(key=lambda entry: (0 if entry["configured"] else 1, entry["site"]))
        return {
            "status": "success",
            "sites": sites,
            "configured_sites": sorted(configured),
            "products": _radar_live_catalog(),
            "webgl": _radar_webgl_config(),
            "count": len(sites),
        }
    except Exception as exc:
        print(f"Radar live sites endpoint error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


def get_radar_live_products_data() -> dict:
    """Return the complete live radar products catalog."""
    try:
        catalog = _radar_live_catalog()
        return {
            "status": "success",
            "products": catalog,
            "count": len(catalog),
        }
    except Exception as exc:
        print(f"Radar products endpoint error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


def get_radar_live_latest_data(
    site: str = "KMHX",
    product: str = "L3_N0B",
    elevation: str = "auto",
    force: bool = False,
    storm_motion_speed_kt: str | float | None = None,
    storm_motion_to_degrees: str | float | None = None,
    storm_motion_source: str | None = None,
    storm_cell_id: str | None = None,
) -> dict:
    """Return latest live radar frame from cache."""
    from cache.overlay_cache_utils import radar_read_latest_frame
    from config.radar_config import (
        LIVE_RADAR_LOOKBACK_HOURS,
        LIVE_RADAR_WORKER_INTERVAL_MIN,
    )

    site_id = normalize_radar_site_id(site)
    product_key = str(product or "L3_N0B").strip().upper()
    elevation_key = normalize_radar_elevation(product_key, elevation)
    motion = normalize_radar_srv_motion(
        product_key,
        storm_motion_speed_kt,
        storm_motion_to_degrees,
        storm_motion_source,
        storm_cell_id,
    )
    cache_product_key = radar_cache_product_key(product_key, elevation_key, motion)
    configured = _radar_live_is_configured(site_id, product_key)
    level_code = "L2" if product_key.startswith("L2_") else "L3"
    freshness_hours = max(0.25, float(LIVE_RADAR_LOOKBACK_HOURS or 3.0))

    if not _radar_live_product_supported(product_key):
        raise HTTPException(
            status_code=404,
            detail=f"Live radar product is not supported: {product_key}.",
        )
    if not _radar_live_site_supported(site_id):
        raise HTTPException(
            status_code=404,
            detail=f"Live radar site is not supported: {site_id}.",
        )

    meta = _radar_live_filter_stale_latest_meta(
        radar_read_latest_frame(CACHE_ROOT, site_id, level_code, cache_product_key),
        max_age_hours=freshness_hours,
    )
    fallback_cached = 0
    if force and meta:
        meta_dt = _radar_live_latest_meta_dt(meta)
        recent_cutoff = datetime.now(timezone.utc) - timedelta(
            minutes=float(LIVE_RADAR_WORKER_INTERVAL_MIN or 5) + 1.0
        )
        if meta_dt is not None and meta_dt >= recent_cutoff:
            force = False
    if force:
        try:
            fallback_cached = _radar_live_render_on_demand(
                site_id,
                product_key,
                latest_only=True,
                backfill_history=True,
                elevation=elevation_key,
                motion=motion,
            )
        except Exception as exc:
            print(
                f"[radar_live_fallback] forced latest {site_id}/{product_key} failed: "
                f"{type(exc).__name__}: {exc}"
            )
        meta = _radar_live_filter_stale_latest_meta(
            radar_read_latest_frame(CACHE_ROOT, site_id, level_code, cache_product_key),
            max_age_hours=freshness_hours,
        )

    if not meta:
        try:
            fallback_cached = _radar_live_render_on_demand(
                site_id,
                product_key,
                latest_only=True,
                backfill_history=True,
                elevation=elevation_key,
                motion=motion,
            )
        except Exception as exc:
            print(
                f"[radar_live_fallback] latest {site_id}/{product_key} failed: "
                f"{type(exc).__name__}: {exc}"
            )
        meta = _radar_live_filter_stale_latest_meta(
            radar_read_latest_frame(CACHE_ROOT, site_id, level_code, cache_product_key),
            max_age_hours=freshness_hours,
        )

    if not meta:
        try:
            fallback_cached = max(
                fallback_cached,
                _radar_live_render_on_demand(
                    site_id,
                    product_key,
                    latest_only=False,
                    backfill_history=True,
                    newest_first=True,
                    max_render_frames=1,
                    elevation=elevation_key,
                    motion=motion,
                ),
            )
        except Exception as exc:
            print(
                f"[radar_live_fallback] full latest {site_id}/{product_key} failed: "
                f"{type(exc).__name__}: {exc}"
            )
        meta = _radar_live_filter_stale_latest_meta(
            radar_read_latest_frame(CACHE_ROOT, site_id, level_code, cache_product_key),
            max_age_hours=freshness_hours,
        )
    if not meta:
        raise HTTPException(
            status_code=404,
            detail="No live radar frame cached yet within lookback window.",
        )

    image_url = (meta.get("render") or {}).get("image_url")
    if not image_url:
        raise HTTPException(
            status_code=404, detail="Latest live radar image is missing."
        )

    activity_active = _radar_live_render_in_background(
        site_id,
        product_key,
        elevation_key,
        motion,
        freshness_hours,
    )
    payload = {
        "status": "success",
        "source": (
            "live_cache_forced"
            if force and fallback_cached > 0
            else "live_cache_fallback"
            if fallback_cached > 0
            else "live_cache"
        ),
        "history_filling": activity_active,
        "configured": configured,
        "site": site_id,
        "product": product_key,
        "product_capabilities": _radar_live_product_metadata(product_key).get(
            "capabilities", {}
        ),
        "provider": "NODD-AWS",
        "network": "NEXRAD",
        "timestamp": meta.get("timestamp"),
        "source_timestamp": meta.get("timestamp"),
        "frame_key": meta.get("frame_key") or meta.get("source_data_key", ""),
        "available_elevations": meta.get("available_elevations") or [],
        "selected_elevation": meta.get("selected_elevation"),
        "requested_elevation": elevation_key,
        "storm_motion": motion,
        "source_data_key": meta.get("source_data_key", ""),
        "image_url": image_url,
        "bounds": meta.get("bounds"),
        "full_name": meta.get("full_name", product_key),
        "units": meta.get("units", ""),
    }
    webgl_artifact = _radar_webgl_artifact_metadata(
        payload, site_id, product_key, elevation_key
    )
    if webgl_artifact is not None:
        payload["webgl_artifact"] = webgl_artifact
    return payload


def get_radar_live_frames_data(
    site: str = "KMHX",
    product: str = "L3_N0B",
    elevation: str = "auto",
    hours: float = 2,
    refresh: bool = False,
    storm_motion_speed_kt: str | float | None = None,
    storm_motion_to_degrees: str | float | None = None,
    storm_motion_source: str | None = None,
    storm_cell_id: str | None = None,
) -> dict:
    """Return live radar frames list for scrubber playback."""
    from cache.overlay_cache_utils import radar_list_frames
    from config.cache_config import (
        OVERLAY_EMPTY_CACHE_SYNC_FRAMES,
        OVERLAY_STALE_SERVE_WINDOW_MIN,
    )
    from config.radar_config import normalize_live_radar_lookback_hours

    site_id = normalize_radar_site_id(site)
    product_key = str(product or "L3_N0B").strip().upper()
    elevation_key = normalize_radar_elevation(product_key, elevation)
    motion = normalize_radar_srv_motion(
        product_key,
        storm_motion_speed_kt,
        storm_motion_to_degrees,
        storm_motion_source,
        storm_cell_id,
    )
    cache_product_key = radar_cache_product_key(product_key, elevation_key, motion)
    configured = _radar_live_is_configured(site_id, product_key)
    level_code = "L2" if product_key.startswith("L2_") else "L3"

    if not _radar_live_product_supported(product_key):
        raise HTTPException(
            status_code=404,
            detail=f"Live radar product is not supported: {product_key}.",
        )
    if not _radar_live_site_supported(site_id):
        raise HTTPException(
            status_code=404,
            detail=f"Live radar site is not supported: {site_id}.",
        )

    def _within(frame_list, cutoff):
        out = []
        for frame in frame_list:
            ts = frame.get("timestamp")
            if ts:
                try:
                    dt = parse_utc_datetime(ts)
                except Exception:
                    dt = None
            else:
                dt = None
            if dt and dt < cutoff:
                continue
            out.append(frame)
        return out

    def _render_newest_sync():
        try:
            return _radar_live_render_on_demand(
                site_id,
                product_key,
                latest_only=False,
                backfill_history=False,
                newest_first=True,
                max_render_frames=min(
                    _RADAR_EMPTY_CACHE_RESPONSE_SYNC_FRAMES,
                    OVERLAY_EMPTY_CACHE_SYNC_FRAMES,
                ),
                elevation=elevation_key,
                motion=motion,
                lookback_hours=requested_hours,
            )
        except Exception as exc:
            print(
                f"[radar_live_fallback] frames {site_id}/{product_key} failed: "
                f"{type(exc).__name__}: {exc}"
            )
            return 0

    requested_hours = normalize_live_radar_lookback_hours(hours)
    cutoff_dt = datetime.now(timezone.utc) - timedelta(hours=requested_hours)
    frames = radar_list_frames(CACHE_ROOT, site_id, level_code, cache_product_key)
    fallback_cached = 0
    refreshing = False

    if not frames:
        fallback_cached = _render_newest_sync()
        frames = radar_list_frames(CACHE_ROOT, site_id, level_code, cache_product_key)

    filtered = _within(frames, cutoff_dt) if frames else []

    if not filtered and frames:
        grace_min = OVERLAY_STALE_SERVE_WINDOW_MIN.get("radar_live", 15)
        filtered = _within(frames, cutoff_dt - timedelta(minutes=grace_min))
        if not filtered:
            fallback_cached = max(fallback_cached, _render_newest_sync())
            frames = radar_list_frames(CACHE_ROOT, site_id, level_code, cache_product_key)
            filtered = _within(frames, cutoff_dt)

    oldest_filtered_dt = None
    for frame in filtered:
        try:
            frame_dt = parse_utc_datetime(frame.get("timestamp"))
        except Exception:
            frame_dt = None
        if frame_dt is not None and (
            oldest_filtered_dt is None or frame_dt < oldest_filtered_dt
        ):
            oldest_filtered_dt = frame_dt
    coverage_complete = bool(
        oldest_filtered_dt
        and oldest_filtered_dt <= cutoff_dt + timedelta(minutes=10)
    )
    activity_active = _radar_live_render_in_background(
        site_id,
        product_key,
        elevation_key,
        motion,
        requested_hours,
        urgent=not coverage_complete,
    )
    refreshing = activity_active or _radar_live_render_still_filling(
        site_id, product_key, elevation_key, motion
    )
    history_filling = bool(not coverage_complete and refreshing)
    frames_with_artifacts = []
    for frame in filtered:
        artifact = _radar_webgl_artifact_metadata(
            frame, site_id, product_key, elevation_key
        )
        frames_with_artifacts.append(
            {**frame, "webgl_artifact": artifact} if artifact is not None else frame
        )
    filtered = frames_with_artifacts

    return {
        "status": "success",
        "source": "live_cache_fallback" if fallback_cached > 0 else "live_cache",
        "configured": configured,
        "site": site_id,
        "product": product_key,
        "product_capabilities": _radar_live_product_metadata(product_key).get(
            "capabilities", {}
        ),
        "provider": "NODD-AWS",
        "network": "NEXRAD",
        "available_elevations": (
            filtered[-1].get("available_elevations") if filtered else []
        ) or [],
        "selected_elevation": (
            filtered[-1].get("selected_elevation") if filtered else None
        ),
        "requested_elevation": elevation_key,
        "storm_motion": motion,
        "frame_count": len(filtered),
        "lookback_hours": requested_hours,
        "coverage_complete": coverage_complete,
        "history_filling": history_filling,
        "refreshing": refreshing,
        "frames": filtered,
    }


def get_radar_live_webgl_artifact_data(
    version: str,
    product: str,
    site: str,
    elevation: str,
    frame_key: str,
) -> FileResponse:
    """Serve a versioned artifact only while the Phase 6 feature is enabled."""
    from radar.webgl_artifact import resolve_artifact

    path = resolve_artifact(
        CACHE_ROOT, version, product, site, elevation, frame_key
    )
    if path is None:
        raise HTTPException(status_code=404, detail="Radar WebGL artifact unavailable.")
    return FileResponse(
        path,
        media_type="application/vnd.nchurricane.radar-polar",
        headers={"Cache-Control": "no-store"},
    )


def get_radar_live_value_data(
    site: str = "KMHX",
    product: str = "L3_N0B",
    elevation: str = "auto",
    frame_key: str | None = None,
    lat: float | str | None = None,
    lon: float | str | None = None,
    storm_motion_speed_kt: str | float | None = None,
    storm_motion_to_degrees: str | float | None = None,
    storm_motion_source: str | None = None,
    storm_cell_id: str | None = None,
) -> dict:
    """Sample the active live radar frame at a map lat/lon."""
    from cache.overlay_cache_utils import radar_list_frames, radar_read_latest_frame
    from workers.radar_live_worker import sample_live_radar_value

    try:
        lat_value = float(lat)
        lon_value = float(lon)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Valid lat and lon are required.")

    if not (-90.0 <= lat_value <= 90.0 and -180.0 <= lon_value <= 180.0):
        raise HTTPException(status_code=400, detail="Lat/lon is outside valid bounds.")

    site_id = normalize_radar_site_id(site)
    product_key = str(product or "L3_N0B").strip().upper()
    elevation_key = normalize_radar_elevation(product_key, elevation)
    motion = normalize_radar_srv_motion(
        product_key,
        storm_motion_speed_kt,
        storm_motion_to_degrees,
        storm_motion_source,
        storm_cell_id,
    )
    cache_product_key = radar_cache_product_key(product_key, elevation_key, motion)
    level_code = "L2" if product_key.startswith("L2_") else "L3"

    if not _radar_live_product_supported(product_key):
        raise HTTPException(
            status_code=404,
            detail=f"Live radar product is not supported: {product_key}.",
        )
    if not _radar_live_site_supported(site_id):
        raise HTTPException(
            status_code=404,
            detail=f"Live radar site is not supported: {site_id}.",
        )

    frames = radar_list_frames(CACHE_ROOT, site_id, level_code, cache_product_key)
    frame = None
    requested_frame_key = str(frame_key or "").strip()
    if requested_frame_key:
        frame = next(
            (
                item
                for item in frames
                if str(item.get("frame_key") or "") == requested_frame_key
            ),
            None,
        )
    if frame is None:
        frame = radar_read_latest_frame(
            CACHE_ROOT, site_id, level_code, cache_product_key
        )
    if not frame:
        raise HTTPException(status_code=404, detail="No live radar frame cached yet.")

    resolved_frame_key = str(
        frame.get("frame_key") or requested_frame_key or frame.get("source_data_key") or ""
    )
    sampled = sample_live_radar_value(
        site=site_id,
        product_key=product_key,
        frame_key=resolved_frame_key,
        lat=lat_value,
        lon=lon_value,
        elevation=elevation_key,
        source_data_key=frame.get("source_data_key"),
        storm_motion=motion,
    )
    sampled.update(
        {
            "site": site_id,
            "product": product_key,
            "requested_elevation": elevation_key,
            "storm_motion": motion,
            "timestamp": frame.get("timestamp"),
            "frame_key": resolved_frame_key,
            "lat": round(lat_value, 5),
            "lon": round(lon_value, 5),
        }
    )
    return sampled
