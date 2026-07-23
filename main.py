import os as _os
from contextlib import asynccontextmanager

import certifi as _certifi
from dotenv import load_dotenv as _load_dotenv

_load_dotenv()

# Python on macOS ships with no default CA bundle (ssl cafile=None), so plain
# urllib/pandas HTTPS fetches fail certificate verification. Point OpenSSL at
# certifi's bundle unless the environment already provides one. Must run
# before any module builds an SSL context.
_os.environ.setdefault("SSL_CERT_FILE", _certifi.where())
_os.environ.setdefault("REQUESTS_CA_BUNDLE", _certifi.where())

from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI
import uvicorn
import os
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
from routes.water import router as water_router
from routes.wpc import router as wpc_router
from services.rtma_service import get_rtma_data

# --- IMPORT YOUR UTILITIES ---


@asynccontextmanager
async def _application_lifespan(_app: FastAPI):
    """Own startup and graceful shutdown of application background work."""
    initialize_runtime()
    try:
        yield
    finally:
        shutdown_runtime()


# Defer directory creation and module initialization to startup handler
app = FastAPI(
    title="NCHurricane Weather API",
    lifespan=_application_lifespan,
)
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
app.include_router(water_router)
app.include_router(wpc_router)

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
app.mount(
    "/frontend",
    StaticFiles(directory=os.path.join(BASE_DIR, "frontend")),
    name="frontend",
)
app.mount("/data", StaticFiles(directory=os.path.join(BASE_DIR, "data")), name="data")
app.mount("/img", StaticFiles(directory=os.path.join(BASE_DIR, "img")), name="img")
app.mount(
    "/fonts", StaticFiles(directory=os.path.join(BASE_DIR, "fonts")), name="fonts"
)


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
