"""Tile planning and warming for Satellite v2."""

from __future__ import annotations

import math
import os
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable, Any, Mapping, Sequence

import numpy as np


from config.satellite_v2_config import (
    SATELLITE_V2_LIVE_SUPERTILE_RADIUS,
    SATELLITE_V2_SECTOR_BOUNDS,
    SATELLITE_V2_TILE_SIZE,
    normalize_channel,
    normalize_sat_id,
    normalize_sector,
    source_channels_for_product,
)
from satellite_v2.cache import (
    clear_negative_tile_marker,
    is_negative_tile_cached,
    is_valid_tile_file,
    tile_image_has_content,
    tile_path,
    write_negative_tile_marker,
)
from satellite_v2.providers import download_product_source_frames
from satellite_v2.renderer import SatelliteTileRenderer


_WARM_TILE_RENDERER: SatelliteTileRenderer | None = None


def _initialize_warm_tile_worker(
    channel_key: str,
    source_files: dict[str, str],
    sat_id: str | None = None,
) -> None:
    global _WARM_TILE_RENDERER
    source_file_paths: dict[str, str | Path] = {
        str(channel): Path(path) for channel, path in source_files.items()
    }
    _WARM_TILE_RENDERER = SatelliteTileRenderer.from_sources(
        channel_key,
        source_file_paths,
        sat_id=sat_id,
    )


def lon_lat_to_tile(lon: float, lat: float, z: int) -> tuple[int, int]:
    lat = max(min(float(lat), 85.05112878), -85.05112878)
    scale = 2 ** int(z)
    x = int(math.floor(((float(lon) + 180.0) / 360.0) * scale))
    lat_rad = math.radians(lat)
    y = int(
        math.floor(
            (
                (1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi)
                / 2.0
            )
            * scale
        )
    )
    return max(0, min(scale - 1, x)), max(0, min(scale - 1, y))


def sector_tile_coords(sector: str, z: int) -> list[tuple[int, int]]:
    sector_key = normalize_sector(sector)
    bounds = SATELLITE_V2_SECTOR_BOUNDS[sector_key]
    x_min, y_max = lon_lat_to_tile(bounds["west"], bounds["south"], z)
    x_max, y_min = lon_lat_to_tile(bounds["east"], bounds["north"], z)
    x0, x1 = sorted((x_min, x_max))
    y0, y1 = sorted((y_min, y_max))
    return [(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)]


def _normalize_tile_bounds(
    bounds: Mapping[str, float] | Sequence[float] | None,
) -> tuple[float, float, float, float] | None:
    if bounds is None:
        return None
    if isinstance(bounds, Mapping):
        west = float(bounds["west"])
        south = float(bounds["south"])
        east = float(bounds["east"])
        north = float(bounds["north"])
    else:
        values = list(bounds)
        if len(values) != 4:
            raise ValueError("Tile bounds must be west,south,east,north.")
        west, south, east, north = (float(value) for value in values)
    if south > north:
        south, north = north, south
    return west, south, east, north


def tile_coords_for_bounds(
    bounds: Mapping[str, float] | Sequence[float],
    z: int,
    buffer_tiles: int = 0,
) -> list[tuple[int, int]]:
    west, south, east, north = _normalize_tile_bounds(bounds) or (0.0, 0.0, 0.0, 0.0)
    x_min, y_max = lon_lat_to_tile(west, south, z)
    x_max, y_min = lon_lat_to_tile(east, north, z)
    x0, x1 = sorted((x_min, x_max))
    y0, y1 = sorted((y_min, y_max))
    max_tile_index = max(0, (2 ** int(z)) - 1)
    pad = max(0, int(buffer_tiles or 0))
    x0 = max(0, x0 - pad)
    x1 = min(max_tile_index, x1 + pad)
    y0 = max(0, y0 - pad)
    y1 = min(max_tile_index, y1 + pad)
    return [(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)]


def planning_tile_coords(
    sector: str,
    z: int,
    bounds: Mapping[str, float] | Sequence[float] | None = None,
    buffer_tiles: int = 0,
) -> list[tuple[int, int]]:
    if bounds is None:
        return sector_tile_coords(sector, z)
    return tile_coords_for_bounds(bounds, z, buffer_tiles=buffer_tiles)


