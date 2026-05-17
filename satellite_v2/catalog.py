"""Satellite v2 catalog publishing."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

from config.satellite_v2_config import (
    SATELLITE_V2_CATALOG_MAX_AGE_SECONDS,
    SATELLITE_V2_DEFAULT_HOURS,
    SATELLITE_V2_DEFAULT_MAX_FRAMES,
    SATELLITE_V2_PROVIDER,
    SATELLITE_V2_RENDER_VERSION,
    SATELLITE_V2_TILE_SIZE,
    max_native_zoom_for_product,
    normalize_channel,
    normalize_sat_id,
    normalize_sector,
    zooms_for_sector,
)
from satellite_v2.cache import (
    atomic_write_json,
    catalog_path,
    count_frame_tiles,
    file_age_seconds,
    read_json,
    sample_frame_tiles,
)
from satellite_v2.models import CatalogFrame, utc_now_iso
from satellite_v2.provider_aws import list_recent_frames


def _request_values(hours: int, max_frames: int) -> tuple[int, int]:
    hours_value = max(1, int(hours or SATELLITE_V2_DEFAULT_HOURS))
    max_frames_value = max(1, int(max_frames or SATELLITE_V2_DEFAULT_MAX_FRAMES))
    return hours_value, max_frames_value


def _parse_frame_time(frame: dict[str, Any]) -> datetime | None:
    timestamp = str(frame.get("timestamp_utc") or frame.get("frame_key") or "")
    if not timestamp:
        return None
    try:
        if timestamp.endswith("Z"):
            timestamp = timestamp[:-1] + "+00:00"
        parsed = datetime.fromisoformat(timestamp)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _cached_catalog_covers_request(
    catalog: dict[str, Any],
    hours: int,
    max_frames: int,
) -> bool:
    cached_hours = int(catalog.get("hours") or 0)
    cached_max_frames = int(catalog.get("max_frames") or 0)
    return cached_hours >= hours and cached_max_frames >= max_frames


def _catalog_for_request(
    catalog: dict[str, Any],
    hours: int,
    max_frames: int,
) -> dict[str, Any]:
    payload = deepcopy(catalog)
    max_native_zoom = None
    try:
        max_native_zoom = max_native_zoom_for_product(
            str(payload.get("sector") or ""), str(payload.get("channel") or "")
        )
    except ValueError:
        max_native_zoom = payload.get("max_native_zoom")
    frames = [frame for frame in payload.get("frames", []) if isinstance(frame, dict)]
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    requested_frames = [
        frame
        for frame in frames
        if (frame_time := _parse_frame_time(frame)) is not None and frame_time >= cutoff
    ]
    requested_frames.sort(
        key=lambda frame: str(
            frame.get("timestamp_utc") or frame.get("frame_key") or ""
        )
    )
    requested_frames = requested_frames[-max_frames:]
    payload["frames"] = requested_frames
    payload["frame_count"] = len(requested_frames)
    payload["hours"] = hours
    payload["max_frames"] = max_frames
    payload["render_version"] = SATELLITE_V2_RENDER_VERSION
    payload["catalog_request_hours"] = hours
    payload["catalog_request_max_frames"] = max_frames
    if max_native_zoom is not None:
        payload["max_native_zoom"] = max_native_zoom
        for frame in requested_frames:
            frame["max_native_zoom"] = max_native_zoom
    return payload


def _catalog_template(
    sat_id: str,
    sector: str,
    channel_key: str,
    hours: int,
    max_frames: int,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "success",
        "data_mode": "current",
        "provider": SATELLITE_V2_PROVIDER,
        "render_version": SATELLITE_V2_RENDER_VERSION,
        "sat_id": sat_id,
        "sector": sector,
        "channel": channel_key,
        "hours": hours,
        "max_frames": max_frames,
        "tile_size": SATELLITE_V2_TILE_SIZE,
        "tile_url_template": (
            "/api/satellite-v2/tile/{z}/{x}/{y}"
            f"?sat_id={sat_id}&sector={sector}&channel={channel_key}"
            "&frame_key={frame_key}"
        ),
        "generated_at": utc_now_iso(),
        "catalog_max_age_seconds": SATELLITE_V2_CATALOG_MAX_AGE_SECONDS,
        "frames": [],
        "frame_count": 0,
    }


def build_catalog(
    cache_root: str,
    sat_id: str,
    sector: str,
    channel_key: str,
    hours: int = SATELLITE_V2_DEFAULT_HOURS,
    max_frames: int = SATELLITE_V2_DEFAULT_MAX_FRAMES,
) -> dict[str, Any]:
    sat_key = normalize_sat_id(sat_id)
    sector_key = normalize_sector(sector)
    channel = normalize_channel(channel_key)
    hours_value, max_frames_value = _request_values(hours, max_frames)
    zooms = zooms_for_sector(sector_key)
    max_native_zoom = max_native_zoom_for_product(sector_key, channel)

    payload = _catalog_template(
        sat_key, sector_key, channel, hours_value, max_frames_value
    )
    payload["max_native_zoom"] = max_native_zoom
    source_frames = list_recent_frames(
        sat_id=sat_key,
        sector=sector_key,
        channel_key=channel,
        hours=hours_value,
        max_frames=max_frames_value,
    )
    catalog_frames: list[dict[str, Any]] = []
    for source_frame in source_frames:
        tile_counts = count_frame_tiles(
            cache_root,
            sat_key,
            sector_key,
            channel,
            source_frame.frame_key,
            zooms,
        )
        available_zooms = [int(z) for z, count in tile_counts.items() if count > 0]
        sample_tiles = sample_frame_tiles(
            cache_root,
            sat_key,
            sector_key,
            channel,
            source_frame.frame_key,
            zooms,
        )
        frame_payload = CatalogFrame(
            frame_key=source_frame.frame_key,
            timestamp_utc=source_frame.timestamp_utc,
            provider=source_frame.provider,
            source_key=source_frame.source_key,
            source_url=source_frame.source_url,
            source_keys=source_frame.source_keys,
            source_urls=source_frame.source_urls,
            file_sizes=source_frame.file_sizes,
            available_zooms=available_zooms,
            tile_counts=tile_counts,
            max_native_zoom=max_native_zoom,
        ).to_dict()
        frame_payload["sample_tiles"] = sample_tiles
        catalog_frames.append(frame_payload)

    payload["frames"] = catalog_frames
    payload["frame_count"] = len(catalog_frames)
    payload["configured_zooms"] = list(zooms)
    atomic_write_json(catalog_path(cache_root, sat_key, sector_key, channel), payload)
    return payload


def get_catalog(
    cache_root: str,
    sat_id: str,
    sector: str,
    channel_key: str,
    hours: int = SATELLITE_V2_DEFAULT_HOURS,
    max_frames: int = SATELLITE_V2_DEFAULT_MAX_FRAMES,
    refresh: bool = False,
) -> dict[str, Any]:
    sat_key = normalize_sat_id(sat_id)
    sector_key = normalize_sector(sector)
    channel = normalize_channel(channel_key)
    hours_value, max_frames_value = _request_values(hours, max_frames)
    path = catalog_path(cache_root, sat_key, sector_key, channel)
    age = file_age_seconds(path)
    cached = read_json(path)

    # Cache-first behavior for interactive UI loads:
    # if a catalog exists on disk and caller did not request refresh,
    # return it immediately instead of rebuilding from provider.
    cached_render_version = str(cached.get("render_version") or "") if cached else ""
    if cached and not refresh and cached_render_version == SATELLITE_V2_RENDER_VERSION:
        if _cached_catalog_covers_request(cached, hours_value, max_frames_value):
            payload = _catalog_for_request(cached, hours_value, max_frames_value)
            age_seconds = int(age) if age is not None else 0
            is_fresh = age is not None and age <= SATELLITE_V2_CATALOG_MAX_AGE_SECONDS
            should_rebuild_stale_current = not is_fresh and (
                hours_value <= SATELLITE_V2_DEFAULT_HOURS
                or int(payload.get("frame_count") or 0) < 1
            )
            if not should_rebuild_stale_current:
                payload["catalog_age_seconds"] = age_seconds
                payload["catalog_source"] = "disk" if is_fresh else "disk-stale"
                return payload

    try:
        fresh = build_catalog(
            cache_root, sat_key, sector_key, channel, hours_value, max_frames_value
        )
        fresh["catalog_age_seconds"] = 0
        fresh["catalog_source"] = "provider"
        return fresh
    except Exception as exc:
        if cached:
            payload = _catalog_for_request(cached, hours_value, max_frames_value)
            payload["status"] = "stale"
            payload["catalog_age_seconds"] = int(age or 0)
            payload["catalog_source"] = (
                "disk"
                if age is not None and age <= SATELLITE_V2_CATALOG_MAX_AGE_SECONDS
                else "disk-stale"
            )
            payload["provider_error"] = str(exc)
            return payload
        raise


def status_payload(cache_root: str) -> dict[str, Any]:
    root = catalog_path(cache_root, "goes19", "CONUS", "Channel13").parents[2]
    catalogs = list(root.glob("*/*/*.json")) if root.exists() else []
    newest_age = None
    if catalogs:
        ages = [file_age_seconds(path) for path in catalogs]
        valid_ages = [age for age in ages if age is not None]
        if valid_ages:
            newest_age = int(min(valid_ages))
    return {
        "status": "success",
        "schema_version": 1,
        "catalog_count": len(catalogs),
        "newest_catalog_age_seconds": newest_age,
        "cache_root": str(root.parents[1]) if root.exists() else str(root),
        "generated_at": utc_now_iso(),
    }
