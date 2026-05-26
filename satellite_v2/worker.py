"""Satellite v2 catalog worker.

This first implementation publishes immutable source-frame catalogs without
using the legacy satellite utilities. Tile rendering is intentionally isolated
for the next implementation step.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import time
from typing import Iterable

from config.satellite_v2_config import (
    SATELLITE_V2_DEFAULT_MAX_FRAMES,
    SATELLITE_V2_WORKER_BASELINE_FRAMES,
    SATELLITE_V2_WORKER_CURRENT_DEEP_JOBS_PER_RUN,
    SATELLITE_V2_WORKER_CURRENT_SECTORS,
    SATELLITE_V2_WORKER_MESO_DEEP_JOBS_PER_RUN,
    SATELLITE_V2_WORKER_MESO_PREWARM_FRAMES,
    SATELLITE_V2_WORKER_MESO_SECTORS,
    SATELLITE_V2_WORKER_PREWARM_FRAMES,
    SATELLITE_V2_WORKER_PRIORITY_PRODUCTS,
    SATELLITE_V2_WORKER_PRODUCTS,
    SATELLITE_V2_WORKER_PROFILES,
    SATELLITE_V2_WORKER_SATELLITES,
    normalize_channel,
    normalize_sat_id,
    satellite_v2_worker_tile_workers,
    worker_baseline_zooms_for_sector,
    worker_zooms_for_product,
)
from satellite_v2.catalog import build_catalog
from satellite_v2.tiler import warm_frame_tiles_from_canvas
from workers._freshness import is_cache_fresh, mark_run_complete, redirect_stdio_to_log

_BASE_DIR = Path(__file__).resolve().parent.parent


def _resolve_cache_root() -> Path:
    configured = os.environ.get("WX_DASHBOARD_CACHE_ROOT") or os.environ.get(
        "WX_SATELLITE_V2_CACHE_ROOT"
    )
    return Path(configured or (_BASE_DIR / "cache")).expanduser().resolve()


_CACHE_ROOT = str(_resolve_cache_root())
_WORKER_STATE_DIR = Path(_CACHE_ROOT) / ".workers"
_FRESH_WINDOW_SECONDS = 10 * 60


def _ordered_unique(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        key = str(value)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(key)
    return tuple(ordered)


def _profile_config(profile: str | None) -> dict:
    profile_key = str(profile or "full").strip().lower() or "full"
    if profile_key not in SATELLITE_V2_WORKER_PROFILES:
        valid = ", ".join(sorted(SATELLITE_V2_WORKER_PROFILES))
        raise ValueError(
            f"Unknown Satellite v2 worker profile '{profile}'. Use one of: {valid}."
        )
    return SATELLITE_V2_WORKER_PROFILES[profile_key]


def _profile_key(profile: str | None) -> str:
    return str(profile or "full").strip().lower() or "full"


def _ordered_products(profile: str | None = None) -> tuple[str, ...]:
    products = tuple(
        str(value)
        for value in _profile_config(profile).get("products")
        or SATELLITE_V2_WORKER_PRODUCTS
    )
    product_set = {normalize_channel(product) for product in products}
    priority_products = tuple(
        product
        for product in SATELLITE_V2_WORKER_PRIORITY_PRODUCTS
        if normalize_channel(product) in product_set
    )
    return _ordered_unique((*priority_products, *products))


def _ordered_satellites(profile: str | None = None) -> tuple[str, ...]:
    satellites = tuple(
        str(value)
        for value in _profile_config(profile).get("satellites")
        or SATELLITE_V2_WORKER_SATELLITES
    )
    return _ordered_unique(("goes19", *satellites))


def _ordered_sectors(meso: bool, profile: str | None = None) -> tuple[str, ...]:
    configured = tuple(
        str(value) for value in (_profile_config(profile).get("sectors") or ())
    )
    if configured:
        return _ordered_unique(configured)
    if meso:
        return _ordered_unique(SATELLITE_V2_WORKER_MESO_SECTORS)
    # FULLDISK intentionally excluded — handled on-demand by live tile renderer.
    return _ordered_unique(("CONUS", *SATELLITE_V2_WORKER_CURRENT_SECTORS))


def _worker_jobs(meso: bool, profile: str | None = None) -> list[tuple[str, str, str]]:
    config = _profile_config(profile)
    excluded = {
        (normalize_sat_id(sat_id), normalize_channel(channel))
        for sat_id, channel in config.get("exclude_jobs") or ()
    }
    jobs = [
        (sat_id, sector, channel)
        for sat_id in _ordered_satellites(profile)
        for sector in _ordered_sectors(meso, profile)
        for channel in _ordered_products(profile)
    ]
    return [
        (sat_id, sector, channel)
        for sat_id, sector, channel in jobs
        if (normalize_sat_id(sat_id), normalize_channel(channel)) not in excluded
    ]


def _deep_state_path(worker_name: str) -> Path:
    return _WORKER_STATE_DIR / f"{worker_name}.deep_index.json"


def _load_deep_index(worker_name: str, job_count: int) -> int:
    if job_count <= 0:
        return 0
    path = _deep_state_path(worker_name)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return max(0, int(payload.get("next_index") or 0)) % job_count
    except (FileNotFoundError, json.JSONDecodeError, OSError, TypeError, ValueError):
        return 0


def _save_deep_index(worker_name: str, next_index: int) -> None:
    _WORKER_STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = _deep_state_path(worker_name)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    payload = {"next_index": max(0, int(next_index))}
    tmp_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(tmp_path, path)


def _resume_state_path(worker_name: str) -> Path:
    return _WORKER_STATE_DIR / f"{worker_name}.rolling_resume.json"


def _lock_path(worker_name: str) -> Path:
    return _WORKER_STATE_DIR / f"{worker_name}.lock"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _job_key(sat_id: str, sector: str, channel: str) -> str:
    return f"{normalize_sat_id(sat_id)}|{sector}|{normalize_channel(channel)}"


def _load_resume_state(worker_name: str) -> dict:
    path = _resume_state_path(worker_name)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload
    except (FileNotFoundError, json.JSONDecodeError, OSError, TypeError, ValueError):
        pass
    return {"next_job_index": 0, "job_offsets": {}}


def _save_resume_state(worker_name: str, payload: dict) -> None:
    _WORKER_STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = _resume_state_path(worker_name)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    state = dict(payload)
    state["updated_at"] = _now_utc().isoformat().replace("+00:00", "Z")
    tmp_path.write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp_path, path)


@contextmanager
def _run_lock(worker_name: str, enabled: bool = True, stale_seconds: int = 6 * 3600):
    if not enabled:
        yield True
        return

    _WORKER_STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = _lock_path(worker_name)
    if path.exists():
        age_seconds = _now_utc().timestamp() - path.stat().st_mtime
        if age_seconds > max(60, int(stale_seconds)):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass

    fd: int | None = None
    acquired = False
    try:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            print(f"[{worker_name}] Overlap lock present at {path}; skipping run")
            yield False
            return

        payload = {
            "pid": os.getpid(),
            "worker": worker_name,
            "started_at": _now_utc().isoformat().replace("+00:00", "Z"),
        }
        os.write(fd, (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8"))
        acquired = True
        yield True
    finally:
        if fd is not None:
            os.close(fd)
        if acquired:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass


def _deadline_from_now(minutes: int, buffer_seconds: int) -> datetime:
    return _now_utc() + timedelta(
        minutes=max(1, int(minutes)),
        seconds=-max(0, int(buffer_seconds)),
    )


def _deadline_reached(deadline_utc: datetime | None) -> bool:
    return bool(deadline_utc and _now_utc() >= deadline_utc)


def _rotating_jobs(
    jobs: list[tuple[str, str, str]],
    start_index: int,
    count: int,
) -> tuple[list[tuple[str, str, str]], int]:
    if not jobs or count <= 0:
        return [], start_index
    take = min(len(jobs), int(count))
    selected = [jobs[(start_index + offset) % len(jobs)] for offset in range(take)]
    next_index = (start_index + take) % len(jobs)
    return selected, next_index


def _mark_profile_run_complete(
    worker_name: str, state_name: str, profile_key: str
) -> None:
    mark_run_complete(state_name)
    if (
        profile_key in {"local-primary", "goes19-freshness"}
        and state_name != worker_name
    ):
        mark_run_complete(worker_name)


def _format_elapsed(seconds: float) -> str:
    total = max(0, int(round(float(seconds))))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours}h {minutes}m {secs}s"


def _warm_job(
    worker_name: str,
    sat_id: str,
    sector: str,
    channel: str,
    frame_count: int,
    zooms: tuple[int, ...],
    phase: str,
    tile_workers: int,
) -> dict[str, int]:
    catalog_start = time.perf_counter()
    payload = build_catalog(
        cache_root=_CACHE_ROOT,
        sat_id=sat_id,
        sector=sector,
        channel_key=channel,
        hours=3,
        max_frames=SATELLITE_V2_DEFAULT_MAX_FRAMES,
    )
    catalog_elapsed = time.perf_counter() - catalog_start
    frames = payload.get("frames") or []
    total = {"cataloged": len(frames), "rendered": 0, "skipped": 0, "errors": 0}
    print(
        f"[{worker_name}] {phase} {sat_id}/{sector}/{channel}: "
        f"cataloged {len(frames)} frames, warming {min(len(frames), frame_count)} "
        f"frames at zooms {','.join(str(value) for value in zooms)} "
        f"with {tile_workers} zoom workers (canvas mode), "
        f"catalog step {_format_elapsed(catalog_elapsed)}"
    )

    # Prioritize the newest frames first so the latest dashboard selections
    # become viewable before older tail frames finish warming.
    for frame in reversed(frames[-frame_count:]):
        frame_start = time.perf_counter()
        stats = warm_frame_tiles_from_canvas(
            cache_root=_CACHE_ROOT,
            sat_id=sat_id,
            sector=sector,
            channel_key=channel,
            frame=frame,
            zooms=zooms,
            render_workers=tile_workers,
        )
        frame_elapsed = time.perf_counter() - frame_start
        total["rendered"] += int(stats.get("rendered") or 0)
        total["skipped"] += int(stats.get("skipped") or 0)
        total["errors"] += int(stats.get("errors") or 0)
        print(
            f"[{worker_name}] {phase} {sat_id}/{sector}/{channel}/{frame.get('frame_key')}: "
            f"rendered={stats.get('rendered')} skipped={stats.get('skipped')} "
            f"errors={stats.get('errors')} elapsed={_format_elapsed(frame_elapsed)}"
        )

    refresh_start = time.perf_counter()
    build_catalog(
        cache_root=_CACHE_ROOT,
        sat_id=sat_id,
        sector=sector,
        channel_key=channel,
        hours=3,
        max_frames=SATELLITE_V2_DEFAULT_MAX_FRAMES,
    )
    refresh_elapsed = time.perf_counter() - refresh_start
    print(
        f"[{worker_name}] {phase} {sat_id}/{sector}/{channel}: "
        f"catalog refresh step {_format_elapsed(refresh_elapsed)}"
    )
    return total


def _run_warm_jobs(
    worker_name: str,
    jobs: list[tuple[str, str, str]],
    frame_count: int,
    phase: str,
    baseline: bool = False,
    tile_workers: int = 1,
) -> dict[str, int]:
    totals = {"cataloged": 0, "rendered": 0, "skipped": 0, "errors": 0, "jobs": 0}
    for sat_id, sector, channel in jobs:
        zooms = (
            worker_baseline_zooms_for_sector(sector)
            if baseline
            else worker_zooms_for_product(sector, channel)
        )
        job_start = time.perf_counter()
        try:
            stats = _warm_job(
                worker_name,
                sat_id,
                sector,
                channel,
                frame_count,
                zooms,
                phase,
                tile_workers,
            )
        except Exception as exc:
            totals["errors"] += 1
            job_elapsed = time.perf_counter() - job_start
            print(
                f"[{worker_name}] {phase} {sat_id}/{sector}/{channel}: "
                f"ERROR {exc} elapsed={_format_elapsed(job_elapsed)}"
            )
            continue
        job_elapsed = time.perf_counter() - job_start
        totals["cataloged"] += int(stats.get("cataloged") or 0)
        totals["rendered"] += int(stats.get("rendered") or 0)
        totals["skipped"] += int(stats.get("skipped") or 0)
        totals["errors"] += int(stats.get("errors") or 0)
        totals["jobs"] += 1
        print(
            f"[{worker_name}] {phase} {sat_id}/{sector}/{channel}: "
            f"job elapsed={_format_elapsed(job_elapsed)}"
        )
    return totals


def _warm_job_rolling(
    worker_name: str,
    sat_id: str,
    sector: str,
    channel: str,
    zooms: tuple[int, ...],
    tile_workers: int,
    recency_hours: int,
    latest_frames_per_job: int,
    start_offset: int,
    deadline_utc: datetime | None,
) -> tuple[dict[str, int], int, bool]:
    payload = build_catalog(
        cache_root=_CACHE_ROOT,
        sat_id=sat_id,
        sector=sector,
        channel_key=channel,
        hours=max(1, int(recency_hours)),
        max_frames=SATELLITE_V2_DEFAULT_MAX_FRAMES,
    )
    frames = payload.get("frames") or []
    newest_first = list(reversed(frames))
    totals = {
        "cataloged": len(frames),
        "rendered": 0,
        "skipped": 0,
        "errors": 0,
        "frames_processed": 0,
    }

    guaranteed_latest = min(max(0, int(latest_frames_per_job)), len(newest_first))
    print(
        f"[{worker_name}] rolling {sat_id}/{sector}/{channel}: "
        f"cataloged {len(frames)} frames, latest_first={guaranteed_latest}, "
        f"resume_offset={max(0, int(start_offset))}"
    )

    for idx in range(guaranteed_latest):
        if _deadline_reached(deadline_utc):
            return totals, max(start_offset, guaranteed_latest), True
        frame = newest_first[idx]
        stats = warm_frame_tiles_from_canvas(
            cache_root=_CACHE_ROOT,
            sat_id=sat_id,
            sector=sector,
            channel_key=channel,
            frame=frame,
            zooms=zooms,
            render_workers=tile_workers,
        )
        totals["rendered"] += int(stats.get("rendered") or 0)
        totals["skipped"] += int(stats.get("skipped") or 0)
        totals["errors"] += int(stats.get("errors") or 0)
        totals["frames_processed"] += 1

    # Refresh catalog metadata after warming.  Use a wider hours window (3h)
    # so the on-disk catalog satisfies get_catalog cache checks for the 1h,
    # 2h, and 3h UI lookback values without triggering a live S3 listing on
    # every user request.  _catalog_for_request trims the result to whatever
    # hours the UI actually asked for.
    build_catalog(
        cache_root=_CACHE_ROOT,
        sat_id=sat_id,
        sector=sector,
        channel_key=channel,
        hours=3,
        max_frames=SATELLITE_V2_DEFAULT_MAX_FRAMES,
    )
    return totals, 0, False


def _run_rolling_lookback(
    worker_name: str,
    state_name: str,
    profile_key: str,
    jobs: list[tuple[str, str, str]],
    tile_workers: int,
    recency_hours: int,
    latest_frames_per_job: int,
    deadline_minutes: int,
    deadline_buffer_seconds: int,
) -> None:
    if not jobs:
        _mark_profile_run_complete(worker_name, state_name, profile_key)
        print(f"[{worker_name}] rolling complete: no jobs configured")
        return

    resume = _load_resume_state(state_name)
    next_job_index = int(resume.get("next_job_index") or 0) % len(jobs)
    job_offsets = {
        str(key): max(0, int(value))
        for key, value in dict(resume.get("job_offsets") or {}).items()
    }
    deadline_utc = _deadline_from_now(deadline_minutes, deadline_buffer_seconds)
    run_start_index = next_job_index
    ordered_jobs = [
        jobs[(next_job_index + offset) % len(jobs)] for offset in range(len(jobs))
    ]
    totals = {
        "cataloged": 0,
        "rendered": 0,
        "skipped": 0,
        "errors": 0,
        "jobs": 0,
        "frames_processed": 0,
    }
    stopped_by_deadline = False

    for offset, (sat_id, sector, channel) in enumerate(ordered_jobs):
        if _deadline_reached(deadline_utc):
            stopped_by_deadline = True
            next_job_index = (run_start_index + offset) % len(jobs)
            break

        zooms = worker_zooms_for_product(sector, channel)
        key = _job_key(sat_id, sector, channel)
        start_offset = int(job_offsets.get(key) or 0)
        rolling_job_start = time.perf_counter()
        try:
            stats, next_offset, hit_deadline = _warm_job_rolling(
                worker_name=worker_name,
                sat_id=sat_id,
                sector=sector,
                channel=channel,
                zooms=zooms,
                tile_workers=tile_workers,
                recency_hours=recency_hours,
                latest_frames_per_job=latest_frames_per_job,
                start_offset=start_offset,
                deadline_utc=deadline_utc,
            )
        except Exception as exc:
            totals["errors"] += 1
            rolling_job_elapsed = time.perf_counter() - rolling_job_start
            print(
                f"[{worker_name}] rolling {sat_id}/{sector}/{channel}: "
                f"ERROR {exc} elapsed={_format_elapsed(rolling_job_elapsed)}"
            )
            continue
        rolling_job_elapsed = time.perf_counter() - rolling_job_start

        totals["cataloged"] += int(stats.get("cataloged") or 0)
        totals["rendered"] += int(stats.get("rendered") or 0)
        totals["skipped"] += int(stats.get("skipped") or 0)
        totals["errors"] += int(stats.get("errors") or 0)
        totals["frames_processed"] += int(stats.get("frames_processed") or 0)
        totals["jobs"] += 1
        print(
            f"[{worker_name}] rolling {sat_id}/{sector}/{channel}: "
            f"job elapsed={_format_elapsed(rolling_job_elapsed)}"
        )
        job_offsets[key] = max(0, int(next_offset))

        if hit_deadline:
            stopped_by_deadline = True
            next_job_index = (run_start_index + offset) % len(jobs)
            _save_resume_state(
                state_name,
                {
                    "next_job_index": next_job_index,
                    "job_offsets": job_offsets,
                    "recency_hours": recency_hours,
                    "stopped_by_deadline": stopped_by_deadline,
                },
            )
            break

        next_job_index = (run_start_index + offset + 1) % len(jobs)
        _save_resume_state(
            state_name,
            {
                "next_job_index": next_job_index,
                "job_offsets": job_offsets,
                "recency_hours": recency_hours,
                "stopped_by_deadline": False,
            },
        )

    _save_resume_state(
        state_name,
        {
            "next_job_index": next_job_index,
            "job_offsets": job_offsets,
            "recency_hours": recency_hours,
            "stopped_by_deadline": stopped_by_deadline,
        },
    )
    _mark_profile_run_complete(worker_name, state_name, profile_key)
    print(
        f"[{worker_name}] rolling complete: jobs={totals['jobs']} "
        f"cataloged={totals['cataloged']} rendered={totals['rendered']} "
        f"skipped={totals['skipped']} errors={totals['errors']} "
        f"frames_processed={totals['frames_processed']} "
        f"stopped_by_deadline={stopped_by_deadline} "
        f"next_job_index={next_job_index}"
    )


def run_satellite_v2_worker(
    force: bool = False,
    meso: bool = False,
    tile_workers: int | None = None,
    profile: str | None = None,
    all_frames: bool = False,
    worker_name_override: str | None = None,
) -> None:
    run_start = time.perf_counter()
    profile_key = _profile_key(profile)
    profile_config = _profile_config(profile_key)
    worker_name = str(worker_name_override or "").strip() or (
        "satellite_v2_meso" if meso else "satellite_v2"
    )
    state_name = (
        worker_name
        if profile_key == "full" or worker_name_override
        else f"{worker_name}_{profile_key}"
    )
    if not force and is_cache_fresh(state_name, _FRESH_WINDOW_SECONDS):
        print(f"[{worker_name}] Cache fresh for profile {profile_key} - skipping run")
        return

    render_workers = satellite_v2_worker_tile_workers(meso, tile_workers)
    jobs = _worker_jobs(meso, profile_key)
    print(f"[{worker_name}] Profile: {profile_key}")
    print(f"[{worker_name}] Cache root: {_CACHE_ROOT}")
    print(f"[{worker_name}] Tile render workers: {render_workers}")
    print(f"[{worker_name}] Jobs: {len(jobs)}")

    lock_enabled = bool(profile_config.get("overlap_lock"))
    lock_stale_seconds = int(profile_config.get("lock_stale_seconds") or 6 * 3600)
    with _run_lock(
        state_name, enabled=lock_enabled, stale_seconds=lock_stale_seconds
    ) as acquired:
        if not acquired:
            return

        if profile_config.get("mode") == "rolling-lookback":
            rolling_start = time.perf_counter()
            recency_hours = max(1, int(profile_config.get("recency_hours") or 1))
            deadline_minutes = max(
                1, int(profile_config.get("deadline_minutes") or 115)
            )
            deadline_buffer_seconds = max(
                0, int(profile_config.get("deadline_buffer_seconds") or 180)
            )
            latest_frames_per_job = max(
                0, int(profile_config.get("latest_frames_per_job") or 1)
            )
            print(
                f"[{worker_name}] Rolling mode: recency_hours={recency_hours} "
                f"deadline_minutes={deadline_minutes} "
                f"deadline_buffer_seconds={deadline_buffer_seconds} "
                f"latest_frames_per_job={latest_frames_per_job}"
            )
            _run_rolling_lookback(
                worker_name=worker_name,
                state_name=state_name,
                profile_key=profile_key,
                jobs=jobs,
                tile_workers=render_workers,
                recency_hours=recency_hours,
                latest_frames_per_job=latest_frames_per_job,
                deadline_minutes=deadline_minutes,
                deadline_buffer_seconds=deadline_buffer_seconds,
            )
            print(
                f"[{worker_name}] rolling phase elapsed: "
                f"{_format_elapsed(time.perf_counter() - rolling_start)}"
            )
            print(
                f"[{worker_name}] run elapsed: "
                f"{_format_elapsed(time.perf_counter() - run_start)}"
            )
            return

        if all_frames:
            backfill_start = time.perf_counter()
            totals = _run_warm_jobs(
                worker_name,
                jobs,
                frame_count=SATELLITE_V2_DEFAULT_MAX_FRAMES,
                phase="backfill-all",
                baseline=False,
                tile_workers=render_workers,
            )
            _mark_profile_run_complete(worker_name, state_name, profile_key)
            print(
                f"[{worker_name}] backfill-all complete: jobs={totals['jobs']} "
                f"cataloged={totals['cataloged']} rendered={totals['rendered']} "
                f"skipped={totals['skipped']} errors={totals['errors']}"
            )
            print(
                f"[{worker_name}] backfill-all phase elapsed: "
                f"{_format_elapsed(time.perf_counter() - backfill_start)}"
            )
            print(
                f"[{worker_name}] run elapsed: "
                f"{_format_elapsed(time.perf_counter() - run_start)}"
            )
            return

        baseline_start = time.perf_counter()
        baseline_totals = _run_warm_jobs(
            worker_name,
            jobs,
            frame_count=SATELLITE_V2_WORKER_BASELINE_FRAMES,
            phase="baseline",
            baseline=True,
            tile_workers=render_workers,
        )
        _mark_profile_run_complete(worker_name, state_name, profile_key)
        print(
            f"[{worker_name}] baseline complete: jobs={baseline_totals['jobs']} "
            f"cataloged={baseline_totals['cataloged']} rendered={baseline_totals['rendered']} "
            f"skipped={baseline_totals['skipped']} errors={baseline_totals['errors']}"
        )
        print(
            f"[{worker_name}] baseline phase elapsed: "
            f"{_format_elapsed(time.perf_counter() - baseline_start)}"
        )

        deep_jobs_per_run = (
            SATELLITE_V2_WORKER_MESO_DEEP_JOBS_PER_RUN
            if meso
            else SATELLITE_V2_WORKER_CURRENT_DEEP_JOBS_PER_RUN
        )
        prewarm_frames = (
            SATELLITE_V2_WORKER_MESO_PREWARM_FRAMES
            if meso
            else SATELLITE_V2_WORKER_PREWARM_FRAMES
        )
        start_index = _load_deep_index(state_name, len(jobs))
        deep_jobs, next_index = _rotating_jobs(jobs, start_index, deep_jobs_per_run)
        deep_start = time.perf_counter()
        deep_totals = _run_warm_jobs(
            worker_name,
            deep_jobs,
            frame_count=prewarm_frames,
            phase="deep",
            baseline=False,
            tile_workers=render_workers,
        )
        _save_deep_index(state_name, next_index)
        _mark_profile_run_complete(worker_name, state_name, profile_key)
        print(
            f"[{worker_name}] complete: baseline_jobs={baseline_totals['jobs']} "
            f"deep_jobs={deep_totals['jobs']} next_deep_index={next_index} "
            f"cataloged={baseline_totals['cataloged'] + deep_totals['cataloged']} "
            f"rendered={baseline_totals['rendered'] + deep_totals['rendered']} "
            f"skipped={baseline_totals['skipped'] + deep_totals['skipped']} "
            f"errors={baseline_totals['errors'] + deep_totals['errors']}"
        )
        print(
            f"[{worker_name}] deep phase elapsed: "
            f"{_format_elapsed(time.perf_counter() - deep_start)}"
        )
        print(
            f"[{worker_name}] run elapsed: "
            f"{_format_elapsed(time.perf_counter() - run_start)}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh Satellite v2 catalogs")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--meso", action="store_true")
    parser.add_argument("--log-to-file", action="store_true")
    parser.add_argument(
        "--tile-workers",
        type=int,
        default=None,
        help="Override Satellite v2 tile render worker process count.",
    )
    parser.add_argument(
        "--profile",
        default="full",
        choices=sorted(SATELLITE_V2_WORKER_PROFILES),
        help="Satellite v2 worker ownership profile.",
    )
    parser.add_argument(
        "--all-frames",
        action="store_true",
        help="Warm every cataloged frame for selected jobs instead of baseline/deep rotation.",
    )
    args = parser.parse_args()
    if args.log_to_file:
        redirect_stdio_to_log("satellite_v2_meso" if args.meso else "satellite_v2")
    run_satellite_v2_worker(
        force=args.force,
        meso=args.meso,
        tile_workers=args.tile_workers,
        profile=args.profile,
        all_frames=args.all_frames,
    )


if __name__ == "__main__":
    main()
