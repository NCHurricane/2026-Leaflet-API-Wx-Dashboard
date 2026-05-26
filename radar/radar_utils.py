from config.radar_config import L3_PRODUCTS
from config.style_config import resolve_radar_style_config
from font_utils import register_montserrat_fonts
from matplotlib.offsetbox import AnnotationBbox, OffsetImage
import matplotlib.image as mpimg
from dateutil import tz
from metpy.plots import USCOUNTIES
from siphon.radarserver import RadarServer
from datetime import datetime, timedelta, timezone
import matplotlib.patheffects as PathEffects
import cartopy.crs as ccrs
import cartopy.feature as cfeature
import numpy as np
import imageio.v2 as imageio
import matplotlib.pyplot as plt
import io
import os
import json
import glob
import re
import math
import time as _time
import matplotlib
import requests
from shapely.geometry import shape
from matplotlib.lines import Line2D

from alerts import alerts_utils

from listing_cache import (
    cached_call,
    load_json_config as _load_json_config_raw,
    check_dependencies as _check_deps_raw,
)

matplotlib.use("Agg")

# Import GRS colormap functions
try:
    from .radar_colormaps import (
        create_grs_cc_cmap,
        create_grs_bv_cmap,
        create_grs_br_cmap,
        create_grs_zdr_cmap,
        create_grs_vil_cmap,
        create_grs_et_cmap,
        create_grs_sw_cmap,
        create_grs_precip_cmap,
        create_grs_dpa_cmap,
        create_grs_precip_total_cmap,
        create_grs_hca_style,
    )
except ImportError:
    # Fallback if running script directly
    from radar_colormaps import (
        create_grs_cc_cmap,
        create_grs_bv_cmap,
        create_grs_br_cmap,
        create_grs_zdr_cmap,
        create_grs_vil_cmap,
        create_grs_et_cmap,
        create_grs_sw_cmap,
        create_grs_precip_cmap,
        create_grs_dpa_cmap,
        create_grs_precip_total_cmap,
        create_grs_hca_style,
    )


# --- 1. REQUIREMENTS CHECK ---
def check_dependencies():
    """Verifies that all required libraries are installed."""
    required = {
        "streamlit": "streamlit",
        "pyart": "arm-pyart",
        "metpy": "metpy",
        "siphon": "siphon",
        "cartopy": "cartopy",
        "imageio": "imageio",
        "matplotlib": "matplotlib",
        "numpy": "numpy",
    }
    return _check_deps_raw(required)


# Define the list for the dashboard to check
MISSING_LIB_LIST = check_dependencies()

# Ensure all Montserrat weights are available to Matplotlib.
register_montserrat_fonts()


# --- 2. CONFIG LOADERS ---
def load_json_config(filename, default):
    """Loads a JSON configuration file from the script directory."""
    return _load_json_config_raw(
        os.path.dirname(os.path.abspath(__file__)), filename, default
    )


RADAR_SITES = load_json_config(
    "radar_sites.json", {"Newport/Morehead City, NC": "KMHX"}
)

_COORD_LABEL_RE = re.compile(
    r"^\s*-?\d+(?:\.\d+)?\s*°?\s*[NSEW]\s*$", re.IGNORECASE)


def _suppress_geo_labels(ax_obj, fig_obj=None):
    """Hide coordinate ticks/grid labels injected by Cartopy/Py-ART."""
    try:
        ax_obj.tick_params(
            axis="both",
            which="both",
            bottom=False,
            top=False,
            left=False,
            right=False,
            labelbottom=False,
            labelleft=False,
        )
        for tick_label in list(ax_obj.get_xticklabels()) + list(
            ax_obj.get_yticklabels()
        ):
            tick_label.set_visible(False)
    except Exception:
        pass

    text_pool = []
    if fig_obj is not None:
        try:
            text_pool = fig_obj.findobj(
                match=lambda artist: isinstance(artist, matplotlib.text.Text)
            )
        except Exception:
            text_pool = []
    if not text_pool:
        text_pool = list(getattr(ax_obj, "texts", []))

    for txt in text_pool:
        label = txt.get_text() if hasattr(txt, "get_text") else ""
        if _COORD_LABEL_RE.match(str(label or "")):
            txt.set_visible(False)

    try:
        for child in list(ax_obj.get_children()):
            if hasattr(child, "xline_artists") and hasattr(child, "yline_artists"):
                for attr in (
                    "xline_artists",
                    "yline_artists",
                    "xlabel_artists",
                    "ylabel_artists",
                    "top_label_artists",
                    "bottom_label_artists",
                    "left_label_artists",
                    "right_label_artists",
                ):
                    artists = getattr(child, attr, None)
                    if not artists:
                        continue
                    for artist in list(artists):
                        try:
                            artist.set_visible(False)
                        except Exception:
                            pass
    except Exception:
        pass


def _is_radar_alert_event_allowed(event_name: str) -> bool:
    """Allow tornado/severe thunderstorm and flash flood alerts, excluding watches."""
    name = str(event_name or "").strip()
    if not name:
        return False
    if name.startswith("Tornado"):
        return "Watch" not in name
    if name.startswith("Severe Thunderstorm"):
        return "Watch" not in name
    if name.startswith("Flash Flood"):
        return "Watch" not in name
    return False


# --- Radar basemap cache ---
RADAR_BASEMAP_CACHE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "basemap_cache",
    "radar",
)
os.makedirs(RADAR_BASEMAP_CACHE_DIR, exist_ok=True)

# Range rings are drawn at 25 nm, 50 nm, and 100 nm.
# Basemaps are generated with a 1.20× padding factor beyond the 100 nm ring.
_MAX_RANGE_NM = 100
_NM_TO_KM = 1.852
_KM_PER_DEG_LAT = 111.32
_DEFAULT_PADDING_FACTOR = 1.20
_RADAR_OUTPUT_DPI = 150
_RADAR_BASE_FIG_HEIGHT_IN = 7.2


def compute_radar_extent(site_lat, site_lon, padding_factor=_DEFAULT_PADDING_FACTOR):
    """Return (min_lat, max_lat, min_lon, max_lon) for a radar site.

    The extent is the outermost range ring (100 nm) scaled by
    *padding_factor*, converted to degrees.  The longitude offset is
    adjusted for the station's latitude.
    """
    padded_km = _MAX_RANGE_NM * _NM_TO_KM * padding_factor
    lat_offset = padded_km / _KM_PER_DEG_LAT
    lon_offset = padded_km / \
        (_KM_PER_DEG_LAT * math.cos(math.radians(site_lat)))
    return (
        site_lat - lat_offset,
        site_lat + lat_offset,
        site_lon - lon_offset,
        site_lon + lon_offset,
    )


