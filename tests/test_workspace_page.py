from pathlib import Path

from app_core.paths import BASE_DIR
from routes.pages import read_weather_page, read_workspace_page


def test_workspace_route_serves_new_page_and_legacy_url_redirects():
    response = read_workspace_page()
    expected = Path(BASE_DIR) / "frontend" / "pages" / "workspace" / "workspace.html"

    assert Path(response.path) == expected
    assert read_weather_page().headers["location"] == "/workspace"


def test_workspace_declares_favicon_and_spc_uses_one_module_identity():
    workspace = (
        Path(BASE_DIR) / "frontend" / "pages" / "workspace" / "workspace.html"
    ).read_text(encoding="utf-8")
    workspace_app = (
        Path(BASE_DIR) / "frontend" / "pages" / "workspace" / "workspace-app.js"
    ).read_text(encoding="utf-8")
    spc_page = (
        Path(BASE_DIR) / "frontend" / "pages" / "spc" / "spc-page.js"
    ).read_text(encoding="utf-8")
    spc_render = (
        Path(BASE_DIR) / "frontend" / "pages" / "spc" / "spc-render.js"
    ).read_text(encoding="utf-8")

    assert '<link rel="icon" href="/img/favicon.ico">' in workspace
    expected = "spc-engine.js?v=20260801a"
    assert expected in workspace_app
    assert expected in spc_page
    assert expected in spc_render


