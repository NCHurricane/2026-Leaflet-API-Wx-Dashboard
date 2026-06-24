"""NEXRAD Level III NST storm-track parsing and API helpers."""

from __future__ import annotations

import math
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from app_core.paths import CACHE_ROOT
from services.radar_service import normalize_radar_site_id

_NST_PRODUCT = "NST"
_NST_EARTH_RADIUS_NM = 3440.065
_NST_CACHE_LOOKBACK_HOURS = 2.0


def _bearing_range_to_latlon(
    radar_lat: float, radar_lon: float, azimuth_deg: float, range_nm: float
) -> tuple[float, float]:
    """Convert radar-relative azimuth/range to lat/lon."""
    lat1 = math.radians(float(radar_lat))
    lon1 = math.radians(float(radar_lon))
    bearing = math.radians(float(azimuth_deg))
    angular_distance = float(range_nm) / _NST_EARTH_RADIUS_NM

    lat2 = math.asin(
        math.sin(lat1) * math.cos(angular_distance)
        + math.cos(lat1) * math.sin(angular_distance) * math.cos(bearing)
    )
    lon2 = lon1 + math.atan2(
        math.sin(bearing) * math.sin(angular_distance) * math.cos(lat1),
        math.cos(angular_distance) - math.sin(lat1) * math.sin(lat2),
    )
    return math.degrees(lat2), ((math.degrees(lon2) + 540.0) % 360.0) - 180.0


def _printable_strings(raw: bytes) -> list[str]:
    return [
        match.group().decode("ascii", errors="replace")
        for match in re.finditer(rb"[ -~]{2,}", raw)
    ]


def _parse_nst_timestamp(lines: list[str]) -> str | None:
    for line in lines:
        match = re.search(
            r"DATE/TIME\s+(\d{2}):(\d{2}):(\d{2})/(\d{2}):(\d{2}):(\d{2})",
            line,
        )
        if not match:
            continue
        month, day, year, hour, minute, second = [int(part) for part in match.groups()]
        year += 2000 if year < 70 else 1900
        return datetime(
            year, month, day, hour, minute, second, tzinfo=timezone.utc
        ).isoformat()
    return None


def _parse_azran(value: str) -> tuple[int, int] | None:
    match = re.fullmatch(r"\s*(\d{1,3})/\s*(\d{1,3})\s*", value or "")
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _parse_forecast_position(
    raw_value: str, radar_lat: float, radar_lon: float, minutes: int
) -> dict[str, Any] | None:
    raw_value = str(raw_value or "").strip()
    if raw_value.upper() == "NO DATA":
        return None
    parsed = _parse_azran(raw_value)
    if not parsed:
        return None
    azimuth, range_nm = parsed
    lat, lon = _bearing_range_to_latlon(radar_lat, radar_lon, azimuth, range_nm)
    return {
        "minutes": minutes,
        "azimuth_deg": azimuth,
        "range_nm": range_nm,
        "lat": lat,
        "lon": lon,
    }


_NST_ROW_RE = re.compile(
    r"^P?\s*"
    r"(?P<id>[A-Z0-9]{1,3})\s+"
    r"(?P<current>\d{1,3}/\s*\d{1,3})\s+"
    r"(?P<motion>\d{1,3}/\s*\d{1,3})\s+"
    r"(?P<fcst15>(?:\d{1,3}/\s*\d{1,3}|NO DATA))\s+"
    r"(?P<fcst30>(?:\d{1,3}/\s*\d{1,3}|NO DATA))\s+"
    r"(?P<fcst45>(?:\d{1,3}/\s*\d{1,3}|NO DATA))\s+"
    r"(?P<fcst60>(?:\d{1,3}/\s*\d{1,3}|NO DATA))\s+"
    r"(?P<error>\d+(?:\.\d+)?/\s*\d+(?:\.\d+)?)"
)


def parse_nst_storm_tracks(raw: bytes, source_path: str = "") -> dict[str, Any]:
    """Parse a Level III NST product into cell metadata and GeoJSON features."""
    lines = [line.rstrip() for line in _printable_strings(raw)]
    timestamp = _parse_nst_timestamp(lines)
    radar_lat = radar_lon = None
    avg_speed_kt = avg_direction_deg = None
    cell_count = None

    for line in lines:
        if match := re.search(r"NUMBER OF STORM CELLS\s+(\d+)", line):
            cell_count = int(match.group(1))
        if match := re.search(r"AVG SPEED\s+(\d+)\s+KTS\s+AVG DIRECTION\s+(\d+)\s+DEG", line):
            avg_speed_kt = int(match.group(1))
            avg_direction_deg = int(match.group(2))

    # Radar lat/lon are not printed in the NST table, so the caller attaches
    # site coordinates before GeoJSON conversion. Keep this parser tolerant for
    # unit tests and direct file inspection.
    cells: list[dict[str, Any]] = []
    raw_rows: list[dict[str, str]] = []
    for line in lines:
        row = _NST_ROW_RE.match(line)
        if not row:
            continue
        values = row.groupdict()
        raw_rows.append(values)
        current = _parse_azran(values["current"])
        motion = _parse_azran(values["motion"])
        if not current or not motion:
            continue
        current_azimuth, current_range_nm = current
        motion_to_degrees, speed_kt = motion
        cells.append(
            {
                "id": values["id"],
                "current_azimuth_deg": current_azimuth,
                "current_range_nm": current_range_nm,
                "motion_to_degrees": motion_to_degrees,
                "speed_kt": speed_kt,
                "forecast_raw": {
                    15: values["fcst15"].strip(),
                    30: values["fcst30"].strip(),
                    45: values["fcst45"].strip(),
                    60: values["fcst60"].strip(),
                },
                "error": values["error"].replace(" ", ""),
            }
        )

    return {
        "source_path": source_path,
        "timestamp": timestamp,
        "cell_count": cell_count if cell_count is not None else len(cells),
        "average_motion": {
            "speed_kt": avg_speed_kt,
            "motion_to_degrees": avg_direction_deg,
        },
        "cells": cells,
        "raw_rows": raw_rows,
    }


