"""Historical archive API routes."""

from fastapi import APIRouter

from services.archive_service import (
    get_archive_alerts,
    get_archive_surface,
)

router = APIRouter()


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
