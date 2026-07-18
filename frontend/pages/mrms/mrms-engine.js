import { createRequestGate } from '../../core/api.js';

// DOM-free MRMS engine: frame discovery, overlay rendering, and legend HTML.
// Ported from js/mrms-engine.js + the monolith's scrub-frame renderer.

const STALE_MS = 90 * 60 * 1000;
const PREFETCH_FRAMES = 2;
const LEGACY_BBOX = 'south=21.0&west=-130.0&north=52.0&east=-60.0';

function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, (char) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[char]));
}

export function timestampMs(value) {
    if (value == null) return null;
    if (typeof value === 'number') return value > 1e12 ? value : value * 1000;
    const parsed = Date.parse(String(value));
    return Number.isFinite(parsed) ? parsed : null;
}

export function formatValidTimeLabel(tsMs) {
    if (!Number.isFinite(tsMs)) return '—';
    return new Date(tsMs).toLocaleString([], {
        month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
    });
}

function normalizeFrame(raw, product) {
    return {
        frame_key: raw.frame_key,
        source_data_key: raw.source_data_key || '',
        image_url: raw.image_url || '',
        bounds: raw.bounds || null,
        timestamp: raw.timestamp || '',
        legend: raw.legend || null,
        full_name: raw.full_name || product,
        units: raw.units || '',
        vmin: raw.vmin ?? null,
        vmax: raw.vmax ?? null,
        product,
    };
}

export function frameIdentity(frame) {
    return `${frame.frame_key || ''}|${frame.timestamp || ''}`;
}

// ── Legend HTML on the shared core legend tray ──────────────────────────────
function legendShellHtml(titleHtml, bodyHtml) {
    return `<div class="core-legend-header">
            <span class="core-legend-provider">MRMS</span>
            <div class="core-legend-heading"><div class="core-legend-title">${titleHtml}</div></div>
        </div>
        <div class="core-legend-body">${bodyHtml}</div>`;
}

function scaleLegendHtml(legend) {
    const scale = Array.isArray(legend?.scale) ? legend.scale : [];
    if (!scale.length) return '';
    const segments = scale
        .map((item) => `<span class="mrms-legend-segment" style="background:${item.color}"></span>`)
        .join('');
    const labels = scale
        .map((item) => `<span class="mrms-legend-tick">${escapeHtml(item.label)}</span>`)
        .join('');
    const units = legend?.display_units
        ? `<div class="mrms-legend-units">${escapeHtml(legend.display_units)}</div>`
        : '';
    return `<div class="mrms-legend-scale">${units}<div class="mrms-legend-scale-bar">${segments}</div><div class="mrms-legend-scale-labels">${labels}</div></div>`;
}

function categoricalLegendHtml(legend) {
    const items = Array.isArray(legend?.items) ? legend.items : [];
    if (!items.length) return '';
    const rows = items.map((item) => (
        `<span class="mrms-legend-item"><span class="mrms-legend-swatch" style="background:${item.color}"></span><span class="mrms-legend-text">${escapeHtml(item.label)}</span></span>`
    )).join('');
    return `<div class="mrms-legend-flow">${rows}</div>`;
}

export function mrmsLegendHtml(data) {
    const legend = data?.legend;
    if (!legend) {
        const rows = [
            `<span class="mrms-legend-item"><span class="mrms-legend-swatch" style="background:#b0d4f0"></span><span class="mrms-legend-text">≤ ${escapeHtml(String(data?.vmin ?? ''))} ${escapeHtml(data?.units || '')}</span></span>`,
            `<span class="mrms-legend-item"><span class="mrms-legend-swatch" style="background:#ff4f4f"></span><span class="mrms-legend-text">≥ ${escapeHtml(String(data?.vmax ?? ''))} ${escapeHtml(data?.units || '')}</span></span>`,
        ].join('');
        return legendShellHtml(escapeHtml(data?.full_name || 'MRMS'), `<div class="mrms-legend-flow">${rows}</div>`);
    }
    const title = escapeHtml(legend.title || 'MRMS');
    const stat = legend.stat
        ? `<span class="mrms-legend-stat">${escapeHtml(legend.stat.label)}: ${escapeHtml(legend.stat.text)}</span>`
        : '';
    const body = legend.kind === 'categorical'
        ? categoricalLegendHtml(legend)
        : scaleLegendHtml(legend);
    return legendShellHtml(`${title}${stat}`, body);
}

