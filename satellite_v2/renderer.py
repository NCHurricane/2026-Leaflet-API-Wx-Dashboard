"""NetCDF-to-Web-Mercator tile renderer for Satellite v2."""

from __future__ import annotations

import math
import re
import threading
import time
from collections import OrderedDict
from contextlib import ExitStack
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Sequence

import matplotlib.pyplot as plt
import numpy as np
import xarray as xr
from PIL import Image
from pyproj import Transformer

from rasterio.crs import CRS as RioCRS
from rasterio.transform import from_bounds as rio_from_bounds
from rasterio.warp import Resampling, reproject as rio_reproject

from config.satellite_platforms import SATELLITE_PLATFORMS
from config.satellite_v2_config import (
    ABI_CHANNELS,
    RGB_COMPOSITE_KEYS,
    SATELLITE_V2_AHI_MAX_GRID,
    SATELLITE_V2_AMI_MAX_GRID,
    SATELLITE_V2_FCI_MAX_GRID,
    SATELLITE_V2_GOES_FULLDISK_MAX_GRID,
    SATELLITE_V2_NETCDF_CACHE_SIZE,
    SATELLITE_V2_RENDERER_CACHE_SIZE,
    SATELLITE_V2_SOURCE_RASTER_CACHE_MB,
    SATELLITE_V2_TILE_SIZE,
    normalize_channel,
    source_channels_for_product,
)
from satellite_v2.ahi_hsd import load_ahi_raster
from satellite_v2._bench_timing import add_timing_ms, bench_enabled
from satellite_v2.composites import (
    COMPOSITES_REQUIRING_LONLAT,
    render_composite_rgb,
    scalar_reflectance,
)


_SATELLITE_FILLED_ALPHA = 255
_SATELLITE_OVERLAY_ALPHA = 230

# GOES ABI L2 aerosol products. ADP renders as a categorical smoke/dust mask
# (nearest-neighbour resample so the 0/1/2/3 codes never smear); AOD renders
# as a continuous field with a value-driven alpha ramp so clear air stays
# transparent and plumes read opaque.
_ADP_CATEGORICAL_KEYS = frozenset({"AerosolDetection"})
_AOD_KEYS = frozenset({"AerosolOpticalDepth"})
_SPARSE_SCALAR_OVERLAY_KEYS = frozenset({"FireRadiativePower"})
# Categorical LUT — colours must match the AerosolDetection interpretive
# legend in config.satellite_v2_config.
_ADP_SMOKE_RGB = (0x39, 0xD0, 0xD8)
_ADP_DUST_RGB = (0xE8, 0xA3, 0x3D)
_ADP_BOTH_RGB = (0xC4, 0x4D, 0xFF)
# Opacity per DQF confidence level, indexed 0=high, 1=medium, 2=low, so
# high-confidence detections read solid and low-confidence edges read faint.
_ADP_CONFIDENCE_ALPHA = (210, 140, 80)
# AOD alpha ramp: fully transparent at/below _AOD_ALPHA_MIN, fully opaque
# at/above _AOD_ALPHA_FULL (optical depth at 550 nm).
_AOD_ALPHA_MIN = 0.10
_AOD_ALPHA_FULL = 0.40


# NetCDF dataset memory cache (keyed by file path, avoid re-reading from disk)
_NETCDF_CACHE: OrderedDict[str, tuple[xr.Dataset, int]] = OrderedDict()
_NETCDF_CACHE_LOCK = threading.RLock()
_NETCDF_CACHE_MAX = SATELLITE_V2_NETCDF_CACHE_SIZE


_RENDERER_CACHE_MAX = SATELLITE_V2_RENDERER_CACHE_SIZE
_RENDERER_CACHE_LOCK = threading.RLock()
_RENDERER_CACHE: OrderedDict[tuple[object, ...], "SatelliteTileRenderer"] = (
    OrderedDict()
)
_RENDERER_KEY_LOCKS: dict[tuple[object, ...], threading.Lock] = {}


_SOURCE_RASTER_CACHE_MAX_BYTES = SATELLITE_V2_SOURCE_RASTER_CACHE_MB * 1024 * 1024
_SOURCE_RASTER_CACHE_LOCK = threading.RLock()
_SOURCE_RASTER_CACHE: OrderedDict[tuple[object, ...], "SourceRaster"] = OrderedDict()
_SOURCE_RASTER_CACHE_BYTES = 0
_SOURCE_RASTER_KEY_LOCKS: dict[tuple[object, ...], threading.Lock] = {}


@dataclass
class SourceRaster:
    """GOES NetCDF source data for rasterio reprojection."""

    cmi: np.ndarray  # float32, shape (rows, cols), sorted ascending in both axes
    src_transform: object  # rasterio Affine transform in geostationary metres
    src_crs: object  # rasterio CRS for the GOES geostationary projection
    observation_time: datetime | None = None
    satellite_longitude: float | None = None
    satellite_height_km: float | None = None


