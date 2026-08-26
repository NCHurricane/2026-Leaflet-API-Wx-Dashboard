"""FastAPI-facing service functions for Satellite v2."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from concurrent.futures import CancelledError, Future, ThreadPoolExecutor, TimeoutError
from functools import partial
import logging
import threading
import time
from pathlib import Path
from typing import Any, Callable

import matplotlib.colors as mcolors
import numpy as np
from pyproj import Transformer

from config.satellite_platforms import PROVIDER_EUMETSAT, platform_descriptor
from config.satellite_v2_config import (
    ABI_CHANNELS,
    SATELLITE_V2_INTERPRETIVE_LEGENDS,
    SATELLITE_V2_LEGEND_ANCHOR_COUNT,
    SATELLITE_V2_LEGEND_TICK_COUNT,
    SATELLITE_V2_LIVE_TILE_RENDER_WORKERS,
    SATELLITE_V2_METEOSAT_PREFETCH_JOBS,
    SATELLITE_V2_METEOSAT_RSS_PREFETCH_FRAMES,
    SATELLITE_V2_METEOSAT_RSS_PREFETCH_HOURS,
    SATELLITE_V2_METEOSAT_RSS_PREFETCH_KEEP_HOURS,
    SATELLITE_V2_METEOSAT_RSS_TILE_WARM_FRESH_WINDOW_SECONDS,
    SATELLITE_V2_METEOSAT_RSS_TILE_WARM_JOBS,
    SATELLITE_V2_METEOSAT_RSS_TILE_WARM_ZOOMS,
    SATELLITE_V2_METEOSAT_TILE_WARM_FRESH_WINDOW_SECONDS,
    SATELLITE_V2_METEOSAT_TILE_WARM_WORKERS,
    SATELLITE_V2_METEOSAT_TILE_WARM_ZOOMS,
    SATELLITE_V2_ON_DEMAND_CATALOG_HOURS,
    SATELLITE_V2_ON_DEMAND_CATALOG_MAX_FRAMES,
    SATELLITE_V2_PRODUCTS,
    SATELLITE_V2_RAPID_WORKER_FRESH_WINDOW_SECONDS,
    SATELLITE_V2_RAPID_WORKER_JOBS,
    SATELLITE_V2_RAPID_WORKER_PRODUCTS,
    SATELLITE_V2_RAPID_WORKER_ZOOMS,
    normalize_channel,
    normalize_sat_id,
    normalize_sector,
    satellite_v2_render_version_for_satellite,
    source_channels_for_product,
)
from satellite_v2 import catalog
from satellite_v2._bench_timing import begin_timing, bench_enabled, finish_timing
from satellite_v2.cache import (
    catalog_path,
    is_negative_tile_cached,
    is_valid_tile_file,
    read_json,
    tile_path,
)
from satellite_v2 import providers
from satellite_v2.providers import download_product_source_frames, list_recent_frames
from satellite_v2.renderer import _load_source_raster, estimate_source_grid_bytes
from satellite_v2.tiler import render_frame_tile


logger = logging.getLogger(__name__)


_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


_ON_DEMAND_TILE_RENDER_POOL = ThreadPoolExecutor(
    max_workers=SATELLITE_V2_LIVE_TILE_RENDER_WORKERS,
    thread_name_prefix="sat-v2-live",
)
_TILE_REQUEST_WAIT_POOL = ThreadPoolExecutor(
    max_workers=SATELLITE_V2_LIVE_TILE_RENDER_WORKERS,
    thread_name_prefix="sat-v2-request",
)
_IN_FLIGHT_TILE_RENDERS: dict[Path, Future] = {}
_IN_FLIGHT_TILE_RENDERS_LOCK = threading.RLock()
_SATELLITE_SELECTIONS: dict[str, tuple[tuple[str, str, str], float]] = {}
_SATELLITE_FRAME_REQUESTS: dict[
    str, tuple[tuple[str, str, str], str, int, float]
] = {}
_SATELLITE_SELECTIONS_LOCK = threading.RLock()
_SATELLITE_SELECTION_TTL_SECONDS = 10 * 60.0


def _record_satellite_selection(
    client_id: str | None, selection: tuple[str, str, str]
) -> None:
    normalized_client_id = str(client_id or "").strip()[:128]
    if not normalized_client_id:
        return
    now = time.monotonic()
    with _SATELLITE_SELECTIONS_LOCK:
        expired = [
            key
            for key, (_, expires_at) in _SATELLITE_SELECTIONS.items()
            if expires_at <= now
        ]
        for key in expired:
            _SATELLITE_SELECTIONS.pop(key, None)
            _SATELLITE_FRAME_REQUESTS.pop(key, None)
        active_frame_request = _SATELLITE_FRAME_REQUESTS.get(normalized_client_id)
        if active_frame_request is not None and active_frame_request[0] != selection:
            _SATELLITE_FRAME_REQUESTS.pop(normalized_client_id, None)
        _SATELLITE_SELECTIONS[normalized_client_id] = (
            selection,
            now + _SATELLITE_SELECTION_TTL_SECONDS,
        )


def release_satellite_selection(client_id: str | None) -> None:
    normalized_client_id = str(client_id or "").strip()[:128]
    if not normalized_client_id:
        return
    with _SATELLITE_SELECTIONS_LOCK:
        _SATELLITE_SELECTIONS.pop(normalized_client_id, None)
        _SATELLITE_FRAME_REQUESTS.pop(normalized_client_id, None)


def _satellite_client_owns_selection(
    client_id: str | None, selection: tuple[str, str, str]
) -> bool:
    normalized_client_id = str(client_id or "").strip()[:128]
    if not normalized_client_id:
        return True
    now = time.monotonic()
    with _SATELLITE_SELECTIONS_LOCK:
        active = _SATELLITE_SELECTIONS.get(normalized_client_id)
        if active is None:
            return False
        active_selection, expires_at = active
        if expires_at <= now:
            _SATELLITE_SELECTIONS.pop(normalized_client_id, None)
            return False
        return active_selection == selection


def _record_satellite_frame_request(
    client_id: str | None,
    selection: tuple[str, str, str],
    foreground_frame_key: str | None,
    frame_generation: int | None,
) -> None:
    normalized_client_id = str(client_id or "").strip()[:128]
    normalized_frame_key = str(foreground_frame_key or "").strip()[:256]
    try:
        normalized_generation = int(frame_generation or 0)
    except (TypeError, ValueError):
        normalized_generation = 0
    if (
        not normalized_client_id
        or not normalized_frame_key
        or normalized_generation <= 0
    ):
        return
    now = time.monotonic()
    with _SATELLITE_SELECTIONS_LOCK:
        active_selection = _SATELLITE_SELECTIONS.get(normalized_client_id)
        if active_selection is None:
            return
        owned_selection, selection_expires_at = active_selection
        if selection_expires_at <= now or owned_selection != selection:
            if selection_expires_at <= now:
                _SATELLITE_SELECTIONS.pop(normalized_client_id, None)
                _SATELLITE_FRAME_REQUESTS.pop(normalized_client_id, None)
            return
        active_request = _SATELLITE_FRAME_REQUESTS.get(normalized_client_id)
        if active_request is not None:
            active_request_selection, _, active_generation, expires_at = active_request
            if expires_at > now and active_request_selection == selection:
                if active_generation > normalized_generation:
                    return
                if (
                    active_generation == normalized_generation
                    and active_request[1] != normalized_frame_key
                ):
                    return
        _SATELLITE_FRAME_REQUESTS[normalized_client_id] = (
            selection,
            normalized_frame_key,
            normalized_generation,
            now + _SATELLITE_SELECTION_TTL_SECONDS,
        )


def _satellite_client_owns_frame_request(
    client_id: str | None,
    selection: tuple[str, str, str],
    tile_frame_key: str,
    foreground_frame_key: str | None,
    frame_generation: int | None,
) -> bool:
    normalized_client_id = str(client_id or "").strip()[:128]
    if not normalized_client_id:
        return True
    normalized_foreground_key = str(foreground_frame_key or "").strip()[:256]
    try:
        normalized_generation = int(frame_generation or 0)
    except (TypeError, ValueError):
        normalized_generation = 0
    if not normalized_foreground_key or normalized_generation <= 0:
        return _satellite_client_owns_selection(normalized_client_id, selection)
    now = time.monotonic()
    with _SATELLITE_SELECTIONS_LOCK:
        active_selection = _SATELLITE_SELECTIONS.get(normalized_client_id)
        if active_selection is None:
            return False
        owned_selection, selection_expires_at = active_selection
        if selection_expires_at <= now:
            _SATELLITE_SELECTIONS.pop(normalized_client_id, None)
            _SATELLITE_FRAME_REQUESTS.pop(normalized_client_id, None)
            return False
        if owned_selection != selection:
            return False
        active_request = _SATELLITE_FRAME_REQUESTS.get(normalized_client_id)
        if active_request is None:
            return False
        request_selection, active_foreground_key, active_generation, expires_at = (
            active_request
        )
        if expires_at <= now:
            _SATELLITE_FRAME_REQUESTS.pop(normalized_client_id, None)
            return False
        if request_selection != selection:
            return False
        return (
            active_foreground_key == str(tile_frame_key or "")
            or (
                active_foreground_key == normalized_foreground_key
                and active_generation == normalized_generation
            )
        )


def _satellite_frame_request_is_active(
    client_id: str | None,
    selection: tuple[str, str, str],
    tile_frame_key: str,
    foreground_frame_key: str | None,
    frame_generation: int | None,
) -> bool:
    if _satellite_client_owns_frame_request(
        client_id,
        selection,
        tile_frame_key,
        foreground_frame_key,
        frame_generation,
    ):
        return True
    normalized_client_id = str(client_id or "").strip()[:128]
    now = time.monotonic()
    with _SATELLITE_SELECTIONS_LOCK:
        expired = [
            key
            for key, (_, expires_at) in _SATELLITE_SELECTIONS.items()
            if expires_at <= now
        ]
        for key in expired:
            _SATELLITE_SELECTIONS.pop(key, None)
            _SATELLITE_FRAME_REQUESTS.pop(key, None)
        return any(
            key != normalized_client_id and active_selection == selection
            for key, (active_selection, _) in _SATELLITE_SELECTIONS.items()
        )


def _satellite_selection_is_active(selection: tuple[str, str, str]) -> bool:
    now = time.monotonic()
    with _SATELLITE_SELECTIONS_LOCK:
        expired = [
            key
            for key, (_, expires_at) in _SATELLITE_SELECTIONS.items()
            if expires_at <= now
        ]
        for key in expired:
            _SATELLITE_SELECTIONS.pop(key, None)
            _SATELLITE_FRAME_REQUESTS.pop(key, None)
        return any(
            active_selection == selection
            for active_selection, _ in _SATELLITE_SELECTIONS.values()
        )


def _wait_for_live_tile_idle(
    timeout_seconds: float = 120.0,
    should_continue: Callable[[], bool] | None = None,
) -> bool:
    """Let current viewport tiles finish before a selected-page accelerator."""
    deadline = time.monotonic() + max(0.0, float(timeout_seconds))
    while True:
        if should_continue is not None and not should_continue():
            return False
        with _IN_FLIGHT_TILE_RENDERS_LOCK:
            active = any(
                not future.done() for future in _IN_FLIGHT_TILE_RENDERS.values()
            )
        if not active:
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)


class _TileRenderCancelled(RuntimeError):
    pass


def _render_tile_with_budget(
    render_should_continue: Callable[[], bool] | None = None,
    **render_kwargs: Any,
):
    from app_core.render_budget import satellite_render_slot

    estimated_bytes = estimate_source_grid_bytes(
        str(render_kwargs.get("sat_id") or ""),
        str(render_kwargs.get("channel_key") or ""),
        destination_zoom=int(render_kwargs.get("z") or 0),
    )
    with satellite_render_slot(
        estimated_bytes,
        should_continue=render_should_continue,
    ) as acquired:
        if not acquired:
            raise _TileRenderCancelled("Satellite tile render ownership ended.")
        path, stats = render_frame_tile(**render_kwargs)
        stats["estimated_memory_bytes"] = estimated_bytes
        return path, stats


def _submit_tile_render(
    target: Path,
    *,
    client_id: str | None = None,
    selection: tuple[str, str, str] | None = None,
    tile_frame_key: str = "",
    foreground_frame_key: str | None = None,
    frame_generation: int | None = None,
    **render_kwargs: Any,
) -> tuple[Future, bool]:
    key = target.resolve()
    with _IN_FLIGHT_TILE_RENDERS_LOCK:
        existing = _IN_FLIGHT_TILE_RENDERS.get(key)
        if existing is not None:
            return existing, False
        render_should_continue = (
            (
                lambda: _satellite_frame_request_is_active(
                    client_id,
                    selection,
                    tile_frame_key,
                    foreground_frame_key,
                    frame_generation,
                )
            )
            if str(client_id or "").strip() and selection is not None
            else None
        )
        future = _ON_DEMAND_TILE_RENDER_POOL.submit(
            _render_tile_with_budget,
            render_should_continue=render_should_continue,
            **render_kwargs,
        )
        _IN_FLIGHT_TILE_RENDERS[key] = future

        def _release(completed: Future) -> None:
            with _IN_FLIGHT_TILE_RENDERS_LOCK:
                if _IN_FLIGHT_TILE_RENDERS.get(key) is completed:
                    _IN_FLIGHT_TILE_RENDERS.pop(key, None)
            if completed.cancelled():
                return
            error = completed.exception()
            if error is not None and not isinstance(error, _TileRenderCancelled):
                logger.warning("Satellite tile render failed for %s: %s", key, error)

        future.add_done_callback(_release)
        return future, True


def _provider_name_for_sat(sat_id: str) -> str:
    try:
        return str(platform_descriptor(sat_id).get("provider") or "unknown")
    except ValueError:
        return "unknown"


def _cancelled_tile_stats(
    *,
    started: float,
    path_exists_before: bool,
    path_size_before: int,
    sat_id: str,
    sector: str,
    channel: str,
    frame_key: str,
) -> dict[str, Any]:
    return {
        "cache_status": "cancelled",
        "miss_reason": "selection-released",
        "tile_exists_before": path_exists_before,
        "tile_size_before": path_size_before,
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
        "provider": _provider_name_for_sat(sat_id),
        "frame_key": frame_key,
        "sat_id": sat_id,
        "sector": sector,
        "channel": channel,
    }


def _run_selected_satellite_accelerator(
    sat_id: str,
    sector: str,
    channel: str,
    accelerator: str,
    should_continue: Callable[[], bool] | None = None,
) -> dict[str, int]:
    if not _wait_for_live_tile_idle(should_continue=should_continue):
        return {"cancelled": 1}
    if accelerator in {"meteosat-tiles", "meteosat-rss-tiles"}:
        from satellite_v2.meteosat_prefetch_worker import (
            run_satellite_v2_meteosat_prefetch_worker,
        )
        from satellite_v2.meteosat_tile_worker import (
            run_selected_meteosat_tile_warmer,
        )

        rss_tuned = accelerator == "meteosat-rss-tiles"
        source_options = (
            {
                "frames": int(SATELLITE_V2_METEOSAT_RSS_PREFETCH_FRAMES),
                "backfill": 0,
                "newest_only": True,
                "hours": int(SATELLITE_V2_METEOSAT_RSS_PREFETCH_HOURS),
                "keep_hours": int(SATELLITE_V2_METEOSAT_RSS_PREFETCH_KEEP_HOURS),
            }
            if rss_tuned
            else {}
        )
        source_stats = run_satellite_v2_meteosat_prefetch_worker(
            force=True,
            jobs=((sat_id, sector),),
            worker_name=f"app-meteosat-{sat_id}-{sector}".lower(),
            should_continue=should_continue,
            **source_options,
        )
        combined = {
            f"source_{key}": int(value or 0) for key, value in source_stats.items()
        }
        if should_continue is not None and not should_continue():
            combined["cancelled"] = 1
            return combined
        if not _wait_for_live_tile_idle(should_continue=should_continue):
            combined["cancelled"] = 1
            return combined

        from app_core.render_budget import satellite_render_slot

        configured_zooms = (
            SATELLITE_V2_METEOSAT_RSS_TILE_WARM_ZOOMS
            if rss_tuned
            else SATELLITE_V2_METEOSAT_TILE_WARM_ZOOMS
        )
        destination_zoom = max((int(value) for value in configured_zooms), default=6)
        estimated_bytes = estimate_source_grid_bytes(
            sat_id,
            channel,
            destination_zoom=destination_zoom,
        ) * max(1, int(SATELLITE_V2_METEOSAT_TILE_WARM_WORKERS))
        with satellite_render_slot(
            estimated_bytes,
            should_continue=should_continue,
        ) as acquired:
            if not acquired:
                combined["cancelled"] = 1
                return combined
            tile_stats = run_selected_meteosat_tile_warmer(
                sat_id=sat_id,
                sector=sector,
                channel=channel,
                should_continue=should_continue,
                wait_until_ready=lambda: _wait_for_live_tile_idle(
                    timeout_seconds=0.0,
                    should_continue=should_continue
                ),
            )
        combined.update(
            {f"tile_{key}": int(value or 0) for key, value in tile_stats.items()}
        )
        combined["estimated_memory_bytes"] = estimated_bytes
        combined["cancelled"] = int(tile_stats.get("cancelled") or 0)
        return combined

    from app_core.render_budget import satellite_render_slot
    from satellite_v2.rapid_worker import run_satellite_v2_rapid_worker

    zooms = SATELLITE_V2_RAPID_WORKER_ZOOMS.get(normalize_sector(sector), ())
    destination_zoom = max((int(value) for value in zooms), default=7)
    estimated_bytes = estimate_source_grid_bytes(
        sat_id,
        channel,
        destination_zoom=destination_zoom,
    )
    with satellite_render_slot(
        estimated_bytes,
        should_continue=should_continue,
    ) as acquired:
        if not acquired:
            return {"cancelled": 1}
        return run_satellite_v2_rapid_worker(
            force=True,
            jobs=((sat_id, sector),),
            products=(channel,),
            tile_workers=1,
            worker_name=f"app-rapid-{sat_id}-{sector}-{channel}".lower(),
            should_continue=should_continue,
        )


def _activate_satellite_accelerator(
    sat_id: str,
    sector: str,
    channel: str,
    client_id: str | None = None,
) -> dict[str, Any]:
    from app_core.refresh_coordinator import get_refresh_coordinator

    sat_key = normalize_sat_id(sat_id)
    sector_key = normalize_sector(sector)
    channel_key = normalize_channel(channel)
    selection = (sat_key, sector_key, channel_key)
    has_client_id = bool(str(client_id or "").strip())
    descriptor = platform_descriptor(sat_key)
    provider = (
        "eumetsat"
        if descriptor.get("provider") == PROVIDER_EUMETSAT
        else "satellite-aws"
    )
    if (sat_key, sector_key) in SATELLITE_V2_METEOSAT_PREFETCH_JOBS:
        accelerator = "meteosat-tiles"
        interval_seconds = float(
            SATELLITE_V2_METEOSAT_TILE_WARM_FRESH_WINDOW_SECONDS
        )
        key = ("satellite", "meteosat-tiles", sat_key, sector_key, channel_key)
    elif (
        (sat_key, sector_key) in SATELLITE_V2_RAPID_WORKER_JOBS
        and channel_key in SATELLITE_V2_RAPID_WORKER_PRODUCTS
    ):
        accelerator = "rapid-tiles"
        interval_seconds = float(SATELLITE_V2_RAPID_WORKER_FRESH_WINDOW_SECONDS)
        key = ("satellite", "rapid-tiles", sat_key, sector_key, channel_key)
    elif (sat_key, sector_key) in SATELLITE_V2_METEOSAT_RSS_TILE_WARM_JOBS:
        accelerator = "meteosat-rss-tiles"
        interval_seconds = float(
            SATELLITE_V2_METEOSAT_RSS_TILE_WARM_FRESH_WINDOW_SECONDS
        )
        key = (
            "satellite",
            "meteosat-rss-tiles",
            sat_key,
            sector_key,
            channel_key,
        )
    else:
        return {"accelerator": "live-on-demand", "accelerator_status": "not_needed"}

    interval_seconds = max(30.0, interval_seconds)
    submission = get_refresh_coordinator().activate_presence_job(
        key=key,
        provider=provider,
        interval_seconds=interval_seconds,
        min_success_interval_seconds=interval_seconds,
        run_immediately=False,
        initial_delay_seconds=5.0,
        function=lambda: _run_selected_satellite_accelerator(
            sat_key,
            sector_key,
            channel_key,
            accelerator,
            (
                (lambda: _satellite_selection_is_active(selection))
                if has_client_id
                else None
            ),
        ),
    )
    return {
        "accelerator": accelerator,
        "accelerator_status": submission.status,
        "accelerator_retry_after_seconds": submission.retry_after_seconds,
    }


def shutdown_live_tile_pool() -> None:
    from satellite_v2.meteosat_tile_worker import shutdown_meteosat_tile_pool

    shutdown_meteosat_tile_pool()
    _TILE_REQUEST_WAIT_POOL.shutdown(wait=False, cancel_futures=True)
    _ON_DEMAND_TILE_RENDER_POOL.shutdown(wait=False, cancel_futures=True)


async def resolve_tile_async(**kwargs: Any) -> tuple[Path, dict[str, Any]]:
    """Wait for a tile outside AnyIO's shared synchronous-request workers."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _TILE_REQUEST_WAIT_POOL,
        partial(resolve_tile, **kwargs),
    )


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
    if product.kind in ("composite", "categorical"):
        legend = SATELLITE_V2_INTERPRETIVE_LEGENDS.get(channel_key)
        if legend:
            return {
                "status": "success",
                "available": True,
                "channel": channel_key,
                "title": product.label,
                "kind": product.kind,
                "legend_type": "interpretive",
                "subtitle": legend.get("subtitle", ""),
                "items": list(legend.get("items") or ()),
            }
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

    is_aod = product.kind == "aod"
    is_frp = product.kind == "frp"

    def _scalar_label(value: float) -> str:
        if is_frp:
            return f"{value:.0f}"
        if is_aod:
            return f"{value:.2f}"
        return _brightness_temperature_label(value)

    if is_frp:
        units, axis_label = "MW", "Fire Radiative Power (MW)"
    elif is_aod:
        units, axis_label = "", "Aerosol Optical Depth (550 nm)"
    else:
        units, axis_label = "°C", None

    anchors = [
        {
            "value": round(float(value), 3),
            "color": _color_for_value(cmap, norm, float(value)),
        }
        for value in np.linspace(vmin_f, vmax_f, SATELLITE_V2_LEGEND_ANCHOR_COUNT)
    ]
    ticks = [
        {
            "value": round(float(value), 3),
            "label": _scalar_label(float(value)),
        }
        for value in np.linspace(vmin_f, vmax_f, SATELLITE_V2_LEGEND_TICK_COUNT)
    ]
    return {
        "status": "success",
        "available": True,
        "channel": channel_key,
        "title": product.label,
        "kind": product.kind,
        "units": units,
        "axis_label": axis_label,
        "value_units": product.units,
        "vmin": vmin_f,
        "vmax": vmax_f,
        "anchors": anchors,
        "ticks": ticks,
    }


