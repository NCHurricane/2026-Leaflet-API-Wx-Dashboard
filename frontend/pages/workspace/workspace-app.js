import * as api from '../../core/api.js';
import { createMapCore, REGION_LABELS } from '../../core/map-core.js';
import { renderProductNav } from '../../core/nav.js';
import { createSidebarTabs } from '../../core/sidebar-tabs.js';
import { createStatusReporter } from '../../core/status.js';
import { ALERT_CATEGORIES, LSR_CATEGORIES, SEVERE_EVENTS } from '../alerts/alerts-config.js?v=20260719a';
import { createAlertsEngine } from '../alerts/alerts-engine.js?v=20260719a';
import { createRadarEngine } from '../radar/radar-engine.js?v=20260718a';
import { createWorkspaceTools } from './workspace-tools.js?v=20260719a';

const byId = (id) => document.getElementById(id);

function createStackLegend(root) {
    return Object.freeze({
        clear() { root.replaceChildren(); root.hidden = true; },
        setHtml(html) { root.innerHTML = html || ''; root.hidden = !html; },
    });
}

function radarSelection() {
    return {
        site: String(byId('workspace-radar-site').value || '').toUpperCase(),
        product: String(byId('workspace-radar-product').value || 'L2_REF').toUpperCase(),
        elevation: String(byId('workspace-radar-elevation').value || 'auto'),
        hours: 1,
    };
}

