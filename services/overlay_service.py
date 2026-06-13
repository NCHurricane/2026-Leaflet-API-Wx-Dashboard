"""Shared overlay latest/frames service helpers."""

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
import os

from fastapi import HTTPException

from app_core.background_render import spawn_live_render_thread
from app_core.http import parse_utc_datetime
from app_core.paths import CACHE_ROOT
from config.geo_config import STATE_BOUNDS


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
    from cache.overlay_cache_utils import (
        datetime_from_frame_key,
        flat_overlay_image_path,
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

    return meta


def get_overlay_frames(
    *,
    family: str = "rtma",
    region: str = "CONUS",
    stream: str = "rtma_hourly",
    product: str = "temperature",
    hours: int = 1,
) -> dict:
    """Return pre-rendered frames for a product within a lookback window."""
    from cache.overlay_cache_utils import flat_overlay_list_frames
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
            print(
                f"[overlay_frames] {family.upper()} on-demand render failed for {label}: {exc}"
            )
            return 0

    def _kick_background_render():
        return spawn_live_render_thread(
            ("overlay", family, region_key, stream, product),
            f"{family}-{region_key}-{stream}-{product}",
            _render_on_demand,
        )

    stale_window_min = OVERLAY_STALE_SERVE_WINDOW_MIN.get(
        "mrms" if family == "mrms" else stream, 30
    )

    raw_frames = flat_overlay_list_frames(CACHE_ROOT, family, path_parts)
    frames = _filter_by_lookback(raw_frames) if raw_frames else []
    refreshing = False

    if not frames and raw_frames:
        stale_frames = _filter_by_lookback(raw_frames, grace_minutes=stale_window_min)
        if stale_frames:
            frames = stale_frames
            refreshing = _kick_background_render()

    if not frames:
        if _render_on_demand(max_render_frames=OVERLAY_EMPTY_CACHE_SYNC_FRAMES) > 0:
            raw_frames = flat_overlay_list_frames(CACHE_ROOT, family, path_parts)
            frames = _filter_by_lookback(raw_frames)
            refreshing = _kick_background_render()

    return {
        "family": family,
        "region": region_key,
        "stream": stream,
        "product": product,
        "frame_count": len(frames),
        "refreshing": refreshing,
        "frames": frames,
    }
