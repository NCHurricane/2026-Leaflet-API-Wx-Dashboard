import { createRequestGate } from '../../core/api.js';

// ── SPC catalog data (authoritative colors from SPC published legends) ──────
export const SPC_CAT_COLORS = Object.freeze({
    TSTM: { fill: '#b5dcb3', stroke: '#5a9e61' },
    MRGL: { fill: '#69bb6d', stroke: '#2d7a32' },
    SLGT: { fill: '#f5dd72', stroke: '#c8a000' },
    ENH: { fill: '#ff9d2e', stroke: '#c85a00' },
    MDT: { fill: '#ff4f4f', stroke: '#a00000' },
    HIGH: { fill: '#ff66ff', stroke: '#880088' },
});

export const SPC_PROB_COLORS = Object.freeze({
    '2': { fill: '#b5dcb3', stroke: '#5a9e61' },
    '5': { fill: '#69bb6d', stroke: '#2d7a32' },
    '10': { fill: '#f5dd72', stroke: '#c8a000' },
    '15': { fill: '#ff9d2e', stroke: '#c85a00' },
    '30': { fill: '#ff4f4f', stroke: '#a00000' },
    '45': { fill: '#ff66ff', stroke: '#880088' },
    '60': { fill: '#ff00ff', stroke: '#880088' },
    // CIG intensity levels (SPC March 2026 enhancement)
    CIG1: { fill: '#ffa040', stroke: '#cc5500' },
    CIG2: { fill: '#ff3300', stroke: '#aa0000' },
    CIG3: { fill: '#cc0099', stroke: '#880066' },
});

export const SPC_FIRE_COLORS = Object.freeze({
    'Elevated': { fill: '#FFBF80', stroke: '#FF7F00' },
    'Critical': { fill: '#FF8080', stroke: '#FF0000' },
    'Extremely Critical': { fill: '#FF80FF', stroke: '#FF00FF' },
    'Isolated': { fill: '#FFBF80', stroke: '#FF7F00' },
    'Scattered': { fill: '#FF8080', stroke: '#FF0000' },
});

export const SPC_REPORT_COLORS = Object.freeze({
    torn: '#ff4d4f',
    wind: '#26a9ff',
    hail: '#66e06a',
    other: '#f5d06b',
});

export const SPC_REPORT_FA_ICON = Object.freeze({
    torn: 'fa-solid fa-tornado',
    wind: 'fa-solid fa-wind',
    hail: 'fa-solid fa-caret-up',
});

export const CONVECTIVE_LABELS = Object.freeze({
    cat: 'Categorical',
    torn: 'Tornado Probabilistic',
    cigtorn: 'Tornado Significant',
    wind: 'Wind Probabilistic',
    cigwind: 'Wind Significant',
    hail: 'Hail Probabilistic',
    cighail: 'Hail Significant',
    prob: 'Probabilistic',
});

export const CIG_OVERLAY_BY_HAZARD = Object.freeze({
    torn: 'cigtorn',
    wind: 'cigwind',
    hail: 'cighail',
});

// Per-hazard probabilistic fill scales for the legend.
const PROB_HAZARD_COLORS = Object.freeze({
    torn: [
        ['60%', '#104E8B'], ['45%', '#912CEE'], ['30%', '#FF00FF'],
        ['15%', '#FF9696'], ['10%', '#FFEB7F'], ['5%', '#BD998A'], ['2%', '#79BA7A'],
    ],
    hail: [
        ['60%', '#912CEE'], ['45%', '#FF00FF'], ['30%', '#FF0000'],
        ['15%', '#FFEB7F'], ['5%', '#C5A392'],
    ],
    wind: [
        ['90%', '#00FFFF'], ['75%', '#104E8B'], ['60%', '#912CEE'], ['45%', '#FF00FF'],
        ['30%', '#FF0000'], ['15%', '#FFEB7F'], ['5%', '#C5A392'],
    ],
});

const HAZARD_TITLES = Object.freeze({ torn: 'Tornado', hail: 'Hail', wind: 'Wind' });

// How many CIG intensity levels exist for each hazard (hail has 1-2, others 1-3).
const HAZARD_CIG_LEVELS = Object.freeze({ torn: 3, hail: 2, wind: 3 });

