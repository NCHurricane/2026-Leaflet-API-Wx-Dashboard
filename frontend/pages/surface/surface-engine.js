import { createRequestGate } from '../../core/api.js';
import { SURFACE_COLORMAPS, SURFACE_PRODUCT_LABELS, SURFACE_PRODUCT_UNITS } from './surface-render.js';

const GRADIENT_META_TTL_MS = 5 * 60 * 1000;
const STALE_THRESHOLD_MS = 90 * 60 * 1000;
const REFRESH_POLL_BUDGET_MS = 90 * 1000;

function refreshPollDelayMs(data) {
    const retrySeconds = Number(data?.retry_after_seconds);
    if (data?.cache_state === 'backoff') {
        return 1000 * Math.max(1, Math.min(60, retrySeconds || 5));
    }
    return 1000 * Math.max(1, Math.min(5, retrySeconds || 2));
}

function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, (char) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[char]));
}

function formatTick(value) {
    return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

function legendHtml(product, stationCount) {
    const anchors = SURFACE_COLORMAPS[product];
    if (!anchors?.length) return '';

    const label = SURFACE_PRODUCT_LABELS[product] || product.replace(/_/g, ' ');
    const unit = SURFACE_PRODUCT_UNITS[product] || '';
    const min = anchors[0][0];
    const max = anchors[anchors.length - 1][0];
    const range = Math.max(1, max - min);
    const stops = anchors.map(([value, color]) => (
        `${color} ${(((value - min) / range) * 100).toFixed(2)}%`
    )).join(', ');
    const ticks = anchors.map(([value]) => {
        const pct = ((value - min) / range) * 100;
        return `<span class="core-legend-tick" style="left:${pct.toFixed(2)}%">${escapeHtml(formatTick(value))}</span>`;
    }).join('');

    return `<div class="core-legend-header">
            <span class="core-legend-provider">IEM</span>
            <div class="core-legend-heading"><div class="core-legend-title">Surface: ${escapeHtml(label)}</div></div>
            <span class="core-legend-meta">${escapeHtml(unit || '—')}</span>
            <span class="core-legend-meta">${stationCount} stations</span>
        </div>
        <div class="core-legend-body">
            <div class="core-legend-colorbar" style="background: linear-gradient(to right, ${stops});"></div>
            <div class="core-legend-ticks">${ticks}</div>
        </div>`;
}

// Gradient source interpolates from continent-scale observations: WORLD views
// use WORLD stations, every other region uses CONUS.
function gradientSourceRegion(region) {
    return String(region || 'CONUS').toUpperCase() === 'WORLD' ? 'WORLD' : 'CONUS';
}

export function createSurfaceEngine({ api, renderer, legend, status, onStationCount }) {
    const gate = createRequestGate();
    const gradientMetaCache = new Map();
    const gradientMetaInflight = new Map();
    const gradientPendingKeys = new Set();
    let stations = [];
    let gradientStations = [];
    let gradientProduct = null;
    let gradientRegion = null;
    let lastView = null;

    function filteredStations(view) {
        if (!(view.networks instanceof Set)) return stations;
        return stations.filter((s) => view.networks.has(s.network || 'ASOS'));
    }

    function gradientMetaKey(product, region) {
        return `${gradientSourceRegion(region)}|${product}`;
    }

    function freshGradientMeta(product, region) {
        const meta = gradientMetaCache.get(gradientMetaKey(product, region)) || null;
        return meta?.image_url ? meta : null;
    }

    async function primeGradientMeta(product, region, onMeta) {
        if (!product) return null;
        const key = gradientMetaKey(product, region);
        const cached = gradientMetaCache.get(key) || null;
        const fetchedAt = Number(cached?._fetchedAtMs || 0);
        if (cached && fetchedAt > 0 && (Date.now() - fetchedAt) < GRADIENT_META_TTL_MS) {
            return cached;
        }
        if (gradientMetaInflight.has(key)) return gradientMetaInflight.get(key);

        const sourceRegion = gradientSourceRegion(region);
        const fetchPromise = (async () => {
            let latest = cached;
            try {
                for (let attempt = 0; attempt < 60; attempt += 1) {
                    const meta = await api.fetchJson(
                        `/api/data/surface-gradient?region=${encodeURIComponent(sourceRegion)}&product=${encodeURIComponent(product)}`,
                        { cache: 'no-cache' },
                    );
                    if (meta?.image_url && Array.isArray(meta.bounds) && meta.bounds.length === 4) {
                        meta._fetchedAtMs = meta.refreshing ? 0 : Date.now();
                        gradientMetaCache.set(key, meta);
                        latest = meta;
                        onMeta?.(meta);
                    }
                    if (!meta?.refreshing) return latest;
                    const retrySeconds = Math.max(
                        1,
                        Math.min(5, Number(meta.retry_after_seconds) || 1),
                    );
                    await new Promise((resolve) => setTimeout(resolve, retrySeconds * 1000));
                }
            } catch (_) {
                // Silent: the renderer falls back to client-side interpolation.
            }
            return latest;
        })();

        gradientMetaInflight.set(key, fetchPromise);
        try {
            return await fetchPromise;
        } finally {
            gradientMetaInflight.delete(key);
        }
    }

    // ASOS-only source stations for gradient interpolation — more reliable
    // sensors, fewer outliers than COOP/DCP/RWIS.
    async function ensureGradientStations(product, region, prefetched, signal) {
        const sourceRegion = gradientSourceRegion(region);
        if (gradientProduct === product && gradientRegion === sourceRegion && gradientStations.length) {
            return;
        }
        try {
            let allStations = prefetched;
            if (!allStations) {
                const data = await api.fetchJson(
                    `/api/data/surface?region=${encodeURIComponent(sourceRegion)}&product=${encodeURIComponent(product)}`,
                    { signal },
                );
                allStations = Array.isArray(data?.stations) ? data.stations : [];
            }
            gradientStations = allStations.filter((s) => (s.network || 'ASOS') === 'ASOS');
            gradientProduct = product;
            gradientRegion = sourceRegion;
        } catch (error) {
            if (error.name === 'AbortError') throw error;
            console.warn(`[surface] ${sourceRegion} gradient source unavailable, falling back to regional stations:`, error);
        }
    }

    function renderView(view) {
        const gradientKey = gradientMetaKey(view.product, view.region);
        renderer.render(filteredStations(view), {
            product: view.product,
            region: view.region,
            density: view.density,
            valueOpacity: view.valueOpacity,
            gradientEnabled: view.gradientEnabled,
            gradientOpacity: view.gradientOpacity,
            gradientMeta: view.gradientEnabled ? freshGradientMeta(view.product, view.region) : null,
            gradientPending: view.gradientEnabled && gradientPendingKeys.has(gradientKey),
            gradientStations: gradientProduct === view.product
                && gradientRegion === gradientSourceRegion(view.region)
                ? gradientStations
                : null,
        });
    }

    async function load(view, options = {}) {
        if (!view.product || !view.region) return;
        const request = gate.begin();
        const label = SURFACE_PRODUCT_LABELS[view.product] || view.product;
        status.setMessage(`Loading surface ${label} for ${view.region}…`);

        try {
            const baseUrl = `/api/data/surface?region=${encodeURIComponent(view.region)}&product=${encodeURIComponent(view.product)}`;
            const url = baseUrl
                + (options.forceRefresh ? '&force_refresh=true' : '');
            let data = await api.fetchJson(
                url,
                { signal: request.signal },
            );
            if (!gate.isCurrent(request.sequence)) return;

            stations = Array.isArray(data?.stations) ? data.stations : [];
            lastView = { ...view };
            const gradientKey = gradientMetaKey(view.product, view.region);
            if (view.gradientEnabled && !freshGradientMeta(view.product, view.region)) {
                gradientPendingKeys.add(gradientKey);
            } else {
                gradientPendingKeys.delete(gradientKey);
            }
            renderView(lastView);
            legend.setHtml(legendHtml(view.product, stations.length));
            onStationCount?.(stations.length);

            const refreshStates = new Set(['refreshing', 'stale_refreshing', 'backoff']);
            if (refreshStates.has(data?.cache_state)) {
                status.setMessage(
                    data?.cache_state === 'stale_refreshing'
                        ? `Showing cached ${label}; refreshing…`
                        : `Warming surface ${label} for ${view.region}…`,
                );
                const pollDeadline = Date.now() + REFRESH_POLL_BUDGET_MS;
                for (let attempt = 0; attempt < 60; attempt += 1) {
                    const remainingMs = pollDeadline - Date.now();
                    if (remainingMs <= 0) break;
                    const delayMs = Math.min(refreshPollDelayMs(data), remainingMs);
                    await new Promise((resolve) => setTimeout(resolve, delayMs));
                    if (!gate.isCurrent(request.sequence)) return;
                    const refreshed = await api.fetchJson(baseUrl, { signal: request.signal });
                    data = refreshed;
                    if (refreshStates.has(data?.cache_state)) continue;
                    stations = Array.isArray(data?.stations) ? data.stations : [];
                    renderView(lastView);
                    legend.setHtml(legendHtml(view.product, stations.length));
                    onStationCount?.(stations.length);
                    break;
                }
                if (refreshStates.has(data?.cache_state)) {
                    status.setMessage(
                        `Surface ${label} is still warming; retrying on the next refresh.`,
                    );
                    return;
                }
            }

            const tsMs = new Date(data?.timestamp).getTime();
            const stale = Number.isFinite(tsMs) && (Date.now() - tsMs) > STALE_THRESHOLD_MS;
            status.setDataInfo({
                timestamp: data?.timestamp,
                provider: 'IEM',
                source: data?.timestamp_source === 'station_valid' || !data?.timestamp_source
                    ? 'Station observation valid time'
                    : String(data.timestamp_source),
                stale,
            });
            status.setMessage(
                `Surface ${label} for ${view.region}: ${stations.length} stations.${stale ? ' [STALE]' : ''}`,
                stale ? 'error' : 'success',
            );

            if (view.gradientEnabled) {
                const hadMeta = !!freshGradientMeta(view.product, view.region);
                let meta = null;
                try {
                    await ensureGradientStations(view.product, view.region, stations, request.signal);
                    meta = await primeGradientMeta(view.product, view.region, () => {
                        if (
                            gate.isCurrent(request.sequence)
                            && lastView
                            && gradientMetaKey(lastView.product, lastView.region) === gradientKey
                        ) {
                            renderView(lastView);
                        }
                    });
                } finally {
                    gradientPendingKeys.delete(gradientKey);
                }
                if (!gate.isCurrent(request.sequence)) return;
                // Use client interpolation only after the server path has
                // finished without a usable current or last-complete PNG.
                if (meta || !hadMeta) renderView(lastView);
            }
        } catch (error) {
            if (error.name === 'AbortError' || !gate.isCurrent(request.sequence)) return;
            console.error('[surface] load failed', error);
            status.setMessage(`Surface error: ${error.message}`, 'error');
        }
    }

    // Cheap re-render of already-loaded stations (opacity, density, network,
    // zoom, or gradient-style changes). Returns false when nothing is loaded.
    function rerender(view) {
        if (!lastView || !stations.length) return false;
        lastView = { ...lastView, ...view };
        renderView(lastView);
        return true;
    }

    // Gradient toggled on after load: make sure source stations and the worker
    // PNG metadata exist, then re-render.
    async function applyGradient(view) {
        const gradientKey = gradientMetaKey(view.product, view.region);
        if (view.gradientEnabled && !freshGradientMeta(view.product, view.region)) {
            gradientPendingKeys.add(gradientKey);
        } else {
            gradientPendingKeys.delete(gradientKey);
        }
        if (!rerender(view)) {
            gradientPendingKeys.delete(gradientKey);
            return;
        }
        if (!lastView.gradientEnabled) return;
        const request = gate.begin();
        try {
            await ensureGradientStations(lastView.product, lastView.region, null, request.signal);
            await primeGradientMeta(lastView.product, lastView.region, () => {
                if (
                    gate.isCurrent(request.sequence)
                    && lastView
                    && gradientMetaKey(lastView.product, lastView.region) === gradientKey
                ) {
                    renderView(lastView);
                }
            });
            gradientPendingKeys.delete(gradientKey);
            if (gate.isCurrent(request.sequence)) renderView(lastView);
        } catch (error) {
            if (error.name === 'AbortError') return;
            console.warn('[surface] gradient refresh failed', error);
        } finally {
            gradientPendingKeys.delete(gradientKey);
        }
    }

    function clear() {
        gate.cancel();
        gradientPendingKeys.clear();
        stations = [];
        lastView = null;
        renderer.clear();
        legend.clear();
        status.clear();
        onStationCount?.(0);
    }

    function renderArchiveFrame(frame, view) {
        gate.cancel();
        stations = Array.isArray(frame?.stations) ? frame.stations : [];
        lastView = { ...view, gradientEnabled: false };
        renderView(lastView);
        legend.setHtml(legendHtml(view.product, stations.length));
        onStationCount?.(stations.length);
        status.setDataInfo({ timestamp: frame?.timestamp, provider: 'IEM' });
        status.setMessage(`Surface archive: ${stations.length} stations.`, 'success');
    }

    return Object.freeze({
        clear,
        destroy: clear,
        applyGradient,
        load,
        renderArchiveFrame,
        rerender,
        get hasStations() { return stations.length > 0; },
    });
}