export function createMrmsEngine({ api, mapCore, legend, status }) {
    const leaflet = mapCore.leaflet;
    const map = mapCore.map;
    const gate = createRequestGate();
    let overlay = null;
    let opacity = 0.8;
    let renderSeq = 0;
    let lastWorkerProductSet = null;

    function removeOverlay() {
        if (overlay && map.hasLayer(overlay)) map.removeLayer(overlay);
        overlay = null;
    }

    function clear() {
        gate.cancel();
        renderSeq += 1;
        removeOverlay();
        legend.clear();
    }

    function setOpacity(value) {
        const parsed = parseFloat(value);
        if (!Number.isFinite(parsed)) return;
        opacity = parsed;
        overlay?.setOpacity(opacity);
    }

    // Points the backend MRMS worker at the active product so its frame cache
    // fills for the right GRIB stream. Best-effort; the overlay APIs still
    // serve whatever is cached if this fails.
    async function setWorkerProduct(product) {
        if (!product || lastWorkerProductSet === product) return;
        try {
            const resp = await fetch(api.apiUrl(`/api/mrms/set-product?product=${encodeURIComponent(product)}`));
            if (resp.ok) lastWorkerProductSet = product;
        } catch (err) {
            console.warn('[mrms] Could not set worker active product:', err?.message || err);
        }
    }

    async function fetchFrames(product, hours, { signal } = {}) {
        const params = new URLSearchParams({ family: 'mrms', product, hours: String(hours) });
        const data = await api.fetchJson(`/api/overlay/frames?${params}`, { cache: 'no-store', signal });
        const rawFrames = Array.isArray(data.frames) ? data.frames : [];
        return rawFrames.map((raw) => normalizeFrame(raw, product));
    }

    async function loadFrames(product, hours) {
        const request = gate.begin();
        await setWorkerProduct(product);
        const frames = await fetchFrames(product, hours, { signal: request.signal });
        if (!gate.isCurrent(request.sequence)) return null;
        return frames;
    }

    // Frames beyond the ones already shown (auto-update append path).
    async function fetchNewFrames(product, hours, existingFrames) {
        const existing = new Set(existingFrames.map(frameIdentity));
        const frames = await fetchFrames(product, hours);
        return frames.filter((frame) => !existing.has(frameIdentity(frame)));
    }

    function applyFrameStatus(frame) {
        const tsMs = timestampMs(frame?.timestamp);
        status.setDataInfo({
            timestamp: Number.isFinite(tsMs) ? new Date(tsMs).toISOString() : null,
            provider: 'NOAA MRMS',
            source: frame?.full_name || frame?.product || 'MRMS overlay',
        });
        return tsMs;
    }

    async function renderFrame(frame) {
        const seq = ++renderSeq;
        const imageUrl = frame?.image_url || '';
        const bounds = Array.isArray(frame?.bounds) ? frame.bounds : null;
        if (!imageUrl || !bounds || bounds.length < 4) return;

        await new Promise((resolve) => {
            const img = new Image();
            img.onload = resolve;
            img.onerror = resolve;
            img.src = api.apiUrl(imageUrl);
        });
        if (seq !== renderSeq) return;

        const leafletBounds = [[bounds[2], bounds[0]], [bounds[3], bounds[1]]];
        const oldOverlay = overlay;
        const newOverlay = leaflet.imageOverlay(api.apiUrl(imageUrl), leafletBounds, { opacity });
        newOverlay.addTo(map);
        if (oldOverlay && map.hasLayer(oldOverlay)) map.removeLayer(oldOverlay);
        overlay = newOverlay;

        legend.setHtml(mrmsLegendHtml(frame));
        applyFrameStatus(frame);
    }

    // Browser-cache prefetch of the next frames after `index` (fire-and-forget).
    function prefetchFrames(frames, index) {
        const count = Math.min(PREFETCH_FRAMES, frames.length - index - 1);
        for (let i = 1; i <= count; i += 1) {
            const next = frames[index + i];
            if (next?.image_url) {
                const img = new Image();
                img.src = api.apiUrl(next.image_url);
            }
        }
    }

    // Fallback when no timestamped frames exist: current on-demand overlay,
    // preferring the overlay worker's latest render over the legacy render API.
    async function loadLatest(product) {
        const request = gate.begin();
        await setWorkerProduct(product);

        let data = null;
        try {
            const overlayData = await api.fetchJson(
                `/api/overlay/latest?family=mrms&region=CONUS&stream=default&product=${encodeURIComponent(product)}`,
                { signal: request.signal },
            );
            data = {
                image_url: overlayData?.render?.image_url ?? '',
                bounds: overlayData?.bounds ?? [],
                legend: overlayData?.legend ?? null,
                full_name: overlayData?.full_name ?? product,
                units: overlayData?.units ?? '',
                vmin: overlayData?.vmin ?? null,
                vmax: overlayData?.vmax ?? null,
                timestamp: overlayData?.timestamp ?? null,
                product,
            };
            const overlayTsMs = timestampMs(data.timestamp) || 0;
            if (!overlayTsMs || (Date.now() - overlayTsMs) > STALE_MS) data = null;
        } catch (err) {
            if (err.name === 'AbortError') return null;
            data = null;
        }

        if (!data || !data.image_url) {
            const legacy = await api.fetchJson(
                `/api/data/mrms?product=${encodeURIComponent(product)}&${LEGACY_BBOX}`,
                { signal: request.signal },
            );
            data = { ...legacy, product };
        }
        if (!gate.isCurrent(request.sequence)) return null;

        await renderFrame(data);
        const tsMs = timestampMs(data.timestamp);
        const stale = Number.isFinite(tsMs) && (Date.now() - tsMs) > STALE_MS;
        return { data, tsMs, stale };
    }

    return Object.freeze({
        clear,
        destroy: clear,
        fetchNewFrames,
        loadFrames,
        loadLatest,
        prefetchFrames,
        renderFrame,
        setOpacity,
    });
}
