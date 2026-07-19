from pathlib import Path

from app_core.paths import BASE_DIR
from routes.pages import read_tropical_page


def test_tropical_route_serves_standalone_page():
    response = read_tropical_page()
    expected = Path(BASE_DIR) / "frontend" / "pages" / "tropical" / "tropical.html"

    assert Path(response.path) == expected
    assert expected.exists()


def test_tropical_page_uses_only_new_frontend_boundary():
    page = (
        Path(BASE_DIR) / "frontend" / "pages" / "tropical" / "tropical.html"
    ).read_text(encoding="utf-8")

    assert "/frontend/core/core.css" in page
    assert "/frontend/pages/tropical/tropical-engine.js" in page
    assert "/frontend/pages/tropical/tropical-controller.js" in page
    assert "/frontend/pages/tropical/tropical-app.js" in page
    assert "js/weather.js" not in page
    assert "js/tropical-engine.js" not in page
    assert "js/tropical-page.js" not in page
    assert "css/dashboard.css" not in page


def test_tropical_page_contains_required_workspace_targets():
    page = (
        Path(BASE_DIR) / "frontend" / "pages" / "tropical" / "tropical.html"
    ).read_text(encoding="utf-8")

    for target_id in (
        "weather-map",
        "weather-tropical-basin",
        "weather-tropical-system-cards",
        "weather-tropical-inspector",
        "wx-archive-season",
        "wx-tropical-adv-scrubber",
    ):
        assert f'id="{target_id}"' in page
