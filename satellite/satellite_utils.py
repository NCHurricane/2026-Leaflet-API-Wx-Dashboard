from config.satellite_config import ABI_CHANNELS, RGB_COMPOSITE_KEYS
from config.style_config import resolve_satellite_style_config

try:
    from config.satellite_colormaps import IR_CMAP, IR_NORM
except ImportError:
    from config.satellite_colormaps import IR_CMAP, IR_NORM
from font_utils import register_montserrat_fonts
import os
import glob
import json
import re
import time as _time
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timezone, timedelta
from dateutil import tz
import imageio.v2 as imageio
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from siphon.catalog import TDSCatalog
import xarray as xr
from scipy.ndimage import zoom as _ndimage_zoom
import matplotlib
import matplotlib.image as mpimg
from matplotlib.offsetbox import AnnotationBbox, OffsetImage
import matplotlib.patheffects as PathEffects
import io
import pyproj

from listing_cache import cached_call
from geo_utils import CensusCounties  # Consolidated county shapefile class

matplotlib.use("Agg")

# Ensure all Montserrat weights are available to Matplotlib.
register_montserrat_fonts()


_GEOCOLOR_NIGHT_BG_CACHE = {}


# =============================================================================
# CENSUS COUNTIES SHAPEFILE SUPPORT — imported from geo_utils
# =============================================================================
# CensusCounties is imported at the top of this file from geo_utils.
# Consumers that import `from satellite_utils import CensusCounties` will
# continue to work via the re-export.


def parse_goes_time_from_filename(filename):
    """
    Extract UTC time from a GOES ABI L2 filename.
    Filename format: OR_ABI-L2-CMIPC-M6C13_G19_s20260410001170_e...
    The 's20260410001170' part encodes the scan start time as YYYYJJJHHMMSSff (year, Julian day, hour, minute, second, fractional seconds).
    Returns a timezone-aware UTC datetime object or None if parsing fails.
    """
    match = re.search(r"_s(\d{14})", filename)
    if not match:
        return None
    time_str = match.group(1)  # e.g., "20260410001170"
    try:
        # First 12 chars: YYYYJJJHHMMSS, last 2 chars: fractional seconds
        dt_obj = datetime.strptime(time_str[:12], "%Y%j%H%M%S")
        return dt_obj.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _date_partition_dir(base_dir, dt_obj):
    dt_utc = (
        dt_obj.replace(tzinfo=timezone.utc)
        if isinstance(dt_obj, datetime) and dt_obj.tzinfo is None
        else dt_obj.astimezone(timezone.utc)
        if isinstance(dt_obj, datetime)
        else datetime.now(timezone.utc)
    )
    return os.path.join(
        base_dir,
        dt_utc.strftime("%Y"),
        dt_utc.strftime("%m"),
        dt_utc.strftime("%d"),
    )


def get_cmi_var(ds):
    """
    Return the correct variable name for the CMI (Cloud and Moisture Imagery) data in a dataset.
    Handles both standard and sectorized variable names.
    Raises KeyError if neither is found.
    """
    if "CMI" in ds.variables:
        return "CMI"
    elif "Sectorized_CMI" in ds.variables:
        return "Sectorized_CMI"
    raise KeyError(f"Could not find 'CMI'. Found: {list(ds.variables)}")


def _get_catalog_datasets_cached(catalog_url):
    """
    Retrieve and cache the list of datasets from a THREDDS catalog URL.
    Uses a short TTL (20s) to avoid repeated network requests for the same catalog.
    Returns a dict of dataset names to dataset objects.
    """

    def _fetch():
        catalog = TDSCatalog(catalog_url)
        sorted_keys = sorted(catalog.datasets.keys())
        return {name: catalog.datasets[name] for name in sorted_keys}

    return cached_call(
        namespace="satellite_thredds_catalog",
        key=catalog_url,
        fetch_fn=_fetch,
        ttl_seconds=20,
    )


def get_goes_data(sat_id, sector, channel_key, lookback_hours=2):
    """
    Query the UCAR THREDDS server for recent GOES satellite data files.
    Returns a dict mapping channel names to dicts of filename:dataset for the requested lookback period.
    Handles sector naming, channel requirements, and fallback to previous day if needed.
    """
    sat_num = "".join(filter(str.isdigit, str(sat_id)))
    base_url = f"https://thredds.ucar.edu/thredds/catalog/satellite/goes/{sat_num}/products/CloudAndMoistureImagery/"

    sector_raw = str(sector or "CONUS").strip()
    sector_slug = sector_raw.lower().replace(
        " ", "").replace("_", "").replace("-", "")
    if sector_slug == "fulldisk":
        sector = "Full Disk"
    elif sector_slug in ("meso1", "mesoscale1"):
        sector = "Meso1"
    elif sector_slug in ("meso2", "mesoscale2"):
        sector = "Meso2"
    else:
        sector = "CONUS" if sector_slug == "conus" else sector_raw

    sector_path = {
        "CONUS": "CONUS",
        "Full Disk": "FullDisk",
        "Meso1": "Mesoscale-1",
        "Meso2": "Mesoscale-2",
    }.get(sector, "CONUS")

    channels_to_fetch = ABI_CHANNELS[channel_key].get("req", [channel_key])
    results = {}

    if "meso" in sector.lower():
        scans_per_hr = 60
    elif "conus" in sector.lower():
        scans_per_hr = 12
    else:
        scans_per_hr = 6
    total_needed = int(lookback_hours * scans_per_hr)

    current_time = datetime.now(timezone.utc)

    for ch in channels_to_fetch:
        day1_str = current_time.strftime("%Y%m%d")
        cat_url_1 = f"{base_url}{sector_path}/{ch}/{day1_str}/catalog.xml"
        files_found = {}

        try:
            datasets_today = _get_catalog_datasets_cached(cat_url_1)
            for name, dataset in datasets_today.items():
                files_found[name] = dataset
        except Exception as e:
            print(
                f"Warning: Could not check today's catalog ({day1_str}): {e}")

        if len(files_found) < total_needed:
            needed_from_yesterday = total_needed - len(files_found)
            yesterday_time = current_time - timedelta(days=1)
            day2_str = yesterday_time.strftime("%Y%m%d")
            cat_url_2 = f"{base_url}{sector_path}/{ch}/{day2_str}/catalog.xml"

            try:
                datasets_yesterday = _get_catalog_datasets_cached(cat_url_2)
                yesterday_keys = sorted(datasets_yesterday.keys())
                for name in yesterday_keys[-needed_from_yesterday:]:
                    files_found[name] = datasets_yesterday[name]
            except Exception as e:
                print(
                    f"Warning: Could not check yesterday's catalog ({day2_str}): {e}")

        sorted_keys = sorted(files_found.keys())
        final_selection = {k: files_found[k]
                           for k in sorted_keys[-total_needed:]}
        results[ch] = final_selection

    return results


def download_goes_data(
    sat_id,
    sector,
    channel_key,
    lookback_hours,
    base_dir,
    progress_callback=None,
    latest_only=False,
):
    """
    Download recent GOES satellite data files for the specified satellite, sector, and channel.
    Uses get_goes_data to find files, then downloads any missing files to the local directory.
    Returns the save root, total files found, and number of new downloads.
    """
    data_map = get_goes_data(sat_id, sector, channel_key, lookback_hours)

    if latest_only:
        filtered_map = {}
        for channel, datasets in data_map.items():
            if not datasets:
                filtered_map[channel] = {}
                continue
            latest_name = sorted(datasets.keys())[-1]
            filtered_map[channel] = {latest_name: datasets[latest_name]}
        data_map = filtered_map

    total_found = sum(len(datasets) for datasets in data_map.values())

    if total_found == 0:
        print(
            f"[ERROR] No satellite data found for {sat_id} {sector} {channel_key} in the last {lookback_hours} hours"
        )
        return None, 0, 0

    save_root = os.path.join(base_dir, "satellite_downloads", sat_id, sector)
    os.makedirs(save_root, exist_ok=True)
    download_count = 0
    processed_count = 0

    for ch, datasets in data_map.items():
        ch_root = os.path.join(save_root, ch)
        os.makedirs(ch_root, exist_ok=True)

        for name, ds in datasets.items():
            processed_count += 1
            if progress_callback:
                progress_callback(processed_count, total_found)

            scan_time = parse_goes_time_from_filename(name)
            day_dir = _date_partition_dir(
                ch_root, scan_time or datetime.now(timezone.utc)
            )
            os.makedirs(day_dir, exist_ok=True)
            path = os.path.join(day_dir, name)
            if not os.path.exists(path):
                try:
                    ds.download(path)
                    download_count += 1
                except Exception:
                    pass
    return save_root, total_found, download_count


def normalize_data(da, apply_gamma=False, gamma_value=1 / 2.2):
    """
    Normalize a DataArray to the range [0, 1].
    Optionally applies gamma correction.
    Handles both reflectance (0-1) and scaled (0-100) data.
    """
    data_max = da.max().values
    if data_max > 1.5:
        da = da / 100.0
    da = np.clip(da, 0, 1)
    if apply_gamma:
        return np.power(da, gamma_value)
    return da


def normalize(value, lower_limit, upper_limit, clip=True):
    """Contrast-stretch *value* into the 0-1 range.

    Follows the `goes2go` / CIRA normalization convention::

        normalized = (value - lower_limit) / (upper_limit - lower_limit)

    Parameters
    ----------
    value : array-like
        Original values (scalar, vector, or 2-D array).
    lower_limit : float
        Value that maps to 0.
    upper_limit : float
        Value that maps to 1.
    clip : bool, optional
        If *True* (default), clip the result to [0, 1].
    """
    norm = (value - lower_limit) / (upper_limit - lower_limit)
    if clip:
        norm = np.clip(norm, 0, 1)
    return norm


def gamma_correction(a, gamma):
    """Apply `gamma correction <https://en.wikipedia.org/wiki/Gamma_correction>`_.

    Parameters
    ----------
    a : array-like
        Input values (typically 0-1 after normalization).
    gamma : float
        Gamma > 1 lightens the image; gamma < 1 darkens it.
    """
    if gamma == 1:
        return a
    return np.power(a, 1 / gamma)


def satpy_visible_reflectance(da):
    """
    Satpy-like enhancement for visible reflectance channels.
    Stretches reflectance to [0, 1] and applies a gamma curve for visual realism.
    Equivalent intent: stretch 0-100 reflectance to 0-1 then apply gamma 1.5.
    """
    gamma_value = 1 / 2
    return normalize_data(da, apply_gamma=True, gamma_value=gamma_value)


def _resample_to_match(source_da, target_da):
    """
    Fast grid resampling for GOES ABI fixed-grid data.
    Replaces xarray's interp_like with scipy.ndimage.zoom, which is
    dramatically faster for regular grids (skips coordinate parsing overhead).
    Returns a float32 numpy array matching target_da's 2-D shape.
    """
    src = np.asarray(source_da, dtype=np.float32)
    tgt_shape = (target_da.shape[0], target_da.shape[1])
    if src.shape == tgt_shape:
        return src
    zy = tgt_shape[0] / src.shape[0]
    zx = tgt_shape[1] / src.shape[1]
    return _ndimage_zoom(src, (zy, zx), order=1, mode="nearest").astype(np.float32)


def _compute_downscale_factor(da_shape, max_size):
    """Return a float scale factor (<=1.0) so neither dimension exceeds *max_size*."""
    if max_size is None or max_size <= 0:
        return 1.0
    return min(1.0, max_size / max(da_shape[0], da_shape[1]))


