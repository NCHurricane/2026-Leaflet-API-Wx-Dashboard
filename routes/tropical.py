"""Tropical cyclone API routes."""

from fastapi import APIRouter

from services.tropical_service import (
    get_tropical_archive_advisory_data,
    get_tropical_archive_catalog_data,
    get_tropical_archive_storm_data,
    get_tropical_archive_warm_status_data,
    get_tropical_basin_feeds_data,
    get_tropical_storm_data,
    get_tropical_storms_data,
    get_tropical_summary_data,
    start_tropical_archive_warm_data,
)

router = APIRouter()


@router.get("/api/tropical/products")
def get_tropical_products():
    return {
        "status": "success",
        "products": [
            "active_storms",
            "archive_catalog",
            "basin_feeds",
        ],
        "basins": ["ATLANTIC", "PACIFIC", "WORLD"],
        "count": 3,
    }


@router.get("/api/tropical/storms")
def get_tropical_storms(basin: str = "WORLD", force: bool = False):
    return get_tropical_storms_data(basin=basin, force=force)


@router.get("/api/tropical/summary")
def get_tropical_summary(force: bool = False):
    return get_tropical_summary_data(force=force)


@router.get("/api/tropical/basin/{basin_id}/feeds")
def get_tropical_basin_feeds(basin_id: str):
    return get_tropical_basin_feeds_data(basin_id=basin_id)


@router.get("/api/tropical/storm/{storm_id}")
def get_tropical_storm(storm_id: str):
    return get_tropical_storm_data(storm_id=storm_id)


@router.get("/api/tropical/archive/catalog")
def get_tropical_archive_catalog():
    return get_tropical_archive_catalog_data()


@router.get("/api/tropical/archive/storm/{atcf_id}")
def get_tropical_archive_storm(atcf_id: str):
    return get_tropical_archive_storm_data(atcf_id=atcf_id)


@router.get("/api/tropical/archive/storm/{atcf_id}/advisory/{step}")
def get_tropical_archive_advisory(atcf_id: str, step: str):
    return get_tropical_archive_advisory_data(atcf_id=atcf_id, step=step)


@router.post("/api/tropical/archive/storm/{atcf_id}/warm")
def start_tropical_archive_warm(
    atcf_id: str,
    mode: str = "window",
    anchor: str | None = None,
):
    return start_tropical_archive_warm_data(
        atcf_id=atcf_id,
        mode=mode,
        anchor=anchor,
    )


@router.get("/api/tropical/archive/storm/{atcf_id}/warm")
def get_tropical_archive_warm_status(atcf_id: str):
    return get_tropical_archive_warm_status_data(atcf_id=atcf_id)
