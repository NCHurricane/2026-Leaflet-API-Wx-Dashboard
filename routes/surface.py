"""Surface API routes."""

from fastapi import APIRouter

from services.surface_service import (
    SURFACE_PRODUCTS,
    get_surface_data,
    get_surface_gradient,
)

router = APIRouter()


@router.get("/api/surface/products")
def get_surface_products():
    return {
        "status": "success",
        "products": SURFACE_PRODUCTS,
        "count": len(SURFACE_PRODUCTS),
    }


@router.get("/api/data/surface")
def get_data_surface(
    region: str = "NC", product: str = "temperature", force_refresh: bool = False
):
    return get_surface_data(
        region=region, product=product, force_refresh=force_refresh
    )


@router.get("/api/data/surface-gradient")
def get_data_surface_gradient(region: str = "CONUS", product: str = "temperature"):
    return get_surface_gradient(region=region, product=product)
