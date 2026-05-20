"""One-time MRMS cache pre-loader.

Walks the full configured lookback window for each product in the preload
list, downloads every available GRIB2 frame from S3, renders a PNG overlay
per frame, and writes each frame into the shared overlay cache.

This mirrors what rtma_preload.py does for RTMA — after this script runs the
15-minute mrms_worker only needs to add the newest frame incrementally.

Only CONUS is supported (MRMS products are CONUS-only on NODD).

Lookback windows by product class
-----------------------------------
  High-cadence (PrecipRate, Reflectivity, AzShear, …) → 2 h  (≈60 frames at 2-min cadence)
  QPE / Model accumulations                            → 6 h  (≈6 frames at hourly cadence)
  Track / MESH aggregates (60min, 120min, …)           → 6 h
  Long accumulations (24H, 48H, 72H)                   → 24 h

Usage examples
--------------
  # Full backfill for the default product set:
  python -m workers.mrms_preload

  # Single product:
  python -m workers.mrms_preload --product PrecipRate

  # Override lookback (minutes):
  python -m workers.mrms_preload --lookback 60

  # Force re-render even if frames are already cached:
  python -m workers.mrms_preload --force

  # Redirect output to log (headless/task scheduler):
  python -m workers.mrms_preload --log-to-file
"""

from __future__ import annotations

import os
import time as _time
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Products to pre-load.  Mirrors _PREWARM_PRODUCTS in mrms_worker but can be
# overridden per-run via --product.  Listed in priority order (most-requested
# first so the cache is useful as quickly as possible).
# ---------------------------------------------------------------------------
_PRELOAD_PRODUCTS: list[str] = [
    # Reflectivity (critical radar overlay for UI)
    "Refl_BaseQC",  # Base Reflectivity QC - Primary radar overlay
    # Precipitation
    "PrecipFlag",
    "PrecipRate",
    # Reflectivity variants
    "Refl_HSR",  # Hybrid Scan Reflectivity
    # Rotation tracks
    "RotationTrack_LL_60min",
    "RotationTrack_ML_60min",
    # Hail
    "SHI",
    "POSH",
    "MESH_Instant",
    "MESH_Max_60min",
    # Azimuthal shear
    "AzShear_Low",
    "AzShear_Mid",
    # Lightning
    "Lightning_30min",
    "Lightning_60min",
]

_CACHE_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cache"
)
_MRMS_CACHE = os.path.join(_CACHE_ROOT, "mrms")
_CONUS_EXTENT = [-140.0, -60.0, 21.0, 52.0]  # [west, east, south, north]


# ---------------------------------------------------------------------------
# Lookback window per product class (mirrors worker's candidate_lookbacks but
# returns a single best window rather than a fallback list)
# ---------------------------------------------------------------------------


def _lookback_minutes(product: str) -> int:
    """Return the default lookback window in minutes for a product."""
    p = str(product or "")
    if p.startswith("QPE_") or p.startswith("Model_"):
        return 6 * 60
    if any(tag in p for tag in ["_1440min", "_360min", "_240min", "_120min"]):
        return 6 * 60
    if any(tag in p for tag in ["_72H", "_48H", "_24H", "_12H", "_06H"]):
        return 24 * 60
    if any(tag in p for tag in ["_03H", "_01H"]):
        return 6 * 60
    # High-cadence: 2-minute data → keep last 6 hours (≈180 frames).
    return 6 * 60


def _keep_n(product: str) -> int:
    """Return how many frames to retain in the overlay cache per product."""
    p = str(product or "")
    # Long accumulations publish very infrequently; a handful is plenty.
    if any(tag in p for tag in ["_72H", "_48H", "_24H"]):
        return 10
    # QPE / Model: hourly cadence over 6 h → ~6 frames, keep a bit more.
    if p.startswith("QPE_") or p.startswith("Model_"):
        return 12
    # Mid-range aggregates over 6 h window.
    if any(tag in p for tag in ["_1440min", "_360min", "_240min", "_120min"]):
        return 12
    if any(tag in p for tag in ["_12H", "_06H", "_03H", "_01H"]):
        return 12
    # High-cadence: 2-min data over 6 h → keep up to 180 frames.
    return 180


