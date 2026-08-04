"""MRMS product state, cache, and rendering helpers."""

from datetime import datetime, timezone
import json
import os

from fastapi import HTTPException

from app_core.paths import CACHE_ROOT
from app_core.refresh_coordinator import Submission, get_refresh_coordinator

_active_mrms_product: str = "Refl_BaseQC"
_MRMS_REFRESH_INTERVAL_SECONDS = 2 * 60


def _mrms_refresh_key(product: str) -> tuple[str, ...]:
    return ("mrms", "latest", product)


def _refresh_mrms_product(product: str) -> dict:
    from workers.mrms_worker import run_mrms_worker

    return run_mrms_worker(force=True, product=product)


def _start_mrms_product_refresh(product: str) -> Submission:
    from config.mrms_config import MRMS_PRODUCTS

    if product not in MRMS_PRODUCTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown MRMS product '{product}'.",
        )
    coordinator = get_refresh_coordinator()
    key = _mrms_refresh_key(product)
    coordinator.record_presence(
        key=key,
        provider="noaa-mrms",
    )
    return coordinator.submit(
        key=key,
        provider="noaa-mrms",
        function=lambda: _refresh_mrms_product(product),
        min_success_interval_seconds=_MRMS_REFRESH_INTERVAL_SECONDS,
    )


def _load_mrms_render_meta(meta_sidecar: str) -> dict:
    if not os.path.exists(meta_sidecar):
        return {}
    with open(meta_sidecar, "r") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def _write_mrms_render_meta(meta_sidecar: str, render_meta: dict) -> None:
    with open(meta_sidecar, "w") as f:
        json.dump(render_meta, f)


def _load_latest_source_timestamp(product_cache_dir: str) -> str | None:
    """Read the canonical NOAA object timestamp for the current cached GRIB."""
    state_path = os.path.join(product_cache_dir, "latest_source.json")
    try:
        with open(state_path, "r", encoding="utf-8") as handle:
            state = json.load(handle)
    except (OSError, ValueError):
        return None
    return _normalize_mrms_data_timestamp(state.get("source_timestamp"))


def _normalize_mrms_data_timestamp(raw_time) -> str | None:
    """Convert GRIB time metadata to an ISO-8601 UTC string."""
    if raw_time is None:
        return None

    value = raw_time
    if hasattr(value, "tolist"):
        try:
            value = value.tolist()
        except Exception:
            pass
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    if value is None:
        return None

    dt = None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if not text or text.lower() == "nat":
            return None
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except Exception:
            dt = None

    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _build_mrms_meta_from_grib(grib_path: str, product: str, crop_extent: list) -> dict:
    from mrms.legend_utils import build_mrms_overlay_meta
    from mrms.mrms_utils import read_mrms_grib2

    data, meta = read_mrms_grib2(grib_path, product, crop_extent=crop_extent)
    render_meta = build_mrms_overlay_meta(product, data)
    data_ts = _normalize_mrms_data_timestamp(meta.get("time"))
    if data_ts:
        render_meta["data_timestamp"] = data_ts
    return render_meta


def set_mrms_product(product: str) -> dict:
    """Switch the active MRMS product the worker will refresh."""
    global _active_mrms_product
    from config.mrms_config import MRMS_PRODUCTS

    if product not in MRMS_PRODUCTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown MRMS product '{product}'.",
        )
    _active_mrms_product = product
    try:
        from workers.mrms_worker import set_active_product

        set_active_product(product)
    except Exception:
        pass
    refresh = _start_mrms_product_refresh(product)
    return {
        "active_product": product,
        "refreshing": refresh.status in {"queued", "running"},
        "refresh_status": refresh.status,
        "retry_after_seconds": refresh.retry_after_seconds,
    }


