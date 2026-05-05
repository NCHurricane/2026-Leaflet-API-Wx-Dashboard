"""
MRMS Utilities
Image generation for Multi-Radar Multi-Sensor (MRMS) products.
"""

import importlib.util
import json
from dateutil import tz
import cartopy.feature as cfeature
import cartopy.crs as ccrs
from matplotlib.offsetbox import AnnotationBbox, OffsetImage
import matplotlib.image as mpimg
import matplotlib.patheffects as PathEffects
import matplotlib.pyplot as plt
import os
import sys
import gzip
import shutil
import threading
import time as _time
from datetime import datetime
from typing import List, Tuple, Optional, Callable
from font_utils import register_montserrat_fonts
from config.mrms_config import MRMS_PRODUCTS, MRMS_COLORMAPS
from config.geo_config import STATE_BOUNDS, STATES_FULL
from config.style_config import resolve_mrms_style_config
from geo_utils import (
    CensusCounties,
    load_state_geometries,
    build_conus_geometry,
)  # Consolidated geometry helpers

import numpy as np
import matplotlib

matplotlib.use("Agg")

# GRIB2 reading

try:
    import xarray as xr

    CFGRIB_AVAILABLE = importlib.util.find_spec("cfgrib") is not None
    CFGRIB_IMPORT_ERROR = None
except ImportError as e:
    CFGRIB_AVAILABLE = False
    CFGRIB_IMPORT_ERROR = str(e)

# Add parent directory to path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)


# Font registration
register_montserrat_fonts()

# Check imageio availability for animation encoding support.
IMAGEIO_AVAILABLE = importlib.util.find_spec("imageio") is not None

# Serialize .grib2 refresh from .grib2.gz so parallel requests/workers do not
# read a partially-written uncompressed file.
_MRMS_GRIB_DECOMPRESS_LOCK = threading.Lock()


# =============================================================================
# CENSUS COUNTIES SHAPEFILE SUPPORT — imported from geo_utils
# =============================================================================
# CensusCounties is imported at the top of this file from geo_utils.


def warp_array_to_mercator(
    data: np.ma.MaskedArray,
    lat_1d: np.ndarray,
    lon_1d: np.ndarray,
) -> tuple[np.ma.MaskedArray, list[float]]:
    """Reproject a flat (equirectangular) data array to Web Mercator (EPSG:3857)
    so pixels align with Leaflet's imageOverlay at any zoom level.

    Args:
        data:   2-D masked array, rows ordered N→S (origin=upper) or S→N (origin=lower).
        lat_1d: 1-D latitude coordinate array matching data rows.
        lon_1d: 1-D longitude coordinate array matching data cols.

    Returns:
        (warped_masked_array, [west, east, south, north]) — bounds are WGS84,
        unchanged from the source grid, because Leaflet still expects geographic
        corner coordinates for imageOverlay.  Only the pixel content is warped.
    """
    import rasterio
    import rasterio.transform
    import rasterio.warp
    import rasterio.crs

    lat = np.asarray(lat_1d, dtype=np.float64)
    lon = np.asarray(lon_1d, dtype=np.float64)

    # Ensure longitude is in [-180, 180].
    lon = np.where(lon > 180.0, lon - 360.0, lon)

    lat_min, lat_max = float(lat.min()), float(lat.max())
    lon_min, lon_max = float(lon.min()), float(lon.max())

    src_rows, src_cols = data.shape

    # rasterio expects rows N→S (top = north).
    if lat[0] < lat[-1]:  # S→N stored — flip to N→S.
        data_ns = data[::-1, :]
        lat_ns = lat[::-1]
    else:
        data_ns = data
        lat_ns = lat

    dlat = abs(float(lat_ns[0] - lat_ns[1])) if src_rows > 1 else 0.01
    dlon = abs(float(lon[1] - lon[0])) if src_cols > 1 else 0.01

    src_transform = rasterio.transform.from_bounds(
        lon_min - 0.5 * dlon,
        lat_min - 0.5 * dlat,
        lon_max + 0.5 * dlon,
        lat_max + 0.5 * dlat,
        src_cols,
        src_rows,
    )
    src_crs = rasterio.crs.CRS.from_epsg(4326)
    dst_crs = rasterio.crs.CRS.from_epsg(3857)

    fill_val = 1e38
    src_data = np.ma.filled(data_ns.astype(np.float32), fill_val)

    dst_transform, dst_width, dst_height = rasterio.warp.calculate_default_transform(
        src_crs,
        dst_crs,
        src_cols,
        src_rows,
        left=lon_min - 0.5 * dlon,
        bottom=lat_min - 0.5 * dlat,
        right=lon_max + 0.5 * dlon,
        top=lat_max + 0.5 * dlat,
    )

    dst_data = np.full((dst_height, dst_width), fill_val, dtype=np.float32)
    rasterio.warp.reproject(
        source=src_data,
        destination=dst_data,
        src_transform=src_transform,
        src_crs=src_crs,
        dst_transform=dst_transform,
        dst_crs=dst_crs,
        resampling=rasterio.warp.Resampling.nearest,
        src_nodata=fill_val,
        dst_nodata=fill_val,
    )

    warped_masked = np.ma.masked_where(
        (dst_data >= fill_val * 0.9) | ~np.isfinite(dst_data), dst_data
    )

    actual_bounds = [lon_min, lon_max, lat_min, lat_max]
    return warped_masked, actual_bounds


def decompress_grib2_gz(gz_path: str) -> str:
    """
    Decompress .grib2.gz file to .grib2 file.

    Args:
        gz_path: Path to .grib2.gz file

    Returns:
        Path to decompressed .grib2 file
    """
    if not gz_path.endswith(".gz"):
        return gz_path

    grib_path = gz_path[:-3]  # Remove .gz extension

    with _MRMS_GRIB_DECOMPRESS_LOCK:
        # Skip decompression only when the existing .grib2 is as new as (or newer
        # than) the .gz.  If the .gz was just updated by the worker, the .grib2
        # will be older and must be replaced to avoid serving stale data.
        if os.path.exists(grib_path):
            gz_mtime = os.path.getmtime(gz_path)
            grib_mtime = os.path.getmtime(grib_path)
            if grib_mtime >= gz_mtime and os.path.getsize(grib_path) > 0:
                return grib_path

        tmp_path = grib_path + ".part"
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass

        with gzip.open(gz_path, "rb") as f_in:
            with open(tmp_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)

        if not os.path.exists(tmp_path) or os.path.getsize(tmp_path) == 0:
            raise ValueError(f"Decompressed MRMS file is empty: {gz_path}")

        os.replace(tmp_path, grib_path)

    return grib_path


def _compute_crop_slices(lat_coord, lon_coord, crop_extent, buffer_deg=2.0):
    """Compute 1D latitude/longitude slice objects for an extent.

    Returns ``None`` when no overlap is found.
    """
    if crop_extent is None or lat_coord is None or lon_coord is None:
        return None

    west, east, south, north = crop_extent
    lon_mask = (lon_coord >= west -
                buffer_deg) & (lon_coord <= east + buffer_deg)
    lat_mask = (lat_coord >= south -
                buffer_deg) & (lat_coord <= north + buffer_deg)

    if not np.any(lon_mask) or not np.any(lat_mask):
        return None

    lon_idx = np.where(lon_mask)[0]
    lat_idx = np.where(lat_mask)[0]
    return (
        slice(int(lat_idx[0]), int(lat_idx[-1]) + 1),
        slice(int(lon_idx[0]), int(lon_idx[-1]) + 1),
    )


