"""
NEXRAD Level 2 chunk assembler for unidata-nexrad-level2-chunks.

Chunks in this bucket are raw LDM record segments split from the standard
AR2V volume file at LDM record boundaries. Concatenating all chunks for a
scan in sequence order reproduces a valid AR2V file that Py-ART can read.

Key format: {SITE}/{VCP}/{YYYYMMDD}-{HHMMSS}-{SEQ:03d}-{TYPE}
  SITE = 4-char ICAO
  VCP  = volume coverage pattern number (subdirectory)
  SEQ  = chunk sequence number (001, 002, ...)
  TYPE = S (start), I (intermediate), E (end)

Public interface mirrors radar_nodd_utils.download_radar_data so the
worker can call it without structural changes.

Latency strategy: individual chunk files are cached locally so each
worker run downloads only the delta since the last run (~5-10 chunks
instead of the full ~90-chunk scan). Re-assembly is a local disk
concatenation. A .complete marker in the chunk dir prevents unnecessary
re-downloads once the end-of-volume (type E) chunk has been received.
"""

from __future__ import annotations

import os
import re
import shutil
import threading
import time as _time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app_core.atomic_io import atomic_output_path

CHUNKS_BUCKET = "unidata-nexrad-level2-chunks"

# Local cache for individual downloaded chunk files, kept between worker runs.
_CHUNK_CACHE_ROOT = (
    Path(__file__).resolve().parent.parent
    / "cache"
    / "radar"
    / "live"
    / "l2_chunk_cache"
)

_CHUNK_RE = re.compile(
    r"^(?P<site>[A-Z]{4})/(?P<vcp>\d+)/"
    r"(?P<date>\d{8})-(?P<time>\d{6})-(?P<seq>\d+)-(?P<ctype>[A-Z])$"
)

# In-process memo of VCP folders already confirmed complete (contain an 'E' chunk),
# keyed by site. Once a folder is known complete it never needs to be re-listed from
# S3 on later polls -- only the handful of in-progress folders at the front do.
_COMPLETE_VCP_CACHE: dict[str, set[str]] = {}
_VCP_SCAN_TIME_CACHE: dict[str, dict[str, str]] = {}
_PREFIX_CACHE_TTL_SECONDS = 30.0
_PREFIX_CACHE: dict[str, tuple[float, list[str]]] = {}
_PREFIX_CACHE_LOCK = threading.Lock()


def _log(msg: str) -> None:
    try:
        print(msg)
    except (UnicodeEncodeError, UnicodeDecodeError):
        print(msg.encode("ascii", errors="replace").decode("ascii"))


def _parse_chunk_key(key: str) -> dict | None:
    m = _CHUNK_RE.match(key)
    if not m:
        return None
    d = m.groupdict()
    try:
        d["seq"] = int(d["seq"])
        d["scan_prefix"] = f"{d['site']}/{d['vcp']}/{d['date']}-{d['time']}-"
        d["scan_dt"] = datetime.strptime(
            f"{d['date']}{d['time']}", "%Y%m%d%H%M%S"
        ).replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return d


def _list_site_chunks(s3_client, site: str, max_keys: int = 1000) -> list[dict]:
    """Return parsed chunk records for a site, sorted by scan time then sequence."""
    prefix = f"{site}/"
    try:
        paginator = s3_client.get_paginator("list_objects_v2")
        chunks = []
        for page in paginator.paginate(
            Bucket=CHUNKS_BUCKET,
            Prefix=prefix,
            PaginationConfig={"MaxItems": max_keys},
        ):
            for obj in page.get("Contents", []):
                parsed = _parse_chunk_key(obj["Key"])
                if parsed:
                    parsed["key"] = obj["Key"]
                    parsed["last_modified"] = obj.get("LastModified")
                    parsed["size"] = obj.get("Size", 0)
                    chunks.append(parsed)
        chunks.sort(key=lambda c: (c["scan_dt"], c["seq"]))
        return chunks
    except Exception as exc:
        _log(f"[chunks] list failed for {site}: {type(exc).__name__}: {exc}")
        return []


