"""Native-resolution MRMS tile-source and PNG tile helpers.

The operational overlay PNG remains authoritative at low zoom and as a
fallback. A versioned, tiled scalar GeoTIFF is built once per selected frame;
individual Web Mercator PNG tiles then read only the required source blocks.
"""

from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import numpy as np

from app_core.paths import CACHE_ROOT
from cache.overlay_cache_utils import datetime_from_frame_key, frame_key_from_datetime
from config.mrms_config import (
    MRMS_PRODUCTS,
    MRMS_TILE_MIN_ZOOM,
    MRMS_TILE_RENDER_VERSION,
    MRMS_TILE_SIZE,
    MRMS_TILES_ENABLED,
)

_NODATA = np.float32(1e38)
_WEB_MERCATOR_LIMIT = 20037508.342789244
_CONUS_EXTENT = [-130.0, -60.0, 21.0, 52.0]
_SOURCE_LOCKS = tuple(threading.RLock() for _ in range(16))
_TILE_LOCKS = tuple(threading.Lock() for _ in range(64))
_LOCAL_TIMESTAMP_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})\.grib2(?:\.gz)?$"
)
_NODD_TIMESTAMP_RE = re.compile(r"_(\d{8}-\d{6})\.grib2(?:\.gz)?$")


def _lock_for(path: str | Path, locks):
    return locks[hash(os.path.abspath(str(path))) % len(locks)]


def _valid_file(path: str | Path) -> bool:
    try:
        return os.path.isfile(path) and os.path.getsize(path) > 0
    except OSError:
        return False


def max_native_zoom_for_product(product: str) -> int:
    """Return the closest Web Mercator zoom to the product's native grid."""
    product_key = str(product or "")
    if product_key.startswith(("RotationTrack_", "AzShear_")):
        return 8  # 0.005-degree MRMS grids
    return 7  # standard 0.01-degree MRMS grids


def tile_source_path(
    product: str,
    frame_key: str,
    *,
    cache_root: str = CACHE_ROOT,
) -> str:
    return os.path.join(
        cache_root,
        "mrms",
        "tiles",
        MRMS_TILE_RENDER_VERSION,
        product,
        frame_key,
        "source.tif",
    )


def tile_image_path(
    product: str,
    frame_key: str,
    z: int,
    x: int,
    y: int,
    *,
    cache_root: str = CACHE_ROOT,
) -> str:
    return os.path.join(
        cache_root,
        "mrms",
        "tiles",
        MRMS_TILE_RENDER_VERSION,
        product,
        frame_key,
        str(z),
        str(x),
        f"{y}.png",
    )


def tile_metadata(
    product: str,
    frame_key: str,
    *,
    cache_root: str = CACHE_ROOT,
) -> dict | None:
    if not MRMS_TILES_ENABLED or product not in MRMS_PRODUCTS or not frame_key:
        return None
    encoded_product = quote(product, safe="")
    source_path = tile_source_path(product, frame_key, cache_root=cache_root)
    return {
        "version": MRMS_TILE_RENDER_VERSION,
        "url_template": (
            f"/api/mrms/tiles/{MRMS_TILE_RENDER_VERSION}/{encoded_product}/"
            f"{frame_key}/{{z}}/{{x}}/{{y}}.png"
        ),
        "prepare_url": (
            "/api/mrms/tiles/prepare?"
            f"product={encoded_product}&frame_key={frame_key}"
        ),
        "min_zoom": MRMS_TILE_MIN_ZOOM,
        "max_native_zoom": max_native_zoom_for_product(product),
        "ready": _valid_file(source_path),
    }


def enrich_frame_with_tiles(
    frame: dict,
    product: str,
    *,
    cache_root: str = CACHE_ROOT,
) -> dict:
    payload = dict(frame or {})
    metadata = tile_metadata(
        product,
        str(payload.get("frame_key") or ""),
        cache_root=cache_root,
    )
    if metadata is None:
        return payload
    render = dict(payload.get("render") or {})
    render["tile"] = metadata
    payload["render"] = render
    payload["tile"] = metadata
    return payload


