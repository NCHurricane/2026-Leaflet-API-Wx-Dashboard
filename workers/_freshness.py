"""Cache-staleness gate shared by all background workers.

Each worker writes a small *sentinel touch file* (zero bytes, just a timestamp
in its mtime) after a successful run. Subsequent invocations check that
sentinel before doing any work. If the sentinel was updated within the
freshness window, the run is skipped.

These sentinels remain a local cadence guard for one-off legacy worker CLIs.
They are not the application health model and do not coordinate optional
warmers. Application health and refresh ownership live in
``app_core.refresh_coordinator``.
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


# cache/logs/scheduled/<name>.log destination for headless task runs.
_LOG_DIR = Path(__file__).resolve().parent.parent / "cache" / "logs" / "scheduled"


def redirect_stdio_to_log(log_name: str) -> None:
    """Redirect stdout/stderr into ``cache/logs/scheduled/<log_name>.log`` (append).

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
