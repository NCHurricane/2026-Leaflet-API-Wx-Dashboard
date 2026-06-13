import os as _os

import certifi as _certifi

# Python on macOS ships with no default CA bundle (ssl cafile=None), so plain
# urllib/pandas HTTPS fetches fail certificate verification. Point OpenSSL at
# certifi's bundle unless the environment already provides one. Must run
# before any module builds an SSL context.
_os.environ.setdefault("SSL_CERT_FILE", _certifi.where())
_os.environ.setdefault("REQUESTS_CA_BUNDLE", _certifi.where())

from surface import surface_utils
from config.rtma_config import RTMA_STREAM_MAX_HOURS, clamp_stream_hours
from datetime import datetime, timezone, timedelta
import json
from typing import Any, Optional
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI, HTTPException
import uvicorn
import time as _time
import os
import shutil
import threading
from pathlib import Path
from config.geo_config import STATE_BOUNDS
from app_core.http import (
    error_payload,
    parse_utc_datetime,
    validate_archive_range,
)
from app_core.background_render import spawn_live_render_thread
from app_core.paths import BASE_DIR, CACHE_ROOT as _CACHE_ROOT, ensure_runtime_dirs
from app_core.progress import active_tasks
from app_core.runtime import initialize_runtime, shutdown_runtime
from app_core.static_assets import CacheStaticFiles
from routes.alerts import router as alerts_router
from routes.core import router as core_router
from routes.drought import router as drought_router
from routes.health import router as health_router
from routes.overlays import create_overlays_router
from routes.pages import router as pages_router
from routes.satellite_v2 import router as satellite_v2_router
from routes.spc import router as spc_router
from services.alerts_service import enrich_alert_features_geometry

# --- IMPORT YOUR UTILITIES ---

# Defer directory creation and module initialization to startup handler
app = FastAPI(title="NCHurricane Weather API")
app.include_router(health_router)
app.include_router(pages_router)
app.include_router(core_router)
app.include_router(alerts_router)
app.include_router(spc_router)
app.include_router(drought_router)
app.include_router(satellite_v2_router)


@app.on_event("startup")
def _run_startup_sequence():
    """Execute the complete startup sequence with initialization."""
    initialize_runtime()


@app.on_event("shutdown")
def _stop_background_workers():
    """Shut down background schedulers and live render pools on app exit."""
    shutdown_runtime()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Sound files
app.mount("/sounds", StaticFiles(directory="sounds"), name="sounds")

# Cache directory — worker-written GeoJSON artifacts (gitignored)
ensure_runtime_dirs()
app.mount("/cache", CacheStaticFiles(directory=_CACHE_ROOT), name="cache")

app.mount("/css", StaticFiles(directory=os.path.join(BASE_DIR, "css")), name="css")
app.mount("/js", StaticFiles(directory=os.path.join(BASE_DIR, "js")), name="js")
app.mount("/data", StaticFiles(directory=os.path.join(BASE_DIR, "data")), name="data")
app.mount("/img", StaticFiles(directory=os.path.join(BASE_DIR, "img")), name="img")
app.mount(
    "/fonts", StaticFiles(directory=os.path.join(BASE_DIR, "fonts")), name="fonts"
)

def parse_styles(style_str: Optional[str]):
    parsed_styles = {}
    if style_str:
        try:
            # Handle case where style_str might already be a dict
            if isinstance(style_str, dict):
                raw_styles = style_str
            else:
                raw_styles = json.loads(style_str)
            for k, v in raw_styles.items():
                try:
                    float_v = float(v)
                    parsed_styles[k] = int(float_v) if float_v.is_integer() else float_v
                except (ValueError, TypeError):
                    parsed_styles[k] = v
        except Exception as e:
            print(f"Warning: Could not parse styles: {e}")
            pass

    if "logo_user_size" in parsed_styles:
        try:
            logo_user_size = float(parsed_styles["logo_user_size"])
            if logo_user_size > 2:
                logo_user_size = logo_user_size / 100.0
            if logo_user_size <= 0:
                logo_user_size = 0.08
            parsed_styles["logo_user_size"] = logo_user_size
        except (TypeError, ValueError):
            parsed_styles["logo_user_size"] = 0.08

    return parsed_styles


def _parse_and_validate_styles(style_config: Optional[str]) -> dict:
    parsed_styles = parse_styles(style_config)
    if not isinstance(parsed_styles, dict):
        return {}
    return parsed_styles


def _resolve_extent(
    n: Optional[float], s: Optional[float], e: Optional[float], w: Optional[float]
) -> Optional[tuple]:
    if all(value is not None for value in [n, s, e, w]):
        return (s, n, w, e)
    return None


def infer_data_mode(date_from: Optional[str], date_to: Optional[str]) -> str:
    has_from = bool((date_from or "").strip())
    has_to = bool((date_to or "").strip())
    if has_from and has_to:
        return "archive"
    if not has_from and not has_to:
        return "recent"
    raise HTTPException(
        status_code=400,
        detail=error_payload(
            "Both date_from and date_to must be provided together.",
            code="missing_paired_date",
        ),
    )

def format_utc_for_legacy(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M")


RADAR_SITE_ALIASES = {
    "KILM": "KLTX",
    "KRAH": "KRAX",
    "KRNK": "KFCX",
    "KABQ": "KABX",
    "KALY": "KENX",
    "KBOI": "KCBX",
    "KBOU": "KFTG",
    "KBTV": "KCXX",
    "KBYZ": "KBLX",
    "KCAR": "KCBW",
    "KCHS": "KCLX",
    "KCTP": "KCCX",
    "KEKA": "KBHX",
    "KFGF": "KMVX",
    "KFGZ": "KFSX",
    "KFWD": "KFWS",
    "KGID": "KUEX",
    "KGJT": "KGJX",
    "KHUN": "KHTX",
    "KJAN": "KDGX",
    "KKEY": "KBYX",
    "KLBF": "KLNX",
    "KLKN": "KLRX",
    "KLMK": "KLVX",
    "KLOX": "KVTX",
    "KLUB": "KLBB",
    "KMEG": "KNQA",
    "KMFL": "KAMX",
    "KMFR": "KMAX",
    "KMSO": "KMSX",
    "KMTR": "KMUX",
    "KOUN": "KTLX",
    "KPHI": "KDIX",
    "KPIH": "KSFX",
    "KPQR": "KRTX",
    "KPSR": "KIWA",
    "KPUB": "KPUX",
    "KREV": "KRGX",
    "KSEW": "KATX",
    "KSGX": "KNKX",
    "KSLC": "KMTX",
    "KSTO": "KDAX",
    "KTAE": "KTLH",
    "KTOP": "KTWX",
    "KTSA": "KINX",
    "KTWC": "KEMX",
    "KUNR": "KUDX",
    "KVEF": "KESX",
}


def normalize_radar_site_id(site: str) -> str:
    site_id = str(site or "").strip().upper()
    return RADAR_SITE_ALIASES.get(site_id, site_id)


def build_mrms_recent_windows(
    end_time_utc,
    lookback_hours: float,
    enable_clock_skew_fallback: bool = True,
    max_days_back: int = 365,
):
    """Build ordered MRMS recent windows with optional clock-skew fallback."""
    base_hours = max(0.25, float(lookback_hours or 0.25))
    max_back = max(0, int(max_days_back or 0))

    offsets = [0]
    if enable_clock_skew_fallback and max_back > 0:
        # Sparse offsets keep request count low while handling common skew ranges.
        for day_offset in (1, 2, 3, 7, 14, 30, 60, 120, 240, 365):
            if day_offset <= max_back:
                offsets.append(day_offset)

    windows = []
    seen_offsets = set()
    for day_offset in offsets:
        if day_offset in seen_offsets:
            continue
        seen_offsets.add(day_offset)
        candidate_end = end_time_utc - timedelta(days=day_offset)
        candidate_start = candidate_end - timedelta(hours=base_hours)
        windows.append(
            {
                "offset_days": day_offset,
                "start": candidate_start,
                "end": candidate_end,
            }
        )
    return windows


# ── MRMS app state (Phase 3) ─────────────────────────────────────────────────
# Tracks which MRMS product the worker is actively refreshing.
# Mutated by /api/mrms/set-product; read by the mrms_worker.
_active_mrms_product: str = "Refl_BaseQC"

# ── Surface color helpers (Phase 2) ─────────────────────────────────────────
try:
    from config.surface_config import TEMPERATURE_GRADIENT_ANCHORS as _TEMP_ANCHORS
except Exception:
    _TEMP_ANCHORS = [
        (-60, "#00352C"),
        (-20, "#c4c4d4"),
        (0, "#570057"),
        (32, "#0000ff"),
        (50, "#c4c403"),
        (80, "#c20303"),
        (130, "#000000"),
    ]

_WIND_ANCHORS = [
    (0, "#b0d4f0"),
    (10, "#70b0e0"),
    (20, "#3090d0"),
    (30, "#f5dd72"),
    (45, "#ff9d2e"),
    (60, "#ff4f4f"),
]
_RH_ANCHORS = [
    (0, "#c8a000"),
    (20, "#f5dd72"),
    (40, "#69bb6d"),
    (60, "#0099cc"),
    (80, "#0055aa"),
    (100, "#003377"),
]
_PRESSURE_ANCHORS = [
    (990, "#5b1a8f"),
    (1000, "#2a6db3"),
    (1010, "#2ca58d"),
    (1020, "#f5dd72"),
    (1030, "#ff9d2e"),
    (1040, "#bf2c2c"),
]
_VISIBILITY_ANCHORS = [
    (0, "#7f1d1d"),
    (1, "#b45309"),
    (3, "#d97706"),
    (5, "#65a30d"),
    (7, "#16a34a"),
    (10, "#0ea5e9"),
]

_SURFACE_PRODUCTS = {
    "station_plot": {"col": "air_temperature", "unit": "\u00b0F", "anchors": "temp"},
    "temperature": {"col": "air_temperature", "unit": "\u00b0F", "anchors": "temp"},
    "feels_like": {"col": "feels_like", "unit": "\u00b0F", "anchors": "temp"},
    "dew_point": {"col": "dew_point_temperature", "unit": "\u00b0F", "anchors": "temp"},
    "relative_humidity": {"col": "relative_humidity", "unit": "%", "anchors": "rh"},
    "wind_speed": {"col": "wind_speed", "unit": "kt", "anchors": "wind"},
    "wind_gust": {"col": "peak_wind", "unit": "kt", "anchors": "wind"},
    "altimeter": {"col": "altimeter", "unit": "inHg", "anchors": "pressure"},
    "mslp": {"col": "mean_sea_level_pressure", "unit": "hPa", "anchors": "pressure"},
    "visibility": {"col": "visibility", "unit": "mi", "anchors": "visibility"},
}

_SURFACE_CACHE_TTL_SECONDS = 300
_surface_refresh_lock = threading.Lock()
_surface_refresh_inflight = set()


def _interpolate_color(anchors: list, value: float) -> str:
    """Map a numeric value to a hex color via piecewise linear interpolation."""
    if not anchors:
        return "#aaaaaa"
    if value <= anchors[0][0]:
        return anchors[0][1]
    if value >= anchors[-1][0]:
        return anchors[-1][1]
    for i in range(len(anchors) - 1):
        v0, c0 = anchors[i]
        v1, c1 = anchors[i + 1]
        if v0 <= value <= v1:
            frac = (value - v0) / (v1 - v0)
            r0, g0, b0 = int(c0[1:3], 16), int(c0[3:5], 16), int(c0[5:7], 16)
            r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
            r = int(r0 + (r1 - r0) * frac)
            g = int(g0 + (g1 - g0) * frac)
            b = int(b0 + (b1 - b0) * frac)
            return f"#{r:02x}{g:02x}{b:02x}"
    return "#aaaaaa"


def _build_surface_stations(df, product: str) -> list:
    """Serialize a surface DataFrame to a JSON-safe station list with per-station colors."""
    import math

    meta = _SURFACE_PRODUCTS.get(product)
    if meta is None or df is None or df.empty:
        return []

    col = meta["col"]
    anchors_key = meta["anchors"]
    if anchors_key == "temp":
        anchors = _TEMP_ANCHORS
    elif anchors_key == "wind":
        anchors = _WIND_ANCHORS
    elif anchors_key == "pressure":
        anchors = _PRESSURE_ANCHORS
    elif anchors_key == "visibility":
        anchors = _VISIBILITY_ANCHORS
    else:
        anchors = _RH_ANCHORS

    if col not in df.columns:
        return []

    stations = []
    for _, row in df.iterrows():
        raw_val = row.get(col)
        if raw_val is None or (isinstance(raw_val, float) and math.isnan(raw_val)):
            continue
        val = float(raw_val)
        color = _interpolate_color(anchors, val)
        station = {
            "id": str(row.get("station_id", "")),
            "name": str(row.get("name", "")),
            "network": str(
                row.get("network", "ASOS")
            ),  # Default to ASOS if not specified
            "lat": float(row.get("latitude", 0)),
            "lon": float(row.get("longitude", 0)),
            "value": round(val, 1),
            "color": color,
            "unit": meta["unit"],
            "temperature": _safe_float(row, "air_temperature"),
            "dew_point": _safe_float(row, "dew_point_temperature"),
            "feels_like": _safe_float(row, "feels_like"),
            "rh": _safe_float(row, "relative_humidity"),
            "wind_speed": _safe_float(row, "wind_speed"),
            "wind_dir": _safe_float(row, "wind_dir"),
            "wind_gust": _safe_float(row, "peak_wind"),
            "visibility": _safe_float(row, "visibility"),
        }
        stations.append(station)
    return stations


def _refresh_surface_cache_async(
    region_upper: str, product_lower: str, cache_file: str
) -> None:
    """Refresh stale surface cache in background (stale-while-revalidate)."""
    cache_key = f"{region_upper}:{product_lower}"
    try:
        df = surface_utils.fetch_metar_data(region_upper)
        stations = _build_surface_stations(df, product_lower)
        source_ts = _surface_source_timestamp_iso(df)
        result = {
            "stations": stations,
            "product": product_lower,
            "unit": _SURFACE_PRODUCTS[product_lower]["unit"],
            "region": region_upper,
            "count": len(stations),
            "timestamp": source_ts,
            "timestamp_source": "station_valid",
        }
        try:
            with open(cache_file, "w", encoding="utf-8") as fh:
                json.dump(result, fh)
        except Exception:
            pass
    except Exception as exc:
        print(f"[WARN] Surface background refresh failed ({cache_key}): {exc}")
    finally:
        with _surface_refresh_lock:
            _surface_refresh_inflight.discard(cache_key)


def _kickoff_surface_refresh_if_needed(
    region_upper: str, product_lower: str, cache_file: str
) -> None:
    """Start at most one background refresh per region/product cache key."""
    cache_key = f"{region_upper}:{product_lower}"
    with _surface_refresh_lock:
        if cache_key in _surface_refresh_inflight:
            return
        _surface_refresh_inflight.add(cache_key)
    threading.Thread(
        target=_refresh_surface_cache_async,
        args=(region_upper, product_lower, cache_file),
        name=f"surface-refresh-{region_upper}-{product_lower}",
        daemon=True,
    ).start()


def _safe_float(row, col: str):
    import math

    val = row.get(col)
    if val is None:
        return None
    try:
        f = float(val)
        return None if math.isnan(f) else round(f, 1)
    except (TypeError, ValueError):
        return None


def _surface_source_timestamp_iso(df) -> str | None:
    """Return newest UTC observation timestamp from a surface dataframe."""
    if df is None or getattr(df, "empty", True) or "valid" not in df.columns:
        return None

    latest_dt: datetime | None = None
    try:
        valid_values = df["valid"].tolist()
    except Exception:
        return None

    for raw in valid_values:
        if raw is None:
            continue

        dt_val: datetime | None = None
        if isinstance(raw, datetime):
            dt_val = raw
        else:
            text = str(raw).strip()
            if not text or text.lower() in {"nat", "nan", "none"}:
                continue
            try:
                dt_val = datetime.fromisoformat(text.replace("Z", "+00:00"))
            except Exception:
                dt_val = None

        if dt_val is None:
            continue

        if dt_val.tzinfo is None:
            dt_val = dt_val.replace(tzinfo=timezone.utc)
        else:
            dt_val = dt_val.astimezone(timezone.utc)

        if latest_dt is None or dt_val > latest_dt:
            latest_dt = dt_val

    return latest_dt.isoformat() if latest_dt else None


# ── Phase 1: Data Endpoints (served from worker cache) ───────────────────────


@app.get("/api/data/surface")
def get_data_surface(region: str = "NC", product: str = "temperature"):
    """Return surface observations JSON with stale-while-revalidate caching."""
    region_upper = region.upper().strip()
    product_lower = product.lower().strip()
    if product_lower not in _SURFACE_PRODUCTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown product '{product}'. Valid: {list(_SURFACE_PRODUCTS.keys())}",
        )

    surface_cache_dir = os.path.join(_CACHE_ROOT, "surface")
    os.makedirs(surface_cache_dir, exist_ok=True)
    cache_file = os.path.join(surface_cache_dir, f"{region_upper}_{product_lower}.json")

    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as fh:
                cached = json.load(fh)

            # Migration guard: pre-source-timestamp cache entries used local
            # generation time. Rebuild once so Current tab reflects source time.
            # Also skip the cache if timestamp is null (pre-source-ts build).
            if (
                cached.get("timestamp_source") == "station_valid"
                and cached.get("timestamp") is not None
            ):
                age = _time.time() - os.path.getmtime(cache_file)
                if age >= _SURFACE_CACHE_TTL_SECONDS:
                    _kickoff_surface_refresh_if_needed(
                        region_upper, product_lower, cache_file
                    )
                return cached
        except Exception:
            pass

    try:
        df = surface_utils.fetch_metar_data(region_upper)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Surface data unavailable: {exc}")

    stations = _build_surface_stations(df, product_lower)
    source_ts = _surface_source_timestamp_iso(df)
    result = {
        "stations": stations,
        "product": product_lower,
        "unit": _SURFACE_PRODUCTS[product_lower]["unit"],
        "region": region_upper,
        "count": len(stations),
        "timestamp": source_ts,
        "timestamp_source": "station_valid",
    }

    try:
        with open(cache_file, "w", encoding="utf-8") as fh:
            json.dump(result, fh)
    except Exception:
        pass

    return result


