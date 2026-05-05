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
    from workers.rtma_worker import run_rtma_worker
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
        run_rtma_worker,
        "interval",
        minutes=15,
        id="rtma_worker",
        max_instances=1,
        misfire_grace_time=60,
        next_run_time=now + timedelta(seconds=45),
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

    _scheduler.start()

    print(
        "[scheduler] In-process fallback ENABLED — alerts (1 min), spc (30 min), "
        "mrms (15 min, +30s delay), radar_live (5 min, +20s delay), "
        "radar_tiles (5 min, +25s delay), "
        "rtma (15 min, +45s delay), surface (30 min)"
    )


def stop_scheduler() -> None:
    """Shutdown the scheduler gracefully (no-op when never started)."""
    try:
        if _scheduler.running:
            _scheduler.shutdown(wait=False)
    except Exception:
        pass
