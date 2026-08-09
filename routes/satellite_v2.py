"""Satellite v2 API routes."""

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app_core.paths import CACHE_ROOT
from config.satellite_v2_config import (
    SATELLITE_V2_DEFAULT_CHANNEL,
    SATELLITE_V2_DEFAULT_HOURS,
    SATELLITE_V2_DEFAULT_MAX_FRAMES,
    SATELLITE_V2_DEFAULT_SAT_ID,
    SATELLITE_V2_DEFAULT_SECTOR,
)
from satellite_v2 import service as satellite_v2_service

router = APIRouter()
_LOGGER = logging.getLogger(__name__)

_TRANSPARENT_PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
    b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


@router.get("/api/satellite/products")
def get_satellite_products():
    """Alias for /api/satellite-v2/catalog for consistent naming."""
    return get_satellite_v2_catalog()


@router.get("/api/satellite-v2/catalog")
def get_satellite_v2_catalog(
    sat_id: str = SATELLITE_V2_DEFAULT_SAT_ID,
    sector: str = SATELLITE_V2_DEFAULT_SECTOR,
    channel: str = SATELLITE_V2_DEFAULT_CHANNEL,
    hours: int = SATELLITE_V2_DEFAULT_HOURS,
    max_frames: int = SATELLITE_V2_DEFAULT_MAX_FRAMES,
    refresh: bool = False,
    client_id: str | None = None,
):
    try:
        return satellite_v2_service.get_catalog_payload(
            cache_root=CACHE_ROOT,
            sat_id=sat_id,
            sector=sector,
            channel=channel,
            hours=max(1, int(hours or SATELLITE_V2_DEFAULT_HOURS)),
            max_frames=max(1, int(max_frames or SATELLITE_V2_DEFAULT_MAX_FRAMES)),
            refresh=refresh,
            client_id=client_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        _LOGGER.error(
            "Satellite catalog failed sat_id=%s sector=%s channel=%s "
            "hours=%s max_frames=%s refresh=%s error_type=%s",
            sat_id,
            sector,
            channel,
            hours,
            max_frames,
            refresh,
            type(exc).__name__,
        )
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/satellite-v2/frame-bounds")
def get_satellite_v2_frame_bounds(
    sat_id: str = SATELLITE_V2_DEFAULT_SAT_ID,
    sector: str = SATELLITE_V2_DEFAULT_SECTOR,
    channel: str = SATELLITE_V2_DEFAULT_CHANNEL,
):
    """Geographic bounds of the latest frame, for sectors with no fixed extent."""
    try:
        bounds = satellite_v2_service.get_frame_bounds(
            cache_root=CACHE_ROOT,
            sat_id=sat_id,
            sector=sector,
            channel=channel,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"bounds": bounds}


@router.get("/api/satellite-v2/legend")
def get_satellite_v2_legend(channel: str = SATELLITE_V2_DEFAULT_CHANNEL):
    try:
        return satellite_v2_service.get_legend_payload(channel=channel)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/satellite-v2/tile/{z}/{x}/{y}")
async def get_satellite_v2_tile(
    z: int,
    x: int,
    y: int,
    sat_id: str,
    sector: str,
    channel: str,
    frame_key: str,
    render_live: bool = True,
    render_neighbors: bool = True,
    client_id: str | None = None,
):
    try:
        tile_file, tile_stats = await satellite_v2_service.resolve_tile_async(
            cache_root=CACHE_ROOT,
            sat_id=sat_id,
            sector=sector,
            channel=channel,
            frame_key=frame_key,
            z=z,
            x=x,
            y=y,
            allow_render=render_live,
            render_neighbors=render_neighbors,
            client_id=client_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    cache_status = str(tile_stats.get("cache_status") or "hit")
    source_label = _satellite_v2_tile_source_label(cache_status)
    validate_ms = int(tile_stats.get("validate_elapsed_ms") or 0)
    _LOGGER.info(
        "Satellite tile source=%s cache_status=%s miss_reason=%s "
        "validate_ms=%s elapsed_ms=%s sat_id=%s sector=%s channel=%s "
        "download_ms=%s decode_ms=%s render_ms=%s frame_key=%s z=%s x=%s y=%s",
        source_label,
        cache_status.upper(),
        str(tile_stats.get("miss_reason") or "none"),
        validate_ms,
        int(tile_stats.get("elapsed_ms") or 0),
        tile_stats.get("sat_id") or sat_id,
        tile_stats.get("sector") or sector,
        tile_stats.get("channel") or channel,
        int(tile_stats.get("download_elapsed_ms") or 0),
        int(tile_stats.get("decode_elapsed_ms") or 0),
        int(tile_stats.get("render_elapsed_ms") or 0),
        frame_key,
        z,
        x,
        y,
    )

    if not tile_file.exists():
        if cache_status.lower() in {"cancelled", "empty", "invalid", "missing"}:
            response = Response(content=_TRANSPARENT_PNG_1X1, media_type="image/png")
            response.headers["X-Satellite-V2-Cache"] = cache_status.upper()
            response.headers["X-Satellite-V2-Provider"] = str(
                tile_stats.get("provider") or "aws"
            )
            response.headers["X-Satellite-V2-Elapsed-Ms"] = str(
                int(tile_stats.get("elapsed_ms") or 0)
            )
            response.headers["X-Satellite-V2-Frame-Key"] = str(frame_key or "")
            response.headers["Cache-Control"] = "no-store, max-age=0"
            response.headers["ETag"] = (
                f"satv2-empty-{sat_id}-{sector}-{channel}-{frame_key}-{z}-{x}-{y}"
            )
            response.headers["Vary"] = "Accept-Encoding"
            return response
        raise HTTPException(
            status_code=404, detail="Satellite tile could not be generated."
        )

    try:
        tile_content = tile_file.read_bytes()
    except OSError as exc:
        raise HTTPException(
            status_code=404, detail="Satellite tile could not be read."
        ) from exc
    # FileResponse performs a deferred threadpool read after the handler
    # returns. Reading the small PNG here keeps delivery independent of the
    # shared request-worker pool even during a cold tile burst.
    response = Response(content=tile_content, media_type="image/png")
    response.headers["X-Satellite-V2-Cache"] = cache_status.upper()
    response.headers["X-Satellite-V2-Provider"] = str(
        tile_stats.get("provider") or "aws"
    )
    response.headers["X-Satellite-V2-Elapsed-Ms"] = str(
        int(tile_stats.get("elapsed_ms") or 0)
    )
    response.headers["X-Satellite-V2-Frame-Key"] = str(frame_key or "")
    response.headers["X-Satellite-V2-Download-Ms"] = str(
        int(tile_stats.get("download_elapsed_ms") or 0)
    )
    response.headers["X-Satellite-V2-Decode-Ms"] = str(
        int(tile_stats.get("decode_elapsed_ms") or 0)
    )
    response.headers["X-Satellite-V2-Render-Ms"] = str(
        int(tile_stats.get("render_elapsed_ms") or 0)
    )
    response.headers["Cache-Control"] = "public, max-age=86400, immutable"
    response.headers["ETag"] = (
        f"satv2-{sat_id}-{sector}-{channel}-{frame_key}-{z}-{x}-{y}"
    )
    response.headers["Vary"] = "Accept-Encoding"
    return response


@router.post("/api/satellite-v2/selection/release", status_code=204)
async def release_satellite_v2_selection(client_id: str):
    satellite_v2_service.release_satellite_selection(client_id)
    return Response(status_code=204)


def _satellite_v2_tile_source_label(cache_status: object) -> str:
    status = str(cache_status or "hit").strip().lower()
    if status == "hit":
        return "cached"
    if status in {"empty", "missing"}:
        return "cache-empty"
    if status in {"miss", "rendered"}:
        return "rendered-live"
    if status == "invalid":
        return "invalid"
    return status or "unknown"
