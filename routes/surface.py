"""Surface API routes."""

from fastapi import APIRouter

from services.surface_service import (
    get_colormap_data,
    get_surface_data,
    get_surface_gradient,
)

router = APIRouter()


@router.get("/api/data/surface")
def get_data_surface(region: str = "NC", product: str = "temperature"):
    return get_surface_data(region=region, product=product)


@router.get("/api/data/surface-gradient")
def get_data_surface_gradient(region: str = "CONUS", product: str = "temperature"):
    return get_surface_gradient(region=region, product=product)


@router.get("/api/data/colormap")
def get_colormap(product: str = "temperature"):
    return get_colormap_data(product=product)
