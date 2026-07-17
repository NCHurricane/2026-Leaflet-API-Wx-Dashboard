import { createRequestGate } from '../../core/api.js';

const COLORS = Object.freeze({ 0: '#ffff00', 1: '#fcd37f', 2: '#ffaa00', 3: '#e60000', 4: '#730000' });
const LABELS = Object.freeze({
    0: 'D0 — Abnormally Dry', 1: 'D1 — Moderate Drought',
    2: 'D2 — Severe Drought', 3: 'D3 — Extreme Drought',
    4: 'D4 — Exceptional Drought',
});
const LEGEND_LABELS = Object.freeze({
    0: 'Abnormally Dry', 1: 'Moderate', 2: 'Severe', 3: 'Extreme', 4: 'Exceptional',
});
const ALL_CATEGORIES = Object.freeze([0, 1, 2, 3, 4]);

function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, (char) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[char]));
}

function formatPct(value) {
    const number = Number(value);
    return Number.isFinite(number) ? `${number.toFixed(1)}%` : '—';
}

function legendHtml(categories, stats, stateCode, date) {
    const active = new Set(categories);
    const cumulative = stats?.cumulative || {};
    const individual = stats?.individual || {};
    const categoriesHtml = ALL_CATEGORIES.map((dm) => `
        <div class="core-legend-category${active.has(dm) ? '' : ' is-disabled'}"
            aria-label="D${dm}, ${escapeHtml(LEGEND_LABELS[dm])}${active.has(dm) ? '' : ', disabled'}">
            <span class="core-legend-color" style="background:${COLORS[dm]}" aria-hidden="true"></span>
            <span class="core-legend-category-copy">
                <span class="core-legend-category-code">D${dm}</span>
                <span class="core-legend-category-label">${escapeHtml(LEGEND_LABELS[dm])}</span>
            </span>
        </div>`).join('');
    const headers = ALL_CATEGORIES.map((dm) => `<div class="drought-stat-code${active.has(dm) ? '' : ' is-disabled'}">D${dm}</div>`).join('');
    const cumulativeValues = ALL_CATEGORIES.map((dm) => `<div>${formatPct(cumulative[dm === 4 ? 'D4' : `D${dm}-D4`])}</div>`).join('');
    const individualValues = ALL_CATEGORIES.map((dm) => `<div>${formatPct(individual[`D${dm}`])}</div>`).join('');
    const dsci = Number(stats?.dsci);
    const stateMeta = stateCode ? `<span class="core-legend-meta">${escapeHtml(stateCode)}</span>` : '';
    const stateDetails = stateCode ? `
        <section class="drought-legend-stats" aria-label="${escapeHtml(stateCode)} drought statistics">
            <div class="drought-stats-header">
                <span>${escapeHtml(stateCode)} statistics</span>
                <span class="drought-dsci">DSCI <strong>${Number.isFinite(dsci) ? dsci.toFixed(1) : '—'}</strong></span>
            </div>
            <div class="drought-stats-grid">
                <div></div>${headers}
                <div class="drought-stat-label">Cumulative</div>${cumulativeValues}
                <div class="drought-stat-label">Individual</div>${individualValues}
            </div>
        </section>` : '';

    return `<div class="core-legend-header">
            <span class="core-legend-provider">USDM</span>
            <div class="core-legend-heading"><div class="core-legend-title">U.S. Drought Monitor</div></div>
            <span class="core-legend-meta">Valid ${escapeHtml(date)}</span>
            ${stateMeta}
        </div>
        <div class="core-legend-body">
            <div class="core-legend-categories">${categoriesHtml}</div>
            ${stateDetails}
        </div>`;
}

