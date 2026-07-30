"""AWS NOAA GK2A AMI Level 1B listing provider for Satellite v2."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import re
import tempfile
import threading
import time

import boto3
from botocore import UNSIGNED
from botocore.config import Config

from config.satellite_v2_config import (
    ami_channel_for_source_channel,
    normalize_channel,
    normalize_sat_id,
    normalize_sector,
    source_channels_for_product,
)
from lib.s3_utils import track_s3_client
from satellite_v2.cache import source_path
from satellite_v2.models import SourceFrame

_BUCKET = "noaa-gk2a-pds"
_FRAME_RE = re.compile(
    r"^gk2a_ami_le1b_(?P<channel>[a-z0-9]+)_fd\d+ge_"
    r"(?P<stamp>\d{12})\.nc$",
    re.IGNORECASE,
)
_S3_CLIENT = None
_S3_CLIENT_LOCK = threading.Lock()
_PREFIX_LIST_TTL_SECONDS = 60.0
_PREFIX_LIST_CACHE: dict[str, tuple[float, list[tuple[str, int]]]] = {}
_PREFIX_LIST_CACHE_LOCK = threading.Lock()


def _s3_client():
    global _S3_CLIENT
    if _S3_CLIENT is None:
        with _S3_CLIENT_LOCK:
            if _S3_CLIENT is None:
                _S3_CLIENT = track_s3_client(
                    boto3.client(
                        "s3",
                        config=Config(
                            signature_version=UNSIGNED,
                            connect_timeout=10,
                            read_timeout=45,
                            retries={"max_attempts": 3, "mode": "standard"},
                        ),
                    )
                )
    return _S3_CLIENT


def _list_prefix_objects(prefix: str) -> list[tuple[str, int]]:
    now = time.monotonic()
    with _PREFIX_LIST_CACHE_LOCK:
        cached = _PREFIX_LIST_CACHE.get(prefix)
        if cached is not None and now - cached[0] <= _PREFIX_LIST_TTL_SECONDS:
            return cached[1]

    objects: list[tuple[str, int]] = []
    paginator = _s3_client().get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=_BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            objects.append((str(obj.get("Key") or ""), int(obj.get("Size") or 0)))

    with _PREFIX_LIST_CACHE_LOCK:
        _PREFIX_LIST_CACHE[prefix] = (now, objects)
        if len(_PREFIX_LIST_CACHE) > 64:
            for stale_key in [
                key
                for key, (stamp, _) in _PREFIX_LIST_CACHE.items()
                if now - stamp > _PREFIX_LIST_TTL_SECONDS
            ]:
                _PREFIX_LIST_CACHE.pop(stale_key, None)
    return objects


def _iter_hour_prefixes(hours: int) -> list[str]:
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    count = max(1, int(hours)) + 2
    return [
        (now - timedelta(hours=offset)).strftime("AMI/L1B/FD/%Y%m/%d/%H/")
        for offset in range(count)
    ]


def _parse_frame(key: str, expected_channel: str) -> SourceFrame | None:
    filename = key.rsplit("/", 1)[-1]
    match = _FRAME_RE.fullmatch(filename)
    if match is None or match.group("channel").lower() != expected_channel.lower():
        return None
    dt = datetime.strptime(match.group("stamp"), "%Y%m%d%H%M").replace(
        tzinfo=timezone.utc
    )
    frame_key = dt.strftime("%Y%m%dT%H%M00Z")
    timestamp = dt.isoformat().replace("+00:00", "Z")
    source_url = f"s3://{_BUCKET}/{key}"
    return SourceFrame(
        frame_key=frame_key,
        timestamp_utc=timestamp,
        provider="aws",
        source_key=key,
        source_url=source_url,
    )


def _list_recent_channel_frames(
    source_channel: str,
    hours: int,
) -> dict[str, SourceFrame]:
    ami_channel = ami_channel_for_source_channel(source_channel)
    frames: dict[str, SourceFrame] = {}
    for prefix in _iter_hour_prefixes(hours):
        for key, size in _list_prefix_objects(prefix):
            frame = _parse_frame(key, ami_channel)
            if frame is None:
                continue
            frames[frame.frame_key] = SourceFrame(
                frame_key=frame.frame_key,
                timestamp_utc=frame.timestamp_utc,
                provider=frame.provider,
                source_key=frame.source_key,
                source_url=frame.source_url,
                file_size=size,
                source_keys={source_channel: frame.source_key},
                source_urls={source_channel: frame.source_url},
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
    if sat_key != "gk2a":
        raise ValueError(f"GK2A provider cannot serve satellite '{sat_id}'.")
    if sector_key != "FULLDISK":
        raise ValueError("GK2A currently supports only the FULLDISK sector.")

    source_channels = source_channels_for_product(channel)
    channel_maps = {
        source_channel: _list_recent_channel_frames(source_channel, hours)
        for source_channel in source_channels
    }
    if not channel_maps:
        return []

    primary_channel = source_channels[0]
    common_frame_keys = set(channel_maps[primary_channel])
    for source_channel in source_channels[1:]:
        common_frame_keys &= set(channel_maps[source_channel])

    frames: list[SourceFrame] = []
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
            source_channel: int(
                channel_maps[source_channel][frame_key].file_size or 0
            )
            for source_channel in source_channels
        }
        frames.append(
            SourceFrame(
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
        )
    frames.sort(key=lambda frame: frame.timestamp_utc)
    return frames[-max(1, int(max_frames)) :]


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
    if sat_key != "gk2a" or sector_key != "FULLDISK":
        raise ValueError("GK2A source downloads require gk2a/FULLDISK.")

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
        raise ValueError("GK2A frame is missing frame_key.")

    paths: dict[str, Path] = {}
    for source_channel in source_channels:
        source_key = str(source_keys.get(source_channel) or "")
        if not source_key:
            raise ValueError(
                f"GK2A frame is missing source key for {source_channel}."
            )
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
                _s3_client().download_file(_BUCKET, source_key, tmp_name)
                os.replace(tmp_name, target)
            except Exception:
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass
                raise
        paths[source_channel] = target
    return paths
