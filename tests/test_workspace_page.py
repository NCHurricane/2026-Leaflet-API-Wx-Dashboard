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
    assert "function hideProjectedArrival({ preserveAlert = false } = {})" in app
    assert "const PROJECTED_ARRIVAL_EVENTS = new Set([" in app
    assert "'Tornado Warning'," in app
    assert "'Severe Thunderstorm Warning'," in app
    assert "'Special Marine Warning'," in app
    assert "'Special Weather Statement'," in app
    assert "function supportsProjectedArrival(feature)" in app
    assert "['Polygon', 'MultiPolygon'].includes(geometryType)" in app
    assert "let projectedArrivalFeature = null;" in app
    assert "function syncProjectedArrivalVisibility()" in app
    assert "Boolean(radarSelection().site)" in app
    assert "hideProjectedArrival({ preserveAlert: true });" in app
    assert "projectedArrivalFeature = feature;" in app
    assert "projectedArrivalReady = syncProjectedArrivalVisibility();" in app
    assert "select a radar site to use Projected Arrival" in app
    assert "if (supportsProjectedArrival(feature))" in app
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
    assert 'id="workspace-watch-filters"' in page
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
    assert "WORKSPACE_WARNING_EVENTS" in app
    assert "WORKSPACE_WATCH_EVENTS" in app
    assert "function toggleAlertPill" in app
    assert "function syncRadarControls" in app
    assert "String(product?.level || '') === level" in app
    assert "radarEngine.isConusSite(site)" in app
    assert "byId('workspace-radar-product-options').hidden = !hasSite" in app
    assert "byId('workspace-radar-enabled').addEventListener('change'" in app
    assert "function syncRightRailVisibility" in app
    assert "onLsrReports: renderLsrReports" in app
    assert "onRenderedAlerts(features) { tools.setAlerts(features); }" in app
    assert "onWarnings: renderWarnings" in app
    assert "railScope: 'national'" in app
    assert "refreshFeeds: false" in app
    assert "const railScope = options.railScope === 'national' ? 'national' : 'rendered'" in (
        Path(BASE_DIR) / "frontend" / "pages" / "alerts" / "alerts-engine.js"
    ).read_text(encoding="utf-8")
    assert "'/api/data/alerts?geometry_mode=full&zoom_bucket=high'" in (
        Path(BASE_DIR) / "frontend" / "pages" / "alerts" / "alerts-engine.js"
    ).read_text(encoding="utf-8")
    assert "`/api/data/alerts/lsr?hours=${encodeURIComponent(String(hours || 24))}`" in (
        Path(BASE_DIR) / "frontend" / "pages" / "alerts" / "alerts-engine.js"
    ).read_text(encoding="utf-8")
    engine = (
        Path(BASE_DIR) / "frontend" / "pages" / "alerts" / "alerts-engine.js"
    ).read_text(encoding="utf-8")
    assert "const rail = railScope === 'national' ? railAlertBaseFeatures : full" in engine
    assert "const notificationFeatures = railScope === 'national' ? railAlertBaseFeatures : renderedAlerts" in engine
    assert "if (!selection.categories.length && railScope !== 'national')" in engine
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
    assert "function createTabbedLegendTray" in app
    assert "legendTray.legend('alerts')" in app
    assert "legendTray.markReady()" in app
    assert 'class="workspace-legend-tabs" role="tablist"' in page
    assert page.count('class="workspace-legend-tab"') == 4
    assert "fa-chevron-down" in page
    assert "panel.classList.toggle('is-collapsed', !isOpen)" in app
    assert "elevation: '0.5'" in app
    assert "radarEngine.loadFrames({ refresh: true })" in app
    assert "notifyNewAlerts: false" in app
    assert 'id="workspace-alert-all" type="button" aria-pressed="false"' in page
    assert 'data-warning="all"' not in page
    assert 'data-watch="all"' not in page
    assert 'class="is-active" type="button" data-warning="tor" aria-pressed="true"' in page
    assert 'class="is-active" type="button" data-warning="svr" aria-pressed="true"' in page
    assert 'data-warning="sps" aria-pressed="false" title="Special Weather Statement">SPS</button>' in page
    assert 'class="is-active" type="button" data-watch="tor" aria-pressed="true" title="Tornado Watch"' in page
    assert 'class="is-active" type="button" data-watch="svr" aria-pressed="true" title="Severe Thunderstorm Watch"' in page
    assert 'data-watch="fld" aria-pressed="false" title="Flood Watch / Flash Flood Watch">FLD</button>' in page
    assert "sps: ['Special Weather Statement']" in app
    assert "fld: ['Flash Flood Watch', 'Flood Watch']" in app
    assert "categories.add('Severe Weather Watches')" in app
    assert "categories.add('Hydrology Alerts')" in app
    assert "eventTypes: [...new Set([...warningEvents, ...watchEvents])]" in app
    assert "categories: Object.keys(ALERT_CATEGORIES)" in app
    assert "warningTypes: Object.keys(SEVERE_EVENTS)" in app
    assert "subdueWatches: true" in app
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


