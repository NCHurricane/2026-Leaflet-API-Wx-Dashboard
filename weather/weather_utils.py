"""
Unified weather workflow utilities.

Handles basemap generation, layered session management, frame export,
and animation export for the consolidated weather dashboard.

Does NOT import or chain into legacy surface/alerts/mrms/spc endpoint code.
Uses the same pipeline pattern: download -> cache -> parse -> render -> output.
"""

from video_utils import OUTPUT_DPI, FIGSIZE_16x9
from font_utils import register_montserrat_fonts
from config.style_config import (
    resolve_weather_group_style_config,
)
from config.surface_config import (
    TEMPERATURE_COLORMAP,
    TEMPERATURE_MIN_F,
    TEMPERATURE_MAX_F,
)
from config.geo_config import STATE_BOUNDS
from PIL import Image
import cartopy.feature as cfeature
import cartopy.crs as ccrs
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
import os
import json
import uuid
import shutil
import hashlib
from datetime import datetime, timezone, timedelta
from matplotlib.offsetbox import AnnotationBbox, OffsetImage
from config.geo_config import STATES_FULL

import numpy as np
import matplotlib

matplotlib.use("Agg")
register_montserrat_fonts()


# ── Directory roots ──────────────────────────────────────────────────────────
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _parse_datetime(value: str) -> datetime:
    """Parse a datetime string into a timezone-aware UTC datetime."""
    raw = (value or "").strip().replace("Z", "+00:00")
    parsed = None
    for fmt in ["%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d"]:
        try:
            parsed = datetime.strptime(raw, fmt)
            break
        except ValueError:
            continue
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            parsed = datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


WEATHER_ROOT = os.path.join(_PROJECT_ROOT, "weather")
WEATHER_IMAGES = os.path.join(WEATHER_ROOT, "weather_images")
WEATHER_CACHE = os.path.join(WEATHER_ROOT, "weather_cache")
WEATHER_ARCHIVE = os.path.join(WEATHER_ROOT, "weather_archive")
WEATHER_ARCHIVE_LAYERS = os.path.join(WEATHER_ARCHIVE, "archive_layers")
BASEMAP_CACHE = os.path.join(_PROJECT_ROOT, "basemap_cache")
WEATHER_BASEMAP_CACHE = os.path.join(BASEMAP_CACHE, "weather")

for _d in [
    WEATHER_ROOT,
    WEATHER_IMAGES,
    WEATHER_CACHE,
    WEATHER_ARCHIVE,
    WEATHER_ARCHIVE_LAYERS,
    WEATHER_BASEMAP_CACHE,
]:
    os.makedirs(_d, exist_ok=True)

# ── Session config ───────────────────────────────────────────────────────────
SESSION_TTL_HOURS = 4
MAX_SESSIONS = 50

# ── Product group map ────────────────────────────────────────────────────────
PRODUCT_GROUPS = {
    "surface": [
        "Station Plot",
        "Temperature",
        "Temperature Gradient",
        "Temperature Gradient and Values",
        "Feels Like",
        "Feels Like Gradient",
        "Feels Like Gradient and Values",
        "Dewpoint",
        "Relative Humidity",
        "Wind Speed",
        "Wind Gust",
        "Altimeter",
        "MSLP",
        "Visibility",
    ],
    "alerts": [
        "All Alerts",
        "Severe Weather Alerts",
        "Severe Weather Warnings",
        "Tropical Cyclone Alerts",
        "Hydrology Alerts",
        "Flash Flood Alerts",
        "Winter Alerts",
        "Cold Alerts",
        "Fire Alerts",
        "Heat Alerts",
        "Coastal Alerts",
        "Marine Alerts",
        "Non-Precipitation Alerts",
    ],
    "mrms": [
        # Rotation tracks
        "RotationTrack_LL_30min",
        "RotationTrack_LL_60min",
        "RotationTrack_LL_120min",
        "RotationTrack_LL_240min",
        "RotationTrack_LL_360min",
        "RotationTrack_LL_1440min",
        "RotationTrack_ML_30min",
        "RotationTrack_ML_60min",
        "RotationTrack_ML_120min",
        "RotationTrack_ML_240min",
        "RotationTrack_ML_360min",
        "RotationTrack_ML_1440min",
        # MESH / hail
        "MESH_Instant",
        "MESH_Max_30min",
        "MESH_Max_60min",
        "MESH_Max_120min",
        "MESH_Max_240min",
        "MESH_Max_360min",
        "MESH_Max_1440min",
        "SHI",
        "POSH",
        # Azimuthal shear
        "AzShear_Low",
        "AzShear_Mid",
        # Echo top
        "EchoTop_18",
        "EchoTop_30",
        "EchoTop_50",
        "EchoTop_60",
        # VIL
        "VIL_Instant",
        "VIL_Density",
        "VIL_Max_120min",
        "VIL_Max_1440min",
        # QPE – MultiSensor Pass 2
        "QPE_MS2_01H",
        "QPE_MS2_03H",
        "QPE_MS2_06H",
        "QPE_MS2_12H",
        "QPE_MS2_24H",
        "QPE_MS2_48H",
        "QPE_MS2_72H",
        # QPE – MultiSensor Pass 1
        "QPE_MS1_01H",
        "QPE_MS1_03H",
        "QPE_MS1_06H",
        "QPE_MS1_12H",
        "QPE_MS1_24H",
        "QPE_MS1_48H",
        "QPE_MS1_72H",
        # QPE – Radar Only
        "QPE_RO_15M",
        "QPE_RO_01H",
        "QPE_RO_03H",
        "QPE_RO_06H",
        "QPE_RO_12H",
        "QPE_RO_24H",
        "QPE_RO_48H",
        "QPE_RO_72H",
        "QPE_RO_Since12Z",
        # Reflectivity
        "Refl_HSR",
        "Refl_BaseQC",
        "Refl_CompLow",
        "Refl_CompHigh",
        "Refl_CompSuper",
        "Refl_BREF_1HR_MAX",
        "Refl_CREF_1HR_MAX",
        # Lightning
        "Lightning_30min",
        "Lightning_60min",
        # Model / environment
        "Model_FreezingLevel",
        "Model_SurfaceTemp",
        "Model_WetBulbTemp",
        # Standalone
        "PrecipFlag",
        "PrecipRate",
        "RadarQualityIndex",
    ],
    "spc": [
        "cat",
        "torn",
        "wind",
        "hail",
        "prob",
        "watches",
        "mds",
        "reports",
        "fire_windrh",
        "fire_dryt",
    ],
}

MAX_ARCHIVE_SPAN = {
    "surface": 7,
    "alerts": 7,
    "mrms": 3,
    "spc": 14,
}


# ── Layout fractions (header / footer / map area) ───────────────────────────
# All layers share the same figure dimensions.  The map content lives in the
# middle band; the header holds the timestamp, and the footer holds the legend.
LAYOUT_HEADER_FRAC = 0.055  # top 4.5 % of figure
LAYOUT_FOOTER_FRAC = 0.20  # bottom 10 % of figure
LAYOUT_SIDE_FRAC = 0.025  # left/right margin matching header
LAYOUT_MAP_BOTTOM = LAYOUT_FOOTER_FRAC
LAYOUT_MAP_HEIGHT = 1.0 - LAYOUT_HEADER_FRAC - LAYOUT_FOOTER_FRAC
# axes rect for map layers:  [left, bottom, width, height]
LAYOUT_MAP_RECT = [
    LAYOUT_SIDE_FRAC,
    LAYOUT_MAP_BOTTOM,
    1.0 - 2 * LAYOUT_SIDE_FRAC,
    LAYOUT_MAP_HEIGHT,
]


def validate_product_group(product_group: str, product: str):
    """Validate product_group and product are known."""
    group = product_group.lower()
    if group not in PRODUCT_GROUPS:
        return False, f"Unknown product_group: {product_group}"
    products = PRODUCT_GROUPS[group]
    # SPC products are case-sensitive lowered
    if group == "spc":
        if product.lower() not in [p.lower() for p in products]:
            return False, f"Unknown product '{product}' for group '{group}'"
    else:
        if product not in products:
            return False, f"Unknown product '{product}' for group '{group}'"
    return True, ""


# ═════════════════════════════════════════════════════════════════════════════
# PROJECTION
# ═════════════════════════════════════════════════════════════════════════════


def compute_lambert_params(region: str, custom_extent: tuple = None):
    """Compute consistent Lambert projection parameters for a region.

    Returns (projection, extent, fig_width, fig_height) tuple.
    extent is (west, east, south, north) in lon/lat.
    Figure dimensions are calculated from the *projected* extent so the map
    fills the axes with minimal side padding.
    """
    if custom_extent:
        s, n, w, e = custom_extent
    else:
        bounds = STATE_BOUNDS.get(region.upper(), STATE_BOUNDS["CONUS"])
        w, e, s, n = bounds

    center_lon = (w + e) / 2.0
    center_lat = (s + n) / 2.0

    std_parallels = (max(s, center_lat - 10), min(n, center_lat + 10))

    projection = ccrs.LambertConformal(
        central_longitude=center_lon,
        central_latitude=center_lat,
        standard_parallels=std_parallels,
    )

    extent = (w, e, s, n)

    # Compute figure width from the PROJECTED extent so the map fills the
    # axes without large side margins.  Transform the four corners + midpoints
    # into projected coordinates and measure the bounding box.
    src = ccrs.PlateCarree()
    sample_lons = [w, e, w, e, center_lon, center_lon, w, e]
    sample_lats = [s, s, n, n, s, n, center_lat, center_lat]
    proj_coords = projection.transform_points(
        src, np.array(sample_lons), np.array(sample_lats)
    )
    px = proj_coords[:, 0]
    py = proj_coords[:, 1]
    proj_width = px.max() - px.min()
    proj_height = py.max() - py.min()
    proj_aspect = proj_width / max(proj_height, 1.0)

    # The map band occupies (1 - header - footer) of figure height
    # and (1 - 2*side) of figure width.
    map_frac = LAYOUT_MAP_HEIGHT  # vertical fraction for map
    map_w_frac = 1.0 - 2 * LAYOUT_SIDE_FRAC  # horizontal fraction for map
    fig_h = FIGSIZE_16x9[1]
    # map_band_height = fig_h * map_frac
    # map_band_width  = fig_w * map_w_frac  (must equal map_band_height * proj_aspect)
    # => fig_w = (fig_h * map_frac * proj_aspect) / map_w_frac
    fig_w = (fig_h * map_frac * proj_aspect) / map_w_frac

    # Clamp to reasonable bounds
    fig_w = max(8, min(fig_w, 19.2))
    fig_h = max(5, min(fig_h, 10.8))

    return projection, extent, fig_w, fig_h


