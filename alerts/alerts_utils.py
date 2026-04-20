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

try:
    from tools.generate_state_basemaps import (
        _expand_extent as _expand_prebuilt_state_extent,
        get_basemap_path as _get_prebuilt_state_basemap_path,
        _get_geometry_bounds as _get_prebuilt_state_geometry_bounds,
        _load_conus_geometry as _load_prebuilt_conus_geometry,
        _load_state_geometry as _load_prebuilt_state_geometry,
    )

    _PREBUILT_STATE_BASEMAPS_AVAILABLE = True
except Exception:
    _expand_prebuilt_state_extent = None
    _get_prebuilt_state_basemap_path = None
    _get_prebuilt_state_geometry_bounds = None
    _load_prebuilt_conus_geometry = None
    _load_prebuilt_state_geometry = None
    _PREBUILT_STATE_BASEMAPS_AVAILABLE = False

from alerts import alerts_iem_utils

matplotlib.use("Agg")

ACTIVE_ALERTS_CACHE_SECONDS = 60

# Ensure all Montserrat weights are available to Matplotlib.
register_montserrat_fonts()

ALERTS_BASEMAP_CACHE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "basemap_cache",
    "alerts",
)
os.makedirs(ALERTS_BASEMAP_CACHE_DIR, exist_ok=True)
ALERTS_BASEMAP_CACHE_VERSION = "v13"

ALERTS_BASEMAP_LAND_COLOR = "#5c5c5c"
ALERTS_BASEMAP_OCEAN_COLOR = "#152238"
ALERTS_BASEMAP_COASTLINE_WIDTH = 0.5
ALERTS_BASEMAP_COASTLINE_COLOR = "#303030"

# resolve_alerts_style_config is imported from config.style_config,
# the single source of truth for workflow style settings.

_OCEAN_GEOMETRY = None
_OCEAN_GEOMETRY_FAILED = False
_OCEAN_GEOMETRY_RESOLUTION = "50m"
_ALERTS_PREBUILT_VIEW_CACHE = {}
_ALERTS_CONUS_LON_PAD_FRAC = 0.03
_ALERTS_CONUS_MIN_LON_PAD = 1.5
_ALERTS_CONUS_LAT_PAD_FRAC = 0.02
_ALERTS_CONUS_MIN_LAT_PAD = 0.6
_ALERTS_CONUS_TOP_PAD_DEG = 3.5
_ALERTS_CONUS_BOTTOM_PAD_DEG = 0.8

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
# ---------------------------------------------------------------------------
_ZONE_GEOM_CACHE = {}  # zone_id -> (shapely_geom | None, expire_ts)
_ZONE_GEOM_LOCK = threading.Lock()
_ZONE_GEOM_TTL = 6 * 3600  # 6 hours – zone boundaries rarely change
_ZONE_GEOM_MAX_WORKERS = 20  # concurrent HTTP fetches for a batch
_NWS_HEADERS = {
    "User-Agent": "(NCHurricane.com Weather Suite, contact@nchurricane.com)"
}


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
            props = feat.get("properties", {}) if isinstance(feat, dict) else {}
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


def get_ocean_geometry():
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
                            print(f"[WARN] Error refreshing alert cache: {cache_error}")
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

    headers = {"User-Agent": "(NCHurricane.com Weather Suite, contact@nchurricane.com)"}
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
        is_marine_event = bool(props.get("isMarine")) or event_name in marine_events

        if not _is_alert_active_for_time(props, valid_time):
            continue

        color = ALERT_COLORS.get(event_name, "#6699CC")
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

        if not final_geom:
            same_codes = props.get("geocode", {}).get("SAME", [])
            if same_codes:
                if not counties_loaded:
                    CensusCounties.load()
                    counties_loaded = True
                fips_codes = [c[1:] for c in same_codes if len(c) == 6]
                final_geom = CensusCounties.get_geometry_for_fips(fips_codes)
                used_county_fallback = final_geom is not None

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
        cities_path = os.path.join(os.path.dirname(script_dir), "data", filename)

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
            [PathEffects.withStroke(linewidth=halo_width, foreground=halo_color)]
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


