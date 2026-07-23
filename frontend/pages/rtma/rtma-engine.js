import { createRequestGate } from '../../core/api.js';

// RTMA engine: pre-rendered gradient overlays, city-value markers (colored
// text + wind barbs), frame discovery, and per-frame scrub rendering.
// Ported from js/rtma-engine.js + the monolith's RTMA render/points layer.

export const STREAM_MAX_HOURS = Object.freeze({
    rtma_hourly: 24,
    rtma_rapid_update: 6,
});

const RTMA_REGIONS = Object.freeze(['CONUS', 'AK', 'HI', 'PR']);
const VALUE_MARKER_OFFSET_X_PX = 0;
const VALUE_MARKER_OFFSET_Y_PX = -15;
const INTEGER_LABEL_PRODUCTS = new Set(['temperature', 'dew_point', 'apparent_temperature']);

export function dataRegionForMapRegion(selectedRegion) {
    const region = String(selectedRegion || 'CONUS').toUpperCase();
    return RTMA_REGIONS.includes(region) ? region : 'CONUS';
}

export function staleThresholdMs(stream) {
    if (stream === 'rtma_rapid_update') return 3 * 60 * 60 * 1000;
    return 12 * 60 * 60 * 1000;
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

function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, (char) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[char]));
}

function haversineKm(lat1, lon1, lat2, lon2) {
    const R = 6371;
    const dLat = (lat2 - lat1) * Math.PI / 180;
    const dLon = (lon2 - lon1) * Math.PI / 180;
    const a = Math.sin(dLat / 2) ** 2
        + Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.sin(dLon / 2) ** 2;
    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

// No two accepted items closer than minDistKm (rank-first order preserved).
function filterByMinDistKm(items, getLat, getLon, minDistKm) {
    if (!items.length || minDistKm <= 0) return items;
    const cellDeg = minDistKm / 111;
    const grid = new Map();
    const accepted = [];
    for (const item of items) {
        const lat = getLat(item);
        const lon = getLon(item);
        if (!Number.isFinite(lat) || !Number.isFinite(lon)) continue;
        const row = Math.floor(lat / cellDeg);
        const col = Math.floor(lon / cellDeg);
        let tooClose = false;
        outer: for (let dr = -2; dr <= 2; dr += 1) {
            for (let dc = -2; dc <= 2; dc += 1) {
                const bucket = grid.get(`${row + dr}:${col + dc}`);
                if (!bucket) continue;
                for (const [bLat, bLon] of bucket) {
                    if (haversineKm(lat, lon, bLat, bLon) < minDistKm) {
                        tooClose = true;
                        break outer;
                    }
                }
            }
        }
        if (!tooClose) {
            accepted.push(item);
            const key = `${row}:${col}`;
            const bucket = grid.get(key);
            if (bucket) bucket.push([lat, lon]);
            else grid.set(key, [[lat, lon]]);
        }
    }
    return accepted;
}

// Slider tops out at 2; base values yield the configured far-right minimum
// spacing after division by the density factor.
export function baseDistKm(zoom) {
    if (zoom >= 9) return 10;
    if (zoom === 8) return 20;
    if (zoom === 7) return 60;
    if (zoom >= 5) return 200;
    return 400;
}

// ── Legend HTML on the shared core legend tray ──────────────────────────────
export function rtmaLegendHtml(data) {
    const title = escapeHtml(data?.full_name || 'RTMA');
    const units = escapeHtml(data?.units || '');
    const anchors = (Array.isArray(data?.legend?.anchors) ? data.legend.anchors : [])
        .map((item) => Array.isArray(item)
            ? [Number(item[0]), item[1], item[2]]
            : [Number(item?.value), item?.color, item?.label])
        .filter(([value, color]) => Number.isFinite(value) && color);

    const header = `<div class="core-legend-header">
            <span class="core-legend-provider">RTMA</span>
            <div class="core-legend-heading"><div class="core-legend-title">${title}</div></div>
            <span class="core-legend-meta">${units || '—'}</span>
        </div>`;

    if (anchors.length) {
        const min = anchors[0][0];
        const max = anchors[anchors.length - 1][0];
        const range = Math.max(1, max - min);
        const stops = anchors.map(([value, color]) => (
            `${color} ${(((value - min) / range) * 100).toFixed(2)}%`
        )).join(', ');
        const ticks = anchors.map(([value, , label]) => {
            const pct = ((value - min) / range) * 100;
            const text = label ?? (Number.isInteger(value) ? String(value) : value.toFixed(1));
            return `<span class="core-legend-tick" style="left:${pct.toFixed(2)}%">${escapeHtml(text)}</span>`;
        }).join('');
        return `${header}
            <div class="core-legend-body">
                <div class="core-legend-colorbar" style="background: linear-gradient(to right, ${stops});"></div>
                <div class="core-legend-ticks">${ticks}</div>
            </div>`;
    }

    const hasRange = Number.isFinite(Number(data?.vmin)) && Number.isFinite(Number(data?.vmax));
    const body = hasRange
        ? `<div class="rtma-legend-range">${escapeHtml(String(data.vmin))} to ${escapeHtml(String(data.vmax))} ${units}</div>`
        : '';
    return `${header}<div class="core-legend-body">${body}</div>`;
}

export function createRtmaEngine({ api, mapCore, legend, status }) {
    const leaflet = mapCore.leaflet;
    const map = mapCore.map;
    const gate = createRequestGate();

    let gradientLayer = null;
    let pointLayer = null;
    let gradientOpacity = 0.9;
    let valueOpacity = 0.9;
    let density = 0.25;
    let showValues = false;

    let primaryPoints = [];
    let primaryUnits = '';
    let primaryProduct = '';
    let primaryLabel = '';
    let secondaryPoints = [];
    let secondaryUnits = '';
    let secondaryLabel = '';

    let renderSeq = 0;
    const frameCache = new Map();

    // ── Marker icons (zoom-responsive, ported from the shell) ───────────────
    function windDirectionBarbIcon(dirDeg) {
        const zoom = map?.getZoom() ?? 5;
        const t = Math.max(0, Math.min(1, (zoom - 5) / 4));
        const size = Math.round(22 + t * 18); // 22px @ z5 → 40px @ z9+
        const alpha = Math.max(0, Math.min(1, valueOpacity));
        const rot = ((dirDeg % 360) + 360) % 360;
        const svg =
            `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" `
            + `width="${size}" height="${size}" style="overflow:visible;opacity:${alpha};" `
            + `role="img" aria-label="Wind from ${Math.round(rot)}°">`
            + '<defs>'
            + '<filter id="wdb-shadow" x="-60%" y="-60%" width="220%" height="220%">'
            + '<feDropShadow dx="0" dy="0" stdDeviation="1.4" flood-color="black" flood-opacity="0.95"/>'
            + '</filter>'
            + '</defs>'
            + `<g transform="rotate(${rot},10,10)" filter="url(#wdb-shadow)">`
            + '<line x1="10" y1="18" x2="10" y2="7" stroke="white" stroke-width="2.5" stroke-linecap="round"/>'
            + '<polygon points="10,1 5,9 15,9" fill="white"/>'
            + '</g>'
            + '</svg>';
        return leaflet.divIcon({
            className: '',
            html: `<div style="width:${size}px;height:${size}px;">${svg}</div>`,
            iconSize: [size, size],
            iconAnchor: [
                Math.round(size / 2 - VALUE_MARKER_OFFSET_X_PX),
                Math.round(size - VALUE_MARKER_OFFSET_Y_PX),
            ],
        });
    }

    function coloredTextIcon(value, unit, forceInteger) {
        const label = forceInteger || unit === '°F' || unit === '%' || unit === 'kt'
            ? String(Math.round(value))
            : Number(value).toFixed(1);
        const alpha = Math.max(0, Math.min(1, valueOpacity));
        const zoom = map?.getZoom() ?? 5;
        const t = Math.max(0, Math.min(1, (zoom - 5) / 4));
        const fontSizePx = Math.round(16 + t * 22); // 16px @ z5 → 38px @ z9+
        const strokePx = Math.max(1, Math.round(fontSizePx * 0.1));
        const iconWidth = Math.max(32, Math.round(fontSizePx * (label.length * 0.62 + 0.8)));
        const iconHeight = Math.max(20, Math.round(fontSizePx * 1.25));
        return leaflet.divIcon({
            className: '',
            html: `<div style="opacity:${alpha};color:rgb(255,255,0);font-weight:800;font-size:${fontSizePx}px;line-height:1;font-family:Montserrat-ExtraBold, sans-serif;text-align:center;-webkit-text-stroke:${strokePx}px black;paint-order:stroke fill;">${label}</div>`,
            iconSize: [iconWidth, iconHeight],
            iconAnchor: [
                Math.round(iconWidth / 2 - VALUE_MARKER_OFFSET_X_PX),
                Math.round(iconHeight / 2 - VALUE_MARKER_OFFSET_Y_PX),
            ],
        });
    }

    // ── Point thinning + rendering ──────────────────────────────────────────
    function thinPoints(points) {
        if (!Array.isArray(points) || !points.length) return [];
        const zoom = map.getZoom();
        const minDistKm = baseDistKm(zoom) / density;
        const bounds = map.getBounds();
        const inView = points.filter((p) => bounds.contains([p.lat, p.lon]));
        return filterByMinDistKm(inView, (p) => p.lat, (p) => p.lon, minDistKm);
    }

    function clearPointLayer() {
        if (pointLayer && map.hasLayer(pointLayer)) map.removeLayer(pointLayer);
        pointLayer = null;
    }

    function renderPoints() {
        clearPointLayer();
        if (!showValues) return;
        if (!primaryPoints.length && !secondaryPoints.length) return;

        const markers = [];
        if (primaryPoints.length) {
            const isWindDir = primaryUnits === 'deg';
            const useIntegerLabels = INTEGER_LABEL_PRODUCTS.has(primaryProduct);
            thinPoints(primaryPoints).forEach((p) => {
                const icon = isWindDir
                    ? windDirectionBarbIcon(p.value)
                    : coloredTextIcon(p.value, primaryUnits, useIntegerLabels);
                const marker = leaflet.marker([p.lat, p.lon], { icon });
                const location = [p.city, p.state].filter(Boolean).join(', ') || 'Sample location';
                const value = isWindDir ? `${Math.round(p.value)}°` : `${p.value} ${primaryUnits}`.trim();
                marker.bindPopup(`<strong>${escapeHtml(location)}</strong><br>${escapeHtml(primaryLabel || primaryProduct)}: ${escapeHtml(value)}`);
                markers.push(marker);
            });
        }
        if (secondaryPoints.length) {
            const isWindDir = secondaryUnits === 'deg';
            thinPoints(secondaryPoints).forEach((p) => {
                const icon = isWindDir
                    ? windDirectionBarbIcon(p.value)
                    : coloredTextIcon(p.value, secondaryUnits, false);
                const marker = leaflet.marker([p.lat, p.lon], { icon });
                const location = [p.city, p.state].filter(Boolean).join(', ') || 'Sample location';
                const value = isWindDir ? `${Math.round(p.value)}°` : `${p.value} ${secondaryUnits}`.trim();
                marker.bindPopup(`<strong>${escapeHtml(location)}</strong><br>${escapeHtml(secondaryLabel || 'Value')}: ${escapeHtml(value)}`);
                markers.push(marker);
            });
        }
        if (markers.length) {
            pointLayer = leaflet.layerGroup(markers).addTo(map);
        }
    }

    // ── Layer management ────────────────────────────────────────────────────
    function clearGradientLayer() {
        if (gradientLayer && map.hasLayer(gradientLayer)) map.removeLayer(gradientLayer);
        gradientLayer = null;
    }

    function clear() {
        gate.cancel();
        renderSeq += 1;
        clearGradientLayer();
        clearPointLayer();
        primaryPoints = [];
        primaryUnits = '';
        primaryLabel = '';
        secondaryPoints = [];
        secondaryUnits = '';
        secondaryLabel = '';
        frameCache.clear();
        legend.clear();
    }

    function clearSecondary() {
        secondaryPoints = [];
        secondaryUnits = '';
        secondaryLabel = '';
        renderPoints();
    }

    function setGradientOpacity(value) {
        const parsed = parseFloat(value);
        if (!Number.isFinite(parsed)) return;
        gradientOpacity = parsed;
        gradientLayer?.setOpacity(gradientOpacity);
    }

    function setDensity(value) {
        const parsed = parseFloat(value);
        if (!Number.isFinite(parsed)) return;
        density = Math.max(0.01, Math.min(2, parsed));
        renderPoints();
    }

    function setShowValues(value) {
        showValues = !!value;
        if (!showValues) clearPointLayer();
        else renderPoints();
    }

    function boundsQuery() {
        const bounds = map.getBounds();
        return (
            `&south=${bounds.getSouth().toFixed(4)}`
            + `&west=${bounds.getWest().toFixed(4)}`
            + `&north=${bounds.getNorth().toFixed(4)}`
            + `&east=${bounds.getEast().toFixed(4)}`
        );
    }

    function viewportKey() {
        const bounds = map.getBounds();
        return [
            bounds.getSouth().toFixed(2),
            bounds.getWest().toFixed(2),
            bounds.getNorth().toFixed(2),
            bounds.getEast().toFixed(2),
        ].join(',');
    }

    function setGradientFromImage(imageUrl, bounds) {
        const leafletBounds = [[bounds[2], bounds[0]], [bounds[3], bounds[1]]];
        const oldLayer = gradientLayer;
        const newLayer = leaflet.imageOverlay(api.apiUrl(imageUrl), leafletBounds, {
            opacity: gradientOpacity,
            className: 'surface-gradient-overlay',
        }).addTo(map);
        if (oldLayer && map.hasLayer(oldLayer)) map.removeLayer(oldLayer);
        gradientLayer = newLayer;
    }

    function applyStatus({ title, stream, tsMs, note = '', tone = '' }) {
        status.setDataInfo({
            timestamp: Number.isFinite(tsMs) ? new Date(tsMs).toISOString() : null,
            provider: `NOAA ${stream || 'RTMA'}`,
            source: title,
        });
        status.setMessage(`RTMA ${title} valid ${formatValidTimeLabel(tsMs)}.${note}`, tone);
    }

    async function fetchPoints(selection, sourceDataKey, { signal } = {}) {
        const { region, stream, product } = selection;
        const url = `/api/data/rtma/points?region=${encodeURIComponent(region)}`
            + `&stream=${encodeURIComponent(stream)}&product=${encodeURIComponent(product)}`
            + (sourceDataKey ? `&source_data_key=${encodeURIComponent(sourceDataKey)}` : '')
            + boundsQuery();
        return api.fetchJson(url, { signal });
    }

    // ── Latest analysis (gradient overlay + optional value markers) ─────────
    async function loadLatest(selection) {
        const { region, stream, product } = selection;
        const request = gate.begin();
        status.setMessage(`Loading ${region} ${stream} ${product}…`);

        let usedPrerender = false;
        let pointsSourceDataKey = '';

        // Pre-rendered overlay first; wind direction is barbs-only (no raster).
        if (product !== 'wind_direction') {
            try {
                const overlayData = await api.fetchJson(
                    `/api/overlay/latest?family=rtma&region=${encodeURIComponent(region)}`
                    + `&stream=${encodeURIComponent(stream)}&product=${encodeURIComponent(product)}`,
                    { signal: request.signal },
                );
                if (!gate.isCurrent(request.sequence)) return;
                const imageUrl = overlayData?.render?.image_url;
                const bounds = overlayData?.bounds;
                pointsSourceDataKey = typeof overlayData?.source_data_key === 'string'
                    ? overlayData.source_data_key : '';
                if (imageUrl && Array.isArray(bounds) && bounds.length === 4) {
                    setGradientFromImage(imageUrl, bounds);
                    legend.setHtml(rtmaLegendHtml(overlayData));
                    const tsMs = timestampMs(overlayData?.timestamp);
                    const stale = Number.isFinite(tsMs) && (Date.now() - tsMs) > staleThresholdMs(stream);
                    applyStatus({
                        title: overlayData?.full_name || product,
                        stream,
                        tsMs,
                        note: stale ? ' — cached data may be stale.' : '',
                        tone: stale ? 'error' : 'success',
                    });
                    usedPrerender = true;
                }
            } catch (err) {
                if (err.name === 'AbortError') return;
                // fall through to the on-demand path
            }
        }

        if (!usedPrerender && product !== 'wind_direction') {
            try {
                const data = await api.fetchJson(
                    `/api/data/rtma?region=${encodeURIComponent(region)}&stream=${encodeURIComponent(stream)}`
                    + `&product=${encodeURIComponent(product)}${boundsQuery()}`,
                    { signal: request.signal },
                );
                if (!gate.isCurrent(request.sequence)) return;
                const b = data?.bounds;
                pointsSourceDataKey = typeof data?.source_data_key === 'string' ? data.source_data_key : '';
                if (data?.image_url && Array.isArray(b) && b.length === 4) {
                    setGradientFromImage(data.image_url, b);
                    legend.setHtml(rtmaLegendHtml(data));
                    const tsMs = timestampMs(data?.timestamp);
                    const stale = Number.isFinite(tsMs) && (Date.now() - tsMs) > staleThresholdMs(stream);
                    applyStatus({
                        title: data?.full_name || product,
                        stream,
                        tsMs,
                        note: stale ? ' — cached data may be stale.' : '',
                        tone: stale ? 'error' : 'success',
                    });
                    usedPrerender = true;
                }
            } catch (err) {
                if (err.name === 'AbortError') return;
                // points-only fallback below still runs
            }
        }

        try {
            const data = await fetchPoints(selection, pointsSourceDataKey, { signal: request.signal });
            if (!gate.isCurrent(request.sequence)) return;
            primaryPoints = Array.isArray(data.points) ? data.points : [];
            primaryUnits = data.units || '';
            primaryProduct = product;
            primaryLabel = data.full_name || product;
            renderPoints();
            if (!usedPrerender) {
                clearGradientLayer();
                legend.setHtml(rtmaLegendHtml(data));
                const tsMs = timestampMs(data?.timestamp);
                status.setDataInfo({
                    timestamp: Number.isFinite(tsMs) ? new Date(tsMs).toISOString() : null,
                    provider: `NOAA ${stream}`,
                    source: data?.full_name || product,
                });
                status.setMessage(`RTMA ${data?.full_name || product} — overlay cache not yet built (markers only).`);
            }
        } catch (err) {
            if (err.name === 'AbortError' || !gate.isCurrent(request.sequence)) return;
            console.error('[rtma] load failed', err);
            if (!usedPrerender) {
                clearGradientLayer();
                clearPointLayer();
                legend.clear();
                status.setMessage(`RTMA load failed: ${err.message}`, 'error');
            }
        }
    }

    // Secondary wind product (wind_speed + wind_direction selected together).
    async function loadSecondary(selection, product) {
        if (!showValues || !product) return;
        try {
            const data = await fetchPoints({ ...selection, product }, '');
            secondaryPoints = Array.isArray(data.points) ? data.points : [];
            secondaryUnits = data.units || '';
            secondaryLabel = data.full_name || product;
            renderPoints();
        } catch (_) { /* silent fail for the secondary product */ }
    }

    // Refresh primary markers for the current viewport (moveend with values on).
    async function reloadPoints(selection) {
        if (!showValues) return;
        try {
            const data = await fetchPoints(selection, '');
            primaryPoints = Array.isArray(data.points) ? data.points : [];
            primaryUnits = data.units || '';
            primaryProduct = selection.product;
            primaryLabel = data.full_name || selection.product;
            renderPoints();
        } catch (_) { /* transient viewport fetch */ }
    }

    // ── Scrubber frames ─────────────────────────────────────────────────────
    function normalizeFrame(raw, selection) {
        return {
            frame_key: raw.frame_key,
            source_data_key: raw.source_data_key || '',
            timestamp: raw.timestamp || '',
            region: selection.region,
            stream: selection.stream,
            product: selection.product,
            image_url: raw.image_url || null,
            bounds: raw.bounds || null,
        };
    }

    async function fetchFramesList(selection, hours, signal) {
        const { region, stream, product } = selection;
        let frames = [];
        let refreshing = false;
        try {
            const params = new URLSearchParams({
                family: 'rtma', region, stream, product, hours: String(hours),
            });
            const data = await api.fetchJson(`/api/overlay/frames?${params}`, {
                cache: 'no-store', signal,
            });
            refreshing = Boolean(data.refreshing);
            frames = (Array.isArray(data.frames) ? data.frames : [])
                .map((raw) => normalizeFrame(raw, selection));
        } catch (err) {
            if (err.name === 'AbortError') throw err;
            frames = [];
        }

        if (!frames.length) {
            const data = await api.fetchJson(
                `/api/data/rtma/frames?region=${encodeURIComponent(selection.region)}`
                + `&stream=${encodeURIComponent(selection.stream)}&product=${encodeURIComponent(selection.product)}`
                + `&max_hours=${encodeURIComponent(hours)}`,
                { signal },
            );
            frames = (Array.isArray(data.frames) ? data.frames : [])
                .map((raw) => normalizeFrame(raw, selection));
        }
        return { frames, refreshing };
    }

    async function loadFrames(selection, hours) {
        const request = gate.begin();
        frameCache.clear();
        try {
            const batch = await fetchFramesList(selection, hours, request.signal);
            if (!gate.isCurrent(request.sequence)) return null;
            return batch;
        } catch (err) {
            if (err.name === 'AbortError') return null;
            throw err;
        }
    }

    // Ungated: the auto-update poll must not abort an in-flight user load.
    async function fetchNewFrames(selection, hours, existingFrames) {
        const identity = (f) => `${f.source_data_key || f.frame_key || ''}|${f.timestamp || ''}`;
        const existing = new Set(existingFrames.map(identity));
        const batch = await fetchFramesList(selection, hours);
        return {
            frames: batch.frames.filter((frame) => !existing.has(identity(frame))),
            refreshing: batch.refreshing,
        };
    }

    // Pre-rendered overlay + points in parallel; points-only when the frame's
    // PNG is not yet cached (never triggers server-side GRIB parsing).
    async function fetchFramePayload(frame) {
        const { region, stream, product } = frame;
        const cacheKey = `${region}|${stream}|${product}|${frame.source_data_key || frame.frame_key}|${viewportKey()}`;
        const existing = frameCache.get(cacheKey);
        if (existing) return existing;

        const selection = { region, stream, product };
        if (frame.frame_key) {
            try {
                const [overlayData, pointsData] = await Promise.all([
                    api.fetchJson(
                        `/api/overlay/latest?family=rtma&region=${encodeURIComponent(region)}`
                        + `&stream=${encodeURIComponent(stream)}&product=${encodeURIComponent(product)}`
                        + `&frame_key=${encodeURIComponent(frame.frame_key)}`,
                    ),
                    fetchPoints(selection, frame.source_data_key).catch(() => null),
                ]);
                const payload = {
                    overlay: {
                        image_url: (overlayData.render || {}).image_url,
                        bounds: overlayData.bounds,
                        full_name: overlayData.full_name,
                        units: overlayData.units,
                        legend: overlayData.legend,
                        timestamp: overlayData.timestamp,
                        vmin: overlayData.vmin,
                        vmax: overlayData.vmax,
                    },
                    points: pointsData,
                    fromPrerender: true,
                };
                frameCache.set(cacheKey, payload);
                return payload;
            } catch (_) {
                // 404 → pre-render not yet cached; fall through to points-only.
            }
        }

        const pointsData = await fetchPoints(selection, frame.source_data_key);
        const payload = { overlay: null, points: pointsData, fromPrerender: false };
        frameCache.set(cacheKey, payload);
        return payload;
    }

    async function renderFrame(frame) {
        const seq = ++renderSeq;
        const payload = await fetchFramePayload(frame);
        if (seq !== renderSeq) return;
        const data = payload.overlay || payload.points || {};
        const pointsData = payload.points;

        if (payload.overlay?.image_url && Array.isArray(payload.overlay.bounds)) {
            // Preload before swapping so the new overlay is never transparent.
            await new Promise((resolve) => {
                const img = new Image();
                img.onload = resolve;
                img.onerror = resolve;
                img.src = api.apiUrl(payload.overlay.image_url);
            });
            if (seq !== renderSeq) return;
            setGradientFromImage(payload.overlay.image_url, payload.overlay.bounds);
        } else {
            clearGradientLayer();
        }

        primaryPoints = Array.isArray(pointsData?.points) ? pointsData.points : [];
        primaryUnits = pointsData?.units || '';
        primaryProduct = frame.product;
        primaryLabel = pointsData?.full_name || data?.full_name || frame.product;
        renderPoints();

        legend.setHtml(rtmaLegendHtml(pointsData || data));
        const tsMs = timestampMs(pointsData?.timestamp || data?.timestamp || frame.timestamp);
        const title = pointsData?.full_name || data?.full_name || frame.product;
        const renderNote = payload.fromPrerender ? 'pre-rendered' : 'cache pending';
        status.setDataInfo({
            timestamp: Number.isFinite(tsMs) ? new Date(tsMs).toISOString() : null,
            provider: `NOAA ${frame.stream}`,
            source: title,
        });
        status.setMessage(`RTMA ${title} (${renderNote}) ${formatValidTimeLabel(tsMs)}.`);
    }

    // Browser-cache prefetch of upcoming frame PNGs (fire-and-forget).
    function prefetchFrames(frames, index) {
        const count = Math.min(2, frames.length - index - 1);
        for (let i = 1; i <= count; i += 1) {
            const next = frames[index + i];
            if (next?.image_url) {
                const img = new Image();
                img.src = api.apiUrl(next.image_url);
            }
        }
    }

    return Object.freeze({
        clear,
        clearSecondary,
        destroy: clear,
        fetchNewFrames,
        loadFrames,
        loadLatest,
        loadSecondary,
        prefetchFrames,
        reloadPoints,
        renderFrame,
        renderPoints,
        setDensity,
        setGradientOpacity,
        setShowValues,
    });
}