# ═════════════════════════════════════════════════════════════════════════════
# BASEMAP GENERATION (land + ocean only)
# ═════════════════════════════════════════════════════════════════════════════


def _basemap_cache_key(region: str, custom_extent: tuple, style_config: dict):
    """Generate a stable cache key for basemap files.

    Standard regions with default colors get a human-readable key (e.g. "CONUS").
    Custom extents or non-default colors fall back to an MD5 hash.
    """
    _DEFAULT_LAND = "#5c5c5c"
    _DEFAULT_OCEAN = "#152238"

    land = style_config.get("land_color", _DEFAULT_LAND).lower()
    ocean = style_config.get("ocean_color", _DEFAULT_OCEAN).lower()
    is_default_colors = land == _DEFAULT_LAND and ocean == _DEFAULT_OCEAN

    if custom_extent is None and is_default_colors:
        return region.upper()

    parts = [region.upper()]
    if custom_extent:
        parts.append(
            f"{custom_extent[0]:.2f}_{custom_extent[1]:.2f}_{custom_extent[2]:.2f}_{custom_extent[3]:.2f}"
        )
    parts.append(f"land_{land}_ocean_{ocean}")
    parts.append("layout_v3")

    key_str = "__".join(parts)
    return hashlib.md5(key_str.encode()).hexdigest()[:16]


_MARGIN_BG = "#f5f5f5"  # solid background for header / footer margins
_MARGIN_FG = "#1a1a1a"  # text colour for content in margins


def generate_basemap(
    region: str = "CONUS",
    custom_extent: tuple = None,
    style_config: dict = None,
    force: bool = False,
):
    """Generate a basemap image with header/footer margins.

    The map (land + ocean) occupies the middle band defined by LAYOUT_MAP_RECT.
    Header and footer margins are filled with _MARGIN_BG.
    Returns the absolute path to the cached basemap PNG.
    """
    style_config = style_config or {}
    cache_key = _basemap_cache_key(region, custom_extent, style_config)
    cache_path = os.path.join(WEATHER_BASEMAP_CACHE, f"basemap_{cache_key}.png")

    if not force and os.path.exists(cache_path):
        return cache_path

    projection, extent, fig_w, fig_h = compute_lambert_params(region, custom_extent)
    land_color = style_config.get("land_color", "#5c5c5c")
    ocean_color = style_config.get("ocean_color", "#152238")

    fig = plt.figure(figsize=(fig_w, fig_h), dpi=OUTPUT_DPI)
    fig.patch.set_facecolor(_MARGIN_BG)

    ax = fig.add_axes(LAYOUT_MAP_RECT, projection=projection)
    ax.set_extent(extent, crs=ccrs.PlateCarree())

    # Ocean as background
    ax.set_facecolor(ocean_color)

    # Land fill only - no edgecolor, no coastlines
    ax.add_feature(
        cfeature.NaturalEarthFeature(
            "physical",
            "land",
            "10m",
            facecolor=land_color,
            edgecolor="none",
        ),
        zorder=0,
    )

    # Hide the border but keep the background patch so ocean_color renders
    if hasattr(ax, "outline_patch"):
        ax.outline_patch.set_visible(False)
    for spine in ax.spines.values():
        spine.set_visible(False)

    fig.savefig(
        cache_path,
        dpi=OUTPUT_DPI,
        facecolor=_MARGIN_BG,
        transparent=False,
        pad_inches=0,
    )
    plt.close(fig)
    return cache_path


# ═════════════════════════════════════════════════════════════════════════════
# SESSION MANAGEMENT
# ═════════════════════════════════════════════════════════════════════════════


def _session_dir(session_id: str):
    return os.path.join(WEATHER_ARCHIVE_LAYERS, session_id)


def _manifest_path(session_id: str):
    return os.path.join(_session_dir(session_id), "manifest.json")


def create_session(
    product_group: str, product: str, region: str, custom_extent: tuple = None
):
    """Create a new layered session directory with manifest."""
    session_id = f"{product_group}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    session_path = _session_dir(session_id)

    subdirs = [
        "basemap",
        "product",
        "cities",
        "counties",
        "states",
        "static_overlay",
        "hud_right",
        "legend",
        "exports",
    ]
    for sub in subdirs:
        os.makedirs(os.path.join(session_path, sub), exist_ok=True)

    now_utc = datetime.now(timezone.utc).isoformat()
    expires_utc = (
        datetime.now(timezone.utc) + timedelta(hours=SESSION_TTL_HOURS)
    ).isoformat()

    extent_sig = ""
    if custom_extent:
        extent_sig = f"{custom_extent[0]:.2f},{custom_extent[1]:.2f},{custom_extent[2]:.2f},{custom_extent[3]:.2f}"
    else:
        extent_sig = region.upper()

    manifest = {
        "session_id": session_id,
        "created_utc": now_utc,
        "updated_utc": now_utc,
        "last_access_utc": now_utc,
        "expires_utc": expires_utc,
        "product_group": product_group,
        "product": product,
        "region": region,
        "extent_signature": extent_sig,
        "frame_count": 0,
        "frames": [],
    }

    with open(_manifest_path(session_id), "w") as f:
        json.dump(manifest, f, indent=2)

    return session_id, session_path, manifest


def touch_session(session_id: str):
    """Update last_access_utc and refresh expiry on a session."""
    manifest_file = _manifest_path(session_id)
    if not os.path.exists(manifest_file):
        return
    try:
        with open(manifest_file, "r") as f:
            manifest = json.load(f)
        now_utc = datetime.now(timezone.utc).isoformat()
        manifest["last_access_utc"] = now_utc
        manifest["expires_utc"] = (
            datetime.now(timezone.utc) + timedelta(hours=SESSION_TTL_HOURS)
        ).isoformat()
        with open(manifest_file, "w") as f:
            json.dump(manifest, f, indent=2)
    except Exception:
        pass


def cleanup_sessions():
    """Remove expired sessions and enforce max-session cap."""
    if not os.path.isdir(WEATHER_ARCHIVE_LAYERS):
        return

    sessions = []
    for entry in os.listdir(WEATHER_ARCHIVE_LAYERS):
        entry_path = os.path.join(WEATHER_ARCHIVE_LAYERS, entry)
        if not os.path.isdir(entry_path):
            continue
        manifest_file = os.path.join(entry_path, "manifest.json")
        if not os.path.exists(manifest_file):
            # Orphan directory - remove
            try:
                shutil.rmtree(entry_path)
            except Exception:
                pass
            continue
        try:
            with open(manifest_file, "r") as f:
                manifest = json.load(f)
            sessions.append((entry, manifest))
        except Exception:
            pass

    now = datetime.now(timezone.utc)

    # TTL cleanup
    active = []
    for session_id, manifest in sessions:
        expires_str = manifest.get("expires_utc", "")
        try:
            expires = datetime.fromisoformat(expires_str)
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires < now:
                try:
                    shutil.rmtree(_session_dir(session_id))
                except Exception:
                    pass
                continue
        except Exception:
            pass
        active.append((session_id, manifest))

    # Max-session pruning (remove oldest first)
    if len(active) > MAX_SESSIONS:
        active.sort(
            key=lambda x: x[1].get("last_access_utc", ""),
            reverse=True,
        )
        for session_id, _ in active[MAX_SESSIONS:]:
            try:
                shutil.rmtree(_session_dir(session_id))
            except Exception:
                pass


def validate_layers_path(layers_path: str):
    """Validate that layers_path is safe and resolves under weather archive root.

    Returns (absolute_path, error_message). error_message is None on success.
    """
    if not layers_path:
        return None, "layers_path is required"

    # Reject absolute paths
    if os.path.isabs(layers_path):
        return None, "Absolute paths are not allowed"

    # Normalize and check for traversal
    normalized = os.path.normpath(layers_path)
    if ".." in normalized.split(os.sep):
        return None, "Path traversal is not allowed"

    full_path = os.path.join(WEATHER_ARCHIVE_LAYERS, normalized)
    full_path = os.path.realpath(full_path)

    # Ensure it resolves under the archive layers root
    real_root = os.path.realpath(WEATHER_ARCHIVE_LAYERS)
    if not full_path.startswith(real_root + os.sep) and full_path != real_root:
        return None, "Path resolves outside weather archive root"

    if not os.path.isdir(full_path):
        return None, f"Session directory not found: {layers_path}"

    return full_path, None


# ═════════════════════════════════════════════════════════════════════════════
# TRANSPARENT FIGURE HELPERS
# ═════════════════════════════════════════════════════════════════════════════


def _create_transparent_axes(projection, extent, fig_w, fig_h):
    """Create a transparent figure + cartopy axes matching the basemap geometry.

    The map axes occupy the LAYOUT_MAP_RECT area; header/footer are blank
    transparent so they composite cleanly over the basemap margins.
    """
    fig = plt.figure(figsize=(fig_w, fig_h), dpi=OUTPUT_DPI)
    ax = fig.add_axes(LAYOUT_MAP_RECT, projection=projection)
    ax.set_extent([extent[0], extent[1], extent[2], extent[3]], crs=ccrs.PlateCarree())
    ax.set_facecolor("none")
    fig.patch.set_alpha(0.0)
    ax.set_frame_on(False)
    if hasattr(ax, "outline_patch"):
        ax.outline_patch.set_visible(False)
    return fig, ax


def _save_transparent(fig, path):
    """Save figure as transparent PNG and close it."""
    fig.savefig(path, dpi=OUTPUT_DPI, transparent=True, pad_inches=0)
    plt.close(fig)


def _format_weather_region_label(region: str, custom_extent=None) -> str:
    if custom_extent:
        return "CONUS - Target Area"
    key = str(region or "CONUS").strip().upper()
    return STATES_FULL.get(key, key)


def get_weather_group_label(product_group: str) -> str:
    key = str(product_group or "").strip().lower()
    labels = {
        "surface": "Current Observations",
        "alerts": "Watches/Warnings/Advisories",
        "mrms": "MRMS",
        "spc": "Storm Prediction Center",
    }
    return labels.get(key, str(product_group or "Weather").strip() or "Weather")