def read_mrms_grib2(
    grib_path: str,
    product: str,
    crop_extent: Optional[List[float]] = None,
    crop_slices: Optional[Tuple[slice, slice]] = None,
) -> Tuple[np.ndarray, dict]:
    """
    Read MRMS GRIB2 file using cfgrib/xarray.

    Args:
        grib_path: Path to GRIB2 file (.grib2 or .grib2.gz)
        product: MRMS product key
        crop_extent: Optional [west, east, south, north] extent for read-time cropping
        crop_slices: Optional precomputed (lat_slice, lon_slice) to reuse across frames

    Returns:
        Tuple of (data_array, metadata_dict)

    Raises:
        RuntimeError: If cfgrib is not available
        ValueError: If file cannot be read
    """
    if not CFGRIB_AVAILABLE:
        raise RuntimeError(
            f"cfgrib is required to read GRIB2 files. Install with: pip install cfgrib eccodes\nError: {CFGRIB_IMPORT_ERROR}"
        )

    # Decompress if needed
    if grib_path.endswith(".gz"):
        grib_path = decompress_grib2_gz(grib_path)

    try:
        # Open GRIB2 file with xarray/cfgrib.
        # Use in-memory index to avoid stale .idx sidecar warnings and extra disk churn.
        try:
            ds = xr.open_dataset(
                grib_path,
                engine="cfgrib",
                backend_kwargs={"indexpath": ""},
            )
        except TypeError:
            # Fallback for environments where backend_kwargs is not accepted.
            ds = xr.open_dataset(grib_path, engine="cfgrib")

        # Extract data array (first data variable)
        data_vars = list(ds.data_vars)
        if not data_vars:
            raise ValueError(f"No data variables found in {grib_path}")

        # Extract metadata - handle different coordinate naming conventions
        # MRMS GRIB2 files may use 'latitude'/'longitude' or 'lat'/'lon' or 'y'/'x'
        lat_coord = None
        lon_coord = None
        lat_dim_name = None
        lon_dim_name = None

        print(f"[DEBUG] Reading {grib_path}")
        print(f"[DEBUG] Dataset coords: {list(ds.coords.keys())}")
        print(f"[DEBUG] Dataset dims: {list(ds.sizes.keys())}")
        print(f"[DEBUG] Dataset variables: {list(ds.data_vars.keys())}")

        # Try different latitude coordinate names
        for lat_name in ["latitude", "lat", "y"]:
            if lat_name in ds.coords or lat_name in ds.dims:
                lat_dim_name = lat_name
                lat_coord = ds[lat_name].values
                print(
                    f"[DEBUG] Found latitude as '{lat_name}', shape: {lat_coord.shape}"
                )
                break

        # Try different longitude coordinate names
        for lon_name in ["longitude", "lon", "x"]:
            if lon_name in ds.coords or lon_name in ds.dims:
                lon_dim_name = lon_name
                lon_coord = ds[lon_name].values
                print(
                    f"[DEBUG] Found longitude as '{lon_name}', shape: {lon_coord.shape}"
                )
                break

        if lat_coord is None:
            print(
                f"[DEBUG] WARNING: Could not find latitude in coords: {list(ds.coords.keys())}"
            )
        if lon_coord is None:
            print(
                f"[DEBUG] WARNING: Could not find longitude in coords: {list(ds.coords.keys())}"
            )

        # If we have 1D coordinates, keep them as-is for imshow
        # (pcolormesh needs 2D meshgrid, but imshow just needs extent)
        # Convert longitude from 0-360 to -180/180 if needed
        if lon_coord is not None and np.any(lon_coord > 180):
            lon_coord = lon_coord - 360

        data_da = ds[data_vars[0]]
        resolved_crop_slices = crop_slices

        # Compute read-time crop slices once and reuse across subsequent frames.
        if resolved_crop_slices is None and crop_extent is not None:
            resolved_crop_slices = _compute_crop_slices(
                lat_coord, lon_coord, crop_extent
            )

        pre_cropped = False
        if (
            resolved_crop_slices is not None
            and lat_dim_name is not None
            and lon_dim_name is not None
        ):
            lat_slice, lon_slice = resolved_crop_slices
            data_da = data_da.isel(
                {lat_dim_name: lat_slice, lon_dim_name: lon_slice})
            if lat_coord is not None:
                lat_coord = lat_coord[lat_slice]
            if lon_coord is not None:
                lon_coord = lon_coord[lon_slice]
            pre_cropped = True

        data_array = data_da.values

        metadata = {
            "latitude": lat_coord,
            "longitude": lon_coord,
            "time": ds["time"].values if "time" in ds else None,
            "projection": str(ds.attrs.get("GRIB_gridType", "unknown")),
            "crop_slices": resolved_crop_slices,
            "pre_cropped": pre_cropped,
        }

        ds.close()

        return data_array, metadata

    except Exception as e:
        raise ValueError(f"Failed to read GRIB2 file {grib_path}: {e}")


def plot_cities_on_map(ax, extent, style_config, z_cities=30):
    """
    Plot city labels on map with collision detection and proper styling.
    Matches satellite/radar city rendering approach.

    Args:
        ax: Matplotlib axes (Cartopy GeoAxes)
        extent: Map extent [west, east, south, north]
        style_config: Style configuration dict
        z_cities: Base z-order for city elements
    """
    cities_file = style_config.get("cities_file", "us-cities.json")
    city_density = float(style_config.get("city_density", 5))
    density_scale = city_density / 5.0
    city_collision_w = float(style_config.get("city_collision_w", 0.05))
    city_collision_h = float(style_config.get("city_collision_h", 0.02))
    city_text_size = int(style_config.get("city_text_size", 12))
    city_text_color = style_config.get("city_text_color", "#ffffff")
    city_text_bg_color = style_config.get("city_text_bg_color", "#000000")
    city_text_bg_alpha = float(style_config.get("city_text_bg_alpha", 0.3))

    if isinstance(cities_file, str) and cities_file.startswith("data/"):
        cities_file = cities_file.split("/", 1)[1]

    # Construct full path to cities file
    cities_path = os.path.join(PARENT_DIR, "data", cities_file)
    print(
        f"[DEBUG] plot_cities_on_map: Looking for cities file at: {cities_path}")

    if not os.path.exists(cities_path):
        fallback_path = os.path.join(PARENT_DIR, "data", "us-cities.json")
        print(
            f"[WARN] Cities file not found: {cities_path}; using {fallback_path}")
        cities_path = fallback_path

    with open(cities_path, "r") as f:
        cities = json.load(f)

    print(
        f"[DEBUG] Loaded cities from {cities_file}, type={type(cities).__name__}")

    # Filter cities by extent
    west, east, south, north = extent

    # Handle list-of-dict format (us-cities.json)
    if not isinstance(cities, list):
        print(
            f"[WARN] Cities data is not a list, type={type(cities).__name__}")
        return

    visible_cities = []
    for c in cities:
        try:
            lat = float(c.get("latitude"))
            lon = float(c.get("longitude"))
        except (ValueError, TypeError):
            continue
        if (south - 0.1) <= lat <= (north + 0.1) and (west - 0.1) <= lon <= (
            east + 0.1
        ):
            visible_cities.append(c)

    print(
        f"[DEBUG] Found {len(visible_cities)} cities in extent [{west:.2f}, {east:.2f}, {south:.2f}, {north:.2f}]"
    )

    # Sort by city rank (lower is higher priority)
    def _city_priority(city):
        try:
            rank_val = float(city.get("rank"))
        except (TypeError, ValueError):
            rank_val = 9999.0
        return rank_val

    visible_cities.sort(key=_city_priority)

    # Collision detection
    map_width = east - west
    map_height = north - south
    text_w = map_width * city_collision_w * density_scale
    text_h = map_height * city_collision_h * density_scale
    drawn_bboxes = []
    drawn_count = 0

    for city in visible_cities:
        lat = float(city["latitude"])
        lon = float(city["longitude"])
        city_name = city.get("city", "")

        # Collision box
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

        # Draw city label at the city coordinate
        txt = ax.text(
            lon,
            lat,
            city_name.upper(),
            transform=ccrs.PlateCarree(),
            fontsize=city_text_size,
            color=city_text_color,
            fontname="Montserrat",
            fontweight="black",
            fontstyle="italic",
            ha="center",
            va="center",
            zorder=z_cities + 1,
            alpha=0.95,
            bbox=dict(
                facecolor=city_text_bg_color,
                alpha=city_text_bg_alpha,
                edgecolor="none",
                boxstyle="round,pad=0.2",
            ),
            clip_on=True,
        )
        txt.set_path_effects(
            [PathEffects.withStroke(linewidth=2, foreground="black")])
        drawn_bboxes.append((cand_x_min, cand_x_max, cand_y_min, cand_y_max))
        drawn_count += 1

    print(f"[DEBUG] Drew {drawn_count} cities on map")


