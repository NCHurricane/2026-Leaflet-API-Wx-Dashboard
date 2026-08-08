"""Shared overlay latest/frames service helpers."""

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
import logging
import os

from fastapi import HTTPException

from app_core.http import parse_utc_datetime
from app_core.paths import CACHE_ROOT
from app_core.refresh_coordinator import Submission, get_refresh_coordinator
from config.geo_config import STATE_BOUNDS

_LOGGER = logging.getLogger(__name__)


def _start_selected_refresh(
    family: str,
    region: str,
    stream: str,
    product: str,
) -> Submission:
    if family == "mrms":
        from services.mrms_service import _start_mrms_product_refresh

        return _start_mrms_product_refresh(product)
    from services.rtma_service import start_rtma_product_refresh

    return start_rtma_product_refresh(region, stream, product)


def _refresh_fields(refresh: Submission) -> dict:
    return {
        "refreshing": refresh.status in {"queued", "running"},
        "refresh_status": refresh.status,
        "retry_after_seconds": refresh.retry_after_seconds,
    }


def get_overlay_latest(
    *,
    family: str = "rtma",
    region: str = "CONUS",
    stream: str = "rtma_hourly",
    product: str = "temperature",
    frame_key: str | None = None,
    rtma_bootstrap: Callable[..., object] | None = None,
) -> dict:
    """Return the pre-rendered overlay meta for a specific or latest frame."""
    from app_core.overlay_cache import (
        datetime_from_frame_key,
        flat_overlay_image_path,
        flat_overlay_list_frames,
        flat_overlay_read_latest,
    )

    allowed_families = {"rtma", "mrms"}
    if family not in allowed_families:
        raise HTTPException(
            status_code=400, detail=f"Unsupported overlay family '{family}'."
        )

    region_key = region.upper()

    if family == "rtma":
        if region_key not in STATE_BOUNDS:
            raise HTTPException(
                status_code=400, detail=f"Unknown RTMA region '{region}'."
            )
        if product == "temperature_change_24h" and stream != "rtma_hourly":
            raise HTTPException(
                status_code=400,
                detail="RTMA 24-hour temperature change is only available on rtma_hourly.",
            )
        if stream == "rtma_rapid_update" and region_key != "CONUS":
            raise HTTPException(
                status_code=400,
                detail="RTMA rapid update stream is only available for CONUS.",
            )
        path_parts = (region_key, stream, product)
    else:
        path_parts = ("CONUS", "default", product)

    refresh = _start_selected_refresh(
        family,
        region_key,
        stream,
        product,
    )

    if frame_key:
        img_path = flat_overlay_image_path(CACHE_ROOT, family, path_parts, frame_key)
        if not os.path.exists(img_path) or os.path.getsize(img_path) == 0:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"No pre-rendered overlay found for family={family}, region={region_key}, "
                    f"stream={stream}, product={product}, frame_key={frame_key}. "
                    "Worker may not have run yet."
                ),
            )
        rel_dir = (
            "/cache/overlays/" + family + "/" + "/".join(str(p) for p in path_parts)
        )
        image_url = f"{rel_dir}/{frame_key}.png"
        try:
            frame_dt = datetime_from_frame_key(frame_key)
            timestamp = frame_dt.isoformat()
        except Exception:
            timestamp = frame_key
        latest = flat_overlay_read_latest(CACHE_ROOT, family, path_parts) or {}
        meta = {
            "frame_key": frame_key,
            "timestamp": timestamp,
            "source_data_key": frame_key,
            "image_url": image_url,
            "bounds": latest.get("bounds"),
            "full_name": latest.get("full_name", ""),
            "units": latest.get("units", ""),
            "legend": latest.get("legend"),
            "vmin": latest.get("vmin"),
            "vmax": latest.get("vmax"),
            "render": {"type": "image", "image_url": image_url},
        }
    else:
        if family == "mrms":
            from mrms.mrms_tiles import filter_unpreparable_duplicate_frames

            candidates = filter_unpreparable_duplicate_frames(
                flat_overlay_list_frames(CACHE_ROOT, family, path_parts),
                product,
            )
            meta = candidates[-1] if candidates else None
        else:
            meta = flat_overlay_read_latest(CACHE_ROOT, family, path_parts)

    if (
        not meta
        and family == "rtma"
        and frame_key is None
        and product != "wind_direction"
        and rtma_bootstrap is not None
    ):
        try:
            bounds = STATE_BOUNDS.get(region_key, [-130.0, -60.0, 21.0, 52.0])
            rtma_bootstrap(
                region=region_key,
                stream=stream,
                product=product,
                south=float(bounds[2]),
                west=float(bounds[0]),
                north=float(bounds[3]),
                east=float(bounds[1]),
            )
            meta = flat_overlay_read_latest(CACHE_ROOT, family, path_parts)
        except HTTPException:
            pass
        except Exception:
            pass

    if not meta:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No pre-rendered overlay found for family={family}, region={region_key}, "
                f"stream={stream}, product={product}" + ". Worker may not have run yet."
            ),
        )

    image_url = (meta.get("render") or {}).get("image_url") or meta.get("image_url", "")
    if image_url:
        rel = image_url.lstrip("/")
        if rel.startswith("cache/"):
            rel = rel[len("cache/") :]
        img_disk = os.path.join(CACHE_ROOT, rel)
        if not os.path.exists(img_disk):
            raise HTTPException(
                status_code=404,
                detail="Pre-rendered overlay image has been pruned; worker re-render pending.",
            )

    payload = {**meta, **_refresh_fields(refresh)}
    if family == "mrms":
        from mrms.mrms_tiles import enrich_frame_with_tiles

        payload = enrich_frame_with_tiles(payload, product)
    return payload


