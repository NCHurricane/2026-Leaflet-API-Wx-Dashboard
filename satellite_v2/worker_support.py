"""Shared lifecycle helpers for Satellite v2 worker entry points."""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from config.satellite_v2_config import normalize_sat_id, normalize_sector

_BASE_DIR = Path(__file__).resolve().parent.parent


def resolve_cache_root() -> Path:
    configured = os.environ.get("WX_DASHBOARD_CACHE_ROOT") or os.environ.get(
        "WX_SATELLITE_V2_CACHE_ROOT"
    )
    return Path(configured or (_BASE_DIR / "cache")).expanduser().resolve()


def format_elapsed(seconds: float) -> str:
    total = max(0, int(round(float(seconds))))
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m {secs}s"


def parse_jobs(value: str | None) -> tuple[tuple[str, str], ...] | None:
    if not value:
        return None
    jobs: list[tuple[str, str]] = []
    for raw in value.split(","):
        if ":" not in raw:
            raise ValueError("--jobs entries must be formatted as sat_id:sector")
        sat_id, sector = (part.strip() for part in raw.split(":", 1))
        jobs.append((normalize_sat_id(sat_id), normalize_sector(sector)))
    return tuple(jobs)


@contextmanager
def worker_lock(worker_name: str):
    state_dir = resolve_cache_root() / ".workers"
    state_dir.mkdir(parents=True, exist_ok=True)
    lock_path = state_dir / f"{worker_name}.lock"
    try:
        descriptor = os.open(
            str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY
        )
    except FileExistsError:
        logging.getLogger(__name__).info(
            "Satellite worker %s skipped; lock exists at %s",
            worker_name,
            lock_path,
        )
        yield False
        return
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(datetime.now(timezone.utc).isoformat())
            handle.write("\n")
        yield True
    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass
