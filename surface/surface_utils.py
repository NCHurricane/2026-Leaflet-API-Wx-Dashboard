from config.style_config import (
    SURFACE_FIXED_STYLE_CONFIG,
    resolve_surface_style_config,
)
from config.geo_config import STATES_FULL, STATE_BOUNDS
from config.surface_config import (
    build_temperature_gradient_levels_colors,
    TEMPERATURE_COLORMAP,
    TEMPERATURE_MIN_F,
    TEMPERATURE_MAX_F,
    FEELS_LIKE_COLORMAP,
    FEELS_LIKE_MIN_F,
    FEELS_LIKE_MAX_F,
)
from scipy.ndimage import gaussian_filter
from metpy.units import units
from metpy.calc import reduce_point_density, wind_components
from metpy.plots import StationPlot, USCOUNTIES, sky_cover, current_weather
from dateutil import tz
from datetime import datetime, timezone
import cartopy.feature as cfeature
import cartopy.crs as ccrs
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.offsetbox import AnnotationBbox, OffsetImage
import matplotlib.image as mpimg
import matplotlib.patheffects as PathEffects
import matplotlib.pyplot as plt
from font_utils import register_montserrat_fonts
from geo_utils import (
    load_state_geometries as _load_state_geometries_impl,
    build_conus_geometry as _build_conus_geometry_impl,
    get_us_country_geometry as _get_us_country_geometry_impl,
)
import os
import json
import time
import requests
import pandas as pd
import numpy as np
import matplotlib
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed

matplotlib.use("Agg")

# MetPy Imports

# Ensure all Montserrat weights are available to Matplotlib.
register_montserrat_fonts()

# SURFACE_FIXED_STYLE_CONFIG and resolve_surface_style_config are imported
# from config.style_config — the single source of truth for all workflow styles.


# --- STATE GEOMETRY CACHE (for region masking) ---
_STATE_GEOM_CACHE = None
_CONUS_GEOM_CACHE = None
_US_COUNTRY_GEOM_CACHE = None
_CITIES_CACHE = {}
# Cache for pre-computed viewport mask geometries keyed by (state_code, lon0, lon1, lat0, lat1)
_REGION_MASK_CACHE = {}
# Cache for pre-projected matplotlib Path objects keyed by the same mask_key + optional suffix
_MASK_PATH_CACHE = {}

# --- BASEMAP CACHE PATHS ---
BASEMAP_CACHE_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "basemap_cache"
)
os.makedirs(BASEMAP_CACHE_DIR, exist_ok=True)
BASEMAP_CACHE_VERSION = "nomask_v1"


def get_basemap_path(state_code: str, style_config: dict = None) -> str:
    """Return the expected path for a pre-rendered basemap PNG."""
    return os.path.join(
        BASEMAP_CACHE_DIR,
        f"{state_code.upper()}_{BASEMAP_CACHE_VERSION}.png",
    )


def basemap_exists(state_code: str, style_config: dict = None) -> bool:
    """Return True if a pre-rendered basemap PNG exists for this state."""
    return os.path.exists(get_basemap_path(state_code))


def _add_geometry_patch(
    ax, geom, cache_key, facecolor, edgecolor, linewidth, alpha, zorder
):
    """
    Pre-project a Shapely geometry into the axes' native data CRS and add it
    as a PathPatch, bypassing Cartopy's slow add_geometries rendering pipeline.
    Projected paths are cached by cache_key so repeated renders skip reprojection.
    """
    from matplotlib.patches import PathPatch
    from matplotlib.path import Path

    global _MASK_PATH_CACHE
    cached_path = _MASK_PATH_CACHE.get(cache_key)
    if cached_path is None:
        source_crs = ccrs.PlateCarree()
        proj = ax.projection
        all_verts, all_codes = [], []
        polys = (
            list(geom.geoms)
            if geom.geom_type in ("MultiPolygon", "GeometryCollection")
            else [geom]
        )
        for poly in polys:
            if not hasattr(poly, "exterior"):
                continue
            for ring in [poly.exterior] + list(poly.interiors):
                coords = np.array(ring.coords)
                if len(coords) < 3:
                    continue
                lons, lats = coords[:, 0], coords[:, 1]
                pts = proj.transform_points(source_crs, lons, lats)
                xy = pts[:, :2]
                valid = np.isfinite(xy).all(axis=1)
                xy = xy[valid]
                if len(xy) < 3:
                    continue
                n = len(xy)
                codes = np.full(n, Path.LINETO, dtype=np.uint8)
                codes[0] = Path.MOVETO
                codes[-1] = Path.CLOSEPOLY
                all_verts.append(xy)
                all_codes.append(codes)
        if not all_verts:
            return
        verts = np.concatenate(all_verts)
        codes = np.concatenate(all_codes)
        cached_path = Path(verts, codes)
        _MASK_PATH_CACHE[cache_key] = cached_path

    patch = PathPatch(
        cached_path,
        facecolor=facecolor,
        edgecolor=edgecolor,
        linewidth=linewidth,
        alpha=alpha,
        zorder=zorder,
        transform=ax.transData,
    )
    ax.add_patch(patch)


def _perf_enabled(style_config):
    val = style_config.get("perf_debug", True)
    if isinstance(val, str):
        return val.lower() in ("1", "true", "yes", "on")
    return bool(val)


def _perf_log(enabled, stage, start_time):
    if enabled:
        print(f"[surface/perf] {stage}: {(time.time() - start_time):.3f}s")


def _is_gradient_parameter(parameter):
    return parameter.startswith("Temperature Gradient") or parameter.startswith(
        "Feels Like Gradient"
    )


def _load_state_geometries():
    """Load and cache US state polygon geometries from Natural Earth.

    Delegates to geo_utils.load_state_geometries() — the single shared
    implementation — and keeps the module-level cache reference in sync.
    """
    global _STATE_GEOM_CACHE
    result = _load_state_geometries_impl()
    _STATE_GEOM_CACHE = result
    return result


def _build_conus_geometry():
    """Build and cache a lower-48 CONUS union geometry from state polygons.

    Delegates to geo_utils.build_conus_geometry().
    """
    global _CONUS_GEOM_CACHE
    result = _build_conus_geometry_impl()
    _CONUS_GEOM_CACHE = result
    return result


def _get_us_country_geometry():
    """Load and cache USA country polygon from Natural Earth.

    Delegates to geo_utils.get_us_country_geometry().
    """
    global _US_COUNTRY_GEOM_CACHE
    result = _get_us_country_geometry_impl()
    _US_COUNTRY_GEOM_CACHE = result
    return result


# --- 1. CONFIGURATION ---


# --- 2. CALCULATION HELPERS ---


def calc_wind_chill(temp_f, speed_kts):
    speed_mph = speed_kts * 1.15078
    wc = (
        35.74
        + (0.6215 * temp_f)
        - (35.75 * np.power(speed_mph, 0.16))
        + (0.4275 * temp_f * np.power(speed_mph, 0.16))
    )
    return wc


def calc_relative_humidity(t_f, td_f):
    t_c = (t_f - 32) * 5 / 9
    td_c = (td_f - 32) * 5 / 9
    es = 6.112 * np.exp((17.67 * t_c) / (t_c + 243.5))
    e = 6.112 * np.exp((17.67 * td_c) / (td_c + 243.5))
    rh = (e / es) * 100
    return np.clip(rh, 0, 100)


def calc_heat_index(t_f, rh):
    hi = 0.5 * (t_f + 61.0 + ((t_f - 68.0) * 1.2) + (rh * 0.094))
    if isinstance(hi, pd.Series):
        mask = hi > 80
        if mask.any():
            t = t_f[mask]
            r = rh[mask]
            hi_full = (
                -42.379
                + 2.04901523 * t
                + 10.14333127 * r
                - 0.22475541 * t * r
                - 0.00683783 * t * t
                - 0.05481717 * r * r
                + 0.00122874 * t * t * r
                + 0.00085282 * t * r * r
                - 0.00000199 * t * t * r * r
            )
            hi[mask] = hi_full
    return hi


