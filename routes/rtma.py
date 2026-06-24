"""RTMA API routes."""

from fastapi import APIRouter

from config.rtma_config import RTMA_UI_PRODUCTS, RTMA_STREAMS
from services.rtma_service import (
    get_rtma_data,
    get_rtma_frames,
    get_rtma_grid,
    get_rtma_points,
)

router = APIRouter()


@router.get("/api/rtma/products")
def get_rtma_products():
    return {
        "status": "success",
        "products": RTMA_UI_PRODUCTS,
        "streams": list(RTMA_STREAMS),
        "count": len(RTMA_UI_PRODUCTS),
    }


@router.get("/api/data/rtma/points")
def get_data_rtma_points(
    region: str = "CONUS",
    stream: str = "rtma_hourly",
    product: str = "temperature",
    source_data_key: str | None = None,
    south: float | None = None,
    west: float | None = None,
    north: float | None = None,
    east: float | None = None,
    stride: int = 30,
):
    return get_rtma_points(
        region=region,
        stream=stream,
        product=product,
        source_data_key=source_data_key,
        south=south,
        west=west,
        north=north,
        east=east,
        stride=stride,
    )


@router.get("/api/data/rtma/grid")
def get_data_rtma_grid(
    region: str = "CONUS",
    stream: str = "rtma_hourly",
    product: str = "temperature",
    source_data_key: str | None = None,
    stride: int = 2,
):
    return get_rtma_grid(
        region=region,
        stream=stream,
        product=product,
        source_data_key=source_data_key,
        stride=stride,
    )


@router.get("/api/data/rtma")
def get_data_rtma(
    region: str = "CONUS",
    stream: str = "rtma_hourly",
    product: str = "temperature",
    source_data_key: str | None = None,
    south: float = 21.0,
    west: float = -130.0,
    north: float = 52.0,
    east: float = -60.0,
):
    return get_rtma_data(
        region=region,
        stream=stream,
        product=product,
        source_data_key=source_data_key,
        south=south,
        west=west,
        north=north,
        east=east,
    )


@router.get("/api/data/rtma/frames")
def get_data_rtma_frames(
    region: str = "CONUS",
    stream: str = "rtma_hourly",
    product: str = "temperature",
    max_hours: int | None = None,
):
    return get_rtma_frames(
        region=region,
        stream=stream,
        product=product,
        max_hours=max_hours,
    )
