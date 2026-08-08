"""USDM drought data cache helpers."""

from datetime import date as _date
from datetime import timedelta
import json
import math
from pathlib import Path
import re
import urllib.parse as _up
import urllib.request as _ur

from app_core.upstream_ledger import urlopen

from fastapi import HTTPException
from fastapi.responses import Response

from app_core.paths import CACHE_ROOT
from app_core.atomic_io import atomic_write_json, atomic_write_text
from config.refresh_schedules import latest_usdm_valid_date

_STATE_TO_FIPS = {
    "AL": "01",
    "AK": "02",
    "AZ": "04",
    "AR": "05",
    "CA": "06",
    "CO": "08",
    "CT": "09",
    "DE": "10",
    "DC": "11",
    "FL": "12",
    "GA": "13",
    "HI": "15",
    "ID": "16",
    "IL": "17",
    "IN": "18",
    "IA": "19",
    "KS": "20",
    "KY": "21",
    "LA": "22",
    "ME": "23",
    "MD": "24",
    "MA": "25",
    "MI": "26",
    "MN": "27",
    "MS": "28",
    "MO": "29",
    "MT": "30",
    "NE": "31",
    "NV": "32",
    "NH": "33",
    "NJ": "34",
    "NM": "35",
    "NY": "36",
    "NC": "37",
    "ND": "38",
    "OH": "39",
    "OK": "40",
    "OR": "41",
    "PA": "42",
    "RI": "44",
    "SC": "45",
    "SD": "46",
    "TN": "47",
    "TX": "48",
    "UT": "49",
    "VT": "50",
    "VA": "51",
    "WA": "53",
    "WV": "54",
    "WI": "55",
    "WY": "56",
    "PR": "72",
}

_DROUGHT_LEVEL_KEYS = ("D0-D4", "D1-D4", "D2-D4", "D3-D4", "D4")
_INDIVIDUAL_LEVEL_KEYS = ("D0", "D1", "D2", "D3", "D4")


def _validate_geojson(raw: bytes) -> None:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (AttributeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid USDM GeoJSON") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("type") != "FeatureCollection"
        or not isinstance(payload.get("features"), list)
    ):
        raise ValueError("invalid USDM GeoJSON")


def _provider_row(payload, label: str) -> dict:
    if not isinstance(payload, list):
        raise ValueError(f"invalid {label} payload")
    if not payload:
        return {}
    if not isinstance(payload[0], dict):
        raise ValueError(f"invalid {label} row")
    return payload[0]


def _provider_number(row: dict, key: str) -> float:
    value = row.get(key)
    if value in (None, ""):
        return 0.0
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid {key} value") from exc
    if not math.isfinite(number):
        raise ValueError(f"invalid {key} value")
    return number


def _valid_state_stats_cache(payload, state_code: str, valid_date: str) -> bool:
    if (
        not isinstance(payload, dict)
        or payload.get("state") != state_code
        or payload.get("date") != valid_date
        or not isinstance(payload.get("cumulative"), dict)
        or not isinstance(payload.get("individual"), dict)
    ):
        return False
    values = [
        *(payload["cumulative"].get(key) for key in _DROUGHT_LEVEL_KEYS),
        *(payload["individual"].get(key) for key in _INDIVIDUAL_LEVEL_KEYS),
        payload.get("dsci"),
    ]
    try:
        return all(math.isfinite(float(value)) for value in values)
    except (TypeError, ValueError):
        return False


def get_drought_dates() -> dict:
    """Return the last 15 USDM valid dates (Tuesdays), most recent first."""
    latest = _latest_usdm_date()
    dates = [(latest - timedelta(weeks=i)).isoformat() for i in range(15)]
    return {"dates": dates, "latest": dates[0]}