def _format_weather_product_line(
    product_group: str,
    product: str,
    day: int = 1,
    report_day: str = "today",
) -> str:
    group = str(product_group or "").strip().lower()
    prod = str(product or "").strip()

    if group == "spc":
        p = prod.lower()
        convective = {"cat", "torn", "wind", "hail", "prob"}
        if p in convective:
            return f"Convective Outlook Day {max(1, int(day or 1))}"
        if p in {"fire_windrh", "fire_dryt"}:
            return f"Fire Weather Outlook Day {max(1, int(day or 1))}"
        if p == "reports":
            suffix = (
                "Yesterday" if str(report_day or "").lower() == "yesterday" else "Today"
            )
            return f"Storm Reports ({suffix})"
        if p == "watches":
            return "SPC Watches"
        if p == "mds":
            return "Mesoscale Discussions"

    return prod or "Unknown Product"


def _format_weather_hud_right_text(timestamp_str: str) -> str:
    raw = str(timestamp_str or "").strip()
    if not raw:
        return "N/A"

    parse_formats = [
        "%Y-%m-%d %I:%M %p %Z",
        "%Y-%m-%d %H:%M %Z",
        "%Y-%m-%d %H:%M UTC",
    ]

    for fmt in parse_formats:
        try:
            parsed = datetime.strptime(raw, fmt)
            date_line = parsed.strftime("%m/%d/%Y")
            time_line = parsed.strftime("%I:%M %p")
            zone = raw.rsplit(" ", 1)[-1] if " " in raw else ""
            return f"{date_line}\n{time_line} {zone}".strip()
        except ValueError:
            continue

    parts = raw.split()
    if len(parts) >= 3:
        date_part = parts[0]
        time_part = " ".join(parts[1:])
        try:
            parsed_date = datetime.strptime(date_part, "%Y-%m-%d")
            return f"{parsed_date.strftime('%m/%d/%Y')}\n{time_part}"
        except ValueError:
            pass

    return raw


def _render_hud_left_logo(
    session_path,
    frame_index,
    fig_w,
    fig_h,
    projection,
    extent,
    product_group,
    product,
    region,
    custom_extent,
    style_config,
    logo_file=None,
    day=1,
    report_day="today",
):
    """Render left HUD text + logo in map-space, matching radar/satellite styling."""
    overlay_path = os.path.join(
        session_path, "static_overlay", f"frame_{frame_index:04d}.png"
    )

    fig, ax = _create_transparent_axes(projection, extent, fig_w, fig_h)

    font_family = style_config.get("font_family", "Montserrat")
    hud_left_size = int(style_config.get("hud_left_size", 10))
    hud_left_x = float(style_config.get("hud_left_x", 0.03))
    hud_left_y = float(style_config.get("hud_left_y", 0.97))
    hud_font_weight = style_config.get("hud_font_weight", "black")
    hud_font_style = style_config.get("hud_font_style", "italic")
    hud_line_spacing = float(style_config.get("hud_line_spacing", 1.15))
    hud_left_text_color = style_config.get("hud_left_text_color", "#ffffff")
    hud_left_bg_color = style_config.get("hud_left_bg_color", "#000000")
    hud_left_edge_color = style_config.get("hud_left_edge_color", "#555555")
    hud_left_alpha = float(style_config.get("hud_left_alpha", 0.7))
    hud_left_box_style = style_config.get("hud_left_box_style", "round,pad=0.5")

    logo_user_size = float(style_config.get("logo_user_size", 0.08))
    logo_user_x = float(style_config.get("logo_user_x", 0.98))
    logo_user_y = float(style_config.get("logo_user_y", 0.01))

    group_line = get_weather_group_label(product_group)
    product_line = _format_weather_product_line(
        product_group, product, day=day, report_day=report_day
    )
    region_line = _format_weather_region_label(region, custom_extent)
    hud_stacked = f"{group_line}\n{product_line}\n{region_line}"

    ax.annotate(
        hud_stacked,
        xy=(hud_left_x, hud_left_y),
        xycoords="axes fraction",
        fontsize=hud_left_size,
        fontname=font_family,
        fontweight=hud_font_weight,
        fontstyle=hud_font_style,
        color=hud_left_text_color,
        va="top",
        linespacing=hud_line_spacing,
        bbox=dict(
            boxstyle=hud_left_box_style,
            fc=hud_left_bg_color,
            ec=hud_left_edge_color,
            alpha=hud_left_alpha,
        ),
        zorder=100,
    )

    if logo_file and os.path.exists(logo_file):
        try:
            n_img = mpimg.imread(logo_file)
            ax.add_artist(
                AnnotationBbox(
                    OffsetImage(n_img, zoom=logo_user_size),
                    (logo_user_x, logo_user_y),
                    xycoords="axes fraction",
                    frameon=False,
                    box_alignment=(1, 0),
                    zorder=100,
                )
            )
        except Exception:
            pass

    _save_transparent(fig, overlay_path)
    return overlay_path


# ═════════════════════════════════════════════════════════════════════════════
# HUD RIGHT RENDERER
# ═════════════════════════════════════════════════════════════════════════════


def _render_hud_right(
    session_path,
    frame_index,
    fig_w,
    fig_h,
    timestamp_str,
    style_config,
    projection,
    extent,
):
    """Render right HUD timestamp in map-space, matching radar/satellite placement."""
    hud_right_path = os.path.join(
        session_path, "hud_right", f"frame_{frame_index:04d}.png"
    )

    fig, ax = _create_transparent_axes(projection, extent, fig_w, fig_h)

    hud_text = _format_weather_hud_right_text(timestamp_str)
    font_family = style_config.get("font_family", "Montserrat")
    hud_right_size = int(style_config.get("hud_right_size", 10))
    hud_right_x = float(style_config.get("hud_right_x", 0.97))
    hud_right_y = float(style_config.get("hud_right_y", 0.97))
    hud_font_weight = style_config.get("hud_font_weight", "black")
    hud_font_style = style_config.get("hud_font_style", "italic")
    hud_right_text_color = style_config.get("hud_right_text_color", "#ffd700")
    hud_right_bg_color = style_config.get("hud_right_bg_color", "#000000")
    hud_right_edge_color = style_config.get("hud_right_edge_color", "#555555")
    hud_right_alpha = float(style_config.get("hud_right_alpha", 0.7))
    hud_right_box_style = style_config.get("hud_right_box_style", "round,pad=0.4")

    ax.annotate(
        hud_text,
        xy=(hud_right_x, hud_right_y),
        xycoords="axes fraction",
        fontsize=hud_right_size,
        fontname=font_family,
        fontweight=hud_font_weight,
        fontstyle=hud_font_style,
        color=hud_right_text_color,
        ha="right",
        va="top",
        bbox=dict(
            boxstyle=hud_right_box_style,
            fc=hud_right_bg_color,
            ec=hud_right_edge_color,
            alpha=hud_right_alpha,
        ),
        zorder=100,
    )

    _save_transparent(fig, hud_right_path)
    return hud_right_path


# ═════════════════════════════════════════════════════════════════════════════
# ALERTS PRODUCT RENDERER
# ═════════════════════════════════════════════════════════════════════════════


def _render_alerts_product(
    session_path,
    frame_index,
    product,
    region,
    projection,
    extent,
    fig_w,
    fig_h,
    style_config,
    custom_extent=None,
):
    """Render alerts product layer with real NWS/IEM data."""
    from alerts.alerts_utils import fetch_active_alerts_with_source, process_alerts
    from cartopy.feature import ShapelyFeature
    from matplotlib.colors import to_rgba

    product_path = os.path.join(session_path, "product", f"frame_{frame_index:04d}.png")
    fig, ax = _create_transparent_axes(projection, extent, fig_w, fig_h)
    active_types = []

    try:
        state_param = None if region.upper() == "CONUS" else region.upper()
        features, _ = fetch_active_alerts_with_source(state=state_param, source="iem")

        w, e, s, n = extent
        bbox = (s, n, w, e)
        alerts_data = process_alerts(
            features, category_filter_name=product, bbox_filter=bbox
        )

        fill_alpha = float(style_config.get("alert_fill_alpha", 0.35))
        line_width = float(style_config.get("alert_line_width", 1.1))
        if region.upper() == "CONUS":
            line_width = max(line_width, 0.3)

        seen_types = set()
        for item in alerts_data:
            shape = ShapelyFeature(
                [item["geometry"]],
                ccrs.PlateCarree(),
                facecolor=to_rgba(item["color"], alpha=fill_alpha),
                edgecolor=item["color"],
                linewidth=line_width,
            )
            ax.add_feature(shape, zorder=30)
            event_name = item.get("event", "Unknown")
            if event_name not in seen_types:
                seen_types.add(event_name)
                active_types.append((event_name, item["color"]))

    except Exception as exc:
        import traceback

        traceback.print_exc()
        ax.text(
            0.5,
            0.5,
            f"Alerts data unavailable:\n{exc}",
            transform=ax.transAxes,
            fontsize=10,
            color="red",
            ha="center",
            va="center",
            bbox=dict(facecolor="black", alpha=0.7),
            zorder=100,
        )

    _save_transparent(fig, product_path)
    legend_data = {"active_types": active_types} if active_types else None
    return {"product_path": product_path, "legend_data": legend_data}


# ═════════════════════════════════════════════════════════════════════════════
# SURFACE PRODUCT RENDERER
# ═════════════════════════════════════════════════════════════════════════════

_SURFACE_PARAM_MAP = {
    "Temperature": (
        "air_temperature",
        TEMPERATURE_COLORMAP,
        TEMPERATURE_MIN_F,
        TEMPERATURE_MAX_F,
    ),
    "Dewpoint": ("dew_point_temperature", "BuGn", -20, 80),
    "Relative Humidity": ("relative_humidity", "YlGnBu", 0, 100),
    "Wind Speed": ("wind_speed", "YlOrRd", 0, 130),
    "Wind Gust": ("wind_gust", "YlOrRd", 0, 130),
    "Altimeter": ("altimeter", "coolwarm", 29.5, 30.8),
    "MSLP": ("mean_sea_level_pressure", "coolwarm", 990, 1040),
    "Visibility": ("visibility", "YlGn_r", 0, 10),
    "Feels Like": (
        "feels_like",
        TEMPERATURE_COLORMAP,
        TEMPERATURE_MIN_F,
        TEMPERATURE_MAX_F,
    ),
    "Temperature Gradient": (
        "air_temperature",
        TEMPERATURE_COLORMAP,
        TEMPERATURE_MIN_F,
        TEMPERATURE_MAX_F,
    ),
    "Temperature Gradient and Values": (
        "air_temperature",
        TEMPERATURE_COLORMAP,
        TEMPERATURE_MIN_F,
        TEMPERATURE_MAX_F,
    ),
    "Feels Like Gradient": (
        "feels_like",
        TEMPERATURE_COLORMAP,
        TEMPERATURE_MIN_F,
        TEMPERATURE_MAX_F,
    ),
    "Feels Like Gradient and Values": (
        "feels_like",
        TEMPERATURE_COLORMAP,
        TEMPERATURE_MIN_F,
        TEMPERATURE_MAX_F,
    ),
}


