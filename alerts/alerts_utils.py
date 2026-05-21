from config.style_config import (
    resolve_alerts_style_config,
)
from config.alerts_config import (
    ALERT_PRIORITY,
    ALERT_COLORS,
    DEFAULT_COLOR,
    HAZARD_CATEGORIES,
    HAZARD_CATEGORY_ALIASES,
    NWS_WFO_MAP,
)
from config.geo_config import STATE_BOUNDS, STATES_FULL
from shapely.ops import unary_union
from shapely.geometry import shape, mapping, box
from cartopy.feature import ShapelyFeature
import cartopy.io.shapereader as shpreader
import cartopy.feature as cfeature
import cartopy.crs as ccrs
from matplotlib.offsetbox import AnnotationBbox, OffsetImage
import matplotlib.image as mpimg
import matplotlib.patheffects as PathEffects
import matplotlib.patches as mpatches
from matplotlib.colors import to_rgba
from dateutil import tz
from datetime import datetime, timezone
import matplotlib.pyplot as plt
from font_utils import register_montserrat_fonts
from geo_utils import CensusCounties  # Consolidated county shapefile class
from geo_utils import load_state_geometries as _load_state_geometries
import os
import json
import hashlib
import time
import requests
import numpy as np
import matplotlib
import concurrent.futures
import threading

from alerts import alerts_iem_utils

ACTIVE_ALERTS_CACHE_SECONDS = 60

# Ensure all Montserrat weights are available to Matplotlib.
register_montserrat_fonts()

MARINE_ALERT_EVENTS = {
    "Small Craft Advisory",
    "Gale Warning",
    "Gale Watch",
    "Marine Weather Statement",
    "Hazardous Seas Warning",
    "Hazardous Seas Watch",
    "Brisk Wind Advisory",
    "Storm Warning",
    "Storm Watch",
    "Hurricane Force Wind Warning",
    "Hurricane Force Wind Watch",
    "Low Water Advisory",
    "Special Marine Warning",
}

# CensusCounties is imported at the top of this file from geo_utils.
# Consumers that import `from alerts.alerts_utils import CensusCounties`
# will continue to work via the re-export.

# ---------------------------------------------------------------------------
# Zone geometry cache – resolves NWS forecast-zone / marine-zone polygons
# from the public zones API and keeps them in memory with a TTL.
# Disk-backed so the ~50s zone fetch survives server restarts.
# ---------------------------------------------------------------------------
_ZONE_GEOM_CACHE = {}  # zone_id -> (shapely_geom | None, expire_ts)
_ZONE_GEOM_LOCK = threading.Lock()
# NWS forecast/public/fire zones change on the order of years, not hours.
# A long TTL means restart-after-restart hits the disk cache instead of
# re-fetching ~1000+ zones (~60s of cold-start latency).
_ZONE_GEOM_TTL = 30 * 24 * 3600  # 30 days
_ZONE_GEOM_MAX_WORKERS = 20  # concurrent HTTP fetches for a batch
_NWS_HEADERS = {
    "User-Agent": "(NCHurricane.com Weather Suite, contact@nchurricane.com)"
}

_ZONE_DISK_CACHE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "cache",
    "alerts",
    "zone_geometry_cache.json",
)


def _load_zone_disk_cache() -> None:
    """Load persisted zone geometries from disk into the in-memory cache."""
    try:
        if not os.path.exists(_ZONE_DISK_CACHE_PATH):
            return
        with open(_ZONE_DISK_CACHE_PATH, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        now = time.time()
        loaded = 0
        with _ZONE_GEOM_LOCK:
            for zone_id, entry in raw.items():
                expire_ts = entry.get("expire_ts", 0)
                if expire_ts <= now:
                    continue  # skip expired entries
                geom_raw = entry.get("geometry")
                geom = shape(geom_raw) if geom_raw else None
                _ZONE_GEOM_CACHE[zone_id] = (geom, expire_ts)
                loaded += 1
        if loaded:
            print(
                f"[zone-geom] Loaded {loaded} zone geometries from disk cache")
    except Exception as exc:
        print(f"[zone-geom] Disk cache load skipped: {exc}")


def _save_zone_disk_cache() -> None:
    """Persist current in-memory zone geometry cache to disk."""
    try:
        os.makedirs(os.path.dirname(_ZONE_DISK_CACHE_PATH), exist_ok=True)
        snapshot = {}
        with _ZONE_GEOM_LOCK:
            for zone_id, (geom, expire_ts) in _ZONE_GEOM_CACHE.items():
                try:
                    snapshot[zone_id] = {
                        "expire_ts": expire_ts,
                        "geometry": mapping(geom) if geom else None,
                    }
                except Exception:
                    pass
        with open(_ZONE_DISK_CACHE_PATH, "w", encoding="utf-8") as fh:
            json.dump(snapshot, fh)
    except Exception as exc:
        print(f"[zone-geom] Disk cache save skipped: {exc}")


# Load persisted zone geometries at module import time so the first worker
# run after a restart hits warm cache instead of re-fetching ~895 zones.
_load_zone_disk_cache()


def _fetch_single_zone_geometry(zone_url):
    """Fetch geometry for one NWS zone URL.  Returns (zone_id, geom|None)."""
    zone_id = zone_url.rstrip("/").split("/")[-1]
    now = time.time()
    with _ZONE_GEOM_LOCK:
        cached = _ZONE_GEOM_CACHE.get(zone_id)
        if cached is not None and cached[1] > now:
            return zone_id, cached[0]
    try:
        resp = requests.get(zone_url, headers=_NWS_HEADERS, timeout=12)
        resp.raise_for_status()
        raw = resp.json().get("geometry")
        geom = shape(raw) if raw else None
    except Exception:
        geom = None
    with _ZONE_GEOM_LOCK:
        _ZONE_GEOM_CACHE[zone_id] = (geom, now + _ZONE_GEOM_TTL)
    return zone_id, geom


def _prefetch_zone_geometries(features):
    """Bulk-prefetch all zone geometries referenced by *features* into cache.

    Collects every unique affectedZones URL across all features that lack
    inline geometry, then fetches them in one batched pass so that later
    per-alert `_resolve_zone_geometry` calls hit the warm cache.
    """
    now = time.time()
    urls_needed = set()
    for feat in features:
        raw_geom = feat.get("geometry") if isinstance(feat, dict) else None
        has_geom = False
        if raw_geom:
            try:
                g = shape(raw_geom)
                has_geom = g is not None and not g.is_empty
            except Exception:
                pass
        if not has_geom:
            props = feat.get("properties", {}) if isinstance(
                feat, dict) else {}
            for url in props.get("affectedZones", []):
                zid = url.rstrip("/").split("/")[-1]
                with _ZONE_GEOM_LOCK:
                    entry = _ZONE_GEOM_CACHE.get(zid)
                if entry is None or entry[1] <= now:
                    urls_needed.add(url)
    if not urls_needed:
        return
    urls_list = list(urls_needed)
    workers = min(_ZONE_GEOM_MAX_WORKERS, len(urls_list))
    fetch_start = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(_fetch_single_zone_geometry, urls_list))
    print(
        f"[zone-geom] Prefetched {len(urls_list)} unique zone(s) with {workers} "
        f"workers in {time.time() - fetch_start:.1f}s | "
        f"{len(_ZONE_GEOM_CACHE)} cached total"
    )
    # Persist updated cache to disk so restarts don't re-fetch
    _save_zone_disk_cache()


