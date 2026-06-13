"""Overlay and boundary API routes."""

from collections.abc import Callable

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from services.boundary_service import (
    get_us_boundaries_geojson,
    get_world_borders_geojson,
)
from services.overlay_service import (
    get_overlay_frames as get_overlay_frames_payload,
    get_overlay_latest as get_overlay_latest_payload,
)


def create_overlays_router(rtma_bootstrap: Callable[..., object] | None = None) -> APIRouter:
    router = APIRouter()

    @router.get("/api/overlay/world-borders")
    def get_world_borders():
        try:
            data = get_world_borders_geojson()
            return JSONResponse(content=data)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @router.get("/api/overlay/us-boundaries")
    def get_us_boundaries():
        try:
            data = get_us_boundaries_geojson()
            return JSONResponse(content=data)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @router.get("/api/overlay/latest")
    def get_overlay_latest(
        family: str = "rtma",
        region: str = "CONUS",
        stream: str = "rtma_hourly",
        product: str = "temperature",
        frame_key: str | None = None,
    ):
        return get_overlay_latest_payload(
            family=family,
            region=region,
            stream=stream,
            product=product,
            frame_key=frame_key,
            rtma_bootstrap=rtma_bootstrap,
        )

    @router.get("/api/overlay/frames")
    def get_overlay_frames(
        family: str = "rtma",
        region: str = "CONUS",
        stream: str = "rtma_hourly",
        product: str = "temperature",
        hours: int = 1,
    ):
        return get_overlay_frames_payload(
            family=family,
            region=region,
            stream=stream,
            product=product,
            hours=hours,
        )

    return router