def _render_tile_to_target(
    renderer: SatelliteTileRenderer,
    target: Path,
    z: int,
    x: int,
    y: int,
    target_was_invalid: bool,
) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent)
    )
    os.close(fd)
    try:
        image = renderer.render_tile(int(z), int(x), int(y), SATELLITE_V2_TILE_SIZE)
        if not tile_image_has_content(image):
            if target_was_invalid:
                target.unlink(missing_ok=True)
            write_negative_tile_marker(target)
            os.unlink(tmp_name)
            return "invalid"
        image.save(tmp_name, format="PNG", optimize=False, compress_level=1)
        if not is_valid_tile_file(Path(tmp_name)):
            if target_was_invalid:
                target.unlink(missing_ok=True)
            write_negative_tile_marker(target)
            os.unlink(tmp_name)
            return "invalid"
        os.replace(tmp_name, target)
        clear_negative_tile_marker(target)
        return "rendered"
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _live_supertile_coords(z: int, x: int, y: int) -> list[tuple[int, int]]:
    radius = max(0, int(SATELLITE_V2_LIVE_SUPERTILE_RADIUS or 0))
    max_tile_index = max(0, (2 ** int(z)) - 1)
    coords = [(int(x), int(y))]
    if radius <= 0:
        return coords
    for yy in range(max(0, int(y) - radius), min(max_tile_index, int(y) + radius) + 1):
        for xx in range(max(0, int(x) - radius), min(max_tile_index, int(x) + radius) + 1):
            if xx == int(x) and yy == int(y):
                continue
            coords.append((xx, yy))
    return coords


def _target_needs_live_render(target: Path, overwrite: bool) -> tuple[bool, bool]:
    target_was_invalid = target.exists() and not is_valid_tile_file(target)
    if target.exists() and is_valid_tile_file(target) and not overwrite:
        return False, target_was_invalid
    if is_negative_tile_cached(target) and not overwrite:
        return False, target_was_invalid
    return True, target_was_invalid


def _render_warm_tile_task(task: dict[str, Any]) -> dict[str, int]:
    if _WARM_TILE_RENDERER is None:
        raise RuntimeError("Satellite v2 warm tile worker was not initialized.")

    target = tile_path(
        task["cache_root"],
        task["sat_id"],
        task["sector"],
        task["channel"],
        task["frame_key"],
        int(task["z"]),
        int(task["x"]),
        int(task["y"]),
    )
    target_was_invalid = target.exists() and not is_valid_tile_file(target)
    if (
        target.exists()
        and is_valid_tile_file(target)
        and not bool(task.get("overwrite"))
    ):
        return {"rendered": 0, "skipped": 1, "errors": 0, "repaired": 0, "invalid": 0}

    result = _render_tile_to_target(
        _WARM_TILE_RENDERER,
        target,
        int(task["z"]),
        int(task["x"]),
        int(task["y"]),
        target_was_invalid,
    )
    return {
        "rendered": 1 if result == "rendered" else 0,
        "skipped": 0,
        "errors": 0,
        "repaired": 1 if result == "rendered" and target_was_invalid else 0,
        "invalid": 1 if result == "invalid" else 0,
    }


def _merge_tile_stats(total: dict[str, int], part: dict[str, int]) -> None:
    for key in ("rendered", "skipped", "errors", "repaired", "invalid"):
        total[key] += int(part.get(key) or 0)