def get_alerts_prebuilt_state_basemap_spec(view_key, projection_mode):
    if not _PREBUILT_STATE_BASEMAPS_AVAILABLE:
        return None

    region_key = str(view_key or "").strip().upper()
    if not region_key:
        return None

    normalized_mode = _normalize_alerts_projection_mode(projection_mode)
    if normalized_mode not in {"auto", "state_lambert", "platecarree"}:
        return None

    cache_key = (region_key, normalized_mode)

    # Re-check when cached value is None so newly generated basemaps are picked up
    # without requiring a server restart.
    if cache_key in _ALERTS_PREBUILT_VIEW_CACHE:
        cached = _ALERTS_PREBUILT_VIEW_CACHE.get(cache_key)
        if cached is not None:
            return cached

    spec = None
    try:
        source_path = _get_prebuilt_state_basemap_path(region_key)
        if source_path and os.path.exists(source_path):
            if region_key == "CONUS":
                geometry = _load_prebuilt_conus_geometry()
            else:
                geometry = _load_prebuilt_state_geometry(region_key)

            west, east, south, north = _get_prebuilt_state_geometry_bounds(geometry)
            if _expand_prebuilt_state_extent is not None:
                if region_key == "CONUS":
                    # Match tools/generate_state_basemaps.py CONUS framing.
                    west, east, south, north = _expand_prebuilt_state_extent(
                        west,
                        east,
                        south,
                        north,
                        lon_frac=_ALERTS_CONUS_LON_PAD_FRAC,
                        lat_frac=_ALERTS_CONUS_LAT_PAD_FRAC,
                        min_lon_pad=_ALERTS_CONUS_MIN_LON_PAD,
                        min_lat_pad=_ALERTS_CONUS_MIN_LAT_PAD,
                    )
                    # Add explicit vertical safety room for HUD/title and Keys.
                    south = max(-90.0, south - _ALERTS_CONUS_BOTTOM_PAD_DEG)
                    north = min(90.0, north + _ALERTS_CONUS_TOP_PAD_DEG)
                else:
                    west, east, south, north = _expand_prebuilt_state_extent(
                        west,
                        east,
                        south,
                        north,
                    )
            west, east = _normalize_extent_longitudes(west, east)
            if west > east:
                # Antimeridian-crossing extent (e.g. Alaska):
                # wrap east into the same hemisphere before averaging.
                center_lon = west + ((east + 360.0 - west) / 2.0)
            else:
                center_lon = west + ((east - west) / 2.0)
            center_lon = ((center_lon + 180.0) % 360.0) - 180.0
            center_lat = south + ((north - south) / 2.0)
            source_for_mode = source_path
            if normalized_mode == "platecarree" and region_key != "CONUS":
                # State prebuilt rasters are Lambert-based; avoid reusing them in
                # explicit platecarree mode.
                source_for_mode = None
            spec = {
                "source_path": source_for_mode,
                "extent": (west, east, south, north),
                "center": (center_lon, center_lat),
                "geometry": geometry,
            }
    except Exception:
        spec = None

    _ALERTS_PREBUILT_VIEW_CACHE[cache_key] = spec
    return spec


def alerts_basemap_cache_eligible(
    crop_to_alerts,
    valid_custom_extent,
    view_key,
):
    if crop_to_alerts:
        return False
    if valid_custom_extent is not None:
        return False
    if view_key is None:
        return False
    return True


def get_alerts_basemap_cache_path(view_key, projection_mode, style_config):
    def _coerce_bool(value, default):
        if value is None:
            return default
        if isinstance(value, str):
            return value.strip().lower() not in ("false", "0", "no", "off")
        return bool(value)

    static_style = {
        "projection_mode": projection_mode,
        "prebuilt_state_source": bool(
            get_alerts_prebuilt_state_basemap_spec(view_key, projection_mode)
        ),
        "land_color": ALERTS_BASEMAP_LAND_COLOR,
        "ocean_color": ALERTS_BASEMAP_OCEAN_COLOR,
        "coastline_width": ALERTS_BASEMAP_COASTLINE_WIDTH,
        "coastline_color": ALERTS_BASEMAP_COASTLINE_COLOR,
        "show_country": _coerce_bool(style_config.get("show_country", True), True),
        "country_width": float(style_config.get("country_width", 0.8)),
        "country_color": style_config.get("country_color", "#000000"),
        "show_lakes": _coerce_bool(style_config.get("show_lakes", True), True),
        "lake_color": style_config.get("lake_color", "#4774bd"),
        "lake_outline_color": style_config.get("lake_outline_color", "#333333"),
        "lake_outline_width": float(style_config.get("lake_outline_width", 0.5)),
        "show_rivers": _coerce_bool(style_config.get("show_rivers", False), False),
        "river_color": style_config.get("river_color", "#A0C8F0"),
        "river_width": float(style_config.get("river_width", 0.5)),
        "show_highways": _coerce_bool(style_config.get("show_highways", False), False),
        "highway_color": style_config.get("highway_color", "#888888"),
        "highway_width": float(style_config.get("highway_width", 0.8)),
        "highway_opacity": float(style_config.get("highway_opacity", 0.6)),
    }
    digest = hashlib.sha1(
        json.dumps(static_style, sort_keys=True).encode("utf-8")
    ).hexdigest()[:12]

    region_key = str(view_key or "MISC").upper()
    region_key = "".join(
        ch if (ch.isalnum() or ch in ("-", "_")) else "_" for ch in region_key
    )
    region_cache_dir = os.path.join(ALERTS_BASEMAP_CACHE_DIR, region_key)
    os.makedirs(region_cache_dir, exist_ok=True)

    return os.path.join(
        region_cache_dir,
        f"{projection_mode}_{ALERTS_BASEMAP_CACHE_VERSION}_{digest}.png",
    )


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
            cfeature.BORDERS, linewidth=country_width, edgecolor=country_color
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


