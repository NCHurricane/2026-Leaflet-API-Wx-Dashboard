"""Satellite v2 API routes."""

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
        import traceback

        print(
            "[satellite-v2 catalog] ERROR "
            f"sat_id={sat_id} sector={sector} channel={channel} "
            f"hours={hours} max_frames={max_frames} refresh={refresh}: {exc}",
            flush=True,
        )
        traceback.print_exc()
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
def get_satellite_v2_tile(
    z: int,
    x: int,
    y: int,
    sat_id: str,
    sector: str,
    channel: str,
    frame_key: str,
    render_live: bool = True,
    render_neighbors: bool = True,
):
    try:
        tile_file, tile_stats = satellite_v2_service.resolve_tile(
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
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    cache_status = str(tile_stats.get("cache_status") or "hit")
    source_label = _satellite_v2_tile_source_label(cache_status)
    validate_ms = int(tile_stats.get("validate_elapsed_ms") or 0)
    print(
        "[satellite-v2 tile] "
        f"source={source_label} "
        f"cache_status={cache_status.upper()} "
        f"miss_reason={str(tile_stats.get('miss_reason') or 'none')} "
        f"validate_ms={validate_ms} "
        f"elapsed_ms={int(tile_stats.get('elapsed_ms') or 0)} "
        f"sat_id={tile_stats.get('sat_id') or sat_id} "
        f"sector={tile_stats.get('sector') or sector} "
        f"channel={tile_stats.get('channel') or channel} "
        f"frame_key={frame_key} z={z} x={x} y={y}",
        flush=True,
    )

    if not tile_file.exists():
        if cache_status.lower() in {"empty", "invalid", "missing"}:
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
    # FileResponse performs another threadpool read after this synchronous
    # route returns. A cold tile burst can occupy every request worker with
    # render waits, starving an already-rendered PNG before it reaches Leaflet.
    response = Response(content=tile_content, media_type="image/png")
    response.headers["X-Satellite-V2-Cache"] = cache_status.upper()
    response.headers["X-Satellite-V2-Provider"] = str(
        tile_stats.get("provider") or "aws"
    )
    response.headers["X-Satellite-V2-Elapsed-Ms"] = str(
        int(tile_stats.get("elapsed_ms") or 0)
    )
    response.headers["X-Satellite-V2-Frame-Key"] = str(frame_key or "")
    response.headers["Cache-Control"] = "public, max-age=86400, immutable"
    response.headers["ETag"] = (
        f"satv2-{sat_id}-{sector}-{channel}-{frame_key}-{z}-{x}-{y}"
    )
    response.headers["Vary"] = "Accept-Encoding"
    return response


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
