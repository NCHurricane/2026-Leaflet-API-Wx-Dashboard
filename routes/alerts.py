"""Alert API routes."""

from typing import Optional

from fastapi import APIRouter

from services.alerts_service import (
    get_alerts_data,
    get_local_storm_reports,
)

router = APIRouter()


@router.get("/api/data/alerts")
def get_data_alerts(
    state: Optional[str] = None,
    geometry_mode: Optional[str] = None,
    zoom_bucket: Optional[str] = None,
    west: Optional[float] = None,
    east: Optional[float] = None,
    south: Optional[float] = None,
    north: Optional[float] = None,
):
    return get_alerts_data(
        state=state,
        geometry_mode=geometry_mode,
        zoom_bucket=zoom_bucket,
        west=west,
        east=east,
        south=south,
        north=north,
    )


@router.get("/api/data/alerts/lsr")
def get_data_local_storm_reports(
    west: Optional[float] = None,
    east: Optional[float] = None,
    south: Optional[float] = None,
    north: Optional[float] = None,
    hours: Optional[int] = None,
):
    return get_local_storm_reports(
        west=west,
        east=east,
        south=south,
        north=north,
        hours=hours,
    )