# --- 3. DATA ACQUISITION & CACHING ---


def get_cache_path(state_code, reference_dt=None):
    base_path = os.path.dirname(os.path.abspath(__file__))
    if reference_dt is None:
        reference_dt = datetime.now(timezone.utc)
    if reference_dt.tzinfo is None:
        reference_dt = reference_dt.replace(tzinfo=timezone.utc)

    cache_dir = os.path.join(
        base_path,
        "surface_data",
        state_code.upper(),
        reference_dt.strftime("%Y"),
        reference_dt.strftime("%m"),
        reference_dt.strftime("%d"),
    )
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir, os.path.join(cache_dir, "data.csv")


def is_cache_valid(file_path, minutes=30):
    if not os.path.exists(file_path):
        return False
    if (time.time() - os.path.getmtime(file_path)) < (minutes * 60):
        return True
    return False


def process_dataframe(df, state_code):
    rename_map = {
        "station": "station_id",
        "lat": "latitude",
        "lon": "longitude",
        "tmpf": "air_temperature",
        "dwpf": "dew_point_temperature",
        "sknt": "wind_speed",
        "drct": "wind_dir",
        "relh": "relative_humidity",
        "alti": "altimeter",
        "vsby": "visibility",
        "gust": "wind_gust",
        "mslp": "mean_sea_level_pressure",
        "wxcodes": "wxcodes",
    }
    actual_rename = {k: v for k, v in rename_map.items() if k in df.columns}
    df = df.rename(columns=actual_rename)

    numeric_cols = [
        "air_temperature",
        "dew_point_temperature",
        "wind_speed",
        "wind_dir",
        "latitude",
        "longitude",
        "relative_humidity",
        "altimeter",
        "visibility",
        "wind_gust",
        "mean_sea_level_pressure",
    ]

    for c in numeric_cols:
        if c not in df.columns:
            df[c] = np.nan
        df[c] = pd.to_numeric(df[c], errors="coerce")

    if "wxcodes" not in df.columns:
        df["wxcodes"] = np.nan

    df = df.dropna(subset=["latitude", "longitude", "air_temperature"])
    if df.empty:
        return df

    wspd_safe = df["wind_speed"].fillna(0)
    wdir_safe = df["wind_dir"].fillna(0)
    u, v = wind_components(
        wspd_safe.values * units.knots, wdir_safe.values * units.degrees
    )
    df["u"] = u.m
    df["v"] = v.m

    df["peak_wind"] = df["wind_gust"].fillna(df["wind_speed"])
    df["wind_chill"] = calc_wind_chill(df["air_temperature"], wspd_safe)

    if df["relative_humidity"].isna().all():
        if "dew_point_temperature" in df.columns:
            df["relative_humidity"] = calc_relative_humidity(
                df["air_temperature"],
                df["dew_point_temperature"].fillna(df["air_temperature"]),
            )
        else:
            df["relative_humidity"] = 50

    df["heat_index"] = calc_heat_index(
        df["air_temperature"], df["relative_humidity"])

    wspd_mph = wspd_safe * 1.15078
    cond_cold = (df["air_temperature"] <= 50) & (wspd_mph >= 3)
    cond_hot = df["air_temperature"] >= 80
    df["feels_like"] = df["air_temperature"]
    df.loc[cond_cold, "feels_like"] = df.loc[cond_cold, "wind_chill"]
    df.loc[cond_hot, "feels_like"] = df.loc[cond_hot, "heat_index"]

    return df


def fetch_nws_current_observations(state_code):
    """
    Fetch current surface observations from NWS API (api.weather.gov).
    Returns DataFrame in the same format as IEM METAR data for compatibility.
    Falls back gracefully if NWS is unavailable or sparse.
    """
    if state_code.upper() not in STATES_FULL:
        return pd.DataFrame()

    state_bounds = STATE_BOUNDS.get(state_code.upper())
    if not state_bounds:
        return pd.DataFrame()

    # STATE_BOUNDS format: [west, east, south, north]
    west, east, south, north = state_bounds
    center_lat = (north + south) / 2.0
    center_lon = (east + west) / 2.0

    try:
        # NWS gridpoint endpoint
        gridpoint_url = (
            f"https://api.weather.gov/points/{center_lat:.2f},{center_lon:.2f}"
        )
        resp = requests.get(gridpoint_url, timeout=10)
        resp.raise_for_status()
        gridpoint_data = resp.json()

        # Extract grid point ID for observations
        if 'properties' not in gridpoint_data:
            return pd.DataFrame()

        grid_id = gridpoint_data['properties'].get('gridId')
        grid_x = gridpoint_data['properties'].get('gridX')
        grid_y = gridpoint_data['properties'].get('gridY')

        if not (grid_id and grid_x is not None and grid_y is not None):
            return pd.DataFrame()

        # Fetch observations from that grid point
        obs_url = f"https://api.weather.gov/gridpoints/{grid_id}/{grid_x},{grid_y}/observations/latest"
        obs_resp = requests.get(obs_url, timeout=10)
        obs_resp.raise_for_status()
        obs_data = obs_resp.json()

        if 'features' not in obs_data or not obs_data['features']:
            return pd.DataFrame()

        # Convert NWS format to METAR-like format for compatibility
        records = []
        for feature in obs_data['features']:
            props = feature.get('properties', {})
            if not props:
                continue

            # Extract key fields and standardize names
            record = {
                'station': props.get('station', '').split('/')[-1],
                'tmpf': props.get('temperature'),
                'dwpf': props.get('dewpoint'),
                'relh': props.get('relativeHumidity'),
                'drct': props.get('windDirection'),
                'sknt': props.get('windSpeed'),
                'vsby': props.get('visibility'),
                'alti': props.get('seaLevelPressure'),
                'mslp': props.get('seaLevelPressure'),
                'gust': props.get('windGust'),
                'valid': props.get('timestamp'),
            }
            if pd.notna(record['tmpf']) and pd.notna(record['dwpf']):
                record['feelsx'] = record['tmpf']
            records.append(record)

        if not records:
            return pd.DataFrame()

        df = pd.DataFrame(records)
        return process_dataframe(df, state_code)

    except Exception as e:
        print(f"[WARN] NWS current fetch failed for {state_code.upper()}: {e}")
        return pd.DataFrame()


