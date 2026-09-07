"""Tile planning and warming for Satellite v2."""

from __future__ import annotations

import math
import logging
import os
import tempfile
import time
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from pathlib import Path
from typing import Callable, Iterable, Any, Mapping, Sequence

from config.satellite_v2_config import (
    SATELLITE_V2_LIVE_SUPERTILE_RADIUS,
    SATELLITE_V2_SECTOR_BOUNDS,
    SATELLITE_V2_TILE_SIZE,
    normalize_channel,
    normalize_sat_id,
    normalize_sector,
)
from satellite_v2.cache import (
    clear_negative_tile_marker,
    is_negative_tile_cached,
    is_valid_tile_file,
    tile_image_has_content,
    tile_path,
    write_negative_tile_marker,
)
from satellite_v2._bench_timing import (
    add_timing_ms,
    begin_timing,
    bench_enabled,
    finish_timing,
)
from satellite_v2.providers import download_product_source_frames
from satellite_v2.renderer import SatelliteTileRenderer

_LOGGER = logging.getLogger(__name__)


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


def _publish_tile_image_to_target(
    image,
    target: Path,
    target_was_invalid: bool,
) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent)
    )
    os.close(fd)
    try:
        if not tile_image_has_content(image):
            if target_was_invalid:
                target.unlink(missing_ok=True)
            write_negative_tile_marker(target)
            os.unlink(tmp_name)
            return "invalid"
        encode_started = time.perf_counter() if bench_enabled() else 0.0
        image.save(tmp_name, format="PNG", optimize=False, compress_level=1)
        if bench_enabled():
            add_timing_ms("encode_ms", (time.perf_counter() - encode_started) * 1000.0)
        validate_started = time.perf_counter() if bench_enabled() else 0.0
        tmp_valid = is_valid_tile_file(Path(tmp_name))
        if bench_enabled():
            add_timing_ms(
                "validate_ms", (time.perf_counter() - validate_started) * 1000.0
            )
        if not tmp_valid:
            if target_was_invalid:
                target.unlink(missing_ok=True)
            write_negative_tile_marker(target)
            os.unlink(tmp_name)
            return "invalid"
        write_started = time.perf_counter() if bench_enabled() else 0.0
        os.replace(tmp_name, target)
        clear_negative_tile_marker(target)
        if bench_enabled():
            add_timing_ms("write_ms", (time.perf_counter() - write_started) * 1000.0)
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
    validate_started = time.perf_counter() if bench_enabled() else 0.0
    target_was_invalid = target.exists() and not is_valid_tile_file(target)
    if target.exists() and is_valid_tile_file(target) and not overwrite:
        if bench_enabled():
            add_timing_ms(
                "validate_ms", (time.perf_counter() - validate_started) * 1000.0
            )
        return False, target_was_invalid
    if is_negative_tile_cached(target) and not overwrite:
        if bench_enabled():
            add_timing_ms(
                "validate_ms", (time.perf_counter() - validate_started) * 1000.0
            )
        return False, target_was_invalid
    if bench_enabled():
        add_timing_ms("validate_ms", (time.perf_counter() - validate_started) * 1000.0)
    return True, target_was_invalid


def _merge_tile_stats(total: dict[str, int], part: dict[str, int]) -> None:
    for key in ("rendered", "skipped", "errors", "repaired", "invalid"):
        total[key] += int(part.get(key) or 0)


