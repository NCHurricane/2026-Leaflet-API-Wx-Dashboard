"""Historical archive endpoint services."""

from datetime import datetime, timedelta, timezone
import json
import os
import shutil
import threading

from fastapi import HTTPException

from app_core.http import validate_archive_range
from app_core.paths import CACHE_ROOT
from app_core.progress import active_tasks
from config.geo_config import STATE_BOUNDS
from services.alerts_service import enrich_alert_features_geometry
from services.mrms_service import render_mrms_png
from services.surface_service import (
    SURFACE_PRODUCTS,
    build_surface_stations,
    fetch_surface_archive_at_time,
    fetch_surface_archive_frames,
)

_ARCHIVE_ROOT = os.path.join(CACHE_ROOT, "archive")
_ARCHIVE_SESSION_TTL_HOURS = 2
_ARCHIVE_MAX_SESSIONS = 20
_archive_sessions: dict = {}
_archive_lock = threading.Lock()

_ARCHIVE_JSON_DIR = os.path.join("cache", "archive", "json")
os.makedirs(_ARCHIVE_JSON_DIR, exist_ok=True)

_SURFACE_ARCHIVE_PRODUCT_MAP = {
    "station_plot": "Station Plot",
    "temperature": "Temperature",
    "feels_like": "Feels Like",
    "dew_point": "Dewpoint",
    "relative_humidity": "Relative Humidity",
    "wind_speed": "Wind Speed",
    "wind_gust": "Wind Gust",
    "altimeter": "Altimeter",
    "mslp": "MSLP",
    "visibility": "Visibility",
}


def _archive_session_key(product_type: str, params: dict) -> str:
    import hashlib

    payload = json.dumps({"t": product_type, **params}, sort_keys=True)
    return hashlib.md5(payload.encode()).hexdigest()[:16]


def _cleanup_archive_sessions() -> None:
    now = datetime.now(timezone.utc)
    with _archive_lock:
        expired = [
            k
            for k, v in _archive_sessions.items()
            if datetime.fromisoformat(v["expires_utc"]) < now
        ]
        for k in expired:
            _evict_session(k)
        if len(_archive_sessions) > _ARCHIVE_MAX_SESSIONS:
            oldest = sorted(
                _archive_sessions.items(),
                key=lambda x: x[1].get("created_utc", ""),
            )
            for k, _ in oldest[: len(_archive_sessions) - _ARCHIVE_MAX_SESSIONS]:
                _evict_session(k)


def _evict_session(session_id: str) -> None:
    """Remove session from memory and disk. Caller must hold _archive_lock."""
    _archive_sessions.pop(session_id, None)
    disk_path = os.path.join(_ARCHIVE_ROOT, session_id)
    if os.path.isdir(disk_path):
        try:
            shutil.rmtree(disk_path)
        except Exception:
            pass


def _new_archive_session(session_id: str, product_type: str) -> dict:
    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=_ARCHIVE_SESSION_TTL_HOURS)
    session = {
        "session_id": session_id,
        "product_type": product_type,
        "status": "processing",
        "created_utc": now.isoformat(),
        "expires_utc": expires.isoformat(),
        "frames": [],
        "frame_count": 0,
        "error": None,
    }
    os.makedirs(os.path.join(_ARCHIVE_ROOT, session_id), exist_ok=True)
    with _archive_lock:
        _archive_sessions[session_id] = session
    return session


def _parse_archive_dt(value: str) -> datetime:
    """Parse ISO 8601 or YYYY-MM-DDTHH:MM string to UTC datetime."""
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    raise ValueError(
        f"Cannot parse date '{value}'. Use ISO 8601, e.g. 2026-04-16T18:00."
    )


def _archive_cache_path(prefix: str, **params) -> str:
    """Return a deterministic file path for an archive query."""
    import hashlib

    key = json.dumps(params, sort_keys=True, default=str)
    digest = hashlib.sha256(key.encode()).hexdigest()[:16]
    return os.path.join(_ARCHIVE_JSON_DIR, f"{prefix}_{digest}.json")