@dataclass
class SatelliteTileRenderer:
    product_key: str
    source_rasters: dict[str, SourceRaster]
    source_files: dict[str, Path] = field(default_factory=dict)
    instrument: str | None = None

    @classmethod
    def from_source(
        cls,
        source_file: str | Path,
        product_key: str = "Channel13",
        sat_id: str | None = None,
    ) -> "SatelliteTileRenderer":
        product = normalize_channel(product_key)
        source_channel = source_channels_for_product(product)[0]
        return cls.from_sources(
            product, {source_channel: source_file}, sat_id=sat_id
        )

    @classmethod
    def from_sources(
        cls,
        product_key: str,
        source_files: dict[str, str | Path],
        sat_id: str | None = None,
        destination_zoom: int | None = None,
    ) -> "SatelliteTileRenderer":
        product = normalize_channel(product_key)
        required = source_channels_for_product(product)
        missing = [channel for channel in required if channel not in source_files]
        if missing:
            raise ValueError(f"Missing source files for: {', '.join(missing)}")
        instrument = SATELLITE_PLATFORMS.get(str(sat_id or "").strip().lower(), {}).get(
            "instrument"
        )
        return _get_cached_renderer(
            cls,
            product,
            source_files,
            required,
            instrument,
            destination_zoom=destination_zoom,
        )

    def render_tile(
        self,
        z: int,
        x: int,
        y: int,
        tile_size: int = SATELLITE_V2_TILE_SIZE,
    ) -> Image.Image:
        # Single-tile render is just a 1x1 zoom canvas, so it reuses the same
        # GDAL-backed (rasterio) reprojection path as canvas warming.
        return self.render_zoom_canvas(
            int(z), int(x), int(y), int(x), int(y), tile_size=tile_size
        )

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
        # Categorical products (ADP smoke/dust codes) must use nearest so the
        # integer codes are never blended into meaningless fractional values.
        resampling = (
            Resampling.nearest
            if self.product_key in _ADP_CATEGORICAL_KEYS
            else Resampling.bilinear
        )

        def _warp_channel(raster: SourceRaster) -> np.ndarray:
            dst = np.full((canvas_h, canvas_w), np.nan, dtype=np.float32)
            rio_reproject(
                source=raster.cmi,
                destination=dst,
                src_transform=raster.src_transform,
                src_crs=raster.src_crs,
                dst_transform=dst_transform,
                dst_crs=dst_crs,
                resampling=resampling,
                src_nodata=np.nan,
                dst_nodata=np.nan,
            )
            return dst

        samples = {}
        for channel, raster in self.source_rasters.items():
            warp_started = time.perf_counter() if bench_enabled() else 0.0
            samples[channel] = _warp_channel(raster)
            if bench_enabled():
                add_timing_ms(
                    f"warp_ms{{{channel}}}",
                    (time.perf_counter() - warp_started) * 1000.0,
                )

        # --- colorise (same logic as before) ---
        composite_started = time.perf_counter() if bench_enabled() else 0.0
        try:
            return self._composite_image(
                samples, z, x_min, y_min, canvas_w, canvas_h, tile_size
            )
        finally:
            if bench_enabled():
                add_timing_ms(
                    "composite_ms",
                    (time.perf_counter() - composite_started) * 1000.0,
                )

    def _composite_image(
        self,
        samples: dict[str, np.ndarray],
        z: int,
        x_min: int,
        y_min: int,
        canvas_w: int,
        canvas_h: int,
        tile_size: int,
    ) -> Image.Image:
        valid = _valid_mask(samples)
        if self.product_key in RGB_COMPOSITE_KEYS:
            lon_grid = lat_grid = None
            if self.product_key in COMPOSITES_REQUIRING_LONLAT:
                lon_grid, lat_grid = _canvas_lon_lat_grid(
                    z, x_min, y_min, canvas_w, canvas_h, tile_size
                )
            geometry_source = next(iter(self.source_rasters.values()))
            rgb = render_composite_rgb(
                self.product_key,
                samples,
                lon_grid=lon_grid,
                lat_grid=lat_grid,
                instrument=self.instrument,
                observation_time=geometry_source.observation_time,
                satellite_longitude=geometry_source.satellite_longitude,
                satellite_height_km=geometry_source.satellite_height_km,
            )
            return _rgb_to_image(rgb, valid)

        product = ABI_CHANNELS[self.product_key]
        source_channel = source_channels_for_product(self.product_key)[0]
        values = samples[source_channel]
        if self.product_key in _ADP_CATEGORICAL_KEYS:
            return _colorize_categorical(values, valid)
        if _is_reflectance_channel(source_channel):
            values = scalar_reflectance(values, source_channel=source_channel)
        cmap = product.get("cmap") or plt.get_cmap("Greys_r")
        norm = product.get("norm")
        if self.product_key in _AOD_KEYS:
            return _colorize_aod(values, valid, cmap, norm)
        alpha = (
            _SATELLITE_OVERLAY_ALPHA
            if self.product_key in _SPARSE_SCALAR_OVERLAY_KEYS
            else _SATELLITE_FILLED_ALPHA
        )
        return _colorize_scalar(values, valid, cmap, norm, alpha=alpha)


def _source_file_signature(source_file: str | Path) -> tuple[str, int, int]:
    path = Path(source_file).resolve()
    stat = path.stat()
    return str(path), int(stat.st_mtime_ns), int(stat.st_size)


def _zoom_derived_grid_cap(destination_zoom: int | None) -> int:
    if destination_zoom is None or int(destination_zoom) >= 7:
        return 0
    if int(destination_zoom) <= 4:
        return 2048
    return 4096


