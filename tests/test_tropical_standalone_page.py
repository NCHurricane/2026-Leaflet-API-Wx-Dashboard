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
        "tropical-panel-live",
        "tropical-panel-archive",
        "weather-tropical-system-cards",
        "tropical-system-inspector",
        "tropical-system-close",
        "tropical-system-open",
        "weather-tropical-inspector",
        "tropical-city-density",
        "tropical-city-font-size",
        "wx-archive-season",
        "wx-tropical-adv-scrubber",
    ):
        assert f'id="{target_id}"' in page

    assert 'id="tropical-system-tab"' not in page
    assert 'data-sidebar-tab="live"' in page
    assert 'data-sidebar-tab="archive"' in page
    assert page.count("data-live-basin=") == 4
    assert 'data-live-basin="WORLD" aria-pressed="true"' in page


def test_tropical_live_filter_does_not_auto_select_first_storm():
    engine = (
        Path(BASE_DIR) / "frontend" / "pages" / "tropical" / "tropical-engine.js"
    ).read_text(encoding="utf-8")

    assert "context.filterStorms" in engine
    assert "context.clearFilteredStorm" in engine
    assert "context.renderActiveStorms" in engine
    assert "featuredStormId" not in engine


def test_tropical_legend_uses_refactored_core_shell():
    page = (
        Path(BASE_DIR) / "frontend" / "pages" / "tropical" / "tropical.html"
    ).read_text(encoding="utf-8")
    app = (
        Path(BASE_DIR) / "frontend" / "pages" / "tropical" / "tropical-app.js"
    ).read_text(encoding="utf-8")

    assert 'class="tropical-legend" data-legend-align="left" hidden' in page
    assert 'class="core-legend-header"' in app
    assert 'class="core-legend-provider">NHC' in app
    assert 'class="core-legend-body"' in app


def test_tropical_archive_scrubber_is_anchored_to_map_bottom():
    page = (
        Path(BASE_DIR) / "frontend" / "pages" / "tropical" / "tropical.html"
    ).read_text(encoding="utf-8")
    styles = (
        Path(BASE_DIR) / "frontend" / "pages" / "tropical" / "tropical.css"
    ).read_text(encoding="utf-8")

    assert '<div id="wx-tropical-adv-scrubber" hidden>' in page
    assert ".weather-map-wrap > #wx-tropical-adv-scrubber" in styles
    assert "position: absolute;" in styles
    assert "bottom: 8px;" in styles
