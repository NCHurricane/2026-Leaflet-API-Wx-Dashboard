import * as api from '../../core/api.js';
import { createLegendHost } from '../../core/legend.js';
import { createMapCore, REGION_LABELS } from '../../core/map-core.js';
import { renderProductNav } from '../../core/nav.js';
import { createScrubber } from '../../core/scrubber.js';
import { createSidebarTabs } from '../../core/sidebar-tabs.js';
import { loadDefaultSettings, loadPageSettings } from '../../core/settings.js';
import { createStatusReporter } from '../../core/status.js';
import { ALERT_CATEGORIES, ALERT_COLORS, ALERT_DEFAULT_COLOR, ALERT_TEXT_COLORS, LSR_CATEGORIES, SEVERE_EVENTS } from './alerts-config.js?v=20260719a';
import { createAlertDetail } from './alerts-detail.js?v=20260719b';
import { classifyLsrEvent, createAlertsEngine } from './alerts-engine.js?v=20260723a';

const byId = (id) => document.getElementById(id);
const AUTO_UPDATE_MS = 60_000;

function selectedMode() {
    return document.querySelector('#alerts-sidebar-tabs .core-sidebar-tab.is-active')?.dataset.sidebarTab === 'archive'
        ? 'archive'
        : 'live';
}
function selectedCategories() { return [...document.querySelectorAll('#alerts-category-list .alerts-category-input:checked')].map((input) => input.value); }
function selectedWarningTypes() { return [...document.querySelectorAll('#alerts-warning-subtypes input:checked')].map((input) => input.value); }
function selectedLsrCategories() { return [...document.querySelectorAll('#alerts-lsr-list input:checked')].map((input) => input.value); }
function selectedLsrHours() { return Number(byId('alerts-lsr-hours').querySelector('.is-active')?.dataset.hours || 24); }
function notificationMode() { return document.querySelector('input[name="alerts-notification-mode"]:checked')?.value || 'severe'; }
function selection() { return { categories: selectedCategories(), warningTypes: selectedWarningTypes() }; }

function localDatetimeValue(date) {
    const shifted = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
    return shifted.toISOString().slice(0, 16);
}

function frameLabel(frame) {
    const date = new Date(frame?.timestamp || '');
    return Number.isFinite(date.getTime()) ? date.toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }) : '—';
}

