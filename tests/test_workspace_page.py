from pathlib import Path

from app_core.paths import BASE_DIR
from routes.pages import read_weather_page, read_workspace_page


def test_workspace_route_serves_new_page_and_legacy_url_redirects():
    response = read_workspace_page()
    expected = Path(BASE_DIR) / "frontend" / "pages" / "workspace" / "workspace.html"

    assert Path(response.path) == expected
    assert read_weather_page().headers["location"] == "/workspace"


def test_workspace_composes_engines_without_page_controllers():
    app = (
        Path(BASE_DIR) / "frontend" / "pages" / "workspace" / "workspace-app.js"
    ).read_text(encoding="utf-8")

    assert "../alerts/alerts-engine.js" in app
    assert "../radar/radar-engine.js" in app
    assert "alerts-page.js" not in app
    assert "radar-page.js" not in app
    assert "js/weather.js" not in app


def test_workspace_preserves_projected_arrival_and_speed_estimator():
    page = (
        Path(BASE_DIR) / "frontend" / "pages" / "workspace" / "workspace.html"
    ).read_text(encoding="utf-8")
    tools = (
        Path(BASE_DIR) / "frontend" / "pages" / "workspace" / "workspace-tools.js"
    ).read_text(encoding="utf-8")

    assert 'id="wx-stormtrack-start"' in page
    assert 'id="wx-radarcal-start"' in page
    assert "function _activateStormTrackDragProjection" in tools
    assert "function _computeRadarCalSpeed" in tools


def test_all_product_pages_use_vendored_leaflet():
    page_root = Path(BASE_DIR) / "frontend" / "pages"
    pages = list(page_root.rglob("*.html"))

    assert pages
    for page_path in pages:
        page = page_path.read_text(encoding="utf-8")
        assert "unpkg.com/leaflet" not in page
        assert "/frontend/lib/leaflet/leaflet.js" in page
        assert "/frontend/lib/leaflet/leaflet.css" in page


def test_legacy_monolith_assets_are_deleted():
    assert not (Path(BASE_DIR) / "weather.html").exists()
    assert not (Path(BASE_DIR) / "js" / "weather.js").exists()
    assert not (Path(BASE_DIR) / "js" / "product-page-shell.js").exists()
    assert not (Path(BASE_DIR) / "js" / "product-app-context.js").exists()
    assert not (Path(BASE_DIR) / "css" / "dashboard.css").exists()
