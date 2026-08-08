"""NOAA water monitoring services."""

from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import threading
import time
from urllib.parse import urlencode
import urllib.error
import urllib.request

from app_core.refresh_coordinator import Submission, get_refresh_coordinator
from app_core.upstream_ledger import urlopen

from fastapi import HTTPException

NWPS_GAUGE_URL = "https://api.water.noaa.gov/nwps/v1/gauges/{identifier}"
NWPS_GAUGE_PAGE_URL = "https://water.noaa.gov/gauges/{identifier}"
COOPS_DATA_URL = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
WATER_CACHE_TTL_SEC = 180
WATER_CACHE_MAX_ENTRIES = 128
WATER_DETAIL_CACHE_TTL_SEC = 5 * 60
WATER_DETAIL_CACHE_MAX_ENTRIES = 512
WATER_RIV_GAUGES_CACHE_MAX_AGE_SEC = 30 * 60
WATER_INDEX_RETRY_AFTER_SEC = 2.0
WATER_REQUIRED_NETWORKS = frozenset({"river", "coastal", "buoy"})
WATER_RIV_GAUGES_INDEX_FILE = Path(__file__).resolve().parent.parent / "cache" / "water" / "riv_gauges.json"

_WATER_CACHE: OrderedDict[str, tuple[float, dict]] = OrderedDict()
_WATER_CACHE_LOCK = threading.RLock()
_WATER_DETAIL_CACHE: OrderedDict[str, tuple[float, dict]] = OrderedDict()
_WATER_DETAIL_CACHE_LOCK = threading.RLock()
_DETAIL_PROVIDER_LOCKS = {
    "coops": threading.Lock(),
    "nwps": threading.Lock(),
}
_DETAIL_PROVIDER_BACKOFF: dict[str, tuple[int, float]] = {}
_NWPS_MISSING_VALUE = {-999, -9999}


def _read_json_request(req: urllib.request.Request, timeout: int = 20, retries: int = 1) -> dict:
    for attempt in range(retries + 1):
        try:
            with urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < retries:
                retry_after = exc.headers.get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after else 2.0
                except (TypeError, ValueError):
                    delay = 2.0
                time.sleep(max(1.0, min(delay, 5.0)))
                continue
            raise
    raise RuntimeError("request retry failed")


def _cache_get(key: str) -> dict | None:
    with _WATER_CACHE_LOCK:
        cached = _WATER_CACHE.get(key)
        if not cached:
            return None
        ts, data = cached
        if time.monotonic() - ts > WATER_CACHE_TTL_SEC:
            _WATER_CACHE.pop(key, None)
            return None
        _WATER_CACHE.move_to_end(key)
        return data


def _cache_set(key: str, data: dict) -> dict:
    now = time.monotonic()
    with _WATER_CACHE_LOCK:
        expired = [
            cache_key
            for cache_key, (cached_at, _payload) in _WATER_CACHE.items()
            if now - cached_at > WATER_CACHE_TTL_SEC
        ]
        for cache_key in expired:
            _WATER_CACHE.pop(cache_key, None)
        _WATER_CACHE[key] = (now, data)
        _WATER_CACHE.move_to_end(key)
        while len(_WATER_CACHE) > WATER_CACHE_MAX_ENTRIES:
            _WATER_CACHE.popitem(last=False)
    return data


def _detail_cache_get(key: str) -> dict | None:
    with _WATER_DETAIL_CACHE_LOCK:
        cached = _WATER_DETAIL_CACHE.get(key)
        if not cached:
            return None
        ts, data = cached
        if time.monotonic() - ts > WATER_DETAIL_CACHE_TTL_SEC:
            _WATER_DETAIL_CACHE.pop(key, None)
            return None
        _WATER_DETAIL_CACHE.move_to_end(key)
        return data


def _detail_cache_set(key: str, data: dict) -> dict:
    with _WATER_DETAIL_CACHE_LOCK:
        _WATER_DETAIL_CACHE[key] = (time.monotonic(), data)
        _WATER_DETAIL_CACHE.move_to_end(key)
        while len(_WATER_DETAIL_CACHE) > WATER_DETAIL_CACHE_MAX_ENTRIES:
            _WATER_DETAIL_CACHE.popitem(last=False)
    return data


