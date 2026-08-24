"""Identity for the currently running dashboard server session."""

from datetime import datetime, timezone


_server_started_at: str | None = None


def mark_server_started(now: datetime | None = None) -> str:
    """Record a UTC wall-clock boundary after application startup completes."""
    global _server_started_at
    started = now or datetime.now(timezone.utc)
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    _server_started_at = started.astimezone(timezone.utc).isoformat(
        timespec="milliseconds"
    )
    return _server_started_at


def server_started_at() -> str | None:
    """Return the current server-session boundary, if startup has completed."""
    return _server_started_at