def _source_raster_grid_cap(
    path: Path,
    source_channel: str,
    destination_zoom: int | None = None,
) -> int:
    if _is_ahi_hsd_file(path):
        platform_cap = SATELLITE_V2_AHI_MAX_GRID
    elif _is_fci_chunk_file(path):
        platform_cap = SATELLITE_V2_FCI_MAX_GRID
    elif _is_ami_l1b_file(path):
        platform_cap = SATELLITE_V2_AMI_MAX_GRID
    elif (
        path.suffix.lower() == ".nc"
        and not _is_gmgsi_file(path)
        and source_channel not in {"ADP", "AOD", "FRP"}
    ):
        platform_cap = SATELLITE_V2_GOES_FULLDISK_MAX_GRID
    else:
        platform_cap = 0
    zoom_cap = _zoom_derived_grid_cap(destination_zoom)
    if platform_cap and zoom_cap:
        return min(platform_cap, zoom_cap)
    return platform_cap


def _source_raster_cache_key(
    source_file: str | Path,
    source_channel: str,
    destination_zoom: int | None = None,
) -> tuple[object, ...]:
    path = Path(source_file)
    return (
        *_source_file_signature(path),
        source_channel,
        _source_raster_grid_cap(path, source_channel, destination_zoom),
    )


def _source_raster_bytes(raster: SourceRaster) -> int:
    return int(getattr(raster.cmi, "nbytes", 0) or 0)


def _evict_renderers_holding(raster: SourceRaster) -> None:
    with _RENDERER_CACHE_LOCK:
        stale_keys = [
            key
            for key, candidate in _RENDERER_CACHE.items()
            if any(value is raster for value in candidate.source_rasters.values())
        ]
        for key in stale_keys:
            _RENDERER_CACHE.pop(key, None)


def _cache_source_raster(
    key: tuple[object, ...], raster: SourceRaster
) -> None:
    global _SOURCE_RASTER_CACHE_BYTES
    weight = _source_raster_bytes(raster)
    if _SOURCE_RASTER_CACHE_MAX_BYTES <= 0 or weight > _SOURCE_RASTER_CACHE_MAX_BYTES:
        return
    evicted: list[SourceRaster] = []
    with _SOURCE_RASTER_CACHE_LOCK:
        replaced = _SOURCE_RASTER_CACHE.pop(key, None)
        if replaced is not None:
            _SOURCE_RASTER_CACHE_BYTES -= _source_raster_bytes(replaced)
        _SOURCE_RASTER_CACHE[key] = raster
        _SOURCE_RASTER_CACHE_BYTES += weight
        while (
            _SOURCE_RASTER_CACHE
            and _SOURCE_RASTER_CACHE_BYTES > _SOURCE_RASTER_CACHE_MAX_BYTES
        ):
            old_key, old_raster = _SOURCE_RASTER_CACHE.popitem(last=False)
            _SOURCE_RASTER_CACHE_BYTES -= _source_raster_bytes(old_raster)
            old_lock = _SOURCE_RASTER_KEY_LOCKS.get(old_key)
            if old_lock is not None and not old_lock.locked():
                _SOURCE_RASTER_KEY_LOCKS.pop(old_key, None)
            evicted.append(old_raster)
    for old_raster in evicted:
        _evict_renderers_holding(old_raster)


def _cached_source_raster(key: tuple[object, ...]) -> SourceRaster | None:
    with _SOURCE_RASTER_CACHE_LOCK:
        raster = _SOURCE_RASTER_CACHE.get(key)
        if raster is not None:
            _SOURCE_RASTER_CACHE.move_to_end(key)
        return raster


def _source_raster_key_lock(key: tuple[object, ...]) -> threading.Lock:
    with _SOURCE_RASTER_CACHE_LOCK:
        lock = _SOURCE_RASTER_KEY_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _SOURCE_RASTER_KEY_LOCKS[key] = lock
        return lock


def _load_source_raster_cached(
    source_file: str | Path,
    source_channel: str,
    destination_zoom: int | None = None,
) -> tuple[SourceRaster, bool]:
    grid_cap = _source_raster_grid_cap(
        Path(source_file), source_channel, destination_zoom
    )
    if _SOURCE_RASTER_CACHE_MAX_BYTES <= 0:
        if destination_zoom is None:
            return _load_source_raster(source_file, source_channel), True
        return _load_source_raster(source_file, source_channel, max_grid=grid_cap), True
    key = _source_raster_cache_key(source_file, source_channel, destination_zoom)
    cached = _cached_source_raster(key)
    if cached is not None:
        return cached, False
    key_lock = _source_raster_key_lock(key)
    with key_lock:
        cached = _cached_source_raster(key)
        if cached is not None:
            return cached, False
        raster = (
            _load_source_raster(source_file, source_channel)
            if destination_zoom is None
            else _load_source_raster(
                source_file, source_channel, max_grid=grid_cap
            )
        )
        _cache_source_raster(key, raster)
    with _SOURCE_RASTER_CACHE_LOCK:
        if (
            key not in _SOURCE_RASTER_CACHE
            and _SOURCE_RASTER_KEY_LOCKS.get(key) is key_lock
        ):
            _SOURCE_RASTER_KEY_LOCKS.pop(key, None)
    return raster, True