def _downscale_array(arr, scale):
    """Downsample a 2-D or 3-D numpy array by *scale* using bilinear zoom."""
    if scale >= 1.0:
        return arr
    if arr.ndim == 2:
        return _ndimage_zoom(arr, scale, order=1, mode="nearest").astype(arr.dtype)
    # 3-D: scale spatial dims only
    return _ndimage_zoom(arr, (scale, scale, 1), order=1, mode="nearest").astype(
        arr.dtype
    )


def build_true_color_rgb(ch_data, max_size=None):
    """
    Build a simulated true color RGB image from GOES ABI channels.
    Uses Satpy's simulated green logic (mix of red, blue, and veggie channels).
    If *max_size* is given, the working resolution is capped at that many pixels
    on the longest side (saves huge time for composites destined for ≤1280 px output).
    Returns (rgb_image, red_reflectance_da, scale_factor).
    """
    r_full = satpy_visible_reflectance(
        _get_cmi_dataarray(ch_data["Channel02"]))
    scale = _compute_downscale_factor(r_full.shape, max_size)
    r_np = _downscale_array(np.array(r_full, dtype=np.float32), scale)
    _tgt = type("S", (), {"shape": r_np.shape})()

    # Resample Ch01/Ch03 directly to the (possibly downscaled) target shape
    b = _resample_to_match(
        np.array(
            satpy_visible_reflectance(
                _get_cmi_dataarray(ch_data["Channel01"])),
            dtype=np.float32,
        ),
        _tgt,
    )
    v = _resample_to_match(
        np.array(
            satpy_visible_reflectance(
                _get_cmi_dataarray(ch_data["Channel03"])),
            dtype=np.float32,
        ),
        _tgt,
    )

    # Satpy ABI uses simulated green family for true color composites.
    g = np.clip(0.45 * r_np + 0.1 * v + 0.45 * b, 0, 1)
    rgb = np.dstack([r_np, g, b])
    return rgb, r_full, scale


def build_geocolor_rgba(ch_data, max_size=None):
    """
    Compose a Satpy-inspired GEOColor RGBA image (day/night blend).
    - Day: True Color composite
    - Night: Synthetic blue background with cloud enhancement (high/low cloud detection)
    - Blending: Uses red reflectance as a proxy for solar zenith angle
    Returns a float32 RGBA array.
    """
    day_rgb, _red_ref_da, scale = build_true_color_rgb(
        ch_data, max_size=max_size)
    red_ref = day_rgb[:, :, 0]  # red channel at working resolution
    _tgt = type("S", (), {"shape": red_ref.shape})()

    bt13 = _resample_to_match(
        _downscale_array(
            _get_cmi_dataarray(ch_data["Channel13"]).values.astype(
                np.float32), scale
        ),
        _tgt,
    )
    if "Channel07" in ch_data:
        bt07 = _resample_to_match(
            _downscale_array(
                _get_cmi_dataarray(
                    ch_data["Channel07"]).values.astype(np.float32),
                scale,
            ),
            _tgt,
        )
    else:
        bt07 = bt13

    high_cloud = normalize(bt13, 273.15, 193.15)  # cold = 1, warm = 0
    split_window = bt13 - bt07
    low_cloud = normalize(split_window, 1.0, 8.0)

    # Night background approximation (deep blue with colder cloud emphasis).
    night_rgb = np.zeros((*bt13.shape, 3), dtype=np.float32)
    night_rgb[:, :, 0] = 0.03
    night_rgb[:, :, 1] = 0.05
    night_rgb[:, :, 2] = 0.10

    NIGHT_BG_OPACITY = 0.5  # <-- Set your fixed opacity here (0.0 to 1.0)
    night_rgb *= NIGHT_BG_OPACITY

    cold_boost = normalize(bt13, 260.0, 200.0)  # cold = 1, warm = 0
    night_rgb[:, :, 2] += 0.12 * cold_boost

    # Low clouds: cyan tint, High clouds: white enhancement.
    night_rgb[:, :, 0] += 0.30 * low_cloud
    night_rgb[:, :, 1] += 0.45 * low_cloud
    night_rgb[:, :, 2] += 0.55 * low_cloud
    for channel in range(3):
        night_rgb[:, :, channel] += 1.3 * high_cloud
    night_rgb = np.clip(night_rgb, 0.0, 1.0)

    # Day-night blend proxy (Satpy uses solar-zenith based blending).
    day_weight = np.clip((red_ref - 0.05) / 0.15, 0.0, 1.0)
    blended = day_rgb * day_weight[:, :, np.newaxis] + night_rgb * (
        1.0 - day_weight[:, :, np.newaxis]
    )

    result = np.zeros((*red_ref.shape, 4), dtype=np.float32)
    result[:, :, :3] = np.clip(blended, 0.0, 1.0)
    result[:, :, 3] = 1.0
    return result


def _load_geocolor_night_background(
    target_da,
    night_bg_lon_offset=0.0,
    night_bg_lat_offset=0.0,
    night_bg_zoom=100.0,
    night_bg_source_pref="tiff_first",
):
    """
    Load and project a static night background image (Black Marble or synthetic fallback) to match the satellite grid.
    - Attempts to load JPG, PNG, or TIFF backgrounds in priority order.
    - If geographic bounds are available, reprojects the image to match the satellite grid.
    - Applies optional longitude/latitude offset and zoom.
    - Caches the result for performance.
    - Returns a float32 RGB image aligned to the target grid.

    Args:
        target_da: xarray DataArray with coordinate info (lat/lon or x/y projection coords)

    Returns:
        RGB float32 array aligned to target_da's grid
    """
    height, width = target_da.shape

    # Extract lat/lon bounds via pyproj transform from geostationary x/y
    lat_min = lat_max = lon_min = lon_max = None
    try:
        if hasattr(target_da, "metpy"):
            crs = target_da.metpy.cartopy_crs
            geo_proj = pyproj.CRS(crs.proj4_init)
            wgs84 = pyproj.CRS("EPSG:4326")
            transformer = pyproj.Transformer.from_crs(
                geo_proj, wgs84, always_xy=True)

            xmin_m, xmax_m = float(target_da.x.min()), float(target_da.x.max())
            ymin_m, ymax_m = float(target_da.y.min()), float(target_da.y.max())
            mid_x = (xmin_m + xmax_m) / 2
            mid_y = (ymin_m + ymax_m) / 2

            corners_x = np.array(
                [xmin_m, xmax_m, xmin_m, xmax_m, mid_x, mid_x, xmin_m, xmax_m]
            )
            corners_y = np.array(
                [ymin_m, ymin_m, ymax_m, ymax_m, ymin_m, ymax_m, mid_y, mid_y]
            )
            lons_c, lats_c = transformer.transform(corners_x, corners_y)
            valid = np.isfinite(lats_c) & np.isfinite(lons_c)

            if valid.any():
                lat_min, lat_max = (
                    float(np.min(lats_c[valid])),
                    float(np.max(lats_c[valid])),
                )
                lon_min, lon_max = (
                    float(np.min(lons_c[valid])),
                    float(np.max(lons_c[valid])),
                )
                cache_key = (
                    int(height),
                    int(width),
                    round(lat_min, 2),
                    round(lat_max, 2),
                    round(lon_min, 2),
                    round(lon_max, 2),
                    round(float(night_bg_lon_offset), 2),
                    round(float(night_bg_lat_offset), 2),
                    round(float(night_bg_zoom), 2),
                    str(night_bg_source_pref or "tiff_first").strip().lower(),
                )
            else:
                cache_key = (
                    int(height),
                    int(width),
                    round(float(night_bg_lon_offset), 2),
                    round(float(night_bg_lat_offset), 2),
                    round(float(night_bg_zoom), 2),
                    str(night_bg_source_pref or "tiff_first").strip().lower(),
                )
        else:
            cache_key = (
                int(height),
                int(width),
                round(float(night_bg_lon_offset), 2),
                round(float(night_bg_lat_offset), 2),
                round(float(night_bg_zoom), 2),
                str(night_bg_source_pref or "tiff_first").strip().lower(),
            )
    except Exception:
        cache_key = (
            int(height),
            int(width),
            round(float(night_bg_lon_offset), 2),
            round(float(night_bg_lat_offset), 2),
            round(float(night_bg_zoom), 2),
            str(night_bg_source_pref or "tiff_first").strip().lower(),
        )
        lat_min = lat_max = lon_min = lon_max = None

    cached_img = _GEOCOLOR_NIGHT_BG_CACHE.get(cache_key)
    if cached_img is not None:
        return cached_img

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # New priority: jpg (default), png (fallback), tiff (final fallback)
    png_candidates = [
        os.path.join(base_dir, "img", "BlackMarble_2016_3km_geo.png"),
    ]
    jpg_candidates = [
        os.path.join(base_dir, "img", "BlackMarble_2016_3km_blue_sm.jpg"),
    ]
    tiff_candidates = [
        os.path.join(base_dir, "img", "BlackMarble_2016_3km_geo.tif"),
        os.path.join(base_dir, "img", "BlackMarble_2016_01deg_geo.tif"),
        os.path.join(base_dir, "data", "BlackMarble_2016_3km_geo.tif"),
        os.path.join(base_dir, "data", "BlackMarble_2016_01deg_geo.tif"),
    ]
    # Always try png first, then jpg, then tiff
    candidates = tiff_candidates + png_candidates + jpg_candidates

    for path in candidates:
        if os.path.exists(path):
            try:
                ext = os.path.splitext(path)[1].lower()
                if ext in (".tif", ".tiff"):
                    img = imageio.imread(path)
                else:
                    img = mpimg.imread(path)

                img = np.asarray(img).astype(np.float32)
                if img.ndim == 2:
                    img = np.dstack([img, img, img])
                if img.shape[2] > 3:
                    img = img[:, :, :3]

                src_h, src_w = img.shape[:2]
                # If we have geographic bounds, do proper geo-registration
                if (
                    lat_min is not None
                    and np.isfinite([lat_min, lat_max, lon_min, lon_max]).all()
                ):
                    if img.max() > 1.5:
                        img = img / 255.0

                    x_vals = np.asarray(target_da.x.values, dtype=np.float64)
                    y_vals = np.asarray(target_da.y.values, dtype=np.float64)

                    finite_xy = np.isfinite(
                        x_vals).all() and np.isfinite(y_vals).all()
                    if finite_xy:
                        max_abs_xy = max(
                            float(np.max(np.abs(x_vals))), float(
                                np.max(np.abs(y_vals)))
                        )
                        if max_abs_xy < 20.0:
                            try:
                                proj_params = (
                                    getattr(
                                        target_da.metpy.cartopy_crs, "proj4_params", {}
                                    )
                                    or {}
                                )
                                sat_h = proj_params.get("h")
                                if sat_h is None:
                                    sat_h = proj_params.get("satellite_height")
                                sat_h = float(
                                    sat_h) if sat_h is not None else None
                                if (
                                    sat_h is not None
                                    and np.isfinite(sat_h)
                                    and sat_h > 0
                                ):
                                    x_vals = x_vals * sat_h
                                    y_vals = y_vals * sat_h
                            except Exception:
                                pass

                    x_grid, y_grid = np.meshgrid(x_vals, y_vals)

                    crs = target_da.metpy.cartopy_crs
                    geo_proj = pyproj.CRS(crs.proj4_init)
                    wgs84 = pyproj.CRS("EPSG:4326")
                    transformer = pyproj.Transformer.from_crs(
                        geo_proj, wgs84, always_xy=True
                    )
                    lon_grid, lat_grid = transformer.transform(x_grid, y_grid)

                    valid = np.isfinite(lon_grid) & np.isfinite(lat_grid)
                    if valid.any():
                        center_lon = float(np.mean(lon_grid[valid]))
                        center_lat = float(np.mean(lat_grid[valid]))
                    else:
                        center_lon = 0.0
                        center_lat = 0.0

                    zoom_factor = max(float(night_bg_zoom), 1.0) / 100.0
                    lon_adj = ((lon_grid - center_lon) /
                               zoom_factor) + center_lon
                    lat_adj = ((lat_grid - center_lat) /
                               zoom_factor) + center_lat
                    lon_adj = lon_adj + float(night_bg_lon_offset)
                    lat_adj = lat_adj + float(night_bg_lat_offset)

                    lon_adj = ((lon_adj + 180.0) % 360.0) - 180.0
                    lat_adj = np.clip(lat_adj, -90.0, 90.0)

                    # Map lon/lat to source image pixel space (global georeferenced image).
                    col_f = ((lon_adj + 180.0) / 360.0) * (src_w - 1)
                    row_f = ((90.0 - lat_adj) / 180.0) * (src_h - 1)

                    valid = valid & np.isfinite(col_f) & np.isfinite(row_f)
                    col_f = np.clip(col_f, 0.0, src_w - 1.0)
                    row_f = np.clip(row_f, 0.0, src_h - 1.0)

                    # Guard invalid projected pixels (NaN/Inf) from int-cast underflow.
                    col_f_safe = np.where(valid, col_f, 0.0)
                    row_f_safe = np.where(valid, row_f, 0.0)

                    row0 = np.floor(row_f_safe).astype(np.int32)
                    col0 = np.floor(col_f_safe).astype(np.int32)
                    row1 = np.clip(row0 + 1, 0, src_h - 1)
                    col1 = np.clip(col0 + 1, 0, src_w - 1)

                    dr = (row_f_safe - row0).astype(np.float32)
                    dc = (col_f_safe - col0).astype(np.float32)

                    out = np.zeros((height, width, 3), dtype=np.float32)
                    for ch in range(3):
                        v00 = img[row0, col0, ch]
                        v01 = img[row0, col1, ch]
                        v10 = img[row1, col0, ch]
                        v11 = img[row1, col1, ch]
                        out[:, :, ch] = (
                            (1.0 - dr) * (1.0 - dc) * v00
                            + (1.0 - dr) * dc * v01
                            + dr * (1.0 - dc) * v10
                            + dr * dc * v11
                        )

                    if not valid.all():
                        out[~valid] = 0.0

                    img = out
                else:
                    # Simple resize for non-georeferenced images
                    if src_h != height or src_w != width:
                        y_idx = np.linspace(
                            0, src_h - 1, height).astype(np.int32)
                        x_idx = np.linspace(
                            0, src_w - 1, width).astype(np.int32)
                        img = img[y_idx][:, x_idx]

                if img.max() > 1.5:
                    img = img / 255.0
                final_img = np.clip(img, 0.0, 1.0)
                _GEOCOLOR_NIGHT_BG_CACHE[cache_key] = final_img
                return final_img
            except Exception:
                pass

    # Synthetic fallback
    y = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, np.newaxis]
    x = np.linspace(0.0, 1.0, width, dtype=np.float32)[np.newaxis, :]
    bg = np.zeros((height, width, 3), dtype=np.float32)
    bg[:, :, 0] = 0.02 + 0.04 * (1.0 - y)
    bg[:, :, 1] = 0.03 + 0.05 * (1.0 - y)
    bg[:, :, 2] = 0.06 + 0.10 * (1.0 - y)
    city = np.clip(np.sin(40 * x) * np.sin(28 * y), 0.0, 1.0)
    bg[:, :, 0] += 0.08 * city
    bg[:, :, 1] += 0.07 * city
    bg[:, :, 2] += 0.03 * city
    final_bg = np.clip(bg, 0.0, 1.0)
    _GEOCOLOR_NIGHT_BG_CACHE[cache_key] = final_bg
    return final_bg


