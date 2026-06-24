"""Radar API routes."""

from fastapi import APIRouter

from services.radar_service import (
    get_radar_alert_tile,
    get_radar_colortable_data,
    get_radar_live_frames_data,
    get_radar_live_latest_data,
    get_radar_live_sites_data,
    get_radar_site_locations_data,
    get_radar_sites_data,
    get_radar_status_data,
    get_radar_tiles_freshness_data,
    head_radar_alert_tile,
)

router = APIRouter()


@router.get("/api/radar/sites")
def get_radar_sites():
    return get_radar_sites_data()


@router.get("/api/radar/site-locations")
def get_radar_site_locations():
    return get_radar_site_locations_data()


@router.get("/api/radar/colortable")
def get_radar_colortable(product: str = "BR"):
    return get_radar_colortable_data(product=product)


@router.get("/api/radar/tiles/{z}/{x}/{y}")
def get_radar_alert_tiles(z: str, x: str, y: str, frame: int = 4):
    return get_radar_alert_tile(z=z, x=x, y=y, frame=frame)


@router.head("/api/radar/tiles/{z}/{x}/{y}")
def head_radar_alert_tiles(z: str, x: str, y: str):
    return head_radar_alert_tile()


@router.get("/api/radar/tiles/freshness")
def get_radar_tiles_freshness():
    return get_radar_tiles_freshness_data()


@router.get("/api/radar/status")
def get_radar_status():
    return get_radar_status_data()


@router.get("/api/radar/live/sites")
def get_radar_live_sites():
    return get_radar_live_sites_data()


@router.get("/api/radar/live/latest")
def get_radar_live_latest(
    site: str = "KMHX",
    product: str = "L3_N0B",
    elevation: str = "auto",
    force: bool = False,
):
    return get_radar_live_latest_data(
        site=site, product=product, elevation=elevation, force=force
    )


@router.get("/api/radar/live/frames")
def get_radar_live_frames(
    site: str = "KMHX",
    product: str = "L3_N0B",
    elevation: str = "auto",
    hours: int = 2,
):
    return get_radar_live_frames_data(
        site=site, product=product, elevation=elevation, hours=hours
    )