@app.get("/api/data/surface-gradient")
def get_data_surface_gradient(region: str = "CONUS", product: str = "temperature"):
    """Return cached worker-generated surface gradient metadata.

    Gradients are generated by workers/surface_worker.py and stored under
    cache/surface/gradients/{source_region}/{product}.json.
    """
    region_upper = str(region or "CONUS").upper().strip()
    product_lower = str(product or "temperature").lower().strip()

    if product_lower not in _SURFACE_PRODUCTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown product '{product}'. Valid: {list(_SURFACE_PRODUCTS.keys())}",
        )
    if product_lower == "station_plot":
        raise HTTPException(
            status_code=400,
            detail="station_plot does not have a gradient overlay.",
        )

    source_region = "WORLD" if region_upper == "WORLD" else "CONUS"
    gradient_dir = os.path.join(
        _CACHE_ROOT,
        "surface",
        "gradients",
        source_region,
    )
    meta_path = os.path.join(gradient_dir, f"{product_lower}.json")

    if not os.path.exists(meta_path):
        raise HTTPException(
            status_code=404,
            detail=(
                f"No cached surface gradient for region={source_region}, "
                f"product={product_lower}. Worker may not have run yet."
            ),
        )

    try:
        with open(meta_path, "r", encoding="utf-8") as fh:
            meta = json.load(fh)
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to read gradient meta: {exc}"
        )

    image_url = str(meta.get("image_url") or "")
    if not image_url:
        raise HTTPException(
            status_code=500, detail="Gradient metadata is missing image_url."
        )

    rel = image_url.lstrip("/")
    if rel.startswith("cache/"):
        rel = rel[len("cache/") :]
    image_disk = os.path.join(_CACHE_ROOT, rel)
    if not os.path.exists(image_disk):
        raise HTTPException(
            status_code=404,
            detail="Cached gradient image is missing on disk. Worker refresh pending.",
        )

    return meta


@app.get("/api/data/colormap")
def get_colormap(product: str = "temperature"):
    """Return colormap anchor points for a given surface product."""
    product_lower = product.lower().strip()
    if product_lower not in _SURFACE_PRODUCTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown product '{product}'. Valid: {list(_SURFACE_PRODUCTS.keys())}",
        )
    meta = _SURFACE_PRODUCTS[product_lower]
    if meta["anchors"] == "temp":
        anchors = _TEMP_ANCHORS
    elif meta["anchors"] == "wind":
        anchors = _WIND_ANCHORS
    elif meta["anchors"] == "pressure":
        anchors = _PRESSURE_ANCHORS
    elif meta["anchors"] == "visibility":
        anchors = _VISIBILITY_ANCHORS
    else:
        anchors = _RH_ANCHORS
    return {
        "product": product_lower,
        "unit": meta["unit"],
        "anchors": [{"value": a[0], "color": a[1]} for a in anchors],
    }


def _load_mrms_render_meta(meta_sidecar: str) -> dict:
    if not os.path.exists(meta_sidecar):
        return {}
    with open(meta_sidecar, "r") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def _write_mrms_render_meta(meta_sidecar: str, render_meta: dict) -> None:
    with open(meta_sidecar, "w") as f:
        json.dump(render_meta, f)


def _normalize_mrms_data_timestamp(raw_time) -> str | None:
    """Convert GRIB time metadata to an ISO-8601 UTC string."""
    if raw_time is None:
        return None

    value = raw_time
    if hasattr(value, "tolist"):
        try:
            value = value.tolist()
        except Exception:
            pass
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    if value is None:
        return None

    dt = None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if not text or text.lower() == "nat":
            return None
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except Exception:
            dt = None

    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _build_mrms_meta_from_grib(grib_path: str, product: str, crop_extent: list) -> dict:
    from mrms.legend_utils import build_mrms_overlay_meta
    from mrms.mrms_utils import read_mrms_grib2

    data, meta = read_mrms_grib2(grib_path, product, crop_extent=crop_extent)
    render_meta = build_mrms_overlay_meta(product, data)
    data_ts = _normalize_mrms_data_timestamp(meta.get("time"))
    if data_ts:
        render_meta["data_timestamp"] = data_ts
    return render_meta


# ── Phase 3: MRMS Endpoints ──────────────────────────────────────────────────


@app.get("/api/mrms/set-product")
def mrms_set_product(product: str):
    """Switch the active MRMS product the worker will refresh."""
    global _active_mrms_product
    from config.mrms_config import MRMS_PRODUCTS

    if product not in MRMS_PRODUCTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown MRMS product '{product}'.",
        )
    _active_mrms_product = product
    # Also update the worker module's state so the scheduler picks it up
    try:
        from workers.mrms_worker import set_active_product

        set_active_product(product)
    except Exception:
        pass
    return {"active_product": product}


