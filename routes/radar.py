"""Radar API routes."""

from fastapi import APIRouter

from services.radar_service import (
    get_radar_alert_tile,
    get_radar_colortable_data,
    get_radar_live_frames_data,
    get_radar_live_latest_data,
    get_radar_live_products_data,
    get_radar_live_sites_data,
    get_radar_live_value_data,
    get_radar_site_locations_data,
    get_radar_sites_data,
    get_radar_status_data,
    get_radar_tiles_freshness_data,
    head_radar_alert_tile,
)
from services.radar_storm_attributes_service import get_radar_storm_cells_data, _fetch_iem, _radar_3letter

router = APIRouter()


@router.get("/api/radar/sites")
def get_radar_sites():
    return get_radar_sites_data()


@router.get("/api/radar/site-locations")
def get_radar_site_locations():
    return get_radar_site_locations_data()


@router.get("/api/radar/colortable")
def get_radar_colortable(product: str = "BR"):
    return get_radar_colortable_data(product=product)


@router.get("/api/radar/tiles/{z}/{x}/{y}")
def get_radar_alert_tiles(z: str, x: str, y: str, frame: int = 4):
    return get_radar_alert_tile(z=z, x=x, y=y, frame=frame)


@router.head("/api/radar/tiles/{z}/{x}/{y}")
def head_radar_alert_tiles(z: str, x: str, y: str):
    return head_radar_alert_tile()


@router.get("/api/radar/tiles/freshness")
def get_radar_tiles_freshness():
    return get_radar_tiles_freshness_data()


@router.get("/api/radar/status")
def get_radar_status():
    return get_radar_status_data()


@router.get("/api/radar/products")
def get_radar_products():
    return get_radar_live_products_data()


@router.get("/api/radar/live/sites")
def get_radar_live_sites():
    return get_radar_live_sites_data()


@router.get("/api/radar/live/latest")
def get_radar_live_latest(
    site: str = "KMHX",
    product: str = "L3_N0B",
    elevation: str = "auto",
    force: bool = False,
    storm_motion_speed_kt: str | None = None,
    storm_motion_to_degrees: str | None = None,
    storm_motion_source: str | None = None,
    storm_cell_id: str | None = None,
):
    return get_radar_live_latest_data(
        site=site,
        product=product,
        elevation=elevation,
        force=force,
        storm_motion_speed_kt=storm_motion_speed_kt,
        storm_motion_to_degrees=storm_motion_to_degrees,
        storm_motion_source=storm_motion_source,
        storm_cell_id=storm_cell_id,
    )


@router.get("/api/radar/live/frames")
def get_radar_live_frames(
    site: str = "KMHX",
    product: str = "L3_N0B",
    elevation: str = "auto",
    hours: float = 2,
    refresh: bool = False,
    storm_motion_speed_kt: str | None = None,
    storm_motion_to_degrees: str | None = None,
    storm_motion_source: str | None = None,
    storm_cell_id: str | None = None,
):
    return get_radar_live_frames_data(
        site=site,
        product=product,
        elevation=elevation,
        hours=hours,
        refresh=refresh,
        storm_motion_speed_kt=storm_motion_speed_kt,
        storm_motion_to_degrees=storm_motion_to_degrees,
        storm_motion_source=storm_motion_source,
        storm_cell_id=storm_cell_id,
    )


@router.get("/api/radar/live/value")
def get_radar_live_value(
    site: str = "KMHX",
    product: str = "L3_N0B",
    elevation: str = "auto",
    frame_key: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    storm_motion_speed_kt: str | None = None,
    storm_motion_to_degrees: str | None = None,
    storm_motion_source: str | None = None,
    storm_cell_id: str | None = None,
):
    return get_radar_live_value_data(
        site=site,
        product=product,
        elevation=elevation,
        frame_key=frame_key,
        lat=lat,
        lon=lon,
        storm_motion_speed_kt=storm_motion_speed_kt,
        storm_motion_to_degrees=storm_motion_to_degrees,
        storm_motion_source=storm_motion_source,
        storm_cell_id=storm_cell_id,
    )


@router.get("/api/radar/debug/meso-raw")
def get_radar_debug_meso_raw(site: str = "KMHX"):
    """Return raw IEM meso/tvs field values for every cell at a radar site.

    Use this to inspect the numeric scale IEM uses for the ``meso`` and ``tvs``
    fields so an appropriate threshold can be chosen for icon filtering.
    """
    radar3 = _radar_3letter(site)
    try:
        geojson = _fetch_iem(valid=None)
    except Exception as exc:
        return {"error": str(exc), "site": site}

    cells = []
    for feature in geojson.get("features", []):
        props = feature.get("properties") or {}
        if str(props.get("nexrad", "")).upper() != radar3:
            continue
        cells.append({
            "cell_id": props.get("storm_id"),
            "meso_raw": props.get("meso"),
            "tvs_raw": props.get("tvs"),
            "posh": props.get("posh"),
            "poh": props.get("poh"),
            "max_dbz": props.get("max_dbz"),
            "valid": props.get("valid"),
        })

    return {"site": site, "radar3": radar3, "cell_count": len(cells), "cells": cells}


@router.get("/api/radar/live/storm-tracks")
def get_radar_live_storm_tracks(
    site: str = "KMHX",
    timestamp: str | None = None,
    hours: float = 2,
    force: bool = False,
):
    return get_radar_storm_cells_data(
        site=site, timestamp=timestamp, hours=hours, force=force
    )