def _publish_zoom_canvas_tiles(
    canvas,
    *,
    cache_root: str | Path,
    sat_id: str,
    sector: str,
    channel: str,
    frame_key: str,
    zoom: int,
    coords: Sequence[tuple[int, int]],
    x_min: int,
    y_min: int,
    tile_size: int,
    overwrite: bool,
    raise_coord: tuple[int, int] | None = None,
) -> tuple[dict[str, int], dict[tuple[int, int], str]]:
    """Crop and atomically publish tiles from one already-rendered zoom canvas."""
    stats = {"rendered": 0, "skipped": 0, "errors": 0, "repaired": 0, "invalid": 0}
    results: dict[tuple[int, int], str] = {}
    for x, y in coords:
        coord = (int(x), int(y))
        target = tile_path(
            cache_root,
            sat_id,
            sector,
            channel,
            frame_key,
            int(zoom),
            coord[0],
            coord[1],
        )
        needs_render, target_was_invalid = _target_needs_live_render(
            target, overwrite
        )
        if not needs_render:
            stats["skipped"] += 1
            results[coord] = "skipped"
            continue

        left = (coord[0] - int(x_min)) * int(tile_size)
        top = (coord[1] - int(y_min)) * int(tile_size)
        tile_img = canvas.crop(
            (left, top, left + int(tile_size), top + int(tile_size))
        )
        try:
            result = _publish_tile_image_to_target(
                tile_img, target, target_was_invalid
            )
        except Exception:
            stats["errors"] += 1
            results[coord] = "error"
            if raise_coord is not None and coord == raise_coord:
                raise
            continue

        results[coord] = result
        if result == "invalid":
            stats["invalid"] += 1
        else:
            stats["rendered"] += 1
            if target_was_invalid:
                stats["repaired"] += 1
    return stats, results


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
            channel, source_files, sat_id=sat_id, destination_zoom=zoom
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
        if sat_id == "meteosat12":
            from satellite_v2.fci_windows import FciRenderCancelled

            if isinstance(exc, FciRenderCancelled):
                stats["cancelled"] = 1
                return stats
        _LOGGER.warning(
            "Satellite canvas warm failed for %s/%s/%s/%s/z%s (%s)",
            sat_id,
            sector,
            channel,
            frame_key,
            zoom,
            type(exc).__name__,
        )
        stats["errors"] += len(coords)
        return stats

    publish_stats, _ = _publish_zoom_canvas_tiles(
        canvas,
        cache_root=cache_root,
        sat_id=sat_id,
        sector=sector,
        channel=channel,
        frame_key=frame_key,
        zoom=zoom,
        coords=coords,
        x_min=x_min,
        y_min=y_min,
        tile_size=tile_size,
        overwrite=overwrite,
    )
    _merge_tile_stats(stats, publish_stats)
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
    pool: ProcessPoolExecutor | None = None,
    should_continue: Callable[[], bool] | None = None,
    wait_until_ready: Callable[[], bool] | None = None,
) -> dict[str, int]:
    sat_key = normalize_sat_id(sat_id)
    sector_key = normalize_sector(sector)
    channel = normalize_channel(channel_key)
    frame_key = str(frame.get("frame_key") or "")
    if not frame_key:
        raise ValueError("Satellite v2 frame is missing frame_key.")

    stats = {
        "rendered": 0,
        "skipped": 0,
        "errors": 0,
        "repaired": 0,
        "invalid": 0,
        "cancelled": 0,
    }

    zoom_list = [int(value) for value in zooms]
    if not zoom_list:
        return stats

    # Cheap pre-check: keep only coords whose tile (or negative marker) is not
    # already on disk, so fully warmed frames skip the source download and
    # canvas render entirely.
    pending_coords: dict[int, list[tuple[int, int]]] = {}
    for zoom in zoom_list:
        if should_continue is not None and not should_continue():
            stats["cancelled"] = 1
            break
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

    def ready_for_more_work() -> bool:
        if should_continue is not None and not should_continue():
            return False
        return wait_until_ready is None or bool(wait_until_ready())

    if not ready_for_more_work():
        stats["cancelled"] = 1
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

    if sat_key == "meteosat12":
        # Keep native-window planning/output bounded and give live work a
        # scheduling boundary between canvases. Reuse the process-local cache.
        bounded_tasks = []
        for task in tasks:
            blocks: dict[tuple[int, int], list[tuple[int, int]]] = {}
            for x, y in task["coords"]:
                blocks.setdefault((x // 3, y // 3), []).append((x, y))
            bounded_tasks.extend({**task, "coords": coords} for coords in blocks.values())
        tasks = bounded_tasks
        pool = None
        render_workers = 1

    worker_count = max(1, min(int(render_workers or 1), len(tasks)))
    if pool is None and worker_count <= 1:
        for task in tasks:
            if not ready_for_more_work():
                stats["cancelled"] = 1
                break
            if sat_key == "meteosat12":
                from satellite_v2.fci_windows import render_context

                with render_context(should_continue):
                    part = _render_warm_zoom_canvas_task(task)
            else:
                part = _render_warm_zoom_canvas_task(task)
            _merge_tile_stats(stats, part)
            if part.get("cancelled"):
                stats["cancelled"] = 1
                break
        return stats

    def collect(executor: ProcessPoolExecutor) -> None:
        task_iter = iter(tasks)
        active = set()
        scheduling_stopped = False

        def fill_capacity() -> None:
            nonlocal scheduling_stopped
            while not scheduling_stopped and len(active) < worker_count:
                if not ready_for_more_work():
                    stats["cancelled"] = 1
                    scheduling_stopped = True
                    return
                try:
                    task = next(task_iter)
                except StopIteration:
                    scheduling_stopped = True
                    return
                active.add(executor.submit(_render_warm_zoom_canvas_task, task))

        fill_capacity()
        while active:
            completed, _ = wait(active, return_when=FIRST_COMPLETED)
            for future in completed:
                active.remove(future)
                try:
                    _merge_tile_stats(stats, future.result())
                except Exception:
                    stats["errors"] += 1
            fill_capacity()

    if pool is not None:
        collect(pool)
    else:
        with ProcessPoolExecutor(max_workers=worker_count) as owned_pool:
            collect(owned_pool)
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
    bench_seed: dict[str, Any] | None = None,
    render_supertile: bool = True,
    record_timing: bool = True,
) -> tuple[Path, dict[str, int | str]]:
    """Render one tile and optionally warm its configured neighbors inline.

    The HTTP service enables the bounded supertile for ordinary live misses so
    one canvas warp can publish the requested tile and its neighbors. Explicit
    prefetch callers disable it and retain single-tile behavior.
    """
    started = time.perf_counter()
    sat_key = normalize_sat_id(sat_id)
    sector_key = normalize_sector(sector)
    channel = normalize_channel(channel_key)
    frame_key = str(frame.get("frame_key") or "")
    if not frame_key:
        raise ValueError("Satellite v2 frame is missing frame_key.")

    timing_token = None
    if bench_enabled() and record_timing:
        timing_token = begin_timing(
            cache_root,
            {
                "sat_id": sat_key,
                "sector": sector_key,
                "product": channel,
                "frame_key": frame_key,
                "z": int(z),
                "x": int(x),
                "y": int(y),
            },
            initial=bench_seed,
        )

    target = tile_path(cache_root, sat_key, sector_key, channel, frame_key, z, x, y)
    target_needs_render, _ = _target_needs_live_render(target, overwrite)
    if not target_needs_render:
        finish_timing(timing_token, cache_status="hit")
        return target, {"cache_status": "hit", "rendered": 0, "skipped": 1, "errors": 0}

    tile_id = f"{sat_key}/{sector_key}/{channel}/{frame_key}/z{z}/{x}/{y}"
    _LOGGER.info("Satellite tile stage=source_start tile=%s", tile_id)
    source_start = time.perf_counter()
    source_files = download_product_source_frames(
        cache_root, sat_key, sector_key, channel, frame
    )
    if bench_enabled():
        add_timing_ms("download_ms", (time.perf_counter() - source_start) * 1000.0)
    source_elapsed = int((time.perf_counter() - source_start) * 1000)
    _LOGGER.info(
        "Satellite tile stage=source_complete tile=%s sources=%s elapsed_ms=%s",
        tile_id,
        len(source_files),
        source_elapsed,
    )
    source_files_for_renderer: dict[str, str | Path] = dict(source_files)
    renderer_start = time.perf_counter()
    _LOGGER.info("Satellite tile stage=renderer_start tile=%s", tile_id)
    renderer = SatelliteTileRenderer.from_sources(
        channel, source_files_for_renderer, sat_id=sat_key, destination_zoom=int(z)
    )
    renderer_elapsed = int((time.perf_counter() - renderer_start) * 1000)
    _LOGGER.info(
        "Satellite tile stage=renderer_ready tile=%s elapsed_ms=%s",
        tile_id,
        renderer_elapsed,
    )
    stats = {
        "cache_status": "miss",
        "rendered": 0,
        "skipped": 0,
        "errors": 0,
        "download_elapsed_ms": source_elapsed,
        "decode_elapsed_ms": renderer_elapsed,
        "render_elapsed_ms": 0,
        "supertile_rendered": 0,
        "supertile_skipped": 0,
        "supertile_invalid": 0,
        "supertile_errors": 0,
        "supertile_radius": (
            int(SATELLITE_V2_LIVE_SUPERTILE_RADIUS or 0) if render_supertile else 0
        ),
    }
    try:
        coords = (
            _live_supertile_coords(int(z), int(x), int(y))
            if render_supertile
            else [(int(x), int(y))]
        )
        xs = [tile_x for tile_x, _ in coords]
        ys = [tile_y for _, tile_y in coords]
        x_min, x_max = min(xs), max(xs)
        y_min, y_max = min(ys), max(ys)
        render_start = time.perf_counter()
        canvas = renderer.render_zoom_canvas(
            int(z),
            x_min,
            y_min,
            x_max,
            y_max,
            tile_size=SATELLITE_V2_TILE_SIZE,
        )
        publish_stats, results = _publish_zoom_canvas_tiles(
            canvas,
            cache_root=cache_root,
            sat_id=sat_key,
            sector=sector_key,
            channel=channel,
            frame_key=frame_key,
            zoom=int(z),
            coords=coords,
            x_min=x_min,
            y_min=y_min,
            tile_size=SATELLITE_V2_TILE_SIZE,
            overwrite=overwrite,
            raise_coord=(int(x), int(y)),
        )
        render_elapsed = int((time.perf_counter() - render_start) * 1000)
        stats["render_elapsed_ms"] = render_elapsed
        requested_coord = (int(x), int(y))
        requested_result = results.get(requested_coord, "error")
        if requested_result == "invalid":
            stats["cache_status"] = "invalid"
            stats["errors"] = 1
        elif requested_result == "rendered":
            stats["rendered"] = 1
        elif requested_result == "skipped":
            stats["cache_status"] = "hit"
            stats["skipped"] = 1
        else:
            stats["errors"] = 1

        for coord, result in results.items():
            if coord == requested_coord:
                continue
            if result == "rendered":
                stats["supertile_rendered"] += 1
            elif result == "skipped":
                stats["supertile_skipped"] += 1
            elif result == "invalid":
                stats["supertile_invalid"] += 1
            else:
                stats["supertile_errors"] += 1
        total_elapsed = int((time.perf_counter() - started) * 1000)
        _LOGGER.info(
            "Satellite tile stage=tile_render_complete tile=%s result=%s "
            "render_ms=%s total_ms=%s canvas_tiles=%s",
            tile_id,
            requested_result,
            render_elapsed,
            total_elapsed,
            len(coords),
        )
    except Exception:
        stats["supertile_errors"] += 1
        raise
    total_elapsed = int((time.perf_counter() - started) * 1000)
    _LOGGER.info(
        "Satellite tile stage=supertile_complete tile=%s radius=%s rendered=%s "
        "skipped=%s invalid=%s errors=%s total_ms=%s",
        tile_id,
        stats["supertile_radius"],
        stats["supertile_rendered"],
        stats["supertile_skipped"],
        stats["supertile_invalid"],
        stats["supertile_errors"],
        total_elapsed,
    )
    finish_timing(timing_token, cache_status=str(stats.get("cache_status") or "miss"))
    return target, stats
