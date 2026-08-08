"""Narrow rapid-scan warmer for Satellite v2.

This worker is intentionally separate from the broad Satellite v2 scheduled
workers.  It warms only high-cadence sectors where animation latency matters;
Full Disk and CONUS stay live-rendered/cache-assisted by default.
"""

from __future__ import annotations

import logging

import argparse
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
import os
from pathlib import Path
import time
from typing import Callable, Iterable

from config.satellite_v2_config import (
    SATELLITE_V2_RAPID_WORKER_BOUNDS,
    SATELLITE_V2_RAPID_WORKER_FRAMES,
    SATELLITE_V2_RAPID_WORKER_FRESH_WINDOW_SECONDS,
    SATELLITE_V2_RAPID_WORKER_HOURS,
    SATELLITE_V2_RAPID_WORKER_JOBS,
    SATELLITE_V2_RAPID_WORKER_MAX_FRAMES,
    SATELLITE_V2_RAPID_WORKER_PRODUCTS,
    SATELLITE_V2_RAPID_WORKER_TILE_BUFFER,
    SATELLITE_V2_RAPID_WORKER_TILE_WORKERS,
    SATELLITE_V2_RAPID_WORKER_ZOOMS,
    normalize_channel,
    normalize_sat_id,
    normalize_sector,
)
from satellite_v2.catalog import build_catalog
from satellite_v2.tiler import warm_frame_tiles_from_canvas
from workers._freshness import is_cache_fresh, mark_run_complete, redirect_stdio_to_log


_BASE_DIR = Path(__file__).resolve().parent.parent
_WORKER_NAME = "satellite_v2_rapid"
TileBounds = tuple[float, float, float, float]


def _resolve_cache_root() -> Path:
    configured = os.environ.get("WX_DASHBOARD_CACHE_ROOT") or os.environ.get(
        "WX_SATELLITE_V2_CACHE_ROOT"
    )
    return Path(configured or (_BASE_DIR / "cache")).expanduser().resolve()


_CACHE_ROOT = str(_resolve_cache_root())
_WORKER_STATE_DIR = Path(_CACHE_ROOT) / ".workers"


def _format_elapsed(seconds: float) -> str:
    total = max(0, int(round(float(seconds))))
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m {secs}s"