async function initialize() {
    renderProductNav(byId('product-nav'), 'Alerts');
    createSidebarTabs(byId('alerts-sidebar-tabs'), { defaultTab: 'live' });
    const settings = await loadPageSettings('alerts', { mapView: 'CONUS' });
    const defaults = await loadDefaultSettings().catch(() => ({}));
    const cityDefaults = defaults?.global?.cityLabels || {};

    const regionSelect = byId('alerts-region');
    regionSelect.replaceChildren(...Object.entries(REGION_LABELS).map(([code, label]) => new Option(label, code)));
    regionSelect.value = REGION_LABELS[settings.mapView] ? settings.mapView : 'CONUS';
    let closeDetail = () => {};
    const mapCore = createMapCore(byId('alerts-map'), {
        region: regionSelect.value,
        basemap: 'Dark (No Labels)',
        onResetView: () => closeDetail(),
    });
    const legend = createLegendHost(byId('alerts-legend'), { align: 'left' });
    const lsrLegend = createLegendHost(byId('alerts-lsr-legend'), { align: 'right' });
    const status = createStatusReporter({
        globalTimestamp: byId('global-timestamp'), message: byId('alerts-message'),
        updated: byId('alerts-updated'), age: byId('alerts-age'),
        provider: byId('alerts-provider'), source: byId('alerts-source'),
    });
    const detail = createAlertDetail(byId('alerts-detail'), {
        initialTop: 70,
        onZoom: (feature) => engine.zoomTo(feature, { maxZoom: 9 }),
        lsrColor(feature) {
            const category = classifyLsrEvent(feature?.properties?.event);
            return (LSR_CATEGORIES[category] || LSR_CATEGORIES.other)[1];
        },
    });
    mapCore.leaflet.DomEvent.disableClickPropagation(byId('alerts-detail'));
    mapCore.leaflet.DomEvent.disableScrollPropagation(byId('alerts-detail'));
    mapCore.leaflet.DomEvent.disableClickPropagation(byId('alerts-notifications'));
    closeDetail = detail.close;
    let currentWarnings = [];
    let warningRailFilter = 'all';
    let currentLsrReports = [];
    let lsrRailFilter = 'all';

    function renderWarnings(features = currentWarnings) {
        currentWarnings = features.filter((feature) => Object.values(SEVERE_EVENTS).includes(feature?.properties?.event));
        const counts = { all: currentWarnings.length, tor: 0, svr: 0, ffw: 0, smw: 0 };
        currentWarnings.forEach((feature) => {
            const key = Object.entries(SEVERE_EVENTS).find(([, event]) => event === feature?.properties?.event)?.[0];
            if (key) counts[key] += 1;
        });
        Object.entries(counts).forEach(([key, value]) => {
            const count = byId('alerts-warning-filters').querySelector(`[data-count="${key}"]`);
            if (count) count.textContent = String(value);
        });
        byId('alerts-warning-count').textContent = String(currentWarnings.length);
        const visible = currentWarnings.filter((feature) => warningRailFilter === 'all' || feature?.properties?.event === SEVERE_EVENTS[warningRailFilter]);
        const list = byId('alerts-warning-list');
        list.replaceChildren(...visible.sort((a, b) => Date.parse(a?.properties?.expires || '') - Date.parse(b?.properties?.expires || '')).map((feature) => {
            const props = feature?.properties || {};
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'alerts-warning-card';
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
            button.addEventListener('click', () => { engine.zoomTo(feature, { maxZoom: 9 }); detail.open(feature); });
            return button;
        }));
        byId('alerts-warning-empty').hidden = visible.length > 0;
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
            const count = byId('alerts-lsr-filters').querySelector(`[data-count="${key}"]`);
            if (count) count.textContent = String(value);
        });
        byId('alerts-lsr-rail-count').textContent = String(currentLsrReports.length);
        const visible = currentLsrReports
            .filter((feature) => lsrRailFilter === 'all' || lsrFilterGroup(feature) === lsrRailFilter)
            .sort((a, b) => Date.parse(b?.properties?.time || '') - Date.parse(a?.properties?.time || ''));
        byId('alerts-lsr-rail-list').replaceChildren(...visible.map((feature) => {
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
            card.addEventListener('click', () => engine.showLsr(feature));
            return card;
        }));
        byId('alerts-lsr-rail-empty').hidden = visible.length > 0;
    }

    function syncRightRailVisibility() {
        const alertsSelected = selectedCategories().length > 0;
        const lsrSelected = selectedLsrCategories().length > 0;
        byId('alerts-warning-section').hidden = !alertsSelected;
        byId('alerts-lsr-section').hidden = !lsrSelected;
        byId('alerts-right-rail').hidden = !alertsSelected && !lsrSelected;
        document.querySelector('.alerts-app').classList.toggle('is-rail-hidden', !alertsSelected && !lsrSelected);
        requestAnimationFrame(() => mapCore.map.invalidateSize({ pan: false }));
    }

    function showNewAlert(feature) {
        const props = feature?.properties || {};
        const mode = notificationMode();
        if (mode === 'off') return;
        if (mode === 'severe' && !Object.values(SEVERE_EVENTS).includes(props.event)) return;
        const root = byId('alerts-notifications');
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
        close.type = 'button'; close.className = 'alerts-notification-close'; close.setAttribute('aria-label', 'Dismiss alert'); close.textContent = '×';
        close.addEventListener('click', (event) => { event.stopPropagation(); notice.remove(); });
        notice.append(title, area, close);
        const openNotice = () => { engine.zoomTo(feature, { maxZoom: 9 }); detail.open(feature); notice.remove(); };
        notice.addEventListener('click', openNotice);
        notice.addEventListener('keydown', (event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); openNotice(); } });
        root.prepend(notice);
        while (root.children.length > 3) root.lastElementChild.remove();
        setTimeout(() => notice.remove(), 20_000);
    }

    let displayedAlertCount = 0;
    let displayedLsrCount = 0;

    function syncDataMessage() {
        const parts = [];
        if (selectedCategories().length) {
            parts.push(`${displayedAlertCount} active alert${displayedAlertCount === 1 ? '' : 's'}`);
        }
        if (selectedLsrCategories().length) {
            parts.push(`${displayedLsrCount} Local Storm Report${displayedLsrCount === 1 ? '' : 's'} in view`);
        }
        status.setMessage(parts.length ? `${parts.join(' · ')}.` : 'Select alert or Local Storm Report categories.');
    }

    const engine = createAlertsEngine({
        api, mapCore, legend, lsrLegend, status,
        onAlertCount: (count) => {
            displayedAlertCount = count;
            byId('alerts-count').textContent = String(count);
            syncDataMessage();
        },
        onLsrCount: (count) => {
            displayedLsrCount = count;
            byId('alerts-lsr-count').textContent = String(count);
            syncDataMessage();
        },
        onLsrReports: renderLsrReports,
        onWarnings: renderWarnings,
        onDetail: (feature) => detail.open(feature),
        onLsrDetail: (feature) => detail.openLsr(feature),
        onLsrDetailClose: detail.closeLsr,
        onNewAlert: showNewAlert,
    });
    const scrubberBar = byId('alerts-scrubber-bar');
    const scrubber = createScrubber(byId('alerts-bottom-scrubber'), {
        holdAtEnd: true,
        onFrame(frame) { engine.renderArchiveFrame(frame); },
    });

    function populateFilters() {
        const master = byId('alerts-all').closest('label');
        byId('alerts-category-list').replaceChildren(master, ...Object.keys(ALERT_CATEGORIES).map((category) => {
            const label = document.createElement('label');
            label.className = 'alerts-check';
            label.innerHTML = `<span>${category}</span><input class="alerts-category-input" type="checkbox" value="${category}">`;
            label.querySelector('input').checked = category === 'Severe Weather Warnings';
            return label;
        }));
        byId('alerts-lsr-list').replaceChildren(...Object.entries(LSR_CATEGORIES).map(([category, [labelText]]) => {
            const label = document.createElement('label');
            label.className = 'alerts-check';
            label.innerHTML = `<span>${labelText}</span><input type="checkbox" value="${category}">`;
            return label;
        }));
        const severeWarningsInput = [...document.querySelectorAll('#alerts-category-list .alerts-category-input')]
            .find((input) => input.value === 'Severe Weather Warnings');
        severeWarningsInput?.closest('label')?.after(byId('alerts-warning-subtypes'));
    }
    populateFilters();

    function syncCategoryMaster() {
        const inputs = [...document.querySelectorAll('#alerts-category-list .alerts-category-input')];
        const master = byId('alerts-all');
        master.checked = inputs.length > 0 && inputs.every((input) => input.checked);
        master.indeterminate = !master.checked && inputs.some((input) => input.checked);
        byId('alerts-warning-subtypes').hidden = !selectedCategories().includes('Severe Weather Warnings');
    }
    function syncLsrMaster() {
        const inputs = [...document.querySelectorAll('#alerts-lsr-list input')];
        const master = byId('alerts-lsr-all');
        master.checked = inputs.length > 0 && inputs.every((input) => input.checked);
        master.indeterminate = !master.checked && inputs.some((input) => input.checked);
    }
    syncCategoryMaster(); syncLsrMaster(); syncRightRailVisibility();

    async function loadLive(options = {}) {
        if (selectedMode() !== 'live') return;
        await Promise.all([
            engine.loadLive(selection(), regionSelect.value, options),
            engine.loadLsr(selectedLsrCategories(), selectedLsrHours(), options),
        ]);
    }

    let moveTimer = null;
    function scheduleViewportRefresh() {
        if (selectedMode() !== 'live') return;
        clearTimeout(moveTimer);
        moveTimer = setTimeout(() => void loadLive({ silent: true }), 350);
    }

    function applyAlertSelection() {
        const nextSelection = selection();
        const hasCache = engine.setSelection(nextSelection);
        if (nextSelection.categories.length && !hasCache) void engine.loadLive(nextSelection, regionSelect.value);
    }

    byId('alerts-all').addEventListener('change', (event) => {
        document.querySelectorAll('#alerts-category-list .alerts-category-input').forEach((input) => { input.checked = event.target.checked; });
        syncCategoryMaster(); syncRightRailVisibility(); applyAlertSelection();
    });
    byId('alerts-category-list').addEventListener('change', (event) => {
        if (!event.target.matches('.alerts-category-input')) return;
        syncCategoryMaster(); syncRightRailVisibility(); applyAlertSelection();
    });
    byId('alerts-warning-subtypes').addEventListener('change', applyAlertSelection);
    byId('alerts-lsr-all').addEventListener('change', (event) => {
        document.querySelectorAll('#alerts-lsr-list input').forEach((input) => { input.checked = event.target.checked; });
        syncLsrMaster(); syncRightRailVisibility(); engine.clearLsrSelection(); void engine.loadLsr(selectedLsrCategories(), selectedLsrHours());
    });
    byId('alerts-lsr-list').addEventListener('change', () => { syncLsrMaster(); syncRightRailVisibility(); engine.clearLsrSelection(); void engine.loadLsr(selectedLsrCategories(), selectedLsrHours()); });
    byId('alerts-lsr-hours').addEventListener('click', (event) => {
        const button = event.target.closest('[data-hours]'); if (!button) return;
        byId('alerts-lsr-hours').querySelectorAll('button').forEach((item) => item.classList.toggle('is-active', item === button));
        engine.clearLsrSelection();
        void engine.loadLsr(selectedLsrCategories(), selectedLsrHours());
    });
    byId('alerts-warning-filters').addEventListener('click', (event) => {
        const button = event.target.closest('[data-filter]'); if (!button) return;
        warningRailFilter = button.dataset.filter;
        byId('alerts-warning-filters').querySelectorAll('button').forEach((item) => item.classList.toggle('is-active', item === button));
        renderWarnings();
    });
    byId('alerts-lsr-filters').addEventListener('click', (event) => {
        const button = event.target.closest('[data-filter]'); if (!button) return;
        lsrRailFilter = button.dataset.filter;
        byId('alerts-lsr-filters').querySelectorAll('button').forEach((item) => item.classList.toggle('is-active', item === button));
        renderLsrReports();
    });

    byId('alerts-sidebar-tabs').addEventListener('core:sidebar-tab-change', (event) => {
        if (!['live', 'archive'].includes(event.detail?.tab)) return;
        const archive = event.detail.tab === 'archive';
        scrubber.pause(); scrubber.setFrames([]); scrubberBar.hidden = true;
        engine.clear(); detail.close(); status.clear();
        if (!archive) void loadLive(); else status.setMessage('Choose an ending time and lookback, then load.');
    });

    const now = new Date();
    const archiveTime = byId('alerts-archive-time');
    const archiveLookback = byId('alerts-archive-lookback');
    const archiveLookbackValue = byId('alerts-archive-lookback-value');
    archiveTime.value = localDatetimeValue(now);
    function formatArchiveLookback(value) {
        const minutes = Math.max(5, Math.round(Number(value)));
        const wholeHours = Math.floor(minutes / 60);
        const remainder = minutes % 60;
        if (!wholeHours) return `${remainder} min`;
        return remainder ? `${wholeHours}h ${remainder}m` : `${wholeHours} hour${wholeHours === 1 ? '' : 's'}`;
    }
    archiveLookback.addEventListener('input', () => {
        archiveLookbackValue.textContent = formatArchiveLookback(archiveLookback.value);
    });
    byId('alerts-load-archive').addEventListener('click', async () => {
        const to = archiveTime.value;
        const endMs = Date.parse(to);
        if (!to || !Number.isFinite(endMs)) { status.setMessage('Choose a valid archive ending time.', 'error'); return; }
        const from = new Date(endMs - Number(archiveLookback.value) * 60_000).toISOString();
        try {
            const frames = await engine.loadArchive(from, to, regionSelect.value);
            const labeled = frames.map((frame) => ({ ...frame, label: frameLabel(frame) }));
            scrubber.setFrames(labeled, { index: Math.max(0, labeled.length - 1) });
            scrubberBar.hidden = labeled.length === 0;
        } catch (error) { status.setMessage(`Archive unavailable: ${error.message}`, 'error'); }
    });

    let autoTimer = null;
    const autoUpdate = byId('alerts-auto-update');
    function syncAutoUpdate() {
        clearInterval(autoTimer);
        autoTimer = autoUpdate.checked ? setInterval(() => void loadLive({ silent: true, refresh: true }), AUTO_UPDATE_MS) : null;
    }
    autoUpdate.addEventListener('change', syncAutoUpdate);
    syncAutoUpdate();
    regionSelect.addEventListener('change', () => { detail.close(); engine.clear(); mapCore.fitRegion(regionSelect.value); scheduleViewportRefresh(); });
    byId('alerts-refresh').addEventListener('click', () => selectedMode() === 'live' ? void loadLive({ refresh: true }) : byId('alerts-load-archive').click());
    byId('alerts-clear').addEventListener('click', () => { scrubber.pause(); scrubber.setFrames([]); scrubberBar.hidden = true; detail.close(); engine.clear(); status.clear(); status.setMessage('Alerts cleared.'); });
    byId('alerts-basemap').addEventListener('change', (event) => mapCore.setBasemap(event.target.value));
    const opacity = byId('alerts-opacity');
    opacity.addEventListener('input', () => { const value = engine.setOpacity(opacity.value); byId('alerts-opacity-label').textContent = `Polygon Opacity (${value.toFixed(2).replace(/\.?0+$/, '')})`; });
    opacity.dispatchEvent(new Event('input'));
    document.querySelectorAll('input[name="alerts-polygon-pulse"]').forEach((input) => input.addEventListener('change', () => {
        if (input.checked) engine.setPulseEnabled(input.value === 'on');
    }));
    engine.setPulseEnabled(document.querySelector('input[name="alerts-polygon-pulse"]:checked')?.value !== 'off');

    const cityDensity = byId('alerts-city-density'); const cityFont = byId('alerts-city-font-size');
    cityDensity.value = String(Number(cityDefaults.density) || 0.25); cityFont.value = String(Number(cityDefaults.fontSize) || 0.6);
    const citySource = ['us', 'world'].includes(cityDefaults.source) ? cityDefaults.source : 'off';
    document.querySelector(`input[name="alerts-cities-source"][value="${citySource}"]`).checked = true;
    function syncCityControls() {
        const source = document.querySelector('input[name="alerts-cities-source"]:checked')?.value || 'off';
        document.querySelectorAll('[data-city-adjustment]').forEach((row) => { row.classList.toggle('is-disabled', source === 'off'); row.querySelector('input').disabled = source === 'off'; });
        byId('alerts-city-font-size-label').textContent = `City Font Size (${Number(cityFont.value).toFixed(2).replace(/\.?0+$/, '')})`;
    }
    document.querySelectorAll('input[name="alerts-cities-source"]').forEach((input) => input.addEventListener('change', () => { syncCityControls(); void mapCore.setCitySource(input.value); }));
    cityDensity.addEventListener('input', () => mapCore.setCityDensity(cityDensity.value));
    cityFont.addEventListener('input', () => { mapCore.setCityFontSize(cityFont.value); syncCityControls(); });
    mapCore.setCityDensity(cityDensity.value); mapCore.setCityFontSize(cityFont.value); syncCityControls(); void mapCore.setCitySource(citySource);
    document.querySelectorAll('[data-map-overlay]').forEach((input) => input.addEventListener('change', () => void mapCore.setOverlayVisible(input.dataset.mapOverlay, input.checked)));
    await Promise.all([...document.querySelectorAll('[data-map-overlay]:checked')].map((input) => mapCore.setOverlayVisible(input.dataset.mapOverlay, true))).catch(() => {});

    mapCore.map.on('movestart zoomstart', detail.close);
    mapCore.map.on('moveend', () => { engine.renderLegend(); scheduleViewportRefresh(); });
    status.setMessage('Loading active severe-weather warnings…');
    await loadLive();
}

initialize().catch((error) => {
    console.error('[alerts] initialization failed', error);
    byId('alerts-message').textContent = `Alerts initialization failed: ${error.message}`;
});