def _render_warm_zoom_canvas_task(task: dict[str, Any]) -> dict[str, int]:
    stats = {"rendered": 0, "skipped": 0, "errors": 0, "repaired": 0, "invalid": 0}
    cache_root = task["cache_root"]
    sat_id = task["sat_id"]
    sector = task["sector"]
    channel = task["channel"]
    frame_key = task["frame_key"]
    zoom = int(task["z"])
    overwrite = bool(task.get("overwrite"))
    tile_size = int(task.get("tile_size") or SATELLITE_V2_TILE_SIZE)
    coords: list[tuple[int, int]] = [
        (int(x), int(y)) for x, y in task.get("coords") or []
    ]
    if not coords:
        return stats

    xs = [x for x, _ in coords]
    ys = [y for _, y in coords]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)

    try:
        source_files: dict[str, str | Path] = {
            source_channel: Path(path)
            for source_channel, path in (task.get("source_files") or {}).items()
        }
        renderer = SatelliteTileRenderer.from_sources(
            channel, source_files, sat_id=sat_id
        )
        canvas = renderer.render_zoom_canvas(
            zoom,
            x_min,
            y_min,
            x_max,
            y_max,
            tile_size=tile_size,
        )
    except Exception as exc:
        print(
            f"[satellite_v2] canvas warm error "
            f"{sat_id}/{sector}/{channel}/{frame_key}/z{zoom}: {exc}"
        )
        stats["errors"] += len(coords)
        return stats

    # Fast path: if the entire canvas is transparent the MESO/source footprint
    # does not intersect this tile range.  Skip all coords immediately.
    canvas_arr = np.array(canvas)
    if (
        canvas_arr.ndim == 3
        and canvas_arr.shape[2] == 4
        and not np.any(canvas_arr[:, :, 3])
    ):
        for x, y in coords:
            write_negative_tile_marker(
                tile_path(cache_root, sat_id, sector, channel, frame_key, zoom, x, y)
            )
        stats["invalid"] += len(coords)
        return stats

    for x, y in coords:
        target = tile_path(
            cache_root,
            sat_id,
            sector,
            channel,
            frame_key,
            zoom,
            x,
            y,
        )
        if target.exists() and is_valid_tile_file(target) and not overwrite:
            stats["skipped"] += 1
            continue

        target_was_invalid = target.exists() and not is_valid_tile_file(target)
        left = (x - x_min) * tile_size
        top = (y - y_min) * tile_size
        right = (x - x_min + 1) * tile_size
        bottom = (y - y_min + 1) * tile_size
        tile_img = canvas.crop((left, top, right, bottom))

        if not tile_image_has_content(tile_img):
            if target_was_invalid:
                target.unlink(missing_ok=True)
            write_negative_tile_marker(target)
            stats["invalid"] += 1
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent)
        )
        os.close(fd)
        try:
            tile_img.save(tmp_name, format="PNG", optimize=False, compress_level=1)
            if not is_valid_tile_file(Path(tmp_name)):
                if target_was_invalid:
                    target.unlink(missing_ok=True)
                os.unlink(tmp_name)
                stats["invalid"] += 1
                continue
            os.replace(tmp_name, target)
            clear_negative_tile_marker(target)
            stats["rendered"] += 1
            if target_was_invalid:
                stats["repaired"] += 1
        except Exception:
            stats["errors"] += 1
            try:
                os.unlink(tmp_name)
            except OSError:
                pass

    return stats


def warm_frame_tiles(
    cache_root: str | Path,
    sat_id: str,
    sector: str,
    channel_key: str,
    frame: dict,
    zooms: Iterable[int],
    overwrite: bool = False,
    render_workers: int = 1,
    tile_bounds: Mapping[str, float] | Sequence[float] | None = None,
    tile_buffer: int = 0,
) -> dict[str, int]:
    sat_key = normalize_sat_id(sat_id)
    sector_key = normalize_sector(sector)
    channel = normalize_channel(channel_key)
    frame_key = str(frame.get("frame_key") or "")
    if not frame_key:
        raise ValueError("Satellite v2 frame is missing frame_key.")

    source_files = download_product_source_frames(
        cache_root, sat_key, sector_key, channel, frame
    )
    stats = {"rendered": 0, "skipped": 0, "errors": 0, "repaired": 0, "invalid": 0}
    tasks: list[dict[str, Any]] = []

    for zoom in [int(value) for value in zooms]:
        for x, y in planning_tile_coords(
            sector_key, zoom, bounds=tile_bounds, buffer_tiles=tile_buffer
        ):
            target = tile_path(
                cache_root, sat_key, sector_key, channel, frame_key, zoom, x, y
            )
            if target.exists() and is_valid_tile_file(target) and not overwrite:
                stats["skipped"] += 1
                continue

            tasks.append(
                {
                    "cache_root": str(cache_root),
                    "sat_id": sat_key,
                    "sector": sector_key,
                    "channel": channel,
                    "frame_key": frame_key,
                    "z": zoom,
                    "x": x,
                    "y": y,
                    "overwrite": overwrite,
                }
            )

    if not tasks:
        return stats

    worker_count = max(1, min(int(render_workers or 1), len(tasks)))
    source_file_map = {key: str(path) for key, path in source_files.items()}
    if worker_count <= 1:
        source_files_for_renderer: dict[str, str | Path] = dict(source_files)
        renderer = SatelliteTileRenderer.from_sources(
            channel, source_files_for_renderer, sat_id=sat_key
        )
        for task in tasks:
            try:
                target = tile_path(
                    task["cache_root"],
                    task["sat_id"],
                    task["sector"],
                    task["channel"],
                    task["frame_key"],
                    int(task["z"]),
                    int(task["x"]),
                    int(task["y"]),
                )
                target_was_invalid = target.exists() and not is_valid_tile_file(target)
                if target.exists() and is_valid_tile_file(target) and not overwrite:
                    stats["skipped"] += 1
                    continue
                result = _render_tile_to_target(
                    renderer,
                    target,
                    int(task["z"]),
                    int(task["x"]),
                    int(task["y"]),
                    target_was_invalid,
                )
                if result == "rendered":
                    stats["rendered"] += 1
                    if target_was_invalid:
                        stats["repaired"] += 1
                else:
                    stats["invalid"] += 1
            except Exception:
                stats["errors"] += 1
        return stats

    with ProcessPoolExecutor(
        max_workers=worker_count,
        initializer=_initialize_warm_tile_worker,
        initargs=(channel, source_file_map, sat_key),
    ) as pool:
        futures = [pool.submit(_render_warm_tile_task, task) for task in tasks]
        for future in as_completed(futures):
            try:
                _merge_tile_stats(stats, future.result())
            except Exception:
                stats["errors"] += 1
    return stats


