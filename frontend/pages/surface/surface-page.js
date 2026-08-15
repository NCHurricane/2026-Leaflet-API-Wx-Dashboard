import * as api from '../../core/api.js';
import { createLegendHost } from '../../core/legend.js';
import { createMapCore, REGION_LABELS } from '../../core/map-core.js';
import { renderProductNav } from '../../core/nav.js';
import { startNonWorkspaceAlertMonitor } from '../../core/non-workspace-alert-monitor.js?v=20260814a';
import { createScrubber } from '../../core/scrubber.js';
import { createSidebarTabs } from '../../core/sidebar-tabs.js';
import { loadDefaultSettings, loadPageSettings } from '../../core/settings.js';
import { createStatusReporter } from '../../core/status.js?v=20260808a';
import { createSurfaceEngine } from './surface-engine.js?v=20260808c';
import { baseDistKm, createSurfaceRenderer } from './surface-render.js?v=20260808a';

const byId = (id) => document.getElementById(id);
const SELECT_PRODUCT_MESSAGE = 'Select a surface product to load observations.';

function populateRegions(select) {
    select.replaceChildren(...Object.entries(REGION_LABELS).map(([code, label]) => {
        const option = document.createElement('option');
        option.value = code;
        option.textContent = label;
        return option;
    }));
}

function activeProduct() {
    return document.querySelector('[data-surface-product]:checked')?.value || null;
}

function gradientChecked(product) {
    if (!product) return false;
    return !!document.querySelector(`[data-surface-gradient][data-product="${product}"]`)?.checked;
}

function selectedNetworks() {
    return new Set([...document.querySelectorAll('[data-surface-network]:checked')]
        .map((input) => input.value));
}

