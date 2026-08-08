"""Application startup and shutdown orchestration."""

import logging
import time as _time

from satellite_v2 import service as satellite_v2_service

_LOGGER = logging.getLogger(__name__)


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
    startup_events = []

    # 1. Validate the live Radar NODD provider import.
    _t0 = _time.time()
    try:
        from radar import radar_nodd_utils as _radar_nodd

        del _radar_nodd
        startup_events.append(("[OK] NODD modules", _time.time() - _t0))
    except Exception as import_error:
        startup_events.append(
            (
                f"[WARN] NODD modules unavailable ({type(import_error).__name__})",
                _time.time() - _t0,
            )
        )

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

    # 3. Health is based on application/coordinator/source/cache state, not
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

    total_time = 0
    for event_msg, elapsed in startup_events:
        total_time += elapsed
        _LOGGER.info("Startup event=%s elapsed_seconds=%.2f", event_msg, elapsed)
    _LOGGER.info("Startup complete elapsed_seconds=%.2f", total_time)


def shutdown_runtime() -> None:
    """Shut down application-owned coordination and live render pools."""
    try:
        satellite_v2_service.shutdown_live_tile_pool()
    except Exception:
        pass
    try:
        from app_core.refresh_coordinator import get_refresh_coordinator

        get_refresh_coordinator().stop(wait=True)
    except Exception:
        pass