def get_overlay_frames(
    *,
    family: str = "rtma",
    region: str = "CONUS",
    stream: str = "rtma_hourly",
    product: str = "temperature",
    hours: int = 1,
) -> dict:
    """Return pre-rendered frames for a product within a lookback window."""
    from app_core.overlay_cache import flat_overlay_list_frames
    from config.cache_config import (
        OVERLAY_EMPTY_CACHE_SYNC_FRAMES,
        OVERLAY_STALE_SERVE_WINDOW_MIN,
    )

    allowed_families = {"rtma", "mrms"}
    if family not in allowed_families:
        raise HTTPException(
            status_code=400, detail=f"Unsupported overlay family '{family}'."
        )

    region_key = region.upper()
    hours_back = max(1, int(hours or 1))
    path_parts = (
        (region_key, stream, product)
        if family == "rtma"
        else ("CONUS", "default", product)
    )
    refresh = _start_selected_refresh(
        family,
        region_key,
        stream,
        product,
    )

    def _filter_by_lookback(frame_list, grace_minutes=0):
        cutoff_dt = datetime.now(timezone.utc) - timedelta(
            hours=hours_back, minutes=grace_minutes
        )
        out = []
        for frame in frame_list:
            ts = frame.get("timestamp")
            dt = None
            if ts:
                try:
                    dt = parse_utc_datetime(ts)
                except Exception:
                    dt = None
            if dt and dt < cutoff_dt:
                continue
            out.append(frame)
        return out

    def _render_on_demand(max_render_frames=None):
        try:
            if family == "mrms":
                from workers.mrms_live_worker import run_mrms_live_product

                return run_mrms_live_product(
                    product,
                    force=True,
                    max_hours=hours_back,
                    max_render_frames=max_render_frames,
                )
            from workers.rtma_live_worker import run_rtma_live_product

            return run_rtma_live_product(
                region_key,
                stream,
                product,
                force=True,
                max_hours=hours_back,
                max_render_frames=max_render_frames,
            )
        except Exception as exc:
            label = product if family == "mrms" else f"{region_key}/{stream}/{product}"
            _LOGGER.warning(
                "%s on-demand render failed for %s (%s)",
                family.upper(),
                label,
                type(exc).__name__,
            )
            return 0

    def _kick_background_render():
        refresh_interval_seconds = (
            2 * 60
            if family == "mrms"
            else (15 * 60 if stream == "rtma_rapid_update" else 60 * 60)
        )
        submission = get_refresh_coordinator().submit(
            key=(
                "overlay-history",
                family,
                region_key,
                stream,
                product,
                str(hours_back),
            ),
            provider="noaa-mrms" if family == "mrms" else "noaa-rtma",
            function=_render_on_demand,
            min_success_interval_seconds=refresh_interval_seconds,
        )
        return submission.status in {"queued", "running"}

    stale_window_min = OVERLAY_STALE_SERVE_WINDOW_MIN.get(
        "mrms" if family == "mrms" else stream, 30
    )

    raw_frames = flat_overlay_list_frames(CACHE_ROOT, family, path_parts)
    if family == "mrms":
        from mrms.mrms_tiles import filter_unpreparable_duplicate_frames

        raw_frames = filter_unpreparable_duplicate_frames(raw_frames, product)
    frames = _filter_by_lookback(raw_frames) if raw_frames else []
    refreshing = False

    if not frames and raw_frames:
        stale_frames = _filter_by_lookback(raw_frames, grace_minutes=stale_window_min)
        if stale_frames:
            frames = stale_frames

    if not frames:
        if _render_on_demand(max_render_frames=OVERLAY_EMPTY_CACHE_SYNC_FRAMES) > 0:
            raw_frames = flat_overlay_list_frames(CACHE_ROOT, family, path_parts)
            if family == "mrms":
                raw_frames = filter_unpreparable_duplicate_frames(
                    raw_frames,
                    product,
                )
            frames = _filter_by_lookback(raw_frames)

    # A partial cache is not proof that the requested horizon is complete.
    # Always ask the coordinator to fill the selected product/lookback in the
    # background; the horizon-specific key and cadence gate make this cheap
    # after a successful fill.
    refreshing = _kick_background_render()

    if family == "mrms":
        from mrms.mrms_tiles import enrich_frame_with_tiles

        frames = [enrich_frame_with_tiles(frame, product) for frame in frames]

    return {
        "family": family,
        "region": region_key,
        "stream": stream,
        "product": product,
        "frame_count": len(frames),
        "refreshing": (
            refreshing or refresh.status in {"queued", "running"}
        ),
        "refresh_status": refresh.status,
        "retry_after_seconds": refresh.retry_after_seconds,
        "frames": frames,
    }