def get_drought_geojson(date: str = "latest") -> Response:
    """Proxy USDM GeoJSON for the given valid date."""
    if date == "latest":
        date = _latest_usdm_date().isoformat()

    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        raise HTTPException(
            status_code=400, detail="Invalid date format; expected YYYY-MM-DD"
        )

    date_compact = date.replace("-", "")
    cache_dir = Path(CACHE_ROOT) / "drought"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"usdm_{date_compact}.json"

    if cache_file.exists():
        try:
            cached = cache_file.read_bytes()
            _validate_geojson(cached)
            return Response(content=cached, media_type="application/json")
        except (OSError, ValueError):
            pass

    url = f"https://droughtmonitor.unl.edu/data/json/usdm_{date_compact}.json"
    try:
        req = _ur.Request(url, headers={"User-Agent": "NCHurricane-Dashboard/1.0"})
        with urlopen(req, timeout=30) as resp:
            if resp.status == 404:
                raise HTTPException(status_code=404, detail=f"No USDM data for {date}")
            raw = resp.read()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"USDM unreachable: {exc}") from exc

    try:
        _validate_geojson(raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=503, detail=f"USDM returned invalid GeoJSON: {exc}"
        ) from exc

    atomic_write_text(cache_file, raw.decode("utf-8"))
    return Response(content=raw, media_type="application/json")


def get_drought_state_stats(date: str = "latest", state: str = "NC") -> dict:
    """Return cached USDM state stats for a specific valid date."""
    state_code = str(state or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{2}", state_code):
        raise HTTPException(
            status_code=400, detail="Invalid state; expected 2-letter code"
        )

    state_fips = _STATE_TO_FIPS.get(state_code)
    if not state_fips:
        raise HTTPException(
            status_code=404, detail=f"Unsupported state code '{state_code}'"
        )

    if date == "latest":
        date = _latest_usdm_date().isoformat()

    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        raise HTTPException(
            status_code=400, detail="Invalid date format; expected YYYY-MM-DD"
        )

    date_compact = date.replace("-", "")
    cache_dir = Path(CACHE_ROOT) / "drought" / "stats"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"usdm_state_stats_{state_code}_{date_compact}.json"

    if cache_file.exists():
        try:
            with cache_file.open("r", encoding="utf-8") as fh:
                cached = json.load(fh)
            if _valid_state_stats_cache(cached, state_code, date):
                return cached
        except Exception:
            pass

    params = _up.urlencode(
        {
            "aoi": state_fips,
            "startdate": f"{int(date[5:7])}/{int(date[8:10])}/{date[0:4]}",
            "enddate": f"{int(date[5:7])}/{int(date[8:10])}/{date[0:4]}",
            "statisticsType": 1,
        }
    )

    area_url = (
        "https://usdmdataservices.unl.edu/api/StateStatistics/"
        f"GetDroughtSeverityStatisticsByAreaPercent?{params}"
    )
    dsci_url = f"https://usdmdataservices.unl.edu/api/StateStatistics/GetDSCI?{params}"

    try:
        headers = {
            "User-Agent": "NCHurricane-Dashboard/1.0",
            "Accept": "application/json",
        }
        area_req = _ur.Request(area_url, headers=headers)
        with urlopen(area_req, timeout=30) as resp:
            area_raw = resp.read()

        dsci_req = _ur.Request(dsci_url, headers=headers)
        with urlopen(dsci_req, timeout=30) as resp:
            dsci_raw = resp.read()
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"USDM state stats unreachable: {exc}"
        ) from exc

    try:
        area = _provider_row(
            json.loads(area_raw.decode("utf-8")),
            "USDM area statistics",
        )
        dsci = _provider_row(
            json.loads(dsci_raw.decode("utf-8")),
            "USDM DSCI",
        )
        d0 = _provider_number(area, "d0")
        d1 = _provider_number(area, "d1")
        d2 = _provider_number(area, "d2")
        d3 = _provider_number(area, "d3")
        d4 = _provider_number(area, "d4")
        dsci_value = _provider_number(dsci, "dsci")
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(
            status_code=503,
            detail=f"USDM state stats returned invalid data: {exc}",
        ) from exc

    payload = {
        "state": state_code,
        "date": date,
        "provider": "USDM/NDMC",
        "cumulative": {
            "D0-D4": max(0.0, d0),
            "D1-D4": max(0.0, d1),
            "D2-D4": max(0.0, d2),
            "D3-D4": max(0.0, d3),
            "D4": max(0.0, d4),
        },
        "individual": {
            "D0": max(0.0, d0 - d1),
            "D1": max(0.0, d1 - d2),
            "D2": max(0.0, d2 - d3),
            "D3": max(0.0, d3 - d4),
            "D4": max(0.0, d4),
        },
        "dsci": dsci_value,
    }

    atomic_write_json(cache_file, payload)

    return payload


def _latest_usdm_date() -> _date:
    return latest_usdm_valid_date()