def _resolve_zone_geometry(affected_zone_urls):
    """Return a unioned Shapely geometry built from *affectedZones* URLs.

    Fetches zone polygons concurrently, caches each one, and returns the
    union of all valid geometries (or *None* when nothing is resolvable).
    """
    if not affected_zone_urls:
        return None
    # Figure out which need fetching vs are cached
    now = time.time()
    to_fetch = []
    cached_geoms = []
    with _ZONE_GEOM_LOCK:
        for url in affected_zone_urls:
            zid = url.rstrip("/").split("/")[-1]
            entry = _ZONE_GEOM_CACHE.get(zid)
            if entry is not None and entry[1] > now:
                if entry[0] is not None and not entry[0].is_empty:
                    cached_geoms.append(entry[0])
            else:
                to_fetch.append(url)
    # Fetch missing zone geometries concurrently
    if to_fetch:
        workers = min(_ZONE_GEOM_MAX_WORKERS, len(to_fetch))
        fetch_start = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            results = pool.map(_fetch_single_zone_geometry, to_fetch)
        for _zid, geom in results:
            if geom is not None and not geom.is_empty:
                cached_geoms.append(geom)
        print(
            f"[zone-geom] Fetched {len(to_fetch)} zone(s) with {workers} workers "
            f"in {time.time() - fetch_start:.1f}s | {len(cached_geoms)} resolved, "
            f"{len(_ZONE_GEOM_CACHE)} cached total"
        )
        # Persist newly-fetched zones so subsequent restarts skip the network round-trip.
        _save_zone_disk_cache()
    if not cached_geoms:
        return None
    return unary_union(cached_geoms) if len(cached_geoms) > 1 else cached_geoms[0]


# resolve_alerts_style_config is imported from config.style_config.


def resolve_alerts_legend_columns(legend_cols_value, legend_count, fig_width):
    """Resolve legend columns with an auto mode based on output width."""
    if legend_count <= 0:
        return 1

    # ~3.2in per column accommodates long hazard labels (e.g. "Special Weather Statement")
    # without overflowing the legend panel at typical 1080p output widths.
    auto_cols = max(1, min(6, int(float(fig_width) / 3.2)))

    if isinstance(legend_cols_value, str):
        mode = legend_cols_value.strip().lower()
        if mode in {"", "auto", "dynamic"}:
            return min(auto_cols, legend_count)
        try:
            explicit_cols = int(mode)
        except Exception:
            explicit_cols = auto_cols
    else:
        try:
            explicit_cols = int(legend_cols_value)
        except Exception:
            explicit_cols = auto_cols

    explicit_cols = max(1, explicit_cols)
    return min(explicit_cols, legend_count)