def test_shared_radar_refresh_uses_latest_only_followup_and_cache_busted_assets():
    root = Path(BASE_DIR) / "frontend" / "pages"
    engine = (root / "radar" / "radar-engine.js").read_text(encoding="utf-8")
    radar_app = (root / "radar" / "radar-page.js").read_text(encoding="utf-8")
    radar_page = (root / "radar" / "radar.html").read_text(encoding="utf-8")
    workspace_app = (root / "workspace" / "workspace-app.js").read_text(
        encoding="utf-8"
    )
    workspace_page = (root / "workspace" / "workspace.html").read_text(
        encoding="utf-8"
    )

    assert "async function refreshAll({ refresh = true } = {})" in engine
    assert "const framesPromise = loadFrames({ refresh });" in engine
    assert "data?.latest_refreshing" in engine
    assert "latestPollAttempt < LATEST_REFRESH_POLL_LIMIT" in engine
    assert "radar-engine.js?v=20260729b" in radar_app
    assert "radar-engine.js?v=20260729b" in workspace_app
    assert "radar-page.js?v=20260729b" in radar_page
    assert "workspace-app.js?v=20260731b" in workspace_page


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


def test_workspace_alerts_use_wide_unscrolled_legend_and_stale_while_revalidate_cache():
    app = (
        Path(BASE_DIR) / "frontend" / "pages" / "workspace" / "workspace-app.js"
    ).read_text(encoding="utf-8")
    engine = (
        Path(BASE_DIR) / "frontend" / "pages" / "alerts" / "alerts-engine.js"
    ).read_text(encoding="utf-8")
    styles = (
        Path(BASE_DIR) / "frontend" / "pages" / "workspace" / "workspace.css"
    ).read_text(encoding="utf-8")

    assert ".workspace-legends { position: absolute; right: 12px; bottom:" in styles
    assert "left: 12px; z-index: 800" in styles
    assert "#workspace-alerts-legend { max-height: none; overflow: visible; }" in styles
    assert "#workspace-alerts-legend .core-legend-categories" in styles
    assert "#workspace-alerts-legend .core-legend-category-code" in styles
    assert "text-overflow: clip" in styles
    assert "overflow-wrap: anywhere" in styles
    assert ".workspace-legend-content .core-legend-body { padding: 0 15px; }" in styles
    assert "LIVE_ALERT_CACHE_NAME = 'nch-alerts-live-v1'" in engine
    assert "const persisted = await readLiveAlertCache(api, paths)" in engine
    assert "const freshPayloads = await freshPromise" in engine
    assert "void writeLiveAlertCache(api, paths, freshPayloads)" in engine
    assert "await Promise.all([radarEngine.loadCatalog(), refreshAlerts()])" in app


def test_workspace_selected_alert_overlay_is_independent_of_polygon_filters():
    app = (
        Path(BASE_DIR) / "frontend" / "pages" / "workspace" / "workspace-app.js"
    ).read_text(encoding="utf-8")
    engine = (
        Path(BASE_DIR) / "frontend" / "pages" / "alerts" / "alerts-engine.js"
    ).read_text(encoding="utf-8")
    detail = (
        Path(BASE_DIR) / "frontend" / "pages" / "alerts" / "alerts-detail.js"
    ).read_text(encoding="utf-8")
    styles = (
        Path(BASE_DIR) / "frontend" / "pages" / "workspace" / "workspace.css"
    ).read_text(encoding="utf-8")

    assert "alertsEngine.showSelectedAlert(feature)" in app
    assert "alertsEngine?.clearSelectedAlert()" in app
    assert "button.dataset.alertId = alertFeatureId(feature)" in app
    assert "button.classList.add('is-selected')" in app
    assert "onSelectedAlertRemoved(feature)" in app
    assert "onClose(mode) { if (mode === 'alert') clearSelectedAlert(); }" in app
    assert "mapCore.map.on('movestart zoomstart', detail.closeLsr)" in app
    assert "mapCore.map.on('movestart zoomstart', detail.close)" not in app
    assert "const selectedAlertPane = map.createPane('alerts-selected')" in engine
    assert "function showSelectedAlert(feature)" in engine
    assert "function reconcileSelectedAlert(features)" in engine
    assert "...alertStyle(feature)" in engine
    assert "color: '#f8fafc'" not in engine
    assert "Selected alert" not in engine
    assert "alerts-selected-legend-area" not in engine
    assert "reconcileSelectedAlert: true" in engine
    assert "selectedAlertMissingGraceRefreshes: 1" in app
    assert "const selectedAlertMissingGraceRefreshes" in engine
    assert "selectedAlertMissingRefreshes <= selectedAlertMissingGraceRefreshes" in engine
    assert "[...railAlertBaseFeatures, ...fullBaseFeatures]" in engine
    assert "options.onClose?.(closedMode)" in detail
    assert "alerts-selected-legend-section" in engine
    assert ".alerts-warning-card.is-selected" in styles
    assert ".alerts-selected-polygon" not in styles