def get_mrms_data(
    product: str = "PrecipRate",
    south: float = 21.0,
    west: float = -130.0,
    north: float = 52.0,
    east: float = -60.0,
) -> dict:
    global _active_mrms_product
    from config.mrms_config import MRMS_PRODUCTS

    if product not in MRMS_PRODUCTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown MRMS product '{product}'.",
        )

    refresh = _start_mrms_product_refresh(product)

    if product != _active_mrms_product:
        _active_mrms_product = product
        try:
            from workers.mrms_worker import set_active_product

            set_active_product(product)
        except Exception:
            pass

    product_cache_dir = os.path.join(CACHE_ROOT, "mrms", product)
    os.makedirs(product_cache_dir, exist_ok=True)
    grib_path = os.path.join(product_cache_dir, "conus.grib2.gz")

    if not os.path.exists(grib_path):
        try:
            from workers.mrms_worker import run_mrms_worker, set_active_product

            set_active_product(product)
            run_mrms_worker(force=True, product=product)
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail=f"MRMS data for '{product}' not yet available: {exc}",
            )

    if not os.path.exists(grib_path):
        raise HTTPException(
            status_code=503,
            detail=f"MRMS cache file missing after fetch attempt for '{product}'.",
        )

    mrms_stale_grib_seconds = 90 * 60
    grib_mtime = os.path.getmtime(grib_path)
    grib_age_seconds = datetime.now(timezone.utc).timestamp() - grib_mtime
    if grib_age_seconds > mrms_stale_grib_seconds:
        try:
            from workers.mrms_worker import run_mrms_worker, set_active_product

            set_active_product(product)
            run_mrms_worker(force=True, product=product)
        except Exception:
            pass

        if not os.path.exists(grib_path):
            raise HTTPException(
                status_code=503,
                detail=f"MRMS cache file missing after stale refresh attempt for '{product}'.",
            )
        grib_mtime = os.path.getmtime(grib_path)

    import hashlib

    bounds_key = hashlib.md5(
        f"{product}_{south:.2f}_{west:.2f}_{north:.2f}_{east:.2f}".encode()
    ).hexdigest()[:10]
    png_path = os.path.join(product_cache_dir, f"overlay_{bounds_key}.png")
    grib_mtime = os.path.getmtime(grib_path)
    png_stale = not os.path.exists(png_path) or os.path.getmtime(png_path) < grib_mtime

    meta_sidecar = png_path.replace(".png", "_meta.json")

    if png_stale:
        try:
            png_path, actual_bounds, render_meta = render_mrms_png(
                grib_path, product, [west, east, south, north], png_path
            )
        except Exception:
            stale_grib2 = grib_path[:-3] if grib_path.endswith(".gz") else None
            for stale_path in [
                grib_path,
                stale_grib2,
                png_path,
                png_path.replace(".png", "_bounds.json"),
                meta_sidecar,
            ]:
                if stale_path and os.path.exists(stale_path):
                    try:
                        os.remove(stale_path)
                    except OSError:
                        pass

            try:
                from workers.mrms_worker import run_mrms_worker, set_active_product

                set_active_product(product)
                run_mrms_worker(force=True, product=product)
            except Exception:
                pass

            try:
                png_path, actual_bounds, render_meta = render_mrms_png(
                    grib_path, product, [west, east, south, north], png_path
                )
            except Exception as retry_exc:
                raise HTTPException(
                    status_code=503,
                    detail=(
                        f"MRMS render error for '{product}' after refresh retry: {retry_exc}"
                    ),
                ) from retry_exc
    else:
        sidecar = png_path.replace(".png", "_bounds.json")
        if os.path.exists(sidecar):
            with open(sidecar, "r") as f:
                actual_bounds = json.load(f)
        else:
            actual_bounds = [west, east, south, north]
        render_meta = _load_mrms_render_meta(meta_sidecar)
        if not render_meta:
            try:
                render_meta = _build_mrms_meta_from_grib(
                    grib_path, product, [west, east, south, north]
                )
            except Exception:
                render_meta = {}
            _write_mrms_render_meta(meta_sidecar, render_meta)
        elif not render_meta.get("data_timestamp"):
            try:
                refreshed_meta = _build_mrms_meta_from_grib(
                    grib_path, product, [west, east, south, north]
                )
                if refreshed_meta.get("data_timestamp"):
                    render_meta["data_timestamp"] = refreshed_meta.get("data_timestamp")
                    _write_mrms_render_meta(meta_sidecar, render_meta)
            except Exception:
                pass

    rel = os.path.relpath(png_path, CACHE_ROOT).replace("\\", "/")
    image_url = f"/cache/{rel}"

    timestamp = (
        render_meta.get("data_timestamp")
        or _load_latest_source_timestamp(product_cache_dir)
        or datetime.fromtimestamp(grib_mtime, tz=timezone.utc).isoformat()
    )

    try:
        from workers.mrms_worker import _write_mrms_overlay_cache

        frame_dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if frame_dt.tzinfo is None:
            frame_dt = frame_dt.replace(tzinfo=timezone.utc)
        _write_mrms_overlay_cache(product, png_path, frame_dt)
    except Exception:
        pass

    prod_info = MRMS_PRODUCTS[product]
    return {
        "image_url": image_url,
        "bounds": actual_bounds,
        "product": product,
        "full_name": prod_info.get("full_name", product),
        "units": prod_info.get("units", ""),
        "colormap": prod_info.get("colormap", ""),
        "vmin": prod_info.get("vmin", 0),
        "vmax": prod_info.get("vmax", 100),
        "legend": render_meta.get("legend"),
        "timestamp": timestamp,
        "refreshing": refresh.status in {"queued", "running"},
        "refresh_status": refresh.status,
        "retry_after_seconds": refresh.retry_after_seconds,
    }


