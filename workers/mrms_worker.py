"""
MRMS Worker
Downloads the latest GRIB2 for the currently-active MRMS product from S3
and stores it in cache/mrms/{product}/conus.grib2.gz.

The active product is tracked via FastAPI app.state.active_mrms_product.
Only ONE product is refreshed at a time (active product pivots on user request).
"""

import json
import os
import shutil
from datetime import timezone

from workers._freshness import is_cache_fresh, mark_run_complete

_CACHE_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cache"
)
_MRMS_CACHE = os.path.join(_CACHE_ROOT, "mrms")

# User-selected high-value products to keep hot in cache.
_PREWARM_PRODUCTS = [
    "Refl_HSR",  # Reflectivity - Hybrid Scan
    "PrecipFlag",  # Surface Precip Type
    "QPE_MS2_01H",  # QPE Multisensor Pass2 1-hour
    "RotationTrack_LL_60min",  # Rotation Tracks low-level 60 min
    "MESH_Max_60min",  # MESH/Hail max 60 min
    "Lightning_30min",  # Lightning probability next 30 min
]

# Module-level active product state (also mirrored in app.state for API access)
_active_product: str = "PrecipFlag"

# Skip if a successful refresh happened within the last ~11 min
# (75% of the 15 min Task Scheduler interval).
_FRESH_WINDOW_SEC = 11 * 60


def _candidate_lookbacks_minutes(product: str) -> list[int]:
    """Return ordered lookback windows for product fetch attempts.

    Many MRMS products are available every 2-5 minutes, but some aggregate/model
    products publish less frequently. A fixed 30-minute window is too narrow for
    those feeds and can cause false 503s.
    """
    p = str(product or "")

    # Explicit hourly/multi-hour accumulations and model fields.
    if p.startswith("QPE_") or p.startswith("Model_"):
        return [30, 120, 360, 1440]

    # Time-aggregated track/max products.
    if any(tag in p for tag in ["_1440min", "_360min", "_240min", "_120min"]):
        return [30, 120, 360, 1440]

    # Mid-cadence products (hourly windows or 24-72h labels).
    if any(
        tag in p for tag in ["_72H", "_48H", "_24H", "_12H", "_06H", "_03H", "_01H"]
    ):
        return [30, 120, 360, 1440]

    # High-cadence defaults.
    return [30, 120]


def set_active_product(product: str) -> None:
    global _active_product
    _active_product = product


def get_active_product() -> str:
    return _active_product


def _fetch_latest_product_grib(
    product: str, get_latest_mrms_file
) -> tuple[str, object] | None:
    """Fetch latest GRIB for a product, with adaptive lookback and atomic replace."""
    product_cache_dir = os.path.join(_MRMS_CACHE, product)
    os.makedirs(product_cache_dir, exist_ok=True)

    result = None
    for lookback_minutes in _candidate_lookbacks_minutes(product):
        result = get_latest_mrms_file(
            product,
            lookback_minutes=lookback_minutes,
            local_dir=product_cache_dir,
        )
        if result is not None:
            if lookback_minutes > 30:
                print(
                    f"[mrms_worker] {product} found using extended "
                    f"lookback ({lookback_minutes} min)"
                )
            break

    if result is None:
        return None

    local_path, file_dt = result
    dest = os.path.join(product_cache_dir, "conus.grib2.gz")

    if local_path != dest:
        tmp = dest + ".tmp"
        shutil.move(local_path, tmp)
        if os.path.exists(dest):
            os.remove(dest)
        os.rename(tmp, dest)

    return dest, file_dt


def _run_prewarm_product_set(skip_product: str, get_latest_mrms_file) -> None:
    """Fetch and prewarm the configured MRMS products after active product refresh."""
    for product in _PREWARM_PRODUCTS:
        if product == skip_product:
            continue

        sentinel_name = f"mrms_{product}"
        if is_cache_fresh(sentinel_name, _FRESH_WINDOW_SEC):
            continue

        try:
            fetched = _fetch_latest_product_grib(product, get_latest_mrms_file)
            if fetched is None:
                print(f"[mrms_worker] No files found for prewarm product {product}")
                continue

            grib_path, file_dt = fetched
            product_cache_dir = os.path.join(_MRMS_CACHE, product)
            print(
                f"[mrms_worker] {product} cached at "
                f"{file_dt.strftime('%Y-%m-%d %H:%M UTC')} (prewarm set)"
            )
            mark_run_complete(sentinel_name)
            _prewarm_conus_png(product, grib_path, product_cache_dir, file_dt=file_dt)
        except Exception as exc:
            print(f"[mrms_worker] Prewarm set fetch/render failed for {product}: {exc}")


