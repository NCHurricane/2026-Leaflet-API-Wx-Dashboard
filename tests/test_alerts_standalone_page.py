from pathlib import Path

from app_core.paths import BASE_DIR
from routes.pages import read_alerts_page


def test_alerts_route_serves_standalone_page():
    response = read_alerts_page()
    expected = Path(BASE_DIR) / "frontend" / "pages" / "alerts" / "alerts.html"

    assert Path(response.path) == expected
    assert expected.exists()


def test_alerts_page_uses_only_new_frontend_boundary():
    page = (
        Path(BASE_DIR) / "frontend" / "pages" / "alerts" / "alerts.html"
    ).read_text(encoding="utf-8")

    assert "/frontend/core/core.css" in page
    assert "/frontend/pages/alerts/alerts-page.js" in page
    assert "js/weather.js" not in page
    assert "js/alerts-engine.js" not in page
    assert "js/alerts-page.js" not in page


def test_legacy_alerts_paths_are_removed_but_workspace_tools_are_preserved():
    workspace = (
        Path(BASE_DIR) / "frontend" / "pages" / "workspace" / "workspace.html"
    ).read_text(encoding="utf-8")
    tools = (
        Path(BASE_DIR) / "frontend" / "pages" / "workspace" / "workspace-tools.js"
    ).read_text(encoding="utf-8")

    assert 'id="wx-stormtrack-start"' in workspace
    assert 'id="wx-radarcal-start"' in workspace
    assert "function _activateStormTrackDragProjection" in tools
    assert "function _computeRadarCalSpeed" in tools
    assert "setAlerts(features)" in tools
