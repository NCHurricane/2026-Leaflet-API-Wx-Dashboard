from pathlib import Path

from app_core.paths import BASE_DIR
from routes.pages import read_water_page


def test_water_route_serves_standalone_page():
    response = read_water_page()
    expected = Path(BASE_DIR) / "frontend" / "pages" / "water" / "water.html"

    assert Path(response.path) == expected
    assert expected.exists()


def test_water_page_uses_only_new_frontend_boundary():
    page = (
        Path(BASE_DIR) / "frontend" / "pages" / "water" / "water.html"
    ).read_text(encoding="utf-8")

    assert "/frontend/core/core.css" in page
    assert "/frontend/pages/water/water-app.js" in page
    assert "js/weather.js" not in page
    assert "js/product-page-shell.js" not in page
    assert "css/dashboard.css" not in page


def test_water_page_contains_required_controls():
    page = (
        Path(BASE_DIR) / "frontend" / "pages" / "water" / "water.html"
    ).read_text(encoding="utf-8")

    for target_id in (
        "weather-map",
        "weather-water-network-filters",
        "weather-water-flood-filters",
        "weather-refresh-water",
        "weather-clear-water",
        "weather-water-status",
    ):
        assert f'id="{target_id}"' in page


def test_legacy_water_paths_are_removed_but_workspace_tools_remain():
    shell = (Path(BASE_DIR) / "weather.html").read_text(encoding="utf-8")
    monolith = (Path(BASE_DIR) / "js" / "weather.js").read_text(encoding="utf-8")

    assert 'href="/water"' in shell
    assert 'id="wx-section-water"' not in shell
    assert "_loadWaterStations" not in monolith
    assert "_renderWaterStations" not in monolith
    assert 'id="wx-stormtrack-start"' in shell
    assert 'id="wx-radarcal-start"' in shell
    assert "function _activateStormTrackDragProjection" in monolith
    assert "function _computeRadarCalSpeed" in monolith