def _thin_surface_stations(df, projection, extent, density_km=30):
    """Reduce point density for surface observations using MetPy."""
    from metpy.calc import reduce_point_density

    xy = projection.transform_points(
        ccrs.PlateCarree(), df["longitude"].values, df["latitude"].values
    )
    radius = density_km * 1000
    mask = reduce_point_density(xy[:, 0:2], radius)
    return df[mask].copy()


def _render_surface_product(
    session_path,
    frame_index,
    product,
    region,
    projection,
    extent,
    fig_w,
    fig_h,
    style_config,
    custom_extent=None,
):
    """Render surface observation product layer with real IEM data."""
    from surface.surface_utils import fetch_metar_data, get_weather_symbol_index
    from metpy.plots import StationPlot, sky_cover, current_weather
    from matplotlib.patheffects import withStroke
    import pandas as pd

    product_path = os.path.join(session_path, "product", f"frame_{frame_index:04d}.png")
    fig, ax = _create_transparent_axes(projection, extent, fig_w, fig_h)

    try:
        state_code = region.upper() if region.upper() != "CONUS" else "CONUS"
        df = fetch_metar_data(state_code)

        if df is not None and not df.empty:
            w, e, s, n = extent
            mask = (
                (df["latitude"] >= s)
                & (df["latitude"] <= n)
                & (df["longitude"] >= w)
                & (df["longitude"] <= e)
            )
            df = df[mask].copy()

        if df is not None and not df.empty:
            param_info = _SURFACE_PARAM_MAP.get(product)

            if product == "Station Plot":
                # Full MetPy StationPlot glyph model
                density_km = int(style_config.get("station_density_km", 30))
                df_plot = _thin_surface_stations(df, projection, extent, density_km)

                if df_plot.empty:
                    _save_transparent(fig, product_path)
                    return product_path

                # Derive weather symbol index
                df_plot["wx_idx"] = 0
                if "wxcodes" in df_plot.columns:
                    df_plot["wx_idx"] = df_plot["wxcodes"].apply(
                        get_weather_symbol_index
                    )

                # Derive sky cover from relative humidity (0-8 scale)
                sky_vals = np.zeros(len(df_plot))
                if "relative_humidity" in df_plot.columns:
                    sky_vals = (
                        (df_plot["relative_humidity"].fillna(0) / 12.5)
                        .clip(0, 8)
                        .round()
                        .astype(int)
                        .values
                    )

                station_font_size = int(style_config.get("station_font_size", 8))
                station_spacing = float(style_config.get("station_spacing_factor", 1.2))

                sp = StationPlot(
                    ax,
                    df_plot["longitude"].values,
                    df_plot["latitude"].values,
                    clip_on=True,
                    transform=ccrs.PlateCarree(),
                    fontsize=station_font_size,
                    spacing=int(station_font_size * station_spacing),
                    zorder=30,
                )

                halo_w = int(style_config.get("station_text_halo_width", 2))
                halo_c = style_config.get("station_text_halo_color", "white")
                halo = [withStroke(linewidth=halo_w, foreground=halo_c)]
                stn_weight = style_config.get("station_text_weight", "bold")

                # NW: Temperature
                sp.plot_parameter(
                    "NW",
                    df_plot["air_temperature"].values,
                    color=style_config.get("station_temp_color", "#D32F2F"),
                    weight=stn_weight,
                ).set_path_effects(halo)

                # SW: Dewpoint
                sp.plot_parameter(
                    "SW",
                    df_plot["dew_point_temperature"].values,
                    color=style_config.get("station_dewpoint_color", "#00796B"),
                    weight=stn_weight,
                ).set_path_effects(halo)

                # NE: Pressure (MSLP formatted as 3-digit altimeter)
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

                # E: Visibility
                if "visibility" in df_plot.columns:
                    sp.plot_parameter(
                        "E",
                        df_plot["visibility"].values,
                        color=style_config.get("station_visibility_color", "purple"),
                        formatter=lambda v: f"{v:.0f}" if not pd.isna(v) else "",
                    ).set_path_effects(halo)

                # C: Sky cover symbol
                sp.plot_symbol("C", sky_vals, sky_cover)

                # W: Present weather symbol
                sp.plot_symbol(
                    "W",
                    df_plot["wx_idx"].values,
                    current_weather,
                    color=style_config.get("station_weather_color", "#1976D2"),
                )

                # Wind barbs
                sp.plot_barb(
                    df_plot["u"].fillna(0).values,
                    df_plot["v"].fillna(0).values,
                    color=style_config.get("station_wind_color", "#1976D2"),
                    length=int(style_config.get("wind_barb_length", 5)),
                )

            elif "Gradient" in product and param_info:
                col, cmap_name, vmin, vmax = param_info
                valid = df.dropna(subset=[col, "latitude", "longitude"])
                if len(valid) >= 4:
                    from scipy.interpolate import griddata as _griddata
                    from scipy.ndimage import gaussian_filter as _gaussian

                    lons = valid["longitude"].values
                    lats = valid["latitude"].values
                    vals = valid[col].values

                    grid_x = np.linspace(w, e, 200)
                    grid_y = np.linspace(s, n, 200)
                    gx, gy = np.meshgrid(grid_x, grid_y)
                    grid_z = _griddata((lons, lats), vals, (gx, gy), method="linear")
                    grid_z = _gaussian(
                        np.nan_to_num(grid_z, nan=np.nanmean(vals)), sigma=2
                    )

                    ax.contourf(
                        gx,
                        gy,
                        grid_z,
                        levels=15,
                        cmap=cmap_name,
                        vmin=vmin,
                        vmax=vmax,
                        alpha=0.6,
                        transform=ccrs.PlateCarree(),
                        zorder=25,
                    )

                    if "Values" in product:
                        # Thin stations for value labels
                        density_km = int(style_config.get("station_density_km", 30))
                        thinned = _thin_surface_stations(
                            valid, projection, extent, density_km
                        )
                        if not thinned.empty:
                            for _, row in thinned.iterrows():
                                val = row[col]
                                if pd.notna(val):
                                    ax.text(
                                        row["longitude"],
                                        row["latitude"],
                                        f"{val:.0f}",
                                        transform=ccrs.PlateCarree(),
                                        fontsize=7,
                                        color="white",
                                        fontweight="bold",
                                        ha="center",
                                        va="center",
                                        path_effects=[
                                            withStroke(linewidth=2, foreground="black")
                                        ],
                                        zorder=31,
                                    )

            elif param_info:
                # Dot plot with number value labels
                col, cmap_name, vmin, vmax = param_info
                valid = df.dropna(subset=[col, "latitude", "longitude"])
                if not valid.empty:
                    density_km = int(style_config.get("station_density_km", 30))
                    thinned = _thin_surface_stations(
                        valid, projection, extent, density_km
                    )
                    if not thinned.empty:
                        ax.scatter(
                            thinned["longitude"].values,
                            thinned["latitude"].values,
                            c=thinned[col].values,
                            cmap=cmap_name,
                            vmin=vmin,
                            vmax=vmax,
                            s=18,
                            alpha=0.85,
                            edgecolors="black",
                            linewidths=0.3,
                            transform=ccrs.PlateCarree(),
                            zorder=30,
                        )
                        # Number value labels
                        fmt = ".1f" if col in ("altimeter", "visibility") else ".0f"
                        for _, row in thinned.iterrows():
                            val = row[col]
                            if pd.notna(val):
                                ax.text(
                                    row["longitude"],
                                    row["latitude"],
                                    f"{val:{fmt}}",
                                    transform=ccrs.PlateCarree(),
                                    fontsize=6,
                                    color="white",
                                    fontweight="bold",
                                    ha="center",
                                    va="bottom",
                                    path_effects=[
                                        withStroke(linewidth=2, foreground="black")
                                    ],
                                    zorder=31,
                                )
        else:
            ax.text(
                0.5,
                0.5,
                "No surface observations available",
                transform=ax.transAxes,
                fontsize=10,
                color="yellow",
                ha="center",
                va="center",
                bbox=dict(facecolor="black", alpha=0.6),
                zorder=100,
            )

    except Exception as exc:
        import traceback

        traceback.print_exc()
        ax.text(
            0.5,
            0.5,
            f"Surface data unavailable:\n{exc}",
            transform=ax.transAxes,
            fontsize=10,
            color="red",
            ha="center",
            va="center",
            bbox=dict(facecolor="black", alpha=0.7),
            zorder=100,
        )

    _save_transparent(fig, product_path)
    return {"product_path": product_path, "legend_data": None}


# ═════════════════════════════════════════════════════════════════════════════
# MRMS PRODUCT RENDERER
# ═════════════════════════════════════════════════════════════════════════════