def _list_site_prefixes(s3_client, site: str) -> list[str]:
    """Return numeric VCP subfolder names under SITE/, newest-unsorted.

    Uses a Delimiter listing so only folder names come back (no object bodies),
    which stays cheap even when a site has thousands of historical VCP folders.
    """
    now = _time.monotonic()
    with _PREFIX_CACHE_LOCK:
        cached = _PREFIX_CACHE.get(site)
        if cached is not None and now - cached[0] <= _PREFIX_CACHE_TTL_SECONDS:
            return list(cached[1])

    prefix = f"{site}/"
    prefixes: list[str] = []
    try:
        paginator = s3_client.get_paginator("list_objects_v2")
        for page in paginator.paginate(
            Bucket=CHUNKS_BUCKET, Prefix=prefix, Delimiter="/"
        ):
            for cp in page.get("CommonPrefixes", []):
                name = cp["Prefix"][len(prefix):].rstrip("/")
                if name.isdigit():
                    prefixes.append(name)
    except Exception as exc:
        _log(f"[chunks] prefix list failed for {site}: {type(exc).__name__}: {exc}")
    prefixes.sort(key=int)
    if prefixes:
        with _PREFIX_CACHE_LOCK:
            _PREFIX_CACHE[site] = (now, list(prefixes))
    return prefixes


def _list_chunks_in_prefix(s3_client, site: str, vcp: str) -> list[dict]:
    """Return parsed chunk records for a single SITE/VCP/ subfolder."""
    prefix = f"{site}/{vcp}/"
    chunks: list[dict] = []
    try:
        paginator = s3_client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=CHUNKS_BUCKET, Prefix=prefix):
            for obj in page.get("Contents", []):
                parsed = _parse_chunk_key(obj["Key"])
                if parsed:
                    parsed["key"] = obj["Key"]
                    parsed["last_modified"] = obj.get("LastModified")
                    parsed["size"] = obj.get("Size", 0)
                    chunks.append(parsed)
    except Exception as exc:
        _log(f"[chunks] list failed for {site}/{vcp}: {type(exc).__name__}: {exc}")
    return chunks