def normalize_alerts_custom_extent(custom_extent, target_aspect=4.0 / 3.0):
    """Expand a custom extent to a target map aspect while preserving center.

    Extent format: (south, north, west, east). Returns normalized extent or
    the original input if invalid.
    """
    try:
        south, north, west, east = [float(v) for v in custom_extent]
    except Exception:
        return custom_extent

    if not (north > south and east > west):
        return custom_extent

    try:
        aspect = float(target_aspect)
    except Exception:
        aspect = 4.0 / 3.0
    if aspect <= 0.0:
        return custom_extent

    mid_lat = (south + north) * 0.5
    cos_lat = max(np.cos(np.deg2rad(mid_lat)), 0.2)

    lon_span = east - west
    lat_span = north - south
    effective_lon_span = lon_span * cos_lat
    current_aspect = effective_lon_span / max(lat_span, 1e-6)

    if abs(current_aspect - aspect) < 1e-6:
        return (south, north, west, east)

    center_lat = mid_lat
    center_lon = (west + east) * 0.5

    if current_aspect < aspect:
        effective_lon_span = lat_span * aspect
        lon_span = effective_lon_span / cos_lat
    else:
        lat_span = effective_lon_span / aspect

    half_lat = lat_span * 0.5
    half_lon = lon_span * 0.5
    south = center_lat - half_lat
    north = center_lat + half_lat
    west = center_lon - half_lon
    east = center_lon + half_lon

    # Keep extents in valid world bounds while preserving span when possible.
    if south < -89.5:
        shift = -89.5 - south
        south += shift
        north += shift
    if north > 89.5:
        shift = north - 89.5
        south -= shift
        north -= shift
    if west < -180.0:
        shift = -180.0 - west
        west += shift
        east += shift
    if east > 180.0:
        shift = east - 180.0
        west -= shift
        east -= shift

    south = max(-89.5, south)
    north = min(89.5, north)
    west = max(-180.0, west)
    east = min(180.0, east)

    if not (north > south and east > west):
        return custom_extent

    return (south, north, west, east)


def get_cache_path(state_code, source="nws"):
    base_path = os.path.dirname(os.path.abspath(__file__))
    region_key = state_code.upper() if state_code else "NATIONAL"
    cache_dir = os.path.join(base_path, "alert_data", region_key)
    os.makedirs(cache_dir, exist_ok=True)
    source_key = str(source or "nws").lower()
    if source_key not in {"nws", "iem"}:
        source_key = "nws"
    return cache_dir, os.path.join(cache_dir, f"alerts_{source_key}.json")


def is_cache_valid(file_path, minutes=5):
    if not os.path.exists(file_path):
        return False
    mtime = os.path.getmtime(file_path)
    if (time.time() - mtime) < (minutes * 60):
        return True
    return False


def fetch_active_alerts(state=None, source="nws"):
    features, _source = fetch_active_alerts_with_source(state, source=source)
    return features


def _coerce_utc_datetime(value):
    if value is None:
        return None

    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    if not isinstance(value, str):
        return None

    text = value.strip()
    if not text:
        return None

    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    parsed = None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        for fmt in (
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
        ):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue

    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


# Ocean geometry cache for marine alert clipping
_OCEAN_GEOMETRY = None
_OCEAN_GEOMETRY_FAILED = False
_OCEAN_GEOMETRY_RESOLUTION = "50m"


def get_ocean_geometry():
    """Load ocean and lakes geometry for clipping marine alerts."""
    global _OCEAN_GEOMETRY, _OCEAN_GEOMETRY_FAILED

    if _OCEAN_GEOMETRY is not None:
        return _OCEAN_GEOMETRY
    if _OCEAN_GEOMETRY_FAILED:
        return None

    try:
        ocean_shp = shpreader.natural_earth(
            resolution=_OCEAN_GEOMETRY_RESOLUTION,
            category="physical",
            name="ocean",
        )
        lakes_shp = shpreader.natural_earth(
            resolution=_OCEAN_GEOMETRY_RESOLUTION,
            category="physical",
            name="lakes",
        )

        water_geoms = []

        ocean_reader = shpreader.Reader(ocean_shp)
        water_geoms.extend(
            g for g in ocean_reader.geometries() if g is not None and not g.is_empty
        )

        lakes_reader = shpreader.Reader(lakes_shp)
        water_geoms.extend(
            g for g in lakes_reader.geometries() if g is not None and not g.is_empty
        )

        if not water_geoms:
            _OCEAN_GEOMETRY_FAILED = True
            return None

        _OCEAN_GEOMETRY = unary_union(water_geoms)
        return _OCEAN_GEOMETRY
    except Exception as e:
        print(f"[WARN] Unable to load water geometry for marine clipping: {e}")
        _OCEAN_GEOMETRY_FAILED = True
        return None


def _is_alert_active_for_time(properties, valid_time):
    if valid_time is None:
        return True

    target_dt = _coerce_utc_datetime(valid_time)
    if target_dt is None:
        return True

    start_dt = None
    # Use effective-time semantics first to match NWS /alerts/active behavior.
    # Onset can be later than effective for some products (e.g., Dense Fog Advisory).
    for key in ("effective", "sent", "issued", "issue", "onset"):
        start_dt = _coerce_utc_datetime(properties.get(key))
        if start_dt is not None:
            break

    end_dt = None
    for key in ("ends", "expires", "expire"):
        end_dt = _coerce_utc_datetime(properties.get(key))
        if end_dt is not None:
            break

    if start_dt is not None and target_dt < start_dt:
        return False
    if end_dt is not None and target_dt > end_dt:
        return False
    return True


