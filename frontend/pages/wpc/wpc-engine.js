import { createRequestGate } from '../../core/api.js';

// Mirrors config/wpc_config.py ERO_COLORS / ERO_CATEGORY_LABEL.
export const ERO_COLORS = Object.freeze({ MRGL: '#00FF00', SLGT: '#FFFF00', MDT: '#EE2C2C', HIGH: '#FF00FF' });
export const ERO_LABELS = Object.freeze({
    MRGL: 'Marginal (≥5%)',
    SLGT: 'Slight (≥15%)',
    MDT: 'Moderate (≥40%)',
    HIGH: 'High (≥70%)',
});
export const ERO_ORDER = Object.freeze(['MRGL', 'SLGT', 'MDT', 'HIGH']);

const WINTER_PROBABILITIES = Object.freeze([
    [10, '#00C5F1'],
    [40, '#008A00'],
    [70, '#FF0000'],
]);
const FOP_CATEGORIES = Object.freeze([
    ['POSSIBLE', '#FFFF00', 'Possible'],
    ['LIKELY', '#FFAA00', 'Likely'],
    ['OCCURRING', '#E60000', 'Occurring'],
]);
const MPD_CATEGORIES = Object.freeze([
    ['LIKELY', '#E60000', 'Flash Flooding Likely'],
    ['POSSIBLE', '#F59E0B', 'Flash Flooding Possible'],
    ['UNLIKELY', '#64748B', 'Flash Flooding Unlikely'],
]);

function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, (char) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[char]));
}

function timestampMs(value) {
    if (value == null) return null;
    if (typeof value === 'number') return value > 1e12 ? value : value * 1000;
    const parsed = Date.parse(String(value));
    return Number.isFinite(parsed) ? parsed : null;
}

// ── Legend HTML on the shared core legend tray ──────────────────────────────
function swatchHtml(color, label, disabled = false) {
    return `<span class="wpc-legend-item${disabled ? ' is-disabled' : ''}"><span class="wpc-legend-swatch" style="background:${color}"></span><span class="wpc-legend-text">${escapeHtml(label)}</span></span>`;
}

function legendShellHtml(title, bodyHtml) {
    return `<div class="core-legend-header">
            <span class="core-legend-provider">WPC</span>
            <div class="core-legend-heading"><div class="core-legend-title">${escapeHtml(title)}</div></div>
        </div>
        <div class="core-legend-body"><div class="wpc-legend-flow">${bodyHtml}</div></div>`;
}

export function wpcLegendHtml({ group, day, label, features }) {
    if (group === 'mpd') {
        const present = new Set((features || []).map((feature) => feature.properties?.category));
        const rows = MPD_CATEGORIES.map(([category, color, categoryLabel]) => (
            swatchHtml(color, categoryLabel, present.size > 0 && !present.has(category))
        )).join('');
        return legendShellHtml(label || 'Active Mesoscale Precipitation Discussions', rows);
    }

    if (group === 'fop') {
        const featureColors = new Map((features || []).map((feature) => [
            String(feature.properties?.category || '').toUpperCase(),
            feature.properties?.color,
        ]));
        const rows = FOP_CATEGORIES.map(([category, fallbackColor, categoryLabel]) => (
            swatchHtml(featureColors.get(category) || fallbackColor, categoryLabel)
        )).join('');
        return legendShellHtml(label || '5-Day River Flood Outlook', rows);
    }

    if (group === 'winter') {
        const featureColors = new Map((features || []).map((feature) => [
            Number(feature.properties?.probability),
            feature.properties?.color,
        ]));
        const rows = WINTER_PROBABILITIES.map(([probability, fallbackColor]) => (
            swatchHtml(featureColors.get(probability) || fallbackColor, `≥ ${probability}%`)
        )).join('');
        return legendShellHtml(label || `WPC Winter Weather — Day ${day}`, rows);
    }

    if (group === 'qpf') {
        const bins = new Map();
        (features || []).forEach((feature) => {
            const properties = feature.properties || {};
            const threshold = Number(properties.threshold);
            if (!Number.isFinite(threshold)) return;
            bins.set(threshold, {
                color: properties.color || '#888888',
                label: properties.label || `≥ ${threshold} in`,
            });
        });
        const rows = [...bins.entries()]
            .sort(([a], [b]) => a - b)
            .map(([, bin]) => swatchHtml(bin.color, bin.label))
            .join('');
        return legendShellHtml(label || `WPC QPF — Day ${day}`, rows);
    }

    const present = new Set((features || [])
        .map((feature) => String(feature.properties?.category || '').toUpperCase())
        .filter((category) => ERO_ORDER.includes(category)));
    const rows = ERO_ORDER.map((category) => (
        swatchHtml(ERO_COLORS[category], ERO_LABELS[category], present.size > 0 && !present.has(category))
    )).join('');
    return legendShellHtml(label || `WPC Excessive Rainfall — Day ${day}`, rows);
}

