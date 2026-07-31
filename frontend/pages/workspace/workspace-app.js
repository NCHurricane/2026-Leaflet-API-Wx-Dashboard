import * as api from '../../core/api.js';
import { createMapCore } from '../../core/map-core.js';
import { renderProductNav } from '../../core/nav.js';
import { createScrubber } from '../../core/scrubber.js';
import { loadDefaultSettings } from '../../core/settings.js';
import { createSidebarTabs } from '../../core/sidebar-tabs.js';
import { createStatusReporter } from '../../core/status.js?v=20260725e';
import { ALERT_CATEGORIES, ALERT_COLORS, ALERT_DEFAULT_COLOR, ALERT_TEXT_COLORS, LSR_CATEGORIES, SEVERE_EVENTS } from '../alerts/alerts-config.js?v=20260719a';
import { createAlertDetail } from '../alerts/alerts-detail.js?v=20260726a';
import { classifyLsrEvent, createAlertsEngine } from '../alerts/alerts-engine.js?v=20260731a';
import { createRadarEngine } from '../radar/radar-engine.js?v=20260729b';
import { createWorkspaceTools } from './workspace-tools.js?v=20260719c';

const byId = (id) => document.getElementById(id);
const AUTO_UPDATE_MS = 30_000;
const NEW_ALERT_NOTICE_MS = 15_000;
const NEW_ALERT_EVENTS = new Set([
    'Tornado Warning', 'Tornado Watch',
    'Severe Thunderstorm Warning', 'Severe Thunderstorm Watch',
    'Flash Flood Warning', 'Flash Flood Watch',
]);
const WORKSPACE_WARNING_EVENTS = Object.freeze({
    tor: [SEVERE_EVENTS.tor],
    svr: [SEVERE_EVENTS.svr],
    ffw: [SEVERE_EVENTS.ffw],
    smw: [SEVERE_EVENTS.smw],
    sps: ['Special Weather Statement'],
});
const WORKSPACE_WATCH_EVENTS = Object.freeze({
    tor: ['Tornado Watch'],
    svr: ['Severe Thunderstorm Watch'],
    fld: ['Flash Flood Watch', 'Flood Watch'],
});
const PROJECTED_ARRIVAL_EVENTS = new Set([
    'Tornado Warning',
    'Severe Thunderstorm Warning',
    'Special Marine Warning',
    'Special Weather Statement',
]);

const LSR_FILTER_CATEGORIES = Object.freeze({
    all: Object.keys(LSR_CATEGORIES),
    tornado: ['tornado'], hail: ['hail'], wind: ['wind'], flood: ['flood'], rain: ['rain'],
    other: ['winter', 'fire', 'heat', 'other'],
});

