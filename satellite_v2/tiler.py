"""Tile planning and warming for Satellite v2."""

from __future__ import annotations

import math
import os
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable, Any

import numpy as np


from config.satellite_v2_config import (
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
from satellite_v2.provider_aws import download_product_source_frames
from satellite_v2.renderer import SatelliteTileRenderer


_WARM_TILE_RENDERER: SatelliteTileRenderer | None = None


def _initialize_warm_tile_worker(
    channel_key: str,
    source_files: dict[str, str],
) -> None:
    global _WARM_TILE_RENDERER
    source_file_paths: dict[str, str | Path] = {
        str(channel): Path(path) for channel, path in source_files.items()
    }
    _WARM_TILE_RENDERER = SatelliteTileRenderer.from_sources(
        channel_key,
        source_file_paths,
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
        image.save(tmp_name, format="PNG", optimize=True)
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
        renderer = SatelliteTileRenderer.from_sources(channel, source_files)
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
            tile_img.save(tmp_name, format="PNG", optimize=True)
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
        for x, y in sector_tile_coords(sector_key, zoom):
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
            channel, source_files_for_renderer
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
        initargs=(channel, source_file_map),
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

    zoom_list = [int(value) for value in zooms]
    if not zoom_list:
        return stats

    source_file_map = {key: str(path) for key, path in source_files.items()}
    tasks: list[dict[str, Any]] = []
    for zoom in zoom_list:
        coords = sector_tile_coords(sector_key, zoom)
        if not coords:
            continue
        tasks.append(
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
        )

    if not tasks:
        return stats

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
    sat_key = normalize_sat_id(sat_id)
    sector_key = normalize_sector(sector)
    channel = normalize_channel(channel_key)
    frame_key = str(frame.get("frame_key") or "")
    if not frame_key:
        raise ValueError("Satellite v2 frame is missing frame_key.")

    target = tile_path(cache_root, sat_key, sector_key, channel, frame_key, z, x, y)
    target_was_invalid = target.exists() and not is_valid_tile_file(target)
    if target.exists() and is_valid_tile_file(target) and not overwrite:
        return target, {"cache_status": "hit", "rendered": 0, "skipped": 1, "errors": 0}
    if is_negative_tile_cached(target) and not overwrite:
        return target, {
            "cache_status": "invalid",
            "rendered": 0,
            "skipped": 1,
            "errors": 0,
            "negative_cached": 1,
        }

    source_files = download_product_source_frames(
        cache_root, sat_key, sector_key, channel, frame
    )
    source_files_for_renderer: dict[str, str | Path] = dict(source_files)
    renderer = SatelliteTileRenderer.from_sources(channel, source_files_for_renderer)
    try:
        result = _render_tile_to_target(
            renderer, target, int(z), int(x), int(y), target_was_invalid
        )
        if result == "invalid":
            return target, {
                "cache_status": "invalid",
                "rendered": 0,
                "skipped": 0,
                "errors": 1,
            }
    except Exception:
        raise
    return target, {"cache_status": "miss", "rendered": 1, "skipped": 0, "errors": 0}
