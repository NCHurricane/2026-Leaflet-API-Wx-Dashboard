"""RTMA overlay rendering and publication contracts shared by API and workers."""

from __future__ import annotations

import logging
import os

from app_core.overlay_cache import (
    flat_overlay_image_path,
    flat_overlay_prune_frames,
    flat_overlay_read_processed_keys,
    frame_key_from_datetime,
)
from config.geo_config import STATE_BOUNDS
from rtma.rtma_utils import _render_rtma_png_standalone, ensure_rtma_grib

_LOGGER = logging.getLogger(__name__)


def render_overlay_for_source(
    cache_root: str,
    source,
    region: str,
    stream: str,
    product: str,
    keep_n: int = 30,
    lat_1d=None,
    lon_1d=None,
) -> dict | None:
    """Render one RTMA source into the shared flat overlay cache."""
    path_parts = (region.upper(), stream, product)
    frame_key = frame_key_from_datetime(source.valid_time)
    processed_keys = flat_overlay_read_processed_keys(cache_root, "rtma", path_parts)
    if source.data_key in processed_keys:
        image_path = flat_overlay_image_path(
            cache_root, "rtma", path_parts, frame_key
        )
        if os.path.exists(image_path) and os.path.getsize(image_path) > 0:
            return None

    crop_extent = [
        float(value) for value in STATE_BOUNDS.get(region, [-125, -70, 21, 52])
    ]
    try:
        image_path = flat_overlay_image_path(
            cache_root, "rtma", path_parts, frame_key
        )
        grib_path = ensure_rtma_grib(cache_root, source)
        _out_path, actual_bounds, render_meta = _render_rtma_png_standalone(
            grib_path,
            product,
            crop_extent,
            image_path,
            cache_root=cache_root,
            source=source,
            region=region,
            stream=stream,
            lat_1d=lat_1d,
            lon_1d=lon_1d,
        )
    except Exception as exc:
        _LOGGER.warning(
            "RTMA overlay render failed for %s/%s/%s/%s (%s)",
            region,
            stream,
            product,
            frame_key,
            type(exc).__name__,
        )
        return None

    try:
        flat_overlay_prune_frames(cache_root, "rtma", path_parts, keep_n)
        _LOGGER.info(
            "RTMA overlay published for %s/%s/%s/%s",
            region,
            stream,
            product,
            frame_key,
        )
        return {
            "path_parts": path_parts,
            "frame_key": frame_key,
            "data_key": source.data_key,
            "bounds": actual_bounds,
            "full_name": render_meta.get("full_name", ""),
            "units": render_meta.get("units", ""),
            "legend": render_meta.get("legend"),
            "vmin": render_meta.get("vmin"),
            "vmax": render_meta.get("vmax"),
            "timestamp": render_meta.get("timestamp")
            or source.valid_time.isoformat(),
        }
    except Exception as exc:
        _LOGGER.warning(
            "RTMA overlay prune failed for %s/%s/%s/%s (%s)",
            region,
            stream,
            product,
            frame_key,
            type(exc).__name__,
        )
        return None
