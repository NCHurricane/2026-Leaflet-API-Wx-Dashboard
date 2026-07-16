"""AWS NOAA GOES listing provider for Satellite v2."""

from __future__ import annotations

import re
import os
import tempfile
import threading
import time
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


_S3_CLIENT = None
_S3_CLIENT_LOCK = threading.Lock()


def _s3_client():
    # boto3 clients are thread-safe; reuse one instead of rebuilding per call.
    global _S3_CLIENT
    if _S3_CLIENT is None:
        with _S3_CLIENT_LOCK:
            if _S3_CLIENT is None:
                _S3_CLIENT = boto3.client(
                    "s3",
                    config=Config(
                        signature_version=UNSIGNED,
                        connect_timeout=10,
                        read_timeout=45,
                        retries={"max_attempts": 3, "mode": "standard"},
                    ),
                )
    return _S3_CLIENT


# Hour-prefix listings are shared across source channels (one LIST returns all
# C01-C16 files) and across the pre/post-warm catalog builds of a job, so a
# short TTL cache removes most S3 round trips per worker run.
_PREFIX_LIST_TTL_SECONDS = 60.0
_PREFIX_LIST_CACHE: dict[tuple[str, str], tuple[float, list[tuple[str, int]]]] = {}
_PREFIX_LIST_CACHE_LOCK = threading.Lock()


def _list_prefix_objects(bucket: str, prefix: str) -> list[tuple[str, int]]:
    now = time.monotonic()
    cache_key = (bucket, prefix)
    with _PREFIX_LIST_CACHE_LOCK:
        cached = _PREFIX_LIST_CACHE.get(cache_key)
        if cached is not None and now - cached[0] <= _PREFIX_LIST_TTL_SECONDS:
            return cached[1]

    objects: list[tuple[str, int]] = []
    paginator = _s3_client().get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            objects.append((str(obj.get("Key") or ""), int(obj.get("Size") or 0)))

    with _PREFIX_LIST_CACHE_LOCK:
        _PREFIX_LIST_CACHE[cache_key] = (now, objects)
        if len(_PREFIX_LIST_CACHE) > 64:
            for stale_key in [
                key
                for key, (stamp, _) in _PREFIX_LIST_CACHE.items()
                if now - stamp > _PREFIX_LIST_TTL_SECONDS
            ]:
                _PREFIX_LIST_CACHE.pop(stale_key, None)
    return objects


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
    # Match the mesoscale sub-sector across product families: CMIPM1/CMIPM2
    # (imagery) and ADPM1/ADPM2 (aerosol) both carry "M1-M"/"M2-M" ahead of
    # the scan-mode token (e.g. "...ADPM1-M6...").
    if sector_key == "MESO1":
        return "M1-M" in filename
    if sector_key == "MESO2":
        return "M2-M" in filename
    return True


# ABI-L2 bucket sub-sector suffix. Full Disk = F, CONUS = C, both mesoscales
# share the single M-prefixed listing (filtered by _filename_matches_sector).
_SECTOR_PREFIX_SUFFIX = {"CONUS": "C", "FULLDISK": "F", "MESO1": "M", "MESO2": "M"}


def _aws_family_prefix(source_channel: str, sector_key: str) -> str:
    """AWS listing prefix for a source channel's product family + sector.

    CMIP imagery keeps its existing sector→prefix mapping; the aerosol
    families (ADP, AOD) share the same sector suffix convention.
    """
    if source_channel == "ADP":
        family = "ADP"
    elif source_channel == "AOD":
        family = "AOD"
    else:
        return aws_product_prefix_for_sector(sector_key)
    return f"ABI-L2-{family}{_SECTOR_PREFIX_SUFFIX.get(sector_key, 'C')}"


def _list_recent_channel_frames(
    sat_key: str,
    sector_key: str,
    source_channel: str,
    hours: int,
) -> dict[str, SourceFrame]:
    product_prefix = _aws_family_prefix(source_channel, sector_key)
    # ADP/AOD are single-file-per-scene products with no C## channel token in
    # the filename, so they skip the imagery token filter.
    token = None if source_channel in ("ADP", "AOD") else source_channel_token(source_channel)
    bucket = _bucket_name(sat_key)

    frames: dict[str, SourceFrame] = {}
    for year, day, hour in _iter_hour_prefixes(hours):
        prefix = f"{product_prefix}/{year}/{day:03d}/{hour:02d}/"
        for key, size in _list_prefix_objects(bucket, prefix):
            filename = key.rsplit("/", 1)[-1]
            if not _filename_matches_sector(filename, sector_key):
                continue
            if token is not None and f"{token}_" not in filename:
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
                file_size=size,
                source_keys={source_channel: key},
                source_urls={source_channel: f"s3://{bucket}/{key}"},
                file_sizes={source_channel: size},
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
