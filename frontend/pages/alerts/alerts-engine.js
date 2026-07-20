import { ALERT_CATEGORIES, ALERT_COLORS, ALERT_DEFAULT_COLOR, LSR_CATEGORIES, SEVERE_EVENTS } from './alerts-config.js?v=20260719a';

const PULSE_ALERT_EVENTS = new Set(Object.values(SEVERE_EVENTS));

const CATEGORY_EVENTS = new Set(Object.values(ALERT_CATEGORIES).flat());

function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, (char) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[char]));
}

function eventColor(feature) {
    return ALERT_COLORS[feature?.properties?.event] || ALERT_DEFAULT_COLOR;
}

function vtecAction(feature) {
    const values = feature?.properties?.parameters?.VTEC;
    const match = Array.isArray(values) ? String(values[0] || '').match(/\/O\.([A-Z]{3})\./) : null;
    return match?.[1] || '';
}

function activeFeatures(features) {
    return (Array.isArray(features) ? features : []).filter((feature) => {
        const props = feature?.properties || {};
        const status = String(props.status || '').toLowerCase();
        const messageType = String(props.messageType || '').toLowerCase();
        const event = String(props.event || '').toLowerCase();
        const headline = String(props.headline || '').toLowerCase();
        if (status === 'test' || messageType === 'test' || event === 'test message' || headline.startsWith('test message')) return false;
        return messageType !== 'cancel' && !['CAN', 'EXP'].includes(vtecAction(feature));
    });
}

function matchesSelection(feature, selection) {
    const event = String(feature?.properties?.event || '');
    const categories = selection.categories || [];
    if (!categories.length) return false;
    const categoryMatch = !CATEGORY_EVENTS.has(event)
        || categories.some((category) => (ALERT_CATEGORIES[category] || []).includes(event));
    if (!categoryMatch) return false;
    if (Array.isArray(selection.eventTypes) && selection.eventTypes.length) {
        return selection.eventTypes.includes(event);
    }
    const subtype = Object.entries(SEVERE_EVENTS).find(([, name]) => name === event)?.[0];
    const subtypeFilteringActive = categories.includes('Severe Weather Warnings');
    return !subtype || !subtypeFilteringActive || selection.warningTypes?.includes(subtype);
}

export function classifyLsrEvent(eventText) {
    const event = String(eventText || '').toLowerCase();
    if (/torn|funnel|waterspout/.test(event)) return 'tornado';
    if (event.includes('hail')) return 'hail';
    if (/wind|wnd|downburst/.test(event)) return 'wind';
    if (/snow|blizzard|ice|sleet|freez|winter/.test(event)) return 'winter';
    if (event.includes('flood')) return 'flood';
    if (event.includes('rain')) return 'rain';
    if (/fire|smoke|wildfire/.test(event)) return 'fire';
    if (event.includes('heat')) return 'heat';
    return 'other';
}

function timestampMs(value, fallback = 0) {
    const parsed = Date.parse(value || '');
    return Number.isFinite(parsed) ? parsed : fallback;
}

function legendHeader(title) {
    return `<div class="core-legend-header"><span class="core-legend-provider">Alerts</span><div class="core-legend-heading"><div class="core-legend-title">${escapeHtml(title)}</div></div></div>`;
}