def _available_local_frame_keys(
    product: str,
    *,
    cache_root: str = CACHE_ROOT,
) -> set[str]:
    """Return frame keys backed by either a scalar source or retained GRIB."""
    available: set[str] = set()
    product_dir = Path(cache_root) / "mrms" / product
    try:
        entries = list(product_dir.iterdir())
    except OSError:
        entries = []
    for entry in entries:
        if not entry.is_file() or not _valid_file(entry):
            continue
        match = _LOCAL_TIMESTAMP_RE.match(entry.name)
        timestamp_format = "%Y-%m-%d_%H-%M-%S"
        if match is None:
            match = _NODD_TIMESTAMP_RE.search(entry.name)
            timestamp_format = "%Y%m%d-%H%M%S"
        if match is None:
            continue
        try:
            frame_dt = datetime.strptime(match.group(1), timestamp_format).replace(
                tzinfo=timezone.utc
            )
            available.add(frame_key_from_datetime(frame_dt))
        except ValueError:
            continue

    state_path = product_dir / "latest_source.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        source_timestamp = str(state.get("source_timestamp") or "")
        if source_timestamp:
            available.add(
                frame_key_from_datetime(
                    datetime.fromisoformat(source_timestamp.replace("Z", "+00:00"))
                )
            )
    except (OSError, ValueError, TypeError):
        pass

    tile_root = (
        Path(cache_root)
        / "mrms"
        / "tiles"
        / MRMS_TILE_RENDER_VERSION
        / product
    )
    try:
        tile_frames = list(tile_root.iterdir())
    except OSError:
        tile_frames = []
    for frame_dir in tile_frames:
        if frame_dir.is_dir() and _valid_file(frame_dir / "source.tif"):
            try:
                datetime_from_frame_key(frame_dir.name)
                available.add(frame_dir.name)
            except ValueError:
                continue
    return available


def filter_unpreparable_duplicate_frames(
    frames: list[dict],
    product: str,
    *,
    cache_root: str = CACHE_ROOT,
    duplicate_tolerance_seconds: int = 90,
) -> list[dict]:
    """Hide mtime-derived duplicates while retaining standalone PNG fallbacks."""
    if not MRMS_TILES_ENABLED or len(frames) < 2:
        return list(frames)
    available = _available_local_frame_keys(product, cache_root=cache_root)
    available_times = []
    for key in available:
        try:
            available_times.append(datetime_from_frame_key(key).timestamp())
        except ValueError:
            continue
    if not available_times:
        return list(frames)

    filtered = []
    tolerance = max(0, int(duplicate_tolerance_seconds))
    for frame in frames:
        frame_key = str(frame.get("frame_key") or "")
        if frame_key in available:
            filtered.append(frame)
            continue
        try:
            frame_time = datetime_from_frame_key(frame_key).timestamp()
        except ValueError:
            filtered.append(frame)
            continue
        is_duplicate = any(
            abs(frame_time - available_time) <= tolerance
            for available_time in available_times
        )
        if not is_duplicate:
            filtered.append(frame)
    return filtered


