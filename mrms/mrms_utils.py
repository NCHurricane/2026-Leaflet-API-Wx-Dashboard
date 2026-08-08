"""
MRMS Utilities
Image generation for Multi-Radar Multi-Sensor (MRMS) products.
"""

import importlib.util
import logging
import os
import gzip
import shutil
import threading
from typing import List, Tuple, Optional

import numpy as np
from app_core.atomic_io import atomic_output_path
from app_core.grib_decode import serialized_grib_decode

_LOGGER = logging.getLogger(__name__)

# GRIB2 reading

try:
    import xarray as xr

    CFGRIB_AVAILABLE = importlib.util.find_spec("cfgrib") is not None
    CFGRIB_IMPORT_ERROR = None
except ImportError as e:
    CFGRIB_AVAILABLE = False
    CFGRIB_IMPORT_ERROR = str(e)

# Serialize .grib2 refresh from .grib2.gz so parallel requests/workers do not
# read a partially-written uncompressed file.
_MRMS_GRIB_DECOMPRESS_LOCK = threading.Lock()


def warp_array_to_mercator(
    data: np.ma.MaskedArray,
    lat_1d: np.ndarray,
    lon_1d: np.ndarray,
    max_dim: int | None = None,
) -> tuple[np.ma.MaskedArray, list[float]]:
    """Reproject a flat (equirectangular) data array to Web Mercator (EPSG:3857)
    so pixels align with Leaflet's imageOverlay at any zoom level.

    Args:
        data:   2-D masked array, rows ordered N→S (origin=upper) or S→N (origin=lower).
        lat_1d: 1-D latitude coordinate array matching data rows.
        lon_1d: 1-D longitude coordinate array matching data cols.
        max_dim: Optional cap on the longest output dimension in pixels. The
            warp target is scaled down proportionally when the default output
            would exceed it; nearest-neighbor resampling keeps every output
            pixel an exact source data value.

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

    if max_dim and max(dst_width, dst_height) > max_dim:
        scale = float(max_dim) / float(max(dst_width, dst_height))
        capped_width = max(1, int(round(dst_width * scale)))
        capped_height = max(1, int(round(dst_height * scale)))
        dst_transform, dst_width, dst_height = (
            rasterio.warp.calculate_default_transform(
                src_crs,
                dst_crs,
                src_cols,
                src_rows,
                left=lon_min - 0.5 * dlon,
                bottom=lat_min - 0.5 * dlat,
                right=lon_max + 0.5 * dlon,
                top=lat_max + 0.5 * dlat,
                dst_width=capped_width,
                dst_height=capped_height,
            )
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

    # Compute the EXACT WGS84 bounds of the destination (Mercator) image.
    # calculate_default_transform may round dst_width/dst_height, so we derive
    # bounds from the actual dst_transform that produced the pixels we just
    # rendered. This ensures Leaflet's imageOverlay places the image at the
    # precise lat/lng corners that match the warped pixel content.
    dst_left = dst_transform.c                                 # Mercator x of left edge
    dst_top = dst_transform.f                                  # Mercator y of top edge
    dst_right = dst_left + dst_transform.a * dst_width         # Mercator x of right edge
    dst_bottom = dst_top + dst_transform.e * dst_height        # Mercator y of bottom edge (e is negative)

    wgs_west, wgs_south, wgs_east, wgs_north = rasterio.warp.transform_bounds(
        dst_crs, src_crs, dst_left, dst_bottom, dst_right, dst_top
    )
    actual_bounds = [wgs_west, wgs_east, wgs_south, wgs_north]
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

        with atomic_output_path(grib_path, suffix=".part") as temporary:
            with gzip.open(gz_path, "rb") as f_in:
                with temporary.open("wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)

            if not temporary.exists() or temporary.stat().st_size == 0:
                raise ValueError(f"Decompressed MRMS file is empty: {gz_path}")

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

    # The bundled Windows ecCodes runtime is not thread-enabled. Keep the
    # dataset open, materialization, and close within the shared decoder gate.
    with serialized_grib_decode():
        return _read_mrms_grib2_unlocked(
            grib_path,
            product=product,
            crop_extent=crop_extent,
            crop_slices=crop_slices,
        )


def _select_mrms_data_var(data_vars: list[str], product: str) -> str:
    product_key = "".join(
        character for character in str(product or "").lower()
        if character.isalnum()
    )
    if product_key:
        for variable in data_vars:
            variable_key = "".join(
                character for character in str(variable).lower()
                if character.isalnum()
            )
            if variable_key == product_key:
                return variable
    return data_vars[0]


def _read_mrms_grib2_unlocked(
    grib_path: str,
    *,
    product: str,
    crop_extent: Optional[List[float]] = None,
    crop_slices: Optional[Tuple[slice, slice]] = None,
) -> Tuple[np.ndarray, dict]:
    ds = None
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

        _LOGGER.debug("Reading MRMS GRIB2 file %s", grib_path)
        _LOGGER.debug("Dataset coordinates: %s", list(ds.coords.keys()))
        _LOGGER.debug("Dataset dimensions: %s", list(ds.sizes.keys()))
        _LOGGER.debug("Dataset variables: %s", list(ds.data_vars.keys()))

        # Try different latitude coordinate names
        for lat_name in ["latitude", "lat", "y"]:
            if lat_name in ds.coords or lat_name in ds.dims:
                lat_dim_name = lat_name
                lat_coord = ds[lat_name].values
                _LOGGER.debug(
                    "Found latitude coordinate %s with shape %s",
                    lat_name,
                    lat_coord.shape,
                )
                break

        # Try different longitude coordinate names
        for lon_name in ["longitude", "lon", "x"]:
            if lon_name in ds.coords or lon_name in ds.dims:
                lon_dim_name = lon_name
                lon_coord = ds[lon_name].values
                _LOGGER.debug(
                    "Found longitude coordinate %s with shape %s",
                    lon_name,
                    lon_coord.shape,
                )
                break

        if lat_coord is None:
            _LOGGER.warning(
                "Could not find latitude in MRMS dataset coordinates: %s",
                list(ds.coords.keys()),
            )
        if lon_coord is None:
            _LOGGER.warning(
                "Could not find longitude in MRMS dataset coordinates: %s",
                list(ds.coords.keys()),
            )

        # If we have 1D coordinates, keep them as-is for imshow
        # (pcolormesh needs 2D meshgrid, but imshow just needs extent)
        # Convert longitude from 0-360 to -180/180 if needed
        if lon_coord is not None and np.any(lon_coord > 180):
            lon_coord = lon_coord - 360

        data_da = ds[_select_mrms_data_var(data_vars, product)]
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

        return data_array, metadata

    except Exception as e:
        raise ValueError(f"Failed to read GRIB2 file {grib_path}: {e}")
    finally:
        if ds is not None:
            try:
                ds.close()
            except Exception:
                _LOGGER.warning(
                    "Failed to close MRMS dataset for %s",
                    grib_path,
                    exc_info=True,
                )