function createTabbedLegendTray(root, sourceIds, preferredId = sourceIds[0]) {
    const panel = root.querySelector('.workspace-legend-panel');
    const collapse = root.querySelector('.core-legend-collapse');
    const tablist = root.querySelector('[role="tablist"]');
    const sources = new Map(sourceIds.map((id) => [id, {
        tab: root.querySelector(`[data-legend-tab="${id}"]`),
        view: root.querySelector(`[data-legend-view="${id}"]`),
        available: false,
    }]));
    let activeId = preferredId;
    let isOpen = true;
    let ready = false;

    function availableIds() {
        return sourceIds.filter((id) => sources.get(id).available);
    }

    function sync() {
        const available = availableIds();
        if (!available.includes(activeId)) activeId = available.includes(preferredId) ? preferredId : available[0];
        root.hidden = available.length === 0;
        panel.classList.toggle('is-collapsed', !isOpen);
        collapse.setAttribute('aria-expanded', String(isOpen));
        collapse.setAttribute('aria-label', isOpen ? 'Collapse legends' : 'Expand legends');
        collapse.title = isOpen ? 'Collapse legends' : 'Expand legends';
        sources.forEach((source, id) => {
            const selected = id === activeId;
            source.tab.hidden = !source.available;
            source.tab.setAttribute('aria-selected', String(selected));
            source.tab.tabIndex = selected ? 0 : -1;
            source.view.hidden = !source.available || !selected;
        });
    }

    sources.forEach((source, id) => {
        source.tab.addEventListener('click', () => { activeId = id; sync(); });
    });
    tablist.addEventListener('keydown', (event) => {
        if (!event.target.matches('[data-legend-tab]')) return;
        const available = availableIds();
        const current = available.indexOf(activeId);
        let next = null;
        if (event.key === 'ArrowRight') next = available[(current + 1) % available.length];
        if (event.key === 'ArrowLeft') next = available[(current - 1 + available.length) % available.length];
        if (event.key === 'Home') next = available[0];
        if (event.key === 'End') next = available[available.length - 1];
        if (!next) return;
        event.preventDefault();
        activeId = next;
        sync();
        sources.get(next).tab.focus();
    });
    collapse.addEventListener('click', () => { isOpen = !isOpen; sync(); });
    sync();

    return Object.freeze({
        legend(id) {
            const source = sources.get(id);
            return Object.freeze({
                clear() {
                    source.view.replaceChildren();
                    source.available = false;
                    sync();
                },
                setHtml(html) {
                    if (!html) { this.clear(); return; }
                    const wasAvailable = source.available;
                    source.view.innerHTML = html;
                    source.view.querySelector(':scope > .core-legend-header')?.remove();
                    source.available = true;
                    if (!availableIds().includes(activeId)
                        || (!ready && id === preferredId)
                        || (ready && !wasAvailable)) activeId = id;
                    sync();
                },
            });
        },
        markReady() { ready = true; },
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

function toggleAlertPill(event, dataKey) {
    const button = event.target.closest(`button[data-${dataKey}]`);
    if (!button) return false;
    const active = !button.classList.contains('is-active');
    const buttons = [...button.parentElement.querySelectorAll(`button[data-${dataKey}]`)];
    if (button.dataset[dataKey] === 'all' && active) {
        buttons.forEach((item) => {
            const selected = item === button;
            item.classList.toggle('is-active', selected);
            item.setAttribute('aria-pressed', String(selected));
        });
    } else {
        button.classList.toggle('is-active', active);
        button.setAttribute('aria-pressed', String(active));
        if (active) {
            const allButton = buttons.find((item) => item.dataset[dataKey] === 'all');
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

function alertFeatureId(feature) {
    const props = feature?.properties || {};
    return String(feature?.id || `${props.event || ''}|${props.sent || ''}|${props.areaDesc || ''}`);
}

function radarFrameLabel(frame) {
    const date = new Date(frame?.timestamp || '');
    if (!Number.isFinite(date.getTime())) return String(frame?.frame_key || '—');
    return date.toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
}

async function initialize() {
    renderProductNav(byId('product-nav'), 'Home');
    createSidebarTabs(byId('workspace-sidebar-tabs'), { defaultTab: 'layers' });
    const defaults = await loadDefaultSettings().catch(() => ({}));
    const cityDefaults = defaults?.global?.cityLabels || {};
    document.querySelectorAll('.workspace-group-summary .workspace-layer-toggle').forEach((toggle) => {
        toggle.addEventListener('click', (event) => event.stopPropagation());
    });
    const regionSelect = byId('workspace-region');
    regionSelect.value = 'CONUS';

    let resetWorkspaceState = () => {};
    const mapCore = createMapCore(byId('workspace-map'), {
        region: 'CONUS',
        basemap: 'Dark',
        onResetView: () => resetWorkspaceState(),
    });
    // Delegate to the core region table so CONUS/AK/HI/PR share one source of truth.
    const fitWorkspaceRegion = (region, fitOptions = {}) => mapCore.fitRegion(region, fitOptions);
    fitWorkspaceRegion('CONUS');
    const status = createStatusReporter({
        globalTimestamp: byId('global-timestamp'), message: byId('workspace-message'),
        updated: byId('workspace-updated'), age: byId('workspace-age'),
        provider: byId('workspace-provider'), source: byId('workspace-source'),
    });
    const legendTray = createTabbedLegendTray(
        byId('workspace-legends'),
        ['radar', 'storm-tracks', 'alerts', 'storm-reports'],
        'alerts',
    );
    const alertsLegend = legendTray.legend('alerts');
    const lsrLegend = legendTray.legend('storm-reports');
    const radarLegend = legendTray.legend('radar');
    const stormTrackLegend = legendTray.legend('storm-tracks');
    let alertsEngine = null;
    const detail = createAlertDetail(byId('workspace-detail'), {
        initialTop: 70,
        onClose(mode) { if (mode === 'alert') clearSelectedAlert(); },
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

    const activeAlertEvents = (rootId, dataKey, eventGroups) => {
        return [...byId(rootId).querySelectorAll('.is-active')]
            .map((button) => button.dataset[dataKey])
            .flatMap((key) => eventGroups[key] || []);
    };
    const alertSelection = () => {
        if (byId('workspace-alert-all').classList.contains('is-active')) {
            return {
                categories: Object.keys(ALERT_CATEGORIES),
                warningTypes: Object.keys(SEVERE_EVENTS),
            };
        }
        const warningEvents = activeAlertEvents('workspace-warning-filters', 'warning', WORKSPACE_WARNING_EVENTS);
        const watchEvents = activeAlertEvents('workspace-watch-filters', 'watch', WORKSPACE_WATCH_EVENTS);
        const categories = new Set();
        if (warningEvents.some((event) => event !== 'Special Weather Statement')) categories.add('Severe Weather Warnings');
        if (warningEvents.includes('Special Weather Statement')) categories.add('Informational Alerts');
        if (watchEvents.some((event) => event !== 'Flood Watch')) categories.add('Severe Weather Watches');
        if (watchEvents.includes('Flood Watch')) categories.add('Hydrology Alerts');
        return {
            categories: [...categories],
            warningTypes: Object.keys(SEVERE_EVENTS),
            eventTypes: [...new Set([...warningEvents, ...watchEvents])],
        };
    };
    const selectedLsrCategories = () => LSR_FILTER_CATEGORIES[activePillValue('workspace-lsr-filters', 'lsr', 'all')] || LSR_FILTER_CATEGORIES.all;
    const selectedLsrHours = () => Number(activePillValue('workspace-lsr-hours', 'hours', '1'));
    let currentWarnings = [];
    let warningRailFilter = 'all';
    let selectedAlertId = '';
    let projectedArrivalFeature = null;
    let currentLsrReports = [];
    let lsrRailFilter = 'all';

    function syncSelectedWarningCard() {
        byId('workspace-warning-list').querySelectorAll('.alerts-warning-card').forEach((card) => {
            const selected = Boolean(selectedAlertId) && card.dataset.alertId === selectedAlertId;
            card.classList.toggle('is-selected', selected);
            if (selected) card.setAttribute('aria-current', 'true');
            else card.removeAttribute('aria-current');
        });
    }

    function clearSelectedAlert() {
        selectedAlertId = '';
        alertsEngine?.clearSelectedAlert();
        syncSelectedWarningCard();
    }

    function hideProjectedArrival({ preserveAlert = false } = {}) {
        const group = byId('workspace-projected-arrival-group');
        if (!preserveAlert) projectedArrivalFeature = null;
        tools.setSelectedAlert(null);
        tools.clear();
        group.hidden = true;
        group.open = false;
        byId('workspace-projected-arrival-alert').textContent = '';
    }

    function supportsProjectedArrival(feature) {
        const geometryType = feature?.geometry?.type;
        return PROJECTED_ARRIVAL_EVENTS.has(feature?.properties?.event)
            && ['Polygon', 'MultiPolygon'].includes(geometryType);
    }

    function syncProjectedArrivalVisibility() {
        const hasRadarSite = byId('workspace-radar-enabled').checked
            && Boolean(radarSelection().site);
        if (!hasRadarSite || !supportsProjectedArrival(projectedArrivalFeature)) {
            hideProjectedArrival({ preserveAlert: true });
            return false;
        }
        const props = projectedArrivalFeature.properties || {};
        tools.setSelectedAlert(projectedArrivalFeature);
        const group = byId('workspace-projected-arrival-group');
        group.hidden = false;
        group.open = true;
        byId('workspace-projected-arrival-alert').textContent = [props.event, props.areaDesc].filter(Boolean).join(' — ');
        return true;
    }

    function selectAlert(feature, options = { maxZoom: 9 }) {
        const props = feature?.properties || {};
        clearSelectedAlert();
        let projectedArrivalReady = false;
        if (supportsProjectedArrival(feature)) {
            projectedArrivalFeature = feature;
            projectedArrivalReady = syncProjectedArrivalVisibility();
        } else {
            hideProjectedArrival();
        }
        alertsEngine.zoomTo(feature, options);
        const hasPolygon = alertsEngine.showSelectedAlert(feature);
        selectedAlertId = hasPolygon ? alertFeatureId(feature) : '';
        syncSelectedWarningCard();
        detail.open(feature);
        status.setMessage(!hasPolygon
            ? `${props.event || 'Alert'} selected; polygon unavailable.`
            : projectedArrivalReady
            ? `${props.event || 'Alert'} selected for the Projected Arrival Tool.`
            : supportsProjectedArrival(feature)
            ? `${props.event || 'Alert'} selected; select a radar site to use Projected Arrival.`
            : `${props.event || 'Alert'} selected.`);
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
                button.dataset.alertId = alertFeatureId(feature);
                button.dataset.issued = props.sent || props.effective || props.onset || '';
                if (button.dataset.alertId === selectedAlertId) {
                    button.classList.add('is-selected');
                    button.setAttribute('aria-current', 'true');
                }
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

    alertsEngine = createAlertsEngine({
        api, mapCore, legend: alertsLegend, lsrLegend, status,
        railScope: 'national',
        selectedAlertMissingGraceRefreshes: 1,
        subdueWatches: true,
        alertPaneZIndex: 440,
        onAlertCount(count) { byId('workspace-alert-count').textContent = String(count); },
        onLsrCount(count) { byId('workspace-lsr-count').textContent = String(count); },
        onRenderedAlerts(features) { tools.setAlerts(features); },
        onWarnings: renderWarnings,
        onLsrReports: renderLsrReports,
        onDetail: selectAlert,
        onLsrDetail(feature) { clearSelectedAlert(); detail.openLsr(feature); },
        onLsrDetailClose: detail.closeLsr,
        onNewAlert: showNewAlert,
        onSelectedAlertRemoved(feature) {
            selectedAlertId = '';
            syncSelectedWarningCard();
            detail.closeAlert();
            hideProjectedArrival();
            status.setMessage(`${feature?.properties?.event || 'Selected alert'} is no longer active.`);
        },
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
        holdAtEnd: true,
        onFrame(_frame, index) { void radarEngine.renderFrameAt(index); },
        onPlayingChange(playing) { radarEngine.setPlaybackActive(playing); },
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
            radarScrubber.setFrames(labeled, {
                index: options.index ?? 0,
                silent: true,
                keepPlaying: labeled.length > 0,
            });
            showRadarScrubber(labeled.length > 0);
        },
        onStormTrackLegend(html) { if (html) stormTrackLegend.setHtml(html); else stormTrackLegend.clear(); },
        onSitePicked(site, coords) {
            radarScrubber.pause();
            alertsEngine.clearLsrSelection();
            byId('workspace-radar-site').value = site;
            syncRadarControls();
            mapCore.map.flyTo(coords, Math.max(mapCore.map.getZoom(), 8), { duration: 0.5 });
            void radarEngine.refreshAll();
        },
        onMessage(message, tone) { status.setMessage(message, tone); },
    });

    function syncAlertTooltipSuppression() {
        const suppress = byId('workspace-radar-tracks').checked
            || byId('workspace-radar-inspector').checked;
        document.querySelector('.workspace-shell').classList.toggle('is-alert-tooltip-suppressed', suppress);
    }

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
        syncAlertTooltipSuppression();
        syncProjectedArrivalVisibility();
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
        syncLayerToggle('workspace-alerts-enabled', 'workspace-alert-all-filter');
        syncLayerToggle('workspace-alerts-enabled', 'workspace-warning-filters');
        syncLayerToggle('workspace-alerts-enabled', 'workspace-watch-filters');
        syncRightRailVisibility();
        if (!byId('workspace-alerts-enabled').checked) {
            detail.closeAlert();
            hideProjectedArrival();
        }
        void refreshAlerts({ notifyNewAlerts: false });
    });
    const setAllAlertsPill = (active) => {
        const button = byId('workspace-alert-all');
        button.classList.toggle('is-active', active);
        button.setAttribute('aria-pressed', String(active));
    };
    byId('workspace-alert-all').addEventListener('click', (event) => {
        const active = !event.currentTarget.classList.contains('is-active');
        setAllAlertsPill(active);
        if (active) {
            document.querySelectorAll('#workspace-warning-filters button, #workspace-watch-filters button').forEach((button) => {
                button.classList.remove('is-active');
                button.setAttribute('aria-pressed', 'false');
            });
        }
        const nextSelection = alertSelection();
        if (!alertsEngine.setSelection(nextSelection)) void alertsEngine.loadLive(nextSelection, regionSelect.value);
    });
    byId('workspace-lsr-enabled').addEventListener('change', () => {
        syncLayerToggle('workspace-lsr-enabled', 'workspace-lsr-filters');
        byId('workspace-lsr-hours').classList.toggle('is-disabled', !byId('workspace-lsr-enabled').checked);
        byId('workspace-lsr-hours').querySelectorAll('button').forEach((button) => { button.disabled = !byId('workspace-lsr-enabled').checked; });
        syncRightRailVisibility();
        void refreshAlerts({ notifyNewAlerts: false });
    });
    byId('workspace-warning-filters').addEventListener('click', (event) => {
        if (!toggleAlertPill(event, 'warning')) return;
        setAllAlertsPill(false);
        const nextSelection = alertSelection();
        if (!alertsEngine.setSelection(nextSelection)) void alertsEngine.loadLive(nextSelection, regionSelect.value);
    });
    byId('workspace-watch-filters').addEventListener('click', (event) => {
        if (!toggleAlertPill(event, 'watch')) return;
        setAllAlertsPill(false);
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
        if (byId('workspace-radar-enabled').checked && radarSelection().site) {
            radarEngine.clear();
            void radarEngine.refreshAll();
        }
    });
    byId('workspace-radar-product').addEventListener('change', () => {
        alertsEngine.clearLsrSelection();
        if (byId('workspace-radar-enabled').checked && radarSelection().site) {
            radarEngine.clear();
            void radarEngine.refreshAll();
        }
    });
    byId('workspace-radar-sites').addEventListener('change', (event) => { if (byId('workspace-radar-enabled').checked) { radarEngine.setSitesVisible(event.target.checked); if (event.target.checked) radarEngine.showSiteLegend(); } });
    byId('workspace-radar-tracks').addEventListener('change', (event) => {
        radarEngine.setStormTracksVisible(event.target.checked);
        syncAlertTooltipSuppression();
    });
    byId('workspace-radar-inspector').addEventListener('change', (event) => {
        radarEngine.setInspectorVisible(event.target.checked);
        syncAlertTooltipSuppression();
    });
    const opacityLabel = (prefix, value) => `${prefix} (${value.toFixed(2).replace(/\.?0+$/, '')})`;
    const radarOpacityInput = byId('workspace-radar-opacity');
    const alertsOpacityInput = byId('workspace-alerts-opacity');
    const lsrOpacityInput = byId('workspace-lsr-opacity');
    const updateRadarOpacity = () => {
        const value = radarEngine.setOpacity(radarOpacityInput.value);
        byId('workspace-radar-opacity-label').textContent = opacityLabel('Radar Opacity', value);
    };
    const updateAlertsOpacity = () => {
        const value = alertsEngine.setOpacity(alertsOpacityInput.value);
        byId('workspace-alerts-opacity-label').textContent = opacityLabel('Alerts Opacity', value);
    };
    const updateLsrOpacity = () => {
        const value = alertsEngine.setLsrOpacity(lsrOpacityInput.value);
        byId('workspace-lsr-opacity-label').textContent = opacityLabel('Storm Reports Opacity', value);
    };
    radarOpacityInput.addEventListener('input', updateRadarOpacity);
    alertsOpacityInput.addEventListener('input', updateAlertsOpacity);
    lsrOpacityInput.addEventListener('input', updateLsrOpacity);
    updateRadarOpacity();
    updateAlertsOpacity();
    updateLsrOpacity();
    regionSelect.addEventListener('change', () => {
        alertsEngine.clearLsrSelection();
        clearSelectedAlert();
        hideProjectedArrival();
        byId('workspace-radar-site').value = '';
        radarEngine.syncHighlights();
        radarEngine.clear();
        syncRadarControls();
        fitWorkspaceRegion(regionSelect.value);
        void refreshAlerts({ refresh: true, notifyNewAlerts: false });
    });
    byId('workspace-basemap').addEventListener('change', (event) => mapCore.setBasemap(event.target.value));

    const citySource = ['us', 'world'].includes(cityDefaults.source) ? cityDefaults.source : 'off';
    const cityDensity = Number(cityDefaults.density);
    const cityFontSize = Number(cityDefaults.fontSize);
    const cityDensityInput = byId('workspace-city-density');
    const cityFontSizeInput = byId('workspace-city-font-size');
    cityDensityInput.value = String(cityDensity >= 0.01 && cityDensity <= 1 ? cityDensity : 0.25);
    cityFontSizeInput.value = String(cityFontSize >= 0.4 && cityFontSize <= 1.2 ? cityFontSize : 0.6);
    const initialCitySourceInput = document.querySelector(`input[name="workspace-cities-source"][value="${citySource}"]`);
    if (initialCitySourceInput) initialCitySourceInput.checked = true;

    const selectedCitySource = () => document.querySelector('input[name="workspace-cities-source"]:checked')?.value || 'off';
    function updateCityControlLabels() {
        const source = selectedCitySource();
        const disabled = source === 'off';
        document.querySelectorAll('[data-city-adjustment]').forEach((row) => {
            row.classList.toggle('is-disabled', disabled);
            row.querySelector('input').disabled = disabled;
        });
        const distanceKm = Math.round(mapCore.getCityMinDistanceKm(source, cityDensityInput.value));
        byId('workspace-city-density-label').textContent = `City Density (${distanceKm} km)`;
        const fontSizeLabel = Number(cityFontSizeInput.value).toFixed(2).replace(/\.?0+$/, '');
        byId('workspace-city-font-size-label').textContent = `City Font Size (${fontSizeLabel})`;
    }
    document.querySelectorAll('input[name="workspace-cities-source"]').forEach((input) => {
        input.addEventListener('change', () => {
            updateCityControlLabels();
            void mapCore.setCitySource(selectedCitySource())
                .catch((error) => status.setMessage(`City overlay unavailable: ${error.message}`, 'error'));
        });
    });
    cityDensityInput.addEventListener('input', () => {
        mapCore.setCityDensity(cityDensityInput.value);
        updateCityControlLabels();
    });
    cityFontSizeInput.addEventListener('input', () => {
        mapCore.setCityFontSize(cityFontSizeInput.value);
        updateCityControlLabels();
    });
    mapCore.map.on('zoomend', updateCityControlLabels);
    mapCore.setCityDensity(cityDensityInput.value);
    mapCore.setCityFontSize(cityFontSizeInput.value);
    updateCityControlLabels();
    void mapCore.setCitySource(citySource)
        .catch((error) => status.setMessage(`City overlay unavailable: ${error.message}`, 'error'));

    document.querySelectorAll('[data-map-overlay]').forEach((input) => {
        input.addEventListener('change', () => void mapCore.setOverlayVisible(input.dataset.mapOverlay, input.checked));
        if (input.checked) void mapCore.setOverlayVisible(input.dataset.mapOverlay, true);
    });
    mapCore.map.on('movestart zoomstart', detail.closeLsr);
    mapCore.map.on('moveend', () => void refreshAlerts({ silent: true, notifyNewAlerts: false, refreshFeeds: false }));

    syncLayerToggle('workspace-alerts-enabled', 'workspace-alert-all-filter');
    syncLayerToggle('workspace-alerts-enabled', 'workspace-warning-filters');
    syncLayerToggle('workspace-alerts-enabled', 'workspace-watch-filters');
    syncLayerToggle('workspace-lsr-enabled', 'workspace-lsr-filters');
    byId('workspace-lsr-hours').classList.add('is-disabled');
    byId('workspace-lsr-hours').querySelectorAll('button').forEach((button) => { button.disabled = true; });
    syncRadarControls();
    syncRightRailVisibility();
    syncAutoUpdate();

    await Promise.all([radarEngine.loadCatalog(), refreshAlerts()]);
    legendTray.markReady();
    status.setMessage('Workspace ready. Select a radar site to add live radar.');
    window.addEventListener('beforeunload', () => {
        clearInterval(autoUpdateTimer);
        mapCore.map.off('zoomend', updateCityControlLabels);
        radarScrubber.destroy();
    }, { once: true });
}

initialize().catch((error) => {
    console.error('[workspace] startup failed', error);
    byId('workspace-message').textContent = `Workspace startup failed: ${error.message}`;
});