@app.get("/api/data/mrms")
def get_data_mrms(
    product: str = "PrecipRate",
    south: float = 21.0,
    west: float = -130.0,
    north: float = 52.0,
    east: float = -60.0,
):
    global _active_mrms_product
    from config.mrms_config import MRMS_PRODUCTS

    if product not in MRMS_PRODUCTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown MRMS product '{product}'.",
        )

    # Switching product → update active so worker starts refreshing it
    if product != _active_mrms_product:
        _active_mrms_product = product
        try:
            from workers.mrms_worker import set_active_product

            set_active_product(product)
        except Exception:
            pass

    product_cache_dir = os.path.join(_CACHE_ROOT, "mrms", product)
    os.makedirs(product_cache_dir, exist_ok=True)
    grib_path = os.path.join(product_cache_dir, "conus.grib2.gz")

    # Cold-cache: download now (blocking, first request only)
    if not os.path.exists(grib_path):
        try:
            from workers.mrms_worker import run_mrms_worker, set_active_product

            set_active_product(product)
            run_mrms_worker(force=True)
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail=f"MRMS data for '{product}' not yet available: {exc}",
            )

    if not os.path.exists(grib_path):
        raise HTTPException(
            status_code=503,
            detail=f"MRMS cache file missing after fetch attempt for '{product}'.",
        )

    # If cached GRIB is old, request a targeted refresh for this product.
    # This prevents stale overnight frames from persisting when UI switches
    # to a product that has not been pre-warmed recently.
    MRMS_STALE_GRIB_SECONDS = 90 * 60
    grib_mtime = os.path.getmtime(grib_path)
    grib_age_seconds = datetime.now(timezone.utc).timestamp() - grib_mtime
    if grib_age_seconds > MRMS_STALE_GRIB_SECONDS:
        try:
            from workers.mrms_worker import run_mrms_worker, set_active_product

            set_active_product(product)
            run_mrms_worker(force=True)
        except Exception:
            pass

        if not os.path.exists(grib_path):
            raise HTTPException(
                status_code=503,
                detail=f"MRMS cache file missing after stale refresh attempt for '{product}'.",
            )
        grib_mtime = os.path.getmtime(grib_path)

    # Check if a recent PNG crop is already cached for this product + bounds
    import hashlib

    bounds_key = hashlib.md5(
        f"{product}_{south:.2f}_{west:.2f}_{north:.2f}_{east:.2f}".encode()
    ).hexdigest()[:10]
    png_path = os.path.join(product_cache_dir, f"overlay_{bounds_key}.png")
    grib_mtime = os.path.getmtime(grib_path)
    png_stale = not os.path.exists(png_path) or os.path.getmtime(png_path) < grib_mtime

    meta_sidecar = png_path.replace(".png", "_meta.json")

    if png_stale:
        try:
            png_path, actual_bounds, render_meta = _render_mrms_png(
                grib_path, product, [west, east, south, north], png_path
            )
        except Exception:
            # Self-heal once: clear stale/corrupt artifacts, force-refresh this
            # product, then retry render.
            stale_grib2 = grib_path[:-3] if grib_path.endswith(".gz") else None
            for stale_path in [
                grib_path,
                stale_grib2,
                png_path,
                png_path.replace(".png", "_bounds.json"),
                meta_sidecar,
            ]:
                if stale_path and os.path.exists(stale_path):
                    try:
                        os.remove(stale_path)
                    except OSError:
                        pass

            try:
                from workers.mrms_worker import run_mrms_worker, set_active_product

                set_active_product(product)
                run_mrms_worker(force=True)
            except Exception:
                pass

            try:
                png_path, actual_bounds, render_meta = _render_mrms_png(
                    grib_path, product, [west, east, south, north], png_path
                )
            except Exception as retry_exc:
                raise HTTPException(
                    status_code=503,
                    detail=(
                        f"MRMS render error for '{product}' after refresh retry: {retry_exc}"
                    ),
                ) from retry_exc
    else:
        # Read bounds from sidecar file
        sidecar = png_path.replace(".png", "_bounds.json")
        if os.path.exists(sidecar):
            with open(sidecar, "r") as f:
                actual_bounds = json.load(f)
        else:
            actual_bounds = [west, east, south, north]
        render_meta = _load_mrms_render_meta(meta_sidecar)
        if not render_meta:
            try:
                render_meta = _build_mrms_meta_from_grib(
                    grib_path, product, [west, east, south, north]
                )
            except Exception:
                # Non-fatal when PNG is already rendered: keep serving overlay
                # and fall back to mtime-based timestamp until next refresh.
                render_meta = {}
            _write_mrms_render_meta(meta_sidecar, render_meta)
        elif not render_meta.get("data_timestamp"):
            # Backfill data-valid timestamp for older sidecars.
            try:
                refreshed_meta = _build_mrms_meta_from_grib(
                    grib_path, product, [west, east, south, north]
                )
                if refreshed_meta.get("data_timestamp"):
                    render_meta["data_timestamp"] = refreshed_meta.get("data_timestamp")
                    _write_mrms_render_meta(meta_sidecar, render_meta)
            except Exception:
                pass

    # Build URL relative to /cache mount

    rel = os.path.relpath(png_path, _CACHE_ROOT).replace("\\", "/")
    image_url = f"/cache/{rel}"

    timestamp = (
        render_meta.get("data_timestamp")
        or datetime.fromtimestamp(grib_mtime, tz=timezone.utc).isoformat()
    )

    # Mirror every successful manual view into the flat overlay cache so future
    # product revisits can hit /api/overlay/latest without triggering re-render.
    try:
        from workers.mrms_worker import _write_mrms_overlay_cache

        frame_dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if frame_dt.tzinfo is None:
            frame_dt = frame_dt.replace(tzinfo=timezone.utc)
        _write_mrms_overlay_cache(product, png_path, frame_dt)
    except Exception:
        # Non-fatal: /api/data/mrms still returns the rendered image payload.
        pass

    prod_info = MRMS_PRODUCTS[product]
    return {
        "image_url": image_url,
        "bounds": actual_bounds,
        "product": product,
        "full_name": prod_info.get("full_name", product),
        "units": prod_info.get("units", ""),
        "colormap": prod_info.get("colormap", ""),
        "vmin": prod_info.get("vmin", 0),
        "vmax": prod_info.get("vmax", 100),
        "legend": render_meta.get("legend"),
        "timestamp": timestamp,
    }