def generate_mrms_image(
    product: str,
    data_files: List[Tuple[str, datetime]],
    output_dir: str,
    region: str = "CONUS",
    north: Optional[float] = None,
    south: Optional[float] = None,
    east: Optional[float] = None,
    west: Optional[float] = None,
    show_places: bool = True,
    fps: int = 10,
    style_config: dict = None,
    progress_callback: Optional[Callable[[str, int, int], None]] = None,
    user_tz: str = "America/New_York",
) -> Tuple[str, str]:
    raise RuntimeError(
        "mrms.generate_mrms_image is disabled in Phase 0. "
        "Rendering was removed from mrms_utils; use unified weather/export pipeline."
    )

    """
    Generate MRMS image or animation.

    Args:
        product: MRMS product key (e.g., "QPE_01H", "PrecipRate")
        data_files: List of (file_path, datetime) tuples
        output_dir: Output directory for images
        region: "CONUS", state code (e.g. "NC"), or "custom"
        north, south, east, west: Custom extent bounds (if region="custom")
        show_places: Whether to show city labels
        fps: Frames per second for animation
        style_config: Style configuration dict
        progress_callback: Optional callback(stage, current, total)
        user_tz: User timezone for HUD display

    Returns:
        Tuple of (output_path, message)
    """
    if not CFGRIB_AVAILABLE:
        return (
            "",
            "Error: cfgrib is required. Install with: pip install cfgrib eccodes",
        )

    if not data_files:
        return ("", "No data files provided")

    if product not in MRMS_PRODUCTS:
        return ("", f"Unknown product: {product}")

    # Get product configuration
    product_info = MRMS_PRODUCTS[product]
    style_config = resolve_mrms_style_config(style_config or {})

    print(
        f"[DEBUG] generate_mrms_image: region='{region}', north={north}, south={south}, east={east}, west={west}"
    )

    # Create output directory: output_dir / product / region
    region_dir = region.upper() if region != "custom" else "CUSTOM"
    latest_file_dt = max((dt for _, dt in data_files), default=None)
    if not isinstance(latest_file_dt, datetime):
        latest_file_dt = datetime.utcnow()
    print(f"[DEBUG] region_dir set to: '{region_dir}'")
    output_dir = os.path.join(
        output_dir,
        product,
        region_dir,
        latest_file_dt.strftime("%Y"),
        latest_file_dt.strftime("%m"),
        latest_file_dt.strftime("%d"),
    )
    os.makedirs(output_dir, exist_ok=True)
    print(f"[DEBUG] output_dir: {output_dir}")

    # Determine extent
    if region == "custom":
        if None in (north, south, east, west):
            return ("", "Custom region requires north/south/east/west bounds")
        extent = [west, east, south, north]
        print(
            f"[DEBUG] Custom region extent: west={west}, east={east}, south={south}, north={north}"
        )
        print(f"[DEBUG] Constructed extent: {extent}")
    elif region in STATE_BOUNDS:
        bounds = STATE_BOUNDS[region]  # [lon_min, lon_max, lat_min, lat_max]
        extent = [bounds[0], bounds[1], bounds[2], bounds[3]]
    else:
        extent = [-130, -60, 20, 50]  # CONUS fallback
        print(f"[DEBUG] Using CONUS fallback extent: {extent}")

    # Build a state-centered LambertConformal projection (matches surface/alerts)
    ext_lon0, ext_lon1, ext_lat0, ext_lat1 = extent
    center_lon = (ext_lon0 + ext_lon1) / 2.0
    center_lat = (ext_lat0 + ext_lat1) / 2.0
    proj = ccrs.LambertConformal(
        central_longitude=center_lon,
        central_latitude=center_lat,
    )

    # Compute projected aspect ratio for proper figure sizing
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
    data_aspect = proj_w / max(proj_h, 1.0)

    # Single image or animation?
    is_animation = len(data_files) > 1

    # Compute display label for the HUD
    if region == "custom":
        region_label = "Custom"
    elif region == "CONUS":
        region_label = "CONUS"
    else:
        region_label = STATES_FULL.get(region, region)

    if is_animation:
        return _generate_mrms_animation(
            product,
            product_info,
            data_files,
            output_dir,
            extent,
            proj,
            data_aspect,
            region_label,
            show_places,
            fps,
            style_config,
            progress_callback,
            user_tz,
            region,
        )
    else:
        return _generate_mrms_static_image(
            product,
            product_info,
            data_files[0],
            output_dir,
            extent,
            proj,
            data_aspect,
            region_label,
            show_places,
            style_config,
            progress_callback,
            user_tz,
            region,
        )


def _get_mrms_colormap_settings(product_info: dict):
    """Resolve MRMS colormap and normalization settings for a product."""
    cmap_name = product_info.get("colormap", "qpe")
    cmap_entry = MRMS_COLORMAPS.get(cmap_name, MRMS_COLORMAPS["qpe"])

    # Categorical colormaps return (cmap, norm, boundaries); others return just cmap.
    is_categorical = product_info.get("categorical", False)
    if isinstance(cmap_entry, tuple):
        cmap, cat_norm, cat_boundaries = cmap_entry
    else:
        cmap = cmap_entry
        cat_norm = None
        cat_boundaries = None

    vmin = product_info.get("vmin", 0)
    vmax = product_info.get("vmax", 100)
    return cmap, cat_norm, cat_boundaries, is_categorical, vmin, vmax


