"""Meteosat source-prefetch worker for Satellite v2.

Download-only: fills the shared source cache for Meteosat frames so on-demand
tile rendering skips the slow EUMETSAT download (~790 MB per Meteosat-12 FCI
frame, ~270 MB per Meteosat-9 SEVIRI frame). No tiles are rendered here.

EUMETSAT frames are all-channel bundles, so one prefetched frame warms every
product. Each run downloads the newest missing frames first (current + 1 by
default), then backfills the oldest missing frame inside the lookback window,
so animation depth accumulates across runs without any single run stacking
past the task interval. Frames older than the keep window are pruned.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import time
from typing import Callable, Iterable

from config.satellite_v2_config import (
    SATELLITE_V2_METEOSAT_PREFETCH_BACKFILL,
    SATELLITE_V2_METEOSAT_PREFETCH_CHANNEL,
    SATELLITE_V2_METEOSAT_PREFETCH_FRAMES,
    SATELLITE_V2_METEOSAT_PREFETCH_FRESH_WINDOW_SECONDS,
    SATELLITE_V2_METEOSAT_PREFETCH_HOURS,
    SATELLITE_V2_METEOSAT_PREFETCH_JOBS,
    SATELLITE_V2_METEOSAT_PREFETCH_KEEP_HOURS,
    SATELLITE_V2_METEOSAT_PREFETCH_MAX_FRAMES,
    normalize_sat_id,
    normalize_sector,
)
from satellite_v2.cache import namespace_root, source_path
from satellite_v2.models import SourceFrame
from satellite_v2.providers import download_product_source_frames, list_recent_frames
from workers._freshness import is_cache_fresh, mark_run_complete, redirect_stdio_to_log

_BASE_DIR = Path(__file__).resolve().parent.parent
_WORKER_NAME = "satellite_v2_meteosat_prefetch"

# Pseudo-channel directory each instrument's shared source bundle lives under
# (see provider_eumetsat.download_product_source_frames).
_INSTRUMENT_FOR_SAT = {
    "meteosat9": "SEVIRI",
    "meteosat11": "SEVIRI",
    "meteosat12": "FCI",
}
_FCI_MANIFEST_NAME = "manifest.json"
_FRAME_KEY_FORMAT = "%Y%m%dT%H%M%SZ"


def _resolve_cache_root() -> Path:
    configured = os.environ.get("WX_DASHBOARD_CACHE_ROOT") or os.environ.get(
        "WX_SATELLITE_V2_CACHE_ROOT"
    )
    return Path(configured or (_BASE_DIR / "cache")).expanduser().resolve()


_CACHE_ROOT = str(_resolve_cache_root())
_WORKER_STATE_DIR = Path(_CACHE_ROOT) / ".workers"


def _format_elapsed(seconds: float) -> str:
    total = max(0, int(round(float(seconds))))
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m {secs}s"


@contextmanager
def _worker_lock(worker_name: str):
    _WORKER_STATE_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = _WORKER_STATE_DIR / f"{worker_name}.lock"
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        print(f"[{worker_name}] skipped: lock exists at {lock_path}")
        yield False
        return
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(datetime.now(timezone.utc).isoformat())
            handle.write("\n")
        yield True
    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def _frame_source_dir(sat_id: str, sector: str, frame_key: str) -> Path:
    instrument = _INSTRUMENT_FOR_SAT[normalize_sat_id(sat_id)]
    return source_path(
        _CACHE_ROOT, sat_id, sector, instrument, frame_key, "x"
    ).parent


def _frame_sources_cached(sat_id: str, sector: str, frame: SourceFrame) -> bool:
    """True when the frame's source bundle is fully on disk."""
    sat_key = normalize_sat_id(sat_id)
    instrument = _INSTRUMENT_FOR_SAT[sat_key]
    frame_dir = _frame_source_dir(sat_key, sector, frame.frame_key)
    if instrument == "SEVIRI":
        nat = frame_dir / f"{frame.source_key}.nat"
        return nat.exists() and nat.stat().st_size > 0
    manifest = frame_dir / _FCI_MANIFEST_NAME
    try:
        names = json.loads(manifest.read_text("utf-8")).get("chunks") or []
    except (OSError, ValueError):
        return False
    if not names:
        return False
    return all(
        (frame_dir / str(name)).exists() and (frame_dir / str(name)).stat().st_size > 0
        for name in names
    )


