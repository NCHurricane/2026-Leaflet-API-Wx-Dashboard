"""GOES GLM Flash Extent Density tile rendering."""

from __future__ import annotations

import math
import os
import tempfile
import threading
from functools import lru_cache
from pathlib import Path
from typing import Iterable

import numpy as np
import xarray as xr
from PIL import Image
from pyproj import Transformer

from config.satellite_v2_config import SATELLITE_V2_TILE_SIZE
from satellite_v2.cache import (
    clear_negative_tile_marker,
    is_valid_tile_file,
    tile_image_has_content,
    tile_path,
    write_negative_tile_marker,
)


_GLM_ALPHA = 210
_GLM_SOURCE_CACHE_SIZE = 96
_GLM_READ_LOCK = threading.Lock()
_GLM_GRID_CELL_METERS = 4000.0
_WEB_MERCATOR_LIMIT = 20037508.342789244
_LONLAT_TO_WEB_MERCATOR = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
_GLM_COUNT_STOPS = np.array([0.0, 1.0, 2.0, 4.0, 8.0, 16.0], dtype=np.float32)
_GLM_COLOR_STOPS = np.array(
    [
        [0, 0, 0],
        [0, 51, 255],
        [0, 204, 255],
        [102, 255, 0],
        [255, 204, 0],
        [255, 0, 0],
    ],
    dtype=np.float32,
)


def render_glm_density_tile(
    cache_root: str | Path,
    sat_id: str,
    sector: str,
    product_key: str,
    frame_key: str,
    source_files: Iterable[Path],
    z: int,
    x: int,
    y: int,
    overwrite: bool = False,
) -> tuple[Path, dict[str, int | str]]:
    target = tile_path(cache_root, sat_id, sector, product_key, frame_key, z, x, y)
    if target.exists() and is_valid_tile_file(target) and not overwrite:
        return target, {"cache_status": "hit", "rendered": 0, "skipped": 1, "errors": 0}

    image = _glm_tile_image(source_files, z, x, y)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not tile_image_has_content(image):
        target.unlink(missing_ok=True)
        write_negative_tile_marker(target)
        return target, {
            "cache_status": "invalid",
            "rendered": 0,
            "skipped": 0,
            "errors": 1,
        }

    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent)
    )
    os.close(fd)
    Path(tmp_name).unlink(missing_ok=True)
    try:
        image.save(tmp_name, format="PNG", optimize=False, compress_level=1)
        if not is_valid_tile_file(Path(tmp_name)):
            Path(tmp_name).unlink(missing_ok=True)
            write_negative_tile_marker(target)
            return target, {
                "cache_status": "invalid",
                "rendered": 0,
                "skipped": 0,
                "errors": 1,
            }
        Path(tmp_name).replace(target)
        clear_negative_tile_marker(target)
    finally:
        Path(tmp_name).unlink(missing_ok=True)
    return target, {"cache_status": "miss", "rendered": 1, "skipped": 0, "errors": 0}


def _glm_tile_image(source_files: Iterable[Path], z: int, x: int, y: int) -> Image.Image:
    size = SATELLITE_V2_TILE_SIZE
    tile_west, tile_south, tile_east, tile_north = _tile_mercator_bounds(z, x, y)
    counts = _glm_cell_counts_cached(tuple(sorted(str(Path(path)) for path in source_files)))
    return _counts_to_tile_image(
        counts,
        tile_west,
        tile_south,
        tile_east,
        tile_north,
        size,
    )


@lru_cache(maxsize=_GLM_SOURCE_CACHE_SIZE)
def _glm_cell_counts_cached(source_files: tuple[str, ...]) -> tuple[tuple[int, int, int], ...]:
    merged: dict[tuple[int, int], int] = {}
    for source_file in source_files:
        for cell_x, cell_y, count in _read_glm_cell_counts_cached(source_file):
            key = (int(cell_x), int(cell_y))
            merged[key] = merged.get(key, 0) + int(count)
    return tuple(
        (cell_x, cell_y, count)
        for (cell_x, cell_y), count in sorted(merged.items())
    )