def _attach_geojson(
    parsed: dict[str, Any], radar_lat: float, radar_lon: float, site_id: str
) -> dict[str, Any]:
    features: list[dict[str, Any]] = []
    cells = []
    for cell in parsed.get("cells") or []:
        lat, lon = _bearing_range_to_latlon(
            radar_lat, radar_lon, cell["current_azimuth_deg"], cell["current_range_nm"]
        )
        forecasts = [
            _parse_forecast_position(raw_value, radar_lat, radar_lon, minutes)
            for minutes, raw_value in (cell.get("forecast_raw") or {}).items()
        ]
        forecasts = [forecast for forecast in forecasts if forecast is not None]

        enriched = {
            **cell,
            "lat": lat,
            "lon": lon,
            "forecasts": forecasts,
            "site": site_id,
            "timestamp": parsed.get("timestamp"),
        }
        cells.append(enriched)

        point_props = {
            "kind": "nst_cell",
            "site": site_id,
            "cell_id": cell["id"],
            "timestamp": parsed.get("timestamp"),
            "motion_to_degrees": cell["motion_to_degrees"],
            "speed_kt": cell["speed_kt"],
            "current_azimuth_deg": cell["current_azimuth_deg"],
            "current_range_nm": cell["current_range_nm"],
            "error": cell.get("error"),
        }
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": point_props,
            }
        )
        track_coords = [[lon, lat], *[[fcst["lon"], fcst["lat"]] for fcst in forecasts]]
        if len(track_coords) > 1:
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": track_coords},
                    "properties": {
                        **point_props,
                        "kind": "nst_forecast_track",
                    },
                }
            )

    return {
        **parsed,
        "site": site_id,
        "radar_location": {"lat": radar_lat, "lon": radar_lon},
        "cells": cells,
        "feature_collection": {"type": "FeatureCollection", "features": features},
    }


def parse_nst_file(path: str | os.PathLike[str], site_id: str | None = None) -> dict[str, Any]:
    file_path = Path(path)
    parsed = parse_nst_storm_tracks(file_path.read_bytes(), str(file_path))
    if not site_id:
        return parsed

    try:
        from pyart.io.nexrad_common import NEXRAD_LOCATIONS

        location = NEXRAD_LOCATIONS.get(site_id)
        if not location:
            return parsed
        return _attach_geojson(
            parsed,
            float(location["lat"]),
            float(location["lon"]),
            normalize_radar_site_id(site_id),
        )
    except Exception:
        return parsed


def _download_nst_files(site_id: str, hours: float, latest_only: bool) -> list[Path]:
    from radar import radar_nodd_utils

    data_dir, total_files, _downloaded = radar_nodd_utils.download_radar_data(
        "Level 3",
        site_id,
        _NST_PRODUCT,
        float(hours),
        str(Path(CACHE_ROOT) / "radar" / "live"),
        provider="aws",
        latest_only=latest_only,
    )
    if not data_dir or int(total_files or 0) <= 0:
        return []
    return sorted(Path(data_dir).glob("*"))


def _timestamp_distance_seconds(path: Path, target: datetime | None) -> float:
    if target is None:
        return 0.0
    parsed = parse_nst_storm_tracks(path.read_bytes(), str(path))
    raw_ts = parsed.get("timestamp")
    if not raw_ts:
        return float("inf")
    try:
        ts = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
    except ValueError:
        return float("inf")
    return abs((ts - target).total_seconds())


def get_radar_storm_tracks_data(
    site: str = "KMHX",
    timestamp: str | None = None,
    hours: float = _NST_CACHE_LOOKBACK_HOURS,
    force: bool = False,
) -> dict[str, Any]:
    site_id = normalize_radar_site_id(site)
    try:
        from pyart.io.nexrad_common import NEXRAD_LOCATIONS

        if site_id not in NEXRAD_LOCATIONS:
            raise HTTPException(status_code=404, detail=f"Unknown radar site: {site_id}")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    target_dt = None
    if timestamp:
        try:
            target_dt = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
            if target_dt.tzinfo is None:
                target_dt = target_dt.replace(tzinfo=timezone.utc)
            else:
                target_dt = target_dt.astimezone(timezone.utc)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Invalid timestamp.") from exc

    files = _download_nst_files(
        site_id,
        max(0.25, min(float(hours or 2), 12.0)),
        latest_only=(target_dt is None and not force),
    )
    if not files:
        return {
            "status": "empty",
            "site": site_id,
            "timestamp": None,
            "cell_count": 0,
            "cells": [],
            "feature_collection": {"type": "FeatureCollection", "features": []},
        }

    if target_dt:
        tolerance = timedelta(minutes=8).total_seconds()
        selected = min(files, key=lambda path: _timestamp_distance_seconds(path, target_dt))
        if _timestamp_distance_seconds(selected, target_dt) > tolerance:
            selected = files[-1]
    else:
        selected = files[-1]

    parsed = parse_nst_file(selected, site_id)
    return {
        "status": "success",
        **parsed,
    }