# Every tile miss used to re-read and re-scan the catalog JSON from disk. The
# file only changes when a refresh rewrites it, so the parsed frame index is
# memoized per (catalog file, mtime, render version) and misses in between cost
# a dict lookup instead of a JSON parse.
_CATALOG_FRAME_INDEX_MAX = 32
_CATALOG_FRAME_INDEX: OrderedDict[
    tuple[str, int, str], dict[str, dict[str, Any]]
] = OrderedDict()
_CATALOG_FRAME_INDEX_LOCK = threading.Lock()


def _catalog_frame_index(path: Path, render_version: str) -> dict[str, dict[str, Any]]:
    try:
        mtime_ns = path.stat().st_mtime_ns
    except OSError:
        return {}
    key = (str(path), mtime_ns, render_version)
    with _CATALOG_FRAME_INDEX_LOCK:
        cached = _CATALOG_FRAME_INDEX.get(key)
        if cached is not None:
            _CATALOG_FRAME_INDEX.move_to_end(key)
            return cached
    payload = read_json(path)
    index = {
        str(frame.get("frame_key") or ""): frame
        for frame in (payload or {}).get("frames") or []
        if frame.get("frame_key")
    }
    with _CATALOG_FRAME_INDEX_LOCK:
        _CATALOG_FRAME_INDEX[key] = index
        _CATALOG_FRAME_INDEX.move_to_end(key)
        while len(_CATALOG_FRAME_INDEX) > _CATALOG_FRAME_INDEX_MAX:
            _CATALOG_FRAME_INDEX.popitem(last=False)
    return index


