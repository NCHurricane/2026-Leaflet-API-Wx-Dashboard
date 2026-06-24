"""Drought API routes."""

from fastapi import APIRouter

from services.drought_service import (
    get_drought_dates as get_drought_dates_payload,
    get_drought_geojson as get_drought_geojson_payload,
    get_drought_state_stats as get_drought_state_stats_payload,
)

router = APIRouter()


@router.get("/api/drought/products")
def get_drought_products():
    return {
        "status": "success",
        "products": [
            "USDM (US Drought Monitor)",
        ],
        "data_types": [
            "geojson",
            "state_statistics",
            "dates",
        ],
        "count": 1,
    }


@router.get("/api/data/drought/dates")
def get_drought_dates():
    return get_drought_dates_payload()


@router.get("/api/data/drought")
async def get_drought_geojson(date: str = "latest"):
    return await get_drought_geojson_payload(date=date)


@router.get("/api/data/drought/state-stats")
async def get_drought_state_stats(date: str = "latest", state: str = "NC"):
    return await get_drought_state_stats_payload(date=date, state=state)
