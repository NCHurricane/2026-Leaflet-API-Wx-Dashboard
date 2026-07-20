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


def test_workspace_preserves_projected_arrival_without_speed_estimator():
    page = (
        Path(BASE_DIR) / "frontend" / "pages" / "workspace" / "workspace.html"
    ).read_text(encoding="utf-8")
    tools = (
        Path(BASE_DIR) / "frontend" / "pages" / "workspace" / "workspace-tools.js"
    ).read_text(encoding="utf-8")
    app = (
        Path(BASE_DIR) / "frontend" / "pages" / "workspace" / "workspace-app.js"
    ).read_text(encoding="utf-8")

    assert 'id="wx-stormtrack-start"' in page
    assert 'id="wx-radarcal-start"' not in page
    assert 'Radar Speed Estimator' not in page
    assert 'id="workspace-projected-arrival-group" class="workspace-group workspace-layer-group workspace-projected-arrival-group" hidden' in page
    assert page.index('id="workspace-projected-arrival-group"') > page.index('id="workspace-warning-filters"')
    assert page.index('id="workspace-projected-arrival-group"') < page.index('<h2>Storm Reports</h2>')
    assert 'class="workspace-help"' not in page
    assert 'data-sidebar-tab="tools"' not in page
    assert 'data-sidebar-panel="tools"' not in page
    assert "function _activateStormTrackDragProjection" in tools
    assert "_radarCal" not in tools
    assert "function hideProjectedArrival()" in app
    assert "group.hidden = false" in app
    assert "group.open = true" in app
    assert "onResetView: () => resetWorkspaceState()" in app
    assert "resetWorkspaceState = () =>" in app
    assert "regionSelect.value = 'CONUS'" in app
    assert "byId('workspace-radar-site').value = ''" in app
    assert "setActiveRadarLevel('Level 2')" in app
    assert "hideProjectedArrival();" in app
    assert ".workspace-projected-arrival-group[hidden] { display: none; }" in (
        Path(BASE_DIR) / "frontend" / "pages" / "workspace" / "workspace.css"
    ).read_text(encoding="utf-8")


def test_workspace_uses_simplified_live_controls_and_separate_legends():
    page = (
        Path(BASE_DIR) / "frontend" / "pages" / "workspace" / "workspace.html"
    ).read_text(encoding="utf-8")
    app = (
        Path(BASE_DIR) / "frontend" / "pages" / "workspace" / "workspace-app.js"
    ).read_text(encoding="utf-8")

    assert 'id="workspace-radar-enabled" type="checkbox" checked' in page
    assert 'id="workspace-radar-elevation"' not in page
    assert 'id="workspace-radar-levels"' in page
    assert 'id="workspace-radar-product-options" class="workspace-radar-product-options" hidden' in page
    assert 'data-radar-level="Level 2" aria-pressed="true"' in page
    assert 'data-radar-level="Level 3" aria-pressed="false"' in page
    assert 'id="workspace-alerts-enabled" type="checkbox" checked' in page
    assert 'id="workspace-lsr-enabled" type="checkbox" checked' not in page
    assert 'class="wx-check-row workspace-radar-site-option" hidden' in page
    assert 'id="workspace-warning-filters"' in page
    assert 'id="workspace-lsr-filters"' in page
    assert 'id="workspace-lsr-hours"' in page
    assert 'id="workspace-alerts-legend"' in page
    assert 'id="workspace-lsr-legend"' in page
    assert 'id="workspace-storm-track-legend"' in page
    assert 'id="workspace-radar-scrubber-bar"' in page
    assert 'id="workspace-radar-bottom-scrubber"' in page
    assert all(f'<h2>{label}</h2>' in page for label in ['SPC', 'Satellite', 'RTMA', 'MRMS', 'WPC', 'Water'])
    assert page.count('workspace-layer-group workspace-placeholder') == 6
    assert page.count('workspace-group workspace-layer-group" open') == 1
    assert 'id="workspace-right-rail"' in page
    assert 'id="workspace-warning-section"' in page
    assert 'id="workspace-lsr-section"' in page
    assert 'id="workspace-notifications"' in page
    assert 'id="workspace-detail" class="alerts-detail" hidden' in page
    assert 'id="workspace-auto-update" type="checkbox" checked' in page
    assert "font-awesome/6.7.2/css/all.min.css" in page
    assert ['CONUS', 'AK', 'HI', 'PR'] == [
        value for value in ['CONUS', 'AK', 'HI', 'PR']
        if f'<option value="{value}">' in page
    ]
    assert "WORKSPACE_REGION_BOUNDS" in app
    assert "categories: Object.keys(ALERT_CATEGORIES)" in app
    assert "if (warningTypes.length) categories.push('Severe Weather Warnings')" in app
    assert "function toggleWarningPill" in app
    assert "function syncRadarControls" in app
    assert "String(product?.level || '') === level" in app
    assert "radarEngine.isConusSite(site)" in app
    assert "byId('workspace-radar-product-options').hidden = !hasSite" in app
    assert "byId('workspace-radar-enabled').addEventListener('change'" in app
    assert "function syncRightRailVisibility" in app
    assert "onLsrReports: renderLsrReports" in app
    assert "currentWarnings = [...features]" in app
    assert "alertIssuedMs(b) - alertIssuedMs(a)" in app
    assert "selectAlert(feature, { maxZoom: 9 })" in app
    assert "function selectAlert(feature, options = { maxZoom: 9 })" in app
    assert "alertsEngine.clearLsrSelection()" in app
    assert "const AUTO_UPDATE_MS = 30_000" in app
    assert "const NEW_ALERT_NOTICE_MS = 15_000" in app
    assert "'Tornado Warning', 'Tornado Watch'" in app
    assert "'Severe Thunderstorm Warning', 'Severe Thunderstorm Watch'" in app
    assert "'Flash Flood Warning', 'Flash Flood Watch'" in app
    assert "new Audio('/sounds/weather_alert.mp3')" in app
    assert "NEW_ALERT_EVENTS.has(props.event)" in app
    assert "onNewAlert: showNewAlert" in app
    assert "onLsrDetail: (feature) => detail.openLsr(feature)" in app
    assert "shouldHandleAlertClick: () => !tools.isDrawing()" in app
    assert "detail.open(feature)" in app
    assert "createScrubber" in app
    assert "holdAtEnd: true" in app
    assert "radarScrubber.setFrames" in app
    assert "onStormTrackLegend" in app
    assert "collapse.className = 'core-legend-collapse'" in app
    assert "fa-chevron-down" in app
    assert "panel.classList.toggle('is-collapsed', !isOpen)" in app
    assert "elevation: '0.5'" in app
    assert "radarEngine.loadFrames({ refresh: true })" in app
    assert "notifyNewAlerts: false" in app
    assert 'data-warning="all" aria-pressed="false"' in page
    assert 'class="is-active" type="button" data-warning="tor" aria-pressed="true"' in page
    assert 'class="is-active" type="button" data-warning="svr" aria-pressed="true"' in page
    assert 'data-warning="sps" aria-pressed="false" title="Special Weather Statement">SPS</button>' in page
    assert "sps: 'Special Weather Statement'" in app
    assert "if (filterTypes.includes('sps')) categories.push('Informational Alerts')" in app
    assert "eventTypes: filterTypes.map" in app
    assert 'class="is-active" type="button" data-hours="1"' in page
    assert 'class="is-active" type="button" data-hours="24"' not in page


