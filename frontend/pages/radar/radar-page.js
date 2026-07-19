import * as api from '../../core/api.js';
import { createLegendHost } from '../../core/legend.js';
import { createMapCore, REGION_LABELS } from '../../core/map-core.js?v=20260718b';
import { renderProductNav } from '../../core/nav.js';
import { createScrubber } from '../../core/scrubber.js';
import { createSidebarTabs } from '../../core/sidebar-tabs.js';
import { loadDefaultSettings, loadPageSettings } from '../../core/settings.js';
import { createStatusReporter } from '../../core/status.js';
import { createRadarEngine } from './radar-engine.js';

const byId = (id) => document.getElementById(id);
const AUTO_UPDATE_INTERVAL_MS = 90_000;

function activeSelection() {
    const hours = Number(byId('radar-lookback')?.value || 1);
    return {
        site: String(byId('radar-site')?.value || '').trim().toUpperCase(),
        product: String(byId('radar-product')?.value || '').trim().toUpperCase(),
        elevation: String(byId('radar-elevation')?.value || '').trim(),
        hours: Math.max(0.5, Math.min(12, Number.isFinite(hours) ? hours : 1)),
    };
}

function frameLabel(frame) {
    const date = new Date(frame?.timestamp || '');
    if (!Number.isFinite(date.getTime())) return String(frame?.frame_key || '—');
    return date.toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
}

function lookbackLabel(value) {
    const hours = Number(value);
    if (hours === 0.5) return '30M';
    return `${Number.isInteger(hours) ? hours : hours.toFixed(1)}H`;
}

