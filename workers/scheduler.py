"""APScheduler configuration and (optional) job registration for background data workers.

Default mode: the application-owned refresh coordinator handles migrated
request-driven work and cache cleanup. The older broad fixed worker schedule is
disabled unless explicitly enabled. Unmigrated Windows tasks remain separate
legacy producers and are not coordinator-compatible.

To temporarily bring the in-process fallback scheduler back (e.g. while
developing on a machine without the OS tasks installed), set the env var
``WX_INPROC_WORKERS=1`` before launching the server.
"""

import os
from datetime import datetime, timezone, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor

# Use a multi-thread executor so the first ticks of each worker run in
# parallel rather than queueing behind one another.
_scheduler = BackgroundScheduler(
    timezone="UTC",
    executors={"default": ThreadPoolExecutor(max_workers=8)},
    job_defaults={"coalesce": True, "max_instances": 1},
)

# Opt-in flag to restore the legacy in-process behavior.
_INPROC_ENABLED = os.environ.get("WX_INPROC_WORKERS", "").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)


def start_scheduler() -> None:
    """Start the scheduler. Job registration is gated on ``WX_INPROC_WORKERS``.

    When the env var is unset (the default), no data-worker jobs are registered.
    The OS-level Windows Task Scheduler tasks installed by
    ``tools/install_tasks.ps1`` are responsible for keeping caches warm.

    When the env var is set to ``1`` / ``true``, the legacy APScheduler jobs
    are registered as a fallback. The shared sentinel-file gate
    (``workers/_freshness.py``) prevents double fetches if the OS tasks are
    also active.
    """
    if not _INPROC_ENABLED:
        print(
            "[scheduler] Legacy broad in-process schedule disabled (default). "
            "The refresh coordinator remains active for migrated request paths "
            "and cache cleanup. Set WX_INPROC_WORKERS=1 only for legacy "
            "fallback testing."
        )
        return

    from workers.alerts_worker import run_alerts_worker
    from workers.spc_worker import run_spc_worker
    from workers.wpc_worker import run_wpc_worker
    from workers.tropical_worker import run_tropical_worker
    from workers.tropical_archive_worker import refresh_current_season
    from workers.mrms_worker import run_mrms_worker
    from workers.radar_live_worker import run_radar_live_worker
    from workers.rtma_worker import run_rtma_hourly_worker, run_rtma_rapid_worker
    from satellite_v2.rapid_worker import run_satellite_v2_rapid_worker
    from satellite_v2.meteosat_prefetch_worker import (
        run_satellite_v2_meteosat_prefetch_worker,
    )
    from workers.surface_worker import run_surface_worker
    from workers.water_worker import run_water_worker
    from app_core.refresh_coordinator import get_refresh_coordinator

    refresh_coordinator = get_refresh_coordinator()

    def _submit_wpc_worker() -> None:
        refresh_coordinator.submit(
            key=("wpc", "legacy-catalog", "all"),
            provider="wpc",
            function=run_wpc_worker,
            lease_seconds=0,
        )

    def _submit_surface_worker() -> None:
        refresh_coordinator.submit(
            key=("surface", "gradients", "all"),
            provider="aviationweather",
            function=run_surface_worker,
            lease_seconds=0,
        )

    now = datetime.now(timezone.utc)

    _scheduler.add_job(
        run_alerts_worker,
        "interval",
        minutes=1,
        id="alerts_worker",
        max_instances=1,
        misfire_grace_time=60,
        next_run_time=now,
    )
    _scheduler.add_job(
        run_spc_worker,
        "interval",
        minutes=30,
        id="spc_worker",
        max_instances=1,
        misfire_grace_time=300,
        next_run_time=now,
    )
    _scheduler.add_job(
        run_tropical_worker,
        "interval",
        minutes=30,
        id="tropical_worker",
        max_instances=1,
        misfire_grace_time=300,
        next_run_time=now + timedelta(seconds=10),
    )
    _scheduler.add_job(
        _submit_wpc_worker,
        "interval",
        minutes=30,
        id="wpc_worker",
        max_instances=1,
        misfire_grace_time=300,
        next_run_time=now + timedelta(seconds=15),
    )
    # Keep the in-progress season in the Archive browser fresh from ATCF b-decks.
    # HURDAT2 only publishes after a season closes, so the full archive build is
    # lazy/immutable; this light refresh touches just the current year.
    _scheduler.add_job(
        refresh_current_season,
        "interval",
        hours=3,
        id="tropical_archive_refresh",
        max_instances=1,
        misfire_grace_time=600,
        next_run_time=now + timedelta(seconds=120),
    )
    # MRMS first tick deferred 30s so heavy S3 download doesn't compete with
    # the alerts/surface initial fetches for network bandwidth.
    _scheduler.add_job(
        run_mrms_worker,
        "interval",
        minutes=15,
        id="mrms_worker",
        max_instances=1,
        misfire_grace_time=60,
        next_run_time=now + timedelta(seconds=30),
    )
    _scheduler.add_job(
        run_radar_live_worker,
        "interval",
        minutes=5,
        id="radar_live_worker",
        max_instances=1,
        misfire_grace_time=60,
        next_run_time=now + timedelta(seconds=20),
    )
    _scheduler.add_job(
        run_rtma_hourly_worker,
        "interval",
        minutes=60,
        id="rtma_hourly_worker",
        max_instances=1,
        misfire_grace_time=180,
        next_run_time=now + timedelta(seconds=45),
    )
    _scheduler.add_job(
        run_rtma_rapid_worker,
        "interval",
        minutes=15,
        id="rtma_rapid_worker",
        max_instances=1,
        misfire_grace_time=60,
        next_run_time=now + timedelta(seconds=50),
    )
    _scheduler.add_job(
        _submit_surface_worker,
        "interval",
        minutes=30,
        id="surface_worker",
        max_instances=1,
        misfire_grace_time=120,
        next_run_time=now,
    )
    _scheduler.add_job(
        run_water_worker,
        "interval",
        minutes=30,
        id="water_riv_gauges_worker",
        max_instances=1,
        misfire_grace_time=300,
        next_run_time=now + timedelta(seconds=95),
    )
    _scheduler.add_job(
        run_satellite_v2_rapid_worker,
        "interval",
        minutes=5,
        id="satellite_v2_rapid_worker",
        max_instances=1,
        misfire_grace_time=60,
        next_run_time=now + timedelta(seconds=65),
    )
    _scheduler.add_job(
        run_satellite_v2_meteosat_prefetch_worker,
        "interval",
        minutes=10,
        id="satellite_v2_meteosat_prefetch_worker",
        max_instances=1,
        misfire_grace_time=300,
        next_run_time=now + timedelta(seconds=75),
    )
    _scheduler.start()

    print(
        "[scheduler] In-process fallback ENABLED — alerts (1 min), spc (30 min), "
        "tropical (30 min, +10s delay), mrms (15 min, +30s delay), radar_live (5 min, +20s delay), "
        "rtma_hourly (60 min, +45s delay), rtma_rapid (15 min, +50s delay), "
        "surface (30 min), water_riv_gauges (30 min, +95s delay), "
        "satellite_v2_rapid (5 min, +65s delay), "
        "satellite_v2_meteosat_prefetch (10 min, +75s delay). "
        "Cache cleanup is owned by the refresh coordinator."
    )


def stop_scheduler() -> None:
    """Shutdown the scheduler gracefully (no-op when never started)."""
    try:
        if _scheduler.running:
            _scheduler.shutdown(wait=False)
    except Exception:
        pass
