"""FastAPI-facing service functions for Satellite v2."""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import matplotlib.colors as mcolors
import numpy as np

from config.satellite_config import ABI_CHANNELS
from config.satellite_v2_config import (
    SATELLITE_V2_PRODUCTS,
    normalize_channel,
    normalize_sat_id,
    normalize_sector,
)
from satellite_v2 import catalog
from satellite_v2.cache import (
    catalog_path,
    is_negative_tile_cached,
    is_valid_tile_file,
    read_json,
    tile_path,
)
from satellite_v2.provider_aws import list_recent_frames
from satellite_v2.tiler import render_frame_tile


logger = logging.getLogger(__name__)


_ON_DEMAND_CATALOG_HOURS = 12
_ON_DEMAND_CATALOG_MAX_FRAMES = 360
_LEGEND_ANCHOR_COUNT = 65
_LEGEND_TICK_COUNT = 7
_ON_DEMAND_TILE_RENDER_WORKERS = 10
_ON_DEMAND_TILE_RENDER_POOL = ThreadPoolExecutor(
    max_workers=_ON_DEMAND_TILE_RENDER_WORKERS,
    thread_name_prefix="sat-v2-live",
)


def shutdown_live_tile_pool() -> None:
    _ON_DEMAND_TILE_RENDER_POOL.shutdown(wait=False, cancel_futures=True)


def _format_number(value: float) -> str:
    rounded = round(value)
    if abs(value - rounded) < 0.05:
        return str(int(rounded))
    return f"{value:.1f}"


def _brightness_temperature_label(value_k: float) -> str:
    value_c = value_k - 273.15
    return f"{_format_number(value_c)}°C"


def _color_for_value(cmap: Any, norm: Any, value: float) -> str:
    normalized = norm(value) if norm is not None else value
    return mcolors.to_hex(cmap(normalized), keep_alpha=False)


def get_legend_payload(channel: str) -> dict[str, Any]:
    channel_key = normalize_channel(channel)
    product = SATELLITE_V2_PRODUCTS[channel_key]
    metadata = ABI_CHANNELS[channel_key]

    if product.kind == "reflectance":
        return {
            "status": "success",
            "available": False,
            "channel": channel_key,
            "title": product.label,
            "kind": product.kind,
            "reason": "visible_reflectance",
        }
    if product.kind == "composite":
        return {
            "status": "success",
            "available": False,
            "channel": channel_key,
            "title": product.label,
            "kind": product.kind,
            "reason": "rgb_composite",
        }

    cmap = metadata.get("cmap")
    norm = metadata.get("norm")
    vmin = getattr(norm, "vmin", None)
    vmax = getattr(norm, "vmax", None)
    if cmap is None or norm is None or vmin is None or vmax is None:
        return {
            "status": "success",
            "available": False,
            "channel": channel_key,
            "title": product.label,
            "kind": product.kind,
            "reason": "no_scalar_colormap",
        }

    vmin_f = float(vmin)
    vmax_f = float(vmax)
    if not np.isfinite(vmin_f) or not np.isfinite(vmax_f) or vmin_f == vmax_f:
        return {
            "status": "success",
            "available": False,
            "channel": channel_key,
            "title": product.label,
            "kind": product.kind,
            "reason": "invalid_colormap_range",
        }

    anchors = [
        {
            "value": round(float(value), 3),
            "color": _color_for_value(cmap, norm, float(value)),
        }
        for value in np.linspace(vmin_f, vmax_f, _LEGEND_ANCHOR_COUNT)
    ]
    ticks = [
        {
            "value": round(float(value), 3),
            "label": _brightness_temperature_label(float(value)),
        }
        for value in np.linspace(vmin_f, vmax_f, _LEGEND_TICK_COUNT)
    ]
    return {
        "status": "success",
        "available": True,
        "channel": channel_key,
        "title": product.label,
        "kind": product.kind,
        "units": "°C",
        "value_units": product.units,
        "vmin": vmin_f,
        "vmax": vmax_f,
        "anchors": anchors,
        "ticks": ticks,
    }


def _catalog_frame_for_tile(
    cache_root: str,
    sat_id: str,
    sector: str,
    channel: str,
    frame_key: str,
) -> dict[str, Any]:
    cached = read_json(catalog_path(cache_root, sat_id, sector, channel))
    for frame in (cached or {}).get("frames") or []:
        if str(frame.get("frame_key") or "") == str(frame_key or ""):
            return frame

    frames = list_recent_frames(
        sat_id=sat_id,
        sector=sector,
        channel_key=channel,
        hours=_ON_DEMAND_CATALOG_HOURS,
        max_frames=_ON_DEMAND_CATALOG_MAX_FRAMES,
    )
    for frame in frames:
        if str(frame.frame_key or "") == str(frame_key or ""):
            return frame.to_dict()
    raise ValueError(f"Satellite v2 frame '{frame_key}' was not found in the catalog.")