export function createDroughtEngine({ api, mapCore, legend, status }) {
    const { leaflet, map } = mapCore;
    const gate = createRequestGate();
    const statsCache = new Map();
    let layer = null;
    let dates = [];
    let lastView = null;
    let visible = true;

    async function loadDates({ force = false } = {}) {
        if (dates.length && !force) return [...dates];
        const payload = await api.fetchJson('/api/data/drought/dates', { cache: 'no-store' });
        dates = Array.isArray(payload?.dates) ? payload.dates : [];
        return [...dates];
    }

    async function loadStats(date, stateCode, signal) {
        if (!stateCode) return null;
        const key = `${stateCode}|${date}`;
        if (statsCache.has(key)) return statsCache.get(key);
        const stats = await api.fetchJson(
            `/api/data/drought/state-stats?date=${encodeURIComponent(date)}&state=${encodeURIComponent(stateCode)}`,
            { cache: 'no-store', signal },
        );
        statsCache.set(key, stats);
        return stats;
    }

    function applyStyle(categories, opacity) {
        if (!layer) return;
        const active = new Set(categories);
        layer.eachLayer((featureLayer) => {
            const dm = Number(featureLayer.feature?.properties?.DM);
            const enabled = active.has(dm);
            featureLayer.setStyle({
                fillColor: COLORS[dm] || '#cccccc',
                fillOpacity: enabled ? opacity : 0,
                color: COLORS[dm] || '#cccccc',
                opacity: enabled ? 0.8 : 0,
                weight: enabled ? 0.5 : 0,
            });
        });
    }

    function renderLegend(view = lastView) {
        if (!view) return;
        legend.setHtml(legendHtml(view.categories, view.stats, view.stateCode, view.date));
    }

    async function load(options = {}) {
        const availableDates = await loadDates();
        const date = options.date || availableDates[0];
        if (!date) throw new Error('No U.S. Drought Monitor dates are available.');
        const categories = Array.isArray(options.categories) ? options.categories : [...ALL_CATEGORIES];
        const stateCode = /^[A-Z]{2}$/.test(String(options.stateCode || '').toUpperCase())
            ? String(options.stateCode).toUpperCase()
            : null;
        const opacity = Math.max(0.1, Math.min(1, Number(options.opacity) || 0.75));
        const request = gate.begin();
        status.setMessage(`Loading U.S. Drought Monitor for ${date}…`);

        try {
            const [geojson, stats] = await Promise.all([
                api.fetchJson(`/api/data/drought?date=${encodeURIComponent(date)}`, { signal: request.signal }),
                loadStats(date, stateCode, request.signal).catch((error) => {
                    if (error.name === 'AbortError') throw error;
                    console.warn('[drought] state statistics unavailable', error);
                    return null;
                }),
            ]);
            if (!gate.isCurrent(request.sequence)) return null;

            if (layer) map.removeLayer(layer);
            layer = leaflet.geoJSON(geojson, {
                style: (feature) => {
                    const dm = Number(feature.properties?.DM);
                    return { fillColor: COLORS[dm] || '#cccccc', color: COLORS[dm] || '#cccccc', weight: 0.5 };
                },
                onEachFeature: (feature, featureLayer) => {
                    const dm = Number(feature.properties?.DM);
                    featureLayer.bindTooltip(`<strong>${LABELS[dm] || `DM ${dm}`}</strong>`, {
                        sticky: true,
                        className: 'drought-tooltip',
                    });
                },
            });
            if (visible) layer.addTo(map);
            lastView = { date, categories: [...categories], stateCode, opacity, stats };
            applyStyle(categories, opacity);
            renderLegend();
            status.setDataInfo({
                timestamp: `${date}T12:00:00Z`,
                provider: 'USDM / NDMC',
                source: 'U.S. Drought Monitor valid date',
            });
            status.setMessage(`U.S. Drought Monitor valid ${date}.`, 'success');
            return { date, stats };
        } catch (error) {
            if (error.name === 'AbortError') return null;
            if (gate.isCurrent(request.sequence)) status.setMessage(`Drought load failed: ${error.message}`, 'error');
            throw error;
        }
    }

    function setFilter({ categories, opacity }) {
        if (!lastView) return false;
        lastView.categories = Array.isArray(categories) ? [...categories] : lastView.categories;
        lastView.opacity = Math.max(0.1, Math.min(1, Number(opacity) || lastView.opacity));
        applyStyle(lastView.categories, lastView.opacity);
        renderLegend();
        return true;
    }

    function setVisible(nextVisible) {
        visible = !!nextVisible;
        if (!layer) return;
        if (visible && !map.hasLayer(layer)) layer.addTo(map);
        if (!visible && map.hasLayer(layer)) map.removeLayer(layer);
    }

    function clear() {
        gate.cancel();
        if (layer && map.hasLayer(layer)) map.removeLayer(layer);
        layer = null;
        lastView = null;
        legend.clear();
        status.clear();
    }

    return Object.freeze({
        clear,
        destroy: clear,
        load,
        loadDates,
        setFilter,
        setVisible,
    });
}