def _render_mrms_png(
    grib_path: str,
    product: str,
    crop_extent: list,
    out_path: str,
) -> tuple:
    """
    Read MRMS GRIB2, crop to extent, apply colormap, save as transparent PNG.
    Returns (png_path, [west, east, south, north] actual bounds).
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.colors as mcolors

    from mrms.legend_utils import build_mrms_overlay_meta, mask_mrms_data
    from mrms.mrms_utils import read_mrms_grib2
    from config.mrms_config import MRMS_PRODUCTS, MRMS_COLORMAPS

    prod_info = MRMS_PRODUCTS[product]
    cmap_key = prod_info.get("colormap", "precip_rate")
    vmin = prod_info.get("vmin", 0)
    vmax = prod_info.get("vmax", 100)

    west, east, south, north = crop_extent

    data, meta = read_mrms_grib2(grib_path, product, crop_extent=crop_extent)

    # Mask fill/missing/no-precip values (0 = no precip for all rate/accumulation products)
    data = mask_mrms_data(data, prod_info)

    lat = meta.get("latitude")
    lon = meta.get("longitude")
    if lat is None or lon is None:
        raise ValueError("GRIB2 read did not return lat/lon metadata")

    # Derive bounds from the actual cropped grid coordinates with half-cell
    import numpy as _np_mrms

    _lat = _np_mrms.asarray(lat)
    _lon = _np_mrms.asarray(lon)

    # Build colormap
    cmap_obj = MRMS_COLORMAPS.get(cmap_key)
    if isinstance(cmap_obj, tuple):
        cmap, norm = (
            cmap_obj[0],
            cmap_obj[1]
            if len(cmap_obj) > 1
            else mcolors.Normalize(vmin=vmin, vmax=vmax),
        )
    elif cmap_obj is not None:
        cmap = cmap_obj
        norm = mcolors.Normalize(vmin=vmin, vmax=vmax)
    else:
        cmap = plt.get_cmap("viridis")
        norm = mcolors.Normalize(vmin=vmin, vmax=vmax)

    # Reproject to Web Mercator so pixels align with Leaflet imageOverlay
    # (Leaflet's default map CRS is EPSG:3857). The returned bounds are WGS84
    # lat/lon corners of the warped image — Leaflet expects geographic corner
    # coordinates for imageOverlay.
    from mrms.mrms_utils import warp_array_to_mercator
    from config.mrms_config import MRMS_WARP_MAX_DIM
    from PIL import Image
    import numpy as _np_render

    data = _np_render.ma.asarray(data)
    data, actual_bounds = warp_array_to_mercator(
        data, _lat, _lon, max_dim=MRMS_WARP_MAX_DIM
    )

    # Render the warped Mercator array directly to PNG using PIL, bypassing
    # matplotlib's figure system. This avoids matplotlib's silent downscaling
    # of large figures and ensures the saved PNG dimensions exactly match the
    # warped data shape (which is required for Leaflet to align the overlay).
    masked = _np_render.ma.getmaskarray(data)
    filled = _np_render.ma.filled(data, _np_render.nan)
    normalized = norm(filled)
    rgb = cmap(normalized)
    rgba = (rgb * 255).astype(_np_render.uint8)
    invalid = masked | _np_render.isnan(filled)
    if _np_render.any(invalid):
        rgba[invalid, 3] = 0
    Image.fromarray(rgba, mode="RGBA").save(
        out_path, format="PNG", optimize=False, compress_level=1
    )

    # Write bounds sidecar
    sidecar = out_path.replace(".png", "_bounds.json")
    with open(sidecar, "w") as f:
        json.dump(actual_bounds, f)

    render_meta = build_mrms_overlay_meta(product, data)
    data_ts = _normalize_mrms_data_timestamp(meta.get("time"))
    if data_ts:
        render_meta["data_timestamp"] = data_ts
    _write_mrms_render_meta(out_path.replace(".png", "_meta.json"), render_meta)

    return out_path, actual_bounds, render_meta


@app.get("/api/data/rtma/points")
def get_data_rtma_points(
    region: str = "CONUS",
    stream: str = "rtma_hourly",
    product: str = "temperature",
    source_data_key: str | None = None,
    south: float | None = None,
    west: float | None = None,
    north: float | None = None,
    east: float | None = None,
    stride: int = 30,
):
    from rtma.rtma_utils import (
        build_rtma_legend,
        ensure_rtma_city_geojson,
        get_product_config,
        iter_rtma_sources,
        resolve_rtma_source_by_data_key,
        resolve_rtma_source,
    )

    region_key = region.upper()
    if region_key not in STATE_BOUNDS:
        raise HTTPException(status_code=400, detail=f"Unknown RTMA region '{region}'.")

    if product == "temperature_change_24h" and stream != "rtma_hourly":
        raise HTTPException(
            status_code=400,
            detail="RTMA 24-hour temperature change is only available on rtma_hourly.",
        )

    # Narrow types for the static type checker: explicitly check variables
    # before calling float() so we never pass None to float().
    if south is not None and west is not None and north is not None and east is not None:
        bounds_values = (float(south), float(west), float(north), float(east))
    else:
        bounds_values = None

    def _read_points_from_cache(path: str) -> list[dict]:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception as exc:
            raise HTTPException(
                status_code=500, detail=f"RTMA city-point read error: {exc}"
            )

        points: list[dict] = []
        # Compact format (v1): {"v":1,"points":[[lat,lon,value,rank],...], ...}
        if data.get("v") == 1:
            for row in data.get("points", []):
                if len(row) < 3:
                    continue
                lat, lon, val = float(row[0]), float(row[1]), float(row[2])
                rank = row[3] if len(row) > 3 else None
                if bounds_values is not None:
                    bound_s, bound_w, bound_n, bound_e = bounds_values
                    if (
                        lat < bound_s
                        or lat > bound_n
                        or lon < bound_w
                        or lon > bound_e
                    ):
                        continue
                points.append({"lat": lat, "lon": lon, "value": val, "rank": rank})
            return points

        # Legacy GeoJSON FeatureCollection — remove after next worker run.
        for feat in data.get("features", []):
            geom = feat.get("geometry") or {}
            if geom.get("type") != "Point":
                continue
            coords = geom.get("coordinates") or []
            if len(coords) < 2:
                continue
            lon = float(coords[0])
            lat = float(coords[1])
            if bounds_values is not None:
                bound_s, bound_w, bound_n, bound_e = bounds_values
                if lat < bound_s or lat > bound_n or lon < bound_w or lon > bound_e:
                    continue
            props = feat.get("properties") or {}
            val = props.get("value")
            if val is None:
                continue
            points.append(
                {
                    "lat": lat,
                    "lon": lon,
                    "value": float(val),
                    "rank": props.get("rank"),
                }
            )
        return points

    try:
        product_cfg = get_product_config(product)
        if source_data_key:
            # Fast path: when frontend provides source_data_key and the worker
            # has already cached points for that frame, serve directly from disk
            # with no upstream source-resolution HEAD checks.
            token = "".join(
                ch if ch.isalnum() or ch in {"-", "_", "."} else "_"
                for ch in source_data_key
            )
            points_dir = os.path.join(_CACHE_ROOT, "rtma", "points", region_key, stream)
            cached_geojson_path = os.path.join(
                points_dir, f"{product}__{token}.geojson"
            )
            cached_meta_path = cached_geojson_path.replace(".geojson", "_meta.json")
            if os.path.exists(cached_geojson_path):
                meta = None
                if os.path.exists(cached_meta_path):
                    try:
                        with open(cached_meta_path, "r", encoding="utf-8") as handle:
                            meta = json.load(handle)
                    except Exception:
                        meta = None
                points = _read_points_from_cache(cached_geojson_path)
                return {
                    "points": points,
                    "units": product_cfg.get("units", ""),
                    "full_name": product_cfg.get("label", product),
                    "vmin": product_cfg.get("vmin"),
                    "vmax": product_cfg.get("vmax"),
                    "legend": build_rtma_legend(product_cfg),
                    "timestamp": (meta or {}).get("timestamp")
                    or (meta or {}).get("source_valid_time")
                    or None,
                    "source": source_data_key,
                    "source_data_key": source_data_key,
                    "region": region_key,
                    "stream": stream,
                    "product": product,
                }

            source = resolve_rtma_source_by_data_key(
                region_key,
                stream,
                product,
                source_data_key,
                hours_back=clamp_stream_hours(stream),
            )
        else:
            source = resolve_rtma_source(region_key, stream, product)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    cities_path = os.path.join(BASE_DIR, "data", "us-cities.json")
    if not os.path.exists(cities_path):
        raise HTTPException(status_code=500, detail="Missing data/us-cities.json")

    geojson_path = None
    meta = None
    primary_exc = None

    try:
        geojson_path, meta = ensure_rtma_city_geojson(
            _CACHE_ROOT,
            source,
            region_key,
            stream,
            product,
            cities_path,
            source_data_key=source_data_key,
        )
    except Exception as exc:
        primary_exc = exc

    if not geojson_path:
        if source_data_key:
            raise HTTPException(
                status_code=503,
                detail=(
                    "RTMA city-point generation failed for requested frame: "
                    f"data_key={source_data_key}; error={primary_exc}"
                ),
            )
        fallback_exc = None
        tried = 0
        for alt_source in iter_rtma_sources(region_key, stream, product):
            if alt_source.data_key == source.data_key:
                continue
            tried += 1
            if tried > 8:
                break
            try:
                geojson_path, meta = ensure_rtma_city_geojson(
                    _CACHE_ROOT,
                    alt_source,
                    region_key,
                    stream,
                    product,
                    cities_path,
                    source_data_key=source_data_key,
                )
                source = alt_source
                break
            except Exception as exc:
                fallback_exc = exc

        if not geojson_path:
            raise HTTPException(
                status_code=503,
                detail=(
                    "RTMA city-point generation failed: "
                    f"primary={primary_exc}; fallback={fallback_exc}"
                ),
            )

    points = _read_points_from_cache(geojson_path)

    return {
        "points": points,
        "units": product_cfg.get("units", ""),
        "full_name": product_cfg.get("label", product),
        "vmin": product_cfg.get("vmin"),
        "vmax": product_cfg.get("vmax"),
        "legend": build_rtma_legend(product_cfg),
        "timestamp": (meta or {}).get("timestamp") or source.valid_time.isoformat(),
        "source": source.data_key,
        "source_data_key": source.data_key,
        "region": region_key,
        "stream": stream,
        "product": product,
    }


@app.get("/api/data/rtma/grid")
def get_data_rtma_grid(
    region: str = "CONUS",
    stream: str = "rtma_hourly",
    product: str = "temperature",
    source_data_key: str | None = None,
    stride: int = 2,
):
    from rtma.rtma_utils import (
        build_rtma_legend,
        ensure_rtma_grid_json,
        get_product_config,
        iter_rtma_sources,
        resolve_rtma_source_by_data_key,
        resolve_rtma_source,
    )

    region_key = region.upper()
    if region_key not in STATE_BOUNDS:
        raise HTTPException(status_code=400, detail=f"Unknown RTMA region '{region}'.")

    if product == "temperature_change_24h" and stream != "rtma_hourly":
        raise HTTPException(
            status_code=400,
            detail="RTMA 24-hour temperature change is only available on rtma_hourly.",
        )

    stride = max(1, min(stride, 64))

    try:
        product_cfg = get_product_config(product)
        if source_data_key:
            source = resolve_rtma_source_by_data_key(
                region_key,
                stream,
                product,
                source_data_key,
                hours_back=clamp_stream_hours(stream),
            )
        else:
            source = resolve_rtma_source(region_key, stream, product)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    grid_path = None
    meta = None
    primary_exc = None

    try:
        grid_path, meta = ensure_rtma_grid_json(
            _CACHE_ROOT, source, region_key, stream, product, stride=stride
        )
    except Exception as exc:
        primary_exc = exc

    if not grid_path:
        tried = 0
        for alt_source in iter_rtma_sources(region_key, stream, product):
            if alt_source.data_key == source.data_key:
                continue
            tried += 1
            if tried > 8:
                break
            try:
                grid_path, meta = ensure_rtma_grid_json(
                    _CACHE_ROOT, alt_source, region_key, stream, product, stride=stride
                )
                source = alt_source
                break
            except Exception:
                pass

    if not grid_path:
        raise HTTPException(
            status_code=503,
            detail=f"RTMA grid generation failed: {primary_exc}",
        )

    try:
        with open(grid_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"RTMA grid read error: {exc}")

    return {
        "v": 1,
        "product": product,
        "units": product_cfg.get("units", ""),
        "full_name": product_cfg.get("label", product),
        "vmin": product_cfg.get("vmin"),
        "vmax": product_cfg.get("vmax"),
        "legend": build_rtma_legend(product_cfg),
        "timestamp": (meta or {}).get("timestamp") or source.valid_time.isoformat(),
        "source_data_key": source.data_key,
        "region": region_key,
        "stream": stream,
        "stride": stride,
        "points": data.get("points", []),
    }


@app.get("/api/data/rtma")
def get_data_rtma(
    region: str = "CONUS",
    stream: str = "rtma_hourly",
    product: str = "temperature",
    source_data_key: str | None = None,
    south: float = 21.0,
    west: float = -130.0,
    north: float = 52.0,
    east: float = -60.0,
):
    from rtma.rtma_utils import (
        ensure_rtma_grib,
        get_product_config,
        iter_rtma_sources,
        resolve_rtma_source_by_data_key,
        _render_rtma_png_standalone,
        resolve_rtma_source,
    )

    region_key = region.upper()
    if region_key not in STATE_BOUNDS:
        raise HTTPException(status_code=400, detail=f"Unknown RTMA region '{region}'.")

    if product == "temperature_change_24h" and stream != "rtma_hourly":
        raise HTTPException(
            status_code=400,
            detail="RTMA 24-hour temperature change is only available on rtma_hourly.",
        )

    try:
        product_cfg = get_product_config(product)
        if source_data_key:
            source = resolve_rtma_source_by_data_key(
                region_key,
                stream,
                product,
                source_data_key,
                hours_back=clamp_stream_hours(stream),
            )
        else:
            source = resolve_rtma_source(region_key, stream, product)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    try:
        grib_path = ensure_rtma_grib(_CACHE_ROOT, source)
    except Exception as primary_exc:
        if source_data_key:
            raise HTTPException(
                status_code=503,
                detail=(
                    "RTMA download failed for requested frame: "
                    f"data_key={source_data_key}; error={primary_exc}"
                ),
            )
        grib_path = None
        fallback_exc = None
        tried = 0
        for alt_source in iter_rtma_sources(region_key, stream, product):
            if alt_source.data_key == source.data_key:
                continue
            tried += 1
            if tried > 8:
                break
            try:
                grib_path = ensure_rtma_grib(
                    _CACHE_ROOT, alt_source, force_refresh=True
                )
                source = alt_source
                break
            except Exception as exc:
                fallback_exc = exc

        if not grib_path:
            raise HTTPException(
                status_code=503,
                detail=(
                    "RTMA download failed: "
                    f"primary={primary_exc}; fallback={fallback_exc}"
                ),
            )

    import hashlib

    bounds_key = hashlib.md5(
        f"{region_key}_{stream}_{product}_{source.data_key}_{south:.2f}_{west:.2f}_{north:.2f}_{east:.2f}".encode()
    ).hexdigest()[:12]
    product_cache_dir = os.path.join(_CACHE_ROOT, "rtma", region_key, stream, product)
    os.makedirs(product_cache_dir, exist_ok=True)
    png_path = os.path.join(product_cache_dir, f"overlay_{bounds_key}.png")

    sidecar_bounds = png_path.replace(".png", "_bounds.json")
    sidecar_meta = png_path.replace(".png", "_meta.json")
    png_stale = not os.path.exists(png_path) or os.path.getmtime(
        png_path
    ) < os.path.getmtime(grib_path)

    if png_stale:
        try:
            png_path, actual_bounds, render_meta = _render_rtma_png_standalone(
                grib_path,
                product,
                [west, east, south, north],
                png_path,
                cache_root=_CACHE_ROOT,
                source=source,
                region=region_key,
                stream=stream,
            )
        except Exception as first_exc:
            if source_data_key:
                raise HTTPException(
                    status_code=500,
                    detail=(
                        "RTMA render error for requested frame: "
                        f"data_key={source_data_key}; error={first_exc}"
                    ),
                )
            # Occasionally a cached GRIB can be incomplete/corrupt (for example,
            # interrupted download). Retry once with a force-refreshed file.
            try:
                grib_path = ensure_rtma_grib(_CACHE_ROOT, source, force_refresh=True)
                png_path, actual_bounds, render_meta = _render_rtma_png_standalone(
                    grib_path,
                    product,
                    [west, east, south, north],
                    png_path,
                    cache_root=_CACHE_ROOT,
                    source=source,
                    region=region_key,
                    stream=stream,
                )
            except Exception as exc:
                retry_exc = exc
                # Source can be HEAD-visible but non-GRIB for the latest cycle.
                # Fall back through a few recent candidates.
                alt_render = None
                alt_exc = None
                tried = 0
                for alt_source in iter_rtma_sources(region_key, stream, product):
                    if alt_source.data_key == source.data_key:
                        continue
                    tried += 1
                    if tried > 8:
                        break
                    try:
                        alt_grib_path = ensure_rtma_grib(
                            _CACHE_ROOT, alt_source, force_refresh=True
                        )
                        alt_render = _render_rtma_png_standalone(
                            alt_grib_path,
                            product,
                            [west, east, south, north],
                            png_path,
                            cache_root=_CACHE_ROOT,
                            source=alt_source,
                            region=region_key,
                            stream=stream,
                        )
                        source = alt_source
                        break
                    except Exception as inner_exc:
                        alt_exc = inner_exc

                if alt_render is not None:
                    png_path, actual_bounds, render_meta = alt_render
                else:
                    raise HTTPException(
                        status_code=500,
                        detail=(
                            "RTMA render error after cache refresh: "
                            f"initial={first_exc}; retry={retry_exc}; fallback={alt_exc}"
                        ),
                    )
    else:
        try:
            with open(sidecar_bounds, "r", encoding="utf-8") as handle:
                actual_bounds = json.load(handle)
        except Exception:
            actual_bounds = [west, east, south, north]
        try:
            with open(sidecar_meta, "r", encoding="utf-8") as handle:
                render_meta = json.load(handle)
        except Exception:
            render_meta = {
                "full_name": product_cfg.get("label", product),
                "units": product_cfg.get("units", ""),
                "vmin": product_cfg.get("vmin"),
                "vmax": product_cfg.get("vmax"),
                "legend": None,
                "timestamp": source.valid_time.isoformat(),
            }

    # Mirror successful RTMA on-demand requests into the flat overlay cache so
    # later loads can hit /api/overlay/latest without a fresh render.
    if product != "wind_direction":
        try:
            from workers.rtma_worker import _render_overlay_for_source

            _render_overlay_for_source(
                _CACHE_ROOT,
                source,
                region_key,
                stream,
                product,
                keep_n=30,
            )
        except Exception:
            # Non-fatal: this endpoint still returns the on-demand overlay.
            pass

    rel = os.path.relpath(png_path, _CACHE_ROOT).replace("\\", "/")
    return {
        "image_url": f"/cache/{rel}",
        "bounds": actual_bounds,
        "region": region_key,
        "stream": stream,
        "product": product,
        "full_name": render_meta.get("full_name", product_cfg.get("label", product)),
        "units": render_meta.get("units", product_cfg.get("units", "")),
        "vmin": render_meta.get("vmin", product_cfg.get("vmin")),
        "vmax": render_meta.get("vmax", product_cfg.get("vmax")),
        "legend": render_meta.get("legend"),
        "timestamp": render_meta.get("timestamp") or source.valid_time.isoformat(),
        "source_data_key": source.data_key,
    }


app.include_router(create_overlays_router(rtma_bootstrap=get_data_rtma))


@app.get("/api/data/rtma/frames")
def get_data_rtma_frames(
    region: str = "CONUS",
    stream: str = "rtma_hourly",
    product: str = "temperature",
    max_hours: int | None = None,
):
    from rtma.rtma_utils import get_product_config, iter_rtma_sources_within_hours

    region_key = region.upper()
    if region_key not in STATE_BOUNDS:
        raise HTTPException(status_code=400, detail=f"Unknown RTMA region '{region}'.")

    if stream not in RTMA_STREAM_MAX_HOURS:
        raise HTTPException(
            status_code=400, detail=f"Unsupported RTMA stream '{stream}'."
        )

    if product == "temperature_change_24h" and stream != "rtma_hourly":
        raise HTTPException(
            status_code=400,
            detail="RTMA 24-hour temperature change is only available on rtma_hourly.",
        )

    try:
        product_cfg = get_product_config(product)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    hours_back = clamp_stream_hours(stream, max_hours)
    try:
        frames_desc = list(
            iter_rtma_sources_within_hours(
                region_key,
                stream,
                product,
                hours_back=hours_back,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    # Scrubber expects oldest on the left, newest on the right.
    frames = [
        {
            "source_data_key": src.data_key,
            "timestamp": src.valid_time.astimezone(timezone.utc).isoformat(),
            "region": region_key,
            "stream": stream,
            "product": product,
        }
        for src in sorted(frames_desc, key=lambda x: x.valid_time)
    ]

    return {
        "region": region_key,
        "stream": stream,
        "product": product,
        "full_name": product_cfg.get("label", product),
        "units": product_cfg.get("units", ""),
        "max_hours": int(RTMA_STREAM_MAX_HOURS[stream]),
        "hours_back": hours_back,
        "frame_count": len(frames),
        "frames": frames,
    }


# ── Phase 4: Archive Endpoints ───────────────────────────────────────────────


_ARCHIVE_ROOT = os.path.join(_CACHE_ROOT, "archive")
_ARCHIVE_SESSION_TTL_HOURS = 2
_ARCHIVE_MAX_SESSIONS = 20
_archive_sessions: dict = {}  # session_id → {expires_utc, status, frames, ...}
_archive_lock = threading.Lock()


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


# ─── 4a: MRMS Archive ─────────────────────────────────────────────────────────


@app.get("/api/archive/mrms")
def archive_mrms(
    product: str = "PrecipRate",
    date_from: str = "",
    date_to: str = "",
    max_frames: int = 24,
    south: float = 21.0,
    west: float = -130.0,
    north: float = 52.0,
    east: float = -60.0,
    request_id: str = "",
):
    """
    List MRMS GRIB2 files from S3 for the time range, download and render up to
    max_frames subsampled PNGs in a background thread.
    Poll /api/progress/{request_id} for status; retrieve frames via
    /api/archive/result?session_id={session_id} once status=='success'.
    """
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
            from lib.s3_utils import get_s3_client
            from config.mrms_config import MRMS_BUCKET
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
                    png_path, bounds = _render_mrms_png(
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
                rel = os.path.relpath(png_path, _CACHE_ROOT).replace("\\", "/")
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


@app.get("/api/archive/result")
def archive_result(session_id: str):
    """Return the current state (and frames when complete) of an archive session."""
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


# ─── Archive JSON disk cache ────────────────────────────────────────────────
# Keyed by a hash of the query parameters.  Historical data never changes, so
# cached files live indefinitely and eliminate repeated IEM / SPC / AWC hits.

_ARCHIVE_JSON_DIR = os.path.join("cache", "archive", "json")
os.makedirs(_ARCHIVE_JSON_DIR, exist_ok=True)


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


# ─── 4b: Alerts Archive (IEM WatchWarn) ──────────────────────────────────────


@app.get("/api/archive/alerts")
def archive_alerts(
    date_from: str = "",
    date_to: str = "",
    state: str = "",
):
    """
    Fetch NWS alert polygons from IEM WatchWarn for a historical date range.
    Returns all alerts active during [date_from, date_to] as a single GeoJSON frame.
    """
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

    # IEM expects UTC — convert from whatever tz the caller supplied
    utc_from = dt_from.astimezone(timezone.utc)
    utc_to = dt_to.astimezone(timezone.utc)

    # IEM watchwarn.py filters by issuance time, not active-during window.
    # Extend start 72 h earlier to capture watches/warnings issued before the
    # window but still active during it (e.g. tropical watches issued 48 h
    # ahead of landfall).  The JS frame-slicer filters each frame by
    # onset/expires, so extra pre-window alerts won't display.
    LOOKBACK = timedelta(hours=72)
    query_from = utc_from - LOOKBACK

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

            # Convert IEM YYYYMMDDHHMM timestamps to ISO-8601
            def _iem_to_iso(raw: str) -> str:
                s = str(raw or "").strip()
                if len(s) >= 12:
                    try:
                        dt = datetime(
                            int(s[0:4]),
                            int(s[4:6]),
                            int(s[6:8]),
                            int(s[8:10]),
                            int(s[10:12]),
                            tzinfo=timezone.utc,
                        )
                        return dt.isoformat()
                    except Exception:
                        pass
                return s

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


@app.get("/api/archive/surface")
def archive_surface(
    region: str = "NC",
    product: str = "temperature",
    date_from: str = "",
    date_to: str = "",
    max_frames: int = 24,
    source: str = "iem",
    network: str = "ASOS",
):
    """Fetch historical surface frames from IEM-compatible ASOS data for scrubber playback."""
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
    if product_key not in _SURFACE_PRODUCTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown product '{product}'. Valid: {list(_SURFACE_PRODUCTS.keys())}",
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
    # Surface uses hourly frame times (ASOS reports at top of hour)
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
        frame_dfs = surface_utils.fetch_metar_data_archive_frames(
            region_upper, frame_times, source=source_key
        )
    except Exception:
        frame_dfs = [None] * len(frame_times)

    frames = []
    for idx, ts in enumerate(frame_times):
        try:
            df = frame_dfs[idx] if idx < len(frame_dfs) else None
            if df is None:
                df = surface_utils.fetch_metar_data_at_time(
                    region_upper, ts, source=source_key
                )
            stations = _build_surface_stations(df, product_key)
        except Exception:
            stations = []

        frames.append(
            {
                "timestamp": ts.isoformat(),
                "stations": stations,
                "product": product_key,
                "unit": _SURFACE_PRODUCTS[product_key]["unit"],
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


# ─── 4c: SPC Archive (single-date snapshot) ───────────────────────────────────


@app.get("/api/archive/spc")
def archive_spc(
    day: int = 1,
    hazard: str = "cat",
    date: str = "",
):
    """
    Fetch a historical SPC outlook for a specific date (YYYY-MM-DD).
    Archive URL pattern: /products/outlook/archive/{year}/day{N}otlk_{YYYYMMDD}_{HHMM}.lyr.geojson
    Tries 1200, 1630, 2000, 0100 UTC issue times in order.
    """
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
    else:
        if hazard not in day3_hazards:
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
                with _ur.urlopen(url, timeout=15) as r:
                    geojson = json.loads(r.read().decode("utf-8", errors="replace"))
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


@app.get("/api/radar/sites")
def get_radar_sites():
    try:
        sites_path = os.path.join(BASE_DIR, "radar", "radar_sites.json")
        with open(sites_path, "r", encoding="utf-8") as fh:
            raw_sites = json.load(fh)

        if not isinstance(raw_sites, dict):
            raise ValueError("radar_sites.json is not a key/value object")

        sites = [
            {"label": label, "value": value}
            for label, value in raw_sites.items()
            if isinstance(label, str) and isinstance(value, str)
        ]
        sites.sort(key=lambda entry: entry["label"])

        return {
            "status": "success",
            "sites": sites,
            "count": len(sites),
        }
    except Exception as e:
        print(f"Radar sites endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/radar/site-locations")
def get_radar_site_locations():
    try:
        from pyart.io.nexrad_common import NEXRAD_LOCATIONS

        valid_prefixes = ("K", "P")
        valid_extras = {"TJUA"}

        sites = []
        seen = set()
        for site_id, info in NEXRAD_LOCATIONS.items():
            if not (site_id.startswith(valid_prefixes) or site_id in valid_extras):
                continue

            normalized_id = normalize_radar_site_id(site_id)
            if normalized_id in seen:
                continue

            lat = info.get("lat")
            lon = info.get("lon")
            if lat is None or lon is None:
                continue

            seen.add(normalized_id)
            sites.append(
                {
                    "site": normalized_id,
                    "lat": float(lat),
                    "lon": float(lon),
                }
            )

        sites.sort(key=lambda entry: entry["site"])
        return {
            "status": "success",
            "sites": sites,
            "count": len(sites),
        }
    except Exception as e:
        print(f"Radar site locations endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _radar_live_catalog():
    from config.radar_config import LIVE_RADAR_PRODUCTS

    return dict(LIVE_RADAR_PRODUCTS)


def _radar_live_sites():
    from config.radar_config import LIVE_RADAR_SITES

    return [normalize_radar_site_id(site) for site in LIVE_RADAR_SITES]


_RADAR_LIVE_FALLBACK_LOCKS: dict[tuple[str, str], threading.Lock] = {}
_RADAR_LIVE_FALLBACK_LOCKS_GUARD = threading.Lock()

# --- NWS Radar station operational status cache (5-minute TTL) ---
_NWS_RADAR_STATUS_CACHE: dict | None = None
_NWS_RADAR_STATUS_CACHE_TS: float = 0.0
_NWS_RADAR_STATUS_CACHE_LOCK = threading.Lock()
_NWS_RADAR_STATUS_TTL_SEC = 300


def _fetch_nws_radar_status() -> dict:
    """Fetch and cache radar station status from NWS API. Returns dict keyed by site ID."""
    import time
    import urllib.request as _ur

    global _NWS_RADAR_STATUS_CACHE, _NWS_RADAR_STATUS_CACHE_TS

    now = time.monotonic()
    with _NWS_RADAR_STATUS_CACHE_LOCK:
        if (
            _NWS_RADAR_STATUS_CACHE is not None
            and (now - _NWS_RADAR_STATUS_CACHE_TS) < _NWS_RADAR_STATUS_TTL_SEC
        ):
            return _NWS_RADAR_STATUS_CACHE

    try:
        req = _ur.Request(
            "https://api.weather.gov/radar/stations",
            headers={
                "User-Agent": "2026-Dashboard/1.0 (github.com/NCHurricane)",
                "Accept": "application/geo+json",
            },
        )
        with _ur.urlopen(req, timeout=15) as resp:
            raw = json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as exc:
        print(f"[radar status] NWS fetch failed: {exc}")
        with _NWS_RADAR_STATUS_CACHE_LOCK:
            return _NWS_RADAR_STATUS_CACHE or {}

    status_map: dict = {}
    features = raw.get("features", []) if isinstance(raw, dict) else []
    for feat in features:
        props = feat.get("properties", {}) if isinstance(feat, dict) else {}
        site_id = str(props.get("id") or "").strip().upper()
        if not site_id:
            continue
        rda = props.get("rda") or {}
        rda_props = rda.get("properties") or {}
        latency = props.get("latency") or {}
        status_map[site_id] = {
            "operabilityStatus": rda_props.get("operabilityStatus", ""),
            "status": rda_props.get("status", ""),
            "alarmSummary": rda_props.get("alarmSummary", ""),
            "volumeCoveragePattern": rda_props.get("volumeCoveragePattern", ""),
            "mode": rda_props.get("mode", ""),
            "rdaTimestamp": rda.get("timestamp", ""),
            "levelTwoLastReceived": latency.get("levelTwoLastReceivedTime", ""),
        }

    with _NWS_RADAR_STATUS_CACHE_LOCK:
        _NWS_RADAR_STATUS_CACHE = status_map
        _NWS_RADAR_STATUS_CACHE_TS = now
    return status_map


def _radar_live_site_supported(site: str) -> bool:
    try:
        from pyart.io.nexrad_common import NEXRAD_LOCATIONS

        site_id = normalize_radar_site_id(site)
        info = NEXRAD_LOCATIONS.get(site_id)
        if not info:
            return False
        return info.get("lat") is not None and info.get("lon") is not None
    except Exception:
        return False


def _radar_live_product_supported(product_key: str) -> bool:
    return str(product_key or "").strip().upper() in _radar_live_catalog()


def _radar_live_fallback_lock(site: str, product_key: str) -> threading.Lock:
    key = (normalize_radar_site_id(site), str(product_key or "").strip().upper())
    with _RADAR_LIVE_FALLBACK_LOCKS_GUARD:
        lock = _RADAR_LIVE_FALLBACK_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _RADAR_LIVE_FALLBACK_LOCKS[key] = lock
        return lock


def _radar_live_render_on_demand(
    site: str,
    product_key: str,
    *,
    latest_only: bool = True,
    backfill_history: bool = True,
    newest_first: bool = False,
    max_render_frames: int | None = None,
) -> int:
    from workers.radar_live_worker import run_radar_live_site_product

    site_id = normalize_radar_site_id(site)
    product_id = str(product_key or "").strip().upper()

    # Render a synchronous on-demand pass.
    lock = _radar_live_fallback_lock(site_id, product_id)
    with lock:
        cached = int(
            run_radar_live_site_product(
                site_id,
                product_id,
                force=True,
                latest_only=latest_only,
                newest_first=newest_first,
                max_render_frames=max_render_frames,
            )
        )

    # Optional background back-fill so the scrubber can animate.
    if not backfill_history:
        return cached

    # Avoid kicking off expensive history work when latest probe found nothing.
    if cached <= 0:
        return cached

    if not latest_only and max_render_frames is None:
        return cached

    def _fill_history():
        try:
            lock = _radar_live_fallback_lock(site_id, product_id)
            with lock:
                run_radar_live_site_product(
                    site_id,
                    product_id,
                    force=True,
                    latest_only=False,
                )
        except Exception as exc:
            print(
                f"[radar_live] history back-fill failed {site_id}/{product_id}: {exc}"
            )

    threading.Thread(
        target=_fill_history, name=f"radar-history-{site_id}-{product_id}", daemon=True
    ).start()
    return cached


def _radar_live_render_in_background(site_id: str, product_key: str) -> bool:
    """Fill the live radar frame window in the background (deduped)."""
    return spawn_live_render_thread(
        ("radar_live", site_id, product_key),
        f"radar-{site_id}-{product_key}",
        lambda: _radar_live_render_on_demand(
            site_id, product_key, latest_only=False, backfill_history=False
        ),
    )


def _radar_live_is_configured(site: str, product_key: str) -> bool:
    return site in set(_radar_live_sites()) and product_key in _radar_live_catalog()


def _radar_live_latest_meta_dt(meta: dict | None) -> datetime | None:
    """Best-effort UTC datetime of a latest-frame meta dict, or None."""
    if not meta:
        return None

    dt = None
    ts = str(meta.get("timestamp") or "").strip()
    if ts:
        try:
            dt = parse_utc_datetime(ts)
        except Exception:
            dt = None

    if dt is None:
        frame_key = str(
            meta.get("frame_key") or meta.get("source_data_key") or ""
        ).strip()
        if frame_key:
            try:
                from cache.overlay_cache_utils import datetime_from_frame_key

                dt = datetime_from_frame_key(frame_key)
            except Exception:
                dt = None

    return dt


def _radar_live_filter_stale_latest_meta(
    meta: dict | None, *, max_age_hours: float
) -> dict | None:
    """Return latest-frame meta only when it is within the live lookback window."""
    dt = _radar_live_latest_meta_dt(meta)
    if dt is None:
        return None

    cutoff_dt = datetime.now(timezone.utc) - timedelta(
        hours=max(0.25, float(max_age_hours or 0.25))
    )
    return meta if dt >= cutoff_dt else None


_RADAR_COLORTABLE_PRODUCTS: dict[str, tuple[float, float]] = {
    "BR": (-30.0, 90.0),
    "BV": (-120.0, 120.0),
}

_TROPICAL_BASINS = {"AL": "Atlantic", "EP": "Eastern Pacific", "CP": "Central Pacific"}
_TROPICAL_PRODUCTS = {
    "TCP": "Public Advisory",
    "TCM": "Forecast Advisory",
    "TCD": "Forecast Discussion",
    "PWS": "Wind Speed Probabilities",
    "TCU": "Tropical Cyclone Update",
}
_TROPICAL_CACHE_DIR = Path(BASE_DIR) / "cache" / "tropical"
_TROPICAL_STORMS_CACHE = _TROPICAL_CACHE_DIR / "current_storms.json"
_TROPICAL_SUMMARY_CACHE = _TROPICAL_CACHE_DIR / "summary.json"
_TROPICAL_CACHE_TTL_SECONDS = 2 * 60 * 60

# Archive (HURDAT2) — immutable data, so cache-forever (no TTL).
_TROPICAL_ARCHIVE_DIR = _TROPICAL_CACHE_DIR / "archive"
_TROPICAL_ARCHIVE_CATALOG = _TROPICAL_ARCHIVE_DIR / "catalog" / "seasons.json"
_TROPICAL_ARCHIVE_STORMS_DIR = _TROPICAL_ARCHIVE_DIR / "storms"


def _run_tropical_worker_once(force: bool = False) -> None:
    from workers.tropical_worker import run_tropical_worker

    run_tropical_worker(force=force)


def _run_tropical_archive_worker_once(force: bool = False) -> None:
    from workers.tropical_archive_worker import run_archive_worker

    run_archive_worker(force=force)


def _read_tropical_archive_cache(path: Path) -> dict[str, Any] | None:
    """Read an archive cache file ignoring age — archive data never goes stale."""
    try:
        if not path.is_file():
            return None
        with path.open("r", encoding="utf-8") as fp:
            payload = json.load(fp)
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def _read_tropical_cache(path: Path, max_age_seconds: int) -> dict[str, Any] | None:
    try:
        if not path.is_file():
            return None
        age = _time.time() - path.stat().st_mtime
        if age > max_age_seconds:
            return None
        with path.open("r", encoding="utf-8") as fp:
            payload = json.load(fp)
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def _write_tropical_cache(path: Path, payload: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as fp:
            json.dump(payload, fp, ensure_ascii=False)
        tmp.replace(path)
    except Exception as exc:
        print(f"[tropical] Cache write failed for {path}: {exc}")


def _fetch_json_url(url: str, timeout_seconds: int = 12) -> dict[str, Any]:
    import urllib.request as ur

    req = ur.Request(
        url,
        headers={
            "User-Agent": "NCHurricane Dashboard/2026 (+https://nchurricane.com)",
            "Accept": "application/json,text/xml;q=0.9,*/*;q=0.8",
        },
    )
    with ur.urlopen(req, timeout=timeout_seconds) as resp:
        raw = resp.read()
    decoded = json.loads(raw.decode("utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError("JSON payload was not an object")
    return decoded


def _fetch_text_url(url: str, timeout_seconds: int = 12) -> str:
    import urllib.request as ur

    req = ur.Request(
        url,
        headers={
            "User-Agent": "NCHurricane Dashboard/2026 (+https://nchurricane.com)",
            "Accept": "application/xml,text/xml,text/plain;q=0.9,*/*;q=0.8",
        },
    )
    with ur.urlopen(req, timeout=timeout_seconds) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _normalize_tropical_storms(payload: dict[str, Any]) -> list[dict[str, Any]]:
    active = payload.get("activeStorms")
    if not isinstance(active, list):
        active = payload.get("data", {}).get("activeStorms") if isinstance(payload.get("data"), dict) else []
    storms = []
    for storm in active if isinstance(active, list) else []:
        if not isinstance(storm, dict):
            continue
        storm_id = str(storm.get("id") or storm.get("stormId") or storm.get("atcfID") or "").upper()
        if len(storm_id) < 8:
            continue
        basin = storm_id[:2]
        if basin not in _TROPICAL_BASINS:
            continue
        merged = dict(storm)
        merged["id"] = storm_id
        merged["basin"] = basin
        merged["basinName"] = _TROPICAL_BASINS[basin]
        storms.append(merged)
    return storms


def _tropical_wallet(storm_id: str) -> int:
    return ((int(storm_id[2:4]) - 1) % 5) + 1


def _tropical_xml_basin_code(storm_id: str) -> str:
    basin = storm_id[:2]
    if basin == "AL":
        return "AT"
    return basin


def _extract_xml_item_text(xml_text: str) -> tuple[str, dict[str, str]]:
    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return xml_text, {}

    item = root.find("./channel/item")
    channel = root.find("./channel")
    meta: dict[str, str] = {}
    if channel is not None:
        for key in ("title", "pubDate", "lastBuildDate"):
            val = channel.findtext(key)
            if val:
                meta[key] = val
    if item is not None:
        for key in ("title", "pubDate", "link", "guid"):
            val = item.findtext(key)
            if val:
                meta[key] = val
        desc = item.findtext("description") or ""
        return desc.strip(), meta
    return xml_text, meta


def _parse_tropical_coord(text: str, hemi: str) -> float | None:
    try:
        value = float(text)
    except (TypeError, ValueError):
        return None
    return -value if hemi.upper() in {"S", "W"} else value


def _parse_tropical_advisory(text: str) -> dict[str, Any]:
    import re

    parsed: dict[str, Any] = {}
    summary = re.search(r"SUMMARY OF .*?INFORMATION\s*-+\s*(.*?)(?:\n\s*\n|WATCHES AND WARNINGS|DISCUSSION AND OUTLOOK)", text, re.I | re.S)
    block = summary.group(1) if summary else text

    loc = re.search(r"LOCATION\.*\s*([0-9.]+)([NS])\s+([0-9.]+)([EW])", block, re.I)
    if loc:
        parsed["location"] = {
            "lat": _parse_tropical_coord(loc.group(1), loc.group(2)),
            "lon": _parse_tropical_coord(loc.group(3), loc.group(4)),
            "latText": f"{loc.group(1)}{loc.group(2).upper()}",
            "lonText": f"{loc.group(3)}{loc.group(4).upper()}",
        }
    wind = re.search(r"MAXIMUM SUSTAINED WINDS\.*\s*([0-9]+)\s*MPH.*?([0-9]+)\s*KM/H", block, re.I)
    if wind:
        parsed["maxWindMph"] = int(wind.group(1))
        parsed["maxWindKph"] = int(wind.group(2))
    motion = re.search(r"PRESENT MOVEMENT\.*\s*(.*?)\s+AT\s+([0-9]+)\s*MPH.*?([0-9]+)\s*KM/H", block, re.I)
    if motion:
        parsed["motion"] = {
            "text": motion.group(1).strip(),
            "mph": int(motion.group(2)),
            "kph": int(motion.group(3)),
        }
    pressure = re.search(r"MINIMUM CENTRAL PRESSURE\.*\s*([0-9]+)\s*MB", block, re.I)
    if pressure:
        parsed["pressureMb"] = int(pressure.group(1))
    headline = re.findall(r"\.\.\.(.*?)\.\.\.", text)
    if headline:
        parsed["headline"] = " ".join(part.strip() for part in headline[:2] if part.strip())
    return parsed


def _parse_tropical_track(text: str) -> list[dict[str, Any]]:
    import re

    points: list[dict[str, Any]] = []
    for line in text.splitlines():
        match = re.search(
            r"^(INIT|[0-9]{1,3}H)\s+([0-9]{2}/[0-9]{4}Z)\s+([0-9.]+)([NS])\s+([0-9.]+)([EW])\s+([0-9]+)\s+KT",
            line.strip(),
            re.I,
        )
        if not match:
            continue
        points.append(
            {
                "hour": match.group(1).upper(),
                "time": match.group(2),
                "lat": _parse_tropical_coord(match.group(3), match.group(4)),
                "lon": _parse_tropical_coord(match.group(5), match.group(6)),
                "windKt": int(match.group(7)),
            }
        )
    return [p for p in points if p["lat"] is not None and p["lon"] is not None]


def _tropical_product_url(storm_id: str, product: str) -> str:
    basin_code = _tropical_xml_basin_code(storm_id)
    wallet = _tropical_wallet(storm_id)
    return f"https://www.nhc.noaa.gov/xml/{product}{basin_code}{wallet}.xml"


def _fetch_tropical_products(storm_id: str) -> dict[str, Any]:
    products: dict[str, Any] = {}
    for code, label in _TROPICAL_PRODUCTS.items():
        url = _tropical_product_url(storm_id, code)
        try:
            xml_text = _fetch_text_url(url)
            content, meta = _extract_xml_item_text(xml_text)
            if not content:
                continue
            products[code] = {
                "code": code,
                "label": label,
                "url": url,
                "meta": meta,
                "text": content,
            }
        except Exception as exc:
            products[code] = {
                "code": code,
                "label": label,
                "url": url,
                "error": str(exc),
            }
    return products


@app.get("/api/tropical/storms")
def get_tropical_storms(basin: str = "WORLD", force: bool = False):
    """Return cached current NHC active storms for Atlantic, East Pac, and Central Pac."""
    basin_key = basin.strip().upper()
    if basin_key == "EASTERN_PACIFIC":
        basin_key = "EP"
    if basin_key == "CENTRAL_PACIFIC":
        basin_key = "CP"
    if basin_key == "ATLANTIC":
        basin_key = "AL"
    if basin_key not in {"WORLD", "AL", "EP", "CP"}:
        raise HTTPException(status_code=400, detail="Invalid tropical basin.")

    summary = None if force else _read_tropical_cache(
        _TROPICAL_SUMMARY_CACHE, _TROPICAL_CACHE_TTL_SECONDS
    )
    source = "worker-cache"
    if summary is None:
        try:
            _run_tropical_worker_once(force=force)
        except Exception as exc:
            fallback = _read_tropical_cache(_TROPICAL_SUMMARY_CACHE, 7 * 24 * 60 * 60)
            if fallback is None:
                raise HTTPException(
                    status_code=502,
                    detail=f"Tropical cache refresh failed: {exc}",
                )
            summary = fallback
            source = "stale-worker-cache"
        else:
            summary = _read_tropical_cache(
                _TROPICAL_SUMMARY_CACHE, 7 * 24 * 60 * 60
            )
            source = "worker-cache-refresh"

    if summary is None:
        raise HTTPException(status_code=503, detail="Tropical cache is not available.")

    storms = summary.get("storms") if isinstance(summary.get("storms"), list) else []
    if basin_key != "WORLD":
        storms = [storm for storm in storms if storm.get("basin") == basin_key]
    return {
        "status": "success",
        "source": source,
        "basin": basin_key,
        "updated": summary.get("updated"),
        "interval_minutes": summary.get("interval_minutes"),
        "storms": storms,
        "count": len(storms),
        "errors": summary.get("errors", []),
    }


@app.get("/api/tropical/summary")
def get_tropical_summary(force: bool = False):
    """Return the cached tropical worker summary."""
    summary = None if force else _read_tropical_cache(
        _TROPICAL_SUMMARY_CACHE, _TROPICAL_CACHE_TTL_SECONDS
    )
    if summary is None:
        try:
            _run_tropical_worker_once(force=force)
        except Exception as exc:
            fallback = _read_tropical_cache(_TROPICAL_SUMMARY_CACHE, 7 * 24 * 60 * 60)
            if fallback is None:
                raise HTTPException(
                    status_code=502,
                    detail=f"Tropical cache refresh failed: {exc}",
                )
            return fallback
        summary = _read_tropical_cache(_TROPICAL_SUMMARY_CACHE, 7 * 24 * 60 * 60)
    if summary is None:
        raise HTTPException(status_code=503, detail="Tropical cache is not available.")
    return summary


@app.get("/api/tropical/basin/{basin_id}/feeds")
def get_tropical_basin_feeds(basin_id: str):
    """Return cached normalized RSS/GIS feed data for one tropical basin."""
    basin_key = basin_id.strip().upper()
    if basin_key == "ATLANTIC":
        basin_key = "AL"
    elif basin_key == "EASTERN_PACIFIC":
        basin_key = "EP"
    elif basin_key == "CENTRAL_PACIFIC":
        basin_key = "CP"
    if basin_key not in _TROPICAL_BASINS:
        raise HTTPException(status_code=400, detail="Invalid tropical basin.")

    basin_dir = _TROPICAL_CACHE_DIR / "basins" / basin_key
    index_payload = _read_tropical_cache(basin_dir / "index.json", _TROPICAL_CACHE_TTL_SECONDS)
    gis_payload = _read_tropical_cache(basin_dir / "gis.json", _TROPICAL_CACHE_TTL_SECONDS)
    assets_payload = _read_tropical_cache(basin_dir / "assets.json", _TROPICAL_CACHE_TTL_SECONDS)
    gtwo_payload = _read_tropical_cache(basin_dir / "gtwo.json", _TROPICAL_CACHE_TTL_SECONDS)
    if index_payload is None or gis_payload is None or assets_payload is None:
        try:
            _run_tropical_worker_once(force=False)
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Tropical basin feed refresh failed: {exc}",
            )
        index_payload = _read_tropical_cache(basin_dir / "index.json", 7 * 24 * 60 * 60)
        gis_payload = _read_tropical_cache(basin_dir / "gis.json", 7 * 24 * 60 * 60)
        assets_payload = _read_tropical_cache(basin_dir / "assets.json", 7 * 24 * 60 * 60)
        gtwo_payload = _read_tropical_cache(basin_dir / "gtwo.json", 7 * 24 * 60 * 60)

    if index_payload is None or gis_payload is None or assets_payload is None:
        raise HTTPException(status_code=404, detail=f"No cached tropical feeds for {basin_key}.")
    return {
        "status": "success",
        "basin": basin_key,
        "index": index_payload,
        "gis": gis_payload,
        "assets": assets_payload,
        "gtwo": gtwo_payload,
    }


@app.get("/api/tropical/storm/{storm_id}")
def get_tropical_storm(storm_id: str):
    """Return cached NHC text products and parsed advisory/track details for one storm."""
    import re

    sid = storm_id.strip().upper()
    if not re.fullmatch(r"(AL|EP|CP)[0-9]{2}[0-9]{4}", sid):
        raise HTTPException(status_code=400, detail="Invalid tropical storm id.")

    storm_cache = _TROPICAL_CACHE_DIR / "storms" / sid / "storm.json"
    payload = _read_tropical_cache(storm_cache, _TROPICAL_CACHE_TTL_SECONDS)
    if payload is None:
        try:
            _run_tropical_worker_once(force=False)
        except Exception as exc:
            fallback = _read_tropical_cache(storm_cache, 7 * 24 * 60 * 60)
            if fallback is None:
                raise HTTPException(
                    status_code=502,
                    detail=f"Tropical storm cache refresh failed: {exc}",
                )
            payload = fallback
        else:
            payload = _read_tropical_cache(storm_cache, 7 * 24 * 60 * 60)

    if payload is None:
        raise HTTPException(status_code=404, detail=f"No cached tropical storm: {sid}")
    return payload


@app.get("/api/tropical/archive/catalog")
def get_tropical_archive_catalog():
    """Return the HURDAT2 season catalog, lazily building it on first request."""
    payload = _read_tropical_archive_cache(_TROPICAL_ARCHIVE_CATALOG)
    if payload is None:
        try:
            _run_tropical_archive_worker_once(force=False)
        except Exception as exc:
            raise HTTPException(
                status_code=502, detail=f"Tropical archive build failed: {exc}"
            )
        payload = _read_tropical_archive_cache(_TROPICAL_ARCHIVE_CATALOG)
    if payload is None:
        raise HTTPException(status_code=404, detail="Tropical archive catalog unavailable.")
    return payload


@app.get("/api/tropical/archive/storm/{atcf_id}")
def get_tropical_archive_storm(atcf_id: str):
    """Return one archived storm's best-track payload (build-on-demand, cache-forever)."""
    import re

    sid = atcf_id.strip().upper()
    if not re.fullmatch(r"(AL|EP|CP)[0-9]{2}[0-9]{4}", sid):
        raise HTTPException(status_code=400, detail="Invalid archive storm id.")

    storm_cache = _TROPICAL_ARCHIVE_STORMS_DIR / sid / "storm.json"
    payload = _read_tropical_archive_cache(storm_cache)
    if payload is None:
        try:
            _run_tropical_archive_worker_once(force=False)
        except Exception as exc:
            raise HTTPException(
                status_code=502, detail=f"Tropical archive build failed: {exc}"
            )
        payload = _read_tropical_archive_cache(storm_cache)
    if payload is None:
        raise HTTPException(status_code=404, detail=f"No archived storm: {sid}")

    # Phase B: lazily attach archived forecast GIS (cone/radii/WW from the peak
    # advisory) on first open. Best-effort — never fail the request over it.
    # Also re-enrich storms cached before the advisory index existed (no
    # "advisories" key) so the scrubber/mode-toggle gets its data.
    if not payload.get("gis_enriched") or "advisories" not in payload:
        try:
            from workers.tropical_archive_worker import enrich_storm_gis

            if enrich_storm_gis(sid):
                fresh = _read_tropical_archive_cache(storm_cache)
                if fresh is not None:
                    payload = fresh
        except Exception as exc:
            print(f"[tropical-archive] GIS enrichment failed for {sid}: {exc}")
    return payload


