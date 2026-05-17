"""NetCDF-to-Web-Mercator tile renderer for Satellite v2."""

from __future__ import annotations

import math
import os
import threading
import warnings
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import xarray as xr
from PIL import Image
from pyproj import CRS, Transformer
from scipy.interpolate import RegularGridInterpolator

from rasterio.crs import CRS as RioCRS
from rasterio.transform import from_bounds as rio_from_bounds
from rasterio.warp import Resampling, reproject as rio_reproject

from config.satellite_config import ABI_CHANNELS, RGB_COMPOSITE_KEYS
from config.satellite_v2_config import (
    SATELLITE_V2_TILE_SIZE,
    normalize_channel,
    source_channels_for_product,
)
from satellite_v2.composites import (
    reflectance,
    render_composite_rgb,
    visible_reflectance,
)


_SATELLITE_TILE_ALPHA = 230


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


_RENDERER_CACHE_MAX = _env_int("WX_SATELLITE_V2_RENDERER_CACHE_SIZE", 8, 0, 64)
_RENDERER_CACHE_LOCK = threading.RLock()
_RENDERER_CACHE: OrderedDict[tuple[object, ...], "SatelliteTileRenderer"] = (
    OrderedDict()
)
_RENDERER_KEY_LOCKS: dict[tuple[object, ...], threading.Lock] = {}


@dataclass
class SourceGrid:
    interpolator: RegularGridInterpolator
    transformer: Transformer

    def sample(self, lon_grid: np.ndarray, lat_grid: np.ndarray) -> np.ndarray:
        with np.errstate(invalid="ignore"):
            src_x, src_y = self.transformer.transform(lon_grid, lat_grid)
        points = np.column_stack([src_y.ravel(), src_x.ravel()])
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=RuntimeWarning)
            values = self.interpolator(points)
        return values.reshape(lon_grid.shape).astype(np.float32)


@dataclass
class SourceRaster:
    """GOES NetCDF source data for rasterio reprojection."""

    cmi: np.ndarray  # float32, shape (rows, cols), sorted ascending in both axes
    src_transform: object  # rasterio Affine transform in geostationary metres
    src_crs: object  # rasterio CRS for the GOES geostationary projection