def _compute_extent_ratio(min_lat, max_lat, min_lon, max_lon, projection):
    """Return map width/height ratio in projection space for dynamic figure sizing."""
    corners_ll = np.array(
        [
            [min_lon, min_lat],
            [max_lon, min_lat],
            [max_lon, max_lat],
            [min_lon, max_lat],
        ]
    )

    try:
        corners_proj = projection.transform_points(
            ccrs.PlateCarree(),
            corners_ll[:, 0],
            corners_ll[:, 1],
        )
        xs = corners_proj[:, 0]
        ys = corners_proj[:, 1]
        if np.isfinite(xs).all() and np.isfinite(ys).all():
            width = float(xs.max() - xs.min())
            height = float(ys.max() - ys.min())
            if width > 0 and height > 0:
                return width / height
    except Exception:
        pass

    lat_span = max(max_lat - min_lat, 1e-6)
    lon_span = max(max_lon - min_lon, 1e-6)
    lat_mid = (min_lat + max_lat) * 0.5
    lon_meters = lon_span * max(math.cos(math.radians(lat_mid)), 1e-3)
    return max(lon_meters / lat_span, 1e-3)


def _figure_size_for_extent(min_lat, max_lat, min_lon, max_lon, projection):
    """Compute a non-16:9 figure size from the map extent and projection."""
    ratio = _compute_extent_ratio(
        min_lat, max_lat, min_lon, max_lon, projection)
    fig_height = _RADAR_BASE_FIG_HEIGHT_IN
    fig_width = max(fig_height * ratio, 4.0)
    return fig_width, fig_height


def get_radar_basemap_path(station_id: str) -> str:
    """Return the expected path for a pre-rendered radar basemap PNG."""
    sid = station_id.upper()
    return os.path.join(RADAR_BASEMAP_CACHE_DIR, sid, f"{sid}.png")


def radar_basemap_exists(station_id: str) -> bool:
    """Return True if a pre-rendered basemap PNG exists for this station."""
    sid = station_id.upper()
    new_path = get_radar_basemap_path(sid)
    legacy_path = os.path.join(RADAR_BASEMAP_CACHE_DIR, f"{sid}.png")
    return os.path.exists(new_path) or os.path.exists(legacy_path)


# Keep full-resolution base map layers while avoiding per-frame feature object rebuilds.
_RADAR_NE_SCALE = "10m"
_FEATURE_LAND = cfeature.LAND.with_scale(_RADAR_NE_SCALE)
_FEATURE_LAKES = cfeature.LAKES.with_scale(_RADAR_NE_SCALE)
_FEATURE_RIVERS = cfeature.RIVERS.with_scale(_RADAR_NE_SCALE)
_FEATURE_STATES = cfeature.STATES.with_scale(_RADAR_NE_SCALE)
_FEATURE_ROADS = cfeature.NaturalEarthFeature(
    category="cultural", name="roads", scale=_RADAR_NE_SCALE, facecolor="none"
)
_RADAR_CARTOPY_WARMED = False
_LAKES_GEOMS = ()
_LAKES_BOUNDS = ()
_RIVERS_GEOMS = ()
_RIVERS_BOUNDS = ()
_ROADS_GEOMS = ()
_ROADS_BOUNDS = ()
_STATES_GEOMS = ()
_STATES_BOUNDS = ()


def _materialize_feature_geometries(feature):
    geoms = tuple(feature.geometries())
    bounds = []
    for geom in geoms:
        try:
            bounds.append(geom.bounds)
        except Exception:
            bounds.append((-1e9, -1e9, 1e9, 1e9))
    return geoms, tuple(bounds)


def _subset_geometries_by_extent(geoms, bounds, min_lat, max_lat, min_lon, max_lon):
    subset = []
    for geom, (gx_min, gy_min, gx_max, gy_max) in zip(geoms, bounds):
        if gx_max < min_lon or gx_min > max_lon or gy_max < min_lat or gy_min > max_lat:
            continue
        subset.append(geom)
    return subset


def warm_radar_cartopy_cache():
    """Pre-warm Cartopy Natural Earth assets used by radar rendering."""
    global _RADAR_CARTOPY_WARMED
    global _LAKES_GEOMS, _LAKES_BOUNDS
    global _RIVERS_GEOMS, _RIVERS_BOUNDS
    global _ROADS_GEOMS, _ROADS_BOUNDS
    global _STATES_GEOMS, _STATES_BOUNDS
    if _RADAR_CARTOPY_WARMED:
        return

    t0 = _time.perf_counter()
    try:
        # Touch one geometry from each feature to trigger reader/cache init.
        for feature in (
            _FEATURE_LAND,
            _FEATURE_LAKES,
            _FEATURE_RIVERS,
            _FEATURE_STATES,
            _FEATURE_ROADS,
        ):
            try:
                next(iter(feature.geometries()), None)
            except Exception:
                continue

        _LAKES_GEOMS, _LAKES_BOUNDS = _materialize_feature_geometries(
            _FEATURE_LAKES)
        _RIVERS_GEOMS, _RIVERS_BOUNDS = _materialize_feature_geometries(
            _FEATURE_RIVERS)
        _ROADS_GEOMS, _ROADS_BOUNDS = _materialize_feature_geometries(
            _FEATURE_ROADS)
        _STATES_GEOMS, _STATES_BOUNDS = _materialize_feature_geometries(
            _FEATURE_STATES)
    finally:
        _RADAR_CARTOPY_WARMED = True
        print(
            f"[Perf] radar cartopy warmup took {_time.perf_counter() - t0:.2f}s")


# --- 3. RADAR FUNCTIONS ---
def download_radar_data(
    level,
    station_id,
    product,
    lookback_hours,
    base_dir,
    progress_callback=None,
    latest_only=False,
    start_time=None,
    end_time=None,
):
    """Downloads radar products with progress reporting."""
    if level == "Level 3" and len(station_id) == 4 and station_id.startswith("K"):
        query_id = station_id[1:]
    else:
        query_id = station_id

    level_path = level.lower().replace(" ", "")
    server_url = (
        f"https://thredds.ucar.edu/thredds/radarServer/nexrad/{level_path}/IDD/"
    )

    # Quick health-check: fetch dataset.xml once per server URL window.
    try:
        ds_url = server_url + "dataset.xml"

        def _validate_dataset_xml():
            resp = requests.get(ds_url, timeout=15)
            if resp.status_code != 200 or not resp.content.strip().startswith(b"<?xml"):
                print(
                    f"Thredds dataset.xml check failed: {ds_url} -> {resp.status_code}"
                )
                print(resp.text[:1000])
                raise Exception(
                    f"Thredds server returned non-XML response ({resp.status_code})"
                )
            return True

        cached_call(
            namespace="radar_thredds_health",
            key=ds_url,
            fetch_fn=_validate_dataset_xml,
            ttl_seconds=30,
        )
    except Exception as e:
        print(f"Error contacting Thredds server: {e}")
        raise

    rs = RadarServer(server_url)
    save_dir = os.path.join(
        base_dir, f"radar_{level_path}_downloads", product, station_id
    )
    os.makedirs(save_dir, exist_ok=True)

    if start_time is not None and end_time is not None:
        query_start = (
            start_time.replace(tzinfo=timezone.utc)
            if getattr(start_time, "tzinfo", None) is None
            else start_time.astimezone(timezone.utc)
        )
        query_end = (
            end_time.replace(tzinfo=timezone.utc)
            if getattr(end_time, "tzinfo", None) is None
            else end_time.astimezone(timezone.utc)
        )
    else:
        query_end = datetime.now(timezone.utc)
        query_start = query_end - timedelta(hours=lookback_hours)

    query = rs.query().stations(query_id).time_range(query_start, query_end)
    if level == "Level 3":
        query.variables(product)

    try:
        catalog = rs.get_catalog(query)
        datasets = list(catalog.datasets.values())
    except Exception:
        return save_dir, 0, 0

    if latest_only and datasets:
        datasets = [max(datasets, key=lambda ds: ds.name)]

    downloaded = 0
    total_files = len(datasets)

    for i, ds in enumerate(datasets):
        if progress_callback:
            progress_callback(i + 1, total_files)

        save_path = os.path.join(save_dir, ds.name)
        if not os.path.exists(save_path):
            try:
                data = ds.remote_open()
                with open(save_path, "wb") as f:
                    f.write(data.read())
                downloaded += 1
            except Exception:
                continue
    return save_dir, total_files, downloaded