@app.get("/api/tropical/archive/storm/{atcf_id}/advisory/{step}")
def get_tropical_archive_advisory(atcf_id: str, step: str):
    """Return one archived advisory's payload (summary + products + GIS), cached forever."""
    import re

    sid = atcf_id.strip().upper()
    stp = step.strip().upper()
    if not re.fullmatch(r"(AL|EP|CP)[0-9]{2}[0-9]{4}", sid):
        raise HTTPException(status_code=400, detail="Invalid archive storm id.")
    if not re.fullmatch(r"[0-9]{1,3}[A-Z]?", stp):
        raise HTTPException(status_code=400, detail="Invalid advisory step.")

    try:
        from workers.tropical_archive_worker import get_advisory_payload

        payload = get_advisory_payload(sid, stp)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Advisory build failed: {exc}")
    if payload is None:
        raise HTTPException(status_code=404, detail=f"No archived advisory: {sid} #{stp}")
    return payload


@app.get("/api/radar/colortable")
def get_radar_colortable(product: str = "BR"):
    """Return the legend color entries for a radar product colortable."""
    product = product.upper()
    if product not in _RADAR_COLORTABLE_PRODUCTS:
        raise HTTPException(
            status_code=404,
            detail=f"No colortable for product '{product}'. Valid: {list(_RADAR_COLORTABLE_PRODUCTS)}",
        )
    vmin, vmax = _RADAR_COLORTABLE_PRODUCTS[product]
    try:
        from config.radar_colortable_utils import get_legend_json

        entries = get_legend_json(product, vmin, vmax)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"product": product, "vmin": vmin, "vmax": vmax, "entries": entries}