def _alert_feature_fingerprint(feature):
    props = feature.get("properties", {}) if isinstance(feature, dict) else {}

    # Prefer the stable NWS alert ID for dedup (unique per alert product)
    alert_id = str(feature.get("id", "") or props.get("id", "") or "").strip()
    if alert_id:
        return ("id", alert_id)

    event_name = str(props.get("event", "") or "").strip()
    sender = str(props.get("senderCode", "") or "").strip()
    headline = str(props.get("headline", "") or "").strip()

    bounds_key = ()
    area_key = None
    raw_geom = feature.get("geometry") if isinstance(feature, dict) else None
    if raw_geom:
        try:
            geom = shape(raw_geom)
            if not geom.is_empty:
                bounds_key = tuple(round(float(v), 4) for v in geom.bounds)
                area_key = round(float(geom.area), 4)
        except Exception:
            pass

    # Include UGC codes so zone-only alerts with no geometry are still unique
    ugc_key = tuple(sorted(props.get("geocode", {}).get("UGC", [])))

    return (event_name, sender, headline, bounds_key, area_key, ugc_key)


def _supplement_state_intersecting_alerts(
    features,
    state,
    headers,
    allowed_events=None,
):
    state_code = str(state or "").strip().upper()
    if not state_code or state_code not in STATE_BOUNDS:
        return features

    state_bounds = STATE_BOUNDS.get(state_code)
    if not state_bounds:
        return features

    try:
        west, east, south, north = [float(v) for v in state_bounds]
        state_bbox = box(west, south, east, north)
    except Exception:
        return features

    try:
        all_resp = requests.get(
            "https://api.weather.gov/alerts/active",
            headers=headers,
            timeout=20,
        )
        all_resp.raise_for_status()
        all_features = all_resp.json().get("features", [])
    except Exception as e:
        print(f"[WARN] State supplemental fetch failed: {e}")
        return features

    merged = list(features)
    seen = {_alert_feature_fingerprint(f) for f in merged}

    # Bulk-prefetch zone geometries so per-alert lookups hit warm cache
    _prefetch_zone_geometries(all_features)

    for feat in all_features:
        props = feat.get("properties", {}) if isinstance(feat, dict) else {}
        event_name = str(props.get("event", "") or "").strip()
        if allowed_events is not None and event_name not in allowed_events:
            continue

        raw_geom = feat.get("geometry") if isinstance(feat, dict) else None
        geom = None
        resolved_from_zones = False
        if raw_geom:
            try:
                geom = shape(raw_geom)
            except Exception:
                geom = None

        # Resolve geometry from affectedZones when the alert has none
        if geom is None or geom.is_empty:
            zone_urls = props.get("affectedZones", [])
            if zone_urls:
                geom = _resolve_zone_geometry(zone_urls)
                resolved_from_zones = True

        if geom is None or geom.is_empty:
            continue
        if not geom.intersects(state_bbox):
            continue

        fp = _alert_feature_fingerprint(feat)
        if fp in seen:
            continue
        seen.add(fp)

        # Inject resolved geometry so downstream process_alerts can use it
        if resolved_from_zones:
            feat = dict(feat)
            feat["geometry"] = mapping(geom)
        merged.append(feat)

    return merged


def _supplement_state_marine_alerts(features, state, headers):
    return _supplement_state_intersecting_alerts(
        features,
        state,
        headers,
        allowed_events=MARINE_ALERT_EVENTS,
    )


def fetch_active_alerts_with_source(state=None, source="nws"):
    source_key = str(source or "nws").lower()
    if source_key not in {"nws", "iem"}:
        source_key = "nws"

    cache_dir, cache_file = get_cache_path(state, source=source_key)
    if is_cache_valid(cache_file, minutes=ACTIVE_ALERTS_CACHE_SECONDS / 60.0):
        print(f"Loading cached alerts from {cache_file}...")
        try:
            with open(cache_file, "r") as f:
                data = json.load(f)
                features = data.get("features", [])
                cached_source = data.get("_source", "NWS API")
                if state and source_key == "nws":
                    headers = {
                        "User-Agent": "(NCHurricane.com Weather Suite, contact@nchurricane.com)"
                    }
                    features = _supplement_state_intersecting_alerts(
                        features, state, headers
                    )
                    if len(features) != len(data.get("features", [])):
                        data["features"] = features
                        try:
                            with open(cache_file, "w") as cache_handle:
                                json.dump(data, cache_handle)
                        except Exception as cache_error:
                            print(
                                f"[WARN] Error refreshing alert cache: {cache_error}")
                return features, cached_source
        except Exception as e:
            print(f"[WARN] Error reading alert cache: {e}")

    if source_key == "iem":
        try:
            iem_features = alerts_iem_utils.fetch_active_alerts_iem(state)
            iem_features = _supplement_state_marine_alerts(
                iem_features,
                state,
                {
                    "User-Agent": "(NCHurricane.com Weather Suite, contact@nchurricane.com)"
                },
            )

            wrapper = {"_source": "IEM", "features": iem_features}
            try:
                with open(cache_file, "w") as f:
                    json.dump(wrapper, f)
            except Exception as e:
                print(f"[WARN] Error writing alert cache (IEM): {e}")
            return iem_features, "IEM"
        except Exception as e:
            print(f"[WARN] IEM live alert download failed: {e}")
            return [], "IEM"

    headers = {
        "User-Agent": "(NCHurricane.com Weather Suite, contact@nchurricane.com)"}
    url = (
        f"https://api.weather.gov/alerts/active?area={state}"
        if state
        else "https://api.weather.gov/alerts/active"
    )

    try:
        print(f"Downloading fresh alerts for {state if state else 'CONUS'}...")
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        data["features"] = _supplement_state_intersecting_alerts(
            data.get("features", []),
            state,
            headers,
        )
        data["_source"] = "NWS API"
        try:
            with open(cache_file, "w") as f:
                json.dump(data, f)
        except Exception as e:
            print(f"[WARN] Error writing alert cache: {e}")
        return data.get("features", []), "NWS API"
    except Exception as e:
        print(f"[WARN] NWS alerts API failed, trying IEM fallback: {e}")

    try:
        iem_features = alerts_iem_utils.fetch_active_alerts_iem(state)
        wrapper = {"_source": "IEM", "features": iem_features}
        try:
            with open(cache_file, "w") as f:
                json.dump(wrapper, f)
        except Exception as e:
            print(f"[WARN] Error writing alert cache (IEM): {e}")
        return iem_features, "IEM"
    except Exception as e:
        print(f"[WARN] IEM live fallback failed: {e}")
        return [], "IEM"