def write_tile_source(
    data,
    lat_1d,
    lon_1d,
    product: str,
    frame_key: str,
    *,
    cache_root: str = CACHE_ROOT,
) -> str:
    """Atomically write a block-compressed native scalar raster for one frame."""
    if not MRMS_TILES_ENABLED:
        raise RuntimeError("MRMS native tiles are disabled")
    if product not in MRMS_PRODUCTS:
        raise ValueError(f"Unknown MRMS product '{product}'")
    datetime_from_frame_key(frame_key)

    target = tile_source_path(product, frame_key, cache_root=cache_root)
    with _lock_for(target, _SOURCE_LOCKS):
        if _valid_file(target):
            return target

        import rasterio
        from rasterio.transform import from_bounds

        arr = np.ma.asarray(data)
        lat = np.asarray(lat_1d, dtype=np.float64)
        lon = np.asarray(lon_1d, dtype=np.float64)
        lon = np.where(lon > 180.0, lon - 360.0, lon)
        if arr.ndim != 2 or lat.ndim != 1 or lon.ndim != 1:
            raise ValueError("MRMS tile source requires a 2-D grid and 1-D coordinates")
        if arr.shape != (lat.size, lon.size):
            raise ValueError("MRMS tile source grid does not match its coordinates")

        if lat[0] < lat[-1]:
            arr = arr[::-1, :]
            lat = lat[::-1]
        if lon[0] > lon[-1]:
            arr = arr[:, ::-1]
            lon = lon[::-1]

        dlat = abs(float(lat[0] - lat[1])) if lat.size > 1 else 0.01
        dlon = abs(float(lon[1] - lon[0])) if lon.size > 1 else 0.01
        transform = from_bounds(
            float(lon.min()) - 0.5 * dlon,
            float(lat.min()) - 0.5 * dlat,
            float(lon.max()) + 0.5 * dlon,
            float(lat.max()) + 0.5 * dlat,
            arr.shape[1],
            arr.shape[0],
        )

        os.makedirs(os.path.dirname(target), exist_ok=True)
        temp_path = f"{target}.{os.getpid()}.{threading.get_ident()}.tmp"
        try:
            with rasterio.open(
                temp_path,
                "w",
                driver="GTiff",
                height=arr.shape[0],
                width=arr.shape[1],
                count=1,
                dtype="float32",
                crs="EPSG:4326",
                transform=transform,
                nodata=float(_NODATA),
                tiled=True,
                blockxsize=MRMS_TILE_SIZE,
                blockysize=MRMS_TILE_SIZE,
                compress="deflate",
                predictor=3,
                BIGTIFF="IF_SAFER",
                SPARSE_OK="TRUE",
            ) as dst:
                dst.update_tags(
                    product=product,
                    frame_key=frame_key,
                    render_version=MRMS_TILE_RENDER_VERSION,
                )
                for _, window in dst.block_windows(1):
                    row_start = int(window.row_off)
                    row_end = row_start + int(window.height)
                    col_start = int(window.col_off)
                    col_end = col_start + int(window.width)
                    block = np.ma.asarray(
                        arr[row_start:row_end, col_start:col_end], dtype=np.float32
                    )
                    filled = np.ma.filled(block, _NODATA)
                    filled = np.where(np.isfinite(filled), filled, _NODATA).astype(
                        np.float32, copy=False
                    )
                    dst.write(filled, 1, window=window)
            os.replace(temp_path, target)
        finally:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except OSError:
                pass
        return target


def _resolve_local_grib(product: str, frame_key: str, cache_root: str) -> str:
    product_dir = Path(cache_root) / "mrms" / product
    if not product_dir.is_dir():
        raise FileNotFoundError(f"No local MRMS cache exists for '{product}'")

    frame_dt = datetime_from_frame_key(frame_key)
    local_stamp = frame_dt.strftime("%Y-%m-%d_%H-%M-%S")
    source_stamp = frame_dt.strftime("%Y%m%d-%H%M%S")
    candidates = [
        product_dir / f"{local_stamp}.grib2",
        product_dir / f"{local_stamp}.grib2.gz",
    ]
    candidates.extend(sorted(product_dir.glob(f"*_{source_stamp}.grib2")))
    candidates.extend(sorted(product_dir.glob(f"*_{source_stamp}.grib2.gz")))
    for candidate in candidates:
        if _valid_file(candidate):
            return str(candidate)

    state_path = product_dir / "latest_source.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        source_timestamp = str(state.get("source_timestamp") or "")
        if source_timestamp.startswith(frame_dt.strftime("%Y-%m-%dT%H:%M:%S")):
            for name in ("conus.grib2", "conus.grib2.gz"):
                candidate = product_dir / name
                if _valid_file(candidate):
                    return str(candidate)
    except (OSError, ValueError):
        pass
    raise FileNotFoundError(
        f"The cached GRIB for {product} frame {frame_key} is no longer available"
    )


def ensure_tile_source(
    product: str,
    frame_key: str,
    *,
    cache_root: str = CACHE_ROOT,
) -> str:
    """Build a missing tile source once while preserving global render budgets."""
    if not MRMS_TILES_ENABLED:
        raise RuntimeError("MRMS native tiles are disabled")
    if product not in MRMS_PRODUCTS:
        raise ValueError(f"Unknown MRMS product '{product}'")
    datetime_from_frame_key(frame_key)
    target = tile_source_path(product, frame_key, cache_root=cache_root)
    with _lock_for(target, _SOURCE_LOCKS):
        if _valid_file(target):
            return target

        from app_core.render_budget import heavy_render_slot
        from mrms.legend_utils import mask_mrms_data
        from mrms.mrms_utils import read_mrms_grib2

        grib_path = _resolve_local_grib(product, frame_key, cache_root)
        with heavy_render_slot():
            data, meta = read_mrms_grib2(
                grib_path,
                product,
                crop_extent=_CONUS_EXTENT,
            )
            data = mask_mrms_data(data, MRMS_PRODUCTS[product])
            lat = meta.get("latitude")
            lon = meta.get("longitude")
            if lat is None or lon is None:
                raise ValueError("GRIB2 read did not return lat/lon metadata")
            return write_tile_source(
                data,
                lat,
                lon,
                product,
                frame_key,
                cache_root=cache_root,
            )