_RADAR_FRAME_LAYERS = {
    0: "nexrad-n0q-m20m",
    1: "nexrad-n0q-m15m",
    2: "nexrad-n0q-m10m",
    3: "nexrad-n0q-m05m",
    4: "nexrad-n0q",
}


@app.get("/api/radar/tiles/{z}/{x}/{y}")
def get_radar_alert_tiles(z: str, x: str, y: str, frame: int = 4):
    """Proxy IEM NEXRAD reflectivity tiles. frame 0=oldest (-20m), 4=current."""
    try:
        import urllib.request as ur
        layer = _RADAR_FRAME_LAYERS.get(frame, "nexrad-n0q")
        url = f"https://mesonet.agron.iastate.edu/cache/tile.py/1.0.0/{layer}/{z}/{x}/{y}.png"
        req = ur.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with ur.urlopen(req, timeout=10) as resp:
            data = resp.read()
            # Tile URLs carry a v={last-modified token} that changes whenever
            # IEM publishes new data, so for a given URL the content is fixed:
            # let the browser cache it hard instead of re-fetching every 120s.
            return Response(
                content=data,
                media_type="image/png",
                headers={"Cache-Control": "public, max-age=3600, immutable"},
            )
    except Exception as e:
        print(f"[radar tiles] Tile fetch error: {e}")
        raise HTTPException(status_code=404, detail="Tile not found")