@lru_cache(maxsize=_GLM_SOURCE_CACHE_SIZE)
def _read_glm_cell_counts_cached(source_file: str) -> tuple[tuple[int, int, int], ...]:
    # NetCDF/HDF5 reads are expensive and can be fragile under concurrent tile
    # requests; cache gridded cell counts per worker process.
    with _GLM_READ_LOCK:
        return _read_glm_cell_counts(Path(source_file))


def _read_glm_cell_counts(source_file: Path) -> tuple[tuple[int, int, int], ...]:
    with xr.open_dataset(source_file, decode_times=False) as ds:
        if (
            "group_lat" in ds
            and "group_lon" in ds
            and "group_parent_flash_id" in ds
        ):
            return _cell_counts_from_flash_extent(
                np.asarray(ds["group_lon"].values, dtype=np.float64).ravel(),
                np.asarray(ds["group_lat"].values, dtype=np.float64).ravel(),
                np.asarray(ds["group_parent_flash_id"].values).ravel(),
            )
        if "event_lat" in ds and "event_lon" in ds:
            return _cell_counts_from_points(
                np.asarray(ds["event_lon"].values, dtype=np.float64).ravel(),
                np.asarray(ds["event_lat"].values, dtype=np.float64).ravel(),
            )
        if "flash_lat" in ds and "flash_lon" in ds:
            return _cell_counts_from_points(
                np.asarray(ds["flash_lon"].values, dtype=np.float64).ravel(),
                np.asarray(ds["flash_lat"].values, dtype=np.float64).ravel(),
            )
    return ()


def _cell_counts_from_flash_extent(
    lon: np.ndarray,
    lat: np.ndarray,
    flash_ids: np.ndarray,
) -> tuple[tuple[int, int, int], ...]:
    cell_x, cell_y, valid = _project_to_grid_cells(lon, lat)
    if not np.any(valid):
        return ()
    valid_flash_ids = flash_ids[valid]
    valid_cell_x = cell_x[valid]
    valid_cell_y = cell_y[valid]
    finite_ids = np.isfinite(valid_flash_ids.astype(np.float64, copy=False))
    if not np.any(finite_ids):
        return _cell_counts_from_projected_points(valid_cell_x, valid_cell_y)
    triplets = np.column_stack(
        (
            valid_flash_ids[finite_ids].astype(np.int64, copy=False),
            valid_cell_x[finite_ids].astype(np.int64, copy=False),
            valid_cell_y[finite_ids].astype(np.int64, copy=False),
        )
    )
    unique_flash_cells = np.unique(triplets, axis=0)
    cells, counts = np.unique(unique_flash_cells[:, 1:3], axis=0, return_counts=True)
    return tuple(
        (int(cell[0]), int(cell[1]), int(count))
        for cell, count in zip(cells, counts)
    )


def _cell_counts_from_points(
    lon: np.ndarray,
    lat: np.ndarray,
) -> tuple[tuple[int, int, int], ...]:
    cell_x, cell_y, valid = _project_to_grid_cells(lon, lat)
    if not np.any(valid):
        return ()
    return _cell_counts_from_projected_points(cell_x[valid], cell_y[valid])


def _cell_counts_from_projected_points(
    cell_x: np.ndarray,
    cell_y: np.ndarray,
) -> tuple[tuple[int, int, int], ...]:
    cells, counts = np.unique(
        np.column_stack((cell_x.astype(np.int64), cell_y.astype(np.int64))),
        axis=0,
        return_counts=True,
    )
    return tuple(
        (int(cell[0]), int(cell[1]), int(count))
        for cell, count in zip(cells, counts)
    )


