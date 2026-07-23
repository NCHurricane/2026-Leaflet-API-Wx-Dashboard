from fastapi import APIRouter
import time

from app_core.refresh_coordinator import get_refresh_coordinator

router = APIRouter()

start_time = time.time()

@router.get("/health")
def health():
    uptime = round(time.time() - start_time, 2)
    return {
        "status": "ok",
        "uptime_seconds": uptime,
        "version": "2026.1"
    }


@router.get("/api/health/coordinator")
def coordinator_health():
    """Report credential-safe application refresh state."""
    return get_refresh_coordinator().snapshot()