def _load_fci_source_rasters_cached(
    primary_chunk: Path,
    source_channels: Sequence[str],
    destination_zoom: int | None = None,
) -> tuple[dict[str, SourceRaster], set[str]]:
    grid_cap = _source_raster_grid_cap(
        primary_chunk, source_channels[0], destination_zoom
    )
    if _SOURCE_RASTER_CACHE_MAX_BYTES <= 0:
        loaded = (
            _load_fci_source_rasters(primary_chunk, source_channels)
            if destination_zoom is None
            else _load_fci_source_rasters(
                primary_chunk, source_channels, max_grid=grid_cap
            )
        )
        return loaded, set(source_channels)
    keys = {
        channel: _source_raster_cache_key(
            primary_chunk, channel, destination_zoom
        )
        for channel in source_channels
    }
    results = {
        channel: raster
        for channel, key in keys.items()
        if (raster := _cached_source_raster(key)) is not None
    }
    missing = [channel for channel in source_channels if channel not in results]
    if not missing:
        return results, set()
    parsed_channels: set[str] = set()
    keyed_locks = sorted(
        ((keys[channel], _source_raster_key_lock(keys[channel])) for channel in missing),
        key=lambda item: repr(item[0]),
    )
    with ExitStack() as stack:
        for _, lock in keyed_locks:
            stack.enter_context(lock)
        missing = []
        for channel in source_channels:
            if channel in results:
                continue
            cached = _cached_source_raster(keys[channel])
            if cached is not None:
                results[channel] = cached
            else:
                missing.append(channel)
        if missing:
            loaded = (
                _load_fci_source_rasters(primary_chunk, missing)
                if destination_zoom is None
                else _load_fci_source_rasters(
                    primary_chunk, missing, max_grid=grid_cap
                )
            )
            parsed_channels.update(loaded)
            for channel, raster in loaded.items():
                _cache_source_raster(keys[channel], raster)
                results[channel] = raster
    with _SOURCE_RASTER_CACHE_LOCK:
        for key, lock in keyed_locks:
            if (
                key not in _SOURCE_RASTER_CACHE
                and _SOURCE_RASTER_KEY_LOCKS.get(key) is lock
            ):
                _SOURCE_RASTER_KEY_LOCKS.pop(key, None)
    return results, parsed_channels


def _touch_renderer_source_rasters(renderer: SatelliteTileRenderer) -> None:
    raster_ids = {id(raster) for raster in renderer.source_rasters.values()}
    with _SOURCE_RASTER_CACHE_LOCK:
        for key, raster in list(_SOURCE_RASTER_CACHE.items()):
            if id(raster) in raster_ids:
                _SOURCE_RASTER_CACHE.move_to_end(key)


def _renderer_sources_are_cached(renderer: SatelliteTileRenderer) -> bool:
    if _SOURCE_RASTER_CACHE_MAX_BYTES <= 0:
        return True
    cached_ids = {id(raster) for raster in _SOURCE_RASTER_CACHE.values()}
    return all(id(raster) in cached_ids for raster in renderer.source_rasters.values())


def _renderer_cache_key(
    product_key: str,
    source_files: dict[str, str | Path],
    required: tuple[str, ...],
    instrument: str | None,
    destination_zoom: int | None = None,
) -> tuple[object, ...]:
    return (
        product_key,
        instrument,
        tuple(
            (source_channel, *_source_file_signature(source_files[source_channel]))
            for source_channel in required
        ),
        tuple(
            (
                source_channel,
                _source_raster_grid_cap(
                    Path(source_files[source_channel]),
                    source_channel,
                    destination_zoom,
                ),
            )
            for source_channel in required
        ),
    )


def _load_renderer_uncached(
    renderer_cls: type["SatelliteTileRenderer"],
    product_key: str,
    source_files: dict[str, str | Path],
    required: tuple[str, ...],
    instrument: str | None,
    destination_zoom: int | None = None,
) -> "SatelliteTileRenderer":
    rasters = {}
    remaining = list(required)
    fci_groups: dict[Path, list[str]] = {}
    for source_channel in required:
        source_path = Path(source_files[source_channel])
        if _is_fci_chunk_file(source_path):
            fci_groups.setdefault(source_path.parent.resolve(), []).append(source_channel)

    for channels in fci_groups.values():
        if len(channels) < 2:
            continue
        parse_started = time.perf_counter() if bench_enabled() else 0.0
        loaded_rasters, parsed_channels = _load_fci_source_rasters_cached(
            Path(source_files[channels[0]]),
            channels,
            destination_zoom=destination_zoom,
        )
        rasters.update(loaded_rasters)
        if bench_enabled() and parsed_channels:
            add_timing_ms(
                "parse_ms{FCI-batch}",
                (time.perf_counter() - parse_started) * 1000.0,
            )
        remaining = [channel for channel in remaining if channel not in channels]

    for source_channel in remaining:
        parse_started = time.perf_counter() if bench_enabled() else 0.0
        raster, parsed = _load_source_raster_cached(
            source_files[source_channel],
            source_channel,
            destination_zoom=destination_zoom,
        )
        rasters[source_channel] = raster
        if bench_enabled() and parsed:
            add_timing_ms(
                f"parse_ms{{{source_channel}}}",
                (time.perf_counter() - parse_started) * 1000.0,
            )
    return renderer_cls(
        product_key=product_key,
        source_rasters=rasters,
        source_files={
            source_channel: Path(source_files[source_channel])
            for source_channel in required
        },
        instrument=instrument,
    )