@dataclass
class SatelliteTileRenderer:
    product_key: str
    source_grids: dict[str, SourceGrid]
    source_rasters: dict[str, SourceRaster]

    @classmethod
    def from_source(
        cls,
        source_file: str | Path,
        product_key: str = "Channel13",
    ) -> "SatelliteTileRenderer":
        product = normalize_channel(product_key)
        source_channel = source_channels_for_product(product)[0]
        return cls.from_sources(product, {source_channel: source_file})

    @classmethod
    def from_sources(
        cls,
        product_key: str,
        source_files: dict[str, str | Path],
    ) -> "SatelliteTileRenderer":
        product = normalize_channel(product_key)
        required = source_channels_for_product(product)
        missing = [channel for channel in required if channel not in source_files]
        if missing:
            raise ValueError(f"Missing source files for: {', '.join(missing)}")
        return _get_cached_renderer(cls, product, source_files, required)

    def render_tile(
        self,
        z: int,
        x: int,
        y: int,
        tile_size: int = SATELLITE_V2_TILE_SIZE,
    ) -> Image.Image:
        lon_grid, lat_grid = _tile_lon_lat_grid(int(z), int(x), int(y), tile_size)
        samples = {
            channel: grid.sample(lon_grid, lat_grid)
            for channel, grid in self.source_grids.items()
        }
        valid = _valid_mask(samples)
        if self.product_key in RGB_COMPOSITE_KEYS:
            rgb = render_composite_rgb(
                self.product_key,
                samples,
                lon_grid=lon_grid,
                lat_grid=lat_grid,
            )
            return _rgb_to_image(rgb, valid)

        product = ABI_CHANNELS[self.product_key]
        source_channel = source_channels_for_product(self.product_key)[0]
        values = samples[source_channel]
        if source_channel in {"Channel01", "Channel02", "Channel03"}:
            values = visible_reflectance(values)
        elif _is_reflectance_channel(source_channel):
            values = reflectance(values)
        cmap = product.get("cmap") or plt.get_cmap("Greys_r")
        norm = product.get("norm")
        return _colorize_scalar(values, valid, cmap, norm)

    def render_zoom_canvas(
        self,
        z: int,
        x_min: int,
        y_min: int,
        x_max: int,
        y_max: int,
        tile_size: int = SATELLITE_V2_TILE_SIZE,
    ) -> Image.Image:
        z = int(z)
        x_min, y_min, x_max, y_max = int(x_min), int(y_min), int(x_max), int(y_max)
        if x_max < x_min or y_max < y_min:
            raise ValueError("Invalid zoom canvas bounds.")

        canvas_w = (x_max - x_min + 1) * tile_size
        canvas_h = (y_max - y_min + 1) * tile_size
        scale = float(2**z)

        # --- compute Web Mercator bounds for this canvas block ---
        # tile coordinates → fractional world position → lon/lat → EPSG:3857
        lon_left = (x_min / scale) * 360.0 - 180.0
        lon_right = ((x_max + 1) / scale) * 360.0 - 180.0

        def _merc_to_lat(tile_y_frac: float) -> float:
            m = math.pi * (1.0 - 2.0 * tile_y_frac)
            return math.degrees(math.atan(math.sinh(m)))

        lat_top = _merc_to_lat(y_min / scale)
        lat_bottom = _merc_to_lat((y_max + 1) / scale)

        to_merc = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
        left_m, top_m = to_merc.transform(lon_left, lat_top)
        right_m, bottom_m = to_merc.transform(lon_right, lat_bottom)

        dst_crs = RioCRS.from_epsg(3857)
        dst_transform = rio_from_bounds(
            left_m, bottom_m, right_m, top_m, canvas_w, canvas_h
        )

        # --- reproject each source channel via GDAL (rasterio) ---
        def _warp_channel(raster: SourceRaster) -> np.ndarray:
            dst = np.full((canvas_h, canvas_w), np.nan, dtype=np.float32)
            rio_reproject(
                source=raster.cmi,
                destination=dst,
                src_transform=raster.src_transform,
                src_crs=raster.src_crs,
                dst_transform=dst_transform,
                dst_crs=dst_crs,
                resampling=Resampling.bilinear,
                src_nodata=np.nan,
                dst_nodata=np.nan,
            )
            return dst

        samples = {
            channel: _warp_channel(raster)
            for channel, raster in self.source_rasters.items()
        }

        # --- colorise (same logic as before) ---
        valid = _valid_mask(samples)
        if self.product_key in RGB_COMPOSITE_KEYS:
            # RGB composites need lon/lat for some products — derive them cheaply
            # from the canvas grid (same math as before, but only computed here if needed)
            pixels_x = np.arange(canvas_w, dtype=np.float64) + 0.5
            pixels_y = np.arange(canvas_h, dtype=np.float64) + 0.5
            tile_x = (x_min * tile_size + pixels_x) / (scale * tile_size)
            tile_y = (y_min * tile_size + pixels_y) / (scale * tile_size)
            lon_arr = tile_x * 360.0 - 180.0
            lat_arr = np.degrees(np.arctan(np.sinh(math.pi * (1.0 - 2.0 * tile_y))))
            lon_grid, lat_grid = np.meshgrid(lon_arr, lat_arr)
            rgb = render_composite_rgb(
                self.product_key,
                samples,
                lon_grid=lon_grid,
                lat_grid=lat_grid,
            )
            return _rgb_to_image(rgb, valid)

        product = ABI_CHANNELS[self.product_key]
        source_channel = source_channels_for_product(self.product_key)[0]
        values = samples[source_channel]
        if source_channel in {"Channel01", "Channel02", "Channel03"}:
            values = visible_reflectance(values)
        elif _is_reflectance_channel(source_channel):
            values = reflectance(values)
        cmap = product.get("cmap") or plt.get_cmap("Greys_r")
        norm = product.get("norm")
        return _colorize_scalar(values, valid, cmap, norm)


def _source_file_signature(source_file: str | Path) -> tuple[str, int, int]:
    path = Path(source_file).resolve()
    stat = path.stat()
    return str(path), int(stat.st_mtime_ns), int(stat.st_size)


def _renderer_cache_key(
    product_key: str,
    source_files: dict[str, str | Path],
    required: tuple[str, ...],
) -> tuple[object, ...]:
    return (
        product_key,
        tuple(
            (source_channel, *_source_file_signature(source_files[source_channel]))
            for source_channel in required
        ),
    )


def _load_renderer_uncached(
    renderer_cls: type["SatelliteTileRenderer"],
    product_key: str,
    source_files: dict[str, str | Path],
    required: tuple[str, ...],
) -> "SatelliteTileRenderer":
    grids = {
        source_channel: _load_source_grid(source_files[source_channel])
        for source_channel in required
    }
    rasters = {
        source_channel: _load_source_raster(source_files[source_channel])
        for source_channel in required
    }
    return renderer_cls(
        product_key=product_key,
        source_grids=grids,
        source_rasters=rasters,
    )