def _plot_mrms_data_layer(
    ax,
    data,
    metadata,
    extent,
    product_info,
    zo,
    cmap,
    is_categorical,
    cat_norm,
    vmin,
    vmax,
    data_alpha=1.0,
):
    """Plot the MRMS raster layer and return the image artist."""
    lon = metadata["longitude"]
    lat = metadata["latitude"]

    already_cropped = bool(metadata.get("pre_cropped", False))

    if not already_cropped:
        # extent = [lon_min, lon_max, lat_min, lat_max]
        ext_lon0, ext_lon1, ext_lat0, ext_lat1 = extent

        # Crop data array to visible extent (+2 deg buffer) before reprojection.
        # The full CONUS grid is 3500x7000 - for state views this reduces pixels by 90%+.
        buf = 2.0
        lon_mask = (lon >= ext_lon0 - buf) & (lon <= ext_lon1 + buf)
        lat_mask = (lat >= ext_lat0 - buf) & (lat <= ext_lat1 + buf)

        if np.any(lon_mask) and np.any(lat_mask):
            lon_idx = np.where(lon_mask)[0]
            lat_idx = np.where(lat_mask)[0]
            lon = lon[lon_idx[0]: lon_idx[-1] + 1]
            lat = lat[lat_idx[0]: lat_idx[-1] + 1]
            data = data[lat_idx[0]: lat_idx[-1] +
                        1, lon_idx[0]: lon_idx[-1] + 1]

    # Compute image extent from (possibly cropped) 1D coordinate arrays
    img_extent = [lon.min(), lon.max(), lat.min(), lat.max()]
    print(
        f"[DEBUG] {'Using pre-cropped' if already_cropped else 'After cropping'}: "
        f"img_extent = {img_extent}"
    )
    print(
        f"[DEBUG] {'Using pre-cropped' if already_cropped else 'After cropping'}: "
        f"data.shape = {data.shape}"
    )

    # Determine if latitude is N->S (descending) for origin parameter
    lat_descending = lat[0] > lat[-1] if len(lat) > 1 else False

    # Mask missing/no-data/no-coverage so land/ocean show through
    # Use product-specific sentinel values when available, plus universal <= 0 mask
    missing_val = product_info.get("missing_value")
    no_cov_val = product_info.get("no_coverage")
    mask = data <= 0
    if missing_val is not None and missing_val != 0:
        mask = mask | (data == missing_val)
    if no_cov_val is not None and no_cov_val != 0:
        mask = mask | (data == no_cov_val)
    data_masked = np.ma.masked_where(mask, data)

    if is_categorical and cat_norm is not None:
        image_artist = ax.imshow(
            data_masked,
            cmap=cmap,
            norm=cat_norm,
            extent=img_extent,
            origin="upper" if lat_descending else "lower",
            transform=ccrs.PlateCarree(),
            interpolation="nearest",
            alpha=data_alpha,
            zorder=zo["data"],
        )
    else:
        image_artist = ax.imshow(
            data_masked,
            cmap=cmap,
            extent=img_extent,
            origin="upper" if lat_descending else "lower",
            transform=ccrs.PlateCarree(),
            interpolation="nearest",
            alpha=data_alpha,
            vmin=vmin,
            vmax=vmax,
            zorder=zo["data"],
        )

    # Force the map extent to the requested bounds.
    # imshow() can reset extent, so enforce it after plotting data.
    print(f"[DEBUG] Forcing extent to: {extent}")
    ax.set_extent(extent, crs=ccrs.PlateCarree())
    print(
        f"[DEBUG] After set_extent, ax.get_extent() = {ax.get_extent(crs=ccrs.PlateCarree())}"
    )

    return image_artist


def _format_mrms_timestamp(file_dt, user_tz="America/New_York"):
    """Format MRMS frame time as local timestamp text for HUD display."""
    display_tz = tz.gettz(user_tz) if user_tz else tz.gettz("America/New_York")

    # Ensure file_dt is timezone-aware (assume UTC if naive)
    if file_dt.tzinfo is None:
        file_dt = file_dt.replace(tzinfo=tz.UTC)

    dt_local = file_dt.astimezone(display_tz)
    return dt_local.strftime("%m/%d/%Y\n%I:%M %p %Z")


def _upsert_mrms_time_hud(
    ax,
    file_dt,
    style_config,
    zo,
    user_tz="America/New_York",
    hud_right_ann=None,
):
    """Create or update the right HUD timestamp annotation."""
    hud_right_x = float(style_config.get("hud_right_x", 0.97))
    hud_right_y = float(style_config.get("hud_right_y", 0.97))
    hud_right_size = int(style_config.get("hud_right_size", 14))
    hud_right_text_color = style_config.get("hud_right_text_color", "#ffd700")
    hud_right_bg_color = style_config.get("hud_right_bg_color", "#000000")
    hud_right_edge_color = style_config.get("hud_right_edge_color", "#555555")
    hud_right_alpha = float(style_config.get("hud_right_alpha", 0.7))

    # Keep font sizing behavior consistent with frame renderer.
    fig_width = ax.figure.get_figwidth()
    scale_factor = max(fig_width / 12.8, 0.55)
    hud_right_size = int(hud_right_size * scale_factor)

    time_text = _format_mrms_timestamp(file_dt, user_tz=user_tz)
    if hud_right_ann is not None:
        hud_right_ann.set_text(time_text)
        return hud_right_ann

    return ax.annotate(
        time_text,
        xy=(hud_right_x, hud_right_y),
        xycoords="axes fraction",
        fontsize=hud_right_size,
        fontname="Montserrat",
        fontweight="black",
        fontstyle="italic",
        color=hud_right_text_color,
        ha="right",
        va="top",
        bbox=dict(
            boxstyle="round,pad=0.4",
            fc=hud_right_bg_color,
            ec=hud_right_edge_color,
            alpha=hud_right_alpha,
        ),
        zorder=zo["hud"],
    )


def _resolve_mrms_plot_extent(extent, style_config):
    """Apply style margin expansion to a base [w, e, s, n] extent."""
    west, east, south, north = extent
    expand_top = float(style_config.get("map_margin_top", 0.0))
    expand_bottom = float(style_config.get("map_margin_bottom", 0.0))
    expand_left = float(style_config.get("map_margin_left", 0.0))
    expand_right = float(style_config.get("map_margin_right", 0.0))

    lon_span = east - west
    lat_span = north - south

    return [
        west - lon_span * expand_left,
        east + lon_span * expand_right,
        south - lat_span * expand_bottom,
        north + lat_span * expand_top,
    ]


def _get_mrms_selected_region_geometry(region_code):
    """Return selected region geometry for border highlighting."""
    if not region_code:
        return None

    code = str(region_code).upper()
    if code == "CUSTOM":
        return None
    if code == "CONUS":
        return build_conus_geometry()

    state_geoms = load_state_geometries()
    return state_geoms.get(code)


def _masked_mrms_data(data, product_info):
    """Return MRMS data masked for missing/no-coverage and non-physical values."""
    arr = np.asarray(data, dtype=float)
    missing_val = product_info.get("missing_value")
    no_cov_val = product_info.get("no_coverage")

    invalid = ~np.isfinite(arr)
    invalid |= arr <= 0
    if missing_val is not None and missing_val != 0:
        invalid |= arr == missing_val
    if no_cov_val is not None and no_cov_val != 0:
        invalid |= arr == no_cov_val

    return np.ma.masked_where(invalid, arr)


def _resolve_mrms_data_alpha(style_config, product):
    """Resolve and clamp raster alpha for MRMS products."""
    try:
        data_alpha_default = float(style_config.get("mrms_data_alpha", 1.0))
    except Exception:
        data_alpha_default = 1.0

    if product.startswith("MESH"):
        try:
            data_alpha = float(style_config.get(
                "mesh_data_alpha", data_alpha_default))
        except Exception:
            data_alpha = data_alpha_default
    else:
        data_alpha = data_alpha_default

    return min(1.0, max(0.0, data_alpha))


def _rotation_track_legend_ticks(vmin, vmax):
    """Return user-friendly ticks and labels for Rotation Track colorbars."""
    base_ticks = np.array([0, 2, 4, 6, 8, 10], dtype=float)
    mask = (base_ticks >= float(vmin)) & (base_ticks <= float(vmax))
    ticks = base_ticks[mask]

    labels_by_tick = {
        0: "0\nNone",
        2: "2\nWeak",
        4: "4\nModerate",
        6: "6\nStrong",
        8: "8\nVery Strong",
        10: "10\nExtreme",
    }
    labels = [labels_by_tick.get(int(t), f"{t:g}") for t in ticks]
    return ticks, labels


def _nws_hail_size_reference(size_in):
    """Return nearest NWS hail-size reference label for a diameter in inches."""
    size_in = float(size_in)
    if not np.isfinite(size_in) or size_in <= 0:
        return "Unknown", None

    # NWS reference diameters and labels.
    # Source taxonomy mirrors official NWS hail-size comparison guidance.
    refs = [
        (0.25, "Pea"),
        (0.50, "Mothball/Peanut"),
        (0.75, "Penny"),
        (0.875, "Nickel"),
        (1.00, "Quarter"),
        (1.25, "Half Dollar"),
        (1.50, "Ping Pong Ball"),
        (1.75, "Golf Ball"),
        (2.00, "Hen Egg"),
        (2.50, "Tennis Ball"),
        (2.75, "Baseball"),
        (3.00, "Large Apple"),
        (4.00, "Softball"),
        (4.50, "Grapefruit"),
    ]

    if size_in > 4.5:
        return "Greater than Grapefruit", 4.5

    ref_size, ref_label = min(refs, key=lambda item: abs(item[0] - size_in))
    return ref_label, ref_size