def _read_archive_cache(path: str) -> dict | None:
    """Return cached JSON dict or None."""
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None


def _write_archive_cache(path: str, data: dict) -> None:
    """Persist JSON dict to disk."""
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, separators=(",", ":"))
    except Exception:
        pass


def get_archive_mrms(
    product: str = "PrecipRate",
    date_from: str = "",
    date_to: str = "",
    max_frames: int = 24,
    south: float = 21.0,
    west: float = -130.0,
    north: float = 52.0,
    east: float = -60.0,
    request_id: str = "",
) -> dict:
    from config.mrms_config import MRMS_PRODUCTS

    if product not in MRMS_PRODUCTS:
        raise HTTPException(
            status_code=400, detail=f"Unknown MRMS product '{product}'."
        )
    if not date_from or not date_to:
        raise HTTPException(
            status_code=400, detail="date_from and date_to are required."
        )
    if not 1 <= max_frames <= 48:
        raise HTTPException(status_code=400, detail="max_frames must be 1-48.")
    try:
        dt_from = _parse_archive_dt(date_from)
        dt_to = _parse_archive_dt(date_to)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if dt_to <= dt_from:
        raise HTTPException(status_code=400, detail="date_to must be after date_from.")
    if (dt_to - dt_from).total_seconds() > 72 * 3600:
        raise HTTPException(
            status_code=400, detail="Max MRMS archive span is 72 hours."
        )

    skey = _archive_session_key(
        "mrms",
        {
            "product": product,
            "from": dt_from.isoformat(),
            "to": dt_to.isoformat(),
            "mf": max_frames,
            "s": round(south, 2),
            "w": round(west, 2),
            "n": round(north, 2),
            "e": round(east, 2),
        },
    )
    with _archive_lock:
        existing = _archive_sessions.get(skey)
    if existing and existing["status"] in ("success", "processing"):
        return {
            "status": existing["status"],
            "session_id": skey,
            "request_id": skey,
            "frame_count": existing["frame_count"],
            "frames": existing["frames"] if existing["status"] == "success" else [],
        }

    _cleanup_archive_sessions()
    session = _new_archive_session(skey, "mrms")
    tid = request_id or skey
    active_tasks[tid] = {
        "percent": 0,
        "stage": "queued",
        "message": "MRMS archive request queued",
    }

    def _worker():
        try:
            from config.mrms_config import MRMS_BUCKET
            from lib.s3_utils import get_s3_client
            from mrms.mrms_nodd_utils import list_mrms_files

            active_tasks[tid] = {
                "percent": 5,
                "stage": "listing",
                "message": "Listing MRMS files...",
            }
            all_files = list_mrms_files(product, dt_from, dt_to)
            if not all_files:
                with _archive_lock:
                    session["status"] = "error"
                    session["error"] = (
                        "No MRMS files found for the requested time range."
                    )
                active_tasks[tid] = {
                    "percent": 100,
                    "stage": "error",
                    "message": session["error"],
                }
                return
            if len(all_files) > max_frames:
                step = len(all_files) / max_frames
                all_files = [all_files[int(i * step)] for i in range(max_frames)]
            total = len(all_files)
            disk_dir = os.path.join(_ARCHIVE_ROOT, skey)
            frames = []
            s3 = get_s3_client()
            for idx, (s3_key, file_dt) in enumerate(all_files):
                pct = 10 + int(85 * idx / total)
                active_tasks[tid] = {
                    "percent": pct,
                    "stage": "rendering",
                    "message": f"Frame {idx + 1}/{total}: {file_dt.strftime('%H:%MZ')}",
                }
                local_gz = os.path.join(disk_dir, f"frame_{idx:04d}.grib2.gz")
                try:
                    s3.download_file(MRMS_BUCKET, s3_key, local_gz)
                except Exception as dl_err:
                    print(f"[archive/mrms] S3 skip {s3_key}: {dl_err}")
                    continue
                png_path = local_gz.replace(".grib2.gz", ".png")
                try:
                    png_path, bounds, _render_meta = render_mrms_png(
                        local_gz, product, [west, east, south, north], png_path
                    )
                except Exception as render_err:
                    print(f"[archive/mrms] Render failed frame {idx}: {render_err}")
                    continue
                finally:
                    try:
                        os.remove(local_gz)
                    except Exception:
                        pass
                rel = os.path.relpath(png_path, CACHE_ROOT).replace("\\", "/")
                frames.append(
                    {
                        "timestamp": file_dt.isoformat(),
                        "image_url": f"/cache/{rel}",
                        "bounds": bounds,
                    }
                )
            with _archive_lock:
                session["status"] = "success" if frames else "error"
                session["frames"] = frames
                session["frame_count"] = len(frames)
                if not frames:
                    session["error"] = "All frames failed to render."
            active_tasks[tid] = {
                "percent": 100,
                "stage": "success" if frames else "error",
                "message": f"Rendered {len(frames)} frames",
            }
        except Exception as exc:
            with _archive_lock:
                session["status"] = "error"
                session["error"] = str(exc)
            active_tasks[tid] = {"percent": 100, "stage": "error", "message": str(exc)}

    threading.Thread(target=_worker, daemon=True).start()
    return {
        "status": "processing",
        "session_id": skey,
        "request_id": tid,
        "frame_count": 0,
        "frames": [],
    }


