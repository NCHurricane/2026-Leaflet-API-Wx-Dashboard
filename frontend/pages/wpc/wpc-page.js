import * as api from '../../core/api.js';
import { createLegendHost } from '../../core/legend.js';
import { createMapCore, REGION_LABELS } from '../../core/map-core.js';
import { renderProductNav } from '../../core/nav.js';
import { createSidebarTabs } from '../../core/sidebar-tabs.js';
import { loadDefaultSettings, loadPageSettings } from '../../core/settings.js';
import { createStatusReporter } from '../../core/status.js';
import { createWpcDetailPanel } from './wpc-detail.js';
import { createWpcEngine } from './wpc-engine.js';
import { createScrubber } from '../../core/scrubber.js';

const byId = (id) => document.getElementById(id);
const SELECT_PRODUCT_MESSAGE = 'Pick a WPC product group, then a day or product, to load an overlay.';

// ── Selection state (ported from the shell's wpc-page controller) ───────────
const state = {
    group: 'ero',
    eroDay: 1,
    qpfTab: '6hr',
    qpf24hrId: '',
    qpf6hrIndex: 0,
    qpfMultiId: '',
    winterTab: 'snow',
    snowDay: 1,
    snowId: '',
    iceId: '',
    sigwxId: 'sigwx_day1',
    surfaceIndex: 0,
    forecastIndex: 0,
};

let catalogGroups = new Map();

function qpf6hrProducts() {
    return (catalogGroups.get('qpf')?.products || []).filter((p) => p.id.startsWith('qpf6_'));
}

Object.defineProperty(state, 'surfaceId', {
    get() {
        return (catalogGroups.get('surface')?.products || [])[state.surfaceIndex]?.id || '';
    },
});
Object.defineProperty(state, 'forecastId', {
    get() {
        return (catalogGroups.get('forecast')?.products || [])[state.forecastIndex]?.id || '';
    },
});
Object.defineProperty(state, 'qpf6hrId', {
    get() {
        return qpf6hrProducts()[state.qpf6hrIndex]?.id || '';
    },
});

function activeDay() {
    if (state.group === 'ero') return state.eroDay;
    if (state.group === 'winter') return state.winterTab === 'snow' ? state.snowDay : 1;
    return 1;
}

function activeProduct() {
    switch (state.group) {
        case 'qpf':
            if (state.qpfTab === '24hr') return state.qpf24hrId;
            if (state.qpfTab === 'multiday') return state.qpfMultiId;
            return state.qpf6hrId || '';
        case 'winter':
            return state.winterTab === 'snow' ? state.snowId : state.iceId;
        case 'sigwx':
            return state.sigwxId;
        case 'surface':
            return state.surfaceId || '';
        case 'forecast':
            return state.forecastId || '';
        default:
            return '';
    }
}

// ── Pill / panel helpers ────────────────────────────────────────────────────
function selectPill(container, selectedBtn) {
    container.querySelectorAll('[aria-selected]').forEach((btn) => {
        btn.setAttribute('aria-selected', btn === selectedBtn ? 'true' : 'false');
    });
}

function buildRadioList(ulEl, products, name, currentId) {
    if (!ulEl) return;
    ulEl.replaceChildren(...products.map((p) => {
        const inputId = `${name}-${p.id}`;
        const li = document.createElement('li');
        li.className = 'wpc-radio-item';
        const label = document.createElement('label');
        label.htmlFor = inputId;
        label.textContent = p.label;
        const input = document.createElement('input');
        input.type = 'radio';
        input.id = inputId;
        input.name = name;
        input.value = p.id;
        input.checked = !!currentId && p.id === currentId;
        li.appendChild(label);
        li.appendChild(input);
        return li;
    }));
}