async function initialize() {
    renderProductNav(byId('product-nav'), 'Current');
    startNonWorkspaceAlertMonitor();
    const sidebarTabs = createSidebarTabs(byId('surface-sidebar-tabs'), { defaultTab: 'live' });
    const settings = await loadPageSettings('surface', { mapView: 'CONUS', autoLoad: false });
    const defaults = await loadDefaultSettings().catch(() => ({}));
    const cityDefaults = defaults?.global?.cityLabels || {};
    const regionSelect = byId('surface-region');
    populateRegions(regionSelect);
    regionSelect.value = REGION_LABELS[settings.mapView] ? settings.mapView : 'CONUS';

    const mapCore = createMapCore(byId('surface-map'), {
        region: regionSelect.value,
        basemap: 'Dark',
    });
    const legend = createLegendHost(byId('surface-legend'), { align: 'left' });
    const status = createStatusReporter({
        globalTimestamp: byId('global-timestamp'),
        message: byId('surface-message'),
        updated: byId('surface-updated'),
        age: byId('surface-age'),
        provider: byId('surface-provider'),
    });
    const renderer = createSurfaceRenderer(mapCore);
    const historyGate = api.createRequestGate();
    let currentLiveFrame = null;
    const engine = createSurfaceEngine({
        api,
        renderer,
        legend,
        status,
        onStationCount: (count) => { byId('surface-station-count').textContent = String(count); },
        onLiveFrame: (frame) => {
            currentLiveFrame = frame;
            void loadRecentHistory();
        },
    });
    const scrubberBar = byId('surface-scrubber-bar');
    const scrubber = createScrubber(byId('surface-bottom-scrubber'), {
        holdAtEnd: true,
        onFrame(frame) {
            engine.renderRecentFrame(frame, viewOptions());
        },
    });

    const viewOptions = () => ({
        region: regionSelect.value,
        product: activeProduct(),
        gradientEnabled: gradientChecked(activeProduct()),
        networks: selectedNetworks(),
        density: Number(byId('surface-density').value),
        valueOpacity: Number(byId('surface-value-opacity').value),
        gradientOpacity: Number(byId('surface-gradient-opacity').value),
    });

    function updateDensityLabel() {
        const density = Math.max(0.01, Math.min(1, Number(byId('surface-density').value) || 0.25));
        const distKm = Math.round(baseDistKm(mapCore.map.getZoom(), regionSelect.value) / density);
        byId('surface-density-label').textContent = `Station Density (${distKm} km)`;
    }

    function updateSliderLabel(inputId, baseLabel) {
        const value = Number(byId(inputId).value);
        const label = document.querySelector(`label[for="${inputId}"]`);
        if (label) label.textContent = `${baseLabel} (${value.toFixed(2).replace(/\.?0+$/, '') || '0'})`;
    }

    function formatLookback(hours) {
        const minutes = Math.round(Number(hours) * 60);
        const wholeHours = Math.floor(minutes / 60);
        const remainder = minutes % 60;
        if (!wholeHours) return `${remainder} min`;
        return remainder ? `${wholeHours}h ${remainder}m` : `${wholeHours} hour${wholeHours === 1 ? '' : 's'}`;
    }

    function frameLabel(frame) {
        const date = new Date(frame?.timestamp || '');
        return Number.isFinite(date.getTime())
            ? date.toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
            : '—';
    }

    function recentWindow(hours) {
        const end = new Date();
        end.setUTCMinutes(Math.floor(end.getUTCMinutes() / 15) * 15, 0, 0);
        return {
            start: new Date(end.getTime() - hours * 60 * 60 * 1000),
            end,
        };
    }

    function updateGradientControlState() {
        const enabled = gradientChecked(activeProduct());
        document.querySelectorAll('[data-gradient-adjustment]').forEach((row) => {
            row.classList.toggle('is-disabled', !enabled);
            row.querySelector('input').disabled = !enabled;
        });
    }

    // Networks apply to state regions only; CONUS/WORLD feeds are ASOS-scale
    // and the combined shell hid the filters there — keep that behavior.
    function updateNetworkVisibility() {
        const region = String(regionSelect.value || '').toUpperCase();
        byId('surface-networks-wrap').hidden = region === 'CONUS' || region === 'WORLD';
    }

    function clearRecentHistory() {
        historyGate.cancel();
        scrubber.pause();
        scrubber.setFrames([], { silent: true });
        scrubberBar.hidden = true;
    }

    async function loadRecentHistory() {
        const view = viewOptions();
        if (!view.product || !currentLiveFrame) {
            clearRecentHistory();
            return;
        }

        clearRecentHistory();
        if (Array.isArray(currentLiveFrame.stations) && currentLiveFrame.stations.length) {
            engine.renderRecentFrame({ ...currentLiveFrame, is_live: true }, view);
        }
        const request = historyGate.begin();
        const hours = Number(byId('surface-lookback').value);
        const { start, end } = recentWindow(hours);
        const maxFrames = Math.min(120, Math.floor(hours * 4) + 1);
        try {
            const data = await api.fetchJson(`/api/archive/surface?region=${encodeURIComponent(view.region)}`
                + `&product=${encodeURIComponent(view.product)}&date_from=${encodeURIComponent(start.toISOString())}`
                + `&date_to=${encodeURIComponent(end.toISOString())}&max_frames=${maxFrames}`, {
                cache: 'no-store',
                signal: request.signal,
            });
            if (!historyGate.isCurrent(request.sequence)) return;

            const liveTimestamp = Date.parse(currentLiveFrame.timestamp || '');
            const recentFrames = (Array.isArray(data?.frames) ? data.frames : [])
                .filter((frame) => Array.isArray(frame?.stations) && frame.stations.length)
                .filter((frame) => {
                    const timestamp = Date.parse(frame?.timestamp || '');
                    return !Number.isFinite(liveTimestamp) || !Number.isFinite(timestamp) || timestamp < liveTimestamp;
                })
                .map((frame) => ({ ...frame, label: frameLabel(frame) }));
            const liveTimestampValue = currentLiveFrame.timestamp || new Date().toISOString();
            const liveFrame = {
                ...currentLiveFrame,
                timestamp: liveTimestampValue,
                label: frameLabel({ timestamp: liveTimestampValue }),
                is_live: true,
            };
            const hasLiveStations = Array.isArray(liveFrame.stations) && liveFrame.stations.length > 0;
            const frames = hasLiveStations ? [...recentFrames, liveFrame] : recentFrames;
            scrubber.setFrames(frames, { index: Math.max(0, frames.length - 1) });
            scrubberBar.hidden = frames.length < 2;
        } catch (error) {
            if (error.name === 'AbortError' || !historyGate.isCurrent(request.sequence)) return;
            console.warn('[surface] recent history unavailable', error);
            scrubberBar.hidden = true;
            status.setMessage(`Current Surface data shown; recent history unavailable: ${error.message}`, 'error');
        }
    }

    async function loadActive(options = {}) {
        const view = viewOptions();
        if (!view.product) {
            currentLiveFrame = null;
            clearRecentHistory();
            engine.clear();
            status.setMessage(SELECT_PRODUCT_MESSAGE);
            return;
        }
        currentLiveFrame = null;
        clearRecentHistory();
        try {
            await engine.load(view, options);
        } catch (error) {
            console.error('[surface] load failed', error);
        }
    }

    // ── Product + gradient wiring ────────────────────────────────────────────
    document.querySelectorAll('[data-surface-product]').forEach((input) => {
        input.addEventListener('change', () => {
            if (input.checked) {
                document.querySelectorAll('[data-surface-product]').forEach((other) => {
                    if (other !== input) {
                        other.checked = false;
                        const grad = document.querySelector(`[data-surface-gradient][data-product="${other.value}"]`);
                        if (grad) grad.checked = false;
                    }
                });
                const activeGrad = document.querySelector(`[data-surface-gradient][data-product="${input.value}"]`);
                if (activeGrad) activeGrad.checked = true;
            } else {
                const grad = document.querySelector(`[data-surface-gradient][data-product="${input.value}"]`);
                if (grad) grad.checked = false;
            }
            updateGradientControlState();
            void loadActive();
        });
    });

    document.querySelectorAll('[data-surface-gradient]').forEach((input) => {
        input.addEventListener('change', () => {
            updateGradientControlState();
            void engine.applyGradient(viewOptions());
        });
    });

    // ── Data controls ────────────────────────────────────────────────────────
    document.querySelectorAll('[data-surface-network]').forEach((input) => {
        input.addEventListener('change', () => engine.rerender(viewOptions()));
    });
    byId('surface-density').addEventListener('input', () => {
        updateDensityLabel();
        engine.rerender(viewOptions());
    });

    // ── Style controls ───────────────────────────────────────────────────────
    byId('surface-value-opacity').addEventListener('input', () => {
        updateSliderLabel('surface-value-opacity', 'Value Opacity');
        engine.rerender(viewOptions());
    });
    byId('surface-gradient-opacity').addEventListener('input', () => {
        updateSliderLabel('surface-gradient-opacity', 'Gradient Opacity');
        engine.rerender(viewOptions());
    });
    byId('surface-basemap').addEventListener('change', (event) => mapCore.setBasemap(event.target.value));

    // ── Region / refresh ─────────────────────────────────────────────────────
    byId('surface-region').addEventListener('change', () => {
        mapCore.fitRegion(regionSelect.value);
        updateNetworkVisibility();
        updateDensityLabel();
        if (activeProduct()) void loadActive();
    });
    byId('surface-refresh').addEventListener('click', () => void loadActive({ forceRefresh: true }));

    const lookback = byId('surface-lookback');
    lookback.addEventListener('input', () => {
        byId('surface-lookback-value').textContent = formatLookback(lookback.value);
    });
    lookback.addEventListener('change', () => {
        if (activeProduct() && currentLiveFrame) void loadRecentHistory();
    });

    // ── Cities ───────────────────────────────────────────────────────────────
    const citySource = ['us', 'world'].includes(cityDefaults.source) ? cityDefaults.source : 'off';
    const cityDensity = Number(cityDefaults.density);
    const cityFontSize = Number(cityDefaults.fontSize);
    const cityDensityInput = byId('surface-city-density');
    const cityFontSizeInput = byId('surface-city-font-size');
    cityDensityInput.value = String(cityDensity >= 0.01 && cityDensity <= 1 ? cityDensity : 0.25);
    cityFontSizeInput.value = String(cityFontSize >= 0.4 && cityFontSize <= 1.2 ? cityFontSize : 0.6);
    const initialCitySourceInput = document.querySelector(`input[name="surface-cities-source"][value="${citySource}"]`);
    if (initialCitySourceInput) initialCitySourceInput.checked = true;

    function selectedCitySource() {
        return document.querySelector('input[name="surface-cities-source"]:checked')?.value || 'off';
    }

    function updateCityControlLabels() {
        const source = selectedCitySource();
        const disabled = source === 'off';
        document.querySelectorAll('[data-city-adjustment]').forEach((row) => {
            row.classList.toggle('is-disabled', disabled);
            row.querySelector('input').disabled = disabled;
        });
        const distanceKm = Math.round(mapCore.getCityMinDistanceKm(source, cityDensityInput.value));
        byId('surface-city-density-label').textContent = `City Density (${distanceKm} km)`;
        const fontSizeLabel = Number(cityFontSizeInput.value).toFixed(2).replace(/\.?0+$/, '');
        byId('surface-city-font-size-label').textContent = `City Font Size (${fontSizeLabel})`;
    }

    document.querySelectorAll('input[name="surface-cities-source"]').forEach((input) => {
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

    // ── Map overlays ─────────────────────────────────────────────────────────
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

    // ── Zoom-dependent re-thinning and labels ────────────────────────────────
    const onZoomEnd = () => {
        updateDensityLabel();
        updateCityControlLabels();
        engine.rerender(viewOptions());
    };
    mapCore.map.on('zoomend', onZoomEnd);

    updateNetworkVisibility();
    updateDensityLabel();
    updateGradientControlState();
    status.setMessage(SELECT_PRODUCT_MESSAGE);
    if (settings.autoLoad && activeProduct()) await loadActive();

    window.addEventListener('beforeunload', () => {
        sidebarTabs.destroy();
        legend.destroy();
        mapCore.map.off('zoomend', onZoomEnd);
        historyGate.cancel();
        engine.destroy();
        scrubber.destroy();
        mapCore.destroy();
    }, { once: true });
}

initialize().catch((error) => {
    console.error('[surface] startup failed', error);
    const message = byId('surface-message');
    if (message) message.textContent = `Startup failed: ${error.message}`;
});