def _prune_stale_sources(sat_id: str, sector: str, keep_hours: int) -> int:
    """Remove source frame dirs older than the keep window. Returns count."""
    sat_key = normalize_sat_id(sat_id)
    instrument_dir = (
        namespace_root(_CACHE_ROOT)
        / "source"
        / sat_key
        / normalize_sector(sector)
        / _INSTRUMENT_FOR_SAT[sat_key]
    )
    if not instrument_dir.exists():
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(hours=float(keep_hours))
    pruned = 0
    for frame_dir in instrument_dir.iterdir():
        if not frame_dir.is_dir():
            continue
        try:
            frame_dt = datetime.strptime(frame_dir.name, _FRAME_KEY_FORMAT).replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            continue
        if frame_dt < cutoff:
            try:
                shutil.rmtree(str(frame_dir))
                pruned += 1
            except OSError as exc:
                print(
                    f"[{_WORKER_NAME}] prune failed {frame_dir.name}: "
                    f"{type(exc).__name__}: {exc}"
                )
    return pruned


def _prefetch_one_job(
    worker_name: str,
    sat_id: str,
    sector: str,
    channel: str,
    newest_count: int,
    backfill_count: int,
    hours: int,
    max_frames: int,
    keep_hours: int,
    should_continue: Callable[[], bool] | None = None,
) -> dict[str, int]:
    sat_key = normalize_sat_id(sat_id)
    sector_key = normalize_sector(sector)
    totals = {"cataloged": 0, "downloaded": 0, "cached": 0, "errors": 0, "pruned": 0}

    frames = list_recent_frames(
        sat_id=sat_key,
        sector=sector_key,
        channel_key=channel,
        hours=hours,
        max_frames=max_frames,
    )
    # The provider search can return frames older than the requested window;
    # without this filter the backfill would repeatedly download frames that
    # the keep-window prune deletes on the same run.
    cutoff = datetime.now(timezone.utc) - timedelta(hours=float(hours))
    frames = [
        frame
        for frame in frames
        if datetime.strptime(frame.frame_key, _FRAME_KEY_FORMAT).replace(
            tzinfo=timezone.utc
        )
        >= cutoff
    ]
    totals["cataloged"] = len(frames)
    missing = [
        frame for frame in frames if not _frame_sources_cached(sat_key, sector_key, frame)
    ]
    totals["cached"] = len(frames) - len(missing)

    # Newest missing frames first (current + 1), then the oldest missing frame(s)
    # so the animation window backfills gradually across runs.
    newest = list(reversed(missing[-max(1, int(newest_count)):]))
    backfill = [f for f in missing[: max(0, int(backfill_count))] if f not in newest]
    to_download = newest + backfill
    print(
        f"[{worker_name}] {sat_key}/{sector_key}: cataloged={len(frames)} "
        f"already_cached={totals['cached']} missing={len(missing)} "
        f"downloading={[f.frame_key for f in to_download]}"
    )

    for frame in to_download:
        if should_continue is not None and not should_continue():
            print(
                f"[{worker_name}] {sat_key}/{sector_key}: "
                "stopped after selection changed"
            )
            break
        frame_start = time.perf_counter()
        try:
            download_product_source_frames(
                cache_root=_CACHE_ROOT,
                sat_id=sat_key,
                sector=sector_key,
                channel_key=channel,
                frame=frame,
            )
            totals["downloaded"] += 1
            print(
                f"[{worker_name}] {sat_key}/{sector_key}/{frame.frame_key}: "
                f"downloaded elapsed={_format_elapsed(time.perf_counter() - frame_start)}"
            )
        except Exception as exc:
            totals["errors"] += 1
            print(
                f"[{worker_name}] {sat_key}/{sector_key}/{frame.frame_key} failed: "
                f"{type(exc).__name__}: {exc}"
            )

    totals["pruned"] = _prune_stale_sources(sat_key, sector_key, keep_hours)
    return totals


