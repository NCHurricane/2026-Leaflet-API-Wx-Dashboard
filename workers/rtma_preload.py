"""One-time RTMA cache pre-loader.

Walks the full configured lookback window for each (region, stream, product)
combination and renders every missing overlay PNG + GeoJSON into the cache.
The regular scheduled worker can then run incrementally — it only needs to
fill in the next new frame after this script has primed the cache.

Lookback windows (from rtma_config):
  rtma_hourly:       24 h   (one frame per hour   = up to 24 frames per product)
  rtma_rapid_update:  6 h   (one frame per 15 min = up to 24 frames per product)

Usage examples
--------------
  # Full backfill for all regions / streams / products (may take 30–60 min):
  python -m workers.rtma_preload

  # Scope to a single stream:
  python -m workers.rtma_preload --stream rtma_hourly

  # Scope to a single region and product:
  python -m workers.rtma_preload --region CONUS --product temperature

  # Verbose per-step timing:
  python -m workers.rtma_preload --verbose
"""

from __future__ import annotations

import os
import time as _time

from config.geo_config import STATE_BOUNDS
from config.rtma_config import (
    RTMA_STREAMS,
    RTMA_UI_PRODUCTS,
    RTMA_WORKER_REGIONS,
    clamp_stream_hours,
)

# How many pre-rendered overlay PNGs to retain per (region, stream, product)
# after this backfill run completes.  30 keeps a full 24-h window + gaps.
_OVERLAY_KEEP_N: dict[str, int] = {
    "rtma_hourly": 30,
    "rtma_rapid_update": 30,
}

_ANALYSIS_PROBE_PRODUCT = "temperature"


def _product_supported_on_stream(product: str, stream: str) -> bool:
    # 24h delta needs a now-24h pair and is only valid on hourly stream.
    if product == "temperature_change_24h" and stream != "rtma_hourly":
        return False
    return True


# ---------------------------------------------------------------------------
# Core render helper (mirrors rtma_worker._render_overlay_for_source)
# ---------------------------------------------------------------------------