def run_mrms_worker(force: bool = False) -> None:
    """Download the latest GRIB2 for the active MRMS product."""
    global _active_product
    product = _active_product

    # Gate per-product so a product switch always triggers a fresh download.
    sentinel_name = f"mrms_{product}"
    if not force and is_cache_fresh(sentinel_name, _FRESH_WINDOW_SEC):
        print(f"[mrms_worker] {product} cache fresh — skipping run")
        return

    try:
        from mrms.mrms_nodd_utils import get_latest_mrms_file
    except Exception as exc:
        print(f"[mrms_worker] Import error: {exc}")
        return

    try:
        fetched = _fetch_latest_product_grib(product, get_latest_mrms_file)
        if fetched is None:
            print(f"[mrms_worker] No files found for {product}")
            return

        dest, file_dt = fetched
        product_cache_dir = os.path.join(_MRMS_CACHE, product)

        print(
            f"[mrms_worker] {product} cached at {file_dt.strftime('%Y-%m-%d %H:%M UTC')}"
        )
        mark_run_complete(sentinel_name)

        # Pre-render the default CONUS PNG so the first API request is a cache
        # hit (~50ms) rather than triggering a 5-10s blocking render.
        _prewarm_conus_png(product, dest, product_cache_dir, file_dt=file_dt)

        # Keep selected high-traffic products hot to reduce first-switch delay.
        _run_prewarm_product_set(
            skip_product=product, get_latest_mrms_file=get_latest_mrms_file
        )
    except Exception as exc:
        print(f"[mrms_worker] Error fetching {product}: {exc}")


# CONUS bounds must match the defaults in get_data_mrms() exactly so the
# bounds hash aligns and the API finds the pre-rendered PNG on first request.
_CONUS_EXTENT = [-130.0, -60.0, 21.0, 52.0]  # [west, east, south, north]


def _prewarm_conus_png(
    product: str,
    grib_path: str,
    product_cache_dir: str,
    file_dt=None,
) -> None:
    """Render the default CONUS PNG immediately after a fresh GRIB2 download.

    Bounds are kept in sync with the defaults of get_data_mrms() so that the
    MD5 bounds-hash matches and the API returns the pre-rendered file instantly.
    Also writes the rendered PNG into the shared overlay cache so the frame is
    discoverable via /api/overlay/latest?family=mrms.
    """
    import hashlib
    import time as _t

    south, west, north, east = 21.0, -130.0, 52.0, -60.0
    bounds_key = hashlib.md5(
        f"{product}_{south:.2f}_{west:.2f}_{north:.2f}_{east:.2f}".encode()
    ).hexdigest()[:10]
    png_path = os.path.join(product_cache_dir, f"overlay_{bounds_key}.png")

    try:
        t0 = _t.time()
        _render_mrms_png_standalone(grib_path, product, _CONUS_EXTENT, png_path)
        print(
            f"[mrms_worker] Pre-warmed CONUS PNG for {product} in {_t.time() - t0:.1f}s"
        )
    except Exception as exc:
        print(f"[mrms_worker] Pre-warm failed for {product} (non-fatal): {exc}")
        return

    if file_dt is not None:
        try:
            _write_mrms_overlay_cache(product, png_path, file_dt)
        except Exception as exc:
            print(
                f"[mrms_worker] Overlay cache write failed for {product} (non-fatal): {exc}"
            )


def _write_mrms_overlay_cache(
    product: str,
    png_path: str,
    file_dt,
    *,
    keep_n: int | None = 180,
) -> None:
    """Copy the pre-rendered MRMS PNG into the shared overlay cache structure.

    This makes the frame discoverable via /api/overlay/latest?family=mrms so
    the frontend can use the same overlay contract as RTMA.

    ``keep_n`` controls retention pruning after the write.  Pass ``None`` to
    skip pruning (useful when writing many frames in a batch — caller prunes
    once at the end).
    """
    from cache.overlay_cache_utils import (
        flat_overlay_image_path,
        flat_overlay_prune_frames,
        flat_overlay_read_processed_keys,
        flat_overlay_update_index,
        flat_overlay_write_processed_keys,
        frame_key_from_datetime,
    )
    from config.mrms_config import MRMS_PRODUCTS
    from mrms.legend_utils import build_mrms_legend

    prod_info = MRMS_PRODUCTS.get(product, {})
    path_parts = ("CONUS", "default", product)

    dt_utc = (
        file_dt if file_dt.tzinfo is not None else file_dt.replace(tzinfo=timezone.utc)
    )
    frame_key = frame_key_from_datetime(dt_utc)
    source_key = f"mrms:{product}:{frame_key}"

    # Dedup: skip if this frame has already been processed.
    processed_keys = flat_overlay_read_processed_keys(_CACHE_ROOT, "mrms", path_parts)
    if source_key in processed_keys:
        img_path = flat_overlay_image_path(_CACHE_ROOT, "mrms", path_parts, frame_key)
        if os.path.exists(img_path) and os.path.getsize(img_path) > 0:
            return

    # Read actual bounds from the sidecar written by _render_mrms_png_standalone.
    bounds_sidecar = png_path.replace(".png", "_bounds.json")
    try:
        with open(bounds_sidecar, "r") as fh:
            bounds = json.load(fh)  # [west, east, south, north]
    except (OSError, json.JSONDecodeError):
        bounds = [-130.0, -60.0, 21.0, 52.0]

    # Read legend from the meta sidecar.
    meta_sidecar = png_path.replace(".png", "_meta.json")
    try:
        with open(meta_sidecar, "r") as fh:
            render_meta = json.load(fh)
        legend = render_meta.get("legend") or build_mrms_legend(product)
    except (OSError, json.JSONDecodeError):
        legend = build_mrms_legend(product)

    # Copy PNG into the flat overlay cache directory.
    flat_img = flat_overlay_image_path(_CACHE_ROOT, "mrms", path_parts, frame_key)
    os.makedirs(os.path.dirname(flat_img), exist_ok=True)
    shutil.copy2(png_path, flat_img)

    flat_overlay_update_index(
        _CACHE_ROOT,
        "mrms",
        path_parts,
        frame_key,
        bounds=bounds,
        full_name=prod_info.get("full_name", product),
        units=prod_info.get("units", ""),
        legend=legend,
        vmin=prod_info.get("vmin"),
        vmax=prod_info.get("vmax"),
        timestamp=dt_utc.isoformat(),
    )

    processed_keys.add(source_key)
    flat_overlay_write_processed_keys(
        _CACHE_ROOT,
        "mrms",
        path_parts,
        processed_keys,
        keep_n if keep_n is not None else 180,
    )

    # Prune old frames unless caller requested deferred pruning (batch writes).
    if keep_n is not None:
        flat_overlay_prune_frames(_CACHE_ROOT, "mrms", path_parts, keep_n)

    print(f"[mrms_worker] Overlay cache updated: {product} @ {frame_key}")


