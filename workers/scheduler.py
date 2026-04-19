"""APScheduler configuration and job registration for background data workers."""

from apscheduler.schedulers.background import BackgroundScheduler

_scheduler = BackgroundScheduler(timezone="UTC")


def start_scheduler() -> None:
    """Register background jobs and start the scheduler.

    Jobs:
        alerts_worker — 2 min interval, always active.
        spc_worker    — 30 min interval, always active.
    """
    from workers.alerts_worker import run_alerts_worker
    from workers.spc_worker import run_spc_worker
    from workers.mrms_worker import run_mrms_worker
    from workers.surface_worker import run_surface_worker

    _scheduler.add_job(
        run_alerts_worker,
        "interval",
        minutes=2,
        id="alerts_worker",
        max_instances=1,
        misfire_grace_time=60,
    )
    _scheduler.add_job(
        run_spc_worker,
        "interval",
        minutes=30,
        id="spc_worker",
        max_instances=1,
        misfire_grace_time=300,
    )
    _scheduler.add_job(
        run_mrms_worker,
        "interval",
        minutes=2,
        id="mrms_worker",
        max_instances=1,
        misfire_grace_time=60,
    )
    _scheduler.add_job(
        run_surface_worker,
        "interval",
        minutes=5,
        id="surface_worker",
        max_instances=1,
        misfire_grace_time=120,
    )

    _scheduler.start()

    # Trigger an immediate first run of both workers so cache is warm within seconds
    # of startup rather than waiting for the first scheduled interval.
    try:
        run_alerts_worker()
    except Exception as exc:
        print(f"[scheduler] Initial alerts_worker run failed: {exc}")

    try:
        run_spc_worker()
    except Exception as exc:
        print(f"[scheduler] Initial spc_worker run failed: {exc}")

    try:
        run_surface_worker()
    except Exception as exc:
        print(f"[scheduler] Initial surface_worker run failed: {exc}")

    # MRMS initial run is intentionally NOT triggered at startup to avoid a blocking
    # S3 download on the critical startup path. The worker will run at its first
    # scheduled interval (~2 min). On-demand cold-cache fetch handles the first request.

    print(
        "[scheduler] Background workers started: alerts (2 min), spc (30 min), mrms (2 min), surface (5 min)"
    )


def stop_scheduler() -> None:
    """Shutdown the scheduler gracefully."""
    try:
        _scheduler.shutdown(wait=False)
    except Exception:
        pass