def test_workspace_suppresses_alert_tooltips_for_radar_tools():
    app = (
        Path(BASE_DIR) / "frontend" / "pages" / "workspace" / "workspace-app.js"
    ).read_text(encoding="utf-8")
    styles = (
        Path(BASE_DIR) / "frontend" / "pages" / "workspace" / "workspace.css"
    ).read_text(encoding="utf-8")

    assert "function syncAlertTooltipSuppression()" in app
    assert "byId('workspace-radar-tracks').checked" in app
    assert "byId('workspace-radar-inspector').checked" in app
    assert "classList.toggle('is-alert-tooltip-suppressed', suppress)" in app
    assert ".is-alert-tooltip-suppressed .leaflet-tooltip.alerts-hover-tip:not(.alerts-lsr-hover-tip)" in styles


def test_workspace_all_alerts_pill_matches_standalone_category_scope():
    page = (
        Path(BASE_DIR) / "frontend" / "pages" / "workspace" / "workspace.html"
    ).read_text(encoding="utf-8")
    app = (
        Path(BASE_DIR) / "frontend" / "pages" / "workspace" / "workspace-app.js"
    ).read_text(encoding="utf-8")

    assert 'id="workspace-alert-all" type="button" aria-pressed="false"' in page
    assert "Object.keys(ALERT_CATEGORIES)" in app
    assert "Object.keys(SEVERE_EVENTS)" in app
    assert "setAllAlertsPill(false)" in app
    assert "#workspace-warning-filters button, #workspace-watch-filters button" in app


def test_workspace_storm_track_disable_invalidates_inflight_load():
    engine = (
        Path(BASE_DIR) / "frontend" / "pages" / "radar" / "radar-engine.js"
    ).read_text(encoding="utf-8")

    assert "seq !== trackSequence || !tracksVisible || getSelection().site !== selection.site" in engine
    assert "else {\n                trackSequence += 1;\n                stormLayer.clearLayers();" in engine
    assert "selectedCell = null" not in engine.split("setStormTracksVisible(value)", 1)[1]


def test_workspace_watch_filters_are_independent_and_workspace_scoped():
    page = (
        Path(BASE_DIR) / "frontend" / "pages" / "workspace" / "workspace.html"
    ).read_text(encoding="utf-8")
    app = (
        Path(BASE_DIR) / "frontend" / "pages" / "workspace" / "workspace-app.js"
    ).read_text(encoding="utf-8")
    engine = (
        Path(BASE_DIR) / "frontend" / "pages" / "alerts" / "alerts-engine.js"
    ).read_text(encoding="utf-8")
    map_core = (
        Path(BASE_DIR) / "frontend" / "core" / "map-core.js"
    ).read_text(encoding="utf-8")
    styles = (
        Path(BASE_DIR) / "frontend" / "pages" / "workspace" / "workspace.css"
    ).read_text(encoding="utf-8")

    assert 'id="workspace-watch-filters"' in page
    assert 'aria-label="Watch polygons"' in page
    assert 'data-watch="all" aria-pressed="false"' in page
    assert 'data-watch="tor" aria-pressed="true" title="Tornado Watch"' in page
    assert 'data-watch="svr" aria-pressed="true" title="Severe Thunderstorm Watch"' in page
    assert 'data-watch="fld" aria-pressed="false" title="Flood Watch / Flash Flood Watch"' in page
    assert "fld: ['Flash Flood Watch', 'Flood Watch']" in app
    assert "activeAlertEvents('workspace-watch-filters', 'watch', WORKSPACE_WATCH_EVENTS)" in app
    assert "byId('workspace-watch-filters').addEventListener('click'" in app
    assert "syncLayerToggle('workspace-alerts-enabled', 'workspace-watch-filters')" in app
    assert "subdueWatches: true" in app
    assert "alertPaneZIndex: 440" in app
    assert "const subdueWatches = options.subdueWatches === true" in engine
    assert "watchesPane.style.zIndex = String(alertPaneZIndex - 10)" in engine
    assert "alertsPane.style.zIndex = String(alertPaneZIndex)" in engine
    assert "selectedAlertPane.style.zIndex = String(alertPaneZIndex + 10)" in engine
    assert "boundaryPane.style.zIndex = '420'" in map_core
    assert "fillOpacity: isSubduedWatch ? opacity * 0.16 : opacity" in engine
    assert "buildAlertLayer(displayedWatches, 'alerts-watches')" in engine
    assert "alerts-watch-legend-color" in engine
    assert "#workspace-watch-filters { grid-template-columns: repeat(4" in styles


def test_legacy_monolith_assets_are_deleted():
    assert not (Path(BASE_DIR) / "weather.html").exists()
    assert not (Path(BASE_DIR) / "js" / "weather.js").exists()
    assert not (Path(BASE_DIR) / "js" / "product-page-shell.js").exists()
    assert not (Path(BASE_DIR) / "js" / "product-app-context.js").exists()
    assert not (Path(BASE_DIR) / "css" / "dashboard.css").exists()