@app.head("/api/radar/tiles/{z}/{x}/{y}")
def head_radar_alert_tiles(z: str, x: str, y: str):
    """HEAD request for IEM NEXRAD radar tiles."""
    return Response(media_type="image/png")


@app.get("/api/radar/tiles/freshness")
def get_radar_tiles_freshness():
    """Return Last-Modified header for current IEM nexrad-n0q tile (CONUS sample)."""
    try:
        import urllib.request as ur
        url = "https://mesonet.agron.iastate.edu/cache/tile.py/1.0.0/nexrad-n0q/4/4/6.png"
        req = ur.Request(url, headers={"User-Agent": "Mozilla/5.0"}, method="HEAD")
        with ur.urlopen(req, timeout=8) as resp:
            return {"last_modified": resp.headers.get("Last-Modified", "")}
    except Exception as e:
        print(f"[radar tiles] Freshness check error: {e}")
        return {"last_modified": ""}


@app.get("/api/radar/status")
def get_radar_status():
    """Return NWS radar station operational status for all sites, cached 5 minutes."""
    try:
        status = _fetch_nws_radar_status()
        return {
            "status": "success",
            "stations": status,
            "count": len(status),
        }
    except Exception as exc:
        print(f"[radar status] Endpoint error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/radar/live/sites")