def build_geocolor_satpy_option_rgba(
    ch_data,
    night_bg_lon_offset=0.0,
    night_bg_lat_offset=0.0,
    night_bg_zoom=100.0,
    night_bg_source_pref="tiff_first",
    preloaded_night_bg=None,
    max_size=None,
):
    """
    Compose a Satpy-style GEOColor RGBA image using a real night background (Black Marble).
    - Day: True Color composite
    - Night: Black Marble background with cloud enhancement (high/low cloud detection)
    - Blending: Uses Satpy's lim_low/lim_high logic for day/night transition
    - Applies gamma and opacity to night background for realism
    If *max_size* is given, compositing is done at reduced resolution (huge speedup).
    Returns a float32 RGBA array.
    """
    _t_comp_start = _time.perf_counter()
    day_rgb, _red_ref_da, scale = build_true_color_rgb(
        ch_data, max_size=max_size)
    red_ref = day_rgb[:, :, 0]  # red channel at working resolution
    _tgt = type("S", (), {"shape": red_ref.shape})()
    _t_tc = _time.perf_counter()

    bt13 = _resample_to_match(
        _downscale_array(
            _get_cmi_dataarray(ch_data["Channel13"]).values.astype(
                np.float32), scale
        ),
        _tgt,
    )
    bt07 = (
        _resample_to_match(
            _downscale_array(
                _get_cmi_dataarray(
                    ch_data["Channel07"]).values.astype(np.float32),
                scale,
            ),
            _tgt,
        )
        if "Channel07" in ch_data
        else bt13
    )
    _t_ir = _time.perf_counter()

    high_cloud = normalize(bt13, 310.0, 190.0)  # cold = 1, warm = 0
    low_cloud = normalize(bt13 - bt07, 0.5, 8.0)

    night_bg = (
        preloaded_night_bg
        if preloaded_night_bg is not None
        else _load_geocolor_night_background(
            _red_ref_da,
            night_bg_lon_offset=night_bg_lon_offset,
            night_bg_lat_offset=night_bg_lat_offset,
            night_bg_zoom=night_bg_zoom,
            night_bg_source_pref=night_bg_source_pref,
        )
    )
    # Downsample night background to working resolution if needed
    if night_bg.shape[:2] != red_ref.shape:
        night_bg = _downscale_array(
            night_bg.astype(np.float32), red_ref.shape[0] / night_bg.shape[0]
        )
        if night_bg.shape[:2] != red_ref.shape:
            # exact match via _resample_to_match for each channel
            night_bg = np.dstack(
                [
                    _resample_to_match(night_bg[:, :, c], _tgt)
                    for c in range(night_bg.shape[2])
                ]
            )
    NIGHT_BG_OPACITY = 0.5  # <-- Set your fixed opacity here (0.0 to 1.0)
    night_rgb = night_bg.copy()
    night_rgb *= NIGHT_BG_OPACITY
    night_rgb[:, :, 0] += 0.30 * low_cloud + 1.0 * high_cloud
    night_rgb[:, :, 1] += 0.40 * low_cloud + 1.0 * high_cloud
    night_rgb[:, :, 2] += 0.50 * low_cloud + 1.1 * high_cloud
    night_rgb = np.clip(night_rgb * 1.1, 0, 1)
    gamma = 0.8
    night_rgb = gamma_correction(night_rgb, gamma)
    # night_rgb = np.clip(night_rgb, 0.0, 1.0)

    # Satpy GeoColor has lim_low/lim_high of 78/88 for day-night transition.
    # We proxy this with red-channel reflectance in percent.
    day_signal_pct = red_ref * 100.0
    lim_low, lim_high = 7.8, 8.8
    day_weight = np.clip((day_signal_pct - lim_low) /
                         (lim_high - lim_low), 0.0, 1.0)

    blended = day_rgb * day_weight[:, :, np.newaxis] + night_rgb * (
        1.0 - day_weight[:, :, np.newaxis]
    )
    result = np.zeros((*red_ref.shape, 4), dtype=np.float32)
    result[:, :, :3] = np.clip(blended, 0.0, 1.0)
    result[:, :, 3] = 1.0
    _t_blend = _time.perf_counter()
    print(
        f"[Perf] GeoColor composite: true_color={_t_tc - _t_comp_start:.2f}s "
        f"ir_resample={_t_ir - _t_tc:.2f}s blend={_t_blend - _t_ir:.2f}s "
        f"total={_t_blend - _t_comp_start:.2f}s"
    )
    return result


# ═══════════════════════════════════════════════════════════════════════
#  goes2go-inspired RGB composite builders
#  Each function follows the same pattern from Brian Blaylock's goes2go:
#    1. Extract channel data (Kelvin for IR, reflectance for VIS)
#    2. Compute channel differences where needed
#    3. normalize() to [0, 1] per the RAMMB/CIRA Quick Guide ranges
#    4. Optional gamma_correction() and/or inversion
#    5. np.dstack([R, G, B]) → float32 RGB array
#
#  IR channels arrive in Kelvin; goes2go recipes use °C for normalize
#  ranges, so we subtract 273.15 before normalizing where the Quick
#  Guide specifies Celsius bounds.  Channel differences (K − K) are the
#  same in K and °C, so no conversion needed for those.
# ═══════════════════════════════════════════════════════════════════════


def _ch_vals(ch_data, channel, scale, tgt):
    """Helper: extract a channel's float32 values, downscaled and resampled."""
    raw = _get_cmi_dataarray(ch_data[channel]).values.astype(np.float32)
    return _resample_to_match(_downscale_array(raw, scale), tgt)


def build_fire_temperature_rgb(ch_data, max_size=None):
    """Fire Temperature RGB  (Ch07=R, Ch06=G, Ch05=B).
    Quick Guide: http://rammb.cira.colostate.edu/training/visit/quick_guides/Fire_Temperature_RGB.pdf"""
    ref = _get_cmi_dataarray(ch_data["Channel07"]).values.astype(np.float32)
    scale = _compute_downscale_factor(ref.shape, max_size)
    tgt = type("S", (), {"shape": _downscale_array(ref, scale).shape})()
    R = _ch_vals(ch_data, "Channel07", scale, tgt) - 273.15  # °C
    G = _ch_vals(ch_data, "Channel06", scale, tgt)  # reflectance 0-1
    B = _ch_vals(ch_data, "Channel05", scale, tgt)  # reflectance 0-1
    R = normalize(R, 0, 60)
    G = normalize(G, 0, 1)
    B = normalize(B, 0, 0.75)
    R = gamma_correction(R, 0.4)
    return np.dstack([R, G, B]).astype(np.float32)


