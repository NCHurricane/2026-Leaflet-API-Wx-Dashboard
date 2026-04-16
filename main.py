import os
import time as _time
import uvicorn
import glob
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import json
from datetime import datetime, timezone, timedelta
from dateutil import tz

# --- IMPORT YOUR UTILITIES ---
from surface import surface_utils
from alerts import alerts_utils
from radar import radar_utils as radar_thredds_utils
from satellite import satellite_utils as satellite_thredds_utils
from mrms import mrms_utils
from mrms import mrms_nodd_utils
from spc import spc_utils
from font_utils import resolve_logo_path

USING_NODD = False
try:
    from radar import radar_nodd_utils as radar_utils
    from satellite import satellite_nodd_utils as satellite_utils

    USING_NODD = True
    print("[OK] Using NODD modules for radar and satellite")
except Exception as import_error:
    radar_utils = radar_thredds_utils
    satellite_utils = satellite_thredds_utils
    print(
        f"[WARN] NODD modules unavailable, using THREDDS fallback: {import_error}")

# Archive radar module (standalone, always available when NODD is)
try:
    from radar import radar_archive_utils

    print("[OK] Radar archive module loaded")
except Exception as archive_err:
    radar_archive_utils = None
    print(f"[WARN] Radar archive module unavailable: {archive_err}")

# Archive satellite module (standalone, uses NODD sources)
try:
    from satellite import satellite_archive_utils

    print("[OK] Satellite archive module loaded")
except Exception as sat_archive_err:
    satellite_archive_utils = None
    print(f"[WARN] Satellite archive module unavailable: {sat_archive_err}")

# Unified weather module
try:
    from weather import weather_utils
    print("[OK] Unified weather module loaded")
except Exception as weather_err:
    weather_utils = None
    print(f"[WARN] Unified weather module unavailable: {weather_err}")

# Background workers (APScheduler)
try:
    from workers.scheduler import start_scheduler, stop_scheduler
    _SCHEDULER_AVAILABLE = True
except Exception as sched_err:
    _SCHEDULER_AVAILABLE = False
    print(f"[WARN] Background workers unavailable: {sched_err}")

# --- GLOBAL TASK STORE ---
active_tasks = {}

# --- CONFIGURATION ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGO_PATH = os.path.join(BASE_DIR, "img", "nchurricane_logo.png")

DIRS = {
    "surface": os.path.join(BASE_DIR, "surface", "surface_images"),
    "surface_archive": os.path.join(
        BASE_DIR, "surface", "surface_archive", "surface_images"
    ),
    "alerts": os.path.join(BASE_DIR, "alerts", "alert_images"),
    "alerts_archive": os.path.join(
        BASE_DIR, "alerts", "alerts_archive", "alert_images"
    ),
    "radar": os.path.join(BASE_DIR, "radar"),
    "satellite": os.path.join(BASE_DIR, "satellite", "satellite_images"),
    "satellite_archive": os.path.join(
        BASE_DIR, "satellite", "satellite_archive", "satellite_images"
    ),
    "mrms": os.path.join(BASE_DIR, "mrms", "mrms_images"),
    "spc": os.path.join(BASE_DIR, "spc", "spc_images"),
    "spc_archive": os.path.join(BASE_DIR, "spc", "spc_archive", "spc_images"),
}

os.makedirs(DIRS["surface"], exist_ok=True)
os.makedirs(DIRS["surface_archive"], exist_ok=True)
os.makedirs(DIRS["alerts"], exist_ok=True)
os.makedirs(DIRS["alerts_archive"], exist_ok=True)
os.makedirs(DIRS["mrms"], exist_ok=True)
os.makedirs(DIRS["spc"], exist_ok=True)
os.makedirs(DIRS["spc_archive"], exist_ok=True)

# Weather unified workflow directories
if weather_utils:
    DIRS["weather"] = weather_utils.WEATHER_IMAGES
    DIRS["weather_archive"] = weather_utils.WEATHER_ARCHIVE
    DIRS["weather_archive_layers"] = weather_utils.WEATHER_ARCHIVE_LAYERS
    for _wd in [DIRS["weather"], DIRS["weather_archive"], DIRS["weather_archive_layers"]]:
        os.makedirs(_wd, exist_ok=True)

app = FastAPI(title="NCHurricane Weather API")


@app.on_event("startup")
def _warm_radar_render_assets():
    """Warm radar Cartopy assets at startup to reduce first-render latency."""
    try:
        if hasattr(radar_thredds_utils, "warm_radar_cartopy_cache"):
            radar_thredds_utils.warm_radar_cartopy_cache()
    except Exception as e:
        print(f"[WARN] Radar warmup skipped: {e}")

    try:
        if radar_archive_utils and hasattr(
            radar_archive_utils, "warm_radar_cartopy_cache"
        ):
            radar_archive_utils.warm_radar_cartopy_cache()
    except Exception as e:
        print(f"[WARN] Radar archive warmup skipped: {e}")


@app.on_event("startup")
def _start_background_workers():
    """Start APScheduler background workers for alerts and SPC pre-caching."""
    if _SCHEDULER_AVAILABLE:
        try:
            start_scheduler()
        except Exception as e:
            print(f"[WARN] Background worker startup failed: {e}")


@app.on_event("shutdown")
def _stop_background_workers():
    """Shut down the APScheduler scheduler on app exit."""
    if _SCHEDULER_AVAILABLE:
        try:
            stop_scheduler()
        except Exception:
            pass


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/img/surface",
          StaticFiles(directory=DIRS["surface"]), name="surface_images")
app.mount(
    "/img/surface_archive",
    StaticFiles(directory=DIRS["surface_archive"]),
    name="surface_archive_images",
)
app.mount("/img/alerts",
          StaticFiles(directory=DIRS["alerts"]), name="alert_images")
app.mount(
    "/img/alerts_archive",
    StaticFiles(directory=DIRS["alerts_archive"]),
    name="alert_archive_images",
)
# Recent radar image mounts
os.makedirs(os.path.join(DIRS["radar"], "radar_level2_images"), exist_ok=True)
os.makedirs(os.path.join(DIRS["radar"], "radar_level3_images"), exist_ok=True)
app.mount(
    "/img/radar_level2_images",
    StaticFiles(directory=os.path.join(DIRS["radar"], "radar_level2_images")),
    name="radar_level2_images",
)
app.mount(
    "/img/radar_level3_images",
    StaticFiles(directory=os.path.join(DIRS["radar"], "radar_level3_images")),
    name="radar_level3_images",
)
# Archive radar image mounts
os.makedirs(
    os.path.join(DIRS["radar"], "radar_archive", "radar_level2_images"), exist_ok=True
)
os.makedirs(
    os.path.join(DIRS["radar"], "radar_archive", "radar_level3_images"), exist_ok=True
)
app.mount(
    "/img/radar_archive/radar_level2_images",
    StaticFiles(
        directory=os.path.join(
            DIRS["radar"], "radar_archive", "radar_level2_images")
    ),
    name="radar_archive_level2_images",
)
app.mount(
    "/img/radar_archive/radar_level3_images",
    StaticFiles(
        directory=os.path.join(
            DIRS["radar"], "radar_archive", "radar_level3_images")
    ),
    name="radar_archive_level3_images",
)
app.mount("/img/satellite",
          StaticFiles(directory=DIRS["satellite"]), name="sat_images")
os.makedirs(DIRS["satellite_archive"], exist_ok=True)
app.mount(
    "/img/satellite_archive",
    StaticFiles(directory=DIRS["satellite_archive"]),
    name="sat_archive_images",
)
app.mount("/img/mrms", StaticFiles(directory=DIRS["mrms"]), name="mrms_images")
app.mount("/img/spc", StaticFiles(directory=DIRS["spc"]), name="spc_images")
app.mount(
    "/img/spc_archive",
    StaticFiles(directory=DIRS["spc_archive"]),
    name="spc_archive_images",
)
# Weather unified static mounts
if weather_utils:
    app.mount(
        "/img/weather",
        StaticFiles(directory=DIRS["weather"]),
        name="weather_images",
    )
    app.mount(
        "/img/weather_archive",
        StaticFiles(directory=DIRS["weather_archive"]),
        name="weather_archive_images",
    )
    app.mount(
        "/img/weather_archive_layers",
        StaticFiles(directory=DIRS["weather_archive_layers"]),
        name="weather_archive_layers",
    )

app.mount(
    "/img/basemap_cache",
    StaticFiles(directory=os.path.join(BASE_DIR, "basemap_cache")),
    name="basemap_cache",
)

# Cache directory — worker-written GeoJSON artifacts (gitignored)
_CACHE_ROOT = os.path.join(BASE_DIR, "cache")
os.makedirs(os.path.join(_CACHE_ROOT, "alerts"), exist_ok=True)
os.makedirs(os.path.join(_CACHE_ROOT, "spc"), exist_ok=True)
os.makedirs(os.path.join(_CACHE_ROOT, "surface"), exist_ok=True)
os.makedirs(os.path.join(_CACHE_ROOT, "mrms"), exist_ok=True)
app.mount("/cache", StaticFiles(directory=_CACHE_ROOT), name="cache")

app.mount("/css", StaticFiles(directory=os.path.join(BASE_DIR, "css")), name="css")
app.mount("/js", StaticFiles(directory=os.path.join(BASE_DIR, "js")), name="js")


def _serve_page(filename: str):
    page_path = os.path.join(BASE_DIR, filename)
    if not os.path.exists(page_path):
        raise HTTPException(
            status_code=404, detail=f"Page not found: {filename}")
    return FileResponse(page_path)


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
                    parsed_styles[k] = int(
                        float_v) if float_v.is_integer() else float_v
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


MAX_ARCHIVE_SPAN_DAYS = {
    "alerts": 7,
    "surface": 7,
    "radar": 2,
    "satellite": 3,
    "spc": 14,
}


def error_payload(message: str, *, code: str = "bad_request", details=None):
    payload = {"error": message, "code": code}
    if details is not None:
        payload["details"] = details
    return payload


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


def parse_utc_datetime(value: str) -> datetime:
    raw = (value or "").strip()
    if not raw:
        raise HTTPException(
            status_code=400,
            detail=error_payload(
                "Invalid empty datetime value.", code="invalid_date"),
        )

    normalized = raw.replace("Z", "+00:00")
    parsed = None
    parse_attempts = ["%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d"]

    if any(token in normalized for token in ["+", "T"]):
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            parsed = None

    if parsed is None:
        for fmt in parse_attempts:
            try:
                parsed = datetime.strptime(normalized, fmt)
                break
            except ValueError:
                continue

    if parsed is None:
        raise HTTPException(
            status_code=400,
            detail=error_payload(
                f"Invalid date format: {value}",
                code="invalid_date",
                details="Use YYYY-MM-DD HH:MM, YYYY-MM-DDTHH:MM, or YYYY-MM-DD",
            ),
        )

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def validate_archive_range(category: str, start_utc: datetime, end_utc: datetime):
    if end_utc < start_utc:
        raise HTTPException(
            status_code=400,
            detail=error_payload(
                "date_to must be greater than or equal to date_from.",
                code="invalid_date_range",
            ),
        )

    max_days = float(MAX_ARCHIVE_SPAN_DAYS.get(category, 7))
    max_delta = timedelta(days=max_days)
    if (end_utc - start_utc) > max_delta:
        raise HTTPException(
            status_code=400,
            detail=error_payload(
                f"Archive range too large for {category}.",
                code="date_range_too_large",
                details=f"Maximum allowed span is {max_days} day(s).",
            ),
        )