async function initialize() {
    renderProductNav(byId('product-nav'), 'Radar');
    const sidebarTabs = createSidebarTabs(byId('radar-sidebar-tabs'), { defaultTab: 'data' });
    const settings = await loadPageSettings('radar', { mapView: 'CONUS', hours: 1 });
    const defaults = await loadDefaultSettings().catch(() => ({}));
    const cityDefaults = defaults?.global?.cityLabels || {};

    const regionSelect = byId('radar-region');
    regionSelect.replaceChildren(...Object.entries(REGION_LABELS).map(([code, label]) => {
        const option = document.createElement('option');
        option.value = code;
        option.textContent = label;
        return option;
    }));
    regionSelect.value = REGION_LABELS[settings.mapView] ? settings.mapView : 'CONUS';

    let resetRadarState = () => {};
    const mapCore = createMapCore(byId('radar-map'), {
        region: regionSelect.value,
        basemap: 'Dark (No Labels)',
        onResetView: () => resetRadarState(),
    });
    const legend = createLegendHost(byId('radar-legend'), { align: 'left' });
    const status = createStatusReporter({
        globalTimestamp: byId('global-timestamp'),
        message: byId('radar-message'),
        updated: byId('radar-updated'),
        age: byId('radar-age'),
        provider: byId('radar-provider'),
        source: byId('radar-source'),
    });

    let catalog = { sites: [], products: {} };
    let autoUpdateTimer = null;
    const scrubberBar = byId('radar-scrubber-bar');
    const scrubber = createScrubber(byId('radar-bottom-scrubber'), {
        onFrame(_frame, index) { void engine.renderFrameAt(index); },
    });

    function showScrubber(visible) { scrubberBar.hidden = !visible; }

    function syncElevationControl() {
        const option = byId('radar-product')?.selectedOptions?.[0];
        const enabled = option?.dataset.elevationSelection === 'true';
        byId('radar-elevation-wrap').hidden = !enabled;
        if (!enabled) byId('radar-elevation').value = '';
    }

    function renderElevationPills() {
        const select = byId('radar-elevation');
        const pills = byId('radar-elevation-pills');
        pills.replaceChildren(...Array.from(select.options).filter((option) => option.value).map((option) => {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'radar-elevation-pill';
            button.dataset.elevation = option.value;
            button.setAttribute('role', 'radio');
            button.setAttribute('aria-checked', String(select.value === option.value));
            button.textContent = option.textContent;
            button.addEventListener('click', () => {
                if (select.value === option.value) return;
                select.value = option.value;
                renderElevationPills();
                void engine.refreshAll();
            });
            return button;
        }));
    }

    function updateElevationOptions(data) {
        const elevations = Array.isArray(data?.available_elevations) ? data.available_elevations : [];
        if (!elevations.length) return;
        const select = byId('radar-elevation');
        const current = select.value;
        const selected = data?.selected_elevation != null ? Number(data.selected_elevation).toFixed(1) : '';
        select.replaceChildren(...elevations.map((elevation) => {
            const option = document.createElement('option');
            option.value = Number(elevation).toFixed(1);
            option.textContent = `${option.value}°`;
            return option;
        }));
        const values = new Set(Array.from(select.options, (option) => option.value));
        select.value = values.has(current) ? current : values.has(selected) ? selected : select.options[0]?.value || '';
        renderElevationPills();
        syncElevationControl();
    }

    function populateProducts() {
        const select = byId('radar-product');
        const keep = select.value;
        const site = activeSelection().site;
        const conus = site ? engine.isConusSite(site) : true;
        const groups = new Map();
        select.replaceChildren();
        Object.entries(catalog.products || {}).forEach(([productId, product]) => {
            const level = String(product?.level || 'Other');
            if (level === 'Level 3' && !conus) return;
            if (!groups.has(level)) {
                const group = document.createElement('optgroup');
                group.label = level;
                groups.set(level, group);
                select.appendChild(group);
            }
            const option = document.createElement('option');
            option.value = String(productId).toUpperCase();
            option.textContent = String(product?.label || productId);
            option.dataset.units = String(product?.units || '');
            option.dataset.elevationSelection = String(!!product?.capabilities?.elevation_selection);
            groups.get(level).appendChild(option);
        });
        const values = new Set(Array.from(select.options, (option) => option.value));
        select.value = values.has(keep) ? keep : values.has('L2_REF') ? 'L2_REF' : select.options[0]?.value || '';
        select.disabled = !site;
        syncElevationControl();
    }

    function populateSites() {
        const select = byId('radar-site');
        const keep = select.value;
        const placeholder = document.createElement('option');
        placeholder.value = '';
        placeholder.textContent = '— Select Radar Site —';
        const options = (catalog.sites || []).map((site) => {
            const option = document.createElement('option');
            option.value = String(site.site || '').toUpperCase();
            option.textContent = site.configured ? `${option.value} (Live Cache)` : option.value;
            return option;
        });
        select.replaceChildren(placeholder, ...options);
        if (keep && options.some((option) => option.value === keep)) select.value = keep;
    }

    const engine = createRadarEngine({
        api,
        mapCore,
        legend,
        status,
        getSelection: activeSelection,
        onCatalog(data) {
            catalog = data;
            populateSites();
            populateProducts();
            if (byId('radar-show-sites').checked) engine.showSiteLegend();
        },
        onElevationData: updateElevationOptions,
        onFrames(nextFrames, options = {}) {
            const labeled = nextFrames.map((frame) => ({ ...frame, label: frameLabel(frame) }));
            scrubber.setFrames(labeled, { index: options.index || 0, silent: true, keepPlaying: true });
            showScrubber(labeled.length > 0);
        },
        onSitePicked(site, coords) {
            byId('radar-site').value = site;
            populateProducts();
            engine.syncHighlights(site);
            mapCore.map.flyTo(coords, Math.max(mapCore.map.getZoom(), 9), { duration: 0.6 });
            void engine.refreshAll();
        },
        onMessage(text, tone) { status.setMessage(text, tone); },
    });

    const siteSelect = byId('radar-site');
    resetRadarState = (message = 'Radar selection cleared.') => {
        scrubber.pause();
        siteSelect.value = '';
        byId('radar-product').value = 'L2_REF';
        byId('radar-elevation').replaceChildren(new Option('', ''));
        engine.clear();
        populateProducts();
        engine.syncHighlights('');
        showScrubber(false);
        status.clear();
        status.setMessage(message);
        if (byId('radar-show-sites').checked) engine.showSiteLegend();
    };

    siteSelect.addEventListener('change', () => {
        engine.clear();
        populateProducts();
        engine.syncHighlights();
        const selection = activeSelection();
        const coords = engine.siteCoords(selection.site);
        if (!selection.site) {
            showScrubber(false);
            if (byId('radar-show-sites').checked) engine.showSiteLegend();
            return;
        }
        if (coords) mapCore.map.flyTo(coords, Math.max(mapCore.map.getZoom(), 9), { duration: 0.6 });
        void engine.refreshAll();
    });

    byId('radar-product').addEventListener('change', () => {
        byId('radar-elevation').replaceChildren(new Option('', ''));
        syncElevationControl();
        engine.clear();
        void engine.refreshAll();
    });

    const lookback = byId('radar-lookback');
    lookback.value = String(Math.max(0.5, Math.min(12, Number(settings.hours) || 1)));
    byId('radar-lookback-value').textContent = lookbackLabel(lookback.value);
    lookback.addEventListener('input', () => { byId('radar-lookback-value').textContent = lookbackLabel(lookback.value); });
    lookback.addEventListener('change', () => { if (activeSelection().site) void engine.loadFrames(); });

    byId('radar-show-sites').addEventListener('change', (event) => {
        engine.setSitesVisible(event.target.checked);
        if (event.target.checked && !activeSelection().site) engine.showSiteLegend();
        else if (activeSelection().product) void engine.showProductLegend(activeSelection().product);
    });
    byId('radar-show-storm-tracks').addEventListener('change', (event) => engine.setStormTracksVisible(event.target.checked));
    byId('radar-inspector').addEventListener('change', (event) => engine.setInspectorVisible(event.target.checked));

    byId('radar-auto-update').addEventListener('change', (event) => {
        clearInterval(autoUpdateTimer);
        autoUpdateTimer = event.target.checked
            ? setInterval(() => { if (activeSelection().site) void engine.loadFrames({ refresh: true }); }, AUTO_UPDATE_INTERVAL_MS)
            : null;
    });

    const opacityInput = byId('radar-opacity');
    function updateOpacity() {
        const value = engine.setOpacity(opacityInput.value);
        byId('radar-opacity-label').textContent = `Radar Opacity (${value.toFixed(2).replace(/\.?0+$/, '')})`;
    }
    opacityInput.addEventListener('input', updateOpacity);
    updateOpacity();

    regionSelect.addEventListener('change', () => {
        resetRadarState();
        mapCore.fitRegion(regionSelect.value);
    });
    byId('radar-basemap').addEventListener('change', (event) => mapCore.setBasemap(event.target.value));
    byId('radar-refresh').addEventListener('click', () => {
        if (activeSelection().site) void engine.refreshAll();
        else void engine.loadCatalog();
    });
    byId('radar-clear').addEventListener('click', () => resetRadarState());

    const citySource = ['us', 'world'].includes(cityDefaults.source) ? cityDefaults.source : 'off';
    const cityDensityInput = byId('radar-city-density');
    const cityFontSizeInput = byId('radar-city-font-size');
    cityDensityInput.value = String(Number(cityDefaults.density) || 0.25);
    cityFontSizeInput.value = String(Number(cityDefaults.fontSize) || 0.6);
    const initialCityInput = document.querySelector(`input[name="radar-cities-source"][value="${citySource}"]`);
    if (initialCityInput) initialCityInput.checked = true;
    const selectedCitySource = () => document.querySelector('input[name="radar-cities-source"]:checked')?.value || 'off';
    function syncCityControls() {
        const disabled = selectedCitySource() === 'off';
        document.querySelectorAll('[data-city-adjustment]').forEach((row) => {
            row.classList.toggle('is-disabled', disabled);
            row.querySelector('input').disabled = disabled;
        });
        byId('radar-city-font-size-label').textContent = `City Font Size (${Number(cityFontSizeInput.value).toFixed(2).replace(/\.?0+$/, '')})`;
    }
    document.querySelectorAll('input[name="radar-cities-source"]').forEach((input) => {
        input.addEventListener('change', () => {
            syncCityControls();
            void mapCore.setCitySource(selectedCitySource()).catch((error) => status.setMessage(`City overlay unavailable: ${error.message}`, 'error'));
        });
    });
    cityDensityInput.addEventListener('input', () => mapCore.setCityDensity(cityDensityInput.value));
    cityFontSizeInput.addEventListener('input', () => { mapCore.setCityFontSize(cityFontSizeInput.value); syncCityControls(); });
    mapCore.setCityDensity(cityDensityInput.value);
    mapCore.setCityFontSize(cityFontSizeInput.value);
    syncCityControls();
    void mapCore.setCitySource(citySource).catch((error) => status.setMessage(`City overlay unavailable: ${error.message}`, 'error'));

    document.querySelectorAll('[data-map-overlay]').forEach((input) => {
        input.addEventListener('change', () => {
            void mapCore.setOverlayVisible(input.dataset.mapOverlay, input.checked)
                .catch((error) => status.setMessage(`Map overlay unavailable: ${error.message}`, 'error'));
        });
    });
    void Promise.all([...document.querySelectorAll('[data-map-overlay]:checked')].map((input) => (
        mapCore.setOverlayVisible(input.dataset.mapOverlay, true)
    ))).catch((error) => status.setMessage(`Map overlay unavailable: ${error.message}`, 'error'));

    status.setMessage('Select a radar site to load current imagery and animation frames.');
    await engine.loadCatalog();

    window.addEventListener('beforeunload', () => {
        clearInterval(autoUpdateTimer);
        sidebarTabs.destroy();
        legend.destroy();
        scrubber.destroy();
        engine.destroy();
        mapCore.destroy();
    }, { once: true });
}

initialize().catch((error) => {
    console.error('[radar] startup failed', error);
    const message = byId('radar-message');
    if (message) message.textContent = `Startup failed: ${error.message}`;
});