def _render_mrms_product(
    session_path,
    frame_index,
    product,
    region,
    projection,
    extent,
    fig_w,
    fig_h,
    style_config,
    custom_extent=None,
):
    """Render MRMS product layer with real NODD S3 data."""
    from mrms.mrms_nodd_utils import get_latest_mrms_file
    from mrms.mrms_utils import read_mrms_grib2
    from config.mrms_config import MRMS_PRODUCTS, MRMS_COLORMAPS

    product_path = os.path.join(session_path, "product", f"frame_{frame_index:04d}.png")
    fig, ax = _create_transparent_axes(projection, extent, fig_w, fig_h)
    mrms_legend_data = None

    try:
        product_info = MRMS_PRODUCTS.get(product)
        if not product_info:
            raise ValueError(f"Unknown MRMS product: {product}")

        # Download latest file
        download_dir = os.path.join(WEATHER_CACHE, "mrms_downloads")
        os.makedirs(download_dir, exist_ok=True)

        # QPE source-aware lookback: Pass2 ~2hr delay, Pass1 ~1hr delay
        # Model products update hourly with variable lag
        if product.startswith("QPE_MS2_"):
            lookback = 180
        elif product.startswith("QPE_MS1_"):
            lookback = 120
        elif product.startswith("Model_"):
            lookback = 180
        else:
            lookback = 60

        result = get_latest_mrms_file(
            product, lookback_minutes=lookback, local_dir=download_dir
        )

        if result is None:
            raise ValueError(f"No recent MRMS {product} data available")

        file_path, file_dt = result

        # Read GRIB2 data
        w, e, s, n = extent
        crop_extent = [w, e, s, n]
        data, metadata = read_mrms_grib2(file_path, product, crop_extent=crop_extent)

        # Get colormap
        cmap_key = product_info.get("colormap", "qpe")
        cmap_entry = MRMS_COLORMAPS.get(cmap_key)
        is_categorical = product_info.get("categorical", False)
        cat_norm = None

        if isinstance(cmap_entry, tuple):
            cmap, cat_norm, _ = cmap_entry
            is_categorical = True
        else:
            cmap = cmap_entry

        vmin = product_info.get("vmin", 0)
        vmax = product_info.get("vmax", 100)

        # Mask missing/no-data
        missing_val = product_info.get("missing_value")
        no_cov_val = product_info.get("no_coverage")
        data_mask = data <= 0
        if missing_val is not None and missing_val != 0:
            data_mask = data_mask | (data == missing_val)
        if no_cov_val is not None and no_cov_val != 0:
            data_mask = data_mask | (data == no_cov_val)
        data_masked = np.ma.masked_where(data_mask, data)

        # Compute image extent from coordinate arrays
        lon = metadata["longitude"]
        lat = metadata["latitude"]
        img_extent = [lon.min(), lon.max(), lat.min(), lat.max()]
        lat_descending = lat[0] > lat[-1] if len(lat) > 1 else False

        # Plot data
        if is_categorical and cat_norm is not None:
            ax.imshow(
                data_masked,
                cmap=cmap,
                norm=cat_norm,
                extent=img_extent,
                origin="upper" if lat_descending else "lower",
                transform=ccrs.PlateCarree(),
                interpolation="nearest",
                alpha=0.85,
                zorder=25,
            )
        else:
            ax.imshow(
                data_masked,
                cmap=cmap,
                extent=img_extent,
                origin="upper" if lat_descending else "lower",
                transform=ccrs.PlateCarree(),
                interpolation="nearest",
                alpha=0.85,
                vmin=vmin,
                vmax=vmax,
                zorder=25,
            )

        # Re-enforce extent after imshow
        ax.set_extent([w, e, s, n], crs=ccrs.PlateCarree())

        # Capture legend data for colorbar rendering
        mrms_legend_data = {
            "cmap": cmap,
            "vmin": vmin,
            "vmax": vmax,
            "is_categorical": is_categorical,
            "cat_norm": cat_norm,
            "product_info": product_info,
            "data_masked": data_masked,
        }

    except Exception as exc:
        import traceback

        traceback.print_exc()
        ax.text(
            0.5,
            0.5,
            f"MRMS data unavailable:\n{exc}",
            transform=ax.transAxes,
            fontsize=10,
            color="red",
            ha="center",
            va="center",
            bbox=dict(facecolor="black", alpha=0.7),
            zorder=100,
        )

    _save_transparent(fig, product_path)
    return {"product_path": product_path, "legend_data": mrms_legend_data}


# ═════════════════════════════════════════════════════════════════════════════
# SPC PRODUCT RENDERER
# ═════════════════════════════════════════════════════════════════════════════


def _render_spc_product(
    session_path,
    frame_index,
    product,
    region,
    projection,
    extent,
    fig_w,
    fig_h,
    style_config,
    custom_extent=None,
    day=1,
    report_day="today",
    item_id=None,
):
    """Render SPC outlook product layer with real SPC data."""
    from spc.spc_utils import (
        fetch_outlook_geojson,
        fetch_active_watch_items,
        fetch_active_md_items,
        fetch_reports_rows,
        fetch_fire_wx_geojson,
    )

    product_path = os.path.join(session_path, "product", f"frame_{frame_index:04d}.png")
    fig, ax = _create_transparent_axes(projection, extent, fig_w, fig_h)

    try:
        hazard = product.lower()

        if hazard == "watches":
            # Fetch active watches
            watch_items, _ = fetch_active_watch_items()
            items = watch_items or []
            # Filter to specific item if requested
            if item_id and item_id != "all":
                items = [w for w in items if str(w.get("id")) == str(item_id)]
            if not items:
                ax.text(
                    0.5,
                    0.5,
                    "No active watches",
                    transform=ax.transAxes,
                    fontsize=int(style_config.get("no_items_font_size", 16)),
                    color=style_config.get("no_items_color", "white"),
                    ha="center",
                    va="center",
                    bbox=dict(
                        facecolor="black",
                        alpha=float(style_config.get("no_items_bg_alpha", 0.6)),
                        pad=10,
                    ),
                    zorder=100,
                )
            for watch in items:
                polygon_coords = watch.get("polygon")
                if not polygon_coords or len(polygon_coords) < 3:
                    continue
                from shapely.geometry import Polygon as ShapelyPolygon

                try:
                    poly = ShapelyPolygon(polygon_coords)
                except Exception:
                    continue
                label = (watch.get("title", "") or "").lower()
                color = (
                    style_config.get("watch_tornado_color", "#FFFF00")
                    if "tornado" in label
                    else style_config.get("watch_severe_color", "#FFA500")
                )
                fill_alpha = float(style_config.get("watch_fill_alpha", 0.25))
                from cartopy.feature import ShapelyFeature

                feat = ShapelyFeature(
                    [poly],
                    ccrs.PlateCarree(),
                    facecolor=(*matplotlib.colors.to_rgb(color), fill_alpha),
                    edgecolor=color,
                    linewidth=float(style_config.get("watch_line_width", 1.5)),
                )
                ax.add_feature(feat, zorder=30)

        elif hazard == "mds":
            # Fetch active Mesoscale Discussions
            md_items, _ = fetch_active_md_items()
            items = md_items or []
            # Filter to specific item if requested
            if item_id and item_id != "all":
                items = [m for m in items if str(m.get("id")) == str(item_id)]
            if not items:
                ax.text(
                    0.5,
                    0.5,
                    "No active mesoscale discussions",
                    transform=ax.transAxes,
                    fontsize=int(style_config.get("no_items_font_size", 16)),
                    color=style_config.get("no_items_color", "white"),
                    ha="center",
                    va="center",
                    bbox=dict(
                        facecolor="black",
                        alpha=float(style_config.get("no_items_bg_alpha", 0.6)),
                        pad=10,
                    ),
                    zorder=100,
                )
            for md in items:
                polygon_coords = md.get("polygon")
                if not polygon_coords or len(polygon_coords) < 3:
                    continue
                from shapely.geometry import Polygon as ShapelyPolygon

                try:
                    poly = ShapelyPolygon(polygon_coords)
                except Exception:
                    continue
                md_fill_alpha = float(style_config.get("md_fill_alpha", 0.2))
                md_r = float(style_config.get("md_fill_color_r", 0.4))
                md_g = float(style_config.get("md_fill_color_g", 0.8))
                md_b = float(style_config.get("md_fill_color_b", 1.0))
                from cartopy.feature import ShapelyFeature

                feat = ShapelyFeature(
                    [poly],
                    ccrs.PlateCarree(),
                    facecolor=(md_r, md_g, md_b, md_fill_alpha),
                    edgecolor=style_config.get("md_edge_color", "#66CCFF"),
                    linewidth=float(style_config.get("md_line_width", 1.5)),
                )
                ax.add_feature(feat, zorder=30)

        elif hazard == "reports":
            # Storm reports as scatter points
            now = datetime.now(timezone.utc)
            if report_day == "yesterday":
                target_date = now - timedelta(days=1)
            else:
                target_date = now
            rows, _ = fetch_reports_rows(
                report_date_utc=target_date, report_mode="filtered", report_type="all"
            )
            if rows:
                report_colors = {
                    "tornado": style_config.get("report_tornado_color", "#FF0000"),
                    "hail": style_config.get("report_hail_color", "#00FF00"),
                    "wind": style_config.get("report_wind_color", "#0088FF"),
                }
                default_color = style_config.get("report_default_color", "#FFFFFF")
                marker_size = int(style_config.get("report_marker_size", 4))
                report_alpha = float(style_config.get("report_alpha", 0.8))
                for row in rows:
                    lat = row.get("lat")
                    lon = row.get("lon")
                    rtype = (row.get("event", "") or "").lower()
                    if lat is not None and lon is not None:
                        color = report_colors.get(rtype, default_color)
                        ax.plot(
                            lon,
                            lat,
                            marker="o",
                            markersize=marker_size,
                            color=color,
                            alpha=report_alpha,
                            transform=ccrs.PlateCarree(),
                            zorder=35,
                        )

        elif hazard.startswith("fire_"):
            # Fire weather outlooks: fire_windrh, fire_dryt (Day 1-8)
            fw_hazard = hazard.replace("fire_", "", 1)
            geojson, _ = fetch_fire_wx_geojson(day=day, hazard=fw_hazard)
            features = (geojson or {}).get("features", [])

            for feature in features:
                props = feature.get("properties", {})
                # Skip background / "Probability Too Low" features (dn=0)
                dn = props.get("dn", props.get("DN"))
                try:
                    if int(dn) == 0:
                        continue
                except (TypeError, ValueError):
                    pass

                geometry = feature.get("geometry") or {}
                gtype = geometry.get("type")
                coords = geometry.get("coordinates", [])

                fill_color = (props.get("fill") or "").strip() or "#ffd700"
                edge_color = (props.get("stroke") or "").strip() or "#ffd700"
                poly_alpha = float(style_config.get("outlook_fill_alpha", 0.45))
                line_width = float(style_config.get("outlook_line_width", 1.0))

                def _plot_fire_rings(ax, coord_rings, fc, ec, a, lw):
                    for ring in coord_rings[:1]:
                        if not ring:
                            continue
                        xs = [p[0] for p in ring]
                        ys = [p[1] for p in ring]
                        ax.fill(
                            xs,
                            ys,
                            facecolor=fc,
                            edgecolor=ec,
                            linewidth=lw,
                            alpha=a,
                            transform=ccrs.PlateCarree(),
                            zorder=30,
                        )

                if gtype == "Polygon":
                    _plot_fire_rings(
                        ax, coords, fill_color, edge_color, poly_alpha, line_width
                    )
                elif gtype == "MultiPolygon":
                    for polygon_coords in coords:
                        _plot_fire_rings(
                            ax,
                            polygon_coords,
                            fill_color,
                            edge_color,
                            poly_alpha,
                            line_width,
                        )

        else:
            # Categorical/probabilistic outlook: cat, torn, wind, hail
            geojson, _ = fetch_outlook_geojson(day=day, hazard=hazard)
            features = (geojson or {}).get("features", [])

            for feature in features:
                geometry = feature.get("geometry") or {}
                gtype = geometry.get("type")
                coords = geometry.get("coordinates", [])
                props = feature.get("properties", {})

                fill_color = props.get("fill") or "#ffd700"
                edge_color = props.get("stroke") or "#ffd700"
                poly_alpha = float(style_config.get("outlook_fill_alpha", 0.45))
                line_width = float(style_config.get("outlook_line_width", 1.0))

                def _plot_rings(ax, coord_rings, fc, ec, a, lw):
                    for ring in coord_rings[:1]:
                        if not ring:
                            continue
                        xs = [p[0] for p in ring]
                        ys = [p[1] for p in ring]
                        ax.fill(
                            xs,
                            ys,
                            facecolor=fc,
                            edgecolor=ec,
                            linewidth=lw,
                            alpha=a,
                            transform=ccrs.PlateCarree(),
                            zorder=30,
                        )

                if gtype == "Polygon":
                    _plot_rings(
                        ax, coords, fill_color, edge_color, poly_alpha, line_width
                    )
                elif gtype == "MultiPolygon":
                    for polygon_coords in coords:
                        _plot_rings(
                            ax,
                            polygon_coords,
                            fill_color,
                            edge_color,
                            poly_alpha,
                            line_width,
                        )

    except Exception as exc:
        import traceback

        traceback.print_exc()
        ax.text(
            0.5,
            0.5,
            f"SPC data unavailable:\n{exc}",
            transform=ax.transAxes,
            fontsize=10,
            color="red",
            ha="center",
            va="center",
            bbox=dict(facecolor="black", alpha=0.7),
            zorder=100,
        )

    _save_transparent(fig, product_path)
    return {"product_path": product_path, "legend_data": None}


