"""Presence-driven selected-product tile warming for Meteosat Full Disk/RSS."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
import logging
import threading
import time
from typing import Callable

from config.satellite_platforms import platform_descriptor
from config.satellite_v2_config import (
    SATELLITE_V2_METEOSAT_DISK_LATITUDE_LIMIT_DEGREES,
    SATELLITE_V2_METEOSAT_DISK_LONGITUDE_RADIUS_DEGREES,
    SATELLITE_V2_METEOSAT_PREFETCH_HOURS,
    SATELLITE_V2_METEOSAT_PREFETCH_MAX_FRAMES,
    SATELLITE_V2_METEOSAT_RSS_PREFETCH_HOURS,
    SATELLITE_V2_METEOSAT_RSS_TILE_WARM_FRAMES,
    SATELLITE_V2_METEOSAT_RSS_TILE_WARM_ZOOMS,
    SATELLITE_V2_METEOSAT_TILE_WARM_FRAMES,
    SATELLITE_V2_METEOSAT_TILE_WARM_WORKERS,
    SATELLITE_V2_METEOSAT_TILE_WARM_ZOOMS,
    SATELLITE_V2_RAPID_WORKER_BOUNDS,
    normalize_channel,
    normalize_sat_id,
    normalize_sector,
)
from satellite_v2.catalog import build_catalog
from satellite_v2.tiler import warm_frame_tiles_from_canvas
from satellite_v2.worker_support import format_elapsed, resolve_cache_root


_LOGGER = logging.getLogger(__name__)
_CACHE_ROOT = str(resolve_cache_root())
_POOL_LOCK = threading.Lock()
_TILE_POOL: ProcessPoolExecutor | None = None


def meteosat_disk_bounds(sat_id: str) -> dict[str, float]:
    """Return a non-wrapping Web Mercator planning box around the platform disk."""
    sat_key = normalize_sat_id(sat_id)
    longitude = float(platform_descriptor(sat_key).get("lon_0") or 0.0)
    radius = float(SATELLITE_V2_METEOSAT_DISK_LONGITUDE_RADIUS_DEGREES)
    latitude = float(SATELLITE_V2_METEOSAT_DISK_LATITUDE_LIMIT_DEGREES)
    return {
        "west": max(-180.0, longitude - radius),
        "south": -latitude,
        "east": min(180.0, longitude + radius),
        "north": latitude,
    }


def _tile_warm_policy(
    sat_id: str, sector: str
) -> tuple[int, tuple[int, ...], int, dict[str, float]] | None:
    sat_key = normalize_sat_id(sat_id)
    sector_key = normalize_sector(sector)
    if sat_key in {"meteosat9", "meteosat12"} and sector_key == "FULLDISK":
        return (
            int(SATELLITE_V2_METEOSAT_TILE_WARM_FRAMES),
            tuple(int(zoom) for zoom in SATELLITE_V2_METEOSAT_TILE_WARM_ZOOMS),
            int(SATELLITE_V2_METEOSAT_PREFETCH_HOURS),
            meteosat_disk_bounds(sat_key),
        )
    if sat_key == "meteosat11" and sector_key == "RSS":
        return (
            int(SATELLITE_V2_METEOSAT_RSS_TILE_WARM_FRAMES),
            tuple(int(zoom) for zoom in SATELLITE_V2_METEOSAT_RSS_TILE_WARM_ZOOMS),
            int(SATELLITE_V2_METEOSAT_RSS_PREFETCH_HOURS),
            {
                key: float(value)
                for key, value in SATELLITE_V2_RAPID_WORKER_BOUNDS["RSS"].items()
            },
        )
    return None


def _get_tile_pool() -> ProcessPoolExecutor | None:
    global _TILE_POOL
    workers = max(1, int(SATELLITE_V2_METEOSAT_TILE_WARM_WORKERS))
    if workers <= 1:
        return None
    with _POOL_LOCK:
        if _TILE_POOL is None:
            _TILE_POOL = ProcessPoolExecutor(max_workers=workers)
        return _TILE_POOL


def shutdown_meteosat_tile_pool() -> None:
    global _TILE_POOL
    with _POOL_LOCK:
        pool = _TILE_POOL
        _TILE_POOL = None
    if pool is not None:
        pool.shutdown(wait=False, cancel_futures=True)


def run_selected_meteosat_tile_warmer(
    *,
    sat_id: str,
    sector: str,
    channel: str,
    should_continue: Callable[[], bool] | None = None,
    wait_until_ready: Callable[[], bool] | None = None,
) -> dict[str, int]:
    """Warm a bounded newest-frame tail for the currently selected product."""
    sat_key = normalize_sat_id(sat_id)
    sector_key = normalize_sector(sector)
    channel_key = normalize_channel(channel)
    policy = _tile_warm_policy(sat_key, sector_key)
    if policy is None:
        return {
            "cataloged": 0,
            "frames": 0,
            "rendered": 0,
            "skipped": 0,
            "errors": 0,
            "cancelled": 0,
        }

    if should_continue is not None and not should_continue():
        return {
            "cataloged": 0,
            "frames": 0,
            "rendered": 0,
            "skipped": 0,
            "errors": 0,
            "cancelled": 1,
        }

    frames_to_warm, zooms, catalog_hours, bounds = policy
    started = time.perf_counter()
    payload = build_catalog(
        cache_root=_CACHE_ROOT,
        sat_id=sat_key,
        sector=sector_key,
        channel_key=channel_key,
        hours=catalog_hours,
        max_frames=int(SATELLITE_V2_METEOSAT_PREFETCH_MAX_FRAMES),
    )
    frames = list(payload.get("frames") or [])
    newest = list(reversed(frames[-max(1, frames_to_warm) :]))
    totals = {
        "cataloged": len(frames),
        "frames": 0,
        "rendered": 0,
        "skipped": 0,
        "errors": 0,
        "cancelled": 0,
    }
    pool = None if sat_key == "meteosat12" else _get_tile_pool()
    render_workers = 1 if sat_key == "meteosat12" else int(SATELLITE_V2_METEOSAT_TILE_WARM_WORKERS)

    _LOGGER.info(
        "Meteosat tile warm start selection=%s/%s/%s frames=%s zooms=%s "
        "workers=%s bounds=%s",
        sat_key,
        sector_key,
        channel_key,
        len(newest),
        zooms,
        render_workers,
        bounds,
    )
    for frame in newest:
        if should_continue is not None and not should_continue():
            totals["cancelled"] = 1
            break
        if wait_until_ready is not None and not wait_until_ready():
            totals["cancelled"] = 1
            break
        frame_started = time.perf_counter()
        stats = warm_frame_tiles_from_canvas(
            cache_root=_CACHE_ROOT,
            sat_id=sat_key,
            sector=sector_key,
            channel_key=channel_key,
            frame=frame,
            zooms=zooms,
            render_workers=render_workers,
            tile_bounds=bounds,
            pool=pool,
            should_continue=should_continue,
            wait_until_ready=wait_until_ready,
        )
        totals["frames"] += 1
        for key in ("rendered", "skipped", "errors"):
            totals[key] += int(stats.get(key) or 0)
        if int(stats.get("cancelled") or 0):
            totals["cancelled"] = 1
        _LOGGER.info(
            "Meteosat tile warm frame=%s/%s/%s/%s rendered=%s skipped=%s "
            "errors=%s cancelled=%s elapsed=%s",
            sat_key,
            sector_key,
            channel_key,
            frame.get("frame_key"),
            stats.get("rendered"),
            stats.get("skipped"),
            stats.get("errors"),
            stats.get("cancelled"),
            format_elapsed(time.perf_counter() - frame_started),
        )
        if totals["cancelled"]:
            break

    if totals["rendered"] > 0 or totals["errors"] > 0:
        build_catalog(
            cache_root=_CACHE_ROOT,
            sat_id=sat_key,
            sector=sector_key,
            channel_key=channel_key,
            hours=catalog_hours,
            max_frames=int(SATELLITE_V2_METEOSAT_PREFETCH_MAX_FRAMES),
        )
    _LOGGER.info(
        "Meteosat tile warm complete selection=%s/%s/%s frames=%s rendered=%s "
        "skipped=%s errors=%s cancelled=%s elapsed=%s",
        sat_key,
        sector_key,
        channel_key,
        totals["frames"],
        totals["rendered"],
        totals["skipped"],
        totals["errors"],
        totals["cancelled"],
        format_elapsed(time.perf_counter() - started),
    )
    return totals
