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


def test_workspace_excludes_water_but_preserves_radar_tools():
    workspace = (
        Path(BASE_DIR) / "frontend" / "pages" / "workspace" / "workspace.html"
    ).read_text(encoding="utf-8")

    assert 'id="wx-section-water"' not in workspace
    assert 'id="wx-stormtrack-start"' in workspace
    assert 'id="wx-radarcal-start"' in workspace