const FIRE_HAZARDS = new Set(['windrh', 'dryt', 'drytcat', 'drytprob', 'windrhcat', 'windrhprob']);

const PRIMARY_TIMEOUT_MS = 10_000;
const SUPPLEMENTAL_TIMEOUT_MS = 20_000;
const STALE_CACHE_STATES = new Set(['backoff', 'failed', 'missing', 'stale', 'stopped']);

// ── Pure helpers shared with the renderer ───────────────────────────────────
export function isFireHazard(hazard) {
    return FIRE_HAZARDS.has(hazard);
}

export function isCigOverlayHazard(hazard) {
    // CIG hazards (cigtorn/cigwind/cighail) render with hatch patterns and
    // always require non-zero DN filtering (their .lyr.geojson includes a
    // placeholder DN=0 feature when no Sig threat exists).
    return hazard === 'cigtorn' || hazard === 'cigwind' || hazard === 'cighail';
}

export function nonZeroDn(feat) {
    const raw = feat?.properties?.DN ?? feat?.properties?.dn;
    const value = Number(raw);
    return Number.isFinite(value) ? value !== 0 : true;
}

export function featureIsCig(feat) {
    const label = String(feat?.properties?.LABEL || feat?.properties?.label || '').toUpperCase();
    const label2 = String(feat?.properties?.LABEL2 || feat?.properties?.label2 || '').toUpperCase();
    return /CIG\s*[123]/.test(label) || label2.includes('CONDITIONAL INTENSITY');
}

export function cigIntensity(feat) {
    const label = String(feat?.properties?.LABEL || feat?.properties?.label || '').toUpperCase();
    return Number((label.match(/CIG\s*([123])/) || [])[1] || 0);
}

export function convectiveLabel(hazard, day) {
    if (hazard === 'cat' && day >= 4) return 'Severe Weather Outlook';
    return CONVECTIVE_LABELS[hazard] || hazard;
}

export function allowedConvectiveHazards(day) {
    if (day <= 2) return ['cat', 'torn', 'cigtorn', 'wind', 'cigwind', 'hail', 'cighail'];
    if (day === 3) return ['cat', 'prob'];
    return ['cat'];
}

// Map the selected hazards to the single hazard whose prob legend should be
// shown. cigtorn/cigwind/cighail map back to their base hazard.
export function probLegendHazard(hazards) {
    const cigToBase = { cigtorn: 'torn', cigwind: 'wind', cighail: 'hail' };
    const probHazards = ['torn', 'wind', 'hail', 'prob'];
    for (const hazard of hazards) {
        if (probHazards.includes(hazard)) return hazard === 'prob' ? 'torn' : hazard;
        if (cigToBase[hazard]) return cigToBase[hazard];
    }
    return null;
}

export function reportTypeKey(eventText) {
    const event = String(eventText || '').toLowerCase();
    if (event.includes('torn')) return 'torn';
    if (event.includes('wind')) return 'wind';
    if (event.includes('hail')) return 'hail';
    return 'other';
}

// ── Point-in-polygon (bbox fast path + ray cast) ────────────────────────────
function featureBbox(feat) {
    if (feat._bbox) return feat._bbox;
    const coords = [];
    const geom = feat?.geometry;
    if (!geom) return null;
    const collect = (ring) => { for (const [x, y] of ring) coords.push([x, y]); };
    if (geom.type === 'Polygon') {
        for (const ring of (geom.coordinates || [])) collect(ring);
    } else if (geom.type === 'MultiPolygon') {
        for (const poly of (geom.coordinates || [])) for (const ring of poly) collect(ring);
    }
    if (!coords.length) return null;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const [x, y] of coords) {
        if (x < minX) minX = x; if (x > maxX) maxX = x;
        if (y < minY) minY = y; if (y > maxY) maxY = y;
    }
    feat._bbox = { minX, minY, maxX, maxY };
    return feat._bbox;
}

function ringContainsPoint(ring, lng, lat) {
    if (!Array.isArray(ring) || ring.length < 3) return false;
    let inside = false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
        const xi = ring[i]?.[0];
        const yi = ring[i]?.[1];
        const xj = ring[j]?.[0];
        const yj = ring[j]?.[1];
        if (![xi, yi, xj, yj].every(Number.isFinite)) continue;
        const intersects = ((yi > lat) !== (yj > lat))
            && (lng < (xj - xi) * (lat - yi) / ((yj - yi) || 1e-12) + xi);
        if (intersects) inside = !inside;
    }
    return inside;
}