def fetch_metar_data(state_code, use_nws_first=False):
    """
    Fetch current METAR observations for a state.
    Uses IEM by default. When use_nws_first=True, tries NWS first for
    current-mode flows, then falls back to IEM.
    """
    # Try NWS first for current data
    if use_nws_first:
        try:
            df_nws = fetch_nws_current_observations(state_code)
            if not df_nws.empty and len(df_nws) > 5:
                return df_nws
        except Exception:
            pass

    # Fall back to IEM
    cache_dir, cache_file = get_cache_path(state_code)
    base_path = os.path.dirname(os.path.abspath(__file__))
    legacy_cache_file = os.path.join(
        base_path, "surface_data", state_code.upper(), "data.csv"
    )

    for candidate in (cache_file, legacy_cache_file):
        if is_cache_valid(candidate, minutes=15):
            try:
                df = pd.read_csv(candidate)
                if not df.empty:
                    if candidate != cache_file:
                        try:
                            df.to_csv(cache_file, index=False)
                        except Exception:
                            pass
                    return process_dataframe(df, state_code)
                else:
                    os.remove(candidate)
            except Exception:
                pass

    if state_code.upper() == "CONUS":
        all_dfs = []
        states = [
            state for state in STATES_FULL.keys() if state not in ["AK", "HI", "CONUS"]
        ]

        max_workers = min(12, max(4, len(states)))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_state = {
                executor.submit(fetch_metar_data, state): state for state in states
            }
            for future in as_completed(future_to_state):
                state = future_to_state[future]
                try:
                    df_state = future.result()
                    if not df_state.empty:
                        all_dfs.append(df_state)
                except Exception as e:
                    print(f"API Error {state}: {e}")

        if not all_dfs:
            return pd.DataFrame()
        combined_df = pd.concat(all_dfs, ignore_index=True)
        combined_df.to_csv(cache_file, index=False)
        return combined_df

    network_id = f"{state_code.upper()}_ASOS"
    api_url = (
        f"https://mesonet.agron.iastate.edu/api/1/currents.json?network={network_id}"
    )
    try:
        resp = requests.get(api_url, timeout=20)
        resp.raise_for_status()
        data = resp.json().get("data", [])
        if not data:
            return pd.DataFrame()

        df_processed = process_dataframe(pd.DataFrame(data), state_code)
        if not df_processed.empty:
            df_processed.to_csv(cache_file, index=False)
        return df_processed
    except Exception as e:
        print(f"API Error {state_code}: {e}")
        return pd.DataFrame()


def get_weather_symbol_index(wx_code):
    if pd.isna(wx_code) or not wx_code:
        return 0
    search_str = " ".join(wx_code) if isinstance(
        wx_code, list) else str(wx_code)

    mapping = {
        "FC": 99,
        "TS": 95,
        "GR": 89,
        "SHRA": 80,
        "+RA": 65,
        "RA": 63,
        "-RA": 61,
        "DZ": 53,
        "PL": 79,
        "IC": 76,
        "+SN": 75,
        "SN": 73,
        "-SN": 71,
        "FG": 45,
        "BR": 10,
        "HZ": 5,
        "FU": 4,
        "SQ": 18,
    }
    sorted_keys = sorted(mapping.keys(), key=len, reverse=True)
    for key in sorted_keys:
        if key in search_str:
            return mapping[key]
    return 0


# --- 4 PLOTTING UTILS ---
def plot_cities(
    ax,
    extent_bounds,
    filename="us-cities.json",
    density_scale=1.0,
    collision_w_factor=0.05,
    collision_h_factor=0.02,
    font_size=10,
    z_cities=502,
    text_color="white",
    text_bg_color="black",
    text_bg_alpha=0.5,
    font_family="Montserrat",
    font_weight="black",
    box_style="round,pad=0.2",
    halo_width=1,
    halo_color="black",
):
    try:
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cities_path = os.path.join(root_dir, "data", filename)
        if not os.path.exists(cities_path):
            cities_path = os.path.join(root_dir, "data", "us-cities.json")

        cities = _CITIES_CACHE.get(cities_path)
        if cities is None:
            with open(cities_path, "r") as f:
                raw_data = json.load(f)

            cities = []
            if isinstance(raw_data, dict):
                for k, v in raw_data.items():
                    if isinstance(v, list) and len(v) >= 2:
                        cities.append(
                            {
                                "city": k,
                                "latitude": v[0],
                                "longitude": v[1],
                                "rank": 9999,
                            }
                        )
            elif isinstance(raw_data, list):
                cities = raw_data

            def _city_priority(city):
                try:
                    rank_val = float(city.get("rank"))
                except (TypeError, ValueError):
                    rank_val = 9999.0
                return rank_val

            cities.sort(key=_city_priority)
            _CITIES_CACHE[cities_path] = cities

        min_lon, max_lon, min_lat, max_lat = extent_bounds
        drawn_bboxes = []
        text_w = (max_lon - min_lon) * collision_w_factor * density_scale
        text_h = (max_lat - min_lat) * collision_h_factor * density_scale

        for c in cities:
            lat, lon = float(c["latitude"]), float(c["longitude"])
            if not (
                (min_lat - 0.1) <= lat <= (max_lat + 0.1)
                and (min_lon - 0.1) <= lon <= (max_lon + 0.1)
            ):
                continue

            cx_min, cx_max = lon - (text_w / 2.0), lon + (text_w / 2.0)
            cy_min, cy_max = lat - (text_h / 2.0), lat + (text_h / 2.0)

            if any(
                cx_min < bx_max
                and cx_max > bx_min
                and cy_min < by_max
                and cy_max > by_min
                for bx_min, bx_max, by_min, by_max in drawn_bboxes
            ):
                continue

            txt = ax.text(
                lon,
                lat,
                c["city"].upper(),
                transform=ccrs.PlateCarree(),
                fontsize=font_size,
                color=text_color,
                fontname=font_family,
                fontweight=font_weight,
                ha="center",
                va="center",
                zorder=z_cities + 1,
                clip_on=True,
                bbox=dict(
                    facecolor=text_bg_color,
                    alpha=text_bg_alpha,
                    edgecolor="none",
                    boxstyle=box_style,
                ),
            )
            txt.set_path_effects(
                [PathEffects.withStroke(
                    linewidth=halo_width, foreground=halo_color)]
            )
            drawn_bboxes.append((cx_min, cx_max, cy_min, cy_max))

    except Exception as e:
        print(f"City plot error: {e}")


# --- 6. MAIN GENERATION ---