# ---------------------------------------------------------------------------
# Core: enumerate all frames in window, download + render + cache each one
# ---------------------------------------------------------------------------


def _render_frame(
    product: str,
    s3_key: str,
    file_dt: "datetime",
    product_cache_dir: str,
    *,
    force: bool = False,
    verbose: bool = False,
) -> str:
    """Download (if needed), render, and write one frame to the overlay cache.

    Returns 'ok', 'skip', or 'fail'.
    """

    from cache.overlay_cache_utils import (
        flat_overlay_image_path,
        flat_overlay_read_processed_keys,
        frame_key_from_datetime,
    )
    from mrms.mrms_nodd_utils import download_mrms_file
    from workers.mrms_worker import (
        _render_mrms_png_standalone,
        _write_mrms_overlay_cache,
    )

    if file_dt.tzinfo is None:
        file_dt = file_dt.replace(tzinfo=timezone.utc)
    frame_key = frame_key_from_datetime(file_dt)
    path_parts = ("CONUS", "default", product)
    source_key = f"mrms:{product}:{frame_key}"

    # Skip-if-exists guard unless --force.
    if not force:
        processed_keys = flat_overlay_read_processed_keys(
            _CACHE_ROOT, "mrms", path_parts
        )
        if source_key in processed_keys:
            img = flat_overlay_image_path(_CACHE_ROOT, "mrms", path_parts, frame_key)
            if os.path.exists(img) and os.path.getsize(img) > 0:
                if verbose:
                    print(f"    [skip] {frame_key}")
                return "skip"

    # Download GRIB2 (reuses local copy if already on disk).
    try:
        local_path = download_mrms_file(s3_key, product_cache_dir)
    except Exception as exc:
        print(f"    [FAIL download] {frame_key}: {exc}")
        return "fail"

    # Render to a per-frame PNG path so concurrent frames don't clobber each other.
    png_path = os.path.join(product_cache_dir, f"frame_{frame_key}.png")
    try:
        _render_mrms_png_standalone(local_path, product, _CONUS_EXTENT, png_path)
    except Exception as exc:
        print(f"    [FAIL render] {frame_key}: {exc}")
        return "fail"

    # Write into the overlay cache; defer pruning (caller does one final prune).
    try:
        _write_mrms_overlay_cache(product, png_path, file_dt, keep_n=None)
    except Exception as exc:
        print(f"    [FAIL cache] {frame_key}: {exc}")
        return "fail"

    if verbose:
        print(f"    [ok] {frame_key}")
    return "ok"


