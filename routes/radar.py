"""Radar API routes."""

from fastapi import APIRouter

from services.radar_service import (
    get_radar_colortable_data,
    get_radar_live_frames_data,
    get_radar_live_latest_data,
    get_radar_live_products_data,
    get_radar_live_sites_data,
    get_radar_live_value_data,
    get_radar_live_webgl_artifact_data,
    get_radar_status_data,
)
from services.radar_storm_attributes_service import get_radar_storm_cells_data

router = APIRouter()


@router.get("/api/radar/colortable")
def get_radar_colortable(product: str = "BR"):
    return get_radar_colortable_data(product=product)


@router.get("/api/radar/status")
def get_radar_status():
    return get_radar_status_data()


@router.get("/api/radar/products")
def get_radar_products():
    return get_radar_live_products_data()


@router.get("/api/radar/live/sites")
def get_radar_live_sites():
    return get_radar_live_sites_data()


@router.get("/api/radar/live/latest")
def get_radar_live_latest(
    site: str = "KMHX",
    product: str = "L3_N0B",
    elevation: str = "auto",
    force: bool = False,
    storm_motion_speed_kt: str | None = None,
    storm_motion_to_degrees: str | None = None,
    storm_motion_source: str | None = None,
    storm_cell_id: str | None = None,
):
    return get_radar_live_latest_data(
        site=site,
        product=product,
        elevation=elevation,
        force=force,
        storm_motion_speed_kt=storm_motion_speed_kt,
        storm_motion_to_degrees=storm_motion_to_degrees,
        storm_motion_source=storm_motion_source,
        storm_cell_id=storm_cell_id,
    )


@router.get("/api/radar/live/frames")
def get_radar_live_frames(
    site: str = "KMHX",
    product: str = "L3_N0B",
    elevation: str = "auto",
    hours: float = 2,
    refresh: bool = False,
    storm_motion_speed_kt: str | None = None,
    storm_motion_to_degrees: str | None = None,
    storm_motion_source: str | None = None,
    storm_cell_id: str | None = None,
):
    return get_radar_live_frames_data(
        site=site,
        product=product,
        elevation=elevation,
        hours=hours,
        refresh=refresh,
        storm_motion_speed_kt=storm_motion_speed_kt,
        storm_motion_to_degrees=storm_motion_to_degrees,
        storm_motion_source=storm_motion_source,
        storm_cell_id=storm_cell_id,
    )


@router.get(
    "/api/radar/live/webgl/{version}/{product}/{site}/{elevation}/{frame_key}"
)
def get_radar_live_webgl_artifact(
    version: str,
    product: str,
    site: str,
    elevation: str,
    frame_key: str,
    variant: str | None = None,
):
    return get_radar_live_webgl_artifact_data(
        version, product, site, elevation, frame_key, variant
    )


@router.get("/api/radar/live/value")
def get_radar_live_value(
    site: str = "KMHX",
    product: str = "L3_N0B",
    elevation: str = "auto",
    frame_key: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    storm_motion_speed_kt: str | None = None,
    storm_motion_to_degrees: str | None = None,
    storm_motion_source: str | None = None,
    storm_cell_id: str | None = None,
):
    return get_radar_live_value_data(
        site=site,
        product=product,
        elevation=elevation,
        frame_key=frame_key,
        lat=lat,
        lon=lon,
        storm_motion_speed_kt=storm_motion_speed_kt,
        storm_motion_to_degrees=storm_motion_to_degrees,
        storm_motion_source=storm_motion_source,
        storm_cell_id=storm_cell_id,
    )


@router.get("/api/radar/live/storm-tracks")
def get_radar_live_storm_tracks(
    site: str = "KMHX",
    timestamp: str | None = None,
    hours: float = 2,
    force: bool = False,
):
    return get_radar_storm_cells_data(
        site=site, timestamp=timestamp, hours=hours, force=force
    )
