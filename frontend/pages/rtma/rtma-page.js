import * as api from '../../core/api.js';
import { createLegendHost } from '../../core/legend.js';
import { createMapCore, REGION_LABELS } from '../../core/map-core.js?v=20260826g';
import { renderProductNav } from '../../core/nav.js?v=20260826a';
import { startNonWorkspaceAlertMonitor } from '../../core/non-workspace-alert-monitor.js?v=20260824a';
import { createScrubber } from '../../core/scrubber.js';
import { createSidebarTabs } from '../../core/sidebar-tabs.js';
import { loadDefaultSettings, loadPageSettings } from '../../core/settings.js';
import { createStatusReporter } from '../../core/status.js?v=20260808a';
import {
    STREAM_MAX_HOURS,
    baseDistKm,
    createRtmaEngine,
    dataRegionForMapRegion,
    formatValidTimeLabel,
    timestampMs,
} from './rtma-engine.js';

const byId = (id) => document.getElementById(id);
const SELECT_MESSAGE = 'Pick a data stream and a product to load the latest analysis and frames.';
const AUTO_UPDATE_INTERVAL_MS = 90_000;
const HISTORY_POLL_INTERVAL_MS = 5_000;
const FRAME_CAP = 150;
const POINTS_MOVE_DEBOUNCE_MS = 180;

function activeStream() {
    return document.querySelector('.rtma-stream:checked')?.value || null;
}

function activeProduct() {
    return document.querySelector('.rtma-product:checked')?.value || null;
}

function activeProducts() {
    return Array.from(document.querySelectorAll('.rtma-product:checked')).map((el) => el.value);
}

function windProductPair() {
    const windProds = activeProducts().filter((p) => p === 'wind_speed' || p === 'wind_direction');
    return windProds.length === 2 ? windProds : [];
}

function lookbackHours(stream) {
    const streamMax = STREAM_MAX_HOURS[stream] || 24;
    const slider = byId('rtma-lookback');
    const value = slider ? Number(slider.value) : streamMax;
    // Integer hours only — the backend rejects fractional hours with 422.
    return Math.max(1, Math.min(Math.round(value), streamMax));
}