def _get_cached_renderer(
    renderer_cls: type["SatelliteTileRenderer"],
    product_key: str,
    source_files: dict[str, str | Path],
    required: tuple[str, ...],
    instrument: str | None = None,
    destination_zoom: int | None = None,
) -> "SatelliteTileRenderer":
    if _RENDERER_CACHE_MAX <= 0:
        return _load_renderer_uncached(
            renderer_cls,
            product_key,
            source_files,
            required,
            instrument,
            destination_zoom,
        )

    key = _renderer_cache_key(
        product_key,
        source_files,
        required,
        instrument,
        destination_zoom,
    )
    with _RENDERER_CACHE_LOCK:
        cached = _RENDERER_CACHE.get(key)
        if cached is not None:
            _RENDERER_CACHE.move_to_end(key)
        else:
            key_lock = _RENDERER_KEY_LOCKS.get(key)
            if key_lock is None:
                key_lock = threading.Lock()
                _RENDERER_KEY_LOCKS[key] = key_lock
    if cached is not None:
        _touch_renderer_source_rasters(cached)
        return cached

    with key_lock:
        with _RENDERER_CACHE_LOCK:
            cached = _RENDERER_CACHE.get(key)
            if cached is not None:
                _RENDERER_CACHE.move_to_end(key)
        if cached is not None:
            _touch_renderer_source_rasters(cached)
            return cached

        renderer = _load_renderer_uncached(
            renderer_cls,
            product_key,
            source_files,
            required,
            instrument,
            destination_zoom,
        )

        # Keep source membership stable through renderer insertion. Otherwise a
        # concurrent source eviction could miss this renderer and leave its
        # strong raster reference outside the byte-accounted cache.
        with _SOURCE_RASTER_CACHE_LOCK:
            cache_renderer = _renderer_sources_are_cached(renderer)
            with _RENDERER_CACHE_LOCK:
                if cache_renderer:
                    _RENDERER_CACHE[key] = renderer
                    _RENDERER_CACHE.move_to_end(key)
                    while len(_RENDERER_CACHE) > _RENDERER_CACHE_MAX:
                        old_key, _ = _RENDERER_CACHE.popitem(last=False)
                        _RENDERER_KEY_LOCKS.pop(old_key, None)
                _RENDERER_KEY_LOCKS.pop(key, None)
        return renderer


def _load_netcdf_dataset(source_file: str | Path) -> xr.Dataset:
    """Load NetCDF dataset from cache or disk, reusing opened datasets to avoid re-reads."""
    source_path = Path(source_file).resolve()
    cache_key = str(source_path)
    file_mtime = int(source_path.stat().st_mtime_ns)

    with _NETCDF_CACHE_LOCK:
        cached = _NETCDF_CACHE.get(cache_key)
        if cached is not None:
            cached_dataset, cached_mtime = cached
            if cached_mtime == file_mtime:
                _NETCDF_CACHE.move_to_end(cache_key)
                return cached_dataset

        dataset = xr.open_dataset(source_path, engine="netcdf4", mask_and_scale=True)
        replaced = _NETCDF_CACHE.pop(cache_key, None)
        _NETCDF_CACHE[cache_key] = (dataset, file_mtime)
        if replaced is not None:
            try:
                replaced[0].close()
            except Exception:
                pass

        if len(_NETCDF_CACHE) > _NETCDF_CACHE_MAX:
            old_key, (old_ds, _) = _NETCDF_CACHE.popitem(last=False)
            try:
                old_ds.close()
            except Exception:
                pass

        return dataset


def _parse_observation_time(dataset: xr.Dataset, path: Path) -> datetime | None:
    """Read a UTC frame time from GOES metadata, with filename fallback."""
    for attribute in (
        "time_coverage_start",
        "start_date_time",
        "date_created",
    ):
        value = dataset.attrs.get(attribute)
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    # ABI filenames encode start time as sYYYYJJJHHMMSSf, where JJJ is
    # day-of-year and the trailing fractional-second digits are optional.
    match = re.search(
        r"_s(\d{4})(\d{3})(\d{2})(\d{2})(\d{2})(\d*)_",
        path.name,
    )
    if match is None:
        return None
    year, day_of_year, hour, minute, second, fraction = match.groups()
    microseconds = int((fraction + "000000")[:6]) if fraction else 0
    return datetime(int(year), 1, 1, tzinfo=timezone.utc) + timedelta(
        days=int(day_of_year) - 1,
        hours=int(hour),
        minutes=int(minute),
        seconds=int(second),
        microseconds=microseconds,
    )


def _is_ahi_hsd_file(path: Path) -> bool:
    name = path.name.lower()
    return name.endswith(".dat") or name.endswith(".dat.bz2")


def _is_ami_l1b_file(path: Path) -> bool:
    return (
        "gk2a_ami_le1b_" in path.name.lower()
        and path.suffix.lower() == ".nc"
    )


def _is_gmgsi_file(path: Path) -> bool:
    return path.name.upper().startswith("GLOBCOMP") and path.suffix.lower() == ".nc"


def _load_gmgsi_source_raster(path: Path, source_channel: str) -> SourceRaster:
    from satellite_v2.gmgsi_nc import load_gmgsi_raster

    raster = load_gmgsi_raster(_load_netcdf_dataset(path), source_channel)
    return SourceRaster(
        cmi=raster.values,
        src_transform=raster.src_transform,
        src_crs=raster.src_crs,
        observation_time=raster.observation_time,
    )


def _load_ami_source_raster(
    path: Path, source_channel: str, max_grid: int | None = None
) -> SourceRaster:
    from satellite_v2.ami_nc import load_ami_raster

    raster = load_ami_raster(
        _load_netcdf_dataset(path), source_channel, max_grid=max_grid
    )
    return SourceRaster(
        cmi=raster.values,
        src_transform=raster.src_transform,
        src_crs=raster.src_crs,
        observation_time=raster.observation_time,
        satellite_longitude=raster.satellite_longitude,
        satellite_height_km=raster.satellite_height_km,
    )