def process_alerts(
    features_list,
    category_filter_name=None,
    wfo_filter=None,
    exclude_regions=None,
    bbox_filter=None,
    valid_time=None,
    show_storm_alerts=True,
    show_zone_alerts=True,
):
    marine_events = MARINE_ALERT_EVENTS

    processed = []
    counties_loaded = False

    allowed_events = None
    normalized_category = HAZARD_CATEGORY_ALIASES.get(
        category_filter_name, category_filter_name
    )
    if normalized_category and normalized_category in HAZARD_CATEGORIES:
        allowed_events = HAZARD_CATEGORIES[normalized_category]

    bbox_geom = None
    if bbox_filter is not None:
        try:
            south, north, west, east = [float(v) for v in bbox_filter]
            if north > south and east > west:
                bbox_geom = box(west, south, east, north)
        except Exception:
            bbox_geom = None

    # Bulk-prefetch zone geometries so per-alert lookups hit warm cache
    _prefetch_zone_geometries(features_list)

    for feat in features_list:
        props = feat["properties"]
        event_name = props["event"]
        is_marine_event = bool(props.get("isMarine")
                               ) or event_name in marine_events

        if not _is_alert_active_for_time(props, valid_time):
            continue

        if allowed_events is not None and event_name not in allowed_events:
            continue

        if exclude_regions and "AK" in exclude_regions:
            sender_code = props.get("senderCode", "").upper()
            if sender_code.startswith("PA"):
                continue
            if (
                ", AK" in props.get("areaDesc", "").upper()
                or "ALASKA" in props.get("areaDesc", "").upper()
            ):
                continue

        if exclude_regions and "HI" in exclude_regions:
            sender_code = props.get("senderCode", "").upper()
            if sender_code.startswith("PH"):
                continue
            if (
                ", HI" in props.get("areaDesc", "").upper()
                or "HAWAII" in props.get("areaDesc", "").upper()
            ):
                continue

        if wfo_filter:
            target_wfo = wfo_filter.upper()
            match_found = False
            sender_code = props.get("senderCode", "")
            if sender_code and target_wfo in sender_code.upper():
                match_found = True
            if not match_found:
                params = props.get("parameters", {})
                for key in ["WMOidentifier", "AWIPSidentifier", "NWSidentifier"]:
                    val = params.get(key)
                    if val and target_wfo in str(val).upper():
                        match_found = True
                        break
            if not match_found:
                continue

        raw_geom = feat.get("geometry")
        iem_gtype = str(props.get("gtype", "") or "").upper().strip()
        final_geom = None
        used_county_fallback = False
        if raw_geom:
            try:
                final_geom = shape(raw_geom)
            except Exception:
                pass

        # County fallback from SAME codes
        if not final_geom:
            same_codes = props.get("geocode", {}).get("SAME", [])
            if same_codes:
                if not counties_loaded:
                    CensusCounties.load()
                    counties_loaded = True
                fips_codes = [c[1:] for c in same_codes if len(c) == 6]
                final_geom = CensusCounties.get_geometry_for_fips(fips_codes)
                if final_geom is not None:
                    used_county_fallback = True

        # Zone geometry fallback – resolve from NWS affectedZones API
        if not final_geom:
            zone_urls = props.get("affectedZones", [])
            if zone_urls:
                final_geom = _resolve_zone_geometry(zone_urls)
                if final_geom is not None:
                    used_county_fallback = True  # treat as zone-type polygon

        if not final_geom:
            continue

        polygon_type = "storm"
        if iem_gtype == "C" or used_county_fallback:
            polygon_type = "zone"
        elif iem_gtype == "P":
            polygon_type = "storm"

        if polygon_type == "storm" and not bool(show_storm_alerts):
            continue
        if polygon_type == "zone" and not bool(show_zone_alerts):
            continue

        if is_marine_event:
            ocean_geom = get_ocean_geometry()
            if ocean_geom is not None:
                try:
                    clipped_geom = final_geom.intersection(ocean_geom)
                    if not clipped_geom.is_empty:
                        final_geom = clipped_geom
                except Exception:
                    pass

        if bbox_geom is not None:
            try:
                clipped_to_bbox = final_geom.intersection(bbox_geom)
                if clipped_to_bbox.is_empty:
                    continue
                final_geom = clipped_to_bbox
            except Exception:
                continue

        if exclude_regions and "AK" in exclude_regions and final_geom.bounds[1] > 52:
            continue
        if exclude_regions and "HI" in exclude_regions and final_geom.bounds[2] < -130:
            continue

        priority_val = ALERT_PRIORITY.get(event_name, 999)
        processed.append(
            {
                "event": event_name,
                "geometry": final_geom,
                "priority": priority_val,
                "color": ALERT_COLORS.get(event_name, DEFAULT_COLOR),
                "headline": props.get("headline", event_name),
                "polygon_type": polygon_type,
            }
        )

    processed.sort(key=lambda x: x["priority"], reverse=True)
    return processed