async function initialize() {
    renderProductNav(byId('product-nav'), 'RTMA');
    startNonWorkspaceAlertMonitor();
    const sidebarTabs = createSidebarTabs(byId('rtma-sidebar-tabs'), { defaultTab: 'live' });
    const settings = await loadPageSettings('rtma', { mapView: 'CONUS' });
    const defaults = await loadDefaultSettings().catch(() => ({}));
    const cityDefaults = defaults?.global?.cityLabels || {};
    const regionSelect = byId('rtma-region');
    regionSelect.replaceChildren(...Object.entries(REGION_LABELS).map(([code, label]) => {
        const option = document.createElement('option');
        option.value = code;
        option.textContent = label;
        return option;
    }));
    regionSelect.value = REGION_LABELS[settings.mapView] ? settings.mapView : 'CONUS';

    const mapCore = createMapCore(byId('rtma-map'), {
        region: regionSelect.value,
        basemap: 'Dark',
        boundaryMode: 'conus',
    });
    const legend = createLegendHost(byId('rtma-legend'), { align: 'left' });
    const status = createStatusReporter({
        globalTimestamp: byId('global-timestamp'),
        message: byId('rtma-message'),
        updated: byId('rtma-updated'),
        age: byId('rtma-age'),
        provider: byId('rtma-provider'),
    });
    const engine = createRtmaEngine({ api, mapCore, legend, status });

    function dataRegion() {
        return dataRegionForMapRegion(regionSelect.value);
    }

    function selection() {
        return { region: dataRegion(), stream: activeStream(), product: activeProduct() };
    }

    function hasSelection() {
        return !!activeStream() && !!activeProduct();
    }

    // ── Stream/product availability rules (ported from the shell) ───────────
    function syncProductForStream() {
        const stream = activeStream();
        const hasStream = !!stream;
        let clearedDelta24h = false;
        document.querySelectorAll('.rtma-product').forEach((productEl) => {
            const isDelta24h = productEl.value === 'temperature_change_24h';
            const supported = hasStream && (!isDelta24h || stream === 'rtma_hourly');
            productEl.disabled = !supported;
            if (!supported && productEl.checked) {
                productEl.checked = false;
                if (isDelta24h) clearedDelta24h = true;
            }
            const row = productEl.closest('.rtma-product-row');
            if (row) row.style.opacity = supported ? '' : '0.55';
        });
        if (clearedDelta24h && hasStream && stream !== 'rtma_hourly') {
            status.setMessage('24-hour temp change is only available on RTMA Hourly.');
        }
    }

    function syncStreamForRegion() {
        const rapid = document.querySelector('.rtma-stream[value="rtma_rapid_update"]');
        if (!rapid) return;
        const rapidSupported = dataRegion() === 'CONUS';
        rapid.disabled = !rapidSupported;
        const row = rapid.closest('.rtma-stream-row');
        if (row) row.style.opacity = rapidSupported ? '' : '0.55';
        if (!rapidSupported && rapid.checked) {
            rapid.checked = false;
            status.setMessage('RTMA Rapid Update is only available for CONUS.');
        }
    }

    // ── Frame scrubber ──────────────────────────────────────────────────────
    let frames = [];
    let loadToken = 0;
    let historyPollTimer = null;
    const frameErrors = new Set();

    function frameLabel(frame) {
        return formatValidTimeLabel(timestampMs(frame.timestamp));
    }

    const scrubberBar = byId('rtma-scrubber-bar');
    const scrubber = createScrubber(byId('rtma-bottom-scrubber'), {
        holdAtEnd: true,
        onFrame(frame, index) {
            void engine.renderFrame(frame).then(() => {
                engine.prefetchFrames(frames, index);
            }).catch(() => {
                // Auto-skip to the next frame that has not already errored.
                frameErrors.add(frame.source_data_key || frame.frame_key || String(index));
                const nextIndex = frames.findIndex((f, i) => (
                    i > index && !frameErrors.has(f.source_data_key || f.frame_key || String(i))
                ));
                if (nextIndex !== -1) {
                    status.setMessage('Frame unavailable, skipping…');
                    scrubber.goTo(nextIndex);
                } else {
                    status.setMessage('Frame unavailable.', 'error');
                }
            });
        },
    });

    function showScrubber(visible) {
        scrubberBar.hidden = !visible;
    }

    async function loadUnified() {
        const sel = selection();
        const token = ++loadToken;
        clearTimeout(historyPollTimer);
        historyPollTimer = null;
        if (!sel.stream || !sel.product) {
            clearAll();
            return;
        }

        frameErrors.clear();

        // Latest analysis renders immediately; the wind pair adds the second
        // product's markers when both wind_speed + wind_direction are checked.
        await engine.loadLatest(sel);
        if (token !== loadToken) return;
        const pair = windProductPair();
        if (pair.length === 2) {
            const other = pair.find((p) => p !== sel.product);
            if (other) void engine.loadSecondary(sel, other);
        } else {
            engine.clearSecondary();
        }

        const hours = lookbackHours(sel.stream);
        try {
            const batch = await engine.loadFrames(sel, hours);
            if (token !== loadToken || batch === null) return;
            const loaded = batch.frames;
            if (!loaded.length) {
                frames = [];
                scrubber.setFrames([], { silent: true });
                showScrubber(false);
                if (batch.refreshing) scheduleHistoryPoll(token);
                return;
            }
            frames = loaded.map((frame) => ({ ...frame, label: frameLabel(frame) }));
            showScrubber(true);
            // Latest analysis is already on the map; park the scrubber on the
            // newest frame without re-rendering it.
            scrubber.setFrames(frames, { index: frames.length - 1, silent: true });
            if (batch.refreshing) {
                status.setMessage(`${frames.length} RTMA frames available; filling the ${hours}h window…`);
                scheduleHistoryPoll(token);
            }
        } catch (err) {
            if (token !== loadToken) return;
            console.error('[rtma] frame load failed', err);
            showScrubber(false);
        }
    }

    function clearAll() {
        loadToken += 1;
        clearTimeout(historyPollTimer);
        historyPollTimer = null;
        frames = [];
        frameErrors.clear();
        scrubber.setFrames([], { silent: true });
        showScrubber(false);
        engine.clear();
        status.setMessage(SELECT_MESSAGE);
    }

    // ── Auto-update: append newly cached frames ─────────────────────────────
    async function autoUpdateTick({ force = false, token = loadToken } = {}) {
        if (!force && !byId('rtma-auto-update')?.checked) return false;
        if (token !== loadToken) return false;
        const sel = selection();
        if (!sel.stream || !sel.product) return false;
        if (
            frames.length
            && (frames[0].stream !== sel.stream || frames[0].product !== sel.product)
        ) return false;
        try {
            const batch = await engine.fetchNewFrames(sel, lookbackHours(sel.stream), frames);
            if (token !== loadToken) return false;
            const fresh = batch.frames;
            if (!fresh.length) return batch.refreshing;
            const identity = (frame) => `${frame.source_data_key || frame.frame_key || ''}|${frame.timestamp || ''}`;
            const currentIdentity = frames[scrubber.getIndex()]
                ? identity(frames[scrubber.getIndex()])
                : null;
            const byIdentity = new Map(
                [...frames, ...fresh.map((frame) => ({ ...frame, label: frameLabel(frame) }))]
                    .map((frame) => [identity(frame), frame]),
            );
            const combined = [...byIdentity.values()].sort(
                (left, right) => timestampMs(left.timestamp) - timestampMs(right.timestamp),
            );
            const dropped = Math.max(0, combined.length - FRAME_CAP);
            frames = combined.slice(dropped);
            const preservedIndex = currentIdentity
                ? frames.findIndex((frame) => identity(frame) === currentIdentity)
                : -1;
            const index = preservedIndex >= 0 ? preservedIndex : frames.length - 1;
            showScrubber(true);
            scrubber.setFrames(frames, { index, silent: true, keepPlaying: true });
            if (force) {
                status.setMessage(
                    batch.refreshing
                        ? `${frames.length} RTMA frames available; filling history…`
                        : `${frames.length} RTMA frames loaded for the requested window.`,
                    batch.refreshing ? '' : 'success',
                );
            }
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

    const autoUpdateTimer = setInterval(() => { void autoUpdateTick(); }, AUTO_UPDATE_INTERVAL_MS);

    // ── Stream checkboxes (mutually exclusive, uncheckable) ─────────────────
    document.querySelectorAll('.rtma-stream').forEach((el) => {
        el.addEventListener('change', () => {
            if (el.checked) {
                document.querySelectorAll('.rtma-stream').forEach((other) => {
                    if (other !== el) other.checked = false;
                });
            }
            syncProductForStream();
            if (hasSelection()) void loadUnified();
            else clearAll();
        });
    });

    // ── Product checkboxes (exclusive except the wind pair) ─────────────────
    document.querySelectorAll('.rtma-product').forEach((el) => {
        el.addEventListener('change', () => {
            if (el.checked) {
                if (el.value === 'temperature_change_24h' && activeStream() !== 'rtma_hourly') {
                    const hourly = document.querySelector('.rtma-stream[value="rtma_hourly"]');
                    const rapid = document.querySelector('.rtma-stream[value="rtma_rapid_update"]');
                    if (hourly) hourly.checked = true;
                    if (rapid) rapid.checked = false;
                    syncProductForStream();
                }
                const isWindProduct = el.value === 'wind_speed' || el.value === 'wind_direction';
                document.querySelectorAll('.rtma-product').forEach((other) => {
                    if (other !== el) {
                        const otherIsWind = other.value === 'wind_speed' || other.value === 'wind_direction';
                        if (isWindProduct && otherIsWind) return;
                        other.checked = false;
                    }
                });
            }
            if (windProductPair().length < 2) engine.clearSecondary();
            if (hasSelection()) void loadUnified();
            else clearAll();
        });
    });

    // ── Show Values + density ───────────────────────────────────────────────
    function updateDensityLabel() {
        const zoom = mapCore.map?.getZoom() ?? 5;
        const densityValue = Math.max(0.01, Math.min(2, Number(byId('rtma-density').value) || 0.25));
        const distKm = Math.round(baseDistKm(zoom) / densityValue);
        byId('rtma-density-label').textContent = `Station Density (${distKm} km)`;
    }

    byId('rtma-show-values').addEventListener('change', () => {
        engine.setShowValues(byId('rtma-show-values').checked);
        if (byId('rtma-show-values').checked && hasSelection()) {
            if (frames.length) {
                const frame = frames[scrubber.getIndex()];
                if (frame) void engine.renderFrame(frame).catch(() => {});
            } else {
                void engine.reloadPoints(selection());
            }
        }
    });

    byId('rtma-density').addEventListener('input', () => {
        engine.setDensity(byId('rtma-density').value);
        updateDensityLabel();
    });
    engine.setDensity(byId('rtma-density').value);

    // ── Lookback slider ─────────────────────────────────────────────────────
    const lookbackSlider = byId('rtma-lookback');
    lookbackSlider.addEventListener('input', () => {
        byId('rtma-lookback-value').textContent = `${Number(lookbackSlider.value)}H`;
    });
    lookbackSlider.addEventListener('change', () => {
        if (hasSelection()) void loadUnified();
    });

    // ── Viewport changes re-thin / refetch value markers ────────────────────
    let pointsMoveTimer = null;
    mapCore.map.on('moveend', () => {
        if (!byId('rtma-show-values').checked || !hasSelection()) return;
        if (pointsMoveTimer) clearTimeout(pointsMoveTimer);
        pointsMoveTimer = setTimeout(() => {
            pointsMoveTimer = null;
            if (frames.length) {
                const frame = frames[scrubber.getIndex()];
                if (frame) void engine.renderFrame(frame).catch(() => {});
            } else {
                void engine.reloadPoints(selection());
            }
        }, POINTS_MOVE_DEBOUNCE_MS);
    });
    mapCore.map.on('zoomend', () => {
        updateDensityLabel();
        engine.renderPoints();
    });

    // ── Style controls ──────────────────────────────────────────────────────
    const opacityInput = byId('rtma-gradient-opacity');
    function updateOpacityLabel() {
        const value = Number(opacityInput.value);
        const label = document.querySelector('label[for="rtma-gradient-opacity"]');
        if (label) label.textContent = `Overlay Opacity (${value.toFixed(2).replace(/\.?0+$/, '') || '0'})`;
    }
    opacityInput.addEventListener('input', () => {
        updateOpacityLabel();
        engine.setGradientOpacity(opacityInput.value);
    });
    engine.setGradientOpacity(opacityInput.value);
    byId('rtma-basemap').addEventListener('change', (event) => mapCore.setBasemap(event.target.value));

    // ── Region / refresh ────────────────────────────────────────────────────
    regionSelect.addEventListener('change', () => {
        mapCore.fitRegion(regionSelect.value);
        syncStreamForRegion();
        if (hasSelection()) void loadUnified();
    });
    byId('rtma-refresh').addEventListener('click', () => {
        if (hasSelection()) void loadUnified();
        else status.setMessage(SELECT_MESSAGE);
    });

    // ── Cities ──────────────────────────────────────────────────────────────
    const citySource = ['us', 'world'].includes(cityDefaults.source) ? cityDefaults.source : 'off';
    const cityDensity = Number(cityDefaults.density);
    const cityFontSize = Number(cityDefaults.fontSize);
    const cityDensityInput = byId('rtma-city-density');
    const cityFontSizeInput = byId('rtma-city-font-size');
    cityDensityInput.value = String(cityDensity >= 0.01 && cityDensity <= 1 ? cityDensity : 0.25);
    cityFontSizeInput.value = String(cityFontSize >= 0.4 && cityFontSize <= 1.2 ? cityFontSize : 0.6);
    const initialCitySourceInput = document.querySelector(`input[name="rtma-cities-source"][value="${citySource}"]`);
    if (initialCitySourceInput) initialCitySourceInput.checked = true;

    function selectedCitySource() {
        return document.querySelector('input[name="rtma-cities-source"]:checked')?.value || 'off';
    }

    function updateCityControlLabels() {
        const source = selectedCitySource();
        const disabled = source === 'off';
        document.querySelectorAll('[data-city-adjustment]').forEach((row) => {
            row.classList.toggle('is-disabled', disabled);
            row.querySelector('input').disabled = disabled;
        });
        const distanceKm = Math.round(mapCore.getCityMinDistanceKm(source, cityDensityInput.value));
        byId('rtma-city-density-label').textContent = `City Density (${distanceKm} km)`;
        const fontSizeLabel = Number(cityFontSizeInput.value).toFixed(2).replace(/\.?0+$/, '');
        byId('rtma-city-font-size-label').textContent = `City Font Size (${fontSizeLabel})`;
    }

    document.querySelectorAll('input[name="rtma-cities-source"]').forEach((input) => {
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
    syncStreamForRegion();
    syncProductForStream();
    updateDensityLabel();
    status.setMessage(SELECT_MESSAGE);

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
    console.error('[rtma] startup failed', error);
    const message = byId('rtma-message');
    if (message) message.textContent = `Startup failed: ${error.message}`;
});
