"""AWS NOAA Himawari-9 AHI HSD listing provider for Satellite v2.

Lists and downloads raw AHI L1b HSD segment files from the public
noaa-himawari9 bucket. FULLDISK only: one frame per 10-minute timeslot,
ten segments per band. A frame's source_keys store the S01 segment key per
source channel; the remaining segment keys are derived from the filename's
SnnNN sequence token at download time (all segments share one prefix).
"""

from __future__ import annotations

import os
import re
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config.satellite_v2_config import (
    ahi_band_for_source_channel,
    normalize_channel,
    normalize_sat_id,
    normalize_sector,
    source_channels_for_product,
)
from satellite_v2.cache import source_path
from satellite_v2.models import SourceFrame
from satellite_v2.provider_aws import _list_prefix_objects, _s3_client

_BUCKET = "noaa-himawari9"

_SEGMENT_RE = re.compile(
    r"HS_H\d{2}_(?P<date>\d{8})_(?P<time>\d{4})_B(?P<band>\d{2})_FLDK_"
    r"R\d{2}_S(?P<segment>\d{2})(?P<total>\d{2})\.DAT(?:\.bz2)?$"
)


def _require_fulldisk(sector: str) -> str:
    sector_key = normalize_sector(sector)
    if sector_key != "FULLDISK":
        raise ValueError(
            f"Himawari-9 supports the FULLDISK sector only (got '{sector}')."
        )
    return sector_key


def _iter_hour_prefixes(hours: int) -> list[str]:
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    count = max(1, int(hours)) + 2
    return [
        f"AHI-L1b-FLDK/{(now - timedelta(hours=offset)):%Y/%m/%d/%H}"
        for offset in range(count)
    ]


def _list_band_frames(band: int, hours: int) -> dict[str, dict]:
    """Complete timeslots for one band: frame_key → timestamp + segment keys."""
    slots: dict[str, dict] = {}
    for prefix in _iter_hour_prefixes(hours):
        for key, size in _list_prefix_objects(_BUCKET, prefix):
            match = _SEGMENT_RE.search(key)
            if not match or int(match.group("band")) != band:
                continue
            slot_time = datetime.strptime(
                match.group("date") + match.group("time"), "%Y%m%d%H%M"
            ).replace(tzinfo=timezone.utc)
            frame_key = slot_time.strftime("%Y%m%dT%H%M%SZ")
            entry = slots.setdefault(
                frame_key,
                {
                    "timestamp_utc": slot_time.isoformat().replace("+00:00", "Z"),
                    "total": int(match.group("total")),
                    "segments": {},
                },
            )
            entry["segments"][int(match.group("segment"))] = (key, int(size))
    return {
        frame_key: entry
        for frame_key, entry in slots.items()
        if len(entry["segments"]) >= int(entry["total"])
    }


def _primary_segment(entry: dict) -> tuple[str, int]:
    key, _ = entry["segments"][min(entry["segments"])]
    total_size = sum(size for _, size in entry["segments"].values())
    return key, total_size


def list_recent_frames(
    sat_id: str,
    sector: str,
    channel_key: str,
    hours: int,
    max_frames: int,
) -> list[SourceFrame]:
    normalize_sat_id(sat_id)
    _require_fulldisk(sector)
    channel = normalize_channel(channel_key)

    source_channels = source_channels_for_product(channel)
    channel_slots = {
        source_channel: _list_band_frames(
            ahi_band_for_source_channel(source_channel), hours
        )
        for source_channel in source_channels
    }

    primary_channel = source_channels[0]
    common_frame_keys = set(channel_slots[primary_channel])
    for source_channel in source_channels[1:]:
        common_frame_keys &= set(channel_slots[source_channel])

    frames: list[SourceFrame] = []
    for frame_key in common_frame_keys:
        source_keys: dict[str, str] = {}
        source_urls: dict[str, str] = {}
        file_sizes: dict[str, int] = {}
        for source_channel in source_channels:
            key, total_size = _primary_segment(channel_slots[source_channel][frame_key])
            source_keys[source_channel] = key
            source_urls[source_channel] = f"s3://{_BUCKET}/{key}"
            file_sizes[source_channel] = total_size
        primary_key = source_keys[primary_channel]
        frames.append(
            SourceFrame(
                frame_key=frame_key,
                timestamp_utc=str(
                    channel_slots[primary_channel][frame_key]["timestamp_utc"]
                ),
                provider="aws",
                source_key=primary_key,
                source_url=f"s3://{_BUCKET}/{primary_key}",
                file_size=sum(file_sizes.values()),
                source_keys=source_keys,
                source_urls=source_urls,
                file_sizes=file_sizes,
            )
        )

    frames.sort(key=lambda frame: frame.timestamp_utc)
    return frames[-max(1, int(max_frames)) :]


def _segment_keys_from_primary(primary_key: str) -> list[str]:
    match = _SEGMENT_RE.search(primary_key)
    if match is None:
        raise ValueError(f"Unrecognized AHI HSD segment key: '{primary_key}'.")
    total = int(match.group("total"))
    first = int(match.group("segment"))
    token = f"_S{first:02d}{total:02d}"
    return [
        primary_key.replace(token, f"_S{segment:02d}{total:02d}")
        for segment in range(1, total + 1)
    ]


def download_product_source_frames(
    cache_root: str | Path,
    sat_id: str,
    sector: str,
    channel_key: str,
    frame: SourceFrame | dict,
) -> dict[str, Path]:
    sat_key = normalize_sat_id(sat_id)
    sector_key = _require_fulldisk(sector)
    product_key = normalize_channel(channel_key)

    source_channels = source_channels_for_product(product_key)
    source_keys = (
        frame.source_keys
        if isinstance(frame, SourceFrame)
        else frame.get("source_keys")
    ) or {}
    frame_key = str(
        frame.frame_key if isinstance(frame, SourceFrame) else frame.get("frame_key")
    )
    if not frame_key:
        raise ValueError("Satellite v2 frame is missing frame_key.")

    missing = [channel for channel in source_channels if channel not in source_keys]
    if missing:
        raise ValueError(
            f"Satellite v2 frame is missing source keys for: {', '.join(missing)}"
        )

    paths: dict[str, Path] = {}
    for source_channel in source_channels:
        primary_key = str(source_keys[source_channel])
        for segment_key in _segment_keys_from_primary(primary_key):
            filename = segment_key.rsplit("/", 1)[-1]
            target = source_path(
                cache_root, sat_key, sector_key, source_channel, frame_key, filename
            )
            if source_channel not in paths:
                # The renderer receives the first segment and derives its
                # siblings from the shared frame directory.
                paths[source_channel] = target
            if target.exists() and target.stat().st_size > 0:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(
                prefix=f".{filename}.", suffix=".tmp", dir=str(target.parent)
            )
            os.close(fd)
            try:
                _s3_client().download_file(_BUCKET, segment_key, tmp_name)
                os.replace(tmp_name, target)
            except Exception:
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass
                raise
    return paths