def _load_ahi_source_raster(
    primary_segment: Path, max_grid: int | None = None
) -> SourceRaster:
    """Load Himawari AHI HSD segments into a SourceRaster.

    The provider hands over one segment path; the sibling segments live in
    the same per-frame source cache directory.
    """
    segment_paths = sorted(
        path
        for path in primary_segment.parent.iterdir()
        if _is_ahi_hsd_file(path)
    )
    raster = load_ahi_raster(
        segment_paths, max_grid=max_grid or SATELLITE_V2_AHI_MAX_GRID
    )
    return SourceRaster(
        cmi=raster.values,
        src_transform=raster.src_transform,
        src_crs=raster.src_crs,
    )


def _load_seviri_source_raster(nat_path: Path, source_channel: str) -> SourceRaster:
    """Load one SEVIRI channel from a .nat bundle into a SourceRaster."""
    from satellite_v2.seviri_nat import load_seviri_raster

    raster = load_seviri_raster(nat_path, source_channel)
    return SourceRaster(
        cmi=raster.values,
        src_transform=raster.src_transform,
        src_crs=raster.src_crs,
    )


def _geos_scan_source_raster(
    dataset: xr.Dataset, values: np.ndarray, path: Path
) -> SourceRaster:
    """Build a SourceRaster from a GOES fixed-grid scan array.

    Shared by the ADP/AOD loaders: they carry the same ``goes_imager_projection``
    + ``x``/``y`` scan-angle georeferencing as CMIP imagery, differing only in
    which variable supplies the pixel values. ``values`` is already a
    materialised 2D array (aerosol grids are 2 km, so no decimation applies).
    """
    if "goes_imager_projection" not in dataset or "x" not in dataset or "y" not in dataset:
        raise ValueError(f"Aerosol source file is missing GOES grid metadata: {path}")

    projection = dataset["goes_imager_projection"].attrs
    height = float(projection["perspective_point_height"])
    lon_origin = float(projection["longitude_of_projection_origin"])
    semi_major = float(projection["semi_major_axis"])
    semi_minor = float(projection["semi_minor_axis"])
    sweep = str(projection.get("sweep_angle_axis", "x"))

    x_values = np.asarray(dataset["x"].values, dtype=np.float64) * height
    y_values = np.asarray(dataset["y"].values, dtype=np.float64) * height

    x_order = np.argsort(x_values)
    y_order = np.argsort(y_values)[::-1]
    x_sorted = x_values[x_order]
    y_sorted = y_values[y_order]
    grid = np.asarray(values, dtype=np.float32)[np.ix_(y_order, x_order)]
    grid = np.where(np.isfinite(grid), grid, np.nan)

    proj4 = (
        f"+proj=geos +h={height} +lon_0={lon_origin} +sweep={sweep} "
        f"+a={semi_major} +b={semi_minor} +units=m +no_defs"
    )
    src_crs = RioCRS.from_proj4(proj4)

    x_half = abs(x_sorted[-1] - x_sorted[0]) / (2 * (len(x_sorted) - 1))
    y_half = abs(y_sorted[0] - y_sorted[-1]) / (2 * (len(y_sorted) - 1))
    src_transform = rio_from_bounds(
        float(x_sorted[0]) - x_half,
        float(y_sorted[-1]) - y_half,
        float(x_sorted[-1]) + x_half,
        float(y_sorted[0]) + y_half,
        grid.shape[1],
        grid.shape[0],
    )
    return SourceRaster(cmi=grid, src_transform=src_transform, src_crs=src_crs)


def _load_adp_source_raster(path: Path) -> SourceRaster:
    """Load an ABI-L2-ADP file into a single category+confidence code band.

    Combines the Smoke and Dust detection flags with their DQF confidence into
    one code grid: ``category * 10 + confidence`` where category is
    1=smoke / 2=dust / 3=both and confidence is 0=high / 1=medium / 2=low.
    0 = no detection. ``bad`` confidence (DQF field == 3) is treated as no
    detection. The DQF packs confidence in 2-bit fields: smoke at bits 2-3,
    dust at bits 4-5 (0=high, 1=medium, 2=low, 3=bad). Off-disk/fill pixels
    collapse to 0 (transparent at colorise time).
    """
    dataset = _load_netcdf_dataset(path)
    if "Smoke" not in dataset or "Dust" not in dataset:
        raise ValueError(f"ADP source file is missing Smoke/Dust flags: {path}")
    smoke = np.nan_to_num(np.asarray(dataset["Smoke"].values, dtype=np.float32)) >= 0.5
    dust = np.nan_to_num(np.asarray(dataset["Dust"].values, dtype=np.float32)) >= 0.5
    if "DQF" in dataset:
        dqf = np.nan_to_num(
            np.asarray(dataset["DQF"].values, dtype=np.float32), nan=255.0
        ).astype(np.int32)
    else:
        dqf = np.zeros(smoke.shape, dtype=np.int32)
    smoke_conf = (dqf >> 2) & 0x3
    dust_conf = (dqf >> 4) & 0x3
    smoke_ok = smoke & (smoke_conf != 3)
    dust_ok = dust & (dust_conf != 3)
    both = smoke_ok & dust_ok
    combined = np.where(
        both,
        30 + np.minimum(smoke_conf, dust_conf),
        np.where(
            dust_ok & ~smoke_ok,
            20 + dust_conf,
            np.where(smoke_ok & ~dust_ok, 10 + smoke_conf, 0),
        ),
    ).astype(np.float32)
    return _geos_scan_source_raster(dataset, combined, path)


