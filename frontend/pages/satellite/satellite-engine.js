// Satellite engine: catalog/frame-set fetching and legend building for the
// standalone Satellite page. DOM-free — the page controller owns all elements.

function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, (character) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[character]));
}

// Hand-tuned qualitative legends for RGB composites (ported from the shell).
const INTERPRETIVE_LEGENDS = Object.freeze({
    FireTemperature: {
        title: 'Fire Temperature',
        items: [
            { color: '#ff3a1f', label: 'Active fire / hot spot' },
            { color: '#a94f78', label: 'Warm land / desert background' },
            { color: '#51345f', label: 'Cooler land or shadowed surface' },
            { color: '#0f7eb3', label: 'Cold cloud tops' },
        ],
    },
    AirMass: {
        title: 'Air Mass',
        items: [
            { color: '#c04c5c', label: 'Strong upper-level dry-air signal' },
            { color: '#7d4ca8', label: 'Cold/dry upper-level air' },
            { color: '#49a36b', label: 'Moist low/mid-level air mass' },
            { color: '#d8e7f2', label: 'Cold high cloud tops' },
        ],
    },
    DayCloudPhase: {
        title: 'Day Cloud Phase',
        items: [
            { color: '#efe45a', label: 'Thick cold cloud tops' },
            { color: '#df8a5a', label: 'High cloud edge / mixed phase' },
            { color: '#4ad088', label: 'Low liquid cloud field' },
            { color: '#6bb2d8', label: 'Ice/snow-band response' },
            { color: '#061d38', label: 'Clear water or dark surface' },
        ],
    },
    DayLandCloudFire: {
        title: 'Day Land Cloud Fire',
        items: [
            { color: '#3d9c56', label: 'Vegetation-dominant surface' },
            { color: '#b69476', label: 'Bare or dry ground' },
            { color: '#ff3524', label: 'Strong 2.2 um hot-spot signal' },
            { color: '#1d3048', label: 'Water or very dark surface' },
            { color: '#f5f5f5', label: 'Clouds' },
        ],
    },
    DaySnowFog: {
        title: 'Day Snow/Fog',
        items: [
            { color: '#d8c992', label: 'Snow / ice surface' },
            { color: '#e8e5d8', label: 'Low cloud or fog' },
            { color: '#b8c8ef', label: 'Cold cloud' },
            { color: '#5a8b66', label: 'Vegetated land' },
            { color: '#7b4e43', label: 'Bare or dry land' },
        ],
    },
    NighttimeMicrophysics: {
        title: 'Nighttime Microphysics',
        items: [
            { color: '#0717d6', label: 'Clear or warm low cloud' },
            { color: '#b1009b', label: 'Higher cold cloud' },
            { color: '#740010', label: 'Warm/thin cloud edge' },
            { color: '#2a006f', label: 'Mixed cloud or transition zone' },
        ],
    },
    Dust: {
        title: 'Dust',
        items: [
            { color: '#df65b0', label: 'Dust / split-window signal' },
            { color: '#b8834a', label: 'Dry elevated dust or warm surface' },
            { color: '#7a5fb0', label: 'Dust mixed with cloud' },
            { color: '#5f90b5', label: 'Cloud or moist background' },
            { color: '#2d3142', label: 'Clear or dark background' },
        ],
    },
    Ash: {
        title: 'Ash',
        items: [
            { color: '#d75fb7', label: 'Split-window ash signal' },
            { color: '#7857a4', label: 'Ash mixed with cold cloud' },
            { color: '#d2935a', label: 'Dry slot / warmer split-window signal' },
            { color: '#b8b8c5', label: 'Meteorological cloud' },
        ],
    },
    SulfurDioxide: {
        title: 'Sulfur Dioxide',
        items: [
            { color: '#dacb49', label: 'Stronger SO2-sensitive signal' },
            { color: '#c05aa0', label: 'SO2 mixed with ash/cloud' },
            { color: '#4aa4c7', label: 'Moist cloud or plume' },
            { color: '#614682', label: 'Weak/mixed channel signal' },
            { color: '#30384c', label: 'Background / clear air' },
        ],
    },
    AerosolDetection: {
        title: 'Smoke & Dust (ADP)',
        subtitle: 'Opacity indicates detection confidence',
        items: [
            { color: '#39d0d8', label: 'Smoke detected' },
            { color: '#e8a33d', label: 'Dust detected' },
            { color: '#c44dff', label: 'Smoke + dust detected' },
        ],
    },
});

