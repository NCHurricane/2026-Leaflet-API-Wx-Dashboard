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
        "weather-water-region",
        "weather-water-network-filters",
        "weather-water-flood-filters",
        "weather-refresh-water",
        "weather-clear-water",
        "weather-water-status",
        "weather-water-detail",
    ):
        assert f'id="{target_id}"' in page


def test_water_legend_uses_refactored_core_shell():
    page = (
        Path(BASE_DIR) / "frontend" / "pages" / "water" / "water.html"
    ).read_text(encoding="utf-8")
    app = (
        Path(BASE_DIR) / "frontend" / "pages" / "water" / "water-app.js"
    ).read_text(encoding="utf-8")

    assert 'class="water-legend" data-legend-align="left" hidden' in page
    assert 'class="core-legend-header"' in app
    assert 'class="core-legend-provider">NOAA' in app
    assert 'class="core-legend-body"' in app


def test_water_station_details_use_map_modal_not_leaflet_popups():
    page = (
        Path(BASE_DIR) / "frontend" / "pages" / "water" / "water.html"
    ).read_text(encoding="utf-8")
    app = (
        Path(BASE_DIR) / "frontend" / "pages" / "water" / "water-app.js"
    ).read_text(encoding="utf-8")

    assert 'id="weather-water-detail" class="water-detail" role="dialog"' in page
    assert "_waterStationDetailHtml" in app
    assert "water-detail-close" in app
    assert ".bindPopup(" not in app
    assert ".openPopup(" not in app
    assert ".setPopupContent(" not in app


def test_water_region_selector_uses_shared_map_regions_and_reloads_viewport():
    page = (
        Path(BASE_DIR) / "frontend" / "pages" / "water" / "water.html"
    ).read_text(encoding="utf-8")
    app = (
        Path(BASE_DIR) / "frontend" / "pages" / "water" / "water-app.js"
    ).read_text(encoding="utf-8")

    assert page.index('id="weather-water-region"') < page.index('class="core-sidebar-tabs"')
    assert "createMapCore, REGION_LABELS" in app
    assert "Object.entries(REGION_LABELS)" in app
    assert "mapCore.fitRegion(regionSelect.value)" in app
    assert "_scheduleWaterReload(0)" in app


def test_water_sidebar_controls_use_refactored_label_and_checkbox_styles():
    page = (
        Path(BASE_DIR) / "frontend" / "pages" / "water" / "water.html"
    ).read_text(encoding="utf-8")
    styles = (
        Path(BASE_DIR) / "frontend" / "pages" / "water" / "water.css"
    ).read_text(encoding="utf-8")

    assert page.count('<label class="water-check') == 7
    assert "<h2>Map Overlays</h2>" in page
    assert "label-small" not in page
    assert ".water-control-section h2" in styles
    assert "#wx-section-water label.water-check" in styles
    assert '#water-panel-overlays label.water-check input[type="checkbox"]' in styles


def test_workspace_excludes_water_but_preserves_projected_arrival():
    workspace = (
        Path(BASE_DIR) / "frontend" / "pages" / "workspace" / "workspace.html"
    ).read_text(encoding="utf-8")

    assert 'id="wx-section-water"' not in workspace
    assert 'id="wx-stormtrack-start"' in workspace
    assert 'id="wx-radarcal-start"' not in workspace
