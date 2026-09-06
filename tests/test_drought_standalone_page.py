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
    assert '<option>Dark</option>' in page
    assert '<option>Light</option>' in page
    assert '<option>USA Topo</option>' in page
    assert '<option>Satellite</option>' in page
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
    assert "BRAND_ASSET_URL" in map_core
    assert "/api/overlay/us-boundaries" in map_core
    assert "/api/overlay/world-borders" in map_core
    assert "fetchCachedJson" in map_core
    assert "us-boundaries?layer=state&v=4" in map_core
    assert "us-boundaries?layer=county&v=4" in map_core
    assert "feature?.properties?.layer === layerName" in map_core
    assert "World_Dark_Gray_Base" in map_core
    assert "World_Light_Gray_Base" in map_core
    assert "USA_Topo_Maps" in map_core
    assert "World_Imagery" in map_core
    assert "basemaps.cartocdn.com" not in map_core
    assert "basemap.nationalmap.gov" not in map_core
    assert "core-reset-view" in map_core
    assert "core-zoom-indicator" in map_core
    assert "©2026 Chuck Copeland Weather" in map_core
    assert "options.basemap || 'Dark'" in map_core
    assert "/data/us-cities-all.json" in map_core
    assert "/data/world-cities.json" in map_core
    assert "setCitySource" in map_core
    assert "setCityDensity" in map_core
    assert "setCityFontSize" in map_core
    assert "fa-sun-plant-wilt" in (
        Path(BASE_DIR) / "frontend" / "core" / "nav.js"
    ).read_text(encoding="utf-8")


def test_country_borders_repeat_across_wrapped_worlds():
    map_core = (
        Path(BASE_DIR) / "frontend" / "core" / "map-core.js"
    ).read_text(encoding="utf-8")

    assert "COUNTRY_WORLD_OFFSETS = Object.freeze([-360, 0, 360])" in map_core
    assert "longitude + longitudeOffset" in map_core
    assert "leaflet.featureGroup(countryLayers)" in map_core


def test_shared_map_tiles_overlap_and_cache_bust():
    map_core = (
        Path(BASE_DIR) / "frontend" / "core" / "map-core.js"
    ).read_text(encoding="utf-8")
    core_css = (
        Path(BASE_DIR) / "frontend" / "core" / "core.css"
    ).read_text(encoding="utf-8")

    assert "1 / Math.max(1, Number(window.devicePixelRatio) || 1)" in map_core
    assert "core-tile-seam-overlap" in map_core
    assert "--core-tile-overlap" in map_core
    assert ".leaflet-container img.leaflet-tile" in core_css
    assert "calc(256px + var(--core-tile-overlap, 1px))" in core_css
    assert "mix-blend-mode: normal" in core_css

    for page_path in (Path(BASE_DIR) / "frontend" / "pages").glob("*/*.html"):
        page = page_path.read_text(encoding="utf-8")
        if "/frontend/core/core.css" in page:
            core_version = (
                "20260905-mrms" if page_path.parent.name in {"mrms", "workspace"}
                else "20260904a"
            )
            assert f"/frontend/core/core.css?v={core_version}" in page


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

    assert page.count('data-sidebar-tab="') == 2
    assert page.count('data-sidebar-panel="') == 2
    assert 'role="tablist"' in page
    assert page.count('role="tab"') == 2
    assert page.count('role="tabpanel"') == 2
    assert page.index('class="core-sidebar-header"') < page.index(
        'class="core-sidebar-tabs"'
    ) < page.index('class="core-sidebar-content"') < page.index(
        'class="core-sidebar-footer"'
    )
    assert page.index('id="drought-panel-live"') < page.index('id="drought-dates"')
    assert page.index('id="drought-panel-settings"') < page.index(
        'id="drought-basemap"'
    ) < page.index('id="drought-opacity"') < page.index(
        'id="drought-city-density"'
    ) < page.index('data-map-overlay="graticule"')
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


def test_workspace_does_not_load_drought_page_controller():
    workspace = (
        Path(BASE_DIR) / "frontend" / "pages" / "workspace" / "workspace.html"
    ).read_text(encoding="utf-8")

    assert "drought-page.js" not in workspace
    assert 'id="weather-drought-opts"' not in workspace