def _get_cached_renderer(
    renderer_cls: type["SatelliteTileRenderer"],
    product_key: str,
    source_files: dict[str, str | Path],
    required: tuple[str, ...],
) -> "SatelliteTileRenderer":
    if _RENDERER_CACHE_MAX <= 0:
        return _load_renderer_uncached(
            renderer_cls, product_key, source_files, required
        )

    key = _renderer_cache_key(product_key, source_files, required)
    with _RENDERER_CACHE_LOCK:
        cached = _RENDERER_CACHE.get(key)
        if cached is not None:
            _RENDERER_CACHE.move_to_end(key)
            return cached
        key_lock = _RENDERER_KEY_LOCKS.get(key)
        if key_lock is None:
            key_lock = threading.Lock()
            _RENDERER_KEY_LOCKS[key] = key_lock

    with key_lock:
        with _RENDERER_CACHE_LOCK:
            cached = _RENDERER_CACHE.get(key)
            if cached is not None:
                _RENDERER_CACHE.move_to_end(key)
                return cached

        renderer = _load_renderer_uncached(
            renderer_cls, product_key, source_files, required
        )

        with _RENDERER_CACHE_LOCK:
            _RENDERER_CACHE[key] = renderer
            _RENDERER_CACHE.move_to_end(key)
            while len(_RENDERER_CACHE) > _RENDERER_CACHE_MAX:
                old_key, _ = _RENDERER_CACHE.popitem(last=False)
                _RENDERER_KEY_LOCKS.pop(old_key, None)
            _RENDERER_KEY_LOCKS.pop(key, None)
        return renderer


def _load_source_grid(source_file: str | Path) -> SourceGrid:
    with xr.open_dataset(source_file, engine="netcdf4", mask_and_scale=True) as dataset:
        cmi_var = "CMI" if "CMI" in dataset else None
        if cmi_var is None and "Sectorized_CMI" in dataset:
            cmi_var = "Sectorized_CMI"
        if cmi_var is None:
            raise ValueError(f"Source file is missing CMI variable: {source_file}")
        if "x" not in dataset or "y" not in dataset:
            raise ValueError(
                f"Source file is missing x/y scan coordinates: {source_file}"
            )
        if "goes_imager_projection" not in dataset:
            raise ValueError(
                f"Source file is missing GOES projection metadata: {source_file}"
            )

        projection = dataset["goes_imager_projection"].attrs
        height = float(projection["perspective_point_height"])
        lon_origin = float(projection["longitude_of_projection_origin"])
        semi_major = float(projection["semi_major_axis"])
        semi_minor = float(projection["semi_minor_axis"])
        sweep = str(projection.get("sweep_angle_axis", "x"))

        x_values = np.asarray(dataset["x"].values, dtype=np.float64) * height
        y_values = np.asarray(dataset["y"].values, dtype=np.float64) * height
        cmi = np.asarray(dataset[cmi_var].values, dtype=np.float32)

    if cmi.ndim != 2:
        raise ValueError(f"CMI variable must be 2D: {source_file}")

    x_order = np.argsort(x_values)
    y_order = np.argsort(y_values)
    x_sorted = x_values[x_order]
    y_sorted = y_values[y_order]
    cmi_sorted = cmi[np.ix_(y_order, x_order)]
    cmi_sorted = np.where(np.isfinite(cmi_sorted), cmi_sorted, np.nan)

    geos_crs = CRS.from_proj4(
        "+proj=geos "
        f"+h={height} +lon_0={lon_origin} +sweep={sweep} "
        f"+a={semi_major} +b={semi_minor} +units=m +no_defs"
    )
    transformer = Transformer.from_crs("EPSG:4326", geos_crs, always_xy=True)
    interpolator = RegularGridInterpolator(
        (y_sorted, x_sorted),
        cmi_sorted,
        bounds_error=False,
        fill_value=np.nan,
    )
    return SourceGrid(interpolator=interpolator, transformer=transformer)