def calculate_srv(radar, speed_kts, direction_deg):
    """
    Calculates Storm-Relative Velocity from Base Velocity.
    """
    field_name = (
        "velocity" if "velocity" in radar.fields else list(radar.fields.keys())[
            0]
    )
    bv_data = radar.fields[field_name]["data"]

    azimuths = np.deg2rad(radar.azimuth["data"])[:, None]
    motion_dir_rad = np.deg2rad(direction_deg)

    # SRV = BV - (Speed * cos(Beam_Azimuth - Motion_Direction))
    storm_motion_radial = speed_kts * np.cos(azimuths - motion_dir_rad)
    srv_data = bv_data - storm_motion_radial

    srv_field = radar.fields[field_name].copy()
    srv_field["data"] = srv_data
    srv_field["long_name"] = "Storm Relative Velocity"
    radar.add_field("storm_relative_velocity",
                    srv_field, replace_existing=True)

    return "storm_relative_velocity"


def generate_radar_animation(
    level,
    data_dir,
    product_label,
    max_frames,
    logo_file,
    station_id,
    fps,
    sm_speed,
    sm_dir,
    custom_extent=None,
    progress_callback=None,
    show_places=True,
    style_config=None,
):
    import pyart

    warm_radar_cartopy_cache()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    style_config = resolve_radar_style_config(style_config)

    # --- STYLE UNPACKING ---
    # Values come from the resolved config (RADAR_FIXED_STYLE_CONFIG merged
    # with any runtime overrides).  Edit config/style_config.py to change defaults.
    hud_left_size = style_config.get("hud_left_size", 10)
    hud_left_x = style_config.get("hud_left_x", 0.03)
    hud_left_y = style_config.get("hud_left_y", 0.97)
    hud_right_size = style_config.get("hud_right_size", 10)
    hud_right_x = style_config.get("hud_right_x", 0.97)
    hud_right_y = style_config.get("hud_right_y", 0.97)

    logo_user_size = style_config.get("logo_user_size", 0.05)
    logo_user_x = style_config.get("logo_user_x", 0.98)
    logo_user_y = style_config.get("logo_user_y", 0.01)

    show_rings = style_config.get("show_rings", True)
    ring_color = style_config.get("ring_color", "#ffffff")
    ring_width = style_config.get("ring_width", 1.0)
    show_alert_polygons = style_config.get("show_alert_polygons", True)
    alert_line_width = float(style_config.get("radar_alert_width", 4.0))
    alert_alpha = float(style_config.get("radar_alert_alpha", 1.0))
    show_counties = style_config.get("show_counties", False)
    county_width = style_config.get("county_width", 1.0)
    county_color = style_config.get("county_color", "#000000")
    # Footer sizing is pixel-based so map coverage stays identical to the basemap.
    footer_pixels = float(style_config.get("footer_pixels", 120.0))
    footer_bottom_pad_px = float(
        style_config.get("footer_bottom_pad_px", 22.0))
    cbar_height_px = float(style_config.get("cbar_height_px", 28.0))
    cbar_title_size = style_config.get("cbar_title_size", 11)
    cities_file = style_config.get("cities_file", "us-cities.json")
    city_density = float(style_config.get("city_density", 5))
    city_text_size = int(style_config.get("city_text_size", 8))
    city_collision_w = style_config.get("city_collision_w", 0.05)
    city_collision_h = style_config.get("city_collision_h", 0.02)
    density_scale = city_density / 5.0
    expand_top = float(style_config.get("expand_top", 0.0))
    expand_bottom = float(style_config.get("expand_bottom", 0.0))
    expand_left = float(style_config.get("expand_left", 0.0))
    expand_right = float(style_config.get("expand_right", 0.0))

    # City text styling
    city_text_color = style_config.get("city_text_color", "#ffffff")
    city_text_bg_color = style_config.get("city_text_bg_color", "#000000")
    city_text_bg_alpha = float(style_config.get("city_text_bg_alpha", 0.5))

    # Font
    font_family = style_config.get("font_family", "Montserrat")

    # Base map styling
    map_bg_color = style_config.get("map_bg_color", "#152238")
    land_color = style_config.get("land_color", "#5C5C5C")
    ocean_color = style_config.get("ocean_color", "#152238")

    # State borders
    show_states = style_config.get("show_states", True)
    state_color = style_config.get("state_color", "#ffffff")
    state_width = style_config.get("state_width", 1.5)

    # Highway styling
    show_highways = style_config.get("show_highways", True)
    highway_color = style_config.get("highway_color", "#888888")
    highway_width = style_config.get("highway_width", 0.8)
    highway_opacity = float(style_config.get("highway_opacity", 0.6))

    # HUD text & box styling
    hud_left_text_color = style_config.get("hud_left_text_color", "#ffffff")
    hud_left_bg_color = style_config.get("hud_left_bg_color", "#000000")
    hud_left_edge_color = style_config.get("hud_left_edge_color", "#555555")
    hud_left_alpha = float(style_config.get("hud_left_alpha", 0.7))
    hud_right_text_color = style_config.get("hud_right_text_color", "#ffd700")
    hud_right_bg_color = style_config.get("hud_right_bg_color", "#000000")
    hud_right_edge_color = style_config.get("hud_right_edge_color", "#555555")
    hud_right_alpha = float(style_config.get("hud_right_alpha", 0.7))

    # Lakes & River Styling
    show_lakes = style_config.get("show_lakes", True)
    lake_color = style_config.get("lake_color", "#152238")
    lake_outline_color = style_config.get("lake_outline_color", "#333333")
    lake_outline_width = style_config.get("lake_outline_width", 0.5)
    show_rivers = style_config.get("show_rivers", False)
    river_color = style_config.get("river_color", "#152238")
    river_width = style_config.get("river_width", 0.5)
    use_prebuilt_basemap = False
    radar_projection_mode = style_config.get(
        "radar_projection_mode", "local_aeqd")
    platecarree_projection_tokens = {
        "platecarree",
        "plate_carree",
        "pc",
        "latlon",
    }

    hud_left_size_base = int(hud_left_size)
    hud_right_size_base = int(hud_right_size)
    city_text_size_base = int(city_text_size)
    cbar_title_size_base = int(cbar_title_size)
    logo_user_size_base = float(logo_user_size)

    # Z-order defaults.
    zo = {
        "water": 0,
        "land": 1,
        "radar_data": 2,
        "range_rings": 5,
        "alert_polygons": 20,
        "counties": 10,
        "highways": 11,
        "cities": 12,
        "logos": 100,
        "hud": 150,
    }

    script_dir = os.path.dirname(os.path.abspath(__file__))

    radar_sites = load_json_config("radar_sites.json", {})
    raw_site_name = next(
        (name for name, id in radar_sites.items() if id == station_id), station_id
    )

    site_display_name = raw_site_name.replace(" (No Filter)", "")

    # --- LOAD CITIES (ADAPTED FOR YOUR FORMAT) ---
    # Look one folder up in "data/" for "cities.json"
    root_dir = os.path.dirname(script_dir)
    cities_path = os.path.join(root_dir, "data", cities_file)

    cities_data = []
    if os.path.exists(cities_path):
        try:
            with open(cities_path, "r") as f:
                raw_data = json.load(f)

            # ADAPTER: Convert {"City": [lat, lon, align]} -> [{"city": "City", ...}]
            if isinstance(raw_data, dict):
                for k, v in raw_data.items():
                    if isinstance(v, list) and len(v) >= 2:
                        cities_data.append(
                            {
                                "city": k,
                                "latitude": v[0],
                                "longitude": v[1],
                                "align": v[2] if len(v) > 2 else "left",
                                "rank": 9999,
                            }
                        )
            elif isinstance(raw_data, list):
                cities_data = raw_data

        except Exception as e:
            print(f"Error loading cities from {cities_path}: {e}")

    output_dir = data_dir.replace("downloads", "images")
    frame_dir = os.path.join(output_dir, "frames")
    os.makedirs(frame_dir, exist_ok=True)

    # --- TIMELINE FILTERING LOGIC ---
    raw_files = sorted(glob.glob(os.path.join(data_dir, "*")))
    if not raw_files:
        return None, None

    parsed_files = []
    for f in raw_files:
        fname = os.path.basename(f)
        match = re.search(r"(\d{8})_(\d{4,6})", fname)
        if match:
            date_part, time_part = match.groups()
            if len(time_part) == 4:
                time_part += "00"
            dt_str = date_part + time_part
            try:
                dt = datetime.strptime(dt_str, "%Y%m%d%H%M%S").replace(
                    tzinfo=timezone.utc
                )
                parsed_files.append((dt, f))
            except ValueError:
                pass

    radar_files = []
    if parsed_files:
        parsed_files.sort(key=lambda x: x[0])
        newest_time = parsed_files[-1][0]
        cutoff_time = newest_time - timedelta(hours=12)
        valid_files = [f for t, f in parsed_files if t >= cutoff_time]
        radar_files = valid_files[-max_frames:] if max_frames else valid_files
    else:
        radar_files = raw_files[-max_frames:] if max_frames else raw_files

    frames = []
    total_files = len(radar_files)
    basemap_image_cache = {}

    def _get_session_basemap_image(
        min_lat, max_lat, min_lon, max_lon, fig_width, fig_height
    ):
        cache_key = (
            "dynamic",
            round(min_lat, 5),
            round(max_lat, 5),
            round(min_lon, 5),
            round(max_lon, 5),
            round(fig_width, 3),
            round(fig_height, 3),
            show_lakes,
            show_rivers,
            show_highways,
            show_states,
            show_counties,
        )
        cached = basemap_image_cache.get(cache_key)
        if cached is not None:
            return cached

        fig_base = plt.figure(
            figsize=(fig_width, fig_height), dpi=_RADAR_OUTPUT_DPI)
        ax_base = fig_base.add_axes(
            [0.0, 0.0, 1.0, 1.0], projection=ccrs.PlateCarree())
        ax_base.set_extent(
            [min_lon, max_lon, min_lat, max_lat], crs=ccrs.PlateCarree())
        ax_base.set_aspect("auto")
        ax_base.set_facecolor(map_bg_color)
        ax_base.set_xticks([])
        ax_base.set_yticks([])
        ax_base.set_axis_off()

        ax_base.add_feature(
            _FEATURE_LAND, facecolor=land_color, zorder=zo["land"])
        ax_base.add_feature(
            cfeature.OCEAN, facecolor=ocean_color, zorder=zo["water"])

        if show_lakes:
            lake_geoms = _subset_geometries_by_extent(
                _LAKES_GEOMS, _LAKES_BOUNDS, min_lat, max_lat, min_lon, max_lon
            )
            if lake_geoms:
                ax_base.add_geometries(
                    lake_geoms,
                    ccrs.PlateCarree(),
                    facecolor=lake_color,
                    edgecolor=lake_outline_color,
                    linewidth=lake_outline_width,
                    zorder=zo["water"],
                )

        if show_rivers:
            river_geoms = _subset_geometries_by_extent(
                _RIVERS_GEOMS,
                _RIVERS_BOUNDS,
                min_lat,
                max_lat,
                min_lon,
                max_lon,
            )
            if river_geoms:
                ax_base.add_geometries(
                    river_geoms,
                    ccrs.PlateCarree(),
                    facecolor="none",
                    edgecolor=river_color,
                    linewidth=river_width,
                    zorder=zo["water"],
                )

        if show_highways:
            road_geoms = _subset_geometries_by_extent(
                _ROADS_GEOMS, _ROADS_BOUNDS, min_lat, max_lat, min_lon, max_lon
            )
            if road_geoms:
                ax_base.add_geometries(
                    road_geoms,
                    ccrs.PlateCarree(),
                    facecolor="none",
                    edgecolor=highway_color,
                    linewidth=highway_width,
                    alpha=highway_opacity,
                    zorder=zo["highways"],
                )

        if show_states:
            state_geoms = _subset_geometries_by_extent(
                _STATES_GEOMS,
                _STATES_BOUNDS,
                min_lat,
                max_lat,
                min_lon,
                max_lon,
            )
            if state_geoms:
                ax_base.add_geometries(
                    state_geoms,
                    ccrs.PlateCarree(),
                    facecolor="none",
                    edgecolor=state_color,
                    linewidth=state_width,
                    zorder=zo["highways"],
                )

        if show_counties:
            ax_base.add_feature(
                USCOUNTIES.with_scale("5m"),
                linewidth=county_width,
                edgecolor=county_color,
                alpha=0.4,
                zorder=zo["counties"],
            )

        buf_base = io.BytesIO()
        plt.savefig(
            buf_base,
            format="png",
            dpi=150,
            transparent=False,
            bbox_inches=None,
            pad_inches=0,
        )
        plt.close(fig_base)

        basemap_img = imageio.imread(buf_base.getvalue())
        basemap_image_cache[cache_key] = basemap_img
        return basemap_img

    for i, f in enumerate(radar_files):
        if progress_callback:
            progress_callback(i + 1, total_files)

        frame_t0 = _time.perf_counter()
        radar_loaded_t = frame_t0

        try:
            if level == "Level 3":
                # Try direct read first (works for raw NIDS files)
                try:
                    radar = pyart.io.read_nexrad_level3(f)
                except (NotImplementedError, ValueError):
                    # File may have zlib-compressed payload after WMO header
                    # (THREDDS IDD sometimes wraps NIDS data this way)
                    import zlib
                    import tempfile

                    with open(f, "rb") as fh:
                        raw = fh.read()
                    # Find zlib magic in the first 100 bytes
                    zlib_start = -1
                    for magic in [b"\x78\xda", b"\x78\x9c", b"\x78\x01"]:
                        zlib_start = raw.find(magic, 0, 100)
                        if zlib_start != -1:
                            break
                    if zlib_start == -1:
                        raise
                    d = zlib.decompressobj()
                    header_block = d.decompress(raw[zlib_start:])
                    remaining = d.unused_data
                    full_nids = header_block + remaining
                    tmp_path = tempfile.mktemp(suffix=".nids")
                    with open(tmp_path, "wb") as tmp:
                        tmp.write(full_nids)
                    try:
                        radar = pyart.io.read_nexrad_level3(tmp_path)
                    finally:
                        try:
                            os.unlink(tmp_path)
                        except OSError:
                            pass
            else:
                radar = pyart.io.read_nexrad_archive(f)

            radar_loaded_t = _time.perf_counter()

            available_fields = list(radar.fields.keys())
            if not available_fields:
                continue
            field_name = (
                available_fields[0] if level == "Level 3" else product_label.lower(
                )
            )

            if "velocity" in product_label.lower() or product_label in {
                "N0G",
                "N0U",
                "NVW",
                "N0S",
            }:
                field_name = calculate_srv(radar, sm_speed, sm_dir)

            if field_name in radar.fields:
                data = radar.fields[field_name]["data"]
                best_sweep = 0
                max_valid_points = 0
                for sweep_idx in range(radar.nsweeps):
                    sweep_slice = radar.get_slice(sweep_idx)
                    sweep_data = data[sweep_slice]
                    valid_in_sweep = np.sum(
                        ~sweep_data.mask
                        if hasattr(sweep_data, "mask")
                        else ~np.isnan(sweep_data)
                    )
                    if valid_in_sweep > max_valid_points:
                        max_valid_points = valid_in_sweep
                        best_sweep = sweep_idx
                sweep_to_plot = best_sweep
            else:
                sweep_to_plot = 0

            # Time Conversion
            raw_dt = pyart.util.datetimes_from_radar(radar)[0]
            if isinstance(raw_dt, np.datetime64):
                unix_ts = (
                    raw_dt - np.datetime64("1970-01-01T00:00:00")
                ) / np.timedelta64(1, "s")
                dt_utc = datetime.fromtimestamp(
                    float(unix_ts), tz=timezone.utc)
            elif isinstance(raw_dt, datetime):
                dt_utc = (
                    raw_dt.replace(tzinfo=timezone.utc)
                    if raw_dt.tzinfo is None
                    else raw_dt
                )
            elif hasattr(raw_dt, "year") and hasattr(raw_dt, "month"):
                # cftime.DatetimeGregorian or similar calendar-aware types
                dt_utc = datetime(
                    raw_dt.year,
                    raw_dt.month,
                    raw_dt.day,
                    raw_dt.hour,
                    raw_dt.minute,
                    raw_dt.second,
                    tzinfo=timezone.utc,
                )
            else:
                print(
                    f"[WARN] Unexpected radar datetime type: {type(raw_dt)} -- falling back to now()"
                )
                dt_utc = datetime.now(timezone.utc)
            dt_local = dt_utc.astimezone(tz.gettz("America/New_York"))

            # Display Product Name
            display_product = L3_PRODUCTS.get(product_label, product_label)
            if level == "Level 2":
                level2_names = {
                    "reflectivity": "Base Reflectivity",
                    "velocity": "Base Velocity",
                    "cross_correlation_ratio": "Correlation Coefficient",
                }
                display_product = level2_names.get(
                    field_name, field_name.replace("_", " ").title()
                )
            if field_name == "storm_relative_velocity":
                display_product = "Storm-Relative Velocity"

            # Colormap Selection
            norm = None
            category_ticks = None
            category_labels = None
            cc_codes = {"N0M", "NCR"}
            velocity_codes = {"N0G", "N0U", "NVW", "N0S", "NVL"}
            zdr_codes = {"NBU", "N0X"}
            precip_hourly_codes = {"DHR", "DPR", "N1P"}
            precip_accum_codes = {"DPA", "DAA"}
            precip_total_codes = {"DTA", "NRR", "NTP"}
            hca_codes = {"N0H", "HHC", "NAH", "NBH", "N1H", "N2H", "N3H"}

            if "correlation" in field_name.lower() or "CC" in field_name:
                cmap, vmin, vmax = create_grs_cc_cmap(), 0.7, 1.0
            elif (
                "velocity" in field_name.lower()
                or field_name == "storm_relative_velocity"
                or product_label in velocity_codes
            ):
                cmap, vmin, vmax = create_grs_bv_cmap(), -160, 160
            elif (
                "differential_reflectivity" in field_name.lower()
                or "ZDR" in product_label
                or product_label in zdr_codes
            ):
                cmap, vmin, vmax = create_grs_zdr_cmap(), -2.0, 8.0
            elif (
                "vertically_integrated_liquid" in field_name.lower()
                or "DVL" in product_label
            ):
                cmap, vmin, vmax = create_grs_vil_cmap(), 0, 80
            elif "echo_tops" in field_name.lower() or "NET" in product_label:
                cmap, vmin, vmax = create_grs_et_cmap(), 0, 70
            elif "spectrum_width" in field_name.lower() or "N0S" in product_label:
                cmap, vmin, vmax = create_grs_sw_cmap(), 0, 30
            elif product_label in precip_hourly_codes:
                cmap, vmin, vmax = create_grs_precip_cmap(), 0.0, 4.0
            elif product_label in precip_accum_codes:
                cmap, vmin, vmax = create_grs_dpa_cmap(), 0.0, 8.0
            elif product_label in precip_total_codes:
                cmap, vmin, vmax = create_grs_precip_total_cmap(), 0.0, 20.0
            elif product_label in hca_codes:
                cmap, norm, category_ticks, category_labels = create_grs_hca_style()
                vmin, vmax = 0.5, 10.5
            elif product_label in cc_codes:
                cmap, vmin, vmax = create_grs_cc_cmap(), 0.7, 1.0
            else:
                cmap, vmin, vmax = create_grs_br_cmap(), -10, 95

            if custom_extent:
                min_lat, max_lat, min_lon, max_lon = custom_extent
            else:
                r_lat, r_lon = radar.latitude["data"][0], radar.longitude["data"][0]
                min_lat, max_lat, min_lon, max_lon = compute_radar_extent(
                    r_lat, r_lon)

            try:
                radar_center_lat = float(radar.latitude["data"][0])
                radar_center_lon = float(radar.longitude["data"][0])
            except Exception:
                radar_center_lat = (min_lat + max_lat) * 0.5
                radar_center_lon = (min_lon + max_lon) * 0.5

            use_local_projection = (
                radar_projection_mode not in platecarree_projection_tokens
            )
            if use_local_projection:
                map_projection = ccrs.AzimuthalEquidistant(
                    central_longitude=radar_center_lon,
                    central_latitude=radar_center_lat,
                )
            else:
                map_projection = ccrs.PlateCarree()

            lat_span = max_lat - min_lat
            lon_span = max_lon - min_lon
            min_lat -= lat_span * expand_bottom
            max_lat += lat_span * expand_top
            min_lon -= lon_span * expand_left
            max_lon += lon_span * expand_right
            map_fig_width, map_fig_height = _figure_size_for_extent(
                min_lat,
                max_lat,
                min_lon,
                max_lon,
                projection=map_projection,
            )
            footer_inches = max(footer_pixels, 80.0) / float(_RADAR_OUTPUT_DPI)
            fig_width = map_fig_width
            fig_height = map_fig_height + footer_inches
            footer_height = footer_inches / fig_height
            map_axes_rect = [0.0, footer_height, 1.0, 1.0 - footer_height]
            cbar_height_frac = min(
                (max(cbar_height_px, 14.0) / float(_RADAR_OUTPUT_DPI)) / fig_height,
                footer_height * 0.7,
            )
            cbar_bottom_frac = max(
                (max(footer_bottom_pad_px, 4.0) / float(_RADAR_OUTPUT_DPI))
                / fig_height,
                0.004,
            )
            if cbar_bottom_frac + cbar_height_frac > footer_height - 0.003:
                cbar_bottom_frac = max(
                    0.003, footer_height - cbar_height_frac - 0.003)
            cbar_axes_rect = [0.02, cbar_bottom_frac, 0.96, cbar_height_frac]
            scale_factor = max(map_fig_width / 12.8, 0.55)
            hud_left_size = int(hud_left_size_base * scale_factor)
            hud_right_size = int(hud_right_size_base * scale_factor)
            city_text_size = int(city_text_size_base * scale_factor)
            cbar_title_size = int(cbar_title_size_base * scale_factor)
            logo_user_size = logo_user_size_base * scale_factor

            fig = plt.figure(
                figsize=(fig_width, fig_height),
                dpi=_RADAR_OUTPUT_DPI,
            )
            ax = fig.add_axes(map_axes_rect, projection=map_projection)
            ax.set_zorder(1)
            display = pyart.graph.RadarMapDisplay(radar)
            display.plot_ppi_map(
                field_name,
                sweep=sweep_to_plot,
                vmin=vmin,
                vmax=vmax,
                cmap=cmap,
                norm=norm,
                embellish=False,
                add_grid_lines=False,
                resolution="10m",
                title_flag=False,
                colorbar_flag=False,
                projection=map_projection,
                ax=ax,
                min_lat=min_lat,
                max_lat=max_lat,
                min_lon=min_lon,
                max_lon=max_lon,
                zorder=zo["radar_data"],
                edgecolors="face",
                linewidths=0,
            )
            ax.set_position(map_axes_rect)
            ax.set_aspect("auto")
            ax.set_xticks([])
            ax.set_yticks([])
            ax.set_axis_off()
            _suppress_geo_labels(ax, fig)

            # HUD
            hud_left = f"{site_display_name}\n{level}\n{display_product}"
            ax.annotate(
                hud_left,
                xy=(hud_left_x, hud_left_y),
                xycoords="axes fraction",
                fontsize=hud_left_size,
                fontname=font_family,
                fontweight=style_config.get("hud_font_weight", "black"),
                fontstyle=style_config.get("hud_font_style", "italic"),
                color=hud_left_text_color,
                va="top",
                ha="left",
                linespacing=float(style_config.get("hud_line_spacing", 1.15)),
                bbox=dict(
                    boxstyle=style_config.get(
                        "hud_left_box_style", "round,pad=0.5"),
                    fc=hud_left_bg_color,
                    ec=hud_left_edge_color,
                    alpha=hud_left_alpha,
                ),
                zorder=zo["hud"],
            )

            hud_right = (
                f"{dt_local.strftime('%m/%d/%Y')}\n{dt_local.strftime('%I:%M %p %Z')}"
            )
            ax.annotate(
                hud_right,
                xy=(hud_right_x, hud_right_y),
                xycoords="axes fraction",
                fontsize=hud_right_size,
                fontname=font_family,
                fontweight=style_config.get("hud_font_weight", "black"),
                fontstyle=style_config.get("hud_font_style", "italic"),
                color=hud_right_text_color,
                va="top",
                ha="right",
                bbox=dict(
                    boxstyle=style_config.get(
                        "hud_right_box_style", "round,pad=0.4"),
                    fc=hud_right_bg_color,
                    ec=hud_right_edge_color,
                    alpha=hud_right_alpha,
                ),
                zorder=zo["hud"],
            )

            # Colorbar at bottom for static and animated parity
            cbar = None
            footer_bg = matplotlib.patches.Rectangle(
                (0.0, 0.0),
                1.0,
                footer_height,
                transform=fig.transFigure,
                facecolor=style_config.get("footer_bg_color", "#f2f2f2"),
                edgecolor="none",
                zorder=2,
            )
            fig.add_artist(footer_bg)
            cax = fig.add_axes(cbar_axes_rect)
            cax.set_zorder(3)
            cax.set_facecolor(style_config.get("cbar_bg_color", "#f2f2f2"))
            cax.patch.set_alpha(1.0)
            display.plot_colorbar(
                field=field_name,
                orient="horizontal",
                cax=cax,
            )
            if display.cbs:
                cbar = display.cbs[-1]
                cbar.ax.set_zorder(3)
                cbar.set_label("")
                cbar.ax.set_xlabel("")
                cbar.ax.tick_params(axis="x", colors=style_config.get(
                    "cbar_tick_color", "black"), labelsize=int(style_config.get("cbar_tick_labelsize", 10)))
                if category_ticks and category_labels:
                    cbar.set_ticks(category_ticks)
                    cbar.set_ticklabels(category_labels)
                    cbar.ax.tick_params(axis="x", labelsize=8)
                for tick in cbar.ax.get_xticklabels():
                    tick.set_fontname(font_family)
                    tick.set_fontweight("bold")
                cbar.outline.set_edgecolor(
                    style_config.get("cbar_outline_color", "#555555"))
                cbar.outline.set_linewidth(
                    float(style_config.get("cbar_outline_width", 1.0)))
            # Keep map in the reserved top region after colorbar layout adjustments.
            ax.set_position(map_axes_rect)
            _suppress_geo_labels(ax, fig)

            # Base Layers
            ax.set_facecolor(map_bg_color)
            _use_radar_basemap = (
                not use_local_projection
                and use_prebuilt_basemap
                and not custom_extent
                and expand_top == 0
                and expand_bottom == 0
                and expand_left == 0
                and expand_right == 0
                and radar_basemap_exists(station_id)
            )
            if use_local_projection:
                ax.add_feature(
                    _FEATURE_LAND, facecolor=land_color, zorder=zo["land"])
                ax.add_feature(
                    cfeature.OCEAN, facecolor=ocean_color, zorder=zo["water"]
                )

                if show_lakes:
                    lake_geoms = _subset_geometries_by_extent(
                        _LAKES_GEOMS, _LAKES_BOUNDS, min_lat, max_lat, min_lon, max_lon
                    )
                    if lake_geoms:
                        ax.add_geometries(
                            lake_geoms,
                            ccrs.PlateCarree(),
                            facecolor=lake_color,
                            edgecolor=lake_outline_color,
                            linewidth=lake_outline_width,
                            zorder=zo["water"],
                        )

                if show_rivers:
                    river_geoms = _subset_geometries_by_extent(
                        _RIVERS_GEOMS,
                        _RIVERS_BOUNDS,
                        min_lat,
                        max_lat,
                        min_lon,
                        max_lon,
                    )
                    if river_geoms:
                        ax.add_geometries(
                            river_geoms,
                            ccrs.PlateCarree(),
                            facecolor="none",
                            edgecolor=river_color,
                            linewidth=river_width,
                            zorder=zo["water"],
                        )

                if show_highways:
                    road_geoms = _subset_geometries_by_extent(
                        _ROADS_GEOMS, _ROADS_BOUNDS, min_lat, max_lat, min_lon, max_lon
                    )
                    if road_geoms:
                        ax.add_geometries(
                            road_geoms,
                            ccrs.PlateCarree(),
                            facecolor="none",
                            edgecolor=highway_color,
                            linewidth=highway_width,
                            alpha=highway_opacity,
                            zorder=zo["highways"],
                        )

                if show_states:
                    state_geoms = _subset_geometries_by_extent(
                        _STATES_GEOMS,
                        _STATES_BOUNDS,
                        min_lat,
                        max_lat,
                        min_lon,
                        max_lon,
                    )
                    if state_geoms:
                        ax.add_geometries(
                            state_geoms,
                            ccrs.PlateCarree(),
                            facecolor="none",
                            edgecolor=state_color,
                            linewidth=state_width,
                            zorder=zo["highways"],
                        )

                if show_counties:
                    ax.add_feature(
                        USCOUNTIES.with_scale("5m"),
                        linewidth=county_width,
                        edgecolor=county_color,
                        alpha=0.4,
                        zorder=zo["counties"],
                    )
            elif _use_radar_basemap:
                prebuilt_key = ("prebuilt", station_id.upper())
                _bm = basemap_image_cache.get(prebuilt_key)
                if _bm is None:
                    prebuilt_path = get_radar_basemap_path(station_id)
                    if not os.path.exists(prebuilt_path):
                        prebuilt_path = os.path.join(
                            RADAR_BASEMAP_CACHE_DIR, f"{station_id.upper()}.png"
                        )
                    _bm = plt.imread(prebuilt_path)
                    basemap_image_cache[prebuilt_key] = _bm
            else:
                _bm = _get_session_basemap_image(
                    min_lat=min_lat,
                    max_lat=max_lat,
                    min_lon=min_lon,
                    max_lon=max_lon,
                    fig_width=map_fig_width,
                    fig_height=map_fig_height,
                )
            if not use_local_projection:
                ax.imshow(
                    _bm,
                    extent=[min_lon, max_lon, min_lat, max_lat],
                    transform=ccrs.PlateCarree(),
                    zorder=zo["land"],
                    origin="upper",
                    interpolation="bilinear",
                )
            # --- RANGE RINGS ---
            if show_rings:
                for distance in [46300, 92600, 185200]:
                    display.plot_range_ring(
                        distance / 1000,
                        color=ring_color,
                        linestyle=style_config.get("ring_line_style", "--"),
                        linewidth=ring_width,
                        alpha=float(style_config.get("ring_alpha", 0.5)),
                        zorder=zo["range_rings"],
                    )
            alert_legend_entries = []
            if show_alert_polygons:
                try:
                    alert_extent = [min_lat, max_lat, min_lon, max_lon]
                    feature_collection, _data_source = (
                        alerts_utils.get_active_alert_polygons_geojson(
                            state_code=None,
                            category_filter="All Alerts",
                            wfo_code=None,
                            custom_extent=alert_extent,
                        )
                    )
                    alert_geoms_by_color = {}
                    seen_alert_events = set()
                    for feature in feature_collection.get("features", []):
                        props = (
                            feature.get("properties", {})
                            if isinstance(feature, dict)
                            else {}
                        )
                        event_name = str(props.get("event", "") or "").strip()
                        if not _is_radar_alert_event_allowed(event_name):
                            continue
                        event_color = str(props.get("color", "") or "").strip()
                        if not matplotlib.colors.is_color_like(event_color):
                            event_color = "#C0C0C0"
                        if event_name and event_name not in seen_alert_events:
                            seen_alert_events.add(event_name)
                            alert_legend_entries.append(
                                (event_name, event_color))
                        try:
                            geom = shape(feature.get("geometry"))
                        except Exception:
                            continue
                        if geom.is_empty:
                            continue
                        alert_geoms_by_color.setdefault(
                            event_color, []).append(geom)
                    if alert_geoms_by_color:
                        for color, geoms in alert_geoms_by_color.items():
                            if not geoms:
                                continue
                            ax.add_geometries(
                                geoms,
                                ccrs.PlateCarree(),
                                facecolor="none",
                                edgecolor=color,
                                linewidth=alert_line_width,
                                alpha=alert_alpha,
                                zorder=zo["alert_polygons"],
                            )
                except Exception as e:
                    print(f"[WARN] Radar alert overlay failed: {e}")

            if show_alert_polygons and cbar is not None and alert_legend_entries:
                alert_handles = [
                    Line2D(
                        [0],
                        [0],
                        color=color,
                        linewidth=max(alert_line_width, 5.0),
                        label=event_name,
                    )
                    for event_name, color in alert_legend_entries
                ]
                cbar_box = cbar.ax.get_position()
                legend_center_x = cbar_box.x0 + (cbar_box.width / 2.0)
                legend_y = min(0.985, cbar_box.y1 + 0.01)
                alert_legend = fig.legend(
                    handles=alert_handles,
                    loc="upper center",
                    bbox_to_anchor=(legend_center_x, legend_y),
                    bbox_transform=fig.transFigure,
                    prop={
                        "family": font_family,
                        "weight": style_config.get("alert_legend_font_weight", "bold"),
                        "style": style_config.get("alert_legend_font_style", "italic"),
                        "size": 8,
                    },
                    ncol=3,
                    frameon=True,
                )
                alert_legend.get_frame().set_facecolor(
                    style_config.get("legend_panel_bg_color", "white"))
                alert_legend.get_frame().set_edgecolor(
                    style_config.get("legend_panel_edge_color", "none"))
                alert_legend.get_frame().set_linewidth(0.0)
                alert_legend.get_frame().set_alpha(
                    float(style_config.get("legend_panel_bg_alpha", 0.9)))

            # --- CITY LABELS (NORMALIZED) ---
            if show_places:

                def _city_priority(city):
                    try:
                        rank_val = float(city.get("rank"))
                    except (TypeError, ValueError):
                        rank_val = 9999.0
                    return rank_val

                cities_sorted = sorted(cities_data, key=_city_priority)

                buffer = 0.05
                drawn_bboxes = []
                map_width = max_lon - min_lon
                map_height = max_lat - min_lat
                text_w = map_width * city_collision_w * density_scale
                text_h = map_height * city_collision_h * density_scale

                for city_obj in cities_sorted:
                    try:
                        city_name = city_obj.get("city", "Unknown")
                        lat = float(city_obj.get("latitude"))
                        lon = float(city_obj.get("longitude"))
                    except (ValueError, TypeError):
                        continue

                    # Bounds Check
                    if not (
                        min_lat + buffer <= lat <= max_lat - buffer
                        and min_lon + buffer <= lon <= max_lon - buffer
                    ):
                        continue

                    # Collision Check
                    cand_x_min = lon - (text_w / 2.0)
                    cand_x_max = lon + (text_w / 2.0)
                    cand_y_min = lat - (text_h / 2.0)
                    cand_y_max = lat + (text_h / 2.0)

                    if any(
                        cand_x_min < bx_max
                        and cand_x_max > bx_min
                        and cand_y_min < by_max
                        and cand_y_max > by_min
                        for bx_min, bx_max, by_min, by_max in drawn_bboxes
                    ):
                        continue

                    # Draw Text
                    txt = ax.text(
                        lon,
                        lat,
                        city_name.upper(),
                        transform=ccrs.PlateCarree(),
                        fontsize=city_text_size,
                        color=city_text_color,
                        fontname=font_family,
                        fontweight=style_config.get(
                            "city_font_weight", "black"),
                        fontstyle=style_config.get(
                            "city_font_style", "italic"),
                        ha="center",
                        va="center",
                        zorder=zo["cities"],
                        clip_on=True,
                        alpha=float(style_config.get("city_text_alpha", 0.95)),
                        bbox=dict(
                            facecolor=city_text_bg_color,
                            alpha=city_text_bg_alpha,
                            edgecolor="none",
                            boxstyle=style_config.get(
                                "city_box_style", "round,pad=0.2"),
                        ),
                    )
                    txt.set_path_effects(
                        [PathEffects.withStroke(
                            linewidth=float(style_config.get(
                                "city_halo_width", 1.2)),
                            foreground=style_config.get("city_halo_color", "black"))]
                    )

                    drawn_bboxes.append(
                        (cand_x_min, cand_x_max, cand_y_min, cand_y_max)
                    )

            # User Logo
            if os.path.exists(logo_file):
                n_img = mpimg.imread(logo_file)
                ax.add_artist(
                    AnnotationBbox(
                        # Fixed: used variable
                        OffsetImage(n_img, zoom=logo_user_size),
                        (logo_user_x, logo_user_y),  # Fixed: used variable
                        xycoords="axes fraction",
                        frameon=False,
                        box_alignment=(1, 0),
                        zorder=zo["logos"],
                    )
                )

            if total_files == 1:
                # Fast path for latest-only renders: avoid PNG decode/re-encode roundtrip.
                latest_path = os.path.join(output_dir, "latest.png")
                plt.savefig(
                    latest_path,
                    format="png",
                    dpi=_RADAR_OUTPUT_DPI,
                    bbox_inches=None,
                    pad_inches=0,
                )
                plt.close(fig)
                frame_t1 = _time.perf_counter()
                print(
                    f"[Perf] radar frame {i + 1}/{total_files}: "
                    f"read={radar_loaded_t - frame_t0:.2f}s "
                    f"render={frame_t1 - radar_loaded_t:.2f}s "
                    f"total={frame_t1 - frame_t0:.2f}s"
                )
                return latest_path, latest_path

            # Capture frame via BytesIO (skip disk I/O for intermediate frames)
            buf = io.BytesIO()
            plt.savefig(
                buf,
                format="png",
                dpi=_RADAR_OUTPUT_DPI,
                bbox_inches=None,
                pad_inches=0,
            )
            plt.close(fig)
            png_bytes = buf.getvalue()
            frame_data = imageio.imread(png_bytes)
            if frame_data.shape[-1] == 4:
                frame_data = frame_data[:, :, :3]
            frames.append(frame_data)

            # Save PNG for last frame only (used as preview)
            if i == total_files - 1:
                save_path = os.path.join(frame_dir, f"frame_{i:03d}.png")
                with open(save_path, "wb") as fout:
                    fout.write(png_bytes)

            frame_t1 = _time.perf_counter()
            print(
                f"[Perf] radar frame {i + 1}/{total_files}: "
                f"read={radar_loaded_t - frame_t0:.2f}s "
                f"render={frame_t1 - radar_loaded_t:.2f}s "
                f"total={frame_t1 - frame_t0:.2f}s"
            )

        except Exception as e:
            print(f"Error processing {f}: {e}")
            continue

    if frames:
        latest_path = os.path.join(output_dir, "latest.png")
        imageio.imsave(latest_path, frames[-1])

        # Single-frame requests should return immediately as a static PNG.
        if len(frames) == 1:
            return latest_path, latest_path

        datecode = datetime.now().strftime("%Y%m%d_%H%M%S")
        movie_path = os.path.join(output_dir, f"{datecode}_animation.mp4")

        try:
            from video_utils import save_animation

            movie_path = save_animation(movie_path, frames, fps=fps)
        except Exception as e:
            print(f"[WARN] MP4 Generation failed: {e}")
            print("Falling back to imageio...")
            processed = [
                f[: f.shape[0] - (f.shape[0] % 16),
                  : f.shape[1] - (f.shape[1] % 16), :]
                for f in frames
            ]
            movie_path = os.path.join(output_dir, "animation.gif")
            imageio.mimsave(movie_path, processed, fps=fps, loop=0)

        return movie_path, latest_path

    return None, None