def run_satellite_v2_meteosat_prefetch_worker(
    *,
    force: bool = False,
    jobs: Iterable[tuple[str, str]] | None = None,
    frames: int | None = None,
    backfill: int | None = None,
    hours: int | None = None,
    keep_hours: int | None = None,
    worker_name: str = _WORKER_NAME,
    should_continue: Callable[[], bool] | None = None,
) -> dict[str, int]:
    fresh_window = int(SATELLITE_V2_METEOSAT_PREFETCH_FRESH_WINDOW_SECONDS)
    if not force and is_cache_fresh(worker_name, fresh_window):
        print(f"[{worker_name}] skipped: fresh sentinel within {fresh_window}s")
        return {"jobs": 0, "downloaded": 0, "errors": 0, "pruned": 0}

    selected_jobs = tuple(jobs or SATELLITE_V2_METEOSAT_PREFETCH_JOBS)
    newest_count = int(frames or SATELLITE_V2_METEOSAT_PREFETCH_FRAMES)
    backfill_count = int(
        SATELLITE_V2_METEOSAT_PREFETCH_BACKFILL if backfill is None else backfill
    )
    hours_value = int(hours or SATELLITE_V2_METEOSAT_PREFETCH_HOURS)
    keep_value = int(keep_hours or SATELLITE_V2_METEOSAT_PREFETCH_KEEP_HOURS)

    totals = {"jobs": 0, "downloaded": 0, "errors": 0, "pruned": 0}
    with _worker_lock(worker_name) as acquired:
        if not acquired:
            return totals
        run_start = time.perf_counter()
        for sat_id, sector in selected_jobs:
            if should_continue is not None and not should_continue():
                break
            try:
                stats = _prefetch_one_job(
                    worker_name,
                    sat_id,
                    sector,
                    SATELLITE_V2_METEOSAT_PREFETCH_CHANNEL,
                    newest_count,
                    backfill_count,
                    hours_value,
                    int(SATELLITE_V2_METEOSAT_PREFETCH_MAX_FRAMES),
                    keep_value,
                    should_continue,
                )
            except Exception as exc:
                totals["errors"] += 1
                print(
                    f"[{worker_name}] {sat_id}/{sector} job failed: "
                    f"{type(exc).__name__}: {exc}"
                )
                continue
            totals["jobs"] += 1
            totals["downloaded"] += int(stats.get("downloaded") or 0)
            totals["errors"] += int(stats.get("errors") or 0)
            totals["pruned"] += int(stats.get("pruned") or 0)
        # Mark complete even when nothing was missing; the run did its check.
        mark_run_complete(worker_name)
        print(
            f"[{worker_name}] complete jobs={totals['jobs']} "
            f"downloaded={totals['downloaded']} errors={totals['errors']} "
            f"pruned={totals['pruned']} "
            f"elapsed={_format_elapsed(time.perf_counter() - run_start)}"
        )
    return totals


def _parse_jobs(value: str | None) -> tuple[tuple[str, str], ...] | None:
    if not value:
        return None
    jobs: list[tuple[str, str]] = []
    for raw in value.split(","):
        if ":" not in raw:
            raise ValueError("--jobs entries must be formatted as sat_id:sector")
        sat_id, sector = (part.strip() for part in raw.split(":", 1))
        jobs.append((normalize_sat_id(sat_id), normalize_sector(sector)))
    return tuple(jobs)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prefetch Meteosat source frames into the Satellite v2 cache"
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--log-to-file", action="store_true")
    parser.add_argument("--jobs", help="Comma list of sat_id:sector entries")
    parser.add_argument("--frames", type=int, default=None, help="Newest frames per run")
    parser.add_argument(
        "--backfill", type=int, default=None, help="Oldest missing frames per run"
    )
    parser.add_argument("--hours", type=int, default=None, help="Lookback window")
    parser.add_argument("--keep-hours", type=int, default=None, help="Prune window")
    args = parser.parse_args()
    if args.log_to_file:
        redirect_stdio_to_log(_WORKER_NAME)
    run_satellite_v2_meteosat_prefetch_worker(
        force=args.force,
        jobs=_parse_jobs(args.jobs),
        frames=args.frames,
        backfill=args.backfill,
        hours=args.hours,
        keep_hours=args.keep_hours,
    )


if __name__ == "__main__":
    main()