def generate_surface_map(
    state_code,
    output_dir,
    logo_file,
    show_places=False,
    parameter="Station Plot",
    style_config=None,
    use_smoothing=False,
    custom_extent=None,
    use_nws_current=False,
):
    raise RuntimeError(
        "surface.generate_surface_map is disabled in Phase 0. "
        "Rendering was removed from surface_utils; use unified weather/export pipeline."
    )

    style_config = resolve_surface_style_config(style_config)

    perf = _perf_enabled(style_config)
    t_total = time.time()

    try:
        # Z-order defaults (overridden by style_config zorder_* keys)
        zo = {
            "land": 0,
            "counties": 1,
            "water": 1,
            "gradient": 1,
            "contour_lines": 2,
            "highways": 2,
            "country_mask": 3,
            "borders": 4,
            "contour_labels": 10,
            "scatter": 505,
            "scatter_text": 510,
            "gradient_values": 1500,
            "region_mask": 500,
            "state_border": 501,
            "cities": 502,
            "hud": 2000,
            "logos": 2000,
        }
        for k in zo:
            v = style_config.get(f"zorder_{k}")
            if v is not None:
                zo[k] = int(v)
        zo["state_border"] = max(zo["state_border"], zo["borders"] + 1)

        # Style Unpacking
        font_size = int(style_config.get("font_size", 12))
        dot_size = int(style_config.get("dot_size", 500))
        density_km = float(
            style_config.get(
                "density_km", 330 -
                (int(style_config.get("station_density", 5)) * 30)
            )
        )
        city_text_size = int(style_config.get("city_text_size", 10))
        city_collision_w = float(style_config.get("city_collision_w", 0.05))
        city_collision_h = float(style_config.get("city_collision_h", 0.02))
        show_counties = style_config.get("show_counties", False)
        county_width = float(style_config.get("county_width", 0.5))
        county_color = style_config.get("county_color", "#585858")

        # Base Map Styling
        land_color = style_config.get("land_color", "#585858")
        ocean_color = style_config.get("ocean_color", "#A0C8F0")
        coastline_width = float(style_config.get("coastline_width", 0.8))
        coastline_color = style_config.get("coastline_color", "#000000")

        # Country Styling
        show_country = style_config.get("show_country", True)
        if isinstance(show_country, str):
            show_country = show_country.lower() not in ("false", "0", "no")
        country_border_width = float(
            style_config.get("country_border_width", 0.8))
        country_border_color = style_config.get(
            "country_border_color", "black")

        # State Styling
        show_states = style_config.get("show_states", True)
        if isinstance(show_states, str):
            show_states = show_states.lower() not in ("false", "0", "no")
        state_border_width = float(style_config.get("state_border_width", 0.5))
        state_border_color = style_config.get("state_border_color", "black")

        # City text styling
        city_text_color = style_config.get("city_text_color", "white")
        city_text_bg_color = style_config.get("city_text_bg_color", "black")
        city_text_bg_alpha = float(style_config.get("city_text_bg_alpha", 0.5))

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
        lake_color = style_config.get("lake_color", "#A0C8F0")
        lake_outline_color = style_config.get("lake_outline_color", "#333333")
        lake_outline_width = float(style_config.get("lake_outline_width", 0.5))

        # Rivers
        show_rivers = style_config.get("show_rivers", False)
        if isinstance(show_rivers, str):
            show_rivers = show_rivers.lower() not in ("false", "0", "no")
        river_color = style_config.get("river_color", "#A0C8F0")
        river_width = float(style_config.get("river_width", 0.5))

        # Selection border styling
        sel_border_width = float(style_config.get("sel_border_width", 0.5))
        sel_border_color = style_config.get("sel_border_color", "white")

        # Smoothing
        smooth_sigma = int(style_config.get("smooth_sigma", 5))

        # HUD Colors
        hud_left_text_color = style_config.get("hud_left_text_color", "white")
        hud_left_bg_color = style_config.get("hud_left_bg_color", "black")
        hud_left_edge_color = style_config.get(
            "hud_left_edge_color", "#555555")
        hud_left_opacity = float(style_config.get("hud_left_opacity", 0.7))
        hud_right_text_color = style_config.get("hud_right_text_color", "gold")
        hud_right_bg_color = style_config.get("hud_right_bg_color", "black")
        hud_right_edge_color = style_config.get(
            "hud_right_edge_color", "#555555")
        hud_right_opacity = float(style_config.get("hud_right_opacity", 0.7))

        output_time_utc = datetime.now(timezone.utc)
        image_dir = os.path.join(
            output_dir,
            state_code.upper(),
            output_time_utc.strftime("%Y"),
            output_time_utc.strftime("%m"),
            output_time_utc.strftime("%d"),
        )
        os.makedirs(image_dir, exist_ok=True)

        t_fetch = time.time()
        df = fetch_metar_data(state_code, use_nws_first=use_nws_current)
        _perf_log(perf, "fetch_metar_data", t_fetch)
        if df.empty:
            return None, "No Surface Data Available."

        # Determine map extent from STATE_BOUNDS (avoids outlier stations)
        sc = state_code.upper()

        # Custom extent overrides state bounds
        valid_custom_extent = None
        if custom_extent is not None:
            try:
                s_in, n_in, w_in, e_in = [float(v) for v in custom_extent]
                if n_in > s_in and e_in > w_in:
                    valid_custom_extent = (s_in, n_in, w_in, e_in)
            except Exception:
                valid_custom_extent = None

        if valid_custom_extent is not None:
            ext_lon0, ext_lon1, ext_lat0, ext_lat1 = (
                valid_custom_extent[2],
                valid_custom_extent[3],
                valid_custom_extent[0],
                valid_custom_extent[1],
            )
        elif sc in STATE_BOUNDS:
            sb = STATE_BOUNDS[sc]
            ext_lon0, ext_lon1, ext_lat0, ext_lat1 = sb
        else:
            b = 1.5
            ext_lon0 = df["longitude"].min() - b
            ext_lon1 = df["longitude"].max() + b
            ext_lat0 = df["latitude"].min() - b
            ext_lat1 = df["latitude"].max() + b

        # Filter data to within the map bounds (drop far-flung outlier stations)
        if sc != "CONUS" or valid_custom_extent is not None:
            buf = 1.5
            in_bounds = (
                (df["longitude"] >= ext_lon0 - buf)
                & (df["longitude"] <= ext_lon1 + buf)
                & (df["latitude"] >= ext_lat0 - buf)
                & (df["latitude"] <= ext_lat1 + buf)
            )
            df = df[in_bounds].reset_index(drop=True)
            if df.empty:
                return None, "No Surface Data Available."

        center_lon = (ext_lon0 + ext_lon1) / 2
        center_lat = (ext_lat0 + ext_lat1) / 2

        # Create projection early so we can compute the true projected aspect
        proj = ccrs.LambertConformal(
            central_longitude=center_lon,
            central_latitude=center_lat,
        )

        # Compute aspect ratio from projected extent (not raw lat/lon)
        ext_corners = np.array(
            [
                [ext_lon0, ext_lat0],
                [ext_lon1, ext_lat0],
                [ext_lon1, ext_lat1],
                [ext_lon0, ext_lat1],
            ]
        )
        proj_corners = proj.transform_points(
            ccrs.PlateCarree(), ext_corners[:, 0], ext_corners[:, 1]
        )
        proj_w = proj_corners[:, 0].max() - proj_corners[:, 0].min()
        proj_h = proj_corners[:, 1].max() - proj_corners[:, 1].min()
        data_aspect = proj_w / proj_h

        font_family = style_config.get("font_family", "Montserrat")

        fig_height = 7.2
        # Precompute margins so we can size the figure for the axes area
        left_margin = float(style_config.get("figure_left_margin", 0.02))
        bottom_margin = float(style_config.get(
            "figure_bottom_margin_station" if parameter == "Station Plot"
            else "figure_bottom_margin_other",
            0.20 if parameter == "Station Plot" else 0.12,
        ))
        right_margin = float(style_config.get("figure_right_margin", 0.02))
        top_margin = float(style_config.get("figure_top_margin", 0.02))
        ax_width = 1.0 - left_margin - right_margin
        ax_height = 1.0 - bottom_margin - top_margin

        # Size figure so axes area aspect matches projected map aspect
        fig_width = data_aspect * (ax_height / ax_width) * fig_height

        # Scale HUD/logo sizes relative to the widest figure (12.8")
        # Floor at 0.55 so text stays readable on narrow figures
        scale_factor = max(fig_width / 12.8, 0.55)
        city_text_size = int(city_text_size * scale_factor)
        font_size = int(font_size * scale_factor)
        # Smaller for station plots (many fields per station)
        station_font_scale = float(
            style_config.get("station_font_scale", 0.55))
        station_font_size = max(7, int(font_size * station_font_scale))
        dot_size = int(dot_size * scale_factor)

        fig = plt.figure(figsize=(fig_width, fig_height), dpi=150)
        ax = fig.add_axes(
            [left_margin, bottom_margin, ax_width, ax_height], projection=proj
        )

        # Use a pre-rendered basemap for known state extents.
        # The basemap contains all static cartographic layers: land, ocean, coastline,
        # borders, states, counties, lakes, rivers, highways, and selected-state border.
        # Custom extents and Station Plot always draw from scratch.
        _use_basemap = (
            valid_custom_extent is None
            and parameter != "Station Plot"
            and sc in STATE_BOUNDS
            and basemap_exists(sc, style_config)
        )

        t_base = time.time()
        if _use_basemap:
            _bm = plt.imread(get_basemap_path(sc, style_config))
            _bg_ax = fig.add_axes([0, 0, 1, 1], label="basemap_bg", zorder=0)
            _bg_ax.imshow(_bm, aspect="auto", interpolation="nearest")
            _bg_ax.axis("off")
            _bg_ax.set_zorder(0)
            ax.set_zorder(1)
            ax.patch.set_alpha(0)  # Let basemap show through axes background
            _perf_log(perf, "load_basemap", t_base)
        else:
            ax.add_feature(cfeature.LAND, facecolor=land_color,
                           zorder=zo["land"])
            ax.add_feature(cfeature.OCEAN, facecolor=ocean_color,
                           zorder=zo["land"])
            ax.add_feature(
                cfeature.COASTLINE.with_scale("10m"),
                linewidth=coastline_width,
                edgecolor=coastline_color,
                zorder=zo["borders"],
            )
            if show_country:
                ax.add_feature(
                    cfeature.BORDERS,
                    linewidth=country_border_width,
                    edgecolor=country_border_color,
                    zorder=zo["borders"],
                )
            if show_states:
                ax.add_feature(
                    cfeature.STATES,
                    linewidth=state_border_width,
                    edgecolor=state_border_color,
                    zorder=zo["borders"],
                )
            if show_counties:
                ax.add_feature(
                    USCOUNTIES.with_scale("5m"),
                    linewidth=county_width,
                    edgecolor=county_color,
                    zorder=zo["counties"],
                )

            # Lakes
            if show_lakes:
                ax.add_feature(
                    cfeature.LAKES.with_scale("50m"),
                    facecolor=lake_color,
                    edgecolor=lake_outline_color,
                    linewidth=lake_outline_width,
                    zorder=zo["water"],
                )

            # Rivers
            if show_rivers:
                ax.add_feature(
                    cfeature.RIVERS.with_scale("50m"),
                    edgecolor=river_color,
                    linewidth=river_width,
                    zorder=zo["water"],
                )

            # Highways
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
                        zorder=zo["highways"],
                    )
                except Exception:
                    pass
            _perf_log(perf, "draw_base_features", t_base)

        ax.set_extent([ext_lon0, ext_lon1, ext_lat0, ext_lat1],
                      crs=ccrs.PlateCarree())
        x_min, x_max = ax.get_xlim()
        y_min, y_max = ax.get_ylim()
        x_span = x_max - x_min
        y_span = y_max - y_min
        expand_top = float(style_config.get("map_margin_top", 0.0))
        expand_bottom = float(style_config.get("map_margin_bottom", 0.0))
        expand_left = float(style_config.get("map_margin_left", 0.0))
        expand_right = float(style_config.get("map_margin_right", 0.0))

        ax.set_xlim(x_min - x_span * expand_left,
                    x_max + x_span * expand_right)
        ax.set_ylim(y_min - y_span * expand_bottom,
                    y_max + y_span * expand_top)

        # Data processing
        xy = proj.transform_points(
            ccrs.PlateCarree(), df["longitude"].values, df["latitude"].values
        )

        # --- DATA PREP LOGIC ---
        # If Gradient: Use ALL data for the colors (df_plot).
        # We will calculate a separate 'text mask' later if needed.
        if _is_gradient_parameter(parameter):
            df_plot = df.copy()
        else:
            # Standard thinning for Station Plots
            radius = density_km * 1000
            mask = reduce_point_density(xy[:, 0:2], radius)
            df_plot = df[mask].copy()

        # --- 1. STATION PLOT MODE ---
        if parameter == "Station Plot":
            # ... (Standard Station Plot Logic) ...
            df_plot["wx_idx"] = 0
            if "wxcodes" in df_plot.columns:
                df_plot["wx_idx"] = df_plot["wxcodes"].apply(
                    get_weather_symbol_index)

            sky_vals = np.zeros(len(df_plot))
            if "relative_humidity" in df_plot.columns:
                sky_vals = (
                    (df_plot["relative_humidity"].fillna(0) / 12.5)
                    .clip(0, 8)
                    .round()
                    .astype(int)
                    .values
                )

            station_spacing = float(style_config.get(
                "station_spacing_factor", 1.2))
            sp = StationPlot(
                ax,
                df_plot["longitude"].values,
                df_plot["latitude"].values,
                clip_on=True,
                transform=ccrs.PlateCarree(),
                fontsize=station_font_size,
                spacing=int(station_font_size * station_spacing),
                zorder=zo["scatter"],
            )

            stn_halo_w = int(style_config.get("station_text_halo_width", 2))
            stn_halo_c = style_config.get("station_text_halo_color", "white")
            halo = [PathEffects.withStroke(
                linewidth=stn_halo_w, foreground=stn_halo_c)]

            stn_weight = style_config.get("station_text_weight", "bold")
            sp.plot_parameter(
                "NW", df_plot["air_temperature"].values,
                color=style_config.get("station_temp_color", "#D32F2F"),
                weight=stn_weight,
            ).set_path_effects(halo)
            sp.plot_parameter(
                "SW",
                df_plot["dew_point_temperature"].values,
                color=style_config.get("station_dewpoint_color", "#00796B"),
                weight=stn_weight,
            ).set_path_effects(halo)
            if "mean_sea_level_pressure" in df_plot.columns:
                sp.plot_parameter(
                    "NE",
                    df_plot["mean_sea_level_pressure"].values,
                    color=style_config.get("station_mslp_color", "black"),
                    formatter=lambda v: (
                        f"{int((v - 1000) * 10)}"
                        if v >= 1000
                        else f"{int((v - 900) * 10)}"
                    ),
                ).set_path_effects(halo)
            if "visibility" in df_plot.columns:
                sp.plot_parameter(
                    "E",
                    df_plot["visibility"].values,
                    color=style_config.get(
                        "station_visibility_color", "purple"),
                    formatter=lambda v: f"{v:.0f}" if not pd.isna(v) else "",
                ).set_path_effects(halo)
            sp.plot_symbol("C", sky_vals, sky_cover)
            sp.plot_symbol(
                "W", df_plot["wx_idx"].values, current_weather,
                color=style_config.get("station_weather_color", "#1976D2"),
            )
            sp.plot_barb(
                df_plot["u"].fillna(0).values,
                df_plot["v"].fillna(0).values,
                color=style_config.get("station_wind_color", "#1976D2"),
                length=int(style_config.get("wind_barb_length", 5)),
            )

            # --- STATION MODEL LEGEND (static PNG) ---
            legend_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "img",
                "station_plot_legend.png",
            )
            if os.path.exists(legend_path):
                legend_img = mpimg.imread(legend_path)
                # --- LEGEND TUNING ---
                # Place legend in a dedicated axes that lives in the bottom margin.
                # This axes is part of the figure layout, so bbox_inches="tight"
                # won't clip or shift it.
                leg_pad = float(style_config.get("legend_pad", 0.02))
                leg_ax = fig.add_axes(
                    [
                        # Left edge (fraction of figure)
                        leg_pad,
                        leg_pad,  # Bottom edge
                        # Width (fraction of figure)
                        1.0 - 2 * leg_pad,
                        # Height (fills bottom margin)
                        bottom_margin - 2 * leg_pad,
                    ]
                )
                leg_ax.imshow(legend_img, aspect="equal")
                # Center the image in the axes
                leg_ax.set_anchor("C")
                leg_ax.axis("off")

        # --- 2. TEMPERATURE GRADIENT (BOTH MODES) ---
        elif _is_gradient_parameter(parameter):
            from scipy.interpolate import griddata

            t_gradient = time.time()

            gradient_col = (
                "feels_like"
                if parameter.startswith("Feels Like Gradient")
                else "air_temperature"
            )

            # Grid Setup
            if state_code.upper() == "CONUS" and valid_custom_extent is None:
                # Small buffer so edge states (Maine, Florida Keys, etc.) are
                # fully covered by the interpolated grid.
                extent = [
                    ext_lon0 - 1.5,
                    ext_lon1 + 4.0,
                    ext_lat0 - 1.5,
                    ext_lat1 + 1.5,
                ]
                nx, ny = 400, 250
            else:
                # Use the actual rendered axes extent but floor against the
                # original requested bounds. LambertConformal projection can clip
                # ax.get_extent() smaller than what was passed to set_extent(),
                # leaving gray edges on custom extents. Taking the min/max of
                # both ensures the grid always covers every visible pixel.
                # A larger buffer is used for custom extents where station
                # coverage rarely reaches all four corners of the viewport.
                raw_ext = ax.get_extent(crs=ccrs.PlateCarree())
                buf = 3.0 if valid_custom_extent is not None else 1.5
                extent = [
                    min(raw_ext[0], ext_lon0) - buf,
                    max(raw_ext[1], ext_lon1) + buf,
                    min(raw_ext[2], ext_lat0) - buf,
                    max(raw_ext[3], ext_lat1) + buf,
                ]
                nx, ny = 400, 400

            lon_grid = np.linspace(extent[0], extent[1], nx)
            lat_grid = np.linspace(extent[2], extent[3], ny)
            lon_mesh, lat_mesh = np.meshgrid(lon_grid, lat_grid)

            # Project All Points (for gradient)
            station_xy = proj.transform_points(
                ccrs.PlateCarree(),
                df_plot["longitude"].values,
                df_plot["latitude"].values,
            )
            points = station_xy[:, :2]

            grid_xy = proj.transform_points(
                ccrs.PlateCarree(),
                lon_mesh,
                lat_mesh,
            )
            grid_points = np.column_stack(
                (grid_xy[..., 0].ravel(), grid_xy[..., 1].ravel())
            )

            # Interpolation
            temp_linear = griddata(
                points,
                df_plot[gradient_col].values,
                grid_points,
                method="linear",
            )
            temp_nearest = griddata(
                points,
                df_plot[gradient_col].values,
                grid_points,
                method="nearest",
            )
            temp_linear[np.isnan(temp_linear)
                        ] = temp_nearest[np.isnan(temp_linear)]
            temp_grid = temp_linear.reshape(lon_mesh.shape)

            if use_smoothing:
                temp_grid = gaussian_filter(temp_grid, sigma=smooth_sigma)

            # Custom Colormap
            temp_levels, custom_colors = build_temperature_gradient_levels_colors()
            cmap_name = "custom_temp"
            cm = LinearSegmentedColormap.from_list(
                cmap_name,
                list(zip(np.linspace(0, 1, len(custom_colors)), custom_colors)),
            )
            levels = temp_levels

            # Draw Filled Contours (zorder 1)
            contourf = ax.contourf(
                lon_mesh,
                lat_mesh,
                temp_grid,
                levels=levels,
                cmap=cm,
                transform=ccrs.PlateCarree(),
                extend="both",
                alpha=float(style_config.get("contour_fill_alpha", 0.55)),
                zorder=zo["gradient"],
            )

            # Draw Contour Lines (zorder 2)
            contours = ax.contour(
                lon_mesh,
                lat_mesh,
                temp_grid,
                levels=np.arange(-60, 131, 2),
                colors="none",  # invisible lines
                linewidths=0,
                transform=ccrs.PlateCarree(),
                zorder=zo["contour_lines"],
            )

            # Store flag for deferred values drawing (after masks)
            _draw_gradient_values = "Values" in parameter

            if not _draw_gradient_values:
                # If Clean Mode, just add contour labels
                cl = ax.clabel(contours, fmt="%d",
                               fontsize=int(style_config.get(
                                   "contour_label_size", 9)),
                               inline=True)
                for txt in cl:
                    txt.set_fontname(font_family)
                    txt.set_fontweight(style_config.get(
                        "contour_label_weight", "black"))
                    txt.set_zorder(zo["contour_labels"])

            # Fill masking disabled by request; keep unmasked gradient rendering.

            # Colorbar
            cbar_ax = fig.add_axes([
                float(style_config.get("cbar_left", 0.2)),
                float(style_config.get("cbar_bottom", 0.05)),
                float(style_config.get("cbar_width", 0.6)),
                float(style_config.get("cbar_height", 0.03)),
            ])
            cb = plt.colorbar(contourf, cax=cbar_ax, orientation="horizontal")
            tick_values = np.arange(-60, 131, 2)
            cb.set_ticks(tick_values)
            temp_label_step = (
                20
                if parameter.startswith("Temperature Gradient") and fig_width < 8.0
                else 10
            )
            cb.set_ticklabels(
                [str(t) if t % temp_label_step ==
                 0 else "" for t in tick_values]
            )
            for tick in cb.ax.get_xticklabels():
                tick.set_fontname(font_family)
                tick.set_fontweight(style_config.get(
                    "cbar_tick_weight", "bold"))

            # --- DEFERRED: OVERLAY VALUES (drawn after masks so they're on top) ---
            if _draw_gradient_values:
                radius_text = density_km * 1000
                mask_text = reduce_point_density(xy[:, 0:2], radius_text)
                df_text = df[mask_text]

                for _, row in df_text.iterrows():
                    val = row[gradient_col]
                    if pd.isna(val):
                        continue
                    txt = ax.text(
                        row["longitude"],
                        row["latitude"],
                        str(int(round(val))),
                        transform=ccrs.PlateCarree(),
                        fontsize=font_size,
                        fontname=font_family,
                        fontweight=style_config.get(
                            "value_text_weight", "black"),
                        color=style_config.get("value_text_color", "white"),
                        ha="center",
                        va="center",
                        zorder=zo["gradient_values"],
                        clip_on=True,
                    )
                    txt.set_path_effects(
                        [PathEffects.withStroke(
                            linewidth=int(style_config.get(
                                "value_text_halo_width", 2)),
                            foreground=style_config.get("value_text_halo_color", "black"))]
                    )

            _perf_log(perf, "render_gradient", t_gradient)

        # --- 3. OTHER PARAMETERS ---
        else:
            t_param = time.time()
            params = {
                "Temperature": (
                    "air_temperature",
                    TEMPERATURE_COLORMAP,
                    TEMPERATURE_MIN_F,
                    TEMPERATURE_MAX_F,
                ),
                "Dewpoint": ("dew_point_temperature", "BrBG", 30, 80),
                "Wind Speed": ("wind_speed", "YlOrRd", 0, 40),
                "Relative Humidity": ("relative_humidity", "Greens", 0, 100),
                "Feels Like": (
                    "feels_like",
                    FEELS_LIKE_COLORMAP,
                    FEELS_LIKE_MIN_F,
                    FEELS_LIKE_MAX_F,
                ),
                "Fels Like": (
                    "feels_like",
                    FEELS_LIKE_COLORMAP,
                    FEELS_LIKE_MIN_F,
                    FEELS_LIKE_MAX_F,
                ),
                "Wind Gust": ("peak_wind", "YlOrRd", 0, 60),
                "Altimeter": ("altimeter", "BuPu", 28.5, 31.0),
                "Visibility": ("visibility", "Greys_r", 0, 10),
                "MSLP": ("mean_sea_level_pressure", "BuPu", 990, 1040),
            }
            col, cmap, vmin, vmax = params.get(
                parameter,
                (
                    "air_temperature",
                    TEMPERATURE_COLORMAP,
                    TEMPERATURE_MIN_F,
                    TEMPERATURE_MAX_F,
                ),
            )

            sc = ax.scatter(
                df_plot["longitude"],
                df_plot["latitude"],
                s=dot_size,
                c=df_plot[col],
                cmap=cmap,
                vmin=vmin,
                vmax=vmax,
                alpha=float(style_config.get("scatter_alpha", 0.8)),
                edgecolors=style_config.get("scatter_edge_color", "black"),
                linewidths=float(style_config.get("scatter_edge_width", 0.5)),
                transform=ccrs.PlateCarree(),
                zorder=zo["scatter"],
                clip_on=True,
            )

            for _, r in df_plot.iterrows():
                val = r[col]
                if pd.isna(val):
                    continue

                if parameter == "Altimeter":
                    label_text = f"{float(val):.2f}"
                else:
                    label_text = str(int(round(val)))

                txt = ax.text(
                    r["longitude"],
                    r["latitude"],
                    label_text,
                    transform=ccrs.PlateCarree(),
                    fontsize=font_size,
                    fontname=font_family,
                    weight=style_config.get("value_text_weight", "black"),
                    color=style_config.get("value_text_color", "white"),
                    ha="center",
                    va="center",
                    zorder=zo["scatter_text"],
                    clip_on=True,
                )
                txt.set_path_effects(
                    [PathEffects.withStroke(
                        linewidth=int(style_config.get(
                            "value_text_halo_width", 2)),
                        foreground=style_config.get("value_text_halo_color", "black"))]
                )

            # Add wind arrows for Wind Speed parameter
            if parameter == "Wind Speed":
                offset_lon = float(style_config.get("wind_arrow_offset", 0.01))
                u_vals = df_plot["u"].fillna(0).values
                v_vals = df_plot["v"].fillna(0).values
                mag = np.sqrt(u_vals**2 + v_vals**2)
                mag[mag == 0] = 1
                ax.quiver(
                    df_plot["longitude"].values + offset_lon,
                    df_plot["latitude"].values,
                    u_vals / mag,
                    v_vals / mag,
                    transform=ccrs.PlateCarree(),
                    color=style_config.get("wind_arrow_color", "black"),
                    scale=float(style_config.get("wind_arrow_scale", 25)),
                    width=float(style_config.get("wind_arrow_width", 0.004)),
                    headwidth=float(style_config.get(
                        "wind_arrow_headwidth", 4)),
                    headlength=float(style_config.get(
                        "wind_arrow_headlength", 5)),
                    zorder=zo["scatter"] - 1,
                    clip_on=False,
                )

            cbar_ax = fig.add_axes([
                float(style_config.get("cbar_left", 0.2)),
                float(style_config.get("cbar_bottom", 0.05)),
                float(style_config.get("cbar_width", 0.6)),
                float(style_config.get("cbar_height", 0.03)),
            ])
            cb = plt.colorbar(sc, cax=cbar_ax, orientation="horizontal")
            for tick in cb.ax.get_xticklabels():
                tick.set_fontname(font_family)
                tick.set_fontweight(style_config.get(
                    "cbar_tick_weight", "bold"))
            _perf_log(perf, f"render_parameter:{parameter}", t_param)

        # --- REGION BORDER (selected state outline only) ---
        if state_code.upper() != "CONUS":
            t_mask = time.time()
            try:
                us_states = _load_state_geometries()
                code = state_code.upper()
                if code in us_states:
                    selected_geom = us_states[code]
                    vx0, vx1, vy0, vy1 = ax.get_extent(crs=ccrs.PlateCarree())

                    # Always draw border live so sel_border_color/width are respected
                    simplified_border = _REGION_MASK_CACHE.get(
                        (code, "border"))
                    if simplified_border is None:
                        simplified_border = selected_geom.simplify(
                            0.02, preserve_topology=True
                        )
                        _REGION_MASK_CACHE[(code, "border")
                                           ] = simplified_border
                    border_path_key = (
                        code,
                        round(vx0, 2),
                        round(vx1, 2),
                        round(vy0, 2),
                        round(vy1, 2),
                        "border",
                        sel_border_color,
                        sel_border_width,
                    )
                    _add_geometry_patch(
                        ax,
                        simplified_border,
                        border_path_key,
                        facecolor="none",
                        edgecolor=sel_border_color,
                        linewidth=sel_border_width,
                        alpha=1.0,
                        zorder=zo["state_border"],
                    )
            except Exception as e:
                print(f"Region mask error: {e}")
            _perf_log(perf, "region_masking", t_mask)

        # --- COMMON OVERLAYS ---
        if show_places:
            t_cities = time.time()
            plot_cities(
                ax,
                ax.get_extent(crs=ccrs.PlateCarree()),
                style_config.get("cities_file"),
                float(style_config.get("city_density", 5)) / 5.0,
                city_collision_w,
                city_collision_h,
                city_text_size,
                z_cities=zo["cities"],
                text_color=city_text_color,
                text_bg_color=city_text_bg_color,
                text_bg_alpha=city_text_bg_alpha,
                font_family=font_family,
                font_weight=style_config.get("city_font_weight", "black"),
                box_style=style_config.get("city_box_style", "round,pad=0.2"),
                halo_width=int(style_config.get("city_halo_width", 1)),
                halo_color=style_config.get("city_halo_color", "black"),
            )
            _perf_log(perf, "plot_cities", t_cities)

        # HUD
        dt_local = datetime.now(timezone.utc).astimezone(
            tz.gettz("America/New_York"))
        hud_box = style_config.get("hud_box_style", "round,pad=0.5")
        text_style_left = dict(
            boxstyle=hud_box,
            fc=hud_left_bg_color,
            ec=hud_left_edge_color,
            alpha=hud_left_opacity,
        )
        text_style_right = dict(
            boxstyle=hud_box,
            fc=hud_right_bg_color,
            ec=hud_right_edge_color,
            alpha=hud_right_opacity,
        )

        hud_left_size = int(float(style_config.get(
            "hud_left_size", 15)) * scale_factor)
        hud_right_size = int(
            float(style_config.get("hud_right_size", 15)) * scale_factor
        )
        hud_left_x = float(style_config.get("hud_left_x", 0.03))
        hud_left_y = float(style_config.get("hud_left_y", 0.97))
        hud_right_x = float(style_config.get("hud_right_x", 0.97))
        hud_right_y = float(style_config.get("hud_right_y", 0.97))

        use_target_area = valid_custom_extent is not None
        region_label = (
            "Target Area"
            if use_target_area
            else STATES_FULL.get(state_code, state_code)
        )

        hud_weight = style_config.get("hud_font_weight", "black")
        hud_left_fstyle = style_config.get("hud_left_font_style", "italic")
        hud_spacing = float(style_config.get("hud_line_spacing", 1.15))

        ax.annotate(
            f"{region_label}\nSurface Analysis\n{parameter}",
            xy=(hud_left_x, hud_left_y),
            xycoords="axes fraction",
            fontsize=hud_left_size,
            fontname=font_family,
            fontweight=hud_weight,
            fontstyle=hud_left_fstyle,
            color=hud_left_text_color,
            va="top",
            linespacing=hud_spacing,
            bbox=text_style_left,
            zorder=zo["hud"],
        )
        ax.annotate(
            f"{dt_local.strftime('%m/%d/%Y')}\n{dt_local.strftime('%I:%M %p %Z')}",
            xy=(hud_right_x, hud_right_y),
            xycoords="axes fraction",
            fontsize=hud_right_size,
            fontname=font_family,
            fontweight=hud_weight,
            fontstyle=hud_left_fstyle,
            color=hud_right_text_color,
            ha="right",
            va="top",
            bbox=text_style_right,
            zorder=zo["hud"],
        )

        # --- USER LOGO ---
        # User Custom Logo
        if os.path.exists(logo_file):
            try:
                logo_size = (
                    float(style_config.get("logo_user_size", 0.08)) *
                    scale_factor
                )
                logo_x = float(style_config.get("logo_user_x", 0.98))
                logo_y = float(style_config.get("logo_user_y", 0.01))

                img = mpimg.imread(logo_file)
                ax.add_artist(
                    AnnotationBbox(
                        OffsetImage(img, zoom=logo_size),
                        (logo_x, logo_y),
                        xycoords="axes fraction",
                        frameon=False,
                        box_alignment=(1, 0),
                        zorder=zo["logos"],
                    )
                )
            except Exception:
                pass

        # Pre-render all Cartopy/Matplotlib objects into the renderer cache so
        # that savefig(bbox_inches="tight") only needs to flush, not re-render.
        t_prerender = time.time()
        fig.canvas.draw()
        _perf_log(perf, "pre_render", t_prerender)

        # Save
        date_str = output_time_utc.strftime("%Y%m%d_%H%M%S")
        filename = f"{date_str}_surface_latest.png"
        save_path = os.path.join(image_dir, filename)
        t_save = time.time()
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
        _perf_log(perf, "save_png", t_save)
        plt.close(fig)
        _perf_log(perf, "total_generate_surface_map", t_total)
        return save_path, f"Generated {parameter} Map"

    except Exception as e:
        traceback.print_exc()
        return None, str(e)