def _ordered_unique(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        key = str(value).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        ordered.append(key)
    return tuple(ordered)


def _parse_csv(value: str | None) -> tuple[str, ...] | None:
    if not value:
        return None
    return _ordered_unique(part.strip() for part in value.split(","))


def _parse_jobs(value: str | None) -> tuple[tuple[str, str], ...] | None:
    if not value:
        return None
    jobs: list[tuple[str, str]] = []
    for raw in value.split(","):
        if ":" not in raw:
            raise ValueError("--jobs entries must be formatted as sat_id:sector")
        sat_id, sector = (part.strip() for part in raw.split(":", 1))
        jobs.append((normalize_sat_id(sat_id), normalize_sector(sector)))
    return tuple(jobs)


def _bounds_for_sector(sector: str) -> TileBounds | None:
    bounds = SATELLITE_V2_RAPID_WORKER_BOUNDS.get(normalize_sector(sector))
    if not bounds:
        return None
    return (
        float(bounds["west"]),
        float(bounds["south"]),
        float(bounds["east"]),
        float(bounds["north"]),
    )


def _zooms_for_sector(sector: str) -> tuple[int, ...]:
    zooms = SATELLITE_V2_RAPID_WORKER_ZOOMS.get(normalize_sector(sector), ())
    return tuple(int(value) for value in zooms)


@contextmanager
def _worker_lock(worker_name: str):
    _WORKER_STATE_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = _WORKER_STATE_DIR / f"{worker_name}.lock"
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        logging.getLogger(__name__).info(f"[{worker_name}] skipped: lock exists at {lock_path}")
        yield False
        return
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(datetime.now(timezone.utc).isoformat())
            handle.write("\n")
        yield True
    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def _warm_one_job(
    worker_name: str,
    sat_id: str,
    sector: str,
    channel: str,
    frames_to_warm: int,
    hours: int,
    max_frames: int,
    tile_workers: int,
    tile_buffer: int,
    pool: ProcessPoolExecutor | None,
    should_continue: Callable[[], bool] | None = None,
) -> dict[str, int]:
    sat_key = normalize_sat_id(sat_id)
    sector_key = normalize_sector(sector)
    channel_key = normalize_channel(channel)
    zooms = _zooms_for_sector(sector_key)
    if not zooms:
        logging.getLogger(__name__).info(f"[{worker_name}] skip {sat_key}/{sector_key}/{channel_key}: no zooms")
        return {"cataloged": 0, "frames": 0, "rendered": 0, "skipped": 0, "errors": 0}

    job_start = time.perf_counter()
    payload = build_catalog(
        cache_root=_CACHE_ROOT,
        sat_id=sat_key,
        sector=sector_key,
        channel_key=channel_key,
        hours=hours,
        max_frames=max_frames,
    )
    frames = list(payload.get("frames") or [])
    newest = list(reversed(frames[-max(1, int(frames_to_warm)) :]))
    tile_bounds = _bounds_for_sector(sector_key)
    totals = {
        "cataloged": len(frames),
        "frames": 0,
        "rendered": 0,
        "skipped": 0,
        "errors": 0,
    }
    logging.getLogger(__name__).info(
        f"[{worker_name}] {sat_key}/{sector_key}/{channel_key}: "
        f"cataloged={len(frames)} warming={len(newest)} zooms={zooms} "
        f"tile_workers={tile_workers} bounds={'frame/default' if tile_bounds is None else tile_bounds}"
    )
    for frame in newest:
        if should_continue is not None and not should_continue():
            logging.getLogger(__name__).info(
                f"[{worker_name}] {sat_key}/{sector_key}/{channel_key}: "
                "stopped after selection changed"
            )
            break
        frame_start = time.perf_counter()
        stats = warm_frame_tiles_from_canvas(
            cache_root=_CACHE_ROOT,
            sat_id=sat_key,
            sector=sector_key,
            channel_key=channel_key,
            frame=frame,
            zooms=zooms,
            render_workers=tile_workers,
            tile_bounds=tile_bounds,
            tile_buffer=tile_buffer,
            pool=pool,
        )
        totals["frames"] += 1
        totals["rendered"] += int(stats.get("rendered") or 0)
        totals["skipped"] += int(stats.get("skipped") or 0)
        totals["errors"] += int(stats.get("errors") or 0)
        logging.getLogger(__name__).warning(
            f"[{worker_name}] {sat_key}/{sector_key}/{channel_key}/"
            f"{frame.get('frame_key')}: rendered={stats.get('rendered')} "
            f"skipped={stats.get('skipped')} invalid={stats.get('invalid')} "
            f"errors={stats.get('errors')} elapsed={_format_elapsed(time.perf_counter() - frame_start)}"
        )

    # Refresh only when valid tiles changed. A fully warm/no-op job leaves the
    # pre-warm catalog accurate, so a second provider/catalog scan is wasted.
    if totals["rendered"] > 0 or totals["errors"] > 0:
        build_catalog(
            cache_root=_CACHE_ROOT,
            sat_id=sat_key,
            sector=sector_key,
            channel_key=channel_key,
            hours=hours,
            max_frames=max_frames,
        )
    logging.getLogger(__name__).info(
        f"[{worker_name}] {sat_key}/{sector_key}/{channel_key}: "
        f"done elapsed={_format_elapsed(time.perf_counter() - job_start)}"
    )
    return totals


def run_satellite_v2_rapid_worker(
    *,
    force: bool = False,
    jobs: Iterable[tuple[str, str]] | None = None,
    products: Iterable[str] | None = None,
    frames: int | None = None,
    hours: int | None = None,
    max_frames: int | None = None,
    tile_workers: int | None = None,
    tile_buffer: int | None = None,
    worker_name: str = _WORKER_NAME,
    should_continue: Callable[[], bool] | None = None,
) -> dict[str, int]:
    fresh_window = int(SATELLITE_V2_RAPID_WORKER_FRESH_WINDOW_SECONDS)
    if not force and is_cache_fresh(worker_name, fresh_window):
        logging.getLogger(__name__).info(f"[{worker_name}] skipped: fresh sentinel within {fresh_window}s")
        return {"jobs": 0, "frames": 0, "rendered": 0, "skipped": 0, "errors": 0}

    selected_jobs = tuple(jobs or SATELLITE_V2_RAPID_WORKER_JOBS)
    selected_products = tuple(products or SATELLITE_V2_RAPID_WORKER_PRODUCTS)
    frame_count = int(frames or SATELLITE_V2_RAPID_WORKER_FRAMES)
    hours_value = int(hours or SATELLITE_V2_RAPID_WORKER_HOURS)
    max_frames_value = int(max_frames or SATELLITE_V2_RAPID_WORKER_MAX_FRAMES)
    workers_value = int(tile_workers or SATELLITE_V2_RAPID_WORKER_TILE_WORKERS)
    buffer_value = int(
        SATELLITE_V2_RAPID_WORKER_TILE_BUFFER if tile_buffer is None else tile_buffer
    )

    totals = {"jobs": 0, "frames": 0, "rendered": 0, "skipped": 0, "errors": 0}
    with _worker_lock(worker_name) as acquired:
        if not acquired:
            return totals
        run_start = time.perf_counter()
        pool_context = (
            nullcontext(None)
            if workers_value <= 1
            else ProcessPoolExecutor(max_workers=workers_value)
        )
        with pool_context as tile_pool:
            for sat_id, sector in selected_jobs:
                for channel in selected_products:
                    if should_continue is not None and not should_continue():
                        break
                    stats = _warm_one_job(
                        worker_name,
                        sat_id,
                        sector,
                        channel,
                        frame_count,
                        hours_value,
                        max_frames_value,
                        workers_value,
                        buffer_value,
                        tile_pool,
                        should_continue,
                    )
                    totals["jobs"] += 1
                    totals["frames"] += int(stats.get("frames") or 0)
                    totals["rendered"] += int(stats.get("rendered") or 0)
                    totals["skipped"] += int(stats.get("skipped") or 0)
                    totals["errors"] += int(stats.get("errors") or 0)
                if should_continue is not None and not should_continue():
                    break
        mark_run_complete(worker_name)
        logging.getLogger(__name__).warning(
            f"[{worker_name}] complete jobs={totals['jobs']} frames={totals['frames']} "
            f"rendered={totals['rendered']} skipped={totals['skipped']} "
            f"errors={totals['errors']} elapsed={_format_elapsed(time.perf_counter() - run_start)}"
        )
    return totals


def main() -> None:
    parser = argparse.ArgumentParser(description="Warm narrow Satellite v2 rapid sectors")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--log-to-file", action="store_true")
    parser.add_argument("--jobs", help="Comma list of sat_id:sector entries")
    parser.add_argument("--products", help="Comma list of product/channel keys")
    parser.add_argument("--frames", type=int, default=None)
    parser.add_argument("--hours", type=int, default=None)
    parser.add_argument("--max-frames", type=int, default=None)
    parser.add_argument("--tile-workers", type=int, default=None)
    parser.add_argument("--tile-buffer", type=int, default=None)
    args = parser.parse_args()
    if args.log_to_file:
        redirect_stdio_to_log(_WORKER_NAME)
    run_satellite_v2_rapid_worker(
        force=args.force,
        jobs=_parse_jobs(args.jobs),
        products=_parse_csv(args.products),
        frames=args.frames,
        hours=args.hours,
        max_frames=args.max_frames,
        tile_workers=args.tile_workers,
        tile_buffer=args.tile_buffer,
    )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    main()