def get_catalog_payload(
    cache_root: str,
    sat_id: str,
    sector: str,
    channel: str,
    hours: int,
    max_frames: int,
    refresh: bool,
) -> dict[str, Any]:
    return catalog.get_catalog(
        cache_root=cache_root,
        sat_id=sat_id,
        sector=sector,
        channel_key=channel,
        hours=hours,
        max_frames=max_frames,
        refresh=refresh,
    )


def get_status_payload(cache_root: str) -> dict[str, Any]:
    return catalog.status_payload(cache_root)


def resolve_tile(
    cache_root: str,
    sat_id: str,
    sector: str,
    channel: str,
    frame_key: str,
    z: int,
    x: int,
    y: int,
    allow_render: bool = True,
) -> tuple[Path, dict[str, Any]]:
    started = time.perf_counter()
    sat_key = normalize_sat_id(sat_id)
    sector_key = normalize_sector(sector)
    channel_key = normalize_channel(channel)
    path = tile_path(cache_root, sat_key, sector_key, channel_key, frame_key, z, x, y)
    path_exists_before = path.exists()
    path_size_before = int(path.stat().st_size) if path_exists_before else 0
    tile_valid = is_valid_tile_file(path) if path_exists_before else False
    cache_status = "hit"
    miss_reason = ""
    if not tile_valid:
        miss_reason = "missing" if not path_exists_before else "invalid"
        if not allow_render:
            cache_status = "empty"
            stats = {
                "cache_status": cache_status,
                "miss_reason": miss_reason,
                "tile_exists_before": path_exists_before,
                "tile_size_before": path_size_before,
                "elapsed_ms": int((time.perf_counter() - started) * 1000),
                "provider": "aws",
                "frame_key": frame_key,
                "sat_id": sat_key,
                "sector": sector_key,
                "channel": channel_key,
            }
            return path, stats
        if is_negative_tile_cached(path):
            cache_status = "invalid"
            stats = {
                "cache_status": cache_status,
                "miss_reason": "negative-cache",
                "tile_exists_before": path_exists_before,
                "tile_size_before": path_size_before,
                "elapsed_ms": int((time.perf_counter() - started) * 1000),
                "provider": "aws",
                "frame_key": frame_key,
                "sat_id": sat_key,
                "sector": sector_key,
                "channel": channel_key,
                "negative_cached": 1,
            }
            return path, stats
        frame = _catalog_frame_for_tile(
            cache_root, sat_key, sector_key, channel_key, frame_key
        )
        tile_id = f"{sat_key}/{sector_key}/{channel_key}/{z}/{x}/{y}"
        print(
            "[satellite-v2 tile] "
            f"render_start frame_key={frame_key} tile={tile_id} "
            f"workers={_ON_DEMAND_TILE_RENDER_WORKERS} "
            f"miss_reason={miss_reason} file_exists={path_exists_before} "
            f"file_size={path_size_before}",
            flush=True,
        )
        logger.info("Submitting tile render: %s", tile_id)
        future = _ON_DEMAND_TILE_RENDER_POOL.submit(
            render_frame_tile,
            cache_root=cache_root,
            sat_id=sat_key,
            sector=sector_key,
            channel_key=channel_key,
            frame=frame,
            z=z,
            x=x,
            y=y,
        )
        render_start = time.perf_counter()
        path, render_stats = future.result()
        render_elapsed = int((time.perf_counter() - render_start) * 1000)
        print(
            "[satellite-v2 tile] "
            f"render_complete frame_key={frame_key} tile={tile_id} "
            f"cache_status={str(render_stats.get('cache_status') or 'miss').upper()} "
            f"render_ms={render_elapsed}",
            flush=True,
        )
        logger.info("Tile render complete: %s (%sms)", tile_id, render_elapsed)
        cache_status = str(render_stats.get("cache_status") or "miss")
    stats = {
        "cache_status": cache_status,
        "miss_reason": miss_reason,
        "tile_exists_before": path_exists_before,
        "tile_size_before": path_size_before,
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
        "provider": "aws",
        "frame_key": frame_key,
        "sat_id": sat_key,
        "sector": sector_key,
        "channel": channel_key,
    }
    return path, stats