def build_airmass_rgb(ch_data, max_size=None):
    """Air Mass RGB  (Ch08−Ch10=R, Ch12−Ch13=G, Ch08=B).
    Quick Guide: http://rammb.cira.colostate.edu/training/visit/quick_guides/QuickGuide_GOESR_AirMassRGB_final.pdf
    Note: goes2go uses Ch12 (ozone 9.6 µm) for G, but we substitute Ch09 (6.9 µm WV)
    since Ch12 is rarely fetched.  Both highlight upper-level dynamics."""
    ref = _get_cmi_dataarray(ch_data["Channel08"]).values.astype(np.float32)
    scale = _compute_downscale_factor(ref.shape, max_size)
    tgt = type("S", (), {"shape": _downscale_array(ref, scale).shape})()
    ch08 = _ch_vals(ch_data, "Channel08", scale, tgt)
    ch10 = _ch_vals(ch_data, "Channel10", scale, tgt)
    ch13 = _ch_vals(ch_data, "Channel13", scale, tgt)
    R = ch08 - ch10  # K-K = same in °C
    G = ch10 - ch13  # K-K = same in °C (substituting Ch09-Ch13 range)
    B = ch08 - 273.15  # °C
    R = normalize(R, -26.2, 0.6)
    G = normalize(G, -42.2, 6.7)
    B = normalize(B, -64.65, -29.25)
    B = 1 - B
    return np.dstack([R, G, B]).astype(np.float32)


def build_water_vapor_rgb(ch_data, max_size=None):
    """Simple Water Vapor RGB  (Ch13=R, Ch08=G, Ch10=B).
    Quick Guide: http://rammb.cira.colostate.edu/training/visit/quick_guides/Simple_Water_Vapor_RGB.pdf"""
    ref = _get_cmi_dataarray(ch_data["Channel13"]).values.astype(np.float32)
    scale = _compute_downscale_factor(ref.shape, max_size)
    tgt = type("S", (), {"shape": _downscale_array(ref, scale).shape})()
    R = _ch_vals(ch_data, "Channel13", scale, tgt) - 273.15  # °C
    G = _ch_vals(ch_data, "Channel08", scale, tgt) - 273.15  # °C
    B = _ch_vals(ch_data, "Channel10", scale, tgt) - 273.15  # °C
    R = normalize(R, -70.86, 5.81)
    G = normalize(G, -58.49, -30.48)
    B = normalize(B, -28.03, -12.12)
    R = 1 - R
    G = 1 - G
    B = 1 - B
    return np.dstack([R, G, B]).astype(np.float32)


def build_differential_wv_rgb(ch_data, max_size=None):
    """Differential Water Vapor RGB  (Ch10−Ch08=R, Ch10=G, Ch08=B).
    Quick Guide: http://rammb.cira.colostate.edu/training/visit/quick_guides/QuickGuide_GOESR_DifferentialWaterVaporRGB_final.pdf"""
    ref = _get_cmi_dataarray(ch_data["Channel10"]).values.astype(np.float32)
    scale = _compute_downscale_factor(ref.shape, max_size)
    tgt = type("S", (), {"shape": _downscale_array(ref, scale).shape})()
    ch10 = _ch_vals(ch_data, "Channel10", scale, tgt)
    ch08 = _ch_vals(ch_data, "Channel08", scale, tgt)
    R = ch10 - ch08  # K-K
    G = ch10 - 273.15  # °C
    B = ch08 - 273.15  # °C
    R = normalize(R, -3, 30)
    G = normalize(G, -60, 5)
    B = normalize(B, -64.65, -29.25)
    R = gamma_correction(R, 0.2587)
    G = gamma_correction(G, 0.4)
    B = gamma_correction(B, 0.4)
    R = 1 - R
    G = 1 - G
    B = 1 - B
    return np.dstack([R, G, B]).astype(np.float32)


def build_day_convection_rgb(ch_data, max_size=None):
    """Day Convection RGB  (Ch08−Ch10=R, Ch07−Ch13=G, Ch05−Ch02=B).
    Quick Guide: http://rammb.cira.colostate.edu/training/visit/quick_guides/QuickGuide_GOESR_DayConvectionRGB_final.pdf"""
    ref = _get_cmi_dataarray(ch_data["Channel08"]).values.astype(np.float32)
    scale = _compute_downscale_factor(ref.shape, max_size)
    tgt = type("S", (), {"shape": _downscale_array(ref, scale).shape})()
    ch08 = _ch_vals(ch_data, "Channel08", scale, tgt)
    ch10 = _ch_vals(ch_data, "Channel10", scale, tgt)
    ch07 = _ch_vals(ch_data, "Channel07", scale, tgt)
    ch13 = _ch_vals(ch_data, "Channel13", scale, tgt)
    ch05 = _ch_vals(ch_data, "Channel05", scale, tgt)
    ch02 = _ch_vals(ch_data, "Channel02", scale, tgt)
    R = ch08 - ch10  # K-K
    G = ch07 - ch13  # K-K
    B = ch05 - ch02  # reflectance diff
    R = normalize(R, -35, 5)
    G = normalize(G, -5, 60)
    B = normalize(B, -0.75, 0.25)
    return np.dstack([R, G, B]).astype(np.float32)


def build_day_cloud_convection_rgb(ch_data, max_size=None):
    """Day Cloud Convection RGB  (Ch02=R, Ch02=G, Ch13=B).
    Quick Guide: http://rammb.cira.colostate.edu/training/visit/quick_guides/QuickGuide_DayCloudConvectionRGB_final.pdf"""
    ref = _get_cmi_dataarray(ch_data["Channel02"]).values.astype(np.float32)
    scale = _compute_downscale_factor(ref.shape, max_size)
    tgt = type("S", (), {"shape": _downscale_array(ref, scale).shape})()
    ch02 = _ch_vals(ch_data, "Channel02", scale, tgt)
    ch13 = _ch_vals(ch_data, "Channel13", scale, tgt) - 273.15  # °C
    R = normalize(ch02, 0, 1)
    G = normalize(ch02, 0, 1)
    B = normalize(ch13, -70.15, 49.85)
    B = 1 - B
    R = gamma_correction(R, 1.7)
    G = gamma_correction(G, 1.7)
    return np.dstack([R, G, B]).astype(np.float32)


def build_day_cloud_phase_rgb(ch_data, max_size=None):
    """Day Cloud Phase Distinction RGB  (Ch13=R, Ch02=G, Ch05=B).
    Quick Guide: http://rammb.cira.colostate.edu/training/visit/quick_guides/Day_Cloud_Phase_Distinction.pdf"""
    ref = _get_cmi_dataarray(ch_data["Channel13"]).values.astype(np.float32)
    scale = _compute_downscale_factor(ref.shape, max_size)
    tgt = type("S", (), {"shape": _downscale_array(ref, scale).shape})()
    R = _ch_vals(ch_data, "Channel13", scale, tgt) - 273.15  # °C
    G = _ch_vals(ch_data, "Channel02", scale, tgt)  # reflectance
    B = _ch_vals(ch_data, "Channel05", scale, tgt)  # reflectance
    R = normalize(R, -53.5, 7.5)
    G = normalize(G, 0, 0.78)
    B = normalize(B, 0.01, 0.59)
    R = 1 - R
    return np.dstack([R, G, B]).astype(np.float32)


def build_day_cloud_phase_eumetsat_rgb(ch_data, max_size=None):
    """Day Cloud Phase EUMETSAT RGB  (Ch05=R, Ch06=G, Ch02=B).
    Quick Guide: https://eumetrain.org/sites/default/files/2023-01/CloudPhaseRGB.pdf"""
    ref = _get_cmi_dataarray(ch_data["Channel05"]).values.astype(np.float32)
    scale = _compute_downscale_factor(ref.shape, max_size)
    tgt = type("S", (), {"shape": _downscale_array(ref, scale).shape})()
    R = _ch_vals(ch_data, "Channel05", scale, tgt)
    G = _ch_vals(ch_data, "Channel06", scale, tgt)
    B = _ch_vals(ch_data, "Channel02", scale, tgt)
    R = normalize(R, 0, 0.5)
    G = normalize(G, 0, 0.5)
    B = normalize(B, 0, 1)
    return np.dstack([R, G, B]).astype(np.float32)


def build_day_land_cloud_rgb(ch_data, max_size=None):
    """Day Land Cloud RGB  (Ch05=R, Ch03=G, Ch02=B).
    Quick Guide: http://rammb.cira.colostate.edu/training/visit/quick_guides/QuickGuide_GOESR_daylandcloudRGB_final.pdf"""
    ref = _get_cmi_dataarray(ch_data["Channel05"]).values.astype(np.float32)
    scale = _compute_downscale_factor(ref.shape, max_size)
    tgt = type("S", (), {"shape": _downscale_array(ref, scale).shape})()
    R = _ch_vals(ch_data, "Channel05", scale, tgt)
    G = _ch_vals(ch_data, "Channel03", scale, tgt)
    B = _ch_vals(ch_data, "Channel02", scale, tgt)
    R = normalize(R, 0, 0.975)
    G = normalize(G, 0, 1.086)
    B = normalize(B, 0, 1)
    return np.dstack([R, G, B]).astype(np.float32)


def build_day_land_cloud_fire_rgb(ch_data, max_size=None):
    """Day Land Cloud Fire RGB  (Ch06=R, Ch03=G, Ch02=B).
    Quick Guide: http://rammb.cira.colostate.edu/training/visit/quick_guides/QuickGuide_GOESR_DayLandCloudFireRGB_final.pdf"""
    ref = _get_cmi_dataarray(ch_data["Channel06"]).values.astype(np.float32)
    scale = _compute_downscale_factor(ref.shape, max_size)
    tgt = type("S", (), {"shape": _downscale_array(ref, scale).shape})()
    R = _ch_vals(ch_data, "Channel06", scale, tgt)
    G = _ch_vals(ch_data, "Channel03", scale, tgt)
    B = _ch_vals(ch_data, "Channel02", scale, tgt)
    R = normalize(R, 0, 1)
    G = normalize(G, 0, 1)
    B = normalize(B, 0, 1)
    return np.dstack([R, G, B]).astype(np.float32)


def build_day_snow_fog_rgb(ch_data, max_size=None):
    """Day Snow/Fog RGB  (Ch03=R, Ch05=G, Ch07−Ch13=B).
    Quick Guide: http://rammb.cira.colostate.edu/training/visit/quick_guides/QuickGuide_DaySnowFog.pdf"""
    ref = _get_cmi_dataarray(ch_data["Channel03"]).values.astype(np.float32)
    scale = _compute_downscale_factor(ref.shape, max_size)
    tgt = type("S", (), {"shape": _downscale_array(ref, scale).shape})()
    R = _ch_vals(ch_data, "Channel03", scale, tgt)
    G = _ch_vals(ch_data, "Channel05", scale, tgt)
    ch07 = _ch_vals(ch_data, "Channel07", scale, tgt)
    ch13 = _ch_vals(ch_data, "Channel13", scale, tgt)
    B = ch07 - ch13  # K-K
    R = normalize(R, 0, 1)
    G = normalize(G, 0, 0.7)
    B = normalize(B, 0, 30)
    R = gamma_correction(R, 1.7)
    G = gamma_correction(G, 1.7)
    B = gamma_correction(B, 1.7)
    return np.dstack([R, G, B]).astype(np.float32)


def build_nighttime_microphysics_rgb(ch_data, max_size=None):
    """Nighttime Microphysics RGB  (Ch15−Ch13=R, Ch13−Ch07=G, Ch13=B).
    Quick Guide: http://rammb.cira.colostate.edu/training/visit/quick_guides/QuickGuide_GOESR_NtMicroRGB_final.pdf"""
    ref = _get_cmi_dataarray(ch_data["Channel13"]).values.astype(np.float32)
    scale = _compute_downscale_factor(ref.shape, max_size)
    tgt = type("S", (), {"shape": _downscale_array(ref, scale).shape})()
    ch13 = _ch_vals(ch_data, "Channel13", scale, tgt)
    ch07 = _ch_vals(ch_data, "Channel07", scale, tgt)
    ch15 = _ch_vals(ch_data, "Channel15", scale, tgt)
    R = ch15 - ch13  # K-K
    G = ch13 - ch07  # K-K
    B = ch13 - 273.15  # °C
    R = normalize(R, -6.7, 2.6)
    G = normalize(G, -3.1, 5.2)
    B = normalize(B, -29.6, 19.5)
    return np.dstack([R, G, B]).astype(np.float32)