def _list_recent_site_chunks(
    s3_client, site: str, cutoff_dt: datetime, max_folders: int | None = None
) -> list[dict]:
    """Walk newest-first VCP subfolders under SITE/ until scans predate cutoff_dt.

    A flat SITE/ listing is lexicographic across every VCP subfolder the site has
    ever had; once a site accumulates enough historical subfolders, a MaxItems-capped
    listing never reaches the newest ones. Discovering subfolder names first
    (cheap, no object bodies) and walking them newest-first avoids that trap.

    max_folders is a sanity ceiling, not the primary stop condition (the cutoff_dt
    check below is). A new VCP folder shows up roughly every 4-7 minutes, so it's
    sized off the requested lookback window with generous headroom.

    Folders already confirmed complete on a prior call are served from an
    in-process cache instead of being re-listed from S3 -- otherwise every poll
    would re-list the whole lookback window's worth of folders (e.g. ~30+ for a
    3h window), which is what made polling slow after the discovery-order fix.
    Only the front of the walk (folders still in progress) hits S3 each time.

    The VCP counter is not perfectly monotonic with time -- stray/orphaned
    folders (e.g. a single leftover chunk from days ago) can sort numerically
    after the true newest folder. Stopping on the very first stale folder can
    therefore skip past real current data. A stale *streak* threshold gives
    tolerance for isolated outliers while still bounding the walk.
    """
    if max_folders is None:
        lookback_minutes = max(
            0.0, (datetime.now(timezone.utc) - cutoff_dt).total_seconds() / 60
        )
        max_folders = max(6, int(lookback_minutes / 3) + 10)

    prefixes = _list_site_prefixes(s3_client, site)
    if not prefixes:
        return []

    complete_cache = _COMPLETE_VCP_CACHE.setdefault(site, set())
    time_cache = _VCP_SCAN_TIME_CACHE.setdefault(site, {})

    collected: list[dict] = []
    stale_streak = 0
    stale_streak_limit = 3
    for checked, vcp in enumerate(reversed(prefixes), start=1):
        if vcp in complete_cache and vcp in time_cache:
            scan_dt = datetime.strptime(
                time_cache[vcp], "%Y%m%d-%H%M%S"
            ).replace(tzinfo=timezone.utc)
            if scan_dt < cutoff_dt:
                stale_streak += 1
                if stale_streak >= stale_streak_limit:
                    break
                if checked >= max_folders:
                    break
                continue
            stale_streak = 0
            collected.append(
                {
                    "site": site,
                    "vcp": vcp,
                    "scan_prefix": f"{site}/{vcp}/{time_cache[vcp]}-",
                    "scan_dt": scan_dt,
                    "seq": 0,
                    "ctype": "E",
                    "key": None,
                    "last_modified": None,
                    "size": 0,
                }
            )
            continue

        folder_chunks = _list_chunks_in_prefix(s3_client, site, vcp)
        if folder_chunks:
            collected.extend(folder_chunks)
            newest = max(folder_chunks, key=lambda c: c["scan_dt"])
            time_cache[vcp] = newest["scan_dt"].strftime("%Y%m%d-%H%M%S")
            if _is_scan_complete(folder_chunks):
                complete_cache.add(vcp)
            if newest["scan_dt"] < cutoff_dt:
                stale_streak += 1
                if stale_streak >= stale_streak_limit:
                    break
            else:
                stale_streak = 0
        if checked >= max_folders:
            break

    collected.sort(key=lambda c: (c["scan_dt"], c["seq"]))
    return [c for c in collected if c["scan_dt"] >= cutoff_dt]


def _group_by_scan(chunks: list[dict]) -> dict[str, list[dict]]:
    """Group chunk records by scan prefix, preserving sequence order."""
    groups: dict[str, list[dict]] = {}
    for chunk in chunks:
        prefix = chunk["scan_prefix"]
        groups.setdefault(prefix, []).append(chunk)
    for group in groups.values():
        group.sort(key=lambda c: c["seq"])
    return groups


def _scan_assembled_filename(scan_prefix: str) -> str:
    """Derive an AR2V-style filename from the scan prefix.

    Input:  'KRAX/207/20260629-123456-'
    Output: 'KRAX20260629_123456_V06'  (parseable by _parse_dt_from_filename)
    """
    m = re.search(r"(\d{8})-(\d{6})-$", scan_prefix)
    if m:
        return f"{scan_prefix[:4]}{m.group(1)}_{m.group(2)}_V06"
    return re.sub(r"[^A-Z0-9_]", "_", scan_prefix).strip("_")


def _is_scan_complete(chunks: list[dict]) -> bool:
    """True when the chunk list contains an end-of-volume marker (type E)."""
    return any(c["ctype"] == "E" for c in chunks)


