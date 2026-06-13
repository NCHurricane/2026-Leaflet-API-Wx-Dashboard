"""USDM drought data cache helpers."""

from datetime import date as _date
from datetime import timedelta
import json
from pathlib import Path
import re
import urllib.parse as _up
import urllib.request as _ur

from fastapi import HTTPException
from fastapi.responses import Response

from app_core.paths import CACHE_ROOT

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


def get_drought_dates() -> dict:
    """Return the last 15 USDM valid dates (Tuesdays), most recent first."""
    latest = _latest_usdm_date()
    dates = [(latest - timedelta(weeks=i)).isoformat() for i in range(15)]
    return {"dates": dates, "latest": dates[0]}


async def get_drought_geojson(date: str = "latest") -> Response:
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
        return Response(content=cache_file.read_bytes(), media_type="application/json")

    url = f"https://droughtmonitor.unl.edu/data/json/usdm_{date_compact}.json"
    try:
        req = _ur.Request(url, headers={"User-Agent": "NCHurricane-Dashboard/1.0"})
        with _ur.urlopen(req, timeout=30) as resp:
            if resp.status == 404:
                raise HTTPException(status_code=404, detail=f"No USDM data for {date}")
            raw = resp.read()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"USDM unreachable: {exc}") from exc

    cache_file.write_bytes(raw)
    return Response(content=raw, media_type="application/json")


async def get_drought_state_stats(date: str = "latest", state: str = "NC") -> dict:
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
                return json.load(fh)
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
        with _ur.urlopen(area_req, timeout=30) as resp:
            area_rows = json.loads(resp.read().decode("utf-8"))

        dsci_req = _ur.Request(dsci_url, headers=headers)
        with _ur.urlopen(dsci_req, timeout=30) as resp:
            dsci_rows = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"USDM state stats unreachable: {exc}"
        ) from exc

    area = area_rows[0] if isinstance(area_rows, list) and area_rows else {}
    dsci = dsci_rows[0] if isinstance(dsci_rows, list) and dsci_rows else {}

    d0 = float(area.get("d0") or 0.0)
    d1 = float(area.get("d1") or 0.0)
    d2 = float(area.get("d2") or 0.0)
    d3 = float(area.get("d3") or 0.0)
    d4 = float(area.get("d4") or 0.0)

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
        "dsci": float(dsci.get("dsci") or 0.0),
    }

    with cache_file.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=True)

    return payload


def _latest_usdm_date() -> _date:
    today = _date.today()
    days_since_tuesday = (today.weekday() - 1) % 7
    candidate = today - timedelta(days=days_since_tuesday)
    if today.weekday() in (1, 2):
        candidate -= timedelta(weeks=1)
    return candidate