def get_archive_result(session_id: str) -> dict:
    """Return the current state of an archive session."""
    with _archive_lock:
        session = _archive_sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found or expired.")
    return {
        "status": session["status"],
        "session_id": session_id,
        "product_type": session["product_type"],
        "frame_count": session["frame_count"],
        "frames": session["frames"],
        "error": session.get("error"),
    }


def get_archive_alerts(
    date_from: str = "",
    date_to: str = "",
    state: str = "",
) -> dict:
    if not date_from or not date_to:
        raise HTTPException(
            status_code=400, detail="date_from and date_to are required."
        )
    try:
        dt_from = _parse_archive_dt(date_from)
        dt_to = _parse_archive_dt(date_to)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if (dt_to - dt_from).total_seconds() > 30 * 24 * 3600:
        raise HTTPException(
            status_code=400, detail="Max alerts archive span is 30 days."
        )
    state_upper = state.upper() if state else ""
    cache_file = _archive_cache_path(
        "alerts",
        date_from=dt_from.isoformat(),
        date_to=dt_to.isoformat(),
        state=state_upper,
    )
    cached = _read_archive_cache(cache_file)
    if cached is not None:
        enrich_alert_features_geometry(cached.get("features", []))
        return cached
    try:
        features = _fetch_iem_alerts_range(dt_from, dt_to, state_upper or None)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"IEM fetch error: {exc}")
    enrich_alert_features_geometry(features)
    result = {
        "type": "FeatureCollection",
        "features": features,
        "count": len(features),
        "date_from": dt_from.isoformat(),
        "date_to": dt_to.isoformat(),
        "_source": "iem_watchwarn",
    }
    _write_archive_cache(cache_file, result)
    return result


