"""Live + archive storm cells and attributes from the Iowa Environmental
Mesonet (IEM) NEXRAD storm-attributes service.

This is the single source for the Radar tab's "Storm Tracks (NST)" overlay. IEM
parses the NWS Level III storm-attribute table (storm tracking + hail + meso +
TVS + structure) for every radar into one GeoJSON feed, queryable by ``valid``
time with archive depth back to ~2010 — so it serves both the live edge and
frame-synced scrub/archive playback from a single endpoint.

It replaces the former AWS-NST + AWS-NMD + TGFTP pipeline (the AWS Unidata
mirror stopped carrying the hail/structure/TVS products in 2022).

Feature contract returned to the frontend (unchanged from the prior pipeline):
  - ``nst_cell`` Point features with cell id, motion, and merged attribute
    blocks (``nhi`` hail, ``nss`` structure, ``nme``/``ntv`` meso/TVS markers)
    plus an ``icon_priority`` of tvs > meso > pos_hail > prob_hail > cell.
  - ``nst_forecast_track`` LineString features: a straight-line projection of
    each cell along its motion vector (IEM gives current motion, not the
    algorithm's 15/30/45/60-min positions).
"""

from __future__ import annotations

import importlib
import math
from datetime import datetime, timezone
from typing import Any

from lib.listing_cache import cached_call
from services.radar_service import normalize_radar_site_id

_IEM_URL = "https://mesonet.agron.iastate.edu/geojson/nexrad_attr.geojson"
_EARTH_RADIUS_NM = 3440.065
_FORECAST_MINUTES = 60          # straight-line track projection horizon
_LIVE_TTL_SECONDS = 60          # realtime payload refresh cadence
_ARCHIVE_TTL_SECONDS = 1800     # historical (valid=) payload is effectively fixed
_REQUEST_TIMEOUT = 25
_SEVERE_PCT = 50                # POSH/POH threshold for hail icon classification
_MESO_MIN_RANK = 4              # IEM meso rank threshold (1-25); <=3 = weak shear, not a confirmed meso


def _radar_3letter(site_id: str) -> str:
    """IEM's ``nexrad`` field is the 3-char id (ICAO minus the leading region
    character): KAMA->AMA, KMHX->MHX, PAHG->AHG, TJUA->JUA."""
    return site_id[-3:].upper()


def _project_latlon(
    lat: float, lon: float, bearing_deg: float, distance_nm: float
) -> tuple[float, float]:
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)
    b = math.radians(bearing_deg)
    d = distance_nm / _EARTH_RADIUS_NM
    lat2 = math.asin(
        math.sin(lat1) * math.cos(d) + math.cos(lat1) * math.sin(d) * math.cos(b)
    )
    lon2 = lon1 + math.atan2(
        math.sin(b) * math.sin(d) * math.cos(lat1),
        math.cos(d) - math.sin(lat1) * math.sin(lat2),
    )
    return math.degrees(lat2), ((math.degrees(lon2) + 540.0) % 360.0) - 180.0


def _to_iem_valid(timestamp: str | None) -> str | None:
    """Convert a frame timestamp to IEM's ``valid`` form (UTC, minute precision)."""
    if not timestamp:
        return None
    try:
        dt = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def _present(value: Any) -> bool:
    """True when an IEM categorical field carries a real detection."""
    return bool(value) and str(value).strip().upper() not in {"NONE", "", "0"}


def _meso_confirmed(value: Any) -> bool:
    """True only when the IEM meso rank meets the minimum threshold.

    IEM rank 1-25; values below _MESO_MIN_RANK are weak rotational shear
    signatures that the NWS algorithm detects but trained analysts (and tools
    like Radarscope) do not flag as confirmed mesocyclones.
    """
    if not _present(value):
        return False
    try:
        return float(value) >= _MESO_MIN_RANK
    except (TypeError, ValueError):
        return False


