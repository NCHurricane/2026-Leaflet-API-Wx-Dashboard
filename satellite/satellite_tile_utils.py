import json
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import cartopy.crs as ccrs
import matplotlib
import matplotlib.pyplot as plt
import xarray as xr

from config.satellite_config import ABI_CHANNELS, RGB_COMPOSITE_KEYS
from satellite import satellite_archive_utils
from satellite.satellite_utils import (
    _compute_image_extent,
    _get_cmi_dataarray,
    process_composite,
)

matplotlib.use("Agg")

_DEFAULT_PROVIDER = "aws"


def _normalize_provider(source: str) -> str:
    provider = str(source or _DEFAULT_PROVIDER).strip().lower()
    if provider == "auto":
        provider = _DEFAULT_PROVIDER
    if provider not in {"aws", "gcp"}:
        provider = _DEFAULT_PROVIDER
    return provider


def _provider_candidates(source: str) -> List[str]:
    requested = str(source or "auto").strip().lower()
    if requested == "auto":
        return ["aws", "gcp"]
    if requested in {"aws", "gcp"}:
        return [requested]
    return [_DEFAULT_PROVIDER]


def _normalize_recipe(channel_key: str) -> str:
    key = str(channel_key or "Channel13").strip()
    if key == "NaturalColor":
        return "TrueColor"
    return key


def _tile_bounds_lonlat(z: int, x: int, y: int) -> Tuple[float, float, float, float]:
    n = 2.0**z
    west = x / n * 360.0 - 180.0
    east = (x + 1) / n * 360.0 - 180.0

    def _lat_from_tile(tile_y: int) -> float:
        from math import atan, degrees, pi, sinh

        return degrees(atan(sinh(pi * (1 - 2 * tile_y / n))))

    north = _lat_from_tile(y)
    south = _lat_from_tile(y + 1)
    return west, south, east, north


def _frame_key(scan_time: datetime) -> str:
    return scan_time.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _frame_index_path(
    cache_root: str,
    sat_id: str,
    sector: str,
    channel_key: str,
    provider: str,
    frame_key: str,
) -> str:
    return os.path.join(
        cache_root,
        "satellite",
        "frame_index",
        str(sat_id),
        str(sector),
        str(channel_key),
        str(provider),
        f"{frame_key}.json",
    )


def _tile_cache_path(
    cache_root: str,
    sat_id: str,
    sector: str,
    channel_key: str,
    provider: str,
    frame_key: str,
    z: int,
    x: int,
    y: int,
) -> str:
    return os.path.join(
        cache_root,
        "satellite",
        "tiles",
        str(sat_id),
        str(sector),
        str(channel_key),
        str(provider),
        str(frame_key),
        str(z),
        str(x),
        f"{y}.png",
    )


def _merge_channel_files(
    merged: Dict[str, List[Tuple[datetime, str]]],
    incoming: Dict[str, List[Tuple[datetime, str]]],
) -> None:
    for band, values in incoming.items():
        if band not in merged:
            merged[band] = []
        merged[band].extend(values)


def _resolve_segments(sat_id: str, start_dt: datetime, end_dt: datetime):
    return satellite_archive_utils._split_date_range_by_satellite(
        sat_id, start_dt, end_dt
    )


def build_live_frames(
    cache_root: str,
    base_dir: str,
    sat_id: str,
    sector: str,
    channel_key: str,
    hours: int = 2,
    source: str = "aws",
    max_frames: int = 90,
) -> Dict:
    recipe_key = _normalize_recipe(channel_key)

    if recipe_key not in ABI_CHANNELS:
        raise ValueError(f"Unsupported channel/product: {channel_key}")

    providers = _provider_candidates(source)
    last_error: Optional[Exception] = None
    for provider in providers:
        try:
            payload = _build_live_frames_for_provider(
                cache_root=cache_root,
                base_dir=base_dir,
                sat_id=sat_id,
                sector=sector,
                channel_key=channel_key,
                recipe_key=recipe_key,
                hours=hours,
                provider=provider,
                max_frames=max_frames,
            )
            payload["requested_source"] = (
                str(source or "auto").strip().lower() or "auto"
            )
            payload["provider"] = provider
            payload["source"] = f"NODD-{provider.upper()}"
            return payload
        except Exception as exc:
            last_error = exc
            continue

    if last_error is not None:
        raise last_error

    return {
        "status": "success",
        "source": f"NODD-{_DEFAULT_PROVIDER.upper()}",
        "sat_id": sat_id,
        "sector": sector,
        "channel": channel_key,
        "provider": _DEFAULT_PROVIDER,
        "frame_count": 0,
        "frames": [],
    }


