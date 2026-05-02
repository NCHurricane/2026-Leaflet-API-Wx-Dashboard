"""Background worker: pre-compute RTMA city-point GeoJSON caches.

Strategy (revised):
  1. For each region/stream pair, discover available frames ONCE by probing S3
     with a representative product (avoids repeating the same HEAD checks for
     every product that maps to the same underlying GRIB file).
  2. Pre-download all GRIB files for the discovered frames.
  3. For each downloaded GRIB, generate city-point GeoJSON for every compatible
     product — all extracted from the already-cached GRIB, no extra downloads.

Analysis products (temperature, dew_point, wind_speed, …) all share a single
`2dvaranl_ndfd` GRIB per frame.  Precip products use a separate GRIB and are
discovered and downloaded in their own pass.
"""

from __future__ import annotations

import os
import time as _time

from config.rtma_config import (
    RTMA_STREAMS,
    RTMA_UI_PRODUCTS,
    RTMA_WORKER_REGIONS,
    clamp_stream_hours,
)
from workers._freshness import is_cache_fresh, mark_run_complete

# Skip if successful run happened recently (75% of 15-min schedule)
_FRESH_WINDOW_SEC = 11 * 60

_PRELOAD_REGIONS = list(RTMA_WORKER_REGIONS)
_PRELOAD_STREAMS = list(RTMA_STREAMS)
_PRELOAD_PRODUCTS = list(RTMA_UI_PRODUCTS)

# Representative product used for frame discovery.
_ANALYSIS_PROBE_PRODUCT = "temperature"


def run_rtma_worker(force: bool = False) -> None:
    if not force and is_cache_fresh("rtma", _FRESH_WINDOW_SEC):
        print("[rtma_worker] Cache fresh - skipping run")
        return

    try:
        from rtma_utils import (
            PRODUCTS,
            ensure_rtma_city_geojson,
            ensure_rtma_grib,
            iter_rtma_sources_within_hours,
        )
    except Exception as exc:
        print(f"[rtma_worker] Import error: {exc}")
        return

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cache_root = os.path.join(repo_root, "cache")
    cities_path = os.path.join(repo_root, "data", "us-cities.json")

    if not os.path.exists(cities_path):
        print("[rtma_worker] Missing data/us-cities.json - aborting")
        return

    all_product_keys = [p for p in _PRELOAD_PRODUCTS if p in PRODUCTS]
    analysis_products = [
        p for p in all_product_keys if PRODUCTS[p]["kind"] == "analysis"
    ]

    ok = 0
    skipped = 0
    failed = 0

    t0 = _time.perf_counter()

    for stream in _PRELOAD_STREAMS:
        for region in _PRELOAD_REGIONS:
            if stream == "rtma_rapid_update" and region != "CONUS":
                continue

            hours_back = clamp_stream_hours(stream)

            # ── Analysis products (one GRIB per frame covers all variables) ──
            if analysis_products:
                try:
                    sources = list(
                        iter_rtma_sources_within_hours(
                            region,
                            stream,
                            _ANALYSIS_PROBE_PRODUCT,
                            hours_back=hours_back,
                        )
                    )
                except Exception:
                    sources = []

                for source in sources:
                    # Pre-download the GRIB once for this frame.
                    try:
                        ensure_rtma_grib(cache_root, source)
                    except Exception as exc:
                        failed += len(analysis_products)
                        print(
                            f"[rtma_worker] GRIB download ERROR "
                            f"{region}/{stream}/{source.data_key}: {exc}"
                        )
                        continue

                    # Generate GeoJSON for every analysis product from the cached GRIB.
                    for product in analysis_products:
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
                            ok += 1
                            print(
                                f"[rtma_worker] {region}/{stream}/{product}/"
                                f"{source.data_key}: {meta.get('feature_count', 0)} pts"
                            )
                        except Exception as exc:
                            failed += 1
                            print(
                                f"[rtma_worker] GeoJSON ERROR "
                                f"{region}/{stream}/{product}/{source.data_key}: {exc}"
                            )

    elapsed = _time.perf_counter() - t0
    print(
        "[rtma_worker] done "
        f"ok={ok} skipped={skipped} failed={failed} in {elapsed:.1f}s"
    )
    if ok > 0:
        mark_run_complete("rtma")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run the RTMA worker once.")
    parser.add_argument("--force", action="store_true", help="Bypass freshness gate.")
    parser.add_argument(
        "--log-to-file",
        action="store_true",
        help="Redirect stdout/stderr to logs/scheduled/rtma.log (for headless task runs).",
    )
    args = parser.parse_args()
    if args.log_to_file:
        from workers._freshness import redirect_stdio_to_log

        redirect_stdio_to_log("rtma")
    run_rtma_worker(force=args.force)