def _catalog_frame_for_tile(
    cache_root: str,
    sat_id: str,
    sector: str,
    channel: str,
    frame_key: str,
) -> dict[str, Any]:
    index = _catalog_frame_index(
        catalog_path(cache_root, sat_id, sector, channel),
        satellite_v2_render_version_for_satellite(sat_id),
    )
    # Copied so a caller mutating the frame cannot corrupt the shared index.
    frame = index.get(str(frame_key or ""))
    if frame is not None:
        return dict(frame)

    frames = list_recent_frames(
        sat_id=sat_id,
        sector=sector,
        channel_key=channel,
        hours=SATELLITE_V2_ON_DEMAND_CATALOG_HOURS,
        max_frames=SATELLITE_V2_ON_DEMAND_CATALOG_MAX_FRAMES,
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
    client_id: str | None = None,
) -> dict[str, Any]:
    sat_key = normalize_sat_id(sat_id)
    sector_key = normalize_sector(sector)
    channel_key = normalize_channel(channel)
    _record_satellite_selection(client_id, (sat_key, sector_key, channel_key))
    capability = providers.provider_capability(sat_key)
    if capability["status"] != "available":
        cached = read_json(catalog_path(cache_root, sat_key, sector_key, channel_key))
        if cached:
            payload = catalog.get_catalog(
                cache_root=cache_root,
                sat_id=sat_key,
                sector=sector_key,
                channel_key=channel_key,
                hours=hours,
                max_frames=max_frames,
                refresh=False,
                list_frames_fn=None,
            )
            payload["capability_status"] = capability["status"]
            payload["capability_message"] = capability["message"]
            payload["accelerator"] = "unavailable"
            payload["accelerator_status"] = capability["status"]
            return payload
        return {
            "status": capability["status"],
            "capability_status": capability["status"],
            "provider": capability["provider"],
            "message": capability["message"],
            "sat_id": sat_key,
            "sector": sector_key,
            "channel": channel_key,
            "frames": [],
            "frame_count": 0,
        }
    try:
        payload = catalog.get_catalog(
            cache_root=cache_root,
            sat_id=sat_key,
            sector=sector_key,
            channel_key=channel_key,
            hours=hours,
            max_frames=max_frames,
            refresh=refresh,
            list_frames_fn=None,
        )
    except Exception as exc:
        capability_error = providers.classify_provider_error(sat_key, exc)
        if capability_error is None:
            raise
        return {
            "status": capability_error["status"],
            "capability_status": capability_error["status"],
            "provider": capability_error["provider"],
            "message": capability_error["message"],
            "sat_id": sat_key,
            "sector": sector_key,
            "channel": channel_key,
            "frames": [],
            "frame_count": 0,
        }
    if payload.get("provider_error"):
        capability_error = providers.classify_provider_error(
            sat_key, RuntimeError(str(payload["provider_error"]))
        )
        if capability_error is not None:
            payload["capability_status"] = capability_error["status"]
            payload["capability_message"] = capability_error["message"]
            payload["accelerator"] = "unavailable"
            payload["accelerator_status"] = capability_error["status"]
            return payload
    payload["capability_status"] = "available"
    payload.update(
        _activate_satellite_accelerator(
            sat_key,
            sector_key,
            channel_key,
            client_id=client_id,
        )
    )
    return payload