export function createAlertsEngine(options) {
    const { api, mapCore, legend, lsrLegend = null, status, onAlertCount, onLsrCount, onWarnings, onDetail, onNewAlert, onLsrDetail, onLsrDetailClose, shouldHandleAlertClick } = options;
    const { leaflet, map } = mapCore;
    const alertsPane = map.createPane('alerts-polygons');
    alertsPane.style.zIndex = '360';
    const lsrPane = map.createPane('alerts-lsr');
    lsrPane.style.zIndex = '470';
    let alertLayer = null;
    let lsrLayer = null;
    let fullBaseFeatures = [];
    let displayBaseFeatures = [];
    let alertCacheReady = false;
    let lsrBaseFeatures = [];
    let lsrCacheKey = '';
    let lsrCacheReady = false;
    let renderedAlerts = [];
    let renderedLsr = [];
    let selection = { categories: [], warningTypes: [] };
    let opacity = 0.75;
    let lsrOpacity = 1;
    let pulseEnabled = true;
    let liveSequence = 0;
    let lsrSequence = 0;
    let archiveSequence = 0;
    let knownAlertIds = null;
    let selectedLsrId = '';

    function featureId(feature) {
        const props = feature?.properties || {};
        return String(feature?.id || `${props.event || ''}|${props.sent || ''}|${props.areaDesc || ''}`);
    }

    function lsrFeatureId(feature) {
        const props = feature?.properties || {};
        return String(feature?.id || `${props.event || ''}|${props.time || ''}|${props.location || ''}`);
    }

    function openSelectedLsrPopup() {
        if (!selectedLsrId || onLsrDetail) return;
        lsrLayer?.eachLayer((layer) => { if (lsrFeatureId(layer.feature) === selectedLsrId) layer.openPopup?.(); });
    }

    function clearLsrSelection() {
        selectedLsrId = '';
        map.closePopup();
        onLsrDetailClose?.();
    }

    function replaceLayer(current, next) {
        if (next) next.addTo(map);
        if (current && map.hasLayer(current)) map.removeLayer(current);
        return next;
    }

    function alertStyle(feature) {
        return { pane: 'alerts-polygons', color: eventColor(feature), weight: 2, opacity: 1, fillColor: eventColor(feature), fillOpacity: opacity };
    }

    function syncAlertPulseLayer(layer, feature = layer?.feature) {
        const element = layer?.getElement?.();
        if (!element) return;
        const active = pulseEnabled && PULSE_ALERT_EVENTS.has(feature?.properties?.event);
        element.classList.toggle('alerts-alert-pulse', active);
        if (active) {
            element.style.setProperty('--alerts-pulse-fill-low', String(Math.max(0.08, opacity * 0.2)));
            element.style.setProperty('--alerts-pulse-fill-high', String(Math.max(0.35, opacity)));
        } else {
            element.style.removeProperty('--alerts-pulse-fill-low');
            element.style.removeProperty('--alerts-pulse-fill-high');
        }
    }

    function syncAlertPulseLayers() {
        alertLayer?.eachLayer((layer) => syncAlertPulseLayer(layer));
    }

    function tooltipHtml(feature) {
        const props = feature?.properties || {};
        return `<strong style="color:${eventColor(feature)}">${escapeHtml(props.event || 'Weather Alert')}</strong>${props.areaDesc ? `<br>${escapeHtml(props.areaDesc)}` : ''}`;
    }

    function buildAlertLayer(features) {
        return leaflet.geoJSON({ type: 'FeatureCollection', features }, {
            pane: 'alerts-polygons', style: alertStyle,
            onEachFeature(feature, layer) {
                layer.on('add', () => syncAlertPulseLayer(layer, feature));
                layer.bindTooltip(tooltipHtml(feature), { sticky: true, opacity: 0.95, className: 'alerts-hover-tip' });
                layer.on('click', (event) => {
                    if (shouldHandleAlertClick && !shouldHandleAlertClick(feature, event)) return;
                    if (event.originalEvent) leaflet.DomEvent.stopPropagation(event.originalEvent);
                    onDetail?.(feature);
                });
            },
        });
    }

    function renderAlerts() {
        const full = fullBaseFeatures.filter((feature) => matchesSelection(feature, selection));
        const display = displayBaseFeatures.filter((feature) => matchesSelection(feature, selection));
        renderedAlerts = full;
        alertLayer = replaceLayer(alertLayer, display.length ? buildAlertLayer(display) : null);
        onAlertCount?.(full.length);
        onWarnings?.(full);
        renderLegend();
    }

    function renderLegend() {
        const bounds = map.getBounds();
        const counts = new Map();
        renderedAlerts.forEach((feature) => {
            try {
                if (!leaflet.geoJSON(feature).getBounds().intersects(bounds)) return;
            } catch (_) { return; }
            const event = feature?.properties?.event || 'Other Alert';
            counts.set(event, (counts.get(event) || 0) + 1);
        });
        const alertRows = [...counts.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([event, count]) => (
            `<div class="core-legend-category"><span class="core-legend-color" style="background:${ALERT_COLORS[event] || ALERT_DEFAULT_COLOR}"></span><div class="core-legend-category-copy"><span class="core-legend-category-code">${escapeHtml(event)} (${count})</span></div></div>`
        )).join('');
        const lsrCounts = new Map();
        renderedLsr.forEach((feature) => {
            const category = classifyLsrEvent(feature?.properties?.event);
            lsrCounts.set(category, (lsrCounts.get(category) || 0) + 1);
        });
        const lsrRows = Object.entries(LSR_CATEGORIES).filter(([category]) => lsrCounts.has(category)).map(([category, [label, color, iconClass]]) => {
            const count = lsrCounts.get(category);
            return `<div class="core-legend-category alerts-legend-lsr-category"><span class="alerts-legend-icon" style="color:${color}"><i class="${iconClass}" aria-hidden="true"></i></span><div class="core-legend-category-copy"><span class="core-legend-category-code">${escapeHtml(label)} (${count})</span></div></div>`;
        }).join('');
        const alertSection = alertRows
            ? `<div class="alerts-legend-section"><div class="alerts-legend-label">Alerts in view</div><div class="core-legend-categories">${alertRows}</div></div>` : '';
        const lsrSection = lsrRows
            ? `<div class="alerts-legend-section"><div class="alerts-legend-label">Local storm reports</div><div class="core-legend-categories">${lsrRows}</div></div>` : '';
        if (lsrLegend) {
            if (alertSection) legend.setHtml(`${legendHeader('Active Alerts')}<div class="core-legend-body">${alertSection}</div>`);
            else legend.clear();
            if (lsrSection) lsrLegend.setHtml(`${legendHeader('Local Storm Reports')}<div class="core-legend-body">${lsrSection}</div>`);
            else lsrLegend.clear();
            return;
        }
        const sections = `${alertSection}${lsrSection}`;
        if (!sections) { legend.clear(); return; }
        legend.setHtml(`${legendHeader('Active Alerts')}<div class="core-legend-body">${sections}</div>`);
    }

    function requestParams(region, geometryMode) {
        const params = new URLSearchParams({ geometry_mode: geometryMode, zoom_bucket: map.getZoom() >= 8 ? 'local' : map.getZoom() >= 6 ? 'regional' : 'national' });
        if (region && !['CONUS', 'WORLD'].includes(region)) params.set('state', region);
        else {
            const bounds = map.getBounds();
            params.set('west', bounds.getWest().toFixed(4)); params.set('east', bounds.getEast().toFixed(4));
            params.set('south', bounds.getSouth().toFixed(4)); params.set('north', bounds.getNorth().toFixed(4));
        }
        return params;
    }

    async function loadLive(nextSelection, region, loadOptions = {}) {
        selection = { ...nextSelection };
        const seq = ++liveSequence;
        if (!selection.categories.length) { renderAlerts(); return; }
        if (!loadOptions.silent) status.setMessage('Loading active alerts…');
        try {
            const [full, display] = await Promise.all([
                api.fetchJson(`/api/data/alerts?${requestParams(region, 'full')}`, { cache: 'no-store' }),
                api.fetchJson(`/api/data/alerts?${requestParams(region, 'display')}`, { cache: 'no-store' }),
            ]);
            if (seq !== liveSequence) return;
            fullBaseFeatures = activeFeatures(full?.features);
            displayBaseFeatures = activeFeatures(display?.features || full?.features);
            alertCacheReady = true;
            renderAlerts();
            const nextIds = new Set(fullBaseFeatures.map(featureId));
            if (knownAlertIds && loadOptions.notifyNewAlerts !== false) renderedAlerts.forEach((feature) => {
                if (!knownAlertIds.has(featureId(feature))) onNewAlert?.(feature);
            });
            knownAlertIds = nextIds;
            const updated = full?._updated || display?._updated || new Date().toISOString();
            status.setDataInfo({ timestamp: updated, provider: 'NWS / IEM', source: full?._source || 'alerts cache' });
        } catch (error) {
            if (seq === liveSequence) status.setMessage(`Alerts unavailable: ${error.message}`, 'error');
        }
    }

    function setSelection(nextSelection) {
        selection = { ...nextSelection };
        renderAlerts();
        return alertCacheReady;
    }

    function buildLsrLayer(features) {
        return leaflet.geoJSON({ type: 'FeatureCollection', features }, {
            pane: 'alerts-lsr',
            pointToLayer(feature, latlng) {
                const category = classifyLsrEvent(feature?.properties?.event);
                const [, color, iconClass] = LSR_CATEGORIES[category];
                const size = Math.round(16 * Math.pow(1.1, Math.max(0, map.getZoom() - 7)));
                return leaflet.marker(latlng, { pane: 'alerts-lsr', opacity: lsrOpacity, icon: leaflet.divIcon({ className: '', html: `<i class="${iconClass}" style="color:${color};font-size:${size}px;-webkit-text-stroke:.5px #08111d;text-shadow:0 0 3px #000"></i>`, iconSize: [size, size], iconAnchor: [size / 2, size / 2] }) });
            },
            onEachFeature(feature, layer) {
                const props = feature?.properties || {};
                const meta = [props.location, props.state].filter(Boolean).join(', ');
                const category = classifyLsrEvent(props.event);
                const [, color] = LSR_CATEGORIES[category] || LSR_CATEGORIES.other;
                const title = `${props.event || 'Local Storm Report'}${props.magnitude_label ? ` (${props.magnitude_label})` : ''}`;
                layer.bindTooltip(`<strong style="color:${color}">${escapeHtml(title)}</strong>${meta ? `<br>${escapeHtml(meta)}` : ''}`, {
                    sticky: true, opacity: 0.95, className: 'alerts-hover-tip alerts-lsr-hover-tip',
                });
                if (onLsrDetail) {
                    layer.on('click', (event) => {
                        if (event.originalEvent) leaflet.DomEvent.stopPropagation(event.originalEvent);
                        selectedLsrId = lsrFeatureId(feature);
                        onLsrDetail(feature);
                    });
                } else {
                    layer.bindPopup(`<strong>${escapeHtml(props.event || 'Local Storm Report')}${props.magnitude_label ? ` (${escapeHtml(props.magnitude_label)})` : ''}</strong>${meta ? `<br>${escapeHtml(meta)}` : ''}${props.time ? `<br>${escapeHtml(new Date(props.time).toLocaleString())}` : ''}${props.remarks ? `<br><small>${escapeHtml(props.remarks)}</small>` : ''}`);
                }
            },
        });
    }

    async function loadLsr(categories, hours, loadOptions = {}) {
        const seq = ++lsrSequence;
        if (!categories?.length) {
            clearLsrSelection();
            renderedLsr = []; lsrLayer = replaceLayer(lsrLayer, null); onLsrCount?.(0); options.onLsrReports?.([]); renderLegend(); return;
        }
        const bounds = map.getBounds();
        const params = new URLSearchParams({ west: bounds.getWest().toFixed(4), east: bounds.getEast().toFixed(4), south: bounds.getSouth().toFixed(4), north: bounds.getNorth().toFixed(4), hours: String(hours || 24) });
        const cacheKey = [bounds.getWest(), bounds.getEast(), bounds.getSouth(), bounds.getNorth()]
            .map((value) => Number(value).toFixed(2)).concat(String(hours || 24)).join('|');
        const applySelection = () => {
            renderedLsr = lsrBaseFeatures.filter((feature) => categories.includes(classifyLsrEvent(feature?.properties?.event)));
            lsrLayer = replaceLayer(lsrLayer, renderedLsr.length ? buildLsrLayer(renderedLsr) : null);
            openSelectedLsrPopup();
            onLsrCount?.(renderedLsr.length); options.onLsrReports?.([...renderedLsr]); renderLegend();
        };
        if (lsrCacheReady && lsrCacheKey === cacheKey && !loadOptions.refresh) {
            applySelection();
            return;
        }
        try {
            const data = await api.fetchJson(`/api/data/alerts/lsr?${params}`, { cache: 'no-store' });
            if (seq !== lsrSequence) return;
            lsrBaseFeatures = Array.isArray(data?.features) ? data.features : [];
            lsrCacheKey = cacheKey;
            lsrCacheReady = true;
            applySelection();
        } catch (error) {
            if (seq === lsrSequence && !loadOptions.silent) status.setMessage(`Local Storm Reports unavailable: ${error.message}`, 'error');
        }
    }

    function sliceArchive(features, fromValue, toValue) {
        const start = timestampMs(fromValue); const end = timestampMs(toValue);
        const span = Math.max(60_000, end - start);
        const step = Math.max(60_000, Math.ceil(span / 599 / 60_000) * 60_000);
        const parsed = (features || []).map((feature) => ({ feature, start: timestampMs(feature?.properties?.onset || feature?.properties?.sent, start), end: timestampMs(feature?.properties?.expires, end) }));
        const frames = [];
        for (let time = start; time <= end; time += step) frames.push({ timestamp: new Date(time).toISOString(), features: parsed.filter((item) => item.start <= time && item.end > time).map((item) => item.feature) });
        return frames;
    }

    async function loadArchive(fromValue, toValue, region) {
        const seq = ++archiveSequence;
        liveSequence += 1; lsrSequence += 1;
        status.setMessage('Loading archived alerts…');
        const params = new URLSearchParams({ date_from: new Date(fromValue).toISOString(), date_to: new Date(toValue).toISOString() });
        if (region && !['CONUS', 'WORLD'].includes(region)) params.set('state', region);
        const data = await api.fetchJson(`/api/archive/alerts?${params}`, { cache: 'no-store' });
        if (seq !== archiveSequence) return [];
        const frames = sliceArchive(data?.features || [], data?.date_from || fromValue, data?.date_to || toValue);
        status.setDataInfo({ timestamp: data?.date_to || toValue, provider: 'IEM', source: data?._source || 'archive' });
        status.setMessage(`${frames.length} archive frame${frames.length === 1 ? '' : 's'} loaded.`);
        return frames;
    }

    function renderArchiveFrame(frame) {
        fullBaseFeatures = activeFeatures(frame?.features || []);
        displayBaseFeatures = fullBaseFeatures;
        renderAlerts();
        status.setDataInfo({ timestamp: frame?.timestamp, provider: 'IEM', source: 'alerts archive' });
    }

    function clear() {
        liveSequence += 1; lsrSequence += 1; archiveSequence += 1;
        fullBaseFeatures = []; displayBaseFeatures = []; renderedAlerts = []; renderedLsr = [];
        alertCacheReady = false; lsrBaseFeatures = []; lsrCacheKey = ''; lsrCacheReady = false;
        knownAlertIds = null;
        clearLsrSelection();
        alertLayer = replaceLayer(alertLayer, null); lsrLayer = replaceLayer(lsrLayer, null);
        onAlertCount?.(0); onLsrCount?.(0); onWarnings?.([]); options.onLsrReports?.([]); legend.clear(); lsrLegend?.clear();
    }

    return Object.freeze({
        clear, clearLsrSelection,
        destroy() { clear(); },
        getAlerts() { return [...renderedAlerts]; },
        loadArchive, loadLive, loadLsr, renderArchiveFrame, renderLegend, setSelection,
        setOpacity(value) { opacity = Math.max(0.1, Math.min(1, Number(value) || 0.75)); alertLayer?.setStyle(alertStyle); syncAlertPulseLayers(); return opacity; },
        setLsrOpacity(value) {
            lsrOpacity = Math.max(0.1, Math.min(1, Number(value) || 1));
            lsrLayer?.eachLayer((layer) => layer.setOpacity?.(lsrOpacity));
            return lsrOpacity;
        },
        setPulseEnabled(value) { pulseEnabled = Boolean(value); syncAlertPulseLayers(); return pulseEnabled; },
        showLsr(feature) {
            const coordinates = feature?.geometry?.coordinates;
            if (!Array.isArray(coordinates) || coordinates.length < 2) return;
            map.setView([Number(coordinates[1]), Number(coordinates[0])], Math.max(map.getZoom(), 9), { animate: false });
            selectedLsrId = lsrFeatureId(feature);
            if (onLsrDetail) onLsrDetail(feature);
            else openSelectedLsrPopup();
        },
        zoomTo(feature, zoomOptions = {}) {
            try {
                map.fitBounds(leaflet.geoJSON(feature).getBounds(), {
                    animate: false, padding: [28, 28],
                    ...(Number.isFinite(zoomOptions.maxZoom) ? { maxZoom: zoomOptions.maxZoom } : {}),
                });
            } catch (_) { /* invalid geometry */ }
        },
    });
}
