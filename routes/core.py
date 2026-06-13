"""Core API routes."""

from fastapi import APIRouter

from app_core.progress import active_tasks
from app_core.runtime import is_using_nodd

router = APIRouter()


@router.get("/api/status")
def read_status():
    return {
        "status": "Weather System Online",
        "version": "2026.1",
        "radar_satellite_default_source": "NODD" if is_using_nodd() else "THREDDS",
    }


@router.get("/api/progress/{task_id}")
def get_task_progress(task_id: str):
    return active_tasks.get(
        task_id, {"percent": 0, "message": "Waiting...", "stage": "idle"}
    )
