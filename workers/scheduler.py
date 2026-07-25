"""Application-owned worker lifecycle compatibility hooks.

Refresh work is request-driven through ``app_core.refresh_coordinator``.
No fixed APScheduler or OS-task worker profile is required for correctness,
freshness, archive updates, or cache cleanup.

``start_scheduler`` and ``stop_scheduler`` remain as stable runtime hooks for
older launchers. They intentionally register no broad direct-writing jobs.
Optional Windows warmers call the running application's HTTP API instead.
"""

from __future__ import annotations


def start_scheduler() -> None:
    """Confirm application-owned scheduling without registering worker jobs."""
    print(
        "[scheduler] Application-owned refresh coordination active; "
        "no fixed worker schedule registered."
    )


def stop_scheduler() -> None:
    """Compatibility no-op; the refresh coordinator owns shutdown."""
