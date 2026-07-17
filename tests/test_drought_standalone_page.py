import json
from pathlib import Path

from app_core.paths import BASE_DIR
from routes.pages import read_drought_page


def test_drought_route_serves_standalone_page():
    response = read_drought_page()
    expected = Path(BASE_DIR) / "frontend" / "pages" / "drought" / "drought.html"

    assert Path(response.path) == expected
    assert expected.exists()


def test_drought_page_uses_only_new_frontend_boundary():
    page = (
        Path(BASE_DIR) / "frontend" / "pages" / "drought" / "drought.html"
    ).read_text(encoding="utf-8")

    assert "/frontend/core/core.css" in page
    assert "font-awesome/6.7.2/css/all.min.css" in page
    assert "/frontend/pages/drought/drought-page.js" in page
    assert "js/weather.js" not in page
    assert "js/drought-engine.js" not in page
    assert "js/drought-page.js" not in page
    assert "css/dashboard.css" not in page


def test_drought_page_includes_shared_map_parity_controls():
    page = (
        Path(BASE_DIR) / "frontend" / "pages" / "drought" / "drought.html"
    ).read_text(encoding="utf-8")
    map_core = (
        Path(BASE_DIR) / "frontend" / "core" / "map-core.js"
    ).read_text(encoding="utf-8")

    assert 'id="global-timestamp"' in page
    assert 'id="drought-age"' in page
    assert page.index('<option>Dark (No Labels)</option>') < page.index(
        '<option>Light (No Labels)</option>'
    )
    assert 'data-map-overlay="graticule"' in page
    assert 'data-map-overlay="states"' in page
    assert 'data-map-overlay="countries"' in page
    assert 'data-map-overlay="counties"' in page
    assert 'name="drought-cities-source"' in page
    assert 'id="drought-city-density"' in page
    assert 'id="drought-city-font-size"' in page
    assert page.index('class="core-map-panel drought-map-wrap"') < page.index(
        'id="drought-legend"'
    )
    assert "/img/nchurricane_logo.png" in map_core
    assert "/api/overlay/us-boundaries" in map_core
    assert "/api/overlay/world-borders" in map_core
    assert "fetchCachedJson" in map_core
    assert "us-boundaries?layer=state&v=4" in map_core
    assert "us-boundaries?layer=county&v=4" in map_core
    assert "feature?.properties?.layer === layerName" in map_core
    assert "USGSImageryOnly" in map_core
    assert "core-reset-view" in map_core
    assert "core-zoom-indicator" in map_core
    assert "ChuckCopeland.com/NCHurricane.com" in map_core
    assert "options.basemap || 'Dark (No Labels)'" in map_core
    assert "/data/us-cities-all.json" in map_core
    assert "/data/world-cities.json" in map_core
    assert "setCitySource" in map_core
    assert "setCityDensity" in map_core
    assert "setCityFontSize" in map_core
    assert "fa-sun-plant-wilt" in (
        Path(BASE_DIR) / "frontend" / "core" / "nav.js"
    ).read_text(encoding="utf-8")


def test_drought_sidebar_uses_accessible_mounted_tab_panels():
    page = (
        Path(BASE_DIR) / "frontend" / "pages" / "drought" / "drought.html"
    ).read_text(encoding="utf-8")
    page_script = (
        Path(BASE_DIR) / "frontend" / "pages" / "drought" / "drought-page.js"
    ).read_text(encoding="utf-8")
    tabs = (
        Path(BASE_DIR) / "frontend" / "core" / "sidebar-tabs.js"
    ).read_text(encoding="utf-8")

    assert page.count('data-sidebar-tab="') == 3
    assert page.count('data-sidebar-panel="') == 3
    assert 'role="tablist"' in page
    assert page.count('role="tab"') == 3
    assert page.count('role="tabpanel"') == 3
    assert page.index('class="core-sidebar-header"') < page.index(
        'class="core-sidebar-tabs"'
    ) < page.index('class="core-sidebar-content"') < page.index(
        'class="core-sidebar-footer"'
    )
    assert page.index('id="drought-panel-data"') < page.index('id="drought-dates"')
    assert page.index('id="drought-panel-overlays"') < page.index(
        'id="drought-city-density"'
    ) < page.index('data-map-overlay="graticule"')
    assert page.index('id="drought-panel-style"') < page.index(
        'id="drought-opacity"'
    ) < page.index('id="drought-basemap"')
    assert page.index('id="drought-message"') < page.index('id="drought-refresh"')
    assert "createSidebarTabs" in page_script
    assert "candidate.hidden = candidate !== panel" in tabs
    assert "replaceChildren" not in tabs
    assert "ArrowRight" in tabs and "ArrowLeft" in tabs
    assert "aria-selected" in tabs


def test_drought_uses_shared_confined_collapsible_legend_tray():
    page = (
        Path(BASE_DIR) / "frontend" / "pages" / "drought" / "drought.html"
    ).read_text(encoding="utf-8")
    engine = (
        Path(BASE_DIR) / "frontend" / "pages" / "drought" / "drought-engine.js"
    ).read_text(encoding="utf-8")
    page_css = (
        Path(BASE_DIR) / "frontend" / "pages" / "drought" / "drought.css"
    ).read_text(encoding="utf-8")
    core_css = (Path(BASE_DIR) / "frontend" / "core" / "core.css").read_text(
        encoding="utf-8"
    )
    legend = (
        Path(BASE_DIR) / "frontend" / "core" / "legend.js"
    ).read_text(encoding="utf-8")

    assert 'class="core-map-panel drought-map-wrap"' in page
    assert 'data-legend-align="left"' in page
    assert "new Set(['left', 'center', 'right'])" in legend
    assert "data-legend-collapse" in legend
    assert "setCollapsed" in legend
    assert '.core-map-legend[data-legend-align="left"]' in core_css
    assert '.core-map-legend[data-legend-align="right"]' in core_css
    assert ".core-legend-colorbar" in core_css
    assert "core-legend-categories" in engine
    assert "core-legend-provider" in engine
    assert "drought-legend-stats" in engine
    assert "drought-legend-row" not in engine
    assert "rgba(247, 251, 255" not in page_css


def test_drought_latest_release_auto_loads_by_default():
    settings = json.loads(
        (Path(BASE_DIR) / "config" / "user_settings.default.json").read_text(
            encoding="utf-8"
        )
    )
    page_script = (
        Path(BASE_DIR) / "frontend" / "pages" / "drought" / "drought-page.js"
    ).read_text(encoding="utf-8")

    assert settings["pages"]["drought"]["autoLoad"] is True
    assert settings["global"]["cityLabels"] == {
        "source": "off",
        "density": 0.25,
        "fontSize": 0.6,
    }
    assert "activeDate = settings.autoLoad ? (dates[0] || null) : null" in page_script
    assert "if (settings.autoLoad) await loadActive()" in page_script


def test_drought_engine_has_no_dom_or_sibling_product_dependencies():
    engine = (
        Path(BASE_DIR) / "frontend" / "pages" / "drought" / "drought-engine.js"
    ).read_text(encoding="utf-8")

    assert "document." not in engine
    assert "weather-" not in engine
    assert "exitMrms" not in engine
    assert "exitRtma" not in engine


def test_legacy_shell_links_to_drought_without_loading_old_drought_modules():
    shell = (Path(BASE_DIR) / "weather.html").read_text(encoding="utf-8")

    assert 'href="/drought"' in shell
    assert "js/drought-engine.js" not in shell
    assert "js/drought-page.js" not in shell
    assert 'id="weather-drought-opts"' not in shell
