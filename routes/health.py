from fastapi import APIRouter
import time

from app_core.refresh_coordinator import get_refresh_coordinator

router = APIRouter()

start_time = time.time()


def _coordinator_health_payload() -> dict:
    snapshot = get_refresh_coordinator().snapshot()
    states = snapshot.get("states") or []
    source_states: dict[str, dict] = {}
    for state in states:
        provider = str(state.get("provider") or "unknown")
        source = source_states.setdefault(
            provider,
            {
                "status": "idle",
                "active_resources": 0,
                "failed_resources": 0,
                "backoff_resources": 0,
                "last_success_at": None,
            },
        )
        state_status = str(state.get("status") or "idle")
        if state_status in {"queued", "running"}:
            source["active_resources"] += 1
        elif state_status == "backoff":
            source["backoff_resources"] += 1
        elif state_status == "failed":
            source["failed_resources"] += 1
        last_success = state.get("last_success_at")
        if last_success and (
            source["last_success_at"] is None
            or str(last_success) > source["last_success_at"]
        ):
            source["last_success_at"] = str(last_success)

    for source in source_states.values():
        if source["failed_resources"]:
            source["status"] = "failed"
        elif source["backoff_resources"]:
            source["status"] = "backoff"
        elif source["active_resources"]:
            source["status"] = "active"
        elif source["last_success_at"]:
            source["status"] = "current"

    periodic_jobs = snapshot.get("periodic_jobs") or []
    snapshot.update(
        {
            "health_model": "application_owned",
            "sources": source_states,
            "caches": states,
            "maintenance": {
                "cache_cleanup_registered": (
                    ["maintenance", "cache-cleanup"] in periodic_jobs
                ),
                "current_season_tropical": "request_driven",
            },
        }
    )
    return snapshot


@router.get("/health")
def health():
    uptime = round(time.time() - start_time, 2)
    coordinator = _coordinator_health_payload()
    healthy = bool(
        coordinator.get("running")
        and coordinator["maintenance"]["cache_cleanup_registered"]
    )
    return {
        "status": "ok" if healthy else "degraded",
        "uptime_seconds": uptime,
        "version": "2026.1",
        "health_model": "application_owned",
        "coordinator_running": bool(coordinator.get("running")),
        "cache_cleanup_registered": coordinator["maintenance"][
            "cache_cleanup_registered"
        ],
    }


@router.get("/api/health/coordinator")
def coordinator_health():
    """Report credential-safe coordinator, source, and cache state."""
    return _coordinator_health_payload()
