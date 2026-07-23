"""Application startup and shutdown orchestration."""

from io import StringIO
import sys
import time as _time
from typing import Callable

from satellite_v2 import service as satellite_v2_service

_stderr_cap = StringIO()
sys.stderr, _real_stderr = _stderr_cap, sys.stderr
from radar import radar_utils as radar_thredds_utils  # noqa: E402

sys.stderr = _real_stderr
del _stderr_cap, _real_stderr

USING_NODD = False
radar_utils = None
_SCHEDULER_AVAILABLE = False
start_scheduler: Callable[[], None] | None = None
stop_scheduler: Callable[[], None] | None = None


def is_using_nodd() -> bool:
    return USING_NODD


def initialize_runtime() -> None:
    """Load optional runtime modules at startup with timing."""
    global USING_NODD, radar_utils
    global _SCHEDULER_AVAILABLE
    global start_scheduler, stop_scheduler

    startup_events = []

    # 1. Initialize NODD modules
    _t0 = _time.time()
    old_stderr = sys.stderr
    try:
        sys.stderr = StringIO()

        from radar import radar_nodd_utils as radar_nodd

        sys.stderr = old_stderr

        radar_utils = radar_nodd
        USING_NODD = True
        startup_events.append(("[OK] NODD modules", _time.time() - _t0))
    except Exception as import_error:
        sys.stderr = old_stderr
        radar_utils = radar_thredds_utils
        startup_events.append(
            (f"[WARN] NODD fallback to THREDDS: {import_error}", _time.time() - _t0)
        )

    # 2. Start the application-owned refresh coordinator. Phase 1 supports one
    # application process until persistent cross-process leases are available.
    _t0 = _time.time()
    from app_core.refresh_coordinator import (
        get_refresh_coordinator,
        validate_single_process_configuration,
    )
    from workers.cache_cleanup_worker import run_cache_cleanup_worker

    validate_single_process_configuration()
    refresh_coordinator = get_refresh_coordinator()
    refresh_coordinator.register_periodic(
        key=("maintenance", "cache-cleanup"),
        provider="local",
        interval_seconds=6 * 60 * 60,
        initial_delay_seconds=60,
        function=run_cache_cleanup_worker,
    )
    refresh_coordinator.start()
    startup_events.append(
        ("[OK] Refresh coordinator (single process)", _time.time() - _t0)
    )

    # 3. Initialize Background Scheduler
    _t0 = _time.time()
    try:
        from workers.scheduler import start_scheduler as _start, stop_scheduler as _stop

        start_scheduler = _start
        stop_scheduler = _stop
        _SCHEDULER_AVAILABLE = True
        startup_events.append(("[OK] APScheduler loaded", _time.time() - _t0))
    except Exception as sched_err:
        startup_events.append(
            (f"[WARN] APScheduler unavailable: {sched_err}", _time.time() - _t0)
        )

    # 4. Start background workers (scheduler returns immediately; first ticks
    # run in background threads via APScheduler `next_run_time=now`)
    _t0 = _time.time()
    if _SCHEDULER_AVAILABLE and start_scheduler is not None:
        try:
            start_scheduler()
            startup_events.append(
                ("[OK] Background workers scheduled", _time.time() - _t0)
            )
        except Exception as e:
            startup_events.append(
                (f"[WARN] Background workers failed: {e}", _time.time() - _t0)
            )

    # 5. Cache freshness health check. The OS-level Task Scheduler is the
    # default source of truth for cache refresh; warn loudly if any sentinel
    # is missing or stale so the operator knows to check `tools/install_tasks.ps1`.
    _t0 = _time.time()
    try:
        from workers._freshness import check_cache_freshness

        warnings = check_cache_freshness()
        if warnings:
            for w in warnings:
                print(f"[WARN] {w}")
            startup_events.append(
                (f"[WARN] {len(warnings)} cache freshness issue(s)", _time.time() - _t0)
            )
        else:
            startup_events.append(
                ("[OK] All caches fresh (OS task healthy)", _time.time() - _t0)
            )
    except Exception as e:
        startup_events.append(
            (f"[WARN] Cache freshness check failed: {e}", _time.time() - _t0)
        )

    print("\n" + "=" * 70)
    print("STARTUP SEQUENCE")
    print("=" * 70)
    total_time = 0
    for event_msg, elapsed in startup_events:
        total_time += elapsed
        print(f"{event_msg:<50} {elapsed:.2f}s")
    print("=" * 70)
    print(f"{'TOTAL STARTUP TIME':<50} {total_time:.2f}s")
    print("=" * 70 + "\n")


def shutdown_runtime() -> None:
    """Shut down background schedulers and live render pools on app exit."""
    try:
        satellite_v2_service.shutdown_live_tile_pool()
    except Exception:
        pass
    if _SCHEDULER_AVAILABLE and stop_scheduler is not None:
        try:
            stop_scheduler()
        except Exception:
            pass
    try:
        from app_core.refresh_coordinator import get_refresh_coordinator

        get_refresh_coordinator().stop(wait=True)
    except Exception:
        pass