def generate_radar_image(
    level,
    data_dir,
    product_label,
    logo_file,
    station_id,
    sm_speed,
    sm_dir,
    custom_extent=None,
    progress_callback=None,
    show_places=True,
    max_frames=1,
    fps=4,
    style_config=None,
):
    """
    Generates a radar image OR animation based on max_frames.
    """
    movie_path, latest_path = generate_radar_animation(
        level,
        data_dir,
        product_label,
        max_frames,
        logo_file,
        station_id,
        fps,
        sm_speed,
        sm_dir,
        custom_extent,
        progress_callback=progress_callback,
        show_places=show_places,
        style_config=style_config,
    )

    if max_frames > 1 and movie_path:
        return movie_path
    return latest_path


def purge_old_files(days_to_keep, base_dir):
    """Deletes radar files and images older than a specified number of days."""
    cutoff_sec = datetime.now().timestamp() - (days_to_keep * 86400)
    purged_count = 0
    errors = 0
    target_patterns = [
        os.path.join(base_dir, "radar_level*_downloads"),
        os.path.join(base_dir, "radar_level*_images"),
    ]
    for pattern in target_patterns:
        for root_dir in glob.glob(pattern):
            for root, dirs, files in os.walk(root_dir, topdown=False):
                for name in files:
                    file_path = os.path.join(root, name)
                    try:
                        if os.path.getmtime(file_path) < cutoff_sec:
                            os.remove(file_path)
                            purged_count += 1
                    except Exception:
                        errors += 1
                if not os.listdir(root) and root != root_dir:
                    try:
                        os.rmdir(root)
                    except Exception:
                        pass
    return purged_count, errors