def _dilate_sparse(grid: np.ndarray, radius: int = 1) -> np.ndarray:
    """Grow sparse finite values into their neighbours via a max window.

    Fire pixels are single 2 km cells and would be near-invisible at CONUS zoom;
    a small max-dilation makes each fire a readable block without moving it.
    ``np.fmax`` ignores NaN, so background stays NaN.
    """
    height, width = grid.shape
    out = grid.copy()
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dy == 0 and dx == 0:
                continue
            shifted = np.full_like(grid, np.nan)
            y_src = slice(max(0, dy), height + min(0, dy))
            y_dst = slice(max(0, -dy), height + min(0, -dy))
            x_src = slice(max(0, dx), width + min(0, dx))
            x_dst = slice(max(0, -dx), width + min(0, -dx))
            shifted[y_dst, x_dst] = grid[y_src, x_src]
            out = np.fmax(out, shifted)
    return out


def _load_frp_source_raster(path: Path) -> SourceRaster:
    """Load Fire Radiative Power (MW) from an ABI-L2-FDC file.

    Only actual fire pixels carry a value; everything else is NaN, so the
    scalar colorizer renders fires as hot points over a transparent field.
    """
    dataset = _load_netcdf_dataset(path)
    if "Power" not in dataset:
        raise ValueError(f"FDC source file is missing the Power variable: {path}")
    power = np.asarray(dataset["Power"].values, dtype=np.float32)
    power = _dilate_sparse(power, radius=1)
    return _geos_scan_source_raster(dataset, power, path)


def _load_aod_source_raster(path: Path) -> SourceRaster:
    """Load the AOD (aerosol optical depth at 550 nm) field from an ABI-L2-AOD file.

    Restricted to high- and medium-quality retrievals via DQF (0=high, 1=medium,
    2=low, 3=no-retrieval); low-quality pixels are the main source of clear-sky
    speckle, so they are dropped to NaN — matching NESDIS AerosolWatch imagery.
    """
    dataset = _load_netcdf_dataset(path)
    if "AOD" not in dataset:
        raise ValueError(f"AOD source file is missing the AOD variable: {path}")
    aod = np.asarray(dataset["AOD"].values, dtype=np.float32)
    if "DQF" in dataset:
        dqf = np.nan_to_num(
            np.asarray(dataset["DQF"].values, dtype=np.float32), nan=3.0
        )
        aod = np.where(dqf <= 1.0, aod, np.nan).astype(np.float32)
    return _geos_scan_source_raster(dataset, aod, path)


def _is_fci_chunk_file(path: Path) -> bool:
    name = path.name
    return "FCI-1C-RRAD-FDHSI" in name and "CHK-BODY" in name and name.endswith(".nc")


def _load_fci_source_raster(
    primary_chunk: Path, source_channel: str, max_grid: int | None = None
) -> SourceRaster:
    """Load Meteosat-12 FCI body chunks into a SourceRaster."""
    from satellite_v2.fci_nc import load_fci_raster

    chunk_paths = sorted(path for path in primary_chunk.parent.iterdir() if _is_fci_chunk_file(path))
    raster = load_fci_raster(
        chunk_paths,
        source_channel,
        max_grid=max_grid or SATELLITE_V2_FCI_MAX_GRID,
    )
    return SourceRaster(
        cmi=raster.values,
        src_transform=raster.src_transform,
        src_crs=raster.src_crs,
    )


def _power_of_two_stride(longest: int, max_grid: int) -> int:
    stride = 1
    limit = max(1, int(max_grid))
    while math.ceil(int(longest) / stride) > limit:
        stride *= 2
    return stride


def _goes_fulldisk_stride(
    dataset: xr.Dataset,
    path: Path,
    shape: tuple[int, ...],
    max_grid: int | None = None,
) -> int:
    longest = max(shape)
    grid_cap = int(max_grid or SATELLITE_V2_GOES_FULLDISK_MAX_GRID)
    if longest <= grid_cap:
        return 1
    scene = str(dataset.attrs.get("scene_id", "")).strip().lower()
    is_fulldisk = (
        scene == "full disk"
        or "CMIPF" in path.name.upper()
        or any(part.upper() == "FULLDISK" for part in path.parts)
    )
    if not is_fulldisk:
        return 1
    return _power_of_two_stride(longest, grid_cap)


def _load_source_raster(
    source_file: str | Path,
    source_channel: str | None = None,
    max_grid: int | None = None,
) -> SourceRaster:
    """Load a GOES/GK2A/GMGSI NetCDF, AHI HSD, or SEVIRI .nat source.

    ``source_channel`` matters only for SEVIRI: one .nat bundles all
    channels, so the loader must know which one to extract. GOES and AHI
    sources are per-channel files and ignore it.
    """
    path = Path(source_file)
    if source_channel == "ADP":
        return _load_adp_source_raster(path)
    if source_channel == "AOD":
        return _load_aod_source_raster(path)
    if source_channel == "FRP":
        return _load_frp_source_raster(path)
    if _is_gmgsi_file(path):
        if not source_channel:
            raise ValueError("GMGSI sources require a source_channel.")
        return _load_gmgsi_source_raster(path, source_channel)
    if _is_ami_l1b_file(path):
        if not source_channel:
            raise ValueError("GK2A AMI sources require a source_channel.")
        return _load_ami_source_raster(path, source_channel, max_grid=max_grid)
    if _is_ahi_hsd_file(path):
        return _load_ahi_source_raster(path, max_grid=max_grid)
    if _is_fci_chunk_file(path):
        if not source_channel:
            raise ValueError(
                "FCI NetCDF chunks require a source_channel to extract."
            )
        return _load_fci_source_raster(path, source_channel, max_grid=max_grid)
    if path.name.lower().endswith(".nat"):
        if not source_channel:
            raise ValueError(
                "SEVIRI .nat sources require a source_channel to extract."
            )
        return _load_seviri_source_raster(path, source_channel)
    dataset = _load_netcdf_dataset(source_file)
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

    cmi_lazy = dataset[cmi_var]
    if cmi_lazy.ndim != 2:
        raise ValueError(f"CMI variable must be 2D: {source_file}")

    stride = _goes_fulldisk_stride(
        dataset, path, cmi_lazy.shape, max_grid=max_grid
    )
    if stride > 1:
        # Slice the lazy variable so the full-resolution array is never
        # materialised; netCDF4 reads only the strided hyperslab.
        offset = stride // 2
        x_values = x_values[offset::stride]
        y_values = y_values[offset::stride]
        cmi_lazy = cmi_lazy[offset::stride, offset::stride]
    cmi = np.asarray(cmi_lazy.values, dtype=np.float32)

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

    return SourceRaster(
        cmi=cmi_sorted,
        src_transform=src_transform,
        src_crs=src_crs,
        observation_time=_parse_observation_time(dataset, path),
        satellite_longitude=lon_origin,
        satellite_height_km=height / 1000.0,
    )


