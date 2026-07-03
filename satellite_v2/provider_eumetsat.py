"""EUMETSAT Data Store provider for Satellite v2 (Meteosat).

Hand-rolled REST client for the Data Store: OAuth client-credentials token,
OpenSearch listing by time window, and per-entry download of the single
Level 1.5 ``.nat`` file each SEVIRI repeat cycle produces, or the MTG/FCI
NetCDF body chunks that make up a full-disk frame.

Unlike GOES/AHI there are no per-channel files: one .nat holds all 12 SEVIRI
channels, so every source channel of a frame maps to the same download and
``download_product_source_frames`` returns the same cached path for each
requested channel.

Credentials come from EUMETSAT_CONSUMER_KEY / EUMETSAT_CONSUMER_SECRET
(loaded from .env; free account at https://api.eumetsat.int/api-key/ with
the General EUMETSAT Data Licence and Meteosat NRT licence accepted).
Platforms should be hidden by callers when ``credentials_available()`` is
False.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import requests
from dotenv import load_dotenv

from config.satellite_v2_config import (
    fci_channel_for_source_channel,
    normalize_channel,
    normalize_sat_id,
    normalize_sector,
    source_channels_for_product,
)
from satellite_v2.cache import atomic_write_json, source_path
from satellite_v2.models import SourceFrame

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ENV_PATH = _REPO_ROOT / ".env"
load_dotenv(_ENV_PATH)

_TOKEN_URL = "https://api.eumetsat.int/token"
_SEARCH_URL = "https://api.eumetsat.int/data/search-products/1.0.0/os"
_DOWNLOAD_URL = "https://api.eumetsat.int/data/download/1.0.0"

_COLLECTIONS = {
    "meteosat9": "EO:EUM:DAT:MSG:HRSEVIRI-IODC",
    "meteosat12": "EO:EUM:DAT:0662",
}

_INSTRUMENT_FOR_SAT = {
    "meteosat9": "SEVIRI",
    "meteosat12": "FCI",
}

# SEVIRI full-disk repeat cycle. Scan start times sit a few seconds past the
# nominal slot, so frame keys floor to this.
_SLOT_MINUTES = 15

_HTTP_TIMEOUT = 60
_DOWNLOAD_TIMEOUT = 600

# An FCI full-disk frame is ~40 chunk files (~800 MB total). A few parallel
# connections cut the cold-frame download time several-fold while staying
# well inside EUMETSAT fair-use connection limits.
_FCI_DOWNLOAD_WORKERS = 4
# Written into the frame's FCI source dir after all chunks are verified on
# disk; its presence lets later loads skip the product re-search API call.
_FCI_MANIFEST_NAME = "manifest.json"

_TOKEN_LOCK = threading.Lock()
_TOKEN: dict[str, object] = {"value": "", "expires_at": 0.0}


def _env_first(*names: str) -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def credentials_available() -> bool:
    return bool(
        _env_first("EUMETSAT_CONSUMER_KEY", "WX_EUMETSAT_CONSUMER_KEY")
        and _env_first("EUMETSAT_CONSUMER_SECRET", "WX_EUMETSAT_CONSUMER_SECRET")
    )


def _credentials() -> tuple[str, str]:
    key = _env_first("EUMETSAT_CONSUMER_KEY", "WX_EUMETSAT_CONSUMER_KEY")
    secret = _env_first("EUMETSAT_CONSUMER_SECRET", "WX_EUMETSAT_CONSUMER_SECRET")
    if not key or not secret:
        raise ValueError(
            "EUMETSAT credentials are not configured. Set "
            "EUMETSAT_CONSUMER_KEY/EUMETSAT_CONSUMER_SECRET or "
            "WX_EUMETSAT_CONSUMER_KEY/WX_EUMETSAT_CONSUMER_SECRET in .env."
        )
    return key, secret


def _eumetsat_error_detail(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        text = response.text.strip()
        return text[:500] if text else response.reason
    exceptions = payload.get("exceptions")
    if isinstance(exceptions, list) and exceptions:
        detail = exceptions[0].get("exceptionText")
        if detail:
            return str(detail)
    return str(payload)[:500]


def _bearer_headers(force_refresh: bool = False) -> dict[str, str]:
    # The gateway returns the same cached token for repeated
    # client-credentials requests until it expires, so cache locally by
    # expiry and only re-request near the end of its lifetime.
    with _TOKEN_LOCK:
        now = time.monotonic()
        if (
            not force_refresh
            and _TOKEN["value"]
            and now < float(_TOKEN["expires_at"]) - 120.0
        ):
            return {"Authorization": f"Bearer {_TOKEN['value']}"}
        response = requests.post(
            _TOKEN_URL,
            auth=_credentials(),
            data={"grant_type": "client_credentials"},
            timeout=_HTTP_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
        _TOKEN["value"] = str(payload["access_token"])
        _TOKEN["expires_at"] = now + float(payload.get("expires_in") or 3600)
        return {"Authorization": f"Bearer {_TOKEN['value']}"}


def _authorized_get(url: str, **kwargs) -> requests.Response:
    response = requests.get(url, headers=_bearer_headers(), **kwargs)
    if response.status_code == 401:
        # Token revoked or expired server-side; refresh once and retry.
        response = requests.get(
            url, headers=_bearer_headers(force_refresh=True), **kwargs
        )
    return response


def _collection_for(sat_key: str) -> str:
    collection = _COLLECTIONS.get(sat_key)
    if collection is None:
        raise ValueError(
            f"No EUMETSAT Data Store collection is configured for '{sat_key}'."
        )
    return collection


def _require_fulldisk(sector: str) -> str:
    sector_key = normalize_sector(sector)
    if sector_key != "FULLDISK":
        raise ValueError(
            f"Meteosat live ingest supports the FULLDISK sector only "
            f"(got '{sector}')."
        )
    return sector_key


def _slot_time(start_iso: str) -> datetime:
    stamp = start_iso.strip()
    if stamp.endswith("Z"):
        stamp = stamp[:-1] + "+00:00"
    parsed = datetime.fromisoformat(stamp).astimezone(timezone.utc)
    return parsed.replace(
        minute=parsed.minute - parsed.minute % _SLOT_MINUTES,
        second=0,
        microsecond=0,
    )


def _search_products(collection: str, hours: int) -> list[dict]:
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=max(1, int(hours)) + 1)
    response = _authorized_get(
        _SEARCH_URL,
        params={
            "format": "json",
            "pi": collection,
            "dtstart": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "dtend": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "c": 100,
        },
        timeout=_HTTP_TIMEOUT,
    )
    response.raise_for_status()
    features = response.json().get("features") or []
    return [feature for feature in features if feature.get("id")]


def _feature_entries(feature: dict) -> list[dict]:
    links = feature.get("properties", {}).get("links") or {}
    entries = links.get("sip-entries") or []
    return [entry for entry in entries if entry.get("href") and entry.get("title")]


def _fci_body_entries(feature: dict) -> list[dict]:
    entries = [
        entry
        for entry in _feature_entries(feature)
        if "CHK-BODY" in str(entry.get("title") or "")
        and str(entry.get("title") or "").lower().endswith(".nc")
    ]
    return sorted(entries, key=lambda entry: str(entry.get("title") or ""))


def _fci_feature_for_product(collection: str, product_id: str) -> dict:
    # Product download happens immediately after catalog listing in normal use,
    # so a recent search is enough and avoids a second product-specific API.
    for feature in _search_products(collection, 12):
        if str(feature.get("id") or "") == product_id:
            return feature
    raise RuntimeError(f"EUMETSAT product is no longer listed: {product_id}")


def list_recent_frames(
    sat_id: str,
    sector: str,
    channel_key: str,
    hours: int,
    max_frames: int,
) -> list[SourceFrame]:
    sat_key = normalize_sat_id(sat_id)
    _require_fulldisk(sector)
    channel = normalize_channel(channel_key)
    collection = _collection_for(sat_key)

    source_channels = source_channels_for_product(channel)
    instrument = _INSTRUMENT_FOR_SAT.get(sat_key, "SEVIRI")
    frames: dict[str, SourceFrame] = {}
    for feature in _search_products(collection, hours):
        product_id = str(feature["id"])
        date_range = str(feature.get("properties", {}).get("date") or "")
        start_iso = date_range.split("/", 1)[0]
        if not start_iso:
            continue
        slot = _slot_time(start_iso)
        frame_key = slot.strftime("%Y%m%dT%H%M%SZ")
        timestamp = slot.isoformat().replace("+00:00", "Z")
        size = int(
            feature.get("properties", {})
            .get("productInformation", {})
            .get("size")
            or 0
        )
        if instrument == "FCI" and not _fci_body_entries(feature):
            continue
        # SEVIRI channels share one .nat; FCI channels share one chunk set.
        frames[frame_key] = SourceFrame(
            frame_key=frame_key,
            timestamp_utc=timestamp,
            provider="eumetsat",
            source_key=product_id,
            source_url=f"eumetsat://{collection}/{product_id}",
            file_size=size,
            source_keys={ch: product_id for ch in source_channels},
            source_urls={
                ch: f"eumetsat://{collection}/{product_id}"
                for ch in source_channels
            },
            file_sizes={ch: size for ch in source_channels},
        )

    ordered = sorted(frames.values(), key=lambda frame: frame.timestamp_utc)
    return ordered[-max(1, int(max_frames)) :]


def _download_nat(collection: str, product_id: str, target: Path) -> None:
    url = (
        f"{_DOWNLOAD_URL}/collections/{quote(collection, safe='')}"
        f"/products/{quote(product_id, safe='')}/entry"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent)
    )
    os.close(fd)
    try:
        with _authorized_get(
            url,
            params={"name": f"{product_id}.nat"},
            timeout=_DOWNLOAD_TIMEOUT,
            stream=True,
        ) as response:
            if response.status_code >= 400:
                detail = _eumetsat_error_detail(response)
                raise requests.HTTPError(
                    f"{response.status_code} EUMETSAT download failed for "
                    f"{product_id}: {detail}",
                    response=response,
                )
            with open(tmp_name, "wb") as handle:
                for chunk in response.iter_content(1024 * 1024):
                    handle.write(chunk)
        os.replace(tmp_name, target)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _download_url_to_path(url: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent)
    )
    os.close(fd)
    try:
        with _authorized_get(url, timeout=_DOWNLOAD_TIMEOUT, stream=True) as response:
            if response.status_code >= 400:
                detail = _eumetsat_error_detail(response)
                raise requests.HTTPError(
                    f"{response.status_code} EUMETSAT download failed for "
                    f"{target.name}: {detail}",
                    response=response,
                )
            with open(tmp_name, "wb") as handle:
                for chunk in response.iter_content(1024 * 1024):
                    if chunk:
                        handle.write(chunk)
        os.replace(tmp_name, target)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _read_fci_manifest(manifest_path: Path) -> list[Path] | None:
    """Chunk paths from a completed download, or None if any file is missing."""
    try:
        filenames = json.loads(manifest_path.read_text("utf-8")).get("chunks") or []
    except (OSError, ValueError, AttributeError):
        return None
    paths = [manifest_path.parent / str(name) for name in filenames]
    if not paths:
        return None
    for path in paths:
        try:
            if path.stat().st_size <= 0:
                return None
        except OSError:
            return None
    return paths


def _download_fci_chunks(
    cache_root: str | Path,
    collection: str,
    sat_key: str,
    sector_key: str,
    frame_key: str,
    product_id: str,
) -> Path:
    manifest_path = source_path(
        cache_root, sat_key, sector_key, "FCI", frame_key, _FCI_MANIFEST_NAME
    )
    cached = _read_fci_manifest(manifest_path)
    if cached is not None:
        return cached[0]

    feature = _fci_feature_for_product(collection, product_id)
    entries = _fci_body_entries(feature)
    if not entries:
        raise RuntimeError(f"EUMETSAT FCI product has no body chunks: {product_id}")
    targets: list[tuple[Path, str]] = [
        (
            source_path(
                cache_root, sat_key, sector_key, "FCI", frame_key, str(entry["title"])
            ),
            str(entry["href"]),
        )
        for entry in entries
    ]
    missing = [
        (target, href)
        for target, href in targets
        if not target.exists() or target.stat().st_size <= 0
    ]
    if missing:
        workers = min(_FCI_DOWNLOAD_WORKERS, len(missing))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [
                pool.submit(_download_url_to_path, href, target)
                for target, href in missing
            ]
            for future in as_completed(futures):
                future.result()
    # Written only after every chunk is on disk, so an interrupted download
    # can never satisfy the manifest fast path with partial strips.
    atomic_write_json(
        manifest_path,
        {"product_id": product_id, "chunks": [target.name for target, _ in targets]},
    )
    return targets[0][0]


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
    collection = _collection_for(sat_key)
    instrument = _INSTRUMENT_FOR_SAT.get(sat_key, "SEVIRI")

    source_channels = source_channels_for_product(product_key)
    if instrument == "FCI":
        for source_channel in source_channels:
            fci_channel_for_source_channel(source_channel)
    frame_key = str(
        frame.frame_key if isinstance(frame, SourceFrame) else frame.get("frame_key")
    )
    product_id = str(
        frame.source_key if isinstance(frame, SourceFrame) else frame.get("source_key")
    )
    if not frame_key or not product_id:
        raise ValueError("Satellite v2 frame is missing frame_key or source_key.")

    if instrument == "FCI":
        primary = _download_fci_chunks(
            cache_root, collection, sat_key, sector_key, frame_key, product_id
        )
        return {source_channel: primary for source_channel in source_channels}

    # One shared .nat per frame: store it once under a shared pseudo-channel
    # directory and hand the same path to every requested source channel.
    filename = f"{product_id}.nat"
    target = source_path(cache_root, sat_key, sector_key, "SEVIRI", frame_key, filename)
    if not target.exists() or target.stat().st_size <= 0:
        _download_nat(collection, product_id, target)
    return {source_channel: target for source_channel in source_channels}
