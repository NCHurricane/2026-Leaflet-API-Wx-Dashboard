"""AWS NOAA GOES listing provider for Satellite v2."""

from __future__ import annotations

import re
import os
import tempfile
from pathlib import Path
from datetime import datetime, timedelta, timezone

import boto3
from botocore import UNSIGNED
from botocore.config import Config

from config.satellite_v2_config import (
    aws_product_prefix_for_sector,
    normalize_channel,
    normalize_sat_id,
    normalize_sector,
    source_channel_token,
    source_channels_for_product,
)
from satellite_v2.models import SourceFrame
from satellite_v2.cache import source_path

_START_RE = re.compile(r"_s(?P<stamp>\d{13})")


def _bucket_name(sat_id: str) -> str:
    sat_key = normalize_sat_id(sat_id)
    return f"noaa-{sat_key}"


def _s3_client():
    return boto3.client(
        "s3",
        config=Config(
            signature_version=UNSIGNED,
            connect_timeout=10,
            read_timeout=45,
            retries={"max_attempts": 3, "mode": "standard"},
        ),
    )


def _iter_hour_prefixes(hours: int) -> list[tuple[int, int, int]]:
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    count = max(1, int(hours)) + 2
    return [
        (
            (now - timedelta(hours=offset)).year,
            int((now - timedelta(hours=offset)).strftime("%j")),
            (now - timedelta(hours=offset)).hour,
        )
        for offset in range(count)
    ]


def _parse_frame_timestamp(key: str) -> tuple[str, str] | None:
    match = _START_RE.search(key)
    if not match:
        return None
    raw = match.group("stamp")
    year = int(raw[0:4])
    day_of_year = int(raw[4:7])
    hour = int(raw[7:9])
    minute = int(raw[9:11])
    second = int(raw[11:13])
    dt = datetime(year, 1, 1, tzinfo=timezone.utc) + timedelta(
        days=day_of_year - 1,
        hours=hour,
        minutes=minute,
        seconds=second,
    )
    timestamp = dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    frame_key = dt.strftime("%Y%m%dT%H%M%SZ")
    return frame_key, timestamp


def _filename_matches_sector(filename: str, sector_key: str) -> bool:
    if sector_key == "MESO1":
        return "CMIPM1" in filename
    if sector_key == "MESO2":
        return "CMIPM2" in filename
    return True


def _list_recent_channel_frames(
    sat_key: str,
    sector_key: str,
    source_channel: str,
    hours: int,
) -> dict[str, SourceFrame]:
    product_prefix = aws_product_prefix_for_sector(sector_key)
    token = source_channel_token(source_channel)
    bucket = _bucket_name(sat_key)
    client = _s3_client()

    frames: dict[str, SourceFrame] = {}
    for year, day, hour in _iter_hour_prefixes(hours):
        prefix = f"{product_prefix}/{year}/{day:03d}/{hour:02d}/"
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = str(obj.get("Key") or "")
                filename = key.rsplit("/", 1)[-1]
                if not _filename_matches_sector(filename, sector_key):
                    continue
                if f"{token}_" not in filename:
                    continue
                parsed = _parse_frame_timestamp(key)
                if parsed is None:
                    continue
                frame_key, timestamp = parsed
                frames[frame_key] = SourceFrame(
                    frame_key=frame_key,
                    timestamp_utc=timestamp,
                    provider="aws",
                    source_key=key,
                    source_url=f"s3://{bucket}/{key}",
                    file_size=int(obj.get("Size") or 0),
                    source_keys={source_channel: key},
                    source_urls={source_channel: f"s3://{bucket}/{key}"},
                    file_sizes={source_channel: int(obj.get("Size") or 0)},
                )
    return frames


def list_recent_frames(
    sat_id: str,
    sector: str,
    channel_key: str,
    hours: int,
    max_frames: int,
) -> list[SourceFrame]:
    sat_key = normalize_sat_id(sat_id)
    sector_key = normalize_sector(sector)
    channel = normalize_channel(channel_key)
    source_channels = source_channels_for_product(channel)
    channel_maps = {
        source_channel: _list_recent_channel_frames(
            sat_key, sector_key, source_channel, hours
        )
        for source_channel in source_channels
    }
    if not channel_maps:
        return []

    primary_channel = source_channels[0]
    common_frame_keys = set(channel_maps[primary_channel])
    for source_channel in source_channels[1:]:
        common_frame_keys &= set(channel_maps[source_channel])

    frames: dict[str, SourceFrame] = {}
    for frame_key in common_frame_keys:
        primary_frame = channel_maps[primary_channel][frame_key]
        source_keys = {
            source_channel: channel_maps[source_channel][frame_key].source_key
            for source_channel in source_channels
        }
        source_urls = {
            source_channel: channel_maps[source_channel][frame_key].source_url
            for source_channel in source_channels
        }
        file_sizes = {
            source_channel: int(channel_maps[source_channel][frame_key].file_size or 0)
            for source_channel in source_channels
        }
        frames[frame_key] = SourceFrame(
            frame_key=frame_key,
            timestamp_utc=primary_frame.timestamp_utc,
            provider="aws",
            source_key=primary_frame.source_key,
            source_url=primary_frame.source_url,
            file_size=sum(file_sizes.values()),
            source_keys=source_keys,
            source_urls=source_urls,
            file_sizes=file_sizes,
        )

    ordered = sorted(frames.values(), key=lambda frame: frame.timestamp_utc)
    return ordered[-max(1, int(max_frames)) :]


def download_product_source_frames(
    cache_root: str | Path,
    sat_id: str,
    sector: str,
    channel_key: str,
    frame: SourceFrame | dict,
) -> dict[str, Path]:
    sat_key = normalize_sat_id(sat_id)
    sector_key = normalize_sector(sector)
    product_key = normalize_channel(channel_key)
    source_channels = source_channels_for_product(product_key)
    source_keys = (
        frame.source_keys
        if isinstance(frame, SourceFrame)
        else frame.get("source_keys")
    ) or {}

    if not source_keys:
        primary_key = str(
            frame.source_key
            if isinstance(frame, SourceFrame)
            else frame.get("source_key")
        )
        if primary_key:
            source_keys = {source_channels[0]: primary_key}

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
        source_key = str(source_keys[source_channel])
        filename = source_key.rsplit("/", 1)[-1]
        target = source_path(
            cache_root, sat_key, sector_key, source_channel, frame_key, filename
        )
        if not target.exists() or target.stat().st_size <= 0:
            target.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(
                prefix=f".{filename}.", suffix=".tmp", dir=str(target.parent)
            )
            os.close(fd)
            try:
                _s3_client().download_file(_bucket_name(sat_key), source_key, tmp_name)
                os.replace(tmp_name, target)
            except Exception:
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass
                raise
        paths[source_channel] = target
    return paths
