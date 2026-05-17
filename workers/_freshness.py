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
_SENTINEL_DIR = Path(__file__).resolve().parent.parent / "cache" / ".workers"


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


# Repo root → logs/scheduled/<name>.log destination for headless task runs.
_LOG_DIR = Path(__file__).resolve().parent.parent / "logs" / "scheduled"


def redirect_stdio_to_log(log_name: str) -> None:
    """Redirect stdout/stderr into ``logs/scheduled/<log_name>.log`` (append).

    Intended for use only when the worker is launched headlessly by Task
    Scheduler via ``pythonw.exe`` (no console attached). A timestamped header
    is written first so the log boundary between runs is obvious.

    Failures are swallowed and reported via a fallback file ``_bootstrap.log``
    next to the intended log, because we have no console to print to.
    """
    import sys
    from datetime import datetime

    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_path = _LOG_DIR / f"{log_name}.log"
        # Line-buffered append so external tail-watchers see output promptly.
        stream = open(log_path, "a", buffering=1, encoding="utf-8")
        stream.write(
            f"\n=== {datetime.now().isoformat(timespec='seconds')} {log_name} ===\n"
        )
        sys.stdout = stream
        sys.stderr = stream
    except Exception as exc:  # pragma: no cover - last-ditch diagnostics
        try:
            fallback = _LOG_DIR / "_bootstrap.log"
            fallback.parent.mkdir(parents=True, exist_ok=True)
            with open(fallback, "a", encoding="utf-8") as fb:
                fb.write(
                    f"{datetime.now().isoformat()} redirect_stdio_to_log({log_name!r}) failed: {exc}\n"
                )
        except Exception:
            pass


# Expected sentinels and their max acceptable age (seconds). Used by the
# server's startup health check to flag missing or stale OS-task output.
# A sentinel older than its threshold suggests the corresponding
# Wx-Dashboard-* scheduled task is broken / disabled / not yet installed.
_HEALTH_THRESHOLDS = {
    "alerts": 5 * 60,  # task fires every 1 min
    "spc": 60 * 60,  # task fires every 30 min
    "surface": 60 * 60,  # task fires every 30 min
    "rtma_hourly": 2 * 60 * 60,  # task fires hourly at :05
    "rtma_rapid_update": 30 * 60,  # task fires every 15 min starting :20
    "satellite_v2": 30 * 60,  # task fires every 15 min
    "satellite_v2_meso": 12 * 60,  # task fires every 5 min
    "satellite_v2_light_composites": 15 * 60,  # task fires every 5 min
    "satellite_v2_geocolor": 25 * 60,  # task fires every 10 min
    # MRMS sentinels are per-product; we check whichever exists. See below.
}
_MRMS_THRESHOLD = 30 * 60  # task fires every 15 min


def check_cache_freshness() -> list[str]:
    """Return a list of human-readable warnings about stale or missing sentinels.

    Intended to be called once during server startup so the operator gets a
    visible heads-up when the OS Task Scheduler isn't keeping the caches
    warm. Returns an empty list when everything looks healthy.
    """
    warnings: list[str] = []
    now = time.time()

    for name, max_age in _HEALTH_THRESHOLDS.items():
        sentinel = _sentinel_path(name)
        if not sentinel.exists():
            warnings.append(
                f"No sentinel for '{name}' \u2014 is the Wx-Dashboard-{name.capitalize()} "
                "task installed and has it run at least once?"
            )
            continue
        age = now - sentinel.stat().st_mtime
        if age > max_age:
            warnings.append(
                f"Cache '{name}' is {int(age / 60)} min stale "
                f"(threshold {max_age // 60} min) \u2014 check Task Scheduler."
            )

    # MRMS: check the newest of any mrms_* sentinel, since only one product is
    # active at a time and the active product changes by user toggle.
    mrms_sentinels = (
        list(_SENTINEL_DIR.glob("mrms_*.last_run")) if _SENTINEL_DIR.exists() else []
    )
    if not mrms_sentinels:
        warnings.append(
            "No MRMS sentinel found \u2014 is the Wx-Dashboard-MRMS task installed "
            "and has it run at least once?"
        )
    else:
        newest = max(s.stat().st_mtime for s in mrms_sentinels)
        age = now - newest
        if age > _MRMS_THRESHOLD:
            warnings.append(
                f"MRMS cache is {int(age / 60)} min stale "
                f"(threshold {_MRMS_THRESHOLD // 60} min) \u2014 check Task Scheduler."
            )

    return warnings