def get_active_alert_polygons_geojson(
    state_code=None,
    category_filter="All Alerts",
    wfo_code=None,
    custom_extent=None,
    source="nws",
    valid_time=None,
    show_storm_alerts=True,
    show_zone_alerts=True,
):
    """Return current active alerts as a GeoJSON FeatureCollection.

    This is intended for lightweight UI overlays (e.g., map selector previews).
    """
    exclude_list = []
    is_national_view = state_code is None and wfo_code is None
    if is_national_view:
        exclude_list = ["AK", "HI"]

    fetch_state = None if wfo_code else state_code
    raw_alerts, data_source = fetch_active_alerts_with_source(
        fetch_state, source=source
    )
    clean_alerts = process_alerts(
        raw_alerts,
        category_filter_name=category_filter,
        wfo_filter=wfo_code,
        exclude_regions=exclude_list,
        bbox_filter=custom_extent,
        valid_time=valid_time,
        show_storm_alerts=show_storm_alerts,
        show_zone_alerts=show_zone_alerts,
    )

    features = []
    for item in clean_alerts:
        try:
            geom = mapping(item["geometry"])
        except Exception:
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": geom,
                "properties": {
                    "event": item.get("event", ""),
                    "headline": item.get("headline", ""),
                    "priority": item.get("priority", 999),
                    "color": item.get("color", DEFAULT_COLOR),
                    "polygon_type": item.get("polygon_type", "storm"),
                },
            }
        )

    return {"type": "FeatureCollection", "features": features}, data_source


def plot_cities(
    ax,
    extent_bounds,
    filename="us-cities.json",
    density_scale=1.0,
    collision_w_factor=0.05,
    collision_h_factor=0.02,
    font_size=10,
    z_cities=100,
    text_color="white",
    text_bg_color="black",
    text_bg_alpha=0.5,
    font_family="Montserrat",
    font_weight="black",
    font_style="italic",
    box_style="round,pad=0.2",
    halo_width=1.0,
    halo_color="black",
    text_alpha=0.95,
):
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        cities_path = os.path.join(
            os.path.dirname(script_dir), "data", filename)

        if not os.path.exists(cities_path) and filename != "us-cities.json":
            print(
                f"[WARN] {filename} not found in {cities_path}. Falling back to us-cities.json"
            )
            cities_path = os.path.join(
                os.path.dirname(script_dir), "data", "us-cities.json"
            )

        with open(cities_path, "r") as f:
            raw_data = json.load(f)

        cities = []
        if isinstance(raw_data, dict):
            # Handle NC-style dictionary: {"City": [lat, lon, align]}
            for name, props in raw_data.items():
                if len(props) >= 2:
                    cities.append(
                        {
                            "city": name,
                            "latitude": float(props[0]),
                            "longitude": float(props[1]),
                            "rank": 1,  # Local files treated as high priority
                        }
                    )
        elif isinstance(raw_data, list):
            # Handle US-style list: [{"city": "Name", ...}]
            cities = raw_data

            def _city_priority(city):
                try:
                    rank_val = float(city.get("rank"))
                except (TypeError, ValueError):
                    rank_val = 9999.0
                return rank_val

            cities.sort(key=_city_priority)
        else:
            print("[WARN] Unknown city file format")
            return

    except Exception as e:
        print(f"[WARN] Could not load city data: {e}")
        return

    min_lon, max_lon, min_lat, max_lat = extent_bounds
    drawn_bboxes = []

    map_width = max_lon - min_lon
    map_height = max_lat - min_lat
    text_w = map_width * collision_w_factor * density_scale
    text_h = map_height * collision_h_factor * density_scale

    for city_data in cities:
        city_name = city_data.get("city")
        try:
            lat = float(city_data.get("latitude"))
            lon = float(city_data.get("longitude"))
        except (ValueError, TypeError):
            continue

        if not (
            (min_lat - 0.1) <= lat <= (max_lat + 0.1)
            and (min_lon - 0.1) <= lon <= (max_lon + 0.1)
        ):
            continue

        cand_x_min = lon - (text_w / 2.0)
        cand_x_max = lon + (text_w / 2.0)
        cand_y_min = lat - (text_h / 2.0)
        cand_y_max = lat + (text_h / 2.0)

        collision = False
        for bx_min, bx_max, by_min, by_max in drawn_bboxes:
            if (
                cand_x_min < bx_max
                and cand_x_max > bx_min
                and cand_y_min < by_max
                and cand_y_max > by_min
            ):
                collision = True
                break

        if collision:
            continue

        txt = ax.text(
            lon,
            lat,
            city_name.upper(),
            transform=ccrs.PlateCarree(),
            fontsize=font_size,
            color=text_color,
            fontname=font_family,
            fontweight=font_weight,
            fontstyle=font_style,
            ha="center",
            va="center",
            zorder=z_cities + 1,
            alpha=text_alpha,
            bbox=dict(
                facecolor=text_bg_color,
                alpha=text_bg_alpha,
                edgecolor="none",
                boxstyle=box_style,
            ),
            clip_on=True,
        )
        txt.set_path_effects(
            [PathEffects.withStroke(
                linewidth=halo_width, foreground=halo_color)]
        )
        drawn_bboxes.append((cand_x_min, cand_x_max, cand_y_min, cand_y_max))


def _normalize_alerts_projection_mode(projection_mode):
    mode = str(projection_mode or "auto").strip().lower()
    return mode or "auto"


def _normalize_extent_longitudes(west, east):
    """Shift extent longitudes into a conventional range for shapely/cartopy use."""
    west = float(west)
    east = float(east)

    while west > 180.0 and east > 180.0:
        west -= 360.0
        east -= 360.0
    while west < -180.0 and east < -180.0:
        west += 360.0
        east += 360.0

    return west, east


def draw_alerts_static_layers(
    ax,
    *,
    land_color,
    ocean_color,
    coastline_width,
    coastline_color,
    show_country,
    country_width,
    country_color,
    show_lakes,
    lake_color,
    lake_outline_color,
    lake_outline_width,
    show_rivers,
    river_color,
    river_width,
    show_highways,
    highway_color,
    highway_width,
    highway_opacity,
):
    ax.add_feature(cfeature.LAND, facecolor=land_color)
    ax.add_feature(cfeature.OCEAN, facecolor=ocean_color)
    draw_alerts_static_overlays(
        ax,
        land_color=land_color,
        ocean_color=ocean_color,
        coastline_width=coastline_width,
        coastline_color=coastline_color,
        show_country=show_country,
        country_width=country_width,
        country_color=country_color,
        show_lakes=show_lakes,
        lake_color=lake_color,
        lake_outline_color=lake_outline_color,
        lake_outline_width=lake_outline_width,
        show_rivers=show_rivers,
        river_color=river_color,
        river_width=river_width,
        show_highways=show_highways,
        highway_color=highway_color,
        highway_width=highway_width,
        highway_opacity=highway_opacity,
    )


def draw_alerts_static_overlays(
    ax,
    *,
    land_color,
    ocean_color,
    coastline_width,
    coastline_color,
    show_country,
    country_width,
    country_color,
    show_lakes,
    lake_color,
    lake_outline_color,
    lake_outline_width,
    show_rivers,
    river_color,
    river_width,
    show_highways,
    highway_color,
    highway_width,
    highway_opacity,
):
    ax.add_feature(
        cfeature.COASTLINE, linewidth=coastline_width, edgecolor=coastline_color
    )
    if show_country:
        ax.add_feature(
            cfeature.BORDERS.with_scale("10m"),
            linewidth=country_width,
            edgecolor=country_color,
        )

    if show_lakes:
        ax.add_feature(
            cfeature.LAKES.with_scale("50m"),
            facecolor=lake_color,
            edgecolor=lake_outline_color,
            linewidth=lake_outline_width,
            zorder=5,
        )

    if show_rivers:
        ax.add_feature(
            cfeature.RIVERS.with_scale("50m"),
            edgecolor=river_color,
            linewidth=river_width,
            zorder=1,
        )

    if show_highways:
        try:
            roads = cfeature.NaturalEarthFeature(
                "cultural",
                "roads_north_america",
                "10m",
                facecolor="none",
            )
            ax.add_feature(
                roads,
                edgecolor=highway_color,
                linewidth=highway_width,
                alpha=highway_opacity,
                zorder=2,
            )
        except Exception:
            pass


def draw_alerts_state_overlays(
    ax,
    *,
    state_code,
    region,
    is_national_view,
    show_states,
    state_width,
    state_color,
    sel_border_width,
    sel_border_color,
    states_zorder,
    state_border_zorder,
    selected_geometry=None,
):
    if show_states:
        ax.add_feature(
            cfeature.STATES.with_scale("10m"),
            linewidth=state_width,
            edgecolor=state_color,
            zorder=states_zorder,
        )

    if (state_code or region == "CONUS") and not is_national_view:
        try:
            selected_geom = selected_geometry
            if selected_geom is None:
                us_states = _load_state_geometries()
                code = state_code.upper() if state_code else region

                if code == "CONUS":
                    conus_states = [
                        st for st in us_states.values() if st and not st.is_empty
                    ]
                    selected_geom = unary_union(
                        conus_states) if conus_states else None
                else:
                    selected_geom = us_states.get(code)

            if selected_geom and not selected_geom.is_empty:
                ax.add_geometries(
                    [selected_geom],
                    ccrs.PlateCarree(),
                    facecolor="none",
                    edgecolor=sel_border_color,
                    linewidth=sel_border_width,
                    zorder=state_border_zorder,
                )
        except Exception:
            pass


# ============================================================================
# Geometry Optimization: Simplification for low-zoom rendering (Phase 2)
# ============================================================================


