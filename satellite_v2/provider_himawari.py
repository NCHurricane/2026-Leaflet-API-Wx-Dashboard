"""AWS NOAA Himawari-9 AHI HSD listing provider for Satellite v2.

Lists and downloads raw AHI L1b HSD segment files from the public
noaa-himawari9 bucket.

Three sectors are supported:
- FULLDISK: one frame per 10-minute timeslot, ten segments per band, stitched
  vertically (first_line/total_segments) into one disk-wide grid.
- JAPAN: a fixed Japan-area box re-scanned 4x per 10-minute timeslot
  (JP01..JP04). Each scene is a single self-contained segment (its own
  coff/loff describe that scene's own small grid directly, no full-disk
  offset needed) sharing identical navigation across all 4 scenes, so this
  is a genuine ~2.5-min rapid scan of one fixed box, not four spatial tiles.
- TARGET: JMA's dynamically-retasked "Target Area" (R301..R304 within each
  10-minute timeslot), same single-segment repeat-scan structure as JAPAN
  but the navigation (and hence real-world lat/lon box) can change between
  timeslots depending on what JMA is currently monitoring (a storm, a
  volcano, or nothing at all).

A frame's source_keys store the primary segment key per source channel; for
FULLDISK the remaining segment keys are derived from the filename's SnnNN
sequence token at download time (all segments share one prefix). JAPAN/TARGET
scenes are always single-segment (S0101), so no sibling derivation is needed.
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
    r"HS_H\d{2}_(?P<date>\d{8})_(?P<time>\d{4})_B(?P<band>\d{2})_"
    r"(?P<scene>FLDK|JP0[1-4]|R30[1-4])_"
    r"R\d{2}_S(?P<segment>\d{2})(?P<total>\d{2})\.DAT(?:\.bz2)?$"
)

# S3 folder root and repeat-scan behavior per sector. FULLDISK has one scene
# (FLDK) stitched from multiple segments; JAPAN/TARGET repeat-scan a single
# fixed-grid segment under 4 scene names per 10-minute timeslot, so each
# scene is its own frame rather than a stitched whole.
_SECTOR_INFO = {
    "FULLDISK": {"root": "AHI-L1b-FLDK", "multi_scene": False},
    "JAPAN": {"root": "AHI-L1b-Japan", "multi_scene": True},
    "TARGET": {"root": "AHI-L1b-Target", "multi_scene": True},
}


def _require_supported_sector(sector: str) -> str:
    sector_key = normalize_sector(sector)
    if sector_key not in _SECTOR_INFO:
        raise ValueError(
            f"Himawari-9 supports "
            f"{', '.join(sorted(_SECTOR_INFO))} sectors only (got '{sector}')."
        )
    return sector_key


def _iter_hour_prefixes(root: str, hours: int) -> list[str]:
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    count = max(1, int(hours)) + 2
    return [
        f"{root}/{(now - timedelta(hours=offset)):%Y/%m/%d/%H}"
        for offset in range(count)
    ]


def _list_band_frames(sector_key: str, band: int, hours: int) -> dict[str, dict]:
    """Complete frames for one band: frame_key → timestamp + segment keys.

    For FULLDISK, frame_key is the 10-minute timeslot (segments stitch into
    one frame). For JAPAN/TARGET, frame_key includes the scene suffix
    (JP01..04 / R301..04) since each scene within a timeslot is its own
    frame.
    """
    info = _SECTOR_INFO[sector_key]
    multi_scene = bool(info["multi_scene"])
    slots: dict[str, dict] = {}
    for prefix in _iter_hour_prefixes(str(info["root"]), hours):
        for key, size in _list_prefix_objects(_BUCKET, prefix):
            match = _SEGMENT_RE.search(key)
            if not match or int(match.group("band")) != band:
                continue
            scene = match.group("scene")
            slot_time = datetime.strptime(
                match.group("date") + match.group("time"), "%Y%m%d%H%M"
            ).replace(tzinfo=timezone.utc)
            # The filename only carries the 10-min slot; the actual repeat
            # scan within it (JP01..04 / R301..04) happens roughly every
            # 2.5 min. This offset is an approximation for scrubber
            # ordering/display only, not the true JMA ObsStartTime.
            scene_index = int(scene[-1]) - 1 if multi_scene else 0
            scan_time = slot_time + timedelta(seconds=150 * scene_index)
            frame_key = (
                f"{slot_time:%Y%m%dT%H%M%SZ}_{scene}"
                if multi_scene
                else slot_time.strftime("%Y%m%dT%H%M%SZ")
            )
            entry = slots.setdefault(
                frame_key,
                {
                    "timestamp_utc": scan_time.isoformat().replace("+00:00", "Z"),
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
    sector_key = _require_supported_sector(sector)
    channel = normalize_channel(channel_key)

    source_channels = source_channels_for_product(channel)
    channel_slots = {
        source_channel: _list_band_frames(
            sector_key, ahi_band_for_source_channel(source_channel), hours
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
    sector_key = _require_supported_sector(sector)
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
