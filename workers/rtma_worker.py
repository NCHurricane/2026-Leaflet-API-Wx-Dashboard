"""Background worker: pre-compute RTMA city-point GeoJSON caches and pre-rendered
raster overlay PNGs.

Strategy (revised):
  1. For each region/stream pair, discover available frames ONCE by probing S3
     with a representative product (avoids repeating the same HEAD checks for
     every product that maps to the same underlying GRIB file).
  2. Pre-download all GRIB files for the discovered frames.
  3. For each downloaded GRIB, generate city-point GeoJSON for every compatible
     product — all extracted from the already-cached GRIB, no extra downloads.
  4. For *every* discovered frame of each (region, stream, product), render a
     full-extent PNG overlay and write meta.json + update the family index.
     Already-rendered frames are skipped (skip-if-exists guard), so incremental
     runs are cheap — only new frames cause real work.  This builds a rolling
     on-disk archive that the scrubber can replay without any on-demand GRIB
     parsing.

Analysis products (temperature, dew_point, wind_speed, …) all share a single
`2dvaranl_ndfd` GRIB per frame.  Precip products use a separate GRIB and are
discovered and downloaded in their own pass.
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
from workers._freshness import is_cache_fresh, mark_run_complete

# Skip if successful run happened recently (75% of 15-min schedule)
_FRESH_WINDOW_SEC = 11 * 60

_PRELOAD_REGIONS = list(RTMA_WORKER_REGIONS)
_PRELOAD_STREAMS = list(RTMA_STREAMS)
_PRELOAD_PRODUCTS = list(RTMA_UI_PRODUCTS)

# Representative product used for frame discovery.
_ANALYSIS_PROBE_PRODUCT = "temperature"

# How many pre-rendered overlay PNGs to keep per (region, stream, product).
# Keyed by stream so the rolling window matches the configured lookback.
_OVERLAY_KEEP_N: dict[str, int] = {
    "rtma_hourly": 30,  # covers 24 h + headroom for gaps
    "rtma_rapid_update": 30,  # 15-min cadence × 6 h = 24 frames + headroom
}


def _product_supported_on_stream(product: str, stream: str) -> bool:
    # 24h delta needs a now-24h pair and is only valid on hourly stream.
    if product == "temperature_change_24h" and stream != "rtma_hourly":
        return False
    return True


def _render_overlay_for_source(
    cache_root: str,
    source,
    region: str,
    stream: str,
    product: str,
    keep_n: int = 30,
) -> bool:
    """Render a full-extent PNG overlay for *source* and write meta + update index.

    Returns True on success, False on failure.
    """
    from cache.overlay_cache_utils import (
        build_overlay_meta,
        frame_key_from_datetime,
        overlay_image_path,
        prune_overlay_frames,
        read_overlay_meta,
        update_overlay_index,
        write_overlay_meta,
    )
    from rtma_utils import (
        build_rtma_legend,
        get_product_config,
        render_rtma_png,
        ensure_rtma_grib,
    )

    frame_key = frame_key_from_datetime(source.valid_time)

    # Skip if overlay already rendered for this exact source.
    existing = read_overlay_meta(cache_root, "rtma", region, stream, product, frame_key)
    if existing and existing.get("source_data_key") == source.data_key:
        img_path = overlay_image_path(
            cache_root, "rtma", region, stream, product, frame_key
        )
        if os.path.exists(img_path) and os.path.getsize(img_path) > 0:
            return True  # already fresh

    bounds = STATE_BOUNDS.get(region, [-125, -70, 21, 52])
    west, east, south, north = (
        float(bounds[0]),
        float(bounds[1]),
        float(bounds[2]),
        float(bounds[3]),
    )
    crop_extent = [west, east, south, north]

    try:
        img_path = overlay_image_path(
            cache_root, "rtma", region, stream, product, frame_key
        )
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
        print(
            f"[rtma_worker] Overlay render ERROR {region}/{stream}/{product}/{frame_key}: {exc}"
        )
        return False

    try:
        config = get_product_config(product)
        legend = build_rtma_legend(config)

        # Image URL relative to the project web root (served as /cache/...).
        import os as _os

        img_rel = _os.path.relpath(img_path, _os.path.dirname(cache_root)).replace(
            "\\", "/"
        )
        # Ensure it starts with cache/ for consistent frontend use.
        cache_dir_name = _os.path.basename(cache_root)
        img_rel_url = f"/{cache_dir_name}/{_os.path.relpath(img_path, cache_root).replace(chr(92), '/')}"

        meta_rel_url = img_rel_url.replace("/overlay.png", "/meta.json")

        meta = build_overlay_meta(
            family="rtma",
            region=region,
            stream=stream,
            product=product,
            frame_key=frame_key,
            timestamp=render_meta.get("timestamp") or source.valid_time.isoformat(),
            source_data_key=source.data_key,
            full_name=render_meta.get("full_name", config["label"]),
            units=render_meta.get("units", config["units"]),
            bounds=actual_bounds,
            image_rel_url=img_rel_url,
            legend=legend,
            vmin=config.get("vmin"),
            vmax=config.get("vmax"),
        )

        write_overlay_meta(cache_root, "rtma", region, stream, product, frame_key, meta)
        update_overlay_index(
            cache_root, "rtma", region, stream, product, frame_key, meta_rel_url
        )
        prune_overlay_frames(cache_root, "rtma", region, stream, product, keep_n=keep_n)

        print(f"[rtma_worker] Overlay OK {region}/{stream}/{product}/{frame_key}")
        return True
    except Exception as exc:
        print(
            f"[rtma_worker] Overlay meta/index ERROR {region}/{stream}/{product}/{frame_key}: {exc}"
        )
        return False


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

            stream_products = [
                p for p in analysis_products if _product_supported_on_stream(p, stream)
            ]
            if not stream_products:
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

                overlay_products = [p for p in stream_products if p != "wind_direction"]
                keep_n = _OVERLAY_KEEP_N.get(stream, 30)

                for source in sources:
                    # Pre-download the GRIB once for this frame.
                    try:
                        ensure_rtma_grib(cache_root, source)
                    except Exception as exc:
                        failed += len(stream_products)
                        print(
                            f"[rtma_worker] GRIB download ERROR "
                            f"{region}/{stream}/{source.data_key}: {exc}"
                        )
                        continue

                    # Generate GeoJSON for every analysis product from the cached GRIB.
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

                    # ── Overlay PNG pre-render for this frame ─────────────────
                    # Runs immediately after GeoJSON so the latest frame's overlay
                    # is available as early as possible (not after all frames complete).
                    # Wind direction has no useful scalar gradient; skip its overlay.
                    for product in overlay_products:
                        rendered = _render_overlay_for_source(
                            cache_root,
                            source,
                            region,
                            stream,
                            product,
                            keep_n=keep_n,
                        )
                        if rendered:
                            ok += 1
                        else:
                            failed += 1

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