def assemble_scan(
    s3_client,
    chunks: list[dict],
    out_path: Path,
) -> bool:
    """Download chunks in sequence order and concatenate into a single AR2V file.

    Used by the test script and one-off assembly. For the recurring worker
    path, prefer download_radar_data which uses the incremental local cache.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with atomic_output_path(out_path) as temporary:
            with temporary.open("wb") as fh:
                for chunk in chunks:
                    obj = s3_client.get_object(Bucket=CHUNKS_BUCKET, Key=chunk["key"])
                    fh.write(obj["Body"].read())
        return out_path.exists() and out_path.stat().st_size > 0
    except Exception as exc:
        _log(f"[chunks] assemble failed: {type(exc).__name__}: {exc}")
        return False


# ---------------------------------------------------------------------------
# Incremental chunk caching helpers (worker path)
# ---------------------------------------------------------------------------

def _chunk_local_dir(site: str, scan_prefix: str) -> Path:
    """Local cache directory for individual chunks of one scan.

    scan_prefix 'KRAX/207/20260628-005818-' → l2_chunk_cache/KRAX/20260628-005818/
    """
    m = re.search(r"(\d{8}-\d{6})-$", scan_prefix)
    safe_name = m.group(1) if m else scan_prefix.replace("/", "_").strip("-")
    return _CHUNK_CACHE_ROOT / site / safe_name


_CHUNK_DOWNLOAD_WORKERS = 16


def _download_one_chunk(s3_client, chunk: dict, dest: Path) -> bool:
    try:
        obj = s3_client.get_object(Bucket=CHUNKS_BUCKET, Key=chunk["key"])
        with atomic_output_path(dest, suffix=".part") as temporary:
            temporary.write_bytes(obj["Body"].read())
        return True
    except Exception as exc:
        _log(
            f"[chunks] chunk download failed {chunk['key']}: "
            f"{type(exc).__name__}: {exc}"
        )
        return False


def _download_new_chunks(s3_client, chunks: list[dict], chunk_dir: Path) -> int:
    """Download chunks not already on disk. Returns count of newly downloaded files.

    Each chunk is a separate small S3 object, so latency (not bandwidth) dominates.
    A scan can have 50-100+ chunks and a backfill spans many scans, so downloading
    sequentially (one GetObject round-trip at a time) turned a cold backfill into a
    50+ second stall. Fetching concurrently keeps this to a couple of seconds.
    """
    chunk_dir.mkdir(parents=True, exist_ok=True)
    pending = []
    for chunk in chunks:
        dest = chunk_dir / f"{chunk['seq']:04d}"
        if not dest.exists():
            pending.append((chunk, dest))
    if not pending:
        return 0

    from concurrent.futures import ThreadPoolExecutor

    new_count = 0
    with ThreadPoolExecutor(max_workers=_CHUNK_DOWNLOAD_WORKERS) as pool:
        results = pool.map(
            lambda item: _download_one_chunk(s3_client, item[0], item[1]), pending
        )
        new_count = sum(1 for ok in results if ok)
    return new_count


def _assemble_from_local_cache(chunk_dir: Path, out_path: Path) -> bool:
    """Concatenate all locally cached chunk files into an assembled AR2V file."""
    chunk_files = sorted(chunk_dir.glob("[0-9][0-9][0-9][0-9]"))
    if not chunk_files:
        return False
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with atomic_output_path(out_path) as temporary:
            with temporary.open("wb") as fh:
                for chunk_file in chunk_files:
                    fh.write(chunk_file.read_bytes())
        return out_path.exists() and out_path.stat().st_size > 0
    except Exception as exc:
        _log(f"[chunks] local assemble failed: {type(exc).__name__}: {exc}")
        return False


def _prune_chunk_cache(site: str, cutoff_dt: datetime) -> None:
    """Remove local chunk cache directories older than cutoff_dt."""
    site_dir = _CHUNK_CACHE_ROOT / site
    if not site_dir.exists():
        return
    for scan_dir in site_dir.iterdir():
        if not scan_dir.is_dir():
            continue
        m = re.match(r"^(\d{8})-(\d{6})$", scan_dir.name)
        if not m:
            continue
        try:
            scan_dt = datetime.strptime(
                f"{m.group(1)}{m.group(2)}", "%Y%m%d%H%M%S"
            ).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if scan_dt < cutoff_dt:
            try:
                shutil.rmtree(str(scan_dir))
                _log(f"[chunks] pruned cache dir {scan_dir.name}")
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Public download interface (mirrors radar_nodd_utils.download_radar_data)
# ---------------------------------------------------------------------------

def download_radar_data(
    level: str,
    station_id: str,
    product: str,
    lookback_hours: float,
    base_dir: str,
    latest_only: bool = False,
    provider: str = "aws",
    **_kwargs,
) -> tuple[str, int, int]:
    """Incrementally download and assemble chunk scans for a site.

    On each call only new chunks (not already on disk) are downloaded from S3.
    Re-assembly is a local disk concatenation of cached chunk files, so
    subsequent calls during an in-progress scan are cheap (~5-10 chunk
    downloads + one file concat vs ~90 full chunk downloads per call before).

    A .complete marker is written to the chunk dir once the end-of-volume
    (type E) chunk is present so fully assembled scans skip all S3 I/O on
    future calls.

    Returns (save_dir, total_scans, assembled_count).
    """
    if "2" not in str(level):
        _log(f"[chunks] chunks bucket is Level 2 only; got level={level!r}")
        return ("", 0, 0)

    from lib.s3_utils import get_s3_client

    s3 = get_s3_client()
    site = str(station_id).strip().upper()
    save_dir = os.path.join(base_dir, "radar_level2_downloads", product, site)
    os.makedirs(save_dir, exist_ok=True)

    lookback = float(lookback_hours)
    cutoff_dt = datetime.now(timezone.utc) - timedelta(hours=lookback)

    _t0 = _time.perf_counter()
    _log(f"[chunks] listing site={site} lookback={lookback}h")

    all_chunks = _list_recent_site_chunks(s3, site, cutoff_dt)
    if not all_chunks:
        _log(f"[chunks] no chunks found for {site}")
        return (save_dir, 0, 0)

    scans = _group_by_scan(all_chunks)

    # Prune local chunk cache dirs that have aged out of the lookback window
    _prune_chunk_cache(site, cutoff_dt - timedelta(hours=0.5))

    # Filter to scans within the lookback window
    recent_scans = {
        prefix: chunks
        for prefix, chunks in scans.items()
        if chunks and chunks[0]["scan_dt"] >= cutoff_dt
    }

    if not recent_scans:
        _log(f"[chunks] no recent scans within {lookback}h for {site}")
        return (save_dir, 0, 0)

    sorted_prefixes = sorted(
        recent_scans.keys(),
        key=lambda p: recent_scans[p][0]["scan_dt"],
    )

    if latest_only:
        sorted_prefixes = sorted_prefixes[-1:]

    total = len(sorted_prefixes)
    assembled_count = 0

    for prefix in sorted_prefixes:
        chunks = recent_scans[prefix]
        filename = _scan_assembled_filename(prefix)
        out_path = Path(save_dir) / filename
        chunk_dir = _chunk_local_dir(site, prefix)
        complete_marker = chunk_dir / ".complete"

        # Already complete: assembled file is final, skip all S3 I/O
        if complete_marker.exists() and out_path.exists():
            assembled_count += 1
            continue

        # Download only chunks not already on disk
        new_chunks = _download_new_chunks(s3, chunks, chunk_dir)

        # Re-assemble when new chunks arrived or the assembled file is missing
        if new_chunks > 0 or not out_path.exists():
            cached_chunk_count = len(list(chunk_dir.glob("[0-9][0-9][0-9][0-9]")))
            is_complete = _is_scan_complete(chunks)
            _log(
                f"[chunks] assembling {filename} "
                f"({cached_chunk_count} cached, +{new_chunks} new, complete={is_complete})"
            )
            if _assemble_from_local_cache(chunk_dir, out_path):
                if is_complete:
                    complete_marker.touch(exist_ok=True)
                size_kb = out_path.stat().st_size / 1024
                _log(f"[chunks] assembled {filename} ({size_kb:.1f} KB)")
                assembled_count += 1
            else:
                _log(f"[chunks] failed to assemble {filename}")
        else:
            assembled_count += 1  # up to date

    _log(
        f"[chunks] done in {_time.perf_counter() - _t0:.2f}s — "
        f"{assembled_count}/{total} scans ready"
    )
    return (save_dir, total, assembled_count)
