"""RTMA Live Worker

On-demand frame rendering for RTMA products (triggered by scrubber/animate).
Similar workflow to mrms_live_worker but for RTMA data with region/stream/product.

Discovers available RTMA sources within a lookback window and renders them
to PNG overlays for scrubber playback. API calls this to populate frames
on-demand when user requests animation.
"""

import os
import time as _time
from datetime import timezone

from config.rtma_config import RTMA_STREAMS
from workers._freshness import is_cache_fresh, mark_run_complete

_CACHE_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cache"
)

_FRESH_WINDOW_SEC = 11 * 60  # 75% of 15-min worker interval


def _render_rtma_frame_to_overlay(
    cache_root: str,
    source,
    region: str,
    stream: str,
    product: str,
) -> bool:
    """Render a single RTMA source frame to PNG overlay cache.

    Returns True on success, False on failure.
    """
    from cache.overlay_cache_utils import (
        flat_overlay_image_path,
        flat_overlay_read_processed_keys,
        flat_overlay_update_index,
        flat_overlay_write_processed_keys,
        frame_key_from_datetime,
    )
    from config.geo_config import STATE_BOUNDS
    from rtma_utils import ensure_rtma_grib, _render_rtma_png_standalone

    path_parts = (region.upper(), stream, product)
    frame_key = frame_key_from_datetime(source.valid_time)

    # Dedup: skip if this source key is already recorded as processed.
    processed_keys = flat_overlay_read_processed_keys(cache_root, "rtma", path_parts)
    if source.data_key in processed_keys:
        img_path = flat_overlay_image_path(cache_root, "rtma", path_parts, frame_key)
        if os.path.exists(img_path) and os.path.getsize(img_path) > 0:
            return False  # already fresh, no update needed

    bounds = STATE_BOUNDS.get(region, [-125, -70, 21, 52])
    crop_extent = [float(b) for b in bounds]

    try:
        img_path = flat_overlay_image_path(cache_root, "rtma", path_parts, frame_key)
        os.makedirs(os.path.dirname(img_path), exist_ok=True)

        grib_path = ensure_rtma_grib(cache_root, source)
        _out_path, actual_bounds, render_meta = _render_rtma_png_standalone(
            grib_path,
            product,
            crop_extent,
            img_path,
            cache_root=cache_root,
            source=source,
            region=region,
            stream=stream,
        )
    except Exception as exc:
        print(
            f"[rtma_live] Overlay render ERROR {region}/{stream}/{product}/{frame_key}: {exc}"
        )
        return False

    try:
        # Update index with metadata.
        flat_overlay_update_index(
            cache_root,
            "rtma",
            path_parts,
            frame_key,
            bounds=actual_bounds,
            full_name=render_meta.get("full_name", product),
            units=render_meta.get("units", ""),
            legend=render_meta.get("legend"),
            vmin=render_meta.get("vmin"),
            vmax=render_meta.get("vmax"),
            timestamp=render_meta.get("timestamp") or source.valid_time.isoformat(),
        )

        # Record as processed.
        processed_keys.add(source.data_key)
        flat_overlay_write_processed_keys(
            cache_root,
            "rtma",
            path_parts,
            processed_keys,
            keep_n=30,
        )

        print(f"[rtma_live] {region}/{stream}/{product} frame {frame_key} rendered OK")
        return True
    except Exception as exc:
        print(f"[rtma_live] Overlay index update ERROR {region}/{stream}/{product}/{frame_key}: {exc}")
        return False


def run_rtma_live_product(
    region: str,
    stream: str,
    product: str,
    force: bool = True,
    latest_only: bool = False,
    max_render_frames: int | None = None,
    max_hours: int = 1,
) -> int:
    """Render and cache frames for RTMA product (on-demand by API/scrubber).

    Discovers available RTMA sources within a lookback window and renders
    them to PNG overlays for scrubber playback. Called by API cache-miss fallback.

    Args:
        region: Region key (e.g., 'CONUS')
        stream: RTMA stream (e.g., 'rtma_hourly', 'rtma_rapid_update')
        product: RTMA product key (e.g., 'temperature')
        force: Bypass freshness gate
        latest_only: Render only the most recent frame
        max_render_frames: Limit rendering to N newest frames
        max_hours: Lookback window in hours (default 1 for live)

    Returns:
        Count of frames rendered
    """
    region = str(region or "").strip().upper()
    stream = str(stream or "").strip()
    product = str(product or "").strip()

    if not region or not stream or not product:
        raise ValueError("region, stream, and product are required")

    if stream not in RTMA_STREAMS:
        raise ValueError(f"Unknown RTMA stream: {stream}")

    if not force and is_cache_fresh(f"rtma_live_{stream}", _FRESH_WINDOW_SEC):
        return 0

    try:
        from rtma_utils import iter_rtma_sources_within_hours
        from config.rtma_config import clamp_stream_hours
    except Exception as exc:
        print(f"[rtma_live] Import error: {exc}")
        return 0

    # Discover available sources within lookback window
    hours_back = clamp_stream_hours(stream, max_hours)
    try:
        sources = list(
            iter_rtma_sources_within_hours(
                region,
                stream,
                product,
                hours_back=hours_back,
            )
        )
    except Exception as exc:
        print(f"[rtma_live] Source discovery failed for {region}/{stream}/{product}: {exc}")
        return 0

    if not sources:
        print(f"[rtma_live] No sources found for {region}/{stream}/{product}")
        return 0

    # Optionally limit to latest only or max count
    if latest_only:
        sources = sources[-1:]
    elif max_render_frames:
        sources = sources[-max_render_frames:]

    # Render frames
    cached = 0
    t0 = _time.perf_counter()
    for source in sources:
        if _render_rtma_frame_to_overlay(
            _CACHE_ROOT,
            source,
            region,
            stream,
            product,
        ):
            cached += 1

    elapsed = _time.perf_counter() - t0
    print(
        f"[rtma_live] {region}/{stream}/{product} rendered {cached}/{len(sources)} frames in {elapsed:.1f}s"
    )

    if cached > 0:
        mark_run_complete(f"rtma_live_{stream}")

    return cached


def run_rtma_live_worker(force: bool = False) -> None:
    """Background worker (optional) to keep live frames fresh."""
    # For now, this is a no-op. Frames are rendered on-demand by API.
    # In the future, could proactively warm popular products.
    pass


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run the RTMA live worker once.")
    parser.add_argument("--force", action="store_true", help="Bypass freshness gate.")
    parser.add_argument(
        "--region", default="CONUS", help="RTMA region to render."
    )
    parser.add_argument(
        "--stream", default="rtma_hourly", help="RTMA stream to render."
    )
    parser.add_argument(
        "--product", default="temperature", help="RTMA product to render."
    )
    parser.add_argument(
        "--hours", type=int, default=1, help="Lookback window in hours."
    )
    args = parser.parse_args()

    cached = run_rtma_live_product(
        args.region,
        args.stream,
        args.product,
        force=args.force,
        max_hours=args.hours,
    )
    print(f"Cached {cached} frames")