def _fetch_iem_alerts_range(
    dt_from: datetime, dt_to: datetime, state: str | None
) -> list:
    """Call IEM WatchWarn with explicit start/end and return GeoJSON features."""
    import io
    import tempfile
    import zipfile
    import requests as _requests
    from alerts.alerts_iem_utils import IEM_WATCHWARN_URL, _event_name_from_attrs

    utc_from = dt_from.astimezone(timezone.utc)
    utc_to = dt_to.astimezone(timezone.utc)
    lookback = timedelta(hours=72)
    query_from = utc_from - lookback

    headers = {"User-Agent": "(NCHurricane.com Weather Suite, contact@nchurricane.com)"}

    def _build_url(with_state: bool) -> str:
        url = (
            f"{IEM_WATCHWARN_URL}"
            f"?year1={query_from.year}&month1={query_from.month}&day1={query_from.day}"
            f"&hour1={query_from.hour}&minute1={query_from.minute}"
            f"&year2={utc_to.year}&month2={utc_to.month}&day2={utc_to.day}"
            f"&hour2={utc_to.hour}&minute2={utc_to.minute}"
            f"&simple=yes&fmt=shp"
        )
        if with_state and state:
            url += f"&states={state}"
        return url

    resp = None
    for use_state in [True, False] if state else [False]:
        try:
            resp = _requests.get(
                _build_url(use_state), headers=headers, timeout=(5, 30)
            )
            resp.raise_for_status()
            break
        except Exception:
            resp = None
    if resp is None:
        return []

    tmpdir = tempfile.mkdtemp(prefix="iem_arc_")
    features = []
    try:
        with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
            z.extractall(tmpdir)
        shp_files = [f for f in os.listdir(tmpdir) if f.endswith(".shp")]
        if not shp_files:
            return []
        import cartopy.io.shapereader as shpreader

        reader = shpreader.Reader(os.path.join(tmpdir, shp_files[0]))
        for rec in reader.records():
            geom = rec.geometry
            if geom is None:
                continue
            try:
                geom_json = geom.__geo_interface__
            except Exception:
                continue
            attrs = rec.attributes
            event = _event_name_from_attrs(attrs) or str(attrs.get("PHENOM", ""))

            def _iem_to_iso(raw: str) -> str:
                text = str(raw or "").strip()
                if len(text) >= 12:
                    try:
                        dt = datetime(
                            int(text[0:4]),
                            int(text[4:6]),
                            int(text[6:8]),
                            int(text[8:10]),
                            int(text[10:12]),
                            tzinfo=timezone.utc,
                        )
                        return dt.isoformat()
                    except Exception:
                        pass
                return text

            features.append(
                {
                    "type": "Feature",
                    "geometry": geom_json,
                    "properties": {
                        "event": event,
                        "onset": _iem_to_iso(str(attrs.get("ISSUED", ""))),
                        "expires": _iem_to_iso(str(attrs.get("EXPIRED", ""))),
                        "areaDesc": str(attrs.get("AREA_DESC", "")),
                        "_source": "iem_archive",
                    },
                }
            )
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return features


def get_archive_surface(
    region: str = "NC",
    product: str = "temperature",
    date_from: str = "",
    date_to: str = "",
    max_frames: int = 24,
    source: str = "iem",
    network: str = "ASOS",
) -> dict:
    if not date_from or not date_to:
        raise HTTPException(
            status_code=400, detail="date_from and date_to are required."
        )
    if not 1 <= int(max_frames) <= 120:
        raise HTTPException(status_code=400, detail="max_frames must be 1-120.")

    try:
        dt_from = _parse_archive_dt(date_from)
        dt_to = _parse_archive_dt(date_to)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if dt_to <= dt_from:
        raise HTTPException(status_code=400, detail="date_to must be after date_from.")
    validate_archive_range("surface", dt_from, dt_to)

    product_key = str(product or "").strip().lower()
    if product_key not in SURFACE_PRODUCTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown product '{product}'. Valid: {list(SURFACE_PRODUCTS.keys())}",
        )

    region_upper = str(region or "NC").strip().upper()
    if region_upper not in STATE_BOUNDS:
        region_upper = "NC"

    source_key = str(source or "iem").strip().lower()
    source_key = "iem"

    network_key = str(network or "ASOS").strip().upper()
    if network_key != "ASOS":
        raise HTTPException(
            status_code=400,
            detail="Only ASOS network is supported for surface archive.",
        )

    total = int(max_frames)
    frame_times = []
    cursor = dt_from.replace(minute=0, second=0, microsecond=0)
    if cursor < dt_from:
        cursor += timedelta(hours=1)
    while cursor <= dt_to and len(frame_times) < total:
        frame_times.append(cursor)
        cursor += timedelta(hours=1)
    if not frame_times:
        frame_times = [dt_from]

    cache_file = _archive_cache_path(
        "surface",
        region=region_upper,
        product=product_key,
        date_from=dt_from.isoformat(),
        date_to=dt_to.isoformat(),
        max_frames=total,
    )
    cached = _read_archive_cache(cache_file)
    if cached is not None:
        return cached

    try:
        frame_dfs = fetch_surface_archive_frames(region_upper, frame_times, source_key)
    except Exception:
        frame_dfs = [None] * len(frame_times)

    frames = []
    for idx, ts in enumerate(frame_times):
        try:
            df = frame_dfs[idx] if idx < len(frame_dfs) else None
            if df is None:
                df = fetch_surface_archive_at_time(region_upper, ts, source_key)
            stations = build_surface_stations(df, product_key)
        except Exception:
            stations = []

        frames.append(
            {
                "timestamp": ts.isoformat(),
                "stations": stations,
                "product": product_key,
                "unit": SURFACE_PRODUCTS[product_key]["unit"],
            }
        )

    result = {
        "status": "success",
        "type": "surface_archive",
        "region": region_upper,
        "product": product_key,
        "product_label": _SURFACE_ARCHIVE_PRODUCT_MAP.get(product_key, product_key),
        "source": "awc",
        "network": "ASOS",
        "date_from": dt_from.isoformat(),
        "date_to": dt_to.isoformat(),
        "frame_count": len(frames),
        "frames": frames,
    }
    _write_archive_cache(cache_file, result)
    return result


