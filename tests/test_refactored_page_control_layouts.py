from pathlib import Path
import re


BASE_DIR = Path(__file__).resolve().parents[1]


def page_text(page):
    return (BASE_DIR / "frontend" / "pages" / page / f"{page}.html").read_text(encoding="utf-8")


def script_text(page, filename=None):
    return (BASE_DIR / "frontend" / "pages" / page / (filename or f"{page}-page.js")).read_text(encoding="utf-8")


def assert_in_order(text, *needles):
    positions = [text.index(needle) for needle in needles]
    assert positions == sorted(positions)


def test_primary_pages_use_live_settings_archive_tabs():
    for page in ("surface", "alerts", "radar", "satellite", "spc", "rtma", "mrms"):
        html = page_text(page)
        assert_in_order(
            html,
            f'data-sidebar-tab="live"',
            f'data-sidebar-tab="settings"',
            f'data-sidebar-tab="archive"',
        )
        assert html.count('data-sidebar-tab="') == 3
        assert html.count('data-sidebar-panel="') == 3


def test_two_tab_pages_remain_live_and_settings_only():
    for page in ("drought", "wpc", "water"):
        html = page_text(page)
        assert_in_order(html, 'data-sidebar-tab="live"', 'data-sidebar-tab="settings"')
        assert html.count('data-sidebar-tab="') == 2
        assert 'data-sidebar-tab="archive"' not in html


def test_settings_controls_follow_reference_order():
    expected = {
        "surface": ("surface-basemap", "surface-value-opacity", "surface-gradient-opacity", "surface-city-density", 'data-map-overlay="graticule"'),
        "alerts": ("alerts-basemap", "alerts-opacity", "alerts-city-density", 'data-map-overlay="graticule"', "New Alert Notifications", "Severe Polygon Pulse"),
        "radar": ("radar-basemap", "radar-opacity", "radar-city-density", 'data-map-overlay="graticule"'),
        "satellite": ("satellite-basemap", "satellite-opacity", "satellite-city-density", 'data-map-overlay="graticule"'),
        "spc": ("spc-basemap", "spc-fill-opacity", "spc-stroke-opacity", "spc-city-density", 'data-map-overlay="graticule"'),
        "rtma": ("rtma-basemap", "rtma-gradient-opacity", "rtma-city-density", 'data-map-overlay="graticule"'),
        "mrms": ("mrms-basemap", "mrms-city-density", 'data-map-overlay="graticule"'),
        "drought": ("drought-basemap", "drought-opacity", "drought-city-density", 'data-map-overlay="graticule"'),
        "wpc": ("wpc-basemap", "wpc-city-density", 'data-map-overlay="graticule"'),
        "water": ("water-basemap", "water-city-density", 'data-map-overlay="graticule"'),
    }
    for page, controls in expected.items():
        assert_in_order(page_text(page), *controls)


def test_live_control_moves_and_conditional_wiring_are_preserved():
    surface = page_text("surface")
    assert surface.index("<h2>Products</h2>") < surface.index('id="surface-density"')

    alerts = page_text("alerts")
    assert '<details class="alerts-lsr">' in alerts
    assert alerts.index('id="alerts-category-list"') < alerts.index('id="alerts-all"')
    assert "replaceChildren(master," in script_text("alerts")

    radar = page_text("radar")
    radar_script = script_text("radar")
    assert_in_order(radar, 'id="radar-site"', 'id="radar-levels"', 'id="radar-product"', 'id="radar-show-sites"', 'id="radar-elevation-wrap"', 'id="radar-show-storm-tracks"', 'id="radar-inspector"')
    assert "button.dataset.radarLevel === 'Level 3' && !conus" in radar_script
    assert "document.querySelectorAll('.radar-site-option')" in radar_script

    satellite = page_text("satellite")
    satellite_script = script_text("satellite")
    assert_in_order(satellite, "satellite-sat-id", "satellite-sector-controls", "satellite-view-controls", "satellite-product-controls")
    assert "byId('satellite-sector-controls').hidden = !satId" in satellite_script
    assert "byId('satellite-product-controls').hidden = !sector" in satellite_script
    assert "onResetView: () => resetSatelliteState()" in satellite_script
    assert "resetSatelliteState();\n        mapCore.fitRegion" in satellite_script

    rtma = page_text("rtma")
    assert rtma.index('id="rtma-density"') < rtma.index('id="rtma-lookback"') < rtma.index('id="rtma-auto-update"')
    mrms = page_text("mrms")
    assert_in_order(mrms, 'id="mrms-opacity"', 'id="mrms-lookback"', 'id="mrms-auto-update"')
    wpc = page_text("wpc")
    assert wpc.index('class="wpc-group-pills"') < wpc.index('id="wpc-opacity"') < wpc.index('class="wpc-group-panel')


def test_surface_cached_gradient_does_not_depend_on_marker_rows():
    renderer = script_text("surface", "surface-render.js")
    render_start = renderer.index("    function render(stations, view) {")
    render_end = renderer.index("\n    function clear()", render_start)
    render_body = renderer[render_start:render_end]

    assert "if (!view.product) return;" in render_body
    assert "if (!stations.length || !view.product) return;" not in render_body
    assert "if (stations.length) {" in render_body


def test_shared_border_defaults_enable_state_only():
    for page in ("surface", "alerts", "radar", "satellite", "spc", "rtma", "mrms", "drought", "wpc", "water", "workspace", "tropical"):
        html = page_text(page)
        state = re.search(r'<input[^>]*data-map-overlay="states"[^>]*>', html).group()
        county = re.search(r'<input[^>]*data-map-overlay="counties"[^>]*>', html).group()
        country = re.search(r'<input[^>]*data-map-overlay="countries"[^>]*>', html).group()
        assert "checked" in state
        assert "checked" not in county
        assert "checked" not in country
        graticule = re.search(r'<input[^>]*(?:data-map-overlay="graticule"|id="weather-tropical-graticule")[^>]*>', html).group()
        assert "checked" not in graticule


def test_archive_sliders_use_exact_requested_steps():
    surface = page_text("surface")
    alerts = page_text("alerts")
    assert 'id="surface-archive-lookback" type="range" min="0.25" max="24" step="0.25"' in surface
    assert 'id="alerts-archive-lookback" type="range" min="5" max="360" step="5"' in alerts


def test_tropical_keeps_tab_order_and_uses_shared_settings_spacing():
    tropical = page_text("tropical")
    assert_in_order(tropical, 'data-sidebar-tab="live"', 'data-sidebar-tab="archive"', 'data-sidebar-tab="settings"')
    assert 'id="tropical-panel-settings" class="core-sidebar-panel core-settings-panel"' in tropical
    assert '<div class="core-settings-section">\n                    <h2>Cities</h2>' in tropical
