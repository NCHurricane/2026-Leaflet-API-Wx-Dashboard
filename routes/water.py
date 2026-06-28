"""Water monitoring API routes."""

from fastapi import APIRouter

from services.water_service import get_water_station_data, get_water_stations_data

router = APIRouter()


@router.get("/api/water/stations")
def get_water_stations(bbox: str, max_sites: int = 300, networks: str | None = None):
    return get_water_stations_data(bbox=bbox, max_sites=max_sites, networks=networks)


@router.get("/api/water/stations/{site_id}")
def get_water_station(site_id: str):
    return get_water_station_data(site_id)