def _add_mesh_legend_marker(cb, data, product_info, vmin, vmax):
    """Add a marker to the legend showing current max hail estimate for MESH."""
    masked = _masked_mrms_data(data, product_info)
    if np.ma.count(masked) == 0:
        return {"line": None, "text": None}

    max_mm = float(masked.max())
    clamped = max(float(vmin), min(float(vmax), max_mm))
    max_in = max_mm / 25.4
    nws_label, nws_ref_in = _nws_hail_size_reference(max_in)

    ref_text = nws_label

    line = cb.ax.axvline(clamped, color="#ffffff", linewidth=1.3, alpha=0.95)
    text = cb.ax.text(
        clamped,
        1.12,
        f"{max_mm:.1f} mm ({max_in:.2f} in) - {ref_text}",
        transform=cb.ax.get_xaxis_transform(),
        ha="center",
        va="bottom",
        color="#ffffff",
        fontsize=9,
        fontname="Montserrat",
        fontweight="bold",
        path_effects=[PathEffects.withStroke(linewidth=2, foreground="black")],
    )
    return {"line": line, "text": text}


def _draw_mrms_value_contours(
    ax,
    data,
    metadata,
    product_info,
    cmap,
    style_config,
    zo,
):
    """Draw value contours for continuous MRMS fields when enabled."""
    lat_vals = metadata.get("latitude")
    lon_vals = metadata.get("longitude")
    if lat_vals is None or lon_vals is None:
        return []

    try:
        contour_levels = np.asarray(
            product_info.get("levels", []), dtype=float)
    except Exception:
        return []

    if contour_levels.size == 0:
        return []

    arr = np.asarray(data, dtype=float)
    if arr.ndim != 2:
        return []

    # Limit contour workload on large CONUS grids while preserving structure.
    max_dim = int(style_config.get("mesh_contour_max_dim", 1200))
    stride = max(1, int(np.ceil(max(arr.shape) / max(1, max_dim))))
    if stride > 1:
        arr = arr[::stride, ::stride]
        lat_vals = lat_vals[::stride]
        lon_vals = lon_vals[::stride]

    masked = _masked_mrms_data(arr, product_info)
    if np.ma.count(masked) == 0:
        return []

    data_min = float(masked.min())
    data_max = float(masked.max())
    levels_in_range = contour_levels[
        (contour_levels >= data_min) & (contour_levels <= data_max)
    ]
    if levels_in_range.size == 0:
        return []

    contour_width = float(style_config.get("mesh_contour_width", 1.8))
    contour_alpha = float(style_config.get("mesh_contour_alpha", 0.95))
    contour_zorder = int(style_config.get(
        "zorder_contours", zo.get("contours", 28)))

    contour_set = ax.contour(
        lon_vals,
        lat_vals,
        masked,
        levels=levels_in_range,
        cmap=cmap,
        linewidths=contour_width,
        alpha=contour_alpha,
        transform=ccrs.PlateCarree(),
        zorder=contour_zorder,
    )
    return [contour_set]


