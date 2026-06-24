"""MRMS API routes."""

from fastapi import APIRouter

from config.mrms_config import MRMS_PRODUCTS, MRMS_SUB_PRODUCTS, PRODUCT_GROUPS
from services.mrms_service import get_mrms_data, set_mrms_product

router = APIRouter()


@router.get("/api/mrms/products")
def get_mrms_products():
    return {
        "status": "success",
        "products": MRMS_PRODUCTS,
        "sub_products": MRMS_SUB_PRODUCTS,
        "groups": PRODUCT_GROUPS,
        "count": len(MRMS_PRODUCTS),
    }


@router.get("/api/mrms/set-product")
def mrms_set_product(product: str):
    return set_mrms_product(product=product)


@router.get("/api/data/mrms")
def get_data_mrms(
    product: str = "PrecipRate",
    south: float = 21.0,
    west: float = -130.0,
    north: float = 52.0,
    east: float = -60.0,
):
    return get_mrms_data(
        product=product,
        south=south,
        west=west,
        north=north,
        east=east,
    )