def get_archive_spc(day: int = 1, hazard: str = "cat", date: str = "") -> dict:
    if not date:
        raise HTTPException(status_code=400, detail="date is required (YYYY-MM-DD).")
    try:
        target_dt = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD.")
    if not 1 <= day <= 3:
        raise HTTPException(status_code=400, detail="day must be 1-3 for SPC archive.")

    hazard = (hazard or "cat").strip().lower()
    day12_hazards = {"cat", "torn", "wind", "hail", "prob", "sig"}
    day3_hazards = {"cat", "prob", "sig"}
    if day in (1, 2):
        if hazard not in day12_hazards:
            hazard = "cat"
    elif hazard not in day3_hazards:
        hazard = "cat"

    cache_file = _archive_cache_path("spc", date=date, day=day, hazard=hazard)
    cached = _read_archive_cache(cache_file)
    if cached is not None:
        return cached

    year = target_dt.year
    date_str = target_dt.strftime("%Y%m%d")
    spc_base = "https://www.spc.noaa.gov"
    issue_times = ["1200", "1300", "1630", "2000", "0100"]
    geojson = None
    tried_urls: list = []
    import urllib.request as _ur

    for hhmm in issue_times:
        url_candidates = [
            f"{spc_base}/products/outlook/archive/{year}/day{day}otlk_{date_str}_{hhmm}_{hazard}.lyr.geojson",
            f"{spc_base}/products/outlook/archive/{year}/day{day}otlk_{date_str}_{hhmm}.lyr.geojson",
        ]
        for url in url_candidates:
            tried_urls.append(url)
            try:
                with _ur.urlopen(url, timeout=15) as response:
                    geojson = json.loads(
                        response.read().decode("utf-8", errors="replace")
                    )
                break
            except Exception:
                continue
        if geojson is not None:
            break

    if geojson is None:
        result = {
            "type": "FeatureCollection",
            "features": [],
            "count": 0,
            "date": date,
            "day": day,
            "hazard": hazard,
            "_note": f"No SPC archive found for {date} day{day}.",
        }
        _write_archive_cache(cache_file, result)
        return result

    features = geojson.get("features", []) if isinstance(geojson, dict) else []
    result = {
        "type": "FeatureCollection",
        "features": features,
        "count": len(features),
        "date": date,
        "day": day,
        "hazard": hazard,
        "_source": "spc_archive",
    }
    _write_archive_cache(cache_file, result)
    return result
