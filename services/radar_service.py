"""Radar metadata, tile proxy, and live-frame services."""

from datetime import datetime, timedelta, timezone
import json
import os
import threading

from fastapi import HTTPException
from fastapi.responses import Response

from app_core.background_render import spawn_live_render_thread
from app_core.http import parse_utc_datetime
from app_core.paths import BASE_DIR, CACHE_ROOT

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


def radar_cache_product_key(product_key: str, elevation: str) -> str:
    product_id = str(product_key or "").strip().upper()
    cache_variant = str(
        _radar_live_product_metadata(product_id).get("cache_variant") or ""
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
        with _ur.urlopen(req, timeout=15) as resp:
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


def _radar_live_site_supported(site: str) -> bool:
    try:
        from pyart.io.nexrad_common import NEXRAD_LOCATIONS

        site_id = normalize_radar_site_id(site)
        info = NEXRAD_LOCATIONS.get(site_id)
        if not info:
            return False
        return info.get("lat") is not None and info.get("lon") is not None
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
) -> int:
    from workers.radar_live_worker import run_radar_live_site_product

    site_id = normalize_radar_site_id(site)
    product_id = str(product_key or "").strip().upper()

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
            )
        )

    if not backfill_history:
        return cached
    if cached <= 0:
        return cached
    if not latest_only and max_render_frames is None:
        return cached

    def _fill_history():
        try:
            lock = _radar_live_fallback_lock(site_id, product_id)
            with lock:
                run_radar_live_site_product(
                    site_id,
                    product_id,
                    force=True,
                    latest_only=False,
                    elevation=elevation,
                )
        except Exception as exc:
            print(
                f"[radar_live] history back-fill failed {site_id}/{product_id}: {exc}"
            )

    threading.Thread(
        target=_fill_history, name=f"radar-history-{site_id}-{product_id}", daemon=True
    ).start()
    return cached


def _radar_live_render_in_background(
    site_id: str, product_key: str, elevation: str = "auto"
) -> bool:
    """Fill the live radar frame window in the background."""
    return spawn_live_render_thread(
        ("radar_live", site_id, product_key, elevation),
        f"radar-{site_id}-{product_key}-{elevation}",
        lambda: _radar_live_render_on_demand(
            site_id,
            product_key,
            latest_only=False,
            backfill_history=False,
            elevation=elevation,
        ),
    )


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
    try:
        from config.radar_colortable_utils import get_legend_json

        entries = get_legend_json(palette, vmin, vmax)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {
        "product": product_id,
        "palette": palette,
        "vmin": vmin,
        "vmax": vmax,
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
        with ur.urlopen(req, timeout=10) as resp:
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
        with ur.urlopen(req, timeout=8) as resp:
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
    """Return radar sites with configured live-cache flag."""
    try:
        configured = set(_radar_live_sites())
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
                    "configured": normalized_id in configured,
                }
            )

        sites.sort(key=lambda entry: (0 if entry["configured"] else 1, entry["site"]))
        return {
            "status": "success",
            "sites": sites,
            "configured_sites": sorted(configured),
            "products": _radar_live_catalog(),
            "count": len(sites),
        }
    except Exception as exc:
        print(f"Radar live sites endpoint error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


def get_radar_live_latest_data(
    site: str = "KMHX",
    product: str = "L3_N0B",
    elevation: str = "auto",
    force: bool = False,
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
    cache_product_key = radar_cache_product_key(product_key, elevation_key)
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

    return {
        "status": "success",
        "source": (
            "live_cache_forced"
            if force and fallback_cached > 0
            else "live_cache_fallback"
            if fallback_cached > 0
            else "live_cache"
        ),
        "history_filling": fallback_cached > 0,
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
        "available_elevations": meta.get("available_elevations") or [],
        "selected_elevation": meta.get("selected_elevation"),
        "requested_elevation": elevation_key,
        "source_data_key": meta.get("source_data_key", ""),
        "image_url": image_url,
        "bounds": meta.get("bounds"),
        "full_name": meta.get("full_name", product_key),
        "units": meta.get("units", ""),
    }


def get_radar_live_frames_data(
    site: str = "KMHX",
    product: str = "L3_N0B",
    elevation: str = "auto",
    hours: int = 2,
) -> dict:
    """Return live radar frames list for scrubber playback."""
    from cache.overlay_cache_utils import radar_list_frames
    from config.cache_config import (
        OVERLAY_EMPTY_CACHE_SYNC_FRAMES,
        OVERLAY_STALE_SERVE_WINDOW_MIN,
    )

    site_id = normalize_radar_site_id(site)
    product_key = str(product or "L3_N0B").strip().upper()
    elevation_key = normalize_radar_elevation(product_key, elevation)
    cache_product_key = radar_cache_product_key(product_key, elevation_key)
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
                max_render_frames=OVERLAY_EMPTY_CACHE_SYNC_FRAMES,
                elevation=elevation_key,
            )
        except Exception as exc:
            print(
                f"[radar_live_fallback] frames {site_id}/{product_key} failed: "
                f"{type(exc).__name__}: {exc}"
            )
            return 0

    cutoff_dt = datetime.now(timezone.utc) - timedelta(hours=max(1, int(hours or 2)))
    frames = radar_list_frames(CACHE_ROOT, site_id, level_code, cache_product_key)
    fallback_cached = 0
    refreshing = False

    if not frames:
        fallback_cached = _render_newest_sync()
        frames = radar_list_frames(CACHE_ROOT, site_id, level_code, cache_product_key)
        if frames:
            refreshing = _radar_live_render_in_background(
                site_id, product_key, elevation_key
            )

    filtered = _within(frames, cutoff_dt) if frames else []

    if not filtered and frames:
        grace_min = OVERLAY_STALE_SERVE_WINDOW_MIN.get("radar_live", 15)
        filtered = _within(frames, cutoff_dt - timedelta(minutes=grace_min))
        if filtered:
            refreshing = _radar_live_render_in_background(
                site_id, product_key, elevation_key
            )
        else:
            fallback_cached = max(fallback_cached, _render_newest_sync())
            frames = radar_list_frames(CACHE_ROOT, site_id, level_code, cache_product_key)
            filtered = _within(frames, cutoff_dt)
            if filtered:
                refreshing = _radar_live_render_in_background(
                    site_id, product_key, elevation_key
                )

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
        "frame_count": len(filtered),
        "refreshing": refreshing,
        "frames": filtered,
    }