def _render_mrms_png_standalone(
    grib_path: str,
    product: str,
    crop_extent: list,
    out_path: str,
) -> None:
    """Standalone MRMS PNG renderer — mirrors main._render_mrms_png without
    importing FastAPI/main so it is safe to call from the worker process."""
    import json
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.colors as mcolors

    from mrms.legend_utils import build_mrms_overlay_meta, mask_mrms_data
    from mrms.mrms_utils import read_mrms_grib2
    from config.mrms_config import MRMS_PRODUCTS, MRMS_COLORMAPS

    prod_info = MRMS_PRODUCTS[product]
    cmap_key = prod_info.get("colormap", "precip_rate")
    vmin = prod_info.get("vmin", 0)
    vmax = prod_info.get("vmax", 100)

    west, east, south, north = crop_extent

    data, meta = read_mrms_grib2(grib_path, product, crop_extent=crop_extent)

    data = mask_mrms_data(data, prod_info)

    lat = meta.get("latitude")
    lon = meta.get("longitude")
    if lat is None or lon is None:
        raise ValueError("GRIB2 read did not return lat/lon metadata")

    import numpy as _np_mrms

    _lat = _np_mrms.asarray(lat)
    _lon = _np_mrms.asarray(lon)

    cmap_obj = MRMS_COLORMAPS.get(cmap_key)
    if isinstance(cmap_obj, tuple):
        cmap = cmap_obj[0]
        norm = (
            cmap_obj[1]
            if len(cmap_obj) > 1
            else mcolors.Normalize(vmin=vmin, vmax=vmax)
        )
    elif cmap_obj is not None:
        cmap = cmap_obj
        norm = mcolors.Normalize(vmin=vmin, vmax=vmax)
    else:
        cmap = plt.get_cmap("viridis")
        norm = mcolors.Normalize(vmin=vmin, vmax=vmax)

    from mrms.mrms_utils import warp_array_to_mercator

    data, actual_bounds = warp_array_to_mercator(data, _lat, _lon)

    h, w = data.shape
    dpi = 100
    fig, ax = plt.subplots(1, 1, figsize=(w / dpi, h / dpi), dpi=dpi)
    ax.set_position([0, 0, 1, 1])
    ax.set_axis_off()
    ax.imshow(
        data,
        origin="upper",
        cmap=cmap,
        norm=norm,
        aspect="auto",
        interpolation="nearest",
    )
    fig.patch.set_alpha(0)
    ax.patch.set_alpha(0)
    fig.savefig(out_path, dpi=dpi, bbox_inches=None, transparent=True, format="png")
    plt.close(fig)

    sidecar = out_path.replace(".png", "_bounds.json")
    with open(sidecar, "w") as f:
        json.dump(actual_bounds, f)

    meta_sidecar = out_path.replace(".png", "_meta.json")
    with open(meta_sidecar, "w") as f:
        json.dump(build_mrms_overlay_meta(product, data), f)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run the MRMS worker once.")
    parser.add_argument(
        "--product",
        default=None,
        help="Override the active MRMS product (e.g. PrecipRate).",
    )
    parser.add_argument("--force", action="store_true", help="Bypass freshness gate.")
    parser.add_argument(
        "--log-to-file",
        action="store_true",
        help="Redirect stdout/stderr to logs/scheduled/mrms.log (for headless task runs).",
    )
    args = parser.parse_args()
    if args.log_to_file:
        from workers._freshness import redirect_stdio_to_log

        redirect_stdio_to_log("mrms")
    if args.product:
        set_active_product(args.product)
    run_mrms_worker(force=args.force)
