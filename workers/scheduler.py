"""APScheduler configuration and (optional) job registration for background data workers.

Default mode: **OS-only fetching**. Windows Task Scheduler (see
``tools/install_tasks.ps1``) is the source of truth for refreshing the
alerts / SPC / surface / MRMS / RTMA caches. ``main.py`` simply reads from disk.

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
            "[scheduler] In-process workers disabled (default). "
            "Cache refresh is delegated to Windows Task Scheduler. "
            "Set WX_INPROC_WORKERS=1 to enable the in-process fallback."
        )
        return

    from workers.alerts_worker import run_alerts_worker
    from workers.spc_worker import run_spc_worker
    from workers.mrms_worker import run_mrms_worker
    from workers.radar_live_worker import run_radar_live_worker
    from workers.radar_tiles_worker import run_radar_tiles_worker
    from workers.rtma_worker import run_rtma_hourly_worker, run_rtma_rapid_worker
    from workers.satellite_worker import (
        run_satellite_current_worker,
        run_satellite_meso_worker,
    )
    from satellite_v2.worker import run_satellite_v2_worker
    from workers.surface_worker import run_surface_worker

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
        run_radar_tiles_worker,
        "interval",
        minutes=5,
        id="radar_tiles_worker",
        max_instances=1,
        misfire_grace_time=60,
        next_run_time=now + timedelta(seconds=25),
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
        run_surface_worker,
        "interval",
        minutes=30,
        id="surface_worker",
        max_instances=1,
        misfire_grace_time=120,
        next_run_time=now,
    )
    _scheduler.add_job(
        run_satellite_current_worker,
        "interval",
        minutes=15,
        id="satellite_current_worker",
        max_instances=1,
        misfire_grace_time=60,
        next_run_time=now + timedelta(seconds=35),
    )
    _scheduler.add_job(
        run_satellite_meso_worker,
        "interval",
        minutes=5,
        id="satellite_meso_worker",
        max_instances=1,
        misfire_grace_time=60,
        next_run_time=now + timedelta(seconds=40),
    )
    _scheduler.add_job(
        lambda: run_satellite_v2_worker(profile="local-primary"),
        "interval",
        minutes=15,
        id="satellite_v2_worker",
        max_instances=1,
        misfire_grace_time=60,
        next_run_time=now + timedelta(seconds=55),
    )
    _scheduler.add_job(
        lambda: run_satellite_v2_worker(meso=True, profile="goes19-meso"),
        "interval",
        minutes=5,
        id="satellite_v2_meso_worker",
        max_instances=1,
        misfire_grace_time=60,
        next_run_time=now + timedelta(seconds=65),
    )
    _scheduler.add_job(
        lambda: run_satellite_v2_worker(
            profile="goes19-light-composites",
            tile_workers=2,
            worker_name_override="satellite_v2_light_composites",
        ),
        "interval",
        minutes=5,
        id="satellite_v2_light_composites_worker",
        max_instances=1,
        misfire_grace_time=60,
        next_run_time=now + timedelta(seconds=75),
    )
    _scheduler.add_job(
        lambda: run_satellite_v2_worker(
            profile="goes19-geocolor",
            tile_workers=1,
            worker_name_override="satellite_v2_geocolor",
        ),
        "interval",
        minutes=10,
        id="satellite_v2_geocolor_worker",
        max_instances=1,
        misfire_grace_time=60,
        next_run_time=now + timedelta(seconds=85),
    )

    _scheduler.start()

    print(
        "[scheduler] In-process fallback ENABLED — alerts (1 min), spc (30 min), "
        "mrms (15 min, +30s delay), radar_live (5 min, +20s delay), "
        "radar_tiles (5 min, +25s delay), "
        "rtma_hourly (60 min, +45s delay), rtma_rapid (15 min, +50s delay), "
        "surface (30 min), satellite_current (15 min, +35s delay), "
        "satellite_meso (5 min, +40s delay), satellite_v2 (15 min, +55s delay), "
        "satellite_v2_meso (5 min, +65s delay), "
        "satellite_v2_light_composites (5 min, +75s delay), "
        "satellite_v2_geocolor (10 min, +85s delay)"
    )


def stop_scheduler() -> None:
    """Shutdown the scheduler gracefully (no-op when never started)."""
    try:
        if _scheduler.running:
            _scheduler.shutdown(wait=False)
    except Exception:
        pass
