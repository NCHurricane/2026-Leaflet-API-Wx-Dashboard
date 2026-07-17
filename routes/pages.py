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
    return serve_product_shell_page("spc")


@router.get("/surface")
def read_surface_page():
    return serve_product_shell_page("surface")


@router.get("/drought")
def read_drought_page():
    return serve_page("frontend/pages/drought/drought.html")


@router.get("/satellite")
def read_satellite_page():
    return serve_product_shell_page("satellite")


@router.get("/radar")
def read_radar_standalone_page():
    return serve_product_shell_page("radar")


@router.get("/mrms")
def read_mrms_page():
    return serve_product_shell_page("mrms")


@router.get("/rtma")
def read_rtma_page():
    return serve_product_shell_page("rtma")


@router.get("/wpc")
def read_wpc_page():
    return serve_product_shell_page("wpc")


@router.get("/water")
def read_water_page():
    return serve_product_shell_page("water")
