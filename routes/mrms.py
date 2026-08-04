"""MRMS API routes."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

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


@router.post("/api/mrms/tiles/prepare")
def prepare_mrms_tiles(product: str, frame_key: str):
    from mrms.mrms_tiles import prepare_tile_source

    try:
        tile = prepare_tile_source(product, frame_key)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"MRMS native tile preparation failed: {exc}",
        ) from exc
    return {"status": "ready", "tile": tile}


@router.get(
    "/api/mrms/tiles/{render_version}/{product}/{frame_key}/{z}/{x}/{y}.png"
)
def get_mrms_tile(
    render_version: str,
    product: str,
    frame_key: str,
    z: int,
    x: int,
    y: int,
):
    from mrms.mrms_tiles import resolve_tile

    try:
        path = resolve_tile(render_version, product, frame_key, z, x, y)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"MRMS native tile rendering failed: {exc}",
        ) from exc
    return FileResponse(
        path,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400, immutable"},
    )