def _num(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _build_cells(geojson: dict, site_id: str) -> dict[str, Any]:
    """Pure transform: IEM FeatureCollection -> our storm-cell feature set for
    one radar. Network-free so it can be unit-tested with a fixture."""
    radar3 = _radar_3letter(site_id)
    features: list[dict[str, Any]] = []
    cells: list[dict[str, Any]] = []
    newest_ts: str | None = None

    for feature in geojson.get("features") or []:
        props = feature.get("properties") or {}
        if str(props.get("nexrad", "")).upper() != radar3:
            continue
        geometry = feature.get("geometry") or {}
        coords = geometry.get("coordinates") or [None, None]
        lon, lat = _num(coords[0]), _num(coords[1])
        if lat is None or lon is None:
            continue

        storm_id = str(props.get("storm_id", "")).strip()
        drct = _num(props.get("drct"))
        # IEM drct is the direction the storm moves FROM (METAR convention); the
        # heading it travels toward — used for the track line, popup, and SRV — is
        # the opposite bearing.
        motion_to = ((drct + 180.0) % 360.0) if drct is not None else None
        sknt = _num(props.get("sknt"))
        posh = _num(props.get("posh"))
        poh = _num(props.get("poh"))
        max_size = _num(props.get("max_size"))
        top = _num(props.get("top"))
        vil = _num(props.get("vil"))
        max_dbz = _num(props.get("max_dbz"))
        valid_ts = props.get("valid")
        has_tvs = _present(props.get("tvs"))
        has_meso = _meso_confirmed(props.get("meso"))

        if valid_ts and (newest_ts is None or valid_ts > newest_ts):
            newest_ts = valid_ts

        if has_tvs:
            priority = "tvs"
        elif has_meso:
            priority = "meso"
        elif (posh or 0) >= _SEVERE_PCT:
            priority = "pos_hail"
        elif (poh or 0) >= _SEVERE_PCT:
            priority = "prob_hail"
        else:
            priority = "cell"

        cell_props: dict[str, Any] = {
            "kind": "nst_cell",
            "site": site_id,
            "cell_id": storm_id,
            "timestamp": valid_ts,
            "motion_to_degrees": motion_to,
            "speed_kt": sknt,
            "current_azimuth_deg": _num(props.get("azimuth")),
            "current_range_nm": _num(props.get("range")),
            "icon_priority": priority,
            # Attribute blocks mirror the prior pipeline's popup contract.
            "nhi": {"posh": posh, "poh": poh, "max_hail_size_in": max_size},
            "nss": {"top_kft": top, "vil": vil, "max_dbz": max_dbz},
        }
        if has_meso:
            cell_props["nme"] = {"value": str(props.get("meso"))}
        if has_tvs:
            cell_props["ntv"] = {"value": str(props.get("tvs"))}

        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": cell_props,
            }
        )
        cells.append({**cell_props, "lat": lat, "lon": lon})

        # Straight-line forecast vector along the cell's heading.
        if motion_to is not None and sknt and sknt > 0:
            end_lat, end_lon = _project_latlon(
                lat, lon, motion_to, sknt * (_FORECAST_MINUTES / 60.0)
            )
            features.append(
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[lon, lat], [end_lon, end_lat]],
                    },
                    "properties": {**cell_props, "kind": "nst_forecast_track"},
                }
            )

    return {
        "cells": cells,
        "feature_collection": {"type": "FeatureCollection", "features": features},
        "timestamp": newest_ts,
        "cell_count": len(cells),
    }


def _fetch_iem(valid: str | None) -> dict:
    requests = importlib.import_module("requests")
    params = {"valid": valid} if valid else {}
    resp = requests.get(
        _IEM_URL,
        params=params,
        timeout=_REQUEST_TIMEOUT,
        headers={"User-Agent": "weather-dashboard/1.0 (radar storm attributes)"},
    )
    resp.raise_for_status()
    return resp.json()


def _fetch_iem_cached(valid: str | None, force: bool) -> dict:
    if force:
        return _fetch_iem(valid)
    return cached_call(
        namespace="iem_nexrad_attr",
        key=(valid or "live",),
        fetch_fn=lambda: _fetch_iem(valid),
        ttl_seconds=_ARCHIVE_TTL_SECONDS if valid else _LIVE_TTL_SECONDS,
    )


def get_radar_storm_cells_data(
    site: str = "KMHX",
    timestamp: str | None = None,
    hours: float = 2,
    force: bool = False,
) -> dict[str, Any]:
    """Return storm cells + attributes for a radar from IEM.

    ``timestamp`` (a radar frame time) selects the archive volume via IEM's
    ``valid`` parameter, enabling frame-synced scrub/archive playback. Omitted
    -> the live nationwide feed. ``hours`` is accepted for endpoint
    compatibility but unused (IEM resolves a single valid time).
    """
    site_id = normalize_radar_site_id(site)
    valid = _to_iem_valid(timestamp)

    empty = {
        "status": "empty",
        "site": site_id,
        "timestamp": valid,
        "cell_count": 0,
        "cells": [],
        "feature_collection": {"type": "FeatureCollection", "features": []},
    }

    try:
        geojson = _fetch_iem_cached(valid, force)
    except Exception:
        return {**empty, "status": "error"}

    built = _build_cells(geojson, site_id)
    if not built["cell_count"]:
        return empty
    return {
        "status": "success",
        "site": site_id,
        **built,
    }