def test_workspace_composes_engines_without_page_controllers():
    app = (
        Path(BASE_DIR) / "frontend" / "pages" / "workspace" / "workspace-app.js"
    ).read_text(encoding="utf-8")

    assert "../alerts/alerts-engine.js" in app
    assert "../radar/radar-engine.js" in app
    assert "./workspace-satellite.js" in app
    assert "./workspace-rtma.js" in app
    assert "./workspace-mrms.js" in app
    assert "alerts-page.js" not in app
    assert "radar-page.js" not in app
    assert "satellite-page.js" not in app
    assert "rtma-page.js" not in app
    assert "mrms-page.js" not in app
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
    map_core = (
        Path(BASE_DIR) / "frontend" / "core" / "map-core.js"
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
    assert page.count('workspace-layer-group workspace-placeholder') == 0
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
    assert "WORKSPACE_REGION_BOUNDS" not in app
    assert "const REGION_BOUNDS = Object.freeze" in map_core
    assert "mapCore.fitRegion(region, fitOptions)" in app
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
    assert "onLsrDetail(feature) {" in app
    assert "detail.openLsr(feature);" in app
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
    assert page.count('class="workspace-legend-tab"') == 10
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


def test_workspace_spc_phase1_is_curated_default_off_and_page_capable():
    root = Path(BASE_DIR) / "frontend" / "pages"
    page = (root / "workspace" / "workspace.html").read_text(encoding="utf-8")
    app = (root / "workspace" / "workspace-app.js").read_text(encoding="utf-8")
    styles = (root / "workspace" / "workspace.css").read_text(encoding="utf-8")
    carousel = (root / "workspace" / "workspace-detail-carousel.js").read_text(
        encoding="utf-8"
    )
    renderer = (root / "spc" / "spc-render.js").read_text(encoding="utf-8")
    spc_detail = (root / "spc" / "spc-detail.js").read_text(encoding="utf-8")
    alert_detail = (root / "alerts" / "alerts-detail.js").read_text(
        encoding="utf-8"
    )

    assert 'id="workspace-spc-enabled" type="checkbox"' in page
    assert 'id="workspace-spc-enabled" type="checkbox" checked' not in page
    assert 'id="workspace-spc-controls" class="workspace-group-body is-disabled"' in page
    assert page.count("data-spc-hazard=") == 4
    assert all(
        f'data-spc-hazard="{hazard}" aria-pressed="false" disabled' in page
        for hazard in ["cat", "torn", "wind", "hail"]
    )
    assert 'data-spc-hazard="cat" aria-pressed="false" disabled>CAT</button>' in page
    assert 'data-spc-hazard="torn" aria-pressed="false" disabled>TOR</button>' in page
    assert 'data-spc-hazard="wind" aria-pressed="false" disabled>Wind</button>' in page
    assert 'data-spc-hazard="hail" aria-pressed="false" disabled>Hail</button>' in page
    assert 'id="workspace-spc-mds" type="checkbox" disabled' in page
    assert page.count('data-spc-watch-type="tor"') == 2
    assert page.count('data-spc-watch-type="svr"') == 2
    assert page.count('data-spc-watch-mode="polygon"') == 2
    assert page.count('data-spc-watch-mode="counties"') == 2
    assert '<span class="spc-dual-label">TOR</span>' in page
    assert '<span class="spc-dual-label">SVR</span>' in page
    assert 'id="workspace-spc-fill-opacity" type="range" min="0.1" max="1" step="0.05" value="0.5" disabled' in page
    assert "workspace-spc-stroke-opacity" not in page
    assert "workspace-control-note" not in page
    assert 'id="workspace-spc-legend-tab"' in page
    assert 'id="workspace-spc-legend"' in page
    assert "day: 1" in app
    assert "const cigHazard = CIG_OVERLAY_BY_HAZARD[baseHazard]" in app
    assert "reportsEnabled: false" in app
    assert "mdsEnabled: byId('workspace-spc-mds').checked" in app
    assert "watchesEnabled: watchLayers.length > 0" in app
    assert "if (peer !== input) peer.checked = false" in app
    assert "tasks.push(refreshSpc({ keepDetail: true }))" in app
    assert "const WORKSPACE_SPC_STROKE_OPACITY = 0.1" in app
    assert "spcRenderer.setStrokeOpacity(WORKSPACE_SPC_STROKE_OPACITY)" in app
    assert "workspace-spc-stroke-opacity" not in app
    assert "Significant-threat hatching is paired automatically" in app
    assert "#workspace-spc-legend .spc-legend-item" in styles
    assert (
        "#workspace-spc-legend .spc-legend-flow {\n"
        "    display: grid;\n"
        "    grid-template-columns: repeat(5, minmax(0, 1fr))"
    ) in styles
    assert "background: rgba(17, 31, 53, .78)" in styles
    assert ".workspace-spc-legend-note" in styles
    assert ".workspace-control-note" not in styles

    assert "onDetailPages(latlng, pages)" in app
    assert "detail.hide();" in app
    assert "createWorkspaceDetailCarousel" in app
    assert "detailPagesAtPoint" in renderer
    assert "seenWatches" in renderer
    assert "seenMds" in renderer
    assert "buildSpcOutlookDetailHtml" in spc_detail
    assert "buildSpcTextDetailHtml" in spc_detail
    assert "wireSpcDetailContent" in spc_detail
    assert "workspace-context-dots" in carousel
    assert "ArrowLeft" in carousel and "ArrowRight" in carousel
    assert "touchstart" in carousel and "touchend" in carousel
    assert "hide() { close({ notify: false }); }" in alert_detail


def test_workspace_satellite_phase2_is_curated_default_off_and_uses_shared_timeline():
    root = Path(BASE_DIR) / "frontend" / "pages"
    page = (root / "workspace" / "workspace.html").read_text(encoding="utf-8")
    app = (root / "workspace" / "workspace-app.js").read_text(encoding="utf-8")
    satellite = (root / "workspace" / "workspace-satellite.js").read_text(
        encoding="utf-8"
    )

    assert 'id="workspace-satellite-enabled" type="checkbox"' in page
    assert 'id="workspace-satellite-enabled" type="checkbox" checked' not in page
    assert (
        'id="workspace-satellite-controls" class="workspace-group-body is-disabled" hidden'
        in page
    )
    assert page.count("data-workspace-satellite-platform=") == 2
    assert 'data-workspace-satellite-platform="goes19" disabled>GOES-19</button>' in page
    assert 'data-workspace-satellite-platform="goes18" disabled>GOES-18</button>' in page
    assert 'id="workspace-satellite-sector-stage" hidden' in page
    assert page.count("data-workspace-satellite-region=") == 4
    assert all(
        f'data-workspace-satellite-region="{region}" disabled>{region}</button>'
        in page
        for region in ["CONUS", "AK", "HI", "PR"]
    )
    assert ">Full Disk</button>" not in page
    assert 'id="workspace-satellite-product-stage" hidden' in page
    assert 'id="workspace-satellite-product" disabled' in page
    assert "workspace-satellite-view" not in page
    assert 'id="workspace-satellite-legend-tab"' in page
    assert 'id="workspace-satellite-legend"' in page

    assert "createWorkspaceSatellite" in app
    assert "workspaceSatellite.refresh({ refresh: true, auto: true })" in app
    assert "workspaceSatellite.reset()" in app
    assert "workspaceSatellite.destroy()" in app
    assert "String(region || '').toUpperCase() === 'PR'" in app
    assert "mapCore.map.getZoom() > 9" in app
    assert "mapCore.map.setZoom(9" in app
    assert "../satellite/satellite-engine.js" in satellite
    assert "../satellite/satellite-anim.js" in satellite
    assert "satellite-page.js" not in satellite
    assert "maxFramesForSector(expectedSelection.sector)" in satellite
    assert "return String(sector || '').toUpperCase() === 'CONUS' ? 12 : 6" in satellite
    assert "hours: 1" in satellite
    assert "AUTO_REFRESH_INTERVAL_MS = 5 * 60 * 1000" in satellite
    assert "CONUS: 'CONUS'" in satellite
    assert "AK: 'FullDisk'" in satellite
    assert "HI: 'FullDisk'" in satellite
    assert "PR: 'FullDisk'" in satellite
    assert "syncPillGroup(platformPills, 'workspace-satellite-platform'" in satellite
    assert "syncPillGroup(sectorPills, 'workspace-satellite-region'" in satellite
    assert "bindPillGroup(platformPills, 'workspace-satellite-platform'" in satellite
    assert "bindPillGroup(sectorPills, 'workspace-satellite-region'" in satellite
    assert "getAttribute(`data-${dataAttribute}`)" in satellite
    assert "onRegionSelected" not in satellite
    assert "onRegionSelected(region)" not in app
    assert "['GeoColor', 'GeoColor']" in satellite
    assert "['Channel13', 'Clean IR']" in satellite
    assert "['Channel09RAMSDIS', 'Water Vapor']" in satellite
    assert "['Channel07Fire', 'Shortwave IR / Fire']" in satellite
    assert "['Channel02', 'Visible']" in satellite
    assert "animator.prepareForZoom()" in satellite
    assert "satelliteFrameIndexAtOrBefore" in satellite
    assert "showFrameForTimestamp" in satellite
    assert "onFrames?.([...frames], { index: nextIndex })" in satellite
    assert "awaitFrameOnPlay: true" in app
    assert "workspaceTimelineFrameSets = { radar: [], mrms: [], satellite: [], rtma: [] }" in app
    assert "selectWorkspaceTimelineSource(workspaceTimelineFrameSets)" in app
    assert "workspaceSatellite.showFrameForTimestamp(timestamp" in app
    assert "workspaceSatellite.showFrameAt(safeIndex" in app


def test_workspace_overlay_order_places_satellite_above_rtma_gradient_and_spc():
    root = Path(BASE_DIR) / "frontend" / "pages"
    app = (root / "workspace" / "workspace-app.js").read_text(encoding="utf-8")
    satellite = (root / "satellite" / "satellite-anim.js").read_text(
        encoding="utf-8"
    )
    spc = (root / "spc" / "spc-render.js").read_text(encoding="utf-8")
    radar = (root / "radar" / "radar-engine.js").read_text(encoding="utf-8")
    mrms = (root / "mrms" / "mrms-engine.js").read_text(encoding="utf-8")

    assert "pane.style.zIndex = '330'" in satellite
    assert "rtmaGradientPane.style.zIndex = '350'" in app
    assert "gradientPaneName: 'workspace-rtma-gradient'" in app
    assert "mrmsPane.style.zIndex = '375'" in app
    assert "paneName: 'workspace-mrms-overlays'" in app
    assert "...(paneName ? { pane: paneName } : {})" in mrms
    assert "wpcPane.style.zIndex = '390'" in app
    assert "paneName: 'workspace-wpc-overlays'" in app
    assert "spcPane.style.zIndex = '400'" in app
    assert "paneName: 'workspace-spc-overlays'" in app
    assert "pane: paneName" in spc
    assert "satellitePane.style.zIndex = '405'" in app
    assert "radarPane.style.zIndex = '410'" in radar
    assert "rtmaValuesPane.style.zIndex = '425'" in app
    assert "pointPaneName: 'workspace-rtma-values'" in app
    assert "alertPaneZIndex: 440" in app


def test_workspace_rtma_is_curated_default_off_and_uses_shared_timeline():
    root = Path(BASE_DIR) / "frontend" / "pages"
    page = (root / "workspace" / "workspace.html").read_text(encoding="utf-8")
    app = (root / "workspace" / "workspace-app.js").read_text(encoding="utf-8")
    rtma = (root / "workspace" / "workspace-rtma.js").read_text(encoding="utf-8")
    engine = (root / "rtma" / "rtma-engine.js").read_text(encoding="utf-8")

    assert 'id="workspace-rtma-enabled" type="checkbox"' in page
    assert 'id="workspace-rtma-enabled" type="checkbox" checked' not in page
    assert 'id="workspace-rtma-controls" class="workspace-group-body is-disabled" hidden' in page
    assert 'id="workspace-rtma-product"' not in page
    assert 'id="workspace-rtma-values"' not in page
    assert 'id="workspace-rtma-products" class="workspace-pills workspace-rtma-product-pills"' in page
    assert page.count("data-rtma-product=") == 6
    assert page.index('data-rtma-product="temperature"') < page.index('data-rtma-product="apparent_temperature"')
    assert page.index('data-rtma-product="apparent_temperature"') < page.index('data-rtma-product="dew_point"')
    assert 'data-rtma-product="winds" aria-pressed="false" disabled>Winds</button>' in page
    assert 'data-rtma-product="wind_speed"' not in page
    assert 'data-rtma-product="wind_direction"' not in page
    assert 'id="workspace-rtma-modes" class="workspace-pills workspace-rtma-mode-pills"' in page
    assert 'class="is-active" type="button" data-rtma-mode="values" aria-pressed="true" disabled>Values</button>' in page
    assert 'data-rtma-mode="gradient" aria-pressed="false" disabled>Gradient</button>' in page
    assert 'id="workspace-rtma-opacity" type="range" min="0.1" max="1" step="0.05" value="0.7" disabled' in page
    assert 'id="workspace-rtma-legend-tab"' in page
    assert 'id="workspace-rtma-legend"' in page

    assert "createWorkspaceRtma" in app
    assert "workspaceRtma.refresh({ auto: true })" in app
    assert "workspaceRtma.setRegion()" in app
    assert "workspaceRtma.reset()" in app
    assert "workspaceRtma.destroy()" in app
    assert "../rtma/rtma-engine.js" in rtma
    assert "rtma-page.js" not in rtma
    assert "const AUTO_REFRESH_INTERVAL_MS = 15 * 60 * 1000" in rtma
    assert "const STREAM = 'rtma_rapid_update'" in rtma
    assert "const supportsCurrentRegion = () => dataRegionForMapRegion(getRegion()) === 'CONUS'" in rtma
    assert "auto && !refreshPending" in rtma
    assert "{ value: 'temperature', label: 'Temperature', product: 'temperature' }" in rtma
    assert "{ value: 'apparent_temperature', label: 'Feels Like', product: 'apparent_temperature' }" in rtma
    assert "{ value: 'dew_point', label: 'Dew Point', product: 'dew_point' }" in rtma
    assert "{ value: 'winds', label: 'Winds', product: 'wind_speed', secondaryProduct: 'wind_direction' }" in rtma
    assert "{ value: 'wind_gust', label: 'Wind Gust', product: 'wind_gust' }" in rtma
    assert "{ value: 'visibility', label: 'Visibility', product: 'visibility' }" in rtma
    assert "temperature_change_24h" not in rtma
    assert "const SOURCE_LOOKBACK_HOURS = 2" in rtma
    assert "workspaceFrameWindowWithPredecessor" in rtma
    assert "onFrames?.(timelineSourceFrames.map" in rtma
    assert "engine.loadFrames(primarySelection, SOURCE_LOOKBACK_HOURS)" in rtma
    assert "engine.fetchNewFrames" in rtma
    assert "showFrameForTimestamp" in rtma
    assert "matchingSecondaryFrame" in rtma
    assert "loadLatest(selection())" in rtma
    assert "showValues = true" in rtma
    assert "showGradient = false" in rtma
    assert "engine.loadSecondary(selection(), secondaryProduct)" in rtma
    assert "dataRegionForMapRegion(getRegion())" in rtma
    assert "paneName = ''" in engine
    assert "gradientPaneName = ''" in engine
    assert "pointPaneName = ''" in engine
    assert "setShowGradient" in engine
    assert "pendingGradientLayer" in engine
    assert ".workspace-rtma-product-pills," in (
        root / "workspace" / "workspace.css"
    ).read_text(encoding="utf-8")
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in (
        root / "workspace" / "workspace.css"
    ).read_text(encoding="utf-8")


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
    assert "radar-engine.js?v=20260802a" in workspace_app
    assert "radar-page.js?v=20260814a" in radar_page
    assert "workspace-satellite.js?v=20260814b" in workspace_app
    assert "workspace-wpc.js?v=20260804b" in workspace_app
    assert "workspace.css?v=20260809a" in workspace_page
    assert "workspace-app.js?v=20260814b" in workspace_page


def test_workspace_layer_groups_only_expand_while_enabled():
    root = Path(BASE_DIR) / "frontend" / "pages" / "workspace"
    page = (root / "workspace.html").read_text(encoding="utf-8")
    app = (root / "workspace-app.js").read_text(encoding="utf-8")
    styles = (root / "workspace.css").read_text(encoding="utf-8")

    assert all(
        f'id="workspace-{layer}-enabled" type="checkbox"' in page
        for layer in ("radar", "alerts", "lsr", "spc", "satellite", "rtma", "mrms", "wpc", "water")
    )
    assert "const layerGroupBindings" in app
    assert "if (!enabled) group.open = false;" in app
    assert "else if (input === expandedInput) group.open = true;" in app
    assert "if (!input.checked && !event.target.closest('.workspace-layer-toggle')) event.preventDefault();" in app
    assert "if (group.open && !input.checked) group.open = false;" in app
    assert "group.classList.toggle('is-layer-disabled', !enabled);" in app
    assert app.count("syncWorkspaceLayerGroups();") == 3
    assert ".workspace-layer-group.is-layer-disabled > .workspace-group-summary::after" in styles


def test_workspace_mrms_is_curated_default_off_and_uses_shared_timeline():
    root = Path(BASE_DIR) / "frontend" / "pages"
    page = (root / "workspace" / "workspace.html").read_text(encoding="utf-8")
    app = (root / "workspace" / "workspace-app.js").read_text(encoding="utf-8")
    mrms = (root / "workspace" / "workspace-mrms.js").read_text(encoding="utf-8")
    engine = (root / "mrms" / "mrms-engine.js").read_text(encoding="utf-8")

    assert 'id="workspace-mrms-enabled" type="checkbox"' in page
    assert 'id="workspace-mrms-enabled" type="checkbox" checked' not in page
    assert 'id="workspace-mrms-controls" class="workspace-group-body is-disabled" hidden' in page
    assert page.count("data-mrms-product=") == 6
    assert 'data-mrms-product="rotation"' in page
    assert 'data-mrms-product="mesh_instant"' in page
    assert 'data-mrms-product="mesh_30min"' in page
    assert 'data-mrms-product="lightning_30min"' in page
    assert 'data-mrms-product="precip_type"' in page
    assert 'data-mrms-product="base_reflectivity"' in page
    assert 'id="workspace-mrms-opacity" type="range" min="0.1" max="1" step="0.05" value="0.7" disabled' in page
    assert 'id="workspace-mrms-legend-tab"' in page
    assert 'id="workspace-mrms-legend"' in page

    assert "createWorkspaceMrms" in app
    assert "workspaceMrms.refresh({ auto: true })" in app
    assert "workspaceMrms.setRegion()" in app
    assert "workspaceMrms.reset()" in app
    assert "workspaceMrms.destroy()" in app
    assert "mrmsPane.style.zIndex = '375'" in app
    assert "paneName: 'workspace-mrms-overlays'" in app
    assert "../mrms/mrms-engine.js" in mrms
    assert "mrms-page.js" not in mrms
    assert "const AUTO_REFRESH_INTERVAL_MS = 2 * 60 * 1000" in mrms
    assert "RotationTrack_LL_30min" in mrms
    assert "MESH_Instant" in mrms
    assert "MESH_Max_30min" in mrms
    assert "Lightning_30min" in mrms
    assert "PrecipFlag" in mrms
    assert "Refl_BaseQC" in mrms
    assert "loadLatest(selected.product)" in mrms
    assert "engine.loadFrames(selected.product, LOOKBACK_HOURS)" in mrms
    assert "engine.fetchNewFrames" in mrms
    assert "showFrameForTimestamp" in mrms
    assert "onFrames?.(timelineFrames.map" in mrms
    assert "supportsCurrentRegion" in mrms
    assert "paneName = ''" in engine
    assert "pendingOverlay" in engine
    assert "newOverlay.once('load'" in engine
    assert "leaflet.tileLayer" in engine
    assert "prepare_url" in engine
    assert "Native tile preparation failed; retaining PNG fallback" in engine


def test_workspace_wpc_is_curated_default_off_and_stays_below_live_layers():
    root = Path(BASE_DIR) / "frontend" / "pages"
    page = (root / "workspace" / "workspace.html").read_text(encoding="utf-8")
    app = (root / "workspace" / "workspace-app.js").read_text(encoding="utf-8")
    workspace_wpc = (root / "workspace" / "workspace-wpc.js").read_text(
        encoding="utf-8"
    )
    engine = (root / "wpc" / "wpc-engine.js").read_text(encoding="utf-8")

    assert 'id="workspace-wpc-enabled" type="checkbox"' in page
    assert 'id="workspace-wpc-enabled" type="checkbox" checked' not in page
    assert 'id="workspace-wpc-controls" class="workspace-group-body is-disabled" hidden' in page
    assert page.count("data-wpc-group=") == 4
    assert all(
        f'data-wpc-group="{group}"' in page
        for group in ["ero", "qpf", "mpd", "winter"]
    )
    assert 'id="workspace-wpc-product-pills"' in page
    assert 'id="workspace-wpc-winter-days"' in page
    assert page.count("data-wpc-winter-day=") == 3
    assert 'id="workspace-wpc-product-select-wrap" class="workspace-wpc-selection" hidden' in page
    assert 'id="workspace-wpc-product" disabled' in page
    assert 'id="workspace-wpc-opacity" type="range" min="0.1" max="1" step="0.05" value="0.55" disabled' in page
    assert 'id="workspace-wpc-legend-tab"' in page
    assert 'id="workspace-wpc-legend"' in page

    assert "createWorkspaceWpc" in app
    assert "workspaceWpc.refresh({ auto: true })" in app
    assert "workspaceWpc.setRegion()" in app
    assert "workspaceWpc.reset()" in app
    assert "workspaceWpc.destroy()" in app
    assert "wpcPane.style.zIndex = '390'" in app
    assert "paneName: 'workspace-wpc-overlays'" in app
    assert "../wpc/wpc-engine.js" in workspace_wpc
    assert "wpc-page.js" not in workspace_wpc
    assert "const AUTO_REFRESH_INTERVAL_MS = 30 * 60 * 1000" in workspace_wpc
    assert "const PILL_GROUPS = new Set(['ero', 'qpf'])" in workspace_wpc
    assert all(
        product_id in workspace_wpc
        for product_id in [
            "qpf48_day1_2",
            "qpf72_day1_3",
            "qpf120_day1_5",
            "qpf168_day1_7",
        ]
    )
    assert "activeProductId = productsForActiveGroup()[0]?.id || ''" in workspace_wpc
    assert "data-wpc-product" in workspace_wpc
    assert "data-wpc-winter-day" in workspace_wpc
    assert "productDay(product) === activeWinterDay" in workspace_wpc
    assert "WPC Workspace products are available for CONUS only" in workspace_wpc
    assert "paneName = ''" in engine
    assert "const layerPane = paneName || 'overlayPane'" in engine
    assert engine.count("pane: layerPane") == 2


def test_workspace_water_reuses_shared_engine_and_is_default_off():
    root = Path(BASE_DIR) / "frontend" / "pages"
    page = (root / "workspace" / "workspace.html").read_text(encoding="utf-8")
    app = (root / "workspace" / "workspace-app.js").read_text(encoding="utf-8")
    workspace_water = (root / "workspace" / "workspace-water.js").read_text(
        encoding="utf-8"
    )
    water_engine = (root / "water" / "water-engine.js").read_text(
        encoding="utf-8"
    )
    water_app = (root / "water" / "water-app.js").read_text(encoding="utf-8")

    assert 'id="workspace-water-enabled" type="checkbox"' in page
    assert 'id="workspace-water-enabled" type="checkbox" checked' not in page
    assert 'id="workspace-water-controls" class="workspace-group-body is-disabled" hidden' in page
    assert page.count('id="workspace-water-networks"') == 1
    assert all(
        f'data-water-network="{network}" aria-pressed="true" disabled>{label}</button>' in page
        for network, label in [("river", "RIVER"), ("coastal", "COAST"), ("buoy", "BUOY")]
    )
    assert "data-water-flood=" not in page
    assert "Minimum Flood Stage" not in page
    assert 'id="workspace-water-legend-tab"' in page
    assert 'id="workspace-water-legend"' in page
    assert 'id="workspace-water-detail" class="water-detail workspace-water-detail"' in page

    assert "createWorkspaceWater" in app
    assert "waterPane.style.zIndex = '470'" in app
    assert "workspaceWater.refresh({ auto: true })" in app
    assert app.count("workspaceWater.closeDetail()") >= 3
    assert "workspaceWater.setRegion()" in app
    assert "workspaceWater.reset()" in app
    assert "workspaceWater.destroy()" in app
    assert "../water/water-engine.js" in workspace_water
    assert "water-app.js" not in workspace_water
    assert "const AUTO_REFRESH_INTERVAL_MS = 5 * 60 * 1000" in workspace_water
    assert "networkPills.addEventListener('click'" in workspace_water
    assert 'data-water-network][aria-pressed="true"]' in workspace_water
    assert "button.getAttribute('aria-pressed') !== 'true'" in workspace_water
    assert "data-water-flood" not in workspace_water
    assert "setFloodFilter" not in workspace_water
    assert "createWaterEngine" in water_app
    assert "/api/water/stations?" in water_engine
    assert "/api/water/stations/${encodeURIComponent(siteId)}" in water_engine
    assert "pane: paneName" in water_engine
    assert "map.on('moveend', onMapMoveEnd)" in water_engine


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
    assert 'data-watch="all"' not in page
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
    assert "#workspace-watch-filters { grid-template-columns: repeat(3" in styles


def test_legacy_monolith_assets_are_deleted():
    assert not (Path(BASE_DIR) / "weather.html").exists()
    assert not (Path(BASE_DIR) / "js" / "weather.js").exists()
    assert not (Path(BASE_DIR) / "js" / "product-page-shell.js").exists()
    assert not (Path(BASE_DIR) / "js" / "product-app-context.js").exists()
    assert not (Path(BASE_DIR) / "css" / "dashboard.css").exists()
