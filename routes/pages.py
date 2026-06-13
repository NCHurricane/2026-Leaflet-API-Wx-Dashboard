"""Page-serving routes."""

from fastapi import APIRouter

from app_core.static_assets import serve_page

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
