"""One-time surface cache pre-loader.

Backfills hourly CONUS surface cache artifacts for a rolling window (default 24 h):
1) Archive value payloads (same JSON schema and cache-key strategy as /api/archive/surface)
2) Hourly gradient PNG + metadata frames for each gradient-capable product
3) Live gradient cache refresh using the newest available frame

Usage examples
--------------
  # Full 24h backfill for all surface products (values + gradients)
  python -m workers.surface_preload

  # Single product, 12h window
  python -m workers.surface_preload --product temperature --hours 12

  # Values only
  python -m workers.surface_preload --skip-gradients

  # Gradients only (hourly archive + live latest)
  python -m workers.surface_preload --skip-values

  # Force overwrite existing caches
  python -m workers.surface_preload --force

  # Redirect stdout/stderr to logs/scheduled/surface_preload.log
  python -m workers.surface_preload --log-to-file
"""

from __future__ import annotations

import json
import os
import time as _time
from datetime import datetime, timedelta, timezone

import matplotlib
import numpy as np

from main_old import _SURFACE_PRODUCTS, _build_surface_stations
from surface import surface_utils
from workers import surface_worker

_PRELOAD_REGION = "CONUS"
_DEFAULT_HOURS = 24

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CACHE_ROOT = os.path.join(_REPO_ROOT, "cache")
_ARCHIVE_JSON_DIR = os.path.join(_CACHE_ROOT, "archive", "json")
_ARCHIVE_GRADIENT_ROOT = os.path.join(
    _CACHE_ROOT,
    "surface",
    "gradients",
    "archive",
    _PRELOAD_REGION,
)


def _frame_key(ts: datetime) -> str:
    dt = ts.astimezone(timezone.utc)
    return dt.strftime("%Y%m%d%H%M")


def _archive_cache_path(prefix: str, **params) -> str:
    """Return a deterministic archive cache path that matches main.py behavior."""
    import hashlib

    os.makedirs(_ARCHIVE_JSON_DIR, exist_ok=True)
    key = json.dumps(params, sort_keys=True, default=str)
    digest = hashlib.sha256(key.encode()).hexdigest()[:16]
    return os.path.join(_ARCHIVE_JSON_DIR, f"{prefix}_{digest}.json")