def warm_frame_tiles_from_canvas(
    cache_root: str | Path,
    sat_id: str,
    sector: str,
    channel_key: str,
    frame: dict,
    zooms: Iterable[int],
    overwrite: bool = False,
    render_workers: int = 1,
    tile_bounds: Mapping[str, float] | Sequence[float] | None = None,
    tile_buffer: int = 0,
) -> dict[str, int]:
    sat_key = normalize_sat_id(sat_id)
    sector_key = normalize_sector(sector)
    channel = normalize_channel(channel_key)
    frame_key = str(frame.get("frame_key") or "")
    if not frame_key:
        raise ValueError("Satellite v2 frame is missing frame_key.")

    stats = {"rendered": 0, "skipped": 0, "errors": 0, "repaired": 0, "invalid": 0}

    zoom_list = [int(value) for value in zooms]
    if not zoom_list:
        return stats

    # Cheap pre-check: keep only coords whose tile (or negative marker) is not
    # already on disk, so fully warmed frames skip the source download and
    # canvas render entirely.
    pending_coords: dict[int, list[tuple[int, int]]] = {}
    for zoom in zoom_list:
        coords = planning_tile_coords(
            sector_key, zoom, bounds=tile_bounds, buffer_tiles=tile_buffer
        )
        if not coords:
            continue
        if overwrite:
            pending_coords[zoom] = coords
            continue
        missing: list[tuple[int, int]] = []
        for x, y in coords:
            target = tile_path(
                cache_root, sat_key, sector_key, channel, frame_key, zoom, x, y
            )
            try:
                if target.stat().st_size > 0:
                    stats["skipped"] += 1
                    continue
            except OSError:
                pass
            if is_negative_tile_cached(target):
                stats["skipped"] += 1
                continue
            missing.append((x, y))
        if missing:
            pending_coords[zoom] = missing

    if not pending_coords:
        return stats

    source_files = download_product_source_frames(
        cache_root, sat_key, sector_key, channel, frame
    )
    source_file_map = {key: str(path) for key, path in source_files.items()}
    tasks: list[dict[str, Any]] = [
        {
            "cache_root": str(cache_root),
            "sat_id": sat_key,
            "sector": sector_key,
            "channel": channel,
            "frame_key": frame_key,
            "z": zoom,
            "coords": coords,
            "overwrite": overwrite,
            "tile_size": SATELLITE_V2_TILE_SIZE,
            "source_files": source_file_map,
        }
        for zoom, coords in pending_coords.items()
    ]

    worker_count = max(1, min(int(render_workers or 1), len(tasks)))
    if worker_count <= 1:
        for task in tasks:
            _merge_tile_stats(stats, _render_warm_zoom_canvas_task(task))
        return stats

    with ProcessPoolExecutor(max_workers=worker_count) as pool:
        futures = [pool.submit(_render_warm_zoom_canvas_task, task) for task in tasks]
        for future in as_completed(futures):
            try:
                _merge_tile_stats(stats, future.result())
            except Exception:
                stats["errors"] += 1
    return stats