def format_utc_for_legacy(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M")


def success_payload(
    *,
    message: str,
    image_url: Optional[str],
    source: str,
    data_mode: str,
    request_id: str = "",
    status: str = "success",
):
    payload = {
        "status": status,
        "message": message,
        "image_url": image_url,
        "source": source,
        "data_mode": data_mode,
    }
    if request_id:
        payload["request_id"] = request_id
    return payload


def attach_mode_and_source(payload: dict, data_mode: str):
    if not isinstance(payload, dict):
        return payload
    source_value = payload.get("source") or payload.get(
        "data_source") or "Unknown"
    payload["source"] = source_value
    payload["data_mode"] = data_mode
    return payload


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


def find_nearest_radar_sites(
    center_lat: float, center_lon: float, limit: int = 8
) -> list[str]:
    """Return nearest WSR-88D radar sites ordered by distance to a lat/lon."""
    from pyart.io.nexrad_common import NEXRAD_LOCATIONS
    import math

    # Only consider actual WSR-88D NEXRAD sites, not TDWR or overseas military
    # K-prefix = CONUS, P-prefix = Alaska/Pacific, TJUA = Puerto Rico
    VALID_PREFIXES = ("K", "P")
    VALID_EXTRAS = {"TJUA"}

    candidates = []
    for site_id, info in NEXRAD_LOCATIONS.items():
        if not (site_id.startswith(VALID_PREFIXES) or site_id in VALID_EXTRAS):
            continue
        dlat = info["lat"] - center_lat
        dlon = info["lon"] - center_lon
        dist = math.sqrt(dlat * dlat + dlon * dlon)
        normalized_id = normalize_radar_site_id(site_id)
        candidates.append((dist, normalized_id))

    if not candidates:
        return ["KMHX"]

    candidates.sort(key=lambda pair: pair[0])
    deduped_sites = []
    seen = set()
    for _, site_id in candidates:
        if site_id in seen:
            continue
        seen.add(site_id)
        deduped_sites.append(site_id)
        if len(deduped_sites) >= max(1, int(limit)):
            break

    return deduped_sites or ["KMHX"]


def find_closest_radar_site(center_lat: float, center_lon: float) -> str:
    """Find the NEXRAD WSR-88D radar site closest to a given lat/lon using pyart."""
    return find_nearest_radar_sites(center_lat, center_lon, limit=1)[0]


def build_radar_product_attempts(
    level: str, product: str, lookback: float, latest_only: bool = False
):
    level_name = str(level or "").strip()
    product_id = str(product or "").strip().upper()
    base_lookback = max(0.5, float(lookback or 0.5))

    product_candidates = [product_id]
    if level_name == "Level 3":
        product_aliases = {
            "NVW": ["N0G", "NVW"],
            "N0G": ["N0G", "NVW"],
            "N0M": ["N0M", "NCR"],
            "N0H": ["N0H", "HHC", "NAH", "NBH"],
            "DHR": ["DHR", "DPR", "N1P"],
            "N1P": ["N1P", "DPR", "DHR"],
            "DPA": ["DPA", "DAA"],
            "DTA": ["DTA", "NRR", "NTP"],
            "NTP": ["NTP", "DTA", "NRR"],
            "NRR": ["NRR", "DTA", "NTP"],
        }
        product_candidates = product_aliases.get(product_id, [product_id])

    lookback_candidates = [base_lookback]
    if level_name == "Level 3" and not latest_only:
        if product_id in {"N1P", "DHR", "DPA"}:
            lookback_candidates.extend([3, 6, 12])
        elif product_id in {"NTP", "DTA", "NRR"}:
            lookback_candidates.extend([6, 12, 24])
        else:
            lookback_candidates.extend([2, 4])

    seen_products = set()
    unique_products = []
    for candidate in product_candidates:
        if candidate not in seen_products:
            seen_products.add(candidate)
            unique_products.append(candidate)

    seen_lookbacks = set()
    unique_lookbacks = []
    for candidate in lookback_candidates:
        candidate = max(0.5, float(candidate))
        if candidate not in seen_lookbacks:
            seen_lookbacks.add(candidate)
            unique_lookbacks.append(candidate)

    attempts = []
    for candidate_product in unique_products:
        for candidate_lookback in unique_lookbacks:
            attempts.append((candidate_product, candidate_lookback))
    return attempts


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


@app.get("/")
def read_root():
    return _serve_page("index.html")


@app.get("/api/status")
def read_status():
    return {
        "status": "Weather System Online",
        "version": "2026.1",
        "radar_satellite_default_source": "NODD" if USING_NODD else "THREDDS",
    }


# ── MRMS app state (Phase 3) ─────────────────────────────────────────────────
# Tracks which MRMS product the worker is actively refreshing.
# Mutated by /api/mrms/set-product; read by the mrms_worker.
_active_mrms_product: str = "PrecipRate"

# ── MRMS app state (Phase 3) ─────────────────────────────────────────────────
# Tracks which MRMS product the worker is actively refreshing.
# Mutated by /api/mrms/set-product; read by the mrms_worker.
_active_mrms_product: str = "PrecipRate"

# ── Surface color helpers (Phase 2) ─────────────────────────────────────────
try:
    from config.surface_config import TEMPERATURE_GRADIENT_ANCHORS as _TEMP_ANCHORS
except Exception:
    _TEMP_ANCHORS = [
        (-60, "#00352C"), (-20, "#c4c4d4"), (0, "#570057"), (32, "#0000ff"),
        (50, "#c4c403"), (80, "#c20303"), (130, "#000000"),
    ]

_WIND_ANCHORS = [
    (0, "#b0d4f0"), (10, "#70b0e0"), (20, "#3090d0"),
    (30, "#f5dd72"), (45, "#ff9d2e"), (60, "#ff4f4f"),
]
_RH_ANCHORS = [
    (0, "#c8a000"), (20, "#f5dd72"), (40, "#69bb6d"),
    (60, "#0099cc"), (80, "#0055aa"), (100, "#003377"),
]

_SURFACE_PRODUCTS = {
    "temperature":       {"col": "air_temperature",       "unit": "\u00b0F", "anchors": "temp"},
    "feels_like":        {"col": "feels_like",             "unit": "\u00b0F", "anchors": "temp"},
    "dew_point":         {"col": "dew_point_temperature",  "unit": "\u00b0F", "anchors": "temp"},
    "relative_humidity": {"col": "relative_humidity",      "unit": "%",      "anchors": "rh"},
    "wind_speed":        {"col": "wind_speed",             "unit": "kt",     "anchors": "wind"},
    "wind_gust":         {"col": "peak_wind",              "unit": "kt",     "anchors": "wind"},
}


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
            "id":          str(row.get("station_id", "")),
            "lat":         float(row.get("latitude", 0)),
            "lon":         float(row.get("longitude", 0)),
            "value":       round(val, 1),
            "color":       color,
            "unit":        meta["unit"],
            "temperature": _safe_float(row, "air_temperature"),
            "dew_point":   _safe_float(row, "dew_point_temperature"),
            "feels_like":  _safe_float(row, "feels_like"),
            "rh":          _safe_float(row, "relative_humidity"),
            "wind_speed":  _safe_float(row, "wind_speed"),
            "wind_dir":    _safe_float(row, "wind_dir"),
            "wind_gust":   _safe_float(row, "peak_wind"),
            "visibility":  _safe_float(row, "visibility"),
        }
        stations.append(station)
    return stations


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


# ── Phase 1: Data Endpoints (served from worker cache) ───────────────────────