def draw_alerts_prebuilt_state_basemap(
    fig,
    *,
    basemap_path,
    left_margin,
    bottom_margin,
    ax_width,
    ax_height,
):
    bg_ax = fig.add_axes(
        [left_margin, bottom_margin, ax_width, ax_height],
        label="alerts_prebuilt_state_basemap",
        zorder=0,
    )
    bg_ax.imshow(plt.imread(basemap_path), aspect="auto", interpolation="nearest")
    bg_ax.axis("off")
    bg_ax.set_zorder(0)


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
            cfeature.STATES,
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
                    selected_geom = unary_union(conus_states) if conus_states else None
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


def ensure_alerts_basemap_cache(
    cache_path,
    *,
    fig_width,
    fig_height,
    left_margin,
    bottom_margin,
    ax_width,
    ax_height,
    proj,
    ext_lon0,
    ext_lon1,
    ext_lat0,
    ext_lat1,
    static_layer_kwargs,
    state_basemap_source_path=None,
    fig_bg_color="white",
):
    if os.path.exists(cache_path):
        return

    cache_parent_dir = os.path.dirname(cache_path)
    if cache_parent_dir:
        os.makedirs(cache_parent_dir, exist_ok=True)

    fig = plt.figure(figsize=(fig_width, fig_height), dpi=150, facecolor=fig_bg_color)
    use_prebuilt_state_basemap = bool(
        state_basemap_source_path and os.path.exists(state_basemap_source_path)
    )
    if use_prebuilt_state_basemap:
        draw_alerts_prebuilt_state_basemap(
            fig,
            basemap_path=state_basemap_source_path,
            left_margin=left_margin,
            bottom_margin=bottom_margin,
            ax_width=ax_width,
            ax_height=ax_height,
        )

    ax = fig.add_axes(
        [left_margin, bottom_margin, ax_width, ax_height], projection=proj
    )
    # Hide GeoAxes frame/outline so cached basemaps don't bake in side borders.
    ax.set_frame_on(False)
    ax.set_axis_off()
    try:
        ax.outline_patch.set_visible(False)
    except Exception:
        pass
    ax.set_extent([ext_lon0, ext_lon1, ext_lat0, ext_lat1], crs=ccrs.PlateCarree())
    if use_prebuilt_state_basemap:
        draw_alerts_static_overlays(ax, **static_layer_kwargs)
    else:
        draw_alerts_static_layers(ax, **static_layer_kwargs)
    ax.patch.set_alpha(0)
    plt.savefig(cache_path, dpi=150, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close(fig)


def apply_alerts_cached_basemap(fig, ax, cache_path):
    _bg_ax = fig.add_axes([0, 0, 1, 1], label="alerts_basemap_bg", zorder=0)
    _bg_ax.imshow(plt.imread(cache_path), aspect="auto", interpolation="nearest")
    _bg_ax.axis("off")
    _bg_ax.set_zorder(0)
    ax.set_zorder(1)
    ax.patch.set_alpha(0)


def generate_alerts_map(
    state_code,
    output_dir,
    category_filter="All Alerts",
    wfo_code=None,
    show_places=False,
    crop_to_alerts=True,
    logo_path=None,
    style_config=None,
    custom_extent=None,
    source="nws",
    region=None,
):
    raise RuntimeError(
        "alerts.generate_alerts_map is disabled in Phase 0. "
        "Rendering was removed from alerts_utils; use unified weather/export pipeline."
    )

    if style_config is None:
        style_config = {}
    style_config = resolve_alerts_style_config(style_config)

    perf_start = time.perf_counter()
    perf_last = perf_start

    def perf_mark(stage_name):
        nonlocal perf_last
        now = time.perf_counter()
        step_ms = (now - perf_last) * 1000.0
        total_ms = (now - perf_start) * 1000.0
        print(
            f"[perf] alerts_map::{stage_name}: {step_ms:.1f} ms "
            f"(total {total_ms:.1f} ms)"
        )
        perf_last = now

    hud_left_size = style_config.get("hud_left_size", 12)
    hud_left_x = style_config.get("hud_left_x", 0.03)
    hud_left_y = style_config.get("hud_left_y", 0.97)
    hud_right_size = style_config.get("hud_right_size", 12)
    hud_right_x = style_config.get("hud_right_x", 0.97)
    hud_right_y = style_config.get("hud_right_y", 0.97)
    logo_user_size = style_config.get("logo_user_size", 0.08)
    logo_user_x = style_config.get("logo_user_x", 0.98)
    logo_user_y = style_config.get("logo_user_y", 0.01)
    legend_size = style_config.get("legend_size", 13)
    legend_cols = style_config.get("legend_cols", "auto")
    cities_file = style_config.get("cities_file", "us-cities.json")
    city_density_input = int(style_config.get("city_density", 5))
    city_text_size = int(style_config.get("city_text_size", 8))
    city_collision_w = float(style_config.get("city_collision_w", 0.05))
    city_collision_h = float(style_config.get("city_collision_h", 0.02))
    show_counties = style_config.get("show_counties", False)
    county_width = float(style_config.get("county_width", 0.5))
    county_color = style_config.get("county_color", "#d3d3d3")
    density_scale = city_density_input / 5.0
    show_places = bool(show_places or style_config.get("show_places", False))

    # City text styling
    city_text_color = style_config.get("city_text_color", "#d8e700")
    city_text_bg_color = style_config.get("city_text_bg_color", "#141414")
    city_text_bg_alpha = float(style_config.get("city_text_bg_alpha", 0.1))

    # Highways
    show_highways = style_config.get("show_highways", False)
    if isinstance(show_highways, str):
        show_highways = show_highways.lower() not in ("false", "0", "no")
    highway_color = style_config.get("highway_color", "#888888")
    highway_width = float(style_config.get("highway_width", 0.8))
    highway_opacity = float(style_config.get("highway_opacity", 0.6))

    # Lakes
    show_lakes = style_config.get("show_lakes", True)
    if isinstance(show_lakes, str):
        show_lakes = show_lakes.lower() not in ("false", "0", "no")
    lake_color = style_config.get("lake_color", "#4774bd")
    lake_outline_color = style_config.get("lake_outline_color", "#333333")
    lake_outline_width = float(style_config.get("lake_outline_width", 0.5))

    # Rivers
    show_rivers = style_config.get("show_rivers", False)
    if isinstance(show_rivers, str):
        show_rivers = show_rivers.lower() not in ("false", "0", "no")
    river_color = style_config.get("river_color", "#A0C8F0")
    river_width = float(style_config.get("river_width", 0.5))

    # Base map styling from config (replacing module-level constants).
    land_color = style_config.get("land_color", ALERTS_BASEMAP_LAND_COLOR)
    ocean_color = style_config.get("ocean_color", ALERTS_BASEMAP_OCEAN_COLOR)
    coastline_width = float(
        style_config.get("coastline_width", ALERTS_BASEMAP_COASTLINE_WIDTH)
    )
    coastline_color = style_config.get(
        "coastline_color", ALERTS_BASEMAP_COASTLINE_COLOR
    )
    font_family = style_config.get("font_family", "Montserrat")

    # Country borders
    show_country = style_config.get("show_country", True)
    country_width = float(style_config.get("country_width", 0.8))
    country_color = style_config.get("country_color", "#000000")

    # State borders
    show_states = style_config.get("show_states", False)
    state_width = float(style_config.get("state_width", 0.5))
    state_color = style_config.get("state_color", "#000000")

    # Alert polygon styling
    alert_line_width = float(style_config.get("alert_line_width", 1.1))
    alert_alpha = float(style_config.get("alert_alpha", 0.35))
    show_storm_alerts = bool(style_config.get("show_storm_alerts", True))
    show_zone_alerts = bool(style_config.get("show_zone_alerts", True))

    # Selection border styling
    sel_border_width = float(style_config.get("sel_border_width", 1))
    sel_border_color = style_config.get("sel_border_color", "#d1d1d1")

    # HUD text & box styling
    hud_left_text_color = style_config.get("hud_left_text_color", "#ffffff")
    hud_left_bg_color = style_config.get("hud_left_bg_color", "#000000")
    hud_left_edge_color = style_config.get("hud_left_edge_color", "#555555")
    hud_left_alpha = float(style_config.get("hud_left_alpha", 0.6))
    hud_right_text_color = style_config.get("hud_right_text_color", "#ffd700")
    hud_right_bg_color = style_config.get("hud_right_bg_color", "#000000")
    hud_right_edge_color = style_config.get("hud_right_edge_color", "#555555")
    hud_right_alpha = float(style_config.get("hud_right_alpha", 0.6))

    # Z-order defaults (overridden by style_config zorder_* keys)
    zo = {
        "counties": 10,
        "region_mask": 20,
        "state_border": 21,
        "alerts": 30,
        "cities": 100,
        "logos": 150,
        "hud": 200,
        "legend": 1001,
    }
    if style_config:
        for k in zo:
            v = style_config.get(f"zorder_{k}")
            if v is not None:
                zo[k] = int(v)
    states_zorder = 4
    zo["state_border"] = max(zo["state_border"], states_zorder + 1)
    perf_mark("style_setup")

    region_folder = state_code.upper() if state_code else "CONUS"
    output_time_utc = datetime.now(timezone.utc)
    image_dir = os.path.join(
        output_dir,
        region_folder,
        output_time_utc.strftime("%Y"),
        output_time_utc.strftime("%m"),
        output_time_utc.strftime("%d"),
    )
    os.makedirs(image_dir, exist_ok=True)

    full_state = STATES_FULL.get(state_code, state_code) if state_code else "National"

    exclude_list = []
    is_national_view = state_code is None and wfo_code is None and region != "CONUS"
    if is_national_view:
        exclude_list = ["AK", "HI"]

    wfo_display_name = "National"
    if wfo_code:
        raw_name = next(
            (name for name, code in NWS_WFO_MAP.items() if code == wfo_code), wfo_code
        )
        clean_name = raw_name.replace(" (No Filter)", "").split(",")[0]
        wfo_display_name = f"NWS {clean_name}"

    fetch_state = None if wfo_code else state_code
    raw_alerts, data_source = fetch_active_alerts_with_source(
        fetch_state, source=source
    )
    perf_mark("fetch_active_alerts")

    clean_alerts = process_alerts(
        raw_alerts,
        category_filter,
        wfo_code,
        exclude_regions=exclude_list,
        bbox_filter=custom_extent,
        show_storm_alerts=show_storm_alerts,
        show_zone_alerts=show_zone_alerts,
    )
    perf_mark("process_alerts")

    projection_mode = style_config.get("projection_mode", "auto")

    # Determine extent bounds (same format as STATE_BOUNDS: [lon0, lon1, lat0, lat1])
    valid_custom_extent = None
    if custom_extent is not None:
        try:
            s_in, n_in, w_in, e_in = [float(v) for v in custom_extent]
            if n_in > s_in and e_in > w_in:
                valid_custom_extent = normalize_alerts_custom_extent(
                    (s_in, n_in, w_in, e_in)
                )
        except Exception:
            valid_custom_extent = None

    view_key = (
        "CONUS"
        if (is_national_view or region == "CONUS")
        else (state_code.upper() if state_code else None)
    )
    is_conus_view = view_key == "CONUS"
    effective_projection_mode = (
        "platecarree"
        if (
            projection_mode == "auto"
            and (is_conus_view or valid_custom_extent is not None)
        )
        else projection_mode
    )
    use_cached_basemap = alerts_basemap_cache_eligible(
        crop_to_alerts,
        valid_custom_extent,
        view_key,
    )
    prebuilt_state_basemap = (
        get_alerts_prebuilt_state_basemap_spec(view_key, effective_projection_mode)
        if use_cached_basemap
        else None
    )

    if is_conus_view and effective_projection_mode == "platecarree":
        show_country = False

    if valid_custom_extent is not None:
        ext_lon0, ext_lon1, ext_lat0, ext_lat1 = (
            valid_custom_extent[2],
            valid_custom_extent[3],
            valid_custom_extent[0],
            valid_custom_extent[1],
        )
    elif prebuilt_state_basemap is not None:
        ext_lon0, ext_lon1, ext_lat0, ext_lat1 = prebuilt_state_basemap["extent"]
    elif is_national_view:
        ext_lon0, ext_lon1, ext_lat0, ext_lat1 = STATE_BOUNDS.get(
            "CONUS", [-125, -70, 25, 50]
        )
    elif region == "CONUS":
        ext_lon0, ext_lon1, ext_lat0, ext_lat1 = STATE_BOUNDS.get(
            "CONUS", [-125, -70, 25, 50]
        )
    elif state_code and state_code in STATE_BOUNDS:
        ext_lon0, ext_lon1, ext_lat0, ext_lat1 = STATE_BOUNDS[state_code]
    elif clean_alerts:
        ext_lon0 = min(item["geometry"].bounds[0] for item in clean_alerts) - 0.5
        ext_lon1 = max(item["geometry"].bounds[2] for item in clean_alerts) + 0.5
        ext_lat0 = min(item["geometry"].bounds[1] for item in clean_alerts) - 0.5
        ext_lat1 = max(item["geometry"].bounds[3] for item in clean_alerts) + 0.5
    else:
        ext_lon0, ext_lon1, ext_lat0, ext_lat1 = STATE_BOUNDS.get(
            "CONUS", [-125, -70, 25, 50]
        )

    if prebuilt_state_basemap is not None:
        center_lon, center_lat = prebuilt_state_basemap["center"]
    else:
        if ext_lon0 > ext_lon1:
            center_lon = ext_lon0 + ((ext_lon1 + 360.0 - ext_lon0) / 2.0)
            center_lon = ((center_lon + 180.0) % 360.0) - 180.0
        else:
            center_lon = (ext_lon0 + ext_lon1) / 2.0
        center_lat = (ext_lat0 + ext_lat1) / 2.0

    try:
        plot_extent_geom = box(ext_lon0, ext_lat0, ext_lon1, ext_lat1)
        clean_alerts = [
            item
            for item in clean_alerts
            if item["geometry"].intersects(plot_extent_geom)
        ]
    except Exception:
        pass

    no_alerts_in_view = len(clean_alerts) == 0

    # Build projection (same approach as surface_utils: always state-centered Lambert)
    if effective_projection_mode == "original":
        proj = ccrs.LambertConformal(central_longitude=-96, central_latitude=35)
        if state_code == "NC":
            proj = ccrs.LambertConformal(central_longitude=-79.0, central_latitude=35.5)
    elif effective_projection_mode == "platecarree":
        proj = ccrs.PlateCarree()
    else:
        # "auto" and "state_lambert" both use state-centered Lambert
        proj = ccrs.LambertConformal(
            central_longitude=center_lon,
            central_latitude=center_lat,
        )

    # Compute projected aspect ratio by sampling many points along each edge of
    # the extent rectangle.  A 4-corner-only approach underestimates projected
    # height for LambertConformal because latitude lines are arcs whose midpoints
    # extend beyond corner projections, leading to an overwide figure with dead
    # space on the sides.
    _N = 50
    _sample_lon0 = ext_lon0
    _sample_lon1 = ext_lon1 + 360.0 if ext_lon0 > ext_lon1 else ext_lon1
    edge_lons = np.concatenate(
        [
            np.linspace(_sample_lon0, _sample_lon1, _N),  # bottom edge
            np.full(_N, _sample_lon1),  # right edge
            np.linspace(_sample_lon1, _sample_lon0, _N),  # top edge
            np.full(_N, _sample_lon0),  # left edge
        ]
    )
    edge_lats = np.concatenate(
        [
            np.full(_N, ext_lat0),  # bottom edge
            np.linspace(ext_lat0, ext_lat1, _N),  # right edge
            np.full(_N, ext_lat1),  # top edge
            np.linspace(ext_lat1, ext_lat0, _N),  # left edge
        ]
    )
    proj_pts = proj.transform_points(ccrs.PlateCarree(), edge_lons, edge_lats)
    proj_w = proj_pts[:, 0].max() - proj_pts[:, 0].min()
    proj_h = proj_pts[:, 1].max() - proj_pts[:, 1].min()
    data_aspect = proj_w / max(proj_h, 1.0)

    fig_height = 7.2
    bottom_margin = float(style_config.get("figure_bottom_margin", 0.18))
    top_margin = 0.0
    left_margin = 0.0
    right_margin = 0.0
    ax_width = 1.0 - left_margin - right_margin
    ax_height = 1.0 - bottom_margin - top_margin
    fig_width = data_aspect * (ax_height / ax_width) * fig_height

    # Scale HUD/logo sizes relative to the widest figure (12.8")
    scale_factor = max(fig_width / 12.8, 0.55)
    hud_left_size = int(hud_left_size * scale_factor)
    hud_right_size = int(hud_right_size * scale_factor)
    city_text_size = int(city_text_size * scale_factor)
    legend_size = int(legend_size * scale_factor)
    logo_user_size = logo_user_size * scale_factor

    # Use legend panel background as the figure fill so side padding strips
    # and the bottom legend area share the same colour.
    fig_bg_color = style_config.get("legend_panel_bg_color", "white")
    fig = plt.figure(figsize=(fig_width, fig_height), dpi=150, facecolor=fig_bg_color)

    ax = fig.add_axes(
        [left_margin, bottom_margin, ax_width, ax_height], projection=proj
    )
    # Remove GeoAxes edge lines to avoid apparent left/right padding in CONUS renders.
    ax.set_frame_on(False)
    ax.set_axis_off()
    try:
        ax.outline_patch.set_visible(False)
    except Exception:
        pass
    perf_mark("extent_projection_layout")

    static_layer_kwargs = {
        "land_color": land_color,
        "ocean_color": ocean_color,
        "coastline_width": coastline_width,
        "coastline_color": coastline_color,
        "show_country": show_country,
        "country_width": country_width,
        "country_color": country_color,
        "show_lakes": show_lakes,
        "lake_color": lake_color,
        "lake_outline_color": lake_outline_color,
        "lake_outline_width": lake_outline_width,
        "show_rivers": show_rivers,
        "river_color": river_color,
        "river_width": river_width,
        "show_highways": show_highways,
        "highway_color": highway_color,
        "highway_width": highway_width,
        "highway_opacity": highway_opacity,
    }
    state_overlay_kwargs = {
        "state_code": state_code,
        "region": region,
        "is_national_view": is_national_view,
        "show_states": show_states,
        "state_width": state_width,
        "state_color": state_color,
        "sel_border_width": sel_border_width,
        "sel_border_color": sel_border_color,
        "states_zorder": states_zorder,
        "state_border_zorder": zo["state_border"],
        "selected_geometry": (
            prebuilt_state_basemap.get("geometry")
            if isinstance(prebuilt_state_basemap, dict)
            else None
        ),
    }
    basemap_mode = "direct_draw"
    prebuilt_anchor_source = (
        prebuilt_state_basemap["source_path"]
        if prebuilt_state_basemap is not None
        else None
    )

    # Composite prebuilt state basemap directly (no intermediate cache layer).
    # Dynamic bottom margins make the alerts basemap cache unreliable, and the
    # prebuilt state PNGs from basemap_cache/states/ already provide the heavy
    # land/ocean rendering.  Only lightweight overlays are drawn at runtime.
    if prebuilt_anchor_source and os.path.exists(prebuilt_anchor_source):
        draw_alerts_prebuilt_state_basemap(
            fig,
            basemap_path=prebuilt_anchor_source,
            left_margin=left_margin,
            bottom_margin=bottom_margin,
            ax_width=ax_width,
            ax_height=ax_height,
        )
        ax.patch.set_alpha(0)
        draw_alerts_static_overlays(ax, **static_layer_kwargs)
        basemap_mode = "prebuilt_direct"
    else:
        draw_alerts_static_layers(ax, **static_layer_kwargs)
        basemap_mode = "direct_draw"

    draw_alerts_state_overlays(ax, **state_overlay_kwargs)

    perf_mark(f"static_basemap_{basemap_mode}")

    unique_events = set()
    all_geoms = []
    fill_alpha = max(0.0, min(1.0, alert_alpha))

    if clean_alerts:
        for item in clean_alerts:
            unique_events.add(item["event"])
            all_geoms.append(item["geometry"])
            draw_line_width = alert_line_width
            if state_code is None and region == "CONUS":
                draw_line_width = max(alert_line_width, 0.2)
            shape_feature = ShapelyFeature(
                [item["geometry"]],
                ccrs.PlateCarree(),
                facecolor=to_rgba(item["color"], alpha=fill_alpha),
                edgecolor=item["color"],
                linewidth=draw_line_width,
            )
            ax.add_feature(shape_feature, zorder=zo["alerts"])

    if show_counties:
        # Prefer state-scoped county shapefiles when rendering a single-state map.
        if state_code and state_code.upper() != "CONUS":
            census_feature = CensusCounties.get_feature_for_state(state_code)
        else:
            census_feature = CensusCounties.get_feature()

        if census_feature:
            ax.add_feature(
                census_feature,
                linewidth=county_width,
                edgecolor=county_color,
                facecolor="none",
                zorder=zo["counties"],
            )

    if crop_to_alerts and all_geoms:
        crop_lon0 = min(g.bounds[0] for g in all_geoms) - 0.5
        crop_lon1 = max(g.bounds[2] for g in all_geoms) + 0.5
        crop_lat0 = min(g.bounds[1] for g in all_geoms) - 0.5
        crop_lat1 = max(g.bounds[3] for g in all_geoms) + 0.5
        ax.set_extent(
            [crop_lon0, crop_lon1, crop_lat0, crop_lat1], crs=ccrs.PlateCarree()
        )
    else:
        _set_lon0 = ext_lon0
        _set_lon1 = ext_lon1 + 360.0 if ext_lon0 > ext_lon1 else ext_lon1
        ax.set_extent(
            [_set_lon0, _set_lon1, ext_lat0, ext_lat1], crs=ccrs.PlateCarree()
        )

    if show_places:
        current_extent = ax.get_extent(crs=ccrs.PlateCarree())
        plot_cities(
            ax,
            current_extent,
            filename=cities_file,
            density_scale=density_scale,
            collision_w_factor=city_collision_w,
            collision_h_factor=city_collision_h,
            font_size=city_text_size,
            z_cities=zo["cities"],
            text_color=city_text_color,
            text_bg_color=city_text_bg_color,
            text_bg_alpha=city_text_bg_alpha,
            font_family=font_family,
            font_weight=style_config.get("city_font_weight", "black"),
            font_style=style_config.get("city_font_style", "italic"),
            box_style=style_config.get("city_box_style", "round,pad=0.2"),
            halo_width=float(style_config.get("city_halo_width", 1.0)),
            halo_color=style_config.get("city_halo_color", "black"),
            text_alpha=float(style_config.get("city_text_alpha", 0.95)),
        )
    perf_mark("map_overlays")

    if no_alerts_in_view:
        fig.text(
            0.5,
            max(0.065, bottom_margin * 0.58),
            "NO ACTIVE ALERTS AT THIS TIME",
            ha="center",
            fontsize=max(
                12,
                int(
                    hud_left_size
                    * float(style_config.get("no_alerts_text_size_mult", 1.25))
                ),
            ),
            fontname=font_family,
            fontstyle=style_config.get("hud_font_style", "italic"),
            fontweight=style_config.get("hud_font_weight", "black"),
            color=style_config.get("no_alerts_text_color", "#ff0000"),
        )

    legend_patches = [
        mpatches.Patch(color=ALERT_COLORS.get(e, DEFAULT_COLOR), label=e)
        for e in sorted(list(unique_events), key=lambda x: ALERT_PRIORITY.get(x, 999))
    ]
    if legend_patches:
        legend_cols_eff = resolve_alerts_legend_columns(
            legend_cols, len(legend_patches), fig_width * ax_width
        )
        leg = fig.legend(
            handles=legend_patches,
            loc="center",
            bbox_to_anchor=(0.5, bottom_margin * 0.48),
            bbox_transform=fig.transFigure,
            ncol=legend_cols_eff,
            frameon=False,
            fontsize=int(legend_size),
            title="Active Alerts",
            title_fontsize=int(legend_size) + 2,
            prop={
                "family": font_family,
                "weight": style_config.get("legend_font_weight", "bold"),
                "size": int(legend_size),
            },
        )
        leg.get_title().set(
            text=leg.get_title().get_text().upper(),
            color=style_config.get("legend_title_color", "black"),
            fontstyle=style_config.get("legend_title_style", "italic"),
            fontweight=style_config.get("legend_title_weight", "black"),
            fontname=font_family,
        )
        leg.set_zorder(zo["legend"])

    dt_local = datetime.now(timezone.utc).astimezone(tz.gettz("America/New_York"))
    use_target_area = valid_custom_extent is not None
    region_label = (
        "Target Area"
        if use_target_area
        else (wfo_display_name if wfo_code else full_state)
    )
    hud_left_lines = [region_label]
    if category_filter:
        hud_left_lines.append(category_filter)
    hud_left_lines.append("Active Alerts")
    hud_left = "\n".join(hud_left_lines)

    ax.annotate(
        hud_left,
        xy=(hud_left_x, hud_left_y),
        xycoords="axes fraction",
        fontsize=hud_left_size,
        fontname=font_family,
        fontstyle=style_config.get("hud_font_style", "italic"),
        fontweight=style_config.get("hud_font_weight", "black"),
        color=hud_left_text_color,
        va="top",
        ha="left",
        linespacing=float(style_config.get("hud_line_spacing", 1.15)),
        bbox=dict(
            boxstyle=style_config.get("hud_left_box_style", "round,pad=0.5"),
            fc=hud_left_bg_color,
            ec=hud_left_edge_color,
            alpha=hud_left_alpha,
        ),
        zorder=zo["hud"],
    )
    ax.annotate(
        f"{dt_local.strftime('%m/%d/%Y')}\n{dt_local.strftime('%I:%M %p %Z')}",
        xy=(hud_right_x, hud_right_y),
        xycoords="axes fraction",
        fontsize=hud_right_size,
        fontname=font_family,
        fontstyle=style_config.get("hud_font_style", "italic"),
        fontweight=style_config.get("hud_font_weight", "black"),
        color=hud_right_text_color,
        va="top",
        ha="right",
        bbox=dict(
            boxstyle=style_config.get("hud_right_box_style", "round,pad=0.4"),
            fc=hud_right_bg_color,
            ec=hud_right_edge_color,
            alpha=hud_right_alpha,
        ),
        zorder=zo["hud"],
    )

    target_logo = (
        logo_path
        if logo_path
        else os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png")
    )
    if os.path.exists(target_logo):
        try:
            n_img = mpimg.imread(target_logo)
            ax.add_artist(
                AnnotationBbox(
                    OffsetImage(n_img, zoom=logo_user_size),
                    (logo_user_x, logo_user_y),
                    xycoords="axes fraction",
                    frameon=False,
                    box_alignment=(1, 0),
                    zorder=zo["logos"],
                )
            )
        except Exception as e:
            print(f"Error loading logo: {e}")
    perf_mark("legend_hud_logo")

    date_str = output_time_utc.strftime("%Y%m%d_%H%M")
    filename = f"{date_str}_alerts.png"
    save_path = os.path.join(image_dir, filename)
    plt.savefig(
        save_path,
        bbox_inches="tight",
        pad_inches=0.02,
        facecolor=fig.get_facecolor(),
        edgecolor="none",
    )
    plt.close(fig)
    perf_mark("save_png")

    total_ms = (time.perf_counter() - perf_start) * 1000.0
    print(f"[perf] alerts_map::complete: {total_ms:.1f} ms")

    status_message = (
        f"No active {category_filter} at this time."
        if no_alerts_in_view
        else f"Found {len(clean_alerts)} active {category_filter} polygons."
    )
    return (
        save_path,
        status_message,
        data_source,
    )