def _write_json_atomic(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.part"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, separators=(",", ":"))
    os.replace(tmp, path)


def _build_hourly_times(hours: int) -> list[datetime]:
    now = datetime.now(timezone.utc)
    end = now.replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(hours=max(1, int(hours)) - 1)
    out: list[datetime] = []
    cursor = start
    while cursor <= end:
        out.append(cursor)
        cursor += timedelta(hours=1)
    return out


def _preload_values(
    *,
    region: str,
    products: list[str],
    frame_times: list[datetime],
    force: bool,
) -> tuple[int, int, int]:
    """Write /api/archive/surface-compatible JSON cache entries for each product."""
    if not frame_times:
        return 0, 0, 0

    frame_dfs = surface_utils.fetch_metar_data_archive_frames(
        region, frame_times, source="iem"
    )
    date_from = frame_times[0].isoformat()
    date_to = frame_times[-1].isoformat()
    max_frames = len(frame_times)

    wrote = skipped = failed = 0
    for product in products:
        cache_path = _archive_cache_path(
            "surface",
            region=region,
            product=product,
            date_from=date_from,
            date_to=date_to,
            max_frames=max_frames,
        )
        if not force and os.path.isfile(cache_path):
            skipped += 1
            continue

        frames = []
        try:
            for idx, ts in enumerate(frame_times):
                df = frame_dfs[idx] if idx < len(frame_dfs) else None
                if df is None:
                    df = surface_utils.fetch_metar_data_at_time(
                        region, ts, source="iem"
                    )
                stations = _build_surface_stations(df, product)
                frames.append(
                    {
                        "timestamp": ts.isoformat(),
                        "stations": stations,
                        "product": product,
                        "unit": _SURFACE_PRODUCTS[product]["unit"],
                    }
                )

            payload = {
                "status": "success",
                "type": "surface_archive",
                "region": region,
                "product": product,
                "product_label": product,
                "source": "awc",
                "network": "ASOS",
                "date_from": date_from,
                "date_to": date_to,
                "frame_count": len(frames),
                "frames": frames,
            }
            _write_json_atomic(cache_path, payload)
            wrote += 1
            print(
                f"  [values ok] {product}: {len(frames)} frame(s) -> {os.path.relpath(cache_path, _REPO_ROOT)}"
            )
        except Exception as exc:
            failed += 1
            print(f"  [values fail] {product}: {exc}")

    return wrote, skipped, failed


def _render_gradient_frame(
    *,
    product: str,
    cfg: dict,
    df,
    ts: datetime,
    force: bool,
) -> tuple[bool, bool]:
    """Render one hourly gradient frame.

    Returns (written, skipped).
    """
    product_dir = os.path.join(_ARCHIVE_GRADIENT_ROOT, product)
    os.makedirs(product_dir, exist_ok=True)

    key = _frame_key(ts)
    png_path = os.path.join(product_dir, f"{key}.png")
    meta_path = os.path.join(product_dir, f"{key}.json")

    if not force and os.path.isfile(png_path) and os.path.isfile(meta_path):
        return False, True

    col = cfg["col"]
    if col not in df.columns:
        return False, False

    vals = np.asarray(df[col], dtype=np.float64)
    lons = np.asarray(df["longitude"], dtype=np.float64)
    lats = np.asarray(df["latitude"], dtype=np.float64)

    mask = np.isfinite(vals) & np.isfinite(lons) & np.isfinite(lats)
    vals = vals[mask]
    lons = lons[mask]
    lats = lats[mask]

    if vals.size < 20:
        return False, False

    grid, bounds = surface_worker._interpolate_surface_grid(lons, lats, vals)
    if grid is None or bounds is None:
        return False, False

    rgba = surface_worker._build_rgba_from_values(grid, cfg["anchors"])
    matplotlib.use("Agg")
    from matplotlib import image as mpl_image

    mpl_image.imsave(png_path, rgba)

    rel = os.path.relpath(png_path, _CACHE_ROOT).replace("\\", "/")
    payload = {
        "region": _PRELOAD_REGION,
        "product": product,
        "frame_key": key,
        "bounds": bounds,
        "image_url": f"/cache/{rel}",
        "timestamp": ts.isoformat(),
        "station_count": int(vals.size),
        "grid": {
            "width": int(surface_worker._GRADIENT_WIDTH),
            "height": int(surface_worker._GRADIENT_HEIGHT),
        },
        "unit": str(cfg["unit"]),
    }
    _write_json_atomic(meta_path, payload)

    return True, False


def _preload_gradients(
    *,
    products: list[str],
    frame_times: list[datetime],
    force: bool,
) -> tuple[int, int, int]:
    """Backfill hourly archive gradient frames and refresh live latest frame."""
    if not frame_times:
        return 0, 0, 0

    frame_dfs = surface_utils.fetch_metar_data_archive_frames(
        _PRELOAD_REGION, frame_times, source="iem"
    )

    written = skipped = failed = 0
    latest_cache: dict[str, tuple[np.ndarray, list[float], int, str]] = {}

    for idx, ts in enumerate(frame_times):
        df = frame_dfs[idx] if idx < len(frame_dfs) else None
        if df is None or df.empty:
            try:
                df = surface_utils.fetch_metar_data_at_time(
                    _PRELOAD_REGION, ts, source="iem"
                )
            except Exception:
                df = None
        if df is None or df.empty:
            continue

        for product in products:
            cfg = surface_worker._SURFACE_GRADIENT_PRODUCTS.get(product)
            if cfg is None:
                continue

            try:
                wrote, did_skip = _render_gradient_frame(
                    product=product,
                    cfg=cfg,
                    df=df,
                    ts=ts,
                    force=force,
                )
                if did_skip:
                    skipped += 1
                elif wrote:
                    written += 1
                else:
                    failed += 1

                # Keep the newest successful frame payload to refresh live cache.
                col = cfg["col"]
                if col in df.columns:
                    vals = np.asarray(df[col], dtype=np.float64)
                    lons = np.asarray(df["longitude"], dtype=np.float64)
                    lats = np.asarray(df["latitude"], dtype=np.float64)
                    m = np.isfinite(vals) & np.isfinite(lons) & np.isfinite(lats)
                    vals = vals[m]
                    lons = lons[m]
                    lats = lats[m]
                    if vals.size >= 20:
                        grid, bounds = surface_worker._interpolate_surface_grid(
                            lons, lats, vals
                        )
                        if grid is not None and bounds is not None:
                            rgba = surface_worker._build_rgba_from_values(
                                grid, cfg["anchors"]
                            )
                            latest_cache[product] = (
                                rgba,
                                bounds,
                                int(vals.size),
                                str(cfg["unit"]),
                            )
            except Exception as exc:
                failed += 1
                print(f"  [grad fail] {product} {ts.isoformat()}: {exc}")

        if (idx + 1) % 4 == 0 or idx + 1 == len(frame_times):
            print(
                f"  [grad progress] {idx + 1}/{len(frame_times)} frame(s) "
                f"written={written} skip={skipped} fail={failed}"
            )

    # Refresh live gradient cache from the newest successfully rendered frame.
    refreshed = 0
    for product, (rgba, bounds, station_count, unit) in latest_cache.items():
        try:
            surface_worker._write_gradient_cache(
                product=product,
                rgba=rgba,
                bounds=bounds,
                timestamp_iso=frame_times[-1].isoformat(),
                station_count=station_count,
                unit=unit,
            )
            refreshed += 1
        except Exception as exc:
            print(f"  [live grad fail] {product}: {exc}")

    if refreshed:
        print(f"  [live grad ok] refreshed {refreshed} product(s)")

    return written, skipped, failed


def run_preload(
    *,
    hours: int = _DEFAULT_HOURS,
    products: list[str] | None = None,
    force: bool = False,
    preload_values: bool = True,
    preload_gradients: bool = True,
) -> None:
    if not preload_values and not preload_gradients:
        print(
            "[surface_preload] Nothing to do (--skip-values and --skip-gradients both set)"
        )
        return

    frame_times = _build_hourly_times(hours)
    all_products = sorted(_SURFACE_PRODUCTS.keys())
    selected = products or all_products

    unknown = sorted(set(selected) - set(all_products))
    if unknown:
        print(f"[surface_preload] Unknown product(s) ignored: {unknown}")
    selected = [p for p in selected if p in all_products]
    if not selected:
        print("[surface_preload] No valid products selected")
        return

    gradient_products = [
        p for p in selected if p in surface_worker._SURFACE_GRADIENT_PRODUCTS
    ]

    print(
        "[surface_preload] Starting\n"
        f"  region={_PRELOAD_REGION}\n"
        f"  frames={len(frame_times)} ({frame_times[0].isoformat()} -> {frame_times[-1].isoformat()})\n"
        f"  products={selected}\n"
        f"  gradients={gradient_products}\n"
        f"  force={force}\n"
    )

    t0 = _time.perf_counter()

    values_stats = (0, 0, 0)
    if preload_values:
        print("[surface_preload] Preloading archive values...")
        values_stats = _preload_values(
            region=_PRELOAD_REGION,
            products=selected,
            frame_times=frame_times,
            force=force,
        )

    grad_stats = (0, 0, 0)
    if preload_gradients:
        print("[surface_preload] Preloading gradients...")
        grad_stats = _preload_gradients(
            products=gradient_products,
            frame_times=frame_times,
            force=force,
        )

    elapsed = _time.perf_counter() - t0
    print(
        "\n[surface_preload] Done "
        f"in {elapsed:.1f}s\n"
        f"  values    - wrote={values_stats[0]} skip={values_stats[1]} fail={values_stats[2]}\n"
        f"  gradients - wrote={grad_stats[0]} skip={grad_stats[1]} fail={grad_stats[2]}"
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Pre-load 24h surface values + gradients cache.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=_DEFAULT_HOURS,
        help="Rolling window size in hours (default: 24).",
    )
    parser.add_argument(
        "--product",
        action="append",
        choices=sorted(_SURFACE_PRODUCTS.keys()),
        help="Limit to one or more products (repeat flag). Default: all products.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing cache files.",
    )
    parser.add_argument(
        "--skip-values",
        action="store_true",
        help="Skip archive values cache generation.",
    )
    parser.add_argument(
        "--skip-gradients",
        action="store_true",
        help="Skip gradient frame generation.",
    )
    parser.add_argument(
        "--log-to-file",
        action="store_true",
        help="Redirect stdout/stderr to logs/scheduled/surface_preload.log.",
    )
    args = parser.parse_args()

    if args.log_to_file:
        from workers._freshness import redirect_stdio_to_log

        redirect_stdio_to_log("surface_preload")

    run_preload(
        hours=max(1, int(args.hours)),
        products=args.product,
        force=args.force,
        preload_values=not args.skip_values,
        preload_gradients=not args.skip_gradients,
    )
