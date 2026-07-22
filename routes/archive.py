"""Historical archive API routes."""

from fastapi import APIRouter

from services.archive_service import (
    get_archive_alerts,
    get_archive_mrms,
    get_archive_result,
    get_archive_spc,
    get_archive_surface,
)

router = APIRouter()


@router.get("/api/archive/mrms")
def archive_mrms(
    product: str = "PrecipRate",
    date_from: str = "",
    date_to: str = "",
    max_frames: int = 24,
    south: float = 21.0,
    west: float = -130.0,
    north: float = 52.0,
    east: float = -60.0,
    request_id: str = "",
):
    return get_archive_mrms(
        product=product,
        date_from=date_from,
        date_to=date_to,
        max_frames=max_frames,
        south=south,
        west=west,
        north=north,
        east=east,
        request_id=request_id,
    )


@router.get("/api/archive/result")
def archive_result(session_id: str):
    return get_archive_result(session_id=session_id)


@router.get("/api/archive/alerts")
def archive_alerts(date_from: str = "", date_to: str = "", state: str = ""):
    return get_archive_alerts(date_from=date_from, date_to=date_to, state=state)


@router.get("/api/archive/surface")
def archive_surface(
    region: str = "NC",
    product: str = "temperature",
    date_from: str = "",
    date_to: str = "",
    max_frames: int = 120,
    source: str = "iem",
    network: str = "ASOS",
):
    return get_archive_surface(
        region=region,
        product=product,
        date_from=date_from,
        date_to=date_to,
        max_frames=max_frames,
        source=source,
        network=network,
    )


@router.get("/api/archive/spc")
def archive_spc(day: int = 1, hazard: str = "cat", date: str = ""):
    return get_archive_spc(day=day, hazard=hazard, date=date)
