"""Core API routes."""

import json

from fastapi import APIRouter

from app_core.paths import BASE_PATH
from app_core.runtime import is_using_nodd

router = APIRouter()


@router.get("/api/status")
def read_status():
    return {
        "status": "Weather System Online",
        "version": "2026.1",
        "radar_satellite_default_source": "NODD" if is_using_nodd() else "THREDDS",
    }


@router.get("/api/user-settings/defaults")
def read_default_user_settings():
    settings_path = BASE_PATH / "config" / "user_settings.default.json"
    with settings_path.open("r", encoding="utf-8") as fp:
        return json.load(fp)
