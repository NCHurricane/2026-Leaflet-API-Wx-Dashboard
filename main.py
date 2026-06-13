import os as _os

import certifi as _certifi

# Python on macOS ships with no default CA bundle (ssl cafile=None), so plain
# urllib/pandas HTTPS fetches fail certificate verification. Point OpenSSL at
# certifi's bundle unless the environment already provides one. Must run
# before any module builds an SSL context.
_os.environ.setdefault("SSL_CERT_FILE", _certifi.where())
_os.environ.setdefault("REQUESTS_CA_BUNDLE", _certifi.where())

from datetime import datetime, timezone, timedelta
import json
from typing import Optional
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI, HTTPException
import uvicorn
import os
from app_core.http import (
    error_payload,
)
from app_core.paths import BASE_DIR, CACHE_ROOT as _CACHE_ROOT, ensure_runtime_dirs
from app_core.runtime import initialize_runtime, shutdown_runtime
from app_core.static_assets import CacheStaticFiles
from routes.alerts import router as alerts_router
from routes.archive import router as archive_router
from routes.core import router as core_router
from routes.drought import router as drought_router
from routes.health import router as health_router
from routes.mrms import router as mrms_router
from routes.overlays import create_overlays_router
from routes.pages import router as pages_router
from routes.radar import router as radar_router
from routes.rtma import router as rtma_router
from routes.satellite_v2 import router as satellite_v2_router
from routes.spc import router as spc_router
from routes.surface import router as surface_router
from routes.tropical import router as tropical_router
from services.rtma_service import get_rtma_data

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
app.include_router(surface_router)
app.include_router(mrms_router)
app.include_router(rtma_router)
app.include_router(create_overlays_router(rtma_bootstrap=get_rtma_data))
app.include_router(archive_router)
app.include_router(radar_router)
app.include_router(tropical_router)


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