function polygonContainsPoint(coords, lng, lat) {
    if (!Array.isArray(coords) || !coords.length) return false;
    if (!ringContainsPoint(coords[0], lng, lat)) return false;
    for (let i = 1; i < coords.length; i++) {
        if (ringContainsPoint(coords[i], lng, lat)) return false;
    }
    return true;
}

export function featureContainsLatLng(feat, latlng) {
    const geom = feat?.geometry;
    if (!geom || !latlng) return false;
    const { lng, lat } = latlng;
    if (!Number.isFinite(lng) || !Number.isFinite(lat)) return false;
    const bb = featureBbox(feat);
    if (bb && (lng < bb.minX || lng > bb.maxX || lat < bb.minY || lat > bb.maxY)) return false;
    if (geom.type === 'Polygon') return polygonContainsPoint(geom.coordinates, lng, lat);
    if (geom.type === 'MultiPolygon') {
        return (geom.coordinates || []).some((poly) => polygonContainsPoint(poly, lng, lat));
    }
    return false;
}

export function highestFeatureAtPoint(features, latlng, scoreFeature) {
    return (features || []).reduce((best, candidate) => {
        if (!featureContainsLatLng(candidate, latlng)) return best;
        if (!best) return candidate;
        return scoreFeature(candidate) > scoreFeature(best) ? candidate : best;
    }, null);
}

// ── Legend HTML (rendered into the shared core legend tray) ─────────────────
function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, (char) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[char]));
}

function swatchHtml(color, label) {
    return `<span class="spc-legend-item"><span class="spc-legend-swatch" style="background:${color}"></span><span class="spc-legend-text">${escapeHtml(label)}</span></span>`;
}

// Small inline swatch rendering the SVG hatch pattern used on the map, so the
// legend matches the polygon fill exactly.
function hatchSwatchHtml(intensity, label) {
    const size = 22;
    const patternId = `spc-legend-hatch-cig-${intensity}`;
    let patternBody = '';
    if (intensity === 1) {
        patternBody = `<pattern id="${patternId}" patternUnits="userSpaceOnUse" width="7.5" height="7.5" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="7.5" stroke="black" stroke-width="4" stroke-dasharray="3,4.5"/></pattern>`;
    } else if (intensity === 2) {
        patternBody = `<pattern id="${patternId}" patternUnits="userSpaceOnUse" width="9" height="9" patternTransform="rotate(-45)"><line x1="0" y1="0" x2="0" y2="9" stroke="black" stroke-width="4"/></pattern>`;
    } else {
        patternBody = `<pattern id="${patternId}" patternUnits="userSpaceOnUse" width="9" height="9" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="9" stroke="black" stroke-width="4"/><line x1="0" y1="0" x2="9" y2="0" stroke="black" stroke-width="4"/></pattern>`;
    }
    const svg = `<svg width="${size}" height="${size}" class="spc-legend-hatch-svg"><defs>${patternBody}</defs><rect width="${size}" height="${size}" fill="url(#${patternId})"/></svg>`;
    return `<span class="spc-legend-cig-item">${svg}${escapeHtml(label)}</span>`;
}

function legendShellHtml(title, meta, bodyHtml) {
    return `<div class="core-legend-header">
            <span class="core-legend-provider">SPC</span>
            <div class="core-legend-heading"><div class="core-legend-title">${escapeHtml(title)}</div></div>
            ${meta ? `<span class="core-legend-meta">${escapeHtml(meta)}</span>` : ''}
        </div>
        <div class="core-legend-body">${bodyHtml}</div>`;
}

function catLegendHtml() {
    const rows = [
        ['#ff66ff', 'High'], ['#ff4f4f', 'Moderate'], ['#ff9d2e', 'Enhanced'],
        ['#f5dd72', 'Slight'], ['#69bb6d', 'Marginal'], ['#b5dcb3', 'General Thunderstorms'],
    ].map(([color, label]) => swatchHtml(color, label)).join('');
    return legendShellHtml('Categorical Outlook', '', `<div class="spc-legend-flow">${rows}</div>`);
}

