"""Page-serving routes."""

from fastapi import APIRouter

from app_core.static_assets import serve_page, serve_product_shell_page

router = APIRouter()


@router.get("/")
def read_root():
    return serve_page("index.html")


@router.get("/radar.html")
def read_radar_page():
    return serve_page("radar.html")


@router.get("/weather.html")
def read_weather_page():
    return serve_page("weather.html")


@router.get("/tropical")
def read_tropical_page():
    return serve_page("weather.html")


@router.get("/alerts")
def read_alerts_page():
    return serve_product_shell_page("alerts")


@router.get("/spc")
def read_spc_page():
    return serve_page("weather.html")


@router.get("/surface")
def read_surface_page():
    return serve_page("weather.html")


@router.get("/drought")
def read_drought_page():
    return serve_page("weather.html")


@router.get("/satellite")
def read_satellite_page():
    return serve_page("weather.html")


@router.get("/radar")
def read_radar_standalone_page():
    return serve_page("weather.html")


@router.get("/mrms")
def read_mrms_page():
    return serve_page("weather.html")


@router.get("/rtma")
def read_rtma_page():
    return serve_page("weather.html")