def get_radar_live_sites():
    """Return radar sites with configured live-cache flag for weather.html Radar tab."""
    try:
        configured = set(_radar_live_sites())
        from pyart.io.nexrad_common import NEXRAD_LOCATIONS

        valid_prefixes = ("K", "P")
        valid_extras = {"TJUA"}

        sites = []
        seen = set()
        for site_id, info in NEXRAD_LOCATIONS.items():
            if not (site_id.startswith(valid_prefixes) or site_id in valid_extras):
                continue
            normalized_id = normalize_radar_site_id(site_id)
            if normalized_id in seen:
                continue
            lat = info.get("lat")
            lon = info.get("lon")
            if lat is None or lon is None:
                continue
            seen.add(normalized_id)
            sites.append(
                {
                    "site": normalized_id,
                    "lat": float(lat),
                    "lon": float(lon),
                    "configured": normalized_id in configured,
                }
            )

        sites.sort(key=lambda entry: (0 if entry["configured"] else 1, entry["site"]))
        return {
            "status": "success",
            "sites": sites,
            "configured_sites": sorted(configured),
            "products": _radar_live_catalog(),
            "count": len(sites),
        }
    except Exception as e:
        print(f"Radar live sites endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/radar/live/latest")
def get_radar_live_latest(
    site: str = "KMHX", product: str = "L3_N0B", force: bool = False
):
    """Return latest live radar frame from cache."""
    from cache.overlay_cache_utils import radar_read_latest_frame
    from config.radar_config import (
        LIVE_RADAR_LOOKBACK_HOURS,
        LIVE_RADAR_WORKER_INTERVAL_MIN,
    )

    site_id = normalize_radar_site_id(site)
    product_key = str(product or "L3_N0B").strip().upper()
    configured = _radar_live_is_configured(site_id, product_key)
    level_code = "L2" if product_key.startswith("L2_") else "L3"
    freshness_hours = max(0.25, float(LIVE_RADAR_LOOKBACK_HOURS or 3.0))

    if not _radar_live_product_supported(product_key):
        raise HTTPException(
            status_code=404,
            detail=f"Live radar product is not supported: {product_key}.",
        )
    if not _radar_live_site_supported(site_id):
        raise HTTPException(
            status_code=404,
            detail=f"Live radar site is not supported: {site_id}.",
        )

    meta = _radar_live_filter_stale_latest_meta(
        radar_read_latest_frame(_CACHE_ROOT, site_id, level_code, product_key),
        max_age_hours=freshness_hours,
    )
    fallback_cached = 0
    if force and meta:
        # The frontend sends force=1 on every poll for unconfigured sites. A
        # cached frame newer than the worker cadence means a forced re-render
        # cannot produce anything newer — skip the synchronous probe + render.
        meta_dt = _radar_live_latest_meta_dt(meta)
        recent_cutoff = datetime.now(timezone.utc) - timedelta(
            minutes=float(LIVE_RADAR_WORKER_INTERVAL_MIN or 5) + 1.0
        )
        if meta_dt is not None and meta_dt >= recent_cutoff:
            force = False
    if force:
        try:
            fallback_cached = _radar_live_render_on_demand(
                site_id,
                product_key,
                latest_only=True,
                backfill_history=True,
            )
        except Exception as exc:
            print(
                f"[radar_live_fallback] forced latest {site_id}/{product_key} failed: "
                f"{type(exc).__name__}: {exc}"
            )
        meta = _radar_live_filter_stale_latest_meta(
            radar_read_latest_frame(_CACHE_ROOT, site_id, level_code, product_key),
            max_age_hours=freshness_hours,
        )

    if not meta:
        try:
            fallback_cached = _radar_live_render_on_demand(
                site_id,
                product_key,
                latest_only=True,
                backfill_history=True,
            )
        except Exception as exc:
            print(
                f"[radar_live_fallback] latest {site_id}/{product_key} failed: "
                f"{type(exc).__name__}: {exc}"
            )
        meta = _radar_live_filter_stale_latest_meta(
            radar_read_latest_frame(_CACHE_ROOT, site_id, level_code, product_key),
            max_age_hours=freshness_hours,
        )

    # Cold-start edge case: latest-only probe may miss while broader frame render succeeds.
    # Render the newest frame first so Current can paint immediately, then
    # continue full history in the background for scrubber readiness.
    if not meta:
        try:
            fallback_cached = max(
                fallback_cached,
                _radar_live_render_on_demand(
                    site_id,
                    product_key,
                    latest_only=False,
                    backfill_history=True,
                    newest_first=True,
                    max_render_frames=1,
                ),
            )
        except Exception as exc:
            print(
                f"[radar_live_fallback] full latest {site_id}/{product_key} failed: "
                f"{type(exc).__name__}: {exc}"
            )
        meta = _radar_live_filter_stale_latest_meta(
            radar_read_latest_frame(_CACHE_ROOT, site_id, level_code, product_key),
            max_age_hours=freshness_hours,
        )
    if not meta:
        raise HTTPException(
            status_code=404,
            detail="No live radar frame cached yet within lookback window.",
        )

    image_url = (meta.get("render") or {}).get("image_url")
    if not image_url:
        raise HTTPException(
            status_code=404, detail="Latest live radar image is missing."
        )

    return {
        "status": "success",
        "source": (
            "live_cache_forced"
            if force and fallback_cached > 0
            else "live_cache_fallback"
            if fallback_cached > 0
            else "live_cache"
        ),
        "history_filling": fallback_cached > 0,
        "configured": configured,
        "site": site_id,
        "product": product_key,
        "timestamp": meta.get("timestamp"),
        "source_data_key": meta.get("source_data_key", ""),
        "image_url": image_url,
        "bounds": meta.get("bounds"),
        "full_name": meta.get("full_name", product_key),
        "units": meta.get("units", ""),
    }


@app.get("/api/radar/live/frames")
def get_radar_live_frames(site: str = "KMHX", product: str = "L3_N0B", hours: int = 2):
    """Return live radar frames list for scrubber playback."""
    from cache.overlay_cache_utils import radar_list_frames

    site_id = normalize_radar_site_id(site)
    product_key = str(product or "L3_N0B").strip().upper()
    configured = _radar_live_is_configured(site_id, product_key)
    level_code = "L2" if product_key.startswith("L2_") else "L3"

    if not _radar_live_product_supported(product_key):
        raise HTTPException(
            status_code=404,
            detail=f"Live radar product is not supported: {product_key}.",
        )
    if not _radar_live_site_supported(site_id):
        raise HTTPException(
            status_code=404,
            detail=f"Live radar site is not supported: {site_id}.",
        )

    from config.cache_config import (
        OVERLAY_EMPTY_CACHE_SYNC_FRAMES,
        OVERLAY_STALE_SERVE_WINDOW_MIN,
    )

    def _within(frame_list, cutoff):
        out = []
        for frame in frame_list:
            ts = frame.get("timestamp")
            if ts:
                try:
                    dt = parse_utc_datetime(ts)
                except Exception:
                    dt = None
            else:
                dt = None
            if dt and dt < cutoff:
                continue
            out.append(frame)
        return out

    def _render_newest_sync():
        # Render just the newest frames synchronously so the first paint is
        # not blank; the rest of the window fills in the background.
        try:
            return _radar_live_render_on_demand(
                site_id,
                product_key,
                latest_only=False,
                backfill_history=False,
                newest_first=True,
                max_render_frames=OVERLAY_EMPTY_CACHE_SYNC_FRAMES,
            )
        except Exception as exc:
            print(
                f"[radar_live_fallback] frames {site_id}/{product_key} failed: "
                f"{type(exc).__name__}: {exc}"
            )
            return 0

    cutoff_dt = datetime.now(timezone.utc) - timedelta(hours=max(1, int(hours or 2)))
    frames = radar_list_frames(_CACHE_ROOT, site_id, level_code, product_key)
    fallback_cached = 0
    refreshing = False

    if not frames:
        fallback_cached = _render_newest_sync()
        frames = radar_list_frames(_CACHE_ROOT, site_id, level_code, product_key)
        if frames:
            refreshing = _radar_live_render_in_background(site_id, product_key)

    filtered = _within(frames, cutoff_dt) if frames else []

    if not filtered and frames:
        # Cache holds only stale frames (typical after a server restart):
        # serve any within the grace window immediately as scrubber fill-ins
        # and refresh in the background, instead of blocking this request on
        # a full-window synchronous render.
        grace_min = OVERLAY_STALE_SERVE_WINDOW_MIN.get("radar_live", 15)
        filtered = _within(frames, cutoff_dt - timedelta(minutes=grace_min))
        if filtered:
            refreshing = _radar_live_render_in_background(site_id, product_key)
        else:
            fallback_cached = max(fallback_cached, _render_newest_sync())
            frames = radar_list_frames(_CACHE_ROOT, site_id, level_code, product_key)
            filtered = _within(frames, cutoff_dt)
            if filtered:
                refreshing = _radar_live_render_in_background(site_id, product_key)

    return {
        "status": "success",
        "source": "live_cache_fallback" if fallback_cached > 0 else "live_cache",
        "configured": configured,
        "site": site_id,
        "product": product_key,
        "frame_count": len(filtered),
        "refreshing": refreshing,
        "frames": filtered,
    }

if __name__ == "__main__":
    # On Windows, Uvicorn's reload subprocess can intermittently emit
    # multiprocessing named-pipe errors during startup. Keep reload opt-in.
    use_reload = os.environ.get("WX_DASHBOARD_RELOAD", "0").strip() in {
        "1",
        "true",
        "yes",
        "on",
    }
    # Pass reload-related options ONLY when reload is enabled — otherwise
    # uvicorn warns "Current configuration will not reload as not all
    # conditions are met" because reload_includes/excludes are ignored.
    run_kwargs = {
        "host": "0.0.0.0",
        "port": 8000,
        "reload": use_reload,
        "timeout_graceful_shutdown": 5,
    }
    if use_reload:
        run_kwargs["reload_includes"] = ["*.py"]
        run_kwargs["reload_excludes"] = [
            "radar/*",
            "satellite/*",
            "surface/*",
            "alerts/*",
            "__pycache__/*",
        ]
    uvicorn.run("main:app", **run_kwargs)