def get_frame_bounds(
    cache_root: str,
    sat_id: str,
    sector: str,
    channel: str,
) -> dict[str, Any] | None:
    """Geographic bounds of the most recent frame, or None if none exist.

    Used for sectors whose real-world extent isn't fixed (e.g. Himawari-9
    Target Area, which JMA dynamically retasks to a storm, a volcano, or
    nothing at all) so the frontend can fit the map to wherever the sector
    currently points instead of relying on a static named view preset.
    """
    frames = list_recent_frames(sat_id, sector, channel, hours=1, max_frames=1)
    if not frames:
        return None
    frame = frames[-1]

    source_channel = source_channels_for_product(normalize_channel(channel))[0]
    paths = download_product_source_frames(cache_root, sat_id, sector, channel, frame)
    raster = _load_source_raster(paths[source_channel], source_channel)

    transformer = Transformer.from_crs(raster.src_crs, "EPSG:4326", always_xy=True)
    n_rows, n_cols = raster.cmi.shape
    # Sample an interior grid rather than just the four corners: full-disk
    # sectors have off-Earth corners that transform to infinity, while
    # cropped regional sectors (Target/Japan) are fully on-Earth. Either
    # way, finite samples across the grid bound the real coverage.
    px = np.linspace(0, n_cols, 9)
    py = np.linspace(0, n_rows, 9)
    lons: list[float] = []
    lats: list[float] = []
    for row in py:
        for col in px:
            x, y = raster.src_transform * (float(col), float(row))
            lon, lat = transformer.transform(x, y)
            if np.isfinite(lon) and np.isfinite(lat):
                lons.append(lon)
                lats.append(lat)
    if not lons:
        return None

    return {
        "frame_key": frame.frame_key,
        "timestamp_utc": frame.timestamp_utc,
        "west": min(lons),
        "south": min(lats),
        "east": max(lons),
        "north": max(lats),
    }


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
    render_neighbors: bool = True,
    frame_override: dict[str, Any] | None = None,
    client_id: str | None = None,
    foreground_frame_key: str | None = None,
    frame_generation: int | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Resolve a cached tile or render the requested tile before returning.

    On a render miss, neighbor warming is submitted asynchronously unless
    ``render_neighbors`` is false. Explicit viewport prefetch uses that opt-out
    because it already queues the required coordinates with its own bounds.
    """
    started = time.perf_counter()
    sat_key = normalize_sat_id(sat_id)
    sector_key = normalize_sector(sector)
    channel_key = normalize_channel(channel)
    selection = (sat_key, sector_key, channel_key)
    _record_satellite_frame_request(
        client_id,
        selection,
        foreground_frame_key,
        frame_generation,
    )
    path = tile_path(cache_root, sat_key, sector_key, channel_key, frame_key, z, x, y)
    validate_start = time.perf_counter()
    try:
        path_size_before = int(path.stat().st_size)
        path_exists_before = True
    except (FileNotFoundError, OSError):
        path_size_before = 0
        path_exists_before = False
    tile_valid = False
    if path_exists_before:
        try:
            with path.open("rb") as tile_file:
                tile_valid = (
                    path_size_before > 0
                    and tile_file.read(len(_PNG_SIGNATURE)) == _PNG_SIGNATURE
                )
        except OSError:
            tile_valid = False
        if not tile_valid:
            tile_valid = is_valid_tile_file(path)
    validate_elapsed_precise = (time.perf_counter() - validate_start) * 1000.0
    validate_elapsed = int(validate_elapsed_precise)
    bench_context = None
    if bench_enabled():
        bench_context = {
            "sat_id": sat_key,
            "sector": sector_key,
            "product": channel_key,
            "frame_key": frame_key,
            "z": int(z),
            "x": int(x),
            "y": int(y),
        }
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
                "provider": _provider_name_for_sat(sat_key),
                "frame_key": frame_key,
                "sat_id": sat_key,
                "sector": sector_key,
                "channel": channel_key,
            }
            if bench_context is not None:
                timing_token = begin_timing(
                    cache_root,
                    bench_context,
                    initial={
                        "validate_ms": validate_elapsed_precise,
                        "_total_started": started,
                    },
                )
                finish_timing(timing_token, cache_status=cache_status)
            return path, stats
        if not _satellite_client_owns_frame_request(
            client_id,
            selection,
            frame_key,
            foreground_frame_key,
            frame_generation,
        ):
            return path, _cancelled_tile_stats(
                started=started,
                path_exists_before=path_exists_before,
                path_size_before=path_size_before,
                sat_id=sat_key,
                sector=sector_key,
                channel=channel_key,
                frame_key=frame_key,
            )
        if is_negative_tile_cached(path):
            cache_status = "invalid"
            stats = {
                "cache_status": cache_status,
                "miss_reason": "negative-cache",
                "tile_exists_before": path_exists_before,
                "tile_size_before": path_size_before,
                "elapsed_ms": int((time.perf_counter() - started) * 1000),
                "provider": _provider_name_for_sat(sat_key),
                "frame_key": frame_key,
                "sat_id": sat_key,
                "sector": sector_key,
                "channel": channel_key,
                "negative_cached": 1,
            }
            if bench_context is not None:
                timing_token = begin_timing(
                    cache_root,
                    bench_context,
                    initial={
                        "validate_ms": validate_elapsed_precise,
                        "_total_started": started,
                    },
                )
                finish_timing(timing_token, cache_status=cache_status)
            return path, stats
        frame = (
            dict(frame_override)
            if frame_override is not None
            else _catalog_frame_for_tile(
                cache_root, sat_key, sector_key, channel_key, frame_key
            )
        )
        tile_id = f"{sat_key}/{sector_key}/{channel_key}/{z}/{x}/{y}"
        logger.info(
            "Satellite tile render_start frame_key=%s tile=%s workers=%s "
            "miss_reason=%s file_exists=%s file_size=%s",
            frame_key,
            tile_id,
            SATELLITE_V2_LIVE_TILE_RENDER_WORKERS,
            miss_reason,
            path_exists_before,
            path_size_before,
        )
        logger.info("Submitting tile render: %s", tile_id)
        render_kwargs = {
            "cache_root": cache_root,
            "sat_id": sat_key,
            "sector": sector_key,
            "channel_key": channel_key,
            "frame": frame,
            "z": z,
            "x": x,
            "y": y,
            "bench_seed": (
                {"validate_ms": validate_elapsed_precise, "_total_started": started}
                if bench_enabled()
                else None
            ),
            "render_supertile": bool(render_neighbors),
        }
        future, _ = _submit_tile_render(
            path,
            client_id=client_id,
            selection=selection,
            tile_frame_key=frame_key,
            foreground_frame_key=foreground_frame_key,
            frame_generation=frame_generation,
            **render_kwargs,
        )
        render_start = time.perf_counter()
        while True:
            if not _satellite_client_owns_frame_request(
                client_id,
                selection,
                frame_key,
                foreground_frame_key,
                frame_generation,
            ):
                return path, _cancelled_tile_stats(
                    started=started,
                    path_exists_before=path_exists_before,
                    path_size_before=path_size_before,
                    sat_id=sat_key,
                    sector=sector_key,
                    channel=channel_key,
                    frame_key=frame_key,
                )
            try:
                path, render_stats = future.result(timeout=0.1)
                break
            except TimeoutError:
                continue
            except (CancelledError, _TileRenderCancelled):
                return path, _cancelled_tile_stats(
                    started=started,
                    path_exists_before=path_exists_before,
                    path_size_before=path_size_before,
                    sat_id=sat_key,
                    sector=sector_key,
                    channel=channel_key,
                    frame_key=frame_key,
                )
        render_stats["supertile_submitted"] = 0
        render_elapsed = int((time.perf_counter() - render_start) * 1000)
        logger.info(
            "Satellite tile render_complete frame_key=%s tile=%s cache_status=%s "
            "render_ms=%s supertile_submitted=%s supertile_rendered=%s "
            "supertile_skipped=%s supertile_invalid=%s",
            frame_key,
            tile_id,
            str(render_stats.get("cache_status") or "miss").upper(),
            render_elapsed,
            int(render_stats.get("supertile_submitted") or 0),
            int(render_stats.get("supertile_rendered") or 0),
            int(render_stats.get("supertile_skipped") or 0),
            int(render_stats.get("supertile_invalid") or 0),
        )
        logger.info("Tile render complete: %s (%sms)", tile_id, render_elapsed)
        cache_status = str(render_stats.get("cache_status") or "miss")
    stats = {
        "cache_status": cache_status,
        "miss_reason": miss_reason,
        "tile_exists_before": path_exists_before,
        "tile_size_before": path_size_before,
        "validate_elapsed_ms": validate_elapsed,
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
        "provider": _provider_name_for_sat(sat_key),
        "frame_key": frame_key,
        "sat_id": sat_key,
        "sector": sector_key,
        "channel": channel_key,
    }
    if "render_stats" in locals():
        stats.update(
            {
                "supertile_rendered": int(render_stats.get("supertile_rendered") or 0),
                "supertile_submitted": int(render_stats.get("supertile_submitted") or 0),
                "supertile_skipped": int(render_stats.get("supertile_skipped") or 0),
                "supertile_invalid": int(render_stats.get("supertile_invalid") or 0),
                "supertile_errors": int(render_stats.get("supertile_errors") or 0),
                "supertile_radius": int(render_stats.get("supertile_radius") or 0),
                "download_elapsed_ms": int(
                    render_stats.get("download_elapsed_ms") or 0
                ),
                "decode_elapsed_ms": int(
                    render_stats.get("decode_elapsed_ms") or 0
                ),
                "render_elapsed_ms": int(
                    render_stats.get("render_elapsed_ms") or 0
                ),
                "estimated_memory_bytes": int(
                    render_stats.get("estimated_memory_bytes") or 0
                ),
            }
        )
    elif bench_context is not None:
        timing_token = begin_timing(
            cache_root,
            bench_context,
            initial={
                "validate_ms": validate_elapsed_precise,
                "_total_started": started,
            },
        )
        finish_timing(timing_token, cache_status=cache_status)
    return path, stats