export const SAT_DISPLAY_NAMES = Object.freeze({
    goes18: 'GOES-18 (West)',
    goes19: 'GOES-19 (East)',
    gk2a: 'GK2A',
    gmgsi: 'GMGSI Global Mosaic',
    himawari9: 'Himawari-9',
    meteosat12: 'Meteosat-12',
    meteosat9: 'Meteosat-9',
    meteosat11: 'Meteosat-11 RSS',
});

export function frameIndexForReload(frames, preferredFrameKey = '') {
    if (!Array.isArray(frames) || !frames.length) return 0;
    const preferredKey = String(preferredFrameKey || '');
    if (preferredKey) {
        const preferredIndex = frames.findIndex((frame) => String(frame?.frame_key || '') === preferredKey);
        if (preferredIndex >= 0) return preferredIndex;
    }
    return frames.length - 1;
}

export function formatFrameLabel(frame) {
    const raw = frame?.timestamp_utc || null;
    if (!raw) return '--';
    try {
        return new Date(raw).toLocaleString(undefined, {
            month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZoneName: 'short',
        });
    } catch {
        return String(raw);
    }
}

export function createSatelliteEngine({ api, clientId = '' }) {
    const legendCache = new Map();

    async function fetchFrameSet(selection, { hours, maxFrames, signal, refresh = false, minFrames = 1 }) {
        const { satId, sector, channel } = selection;
        if (!satId || !sector) throw new Error('No satellite or sector selected.');
        const params = new URLSearchParams({
            sat_id: satId,
            sector,
            channel,
            hours: String(hours),
            max_frames: String(maxFrames),
            refresh: refresh ? 'true' : 'false',
        });
        if (clientId) params.set('client_id', clientId);
        const resp = await fetch(api.apiUrl(`/api/satellite-v2/catalog?${params.toString()}`), { cache: 'no-store', signal });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok || (data.status !== 'success' && data.status !== 'stale')) {
            throw new Error(data.detail || data.message || resp.statusText || 'Satellite catalog request failed');
        }
        const frames = Array.isArray(data.frames)
            ? data.frames.filter((frame) => frame && frame.frame_key)
            : [];
        const requiredFrameCount = Math.max(0, Number.isFinite(Number(minFrames)) ? Number(minFrames) : 1);
        if (frames.length < requiredFrameCount) {
            throw new Error('Satellite catalog does not have enough frames yet.');
        }
        return { catalog: data, frames };
    }

    async function fetchLegend(channel) {
        const key = String(channel || '').trim() || 'Channel13';
        if (legendCache.has(key)) return legendCache.get(key);
        if (INTERPRETIVE_LEGENDS[key]) {
            const localLegend = {
                status: 'success',
                available: true,
                channel: key,
                title: INTERPRETIVE_LEGENDS[key].title,
                kind: 'composite',
                legend_type: 'interpretive',
                items: INTERPRETIVE_LEGENDS[key].items,
            };
            legendCache.set(key, localLegend);
            return localLegend;
        }
        const resp = await fetch(api.apiUrl(`/api/satellite-v2/legend?channel=${encodeURIComponent(key)}`), { cache: 'no-store' });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok || data.status !== 'success') {
            throw new Error(data.detail || data.message || resp.statusText || 'Satellite legend request failed');
        }
        legendCache.set(key, data);
        return data;
    }

    function releaseSelection({ beacon = false } = {}) {
        if (!clientId) return false;
        const params = new URLSearchParams({ client_id: clientId });
        const url = api.apiUrl(`/api/satellite-v2/selection/release?${params.toString()}`);
        if (beacon && typeof globalThis.navigator?.sendBeacon === 'function') {
            return globalThis.navigator.sendBeacon(url);
        }
        void fetch(url, {
            method: 'POST',
            cache: 'no-store',
            keepalive: beacon,
        }).catch(() => {});
        return true;
    }

    function interpretiveLegendHtml(title, items) {
        const rows = (Array.isArray(items) ? items : [])
            .filter((item) => item?.color && item?.label)
            .map((item) => (
                `<div class="satellite-legend-item">`
                + `<span class="satellite-legend-swatch" style="background:${item.color};"></span>`
                + `<span>${escapeHtml(item.label)}</span>`
                + `</div>`
            ))
            .join('');
        if (!rows) return '';
        const header = `<div class="core-legend-header">
            <span class="core-legend-provider">Satellite</span>
            <div class="core-legend-heading"><div class="core-legend-title">${escapeHtml(title)}</div></div>
        </div>`;
        return `${header}<div class="core-legend-body"><div class="satellite-legend-items">${rows}</div></div>`;
    }

    function continuousLegendHtml(title, axisLabel, anchors, ticks = null, options = {}) {
        const normalized = (Array.isArray(anchors) ? anchors : [])
            .map((item) => Array.isArray(item)
                ? [Number(item[0]), item[1], item[2]]
                : [Number(item?.value), item?.color, item?.label])
            .filter(([value, color]) => Number.isFinite(value) && color);
        if (!normalized.length) return '';

        const min = normalized[0][0];
        const max = normalized[normalized.length - 1][0];
        const range = Math.max(1, max - min);
        const gradient = normalized.map(([value, color]) => {
            const pct = ((value - min) / range) * 100;
            return `${color} ${pct.toFixed(2)}%`;
        }).join(', ');
        const normalizedTicks = (Array.isArray(ticks) && ticks.length ? ticks : normalized)
            .map((item) => Array.isArray(item)
                ? [Number(item[0]), item[2] ?? item[0]]
                : [Number(item?.value), item?.label ?? item?.value])
            .filter(([value]) => Number.isFinite(value));
        const tickHtml = normalizedTicks.map(([value, label]) => {
            const pct = ((value - min) / range) * 100;
            return `<span class="core-legend-tick" style="left:${pct.toFixed(2)}%">${escapeHtml(label ?? value)}</span>`;
        }).join('');

        const barHtml =
            `<div class="core-legend-colorbar" style="background: linear-gradient(to right, ${gradient});"></div>`
            + `<div class="core-legend-ticks">${tickHtml}</div>`;

        // Optional discrete swatch (e.g. AOD "No Data") shown left of the bar.
        const swatch = options?.leadingSwatch;
        const barBlock = swatch
            ? `<div class="satellite-legend-colorbar-row">`
                + `<div class="satellite-legend-leading-swatch">`
                + `<span class="satellite-legend-swatch" style="background:${swatch.color};"></span>`
                + `<span class="satellite-legend-leading-label">${escapeHtml(swatch.label)}</span>`
                + `</div>`
                + `<div class="satellite-legend-colorbar-main">${barHtml}</div>`
            + `</div>`
            : barHtml;

        const header = `<div class="core-legend-header">
            <span class="core-legend-provider">Satellite</span>
            <div class="core-legend-heading"><div class="core-legend-title">${escapeHtml(title)}</div></div>
        </div>`;
        return `${header}<div class="core-legend-body">${barBlock}`
            + `<div class="satellite-legend-axis">${escapeHtml(axisLabel)}</div></div>`;
    }

    function legendHtmlFor(legendData) {
        if (!legendData) return '';
        if (!legendData.available || !Array.isArray(legendData.anchors) || !legendData.anchors.length) {
            if (legendData.legend_type === 'interpretive' && Array.isArray(legendData.items) && legendData.items.length) {
                return interpretiveLegendHtml(legendData.title || 'Satellite', legendData.items);
            }
            return '';
        }
        const axisLabel = legendData.axis_label
            || (legendData.units ? `Brightness Temperature (${legendData.units})` : 'Brightness Temperature');
        // AOD mirrors the NESDIS convention: a discrete "No Data" swatch left of
        // the 0–1 gradient (no-retrieval pixels render transparent).
        const options = legendData.kind === 'aod'
            ? { leadingSwatch: { color: '#000000', label: 'No Data' } }
            : {};
        return continuousLegendHtml(legendData.title || 'Satellite', axisLabel, legendData.anchors, legendData.ticks, options);
    }

    return Object.freeze({
        fetchFrameSet,
        fetchLegend,
        legendHtmlFor,
        releaseSelection,
    });
}
