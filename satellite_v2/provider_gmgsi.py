"""Anonymous NOAA AWS provider for hourly GMGSI global mosaics."""

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
    normalize_channel,
    normalize_sat_id,
    normalize_sector,
    source_channels_for_product,
)
from lib.s3_utils import track_s3_client
from satellite_v2.cache import source_path
from satellite_v2.models import SourceFrame

_BUCKET = "noaa-gmgsi-pds"
_PRODUCT_FOR_SOURCE_CHANNEL = {
    "Channel02": ("GMGSI_VIS", "VIS"),
    "Channel07": ("GMGSI_SW", "SIR"),
    "Channel09": ("GMGSI_WV", "WV"),
    "Channel13": ("GMGSI_LW", "LIR"),
}
_FRAME_RE = re.compile(
    r"^GLOBCOMP(?P<product>LIR|SIR|VIS|WV)_v\d+r\d+_blend_"
    r"s(?P<start>\d{15})_e\d{15}_c\d{15}\.nc$",
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


def _iter_hour_prefixes(product_prefix: str, hours: int) -> list[str]:
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    return [
        f"{product_prefix}/" + (now - timedelta(hours=offset)).strftime("%Y/%m/%d/%H/")
        for offset in range(max(1, int(hours)) + 2)
    ]


def _parse_frame(key: str, expected_product: str, size: int = 0) -> SourceFrame | None:
    match = _FRAME_RE.fullmatch(key.rsplit("/", 1)[-1])
    if match is None or match.group("product").upper() != expected_product:
        return None
    dt = datetime.strptime(match.group("start")[:14], "%Y%m%d%H%M%S").replace(
        tzinfo=timezone.utc
    )
    source_url = f"s3://{_BUCKET}/{key}"
    return SourceFrame(
        frame_key=dt.strftime("%Y%m%dT%H%M%SZ"),
        timestamp_utc=dt.isoformat().replace("+00:00", "Z"),
        provider="aws",
        source_key=key,
        source_url=source_url,
        file_size=int(size or 0),
    )


def list_recent_frames(
    sat_id: str,
    sector: str,
    channel_key: str,
    hours: int,
    max_frames: int,
) -> list[SourceFrame]:
    if normalize_sat_id(sat_id) != "gmgsi" or normalize_sector(sector) != "GLOBAL":
        raise ValueError("GMGSI listing requires gmgsi/GLOBAL.")
    product_key = normalize_channel(channel_key)
    sources = source_channels_for_product(product_key)
    if len(sources) != 1 or sources[0] not in _PRODUCT_FOR_SOURCE_CHANNEL:
        raise ValueError(f"GMGSI does not support product '{channel_key}'.")
    source_channel = sources[0]
    product_prefix, product_token = _PRODUCT_FOR_SOURCE_CHANNEL[source_channel]
    frames: dict[str, SourceFrame] = {}
    for prefix in _iter_hour_prefixes(product_prefix, hours):
        for key, size in _list_prefix_objects(prefix):
            frame = _parse_frame(key, product_token, size)
            if frame is None:
                continue
            frames[frame.frame_key] = SourceFrame(
                frame_key=frame.frame_key,
                timestamp_utc=frame.timestamp_utc,
                provider=frame.provider,
                source_key=frame.source_key,
                source_url=frame.source_url,
                file_size=frame.file_size,
                source_keys={source_channel: frame.source_key},
                source_urls={source_channel: frame.source_url},
                file_sizes={source_channel: int(frame.file_size or 0)},
            )
    return sorted(frames.values(), key=lambda frame: frame.timestamp_utc)[
        -max(1, int(max_frames)) :
    ]


def download_product_source_frames(
    cache_root: str | Path,
    sat_id: str,
    sector: str,
    channel_key: str,
    frame: SourceFrame | dict,
) -> dict[str, Path]:
    sat_key = normalize_sat_id(sat_id)
    sector_key = normalize_sector(sector)
    if sat_key != "gmgsi" or sector_key != "GLOBAL":
        raise ValueError("GMGSI source downloads require gmgsi/GLOBAL.")
    sources = source_channels_for_product(normalize_channel(channel_key))
    if len(sources) != 1 or sources[0] not in _PRODUCT_FOR_SOURCE_CHANNEL:
        raise ValueError(f"GMGSI does not support product '{channel_key}'.")
    source_channel = sources[0]
    source_keys = (
        frame.source_keys if isinstance(frame, SourceFrame) else frame.get("source_keys")
    ) or {}
    source_key = str(source_keys.get(source_channel) or "")
    frame_key = str(
        frame.frame_key if isinstance(frame, SourceFrame) else frame.get("frame_key")
    )
    if not source_key or not frame_key:
        raise ValueError("GMGSI frame is missing its source key or frame key.")
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
    return {source_channel: target}
