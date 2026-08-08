"""MRMS Live Worker

On-demand frame rendering for MRMS products (triggered by scrubber).
Similar workflow to radar_live_worker but for MRMS data.

Discovers timestamped GRIBs in cache and renders them to PNG overlays
for scrubber playback. API cache-miss fallback calls this to populate
frames on-demand when user requests animation.
"""

import logging

import os
import sys
import tempfile
import time as _time
from datetime import datetime, timedelta, timezone

# Add project root to path for both module and direct execution
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from config.mrms_config import MRMS_PRODUCTS  # noqa: E402
from workers._freshness import is_cache_fresh, mark_run_complete  # noqa: E402

_CACHE_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cache"
)
_MRMS_CACHE = os.path.join(_CACHE_ROOT, "mrms")

_FRESH_WINDOW_SEC = 11 * 60  # 75% of 15-min worker interval


def _discover_timestamped_gribs(product: str, max_hours: int = 1):
    """Discover available timestamped GRIB files for a product.

    Returns list of (filepath, datetime) tuples, newest first.
    """
    product_dir = os.path.join(_MRMS_CACHE, product)
    if not os.path.isdir(product_dir):
        return []

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=max(1, int(max_hours)))

    gribs = []
    for filename in os.listdir(product_dir):
        if not filename.endswith(".grib2.gz") or filename == "conus.grib2.gz":
            continue

        try:
            # Parse timestamp from filename: YYYY-MM-DD_HH-MM-SS.grib2.gz
            timestamp_str = filename.replace(".grib2.gz", "")
            file_dt = datetime.strptime(timestamp_str, "%Y-%m-%d_%H-%M-%S").replace(
                tzinfo=timezone.utc
            )
            if file_dt >= cutoff:
                gribs.append((os.path.join(product_dir, filename), file_dt))
        except ValueError:
            # Skip files that don't match timestamp pattern
            pass

    # Sort newest first
    gribs.sort(key=lambda x: x[1], reverse=True)
    return gribs


def _discover_upstream_gribs(product: str, max_hours: int = 1):
    """List upstream MRMS objects in the requested window, newest first."""
    from mrms.mrms_nodd_utils import list_mrms_files

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=max(1, int(max_hours)))
    frames = list_mrms_files(product, start_time, end_time)
    normalized = []
    for source_key, file_dt in frames:
        dt_utc = (
            file_dt.astimezone(timezone.utc)
            if file_dt.tzinfo is not None
            else file_dt.replace(tzinfo=timezone.utc)
        )
        normalized.append((source_key, dt_utc))
    normalized.sort(key=lambda item: item[1], reverse=True)
    return normalized


def _render_mrms_frame_to_overlay(
    grib_path: str, product: str, file_dt: datetime, cache_root: str
) -> bool:
    """Render a single GRIB frame to PNG overlay cache.

    Returns True on success, False on failure.
    """
    from mrms.publication import (
        render_mrms_png_standalone,
        write_mrms_overlay_cache,
    )
    from app_core.overlay_cache import (
        flat_overlay_image_path,
        flat_overlay_read_processed_keys,
        frame_key_from_datetime,
    )

    _CONUS_EXTENT = [-130.0, -60.0, 21.0, 52.0]  # [west, east, south, north]

    # Dedup before rendering; publication also skips processed frames, but only
    # after the expensive GRIB decode and warp have already run.
    dt_utc = (
        file_dt if file_dt.tzinfo is not None else file_dt.replace(tzinfo=timezone.utc)
    )
    frame_key = frame_key_from_datetime(dt_utc)
    path_parts = ("CONUS", "default", product)
    processed_keys = flat_overlay_read_processed_keys(cache_root, "mrms", path_parts)
    if f"mrms:{product}:{frame_key}" in processed_keys:
        img_path = flat_overlay_image_path(cache_root, "mrms", path_parts, frame_key)
        if os.path.exists(img_path) and os.path.getsize(img_path) > 0:
            return True

    temp_png = None
    try:
        # Create temp PNG path
        product_cache_dir = os.path.join(cache_root, "mrms", product)
        os.makedirs(product_cache_dir, exist_ok=True)

        descriptor, temp_png = tempfile.mkstemp(
            prefix=f"temp_{file_dt.strftime('%Y%m%d_%H%M%S')}_",
            suffix=".png",
            dir=product_cache_dir,
        )
        os.close(descriptor)

        # Render GRIB to PNG
        render_mrms_png_standalone(
            grib_path,
            product,
            _CONUS_EXTENT,
            temp_png,
            tile_frame_key=frame_key,
        )

        # Write to overlay cache (handles index updates)
        write_mrms_overlay_cache(product, temp_png, file_dt, keep_n=None)

        frame_key = file_dt.strftime("%Y_%m_%d_%H_%M_%S")
        logging.getLogger(__name__).info(f"[mrms_live] {product} frame {frame_key} rendered OK")
        return True
    except Exception as exc:
        frame_key = file_dt.strftime("%Y_%m_%d_%H_%M_%S")
        logging.getLogger(__name__).warning(f"[mrms_live] Failed to render {product} frame {frame_key}: {type(exc).__name__}")
        return False
    finally:
        if temp_png:
            for artifact in (
                temp_png,
                temp_png.replace(".png", "_bounds.json"),
                temp_png.replace(".png", "_meta.json"),
            ):
                try:
                    os.remove(artifact)
                except OSError:
                    pass


def run_mrms_live_product(
    product: str,
    force: bool = True,
    latest_only: bool = False,
    max_render_frames: int | None = None,
    max_hours: int = 1,
) -> int:
    """Render and cache frames for MRMS product (on-demand by API/scrubber).

    Discovers timestamped GRIBs in cache and renders them to PNG overlays
    for scrubber playback. Called by API cache-miss fallback.

    Args:
        product: MRMS product key (e.g., 'Refl_BaseQC')
        force: Bypass freshness gate
        latest_only: Render only the most recent frame
        max_render_frames: Limit rendering to N newest frames
        max_hours: Lookback window in hours (default 1 for live)

    Returns:
        Count of frames rendered
    """
    product = str(product or "").strip()
    if not product:
        raise ValueError("product is required")

    if product not in MRMS_PRODUCTS:
        raise ValueError(f"Unknown MRMS product: {product}")

    if not force and is_cache_fresh("mrms_live", _FRESH_WINDOW_SEC):
        return 0

    product_cache_dir = os.path.join(_MRMS_CACHE, product)
    os.makedirs(product_cache_dir, exist_ok=True)

    # A local-only scan cannot repair gaps after server downtime. Prefer the
    # authoritative selected-product listing and fall back to local timestamped
    # GRIBs only when upstream discovery is unavailable.
    try:
        upstream = _discover_upstream_gribs(product, max_hours=max_hours)
    except Exception as exc:
        logging.getLogger(__name__).warning(f"[mrms_live] Upstream history discovery failed for {product}: {type(exc).__name__}")
        upstream = []

    if upstream:
        candidates = [(None, file_dt, source_key) for source_key, file_dt in upstream]
    else:
        candidates = [
            (grib_path, file_dt, None)
            for grib_path, file_dt in _discover_timestamped_gribs(
                product, max_hours=max_hours
            )
        ]
    if not candidates:
        logging.getLogger(__name__).info(f"[mrms_live] No GRIBs found for {product}")
        return 0

    # Optionally limit to latest only or max count
    if latest_only:
        candidates = candidates[:1]
    elif max_render_frames:
        candidates = candidates[:max_render_frames]

    # Render frames
    from app_core.overlay_cache import (
        flat_overlay_image_path,
        flat_overlay_read_processed_keys,
        frame_key_from_datetime,
    )
    from mrms.mrms_nodd_utils import download_mrms_file

    path_parts = ("CONUS", "default", product)
    processed_keys = flat_overlay_read_processed_keys(
        _CACHE_ROOT, "mrms", path_parts
    )
    cached = 0
    t0 = _time.perf_counter()
    attempted = 0
    for grib_path, file_dt, source_key in candidates:
        attempted += 1
        frame_key = frame_key_from_datetime(file_dt)
        processed_key = f"mrms:{product}:{frame_key}"
        image_path = flat_overlay_image_path(
            _CACHE_ROOT, "mrms", path_parts, frame_key
        )
        if (
            processed_key in processed_keys
            and os.path.exists(image_path)
            and os.path.getsize(image_path) > 0
        ):
            cached += 1
            continue
        if source_key:
            try:
                grib_path = download_mrms_file(source_key, product_cache_dir)
            except Exception as exc:
                logging.getLogger(__name__).warning(
                    f"[mrms_live] Failed to download {product} "
                    f"{file_dt.isoformat()}: {type(exc).__name__}"
                )
                continue
        if _render_mrms_frame_to_overlay(grib_path, product, file_dt, _CACHE_ROOT):
            cached += 1

    elapsed = _time.perf_counter() - t0
    logging.getLogger(__name__).info(
        f"[mrms_live] {product} rendered {cached}/{attempted} frames in {elapsed:.1f}s"
    )

    if cached > 0:
        mark_run_complete("mrms_live")

    return cached


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    import argparse

    parser = argparse.ArgumentParser(description="Run the MRMS live worker once.")
    parser.add_argument("--force", action="store_true", help="Bypass freshness gate.")
    parser.add_argument(
        "--product", default="Refl_BaseQC", help="MRMS product to render."
    )
    parser.add_argument(
        "--hours", type=int, default=1, help="Lookback window in hours."
    )
    args = parser.parse_args()

    cached = run_mrms_live_product(
        args.product, force=args.force, max_hours=args.hours
    )
    logging.getLogger(__name__).info(f"Cached {cached} frames")