def _render_mrms_frame(
    fig,
    ax,
    data,
    metadata,
    product,
    product_info,
    file_dt,
    extent,
    show_places,
    style_config,
    zo,
    logo_file=None,
    user_tz="America/New_York",
    region_label="CONUS",
    region_code="CONUS",
):
    """
    Render a single MRMS frame onto the given axes.
    Shared between static image and animation generation.
    Matches satellite/radar styling conventions.
    """
    # Debug: Show requested extent
    print(f"[DEBUG] _render_mrms_frame: extent = {extent}")

    # --- Style config extraction ---
    show_counties = style_config.get("show_counties", False)
    county_color = style_config.get("county_color", "white")
    county_width = float(style_config.get("county_linewidth", 0.3))

    hud_left_size = int(style_config.get("hud_left_size", 14))
    hud_left_x = float(style_config.get("hud_left_x", 0.03))
    hud_left_y = float(style_config.get("hud_left_y", 0.97))

    # HUD colors
    hud_left_text_color = style_config.get("hud_left_text_color", "#ffffff")
    hud_left_bg_color = style_config.get("hud_left_bg_color", "#000000")
    hud_left_edge_color = style_config.get("hud_left_edge_color", "#555555")
    hud_left_alpha = float(style_config.get("hud_left_alpha", 0.7))

    cbar_size = float(style_config.get("cbar_size", 0.75))
    cbar_horizontal_size = float(
        style_config.get("cbar_size_horizontal", min(cbar_size, 0.35))
    )
    cbar_horizontal_fraction = float(
        style_config.get("cbar_fraction_horizontal", 0.045)
    )
    cbar_title_size = int(style_config.get("cbar_title_size", 14))

    logo_user_size = float(style_config.get("logo_user_size", 0.08))
    logo_user_x = float(style_config.get("logo_user_x", 0.98))
    logo_user_y = float(style_config.get("logo_user_y", 0.01))

    city_text_size = int(style_config.get("city_text_size", 12))

    # Base map & feature toggles
    map_bg_color = style_config.get("map_bg_color", "#000000")
    land_color = style_config.get("land_color", "#F0F0F0")
    ocean_color = style_config.get("ocean_color", "#A0C8F0")

    show_country = style_config.get("show_country", True)
    if isinstance(show_country, str):
        show_country = show_country.lower() not in ("false", "0", "no")
    country_color = style_config.get("country_color", "#ffffff")
    country_width = float(style_config.get("country_width", 1))

    show_states = style_config.get("show_states", True)
    if isinstance(show_states, str):
        show_states = show_states.lower() not in ("false", "0", "no")
    state_color = style_config.get("state_color", "#ffffff")
    state_width = float(style_config.get("state_width", 0.5))
    sel_border_color = style_config.get("sel_border_color", "#ffea00")
    sel_border_width = float(style_config.get("sel_border_width", 1.5))

    show_highways = style_config.get("show_highways", False)
    if isinstance(show_highways, str):
        show_highways = show_highways.lower() not in ("false", "0", "no")
    highway_color = style_config.get("highway_color", "#888888")
    highway_width = float(style_config.get("highway_width", 0.8))
    highway_opacity = float(style_config.get("highway_opacity", 0.6))

    show_lakes = style_config.get("show_lakes", True)
    if isinstance(show_lakes, str):
        show_lakes = show_lakes.lower() not in ("false", "0", "no")
    lake_color = style_config.get("lake_color", "#A0C8F0")
    lake_outline_color = style_config.get("lake_outline_color", "#333333")
    lake_outline_width = float(style_config.get("lake_outline_width", 0.5))

    show_rivers = style_config.get("show_rivers", False)
    if isinstance(show_rivers, str):
        show_rivers = show_rivers.lower() not in ("false", "0", "no")
    river_color = style_config.get("river_color", "#A0C8F0")
    river_width = float(style_config.get("river_width", 0.5))

    show_mesh_contours = style_config.get(
        "mesh_contours_enabled", product.startswith("MESH")
    )
    if isinstance(show_mesh_contours, str):
        show_mesh_contours = show_mesh_contours.lower() not in (
            "false",
            "0",
            "no",
            "off",
        )

    # Optional raster transparency to help contour overlays stand out.
    data_alpha = _resolve_mrms_data_alpha(style_config, product)

    # Scale factor (reference width = 12.8")
    fig_width = fig.get_figwidth()
    scale_factor = max(fig_width / 12.8, 0.55)
    hud_left_size = int(hud_left_size * scale_factor)
    city_text_size = int(city_text_size * scale_factor)
    cbar_title_size = int(cbar_title_size * scale_factor)
    logo_user_size = logo_user_size * scale_factor

    # --- Base map features ---
    ax.set_facecolor(map_bg_color)
    ax.add_feature(cfeature.OCEAN.with_scale("10m"),
                   facecolor=ocean_color, zorder=0)
    ax.add_feature(cfeature.LAND.with_scale("10m"),
                   facecolor=land_color, zorder=0)

    # Lakes (configurable)
    if show_lakes:
        ax.add_feature(
            cfeature.LAKES.with_scale("10m"),
            facecolor=lake_color,
            edgecolor=lake_outline_color,
            linewidth=lake_outline_width,
            zorder=1,
        )

    # Rivers (configurable)
    if show_rivers:
        ax.add_feature(
            cfeature.RIVERS.with_scale("10m"),
            edgecolor=river_color,
            linewidth=river_width,
            zorder=1,
        )

    # Highways (configurable)
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

    # Resolve final plotting extent, including style margin expansion.
    plot_extent = _resolve_mrms_plot_extent(extent, style_config)
    ax.set_extent(plot_extent, crs=ccrs.PlateCarree())

    (
        cmap,
        cat_norm,
        cat_boundaries,
        is_categorical,
        vmin,
        vmax,
    ) = _get_mrms_colormap_settings(product_info)

    image_artist = _plot_mrms_data_layer(
        ax,
        data,
        metadata,
        plot_extent,
        product_info,
        zo,
        cmap,
        is_categorical,
        cat_norm,
        vmin,
        vmax,
        data_alpha,
    )

    contour_artists = []
    if show_mesh_contours and product.startswith("MESH") and not is_categorical:
        contour_artists = _draw_mrms_value_contours(
            ax=ax,
            data=data,
            metadata=metadata,
            product_info=product_info,
            cmap=cmap,
            style_config=style_config,
            zo=zo,
        )

    # --- Borders & States (drawn AFTER imshow so they render on top) ---
    if show_country:
        ax.add_feature(
            cfeature.BORDERS.with_scale("10m"),
            edgecolor=country_color,
            linewidth=country_width,
            zorder=zo["borders"],
        )
    if show_states:
        ax.add_feature(
            cfeature.STATES.with_scale("10m"),
            edgecolor=state_color,
            linewidth=state_width,
            zorder=zo["borders"],
        )

    # Selected region border highlight (state or CONUS).
    try:
        selected_geom = _get_mrms_selected_region_geometry(region_code)
        if selected_geom is not None and not selected_geom.is_empty:
            sel_border_zorder = max(
                zo.get("state_border", zo["borders"] + 1), zo["borders"] + 1
            )
            ax.add_geometries(
                [selected_geom],
                ccrs.PlateCarree(),
                facecolor="none",
                edgecolor=sel_border_color,
                linewidth=sel_border_width,
                zorder=sel_border_zorder,
            )
    except Exception as e:
        print(f"[WARN] Could not draw MRMS selection border: {e}")

    # County boundaries
    if show_counties:
        census_feature = CensusCounties.get_feature()
        if census_feature:
            ax.add_feature(
                census_feature,
                edgecolor=county_color,
                linewidth=county_width,
                facecolor="none",
                zorder=zo["counties"],
            )

    # --- City labels ---
    if show_places:
        plot_cities_on_map(ax, plot_extent, style_config,
                           z_cities=zo["cities"])

    # --- Colorbar (bottom, matching radar/satellite layout) ---
    categories = product_info.get("categories")
    mesh_legend_marker = {"line": None, "text": None}
    mesh_cbar_axis = None
    if is_categorical and cat_norm is not None and categories:
        # Categorical colorbar with named tick labels
        sm = plt.cm.ScalarMappable(cmap=cmap, norm=cat_norm)
        cb = fig.colorbar(
            sm,
            ax=ax,
            orientation="horizontal",
            shrink=cbar_horizontal_size,
            fraction=cbar_horizontal_fraction,
            pad=0.05,
            ticks=[],  # clear default ticks; we set custom ones below
        )
        # Place tick at the midpoint of each boundary bin
        tick_locs = []
        tick_labels = []
        cat_keys = sorted(categories.keys())
        for i, bnd_lo in enumerate(cat_boundaries[:-1]):
            bnd_hi = cat_boundaries[i + 1]
            mid = (bnd_lo + bnd_hi) / 2.0
            # Find which category value falls in this bin
            for cv in cat_keys:
                if bnd_lo <= cv < bnd_hi:
                    tick_locs.append(mid)
                    tick_labels.append(categories[cv])
                    break
        cb.set_ticks(tick_locs)
        cb.set_ticklabels(tick_labels)
        tick_fontsize = max(7, int(cbar_title_size * 0.65))
        cb.ax.tick_params(axis="x", colors="black", labelsize=tick_fontsize)
        for tick in cb.ax.get_xticklabels():
            tick.set_fontname("Montserrat")
            tick.set_fontweight("bold")
        cb.outline.set_edgecolor("#555555")
    else:
        sm = plt.cm.ScalarMappable(
            cmap=cmap, norm=plt.Normalize(vmin=vmin, vmax=vmax))
        cb = fig.colorbar(
            sm,
            ax=ax,
            orientation="horizontal",
            shrink=cbar_horizontal_size,
            fraction=cbar_horizontal_fraction,
            pad=0.05,
        )
        if product.startswith("MESH"):
            mesh_levels = np.asarray(
                product_info.get("levels", []), dtype=float)
            mesh_levels = mesh_levels[(
                mesh_levels >= vmin) & (mesh_levels <= vmax)]
            if mesh_levels.size:
                cb.set_ticks(mesh_levels)
                cb.set_ticklabels(
                    [
                        str(int(round(v))) if float(
                            v).is_integer() else f"{v:g}"
                        for v in mesh_levels
                    ]
                )
            cb.set_label(
                "MESH Estimated Hail Size (mm)",
                color="black",
                fontsize=max(9, int(cbar_title_size * 0.85)),
            )
            mesh_legend_marker = _add_mesh_legend_marker(
                cb=cb,
                data=data,
                product_info=product_info,
                vmin=vmin,
                vmax=vmax,
            )
            mesh_cbar_axis = cb.ax
        elif product.startswith("RotationTrack"):
            rot_ticks, rot_labels = _rotation_track_legend_ticks(vmin, vmax)
            if rot_ticks.size:
                cb.set_ticks(rot_ticks)
                cb.set_ticklabels(rot_labels)
            cb.set_label(
                "Rotation Track Intensity (0.001/s)",
                color="black",
                fontsize=max(9, int(cbar_title_size * 0.8)),
            )
        cb.ax.tick_params(axis="x", colors="black", labelsize=8)
        for tick in cb.ax.get_xticklabels():
            tick.set_fontname("Montserrat")
            tick.set_fontweight("bold")
        cb.outline.set_edgecolor("#555555")

    # --- HUD Text ---
    hud_stacked = f"MRMS\n{product_info['full_name']}\n{region_label}"

    # Left HUD: Product info
    ax.annotate(
        hud_stacked,
        xy=(hud_left_x, hud_left_y),
        xycoords="axes fraction",
        fontsize=hud_left_size,
        fontname="Montserrat",
        fontweight="black",
        fontstyle="italic",
        color=hud_left_text_color,
        va="top",
        linespacing=1.15,
        bbox=dict(
            boxstyle="round,pad=0.5",
            fc=hud_left_bg_color,
            ec=hud_left_edge_color,
            alpha=hud_left_alpha,
        ),
        zorder=zo["hud"],
    )

    # Right HUD: Timestamp
    hud_right_ann = _upsert_mrms_time_hud(
        ax,
        file_dt,
        style_config,
        zo,
        user_tz=user_tz,
        hud_right_ann=None,
    )

    # --- Logo ---
    if logo_file is None:
        logo_path = style_config.get("logo_path", "img/nchurricane_logo.png")
        logo_file = os.path.join(PARENT_DIR, logo_path)

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
                    zorder=zo["logos"],
                )
            )
        except Exception as e:
            print(f"[WARN] Could not load logo: {e}")

    return {
        "image_artist": image_artist,
        "hud_right": hud_right_ann,
        "contour_artists": contour_artists,
        "mesh_legend_marker": mesh_legend_marker,
        "mesh_cbar_axis": mesh_cbar_axis,
        "mesh_vmin": vmin,
        "mesh_vmax": vmax,
    }


