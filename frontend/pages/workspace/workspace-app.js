import * as api from '../../core/api.js';
import { createMapCore } from '../../core/map-core.js';
import { renderProductNav } from '../../core/nav.js';
import { createScrubber } from '../../core/scrubber.js';
import { createSidebarTabs } from '../../core/sidebar-tabs.js';
import { createStatusReporter } from '../../core/status.js';
import { ALERT_CATEGORIES, ALERT_COLORS, ALERT_DEFAULT_COLOR, ALERT_TEXT_COLORS, LSR_CATEGORIES, SEVERE_EVENTS } from '../alerts/alerts-config.js?v=20260719a';
import { createAlertDetail } from '../alerts/alerts-detail.js?v=20260719b';
import { classifyLsrEvent, createAlertsEngine } from '../alerts/alerts-engine.js?v=20260719g';
import { createRadarEngine } from '../radar/radar-engine.js?v=20260719a';
import { createWorkspaceTools } from './workspace-tools.js?v=20260719b';

const byId = (id) => document.getElementById(id);
const AUTO_UPDATE_MS = 60_000;
const NEW_ALERT_NOTICE_MS = 15_000;
const NEW_ALERT_EVENTS = new Set([
    'Tornado Warning', 'Tornado Watch',
    'Severe Thunderstorm Warning', 'Severe Thunderstorm Watch',
    'Flash Flood Warning', 'Flash Flood Watch',
]);

const WORKSPACE_REGION_BOUNDS = Object.freeze({
    CONUS: [[24.0, -125.0], [50.0, -66.5]],
    AK: [[50.8, -179.5], [71.8, -129.6]],
    HI: [[18.5, -161.0], [22.5, -154.5]],
    PR: [[17.7, -67.5], [18.7, -65.1]],
});

const LSR_FILTER_CATEGORIES = Object.freeze({
    all: Object.keys(LSR_CATEGORIES),
    tornado: ['tornado'], hail: ['hail'], wind: ['wind'], flood: ['flood'], rain: ['rain'],
    other: ['winter', 'fire', 'heat', 'other'],
});

function createStackLegend(root, label, defaultOpen = false) {
    let isOpen = defaultOpen;
    return Object.freeze({
        clear() { root.replaceChildren(); root.hidden = true; },
        setHtml(html) {
            if (!html) { this.clear(); return; }
            const details = document.createElement('details');
            details.className = 'workspace-legend-panel';
            details.open = isOpen;
            details.innerHTML = `<summary>${label}</summary><div class="workspace-legend-content">${html}</div>`;
            details.addEventListener('toggle', () => { isOpen = details.open; });
            root.replaceChildren(details);
            root.hidden = false;
        },
    });
}

function activePillValue(rootId, dataKey, fallback) {
    return byId(rootId).querySelector('.is-active')?.dataset[dataKey] || fallback;
}

function selectPill(event, dataAttribute) {
    const button = event.target.closest(`button[${dataAttribute}]`);
    if (!button) return false;
    button.parentElement.querySelectorAll('button').forEach((item) => item.classList.toggle('is-active', item === button));
    return true;
}

function toggleWarningPill(event) {
    const button = event.target.closest('button[data-warning]');
    if (!button) return false;
    const active = !button.classList.contains('is-active');
    const buttons = [...button.parentElement.querySelectorAll('button[data-warning]')];
    if (button.dataset.warning === 'all' && active) {
        buttons.forEach((item) => {
            const selected = item === button;
            item.classList.toggle('is-active', selected);
            item.setAttribute('aria-pressed', String(selected));
        });
    } else {
        button.classList.toggle('is-active', active);
        button.setAttribute('aria-pressed', String(active));
        if (active) {
            const allButton = buttons.find((item) => item.dataset.warning === 'all');
            allButton?.classList.remove('is-active');
            allButton?.setAttribute('aria-pressed', 'false');
        }
    }
    return true;
}

function radarSelection() {
    return {
        site: String(byId('workspace-radar-site').value || '').toUpperCase(),
        product: String(byId('workspace-radar-product').value || 'L2_REF').toUpperCase(),
        elevation: '0.5',
        hours: 1,
    };
}

function alertIssuedMs(feature) {
    const props = feature?.properties || {};
    const value = Date.parse(props.sent || props.effective || props.onset || '');
    return Number.isFinite(value) ? value : 0;
}