function fireLegendHtml(hazard) {
    const isDryt = hazard === 'dryt';
    const rows = (isDryt
        ? [['#FF8080', 'Scattered Dry T-Storm'], ['#FFBF80', 'Isolated Dry T-Storm']]
        : [['#FF80FF', 'Extremely Critical'], ['#FF8080', 'Critical'], ['#FFBF80', 'Elevated']]
    ).map(([color, label]) => swatchHtml(color, label)).join('');
    return legendShellHtml(
        `Fire Weather (${isDryt ? 'Dry T-Storm' : 'Wind/RH'})`, '',
        `<div class="spc-legend-flow">${rows}</div>`,
    );
}

function reportsLegendHtml(reportTypes) {
    const allTypes = ['torn', 'wind', 'hail'];
    const active = Array.isArray(reportTypes) && reportTypes.length ? reportTypes : allTypes;
    const labels = { torn: 'Tornado', wind: 'Wind', hail: 'Hail', other: 'Other' };
    const rows = active.map((type) => {
        const color = SPC_REPORT_COLORS[type] || SPC_REPORT_COLORS.other;
        const faClass = SPC_REPORT_FA_ICON[type];
        if (faClass) {
            return `<span class="spc-legend-item"><i class="spc-legend-icon ${faClass}" style="color:${color}" aria-hidden="true"></i><span class="spc-legend-text">${escapeHtml(labels[type] || type)}</span></span>`;
        }
        return swatchHtml(color, labels[type] || type);
    }).join('');
    return legendShellHtml('Storm Reports', '', `<div class="spc-legend-flow">${rows}</div>`);
}

function watchesLegendHtml(counts) {
    const rows = [
        counts.tornado ? swatchHtml('#ffe066', `Tornado Watch (${counts.tornado})`) : '',
        counts.severe ? swatchHtml('#ff8ec7', `Severe Thunderstorm Watch (${counts.severe})`) : '',
    ].filter(Boolean).join('');
    if (!rows) return '';
    return legendShellHtml('Watches In View', '', `<div class="spc-legend-flow">${rows}</div>`);
}

function probLegendHtml(hazard, day = null) {
    let title = HAZARD_TITLES[hazard] || 'Probabilistic';
    let colors = PROB_HAZARD_COLORS[hazard] || [];
    let cigLevels = HAZARD_CIG_LEVELS[hazard] || 0;

    // Day 3 Probabilistic: 60/45/30/15/5, intensity 1-2 only.
    if (day === 3) {
        colors = [
            ['60%', '#104E8B'], ['45%', '#912CEE'], ['30%', '#FF00FF'],
            ['15%', '#FF9696'], ['5%', '#BD998A'],
        ];
        cigLevels = 2;
    }
    // Days 4-8: only 30% and 15%, no intensity.
    if (day >= 4 && day <= 8) {
        colors = [['30%', '#FF00FF'], ['15%', '#FF9696']];
        cigLevels = 0;
        title = 'Severe Weather Outlook';
    }

    const probRow = colors.map(([label, color]) => swatchHtml(color, label)).join('');
    const intensityRow = Array.from({ length: cigLevels }, (_, i) => i + 1)
        .map((level) => hatchSwatchHtml(level, String(level)))
        .join('');
    let body = `<div class="spc-legend-section-label">Probability</div><div class="spc-legend-flow">${probRow}</div>`;
    if (intensityRow) {
        body += `<div class="spc-legend-section-label">Intensity</div><div class="spc-legend-flow">${intensityRow}</div>`;
    }
    return legendShellHtml(`${title} Outlook`, day ? `Day ${day}` : '', body);
}

// ── Timestamp helpers ───────────────────────────────────────────────────────
function timestampMs(value) {
    if (value == null) return null;
    if (value instanceof Date) return Number.isFinite(value.getTime()) ? value.getTime() : null;
    if (typeof value === 'number') {
        if (!Number.isFinite(value)) return null;
        return value > 1e12 ? value : value * 1000;
    }
    const parsed = Date.parse(String(value));
    return Number.isFinite(parsed) ? parsed : null;
}

function latestTimestampValue(values) {
    let latestValue = null;
    let latestMs = null;
    (values || []).forEach((value) => {
        const ms = timestampMs(value);
        if (!Number.isFinite(ms)) return;
        if (latestMs === null || ms > latestMs) {
            latestMs = ms;
            latestValue = value;
        }
    });
    return latestValue;
}