@app.get("/api/data/alerts")
def get_data_alerts(state: Optional[str] = None):
    """Return national alerts GeoJSON from worker cache, optionally filtered by state."""
    cache_file = os.path.join(_CACHE_ROOT, "alerts", "national.geojson")

    if not os.path.exists(cache_file):
        # Cold cache: trigger a synchronous worker run
        try:
            from workers.alerts_worker import run_alerts_worker
            run_alerts_worker()
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Alerts cache not yet available: {exc}",
            )

    try:
        with open(cache_file, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    features = data.get("features", [])

    if state:
        state_upper = state.upper().strip()

        def _matches(feat: dict) -> bool:
            props = feat.get("properties") or {}
            for zone in props.get("affectedZones") or []:
                if f"/{state_upper}" in str(zone):
                    return True
            return state_upper in str(props.get("areaDesc") or "")

        features = [f for f in features if _matches(f)]

    return {
        "type": "FeatureCollection",
        "features": features,
        "_source": data.get("_source", "NWS"),
        "_updated": data.get("_updated"),
        "count": len(features),
    }


@app.get("/api/data/spc")
def get_data_spc(day: int = 1, hazard: str = "cat"):
    """Return SPC outlook GeoJSON from worker cache."""
    hazard_lower = hazard.strip().lower()
    is_fire = hazard_lower in {"windrh", "dryt"}
    cache_name = f"fire_{day}_{hazard_lower}" if is_fire else f"{day}_{hazard_lower}"
    cache_file = os.path.join(_CACHE_ROOT, "spc", f"{cache_name}.geojson")

    if not os.path.exists(cache_file):
        # Cold cache: trigger a synchronous SPC worker run
        try:
            from workers.spc_worker import run_spc_worker
            run_spc_worker()
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail=f"SPC cache not yet available: {exc}",
            )

    if not os.path.exists(cache_file):
        return {
            "type": "FeatureCollection",
            "features": [],
            "_source": "SPC",
            "_updated": None,
            "count": 0,
        }

    try:
        with open(cache_file, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    data["count"] = len(data.get("features") or [])
    return data


@app.get("/api/data/surface")
def get_data_surface(region: str = "NC", product: str = "temperature"):
    """Return surface observations JSON with per-station colors, lazy-cached 5 min."""
    region_upper = region.upper().strip()
    product_lower = product.lower().strip()
    if product_lower not in _SURFACE_PRODUCTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown product '{product}'. Valid: {list(_SURFACE_PRODUCTS.keys())}",
        )

    surface_cache_dir = os.path.join(_CACHE_ROOT, "surface")
    os.makedirs(surface_cache_dir, exist_ok=True)
    cache_file = os.path.join(
        surface_cache_dir, f"{region_upper}_{product_lower}.json")

    if os.path.exists(cache_file):
        age = _time.time() - os.path.getmtime(cache_file)
        if age < 300:
            try:
                with open(cache_file, "r", encoding="utf-8") as fh:
                    return json.load(fh)
            except Exception:
                pass

    try:
        df = surface_utils.fetch_metar_data(region_upper)
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"Surface data unavailable: {exc}")

    stations = _build_surface_stations(df, product_lower)
    result = {
        "stations": stations,
        "product": product_lower,
        "unit": _SURFACE_PRODUCTS[product_lower]["unit"],
        "region": region_upper,
        "count": len(stations),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    try:
        with open(cache_file, "w", encoding="utf-8") as fh:
            json.dump(result, fh)
    except Exception:
        pass

    return result


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
    else:
        anchors = _RH_ANCHORS
    return {
        "product": product_lower,
        "unit": meta["unit"],
        "anchors": [{"value": a[0], "color": a[1]} for a in anchors],
    }


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
    """
    Return an MRMS PNG overlay for the given product and viewport bounds.
    Reads the cached CONUS GRIB2, crops to bounds, applies colormap,
    writes a transparent PNG, and returns its URL + georef bounds.
    On cold cache: triggers a synchronous download (~3-5s first time).
    """
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
            run_mrms_worker()
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

    # Check if a recent PNG crop is already cached for this product + bounds
    import hashlib
    bounds_key = hashlib.md5(
        f"{product}_{south:.2f}_{west:.2f}_{north:.2f}_{east:.2f}".encode()).hexdigest()[:10]
    png_path = os.path.join(product_cache_dir, f"overlay_{bounds_key}.png")
    grib_mtime = os.path.getmtime(grib_path)
    png_stale = not os.path.exists(
        png_path) or os.path.getmtime(png_path) < grib_mtime

    if png_stale:
        try:
            png_path, actual_bounds = _render_mrms_png(
                grib_path, product, [west, east, south, north], png_path
            )
        except Exception as exc:
            raise HTTPException(
                status_code=500, detail=f"MRMS render error: {exc}")
    else:
        # Read bounds from sidecar file
        sidecar = png_path.replace(".png", "_bounds.json")
        if os.path.exists(sidecar):
            with open(sidecar, "r") as f:
                actual_bounds = json.load(f)
        else:
            actual_bounds = [west, east, south, north]

    # Build URL relative to /cache mount
    rel = os.path.relpath(png_path, _CACHE_ROOT).replace("\\", "/")
    image_url = f"/cache/{rel}"

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
        "timestamp": datetime.now(timezone.utc).isoformat(),
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
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.colors as mcolors

    from mrms.mrms_utils import read_mrms_grib2, decompress_grib2_gz
    from config.mrms_config import MRMS_PRODUCTS, MRMS_COLORMAPS

    prod_info = MRMS_PRODUCTS[product]
    cmap_key = prod_info.get("colormap", "precip_rate")
    vmin = prod_info.get("vmin", 0)
    vmax = prod_info.get("vmax", 100)
    missing_value = prod_info.get("missing_value", -1)
    no_coverage = prod_info.get("no_coverage", -3)

    west, east, south, north = crop_extent

    data, meta = read_mrms_grib2(grib_path, product, crop_extent=crop_extent)

    # Mask fill/missing values
    data = np.where(
        (data == missing_value) | (data == no_coverage) | (data < vmin),
        np.nan,
        data,
    )

    lat = meta.get("latitude")
    lon = meta.get("longitude")
    if lat is None or lon is None:
        raise ValueError("GRIB2 read did not return lat/lon metadata")

    # Compute actual rendered bounds
    actual_west = float(np.min(lon))
    actual_east = float(np.max(lon))
    actual_south = float(np.min(lat))
    actual_north = float(np.max(lat))
    actual_bounds = [actual_west, actual_east, actual_south, actual_north]

    # Build colormap
    cmap_obj = MRMS_COLORMAPS.get(cmap_key)
    if isinstance(cmap_obj, tuple):
        cmap, norm = cmap_obj[0], cmap_obj[1] if len(
            cmap_obj) > 1 else mcolors.Normalize(vmin=vmin, vmax=vmax)
    elif cmap_obj is not None:
        cmap = cmap_obj
        norm = mcolors.Normalize(vmin=vmin, vmax=vmax)
    else:
        cmap = plt.get_cmap("viridis")
        norm = mcolors.Normalize(vmin=vmin, vmax=vmax)

    # Render to RGBA PNG (transparent where masked)
    h, w = data.shape
    dpi = 100
    fig_w = w / dpi
    fig_h = h / dpi
    fig, ax = plt.subplots(1, 1, figsize=(fig_w, fig_h), dpi=dpi)
    ax.set_position([0, 0, 1, 1])
    ax.set_axis_off()
    ax.imshow(
        data,
        origin="upper",
        cmap=cmap,
        norm=norm,
        aspect="auto",
        interpolation="nearest",
    )
    fig.patch.set_alpha(0)
    ax.patch.set_alpha(0)
    fig.savefig(out_path, dpi=dpi, bbox_inches=None,
                transparent=True, format="png")
    plt.close(fig)

    # Write bounds sidecar
    sidecar = out_path.replace(".png", "_bounds.json")
    with open(sidecar, "w") as f:
        json.dump(actual_bounds, f)

    return out_path, actual_bounds


def read_index_page():
    return _serve_page("index.html")


@app.get("/radar.html")
def read_radar_page():
    return _serve_page("radar.html")


@app.get("/satellite.html")
def read_satellite_page():
    return _serve_page("satellite.html")


@app.get("/satellite-archive.html")
def read_satellite_archive_page():
    return _serve_page("satellite.html")


@app.get("/weather.html")
def read_weather_page():
    return _serve_page("weather.html")


@app.get("/api/progress/{task_id}")
def get_task_progress(task_id: str):
    return active_tasks.get(
        task_id, {"percent": 0, "message": "Waiting...", "stage": "idle"}
    )


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


@app.get("/api/radar/basemap/{site}")
def get_radar_basemap(site: str):
    """Return the URL to a pre-rendered basemap for the given radar site, or 404 if not found."""
    try:
        site_normalized = normalize_radar_site_id(site.upper())
        # Check if basemap exists at the actual location: basemap_cache/radar/{SITE}/{SITE}.png
        basemap_path = os.path.join(
            BASE_DIR,
            "basemap_cache",
            "radar",
            site_normalized,
            f"{site_normalized}.png",
        )
        if not os.path.exists(basemap_path):
            raise HTTPException(
                status_code=404, detail=f"Basemap not found for site {site_normalized}"
            )

        # Construct the relative URL path
        basemap_url = (
            f"/img/basemap_cache/radar/{site_normalized}/{site_normalized}.png"
        )
        return {
            "status": "success",
            "basemap_url": basemap_url,
            "site": site_normalized,
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Radar basemap endpoint error for site {site}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def get_radar_latest(
    request_id: str,
    site: str = "KMHX",
    product: str = "N0B",
    level: str = "Level 3",
    frames: int = 1,
    fps: int = 4,
    lookback: float = 0.5,
    sm_speed: int = 30,
    sm_dir: int = 225,
    show_places: bool = False,
    n: Optional[float] = None,
    s: Optional[float] = None,
    e: Optional[float] = None,
    w: Optional[float] = None,
    source: str = "auto",
    style_config: Optional[str] = None,
    latest_only: bool = False,
    view_mode: str = "image",
    render_mode: str = "full",
):
    try:
        site = normalize_radar_site_id(site)
        requested_product = str(product or "N0B").strip().upper()
        requested_source = str(source or "auto").strip().lower()
        view_render_mode = str(view_mode or "image").strip().lower()
        data_only_mode = str(
            render_mode or "full").strip().lower() == "data_only"

        if view_render_mode not in {"image", "layers"}:
            view_render_mode = "image"
        if requested_source not in {"auto", "aws", "gcp", "thredds"}:
            return {
                "status": "error",
                "message": "Invalid source. Use auto, aws, gcp, or thredds.",
                "data_source": "UNKNOWN",
            }

        if view_render_mode == "layers":
            now_utc = datetime.now(timezone.utc)
            lookback_hours = max(0.25, float(lookback or 0.5))
            from_utc = now_utc - timedelta(hours=lookback_hours)
            archive_source = requested_source
            if archive_source == "auto":
                archive_source = "aws" if USING_NODD else "thredds"

            return get_radar_archive(
                request_id=request_id,
                site=site,
                product=product,
                level=level,
                date_from=from_utc.strftime("%Y-%m-%d %H:%M"),
                date_to=now_utc.strftime("%Y-%m-%d %H:%M"),
                user_tz="America/New_York",
                frames=1,
                fps=fps,
                sm_speed=sm_speed,
                sm_dir=sm_dir,
                show_places=show_places,
                n=n,
                s=s,
                e=e,
                w=w,
                source=archive_source,
                style_config=style_config,
                latest_only=True,
                view_mode="layers",
            )

        # === DATA-ONLY TRANSPARENT RENDERING MODE ===
        if data_only_mode:
            try:
                from radar.radar_data_only_utils import (
                    render_radar_data_only_transparent,
                )

                # Download latest radar file
                radar_module = radar_utils
                data_source = "THREDDS"
                provider = "aws"

                if requested_source == "thredds":
                    radar_module = radar_thredds_utils
                    data_source = "THREDDS"
                elif requested_source in {"aws", "gcp"}:
                    if not USING_NODD:
                        return {
                            "status": "error",
                            "message": "NODD module unavailable.",
                            "data_source": "THREDDS",
                        }
                    provider = requested_source
                    data_source = f"NODD-{provider.upper()}"
                else:
                    if USING_NODD:
                        provider = "aws"
                        data_source = "NODD-AWS"

                def download_progress(curr, total):
                    active_tasks[request_id] = {
                        "percent": int((curr / total) * 100),
                        "message": f"Downloading {curr}/{total}",
                        "stage": "download",
                        "source": data_source,
                    }

                # Download data
                data_dir, total_files, _ = radar_module.download_radar_data(
                    level,
                    site,
                    requested_product,
                    0.5,
                    os.path.join(BASE_DIR, "radar"),
                    download_progress,
                    provider=provider
                    if radar_module is not radar_thredds_utils
                    else None,
                    latest_only=True,
                )

                if not data_dir or total_files == 0:
                    return {
                        "status": "error",
                        "message": f"No radar data found for {site}",
                        "data_source": data_source,
                    }

                # Find latest file
                radar_files = sorted(
                    glob.glob(os.path.join(data_dir, "*.nexrad"))
                    + glob.glob(os.path.join(data_dir, "*.nc"))
                )
                if not radar_files:
                    return {
                        "status": "error",
                        "message": f"No radar files in {data_dir}",
                        "data_source": data_source,
                    }

                radar_file = radar_files[-1]

                # Render data-only transparent PNG
                output_dir = os.path.join(
                    DIRS["radar"],
                    f"radar_level{level.replace(' ', '')}_images",
                    requested_product,
                    site,
                )
                output_path = os.path.join(output_dir, "latest_data_only.png")

                rendered_path = render_radar_data_only_transparent(
                    radar_file, requested_product, output_path, dpi=150
                )

                if request_id in active_tasks:
                    del active_tasks[request_id]

                if not rendered_path:
                    return {
                        "status": "error",
                        "message": "Failed to render radar data",
                        "data_source": data_source,
                    }

                # Build URL path - the mount is /img/radar_level{3|2}_images → radar/radar_level{3|2}_images/
                level_str = level.replace(" ", "")
                rel_path = os.path.relpath(
                    rendered_path,
                    os.path.join(
                        DIRS["radar"], f"radar_level{level_str}_images"),
                ).replace("\\", "/")
                image_url = f"/img/radar_level{level_str}_images/{rel_path}"

                return {
                    "status": "success",
                    "image_url": image_url,
                    "data_source": data_source,
                    "site_used": site,
                    "product_requested": requested_product,
                }
            except Exception as e:
                if request_id in active_tasks:
                    del active_tasks[request_id]
                return {
                    "status": "error",
                    "message": f"Data-only render failed: {str(e)}",
                    "data_source": "ERROR",
                }

        radar_module = radar_utils
        provider = "aws"
        if requested_source == "thredds":
            radar_module = radar_thredds_utils
            data_source = "THREDDS"
        elif requested_source in {"aws", "gcp"}:
            if not USING_NODD:
                return {
                    "status": "error",
                    "message": "NODD module unavailable. AWS/GCP sources are not available.",
                    "data_source": "THREDDS",
                }
            provider = requested_source
            data_source = f"NODD-{provider.upper()}"
        else:
            # Auto mode: use AWS for both Level 2 and Level 3.
            # Fallback chain: AWS → GCP → THREDDS (handled below).
            if USING_NODD:
                provider = "aws"
                data_source = "NODD-AWS"
            else:
                data_source = "THREDDS"
        parsed_styles = {}
        if style_config:
            raw_styles = json.loads(style_config)
            for k, v in raw_styles.items():
                try:
                    float_v = float(v)
                    parsed_styles[k] = int(
                        float_v) if float_v.is_integer() else float_v
                except (ValueError, TypeError):
                    parsed_styles[k] = v

        def download_progress(curr, total):
            active_tasks[request_id] = {
                "percent": int((curr / total) * 100),
                "message": f"Downloading {curr}/{total}",
                "stage": "download",
                "source": data_source,
            }

        def render_progress(curr, total):
            active_tasks[request_id] = {
                "percent": int((curr / total) * 100),
                "message": f"Rendering {curr}/{total}",
                "stage": "render",
                "source": data_source,
            }

        custom_extent = (
            (s, n, w, e) if all(v is not None for v in [n, s, e, w]) else None
        )
        site_candidates = [site]
        if custom_extent:
            center_lat = (custom_extent[0] +
                          custom_extent[1]) / 2  # (s + n) / 2
            center_lon = (custom_extent[2] +
                          custom_extent[3]) / 2  # (w + e) / 2
            site_candidates = find_nearest_radar_sites(
                center_lat, center_lon, limit=8)
            site = site_candidates[0]
            print(
                f"[INFO] Custom extent active — auto-selected closest radar: {site} "
                f"(fallback pool: {', '.join(site_candidates[:4])}{'...' if len(site_candidates) > 4 else ''})"
            )
        frames = 1 if latest_only else max(1, int(frames))

        attempts = build_radar_product_attempts(
            level, requested_product, lookback, latest_only=latest_only
        )

        def attempt_download(module_to_use, site_id: str, provider_name=None):
            attempted = []
            last_error = None

            for candidate_product, candidate_lookback in attempts:
                attempted.append(f"{candidate_product}@{candidate_lookback}h")
                try:
                    if module_to_use is radar_thredds_utils:
                        data_dir_local, total_files_local, _ = (
                            module_to_use.download_radar_data(
                                level,
                                site_id,
                                candidate_product,
                                candidate_lookback,
                                os.path.join(BASE_DIR, "radar"),
                                download_progress,
                                latest_only=latest_only,
                            )
                        )
                    else:
                        data_dir_local, total_files_local, _ = (
                            module_to_use.download_radar_data(
                                level,
                                site_id,
                                candidate_product,
                                candidate_lookback,
                                os.path.join(BASE_DIR, "radar"),
                                download_progress,
                                provider=provider_name,
                                latest_only=latest_only,
                            )
                        )
                except Exception as attempt_error:
                    last_error = attempt_error
                    continue

                if data_dir_local and total_files_local > 0:
                    return (
                        data_dir_local,
                        candidate_product,
                        candidate_lookback,
                        attempted,
                    )

            if last_error is not None:
                raise RuntimeError(
                    f"No radar data found for {site_id} using attempts: {', '.join(attempted)}"
                ) from last_error

            raise RuntimeError(
                f"No radar data found for {site_id} using attempts: {', '.join(attempted)}"
            )

        def download_with_source_fallback(site_id: str):
            module_in_use = radar_module
            source_in_use = data_source

            try:
                _t_dl_total = _time.perf_counter()
                dl_result = attempt_download(
                    module_in_use, site_id=site_id, provider_name=provider
                )
                print(
                    f"[TIMER] attempt_download TOTAL {_time.perf_counter() - _t_dl_total:.2f}s "
                    f"for site {site_id}"
                )
                return (*dl_result, module_in_use, source_in_use)
            except Exception:
                if requested_source == "auto" and USING_NODD:
                    # GCP Level 3 buckets are not publicly accessible for
                    # individual product files (realtime bucket returns 403;
                    # archive bucket only has daily tar.gz bundles).  Skip GCP
                    # as an alternate provider for Level 3 to avoid wasting
                    # time on requests that will always fail.
                    level_lower = str(level).lower().replace(" ", "")
                    skip_gcp_alt = level_lower == "level3"

                    alt_provider = "aws" if provider == "gcp" else "gcp"
                    if skip_gcp_alt and alt_provider == "gcp":
                        print(
                            f"[WARN] NODD-{provider.upper()} failed, skipping GCP (Level 3 not publicly listable), falling back to THREDDS"
                        )
                        alt_provider = None  # skip straight to THREDDS

                    if alt_provider:
                        try:
                            print(
                                f"[WARN] NODD-{provider.upper()} failed, trying NODD-{alt_provider.upper()}..."
                            )
                            source_in_use = f"NODD-{alt_provider.upper()}"
                            dl_result = attempt_download(
                                module_in_use,
                                site_id=site_id,
                                provider_name=alt_provider,
                            )
                            return (*dl_result, module_in_use, source_in_use)
                        except Exception:
                            print(
                                f"[WARN] NODD-{alt_provider.upper()} also failed, falling back to THREDDS"
                            )
                            module_in_use = radar_thredds_utils
                            source_in_use = "THREDDS"
                            dl_result = attempt_download(
                                module_in_use,
                                site_id=site_id,
                                provider_name=None,
                            )
                            return (*dl_result, module_in_use, source_in_use)

                    # No alt provider (GCP skipped for Level 3), go straight to THREDDS
                    module_in_use = radar_thredds_utils
                    source_in_use = "THREDDS"
                    dl_result = attempt_download(
                        module_in_use,
                        site_id=site_id,
                        provider_name=None,
                    )
                    return (*dl_result, module_in_use, source_in_use)
                raise

        site_attempt_errors = []
        for idx, candidate_site in enumerate(site_candidates, start=1):
            try:
                (
                    data_dir,
                    resolved_product,
                    resolved_lookback,
                    attempted_variants,
                    radar_module,
                    data_source,
                ) = download_with_source_fallback(candidate_site)
                if custom_extent and idx > 1:
                    print(
                        f"[INFO] Closest radar lacked usable data. Using fallback site {candidate_site}"
                    )
                site = candidate_site
                break
            except Exception as site_error:
                site_attempt_errors.append(f"{candidate_site}: {site_error}")
                if len(site_candidates) > 1:
                    print(
                        f"[WARN] Radar site {candidate_site} unavailable: {site_error}"
                    )
        else:
            attempted_sites = ", ".join(site_candidates)
            details = (
                " | ".join(site_attempt_errors[-3:]
                           ) if site_attempt_errors else ""
            )
            raise RuntimeError(
                f"No radar data found for requested extent after trying sites: {attempted_sites}"
                + (f" ({details})" if details else "")
            )

        # Use custom logo path from style config, or fall back to default
        logo_path_to_use = resolve_logo_path(
            parsed_styles, BASE_DIR, LOGO_PATH)

        _t_render = _time.perf_counter()
        result_path = radar_module.generate_radar_image(
            level=level,
            data_dir=data_dir,
            product_label=resolved_product,
            logo_file=logo_path_to_use,
            station_id=site,
            sm_speed=sm_speed,
            sm_dir=sm_dir,
            custom_extent=custom_extent,
            progress_callback=render_progress,
            show_places=show_places,
            max_frames=frames,
            fps=fps,
            style_config=parsed_styles,
        )
        print(
            f"[TIMER] generate_radar_image took {_time.perf_counter() - _t_render:.2f}s"
        )
        if request_id in active_tasks:
            del active_tasks[request_id]

        if result_path is None:
            return {
                "status": "error",
                "message": "Failed to generate radar image. Check server logs for details.",
                "data_source": data_source,
            }

        # Extract the level-specific path (radar_level2_images or radar_level3_images)
        rel_path = os.path.relpath(
            result_path, DIRS["radar"]).replace("\\", "/")
        return {
            "status": "success",
            "image_url": f"/img/{rel_path}",
            "data_source": data_source,
            "site_used": site,
            "product_requested": requested_product,
            "product_used": resolved_product,
            "lookback_used": resolved_lookback,
            "attempts": attempted_variants,
        }
    except Exception as e:
        if request_id:
            active_tasks[request_id] = {
                "percent": 0,
                "message": f"Error: {str(e)}",
                "stage": "error",
                "source": data_source if "data_source" in locals() else None,
            }
        return {
            "status": "error",
            "message": str(e),
            "data_source": data_source if "data_source" in locals() else None,
        }


@app.get("/api/radar/archive")
def get_radar_archive_endpoint(
    request_id: str = "",
    site: str = "KMHX",
    product: str = "N0B",
    level: str = "Level 3",
    date_from: str = "",
    date_to: str = "",
    user_tz: str = "America/New_York",
    frames: int = 150,
    fps: int = 4,
    sm_speed: int = 30,
    sm_dir: int = 225,
    show_places: bool = False,
    show_counties: bool = False,
    n: Optional[float] = None,
    s: Optional[float] = None,
    e: Optional[float] = None,
    w: Optional[float] = None,
    source: str = "aws",
    style_config: Optional[str] = None,
    latest_only: bool = False,
    view_mode: str = "layers",
):
    response = get_radar_archive(
        request_id=request_id,
        site=site,
        product=product,
        level=level,
        date_from=date_from,
        date_to=date_to,
        user_tz=user_tz,
        frames=frames,
        fps=fps,
        sm_speed=sm_speed,
        sm_dir=sm_dir,
        show_places=show_places,
        show_counties=show_counties,
        n=n,
        s=s,
        e=e,
        w=w,
        source=source,
        style_config=style_config,
        latest_only=latest_only,
        view_mode=view_mode,
    )
    return attach_mode_and_source(response, "archive")


@app.get("/api/radar/archive/export-animation")
def export_radar_archive_animation(
    layers_path: str,
    fps: int = 4,
):
    if radar_archive_utils is None:
        return {
            "status": "error",
            "message": "Radar archive module is not available.",
            "data_source": "ARCHIVE",
        }

    requested = str(layers_path or "").strip().replace("\\", "/")
    if not requested:
        return {
            "status": "error",
            "message": "layers_path is required.",
            "data_source": "ARCHIVE",
        }
    if requested.startswith("/") or ".." in requested:
        return {
            "status": "error",
            "message": "Invalid layers_path.",
            "data_source": "ARCHIVE",
        }

    radar_root = os.path.normpath(DIRS["radar"])
    layer_dir = os.path.normpath(os.path.join(radar_root, requested))
    if not (layer_dir.startswith(radar_root) and os.path.isdir(layer_dir)):
        return {
            "status": "error",
            "message": "Layer directory not found.",
            "data_source": "ARCHIVE",
        }

    if "/layers/" not in layer_dir.replace("\\", "/"):
        return {
            "status": "error",
            "message": "layers_path must point to a layered archive directory.",
            "data_source": "ARCHIVE",
        }

    if hasattr(radar_archive_utils, "touch_layer_session"):
        try:
            radar_archive_utils.touch_layer_session(layer_dir)
        except Exception:
            pass

    movie_path, frame_count = radar_archive_utils.export_layered_animation(
        layer_dir=layer_dir,
        fps=max(1, int(fps or 4)),
    )
    if not movie_path:
        return {
            "status": "error",
            "message": "Unable to export layered animation.",
            "data_source": "ARCHIVE",
        }

    rel_path = os.path.relpath(movie_path, DIRS["radar"]).replace("\\", "/")
    return {
        "status": "success",
        "message": f"Exported layered animation ({frame_count} frames).",
        "image_url": f"/img/{rel_path}",
        "layers_path": requested,
        "output_mode": "video",
        "data_source": "ARCHIVE",
    }


@app.get("/api/radar")
def get_radar(
    request_id: str = "",
    site: str = "KMHX",
    product: str = "N0B",
    level: str = "Level 3",
    frames: int = 1,
    fps: int = 4,
    lookback: float = 0.5,
    sm_speed: int = 30,
    sm_dir: int = 225,
    show_places: bool = False,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    user_tz: str = "America/New_York",
    n: Optional[float] = None,
    s: Optional[float] = None,
    e: Optional[float] = None,
    w: Optional[float] = None,
    source: str = "auto",
    style_config: Optional[str] = None,
    latest_only: bool = False,
    view_mode: str = "layers",
):
    """Deprecated: Use /api/radar/archive."""
    data_mode = infer_data_mode(date_from, date_to)
    if data_mode == "recent":
        response = get_radar_latest(
            request_id=request_id,
            site=site,
            product=product,
            level=level,
            # Legacy endpoint is constrained to a single static frame.
            frames=1,
            fps=fps,
            lookback=lookback,
            sm_speed=sm_speed,
            sm_dir=sm_dir,
            show_places=show_places,
            n=n,
            s=s,
            e=e,
            w=w,
            source=source,
            style_config=style_config,
            latest_only=latest_only,
        )
        return attach_mode_and_source(response, "recent")

    return get_radar_archive_endpoint(
        request_id=request_id,
        site=site,
        product=product,
        level=level,
        date_from=date_from or "",
        date_to=date_to or "",
        user_tz=user_tz,
        frames=frames,
        fps=fps,
        sm_speed=sm_speed,
        sm_dir=sm_dir,
        show_places=show_places,
        n=n,
        s=s,
        e=e,
        w=w,
        source=source,
        style_config=style_config,
        latest_only=latest_only,
        view_mode=view_mode,
    )


# ─── Radar Archive (standalone) ─────────────────────────────────────────────
def get_radar_archive(
    request_id: str,
    site: str = "KMHX",
    product: str = "N0B",
    level: str = "Level 3",
    date_from: str = "",
    date_to: str = "",
    user_tz: str = "America/New_York",
    frames: int = 150,
    fps: int = 4,
    sm_speed: int = 30,
    sm_dir: int = 225,
    show_places: bool = False,
    show_counties: bool = False,
    n: Optional[float] = None,
    s: Optional[float] = None,
    e: Optional[float] = None,
    w: Optional[float] = None,
    source: str = "aws",
    style_config: Optional[str] = None,
    latest_only: bool = False,
    view_mode: str = "layers",
):
    """Radar archive endpoint — uses entirely separate download/render pipeline."""
    requested_source = str(source or "aws").strip().lower() or "aws"
    source_used = requested_source
    if radar_archive_utils is None:
        return {
            "status": "error",
            "message": "Radar archive module is not available.",
            "data_source": "ARCHIVE",
            "requested_source": requested_source,
            "source_used": source_used,
        }

    data_source = "ARCHIVE"
    try:
        site = normalize_radar_site_id(site)
        provider = str(source or "aws").strip().lower()
        if provider not in {"aws", "gcp", "thredds"}:
            provider = "aws"
        requested_source = provider
        source_used = provider
        data_source = f"ARCHIVE-{provider.upper()}"
        render_mode = str(view_mode or "layers").strip().lower()
        if render_mode not in {"video", "layers"}:
            render_mode = "layers"

        if not date_from or not date_to:
            return {
                "status": "error",
                "message": "date_from and date_to are required for archive mode.",
                "data_source": data_source,
            }

        parsed_from = parse_utc_datetime(date_from)
        parsed_to = parse_utc_datetime(date_to)
        validate_archive_range("radar", parsed_from, parsed_to)
        frames = 1 if latest_only else max(1, int(frames))
        single_target_utc = None
        if latest_only:
            single_target_utc = parsed_from + (parsed_to - parsed_from) / 2

        # Single-frame mode should pick the scan closest to the selected time.
        # Build one or more download windows so we have nearby candidates even when
        # no file exists at the exact requested minute.
        download_windows = []
        if latest_only and single_target_utc is not None:
            half_span_minutes = 30
            near_start = single_target_utc - \
                timedelta(minutes=half_span_minutes)
            near_end = single_target_utc + timedelta(minutes=half_span_minutes)
            download_windows.append((near_start, near_end))

            if parsed_from != parsed_to:
                download_windows.append((parsed_from, parsed_to))
            else:
                day_start = single_target_utc.replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                day_end = day_start + timedelta(days=1) - timedelta(seconds=1)
                download_windows.append((day_start, day_end))
        else:
            download_windows.append((parsed_from, parsed_to))

        # Dedupe windows while preserving order.
        unique_windows = []
        seen_windows = set()
        for window_start, window_end in download_windows:
            window_key = (window_start, window_end)
            if window_key in seen_windows:
                continue
            seen_windows.add(window_key)
            unique_windows.append((window_start, window_end))

        parsed_styles = parse_styles(style_config)
        if not isinstance(parsed_styles, dict):
            parsed_styles = {}
        parsed_styles["show_counties"] = bool(show_counties)

        def download_progress(curr, total, *, message=None):
            active_tasks[request_id] = {
                "percent": int((curr / total) * 100) if total else 0,
                "message": message or f"Downloading {curr}/{total}",
                "stage": "download",
                "source": data_source,
            }

        def render_progress(curr, total):
            active_tasks[request_id] = {
                "percent": int((curr / total) * 100),
                "message": f"Rendering {curr}/{total}",
                "stage": "render",
                "source": data_source,
            }

        custom_extent = (
            (s, n, w, e) if all(v is not None for v in [n, s, e, w]) else None
        )
        site_candidates = [site]
        if custom_extent:
            center_lat = (custom_extent[0] +
                          custom_extent[1]) / 2  # (s + n) / 2
            center_lon = (custom_extent[2] +
                          custom_extent[3]) / 2  # (w + e) / 2
            site_candidates = find_nearest_radar_sites(
                center_lat, center_lon, limit=8)
            site = site_candidates[0]
            print(
                f"[INFO] Custom extent active — auto-selected closest radar: {site} "
                f"(fallback pool: {', '.join(site_candidates[:4])}{'...' if len(site_candidates) > 4 else ''})"
            )

        logo_path_to_use = LOGO_PATH
        if parsed_styles:
            lp = parsed_styles.get("logo_path")
            if lp:
                abs_lp = lp if os.path.isabs(
                    lp) else os.path.join(BASE_DIR, lp)
                if os.path.exists(abs_lp):
                    logo_path_to_use = abs_lp

        # Download archive files, trying nearby sites when custom extent is active.
        data_dir = None
        total_files = 0
        downloaded = 0
        resolved_product = product
        selected_files = None
        site_attempt_errors = []
        thredds_fallback_used = False

        if provider == "thredds":
            # Direct THREDDS download — skip NODD entirely
            try:
                _now_utc = datetime.now(timezone.utc)
                _thredds_lb = max(
                    0.5, (_now_utc - parsed_from).total_seconds() / 3600)
                _td, _tt, _ = radar_thredds_utils.download_radar_data(
                    level,
                    site,
                    product,
                    _thredds_lb,
                    os.path.join(BASE_DIR, "radar"),
                    download_progress,
                    latest_only=False,
                    start_time=parsed_from,
                    end_time=parsed_to,
                )
                if _tt > 0:
                    data_dir = _td
                    total_files = _tt
                    source_used = "thredds"
                    data_source = "ARCHIVE-THREDDS"
            except Exception as _te:
                print(f"[WARN] THREDDS archive download failed: {_te}")
        else:
            provider_attempts = [provider]
            if provider == "gcp":
                provider_attempts.append("aws")

            for idx, candidate_site in enumerate(site_candidates, start=1):
                candidate_error = None
                for provider_try in provider_attempts:
                    data_source = f"ARCHIVE-{provider_try.upper()}"
                    for window_start, window_end in unique_windows:
                        try:
                            (
                                candidate_dir,
                                candidate_total,
                                candidate_downloaded,
                                candidate_product,
                                candidate_selected_files,
                            ) = radar_archive_utils.download_archive_data(
                                level=level,
                                station_id=candidate_site,
                                product=product,
                                date_from=window_start,
                                date_to=window_end,
                                base_dir=os.path.join(BASE_DIR, "radar"),
                                progress_callback=download_progress,
                                provider=provider_try,
                                # Archive single-frame behavior is handled by renderer
                                # with closest-timestamp selection from downloaded files.
                                latest_only=False,
                            )
                            if candidate_total > 0:
                                data_dir = candidate_dir
                                total_files = candidate_total
                                downloaded = candidate_downloaded
                                resolved_product = candidate_product
                                selected_files = candidate_selected_files
                                if custom_extent and idx > 1:
                                    print(
                                        f"[INFO] Closest radar lacked archive data. Using fallback site {candidate_site}"
                                    )
                                if provider_try != provider:
                                    print(
                                        f"[INFO] Requested source {provider.upper()} had no files; "
                                        f"using {provider_try.upper()} fallback."
                                    )
                                source_used = provider_try
                                site = candidate_site
                                break
                        except Exception as window_error:
                            candidate_error = window_error

                    if total_files > 0:
                        break

                    if provider_try == "gcp" and provider == "gcp":
                        print(
                            "[INFO] No GCP archive files found for this window; "
                            "trying AWS fallback."
                        )

                if total_files > 0:
                    break

                if candidate_error is not None:
                    site_attempt_errors.append(
                        f"{candidate_site}: {candidate_error}")
                    if len(site_candidates) > 1:
                        print(
                            f"[WARN] Radar site {candidate_site} unavailable: {candidate_error}"
                        )
                else:
                    site_attempt_errors.append(f"{candidate_site}: no files")

            # NODD exhausted — try THREDDS as final fallback
            if total_files == 0:
                try:
                    _now_utc = datetime.now(timezone.utc)
                    _thredds_lb = max(
                        0.5, (_now_utc - parsed_from).total_seconds() / 3600
                    )
                    _td, _tt, _ = radar_thredds_utils.download_radar_data(
                        level,
                        site,
                        product,
                        _thredds_lb,
                        os.path.join(BASE_DIR, "radar"),
                        download_progress,
                        latest_only=False,
                        start_time=parsed_from,
                        end_time=parsed_to,
                    )
                    if _tt > 0:
                        data_dir = _td
                        total_files = _tt
                        source_used = "thredds"
                        data_source = "ARCHIVE-THREDDS"
                        thredds_fallback_used = True
                        print(
                            "[INFO] NODD archive exhausted; THREDDS fallback succeeded."
                        )
                except Exception as _te:
                    print(f"[WARN] THREDDS archive fallback failed: {_te}")

        if total_files == 0:
            if request_id in active_tasks:
                del active_tasks[request_id]
            attempted_sites = ", ".join(site_candidates)
            details = (
                " | ".join(site_attempt_errors[-3:]
                           ) if site_attempt_errors else ""
            )
            return {
                "status": "warning",
                "message": (
                    "No archive files found for the specified date range. "
                    f"Sites attempted: {attempted_sites}"
                    + (f" ({details})" if details else "")
                ),
                "data_source": data_source,
                "requested_source": requested_source,
                "source_used": source_used,
            }

        layered_result = radar_archive_utils.generate_archive_layers(
            level=level,
            data_dir=data_dir,
            product_label=resolved_product,
            logo_file=logo_path_to_use,
            station_id=site,
            sm_speed=sm_speed,
            sm_dir=sm_dir,
            frames=frames,
            custom_extent=custom_extent,
            progress_callback=render_progress,
            show_places=show_places,
            style_config=parsed_styles,
            selected_files=selected_files,
            latest_only=latest_only,
            target_time_utc=single_target_utc,
            request_id=request_id,
            user_tz=user_tz,
        )

        if request_id in active_tasks:
            del active_tasks[request_id]

        if not layered_result:
            return {
                "status": "error",
                "message": "Failed to generate layered radar archive output.",
                "data_source": data_source,
                "requested_source": requested_source,
                "source_used": source_used,
            }

        if render_mode == "layers":
            basemap_path = layered_result.get("basemap_path")
            static_overlay_path = layered_result.get("static_overlay_path")
            legend_overlay_path = layered_result.get("legend_overlay_path")
            counties_overlay_path = layered_result.get("counties_overlay_path")
            states_overlay_path = layered_result.get("states_overlay_path")
            rings_overlay_path = layered_result.get("rings_overlay_path")
            frame_entries = layered_result.get("frames", [])
            layer_dir = layered_result.get("layer_dir")
            manifest = layered_result.get("manifest") or {}
            map_extent = layered_result.get("map_extent")
            ui_margin_bottom = layered_result.get("ui_margin_bottom")
            map_axes_pos = layered_result.get("map_axes_pos")
            map_projection = layered_result.get("map_projection")
            extent_info = None
            if isinstance(map_extent, (list, tuple)) and len(map_extent) == 4:
                min_lon, max_lon, min_lat, max_lat = map_extent
                try:
                    extent_info = {
                        "min_lon": float(min_lon),
                        "max_lon": float(max_lon),
                        "min_lat": float(min_lat),
                        "max_lat": float(max_lat),
                        "lon_span": float(max_lon) - float(min_lon),
                        "lat_span": float(max_lat) - float(min_lat),
                    }
                except (TypeError, ValueError):
                    extent_info = None
            if extent_info is not None:
                try:
                    axes_text = (
                        ",".join(f"{float(v):.3f}" for v in map_axes_pos)
                        if isinstance(map_axes_pos, (list, tuple))
                        else "n/a"
                    )
                except (TypeError, ValueError):
                    axes_text = "n/a"
                print(
                    "[INFO] Layered extent "
                    f"lon={extent_info['min_lon']:.3f}..{extent_info['max_lon']:.3f} "
                    f"(span {extent_info['lon_span']:.3f}), "
                    f"lat={extent_info['min_lat']:.3f}..{extent_info['max_lat']:.3f} "
                    f"(span {extent_info['lat_span']:.3f}), "
                    f"proj={map_projection or 'unknown'}, "
                    f"ui_margin_bottom={float(ui_margin_bottom or 0.0):.3f}, "
                    f"map_axes_pos=[{axes_text}]"
                )
            if not basemap_path or not frame_entries:
                return {
                    "status": "warning",
                    "message": "No layered frames were generated for the requested range.",
                    "data_source": data_source,
                    "requested_source": requested_source,
                    "source_used": source_used,
                }

            basemap_abs = os.path.normpath(basemap_path)
            radar_root_abs = os.path.normpath(DIRS["radar"])
            basemap_cache_root_abs = os.path.normpath(
                os.path.join(BASE_DIR, "basemap_cache")
            )

            def _resolve_layer_url(abs_path):
                if not abs_path:
                    return None
                norm_path = os.path.normpath(abs_path)
                if norm_path.startswith(radar_root_abs):
                    rel = os.path.relpath(
                        norm_path, radar_root_abs).replace("\\", "/")
                    return f"/img/{rel}"
                if norm_path.startswith(basemap_cache_root_abs):
                    rel = os.path.relpath(norm_path, basemap_cache_root_abs).replace(
                        "\\", "/"
                    )
                    return f"/img/basemap_cache/{rel}"
                return None

            def _resolve_frame_layer_rel(abs_path):
                if not abs_path:
                    return None
                norm_path = os.path.normpath(abs_path)
                if norm_path.startswith(radar_root_abs):
                    return os.path.relpath(norm_path, radar_root_abs).replace("\\", "/")
                if norm_path.startswith(basemap_cache_root_abs):
                    rel = os.path.relpath(norm_path, basemap_cache_root_abs).replace(
                        "\\", "/"
                    )
                    return f"basemap_cache/{rel}"
                return None

            if basemap_abs.startswith(radar_root_abs):
                basemap_rel = os.path.relpath(basemap_abs, radar_root_abs).replace(
                    "\\", "/"
                )
                basemap_url = f"/img/{basemap_rel}"
            elif basemap_abs.startswith(basemap_cache_root_abs):
                basemap_rel = os.path.relpath(
                    basemap_abs, basemap_cache_root_abs
                ).replace("\\", "/")
                basemap_url = f"/img/basemap_cache/{basemap_rel}"
            else:
                return {
                    "status": "error",
                    "message": "Layered basemap path is outside allowed static directories.",
                    "data_source": data_source,
                    "requested_source": requested_source,
                    "source_used": source_used,
                }
            static_overlay_rel = None
            if static_overlay_path:
                static_overlay_rel = os.path.relpath(
                    static_overlay_path, DIRS["radar"]
                ).replace("\\", "/")
            legend_overlay_rel = None
            if legend_overlay_path:
                legend_overlay_rel = os.path.relpath(
                    legend_overlay_path, DIRS["radar"]
                ).replace("\\", "/")

            counties_overlay_url = _resolve_layer_url(counties_overlay_path)
            states_overlay_url = _resolve_layer_url(states_overlay_path)
            rings_overlay_url = _resolve_layer_url(rings_overlay_path)
            frames_payload = []
            for entry in frame_entries:
                frame_path = entry.get("path")
                if not frame_path:
                    continue
                rel_path = os.path.relpath(
                    frame_path, DIRS["radar"]).replace("\\", "/")
                radar_rel = None
                alerts_rel = None
                cities_rel = None
                counties_rel = None
                rings_rel = None
                legend_rel = None
                hud_right_rel = None
                if entry.get("radar_path"):
                    radar_rel = os.path.relpath(
                        entry["radar_path"], DIRS["radar"]
                    ).replace("\\", "/")
                if entry.get("alerts_path"):
                    alerts_rel = os.path.relpath(
                        entry["alerts_path"], DIRS["radar"]
                    ).replace("\\", "/")
                if entry.get("cities_path"):
                    cities_rel = os.path.relpath(
                        entry["cities_path"], DIRS["radar"]
                    ).replace("\\", "/")
                if entry.get("counties_path"):
                    counties_rel = _resolve_frame_layer_rel(
                        entry["counties_path"])
                states_rel = None
                if entry.get("states_path"):
                    states_rel = _resolve_frame_layer_rel(entry["states_path"])
                if entry.get("rings_path"):
                    rings_rel = _resolve_frame_layer_rel(entry["rings_path"])
                if entry.get("legend_path"):
                    legend_rel = os.path.relpath(
                        entry["legend_path"], DIRS["radar"]
                    ).replace("\\", "/")
                if entry.get("hud_right_path"):
                    hud_right_rel = os.path.relpath(
                        entry["hud_right_path"], DIRS["radar"]
                    ).replace("\\", "/")
                frames_payload.append(
                    {
                        "index": int(entry.get("index", len(frames_payload))),
                        "url": f"/img/{rel_path}",
                        "radar_url": f"/img/{radar_rel}" if radar_rel else None,
                        "alerts_url": f"/img/{alerts_rel}" if alerts_rel else None,
                        "cities_url": f"/img/{cities_rel}" if cities_rel else None,
                        "counties_url": f"/img/{counties_rel}"
                        if counties_rel
                        else None,
                        "states_url": f"/img/{states_rel}" if states_rel else None,
                        "rings_url": f"/img/{rings_rel}" if rings_rel else None,
                        "legend_url": f"/img/{legend_rel}" if legend_rel else None,
                        "hud_right_url": f"/img/{hud_right_rel}"
                        if hud_right_rel
                        else None,
                        "timestamp_utc": entry.get("timestamp_utc", ""),
                        "timestamp_local": entry.get("timestamp_local", ""),
                    }
                )

            if not frames_payload:
                return {
                    "status": "warning",
                    "message": "No layered frames were generated for the requested range.",
                    "data_source": data_source,
                    "requested_source": requested_source,
                    "source_used": source_used,
                }

            layer_rel = None
            if layer_dir:
                layer_rel = os.path.relpath(
                    layer_dir, DIRS["radar"]).replace("\\", "/")

            first_frame = frames_payload[0]
            layers_payload = {
                "basemap": basemap_url,
                "radar": first_frame.get("radar_url"),
                "alerts": first_frame.get("alerts_url"),
                "cities": first_frame.get("cities_url"),
                "counties": first_frame.get("counties_url") or counties_overlay_url,
                "states": first_frame.get("states_url") or states_overlay_url,
                "range_rings": first_frame.get("rings_url") or rings_overlay_url,
                "legend": first_frame.get("legend_url")
                or (f"/img/{legend_overlay_rel}" if legend_overlay_rel else None),
                "hud_right": first_frame.get("hud_right_url"),
            }
            layers_payload = {k: v for k, v in layers_payload.items() if v}
            layer_defs_payload = [
                {
                    "id": "radar",
                    "label": "Radar Layer",
                    "default_visible": True,
                    "default_opacity": 1,
                    "sort": 10,
                },
                {
                    "id": "alerts",
                    "label": "Alerts Layer",
                    "default_visible": True,
                    "default_opacity": 0.9,
                    "sort": 20,
                },
                {
                    "id": "cities",
                    "label": "Cities Layer",
                    "default_visible": True,
                    "default_opacity": 1,
                    "sort": 30,
                },
                {
                    "id": "counties",
                    "label": "County Lines Layer",
                    "default_visible": True,
                    "default_opacity": 1,
                    "sort": 40,
                },
                {
                    "id": "states",
                    "label": "State Outlines Layer",
                    "default_visible": True,
                    "default_opacity": 1,
                    "sort": 45,
                },
                {
                    "id": "range_rings",
                    "label": "Range Rings Layer",
                    "default_visible": True,
                    "default_opacity": 1,
                    "sort": 50,
                },
            ]
            layer_defs_payload = [
                item for item in layer_defs_payload if item["id"] in layers_payload
            ]

            return {
                "status": "success",
                "message": "Radar archive layers generated."
                + (
                    " Note: THREDDS fallback used — data limited to recent scans only."
                    if thredds_fallback_used
                    else ""
                ),
                "image_url": frames_payload[0]["url"],
                "basemap_url": basemap_url,
                "static_overlay_url": f"/img/{static_overlay_rel}"
                if static_overlay_rel
                else None,
                "legend_overlay_url": f"/img/{legend_overlay_rel}"
                if legend_overlay_rel
                else None,
                "frames": frames_payload,
                "frame_count": len(frames_payload),
                "layers_path": layer_rel,
                "session_expires_utc": manifest.get("expires_utc"),
                "output_mode": "layers",
                "layers": layers_payload,
                "layer_defs": layer_defs_payload,
                "data_source": data_source,
                "requested_source": requested_source,
                "source_used": source_used,
                "site_used": site,
                "extent": extent_info,
                "ui_margin_bottom": ui_margin_bottom,
                "map_axes_pos": map_axes_pos,
            }

        layer_dir = layered_result.get("layer_dir")
        if not layer_dir:
            return {
                "status": "error",
                "message": "Layered export directory was not generated.",
                "data_source": data_source,
                "requested_source": requested_source,
                "source_used": source_used,
            }

        movie_path, frame_count = radar_archive_utils.export_layered_animation(
            layer_dir=layer_dir,
            fps=max(1, int(fps or 4)),
        )
        if movie_path is None:
            return {
                "status": "error",
                "message": "Failed to generate archive animation.",
                "data_source": data_source,
                "requested_source": requested_source,
                "source_used": source_used,
            }

        rel_path = os.path.relpath(
            movie_path, DIRS["radar"]).replace("\\", "/")
        layer_rel = os.path.relpath(
            layer_dir, DIRS["radar"]).replace("\\", "/")
        return {
            "status": "success",
            "image_url": f"/img/{rel_path}",
            "layers_path": layer_rel,
            "frame_count": int(frame_count),
            "data_source": data_source,
            "requested_source": requested_source,
            "source_used": source_used,
            "output_mode": "video",
            "site_used": site,
            "message": "Radar archive animation generated."
            + (
                " Note: THREDDS fallback used — data limited to recent scans only."
                if thredds_fallback_used
                else ""
            ),
        }

    except Exception as e:
        import traceback

        traceback.print_exc()
        if request_id:
            active_tasks[request_id] = {
                "percent": 0,
                "message": f"Error: {str(e)}",
                "stage": "error",
                "source": data_source if "data_source" in locals() else None,
            }
        return {
            "status": "error",
            "message": str(e),
            "data_source": data_source,
            "requested_source": requested_source,
            "source_used": source_used,
        }


def get_satellite_latest(
    request_id: str,
    sat_id: str = "goes19",
    sector: str = "CONUS",
    channel: str = "Channel13",
    lookback: int = 2,
    frames: int = 1,
    fps: int = 4,
    show_places: bool = False,
    style_config: Optional[str] = None,
    n: Optional[float] = None,
    s: Optional[float] = None,
    e: Optional[float] = None,
    w: Optional[float] = None,
    source: str = "auto",
    latest_only: bool = False,
):
    try:
        requested_source = str(source or "auto").strip().lower()
        if requested_source not in {"auto", "aws", "gcp", "thredds"}:
            return {
                "status": "error",
                "message": "Invalid source. Use auto, aws, gcp, or thredds.",
                "data_source": "UNKNOWN",
            }

        sat_module = satellite_utils
        provider = "aws"
        if requested_source == "thredds":
            sat_module = satellite_thredds_utils
            data_source = "THREDDS"
        elif requested_source in {"aws", "gcp"}:
            if not USING_NODD:
                return {
                    "status": "error",
                    "message": "NODD module unavailable. AWS/GCP sources are not available.",
                    "data_source": "THREDDS",
                }
            provider = requested_source
            data_source = f"NODD-{provider.upper()}"
        else:
            data_source = "NODD-AWS" if USING_NODD else "THREDDS"
        parsed_styles = parse_styles(style_config)
        active_tasks[request_id] = {
            "percent": 0,
            "message": "Initializing...",
            "stage": "init",
        }

        def download_progress(curr, total):
            active_tasks[request_id] = {
                "percent": int((curr / total) * 100),
                "message": f"Downloading {curr}/{total}",
                "stage": "download",
                "source": data_source,
            }

        def render_progress(curr, total):
            active_tasks[request_id] = {
                "percent": int((curr / total) * 100),
                "message": f"Rendering {curr}/{total}",
                "stage": "render",
                "source": data_source,
            }

        custom_extent = (
            (s, n, w, e) if all(v is not None for v in [n, s, e, w]) else None
        )
        if custom_extent:
            sector = "CONUS"  # Force CONUS when custom extent is active
        frames = 1 if latest_only else max(1, int(frames))
        try:
            if sat_module is satellite_thredds_utils:
                data_dir, _, _ = sat_module.download_goes_data(
                    sat_id,
                    sector,
                    channel,
                    lookback,
                    os.path.join(BASE_DIR, "satellite"),
                    download_progress,
                    latest_only=latest_only,
                )
            else:
                data_dir, _, _ = sat_module.download_goes_data(
                    sat_id,
                    sector,
                    channel,
                    lookback,
                    os.path.join(BASE_DIR, "satellite"),
                    download_progress,
                    provider=provider,
                    latest_only=latest_only,
                )
        except Exception as nodd_error:
            if requested_source == "auto" and USING_NODD:
                print(
                    f"[WARN] NODD satellite failed, falling back to THREDDS: {nodd_error}"
                )
                sat_module = satellite_thredds_utils
                data_source = "THREDDS"
                data_dir, _, _ = sat_module.download_goes_data(
                    sat_id,
                    sector,
                    channel,
                    lookback,
                    os.path.join(BASE_DIR, "satellite"),
                    download_progress,
                    latest_only=latest_only,
                )
            else:
                raise

        if data_dir is None and requested_source == "auto" and USING_NODD:
            print("[WARN] NODD satellite returned no data, trying THREDDS fallback")
            sat_module = satellite_thredds_utils
            data_source = "THREDDS"
            data_dir, _, _ = sat_module.download_goes_data(
                sat_id,
                sector,
                channel,
                lookback,
                os.path.join(BASE_DIR, "satellite"),
                download_progress,
            )

        # Check if data was found
        if data_dir is None:
            if request_id in active_tasks:
                del active_tasks[request_id]
            return {
                "status": "error",
                "message": f"No satellite data found for {sat_id} {sector} {channel}. Data may not be available from THREDDS yet. Try GOES-19 for CONUS or GOES-18 for West Coast.",
                "data_source": data_source,
            }

        # Use custom logo path from style config, or fall back to default
        logo_path_to_use = resolve_logo_path(
            parsed_styles, BASE_DIR, LOGO_PATH)

        movie_path, image_path = sat_module.generate_satellite_animation(
            sat_id=sat_id,
            region_name=sector,
            data_dir=data_dir,
            channel_key=channel,
            max_frames=frames,
            fps=fps,
            logo_file=logo_path_to_use,
            custom_extent=custom_extent,
            progress_callback=render_progress,
            show_places=show_places,
            style_config=parsed_styles,
        )

        # Check if animation generation succeeded
        if movie_path is None and image_path is None:
            if request_id in active_tasks:
                del active_tasks[request_id]
            return {
                "status": "error",
                "message": "Failed to generate satellite animation. Check server logs for details.",
                "data_source": data_source,
            }

        result_path = movie_path if frames > 1 else image_path
        if request_id in active_tasks:
            del active_tasks[request_id]
        return {
            "status": "success",
            "image_url": f"/img/satellite/{os.path.relpath(result_path, DIRS['satellite']).replace('\\', '/')}",
            "data_source": data_source,
        }
    except Exception as e:
        import traceback

        error_detail = f"{type(e).__name__}: {str(e)}"
        print(f"[ERROR] Satellite endpoint error: {error_detail}")
        traceback.print_exc()
        if request_id:
            active_tasks[request_id] = {
                "percent": 0,
                "message": f"Error: {error_detail}",
                "stage": "error",
                "source": data_source if "data_source" in locals() else None,
            }
        return {
            "status": "error",
            "message": error_detail,
            "data_source": data_source if "data_source" in locals() else None,
        }


@app.get("/api/satellite/current")
def get_satellite_current(
    request_id: str = "",
    sat_id: str = "goes16",
    sector: str = "CONUS",
    channel: str = "Channel13",
    lookback: int = 2,
    frames: int = 1,
    fps: int = 4,
    show_places: bool = False,
    style_config: Optional[str] = None,
    n: Optional[float] = None,
    s: Optional[float] = None,
    e: Optional[float] = None,
    w: Optional[float] = None,
    source: str = "auto",
    latest_only: bool = False,
):
    response = get_satellite_latest(
        request_id=request_id,
        sat_id=sat_id,
        sector=sector,
        channel=channel,
        lookback=lookback,
        fps=fps,
        frames=frames,
        show_places=show_places,
        style_config=style_config,
        n=n,
        s=s,
        e=e,
        w=w,
        source=source,
        latest_only=latest_only,
    )
    return attach_mode_and_source(response, "recent")


@app.get("/api/satellite/archive")
def get_satellite_archive_endpoint(
    request_id: str = "",
    sat_id: str = "goes16",
    sector: str = "CONUS",
    channel: str = "Channel13",
    date_from: str = "",
    date_to: str = "",
    frames: int = 240,
    fps: int = 4,
    show_places: bool = False,
    user_tz: str = "America/New_York",
    style_config: Optional[str] = None,
    n: Optional[float] = None,
    s: Optional[float] = None,
    e: Optional[float] = None,
    w: Optional[float] = None,
    source: str = "auto",
    latest_only: bool = False,
    view_mode: str = "video",
):
    archive_source = str(source or "auto").strip().lower()
    if archive_source == "auto":
        archive_source = "aws"

    response = get_satellite_archive(
        request_id=request_id,
        sat_id=sat_id,
        sector=sector,
        channel=channel,
        date_from=date_from,
        date_to=date_to,
        frames=frames,
        fps=fps,
        show_places=show_places,
        user_tz=user_tz,
        style_config=style_config,
        n=n,
        s=s,
        e=e,
        w=w,
        source=archive_source,
        latest_only=latest_only,
        view_mode=view_mode,
    )
    return attach_mode_and_source(response, "archive")


@app.get("/api/satellite/archive/export-animation")
def export_satellite_archive_animation(
    frames_path: str,
    fps: int = 4,
):
    if satellite_archive_utils is None:
        return {
            "status": "error",
            "message": "Satellite archive module is not available.",
            "data_source": "ARCHIVE",
        }

    requested = str(frames_path or "").strip().replace("\\", "/")
    if not requested:
        return {
            "status": "error",
            "message": "frames_path is required.",
            "data_source": "ARCHIVE",
        }
    if requested.startswith("/") or ".." in requested:
        return {
            "status": "error",
            "message": "Invalid frames_path.",
            "data_source": "ARCHIVE",
        }

    sat_archive_root = os.path.normpath(DIRS["satellite_archive"])
    target_path = os.path.normpath(os.path.join(sat_archive_root, requested))
    if not (target_path.startswith(sat_archive_root) and os.path.exists(target_path)):
        return {
            "status": "error",
            "message": "Frame directory not found.",
            "data_source": "ARCHIVE",
        }

    frame_dir = None
    frame_paths = None
    output_dir = None

    if os.path.isfile(target_path):
        if not target_path.lower().endswith(".json"):
            return {
                "status": "error",
                "message": "frames_path must point to a frame directory or scrubber manifest JSON.",
                "data_source": "ARCHIVE",
            }
        try:
            with open(target_path, "r", encoding="utf-8") as manifest_file:
                payload = json.load(manifest_file)
            names = payload.get("frame_files") if isinstance(
                payload, dict) else None
            if not isinstance(names, list):
                names = []
            output_dir = os.path.dirname(target_path)
            frame_paths = []
            for name in names:
                candidate = os.path.normpath(
                    os.path.join(output_dir, os.path.basename(str(name)))
                )
                if candidate.startswith(sat_archive_root) and os.path.isfile(candidate):
                    frame_paths.append(candidate)
        except Exception as manifest_error:
            return {
                "status": "error",
                "message": f"Invalid scrubber manifest: {manifest_error}",
                "data_source": "ARCHIVE",
            }
        if not frame_paths:
            return {
                "status": "error",
                "message": "No frame files found in scrubber manifest.",
                "data_source": "ARCHIVE",
            }
    else:
        frame_dir = target_path
        output_dir = frame_dir

    movie_path, frame_count = satellite_archive_utils.export_scrubber_animation(
        frame_dir=frame_dir,
        output_dir=output_dir,
        fps=max(1, int(fps or 4)),
        frame_paths=frame_paths,
    )
    if not movie_path:
        return {
            "status": "error",
            "message": "Unable to export satellite animation.",
            "data_source": "ARCHIVE",
        }

    rel_path = os.path.relpath(movie_path, sat_archive_root).replace("\\", "/")
    return {
        "status": "success",
        "message": f"Exported satellite animation ({frame_count} frames).",
        "image_url": f"/img/satellite_archive/{rel_path}",
        "output_mode": "video",
        "data_source": "ARCHIVE",
    }


@app.get("/api/satellite")
def get_satellite(
    request_id: str = "",
    sat_id: str = "goes16",
    sector: str = "CONUS",
    channel: str = "Channel13",
    lookback: int = 2,
    frames: int = 1,
    fps: int = 4,
    show_places: bool = False,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    user_tz: str = "America/New_York",
    style_config: Optional[str] = None,
    n: Optional[float] = None,
    s: Optional[float] = None,
    e: Optional[float] = None,
    w: Optional[float] = None,
    source: str = "auto",
    latest_only: bool = False,
):
    """Deprecated: Use /api/satellite/current or /api/satellite/archive."""
    data_mode = infer_data_mode(date_from, date_to)
    if data_mode == "recent":
        return get_satellite_current(
            request_id=request_id,
            sat_id=sat_id,
            sector=sector,
            channel=channel,
            lookback=lookback,
            frames=frames,
            fps=fps,
            show_places=show_places,
            style_config=style_config,
            n=n,
            s=s,
            e=e,
            w=w,
            source=source,
            latest_only=latest_only,
        )

    return get_satellite_archive_endpoint(
        request_id=request_id,
        sat_id=sat_id,
        sector=sector,
        channel=channel,
        date_from=date_from or "",
        date_to=date_to or "",
        frames=frames,
        fps=fps,
        show_places=show_places,
        user_tz=user_tz,
        style_config=style_config,
        n=n,
        s=s,
        e=e,
        w=w,
        source=source,
        latest_only=latest_only,
    )


def get_satellite_archive(
    request_id: str = "",
    sat_id: str = "goes19",
    sector: str = "CONUS",
    channel: str = "Channel13",
    date_from: str = "",
    date_to: str = "",
    fps: int = 4,
    frames: int = 240,
    show_places: bool = False,
    user_tz: str = "America/New_York",
    style_config: Optional[str] = None,
    n: Optional[float] = None,
    s: Optional[float] = None,
    e: Optional[float] = None,
    w: Optional[float] = None,
    source: str = "aws",
    latest_only: bool = False,
    view_mode: str = "video",
):
    data_source = "UNKNOWN"
    if satellite_archive_utils is None:
        return {
            "status": "error",
            "message": "Satellite archive module is not available.",
            "data_source": data_source,
        }

    try:
        requested_source = str(source or "aws").strip().lower()
        if requested_source not in {"aws", "gcp"}:
            return {
                "status": "error",
                "message": "Invalid source. Use aws or gcp.",
                "data_source": data_source,
            }

        if not date_from or not date_to:
            return {
                "status": "error",
                "message": "Both date_from and date_to are required.",
                "data_source": data_source,
            }

        parsed_styles = parse_styles(style_config)
        if request_id:
            active_tasks[request_id] = {
                "percent": 0,
                "message": "Initializing...",
                "stage": "init",
            }

        def download_progress(curr, total):
            percent = int((curr / total) * 100) if total else 0
            if request_id:
                active_tasks[request_id] = {
                    "percent": percent,
                    "message": f"Downloading {curr}/{total}",
                    "stage": "download",
                    "source": data_source,
                }

        def render_progress(curr, total):
            percent = int((curr / total) * 100) if total else 0
            if request_id:
                active_tasks[request_id] = {
                    "percent": percent,
                    "message": f"Rendering {curr}/{total}",
                    "stage": "render",
                    "source": data_source,
                }

        custom_extent = (
            (s, n, w, e) if all(v is not None for v in [n, s, e, w]) else None
        )
        if custom_extent:
            sector = "CONUS"  # Force CONUS when custom extent is active

        logo_path_to_use = resolve_logo_path(
            parsed_styles, BASE_DIR, LOGO_PATH)

        provider_candidates = [requested_source]

        last_error = None
        for provider in provider_candidates:
            data_source = f"NODD-{provider.upper()}"
            try:
                movie_path, preview_path, message = (
                    satellite_archive_utils.generate_satellite_archive_animation(
                        sat_id=sat_id,
                        sector=sector,
                        channel_key=channel,
                        date_from=date_from,
                        date_to=date_to,
                        fps=fps,
                        frames=frames,
                        logo_file=logo_path_to_use,
                        style_config=parsed_styles,
                        progress_callback=render_progress,
                        download_progress=download_progress,
                        custom_extent=custom_extent,
                        show_places=show_places,
                        provider=provider,
                        user_tz=user_tz,
                        latest_only=latest_only,
                        view_mode=view_mode,
                    )
                )

                # ── Scrubber mode: movie_path is a dict manifest ──
                if (
                    isinstance(movie_path, dict)
                    and movie_path.get("mode") == "scrubber"
                ):
                    manifest = movie_path
                    sat_archive_dir = DIRS["satellite_archive"]
                    frame_items = []
                    for entry in manifest["frames"]:
                        rel = os.path.relpath(entry["path"], sat_archive_dir).replace(
                            "\\", "/"
                        )
                        frame_item = {
                            "url": f"/img/satellite_archive/{rel}",
                            "timestamp_utc": entry["timestamp_utc"],
                            "timestamp_local": entry["timestamp_local"],
                        }
                        # Add layer URLs if available
                        if "layers" in entry and entry["layers"]:
                            frame_item["layers"] = {}
                            for layer_name, layer_filename in entry["layers"].items():
                                # Construct relative path from satellite_archive to layer file
                                layer_rel = os.path.relpath(
                                    os.path.join(os.path.dirname(
                                        entry["path"]), layer_filename),
                                    sat_archive_dir
                                ).replace("\\", "/")
                                frame_item["layers"][
                                    layer_name] = f"/img/satellite_archive/{layer_rel}"
                        frame_items.append(frame_item)
                    frames_ref = manifest.get(
                        "frames_ref") or manifest.get("frame_dir")
                    frames_dir_rel = os.path.relpath(
                        frames_ref, sat_archive_dir
                    ).replace("\\", "/")
                    if request_id and request_id in active_tasks:
                        del active_tasks[request_id]
                    return {
                        "status": "success",
                        "view_mode": "scrubber",
                        "frames": frame_items,
                        "frames_path": frames_dir_rel,
                        "total": manifest["total"],
                        "fps": manifest["fps"],
                        "message": message,
                        "data_source": data_source,
                    }

                if movie_path is None and preview_path is None:
                    last_error = message or "No archive output generated."
                    continue

                result_path = movie_path or preview_path
                if request_id and request_id in active_tasks:
                    del active_tasks[request_id]
                rel_path = os.path.relpath(
                    result_path, DIRS["satellite_archive"]
                ).replace("\\", "/")
                return {
                    "status": "success",
                    "image_url": f"/img/satellite_archive/{rel_path}",
                    "message": message,
                    "data_source": data_source,
                }
            except Exception as provider_error:
                last_error = f"{type(provider_error).__name__}: {provider_error}"
                continue

        if request_id and request_id in active_tasks:
            del active_tasks[request_id]
        return {
            "status": "error",
            "message": last_error or "No archive data found from selected provider(s).",
            "data_source": data_source,
        }

    except Exception as e:
        import traceback

        traceback.print_exc()
        if request_id and request_id in active_tasks:
            del active_tasks[request_id]
        return {
            "status": "error",
            "message": f"{type(e).__name__}: {e}",
            "data_source": data_source,
        }


@app.post("/api/purge")
def purge_old_files(hours: float = 168, categories: str = ""):
    """Purge downloaded data and generated images older than N hours. 0 = purge all."""
    if hours < 0:
        raise HTTPException(status_code=400, detail="hours must be >= 0")

    days = hours / 24.0  # for modules that expect days
    results = {}
    valid_categories = {
        "radar",
        "satellite",
        "surface",
        "alerts",
        "mrms",
        "spc",
    }
    if categories and categories.strip():
        requested = {
            c.strip().lower() for c in categories.split(",") if c and c.strip()
        }
        selected_categories = requested & valid_categories
        if not selected_categories:
            raise HTTPException(
                status_code=400,
                detail=f"No valid categories selected. Valid categories: {sorted(valid_categories)}",
            )
    else:
        selected_categories = valid_categories

    # Directories that must never be purged (pre-rendered basemap caches).
    _PURGE_SKIP_DIRS = {"basemap_cache"}

    def _purge_targets(cutoff_ts: float, targets: list[str]):
        purged = 0
        errors = 0
        deduped_targets = []
        for t in targets:
            if t and t not in deduped_targets:
                deduped_targets.append(t)

        for target in deduped_targets:
            if not os.path.exists(target):
                continue
            for root, dirs, files in os.walk(target, topdown=False):
                # Never touch files inside protected cache directories
                if _PURGE_SKIP_DIRS & set(root.replace("\\", "/").split("/")):
                    continue
                for name in files:
                    fp = os.path.join(root, name)
                    try:
                        if os.path.getmtime(fp) < cutoff_ts:
                            os.remove(fp)
                            purged += 1
                    except Exception:
                        errors += 1
                if not os.listdir(root) and root != target:
                    try:
                        os.rmdir(root)
                    except Exception:
                        pass
        return purged, errors

    # Radar purge
    if "radar" in selected_categories:
        try:
            count, errs = radar_utils.purge_old_files(days, DIRS["radar"])
            cutoff = _time.time() - (hours * 3600)
            archive_count, archive_errs = _purge_targets(
                cutoff,
                [
                    os.path.join(
                        BASE_DIR, "radar", "radar_archive", "radar_level2_downloads"
                    ),
                    os.path.join(
                        BASE_DIR, "radar", "radar_archive", "radar_level2_images"
                    ),
                    os.path.join(
                        BASE_DIR, "radar", "radar_archive", "radar_level3_downloads"
                    ),
                    os.path.join(
                        BASE_DIR, "radar", "radar_archive", "radar_level3_images"
                    ),
                ],
            )
            results["radar"] = {
                "purged": count + archive_count,
                "errors": errs + archive_errs,
            }
        except Exception as e:
            results["radar"] = {"purged": 0, "errors": 0, "message": str(e)}
    else:
        results["radar"] = {"purged": 0, "errors": 0, "skipped": True}

    # Satellite purge (downloads and images)
    if "satellite" in selected_categories:
        try:
            sat_base = os.path.join(BASE_DIR, "satellite")
            cutoff = _time.time() - (hours * 3600)
            # Include downloads, images, and archive folders
            targets = [
                os.path.join(sat_base, "satellite_downloads"),
                os.path.join(sat_base, "satellite_images"),
                os.path.join(sat_base, "satellite_archive_images"),
                os.path.join(sat_base, "satellite_archive",
                             "satellite_downloads"),
                DIRS.get("satellite_archive"),
            ]
            sat_purged, sat_errors = _purge_targets(cutoff, targets)
            results["satellite"] = {"purged": sat_purged, "errors": sat_errors}
        except Exception as e:
            results["satellite"] = {"purged": 0,
                                    "errors": 0, "message": str(e)}
    else:
        results["satellite"] = {"purged": 0, "errors": 0, "skipped": True}

    # Surface purge (images and raw data)
    if "surface" in selected_categories:
        try:
            cutoff = _time.time() - (hours * 3600)
            surf_purged = 0
            surf_errors = 0
            # Target both images and raw data folders
            targets = [
                DIRS["surface"],
                DIRS["surface_archive"],
                os.path.join(BASE_DIR, "surface", "surface_data"),
                os.path.join(BASE_DIR, "surface",
                             "surface_archive", "surface_data"),
            ]
            for target in targets:
                if not os.path.exists(target):
                    continue
                for root, dirs, files in os.walk(target, topdown=False):
                    for name in files:
                        fp = os.path.join(root, name)
                        try:
                            if os.path.getmtime(fp) < cutoff:
                                os.remove(fp)
                                surf_purged += 1
                        except Exception:
                            surf_errors += 1
                    if not os.listdir(root) and root != target:
                        try:
                            os.rmdir(root)
                        except Exception:
                            pass
            results["surface"] = {"purged": surf_purged, "errors": surf_errors}
        except Exception as e:
            results["surface"] = {"purged": 0, "errors": 0, "message": str(e)}
    else:
        results["surface"] = {"purged": 0, "errors": 0, "skipped": True}

    # Alerts purge (images and raw data)
    if "alerts" in selected_categories:
        try:
            cutoff = _time.time() - (hours * 3600)
            alert_purged = 0
            alert_errors = 0
            # Target images, raw data, and archives
            targets = [
                DIRS["alerts"],
                DIRS["alerts_archive"],
                os.path.join(BASE_DIR, "alerts", "alert_data"),
                os.path.join(BASE_DIR, "alerts",
                             "alerts_archive", "alert_data"),
                os.path.join(
                    BASE_DIR, "alerts", "alert_archive"
                ),  # Legacy/Structure variation
            ]
            for target in targets:
                if not os.path.exists(target):
                    continue
                for root, dirs, files in os.walk(target, topdown=False):
                    for name in files:
                        fp = os.path.join(root, name)
                        try:
                            if os.path.getmtime(fp) < cutoff:
                                os.remove(fp)
                                alert_purged += 1
                        except Exception:
                            alert_errors += 1
                    if not os.listdir(root) and root != target:
                        try:
                            os.rmdir(root)
                        except Exception:
                            pass
            results["alerts"] = {
                "purged": alert_purged, "errors": alert_errors}
        except Exception as e:
            results["alerts"] = {"purged": 0, "errors": 0, "message": str(e)}
    else:
        results["alerts"] = {"purged": 0, "errors": 0, "skipped": True}

    # SPC purge (images and archive images)
    if "spc" in selected_categories:
        try:
            cutoff = _time.time() - (hours * 3600)
            spc_purged = 0
            spc_errors = 0
            targets = [DIRS["spc"], DIRS["spc_archive"]]
            for target in targets:
                if not os.path.exists(target):
                    continue
                for root, dirs, files in os.walk(target, topdown=False):
                    for name in files:
                        fp = os.path.join(root, name)
                        try:
                            if os.path.getmtime(fp) < cutoff:
                                os.remove(fp)
                                spc_purged += 1
                        except Exception:
                            spc_errors += 1
                    if not os.listdir(root) and root != target:
                        try:
                            os.rmdir(root)
                        except Exception:
                            pass
            results["spc"] = {"purged": spc_purged, "errors": spc_errors}
        except Exception as e:
            results["spc"] = {"purged": 0, "errors": 0, "message": str(e)}
    else:
        results["spc"] = {"purged": 0, "errors": 0, "skipped": True}

    # MRMS purge (downloads and generated images)
    if "mrms" in selected_categories:
        try:
            cutoff = _time.time() - (hours * 3600)
            mrms_purged = 0
            mrms_errors = 0
            targets = [
                os.path.join(BASE_DIR, "mrms", "mrms_downloads"),
                DIRS["mrms"],
            ]
            for target in targets:
                if not os.path.exists(target):
                    continue
                for root, dirs, files in os.walk(target, topdown=False):
                    for name in files:
                        fp = os.path.join(root, name)
                        try:
                            if os.path.getmtime(fp) < cutoff:
                                os.remove(fp)
                                mrms_purged += 1
                        except Exception:
                            mrms_errors += 1
                    if not os.listdir(root) and root != target:
                        try:
                            os.rmdir(root)
                        except Exception:
                            pass
            results["mrms"] = {"purged": mrms_purged, "errors": mrms_errors}
        except Exception as e:
            results["mrms"] = {"purged": 0, "errors": 0, "message": str(e)}
    else:
        results["mrms"] = {"purged": 0, "errors": 0, "skipped": True}

    total_purged = sum(r["purged"] for r in results.values())
    total_errors = sum(r["errors"] for r in results.values())
    return {
        "status": "success",
        "hours": hours,
        "total_purged": total_purged,
        "total_errors": total_errors,
        "details": results,
    }


# ═══════════════════════════════════════════════════════════════════════════
# UNIFIED WEATHER ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/api/weather/spc-items")
def api_weather_spc_items(product: str = "watches"):
    """Return active watches or mesoscale discussions for dropdown population."""
    from spc.spc_utils import fetch_active_watch_items, fetch_active_md_items

    product = (product or "").lower()
    if product == "watches":
        items, _ = fetch_active_watch_items()
        result = []
        for w in (items or []):
            polygon = w.get("polygon") or []
            bounds = None
            if len(polygon) >= 3:
                lons = [pt[0] for pt in polygon]
                lats = [pt[1] for pt in polygon]
                bounds = {
                    "w": min(lons), "e": max(lons),
                    "s": min(lats), "n": max(lats),
                }
            result.append({
                "id": w.get("id"),
                "label": w.get("title") or w.get("label", ""),
                "bounds": bounds,
            })
        return {"status": "ok", "items": result, "product": "watches"}

    elif product == "mds":
        items, _ = fetch_active_md_items()
        result = []
        for md in (items or []):
            polygon = md.get("polygon") or []
            bounds = None
            if len(polygon) >= 3:
                lons = [pt[0] for pt in polygon]
                lats = [pt[1] for pt in polygon]
                bounds = {
                    "w": min(lons), "e": max(lons),
                    "s": min(lats), "n": max(lats),
                }
            result.append({
                "id": md.get("id"),
                "label": md.get("short_label") or md.get("label", ""),
                "bounds": bounds,
            })
        return {"status": "ok", "items": result, "product": "mds"}

    return {"status": "error", "message": f"Unknown product: {product}"}


@app.get("/api/weather")
def api_weather(
    request_id: str = "",
    product_group: str = "surface",
    product: str = "Station Plot",
    region: str = "CONUS",
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    latest_only: Optional[bool] = False,
    frames: Optional[int] = 12,
    fps: Optional[int] = 4,
    user_tz: Optional[str] = None,
    day: Optional[int] = 1,
    report_day: Optional[str] = "today",
    item_id: Optional[str] = None,
    n: Optional[float] = None,
    s: Optional[float] = None,
    e: Optional[float] = None,
    w: Optional[float] = None,
    style_config: Optional[str] = None,
    view_mode: Optional[str] = "layers",
):
    """Unified weather endpoint for current + archive mode inference."""
    if not weather_utils:
        raise HTTPException(status_code=503, detail=error_payload(
            "Weather module unavailable", code="module_unavailable"))

    # Validate product group and product
    valid, err_msg = weather_utils.validate_product_group(
        product_group, product)
    if not valid:
        raise HTTPException(status_code=400, detail=error_payload(err_msg))

    # Mode inference
    data_mode = infer_data_mode(date_from, date_to)

    # Parse styles
    parsed_styles = _parse_and_validate_styles(style_config)
    logo_path_to_use = resolve_logo_path(parsed_styles, BASE_DIR, LOGO_PATH)

    # Custom extent
    custom_extent = _resolve_extent(n, s, e, w)
    if custom_extent:
        region = "CONUS"

    # Archive validation
    if data_mode == "archive":
        start_utc = parse_utc_datetime(date_from)
        end_utc = parse_utc_datetime(date_to)
        max_days = float(weather_utils.MAX_ARCHIVE_SPAN.get(
            product_group.lower(), 7))
        if (end_utc - start_utc) > timedelta(days=max_days):
            raise HTTPException(
                status_code=400,
                detail=error_payload(
                    f"Archive range too large for {product_group}.",
                    code="date_range_too_large",
                    details=f"Maximum allowed span is {max_days} day(s).",
                ),
            )
        if end_utc < start_utc:
            raise HTTPException(
                status_code=400,
                detail=error_payload(
                    "date_to must be >= date_from.", code="invalid_date_range"),
            )

    # Progress setup
    if request_id:
        active_tasks[request_id] = {
            "percent": 0, "message": "Starting...", "stage": "init",
            "source": product_group.upper(),
        }

    def progress_cb(pct, msg, stage):
        if request_id:
            active_tasks[request_id] = {
                "percent": pct, "message": msg, "stage": stage,
                "source": product_group.upper(),
            }

    try:
        result = weather_utils.generate_weather_layers(
            product_group=product_group,
            product=product,
            region=region,
            custom_extent=custom_extent,
            date_from=date_from if data_mode == "archive" else None,
            date_to=date_to if data_mode == "archive" else None,
            frames_count=max(1, min(int(frames or 12), 100)),
            fps=max(1, min(int(fps or 4), 30)),
            user_tz=user_tz,
            style_config=parsed_styles,
            logo_file=logo_path_to_use,
            progress_callback=progress_cb,
            day=max(1, min(int(day or 1), 8)),
            report_day="yesterday" if (
                report_day or "").lower() == "yesterday" else "today",
            item_id=item_id or None,
        )

        if not result or not result.get("frames"):
            return success_payload(
                status="warning",
                message="No output generated for the selected parameters.",
                image_url=None,
                source=product_group.upper(),
                data_mode=data_mode,
                request_id=request_id,
            )

        # Build layered response URLs
        from urllib.parse import quote

        archive_layers_dir = weather_utils.WEATHER_ARCHIVE_LAYERS

        def _layer_url(path_value):
            if not path_value:
                return None
            rel = os.path.relpath(
                path_value, archive_layers_dir).replace("\\", "/")
            rel = quote(rel, safe="/")
            return f"/img/weather_archive_layers/{rel}"

        basemap_url = _layer_url(result["basemap_path"])
        session_id = result["session_id"]

        frames_payload = []
        has_legend = False
        for entry in result["frames"]:
            product_url = _layer_url(entry.get("product_path"))
            static_overlay_url = _layer_url(entry.get("static_overlay_path"))
            hud_right_url = _layer_url(entry.get("hud_right_path"))
            legend_url = _layer_url(entry.get("legend_path"))
            if legend_url:
                has_legend = True
            frames_payload.append({
                "index": entry["index"],
                "timestamp_utc": entry["timestamp_utc"],
                "timestamp_local": entry["timestamp_local"],
                "url": product_url,
                "image_url": product_url,
                "product_url": product_url,
                "static_overlay_url": static_overlay_url,
                "hud_right_url": hud_right_url,
                "legend_url": legend_url,
            })

        layer_defs = [
            {"id": "product", "label": f"{product_group.title()} Layer",
             "default_visible": True, "default_opacity": 1, "sort": 10},
            {"id": "static_overlay", "label": "HUD and Logo Layer",
             "default_visible": True, "default_opacity": 1, "sort": 20},
        ]
        if has_legend:
            layer_defs.append(
                {"id": "legend", "label": "Legend",
                 "default_visible": True, "default_opacity": 1, "sort": 30},
            )
        layer_defs.append(
            {"id": "hud_right", "label": "Timestamp Layer",
             "default_visible": True, "default_opacity": 1, "sort": 50},
        )

        payload = success_payload(
            message=f"{product_group}/{product} generated with {len(frames_payload)} frame(s)",
            image_url=basemap_url,
            source=product_group.upper(),
            data_mode=data_mode,
            request_id=request_id,
        )
        payload.update({
            "output_mode": "layers",
            "basemap_url": basemap_url,
            "frames": frames_payload,
            "layers_path": session_id,
            "session_expires_utc": result["manifest"].get("expires_utc", ""),
            "layer_defs": layer_defs,
        })
        return payload

    except HTTPException:
        raise
    except Exception as exc:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=error_payload(str(exc), code="internal_error"),
        )
    finally:
        if request_id:
            active_tasks.pop(request_id, None)


@app.get("/api/weather/export-frame")
def api_weather_export_frame(
    layers_path: str = "",
    frame_index: int = 0,
):
    """Export a composited PNG from existing layered artifacts."""
    if not weather_utils:
        raise HTTPException(status_code=503, detail=error_payload(
            "Weather module unavailable", code="module_unavailable"))

    session_path, err = weather_utils.validate_layers_path(layers_path)
    if err:
        raise HTTPException(status_code=400, detail=error_payload(err,
                            code="invalid_layers_path"))

    export_path = weather_utils.export_frame_png(session_path, frame_index)
    if not export_path:
        return success_payload(
            status="warning",
            message=f"Frame {frame_index} not available for export.",
            image_url=None,
            source="weather",
            data_mode="export",
        )

    from urllib.parse import quote
    rel = os.path.relpath(
        export_path, weather_utils.WEATHER_ARCHIVE_LAYERS).replace("\\", "/")
    rel = quote(rel, safe="/")
    image_url = f"/img/weather_archive_layers/{rel}"

    return success_payload(
        message=f"Frame {frame_index} exported.",
        image_url=image_url,
        source="weather",
        data_mode="export",
    )


@app.get("/api/weather/export-animation")
def api_weather_export_animation(
    layers_path: str = "",
    fps: int = 4,
):
    """Export MP4 from existing layered artifacts without re-rendering."""
    if not weather_utils:
        raise HTTPException(status_code=503, detail=error_payload(
            "Weather module unavailable", code="module_unavailable"))

    session_path, err = weather_utils.validate_layers_path(layers_path)
    if err:
        raise HTTPException(status_code=400, detail=error_payload(err,
                            code="invalid_layers_path"))

    fps = max(1, min(int(fps or 4), 30))
    export_path = weather_utils.export_animation_mp4(session_path, fps=fps)
    if not export_path:
        return success_payload(
            status="warning",
            message="No frames available for animation export.",
            image_url=None,
            source="weather",
            data_mode="export",
        )

    from urllib.parse import quote
    rel = os.path.relpath(
        export_path, weather_utils.WEATHER_ARCHIVE_LAYERS).replace("\\", "/")
    rel = quote(rel, safe="/")
    image_url = f"/img/weather_archive_layers/{rel}"

    return success_payload(
        message="Animation exported.",
        image_url=image_url,
        source="weather",
        data_mode="export",
    )


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_includes=["*.py"],  # only restart on Python file changes
        reload_excludes=[
            "radar/*",
            "satellite/*",
            "surface/*",
            "alerts/*",
            "__pycache__/*",
        ],
    )