function radarFrameLabel(frame) {
    const date = new Date(frame?.timestamp || '');
    if (!Number.isFinite(date.getTime())) return String(frame?.frame_key || '—');
    return date.toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
}

async function initialize() {
    renderProductNav(byId('product-nav'), 'Home');
    createSidebarTabs(byId('workspace-sidebar-tabs'), { defaultTab: 'layers' });
    document.querySelectorAll('.workspace-group-summary .workspace-layer-toggle').forEach((toggle) => {
        toggle.addEventListener('click', (event) => event.stopPropagation());
    });
    const regionSelect = byId('workspace-region');
    regionSelect.value = 'CONUS';

    let resetWorkspaceState = () => {};
    const mapCore = createMapCore(byId('workspace-map'), {
        region: 'CONUS',
        basemap: 'Dark (No Labels)',
        onResetView: () => resetWorkspaceState(),
    });
    const fitWorkspaceRegion = (region, fitOptions = {}) => {
        const code = WORKSPACE_REGION_BOUNDS[region] ? region : 'CONUS';
        mapCore.map.fitBounds(WORKSPACE_REGION_BOUNDS[code], { animate: fitOptions.animate === true, padding: [20, 20] });
    };
    fitWorkspaceRegion('CONUS');
    const status = createStatusReporter({
        globalTimestamp: byId('global-timestamp'), message: byId('workspace-message'),
        updated: byId('workspace-updated'), age: byId('workspace-age'),
        provider: byId('workspace-provider'), source: byId('workspace-source'),
    });
    const alertsLegend = createStackLegend(byId('workspace-alerts-legend'), 'Active Alerts', true);
    const lsrLegend = createStackLegend(byId('workspace-lsr-legend'), 'Storm Reports');
    const radarLegend = createStackLegend(byId('workspace-radar-legend'), 'Radar');
    const stormTrackLegend = createStackLegend(byId('workspace-storm-track-legend'), 'Storm Tracks');
    const detail = createAlertDetail(byId('workspace-detail'), {
        lsrColor(feature) {
            const category = classifyLsrEvent(feature?.properties?.event);
            return (LSR_CATEGORIES[category] || LSR_CATEGORIES.other)[1];
        },
    });
    mapCore.leaflet.DomEvent.disableClickPropagation(byId('workspace-detail'));
    mapCore.leaflet.DomEvent.disableScrollPropagation(byId('workspace-detail'));
    const tools = createWorkspaceTools({
        map: mapCore.map, leaflet: mapCore.leaflet, apiUrl: api.apiUrl,
        setStatus: (message) => status.setMessage(message),
    });
    mapCore.leaflet.DomEvent.disableClickPropagation(byId('workspace-notifications'));
    const newAlertSound = new Audio('/sounds/weather_alert.mp3');
    newAlertSound.preload = 'auto';
    newAlertSound.load();
    let lastAlertSoundAt = 0;
    let alertSoundUnlocked = false;
    function unlockAlertSound() {
        if (alertSoundUnlocked) return;
        newAlertSound.muted = true;
        void newAlertSound.play().then(() => {
            newAlertSound.pause();
            newAlertSound.currentTime = 0;
            newAlertSound.muted = false;
            alertSoundUnlocked = true;
        }).catch(() => { newAlertSound.muted = false; });
    }
    window.addEventListener('pointerdown', unlockAlertSound, { once: true, capture: true });
    window.addEventListener('keydown', unlockAlertSound, { once: true, capture: true });

    const alertSelection = () => {
        const selected = [...byId('workspace-warning-filters').querySelectorAll('.is-active')]
            .map((button) => button.dataset.warning);
        const allActive = selected.includes('all');
        const warningTypes = selected.filter((value) => value !== 'all');
        return allActive
            ? { categories: Object.keys(ALERT_CATEGORIES), warningTypes: Object.keys(SEVERE_EVENTS) }
            : { categories: warningTypes.length ? ['Severe Weather Warnings'] : [], warningTypes };
    };
    const selectedLsrCategories = () => LSR_FILTER_CATEGORIES[activePillValue('workspace-lsr-filters', 'lsr', 'all')] || LSR_FILTER_CATEGORIES.all;
    const selectedLsrHours = () => Number(activePillValue('workspace-lsr-hours', 'hours', '1'));
    let currentWarnings = [];
    let warningRailFilter = 'all';
    let currentLsrReports = [];
    let lsrRailFilter = 'all';

    function hideProjectedArrival() {
        const group = byId('workspace-projected-arrival-group');
        tools.setSelectedAlert(null);
        tools.clear();
        group.hidden = true;
        group.open = false;
        byId('workspace-projected-arrival-alert').textContent = '';
    }

    function selectAlert(feature, options = { maxZoom: 9 }) {
        tools.setSelectedAlert(feature);
        const group = byId('workspace-projected-arrival-group');
        group.hidden = false;
        group.open = true;
        const props = feature?.properties || {};
        byId('workspace-projected-arrival-alert').textContent = [props.event, props.areaDesc].filter(Boolean).join(' — ');
        alertsEngine.zoomTo(feature, options);
        detail.open(feature);
        status.setMessage(`${feature?.properties?.event || 'Alert'} selected for the Projected Arrival Tool.`);
    }

    function showNewAlert(feature) {
        const props = feature?.properties || {};
        if (!NEW_ALERT_EVENTS.has(props.event)) return;
        const root = byId('workspace-notifications');
        const notice = document.createElement('div');
        notice.className = 'alerts-notification';
        notice.tabIndex = 0;
        notice.setAttribute('role', 'button');
        notice.style.setProperty('--alert-color', ALERT_COLORS[props.event] || ALERT_DEFAULT_COLOR);
        notice.style.setProperty('--alert-text-color', ALERT_TEXT_COLORS[props.event] || ALERT_COLORS[props.event] || ALERT_DEFAULT_COLOR);
        const title = document.createElement('strong');
        title.textContent = `NEW ${props.event || 'WEATHER ALERT'}`;
        const area = document.createElement('span');
        area.textContent = props.areaDesc || 'Area unavailable';
        const close = document.createElement('button');
        close.type = 'button';
        close.className = 'alerts-notification-close';
        close.setAttribute('aria-label', 'Dismiss new alert');
        close.textContent = '×';
        close.addEventListener('click', (event) => { event.stopPropagation(); notice.remove(); });
        const openNotice = () => { selectAlert(feature, { maxZoom: 9 }); notice.remove(); };
        notice.addEventListener('click', openNotice);
        notice.addEventListener('keydown', (event) => {
            if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); openNotice(); }
        });
        notice.append(title, area, close);
        root.prepend(notice);
        while (root.children.length > 3) root.lastElementChild.remove();
        const now = Date.now();
        if (now - lastAlertSoundAt > 1_000) {
            lastAlertSoundAt = now;
            newAlertSound.currentTime = 0;
            void newAlertSound.play().catch(() => {});
        }
        setTimeout(() => notice.remove(), NEW_ALERT_NOTICE_MS);
    }

    function renderWarnings(features = currentWarnings) {
        currentWarnings = [...features];
        const counts = { all: currentWarnings.length, tor: 0, svr: 0, ffw: 0, smw: 0 };
        currentWarnings.forEach((feature) => {
            const key = Object.entries(SEVERE_EVENTS).find(([, event]) => event === feature?.properties?.event)?.[0];
            if (key) counts[key] += 1;
        });
        Object.entries(counts).forEach(([key, value]) => {
            const count = byId('workspace-rail-warning-filters').querySelector(`[data-count="${key}"]`);
            if (count) count.textContent = String(value);
        });
        byId('workspace-warning-count').textContent = String(currentWarnings.length);
        const visible = currentWarnings.filter((feature) => warningRailFilter === 'all' || feature?.properties?.event === SEVERE_EVENTS[warningRailFilter]);
        byId('workspace-warning-list').replaceChildren(...visible
            .sort((a, b) => alertIssuedMs(b) - alertIssuedMs(a))
            .map((feature) => {
                const props = feature?.properties || {};
                const button = document.createElement('button');
                button.type = 'button';
                button.className = 'alerts-warning-card';
                button.dataset.issued = props.sent || props.effective || props.onset || '';
                button.style.setProperty('--alert-color', ALERT_COLORS[props.event] || ALERT_DEFAULT_COLOR);
                button.style.setProperty('--alert-text-color', ALERT_TEXT_COLORS[props.event] || ALERT_COLORS[props.event] || ALERT_DEFAULT_COLOR);
                const expires = Date.parse(props.expires || '');
                const minutes = Number.isFinite(expires) ? Math.max(0, Math.round((expires - Date.now()) / 60_000)) : null;
                const eventName = document.createElement('strong');
                eventName.textContent = props.event || 'Weather Alert';
                const area = document.createElement('span');
                area.className = 'alerts-warning-area';
                area.textContent = props.areaDesc || 'Area unavailable';
                const meta = document.createElement('span');
                meta.className = 'alerts-warning-meta';
                meta.textContent = minutes == null ? 'Expiration unavailable' : `Expires in ${minutes} min`;
                button.append(eventName, area, meta);
                button.addEventListener('click', () => selectAlert(feature, { maxZoom: 9 }));
                return button;
            }));
        byId('workspace-warning-empty').hidden = visible.length > 0;
    }

    function lsrFilterGroup(feature) {
        const category = classifyLsrEvent(feature?.properties?.event);
        return ['tornado', 'hail', 'wind'].includes(category) ? category : 'other';
    }

    function renderLsrReports(features = currentLsrReports) {
        currentLsrReports = [...features];
        const counts = { all: currentLsrReports.length, tornado: 0, hail: 0, wind: 0, other: 0 };
        currentLsrReports.forEach((feature) => { counts[lsrFilterGroup(feature)] += 1; });
        Object.entries(counts).forEach(([key, value]) => {
            const count = byId('workspace-rail-lsr-filters').querySelector(`[data-count="${key}"]`);
            if (count) count.textContent = String(value);
        });
        byId('workspace-lsr-rail-count').textContent = String(currentLsrReports.length);
        const visible = currentLsrReports
            .filter((feature) => lsrRailFilter === 'all' || lsrFilterGroup(feature) === lsrRailFilter)
            .sort((a, b) => Date.parse(b?.properties?.time || '') - Date.parse(a?.properties?.time || ''));
        byId('workspace-lsr-rail-list').replaceChildren(...visible.map((feature) => {
            const props = feature?.properties || {};
            const category = classifyLsrEvent(props.event);
            const [, color] = LSR_CATEGORIES[category] || LSR_CATEGORIES.other;
            const card = document.createElement('button');
            card.type = 'button';
            card.className = 'alerts-warning-card alerts-lsr-card';
            card.style.setProperty('--alert-color', color);
            const title = document.createElement('strong');
            title.textContent = `${props.event || 'Local Storm Report'}${props.magnitude_label ? ` (${props.magnitude_label})` : ''}`;
            const area = document.createElement('span');
            area.className = 'alerts-warning-area';
            area.textContent = [props.location, props.state].filter(Boolean).join(', ') || 'Location unavailable';
            const meta = document.createElement('span');
            meta.className = 'alerts-warning-meta';
            const time = Date.parse(props.time || '');
            meta.textContent = Number.isFinite(time) ? new Date(time).toLocaleString() : 'Time unavailable';
            card.append(title, area, meta);
            card.addEventListener('click', () => alertsEngine.showLsr(feature));
            return card;
        }));
        byId('workspace-lsr-rail-empty').hidden = visible.length > 0;
    }

    function syncRightRailVisibility() {
        const alertsEnabled = byId('workspace-alerts-enabled').checked;
        const lsrEnabled = byId('workspace-lsr-enabled').checked;
        byId('workspace-warning-section').hidden = !alertsEnabled;
        byId('workspace-lsr-section').hidden = !lsrEnabled;
        byId('workspace-right-rail').hidden = !alertsEnabled && !lsrEnabled;
        document.querySelector('.workspace-shell').classList.toggle('is-rail-hidden', !alertsEnabled && !lsrEnabled);
        requestAnimationFrame(() => mapCore.map.invalidateSize({ pan: false }));
    }

    const alertsEngine = createAlertsEngine({
        api, mapCore, legend: alertsLegend, lsrLegend, status,
        onAlertCount(count) { byId('workspace-alert-count').textContent = String(count); },
        onLsrCount(count) { byId('workspace-lsr-count').textContent = String(count); },
        onWarnings(features) { tools.setAlerts(features); renderWarnings(features); },
        onLsrReports: renderLsrReports,
        onDetail: selectAlert,
        onLsrDetail: (feature) => detail.openLsr(feature),
        onLsrDetailClose: detail.closeLsr,
        onNewAlert: showNewAlert,
        shouldHandleAlertClick: () => !tools.isDrawing(),
    });

    let radarCatalog = { sites: [], products: {} };
    const activeRadarLevel = () => byId('workspace-radar-levels').querySelector('.is-active')?.dataset.radarLevel || 'Level 2';
    const setActiveRadarLevel = (level) => {
        byId('workspace-radar-levels').querySelectorAll('[data-radar-level]').forEach((button) => {
            const active = button.dataset.radarLevel === level;
            button.classList.toggle('is-active', active);
            button.setAttribute('aria-pressed', String(active));
        });
    };
    const populateRadarProducts = () => {
        const current = byId('workspace-radar-product').value;
        const level = activeRadarLevel();
        const options = Object.entries(radarCatalog.products || {})
            .filter(([, product]) => String(product?.level || '') === level)
            .map(([id, product]) => new Option(product.label || id, id));
        byId('workspace-radar-product').replaceChildren(...options);
        const fallback = level === 'Level 2' && options.some((option) => option.value === 'L2_REF') ? 'L2_REF' : options[0]?.value || '';
        byId('workspace-radar-product').value = options.some((option) => option.value === current) ? current : fallback;
    };
    const radarScrubberBar = byId('workspace-radar-scrubber-bar');
    const radarScrubber = createScrubber(byId('workspace-radar-bottom-scrubber'), {
        onFrame(_frame, index) { void radarEngine.renderFrameAt(index); },
    });
    function showRadarScrubber(visible) {
        radarScrubberBar.hidden = !visible;
        radarScrubberBar.closest('.weather-map-wrap')?.classList.toggle('has-radar-scrubber', visible);
    }

    const radarEngine = createRadarEngine({
        api, mapCore, legend: radarLegend, status, getSelection: radarSelection,
        onCatalog(data) {
            radarCatalog = data;
            const sites = (data.sites || []).map((site) => new Option(site.site, site.site));
            byId('workspace-radar-site').replaceChildren(new Option('Select site', ''), ...sites);
            syncRadarControls();
            radarEngine.showSiteLegend();
        },
        onFrames(frames, options = {}) {
            const labeled = frames.map((frame) => ({ ...frame, label: radarFrameLabel(frame) }));
            radarScrubber.setFrames(labeled, { index: options.index ?? 0, silent: true, keepPlaying: true });
            showRadarScrubber(labeled.length > 0);
        },
        onStormTrackLegend(html) { if (html) stormTrackLegend.setHtml(html); else stormTrackLegend.clear(); },
        onSitePicked(site, coords) {
            alertsEngine.clearLsrSelection();
            byId('workspace-radar-site').value = site;
            syncRadarControls();
            mapCore.map.flyTo(coords, Math.max(mapCore.map.getZoom(), 8), { duration: 0.5 });
            void radarEngine.refreshAll();
        },
        onMessage(message, tone) { status.setMessage(message, tone); },
    });

    function syncRadarControls() {
        const enabled = byId('workspace-radar-enabled').checked;
        const site = radarSelection().site;
        const hasSite = enabled && Boolean(site);
        const isConus = !site || radarEngine.isConusSite(site);
        if (!isConus && activeRadarLevel() === 'Level 3') setActiveRadarLevel('Level 2');
        byId('workspace-radar-controls').classList.toggle('is-disabled', !enabled);
        byId('workspace-radar-site').disabled = !enabled;
        byId('workspace-radar-sites').disabled = !enabled;
        byId('workspace-radar-product-options').hidden = !hasSite;
        byId('workspace-radar-levels').querySelectorAll('[data-radar-level]').forEach((button) => {
            button.disabled = !hasSite || (button.dataset.radarLevel === 'Level 3' && !isConus);
        });
        populateRadarProducts();
        byId('workspace-radar-product').disabled = !hasSite || !byId('workspace-radar-product').options.length;
        document.querySelectorAll('.workspace-radar-site-option').forEach((row) => { row.hidden = !hasSite; });
        if (!hasSite) {
            byId('workspace-radar-tracks').checked = false;
            byId('workspace-radar-inspector').checked = false;
            radarEngine.setStormTracksVisible(false);
            radarEngine.setInspectorVisible(false);
        }
    }

    resetWorkspaceState = () => {
        regionSelect.value = 'CONUS';
        alertsEngine.clearLsrSelection();
        detail.close();
        hideProjectedArrival();
        byId('workspace-radar-site').value = '';
        setActiveRadarLevel('Level 2');
        radarEngine.syncHighlights('');
        radarEngine.clear();
        syncRadarControls();
        if (byId('workspace-radar-enabled').checked && byId('workspace-radar-sites').checked) {
            radarEngine.showSiteLegend();
        }
        status.setMessage('Workspace reset to the default CONUS view.');
    };

    async function refreshAlerts(options = {}) {
        await Promise.all([
            byId('workspace-alerts-enabled').checked
                ? alertsEngine.loadLive(alertSelection(), regionSelect.value, options)
                : Promise.resolve(alertsEngine.setSelection({ categories: [], warningTypes: [] })),
            alertsEngine.loadLsr(
                byId('workspace-lsr-enabled').checked ? selectedLsrCategories() : [],
                selectedLsrHours(), options,
            ),
        ]);
        if (!byId('workspace-alerts-enabled').checked) tools.setAlerts([]);
    }
    async function refreshRadar() {
        if (!byId('workspace-radar-enabled').checked) {
            radarEngine.setSitesVisible(false);
            radarEngine.clear();
        } else {
            radarEngine.setSitesVisible(byId('workspace-radar-sites').checked);
            if (radarSelection().site) {
                await radarEngine.refreshAll();
                return;
            }
            radarEngine.clear();
            if (byId('workspace-radar-sites').checked) radarEngine.showSiteLegend();
        }
    }
    async function refreshAll(options = {}) { await Promise.all([refreshAlerts(options), refreshRadar()]); }
    async function autoRefreshLiveLayers() {
        const tasks = [refreshAlerts({ silent: true, refresh: true })];
        if (byId('workspace-radar-enabled').checked && radarSelection().site) tasks.push(radarEngine.loadFrames({ refresh: true }));
        await Promise.allSettled(tasks);
    }

    let autoUpdateTimer = null;
    function syncAutoUpdate() {
        clearInterval(autoUpdateTimer);
        autoUpdateTimer = byId('workspace-auto-update').checked
            ? setInterval(() => void autoRefreshLiveLayers(), AUTO_UPDATE_MS)
            : null;
    }

    byId('workspace-refresh').addEventListener('click', () => void refreshAll({ refresh: true }));
    byId('workspace-auto-update').addEventListener('change', syncAutoUpdate);
    const syncLayerToggle = (checkboxId, controlsId) => {
        const enabled = byId(checkboxId).checked;
        byId(controlsId).classList.toggle('is-disabled', !enabled);
        byId(controlsId).querySelectorAll('button').forEach((button) => { button.disabled = !enabled; });
    };
    byId('workspace-alerts-enabled').addEventListener('change', () => {
        syncLayerToggle('workspace-alerts-enabled', 'workspace-warning-filters');
        syncRightRailVisibility();
        if (!byId('workspace-alerts-enabled').checked) {
            detail.closeAlert();
            hideProjectedArrival();
        }
        void refreshAlerts({ notifyNewAlerts: false });
    });
    byId('workspace-lsr-enabled').addEventListener('change', () => {
        syncLayerToggle('workspace-lsr-enabled', 'workspace-lsr-filters');
        byId('workspace-lsr-hours').classList.toggle('is-disabled', !byId('workspace-lsr-enabled').checked);
        byId('workspace-lsr-hours').querySelectorAll('button').forEach((button) => { button.disabled = !byId('workspace-lsr-enabled').checked; });
        syncRightRailVisibility();
        void refreshAlerts({ notifyNewAlerts: false });
    });
    byId('workspace-warning-filters').addEventListener('click', (event) => {
        if (!toggleWarningPill(event)) return;
        const nextSelection = alertSelection();
        if (!alertsEngine.setSelection(nextSelection)) void alertsEngine.loadLive(nextSelection, regionSelect.value);
    });
    byId('workspace-lsr-filters').addEventListener('click', (event) => {
        if (selectPill(event, 'data-lsr')) {
            alertsEngine.clearLsrSelection();
            void alertsEngine.loadLsr(selectedLsrCategories(), selectedLsrHours());
        }
    });
    byId('workspace-lsr-hours').addEventListener('click', (event) => {
        if (selectPill(event, 'data-hours')) {
            alertsEngine.clearLsrSelection();
            void alertsEngine.loadLsr(selectedLsrCategories(), selectedLsrHours());
        }
    });
    byId('workspace-rail-warning-filters').addEventListener('click', (event) => {
        const button = event.target.closest('[data-filter]');
        if (!button) return;
        warningRailFilter = button.dataset.filter;
        byId('workspace-rail-warning-filters').querySelectorAll('button').forEach((item) => item.classList.toggle('is-active', item === button));
        renderWarnings();
    });
    byId('workspace-rail-lsr-filters').addEventListener('click', (event) => {
        const button = event.target.closest('[data-filter]');
        if (!button) return;
        lsrRailFilter = button.dataset.filter;
        byId('workspace-rail-lsr-filters').querySelectorAll('button').forEach((item) => item.classList.toggle('is-active', item === button));
        renderLsrReports();
    });
    byId('workspace-radar-enabled').addEventListener('change', () => {
        syncRadarControls();
        void refreshRadar();
    });
    byId('workspace-radar-site').addEventListener('change', () => { alertsEngine.clearLsrSelection(); radarEngine.syncHighlights(); syncRadarControls(); void refreshRadar(); });
    byId('workspace-radar-levels').addEventListener('click', (event) => {
        const button = event.target.closest('[data-radar-level]');
        if (!button || button.disabled || button.classList.contains('is-active')) return;
        alertsEngine.clearLsrSelection();
        setActiveRadarLevel(button.dataset.radarLevel);
        populateRadarProducts();
        if (byId('workspace-radar-enabled').checked && radarSelection().site) void radarEngine.refreshAll();
    });
    byId('workspace-radar-product').addEventListener('change', () => { alertsEngine.clearLsrSelection(); if (byId('workspace-radar-enabled').checked && radarSelection().site) void radarEngine.refreshAll(); });
    byId('workspace-radar-sites').addEventListener('change', (event) => { if (byId('workspace-radar-enabled').checked) { radarEngine.setSitesVisible(event.target.checked); if (event.target.checked) radarEngine.showSiteLegend(); } });
    byId('workspace-radar-tracks').addEventListener('change', (event) => radarEngine.setStormTracksVisible(event.target.checked));
    byId('workspace-radar-inspector').addEventListener('change', (event) => radarEngine.setInspectorVisible(event.target.checked));
    regionSelect.addEventListener('change', () => {
        alertsEngine.clearLsrSelection();
        hideProjectedArrival();
        byId('workspace-radar-site').value = '';
        radarEngine.syncHighlights();
        radarEngine.clear();
        syncRadarControls();
        fitWorkspaceRegion(regionSelect.value);
        void refreshAlerts({ refresh: true, notifyNewAlerts: false });
    });
    byId('workspace-basemap').addEventListener('change', (event) => mapCore.setBasemap(event.target.value));
    document.querySelectorAll('[data-map-overlay]').forEach((input) => {
        input.addEventListener('change', () => void mapCore.setOverlayVisible(input.dataset.mapOverlay, input.checked));
        if (input.checked) void mapCore.setOverlayVisible(input.dataset.mapOverlay, true);
    });
    mapCore.map.on('movestart zoomstart', detail.close);
    mapCore.map.on('moveend', () => void refreshAlerts({ silent: true, notifyNewAlerts: false }));

    syncLayerToggle('workspace-alerts-enabled', 'workspace-warning-filters');
    syncLayerToggle('workspace-lsr-enabled', 'workspace-lsr-filters');
    byId('workspace-lsr-hours').classList.add('is-disabled');
    byId('workspace-lsr-hours').querySelectorAll('button').forEach((button) => { button.disabled = true; });
    syncRadarControls();
    syncRightRailVisibility();
    syncAutoUpdate();

    await radarEngine.loadCatalog();
    await refreshAlerts();
    status.setMessage('Workspace ready. Select a radar site to add live radar.');
    window.addEventListener('beforeunload', () => { clearInterval(autoUpdateTimer); radarScrubber.destroy(); }, { once: true });
}

initialize().catch((error) => {
    console.error('[workspace] startup failed', error);
    byId('workspace-message').textContent = `Workspace startup failed: ${error.message}`;
});