def _generate_mrms_static_image(
    product: str,
    product_info: dict,
    data_file: Tuple[str, datetime],
    output_dir: str,
    extent: List[float],
    proj,
    data_aspect: float,
    region_label: str,
    show_places: bool,
    style_config: dict,
    progress_callback: Optional[Callable[[str, int, int], None]],
    user_tz: str = "America/New_York",
    region_code: str = "CONUS",
) -> Tuple[str, str]:
    """Generate single static MRMS image."""

    file_path, file_dt = data_file

    if progress_callback:
        progress_callback("Reading data", 1, 2)

    # Read GRIB2 file
    try:
        plot_extent = _resolve_mrms_plot_extent(extent, style_config)
        data, metadata = read_mrms_grib2(
            file_path,
            product,
            crop_extent=plot_extent,
        )
    except Exception as e:
        return ("", f"Error reading GRIB2 file: {e}")

    if progress_callback:
        progress_callback("Rendering image", 2, 2)

    # Z-order defaults
    zo = {
        "data": 3,
        "counties": 14,
        "borders": 15,
        "state_border": 16,
        "contours": 28,
        "cities": 30,
        "hud": 100,
        "logos": 100,
    }
    if style_config:
        for k in zo:
            v = style_config.get(f"zorder_{k}")
            if v is not None:
                zo[k] = int(v)
    zo["state_border"] = max(zo["state_border"], zo["borders"] + 1)

    # Compute figure size from projected aspect ratio
    fig_height = 7.2
    left_margin = float(style_config.get("figure_left_margin", 0.02))
    right_margin = float(style_config.get("figure_right_margin", 0.02))
    top_margin = float(style_config.get("figure_top_margin", 0.02))
    bottom_margin = float(style_config.get("figure_bottom_margin", 0.08))
    ax_width = 1.0 - left_margin - right_margin
    ax_height_frac = 1.0 - top_margin - bottom_margin
    fig_width = data_aspect * (ax_height_frac / ax_width) * fig_height

    fig = plt.figure(figsize=(fig_width, fig_height), dpi=150)
    ax = fig.add_axes(
        [left_margin, bottom_margin, ax_width, ax_height_frac], projection=proj
    )
    ax.set_extent(extent, crs=ccrs.PlateCarree())

    # Render frame
    _render_mrms_frame(
        fig,
        ax,
        data,
        metadata,
        product,
        product_info,
        file_dt,
        extent,
        show_places,
        style_config,
        zo,
        user_tz=user_tz,
        region_label=region_label,
        region_code=region_code,
    )

    # Save image
    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"{date_str}_{product}.png"
    output_path = os.path.join(output_dir, output_filename)

    fig.savefig(output_path, dpi=150, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)

    return (output_path, f"Generated MRMS {product_info['short_name']} image")


