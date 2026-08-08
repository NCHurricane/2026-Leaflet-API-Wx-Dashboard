"""Application startup and shutdown orchestration."""

from io import StringIO
import sys
import time as _time
from typing import Callable

from satellite_v2 import service as satellite_v2_service

_SCHEDULER_AVAILABLE = False
start_scheduler: Callable[[], None] | None = None
stop_scheduler: Callable[[], None] | None = None


def _start_application_maintenance(refresh_coordinator) -> None:
    """Register task-free lifecycle maintenance and start the coordinator."""
    from workers.cache_cleanup_worker import run_cache_cleanup_worker

    refresh_coordinator.register_periodic(
        key=("maintenance", "cache-cleanup"),
        provider="local",
        interval_seconds=6 * 60 * 60,
        initial_delay_seconds=60,
        function=run_cache_cleanup_worker,
    )
    refresh_coordinator.start()


def initialize_runtime() -> None:
    """Load optional runtime modules at startup with timing."""
    global _SCHEDULER_AVAILABLE
    global start_scheduler, stop_scheduler

    startup_events = []

    # 1. Validate the live Radar NODD provider import.
    _t0 = _time.time()
    old_stderr = sys.stderr
    try:
        sys.stderr = StringIO()

        from radar import radar_nodd_utils as _radar_nodd

        del _radar_nodd
        startup_events.append(("[OK] NODD modules", _time.time() - _t0))
    except Exception as import_error:
        startup_events.append(
            (f"[WARN] NODD modules unavailable: {import_error}", _time.time() - _t0)
        )
    finally:
        sys.stderr = old_stderr

    # 2. Start the application-owned refresh coordinator. Phase 1 supports one
    # application process until persistent cross-process leases are available.
    _t0 = _time.time()
    from app_core.refresh_coordinator import (
        get_refresh_coordinator,
        validate_single_process_configuration,
    )
    validate_single_process_configuration()
    refresh_coordinator = get_refresh_coordinator()
    _start_application_maintenance(refresh_coordinator)
    startup_events.append(
        ("[OK] Refresh coordinator (single process)", _time.time() - _t0)
    )

    # 3. Load the stable worker-lifecycle compatibility hooks. Phase 8 removes
    # broad fixed worker registration; refresh and maintenance are coordinator-owned.
    _t0 = _time.time()
    try:
        from workers.scheduler import start_scheduler as _start, stop_scheduler as _stop

        start_scheduler = _start
        stop_scheduler = _stop
        _SCHEDULER_AVAILABLE = True
        startup_events.append(
            ("[OK] Application worker lifecycle loaded", _time.time() - _t0)
        )
    except Exception as sched_err:
        startup_events.append(
            (f"[WARN] Worker lifecycle unavailable: {sched_err}", _time.time() - _t0)
        )

    # 4. Start the compatibility hook. It registers no broad worker schedule.
    _t0 = _time.time()
    if _SCHEDULER_AVAILABLE and start_scheduler is not None:
        try:
            start_scheduler()
            startup_events.append(
                ("[OK] Request-driven workers active", _time.time() - _t0)
            )
        except Exception as e:
            startup_events.append(
                (f"[WARN] Worker lifecycle failed: {e}", _time.time() - _t0)
            )

    # 5. Health is based on application/coordinator/source/cache state, not
    # task-sentinel timestamps. Detailed credential-safe state is exposed at
    # /api/health/coordinator.
    coordinator_snapshot = refresh_coordinator.snapshot()
    maintenance_registered = ["maintenance", "cache-cleanup"] in (
        coordinator_snapshot.get("periodic_jobs") or []
    )
    if coordinator_snapshot.get("running") and maintenance_registered:
        startup_events.append(
            ("[OK] Coordinator/source/cache health model", 0.0)
        )
    else:
        startup_events.append(
            ("[WARN] Coordinator maintenance health degraded", 0.0)
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