def _project_to_grid_cells(
    lon: np.ndarray,
    lat: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    valid = np.isfinite(lon) & np.isfinite(lat)
    if not np.any(valid):
        return (
            np.array([], dtype=np.int64),
            np.array([], dtype=np.int64),
            valid,
        )
    merc_x, merc_y = _LONLAT_TO_WEB_MERCATOR.transform(lon[valid], lat[valid])
    projected_valid = np.isfinite(merc_x) & np.isfinite(merc_y)
    cell_x = np.zeros(lon.shape, dtype=np.int64)
    cell_y = np.zeros(lat.shape, dtype=np.int64)
    valid_indices = np.flatnonzero(valid)
    valid[valid_indices[~projected_valid]] = False
    cell_x[valid_indices[projected_valid]] = np.floor(
        merc_x[projected_valid] / _GLM_GRID_CELL_METERS
    ).astype(np.int64)
    cell_y[valid_indices[projected_valid]] = np.floor(
        merc_y[projected_valid] / _GLM_GRID_CELL_METERS
    ).astype(np.int64)
    return cell_x, cell_y, valid


def _tile_mercator_bounds(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    scale = float(2**int(z))
    tile_span = (2.0 * _WEB_MERCATOR_LIMIT) / scale
    west = -_WEB_MERCATOR_LIMIT + (int(x) * tile_span)
    east = west + tile_span
    north = _WEB_MERCATOR_LIMIT - (int(y) * tile_span)
    south = north - tile_span
    return west, south, east, north


def _counts_to_tile_image(
    counts: tuple[tuple[int, int, int], ...],
    tile_west: float,
    tile_south: float,
    tile_east: float,
    tile_north: float,
    size: int,
) -> Image.Image:
    rgba = np.zeros((size, size, 4), dtype=np.uint8)
    if not counts:
        return Image.fromarray(rgba, mode="RGBA")

    meters_per_px_x = (tile_east - tile_west) / float(size)
    meters_per_px_y = (tile_north - tile_south) / float(size)
    min_cell_x = math.floor(tile_west / _GLM_GRID_CELL_METERS)
    max_cell_x = math.floor((tile_east - 1e-6) / _GLM_GRID_CELL_METERS)
    min_cell_y = math.floor(tile_south / _GLM_GRID_CELL_METERS)
    max_cell_y = math.floor((tile_north - 1e-6) / _GLM_GRID_CELL_METERS)

    for cell_x, cell_y, count in counts:
        if (
            cell_x < min_cell_x
            or cell_x > max_cell_x
            or cell_y < min_cell_y
            or cell_y > max_cell_y
        ):
            continue
        west = cell_x * _GLM_GRID_CELL_METERS
        east = west + _GLM_GRID_CELL_METERS
        south = cell_y * _GLM_GRID_CELL_METERS
        north = south + _GLM_GRID_CELL_METERS
        px0 = max(0, int(math.floor((west - tile_west) / meters_per_px_x)))
        px1 = min(size, int(math.ceil((east - tile_west) / meters_per_px_x)))
        py0 = max(0, int(math.floor((tile_north - north) / meters_per_px_y)))
        py1 = min(size, int(math.ceil((tile_north - south) / meters_per_px_y)))
        if px1 <= px0 or py1 <= py0:
            continue
        rgba[py0:py1, px0:px1, :3] = _color_for_count(count)
        rgba[py0:py1, px0:px1, 3] = _alpha_for_count(count)
    return Image.fromarray(rgba, mode="RGBA")


def _color_for_count(count: int) -> np.ndarray:
    value = float(max(0, count))
    idx = int(np.searchsorted(_GLM_COUNT_STOPS, value, side="right") - 1)
    idx = max(0, min(idx, len(_GLM_COUNT_STOPS) - 2))
    lower_value = float(_GLM_COUNT_STOPS[idx])
    upper_value = float(_GLM_COUNT_STOPS[idx + 1])
    if upper_value <= lower_value:
        weight = 0.0
    else:
        weight = max(0.0, min(1.0, (value - lower_value) / (upper_value - lower_value)))
    color = (
        _GLM_COLOR_STOPS[idx] * (1.0 - weight)
        + _GLM_COLOR_STOPS[idx + 1] * weight
    )
    if value >= float(_GLM_COUNT_STOPS[-1]):
        color = _GLM_COLOR_STOPS[-1]
    return color.astype(np.uint8)


def _alpha_for_count(count: int) -> np.uint8:
    value = min(float(max(0, count)), float(_GLM_COUNT_STOPS[-1]))
    alpha = 90.0 + (value / float(_GLM_COUNT_STOPS[-1]) * _GLM_ALPHA)
    return np.uint8(max(0, min(255, int(round(alpha)))))