def _fetch_station_detail(provider: str, cache_key: str, fetcher) -> dict:
    cached = _detail_cache_get(cache_key)
    if cached is not None:
        return cached
    with _DETAIL_PROVIDER_LOCKS[provider]:
        cached = _detail_cache_get(cache_key)
        if cached is not None:
            return cached
        failures, retry_at = _DETAIL_PROVIDER_BACKOFF.get(provider, (0, 0.0))
        now = time.monotonic()
        if retry_at > now:
            raise RuntimeError(
                f"{provider.upper()} detail requests are backed off for "
                f"{max(1, int(retry_at - now))} seconds."
            )
        try:
            data = fetcher()
        except Exception:
            failures += 1
            delay = min(300.0, 5.0 * (2 ** (failures - 1)))
            _DETAIL_PROVIDER_BACKOFF[provider] = (
                failures,
                time.monotonic() + delay,
            )
            raise
        _DETAIL_PROVIDER_BACKOFF.pop(provider, None)
        return _detail_cache_set(cache_key, data)


def _fetch_json(url: str, params: dict, timeout: int = 20) -> dict:
    full_url = f"{url}?{urlencode(params)}"
    req = urllib.request.Request(
        full_url,
        headers={
            "User-Agent": "NCHurricane Dashboard/2026",
            "Accept": "application/json",
        },
    )
    return _read_json_request(req, timeout=timeout)


def _fetch_json_url(url: str, timeout: int = 20) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "NCHurricane Dashboard/2026",
            "Accept": "application/json",
        },
    )
    return _read_json_request(req, timeout=timeout)


def _parse_bbox(bbox: str) -> tuple[float, float, float, float]:
    try:
        west, south, east, north = [float(part) for part in str(bbox).split(",")]
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail="bbox must be west,south,east,north.",
        ) from exc
    if not (-90 <= south <= 90 and -90 <= north <= 90):
        raise HTTPException(status_code=422, detail="bbox latitude coordinates are outside valid bounds.")
    if east - west >= 360:
        west, east = -180.0, 180.0
    else:
        west = max(-180.0, min(180.0, west))
        east = max(-180.0, min(180.0, east))
    if west >= east or south >= north:
        raise HTTPException(status_code=422, detail="bbox must be west,south,east,north.")
    return west, south, east, north


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def _classify_station(station: dict) -> str:
    latest_ts = None
    for reading in station.get("readings", {}).values():
        dt = _parse_dt(reading.get("timestamp"))
        if dt and (latest_ts is None or dt > latest_ts):
            latest_ts = dt
    if latest_ts is None:
        return "missing"
    if datetime.now(timezone.utc) - latest_ts > timedelta(hours=6):
        return "stale"
    return "normal"