# ═════════════════════════════════════════════════════════════════════════════
# LEGEND RENDERERS
# ═════════════════════════════════════════════════════════════════════════════


def _render_legend(
    session_path,
    frame_index,
    product_group,
    product,
    style_config,
    fig_w=None,
    fig_h=None,
    legend_data=None,
):
    """Render a legend PNG for the given product group.

    Returns the legend image path, or None if no legend is appropriate.
    ``legend_data`` carries per-frame context from the product renderer
    (e.g. MRMS max values, colormap info).
    """
    fw = fig_w or FIGSIZE_16x9[0]
    fh = fig_h or FIGSIZE_16x9[1]
    group = product_group.lower()
    if group == "surface":
        return _render_surface_legend(
            session_path, frame_index, product, style_config, fw, fh, legend_data
        )
    elif group == "alerts":
        return _render_alerts_legend(
            session_path, frame_index, product, style_config, fw, fh, legend_data
        )
    elif group == "mrms":
        return _render_mrms_legend(
            session_path, frame_index, product, style_config, fw, fh, legend_data
        )
    elif group == "spc":
        return _render_spc_legend(
            session_path, frame_index, product, style_config, fw, fh, legend_data
        )
    return None


def _legend_fig(fig_w, fig_h):
    """Create a full-size transparent figure for a legend overlay.

    The legend content should be placed in the footer margin area
    (0 to LAYOUT_FOOTER_FRAC in figure coordinates).
    """
    fig = plt.figure(figsize=(fig_w, fig_h), dpi=OUTPUT_DPI)
    fig.patch.set_alpha(0.0)
    return fig


def _save_legend(fig, path):
    """Save a legend figure as a transparent PNG and close it."""
    fig.savefig(path, dpi=OUTPUT_DPI, transparent=True, pad_inches=0)
    plt.close(fig)


# ── Surface legend ──────────────────────────────────────────────────────────


def _render_surface_legend(
    session_path, frame_index, product, style_config, fig_w, fig_h, legend_data=None
):
    """Render legend for surface products in the footer margin.

    Station Plot -> static station-model key.
    Gradient / Scatter -> horizontal colorbar.
    """
    legend_path = os.path.join(session_path, "legend", f"frame_{frame_index:04d}.png")

    ftr = LAYOUT_FOOTER_FRAC
    param_info = _SURFACE_PARAM_MAP.get(product)

    if product == "Station Plot":
        # Use the static station-model reference image
        static_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "img", "station_plot_legend.png"
        )
        if not os.path.exists(static_path):
            return None

        out_w = int(fig_w * OUTPUT_DPI)
        out_h = int(fig_h * OUTPUT_DPI)
        footer_h = int(out_h * ftr)

        canvas = Image.new("RGBA", (out_w, out_h), (0, 0, 0, 0))
        legend_img = Image.open(static_path).convert("RGBA")

        # Scale legend to fit inside the footer band (with small padding)
        pad = int(footer_h * 0.0000001)
        avail_h = footer_h - 2 * pad
        avail_w = out_w - 2 * pad
        scale = min(avail_w / legend_img.width, avail_h / legend_img.height)
        new_w = int(legend_img.width * scale)
        new_h = int(legend_img.height * scale)
        legend_img = legend_img.resize((new_w, new_h), Image.LANCZOS)

        # Centre in the footer band (bottom of image)
        x_off = (out_w - new_w) // 2
        y_off = out_h - footer_h + (footer_h - new_h) // 2
        canvas.paste(legend_img, (x_off, y_off), legend_img)
        canvas.save(legend_path, "PNG")
        return legend_path

    elif param_info:
        col, cmap_name, vmin, vmax = param_info
        fig = _legend_fig(fig_w, fig_h)

        cmap = plt.get_cmap(cmap_name)
        norm = plt.Normalize(vmin=vmin, vmax=vmax)
        sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
        sm.set_array([])

        # Colorbar centred inside footer margin
        cbar_ax = fig.add_axes([0.05, ftr * 0.55, 0.90, ftr * 0.30])
        cb = fig.colorbar(sm, cax=cbar_ax, orientation="horizontal")
        cb.ax.tick_params(labelsize=8, colors=_MARGIN_FG)
        cb.outline.set_edgecolor("#cccccc")

        unit = (
            "°F"
            if col in ("air_temperature", "feels_like", "dew_point_temperature")
            else ""
        )
        if col == "relative_humidity":
            unit = "%"
        elif col == "visibility":
            unit = "mi"
        elif col in ("altimeter", "mean_sea_level_pressure"):
            unit = "mb" if col == "mean_sea_level_pressure" else "inHg"
        elif col in ("wind_speed", "wind_gust"):
            unit = "kt"
        title = product if not unit else f"{product} ({unit})"
        cb.set_label(title, fontsize=9, color=_MARGIN_FG, fontweight="bold")

        _save_legend(fig, legend_path)
        return legend_path

    return None


# ── Alerts legend ───────────────────────────────────────────────────────────