// ── Fetch helper: request-gate signal plus an independent timeout ───────────
function isAbortLikeError(err) {
    if (!err) return false;
    const name = String(err.name || '');
    if (name === 'AbortError' || name === 'TimeoutError') return true;
    const msg = String(err.message || '').toLowerCase();
    return msg.includes('abort') || msg.includes('timed out');
}

async function fetchJsonWithTimeout(api, path, parentSignal, timeoutMs) {
    const controller = new AbortController();
    const abortFromParent = () => controller.abort();
    if (parentSignal) {
        if (parentSignal.aborted) controller.abort();
        else parentSignal.addEventListener('abort', abortFromParent, { once: true });
    }
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
    try {
        return await api.fetchJson(path, { signal: controller.signal, cache: 'no-store' });
    } catch (err) {
        const parentAborted = !!(parentSignal && parentSignal.aborted);
        if (!parentAborted && controller.signal.aborted) {
            const timeoutErr = new Error(`Request timed out after ${Math.round(timeoutMs / 1000)}s`);
            timeoutErr.name = 'TimeoutError';
            throw timeoutErr;
        }
        throw err;
    } finally {
        clearTimeout(timeoutId);
        if (parentSignal) parentSignal.removeEventListener('abort', abortFromParent);
    }
}

// ── Engine ──────────────────────────────────────────────────────────────────
export function createSpcEngine({ api, renderer, legend, status, onCount, onEmptyMessage }) {
    const gate = createRequestGate();
    let watchFeatures = [];
    let lastSelection = null;

    function hasSupplemental(supplemental) {
        return supplemental.reportsEnabled || supplemental.mdsEnabled || supplemental.watchesEnabled;
    }

    function watchesInViewCounts() {
        const counts = { tornado: 0, severe: 0 };
        const seen = new Map();
        renderer.featuresInView(watchFeatures).forEach((feature) => {
            const properties = feature?.properties || {};
            const type = String(properties.watch_type || properties.event || '').toLowerCase();
            const kind = type.includes('tornado') ? 'tornado'
                : type.includes('severe thunderstorm') ? 'severe' : '';
            if (!kind) return;
            const key = String(
                properties.watch_number || properties.id || feature?.id
                || `${kind}:${properties.sent || ''}`,
            );
            seen.set(`${kind}:${key}`, kind);
        });
        seen.forEach((kind) => { counts[kind] += 1; });
        return counts;
    }

    function refreshWatchesLegend() {
        if (!lastSelection) return;
        const { hazards, supplemental } = lastSelection;
        if (!supplemental.watchesEnabled || hazards.length || !watchFeatures.length) return;
        legend.setHtml(watchesLegendHtml(watchesInViewCounts()));
    }

    function applyLegend(selection, effectiveDay) {
        const { hazards, supplemental } = selection;
        if (supplemental.reportsEnabled && !hazards.length) {
            legend.setHtml(reportsLegendHtml(supplemental.reportTypes));
        } else if (supplemental.watchesEnabled && !hazards.length) {
            legend.setHtml(watchesLegendHtml(watchesInViewCounts()));
        } else if (hazards.length === 1 && isFireHazard(hazards[0])) {
            legend.setHtml(fireLegendHtml(hazards[0]));
        } else if (hazards.includes('cat')) {
            legend.setHtml(effectiveDay >= 4 && effectiveDay <= 8
                ? probLegendHtml('cat', effectiveDay)
                : catLegendHtml());
        } else {
            const baseProbHazard = probLegendHazard(hazards);
            if (baseProbHazard) legend.setHtml(probLegendHtml(baseProbHazard, effectiveDay));
            else legend.clear();
        }
    }

    async function load(selection, { refreshAttempt = 0 } = {}) {
        const { day, fireDay, hazards, supplemental } = selection;
        const request = gate.begin();
        renderer.clear();
        watchFeatures = [];
        lastSelection = selection;

        if (!hazards.length && !hasSupplemental(supplemental)) {
            onCount?.(0);
            legend.clear();
            onEmptyMessage?.(null);
            status.setMessage('SPC selection cleared.');
            return;
        }

        // Fire hazards use the fire day selector; convective hazards the
        // convective day selector.
        const areFireHazards = hazards.length > 0 && hazards.every((h) => isFireHazard(h));
        const effectiveDay = areFireHazards ? fireDay : day;

        const loadingParts = [];
        if (hazards.length) loadingParts.push(`day ${effectiveDay} (${hazards.join(', ')})`);
        if (supplemental.reportsEnabled) {
            const typesLabel = supplemental.reportTypes.length === 3 ? 'all' : supplemental.reportTypes.join(',');
            loadingParts.push(`reports:${supplemental.reportsDays.join('+')}/${typesLabel}`);
        }
        if (supplemental.mdsEnabled) loadingParts.push('MDs');
        if (supplemental.watchesEnabled) {
            loadingParts.push(`watches:${supplemental.watchLayers.map((w) => `${w.type}-${w.mode}`).join(',')}`);
        }
        status.setMessage(`Loading SPC ${loadingParts.join(' + ')}…`);
        if (!hazards.length) onEmptyMessage?.('Loading SPC supplemental overlays…');

        try {
            const results = hazards.length
                ? await Promise.allSettled(hazards.map(async (hazard) => ({
                    hazard,
                    geojson: await fetchJsonWithTimeout(
                        api, `/api/data/spc?day=${effectiveDay}&hazard=${encodeURIComponent(hazard)}`,
                        request.signal, PRIMARY_TIMEOUT_MS,
                    ),
                })))
                : [];
            if (!gate.isCurrent(request.sequence)) return;

            const failures = results.filter((result) => result.status === 'rejected');
            failures.forEach((result) => {
                if (!isAbortLikeError(result.reason)) console.error('[spc] Load error:', result.reason);
            });
            const payloads = results
                .filter((result) => result.status === 'fulfilled' && result.value?.geojson)
                .map((result) => result.value);

            // Supplemental overlays: storm reports, MDs, watches.
            const reportsFeatureMap = new Map();
            const watchFeatureMap = new Map();
            let mdsGeojson = null;
            const supplementalFetches = [];
            const supplementalUpdatedValues = [];
            const reportsUpdatedValues = [];
            const watchesUpdatedValues = [];
            let supplementalTimedOut = false;

            if (supplemental.reportsEnabled) {
                const typeQueries = supplemental.reportTypes.length === 3 ? ['all'] : supplemental.reportTypes;
                supplemental.reportsDays.forEach((dayKey) => {
                    typeQueries.forEach((reportType) => {
                        supplementalFetches.push(fetchJsonWithTimeout(
                            api,
                            `/api/data/spc/reports?day=${encodeURIComponent(dayKey)}`
                            + `&report_type=${encodeURIComponent(reportType)}&report_mode=filtered`,
                            request.signal, SUPPLEMENTAL_TIMEOUT_MS,
                        ).then((geojson) => {
                            if (geojson?._updated) {
                                supplementalUpdatedValues.push(geojson._updated);
                                reportsUpdatedValues.push(geojson._updated);
                            }
                            (geojson?.features || []).forEach((feat) => {
                                const props = feat?.properties || {};
                                const coords = Array.isArray(feat?.geometry?.coordinates)
                                    ? feat.geometry.coordinates : [];
                                const dedupeKey = [
                                    dayKey, props.event || '', props.time || '',
                                    coords[0] ?? '', coords[1] ?? '',
                                    props.location || '', props.county || '', props.state || '',
                                ].join('|');
                                if (!reportsFeatureMap.has(dedupeKey)) {
                                    reportsFeatureMap.set(dedupeKey, {
                                        ...feat,
                                        properties: { ...props, report_day: props.report_day || dayKey },
                                    });
                                }
                            });
                        }));
                    });
                });
            }
            if (supplemental.mdsEnabled) {
                supplementalFetches.push(fetchJsonWithTimeout(
                    api, '/api/data/spc/active?product=mds',
                    request.signal, SUPPLEMENTAL_TIMEOUT_MS,
                ).then((geojson) => {
                    mdsGeojson = geojson;
                    if (geojson?._updated) supplementalUpdatedValues.push(geojson._updated);
                }));
            }
            if (supplemental.watchesEnabled) {
                supplemental.watchLayers.forEach((watchCfg) => {
                    supplementalFetches.push(fetchJsonWithTimeout(
                        api,
                        `/api/data/spc/active?product=watches`
                        + `&watch_mode=${encodeURIComponent(watchCfg.mode)}`
                        + `&watch_types=${encodeURIComponent(watchCfg.type)}`,
                        request.signal, SUPPLEMENTAL_TIMEOUT_MS,
                    ).then((geojson) => {
                        if (geojson?._updated) {
                            supplementalUpdatedValues.push(geojson._updated);
                            watchesUpdatedValues.push(geojson._updated);
                        }
                        (geojson?.features || []).forEach((feat) => {
                            const props = feat?.properties || {};
                            const dedupeKey = String(
                                feat?.id
                                || `${props.id || ''}|${props.watch_type || ''}|${watchCfg.type}|${watchCfg.mode}`,
                            );
                            if (!watchFeatureMap.has(dedupeKey)) watchFeatureMap.set(dedupeKey, feat);
                        });
                    }));
                });
            }
            if (supplementalFetches.length) {
                const supplementalResults = await Promise.allSettled(supplementalFetches);
                supplementalResults.filter((r) => r.status === 'rejected').forEach((r) => {
                    if (isAbortLikeError(r.reason)) {
                        if (String(r.reason?.name || '') === 'TimeoutError') supplementalTimedOut = true;
                        return;
                    }
                    console.error('[spc] Supplemental overlay load error:', r.reason);
                });
            }
            if (!gate.isCurrent(request.sequence)) return;

            const reportsGeojson = reportsFeatureMap.size ? {
                type: 'FeatureCollection',
                features: Array.from(reportsFeatureMap.values()),
                _updated: latestTimestampValue(reportsUpdatedValues),
            } : null;
            const watchesGeojson = watchFeatureMap.size ? {
                type: 'FeatureCollection',
                features: Array.from(watchFeatureMap.values()),
                _updated: latestTimestampValue(watchesUpdatedValues),
            } : null;
            watchFeatures = watchesGeojson?.features || [];

            if (!payloads.length && !hasSupplemental(supplemental)) {
                throw failures[0]?.reason || new Error('No SPC data returned');
            }

            // Count features and capture SPC "Less Than …" placeholder labels
            // so the empty-state overlay can surface SPC's own wording.
            const placeholderLabels = [];
            let count = 0;
            payloads.forEach(({ hazard, geojson }) => {
                const fire = isFireHazard(hazard);
                const cigOverlay = isCigOverlayHazard(hazard);
                const baseProbOrCat = ['cat', 'torn', 'wind', 'hail', 'prob'].includes(hazard);
                const visible = (geojson.features || []).filter((feat) => {
                    if (fire) return nonZeroDn(feat);
                    if (cigOverlay) {
                        if (!nonZeroDn(feat)) {
                            const label = String(feat?.properties?.LABEL || '').trim();
                            if (label) placeholderLabels.push(label);
                            return false;
                        }
                        return true;
                    }
                    if (baseProbOrCat && !nonZeroDn(feat)) {
                        const label = String(feat?.properties?.LABEL || '').trim();
                        if (label) placeholderLabels.push(label);
                        return false;
                    }
                    if (baseProbOrCat && featureIsCig(feat)) return false;
                    return true;
                });
                if (!cigOverlay) count += visible.length;
            });
            count += reportsGeojson?.features?.length || 0;
            count += watchesGeojson?.features?.length || 0;
            count += mdsGeojson?.features?.length || 0;

            renderer.render({
                outlooks: payloads,
                reports: reportsGeojson,
                watches: watchesGeojson,
                mds: mdsGeojson,
                effectiveDay,
            });

            applyLegend(selection, effectiveDay);
            onCount?.(count);

            const refreshingPayloads = payloads
                .map(({ geojson }) => geojson)
                .filter((geojson) => geojson?.cache_state === 'refreshing');
            const coldRefresh = count === 0 && refreshingPayloads.length > 0;
            if (count === 0) {
                const uniqueLabels = Array.from(new Set(placeholderLabels));
                const hazardLabels = hazards.map((h) => convectiveLabel(h, effectiveDay)).join(', ');
                let msg;
                if (coldRefresh) {
                    msg = `Warming SPC Day ${effectiveDay} ${hazardLabels || 'outlook'}…`;
                } else if (hazards.length > 0) {
                    msg = uniqueLabels.length
                        ? `SPC Day ${effectiveDay} ${hazardLabels}: ${uniqueLabels.join(' · ')}`
                        : `No SPC data available for Day ${effectiveDay} ${hazardLabels}`;
                } else {
                    if (supplementalTimedOut) {
                        msg = 'SPC supplemental overlays timed out. Try again.';
                    } else if (
                        supplemental.watchesEnabled
                        && !supplemental.mdsEnabled
                        && !supplemental.reportsEnabled
                    ) {
                        msg = 'No active tornado or severe thunderstorm watches.';
                    } else if (
                        supplemental.mdsEnabled
                        && !supplemental.watchesEnabled
                        && !supplemental.reportsEnabled
                    ) {
                        msg = 'No active mesoscale discussions.';
                    } else if (
                        supplemental.reportsEnabled
                        && !supplemental.watchesEnabled
                        && !supplemental.mdsEnabled
                    ) {
                        msg = 'No storm reports for the current selection.';
                    } else {
                        msg = 'No active SPC supplemental overlays for the current selection.';
                    }
                }
                onEmptyMessage?.(msg);
            } else {
                onEmptyMessage?.(null);
            }

            const statusBits = [];
            if (hazards.length) statusBits.push(`Day ${effectiveDay}: ${hazards.join(', ')}`);
            if (supplemental.reportsEnabled) {
                const typesLabel = supplemental.reportTypes.length === 3 ? 'all' : supplemental.reportTypes.join(',');
                statusBits.push(`Reports ${supplemental.reportsDays.join('+')}/${typesLabel}`);
            }
            if (supplemental.mdsEnabled) statusBits.push('MDs');
            if (supplemental.watchesEnabled) {
                statusBits.push(`Watches ${supplemental.watchLayers.map((w) => `${w.type}-${w.mode}`).join(',')}`);
            }
            const issuedRaw = latestTimestampValue(
                payloads.map(({ geojson }) => geojson?._issued),
            );
            const displayTimestampRaw = issuedRaw || latestTimestampValue([
                ...payloads.map(({ geojson }) => geojson?._updated),
                ...supplementalUpdatedValues,
            ]);
            const displayTimestampMs = timestampMs(displayTimestampRaw);
            const stale = payloads.some(({ geojson }) => (
                STALE_CACHE_STATES.has(String(geojson?.cache_state || '').toLowerCase())
            ));
            status.setDataInfo({
                timestamp: Number.isFinite(displayTimestampMs)
                    ? new Date(displayTimestampMs).toISOString()
                    : null,
                provider: 'NOAA SPC',
                source: issuedRaw ? 'SPC outlook issued' : 'SPC product time',
                stale,
            });
            status.setMessage(
                coldRefresh
                    ? `SPC ${statusBits.join(' + ')}: warming requested outlook…`
                    : `SPC ${statusBits.join(' + ')}: ${count} feature(s).${stale ? ' [STALE]' : ''}`,
                stale ? 'error' : 'success',
            );
            if (refreshingPayloads.length && refreshAttempt < 30) {
                const retryValues = refreshingPayloads
                    .map((geojson) => Number(geojson?.retry_after_seconds))
                    .filter((value) => Number.isFinite(value) && value > 0);
                const retryMs = Math.max(
                    500,
                    1000 * (retryValues.length ? Math.min(...retryValues) : 1),
                );
                window.setTimeout(() => {
                    if (gate.isCurrent(request.sequence)) {
                        load(selection, { refreshAttempt: refreshAttempt + 1 });
                    }
                }, retryMs);
            }
        } catch (err) {
            if (!gate.isCurrent(request.sequence) || isAbortLikeError(err)) return;
            console.error('[spc] Load error:', err);
            onEmptyMessage?.(null);
            status.setMessage(`SPC error: ${err.message}`, 'error');
        }
    }

    function clear() {
        gate.cancel();
        watchFeatures = [];
        lastSelection = null;
        renderer.clear();
        legend.clear();
        status.clear();
        onCount?.(0);
        onEmptyMessage?.(null);
    }

    return Object.freeze({
        load,
        clear,
        destroy: clear,
        refreshWatchesLegend,
    });
}