def prepare_tile_source(
    product: str,
    frame_key: str,
    *,
    cache_root: str = CACHE_ROOT,
) -> dict:
    ensure_tile_source(product, frame_key, cache_root=cache_root)
    return tile_metadata(product, frame_key, cache_root=cache_root) or {}


def _tile_bounds_mercator(z: int, x: int, y: int):
    count = 2**z
    span = (2.0 * _WEB_MERCATOR_LIMIT) / count
    left = -_WEB_MERCATOR_LIMIT + x * span
    right = left + span
    top = _WEB_MERCATOR_LIMIT - y * span
    bottom = top - span
    return left, bottom, right, top


def render_tile(
    product: str,
    frame_key: str,
    z: int,
    x: int,
    y: int,
    *,
    cache_root: str = CACHE_ROOT,
) -> str:
    """Render and atomically cache one native-resolution Web Mercator tile."""
    if not MRMS_TILES_ENABLED:
        raise RuntimeError("MRMS native tiles are disabled")
    if product not in MRMS_PRODUCTS:
        raise ValueError(f"Unknown MRMS product '{product}'")
    datetime_from_frame_key(frame_key)
    max_zoom = max_native_zoom_for_product(product)
    if z < MRMS_TILE_MIN_ZOOM or z > max_zoom:
        raise ValueError(
            f"MRMS tile zoom {z} is outside the supported {MRMS_TILE_MIN_ZOOM}-{max_zoom} range"
        )
    count = 2**z
    if x < 0 or y < 0 or x >= count or y >= count:
        raise ValueError("MRMS tile coordinates are outside the selected zoom")

    source_path = tile_source_path(product, frame_key, cache_root=cache_root)
    if not _valid_file(source_path):
        raise FileNotFoundError(
            f"MRMS native tile source is not ready for {product} {frame_key}"
        )
    target = tile_image_path(product, frame_key, z, x, y, cache_root=cache_root)
    with _lock_for(target, _TILE_LOCKS):
        if _valid_file(target):
            return target

        import rasterio
        from PIL import Image
        from rasterio.transform import from_bounds
        from rasterio.warp import Resampling, reproject

        from mrms.legend_utils import colorize_masked_mrms_data

        tile_bounds = _tile_bounds_mercator(z, x, y)
        destination = np.full(
            (MRMS_TILE_SIZE, MRMS_TILE_SIZE), _NODATA, dtype=np.float32
        )
        with rasterio.open(source_path) as src:
            reproject(
                source=rasterio.band(src, 1),
                destination=destination,
                src_transform=src.transform,
                src_crs=src.crs,
                src_nodata=src.nodata,
                dst_transform=from_bounds(
                    *tile_bounds, MRMS_TILE_SIZE, MRMS_TILE_SIZE
                ),
                dst_crs="EPSG:3857",
                dst_nodata=float(_NODATA),
                resampling=Resampling.nearest,
            )
        masked = np.where(destination >= _NODATA * 0.9, np.nan, destination)
        rgba = colorize_masked_mrms_data(product, masked)

        os.makedirs(os.path.dirname(target), exist_ok=True)
        temp_path = f"{target}.{os.getpid()}.{threading.get_ident()}.tmp"
        try:
            Image.fromarray(rgba, mode="RGBA").save(
                temp_path,
                format="PNG",
                optimize=False,
                compress_level=1,
            )
            os.replace(temp_path, target)
        finally:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except OSError:
                pass
        return target


def resolve_tile(
    render_version: str,
    product: str,
    frame_key: str,
    z: int,
    x: int,
    y: int,
    *,
    cache_root: str = CACHE_ROOT,
) -> str:
    if render_version != MRMS_TILE_RENDER_VERSION:
        raise ValueError(f"Unknown MRMS tile render version '{render_version}'")
    return render_tile(
        product,
        frame_key,
        z,
        x,
        y,
        cache_root=cache_root,
    )