def _load_fci_source_rasters(
    primary_chunk: Path,
    source_channels: Sequence[str],
    max_grid: int | None = None,
) -> dict[str, SourceRaster]:
    """Load multiple FCI channels in one pass over their shared chunks."""
    from satellite_v2.fci_nc import load_fci_rasters

    chunk_paths = sorted(
        path for path in primary_chunk.parent.iterdir() if _is_fci_chunk_file(path)
    )
    rasters = load_fci_rasters(
        chunk_paths,
        source_channels,
        max_grid=max_grid or SATELLITE_V2_FCI_MAX_GRID,
    )
    return {
        source_channel: SourceRaster(
            cmi=raster.values,
            src_transform=raster.src_transform,
            src_crs=raster.src_crs,
        )
        for source_channel, raster in rasters.items()
    }


def _canvas_lon_lat_grid(
    z: int,
    x_min: int,
    y_min: int,
    canvas_w: int,
    canvas_h: int,
    tile_size: int,
) -> tuple[np.ndarray, np.ndarray]:
    scale = float(2**z)
    pixels_x = np.arange(canvas_w, dtype=np.float64) + 0.5
    pixels_y = np.arange(canvas_h, dtype=np.float64) + 0.5
    tile_x = (int(x_min) * tile_size + pixels_x) / (scale * tile_size)
    tile_y = (int(y_min) * tile_size + pixels_y) / (scale * tile_size)
    lon = tile_x * 360.0 - 180.0
    mercator = math.pi * (1.0 - 2.0 * tile_y)
    lat = np.degrees(np.arctan(np.sinh(mercator)))
    return np.meshgrid(lon, lat)


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
    rgba[:, :, 3] = np.where(valid, _SATELLITE_FILLED_ALPHA, 0).astype(np.uint8)
    return Image.fromarray(rgba, mode="RGBA")


def _colorize_scalar(
    values: np.ndarray,
    valid: np.ndarray,
    cmap,
    norm,
    alpha: int = _SATELLITE_FILLED_ALPHA,
) -> Image.Image:
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
    rgba[..., 3] = np.where(valid, alpha, 0).astype(np.uint8)
    return Image.fromarray(rgba, mode="RGBA")


def _colorize_categorical(values: np.ndarray, valid: np.ndarray) -> Image.Image:
    """Colorise ADP category+confidence codes.

    Code = category * 10 + confidence: category 1=smoke / 2=dust / 3=both sets
    the hue, confidence 0=high / 1=medium / 2=low sets the opacity so
    high-confidence cores read solid and low-confidence edges read faint.
    """
    codes = np.rint(np.where(valid, values, 0.0)).astype(np.int16)
    category = codes // 10
    confidence = codes % 10
    rgba = np.zeros((*codes.shape, 4), dtype=np.uint8)
    category_rgb = {1: _ADP_SMOKE_RGB, 2: _ADP_DUST_RGB, 3: _ADP_BOTH_RGB}
    for cat, rgb in category_rgb.items():
        for conf, alpha in enumerate(_ADP_CONFIDENCE_ALPHA):
            mask = valid & (category == cat) & (confidence == conf)
            if not mask.any():
                continue
            rgba[mask, 0] = rgb[0]
            rgba[mask, 1] = rgb[1]
            rgba[mask, 2] = rgb[2]
            rgba[mask, 3] = alpha
    return Image.fromarray(rgba, mode="RGBA")


def _colorize_aod(values: np.ndarray, valid: np.ndarray, cmap, norm) -> Image.Image:
    """Colorise AOD with a value-driven alpha ramp so clear air is transparent."""
    safe = np.where(valid, values, np.nan)
    finite = np.isfinite(safe)
    filled = np.where(finite, safe, 0.0)
    rgba = cmap(norm(filled), bytes=True)
    ramp = np.clip(
        (filled - _AOD_ALPHA_MIN) / (_AOD_ALPHA_FULL - _AOD_ALPHA_MIN), 0.0, 1.0
    )
    alpha = (ramp * _SATELLITE_OVERLAY_ALPHA).astype(np.uint8)
    rgba[..., 3] = np.where(valid & finite, alpha, 0).astype(np.uint8)
    return Image.fromarray(rgba, mode="RGBA")