def build_dust_rgb(ch_data, max_size=None):
    """Dust RGB  (Ch15−Ch13=R, Ch14−Ch11=G, Ch13=B).
    Quick Guide: http://rammb.cira.colostate.edu/training/visit/quick_guides/Dust_RGB_Quick_Guide.pdf"""
    ref = _get_cmi_dataarray(ch_data["Channel13"]).values.astype(np.float32)
    scale = _compute_downscale_factor(ref.shape, max_size)
    tgt = type("S", (), {"shape": _downscale_array(ref, scale).shape})()
    ch13 = _ch_vals(ch_data, "Channel13", scale, tgt)
    ch14 = _ch_vals(ch_data, "Channel14", scale, tgt)
    ch11 = _ch_vals(ch_data, "Channel11", scale, tgt)
    ch15 = _ch_vals(ch_data, "Channel15", scale, tgt)
    R = ch15 - ch13  # K-K
    G = ch14 - ch11  # K-K
    B = ch13 - 273.15  # °C
    R = normalize(R, -6.7, 2.6)
    G = normalize(G, -0.5, 20)
    B = normalize(B, -11.95, 15.55)
    G = gamma_correction(G, 2.5)
    return np.dstack([R, G, B]).astype(np.float32)


def build_ash_rgb(ch_data, max_size=None):
    """Ash RGB  (Ch15−Ch13=R, Ch14−Ch11=G, Ch13=B).
    Quick Guide: http://rammb.cira.colostate.edu/training/visit/quick_guides/GOES_Ash_RGB.pdf"""
    ref = _get_cmi_dataarray(ch_data["Channel13"]).values.astype(np.float32)
    scale = _compute_downscale_factor(ref.shape, max_size)
    tgt = type("S", (), {"shape": _downscale_array(ref, scale).shape})()
    ch13 = _ch_vals(ch_data, "Channel13", scale, tgt)
    ch14 = _ch_vals(ch_data, "Channel14", scale, tgt)
    ch11 = _ch_vals(ch_data, "Channel11", scale, tgt)
    ch15 = _ch_vals(ch_data, "Channel15", scale, tgt)
    R = ch15 - ch13
    G = ch14 - ch11
    B = ch13 - 273.15
    R = normalize(R, -6.7, 2.6)
    G = normalize(G, -6, 6.3)
    B = normalize(B, -29.55, 29.25)
    return np.dstack([R, G, B]).astype(np.float32)


def build_sulfur_dioxide_rgb(ch_data, max_size=None):
    """Sulfur Dioxide RGB  (Ch09−Ch10=R, Ch13−Ch11=G, Ch07=B).
    Quick Guide: http://rammb.cira.colostate.edu/training/visit/quick_guides/Quick_Guide_SO2_RGB.pdf"""
    ref = _get_cmi_dataarray(ch_data["Channel13"]).values.astype(np.float32)
    scale = _compute_downscale_factor(ref.shape, max_size)
    tgt = type("S", (), {"shape": _downscale_array(ref, scale).shape})()
    ch09 = _ch_vals(ch_data, "Channel09", scale, tgt)
    ch10 = _ch_vals(ch_data, "Channel10", scale, tgt)
    ch13 = _ch_vals(ch_data, "Channel13", scale, tgt)
    ch11 = _ch_vals(ch_data, "Channel11", scale, tgt)
    ch07 = _ch_vals(ch_data, "Channel07", scale, tgt)
    R = ch09 - ch10  # K-K
    G = ch13 - ch11  # K-K
    B = ch07 - 273.15  # °C
    R = normalize(R, -4, 2)
    G = normalize(G, -4, 5)
    B = normalize(B, -30.1, 29.8)
    return np.dstack([R, G, B]).astype(np.float32)


def build_split_window_diff_rgb(ch_data, max_size=None):
    """Split Window Difference (greyscale)  (Ch15−Ch13).
    Quick Guide: http://cimss.ssec.wisc.edu/goes/OCLOFactSheetPDFs/ABIQuickGuide_SplitWindowDifference.pdf"""
    ref = _get_cmi_dataarray(ch_data["Channel13"]).values.astype(np.float32)
    scale = _compute_downscale_factor(ref.shape, max_size)
    tgt = type("S", (), {"shape": _downscale_array(ref, scale).shape})()
    ch13 = _ch_vals(ch_data, "Channel13", scale, tgt)
    ch15 = _ch_vals(ch_data, "Channel15", scale, tgt)
    data = ch15 - ch13
    data = normalize(data, -10, 10)
    return np.dstack([data, data, data]).astype(np.float32)


def build_night_fog_diff_rgb(ch_data, max_size=None):
    """Night Fog Difference (greyscale)  (Ch13−Ch07).
    Quick Guide: http://cimss.ssec.wisc.edu/goes/OCLOFactSheetPDFs/ABIQuickGuide_NightFogBTD.pdf"""
    ref = _get_cmi_dataarray(ch_data["Channel13"]).values.astype(np.float32)
    scale = _compute_downscale_factor(ref.shape, max_size)
    tgt = type("S", (), {"shape": _downscale_array(ref, scale).shape})()
    ch13 = _ch_vals(ch_data, "Channel13", scale, tgt)
    ch07 = _ch_vals(ch_data, "Channel07", scale, tgt)
    data = ch13 - ch07
    data = normalize(data, -90, 15)
    data = 1 - data
    return np.dstack([data, data, data]).astype(np.float32)


def build_blowing_snow_rgb(ch_data, max_size=None):
    """Blowing Snow RGB  (Ch02=R, Ch05=G, Ch07−Ch13=B).
    Quick Guide: https://rammb2.cira.colostate.edu/wp-content/uploads/2024/11/GOES-BlowingSnowRGB1_QuickGuide_24April2024.pdf"""
    ref = _get_cmi_dataarray(ch_data["Channel02"]).values.astype(np.float32)
    scale = _compute_downscale_factor(ref.shape, max_size)
    tgt = type("S", (), {"shape": _downscale_array(ref, scale).shape})()
    R = _ch_vals(ch_data, "Channel02", scale, tgt)
    G = _ch_vals(ch_data, "Channel05", scale, tgt)
    ch07 = _ch_vals(ch_data, "Channel07", scale, tgt)
    ch13 = _ch_vals(ch_data, "Channel13", scale, tgt)
    B = ch07 - ch13  # K-K
    R = normalize(R, 0, 0.5)
    G = normalize(G, 0, 0.2)
    B = normalize(B, 0, 30)
    _gamma_bs = 1 / 0.7
    R = gamma_correction(R, _gamma_bs)
    B = gamma_correction(B, _gamma_bs)
    return np.dstack([R, G, B]).astype(np.float32)


def build_sea_spray_rgb(ch_data, max_size=None):
    """Sea Spray RGB  (Ch07−Ch13=R, Ch03=G, Ch02=B).
    Quick Guide: https://rammb.cira.colostate.edu/training/visit/quick_guides/VIIRS_Sea_Spray_RGB_Quick_Guide_v2.pdf"""
    ref = _get_cmi_dataarray(ch_data["Channel07"]).values.astype(np.float32)
    scale = _compute_downscale_factor(ref.shape, max_size)
    tgt = type("S", (), {"shape": _downscale_array(ref, scale).shape})()
    ch07 = _ch_vals(ch_data, "Channel07", scale, tgt)
    ch13 = _ch_vals(ch_data, "Channel13", scale, tgt)
    R = ch07 - ch13  # K-K
    G = _ch_vals(ch_data, "Channel03", scale, tgt)
    B = _ch_vals(ch_data, "Channel02", scale, tgt)
    R = normalize(R, 0, 5)
    G = normalize(G, 0.01, 0.09)
    B = normalize(B, 0.02, 0.12)
    _gamma_ss = 1 / 0.6
    G = gamma_correction(G, _gamma_ss)
    B = gamma_correction(B, _gamma_ss)
    return np.dstack([R, G, B]).astype(np.float32)


def build_rocket_plume_rgb(ch_data, max_size=None):
    """Rocket Plume RGB  (Ch07=R, Ch08=G, Ch02=B).
    Quick Guide: https://cimss.ssec.wisc.edu/satellite-blog/images/2021/06/QuickGuide_Template_GOESRBanner_Rocket_Plume.pdf"""
    ref = _get_cmi_dataarray(ch_data["Channel07"]).values.astype(np.float32)
    scale = _compute_downscale_factor(ref.shape, max_size)
    tgt = type("S", (), {"shape": _downscale_array(ref, scale).shape})()
    R = (
        _ch_vals(ch_data, "Channel07", scale, tgt) - 273.15
    )  # °C → normalize in K offset
    G = _ch_vals(ch_data, "Channel08", scale, tgt) - 273.15  # °C
    B = _ch_vals(ch_data, "Channel02", scale, tgt)  # reflectance
    # goes2go uses K directly for R/G:  normalize(R, 273, 338)  → we use °C equiv
    R = normalize(R, 0, 65)  # 273K–338K → 0°C–65°C
    G = normalize(G, -40, -20)  # 233K–253K → −40°C–−20°C
    B = normalize(B, 0, 0.80)
    return np.dstack([R, G, B]).astype(np.float32)


def _get_cmi_dataarray(ds):
    """
    Extract and parse the CMI variable from a dataset as a MetPy DataArray.
    Handles both standard and sectorized variable names.
    """
    cmi_var = get_cmi_var(ds)
    return ds.metpy.parse_cf(cmi_var)


def _compute_image_extent(sample_da):
    """
    Compute the image extent (bounding box) in projection units for Cartopy plotting.
    Converts from radians to meters if needed for geostationary projections.
    Returns (xmin, xmax, ymin, ymax).
    """
    extent = (
        float(sample_da.x.min().item()),
        float(sample_da.x.max().item()),
        float(sample_da.y.min().item()),
        float(sample_da.y.max().item()),
    )

    finite_vals = [v for v in extent if np.isfinite(v)]
    if len(finite_vals) == 4:
        max_abs = max(abs(v) for v in finite_vals)
        if max_abs < 20.0:
            try:
                crs = sample_da.metpy.cartopy_crs
                proj_params = getattr(crs, "proj4_params", {}) or {}
                sat_h = proj_params.get("h")
                if sat_h is None:
                    sat_h = proj_params.get("satellite_height")
                sat_h = float(sat_h) if sat_h is not None else None
                if sat_h is not None and np.isfinite(sat_h) and sat_h > 0:
                    extent = tuple(v * sat_h for v in extent)
            except Exception:
                pass

    return extent