def _render_mrms_png_unbounded(
    grib_path: str,
    product: str,
    crop_extent: list,
    out_path: str,
) -> tuple:
    """
    Read MRMS GRIB2, crop to extent, apply colormap, save as transparent PNG.
    Returns (png_path, [west, east, south, north] actual bounds, render_meta).
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.colors as mcolors
    import matplotlib.pyplot as plt

    from config.mrms_config import MRMS_COLORMAPS, MRMS_PRODUCTS, MRMS_WARP_MAX_DIM
    from mrms.legend_utils import build_mrms_overlay_meta, mask_mrms_data
    from mrms.mrms_utils import read_mrms_grib2, warp_array_to_mercator
    import numpy as _np_mrms
    import numpy as _np_render
    from PIL import Image

    prod_info = MRMS_PRODUCTS[product]
    cmap_key = prod_info.get("colormap", "precip_rate")
    vmin = prod_info.get("vmin", 0)
    vmax = prod_info.get("vmax", 100)

    data, meta = read_mrms_grib2(grib_path, product, crop_extent=crop_extent)
    data = mask_mrms_data(data, prod_info)

    lat = meta.get("latitude")
    lon = meta.get("longitude")
    if lat is None or lon is None:
        raise ValueError("GRIB2 read did not return lat/lon metadata")

    lat_arr = _np_mrms.asarray(lat)
    lon_arr = _np_mrms.asarray(lon)

    cmap_obj = MRMS_COLORMAPS.get(cmap_key)
    if isinstance(cmap_obj, tuple):
        cmap, norm = (
            cmap_obj[0],
            cmap_obj[1]
            if len(cmap_obj) > 1
            else mcolors.Normalize(vmin=vmin, vmax=vmax),
        )
    elif cmap_obj is not None:
        cmap = cmap_obj
        norm = mcolors.Normalize(vmin=vmin, vmax=vmax)
    else:
        cmap = plt.get_cmap("viridis")
        norm = mcolors.Normalize(vmin=vmin, vmax=vmax)

    data = _np_render.ma.asarray(data)
    data, actual_bounds = warp_array_to_mercator(
        data, lat_arr, lon_arr, max_dim=MRMS_WARP_MAX_DIM
    )

    masked = _np_render.ma.getmaskarray(data)
    filled = _np_render.ma.filled(data, _np_render.nan)
    normalized = norm(filled)
    rgb = cmap(normalized)
    rgba = (rgb * 255).astype(_np_render.uint8)
    invalid = masked | _np_render.isnan(filled)
    if _np_render.any(invalid):
        rgba[invalid, 3] = 0
    Image.fromarray(rgba, mode="RGBA").save(
        out_path, format="PNG", optimize=False, compress_level=1
    )

    sidecar = out_path.replace(".png", "_bounds.json")
    with open(sidecar, "w") as f:
        json.dump(actual_bounds, f)

    render_meta = build_mrms_overlay_meta(product, data)
    data_ts = _normalize_mrms_data_timestamp(meta.get("time"))
    if data_ts:
        render_meta["data_timestamp"] = data_ts
    _write_mrms_render_meta(out_path.replace(".png", "_meta.json"), render_meta)

    return out_path, actual_bounds, render_meta


def render_mrms_png(
    grib_path: str,
    product: str,
    crop_extent: list,
    out_path: str,
) -> tuple:
    from app_core.render_budget import heavy_render_slot

    with heavy_render_slot():
        return _render_mrms_png_unbounded(
            grib_path,
            product,
            crop_extent,
            out_path,
        )
