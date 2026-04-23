"""Cache-staleness gate shared by all background workers.

Each worker writes a small *sentinel touch file* (zero bytes, just a timestamp
in its mtime) after a successful run. Subsequent invocations check that
sentinel before doing any work. If the sentinel was updated within the
freshness window, the run is skipped.

This lets the same worker function be called by both:
  * The in-process APScheduler tick (default fallback)
  * An external OS scheduler (Task Scheduler / launchd / cron)

Whichever fires first refreshes the cache; the other notices the fresh
sentinel and exits immediately. No double fetches, no extra network load.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

# Repo root → cache/.workers/<name>.last_run sentinel files
_SENTINEL_DIR = (
    Path(__file__).resolve().parent.parent / "cache" / ".workers"
)


def _sentinel_path(worker_name: str) -> Path:
    return _SENTINEL_DIR / f"{worker_name}.last_run"


def is_cache_fresh(worker_name: str, max_age_seconds: float) -> bool:
    """Return True when the sentinel file is younger than *max_age_seconds*."""
    if max_age_seconds <= 0:
        return False
    sentinel = _sentinel_path(worker_name)
    if not sentinel.exists():
        return False
    age = time.time() - sentinel.stat().st_mtime
    return age < max_age_seconds


def mark_run_complete(worker_name: str) -> None:
    """Touch the sentinel file so subsequent gates see a fresh timestamp."""
    _SENTINEL_DIR.mkdir(parents=True, exist_ok=True)
    sentinel = _sentinel_path(worker_name)
    sentinel.touch(exist_ok=True)
    # Force mtime to "now" even if the file already existed (touch on some
    # filesystems is a no-op without this).
    os.utime(sentinel, None)
