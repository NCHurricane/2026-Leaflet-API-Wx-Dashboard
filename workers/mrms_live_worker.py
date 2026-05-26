"""MRMS Live Worker

On-demand frame rendering for MRMS products (triggered by scrubber).
Similar workflow to radar_live_worker but for MRMS data.

Discovers timestamped GRIBs in cache and renders them to PNG overlays
for scrubber playback. API cache-miss fallback calls this to populate
frames on-demand when user requests animation.
"""

import os
import time as _time
from datetime import datetime, timedelta, timezone

from config.mrms_config import MRMS_PRODUCTS
from workers._freshness import is_cache_fresh, mark_run_complete

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


def _render_mrms_frame_to_overlay(
    grib_path: str, product: str, file_dt: datetime, cache_root: str
) -> bool:
    """Render a single GRIB frame to PNG overlay cache.

    Returns True on success, False on failure.
    """
    from mrms.mrms_utils import _render_mrms_png_standalone
    from workers.mrms_worker import _write_mrms_overlay_cache

    _CONUS_EXTENT = [-130.0, -60.0, 21.0, 52.0]  # [west, east, south, north]

    try:
        # Create temp PNG path
        product_cache_dir = os.path.join(cache_root, "mrms", product)
        os.makedirs(product_cache_dir, exist_ok=True)

        temp_png = os.path.join(
            product_cache_dir, f"temp_{file_dt.strftime('%Y%m%d_%H%M%S')}.png"
        )

        # Render GRIB to PNG
        _render_mrms_png_standalone(grib_path, product, _CONUS_EXTENT, temp_png)

        # Write to overlay cache (handles index updates)
        _write_mrms_overlay_cache(product, temp_png, file_dt, keep_n=None)

        # Clean up temp file
        try:
            os.remove(temp_png)
        except OSError:
            pass

        frame_key = file_dt.strftime("%Y_%m_%d_%H_%M_%S")
        print(f"[mrms_live] {product} frame {frame_key} rendered OK")
        return True
    except Exception as exc:
        frame_key = file_dt.strftime("%Y_%m_%d_%H_%M_%S")
        print(f"[mrms_live] Failed to render {product} frame {frame_key}: {exc}")
        return False


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

    # Discover available timestamped GRIBs
    gribs = _discover_timestamped_gribs(product, max_hours=max_hours)
    if not gribs:
        print(f"[mrms_live] No timestamped GRIBs found for {product}")
        return 0

    # Optionally limit to latest only or max count
    if latest_only:
        gribs = gribs[:1]
    elif max_render_frames:
        gribs = gribs[:max_render_frames]

    # Render frames
    cached = 0
    t0 = _time.perf_counter()
    for grib_path, file_dt in gribs:
        if _render_mrms_frame_to_overlay(grib_path, product, file_dt, _CACHE_ROOT):
            cached += 1

    elapsed = _time.perf_counter() - t0
    print(
        f"[mrms_live] {product} rendered {cached}/{len(gribs)} frames in {elapsed:.1f}s"
    )

    if cached > 0:
        mark_run_complete("mrms_live")

    return cached


def run_mrms_live_worker(force: bool = False) -> None:
    """Background worker (optional) to keep live frames fresh."""
    # For now, this is a no-op. Frames are rendered on-demand by API.
    # In the future, could proactively warm popular products.
    pass


if __name__ == "__main__":
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
    print(f"Cached {cached} frames")
