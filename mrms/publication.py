"""MRMS render and overlay-publication contracts shared by API and workers."""

from __future__ import annotations

import json
import logging
import os
import shutil
from datetime import timezone

from app_core.atomic_io import atomic_output_path
from app_core.paths import CACHE_ROOT

def write_mrms_overlay_cache(
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
    from app_core.overlay_cache import (
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
    processed_keys = flat_overlay_read_processed_keys(CACHE_ROOT, "mrms", path_parts)
    if source_key in processed_keys:
        img_path = flat_overlay_image_path(CACHE_ROOT, "mrms", path_parts, frame_key)
        if os.path.exists(img_path) and os.path.getsize(img_path) > 0:
            return

    # Read actual bounds from the sidecar written by the standalone renderer.
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
    flat_img = flat_overlay_image_path(CACHE_ROOT, "mrms", path_parts, frame_key)
    os.makedirs(os.path.dirname(flat_img), exist_ok=True)
    with atomic_output_path(flat_img) as temporary:
        shutil.copy2(png_path, temporary)

    flat_overlay_update_index(
        CACHE_ROOT,
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
        CACHE_ROOT,
        "mrms",
        path_parts,
        processed_keys,
        keep_n if keep_n is not None else 180,
    )

    # Prune old frames unless caller requested deferred pruning (batch writes).
    if keep_n is not None:
        flat_overlay_prune_frames(CACHE_ROOT, "mrms", path_parts, keep_n)

    logging.getLogger(__name__).info(f"[mrms_worker] Overlay cache updated: {product} @ {frame_key}")

def _render_mrms_png_standalone_unbounded(
    grib_path: str,
    product: str,
    crop_extent: list,
    out_path: str,
    *,
    tile_frame_key: str | None = None,
) -> None:
    """Standalone MRMS PNG renderer using PIL for ~3-5x faster rendering."""
    import json
    from PIL import Image
    import numpy as np

    from mrms.legend_utils import (
        build_mrms_overlay_meta,
        colorize_masked_mrms_data,
        mask_mrms_data,
    )
    from mrms.mrms_utils import read_mrms_grib2, warp_array_to_mercator
    from config.mrms_config import (
        MRMS_PRODUCTS,
        MRMS_TILES_ENABLED,
        MRMS_WARP_MAX_DIM,
    )

    prod_info = MRMS_PRODUCTS[product]
    data, meta = read_mrms_grib2(grib_path, product, crop_extent=crop_extent)
    data = mask_mrms_data(data, prod_info)

    lat = meta.get("latitude")
    lon = meta.get("longitude")
    if lat is None or lon is None:
        raise ValueError("GRIB2 read did not return lat/lon metadata")

    if tile_frame_key and MRMS_TILES_ENABLED:
        try:
            from mrms.mrms_tiles import write_tile_source

            write_tile_source(data, lat, lon, product, tile_frame_key)
        except Exception as exc:
            logging.getLogger(__name__).warning(
                f"[mrms_worker] Native tile source failed for "
                f"{product} {tile_frame_key} (non-fatal): {type(exc).__name__}"
            )

    data, actual_bounds = warp_array_to_mercator(
        data, np.asarray(lat), np.asarray(lon), max_dim=MRMS_WARP_MAX_DIM
    )
    rgba = colorize_masked_mrms_data(product, data)

    # Create PIL image from RGBA array
    img = Image.fromarray(rgba, mode="RGBA")
    img.save(out_path, format="PNG", optimize=False, compress_level=1)

    # Write sidecars
    sidecar = out_path.replace(".png", "_bounds.json")
    with open(sidecar, "w") as f:
        json.dump(actual_bounds, f)

    render_meta = build_mrms_overlay_meta(product, data)
    if tile_frame_key:
        from app_core.overlay_cache import datetime_from_frame_key

        render_meta["data_timestamp"] = datetime_from_frame_key(
            tile_frame_key
        ).isoformat()
    meta_sidecar = out_path.replace(".png", "_meta.json")
    with open(meta_sidecar, "w") as f:
        json.dump(render_meta, f)

def render_mrms_png_standalone(
    grib_path: str,
    product: str,
    crop_extent: list,
    out_path: str,
    *,
    tile_frame_key: str | None = None,
) -> None:
    from app_core.render_budget import heavy_render_slot

    with heavy_render_slot():
        _render_mrms_png_standalone_unbounded(
            grib_path,
            product,
            crop_extent,
            out_path,
            tile_frame_key=tile_frame_key,
        )