def _backfill_product(
    product: str,
    lookback_minutes: int,
    *,
    force: bool = False,
    verbose: bool = False,
) -> tuple[int, int, int]:
    """Backfill all frames for one product.  Returns (ok, skipped, failed)."""
    from concurrent.futures import ProcessPoolExecutor, as_completed
    from datetime import timedelta
    from mrms.mrms_nodd_utils import list_mrms_files
    from datetime import datetime as _dt

    end_time = _dt.now(tz=timezone.utc)
    start_time = end_time - timedelta(minutes=lookback_minutes)

    product_cache_dir = os.path.join(_MRMS_CACHE, product)
    os.makedirs(product_cache_dir, exist_ok=True)

    print(
        f"  Listing S3 frames for {product} "
        f"({start_time.strftime('%H:%MZ')} – {end_time.strftime('%H:%MZ')})..."
    )
    try:
        frames = list_mrms_files(product, start_time, end_time)
    except Exception as exc:
        print(f"  [FAIL list] {product}: {exc}")
        return 0, 0, 1

    if not frames:
        print(f"  [FAIL list] {product}: no files found in window")
        return 0, 0, 1

    print(f"  {len(frames)} frame(s) found — rendering ({os.cpu_count()} workers)...")
    ok = skipped = failed = 0
    t0 = _time.perf_counter()

    # Render frames in parallel using ProcessPoolExecutor
    max_workers = min(os.cpu_count() or 1, 4)
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _render_frame,
                product,
                s3_key,
                file_dt,
                product_cache_dir,
                force=force,
                verbose=verbose,
            ): idx
            for idx, (s3_key, file_dt) in enumerate(frames, 1)
        }

        for future in as_completed(futures):
            idx = futures[future]
            try:
                result = future.result()
                if result == "ok":
                    ok += 1
                elif result == "skip":
                    skipped += 1
                else:
                    failed += 1
            except Exception as exc:
                failed += 1
                print(f"    [FAIL exception] frame {idx}: {exc}")

            total = idx
            if total % 10 == 0 or total == len(frames):
                pct = total / len(frames) * 100
                print(
                    f"  [progress] {total}/{len(frames)} ({pct:.0f}%) "
                    f"ok={ok} skip={skipped} fail={failed} "
                    f"elapsed={_time.perf_counter() - t0:.0f}s"
                )

    # Single prune pass now that all frames are written.
    kn = _keep_n(product)
    from cache.overlay_cache_utils import flat_overlay_prune_frames

    pruned = flat_overlay_prune_frames(
        _CACHE_ROOT, "mrms", ("CONUS", "default", product), kn
    )
    if pruned:
        print(f"  Pruned {pruned} old frame(s) (kept {kn})")

    return ok, skipped, failed


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------


def run_preload(
    products: list[str],
    lookback_minutes: int | None = None,
    *,
    force: bool = False,
    verbose: bool = False,
) -> None:
    from config.mrms_config import MRMS_PRODUCTS

    valid = [p for p in products if p in MRMS_PRODUCTS]
    invalid = [p for p in products if p not in MRMS_PRODUCTS]
    if invalid:
        print(f"[mrms_preload] Unknown product(s) ignored: {invalid}")
    if not valid:
        print("[mrms_preload] No valid products — aborting")
        return

    print(
        f"[mrms_preload] Starting backfill for {len(valid)} product(s):\n"
        f"  {valid}\n"
        f"  force={force}  verbose={verbose}\n"
    )

    t0 = _time.perf_counter()
    total_ok = total_skip = total_fail = 0

    for product in valid:
        lb = (
            lookback_minutes
            if lookback_minutes is not None
            else _lookback_minutes(product)
        )
        kn = _keep_n(product)
        print(f"\n── {product} (lookback {lb} min, keep_n {kn}) ──")
        ok, skipped, failed = _backfill_product(
            product, lb, force=force, verbose=verbose
        )
        total_ok += ok
        total_skip += skipped
        total_fail += failed

    elapsed = _time.perf_counter() - t0
    print(
        f"\n[mrms_preload] Done in {elapsed:.1f}s  "
        f"rendered: {total_ok}  skipped (cached): {total_skip}  failed: {total_fail}"
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    from config.mrms_config import MRMS_PRODUCTS

    parser = argparse.ArgumentParser(
        description="Pre-load MRMS overlay cache for the default prewarm product set.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--product",
        choices=sorted(MRMS_PRODUCTS.keys()),
        default=None,
        help="Backfill a single product instead of the default set.",
    )
    parser.add_argument(
        "--lookback",
        type=int,
        default=None,
        metavar="MINUTES",
        help="Override lookback window in minutes (default: per-product class).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-render even if the overlay cache is already fresh.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-frame skip/ok messages.",
    )
    parser.add_argument(
        "--log-to-file",
        action="store_true",
        help="Redirect stdout/stderr to logs/scheduled/mrms_preload.log.",
    )
    args = parser.parse_args()

    if args.log_to_file:
        from workers._freshness import redirect_stdio_to_log

        redirect_stdio_to_log("mrms_preload")

    products = [args.product] if args.product else list(_PRELOAD_PRODUCTS)
    run_preload(
        products=products,
        lookback_minutes=args.lookback,
        force=args.force,
        verbose=args.verbose,
    )