def _render_alerts_legend(
    session_path, frame_index, product, style_config, fig_w, fig_h, legend_data=None
):
    """Render legend for alerts showing active hazard type colors."""
    legend_path = os.path.join(session_path, "legend", f"frame_{frame_index:04d}.png")

    active_types = (legend_data or {}).get("active_types", [])
    if not active_types:
        return None

    ftr = LAYOUT_FOOTER_FRAC
    fig = _legend_fig(fig_w, fig_h)
    ax = fig.add_axes([0.0, 0.0, 1.0, ftr])
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 1.2)
    ax.axis("off")

    max_per_row = 4
    rows = max(1, (len(active_types) + max_per_row - 1) // max_per_row)
    per_row = (len(active_types) + rows - 1) // rows

    spacing = 8.0 / max(per_row, 1)
    item_w = 0.60  # swatch + gap to label
    total_span = (per_row - 1) * spacing + item_w
    x_start = (10 - total_span) / 2.0

    # Dynamic row spacing so all rows fit within ylim (0, 1.2)
    top_y = 0.95
    bot_y = 0.15
    row_spacing = (top_y - bot_y) / max(rows, 1) if rows > 1 else 0
    swatch_h = min(0.22, row_spacing * 0.6) if rows > 1 else 0.22
    font_sz = max(5.0, 6.5 - 0.3 * max(0, rows - 3))

    for idx, (name, color) in enumerate(active_types):
        row_i = idx // per_row
        col_i = idx % per_row
        x = x_start + col_i * spacing
        y = top_y - row_i * row_spacing
        ax.add_patch(
            plt.Rectangle(
                (x, y - swatch_h / 2),
                0.25,
                swatch_h,
                facecolor=color,
                edgecolor="#999999",
                linewidth=0.4,
                zorder=3,
            )
        )
        ax.text(
            x + 0.35,
            y + 0.03,
            name,
            fontsize=font_sz,
            color=_MARGIN_FG,
            va="center",
            ha="left",
            fontweight="bold",
            zorder=5,
        )

    _save_legend(fig, legend_path)
    return legend_path


# ── MRMS legend ─────────────────────────────────────────────────────────────


def _render_mrms_legend(
    session_path, frame_index, product, style_config, fig_w, fig_h, legend_data=None
):
    """Render colorbar legend for MRMS products in the footer margin.

    For MESH Track and Rotation Track, adds a per-frame max-value indicator.
    """
    legend_path = os.path.join(session_path, "legend", f"frame_{frame_index:04d}.png")

    ld = legend_data or {}
    cmap = ld.get("cmap")
    vmin = ld.get("vmin", 0)
    vmax = ld.get("vmax", 100)
    is_categorical = ld.get("is_categorical", False)
    cat_norm = ld.get("cat_norm")
    product_info = ld.get("product_info", {})
    data_masked = ld.get("data_masked")

    if cmap is None:
        return None

    ftr = LAYOUT_FOOTER_FRAC
    fig = _legend_fig(fig_w, fig_h)

    if is_categorical and cat_norm is not None:
        sm = plt.cm.ScalarMappable(cmap=cmap, norm=cat_norm)
        sm.set_array([])
        cbar_ax = fig.add_axes([0.05, ftr * 0.55, 0.90, ftr * 0.30])
        cb = fig.colorbar(sm, cax=cbar_ax, orientation="horizontal")

        categories = product_info.get("categories", {})
        if categories:
            bounds = cat_norm.boundaries
            mids = [(bounds[i] + bounds[i + 1]) / 2 for i in range(len(bounds) - 1)]
            cat_labels = [categories.get(int(m), str(int(m))) for m in mids]
            cb.set_ticks(mids)
            cb.set_ticklabels(cat_labels)

        cb.ax.tick_params(labelsize=7, colors=_MARGIN_FG)
        cb.outline.set_edgecolor("#cccccc")
        cb.set_label(product, fontsize=9, color=_MARGIN_FG, fontweight="bold")
    else:
        norm = plt.Normalize(vmin=vmin, vmax=vmax)
        sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
        sm.set_array([])
        cbar_ax = fig.add_axes([0.05, ftr * 0.55, 0.90, ftr * 0.30])
        cb = fig.colorbar(sm, cax=cbar_ax, orientation="horizontal")
        cb.ax.tick_params(labelsize=8, colors=_MARGIN_FG)
        cb.outline.set_edgecolor("#cccccc")

        levels = product_info.get("levels")
        if levels is not None:
            ticks = [l for l in levels if vmin <= l <= vmax]
            if ticks:
                cb.set_ticks(ticks)

        product_key = product_info.get("key", product)

        if "MESH" in product_key.upper() or "MESH" in product.upper():
            cb.set_label(
                "Max Estimated Hail Size (mm)",
                fontsize=9,
                color=_MARGIN_FG,
                fontweight="bold",
            )
            if data_masked is not None and np.ma.count(data_masked) > 0:
                from mrms.mrms_utils import _nws_hail_size_reference

                # Use 99.9th percentile to ignore isolated artifact pixels
                compressed = data_masked.compressed()
                max_mm = float(np.percentile(compressed, 99.9))
                clamped = max(float(vmin), min(float(vmax), max_mm))
                max_in = max_mm / 25.4
                nws_label, _ = _nws_hail_size_reference(max_in)
                cb.ax.axvline(clamped, color="#ff0000", linewidth=2.0, alpha=0.95)
                cb.ax.text(
                    clamped,
                    1.15,
                    f"{max_mm:.1f} mm ({max_in:.2f} in) - {nws_label}",
                    transform=cb.ax.get_xaxis_transform(),
                    ha="center",
                    va="bottom",
                    color="#000000",
                    fontsize=8,
                    fontweight="bold",
                )

        elif "Rotation" in product or "rotation" in product_key:
            cb.set_label(
                "Rotation Track (s⁻¹ × 1000)",
                fontsize=9,
                color=_MARGIN_FG,
                fontweight="bold",
            )
            base_ticks = np.array([0, 2, 4, 6, 8, 10], dtype=float)
            mask = (base_ticks >= vmin) & (base_ticks <= vmax)
            ticks = base_ticks[mask]
            labels_map = {
                0: "0\nNone",
                2: "2\nWeak",
                4: "4\nMod",
                6: "6\nStrong",
                8: "8\nV.Strong",
                10: "10\nExtreme",
            }
            labels = [labels_map.get(int(t), f"{t:g}") for t in ticks]
            cb.set_ticks(ticks)
            cb.set_ticklabels(labels)
        else:
            unit = product_info.get("units", "")
            display_name = product_info.get("full_name", product)
            label = f"{display_name} ({unit})" if unit else display_name
            cb.set_label(label, fontsize=9, color=_MARGIN_FG, fontweight="bold")

    _save_legend(fig, legend_path)
    return legend_path


# ── SPC legend ──────────────────────────────────────────────────────────────


def _render_spc_legend(
    session_path, frame_index, product, style_config, fig_w, fig_h, legend_data=None
):
    """Render legend for SPC products in the footer margin."""
    legend_path = os.path.join(session_path, "legend", f"frame_{frame_index:04d}.png")

    hazard = product.lower()
    ftr = LAYOUT_FOOTER_FRAC

    fig = _legend_fig(fig_w, fig_h)
    ax = fig.add_axes([0.0, 0.0, 1.0, ftr])
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 1.2)
    ax.axis("off")

    lbl_kw = dict(
        fontsize=7.5,
        color=_MARGIN_FG,
        fontweight="bold",
        va="center",
        ha="left",
        zorder=5,
    )

    if hazard == "watches":
        items = [
            ("Tornado Watch", style_config.get("watch_tornado_color", "#FFFF00")),
            ("Severe T-Storm Watch", style_config.get("watch_severe_color", "#FFA500")),
        ]
        spacing = 5.5
        item_w = 1.15  # swatch(0.5) + gap(0.15) + ~label
        total_span = (len(items) - 1) * spacing + item_w
        x_start = (10 - total_span) / 2.0
        for i, (name, color) in enumerate(items):
            x = x_start + i * spacing
            ax.add_patch(
                plt.Rectangle(
                    (x, 0.40),
                    0.5,
                    0.35,
                    facecolor=color,
                    edgecolor="#999999",
                    linewidth=0.5,
                    alpha=float(style_config.get("watch_fill_alpha", 0.25)),
                    zorder=3,
                )
            )
            ax.text(x + 0.65, 0.57, name, **lbl_kw)

    elif hazard == "mds":
        color = (
            float(style_config.get("md_fill_color_r", 0.4)),
            float(style_config.get("md_fill_color_g", 0.8)),
            float(style_config.get("md_fill_color_b", 1.0)),
            float(style_config.get("md_fill_alpha", 0.2)),
        )
        item_w = 2.5  # swatch + label
        x_start = (10 - item_w) / 2.0
        ax.add_patch(
            plt.Rectangle(
                (x_start, 0.40),
                0.5,
                0.35,
                facecolor=color,
                edgecolor=style_config.get("md_edge_color", "#66CCFF"),
                linewidth=1.0,
                zorder=3,
            )
        )
        ax.text(x_start + 0.65, 0.57, "Mesoscale Discussion", **lbl_kw)

    elif hazard == "reports":
        items = [
            ("Tornado", style_config.get("report_tornado_color", "#FF0000")),
            ("Hail", style_config.get("report_hail_color", "#00FF00")),
            ("Wind", style_config.get("report_wind_color", "#0088FF")),
        ]
        spacing = 3.0
        item_w = 0.9  # marker + label
        total_span = (len(items) - 1) * spacing + item_w
        x_start = (10 - total_span) / 2.0
        for i, (name, color) in enumerate(items):
            x = x_start + i * spacing
            ax.plot(
                x + 0.15,
                0.57,
                "o",
                color=color,
                markersize=int(style_config.get("report_marker_size", 4)),
                zorder=3,
            )
            ax.text(x + 0.4, 0.57, name, **lbl_kw)

    elif hazard == "fire_windrh":
        # Fire Weather Wind/RH legend — Elevated / Critical / Extremely Critical
        items = [
            ("Elevated", "#FFBF80", "#FF7F00"),
            ("Critical", "#FF8080", "#FF0000"),
            ("Extremely Critical", "#FF80FF", "#FF00FF"),
        ]
        spacing = 3.0
        item_w = 0.80
        total_span = (len(items) - 1) * spacing + item_w
        x_start = (10 - total_span) / 2.0
        poly_alpha = float(style_config.get("outlook_fill_alpha", 0.45))
        for i, (name, fill, stroke) in enumerate(items):
            x = x_start + i * spacing
            ax.add_patch(
                plt.Rectangle(
                    (x, 0.40),
                    0.35,
                    0.35,
                    facecolor=fill,
                    edgecolor=stroke,
                    linewidth=0.8,
                    alpha=poly_alpha,
                    zorder=3,
                )
            )
            ax.text(x + 0.45, 0.57, name, **lbl_kw)

    elif hazard == "fire_dryt":
        # Fire Weather Dry Thunderstorm legend — Isolated / Scattered
        items = [
            ("Isolated Dry T-Storm", "#FFBF80", "#FF7F00"),
            ("Scattered Dry T-Storm", "#FF8080", "#FF0000"),
        ]
        spacing = 4.5
        item_w = 0.80
        total_span = (len(items) - 1) * spacing + item_w
        x_start = (10 - total_span) / 2.0
        poly_alpha = float(style_config.get("outlook_fill_alpha", 0.45))
        for i, (name, fill, stroke) in enumerate(items):
            x = x_start + i * spacing
            ax.add_patch(
                plt.Rectangle(
                    (x, 0.40),
                    0.35,
                    0.35,
                    facecolor=fill,
                    edgecolor=stroke,
                    linewidth=0.8,
                    alpha=poly_alpha,
                    zorder=3,
                )
            )
            ax.text(x + 0.45, 0.57, name, **lbl_kw)

    else:
        # Convective outlooks (cat/torn/wind/hail/prob)
        cat_colors = [
            ("Gen T-Storms", "#C0E8C0"),
            ("Marginal", "#66A366"),
            ("Slight", "#FFE066"),
            ("Enhanced", "#FFA500"),
            ("Moderate", "#FF0000"),
            ("High", "#FF00FF"),
        ]

        # CIG levels apply to torn/wind/hail individual hazard outlooks
        show_cig = hazard in ("torn", "wind", "hail")
        if show_cig:
            # Patterns match SPC official CIG graphics:
            # CIG1 = broken diag upper-right to lower-left (sparse /)
            # CIG2 = solid diag upper-left to lower-right (dense \)
            # CIG3 = solid cross-hatch both directions   (dense x)
            cig_levels = [("1", "/", 0.6), ("2", "\\\\\\\\", 1.2)]
            if hazard in ("torn", "wind"):
                cig_levels.append(("3", "xx", 1.8))
            cat_y = 0.68
            cat_text_y = 0.85
            cig_y = 0.15
            cig_text_y = 0.32
        else:
            cat_y = 0.40
            cat_text_y = 0.57

        spacing = 1.55
        item_w = 0.80  # swatch(0.35) + gap + label
        total_span = (len(cat_colors) - 1) * spacing + item_w
        x_start = (10 - total_span) / 2.0
        for i, (name, color) in enumerate(cat_colors):
            x = x_start + i * spacing
            ax.add_patch(
                plt.Rectangle(
                    (x, cat_y),
                    0.35,
                    0.35,
                    facecolor=color,
                    edgecolor="#999999",
                    linewidth=0.4,
                    alpha=float(style_config.get("outlook_fill_alpha", 0.45)),
                    zorder=3,
                )
            )
            ax.text(x + 0.45, cat_text_y, name, **lbl_kw)

        if show_cig:
            # CIG intensity swatches matching SPC official style
            from matplotlib.patches import Rectangle as MplRect

            cig_spacing = 2.2 if len(cig_levels) == 3 else 2.8
            total_cig = 1.2 + (len(cig_levels) - 1) * cig_spacing + 0.80
            cig_x_start = (10 - total_cig) / 2.0
            ax.text(
                cig_x_start + 0.1,
                cig_text_y,
                "Intensity",
                fontsize=8,
                color=_MARGIN_FG,
                fontweight="bold",
                va="center",
                ha="left",
                zorder=5,
            )
            swatch_x0 = cig_x_start + 1.4
            cig_hatch_color = style_config.get("cig_hatch_color", "#000000")
            sw = 0.35
            for i, (num_label, hatch_pat, border_w) in enumerate(cig_levels):
                x = swatch_x0 + i * cig_spacing
                # White background swatch with border weight per level
                ax.add_patch(
                    plt.Rectangle(
                        (x, cig_y),
                        sw,
                        sw,
                        facecolor="#ffffff",
                        edgecolor="#000000",
                        linewidth=border_w,
                        zorder=3,
                    )
                )
                if num_label == "1":
                    # CIG1: dashed diagonal lines (/ direction)
                    clip_rect = MplRect(
                        (x, cig_y),
                        sw,
                        sw,
                        transform=ax.transData,
                        fill=False,
                        edgecolor="none",
                    )
                    ax.add_patch(clip_rect)
                    offsets = [-0.15, -0.05, 0.05, 0.15, 0.25, 0.35, 0.45]
                    for off in offsets:
                        (ln,) = ax.plot(
                            [x + off, x + off + sw],
                            [cig_y, cig_y + sw],
                            color=cig_hatch_color,
                            linewidth=0.7,
                            linestyle=(0, (2, 2)),
                            zorder=5,
                            clip_on=True,
                        )
                        ln.set_clip_path(clip_rect)
                else:
                    # CIG2/3: standard matplotlib hatching
                    ax.add_patch(
                        plt.Rectangle(
                            (x, cig_y),
                            sw,
                            sw,
                            facecolor="none",
                            edgecolor=cig_hatch_color,
                            linewidth=0.0,
                            hatch=hatch_pat,
                            zorder=4,
                        )
                    )
                ax.text(x + 0.45, cig_text_y, num_label, **lbl_kw)

    _save_legend(fig, legend_path)
    return legend_path