def test_all_product_pages_use_vendored_leaflet():
    page_root = Path(BASE_DIR) / "frontend" / "pages"
    pages = list(page_root.rglob("*.html"))

    assert pages
    for page_path in pages:
        page = page_path.read_text(encoding="utf-8")
        assert "unpkg.com/leaflet" not in page
        assert "/frontend/lib/leaflet/leaflet.js" in page
        assert "/frontend/lib/leaflet/leaflet.css" in page


def test_standalone_radar_uses_explicit_lowest_tilt_default():
    app = (
        Path(BASE_DIR) / "frontend" / "pages" / "radar" / "radar-page.js"
    ).read_text(encoding="utf-8")

    assert "byId('radar-elevation')?.value || '0.5'" in app
    assert "holdAtEnd: true" in app


def test_radar_scrubbers_hold_on_the_newest_frame():
    scrubber = (
        Path(BASE_DIR) / "frontend" / "core" / "scrubber.js"
    ).read_text(encoding="utf-8")

    assert "const holdAtEnd = options.holdAtEnd === true" in scrubber
    assert "holdAtEnd && next === frames.length - 1" in scrubber
    assert "holdAtEnd ? interval() : interval() * LOOP_HOLD_MULTIPLIER" in scrubber


def test_workspace_hides_pointer_focus_rings_but_keeps_keyboard_focus_visible():
    styles = (
        Path(BASE_DIR) / "frontend" / "pages" / "workspace" / "workspace.css"
    ).read_text(encoding="utf-8")

    assert ".leaflet-interactive:focus:not(:focus-visible)" in styles
    assert ".leaflet-marker-icon:focus:not(:focus-visible)" in styles
    assert ".leaflet-interactive:focus-visible" in styles
    assert ".leaflet-tooltip.alerts-lsr-hover-tip" in styles
    assert "width: min(260px, calc(100vw - 48px))" in styles


def test_legacy_monolith_assets_are_deleted():
    assert not (Path(BASE_DIR) / "weather.html").exists()
    assert not (Path(BASE_DIR) / "js" / "weather.js").exists()
    assert not (Path(BASE_DIR) / "js" / "product-page-shell.js").exists()
    assert not (Path(BASE_DIR) / "js" / "product-app-context.js").exists()
    assert not (Path(BASE_DIR) / "css" / "dashboard.css").exists()