def process_composite(
    ch_data,
    channel_key,
    proj,
    night_bg_lon_offset=0.0,
    night_bg_lat_offset=0.0,
    night_bg_zoom=100.0,
    night_bg_source_pref="tiff_first",
    preloaded_night_bg=None,
    max_size=None,
):
    """
    Main composite builder for satellite imagery.
    Dispatches to the correct compositing function based on channel_key:
    - TrueColor: Simulated true color
    - GeoColor: Satpy-inspired day/night blend
    - GeoColorBlkMar: Satpy-style with Black Marble night background
    - DayNightHybrid: True color by day, IR by night
    - Sandwich: Visible/IR sandwich overlay
    - Single-band: Handles standard visible enhancement
    If *max_size* is given, multi-band compositing works at reduced resolution.
    Returns the processed image (RGB, RGBA, or dict for sandwich).
    """
    if channel_key == "TrueColor":
        rgb, _, _sc = build_true_color_rgb(ch_data, max_size=max_size)
        return rgb

    elif channel_key == "GeoColor":
        return build_geocolor_rgba(ch_data, max_size=max_size)

    elif channel_key == "GeoColorBlkMar":
        return build_geocolor_satpy_option_rgba(
            ch_data,
            night_bg_lon_offset=night_bg_lon_offset,
            night_bg_lat_offset=night_bg_lat_offset,
            night_bg_zoom=night_bg_zoom,
            night_bg_source_pref=night_bg_source_pref,
            preloaded_night_bg=preloaded_night_bg,
            max_size=max_size,
        )

    elif channel_key == "DayNightHybrid":
        # --- Daytime True Color layers (Ch01 blue, Ch02 red, Ch03 veggie) ---
        rgb, _r_ref_da, scale = build_true_color_rgb(
            ch_data, max_size=max_size)
        r_arr = rgb[:, :, 0]  # red channel at working resolution
        _tgt = type("S", (), {"shape": r_arr.shape})()

        # --- Nighttime IR overlay (Ch13 clean-window IR) ---
        ir_vals = _resample_to_match(
            _downscale_array(
                _get_cmi_dataarray(
                    ch_data["Channel13"]).values.astype(np.float32),
                scale,
            ),
            _tgt,
        )
        ir_norm_vals = IR_NORM(ir_vals)
        ir_rgba = IR_CMAP(ir_norm_vals).astype(np.float32)

        # Detect night: visible red reflectance < 5 % → nighttime pixel
        night_mask = r_arr < 0.05

        # Blend: True Color for day, enhanced IR for night
        result = np.zeros((*r_arr.shape, 4), dtype=np.float32)
        result[:, :, :3] = rgb
        result[:, :, 3] = 1.0
        result[night_mask] = ir_rgba[night_mask]

        return result

    elif channel_key == "Sandwich":
        vis_full = satpy_visible_reflectance(
            _get_cmi_dataarray(ch_data["Channel02"]))
        scale = _compute_downscale_factor(vis_full.shape, max_size)
        vis_np = _downscale_array(np.array(vis_full, dtype=np.float32), scale)
        _tgt = type("S", (), {"shape": vis_np.shape})()

        ir_bt_vals = _resample_to_match(
            _downscale_array(
                _get_cmi_dataarray(
                    ch_data["Channel13"]).values.astype(np.float32),
                scale,
            ),
            _tgt,
        )

        ir_norm = IR_NORM(ir_bt_vals)
        ir_rgba = IR_CMAP(ir_norm)

        temp_threshold = 273.0
        alpha = np.clip((temp_threshold - ir_bt_vals) / 50.0, 0, 0.85)
        ir_rgba[:, :, 3] = alpha

        return {"vis": vis_np, "ir": ir_rgba}

    # ── NEW goes2go-style RGB composites ──────────────────────────
    elif channel_key == "FireTemperature":
        return build_fire_temperature_rgb(ch_data, max_size=max_size)
    elif channel_key == "AirMass":
        return build_airmass_rgb(ch_data, max_size=max_size)
    elif channel_key == "WaterVapor":
        return build_water_vapor_rgb(ch_data, max_size=max_size)
    elif channel_key == "DifferentialWaterVapor":
        return build_differential_wv_rgb(ch_data, max_size=max_size)
    elif channel_key == "DayConvection":
        return build_day_convection_rgb(ch_data, max_size=max_size)
    elif channel_key == "DayCloudConvection":
        return build_day_cloud_convection_rgb(ch_data, max_size=max_size)
    elif channel_key == "DayCloudPhase":
        return build_day_cloud_phase_rgb(ch_data, max_size=max_size)
    elif channel_key == "DayCloudPhaseEUMETSAT":
        return build_day_cloud_phase_eumetsat_rgb(ch_data, max_size=max_size)
    elif channel_key == "DayLandCloud":
        return build_day_land_cloud_rgb(ch_data, max_size=max_size)
    elif channel_key == "DayLandCloudFire":
        return build_day_land_cloud_fire_rgb(ch_data, max_size=max_size)
    elif channel_key == "DaySnowFog":
        return build_day_snow_fog_rgb(ch_data, max_size=max_size)
    elif channel_key == "NighttimeMicrophysics":
        return build_nighttime_microphysics_rgb(ch_data, max_size=max_size)
    elif channel_key == "Dust":
        return build_dust_rgb(ch_data, max_size=max_size)
    elif channel_key == "Ash":
        return build_ash_rgb(ch_data, max_size=max_size)
    elif channel_key == "SulfurDioxide":
        return build_sulfur_dioxide_rgb(ch_data, max_size=max_size)
    elif channel_key == "SplitWindowDifference":
        return build_split_window_diff_rgb(ch_data, max_size=max_size)
    elif channel_key == "NightFogDifference":
        return build_night_fog_diff_rgb(ch_data, max_size=max_size)
    elif channel_key == "BlowingSnow":
        return build_blowing_snow_rgb(ch_data, max_size=max_size)
    elif channel_key == "SeaSpray":
        return build_sea_spray_rgb(ch_data, max_size=max_size)
    elif channel_key == "RocketPlume":
        return build_rocket_plume_rgb(ch_data, max_size=max_size)

    else:
        # Resolve actual band key — handles aliases like Channel13AWIPS → Channel13
        data_band = ABI_CHANNELS[channel_key].get("req", [channel_key])[0]
        data = _get_cmi_dataarray(ch_data[data_band])
        if (
            "Channel01" in channel_key
            or "Channel02" in channel_key
            or "Channel03" in channel_key
        ):
            data = satpy_visible_reflectance(data)
        return data


