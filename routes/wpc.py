"""WPC API routes."""

from fastapi import APIRouter

from services.wpc_service import get_wpc_catalog, get_wpc_layer

router = APIRouter()


@router.get("/api/data/wpc")
def get_data_wpc(group: str = "ero", day: int = 1, product: str | None = None):
    return get_wpc_layer(group=group, day=day, product_id=product)


@router.get("/api/data/wpc/catalog")
def get_data_wpc_catalog():
    return get_wpc_catalog()