def render_frame_tile(
    cache_root: str | Path,
    sat_id: str,
    sector: str,
    channel_key: str,
    frame: dict,
    z: int,
    x: int,
    y: int,
    overwrite: bool = False,
) -> tuple[Path, dict[str, int | str]]:
    started = time.perf_counter()
    sat_key = normalize_sat_id(sat_id)
    sector_key = normalize_sector(sector)
    channel = normalize_channel(channel_key)
    frame_key = str(frame.get("frame_key") or "")
    if not frame_key:
        raise ValueError("Satellite v2 frame is missing frame_key.")

    target = tile_path(cache_root, sat_key, sector_key, channel, frame_key, z, x, y)
    target_needs_render, target_was_invalid = _target_needs_live_render(target, overwrite)
    if not target_needs_render:
        return target, {"cache_status": "hit", "rendered": 0, "skipped": 1, "errors": 0}

    tile_id = f"{sat_key}/{sector_key}/{channel}/{frame_key}/z{z}/{x}/{y}"
    print(f"[satellite-v2 tile] stage=source_start tile={tile_id}", flush=True)
    source_start = time.perf_counter()
    source_files = download_product_source_frames(
        cache_root, sat_key, sector_key, channel, frame
    )
    source_elapsed = int((time.perf_counter() - source_start) * 1000)
    print(
        "[satellite-v2 tile] "
        f"stage=source_complete tile={tile_id} "
        f"sources={len(source_files)} elapsed_ms={source_elapsed}",
        flush=True,
    )
    source_files_for_renderer: dict[str, str | Path] = dict(source_files)
    renderer_start = time.perf_counter()
    print(f"[satellite-v2 tile] stage=renderer_start tile={tile_id}", flush=True)
    renderer = SatelliteTileRenderer.from_sources(
        channel, source_files_for_renderer, sat_id=sat_key
    )
    renderer_elapsed = int((time.perf_counter() - renderer_start) * 1000)
    print(
        "[satellite-v2 tile] "
        f"stage=renderer_ready tile={tile_id} elapsed_ms={renderer_elapsed}",
        flush=True,
    )
    stats = {
        "cache_status": "miss",
        "rendered": 0,
        "skipped": 0,
        "errors": 0,
        "supertile_rendered": 0,
        "supertile_skipped": 0,
        "supertile_invalid": 0,
        "supertile_errors": 0,
        "supertile_radius": int(SATELLITE_V2_LIVE_SUPERTILE_RADIUS or 0),
    }
    try:
        for tile_x, tile_y in _live_supertile_coords(int(z), int(x), int(y)):
            current_target = tile_path(
                cache_root,
                sat_key,
                sector_key,
                channel,
                frame_key,
                int(z),
                tile_x,
                tile_y,
            )
            current_needs_render, current_was_invalid = _target_needs_live_render(
                current_target, overwrite
            )
            is_requested_tile = tile_x == int(x) and tile_y == int(y)
            if not current_needs_render:
                if not is_requested_tile:
                    stats["supertile_skipped"] += 1
                continue
            render_start = time.perf_counter()
            try:
                result = _render_tile_to_target(
                    renderer, current_target, int(z), tile_x, tile_y, current_was_invalid
                )
            except Exception:
                if is_requested_tile:
                    raise
                stats["supertile_errors"] += 1
                continue
            render_elapsed = int((time.perf_counter() - render_start) * 1000)
            total_elapsed = int((time.perf_counter() - started) * 1000)
            current_tile_id = (
                f"{sat_key}/{sector_key}/{channel}/{frame_key}/z{z}/{tile_x}/{tile_y}"
            )
            if is_requested_tile:
                print(
                    "[satellite-v2 tile] "
                    f"stage=tile_render_complete tile={current_tile_id} result={result} "
                    f"render_ms={render_elapsed} total_ms={total_elapsed}",
                    flush=True,
                )
            if result == "invalid":
                if is_requested_tile:
                    stats["cache_status"] = "invalid"
                    stats["errors"] = 1
                    break
                else:
                    stats["supertile_invalid"] += 1
                continue
            if is_requested_tile:
                stats["rendered"] = 1
            else:
                stats["supertile_rendered"] += 1
    except Exception:
        stats["supertile_errors"] += 1
        raise
    total_elapsed = int((time.perf_counter() - started) * 1000)
    print(
        "[satellite-v2 tile] "
        f"stage=supertile_complete tile={tile_id} "
        f"radius={stats['supertile_radius']} "
        f"rendered={stats['supertile_rendered']} "
        f"skipped={stats['supertile_skipped']} "
        f"invalid={stats['supertile_invalid']} "
        f"errors={stats['supertile_errors']} "
        f"total_ms={total_elapsed}",
        flush=True,
    )
    return target, stats