def _generate_mrms_animation(
    product: str,
    product_info: dict,
    data_files: List[Tuple[str, datetime]],
    output_dir: str,
    extent: List[float],
    proj,
    data_aspect: float,
    region_label: str,
    show_places: bool,
    fps: int,
    style_config: dict,
    progress_callback: Optional[Callable[[str, int, int], None]],
    user_tz: str = "America/New_York",
    region_code: str = "CONUS",
) -> Tuple[str, str]:
    raise RuntimeError(
        "mrms._generate_mrms_animation is disabled in Phase 0. "
        "Rendering was removed from mrms_utils; use unified weather/export pipeline."
    )

    """Generate MRMS animation (MP4)."""

    if not IMAGEIO_AVAILABLE:
        return (
            "",
            "Error: imageio is required for animations. Install with: pip install imageio[ffmpeg]",
        )

    # Z-order defaults
    zo = {
        "data": 3,
        "counties": 14,
        "borders": 15,
        "state_border": 16,
        "contours": 28,
        "cities": 30,
        "hud": 100,
        "logos": 100,
    }
    if style_config:
        for k in zo:
            v = style_config.get(f"zorder_{k}")
            if v is not None:
                zo[k] = int(v)
    zo["state_border"] = max(zo["state_border"], zo["borders"] + 1)

    # Create frames directory
    frames_dir = os.path.join(output_dir, "frames")
    os.makedirs(frames_dir, exist_ok=True)

    frames = []
    total_frames = len(data_files)
    perf_decode_s = 0.0
    perf_render_s = 0.0
    perf_capture_s = 0.0

    # Compute figure size from projected aspect ratio once; reuse figure across frames.
    fig_height = 7.2
    left_margin = float(style_config.get("figure_left_margin", 0.02))
    right_margin = float(style_config.get("figure_right_margin", 0.02))
    top_margin = float(style_config.get("figure_top_margin", 0.02))
    bottom_margin = float(style_config.get("figure_bottom_margin", 0.08))
    ax_width_frac = 1.0 - left_margin - right_margin
    ax_height_frac = 1.0 - top_margin - bottom_margin
    fig_width = data_aspect * (ax_height_frac / ax_width_frac) * fig_height

    fig = plt.figure(figsize=(fig_width, fig_height), dpi=150)
    ax = fig.add_axes(
        [left_margin, bottom_margin, ax_width_frac, ax_height_frac],
        projection=proj,
    )
    plot_extent = _resolve_mrms_plot_extent(extent, style_config)
    ax.set_extent(plot_extent, crs=ccrs.PlateCarree())
    ax.set_facecolor("black")

    (
        cmap,
        cat_norm,
        _cat_boundaries,
        is_categorical,
        vmin,
        vmax,
    ) = _get_mrms_colormap_settings(product_info)

    image_artist = None
    hud_right_ann = None
    contour_artists = []
    mesh_legend_marker = {"line": None, "text": None}
    mesh_cbar_axis = None
    mesh_vmin = 0.0
    mesh_vmax = 1.0
    static_overlays_ready = False
    grid_crop_slices = None
    tight_crop_px = None
    show_mesh_contours = style_config.get(
        "mesh_contours_enabled", product.startswith("MESH")
    )
    if isinstance(show_mesh_contours, str):
        show_mesh_contours = show_mesh_contours.lower() not in (
            "false",
            "0",
            "no",
            "off",
        )

    data_alpha = _resolve_mrms_data_alpha(style_config, product)

    # Generate individual frames
    for idx, (file_path, file_dt) in enumerate(data_files):
        if progress_callback:
            progress_callback("Rendering frames", idx + 1, total_frames)

        try:
            _frame_t0 = _time.perf_counter()

            # Read GRIB2 file
            _decode_t0 = _time.perf_counter()
            data, metadata = read_mrms_grib2(
                file_path,
                product,
                crop_extent=plot_extent,
                crop_slices=grid_crop_slices,
            )
            decode_elapsed = _time.perf_counter() - _decode_t0
            perf_decode_s += decode_elapsed

            if grid_crop_slices is None:
                grid_crop_slices = metadata.get("crop_slices")

            # Validate coordinates
            lon = metadata.get("longitude")
            lat = metadata.get("latitude")

            if lat is None or lon is None:
                raise ValueError(
                    f"Missing coordinates - lat: {lat is not None}, lon: {lon is not None}"
                )

            if lat.size == 0 or lon.size == 0:
                raise ValueError(
                    f"Empty coordinates - lat shape: {lat.shape}, lon shape: {lon.shape}"
                )

            print(
                f"[DEBUG] Frame {idx}: lat shape={lat.shape}, lon shape={lon.shape}, data shape={data.shape}"
            )

            _render_t0 = _time.perf_counter()
            if not static_overlays_ready:
                # First frame: draw full composition once (base map, cities, borders,
                # colorbar, left HUD, logo), then only update data + time for next frames.
                render_state = _render_mrms_frame(
                    fig,
                    ax,
                    data,
                    metadata,
                    product,
                    product_info,
                    file_dt,
                    extent,
                    show_places,
                    style_config,
                    zo,
                    user_tz=user_tz,
                    region_label=region_label,
                    region_code=region_code,
                )
                image_artist = render_state.get("image_artist")
                hud_right_ann = render_state.get("hud_right")
                contour_artists = render_state.get("contour_artists", [])
                mesh_legend_marker = render_state.get(
                    "mesh_legend_marker", {"line": None, "text": None}
                )
                mesh_cbar_axis = render_state.get("mesh_cbar_axis")
                mesh_vmin = float(render_state.get("mesh_vmin", vmin))
                mesh_vmax = float(render_state.get("mesh_vmax", vmax))
                static_overlays_ready = True
            else:
                # Remove only the previous MRMS raster layer, keep static overlays intact.
                if image_artist is not None:
                    try:
                        image_artist.remove()
                    except Exception:
                        pass

                # Safety cleanup: avoid stacked raster layers if a previous remove() failed.
                if ax.images:
                    for img_artist in list(ax.images):
                        try:
                            img_artist.remove()
                        except Exception:
                            pass

                if contour_artists:
                    for artist in contour_artists:
                        try:
                            artist.remove()
                        except Exception:
                            pass
                    contour_artists = []

                for marker_part in (
                    mesh_legend_marker.get("line"),
                    mesh_legend_marker.get("text"),
                ):
                    if marker_part is not None:
                        try:
                            marker_part.remove()
                        except Exception:
                            pass
                mesh_legend_marker = {"line": None, "text": None}

                image_artist = _plot_mrms_data_layer(
                    ax,
                    data,
                    metadata,
                    plot_extent,
                    product_info,
                    zo,
                    cmap,
                    is_categorical,
                    cat_norm,
                    vmin,
                    vmax,
                    data_alpha,
                )

                if (
                    show_mesh_contours
                    and product.startswith("MESH")
                    and not is_categorical
                ):
                    contour_artists = _draw_mrms_value_contours(
                        ax=ax,
                        data=data,
                        metadata=metadata,
                        product_info=product_info,
                        cmap=cmap,
                        style_config=style_config,
                        zo=zo,
                    )

                if product.startswith("MESH") and mesh_cbar_axis is not None:

                    class _CBProxy:
                        pass

                    cb_proxy = _CBProxy()
                    cb_proxy.ax = mesh_cbar_axis
                    mesh_legend_marker = _add_mesh_legend_marker(
                        cb=cb_proxy,
                        data=data,
                        product_info=product_info,
                        vmin=mesh_vmin,
                        vmax=mesh_vmax,
                    )

                hud_right_ann = _upsert_mrms_time_hud(
                    ax,
                    file_dt,
                    style_config,
                    zo,
                    user_tz=user_tz,
                    hud_right_ann=hud_right_ann,
                )
            render_elapsed = _time.perf_counter() - _render_t0
            perf_render_s += render_elapsed

            # Capture frame directly from Agg canvas to avoid PNG encode/decode overhead.
            _capture_t0 = _time.perf_counter()
            fig.canvas.draw()
            frame_rgba = np.asarray(fig.canvas.buffer_rgba())

            # Match prior savefig(bbox_inches="tight") framing once, then reuse.
            if tight_crop_px is None:
                try:
                    renderer = fig.canvas.get_renderer()
                    tight_bbox = fig.get_tightbbox(renderer)
                    if tight_bbox is not None:
                        pad_inches = max(
                            float(matplotlib.rcParams.get(
                                "savefig.pad_inches", 0.1)),
                            0.15,
                        )
                        tight_bbox = tight_bbox.padded(pad_inches)
                        tight_bbox_px = tight_bbox.transformed(
                            fig.dpi_scale_trans)
                        canvas_h = int(frame_rgba.shape[0])
                        x0 = max(0, int(np.floor(tight_bbox_px.x0)))
                        x1 = min(frame_rgba.shape[1], int(
                            np.ceil(tight_bbox_px.x1)))
                        y0_bbox = max(0, int(np.floor(tight_bbox_px.y0)))
                        y1_bbox = min(canvas_h, int(np.ceil(tight_bbox_px.y1)))

                        # Convert from Matplotlib bbox space (origin at bottom-left)
                        # to NumPy image rows (origin at top-left).
                        y0 = max(0, canvas_h - y1_bbox)
                        y1 = min(canvas_h, canvas_h - y0_bbox)
                        if x1 > x0 and y1 > y0:
                            tight_crop_px = (x0, x1, y0, y1)
                            print(
                                f"[DEBUG] MRMS tight frame crop set: x=({x0},{x1}) y=({y0},{y1})"
                            )
                except Exception as crop_err:
                    print(
                        f"[WARN] Failed to compute MRMS tight crop: {crop_err}")

            if tight_crop_px is not None:
                x0, x1, y0, y1 = tight_crop_px
                frame_rgb = frame_rgba[y0:y1, x0:x1, :3]
            else:
                frame_rgb = frame_rgba[:, :, :3]

            frame_data = np.ascontiguousarray(frame_rgb.copy())
            frames.append(frame_data)

            # Save PNG for last frame only (used as preview)
            if idx == total_frames - 1:
                frame_path = os.path.join(frames_dir, f"f_{idx:03d}.png")
                plt.imsave(frame_path, frame_data)

            _capture_elapsed = _time.perf_counter() - _capture_t0
            perf_capture_s += _capture_elapsed
            _frame_elapsed = _time.perf_counter() - _frame_t0
            print(
                f"[Perf] MRMS frame {idx + 1}/{total_frames}: total={_frame_elapsed:.2f}s "
                f"decode={decode_elapsed:.2f}s render={render_elapsed:.2f}s "
                f"capture={_capture_elapsed:.2f}s {'(setup)' if idx == 0 else '(update)'}"
            )

        except Exception as e:
            print(f"Error rendering frame {idx}: {e}")
            import traceback

            traceback.print_exc()
            continue

    plt.close(fig)

    if not frames:
        return ("", "Failed to render any frames")

    # Create MP4 animation
    if progress_callback:
        progress_callback("Creating animation", 1, 1)

    datecode = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"{datecode}_{product}_animation.mp4"
    output_path = os.path.join(output_dir, output_filename)

    try:
        from video_utils import save_animation

        _encode_t0 = _time.perf_counter()
        save_animation(output_path, frames, fps=fps)
        perf_encode_s = _time.perf_counter() - _encode_t0

        frame_count = max(len(frames), 1)
        print(
            f"[Perf] MRMS summary: frames={len(frames)} "
            f"decode_total={perf_decode_s:.2f}s render_total={perf_render_s:.2f}s "
            f"capture_total={perf_capture_s:.2f}s encode_total={perf_encode_s:.2f}s "
            f"decode_avg={perf_decode_s / frame_count:.2f}s render_avg={perf_render_s / frame_count:.2f}s "
            f"capture_avg={perf_capture_s / frame_count:.2f}s"
        )

        return (
            output_path,
            f"Generated MRMS {product_info['short_name']} animation with {len(frames)} frames",
        )

    except Exception as e:
        return ("", f"Error creating animation: {e}")