def _build_live_frames_for_provider(
    cache_root: str,
    base_dir: str,
    sat_id: str,
    sector: str,
    channel_key: str,
    recipe_key: str,
    hours: int,
    provider: str,
    max_frames: int,
) -> Dict:

    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(hours=max(1, int(hours or 2)))

    segments = _resolve_segments(sat_id, start_dt, end_dt)
    if not segments:
        return {
            "status": "success",
            "source": f"NODD-{provider.upper()}",
            "sat_id": sat_id,
            "sector": sector,
            "channel": channel_key,
            "frame_count": 0,
            "frames": [],
        }

    req_bands = ABI_CHANNELS[recipe_key].get("req", [recipe_key])
    merged_files: Dict[str, List[Tuple[datetime, str]]] = {
        band: [] for band in req_bands
    }

    for seg_sat, seg_start, seg_end in segments:
        _save_root, seg_req_bands, seg_files, _download_count = (
            satellite_archive_utils._download_archive_files(
                sat_id=seg_sat,
                sector=sector,
                channel_key=recipe_key,
                start_dt=seg_start,
                end_dt=seg_end,
                base_dir=base_dir,
                provider=provider,
                progress_callback=None,
                latest_only=False,
            )
        )
        if seg_req_bands:
            req_bands = seg_req_bands
        _merge_channel_files(merged_files, seg_files)

    for band in merged_files:
        merged_files[band].sort(key=lambda item: item[0])

    frame_plan = satellite_archive_utils._build_frame_plan(
        channel_files=merged_files,
        req_bands=req_bands,
        max_frames=max_frames,
    )

    frames = []
    for scan_time, file_map in frame_plan:
        key = _frame_key(scan_time)
        index_path = _frame_index_path(
            cache_root=cache_root,
            sat_id=sat_id,
            sector=sector,
            channel_key=channel_key,
            provider=provider,
            frame_key=key,
        )
        os.makedirs(os.path.dirname(index_path), exist_ok=True)

        payload = {
            "sat_id": sat_id,
            "sector": sector,
            "channel": channel_key,
            "recipe_channel": recipe_key,
            "provider": provider,
            "frame_key": key,
            "timestamp_utc": scan_time.astimezone(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            "files": file_map,
        }
        with open(index_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)

        frames.append(
            {
                "frame_key": key,
                "timestamp_utc": payload["timestamp_utc"],
                "source_data_key": key,
            }
        )

    return {
        "status": "success",
        "source": f"NODD-{provider.upper()}",
        "sat_id": sat_id,
        "sector": sector,
        "channel": channel_key,
        "provider": provider,
        "frame_count": len(frames),
        "frames": frames,
    }


def ensure_tile_cached(
    cache_root: str,
    sat_id: str,
    sector: str,
    channel_key: str,
    source: str,
    frame_key: str,
    z: int,
    x: int,
    y: int,
) -> Optional[str]:
    tile_path, _stats = ensure_tile_cached_with_stats(
        cache_root=cache_root,
        sat_id=sat_id,
        sector=sector,
        channel_key=channel_key,
        source=source,
        frame_key=frame_key,
        z=z,
        x=x,
        y=y,
    )
    return tile_path


def ensure_tile_cached_with_stats(
    cache_root: str,
    sat_id: str,
    sector: str,
    channel_key: str,
    source: str,
    frame_key: str,
    z: int,
    x: int,
    y: int,
) -> Tuple[Optional[str], Dict[str, object]]:
    started = time.perf_counter()
    stats: Dict[str, object] = {
        "cache_status": "miss",
        "provider": "",
        "elapsed_ms": 0,
        "render_ms": 0,
        "index_found": False,
    }

    providers = _provider_candidates(source)
    provider = providers[0]
    index_path = ""
    tile_path = ""
    for candidate in providers:
        candidate_tile = _tile_cache_path(
            cache_root=cache_root,
            sat_id=sat_id,
            sector=sector,
            channel_key=channel_key,
            provider=candidate,
            frame_key=frame_key,
            z=z,
            x=x,
            y=y,
        )
        if os.path.exists(candidate_tile):
            stats["cache_status"] = "hit"
            stats["provider"] = candidate
            stats["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
            return candidate_tile, stats
        candidate_index = _frame_index_path(
            cache_root=cache_root,
            sat_id=sat_id,
            sector=sector,
            channel_key=channel_key,
            provider=candidate,
            frame_key=frame_key,
        )
        if os.path.exists(candidate_index):
            provider = candidate
            index_path = candidate_index
            tile_path = candidate_tile
            break
    if not index_path:
        stats["provider"] = provider
        stats["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
        return None, stats

    stats["index_found"] = True

    with open(index_path, "r", encoding="utf-8") as fh:
        frame_meta = json.load(fh)

    recipe_key = _normalize_recipe(frame_meta.get("recipe_channel") or channel_key)
    if recipe_key not in ABI_CHANNELS:
        stats["provider"] = provider
        stats["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
        return None, stats

    file_map = frame_meta.get("files") or {}
    req_bands = ABI_CHANNELS[recipe_key].get("req", [recipe_key])
    if not all(band in file_map for band in req_bands):
        stats["provider"] = provider
        stats["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
        return None, stats

    west, south, east, north = _tile_bounds_lonlat(z, x, y)

    datasets = {}
    render_started = time.perf_counter()
    try:
        for band in req_bands:
            band_path = file_map.get(band)
            if not band_path or not os.path.exists(band_path):
                stats["provider"] = provider
                stats["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
                return None, stats
            datasets[band] = xr.open_dataset(band_path)

        sample = _get_cmi_dataarray(datasets[req_bands[0]])
        data = process_composite(
            datasets,
            recipe_key,
            sample.metpy.cartopy_crs,
            max_size=2048,
        )
        img_extent = _compute_image_extent(sample)

        os.makedirs(os.path.dirname(tile_path), exist_ok=True)

        fig = plt.figure(figsize=(2.56, 2.56), dpi=100)
        ax = fig.add_axes([0, 0, 1, 1], projection=ccrs.epsg(3857))
        ax.set_axis_off()
        ax.set_extent([west, east, south, north], crs=ccrs.PlateCarree())

        if recipe_key in RGB_COMPOSITE_KEYS:
            ax.imshow(
                data,
                extent=img_extent,
                origin="upper",
                interpolation="bilinear",
                transform=sample.metpy.cartopy_crs,
                zorder=1,
            )
        elif recipe_key == "Sandwich":
            ax.imshow(
                data["vis"],
                cmap="Greys_r",
                extent=img_extent,
                origin="upper",
                interpolation="bilinear",
                transform=sample.metpy.cartopy_crs,
                zorder=1,
            )
            ax.imshow(
                data["ir"],
                extent=img_extent,
                origin="upper",
                interpolation="bilinear",
                transform=sample.metpy.cartopy_crs,
                zorder=2,
            )
        else:
            interpolation_mode = (
                "nearest" if str(recipe_key).startswith("Channel13") else "bilinear"
            )
            ax.imshow(
                data,
                cmap=ABI_CHANNELS[recipe_key]["cmap"],
                norm=ABI_CHANNELS[recipe_key].get("norm"),
                extent=img_extent,
                origin="upper",
                interpolation=interpolation_mode,
                transform=sample.metpy.cartopy_crs,
                zorder=1,
            )

        fig.savefig(tile_path, dpi=100, transparent=True, pad_inches=0)
        plt.close(fig)
        stats["cache_status"] = "rendered"
        stats["provider"] = provider
        stats["render_ms"] = int((time.perf_counter() - render_started) * 1000)
        stats["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
        return tile_path, stats
    finally:
        for ds in datasets.values():
            try:
                ds.close()
            except Exception:
                pass