def generate_surface_current_layers(
    state_code,
    output_dir,
    logo_file,
    parameter="Station Plot",
    show_places=False,
    use_smoothing=False,
    style_config=None,
    custom_extent=None,
    request_id=None,
):
    raise RuntimeError(
        "surface.generate_surface_current_layers is disabled in Phase 0. "
        "Rendering was removed from surface_utils; use unified weather/export pipeline."
    )

    """
    Generate current surface map with separate component layers for compositing.

    Returns dict with basemap_path, component layer paths, and metadata for
    JavaScript layered compositing (like radar workflow).
    """
    import shutil
    import time as time_module

    os.makedirs(output_dir, exist_ok=True)

    # Create request-scoped layer directory
    timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    session_key = request_id or f"current_{timestamp_str}_{int(time_module.time())}"
    layer_dir = os.path.join(
        output_dir, state_code.upper(), parameter, session_key)

    if os.path.isdir(layer_dir):
        shutil.rmtree(layer_dir, ignore_errors=True)
    os.makedirs(layer_dir, exist_ok=True)

    # Fetch current data
    df = fetch_metar_data(state_code, use_nws_first=True)
    if df.empty:
        return None

    df = process_dataframe(df, state_code)
    if df.empty:
        return None

    # Resolve timestamp for display
    current_utc = datetime.now(timezone.utc)
    local_tz = tz.gettz("America/New_York")

    # Import _render_surface_frame from archive utils
    try:
        from surface.surface_archive_utils import _render_surface_frame
    except ImportError:
        # Fallback if not available
        return None

    style_config = resolve_surface_style_config(style_config)

    # Paths for component layers
    basemap_path = os.path.join(layer_dir, "basemap.png")
    states_path = os.path.join(layer_dir, "states.png")
    counties_path = os.path.join(layer_dir, "counties.png")
    cities_path = os.path.join(layer_dir, "cities.png")
    surface_path = os.path.join(layer_dir, "surface.png")
    static_overlay_path = os.path.join(layer_dir, "static_overlay.png")
    hud_right_path = os.path.join(layer_dir, "hud_right.png")

    import imageio

    try:
        # Render basemap
        basemap_img = _render_surface_frame(
            state_code=state_code,
            df=df.copy(),
            frame_time_utc=current_utc,
            output_path=None,
            logo_file=logo_file,
            parameter=parameter,
            show_places=False,
            use_smoothing=use_smoothing,
            style_config=style_config,
            local_tz=local_tz,
            custom_extent=custom_extent,
            component="basemap",
            transparent_bg=False,
            bbox_tight=False,
        )
        imageio.imwrite(basemap_path, basemap_img)

        # Render states overlay
        states_img = _render_surface_frame(
            state_code=state_code,
            df=df.copy(),
            frame_time_utc=current_utc,
            output_path=None,
            logo_file=logo_file,
            parameter=parameter,
            show_places=False,
            use_smoothing=use_smoothing,
            style_config=style_config,
            local_tz=local_tz,
            custom_extent=custom_extent,
            component="states",
            transparent_bg=True,
            bbox_tight=False,
        )
        imageio.imwrite(states_path, states_img)

        # Render counties overlay
        counties_img = _render_surface_frame(
            state_code=state_code,
            df=df.copy(),
            frame_time_utc=current_utc,
            output_path=None,
            logo_file=logo_file,
            parameter=parameter,
            show_places=False,
            use_smoothing=use_smoothing,
            style_config=style_config,
            local_tz=local_tz,
            custom_extent=custom_extent,
            component="counties",
            transparent_bg=True,
            bbox_tight=False,
        )
        imageio.imwrite(counties_path, counties_img)

        # Render cities overlay
        cities_img = _render_surface_frame(
            state_code=state_code,
            df=df.copy(),
            frame_time_utc=current_utc,
            output_path=None,
            logo_file=logo_file,
            parameter=parameter,
            show_places=show_places,
            use_smoothing=use_smoothing,
            style_config=style_config,
            local_tz=local_tz,
            custom_extent=custom_extent,
            component="cities",
            transparent_bg=True,
            bbox_tight=False,
        )
        imageio.imwrite(cities_path, cities_img)

        # Render surface data layer (temperature/pressure/etc.)
        surface_img = _render_surface_frame(
            state_code=state_code,
            df=df.copy(),
            frame_time_utc=current_utc,
            output_path=None,
            logo_file=logo_file,
            parameter=parameter,
            show_places=show_places,
            use_smoothing=use_smoothing,
            style_config=style_config,
            local_tz=local_tz,
            custom_extent=custom_extent,
            component="surface",
            transparent_bg=True,
            bbox_tight=False,
        )
        imageio.imwrite(surface_path, surface_img)

        # Render static overlay (logo, etc.)
        static_overlay_img = _render_surface_frame(
            state_code=state_code,
            df=df.copy(),
            frame_time_utc=current_utc,
            output_path=None,
            logo_file=logo_file,
            parameter=parameter,
            show_places=False,
            use_smoothing=use_smoothing,
            style_config=style_config,
            local_tz=local_tz,
            custom_extent=custom_extent,
            component="static_overlay",
            transparent_bg=True,
            bbox_tight=False,
        )
        imageio.imwrite(static_overlay_path, static_overlay_img)

        # Render HUD right (timestamp)
        hud_right_img = _render_surface_frame(
            state_code=state_code,
            df=df.copy(),
            frame_time_utc=current_utc,
            output_path=None,
            logo_file=logo_file,
            parameter=parameter,
            show_places=False,
            use_smoothing=use_smoothing,
            style_config=style_config,
            local_tz=local_tz,
            custom_extent=custom_extent,
            component="hud_right",
            transparent_bg=True,
            bbox_tight=False,
        )
        imageio.imwrite(hud_right_path, hud_right_img)

        # Build local timestamp label
        local_label = ""
        try:
            local_label = (
                current_utc.replace(tzinfo=timezone.utc)
                .astimezone(local_tz)
                .strftime("%Y-%m-%d %I:%M %p %Z")
            )
        except Exception:
            pass

        # Return layer metadata (matching radar response structure)
        return {
            "basemap_path": basemap_path,
            "states_path": states_path,
            "counties_path": counties_path,
            "cities_path": cities_path,
            "surface_path": surface_path,
            "static_overlay_path": static_overlay_path,
            "hud_right_path": hud_right_path,
            "layer_dir": layer_dir,
            "frames": [
                {
                    "index": 0,
                    "surface_url": surface_path,
                    "cities_url": cities_path,
                    "counties_url": counties_path,
                    "states_url": states_path,
                    "hud_right_url": hud_right_path,
                    "timestamp_utc": current_utc.isoformat() + "Z",
                    "timestamp_local": local_label,
                }
            ],
        }

    except Exception as e:
        print(f"[ERROR] Error generating surface current layers: {e}")
        traceback.print_exc()
        return None
