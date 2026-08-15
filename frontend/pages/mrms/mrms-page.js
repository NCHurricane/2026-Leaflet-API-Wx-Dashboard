import * as api from '../../core/api.js';
import { createLegendHost } from '../../core/legend.js';
import { createMapCore, REGION_LABELS } from '../../core/map-core.js';
import { renderProductNav } from '../../core/nav.js';
import { startNonWorkspaceAlertMonitor } from '../../core/non-workspace-alert-monitor.js?v=20260814a';
import { createScrubber } from '../../core/scrubber.js';
import { createSidebarTabs } from '../../core/sidebar-tabs.js';
import { loadDefaultSettings, loadPageSettings } from '../../core/settings.js';
import { createStatusReporter } from '../../core/status.js?v=20260808a';
import { createMrmsEngine, formatValidTimeLabel, timestampMs } from './mrms-engine.js?v=20260804b';

const byId = (id) => document.getElementById(id);
const SELECT_PRODUCT_MESSAGE = 'Pick an MRMS product to load frames from the rolling cache.';
const AUTO_UPDATE_INTERVAL_MS = 90_000; // matches the shell's MRMS auto-refresh cadence
const HISTORY_POLL_INTERVAL_MS = 5_000;
const FRAME_CAP = 400;

const SUBTAB_BY_PRODUCT = Object.freeze({
    PrecipFlag: 'precip',
    PrecipRate: 'precip',
    QPE: 'precip',
    Reflectivity: 'reflectivity',
    EchoTop: 'reflectivity',
    VIL: 'reflectivity',
    RotationTrack: 'storm',
    AzShear: 'storm',
    MESH: 'hail',
    SHI: 'hail',
    POSH: 'hail',
    Lightning: 'hail',
    Model: 'environment',
    RadarQualityIndex: 'environment',
});

const SUB_PANEL_BY_PRODUCT = Object.freeze({
    QPE: 'mrms-sub-qpe',
    RotationTrack: 'mrms-sub-rotation',
    MESH: 'mrms-sub-mesh',
    AzShear: 'mrms-sub-azshear',
    EchoTop: 'mrms-sub-echotop',
    VIL: 'mrms-sub-vil',
    Reflectivity: 'mrms-sub-reflectivity',
    Lightning: 'mrms-sub-lightning',
    Model: 'mrms-sub-model',
});

function activeProductFamily() {
    return document.querySelector('.mrms-product-check:checked')?.value || null;
}

function radioValue(name, fallback) {
    return document.querySelector(`input[name="${name}"]:checked`)?.value || fallback;
}

// Composed worker product key — ported unchanged from the shell controller.
function composeProductKey() {
    const family = activeProductFamily();
    if (!family) return null;
    const standalone = ['PrecipRate', 'PrecipFlag', 'SHI', 'POSH', 'RadarQualityIndex'];
    if (standalone.includes(family)) return family;

    if (family === 'QPE') {
        return `QPE_${radioValue('mrms-qpe-source', 'MS2')}_${radioValue('mrms-qpe-period', '01H')}`;
    }
    if (family === 'RotationTrack') {
        return `RotationTrack_${radioValue('mrms-rotation-level', 'LL')}_${radioValue('mrms-rotation-time', '60min')}`;
    }
    if (family === 'MESH') {
        const t = radioValue('mrms-mesh-time', 'Instant');
        return t === 'Instant' ? 'MESH_Instant' : `MESH_${t}`;
    }
    if (family === 'AzShear') return `AzShear_${radioValue('mrms-azshear-level', 'Low')}`;
    if (family === 'EchoTop') return `EchoTop_${radioValue('mrms-echotop-threshold', '18')}`;
    if (family === 'VIL') return `VIL_${radioValue('mrms-vil-type', 'Instant')}`;
    if (family === 'Reflectivity') return `Refl_${radioValue('mrms-refl-variant', 'HSR')}`;
    if (family === 'Lightning') return `Lightning_${radioValue('mrms-lightning-window', '30min')}`;
    if (family === 'Model') return `Model_${radioValue('mrms-model-field', 'FreezingLevel')}`;
    return family;
}

function lookbackHours() {
    const slider = byId('mrms-lookback');
    return Math.max(1, Math.round(slider ? Number(slider.value) : 1));
}

