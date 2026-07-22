import * as api from '../../core/api.js';
import { createLegendHost } from '../../core/legend.js';
import { createMapCore, REGION_LABELS } from '../../core/map-core.js';
import { renderProductNav } from '../../core/nav.js';
import { createScrubber } from '../../core/scrubber.js';
import { createSidebarTabs } from '../../core/sidebar-tabs.js';
import { loadDefaultSettings, loadPageSettings } from '../../core/settings.js';
import { createStatusReporter } from '../../core/status.js';
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
        basemap: 'Dark (No Labels)',
    });
    const legend = createLegendHost(byId('rtma-legend'), { align: 'left' });
    const status = createStatusReporter({
        globalTimestamp: byId('global-timestamp'),
        message: byId('rtma-message'),
        updated: byId('rtma-updated'),
        age: byId('rtma-age'),
        provider: byId('rtma-provider'),
        source: byId('rtma-source'),
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
            const loaded = await engine.loadFrames(sel, hours);
            if (token !== loadToken || loaded === null) return;
            if (!loaded.length) {
                frames = [];
                scrubber.setFrames([], { silent: true });
                showScrubber(false);
                return;
            }
            frames = loaded.map((frame) => ({ ...frame, label: frameLabel(frame) }));
            showScrubber(true);
            // Latest analysis is already on the map; park the scrubber on the
            // newest frame without re-rendering it.
            scrubber.setFrames(frames, { index: frames.length - 1, silent: true });
        } catch (err) {
            if (token !== loadToken) return;
            console.error('[rtma] frame load failed', err);
            showScrubber(false);
        }
    }

    function clearAll() {
        loadToken += 1;
        frames = [];
        frameErrors.clear();
        scrubber.setFrames([], { silent: true });
        showScrubber(false);
        engine.clear();
        status.setMessage(SELECT_MESSAGE);
    }

    // ── Auto-update: append newly cached frames ─────────────────────────────
    async function autoUpdateTick() {
        if (!byId('rtma-auto-update')?.checked) return;
        const sel = selection();
        if (!sel.stream || !sel.product || !frames.length) return;
        if (frames[0].stream !== sel.stream || frames[0].product !== sel.product) return;
        try {
            const fresh = await engine.fetchNewFrames(sel, lookbackHours(sel.stream), frames);
            if (!fresh.length || !frames.length) return;
            const combined = [...frames, ...fresh.map((frame) => ({ ...frame, label: frameLabel(frame) }))];
            const dropped = Math.max(0, combined.length - FRAME_CAP);
            frames = combined.slice(dropped);
            const index = Math.max(0, scrubber.getIndex() - dropped);
            scrubber.setFrames(frames, { index, silent: true, keepPlaying: true });
        } catch (_) { /* transient; next tick retries */ }
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