def _simplify_geometry_for_display(geom, tolerance_m: float = 1000.0) -> object | None:
    """Simplify a Shapely geometry using Douglas-Peucker with meter-based tolerance.

    Args:
        geom: Shapely geometry (Polygon or MultiPolygon).
        tolerance_m: Simplification tolerance in meters.

    Returns:
        Simplified Shapely geometry, or None if simplification fails or produces
        an empty/invalid result.
    """
    if geom is None or geom.is_empty:
        return None

    try:
        # Estimate tolerance in degrees (~1000m = 0.009° at equator).
        # Rough conversion: 1 degree ≈ 111 km at equator, scales by cos(latitude).
        bounds = geom.bounds  # (minx, miny, maxx, maxy)
        center_lat = (bounds[1] + bounds[3]) / 2.0
        tolerance_deg = tolerance_m / (
            111000.0
            * max(
                0.1, abs(__import__("math").cos(
                    __import__("math").radians(center_lat)))
            )
        )
        tolerance_deg = max(0.0001, tolerance_deg)

        # Apply Douglas-Peucker simplification.
        simplified = geom.simplify(tolerance_deg, preserve_topology=True)

        if simplified is None or simplified.is_empty:
            return None

        # Validate minimum vertex count.
        min_vertices = 3
        if hasattr(simplified, "exterior"):
            # Polygon: check outer ring.
            if len(simplified.exterior.coords) < min_vertices + 1:  # +1 for closed ring
                return None
        elif hasattr(simplified, "geoms"):
            # MultiPolygon: check all rings.
            valid = True
            for part in simplified.geoms:
                if hasattr(part, "exterior"):
                    if len(part.exterior.coords) < min_vertices + 1:
                        valid = False
                        break
            if not valid:
                return None

        return simplified
    except Exception:
        # Fallback: return None on any simplification error.
        return None


def _create_display_low_features(full_features: list[dict]) -> tuple[list[dict], dict]:
    """Create a simplified display-low variant of alert features.

    Non-excluded events are simplified for low-zoom rendering. Excluded storm
    events always retain full geometry. Validation ensures that invalid
    simplifications fall back to full geometry.

    Args:
        full_features: List of full GeoJSON Feature dicts with geometries.

    Returns:
        (display_features, metrics) where metrics is a dict with simplification stats.
    """
    from config.alerts_config import (
        GEOMETRY_EXCLUDED_EVENTS,
        GEOMETRY_SIMPLIFICATION_SETTINGS,
    )

    tolerance_m = GEOMETRY_SIMPLIFICATION_SETTINGS["low_zoom_tolerance_m"]
    display_features = []
    total_features = 0
    simplified_features = 0
    excluded_features = 0
    total_vertices_before = 0
    total_vertices_after = 0

    for feat in full_features:
        if not isinstance(feat, dict):
            continue

        total_features += 1
        props = feat.get("properties", {})
        event_name = str(props.get("event", "") or "").strip()

        # Skip excluded events – always use full geometry.
        if event_name in GEOMETRY_EXCLUDED_EVENTS:
            display_feat = dict(feat)
            # Mark as not simplified
            display_feat.setdefault("_simplified", False)
            display_features.append(display_feat)
            excluded_features += 1
            continue

        # Attempt to simplify non-excluded events.
        raw_geom = feat.get("geometry")
        if not raw_geom:
            display_feat = dict(feat)
            # Mark as not simplified
            display_feat.setdefault("_simplified", False)
            display_features.append(display_feat)
            continue

        try:
            full_geom = shape(raw_geom)
            if full_geom.is_empty:
                display_feat = dict(feat)
                # Mark as not simplified
                display_feat.setdefault("_simplified", False)
                display_features.append(display_feat)
                continue

            # Count vertices before simplification.
            if hasattr(full_geom, "exterior"):
                total_vertices_before += len(full_geom.exterior.coords)
            elif hasattr(full_geom, "geoms"):
                for part in full_geom.geoms:
                    if hasattr(part, "exterior"):
                        total_vertices_before += len(part.exterior.coords)

            # Attempt simplification.
            simplified_geom = _simplify_geometry_for_display(
                full_geom, tolerance_m=tolerance_m
            )

            # Fallback to full geometry if simplification fails.
            if simplified_geom is None or simplified_geom.is_empty:
                display_feat = dict(feat)
                display_feat.setdefault(
                    "_simplified", False
                )  # Mark as not simplified (fallback)
                display_features.append(display_feat)
                if hasattr(full_geom, "exterior"):
                    total_vertices_after += len(full_geom.exterior.coords)
                elif hasattr(full_geom, "geoms"):
                    for part in full_geom.geoms:
                        if hasattr(part, "exterior"):
                            total_vertices_after += len(part.exterior.coords)
            else:
                # Use simplified geometry.
                display_feat = dict(feat)
                display_feat["geometry"] = mapping(simplified_geom)
                display_feat["_simplified"] = True  # Mark as simplified
                display_features.append(display_feat)
                simplified_features += 1

                if hasattr(simplified_geom, "exterior"):
                    total_vertices_after += len(
                        simplified_geom.exterior.coords)
                elif hasattr(simplified_geom, "geoms"):
                    for part in simplified_geom.geoms:
                        if hasattr(part, "exterior"):
                            total_vertices_after += len(part.exterior.coords)
        except Exception:
            # On any error, include full feature unchanged.
            display_feat = dict(feat)
            display_feat.setdefault(
                "_simplified", False
            )  # Mark as not simplified (error)
            display_features.append(display_feat)

    # Calculate vertex reduction percentage.
    vertex_reduction_pct = 0.0
    if total_vertices_before > 0:
        vertex_reduction_pct = 100.0 * (
            1.0 - (total_vertices_after / total_vertices_before)
        )

    metrics = {
        "total_features": total_features,
        "simplified_features": simplified_features,
        "excluded_features": excluded_features,
        "total_vertices_before": total_vertices_before,
        "total_vertices_after": total_vertices_after,
        "vertex_reduction_percent": round(vertex_reduction_pct, 2),
    }

    return display_features, metrics