// Synthesizes an alert-detail-shaped feature for ERO/winter forecast areas.
// MPD features already carry their own detail properties.
function wpcForecastDetailFeature(feature, geojson, group, day) {
    if (group === 'mpd') return feature;
    const properties = feature?.properties || {};
    const productLabel = geojson?.product_label || 'WPC Forecast';
    const label = properties.label || properties.category || 'Forecast Area';
    const detailByGroup = {
        ero: {
            event: productLabel,
            description: properties.discussion_text || '',
            severity: 'Excessive Rainfall Outlook',
            metricLabel: '',
            metricValue: '',
            color: '#38BDF8',
        },
        winter: {
            event: `${productLabel} — ${label}`,
            description: properties.discussion_text || '',
            severity: 'Winter Weather Probability',
            metricLabel: 'Probability',
            metricValue: label,
        },
    };
    const detail = detailByGroup[group];
    if (!detail) return null;
    return {
        ...feature,
        properties: {
            ...properties,
            event: detail.event,
            headline: detail.event,
            description: detail.description,
            color: detail.color || properties.color,
            sent: geojson?._updated || '',
            source_url: properties.discussion_url || '',
            senderName: 'NWS Weather Prediction Center',
            severity: detail.severity,
            certainty: 'Forecast',
            wpc_forecast: true,
            wpc_group: group,
            wpc_day: day,
            wpc_product: productLabel,
            wpc_metric_label: detail.metricLabel,
            wpc_metric_value: detail.metricValue,
        },
    };
}

