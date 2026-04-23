"""APScheduler configuration and job registration for background data workers."""

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


def start_scheduler() -> None:
    """Register background jobs and start the scheduler.

    All workers are scheduled with `next_run_time=now` so their first tick
    fires immediately on background scheduler threads — the FastAPI startup
    handler returns in milliseconds instead of blocking on initial cache fills.
    """
    from workers.alerts_worker import run_alerts_worker
    from workers.spc_worker import run_spc_worker
    from workers.mrms_worker import run_mrms_worker
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
        "[scheduler] Background workers scheduled: alerts (1 min), spc (30 min), "
        "mrms (15 min, +30s delay), surface (30 min) — first ticks running now in background"
    )


def stop_scheduler() -> None:
    """Shutdown the scheduler gracefully."""
    try:
        _scheduler.shutdown(wait=False)
    except Exception:
        pass