def _valid_nwps_number(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number in _NWPS_MISSING_VALUE:
        return None
    return number


def _nwps_reading(status: dict, label: str) -> dict | None:
    value = _valid_nwps_number(status.get("primary"))
    if value is None:
        return None
    return {
        "value": value,
        "timestamp": status.get("validTime"),
        "qualifiers": "",
        "label": label,
        "units": status.get("primaryUnit") or "",
    }


def _nwps_thresholds(flood: dict) -> dict:
    categories = flood.get("categories") or {}
    parsed = {}
    for key in ("action", "minor", "moderate", "major"):
        item = categories.get(key) or {}
        stage = _valid_nwps_number(item.get("stage"))
        flow = _valid_nwps_number(item.get("flow"))
        if stage is not None or flow is not None:
            parsed[key] = {"stage": stage, "flow": flow}
    return parsed


def _parse_nwps_gauge(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise HTTPException(status_code=404, detail="NWPS gauge not found.")
    lid = str(raw.get("lid") or "").strip().upper()
    if not lid:
        raise HTTPException(status_code=404, detail="NWPS gauge not found.")
    observed_status = raw.get("status", {}).get("observed") or {}
    forecast_status = raw.get("status", {}).get("forecast") or {}
    flood = raw.get("flood") or {}
    images = raw.get("images") or {}
    readings = {}
    observed_label = "Stage"
    pedts_observed = str((raw.get("pedts") or {}).get("observed") or "")
    if pedts_observed.startswith("HM"):
        observed_label = "Tide Height"
    observed_reading = _nwps_reading(observed_status, observed_label)
    if observed_reading:
        readings["stage"] = observed_reading

    forecast_value = _valid_nwps_number(forecast_status.get("primary"))
    forecast = None
    if forecast_value is not None:
        forecast = {
            "value": forecast_value,
            "units": forecast_status.get("primaryUnit") or "",
            "timestamp": forecast_status.get("validTime"),
            "category": forecast_status.get("floodCategory") or raw.get("ForecastFloodCategory") or "",
        }

    station = {
        "site_id": lid,
        "nwps_lid": lid,
        "usgs_id": str(raw.get("usgsId") or "").strip(),
        "name": raw.get("name") or lid,
        "lat": raw.get("latitude"),
        "lon": raw.get("longitude"),
        "site_type": "NWPS",
        "county": raw.get("county") or "",
        "state": (raw.get("state") or {}).get("abbreviation") or "",
        "wfo": (raw.get("wfo") or {}).get("abbreviation") or "",
        "rfc": (raw.get("rfc") or {}).get("abbreviation") or "",
        "time_zone": raw.get("timeZone") or "",
        "readings": readings,
        "status": _classify_station({"readings": readings}),
        "observed_category": observed_status.get("floodCategory") or raw.get("ObservedFloodCategory") or "",
        "forecast_category": forecast_status.get("floodCategory") or raw.get("ForecastFloodCategory") or "",
        "forecast": forecast,
        "flood": {
            "stage_units": flood.get("stageUnits") or observed_status.get("primaryUnit") or "",
            "flow_units": flood.get("flowUnits") or "",
            "categories": _nwps_thresholds(flood),
        },
        "hydrograph_url": (images.get("hydrograph") or {}).get("default") or "",
        "floodcat_hydrograph_url": (images.get("hydrograph") or {}).get("floodcat") or "",
        "forecast_reliability": raw.get("forecastReliability") or "",
        "source_url": NWPS_GAUGE_PAGE_URL.format(identifier=lid.lower()),
        "provider": "NOAA",
        "source": "NOAA NWPS",
    }
    return station


def _fetch_coops_live_readings(coops_id: str, station_type: str) -> dict:
    product = "currents" if str(station_type or "").lower() == "current" else "water_level"
    params: dict[str, str] = {
        "station": coops_id,
        "product": product,
        "datum": "MLLW",
        "time_zone": "gmt",
        "units": "english",
        "format": "json",
        "range": "1",
    }
    if product == "currents":
        params["bin"] = "1"
    raw = _fetch_json(COOPS_DATA_URL, params, timeout=15)
    raw_rows = raw.get("data") if isinstance(raw, dict) else None
    data_rows = (
        [row for row in raw_rows if isinstance(row, dict)]
        if isinstance(raw_rows, list)
        else []
    )
    if not data_rows:
        return {}
    latest = data_rows[-1]
    ts_raw = str(latest.get("t") or "").strip()
    try:
        ts = datetime.strptime(ts_raw, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        ts = ts_raw
    readings: dict = {}
    if product == "water_level":
        value = _valid_nwps_number(latest.get("v"))
        if value is not None:
            readings["water_level"] = {
                "value": value,
                "timestamp": ts,
                "qualifiers": str(latest.get("q") or ""),
                "label": "Water Level",
                "units": "ft",
            }
    else:
        speed = _valid_nwps_number(latest.get("s"))
        direction = _valid_nwps_number(latest.get("d"))
        if speed is not None:
            readings["current_speed"] = {
                "value": speed,
                "timestamp": ts,
                "qualifiers": "",
                "label": "Current Speed",
                "units": "knots",
            }
        if direction is not None:
            readings["current_direction"] = {
                "value": direction,
                "timestamp": ts,
                "qualifiers": "",
                "label": "Current Direction",
                "units": "°T",
            }
    return readings


def _is_nwps_identifier(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9]{3,16}", str(value or "").strip()))


def _read_riv_gauges_index() -> dict | None:
    try:
        with WATER_RIV_GAUGES_INDEX_FILE.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except FileNotFoundError:
        return None
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"NOAA river gauge cache unreadable: {exc}") from exc
    if not isinstance(payload, dict):
        return None
    return payload


def _parse_water_networks(value: str | None) -> set[str]:
    if value is None:
        return {"river", "coastal", "buoy"}
    requested = {
        item.strip().lower()
        for item in str(value or "").split(",")
        if item.strip()
    }
    allowed = {"river", "coastal", "buoy"}
    return requested & allowed


def _station_in_bbox(station: dict, west: float, south: float, east: float, north: float) -> bool:
    try:
        lat = float(station.get("lat"))
        lon = float(station.get("lon"))
    except (TypeError, ValueError):
        return False
    return west <= lon <= east and south <= lat <= north


def _water_index_refresh() -> dict:
    from workers.water_worker import run_water_worker

    run_water_worker(force=True)
    payload = _read_riv_gauges_index() or {}
    return {"source_timestamp": payload.get("updated")}


def _kickoff_water_index_refresh() -> Submission:
    return get_refresh_coordinator().submit(
        key=("water", "station-index"),
        provider="noaa-water",
        function=_water_index_refresh,
        min_success_interval_seconds=WATER_RIV_GAUGES_CACHE_MAX_AGE_SEC,
    )


def _missing_water_networks(payload: dict | None) -> list[str]:
    if not payload:
        return sorted(WATER_REQUIRED_NETWORKS)
    counts = payload.get("network_counts")
    if not isinstance(counts, dict) or not counts:
        counts = {}
        for station in payload.get("stations") or []:
            network = str(station.get("network") or "river").lower()
            counts[network] = counts.get(network, 0) + 1
    missing = []
    for network in WATER_REQUIRED_NETWORKS:
        try:
            count = int(counts.get(network, 0) or 0)
        except (TypeError, ValueError):
            count = 0
        if count <= 0:
            missing.append(network)
    return sorted(missing)


def _balanced_station_limit(
    stations: list[dict],
    selected_networks: set[str],
    limit: int,
) -> list[dict]:
    if len(selected_networks) <= 1:
        return stations[:limit]
    buckets = {
        network: [
            station
            for station in stations
            if (station.get("network") or "river") == network
        ]
        for network in ("coastal", "buoy", "river")
        if network in selected_networks
    }
    per_network = limit // len(selected_networks)
    selected = []
    selected_ids = set()
    for bucket in buckets.values():
        for station in bucket[:per_network]:
            selected.append(station)
            selected_ids.add(str(station.get("site_id") or id(station)))
    if len(selected) < limit:
        for station in stations:
            station_id = str(station.get("site_id") or id(station))
            if station_id in selected_ids:
                continue
            selected.append(station)
            selected_ids.add(station_id)
            if len(selected) >= limit:
                break
    return selected


def get_water_stations_data(bbox: str, max_sites: int = 300, networks: str | None = None) -> dict:
    west, south, east, north = _parse_bbox(bbox)
    limit = max(1, min(int(max_sites or 300), 15000))
    selected_networks = _parse_water_networks(networks)
    payload = _read_riv_gauges_index()
    updated = payload.get("updated") if payload else ""
    updated_dt = _parse_dt(updated)
    cache_age_seconds = (
        max(0, int((datetime.now(timezone.utc) - updated_dt).total_seconds()))
        if updated_dt
        else None
    )
    missing_networks = _missing_water_networks(payload)
    stale = payload is None or cache_age_seconds is None or (
        cache_age_seconds > WATER_RIV_GAUGES_CACHE_MAX_AGE_SEC
    ) or bool(missing_networks)
    submission = _kickoff_water_index_refresh() if stale else None
    refreshing = bool(
        submission and submission.status in {"queued", "running"}
    )
    retry_after_seconds = None
    if submission:
        retry_after_seconds = submission.retry_after_seconds
        if refreshing and retry_after_seconds is None:
            retry_after_seconds = WATER_INDEX_RETRY_AFTER_SEC
        elif stale and retry_after_seconds is None:
            retry_after_seconds = 5.0
    if not payload:
        return {
            "status": "warming",
            "stations": [],
            "count": 0,
            "provider": "NOAA",
            "source": "NOAA water gauges",
            "networks": sorted(selected_networks),
            "cache": "empty",
            "cache_state": (
                "backoff"
                if submission and submission.status == "backoff"
                else "refreshing" if refreshing else "missing"
            ),
            "refreshing": refreshing,
            "retry_after_seconds": retry_after_seconds,
            "missing_networks": missing_networks,
            "message": "NOAA water gauge index is warming.",
        }

    network_key = ",".join(sorted(selected_networks))
    cache_key = (
        f"water-gauges:{updated}:{west:.3f},{south:.3f},{east:.3f},"
        f"{north:.3f}:{int(max_sites)}:{network_key}"
    )
    cached = _cache_get(cache_key)
    if cached:
        return {**cached, "cache": "hit"}

    all_stations = payload.get("stations") if isinstance(payload.get("stations"), list) else []
    stations = sorted(
        (
            station
            for station in all_stations
            if (station.get("network") or "river") in selected_networks
            and _station_in_bbox(station, west, south, east, north)
        ),
        key=lambda item: str(item.get("name") or item.get("site_id") or ""),
    )
    limited_stations = _balanced_station_limit(
        stations,
        selected_networks,
        limit,
    )
    cache_state = (
        "backoff"
        if submission and submission.status == "backoff"
        else "stale_refreshing" if refreshing else "stale" if stale else "fresh"
    )

    return _cache_set(
        cache_key,
        {
            "status": "success",
            "stations": limited_stations,
            "count": len(limited_stations),
            "total_available": len(stations),
            "provider": "NOAA",
            "source": payload.get("source") or "NOAA water gauges",
            "networks": sorted(selected_networks),
            "network_counts": payload.get("network_counts") or {},
            "cache_age_seconds": cache_age_seconds,
            "cache": "miss",
            "stale": stale,
            "cache_state": cache_state,
            "refreshing": refreshing,
            "retry_after_seconds": retry_after_seconds,
            "missing_networks": missing_networks,
            "message": (
                "Water station index is missing "
                f"{', '.join(missing_networks)} stations; rebuilding."
                if missing_networks
                else None
            ),
            "updated": updated,
        },
    )


def get_water_station_data(site_id: str) -> dict:
    site = str(site_id or "").strip()
    if site.upper().startswith("COOPS_"):
        source_name = "NOAA CO-OPS"
    elif site.upper().startswith("NDBC_"):
        source_name = "NOAA NDBC"
    else:
        source_name = ""
    if source_name:
        payload = _read_riv_gauges_index()
        station = None
        if payload:
            for item in payload.get("stations") or []:
                if str(item.get("site_id") or "").upper() == site.upper():
                    station = item
                    break
        if not station:
            raise HTTPException(status_code=404, detail=f"{source_name} station not found in cache.")
        if source_name == "NOAA CO-OPS":
            coops_id = str(station.get("coops_id") or "").strip()
            if coops_id:
                live_cache_key = f"coops-live:{coops_id}"
                live_cached = _detail_cache_get(live_cache_key)
                if live_cached is not None:
                    station = {**station, "readings": live_cached}
                else:
                    try:
                        live_readings = _fetch_station_detail(
                            "coops",
                            live_cache_key,
                            lambda: _fetch_coops_live_readings(
                                coops_id,
                                str(station.get("station_type") or ""),
                            ),
                        )
                        if live_readings:
                            station = {**station, "readings": live_readings}
                    except Exception:
                        pass
        return {
            "status": "success",
            "station": station,
            "provider": "NOAA",
            "source": source_name,
            "cache": "hit",
            "updated": payload.get("updated") or datetime.now(timezone.utc).isoformat(),
        }
    if not _is_nwps_identifier(site):
        raise HTTPException(status_code=422, detail="Invalid water station id.")
    return get_nwps_station_data(site)


def get_nwps_station_data(identifier: str) -> dict:
    gauge_id = str(identifier or "").strip().upper()
    if not _is_nwps_identifier(gauge_id):
        raise HTTPException(status_code=422, detail="Invalid NWPS gauge id.")

    cache_key = f"nwps-station:{gauge_id}"
    cached = _detail_cache_get(cache_key)
    if cached is not None:
        return {**cached, "cache": "hit"}

    try:
        result = _fetch_station_detail(
            "nwps",
            cache_key,
            lambda: {
                "status": "success",
                "station": _parse_nwps_gauge(
                    _fetch_json_url(NWPS_GAUGE_URL.format(identifier=gauge_id))
                ),
                "provider": "NOAA",
                "source": "NOAA NWPS",
                "updated": datetime.now(timezone.utc).isoformat(),
            },
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"NWPS station data unavailable: {exc}") from exc

    return {**result, "cache": "miss"}