export function createWpcEngine({ api, mapCore, legend, status, onEmptyMessage, onDetail }) {
    const leaflet = mapCore.leaflet;
    const map = mapCore.map;
    const gate = createRequestGate();
    let layer = null;
    let opacity = 0.55;

    function removeLayer() {
        if (layer && map.hasLayer(layer)) map.removeLayer(layer);
        layer = null;
    }

    function clear() {
        gate.cancel();
        removeLayer();
        legend.clear();
        onEmptyMessage?.(null);
    }

    function setOpacity(value) {
        const parsed = parseFloat(value);
        if (!Number.isFinite(parsed)) return;
        opacity = parsed;
        if (!layer) return;
        if (typeof layer.setOpacity === 'function') {
            layer.setOpacity(opacity);
        } else if (typeof layer.eachLayer === 'function') {
            layer.eachLayer((child) => child.setStyle?.({ fillOpacity: opacity, opacity: 0.9 }));
        }
    }

    function applyTimestamps(geojson) {
        const updated = geojson?._updated;
        if (!updated) return;
        const tsMs = timestampMs(updated);
        status.setDataInfo({
            timestamp: Number.isFinite(tsMs) ? new Date(tsMs).toISOString() : null,
            provider: 'NOAA/WPC',
            source: 'WPC cache updated',
        });
    }

    async function load(selection, { refreshAttempt = 0 } = {}) {
        const { group, day, product } = selection;
        const request = gate.begin();
        status.setMessage('Loading WPC…');
        onEmptyMessage?.(null);

        try {
            const params = new URLSearchParams({ group, day: String(day) });
            if (product) params.set('product', product);
            if (refreshAttempt) params.set('_refresh', String(Date.now()));
            const geojson = await api.fetchJson(`/api/data/wpc?${params}`, { signal: request.signal });
            if (!gate.isCurrent(request.sequence)) return;

            const pollForFreshCache = () => {
                if (geojson.cache_state !== 'stale_refreshing' || refreshAttempt >= 30) return;
                window.setTimeout(() => {
                    if (gate.isCurrent(request.sequence)) {
                        load(selection, { refreshAttempt: refreshAttempt + 1 });
                    }
                }, 1000);
            };

            removeLayer();

            // Raster surface products (SigWx, surface analysis, forecast charts).
            if (geojson.image_url) {
                const bounds = geojson.bounds;
                if (!bounds) {
                    legend.clear();
                    const emptyMessage = `${geojson.product_label || 'WPC surface product'} is temporarily unavailable from WPC.`;
                    onEmptyMessage?.(emptyMessage);
                    status.setMessage(emptyMessage, 'error');
                    return;
                }
                const leafletBounds = [
                    [Number(bounds.south), Number(bounds.west)],
                    [Number(bounds.north), Number(bounds.east)],
                ];
                layer = leaflet.imageOverlay(
                    api.apiUrl(geojson.image_url),
                    leafletBounds,
                    { opacity, interactive: false, pane: 'overlayPane' },
                ).addTo(map);
                legend.clear();
                onEmptyMessage?.(null);
                applyTimestamps(geojson);
                const cacheNote = geojson.source_available === false
                    ? ' — showing cached data; WPC source is temporarily unavailable.'
                    : (geojson.stale ? ' — cached data may be stale.' : '');
                status.setMessage(
                    `${geojson.product_label || 'WPC Surface Forecast'} — transparent overlay.${cacheNote}`,
                    cacheNote ? 'error' : 'success',
                );
                pollForFreshCache();
                return;
            }

            const features = geojson.features || [];
            if (!features.length) {
                legend.setHtml(wpcLegendHtml({ group, day, label: geojson.product_label, features: [] }));
                const emptyMessage = geojson.unavailable
                    ? `${geojson.product_label || 'WPC product'} is temporarily unavailable from WPC.`
                    : (geojson.empty_message
                        || `No ${geojson.product_label || group.toUpperCase()} area issued.`);
                onEmptyMessage?.(emptyMessage);
                const cacheNote = geojson.source_available === false && !geojson.unavailable
                    ? ' Showing the last cached WPC result.'
                    : '';
                status.setMessage(emptyMessage + cacheNote);
                applyTimestamps(geojson);
                pollForFreshCache();
                return;
            }

            onEmptyMessage?.(null);
            const detailFeatures = features
                .map((feature) => wpcForecastDetailFeature(feature, geojson, group, day))
                .filter(Boolean);
            const detailFeatureById = new Map(detailFeatures.map((feature) => [feature.id, feature]));
            const eroDetailFeature = group === 'ero' ? detailFeatures[0] : null;

            layer = leaflet.geoJSON(geojson, {
                style: (feature) => {
                    const color = feature.properties?.color || '#cccccc';
                    return {
                        fillColor: color,
                        fillOpacity: opacity,
                        color,
                        weight: group === 'mpd' ? 2 : 0.8,
                        opacity: 0.9,
                    };
                },
                onEachFeature: (feature, featureLayer) => {
                    const label = feature.properties?.label
                        || feature.properties?.category || 'Risk';
                    featureLayer.bindTooltip(
                        `<strong>${escapeHtml(label)}</strong>`,
                        { sticky: true, className: 'wpc-hover-tip' },
                    );
                    if (group === 'mpd') {
                        featureLayer.on('click', (event) => {
                            onDetail?.(event?.latlng, feature, [feature]);
                        });
                    } else if (group === 'ero' && eroDetailFeature) {
                        featureLayer.on('click', (event) => {
                            onDetail?.(event?.latlng, eroDetailFeature, [eroDetailFeature]);
                        });
                    } else if (group === 'winter') {
                        featureLayer.on('click', (event) => {
                            const detailFeature = detailFeatureById.get(feature.id);
                            if (detailFeature) {
                                onDetail?.(event?.latlng, detailFeature, detailFeatures);
                            }
                        });
                    }
                },
            }).addTo(map);

            legend.setHtml(wpcLegendHtml({ group, day, label: geojson.product_label, features }));
            applyTimestamps(geojson);
            const cacheNote = geojson.source_available === false
                ? ' — showing cached data; WPC source is temporarily unavailable.'
                : (geojson.stale ? ' — cached data may be stale.' : '');
            status.setMessage(
                `${geojson.product_label || `Day ${day}`} — ${features.length} `
                + `${group === 'mpd' ? 'active discussion(s)' : 'contour(s)'}.`
                + cacheNote,
                cacheNote ? 'error' : 'success',
            );
            pollForFreshCache();
        } catch (err) {
            if (err.name === 'AbortError' || !gate.isCurrent(request.sequence)) return;
            console.error('[wpc] load failed', err);
            onEmptyMessage?.(null);
            status.setMessage(`WPC load failed: ${err.message}`, 'error');
        }
    }

    async function loadCatalog() {
        return api.fetchJson('/api/data/wpc/catalog');
    }

    return Object.freeze({
        clear,
        destroy: clear,
        load,
        loadCatalog,
        setOpacity,
    });
}