def _render_overlay(
    cache_root: str,
    source,
    region: str,
    stream: str,
    product: str,
    keep_n: int,
    *,
    verbose: bool = False,
) -> str:
    """Render a single frame's overlay PNG into the flat cache.  Returns 'ok', 'skip', or 'fail'."""
    from cache.overlay_cache_utils import (
        flat_overlay_image_path,
        flat_overlay_prune_frames,
        flat_overlay_read_processed_keys,
        flat_overlay_update_index,
        flat_overlay_write_processed_keys,
        frame_key_from_datetime,
    )
    from rtma_utils import ensure_rtma_grib, render_rtma_png

    path_parts = (region.upper(), stream, product)
    frame_key = frame_key_from_datetime(source.valid_time)

    # Skip-if-exists guard — same source key + file present → nothing to do.
    processed_keys = flat_overlay_read_processed_keys(cache_root, "rtma", path_parts)
    if source.data_key in processed_keys:
        img_path = flat_overlay_image_path(cache_root, "rtma", path_parts, frame_key)
        if os.path.exists(img_path) and os.path.getsize(img_path) > 0:
            if verbose:
                print(f"  [skip] {region}/{stream}/{product}/{frame_key}")
            return "skip"

    bounds = STATE_BOUNDS.get(region, [-125, -70, 21, 52])
    crop_extent = [float(b) for b in bounds]

    try:
        img_path = flat_overlay_image_path(cache_root, "rtma", path_parts, frame_key)
        grib_path = ensure_rtma_grib(cache_root, source)
        _out_path, actual_bounds, render_meta = render_rtma_png(
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
        print(f"  [FAIL render] {region}/{stream}/{product}/{frame_key}: {exc}")
        return "fail"

    try:
        flat_overlay_update_index(
            cache_root,
            "rtma",
            path_parts,
            frame_key,
            bounds=actual_bounds,
            full_name=render_meta.get("full_name", ""),
            units=render_meta.get("units", ""),
            legend=render_meta.get("legend"),
            vmin=render_meta.get("vmin"),
            vmax=render_meta.get("vmax"),
            timestamp=render_meta.get("timestamp") or source.valid_time.isoformat(),
        )
        processed_keys.add(source.data_key)
        flat_overlay_write_processed_keys(
            cache_root, "rtma", path_parts, processed_keys, keep_n
        )
        flat_overlay_prune_frames(cache_root, "rtma", path_parts, keep_n)

        if verbose:
            print(f"  [ok]   {region}/{stream}/{product}/{frame_key}")
        return "ok"
    except Exception as exc:
        print(f"  [FAIL meta] {region}/{stream}/{product}/{frame_key}: {exc}")
        return "fail"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def run_preload(
    *,
    regions: list[str],
    streams: list[str],
    products: list[str],
    verbose: bool = False,
) -> None:
    try:
        from rtma_utils import (
            PRODUCTS,
            ensure_rtma_city_geojson,
            ensure_rtma_grib,
            iter_rtma_sources_within_hours,
        )
    except Exception as exc:
        print(f"[rtma_preload] Import error: {exc}")
        return

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cache_root = os.path.join(repo_root, "cache")
    cities_path = os.path.join(repo_root, "data", "us-cities.json")

    if not os.path.exists(cities_path):
        print("[rtma_preload] Missing data/us-cities.json — aborting")
        return

    all_product_keys = [p for p in products if p in PRODUCTS]
    analysis_products = [
        p for p in all_product_keys if PRODUCTS[p]["kind"] == "analysis"
    ]

    if not analysis_products:
        print("[rtma_preload] No valid analysis products selected — aborting")
        return

    # Build the full job list so we can show progress totals up front.
    # (region, stream, sources, stream_products)
    jobs: list[tuple[str, str, list, list[str]]] = []
    for stream in streams:
        for region in regions:
            if stream == "rtma_rapid_update" and region != "CONUS":
                continue
            stream_products = [
                p for p in analysis_products if _product_supported_on_stream(p, stream)
            ]
            if not stream_products:
                continue
            hours_back = clamp_stream_hours(stream)
            try:
                sources = list(
                    iter_rtma_sources_within_hours(
                        region, stream, _ANALYSIS_PROBE_PRODUCT, hours_back=hours_back
                    )
                )
            except Exception as exc:
                print(f"[rtma_preload] Frame discovery error {region}/{stream}: {exc}")
                sources = []
            jobs.append((region, stream, sources, stream_products))

    total_overlays = sum(len(s) * len(sp) for _, _, s, sp in jobs)
    total_geojson = sum(len(s) * len(sp) for _, _, s, sp in jobs)
    print(
        f"[rtma_preload] Plan: {len(jobs)} region/stream pair(s), "
        f"~{total_geojson} GeoJSON + ~{total_overlays} overlay frame(s) to check.\n"
        f"  Streams : {streams}\n"
        f"  Regions : {regions}\n"
        f"  Products: {analysis_products}\n"
    )

    t0 = _time.perf_counter()
    ok = skipped = failed = geojson_ok = geojson_skip = geojson_fail = 0
    overlay_done = 0

    for region, stream, sources, stream_products in jobs:
        hours_back = clamp_stream_hours(stream)
        keep_n = _OVERLAY_KEEP_N.get(stream, 30)

        print(
            f"\n── {region}/{stream}: {len(sources)} frame(s) × "
            f"{len(stream_products)} product(s), keep_n={keep_n} ──"
        )

        if not sources:
            print("   (no frames available on S3 — skipping)")
            continue

        # ── Step 1: GeoJSON city-point files ─────────────────────────────────
        print(
            f"  [GeoJSON] pre-computing {len(sources) * len(stream_products)} file(s)..."
        )
        for source in sources:
            try:
                ensure_rtma_grib(cache_root, source)
            except Exception as exc:
                geojson_fail += len(stream_products)
                print(f"  [FAIL GRIB] {region}/{stream}/{source.data_key}: {exc}")
                continue

            for product in stream_products:
                try:
                    _geo_path, meta = ensure_rtma_city_geojson(
                        cache_root,
                        source,
                        region,
                        stream,
                        product,
                        cities_path,
                        source_data_key=source.data_key,
                    )
                    geojson_ok += 1
                    if verbose:
                        print(
                            f"  [geojson ok] {region}/{stream}/{product}/{source.data_key}: "
                            f"{meta.get('feature_count', 0)} pts"
                        )
                except Exception as exc:
                    geojson_fail += 1
                    print(
                        f"  [FAIL geojson] {region}/{stream}/{product}/{source.data_key}: {exc}"
                    )

        # ── Step 2: Overlay PNG pre-render ────────────────────────────────────
        # Wind direction has no useful scalar gradient; skip its overlay.
        overlay_products = [p for p in stream_products if p != "wind_direction"]
        frame_count = len(sources)
        print(
            f"  [Overlay] rendering {frame_count * len(overlay_products)} PNG(s) "
            f"(may skip already-cached)..."
        )
        for frame_idx, source in enumerate(sources, 1):
            for product in overlay_products:
                result = _render_overlay(
                    cache_root,
                    source,
                    region,
                    stream,
                    product,
                    keep_n,
                    verbose=verbose,
                )
                overlay_done += 1
                if result == "ok":
                    ok += 1
                elif result == "skip":
                    skipped += 1
                else:
                    failed += 1

            elapsed = _time.perf_counter() - t0
            pct = overlay_done / max(total_overlays, 1) * 100
            print(
                f"  [progress] frame {frame_idx}/{frame_count} | "
                f"overlay {overlay_done}/{total_overlays} ({pct:.0f}%) | "
                f"elapsed {elapsed:.0f}s"
            )

    elapsed_total = _time.perf_counter() - t0
    print(
        f"\n[rtma_preload] Done in {elapsed_total:.1f}s\n"
        f"  Overlays — rendered: {ok}  skipped (cached): {skipped}  failed: {failed}\n"
        f"  GeoJSON  — ok: {geojson_ok}  failed: {geojson_fail}"
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Pre-load RTMA overlay cache for the last 24h (hourly) / 6h (rapid-update).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--stream",
        choices=list(RTMA_STREAMS),
        default=None,
        help="Limit backfill to one stream (default: all streams).",
    )
    parser.add_argument(
        "--region",
        choices=list(RTMA_WORKER_REGIONS),
        default=None,
        help="Limit backfill to one region (default: all regions).",
    )
    parser.add_argument(
        "--product",
        choices=list(RTMA_UI_PRODUCTS),
        default=None,
        help="Limit backfill to one product (default: all products).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-frame skip/ok messages (noisy but useful for debugging).",
    )
    args = parser.parse_args()

    run_preload(
        regions=[args.region] if args.region else list(RTMA_WORKER_REGIONS),
        streams=[args.stream] if args.stream else list(RTMA_STREAMS),
        products=[args.product] if args.product else list(RTMA_UI_PRODUCTS),
        verbose=args.verbose,
    )