# ═════════════════════════════════════════════════════════════════════════════
# PRODUCT FRAME DISPATCHER
# ═════════════════════════════════════════════════════════════════════════════


def _render_product_frame(
    session_path,
    frame_index,
    product_group,
    product,
    region,
    timestamp_utc,
    timestamp_local,
    projection,
    extent,
    fig_w,
    fig_h,
    style_config=None,
    logo_file=None,
    custom_extent=None,
    day=1,
    report_day="today",
    item_id=None,
):
    """Render a single product frame + HUD + legend using real data sources."""
    style_config = style_config or {}
    group = product_group.lower()
    legend_data = None

    # Dispatch to product-specific renderer (returns dict)
    if group == "alerts":
        render_result = _render_alerts_product(
            session_path,
            frame_index,
            product,
            region,
            projection,
            extent,
            fig_w,
            fig_h,
            style_config,
            custom_extent,
        )
    elif group == "surface":
        render_result = _render_surface_product(
            session_path,
            frame_index,
            product,
            region,
            projection,
            extent,
            fig_w,
            fig_h,
            style_config,
            custom_extent,
        )
    elif group == "mrms":
        render_result = _render_mrms_product(
            session_path,
            frame_index,
            product,
            region,
            projection,
            extent,
            fig_w,
            fig_h,
            style_config,
            custom_extent,
        )
    elif group == "spc":
        render_result = _render_spc_product(
            session_path,
            frame_index,
            product,
            region,
            projection,
            extent,
            fig_w,
            fig_h,
            style_config,
            custom_extent,
            day=day,
            report_day=report_day,
            item_id=item_id,
        )
    else:
        # Fallback: render a label-only placeholder
        fallback_path = os.path.join(
            session_path, "product", f"frame_{frame_index:04d}.png"
        )
        fig, ax = _create_transparent_axes(projection, extent, fig_w, fig_h)
        ax.text(
            0.5,
            0.5,
            f"{product_group.upper()}: {product}\n{timestamp_local or timestamp_utc}",
            transform=ax.transAxes,
            fontsize=14,
            color="white",
            ha="center",
            va="center",
            bbox=dict(facecolor="black", alpha=0.5),
            zorder=100,
        )
        _save_transparent(fig, fallback_path)
        render_result = {"product_path": fallback_path, "legend_data": None}

    product_path = render_result["product_path"]
    legend_data = render_result.get("legend_data")

    # Render legend
    legend_path = _render_legend(
        session_path,
        frame_index,
        product_group,
        product,
        style_config,
        fig_w,
        fig_h,
        legend_data,
    )

    # Render static overlay (left HUD + logo)
    static_overlay_path = _render_hud_left_logo(
        session_path=session_path,
        frame_index=frame_index,
        fig_w=fig_w,
        fig_h=fig_h,
        projection=projection,
        extent=extent,
        product_group=product_group,
        product=product,
        region=region,
        custom_extent=custom_extent,
        style_config=style_config,
        logo_file=logo_file,
        day=day,
        report_day=report_day,
    )

    # Render HUD right (timestamp)
    hud_right_path = _render_hud_right(
        session_path,
        frame_index,
        fig_w,
        fig_h,
        timestamp_local or timestamp_utc,
        style_config,
        projection,
        extent,
    )

    return {
        "product_path": product_path,
        "hud_right_path": hud_right_path,
        "static_overlay_path": static_overlay_path,
        "legend_path": legend_path,
    }


def generate_weather_layers(
    product_group: str,
    product: str,
    region: str = "CONUS",
    custom_extent: tuple = None,
    date_from: str = None,
    date_to: str = None,
    frames_count: int = 1,
    fps: int = 4,
    user_tz: str = None,
    style_config: dict = None,
    logo_file: str = None,
    progress_callback=None,
    day: int = 1,
    report_day: str = "today",
    item_id: str = None,
):
    """Generate layered weather output for current or archive mode.

    Returns a dict with session metadata and frame info, or None on failure.
    """
    # Merge: WEATHER base → per-group defaults → user overrides
    style_config = resolve_weather_group_style_config(product_group, style_config)

    # Cleanup old sessions before creating new one
    cleanup_sessions()

    if progress_callback:
        progress_callback(5, "Initializing session...", "init")

    # Create session
    session_id, session_path, manifest = create_session(
        product_group, product, region, custom_extent
    )

    # Compute projection once for all layers
    projection, extent, fig_w, fig_h = compute_lambert_params(region, custom_extent)

    if progress_callback:
        progress_callback(10, "Generating basemap...", "basemap")

    # Generate or retrieve cached basemap
    basemap_src = generate_basemap(region, custom_extent, style_config)

    # Copy basemap into session
    basemap_session = os.path.join(session_path, "basemap", "basemap.png")
    shutil.copy2(basemap_src, basemap_session)

    # Determine frame timestamps
    now_utc = datetime.now(timezone.utc)

    if date_from and date_to:
        # Archive mode - generate timestamps across the range
        start = _parse_datetime(date_from)
        end = _parse_datetime(date_to)

        total_frames = max(1, min(frames_count, 100))
        if total_frames == 1:
            timestamps = [start]
        else:
            delta = (end - start) / max(1, total_frames - 1)
            timestamps = [start + delta * i for i in range(total_frames)]
    else:
        # Current mode - single frame at now
        timestamps = [now_utc]
        total_frames = 1

    if progress_callback:
        progress_callback(20, f"Rendering {total_frames} frame(s)...", "render")

    # Resolve timezone for display
    from dateutil import tz as tz_module

    display_tz = None
    if user_tz:
        try:
            display_tz = tz_module.gettz(user_tz)
        except Exception:
            pass
    if display_tz is None:
        display_tz = tz_module.gettz("America/New_York")

    frames = []
    for i, ts in enumerate(timestamps):
        ts_utc_str = ts.strftime("%Y-%m-%d %H:%M UTC")
        ts_local = ts.astimezone(display_tz)
        ts_local_str = ts_local.strftime("%Y-%m-%d %I:%M %p %Z")

        pct = 20 + int(70 * (i + 1) / total_frames)
        if progress_callback:
            progress_callback(
                pct, f"Rendering frame {i + 1}/{total_frames}...", "render"
            )

        result = _render_product_frame(
            session_path=session_path,
            frame_index=i,
            product_group=product_group,
            product=product,
            region=region,
            timestamp_utc=ts_utc_str,
            timestamp_local=ts_local_str,
            projection=projection,
            extent=extent,
            fig_w=fig_w,
            fig_h=fig_h,
            style_config=style_config,
            logo_file=logo_file,
            custom_extent=custom_extent,
            day=day,
            report_day=report_day,
            item_id=item_id,
        )

        frames.append(
            {
                "index": i,
                "timestamp_utc": ts_utc_str,
                "timestamp_local": ts_local_str,
                "product_path": result["product_path"],
                "hud_right_path": result["hud_right_path"],
                "static_overlay_path": result.get("static_overlay_path"),
                "legend_path": result.get("legend_path"),
            }
        )

    if progress_callback:
        progress_callback(95, "Finalizing session...", "finalize")

    # Update manifest
    manifest["frame_count"] = len(frames)
    manifest["frames"] = [
        {
            "index": f["index"],
            "timestamp_utc": f["timestamp_utc"],
            "timestamp_local": f["timestamp_local"],
        }
        for f in frames
    ]
    manifest["updated_utc"] = datetime.now(timezone.utc).isoformat()

    with open(_manifest_path(session_id), "w") as f:
        json.dump(manifest, f, indent=2)

    return {
        "session_id": session_id,
        "session_path": session_path,
        "basemap_path": basemap_session,
        "frames": frames,
        "manifest": manifest,
        "projection_params": {
            "center_lon": (extent[0] + extent[1]) / 2.0,
            "center_lat": (extent[2] + extent[3]) / 2.0,
            "extent": extent,
        },
    }
