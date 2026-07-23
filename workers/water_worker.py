"""Background worker for cached NOAA water map markers.

The water map reads broad marker coverage from NWS river gauges plus NOS
CO-OPS coastal stations. Per-station API calls are reserved for user-click
enrichment where needed.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import urllib.request

from app_core.upstream_ledger import urlopen

from services.water_service import _fetch_json
from workers._freshness import is_cache_fresh, mark_run_complete

WORKER_NAME = "water_riv_gauges"
FRESHNESS_WINDOW_SEC = 20 * 60
RESULT_PAGE_SIZE = 2000

RIV_GAUGES_QUERY_URL = (
    "https://mapservices.weather.noaa.gov/eventdriven/rest/services/"
    "water/riv_gauges/MapServer/0/query"
)
COOPS_QUERY_BASE_URL = (
    "https://mapservices.weather.noaa.gov/static/rest/services/"
    "NOS_Observations/CO_OPS_Stations/MapServer/{layer}/query"
)
NDBC_LATEST_OBS_URL = "https://www.ndbc.noaa.gov/data/latest_obs/latest_obs.txt"
CACHE_DIR = Path(__file__).resolve().parent.parent / "cache" / "water"
INDEX_FILE = CACHE_DIR / "riv_gauges.json"

OUT_FIELDS = ",".join(
    (
        "gaugelid",
        "status",
        "location",
        "waterbody",
        "state",
        "obstime",
        "wfo",
        "url",
        "action",
        "flood",
        "moderate",
        "major",
        "observed",
        "latitude",
        "longitude",
        "units",
    )
)

COOPS_OUT_FIELDS = ",".join(
    (
        "id",
        "name",
        "state",
        "affil",
        "latitude",
        "longitude",
        "data",
        "metaapi",
        "dataapi",
        "cg_filedate",
        "cg_ingesttime",
    )
)

COOPS_LAYERS = (
    (0, "water_level", "Water Level"),
    (2, "current", "Current"),
)
OPTIONAL_COOPS_LAYERS = {2}
REQUIRED_NETWORKS = ("river", "coastal", "buoy")


def _log(message: str) -> None:
    print(f"[water_worker] {message}", flush=True)


def _write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _fetch_text_url(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "NCHurricane Dashboard/2026",
            "Accept": "text/plain",
        },
    )
    with urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _as_float(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number <= -999:
        return None
    return number


def _arcgis_time(value) -> str:
    if value in (None, ""):
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number > 10_000_000_000:
        number = number / 1000.0
    try:
        return datetime.fromtimestamp(number, tz=timezone.utc).isoformat()
    except Exception:
        return str(value)


def _ndbc_time(parts: list[str]) -> str:
    try:
        year, month, day, hour, minute = [int(value) for value in parts]
        return datetime(year, month, day, hour, minute, tzinfo=timezone.utc).isoformat()
    except Exception:
        return ""


def _category(value: str | None) -> str:
    text = str(value or "").strip().lower()
    if not text or text in {"no flooding", "not_defined", "none", "normal"}:
        return ""
    return text


def _thresholds(attrs: dict) -> dict:
    parsed = {}
    for source_key, target_key in (
        ("action", "action"),
        ("flood", "minor"),
        ("moderate", "moderate"),
        ("major", "major"),
    ):
        stage = _as_float(attrs.get(source_key))
        if stage is not None:
            parsed[target_key] = {"stage": stage, "flow": None}
    return parsed


def _feature_coords(feature: dict, attrs: dict) -> tuple[float | None, float | None]:
    lat = _as_float(attrs.get("latitude"))
    lon = _as_float(attrs.get("longitude"))
    if lat is not None and lon is not None:
        return lat, lon
    geometry = feature.get("geometry") or {}
    return _as_float(geometry.get("y")), _as_float(geometry.get("x"))


def _normalize_feature(feature: dict) -> dict | None:
    attrs = feature.get("attributes") or feature.get("properties") or {}
    lid = str(attrs.get("gaugelid") or "").strip().upper()
    if not lid:
        return None
    lat, lon = _feature_coords(feature, attrs)
    if lat is None or lon is None:
        return None

    observed = _as_float(attrs.get("observed"))
    units = str(attrs.get("units") or "ft").strip()
    observed_category = _category(attrs.get("status"))
    timestamp = _arcgis_time(attrs.get("obstime"))
    readings = {}
    if observed is not None:
        readings["stage"] = {
            "value": observed,
            "timestamp": timestamp,
            "qualifiers": "",
            "label": "Stage",
            "units": units,
        }

    return {
        "site_id": lid,
        "nwps_lid": lid,
        "name": attrs.get("location") or lid,
        "lat": lat,
        "lon": lon,
        "site_type": "NWPS",
        "network": "river",
        "station_type": "river_gauge",
        "capabilities": ["River Gauge"],
        "waterbody": attrs.get("waterbody") or "",
        "state": attrs.get("state") or "",
        "wfo": attrs.get("wfo") or "",
        "readings": readings,
        "status": "normal" if readings else "missing",
        "observed_category": observed_category,
        "forecast_category": "",
        "forecast": None,
        "flood": {
            "stage_units": units,
            "flow_units": "",
            "categories": _thresholds(attrs),
            "impacts": [],
            "historic_crests": [],
            "recent_crests": [],
        },
        "source_url": attrs.get("url") or f"https://water.noaa.gov/gauges/{lid.lower()}",
        "provider": "NOAA",
        "source": "NOAA Riv Gauges",
    }


def _normalize_coops_feature(feature: dict, station_type: str, station_label: str) -> dict | None:
    attrs = feature.get("attributes") or feature.get("properties") or {}
    coops_id = str(attrs.get("id") or "").strip()
    if not coops_id:
        return None
    lat, lon = _feature_coords(feature, attrs)
    if lat is None or lon is None:
        return None

    state = str(attrs.get("state") or "").strip()
    name = str(attrs.get("name") or coops_id).strip()
    file_time = _arcgis_time(attrs.get("cg_filedate"))
    source_url = f"https://tidesandcurrents.noaa.gov/stationhome.html?id={coops_id}"
    return {
        "site_id": f"COOPS_{coops_id}",
        "coops_id": coops_id,
        "name": name,
        "lat": lat,
        "lon": lon,
        "site_type": "CO-OPS",
        "network": "coastal",
        "station_type": station_type,
        "capabilities": [station_label],
        "waterbody": "",
        "state": state,
        "affiliation": attrs.get("affil") or "",
        "readings": {},
        "status": "normal",
        "observed_category": "",
        "forecast_category": "",
        "forecast": None,
        "flood": {
            "stage_units": "",
            "flow_units": "",
            "categories": {},
            "impacts": [],
            "historic_crests": [],
            "recent_crests": [],
        },
        "source_url": source_url,
        "data_url": attrs.get("data") or "",
        "dataapi_url": attrs.get("dataapi") or "",
        "metaapi_url": attrs.get("metaapi") or "",
        "updated": file_time,
        "provider": "NOAA",
        "source": "NOAA CO-OPS",
    }


def _reading(value, units: str, timestamp: str, label: str) -> dict | None:
    number = _as_float(value)
    if number is None:
        return None
    return {
        "value": number,
        "timestamp": timestamp,
        "qualifiers": "",
        "label": label,
        "units": units,
    }


def _normalize_ndbc_row(parts: list[str]) -> dict | None:
    if len(parts) < 21:
        return None
    station_id = parts[0].strip().upper()
    lat = _as_float(parts[1])
    lon = _as_float(parts[2])
    if not station_id or lat is None or lon is None:
        return None

    timestamp = _ndbc_time(parts[3:8])
    readings = {}
    for key, value, units, label in (
        ("wind_direction", parts[8], "degT", "Wind Direction"),
        ("wind_speed", parts[9], "m/s", "Wind Speed"),
        ("wind_gust", parts[10], "m/s", "Wind Gust"),
        ("wave_height", parts[11], "m", "Wave Height"),
        ("dominant_wave_period", parts[12], "sec", "Dominant Wave Period"),
        ("average_wave_period", parts[13], "sec", "Average Wave Period"),
        ("mean_wave_direction", parts[14], "degT", "Mean Wave Direction"),
        ("pressure", parts[15], "hPa", "Pressure"),
        ("pressure_tendency", parts[16], "hPa", "Pressure Tendency"),
        ("air_temperature", parts[17], "degC", "Air Temperature"),
        ("water_temperature", parts[18], "degC", "Water Temperature"),
        ("dewpoint", parts[19], "degC", "Dew Point"),
        ("visibility", parts[20], "nmi", "Visibility"),
        ("tide", parts[21] if len(parts) > 21 else "", "ft", "Tide"),
    ):
        reading = _reading(value, units, timestamp, label)
        if reading:
            readings[key] = reading

    return {
        "site_id": f"NDBC_{station_id}",
        "ndbc_id": station_id,
        "name": f"NDBC {station_id}",
        "lat": lat,
        "lon": lon,
        "site_type": "NDBC",
        "network": "buoy",
        "station_type": "ndbc",
        "capabilities": ["Marine Observations"],
        "waterbody": "",
        "state": "",
        "readings": readings,
        "status": "normal" if readings else "missing",
        "observed_category": "",
        "forecast_category": "",
        "forecast": None,
        "flood": {
            "stage_units": "",
            "flow_units": "",
            "categories": {},
            "impacts": [],
            "historic_crests": [],
            "recent_crests": [],
        },
        "source_url": f"https://www.ndbc.noaa.gov/station_page.php?station={station_id.lower()}",
        "updated": timestamp,
        "provider": "NOAA",
        "source": "NOAA NDBC",
    }


def _fetch_feature_page(offset: int) -> list[dict]:
    payload = _fetch_json(
        RIV_GAUGES_QUERY_URL,
        {
            "where": "1=1",
            "outFields": OUT_FIELDS,
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "json",
            "resultOffset": offset,
            "resultRecordCount": RESULT_PAGE_SIZE,
        },
        timeout=30,
    )
    if payload.get("error"):
        raise RuntimeError(f"River gauge source error: {payload['error']}")
    return payload.get("features") if isinstance(payload.get("features"), list) else []


def _fetch_coops_feature_page(layer: int, offset: int) -> list[dict]:
    payload = _fetch_json(
        COOPS_QUERY_BASE_URL.format(layer=layer),
        {
            "where": "1=1",
            "outFields": COOPS_OUT_FIELDS,
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "json",
            "resultOffset": offset,
            "resultRecordCount": RESULT_PAGE_SIZE,
        },
        timeout=30,
    )
    if payload.get("error"):
        if layer in OPTIONAL_COOPS_LAYERS:
            _log(
                f"optional CO-OPS layer {layer} unavailable; "
                f"skipping: {payload['error']}"
            )
            return []
        raise RuntimeError(f"CO-OPS source error: {payload['error']}")
    return payload.get("features") if isinstance(payload.get("features"), list) else []


def _fetch_ndbc_latest_stations() -> list[dict]:
    stations = []
    text = _fetch_text_url(NDBC_LATEST_OBS_URL)
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        station = _normalize_ndbc_row(line.split())
        if station:
            stations.append(station)
    return stations


def _dedupe_stations(stations: list[dict]) -> list[dict]:
    by_site = {}
    for station in stations:
        site_id = station.get("site_id")
        if not site_id:
            continue
        existing = by_site.get(site_id)
        if existing and station.get("network") == "coastal":
            capabilities = list(dict.fromkeys((existing.get("capabilities") or []) + (station.get("capabilities") or [])))
            existing["capabilities"] = capabilities
            if len(capabilities) > 1:
                existing["station_type"] = "multi"
        elif site_id not in by_site:
            by_site[site_id] = station
    return sorted(by_site.values(), key=lambda item: str(item.get("name") or item.get("site_id") or ""))


def _existing_network_counts() -> dict[str, int]:
    try:
        payload = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    counts = payload.get("network_counts")
    if isinstance(counts, dict):
        return {
            str(network): int(count)
            for network, count in counts.items()
            if str(count).isdigit()
        }
    return {}


def _validate_network_counts(network_counts: dict[str, int]) -> None:
    existing_counts = _existing_network_counts()
    for network in REQUIRED_NETWORKS:
        count = int(network_counts.get(network, 0))
        if count <= 0:
            raise RuntimeError(
                f"Refusing to publish Water index without {network} stations."
            )
        prior_count = int(existing_counts.get(network, 0))
        if prior_count > 0 and count < prior_count / 2:
            raise RuntimeError(
                "Refusing to publish sharply reduced Water network "
                f"{network}: {count} stations versus prior {prior_count}."
            )


def refresh_riv_gauges_cache() -> dict:
    started_at = time.monotonic()
    stations: list[dict] = []
    offset = 0
    page = 1
    while True:
        _log(f"fetching page {page} offset={offset}")
        features = _fetch_feature_page(offset)
        _log(f"page {page}: returned {len(features)} features")
        if not features:
            break
        for feature in features:
            station = _normalize_feature(feature)
            if station:
                stations.append(station)
        if len(features) < RESULT_PAGE_SIZE:
            break
        offset += RESULT_PAGE_SIZE
        page += 1

    for layer, station_type, station_label in COOPS_LAYERS:
        offset = 0
        page = 1
        while True:
            _log(f"fetching CO-OPS {station_label} page {page} offset={offset}")
            features = _fetch_coops_feature_page(layer, offset)
            _log(f"CO-OPS {station_label} page {page}: returned {len(features)} features")
            if not features:
                break
            for feature in features:
                station = _normalize_coops_feature(feature, station_type, station_label)
                if station:
                    stations.append(station)
            if len(features) < RESULT_PAGE_SIZE:
                break
            offset += RESULT_PAGE_SIZE
            page += 1

    _log("fetching NDBC latest observations")
    ndbc_stations = _fetch_ndbc_latest_stations()
    _log(f"NDBC latest observations: returned {len(ndbc_stations)} stations")
    stations.extend(ndbc_stations)

    deduped = _dedupe_stations(stations)
    network_counts = {}
    for station in deduped:
        network = station.get("network") or "unknown"
        network_counts[network] = network_counts.get(network, 0) + 1
    _validate_network_counts(network_counts)
    payload = {
        "status": "success",
        "provider": "NOAA",
        "source": "NOAA water gauges",
        "updated": datetime.now(timezone.utc).isoformat(),
        "count": len(deduped),
        "network_counts": network_counts,
        "stations": deduped,
    }
    _write_json_atomic(INDEX_FILE, payload)
    elapsed = time.monotonic() - started_at
    _log(f"complete: cached {len(deduped)} gauges in {elapsed:.1f}s")
    return payload


def run_water_worker(*, force: bool = False) -> None:
    if not force and is_cache_fresh(WORKER_NAME, FRESHNESS_WINDOW_SEC):
        _log("Cache fresh; skipping.")
        return
    refresh_riv_gauges_cache()
    mark_run_complete(WORKER_NAME)


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh cached NOAA river gauge markers.")
    parser.add_argument("--force", action="store_true", help="Bypass freshness gate.")
    parser.add_argument("--log-to-file", action="store_true", help="Redirect output to logs/scheduled/water_riv_gauges.log.")
    args = parser.parse_args()

    if args.log_to_file:
        from workers._freshness import redirect_stdio_to_log

        redirect_stdio_to_log("water_riv_gauges")

    run_water_worker(force=args.force)


if __name__ == "__main__":
    main()