def plot_cities_sat(
    ax,
    extent_bounds,
    filename="us-cities.json",
    density_scale=1.0,
    collision_w_factor=0.05,
    collision_h_factor=0.02,
    city_text_size=12,
    z_cities=30,
    city_text_color="#ffffff",
    city_text_bg_color="#000000",
    city_text_bg_alpha=0.3,
    font_family="Montserrat",
    font_weight="black",
    font_style="italic",
    box_style="round,pad=0.2",
    halo_width=2,
    halo_color="black",
    text_alpha=0.95,
):
    """
    Plot city labels on a satellite map axis.
    - Loads city data from JSON
    - Applies collision detection to avoid overlapping labels
    - Styles text according to parameters
    - Only draws cities within the current map extent
    """
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        # Go up one level to root, then into /data
        root_dir = os.path.dirname(script_dir)
        cities_path = os.path.join(root_dir, "data", filename)

        if not os.path.exists(cities_path):
            # Fallback
            cities_path = os.path.join(root_dir, "data", "us-cities.json")

        with open(cities_path, "r") as f:
            raw_data = json.load(f)

        cities = []
        # ADAPTER: Convert {"City": [lat, lon, align]} -> [{"city": "City", ...}]
        if isinstance(raw_data, dict):
            for k, v in raw_data.items():
                if isinstance(v, list) and len(v) >= 2:
                    cities.append(
                        {
                            "city": k,
                            "latitude": v[0],
                            "longitude": v[1],
                            "align": v[2] if len(v) > 2 else "left",
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

    except Exception as e:
        print(f"[WARN] Could not load city data: {e}")
        return

    min_lon, max_lon, min_lat, max_lat = extent_bounds
    drawn_bboxes = []

    # Estimate text size in degrees for collision detection
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

        # 1. Visibility Check
        if not (
            (min_lat - 0.1) <= lat <= (max_lat + 0.1)
            and (min_lon - 0.1) <= lon <= (max_lon + 0.1)
        ):
            continue

        # 2. Collision Box (centered on city point)
        cand_x_min, cand_x_max = lon - (text_w / 2.0), lon + (text_w / 2.0)
        cand_y_min, cand_y_max = lat - (text_h / 2.0), lat + (text_h / 2.0)

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

        # 3. Draw City Label
        txt = ax.text(
            lon,
            lat,
            city_name.upper(),
            transform=ccrs.PlateCarree(),
            fontsize=city_text_size,
            color=city_text_color,
            fontname=font_family,
            fontweight=font_weight,
            fontstyle=font_style,
            ha="center",
            va="center",
            zorder=z_cities + 1,
            alpha=text_alpha,
            bbox=dict(
                facecolor=city_text_bg_color,
                alpha=city_text_bg_alpha,
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


def generate_satellite_animation(
    sat_id,
    region_name,
    data_dir,
    channel_key,
    max_frames,
    fps,
    logo_file,
    custom_extent=None,
    progress_callback=None,
    show_places=False,
    style_config=None,
):
    """
    Generate a high-resolution satellite animation (MP4 and PNG frames) for a given satellite, region, and channel.
    - Loads and sorts recent satellite files for required bands
    - Processes each frame using process_composite and applies map overlays (cities, counties, borders, etc.)
    - Handles style configuration for HUD, logos, colorbars, and overlays
    - Saves each frame as PNG and assembles into an MP4 animation
    Returns (movie_path, last_frame_path) or (None, None) on failure.
    """

    style_config = resolve_satellite_style_config(style_config)

    # --- STYLE UNPACKING ---
    show_places = bool(style_config.get("show_places", show_places))
    font_family = style_config.get("font_family", "Montserrat")
    hud_left_size = style_config.get("hud_left_size", 10)
    hud_left_x = style_config.get("hud_left_x", 0.03)
    hud_left_y = style_config.get("hud_left_y", 0.97)

    hud_right_size = style_config.get("hud_right_size", 10)
    hud_right_x = style_config.get("hud_right_x", 0.97)
    hud_right_y = style_config.get("hud_right_y", 0.97)

    logo_user_size = style_config.get("logo_user_size", 0.08)
    logo_user_x = style_config.get("logo_user_x", 0.98)
    logo_user_y = style_config.get("logo_user_y", 0.01)

    cbar_size = float(style_config.get("cbar_size", 0.75))
    cbar_horizontal_size = float(style_config.get(
        "cbar_size_horizontal", min(cbar_size, 0.55)))
    cbar_horizontal_fraction = float(
        style_config.get("cbar_fraction_horizontal", 0.045))
    cbar_title_size = style_config.get("cbar_title_size", 14)
    cbar_tick_labelsize = style_config.get("cbar_tick_labelsize", 10)
    cbar_tick_color = style_config.get("cbar_tick_color", "black")
    cbar_tick_weight = style_config.get("cbar_tick_weight", "bold")
    cbar_outline_color = style_config.get("cbar_outline_color", "#555555")

    cities_file = style_config.get("cities_file", "us-cities.json")
    city_density = float(style_config.get("city_density", 5))
    density_scale = city_density / 5.0
    city_collision_w = float(style_config.get("city_collision_w", 0.05))
    city_collision_h = float(style_config.get("city_collision_h", 0.02))
    city_text_size = int(style_config.get("city_text_size", 12))
    city_font_weight = style_config.get("city_font_weight", "black")
    city_font_style = style_config.get("city_font_style", "italic")
    city_box_style = style_config.get("city_box_style", "round,pad=0.2")
    city_halo_width = float(style_config.get("city_halo_width", 2))
    city_halo_color = style_config.get("city_halo_color", "black")
    city_text_alpha = float(style_config.get("city_text_alpha", 0.95))

    show_counties = style_config.get("show_counties", False)
    county_linewidth = float(style_config.get(
        "county_linewidth", style_config.get("county_width", 0.3)))
    county_color = style_config.get("county_color", "white")

    # Map Margins
    expand_top = float(style_config.get("map_margin_top", 0.0))
    expand_bottom = float(style_config.get("map_margin_bottom", 0.0))
    expand_left = float(style_config.get("map_margin_left", 0.0))
    expand_right = float(style_config.get("map_margin_right", 0.0))

    # City text styling
    city_text_color = style_config.get("city_text_color", "#ffffff")
    city_text_bg_color = style_config.get("city_text_bg_color", "#000000")
    city_text_bg_alpha = float(style_config.get("city_text_bg_alpha", 0.3))

    night_bg_lon_offset = float(style_config.get("night_bg_lon_offset", 0.0))
    night_bg_lat_offset = float(style_config.get("night_bg_lat_offset", 0.0))
    night_bg_zoom = float(style_config.get("night_bg_zoom", 100.0))
    night_bg_source_pref = str(style_config.get(
        "night_bg_source_pref", "tiff_first"))

    # Base map styling
    map_bg_color = style_config.get("map_bg_color", "#000000")
    land_color = style_config.get("land_color", "#5c5c5c")
    ocean_color = style_config.get("ocean_color", "#152238")
    coastline_width = float(style_config.get("coastline_width", 0.8))
    coastline_color = style_config.get("coastline_color", "#000000")

    # Country borders
    show_country = style_config.get("show_country", True)
    if isinstance(show_country, str):
        show_country = show_country.lower() not in ("false", "0", "no")
    country_color = style_config.get("country_color", "#ffffff")
    country_width = float(style_config.get("country_width", 0.5))

    # State borders
    show_states = style_config.get("show_states", True)
    if isinstance(show_states, str):
        show_states = show_states.lower() not in ("false", "0", "no")
    state_color = style_config.get("state_color", "#ffffff")
    state_width = float(style_config.get("state_width", 0.5))

    # Highway styling
    show_highways = style_config.get("show_highways", True)
    if isinstance(show_highways, str):
        show_highways = show_highways.lower() not in ("false", "0", "no")
    highway_color = style_config.get("highway_color", "#888888")
    highway_width = float(style_config.get("highway_width", 0.8))
    highway_opacity = float(style_config.get("highway_opacity", 0.6))

    # HUD text & box styling
    hud_left_text_color = style_config.get("hud_left_text_color", "#ffffff")
    hud_left_bg_color = style_config.get("hud_left_bg_color", "#000000")
    hud_left_edge_color = style_config.get("hud_left_edge_color", "#555555")
    hud_left_alpha = float(style_config.get("hud_left_alpha", 0.7))
    hud_font_weight = style_config.get("hud_font_weight", "black")
    hud_font_style = style_config.get("hud_font_style", "italic")
    hud_line_spacing = float(style_config.get("hud_line_spacing", 1.15))
    hud_left_box_style = style_config.get(
        "hud_left_box_style", "round,pad=0.5")
    hud_right_box_style = style_config.get(
        "hud_right_box_style", "round,pad=0.4")
    hud_right_text_color = style_config.get("hud_right_text_color", "#ffd700")
    hud_right_bg_color = style_config.get("hud_right_bg_color", "#000000")
    hud_right_edge_color = style_config.get("hud_right_edge_color", "#555555")
    hud_right_alpha = float(style_config.get("hud_right_alpha", 0.7))

    figure_left_margin = float(style_config.get("figure_left_margin", 0.0))
    figure_right_margin = float(style_config.get("figure_right_margin", 0.0))
    figure_top_margin = float(style_config.get("figure_top_margin", 0.0))
    figure_bottom_margin = float(style_config.get("figure_bottom_margin", 0.0))

    # Lakes & River Styling
    show_lakes = style_config.get("show_lakes", True)
    if isinstance(show_lakes, str):
        show_lakes = show_lakes.lower() not in ("false", "0", "no")
    lake_color = style_config.get("lake_color", "#000000")
    lake_outline_color = style_config.get("lake_outline_color", "#333333")
    lake_outline_width = float(style_config.get("lake_outline_width", 0.5))
    show_rivers = style_config.get("show_rivers", True)
    if isinstance(show_rivers, str):
        show_rivers = show_rivers.lower() not in ("false", "0", "no")
    river_color = style_config.get("river_color", "#000000")
    river_width = float(style_config.get("river_width", 0.5))

    # Scale HUD/logo sizes relative to the reference width (12.8")
    fig_width = 12.8
    scale_factor = max(fig_width / 12.8, 0.55)
    hud_left_size = int(hud_left_size * scale_factor)
    hud_right_size = int(hud_right_size * scale_factor)
    city_text_size = int(city_text_size * scale_factor)
    cbar_title_size = int(cbar_title_size * scale_factor)
    logo_user_size = logo_user_size * scale_factor

    # Z-order defaults (overridden by style_config zorder_* keys)
    zo = {
        "land": 0,
        "water": 0,
        "sat_image": 1,
        "counties": 14,
        "borders": 15,
        "cities": 30,
        "hud": 100,
        "logos": 100,
    }
    if style_config:
        for k in zo:
            v = style_config.get(f"zorder_{k}")
            if v is not None:
                zo[k] = int(v)

    script_dir = os.path.dirname(os.path.abspath(__file__))

    req_bands = ABI_CHANNELS[channel_key].get("req", [channel_key])

    # --- TIMELINE FILTERING LOGIC ---
    all_bands_parsed = {}

    for b in req_bands:
        raw_files = glob.glob(os.path.join(
            data_dir, b, "**", "*.nc"), recursive=True)
        parsed_list = []
        for f in raw_files:
            t = parse_goes_time_from_filename(f)
            if t:
                parsed_list.append((t, f))

        parsed_list.sort(key=lambda x: x[0])
        all_bands_parsed[b] = parsed_list

    if not any(all_bands_parsed.values()):
        print(
            f"[ERROR] No satellite files found in {data_dir}. Data may not have been downloaded."
        )
        print(f"   Searched for bands: {req_bands}")
        for b in req_bands:
            ch_dir = os.path.join(data_dir, b)
            print(f"   Directory {ch_dir} exists: {os.path.exists(ch_dir)}")
            if os.path.exists(ch_dir):
                files = glob.glob(os.path.join(
                    ch_dir, "**", "*.nc"), recursive=True)
                print(f"   Files in {b}: {len(files)}")
        return None, None

    latest_timestamps = []
    for b in req_bands:
        if all_bands_parsed[b]:
            latest_timestamps.append(all_bands_parsed[b][-1][0])

    if not latest_timestamps:
        return None, None

    global_newest_time = max(latest_timestamps)
    cutoff_time = global_newest_time - timedelta(hours=12)

    output_day_dir = _date_partition_dir(
        os.path.join(
            script_dir,
            "satellite_images",
            str(sat_id),
            str(region_name),
            str(channel_key),
        ),
        global_newest_time,
    )
    output_dir = output_day_dir
    frame_dir = os.path.join(output_dir, "frames")
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(frame_dir, exist_ok=True)

    band_files = {}
    for b, file_list in all_bands_parsed.items():
        valid_files = [f_path for t, f_path in file_list if t >= cutoff_time]
        band_files[b] = valid_files

    if not any(band_files.values()) or min(len(f) for f in band_files.values()) == 0:
        return None, None

    min_len = min(len(f) for f in band_files.values())
    files_to_process = min(min_len, max_frames)

    preloaded_night_bg = None
    preloaded_night_bg_signature = None
    frames = []

    # Composite at reduced resolution — 2× the output canvas longest dimension
    # gives excellent quality while avoiding 60M-pixel math on 6000×10000 grids.
    _output_dpi = 150
    _canvas_long = int(max(12.8, 7.2) * _output_dpi)  # 1920
    _composite_max_size = _canvas_long * 2  # 3840

    # --- Figure-reuse state (created on first frame, updated on subsequent) ---
    fig = None
    ax = None
    sat_img_artist = None
    sat_ir_artist = None
    hud_right_ann = None

    # Pre-compute static HUD content (invariant across frames)
    sat_num = "".join(filter(str.isdigit, str(sat_id)))
    region_label = os.path.basename(data_dir).upper()
    if custom_extent:
        region_label += " - Target Area"
    hud_stacked = f"GOES-{sat_num}\n{ABI_CHANNELS[channel_key]['name']}\n{region_label}"

    def _draw_static_overlays(ax, fig):
        """Draw all static map overlays (borders, cities, colorbar, HUD left, logo)."""
        if show_places:
            curr_ext = ax.get_extent(crs=ccrs.PlateCarree())
            plot_cities_sat(
                ax,
                curr_ext,
                filename=cities_file,
                density_scale=density_scale,
                collision_w_factor=city_collision_w,
                collision_h_factor=city_collision_h,
                city_text_size=city_text_size,
                z_cities=zo["cities"],
                city_text_color=city_text_color,
                city_text_bg_color=city_text_bg_color,
                city_text_bg_alpha=city_text_bg_alpha,
                font_family=font_family,
                font_weight=city_font_weight,
                font_style=city_font_style,
                box_style=city_box_style,
                halo_width=city_halo_width,
                halo_color=city_halo_color,
                text_alpha=city_text_alpha,
            )

        ax.add_feature(
            cfeature.OCEAN.with_scale("10m"),
            facecolor=ocean_color,
            edgecolor="none",
            zorder=zo["water"],
        )
        ax.add_feature(
            cfeature.LAND.with_scale("10m"),
            facecolor=land_color,
            edgecolor="none",
            zorder=zo["land"],
        )
        ax.coastlines("10m", color=coastline_color,
                      linewidth=coastline_width, zorder=zo["borders"])

        if show_counties:
            census_feature = CensusCounties.get_feature()
            if census_feature:
                ax.add_feature(
                    census_feature,
                    linewidth=county_linewidth,
                    edgecolor=county_color,
                    facecolor="none",
                    zorder=zo["counties"],
                )

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
        if show_highways:
            highways = cfeature.NaturalEarthFeature(
                category="cultural", name="roads", scale="10m", facecolor="none"
            )
            ax.add_feature(
                highways,
                edgecolor=highway_color,
                linewidth=highway_width,
                alpha=highway_opacity,
                zorder=zo["borders"],
            )
        if show_lakes:
            ax.add_feature(
                cfeature.LAKES.with_scale("10m"),
                facecolor=lake_color,
                edgecolor=lake_outline_color,
                linewidth=lake_outline_width,
                zorder=zo["borders"],
            )
        if show_rivers:
            ax.add_feature(
                cfeature.RIVERS.with_scale("10m"),
                edgecolor=river_color,
                linewidth=river_width,
                zorder=zo["borders"],
            )

        if channel_key not in RGB_COMPOSITE_KEYS and channel_key != "Sandwich":
            sm = plt.cm.ScalarMappable(
                cmap=ABI_CHANNELS[channel_key]["cmap"],
                norm=ABI_CHANNELS[channel_key].get("norm"),
            )

            ticks = None
            tick_labels = None
            if "IR" in ABI_CHANNELS[channel_key]["name"]:
                ir_norm = ABI_CHANNELS[channel_key].get("norm")
                if ir_norm is not None and ir_norm.vmax > 380:
                    # Fire detection 3.9 µm — 164–400 K
                    ticks = [173, 213, 253, 273, 313, 353, 393]
                    tick_labels = [
                        "-100C",
                        "-60C",
                        "-20C",
                        "0C",
                        "+40C",
                        "+80C",
                        "+120C",
                    ]
                elif ir_norm is not None and ir_norm.vmin <= 175:
                    # Wide-range IR colormaps (CIRA 160–330 K, MetPy 170–330 K)
                    ticks = [173, 193, 213, 233, 253, 273, 293, 313]
                    tick_labels = [
                        "-100C",
                        "-80C",
                        "-60C",
                        "-40C",
                        "-20C",
                        "0C",
                        "+20C",
                        "+40C",
                    ]
                else:
                    ticks = [193, 213, 233, 253, 273, 303]
                    tick_labels = ["-80C", "-60C",
                                   "-40C", "-20C", "0C", "+30C"]
            elif "WV" in ABI_CHANNELS[channel_key]["name"]:
                ticks = [198, 218, 238, 258, 273]
                tick_labels = ["-75C", "-55C", "-35C", "-15C", "0C"]

            cb = fig.colorbar(
                sm,
                ax=ax,
                orientation="horizontal",
                shrink=cbar_horizontal_size,
                fraction=cbar_horizontal_fraction,
                pad=0.03,
                ticks=ticks,
            )

            cb.ax.tick_params(axis="x", colors=cbar_tick_color,
                              labelsize=cbar_tick_labelsize)
            if tick_labels:
                cb.ax.set_xticklabels(tick_labels)
            for tick in cb.ax.get_xticklabels():
                tick.set_fontname(font_family)
                tick.set_fontweight(cbar_tick_weight)
            cb.outline.set_edgecolor(cbar_outline_color)

        # HUD left annotation (static content)
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
            zorder=zo["hud"],
        )

        # User Logo
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
                print(f"[WARN] Could not load user logo: {e}")

    for i in range(files_to_process):
        if progress_callback:
            progress_callback(i + 1, files_to_process)

        idx = -(files_to_process - i)

        try:
            current_ds = {b: xr.open_dataset(
                band_files[b][idx]) for b in req_bands}
            sample = _get_cmi_dataarray(current_ds[req_bands[0]])

            if channel_key == "GeoColorBlkMar":
                geo_bg_target = (
                    _get_cmi_dataarray(current_ds["Channel02"])
                    if "Channel02" in current_ds
                    else sample
                )
                current_signature = (
                    int(geo_bg_target.shape[0]),
                    int(geo_bg_target.shape[1]),
                    round(float(geo_bg_target.x.min().item()), 6),
                    round(float(geo_bg_target.x.max().item()), 6),
                    round(float(geo_bg_target.y.min().item()), 6),
                    round(float(geo_bg_target.y.max().item()), 6),
                    round(float(night_bg_lon_offset), 2),
                    round(float(night_bg_lat_offset), 2),
                    round(float(night_bg_zoom), 2),
                    str(night_bg_source_pref or "tiff_first").strip().lower(),
                )
                if (
                    preloaded_night_bg is None
                    or preloaded_night_bg_signature != current_signature
                ):
                    print(
                        f"[GeoColor BG] Preloading night background for frame {i}...")
                    preloaded_night_bg = _load_geocolor_night_background(
                        geo_bg_target,
                        night_bg_lon_offset=night_bg_lon_offset,
                        night_bg_lat_offset=night_bg_lat_offset,
                        night_bg_zoom=night_bg_zoom,
                        night_bg_source_pref=night_bg_source_pref,
                    )
                    preloaded_night_bg_signature = current_signature
                    print(
                        f"[GeoColor BG] Night background cached ({preloaded_night_bg.shape})"
                    )
                else:
                    print(
                        f"[GeoColor BG] Reusing cached night background for frame {i}"
                    )

            data = process_composite(
                current_ds,
                channel_key,
                sample.metpy.cartopy_crs,
                night_bg_lon_offset=night_bg_lon_offset,
                night_bg_lat_offset=night_bg_lat_offset,
                night_bg_zoom=night_bg_zoom,
                night_bg_source_pref=night_bg_source_pref,
                preloaded_night_bg=preloaded_night_bg,
                max_size=_composite_max_size,
            )
        except Exception as e:
            print(
                f"[ERROR] Error reading frame {i} (idx={idx}): {type(e).__name__}: {e}"
            )
            continue

        img_extent = _compute_image_extent(sample)

        if isinstance(data, str) and data == "NIGHT_MODE":
            for ds in current_ds.values():
                ds.close()
            if fig is not None:
                plt.close(fig)
            return "NIGHT_MODE", None

        # Compute per-frame timestamp
        primary_nc = band_files[req_bands[0]][idx]
        scan_time = parse_goes_time_from_filename(primary_nc)
        if scan_time is None:
            scan_time = datetime.now(timezone.utc)
        dt_local = scan_time.astimezone(tz.gettz("America/New_York"))
        timestamp_text = dt_local.strftime("%m/%d/%Y\n%I:%M %p %Z")

        _frame_start = _time.perf_counter()

        _anim_dpi = 150

        if fig is None:
            # === FIRST FRAME: Create figure + all static overlays ===
            fig = plt.figure(figsize=(12.8, 7.2), dpi=_anim_dpi)
            fig.subplots_adjust(
                left=figure_left_margin,
                right=1.0 - figure_right_margin,
                bottom=figure_bottom_margin,
                top=1.0 - figure_top_margin,
            )
            ax = fig.add_subplot(1, 1, 1, projection=sample.metpy.cartopy_crs)
            ax.set_facecolor(map_bg_color)

            if custom_extent:
                try:
                    ax.set_extent(
                        [
                            custom_extent[2],
                            custom_extent[3],
                            custom_extent[0],
                            custom_extent[1],
                        ],
                        crs=ccrs.PlateCarree(),
                    )
                except ValueError as e:
                    print(
                        f"[WARN] Invalid custom extent for satellite frame {i}: {type(e).__name__}: {e}; falling back to global"
                    )
                    ax.set_global()
            else:
                if all(np.isfinite(v) for v in img_extent):
                    try:
                        ax.set_extent(img_extent, crs=sample.metpy.cartopy_crs)
                    except ValueError as e:
                        print(
                            f"[WARN] Invalid projected extent for satellite frame {i}: {type(e).__name__}: {e}; falling back to global"
                        )
                        ax.set_global()
                else:
                    ax.set_global()

            x_min, x_max = ax.get_xlim()
            y_min, y_max = ax.get_ylim()
            x_span = x_max - x_min
            y_span = y_max - y_min
            ax.set_xlim(x_min - x_span * expand_left,
                        x_max + x_span * expand_right)
            ax.set_ylim(y_min - y_span * expand_bottom,
                        y_max + y_span * expand_top)

            # Plot satellite data (store artist reference for future updates)
            if channel_key in RGB_COMPOSITE_KEYS:
                sat_img_artist = ax.imshow(
                    data,
                    extent=img_extent,
                    origin="upper",
                    interpolation="bicubic",
                    zorder=zo["sat_image"],
                )
            elif channel_key == "Sandwich":
                sat_img_artist = ax.imshow(
                    data["vis"],
                    cmap="Greys_r",
                    extent=img_extent,
                    origin="upper",
                    interpolation="bicubic",
                    zorder=zo["sat_image"],
                )
                sat_ir_artist = ax.imshow(
                    data["ir"],
                    extent=img_extent,
                    origin="upper",
                    interpolation="bicubic",
                    zorder=zo["sat_image"] + 1,
                )
            else:
                target_norm = ABI_CHANNELS[channel_key].get("norm")
                interpolation_mode = (
                    "nearest" if str(channel_key).startswith(
                        "Channel13") else "bicubic"
                )
                sat_img_artist = ax.imshow(
                    data,
                    cmap=ABI_CHANNELS[channel_key]["cmap"],
                    norm=target_norm,
                    extent=img_extent,
                    origin="upper",
                    interpolation=interpolation_mode,
                    zorder=zo["sat_image"],
                )

            # Draw all static overlays (borders, cities, colorbar, HUD left, logo)
            _draw_static_overlays(ax, fig)

            # HUD right (dynamic - store reference for per-frame updates)
            hud_right_ann = ax.annotate(
                timestamp_text,
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
                zorder=zo["hud"],
            )
        else:
            # === SUBSEQUENT FRAMES: Update only dynamic content ===
            if channel_key in RGB_COMPOSITE_KEYS:
                sat_img_artist.set_data(data)
            elif channel_key == "Sandwich":
                sat_img_artist.set_data(data["vis"])
                sat_ir_artist.set_data(data["ir"])
            else:
                sat_img_artist.set_data(data)
            hud_right_ann.set_text(timestamp_text)

        # Capture frame via savefig → BytesIO → imread
        try:
            buf = io.BytesIO()
            fig.savefig(
                buf, format="png", dpi=_anim_dpi, bbox_inches="tight", pad_inches=0.1
            )
            buf.seek(0)
            frame_data = imageio.imread(buf)
            if frame_data.shape[-1] == 4:
                frame_data = frame_data[:, :, :3]
            frames.append(frame_data)

            # Save PNG only for last frame (used as preview/static image)
            is_last_frame = i == files_to_process - 1
            if is_last_frame or files_to_process == 1:
                save_path = os.path.join(frame_dir, f"f_{i:03d}.png")
                fig.savefig(
                    save_path, dpi=_anim_dpi, bbox_inches="tight", pad_inches=0.1
                )
        except Exception as e:
            print(
                f"[ERROR] Error capturing frame {i}: {type(e).__name__}: {e}")
            continue

        _frame_elapsed = _time.perf_counter() - _frame_start
        print(
            f"[Perf] Frame {i}/{files_to_process}: {_frame_elapsed:.2f}s {'(setup)' if i == 0 else '(update)'}"
        )

        for ds in current_ds.values():
            ds.close()

    # Clean up reused figure
    if fig is not None:
        plt.close(fig)

    if frames:
        try:
            from video_utils import save_animation

            datecode = datetime.now().strftime("%Y%m%d_%H%M%S")
            movie_path = os.path.join(output_dir, f"{datecode}_animation.mp4")
            save_animation(movie_path, frames, fps=fps)
            print(f"Animation saved to {movie_path}")
            return movie_path, os.path.join(
                frame_dir, f"f_{files_to_process - 1:03d}.png"
            )
        except Exception as e:
            print(
                f"[ERROR] Error creating/saving video: {type(e).__name__}: {e}")
            return None, None
    print("[WARN] No frames were successfully processed")
    return None, None


def generate_satellite_image(
    sat_id,
    channel_key,
    base_dir,
    region_name="default_region",
    custom_extent=None,
    logo_file=None,
    progress_callback=None,
    show_places=False,
    style_config=None,
):
    """
    Generate a single satellite image (latest scan) using the animation pipeline.
    Returns the path to the last frame PNG.
    """
    return generate_satellite_animation(
        sat_id,
        region_name,
        base_dir,
        channel_key,
        1,
        1,
        logo_file,
        custom_extent,
        progress_callback=progress_callback,
        show_places=show_places,
        style_config=style_config,
    )[1]