def _load_source_raster(source_file: str | Path) -> SourceRaster:
    """Load a GOES NetCDF source file into a SourceRaster for rasterio reprojection."""
    with xr.open_dataset(source_file, engine="netcdf4", mask_and_scale=True) as dataset:
        cmi_var = "CMI" if "CMI" in dataset else None
        if cmi_var is None and "Sectorized_CMI" in dataset:
            cmi_var = "Sectorized_CMI"
        if cmi_var is None:
            raise ValueError(f"Source file is missing CMI variable: {source_file}")
        if "x" not in dataset or "y" not in dataset:
            raise ValueError(
                f"Source file is missing x/y scan coordinates: {source_file}"
            )
        if "goes_imager_projection" not in dataset:
            raise ValueError(
                f"Source file is missing GOES projection metadata: {source_file}"
            )

        projection = dataset["goes_imager_projection"].attrs
        height = float(projection["perspective_point_height"])
        lon_origin = float(projection["longitude_of_projection_origin"])
        semi_major = float(projection["semi_major_axis"])
        semi_minor = float(projection["semi_minor_axis"])
        sweep = str(projection.get("sweep_angle_axis", "x"))

        x_values = np.asarray(dataset["x"].values, dtype=np.float64) * height
        y_values = np.asarray(dataset["y"].values, dtype=np.float64) * height
        cmi = np.asarray(dataset[cmi_var].values, dtype=np.float32)

    if cmi.ndim != 2:
        raise ValueError(f"CMI variable must be 2D: {source_file}")

    x_order = np.argsort(x_values)
    y_order = np.argsort(y_values)[::-1]
    x_sorted = x_values[x_order]
    y_sorted = y_values[y_order]
    cmi_sorted = cmi[np.ix_(y_order, x_order)]
    cmi_sorted = np.where(np.isfinite(cmi_sorted), cmi_sorted, np.nan)

    proj4 = (
        f"+proj=geos +h={height} +lon_0={lon_origin} +sweep={sweep} "
        f"+a={semi_major} +b={semi_minor} +units=m +no_defs"
    )
    src_crs = RioCRS.from_proj4(proj4)

    # Half-pixel outset so the transform represents pixel centres correctly.
    x_half = abs(x_sorted[-1] - x_sorted[0]) / (2 * (len(x_sorted) - 1))
    y_half = abs(y_sorted[0] - y_sorted[-1]) / (2 * (len(y_sorted) - 1))
    src_transform = rio_from_bounds(
        float(x_sorted[0]) - x_half,
        float(y_sorted[-1]) - y_half,
        float(x_sorted[-1]) + x_half,
        float(y_sorted[0]) + y_half,
        cmi_sorted.shape[1],
        cmi_sorted.shape[0],
    )

    return SourceRaster(cmi=cmi_sorted, src_transform=src_transform, src_crs=src_crs)


def _tile_lon_lat_grid(
    z: int,
    x: int,
    y: int,
    tile_size: int,
) -> tuple[np.ndarray, np.ndarray]:
    scale = float(2**z)
    pixels = np.arange(tile_size, dtype=np.float64) + 0.5
    tile_x = (float(x) * tile_size + pixels) / (scale * tile_size)
    tile_y = (float(y) * tile_size + pixels) / (scale * tile_size)
    lon = tile_x * 360.0 - 180.0
    mercator = math.pi * (1.0 - 2.0 * tile_y)
    lat = np.degrees(np.arctan(np.sinh(mercator)))
    lon_grid, lat_grid = np.meshgrid(lon, lat)
    return lon_grid, lat_grid


def _is_reflectance_channel(source_channel: str) -> bool:
    digits = "".join(ch for ch in source_channel if ch.isdigit())
    return bool(digits) and int(digits) <= 6


def _valid_mask(samples: dict[str, np.ndarray]) -> np.ndarray:
    mask = None
    for values in samples.values():
        finite = np.isfinite(values)
        mask = finite if mask is None else mask & finite
    if mask is None:
        raise ValueError("Satellite v2 renderer has no source samples.")
    return mask


def _rgb_to_image(rgb: np.ndarray, valid: np.ndarray) -> Image.Image:
    rgba = np.zeros((*rgb.shape[:2], 4), dtype=np.uint8)
    safe_rgb = np.where(valid[:, :, np.newaxis], rgb, 0.0)
    rgba[:, :, :3] = np.clip(safe_rgb * 255.0, 0, 255).astype(np.uint8)
    rgba[:, :, 3] = np.where(valid, _SATELLITE_TILE_ALPHA, 0).astype(np.uint8)
    return Image.fromarray(rgba, mode="RGBA")


def _colorize_scalar(values: np.ndarray, valid: np.ndarray, cmap, norm) -> Image.Image:
    if norm is None:
        safe_values = np.where(valid, values, 0.0)
        finite = np.isfinite(safe_values)
        if finite.any():
            vmin = float(np.nanmin(safe_values[finite]))
            vmax = float(np.nanmax(safe_values[finite]))
            normalized = (safe_values - vmin) / max(vmax - vmin, 1e-6)
        else:
            normalized = np.zeros_like(safe_values, dtype=np.float32)
        rgba = cmap(normalized, bytes=True)
    else:
        fallback = getattr(norm, "vmax", 1.0)
        safe_values = np.where(valid, values, fallback)
        rgba = cmap(norm(safe_values), bytes=True)
    rgba[..., 3] = np.where(valid, _SATELLITE_TILE_ALPHA, 0).astype(np.uint8)
    return Image.fromarray(rgba, mode="RGBA")