async function initialize() {
    renderProductNav(byId('product-nav'), 'WPC');
    const sidebarTabs = createSidebarTabs(byId('wpc-sidebar-tabs'), { defaultTab: 'data' });
    const settings = await loadPageSettings('wpc', { mapView: 'CONUS', autoLoad: false });
    const defaults = await loadDefaultSettings().catch(() => ({}));
    const cityDefaults = defaults?.global?.cityLabels || {};
    const regionSelect = byId('wpc-region');
    regionSelect.replaceChildren(...Object.entries(REGION_LABELS).map(([code, label]) => {
        const option = document.createElement('option');
        option.value = code;
        option.textContent = label;
        return option;
    }));
    regionSelect.value = REGION_LABELS[settings.mapView] ? settings.mapView : 'CONUS';

    const mapCore = createMapCore(byId('wpc-map'), {
        region: regionSelect.value,
        basemap: 'Dark (No Labels)',
    });
    const legend = createLegendHost(byId('wpc-legend'), { align: 'left' });
    const status = createStatusReporter({
        globalTimestamp: byId('global-timestamp'),
        message: byId('wpc-message'),
        updated: byId('wpc-updated'),
        age: byId('wpc-age'),
        provider: byId('wpc-provider'),
        source: byId('wpc-source'),
    });
    const detail = createWpcDetailPanel(byId('wpc-map-wrap'), mapCore, {
        zoomToFeature: (feat) => {
            try {
                const bounds = mapCore.leaflet.geoJSON(feat).getBounds();
                if (bounds.isValid()) mapCore.map.flyToBounds(bounds, { padding: [24, 24], duration: 0.9 });
            } catch { /* ignore invalid geometry */ }
        },
    });
    const emptyOverlay = byId('wpc-map-empty');
    const engine = createWpcEngine({
        api,
        mapCore,
        legend,
        status,
        onEmptyMessage: (msg) => {
            emptyOverlay.textContent = msg || '';
            emptyOverlay.hidden = !msg;
        },
        onDetail: (latlng, feat, features) => detail.open(latlng, feat, features),
    });

    let suppressReload = false;

    function reload() {
        if (suppressReload) return;
        detail.close();
        void engine.load({ group: state.group, day: activeDay(), product: activeProduct() });
    }

    function withoutReload(callback) {
        suppressReload = true;
        try {
            callback?.();
        } finally {
            suppressReload = false;
        }
    }

    // ── Shared bottom scrubber (forecast charts + QPF 6-hr sequence) ────────
    const scrubFrames = { forecast: [], qpf6hr: [] };
    let scrubber = null;

    function scrubberKey() {
        if (state.group === 'forecast') return 'forecast';
        if (state.group === 'qpf' && state.qpfTab === '6hr') return 'qpf6hr';
        return null;
    }

    function syncSidebarRadio(listId, index) {
        const ul = byId(listId);
        if (!ul) return;
        ul.querySelectorAll('input[type="radio"]').forEach((input, i) => {
            input.checked = i === index;
        });
    }

    function initScrubber() {
        const el = byId('wpc-bottom-scrubber');
        if (!el || scrubber) return;
        scrubber = createScrubber(el, {
            onFrame(frame, index) {
                const key = scrubberKey();
                if (key === 'forecast') {
                    state.forecastIndex = index;
                    syncSidebarRadio('wpc-forecast-list', index);
                }
                if (key === 'qpf6hr') {
                    state.qpf6hrIndex = index;
                    syncSidebarRadio('wpc-qpf-6hr-list', index);
                }
                reload();
            },
        });
    }

    function activateScrubber() {
        const key = scrubberKey();
        const bar = byId('wpc-scrubber-bar');
        if (!bar) return;
        bar.hidden = !key;
        if (!key) return;
        if (!scrubber) initScrubber();
        const savedIndex = key === 'forecast' ? state.forecastIndex : state.qpf6hrIndex;
        scrubber?.setFrames(scrubFrames[key]);
        scrubber?.goTo(savedIndex);
    }

    // ── Catalog-driven lists ────────────────────────────────────────────────
    function populateCatalogLists() {
        buildRadioList(
            byId('wpc-qpf-24hr-list'),
            (catalogGroups.get('qpf')?.products || []).filter((p) => p.id.startsWith('qpf24_')),
            'wpc-qpf-24hr-list', state.qpf24hrId,
        );
        buildRadioList(
            byId('wpc-qpf-multiday-list'),
            (catalogGroups.get('qpf')?.products || []).filter(
                (p) => !p.id.startsWith('qpf24_') && !p.id.startsWith('qpf6_'),
            ),
            'wpc-qpf-multiday-list', state.qpfMultiId,
        );
        populateWinterSnowList();
        buildRadioList(
            byId('wpc-winter-ice-list'),
            (catalogGroups.get('winter')?.products || []).filter((p) => p.id.includes('_ice')),
            'wpc-winter-ice-list', state.iceId,
        );

        scrubFrames.forecast = (catalogGroups.get('forecast')?.products || [])
            .map((p) => ({ label: p.label, id: p.id }));
        scrubFrames.qpf6hr = qpf6hrProducts().map((p) => ({ label: p.label, id: p.id }));
        const forecastProducts = catalogGroups.get('forecast')?.products || [];
        buildRadioList(byId('wpc-forecast-list'), forecastProducts, 'wpc-forecast-list',
            forecastProducts[state.forecastIndex]?.id || '');
        buildRadioList(byId('wpc-qpf-6hr-list'), qpf6hrProducts(), 'wpc-qpf-6hr-list',
            qpf6hrProducts()[state.qpf6hrIndex]?.id || '');
        withoutReload(() => activateScrubber());
    }

    function populateWinterSnowList() {
        const products = (catalogGroups.get('winter')?.products || []).filter(
            (p) => p.id.includes('_snow') && (p.days || []).includes(state.snowDay),
        );
        buildRadioList(byId('wpc-winter-snow-list'), products, 'wpc-winter-snow-list', state.snowId);
    }

    // ── Group pills: navigation only — clear the overlay, no auto-load ──────
    document.querySelectorAll('.wpc-group-pill').forEach((pill) => {
        pill.addEventListener('click', () => {
            state.group = pill.dataset.wpcGroup;
            selectPill(pill.closest('.wpc-group-pills'), pill);
            document.querySelectorAll('.wpc-group-panel').forEach((panel) => {
                panel.classList.toggle('is-active', panel.id === `wpc-panel-${state.group}`);
            });
            detail.close();
            engine.clear();
            status.setMessage(SELECT_PRODUCT_MESSAGE);
            withoutReload(() => {
                if (state.group === 'qpf') {
                    byId('wpc-panel-qpf')?.querySelector('[data-wpc-qpf-tab="6hr"]')?.click();
                } else if (state.group === 'winter') {
                    byId('wpc-panel-winter')?.querySelector('[data-wpc-winter-tab="snow"]')?.click();
                }
                activateScrubber();
            });
        });
    });

    // ── ERO day pills ───────────────────────────────────────────────────────
    byId('wpc-panel-ero')?.querySelectorAll('[data-wpc-ero-day]').forEach((btn) => {
        btn.addEventListener('click', () => {
            state.eroDay = Number(btn.dataset.wpcEroDay);
            selectPill(btn.closest('.wpc-day-pills'), btn);
            if (state.group === 'ero') reload();
        });
    });

    // ── QPF sub-tabs + radio lists ──────────────────────────────────────────
    const qpfPanel = byId('wpc-panel-qpf');
    qpfPanel?.querySelectorAll('[data-wpc-qpf-tab]').forEach((btn) => {
        btn.addEventListener('click', () => {
            state.qpfTab = btn.dataset.wpcQpfTab;
            selectPill(btn.closest('.wpc-subtabs'), btn);
            qpfPanel.querySelectorAll('.wpc-subtab-panel').forEach((p) => {
                p.classList.toggle('is-active', p.id === `wpc-qpf-panel-${state.qpfTab}`);
            });
            activateScrubber();
            if (state.group === 'qpf') reload();
        });
    });
    const wireQpfRadioList = (listId, stateKey, tab) => {
        byId(listId)?.addEventListener('change', (e) => {
            if (e.target.name === listId) {
                state[stateKey] = e.target.value;
                if (state.group === 'qpf' && state.qpfTab === tab) reload();
            }
        });
    };
    wireQpfRadioList('wpc-qpf-24hr-list', 'qpf24hrId', '24hr');
    wireQpfRadioList('wpc-qpf-multiday-list', 'qpfMultiId', 'multiday');

    // ── Winter sub-tabs, day pills, radio lists ─────────────────────────────
    const winterPanel = byId('wpc-panel-winter');
    winterPanel?.querySelectorAll('[data-wpc-winter-tab]').forEach((btn) => {
        btn.addEventListener('click', () => {
            state.winterTab = btn.dataset.wpcWinterTab;
            selectPill(btn.closest('.wpc-subtabs'), btn);
            winterPanel.querySelectorAll('.wpc-subtab-panel').forEach((p) => {
                p.classList.toggle('is-active', p.id === `wpc-winter-panel-${state.winterTab}`);
            });
            if (state.group === 'winter') reload();
        });
    });
    winterPanel?.querySelectorAll('[data-wpc-snow-day]').forEach((btn) => {
        btn.addEventListener('click', () => {
            state.snowDay = Number(btn.dataset.wpcSnowDay);
            selectPill(btn.closest('.wpc-day-pills'), btn);
            populateWinterSnowList();
            if (state.group === 'winter' && state.winterTab === 'snow') reload();
        });
    });
    byId('wpc-winter-snow-list')?.addEventListener('change', (e) => {
        if (e.target.name === 'wpc-winter-snow-list') {
            state.snowId = e.target.value;
            if (state.group === 'winter' && state.winterTab === 'snow') reload();
        }
    });
    byId('wpc-winter-ice-list')?.addEventListener('change', (e) => {
        if (e.target.name === 'wpc-winter-ice-list') {
            state.iceId = e.target.value;
            if (state.group === 'winter' && state.winterTab === 'ice') reload();
        }
    });

    // ── SigWx radio list ────────────────────────────────────────────────────
    byId('wpc-sigwx-list')?.addEventListener('change', (e) => {
        if (e.target.name === 'wpc-sigwx') {
            state.sigwxId = e.target.value;
            if (state.group === 'sigwx') reload();
        }
    });

    // ── Scrubber sidebar radio lists ────────────────────────────────────────
    const wireScrubberSidebarList = (listId, indexKey) => {
        byId(listId)?.addEventListener('change', (e) => {
            if (e.target.name !== listId) return;
            const inputs = [...byId(listId).querySelectorAll('input[type="radio"]')];
            const index = inputs.indexOf(e.target);
            if (index < 0) return;
            state[indexKey] = index;
            scrubber?.goTo(index);
        });
    };
    wireScrubberSidebarList('wpc-forecast-list', 'forecastIndex');
    wireScrubberSidebarList('wpc-qpf-6hr-list', 'qpf6hrIndex');

    // ── Style controls ──────────────────────────────────────────────────────
    function updateOpacityLabel() {
        const value = Number(byId('wpc-opacity').value);
        const label = document.querySelector('label[for="wpc-opacity"]');
        if (label) label.textContent = `Overlay Opacity (${value.toFixed(2).replace(/\.?0+$/, '') || '0'})`;
    }
    byId('wpc-opacity').addEventListener('input', () => {
        updateOpacityLabel();
        engine.setOpacity(byId('wpc-opacity').value);
    });
    engine.setOpacity(byId('wpc-opacity').value);
    byId('wpc-basemap').addEventListener('change', (event) => mapCore.setBasemap(event.target.value));

    // ── Region / refresh ────────────────────────────────────────────────────
    regionSelect.addEventListener('change', () => mapCore.fitRegion(regionSelect.value));
    byId('wpc-refresh').addEventListener('click', () => reload());

    // ── Cities ──────────────────────────────────────────────────────────────
    const citySource = ['us', 'world'].includes(cityDefaults.source) ? cityDefaults.source : 'off';
    const cityDensity = Number(cityDefaults.density);
    const cityFontSize = Number(cityDefaults.fontSize);
    const cityDensityInput = byId('wpc-city-density');
    const cityFontSizeInput = byId('wpc-city-font-size');
    cityDensityInput.value = String(cityDensity >= 0.01 && cityDensity <= 1 ? cityDensity : 0.25);
    cityFontSizeInput.value = String(cityFontSize >= 0.4 && cityFontSize <= 1.2 ? cityFontSize : 0.6);
    const initialCitySourceInput = document.querySelector(`input[name="wpc-cities-source"][value="${citySource}"]`);
    if (initialCitySourceInput) initialCitySourceInput.checked = true;

    function selectedCitySource() {
        return document.querySelector('input[name="wpc-cities-source"]:checked')?.value || 'off';
    }

    function updateCityControlLabels() {
        const source = selectedCitySource();
        const disabled = source === 'off';
        document.querySelectorAll('[data-city-adjustment]').forEach((row) => {
            row.classList.toggle('is-disabled', disabled);
            row.querySelector('input').disabled = disabled;
        });
        const distanceKm = Math.round(mapCore.getCityMinDistanceKm(source, cityDensityInput.value));
        byId('wpc-city-density-label').textContent = `City Density (${distanceKm} km)`;
        const fontSizeLabel = Number(cityFontSizeInput.value).toFixed(2).replace(/\.?0+$/, '');
        byId('wpc-city-font-size-label').textContent = `City Font Size (${fontSizeLabel})`;
    }

    document.querySelectorAll('input[name="wpc-cities-source"]').forEach((input) => {
        input.addEventListener('change', () => {
            updateCityControlLabels();
            void mapCore.setCitySource(selectedCitySource()).catch((error) => {
                status.setMessage(`City overlay unavailable: ${error.message}`, 'error');
            });
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
    mapCore.setCityDensity(cityDensityInput.value);
    mapCore.setCityFontSize(cityFontSizeInput.value);
    updateCityControlLabels();
    void mapCore.setCitySource(citySource).catch((error) => {
        status.setMessage(`City overlay unavailable: ${error.message}`, 'error');
    });

    // ── Map overlays ────────────────────────────────────────────────────────
    document.querySelectorAll('[data-map-overlay]').forEach((input) => {
        input.addEventListener('change', () => {
            void mapCore.setOverlayVisible(input.dataset.mapOverlay, input.checked).catch((error) => {
                status.setMessage(`Map overlay unavailable: ${error.message}`, 'error');
            });
        });
    });
    void Promise.all([...document.querySelectorAll('[data-map-overlay]:checked')].map((input) => (
        mapCore.setOverlayVisible(input.dataset.mapOverlay, true)
    ))).catch((error) => status.setMessage(`Map overlay unavailable: ${error.message}`, 'error'));

    // ── Startup: catalog first, then optional auto-load ─────────────────────
    status.setMessage(SELECT_PRODUCT_MESSAGE);
    try {
        const catalog = await engine.loadCatalog();
        catalogGroups = new Map((catalog?.groups || []).map((g) => [g.group, g]));
        populateCatalogLists();
    } catch (error) {
        console.error('[wpc] catalog load failed', error);
        status.setMessage(`WPC catalog unavailable: ${error.message}`, 'error');
    }
    if (settings.autoLoad) reload();

    window.addEventListener('beforeunload', () => {
        sidebarTabs.destroy();
        legend.destroy();
        detail.destroy();
        scrubber?.destroy();
        engine.destroy();
        mapCore.destroy();
    }, { once: true });
}

initialize().catch((error) => {
    console.error('[wpc] startup failed', error);
    const message = byId('wpc-message');
    if (message) message.textContent = `Startup failed: ${error.message}`;
});