function setSubtab(tabKey) {
    const buttons = Array.from(document.querySelectorAll('.mrms-subtab-button'));
    const panels = Array.from(document.querySelectorAll('.mrms-subtab-panel'));
    const selectedKey = buttons.some((button) => button.dataset.mrmsSubtab === tabKey)
        ? tabKey
        : 'precip';
    buttons.forEach((button) => {
        const isSelected = button.dataset.mrmsSubtab === selectedKey;
        button.setAttribute('aria-selected', isSelected ? 'true' : 'false');
        button.tabIndex = isSelected ? 0 : -1;
    });
    panels.forEach((panel) => {
        panel.classList.toggle('is-active', panel.dataset.mrmsPanel === selectedKey);
    });
}

function updateSubControls() {
    const family = activeProductFamily();
    const opacityBlock = byId('mrms-opacity-block');
    if (opacityBlock) opacityBlock.hidden = !family;
    document.querySelectorAll('.mrms-sub-panel').forEach((element) => {
        element.style.display = 'none';
    });
    if (!family) return;
    setSubtab(SUBTAB_BY_PRODUCT[family] || 'precip');
    const subPanel = byId(SUB_PANEL_BY_PRODUCT[family]);
    if (subPanel) subPanel.style.display = '';
}

async function initialize() {
    renderProductNav(byId('product-nav'), 'MRMS');
    startNonWorkspaceAlertMonitor();
    const sidebarTabs = createSidebarTabs(byId('mrms-sidebar-tabs'), { defaultTab: 'live' });
    const settings = await loadPageSettings('mrms', { mapView: 'CONUS' });
    const defaults = await loadDefaultSettings().catch(() => ({}));
    const cityDefaults = defaults?.global?.cityLabels || {};
    const regionSelect = byId('mrms-region');
    regionSelect.replaceChildren(...Object.entries(REGION_LABELS).map(([code, label]) => {
        const option = document.createElement('option');
        option.value = code;
        option.textContent = label;
        return option;
    }));
    regionSelect.value = REGION_LABELS[settings.mapView] ? settings.mapView : 'CONUS';

    const mapCore = createMapCore(byId('mrms-map'), {
        region: regionSelect.value,
        basemap: 'Dark',
    });
    const legend = createLegendHost(byId('mrms-legend'), { align: 'left' });
    const status = createStatusReporter({
        globalTimestamp: byId('global-timestamp'),
        message: byId('mrms-message'),
        updated: byId('mrms-updated'),
        age: byId('mrms-age'),
        provider: byId('mrms-provider'),
    });
    const engine = createMrmsEngine({ api, mapCore, legend, status });

    // ── Frame scrubber ──────────────────────────────────────────────────────
    let frames = [];
    let loadToken = 0;
    let historyPollTimer = null;

    function frameLabel(frame) {
        return formatValidTimeLabel(timestampMs(frame.timestamp));
    }

    const scrubberBar = byId('mrms-scrubber-bar');
    const scrubber = createScrubber(byId('mrms-bottom-scrubber'), {
        holdAtEnd: true,
        onFrame(frame, index) {
            void engine.renderFrame(frame).then(() => {
                engine.prefetchFrames(frames, index);
            });
        },
    });

    function showScrubber(visible) {
        scrubberBar.hidden = !visible;
    }

    async function reloadFrames() {
        const product = composeProductKey();
        const token = ++loadToken;
        clearTimeout(historyPollTimer);
        historyPollTimer = null;
        if (!product) {
            scrubber.setFrames([], { silent: true });
            showScrubber(false);
            engine.clear();
            status.setMessage(SELECT_PRODUCT_MESSAGE);
            return;
        }

        const hours = lookbackHours();
        status.setMessage(`Loading MRMS ${product} frames…`);
        status.setDataState('Loading newest frame…', 'loading');
        try {
            const batch = await engine.loadFrames(product, hours);
            if (token !== loadToken || batch === null) return;
            const loaded = batch.frames;

            if (!loaded.length) {
                frames = [];
                scrubber.setFrames([], { silent: true });
                showScrubber(false);
                status.setMessage(`No ${product} animation frames cached; loading current overlay…`);
                status.setDataState('Loading current frame…', 'loading');
                const latest = await engine.loadLatest(product);
                if (token !== loadToken || !latest) return;
                const staleNote = latest.stale ? ' — cached data may be stale.' : '';
                status.setMessage(
                    `${latest.data.full_name || product} valid ${formatValidTimeLabel(latest.tsMs)}.${staleNote}`,
                    staleNote ? 'error' : 'success',
                );
                status.setDataState(latest.stale ? 'Stale data' : 'Ready', latest.stale ? 'stale' : 'fresh');
                if (batch.refreshing) scheduleHistoryPoll(token);
                return;
            }

            frames = loaded
                .map((frame) => ({ ...frame, label: frameLabel(frame) }))
                .sort((left, right) => timestampMs(left.timestamp) - timestampMs(right.timestamp));
            showScrubber(true);
            scrubber.setFrames(frames, { index: frames.length - 1 });
            status.setMessage(
                batch.refreshing
                    ? `${frames.length} MRMS frames available; filling the ${hours}h window…`
                    : `${frames.length} MRMS frames from cache (${hours}h window).`,
                batch.refreshing ? '' : 'success',
            );
            status.setDataState(batch.refreshing ? 'Loading history…' : 'Ready', batch.refreshing ? 'loading' : 'fresh');
            if (batch.refreshing) scheduleHistoryPoll(token);
        } catch (err) {
            if (token !== loadToken) return;
            console.error('[mrms] frame load failed', err);
            showScrubber(false);
            status.setMessage(`MRMS load failed: ${err.message}`, 'error');
            status.setDataState('Load failed', 'error');
        }
    }

    // ── Auto-update: append newly cached frames without restarting playback ──
    let autoUpdateTimer = null;

    async function autoUpdateTick({ force = false, token = loadToken } = {}) {
        if (!force && !byId('mrms-auto-update')?.checked) return false;
        if (token !== loadToken) return false;
        const product = composeProductKey();
        if (!product || (frames.length && frames[0].product !== product)) return false;
        try {
            const batch = await engine.fetchNewFrames(product, lookbackHours(), frames);
            if (token !== loadToken) return false;
            const fresh = batch.frames;
            if (!fresh.length) return batch.refreshing;
            const currentIndex = scrubber.getIndex();
            const wasAtNewest = currentIndex === frames.length - 1;
            const currentTimestamp = frames[currentIndex]?.timestamp;
            const byTimestamp = new Map(
                [...frames, ...fresh.map((frame) => ({ ...frame, label: frameLabel(frame) }))]
                    .map((frame) => [frame.timestamp, frame]),
            );
            const combined = [...byTimestamp.values()].sort(
                (left, right) => timestampMs(left.timestamp) - timestampMs(right.timestamp),
            );
            const dropped = Math.max(0, combined.length - FRAME_CAP);
            frames = combined.slice(dropped);
            const preservedIndex = currentTimestamp
                ? frames.findIndex((frame) => frame.timestamp === currentTimestamp)
                : -1;
            const index = wasAtNewest
                ? frames.length - 1
                : (preservedIndex >= 0 ? preservedIndex : frames.length - 1);
            showScrubber(true);
            scrubber.setFrames(frames, { index, silent: true, keepPlaying: true });
            if (force) {
                status.setMessage(
                    batch.refreshing
                        ? `${frames.length} MRMS frames available; filling history…`
                        : `${frames.length} MRMS frames loaded for the requested window.`,
                    batch.refreshing ? '' : 'success',
                );
            }
            status.setDataState(batch.refreshing ? 'Loading history…' : 'Ready', batch.refreshing ? 'loading' : 'fresh');
            return batch.refreshing;
        } catch (_) {
            return false;
        }
    }

    function scheduleHistoryPoll(token) {
        clearTimeout(historyPollTimer);
        historyPollTimer = setTimeout(async () => {
            historyPollTimer = null;
            const refreshing = await autoUpdateTick({ force: true, token });
            if (refreshing && token === loadToken) scheduleHistoryPoll(token);
        }, HISTORY_POLL_INTERVAL_MS);
    }

    autoUpdateTimer = setInterval(() => { void autoUpdateTick(); }, AUTO_UPDATE_INTERVAL_MS);

    // ── Product checkboxes (mutually exclusive) + sub-option radios ─────────
    document.querySelectorAll('.mrms-product-check').forEach((checkbox) => {
        checkbox.addEventListener('change', () => {
            if (checkbox.checked) {
                document.querySelectorAll('.mrms-product-check').forEach((other) => {
                    if (other !== checkbox) other.checked = false;
                });
            }
            updateSubControls();
            void reloadFrames();
        });
    });

    [
        'mrms-qpe-source', 'mrms-qpe-period',
        'mrms-rotation-level', 'mrms-rotation-time',
        'mrms-mesh-time',
        'mrms-azshear-level',
        'mrms-echotop-threshold',
        'mrms-vil-type',
        'mrms-refl-variant',
        'mrms-lightning-window',
        'mrms-model-field',
    ].forEach((name) => {
        document.querySelectorAll(`input[name="${name}"]`).forEach((input) => {
            input.addEventListener('change', () => {
                if (activeProductFamily()) void reloadFrames();
            });
        });
    });

    // ── Sub-tab buttons (navigation only) ───────────────────────────────────
    const subtabButtons = Array.from(document.querySelectorAll('.mrms-subtab-button'));
    subtabButtons.forEach((button, index) => {
        button.addEventListener('click', () => {
            setSubtab(button.dataset.mrmsSubtab || 'precip');
        });
        button.addEventListener('keydown', (event) => {
            if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
            event.preventDefault();
            let nextIndex = index;
            if (event.key === 'ArrowLeft') nextIndex = index === 0 ? subtabButtons.length - 1 : index - 1;
            if (event.key === 'ArrowRight') nextIndex = index === subtabButtons.length - 1 ? 0 : index + 1;
            if (event.key === 'Home') nextIndex = 0;
            if (event.key === 'End') nextIndex = subtabButtons.length - 1;
            const nextButton = subtabButtons[nextIndex];
            if (!nextButton) return;
            setSubtab(nextButton.dataset.mrmsSubtab || 'precip');
            nextButton.focus();
        });
    });

    // ── Lookback slider ─────────────────────────────────────────────────────
    const lookbackSlider = byId('mrms-lookback');
    lookbackSlider.addEventListener('input', () => {
        byId('mrms-lookback-value').textContent = `${Number(lookbackSlider.value)}H`;
    });
    lookbackSlider.addEventListener('change', () => {
        if (activeProductFamily()) void reloadFrames();
    });

    // ── Style controls ──────────────────────────────────────────────────────
    const opacityInput = byId('mrms-opacity');
    function updateOpacityLabel() {
        const value = Number(opacityInput.value);
        const label = document.querySelector('label[for="mrms-opacity"]');
        if (label) label.textContent = `Overlay Opacity (${value.toFixed(2).replace(/\.?0+$/, '') || '0'})`;
    }
    opacityInput.addEventListener('input', () => {
        updateOpacityLabel();
        engine.setOpacity(opacityInput.value);
    });
    engine.setOpacity(opacityInput.value);
    byId('mrms-basemap').addEventListener('change', (event) => mapCore.setBasemap(event.target.value));

    // ── Region / refresh ────────────────────────────────────────────────────
    regionSelect.addEventListener('change', () => mapCore.fitRegion(regionSelect.value));
    byId('mrms-refresh').addEventListener('click', () => void reloadFrames());

    // ── Cities ──────────────────────────────────────────────────────────────
    const citySource = ['us', 'world'].includes(cityDefaults.source) ? cityDefaults.source : 'off';
    const cityDensity = Number(cityDefaults.density);
    const cityFontSize = Number(cityDefaults.fontSize);
    const cityDensityInput = byId('mrms-city-density');
    const cityFontSizeInput = byId('mrms-city-font-size');
    cityDensityInput.value = String(cityDensity >= 0.01 && cityDensity <= 1 ? cityDensity : 0.25);
    cityFontSizeInput.value = String(cityFontSize >= 0.4 && cityFontSize <= 1.2 ? cityFontSize : 0.6);
    const initialCitySourceInput = document.querySelector(`input[name="mrms-cities-source"][value="${citySource}"]`);
    if (initialCitySourceInput) initialCitySourceInput.checked = true;

    function selectedCitySource() {
        return document.querySelector('input[name="mrms-cities-source"]:checked')?.value || 'off';
    }

    function updateCityControlLabels() {
        const source = selectedCitySource();
        const disabled = source === 'off';
        document.querySelectorAll('[data-city-adjustment]').forEach((row) => {
            row.classList.toggle('is-disabled', disabled);
            row.querySelector('input').disabled = disabled;
        });
        const distanceKm = Math.round(mapCore.getCityMinDistanceKm(source, cityDensityInput.value));
        byId('mrms-city-density-label').textContent = `City Density (${distanceKm} km)`;
        const fontSizeLabel = Number(cityFontSizeInput.value).toFixed(2).replace(/\.?0+$/, '');
        byId('mrms-city-font-size-label').textContent = `City Font Size (${fontSizeLabel})`;
    }

    document.querySelectorAll('input[name="mrms-cities-source"]').forEach((input) => {
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

    // ── Startup ─────────────────────────────────────────────────────────────
    updateSubControls();
    status.setMessage(SELECT_PRODUCT_MESSAGE);

    window.addEventListener('beforeunload', () => {
        clearInterval(autoUpdateTimer);
        clearTimeout(historyPollTimer);
        sidebarTabs.destroy();
        legend.destroy();
        scrubber.destroy();
        engine.destroy();
        mapCore.destroy();
    }, { once: true });
}

initialize().catch((error) => {
    console.error('[mrms] startup failed', error);
    const message = byId('mrms-message');
    if (message) message.textContent = `Startup failed: ${error.message}`;
});