async function initialize() {
    renderProductNav(byId('product-nav'), 'Home');
    createSidebarTabs(byId('workspace-sidebar-tabs'), { defaultTab: 'layers' });
    const regionSelect = byId('workspace-region');
    regionSelect.replaceChildren(...Object.entries(REGION_LABELS).map(([value, label]) => new Option(label, value)));
    regionSelect.value = 'CONUS';

    const mapCore = createMapCore(byId('workspace-map'), { region: 'CONUS', basemap: 'Dark (No Labels)' });
    const status = createStatusReporter({
        globalTimestamp: byId('global-timestamp'), message: byId('workspace-message'),
        updated: byId('workspace-updated'), age: byId('workspace-age'),
        provider: byId('workspace-provider'), source: byId('workspace-source'),
    });
    const alertsLegend = createStackLegend(byId('workspace-alerts-legend'));
    const radarLegend = createStackLegend(byId('workspace-radar-legend'));
    const tools = createWorkspaceTools({
        map: mapCore.map, leaflet: mapCore.leaflet, apiUrl: api.apiUrl,
        setStatus: (message) => status.setMessage(message),
    });

    const alertSelection = {
        categories: Object.keys(ALERT_CATEGORIES),
        warningTypes: Object.keys(SEVERE_EVENTS),
    };
    const alertsEngine = createAlertsEngine({
        api, mapCore, legend: alertsLegend, status,
        onAlertCount(count) { byId('workspace-alert-count').textContent = `${count} warning${count === 1 ? '' : 's'}`; },
        onLsrCount(count) { byId('workspace-lsr-count').textContent = `${count} report${count === 1 ? '' : 's'}`; },
        onWarnings(features) { tools.setAlerts(features); },
        onDetail(feature) {
            tools.setSelectedAlert(feature);
            alertsEngine.zoomTo(feature);
            status.setMessage(`${feature?.properties?.event || 'Alert'} selected for the Projected Arrival Tool.`);
        },
    });

    let radarCatalog = { sites: [], products: {} };
    const populateRadarProducts = () => {
        const current = byId('workspace-radar-product').value;
        const options = Object.entries(radarCatalog.products || {}).map(([id, product]) => new Option(product.label || id, id));
        byId('workspace-radar-product').replaceChildren(...options);
        byId('workspace-radar-product').value = options.some((option) => option.value === current) ? current : (radarCatalog.products?.L2_REF ? 'L2_REF' : options[0]?.value || '');
    };
    const radarEngine = createRadarEngine({
        api, mapCore, legend: radarLegend, status, getSelection: radarSelection,
        onCatalog(data) {
            radarCatalog = data;
            const sites = (data.sites || []).map((site) => new Option(site.site, site.site));
            byId('workspace-radar-site').replaceChildren(new Option('Select site', ''), ...sites);
            populateRadarProducts();
            radarEngine.showSiteLegend();
        },
        onElevationData(data) {
            const elevations = Array.isArray(data?.available_elevations) ? data.available_elevations : [];
            byId('workspace-radar-elevation').replaceChildren(new Option('Auto', 'auto'), ...elevations.map((value) => new Option(`${Number(value).toFixed(1)}°`, Number(value).toFixed(1))));
        },
        onFrames(frames) { if (frames.length) void radarEngine.renderFrameAt(frames.length - 1); },
        onSitePicked(site, coords) {
            byId('workspace-radar-site').value = site;
            mapCore.map.flyTo(coords, Math.max(mapCore.map.getZoom(), 8), { duration: 0.5 });
            byId('workspace-radar-enabled').checked = true;
            void radarEngine.refreshAll();
        },
        onMessage(message, tone) { status.setMessage(message, tone); },
    });

    async function refreshAlerts(options = {}) {
        if (byId('workspace-alerts-enabled').checked) await alertsEngine.loadLive(alertSelection, regionSelect.value, options);
        else { alertsEngine.setSelection({ categories: [], warningTypes: [] }); tools.setAlerts([]); }
        if (byId('workspace-lsr-enabled').checked) await alertsEngine.loadLsr(Object.keys(LSR_CATEGORIES), 24, options);
        else await alertsEngine.loadLsr([], 24, options);
    }
    async function refreshRadar() {
        if (byId('workspace-radar-enabled').checked && radarSelection().site) await radarEngine.refreshAll();
        else if (!byId('workspace-radar-enabled').checked) radarEngine.clear();
    }
    async function refreshAll(options = {}) { await Promise.all([refreshAlerts(options), refreshRadar()]); }

    byId('workspace-refresh').addEventListener('click', () => void refreshAll({ refresh: true }));
    byId('workspace-alerts-enabled').addEventListener('change', () => void refreshAlerts());
    byId('workspace-lsr-enabled').addEventListener('change', () => void refreshAlerts());
    byId('workspace-radar-enabled').addEventListener('change', () => void refreshRadar());
    byId('workspace-radar-site').addEventListener('change', () => { radarEngine.syncHighlights(); if (byId('workspace-radar-enabled').checked) void radarEngine.refreshAll(); });
    byId('workspace-radar-product').addEventListener('change', () => { if (byId('workspace-radar-enabled').checked) void radarEngine.refreshAll(); });
    byId('workspace-radar-elevation').addEventListener('change', () => { if (byId('workspace-radar-enabled').checked) void radarEngine.refreshAll(); });
    byId('workspace-radar-sites').addEventListener('change', (event) => { radarEngine.setSitesVisible(event.target.checked); if (event.target.checked) radarEngine.showSiteLegend(); });
    byId('workspace-radar-tracks').addEventListener('change', (event) => radarEngine.setStormTracksVisible(event.target.checked));
    byId('workspace-radar-inspector').addEventListener('change', (event) => radarEngine.setInspectorVisible(event.target.checked));
    regionSelect.addEventListener('change', () => { mapCore.fitRegion(regionSelect.value); void refreshAlerts({ refresh: true }); });
    byId('workspace-basemap').addEventListener('change', (event) => mapCore.setBasemap(event.target.value));
    document.querySelectorAll('[data-map-overlay]').forEach((input) => {
        input.addEventListener('change', () => void mapCore.setOverlayVisible(input.dataset.mapOverlay, input.checked));
        if (input.checked) void mapCore.setOverlayVisible(input.dataset.mapOverlay, true);
    });
    mapCore.map.on('moveend', () => { if (byId('workspace-alerts-enabled').checked || byId('workspace-lsr-enabled').checked) void refreshAlerts({ silent: true }); });

    await radarEngine.loadCatalog();
    await refreshAlerts();
    status.setMessage('Workspace ready. Select a radar site to add live radar.');
}

initialize().catch((error) => {
    console.error('[workspace] startup failed', error);
    byId('workspace-message').textContent = `Workspace startup failed: ${error.message}`;
});
