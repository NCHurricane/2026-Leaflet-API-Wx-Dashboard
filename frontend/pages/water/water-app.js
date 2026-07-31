import { apiUrl } from '../../core/api.js';
import { createLegendHost } from '../../core/legend.js';
import { createMapCore, REGION_LABELS } from '../../core/map-core.js';
import { renderProductNav } from '../../core/nav.js';
import { createSidebarTabs } from '../../core/sidebar-tabs.js';
import { loadDefaultSettings } from '../../core/settings.js';
import { createStatusReporter } from '../../core/status.js?v=20260725e';

const byId = (id) => document.getElementById(id);
const L = window.L;
const mapCore = createMapCore(byId('weather-map'), { region: 'CONUS', basemap: 'Dark' });
const map = mapCore.map;
const waterMarkersPane = map.createPane('water-markers');
waterMarkersPane.style.zIndex = '470';
const legend = createLegendHost(byId('weather-colorbar'), { align: 'left' });
const status = createStatusReporter({
    globalTimestamp: byId('global-timestamp'), message: byId('weather-water-status'),
    updated: byId('water-updated'), age: byId('water-age'),
    provider: byId('water-provider'), source: byId('water-source'),
});

let waterLayer = null;
let _waterStations = [];
let _waterRequestSeq = 0;
let _waterDetailRequestSeq = 0;
let _waterSelectedSiteId = '';
let _waterReloadTimer = null;
let _waterStationsInFlight = false;
let _waterPendingReload = false;
let _waterFloodFilter = 'all';
const WATER_FLOOD_RANKS = { action: 1, minor: 2, moderate: 3, major: 4 };

const _escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
}[char]));
function _asDate(value) { const date = value instanceof Date ? value : new Date(value); return Number.isNaN(date.getTime()) ? null : date; }
function _formatValidTimeLabel(value) { const date = _asDate(value); return date ? date.toLocaleString() : '—'; }
function _isTypeEnabled(type) { return type === 'water'; }
function setLegend(html) { if (html) legend.setHtml(html); else legend.clear(); }
function _setViewerTimestamp(value) { if (value) status.setDataInfo({ timestamp: value, provider: 'NOAA', source: 'Water observations' }); }
function _setReliability(_type, _label, source, timestamp) { status.setDataInfo({ timestamp, provider: 'NOAA', source }); }
function _setTimestampSource(_type, source, timestamp) { status.setDataInfo({ timestamp, provider: 'NOAA', source }); }

function _installWaterDetailDrag(root, handle) {
    if (!root || !handle) return;
    let drag = null;
    handle.addEventListener('pointerdown', (event) => {
        if (event.target.closest('button, a')) return;
        const parentRect = root.parentElement.getBoundingClientRect();
        const rect = root.getBoundingClientRect();
        root.style.left = `${rect.left - parentRect.left}px`;
        root.style.top = `${rect.top - parentRect.top}px`;
        root.style.right = 'auto';
        drag = { x: event.clientX, y: event.clientY, left: rect.left - parentRect.left, top: rect.top - parentRect.top };
        handle.setPointerCapture(event.pointerId);
        event.preventDefault();
    });
    handle.addEventListener('pointermove', (event) => {
        if (!drag) return;
        const parent = root.parentElement.getBoundingClientRect();
        const maxLeft = Math.max(0, parent.width - root.offsetWidth);
        const maxTop = Math.max(0, parent.height - root.offsetHeight);
        root.style.left = `${Math.max(0, Math.min(maxLeft, drag.left + event.clientX - drag.x))}px`;
        root.style.top = `${Math.max(0, Math.min(maxTop, drag.top + event.clientY - drag.y))}px`;
    });
    const end = () => { drag = null; };
    handle.addEventListener('pointerup', end);
    handle.addEventListener('pointercancel', end);
}

function _closeWaterDetail() {
    _waterDetailRequestSeq += 1;
    _waterSelectedSiteId = '';
    const root = byId('weather-water-detail');
    if (!root) return;
    root.replaceChildren();
    root.hidden = true;
}

function _openWaterDetail(html, siteId, color = '#38bdf8') {
    const root = byId('weather-water-detail');
    if (!root) return;
    _waterSelectedSiteId = siteId || '';
    root.style.setProperty('--water-detail-color', color);
    root.style.left = 'auto';
    root.style.right = '12px';
    root.style.top = '12px';
    root.innerHTML = html;
    root.hidden = false;
    root.querySelector('.water-detail-close')?.addEventListener('click', _closeWaterDetail);
    _installWaterDetailDrag(root, root.querySelector('.water-detail-head'));
}

function _waterDetailMessageHtml(title, message) {
    return `<div class="water-detail-head"><div><div class="water-detail-eyebrow">NOAA Water Observation</div><h2 id="water-detail-title">${_escapeHtml(title)}</h2></div><button class="water-detail-close" type="button" aria-label="Close water station detail">×</button></div>`
        + `<div class="water-detail-body"><p class="water-detail-message">${_escapeHtml(message)}</p></div>`;
}

function _ensureWaterLayer() {
    if (!waterLayer) waterLayer = L.layerGroup();
    return waterLayer;
}

function _setWaterStatus(message) {
    const el = byId('weather-water-status');
    if (el) el.textContent = message || '';
}

function _clearWaterLayer() {
    _waterRequestSeq += 1;
    if (_waterReloadTimer) {
        clearTimeout(_waterReloadTimer);
        _waterReloadTimer = null;
    }
    if (waterLayer) {
        waterLayer.clearLayers();
        if (map.hasLayer(waterLayer)) map.removeLayer(waterLayer);
    }
    _waterStations = [];
    _closeWaterDetail();
}

function _waterMarkerStyle(status) {
    if (status === 'coastal') return { fill: '#14b8a6', stroke: '#e0f2fe', weight: 2.6 };
    if (status === 'buoy') return { fill: '#2563eb', stroke: '#bfdbfe', weight: 2.6 };
    if (status === 'major') return { fill: '#a855f7', stroke: '#581c87' };
    if (status === 'moderate') return { fill: '#ef4444', stroke: '#991b1b' };
    if (status === 'minor') return { fill: '#f97316', stroke: '#9a3412' };
    if (status === 'action') return { fill: '#facc15', stroke: '#a16207' };
    switch (status) {
        case 'stale':
            return { fill: '#64748b', stroke: '#334155' };
        case 'missing':
            return { fill: '#f59e0b', stroke: '#92400e' };
        default:
            return { fill: '#38bdf8', stroke: '#0369a1' };
    }
}

function _waterLegendItems(items) {
    return items.map(([label, status]) => {
        const style = _waterMarkerStyle(status);
        const shadow = status === 'coastal'
            ? 'box-shadow:0 0 0 1px #0f766e;'
            : status === 'buoy'
            ? 'box-shadow:0 0 0 1px #1d4ed8;'
            : '';
        return `<div class="legend-item"><span class="legend-swatch" style="background:${style.fill};border-color:${style.stroke};border-radius:50%;${shadow}"></span><span class="legend-text">${label}</span></div>`;
    }).join('');
}

function _waterLegendHtml() {
    const networks = _selectedWaterNetworks();
    if (!networks.length) return '';
    const sections = [];
    if (networks.includes('river')) {
        const minFloodRank = WATER_FLOOD_RANKS[_waterFloodFilter] || 0;
        const riverLegendItems = [
            ['Major', 'major'],
            ['Moderate', 'moderate'],
            ['Minor', 'minor'],
            ['Action Stage', 'action'],
            ['No Flood / Unknown', 'normal'],
        ].filter(([, status]) => _waterFloodFilter === 'all' || _waterFloodRank(status) >= minFloodRank);
        const riverItems = _waterLegendItems(riverLegendItems);
        sections.push(`<section class="water-legend-section">
            <div class="water-legend-section-title">River Flood Stage</div>
            <div class="water-legend-row water-legend-river">${riverItems}</div>
        </section>`);
    }
    const otherItems = [];
    if (networks.includes('coastal')) otherItems.push(['Coastal Gauge', 'coastal']);
    if (networks.includes('buoy')) otherItems.push(['NDBC Buoy', 'buoy']);
    if (otherItems.length) {
        sections.push(`<section class="water-legend-section">
            <div class="water-legend-section-title">Other Networks</div>
            <div class="water-legend-row water-legend-other">${_waterLegendItems(otherItems)}</div>
        </section>`);
    }
    const networkCount = networks.length;
    return `<div class="core-legend-header">
            <span class="core-legend-provider">NOAA</span>
            <div class="core-legend-heading"><div class="core-legend-title">Water Observations</div></div>
            <span class="core-legend-meta">${networkCount} network${networkCount === 1 ? '' : 's'}</span>
        </div><div class="core-legend-body"><div class="water-legend-sections">${sections.join('')}</div></div>`;
}

function _selectedWaterNetworks() {
    return [...document.querySelectorAll('.weather-water-network-filter input[type="checkbox"]:checked')]
        .map((el) => String(el.value || '').trim().toLowerCase())
        .filter(Boolean);
}

function _isCoastalWaterStation(station) {
    return String(station?.network || '').toLowerCase() === 'coastal';
}

function _isBuoyWaterStation(station) {
    return String(station?.network || '').toLowerCase() === 'buoy';
}

function _waterNetworkLabel(station) {
    const network = String(station?.network || '').toLowerCase();
    if (network === 'coastal') return 'Coastal';
    if (network === 'buoy') return 'NDBC';
    return 'River';
}

function _waterCapabilityText(station) {
    const capabilities = Array.isArray(station?.capabilities) ? station.capabilities : [];
    if (capabilities.length) return capabilities.join(', ');
    const type = String(station?.station_type || '').replace(/_/g, ' ').trim();
    return type ? _waterCategoryText(type) : '';
}

function _waterRequestBbox() {
    const bounds = map.getBounds();
    const south = Math.max(-90, bounds.getSouth());
    const north = Math.min(90, bounds.getNorth());
    const rawWest = bounds.getWest();
    const rawEast = bounds.getEast();
    const span = rawEast - rawWest;
    const west = span >= 360 ? -180 : Math.max(-180, rawWest);
    const east = span >= 360 ? 180 : Math.min(180, rawEast);
    return [west, south, east, north].map((value) => value.toFixed(4)).join(',');
}

function _waterReadingText(station, key) {
    const reading = station?.readings?.[key];
    if (!reading || reading.value == null) return '—';
    const value = Number(reading.value);
    const formatted = Number.isFinite(value)
        ? value.toLocaleString(undefined, { maximumFractionDigits: key === 'flow' ? 0 : 2 })
        : String(reading.value);
    return `${formatted} ${reading.units || ''}`.trim();
}

function _waterReadingRow(station, key, label) {
    const text = _waterReadingText(station, key);
    return text && text !== '—' ? [label, text] : null;
}

function _waterLatestTimestamp(station) {
    const times = Object.values(station?.readings || {})
        .map((reading) => _asDate(reading?.timestamp))
        .filter(Boolean)
        .sort((a, b) => b.getTime() - a.getTime());
    return times[0] || null;
}

function _waterCategoryText(value) {
    const text = String(value || '').replace(/_/g, ' ').trim();
    if (!text) return '';
    return text.replace(/\b\w/g, (char) => char.toUpperCase());
}

function _waterFloodRank(category) {
    const cat = String(category || '').toLowerCase();
    if (cat.includes('major')) return 4;
    if (cat.includes('moderate')) return 3;
    if (cat.includes('minor')) return 2;
    if (cat.includes('action')) return 1;
    return 0;
}

function _applyWaterFloodFilter(stations) {
    if (_waterFloodFilter === 'all') return stations;
    const minRank = WATER_FLOOD_RANKS[_waterFloodFilter] || 0;
    return stations.filter((s) =>
        _isCoastalWaterStation(s) ||
        _isBuoyWaterStation(s) ||
        _waterFloodRank(s.observed_category) >= minRank,
    );
}

function _waterStageGaugeHtml(station) {
    const reading = station?.readings?.stage;
    const categories = station?.flood?.categories || {};
    const current = reading?.value != null ? Number(reading.value) : null;
    if (!Number.isFinite(current)) return '';
    const THRESH = [
        { key: 'action',   color: '#facc15', label: 'Act' },
        { key: 'minor',    color: '#f97316', label: 'Min' },
        { key: 'moderate', color: '#ef4444', label: 'Mod' },
        { key: 'major',    color: '#a855f7', label: 'Maj' },
    ];
    const parsed = THRESH
        .map((t) => ({ ...t, stage: Number(categories[t.key]?.stage) }))
        .filter((t) => Number.isFinite(t.stage));
    if (!parsed.length) return '';
    const maxThreshold = parsed[parsed.length - 1].stage;
    const scaleMax = Math.max(current * 1.1, maxThreshold * 1.15, 1);
    const pct = (val) => `${Math.min(100, Math.max(0, (val / scaleMax) * 100)).toFixed(1)}%`;
    let zones = `<div class="wx-stage-zone" style="left:0;width:${pct(parsed[0].stage)};background:#38bdf830;"></div>`;
    for (let i = 0; i < parsed.length; i++) {
        const start = parsed[i].stage;
        const end = i + 1 < parsed.length ? parsed[i + 1].stage : scaleMax;
        zones += `<div class="wx-stage-zone" style="left:${pct(start)};width:${pct(end - start)};background:${parsed[i].color}50;"></div>`;
    }
    const marker = `<div class="wx-stage-marker" style="left:${pct(current)};"></div>`;
    const units = reading?.units || 'ft';
    const threshText = parsed.map((t) => `${t.label}:${t.stage.toFixed(1)}`).join('  ');
    return `<div class="wx-stage-gauge">`
        + `<div class="wx-stage-bar">${zones}${marker}</div>`
        + `<div class="wx-stage-summary">`
        + `<span class="wx-stage-cur">&#9650; ${current.toFixed(2)} ${units}</span>`
        + `<span class="wx-stage-thresh">${threshText}</span>`
        + `</div></div>`;
}

function _waterBuoyCardHtml(station) {
    const readings = station?.readings || {};
    const rt = (key) => {
        const rd = readings[key];
        if (!rd || rd.value == null) return null;
        const value = Number(rd.value);
        const formatted = Number.isFinite(value)
            ? value.toLocaleString(undefined, { maximumFractionDigits: 1 })
            : String(rd.value);
        return `${formatted}${rd.units ? ' ' + rd.units : ''}`;
    };
    const windDir = readings.wind_direction?.value != null
        ? `${Number(readings.wind_direction.value).toFixed(0)}°T` : null;
    const waveDir = readings.mean_wave_direction?.value != null
        ? `${Number(readings.mean_wave_direction.value).toFixed(0)}°T` : null;
    const groups = [
        { label: 'Wind',  items: [['Speed', rt('wind_speed')], ['Gust', rt('wind_gust')], ['Dir', windDir]] },
        { label: 'Waves', items: [['Height', rt('wave_height')], ['Period', rt('dominant_wave_period')], ['Dir', waveDir]] },
        { label: 'Atmos', items: [['Pressure', rt('pressure')], ['Tendency', rt('pressure_tendency')]] },
        { label: 'Temp',  items: [['Air', rt('air_temperature')], ['Water', rt('water_temperature')], ['Dew Pt', rt('dewpoint')]] },
        { label: 'Other', items: [['Visibility', rt('visibility')], ['Tide', rt('tide')]] },
    ]
        .map((g) => ({ ...g, items: g.items.filter(([, v]) => v != null) }))
        .filter((g) => g.items.length);
    if (!groups.length) return '';
    return `<div class="wx-buoy-card">`
        + groups.map((g) =>
            `<div class="wx-buoy-group">`
            + `<span class="wx-buoy-group-label">${_escapeHtml(g.label)}</span>`
            + `<dl class="wx-storm-popup-grid">`
            + g.items.map(([l, v]) => `<dt>${_escapeHtml(l)}</dt><dd>${_escapeHtml(v)}</dd>`).join('')
            + `</dl></div>`,
        ).join('')
        + `</div>`;
}

function _waterPopupHydrograph(station) {
    const pageUrl = station?.source_url || '';
    const hydrographUrl = station?.floodcat_hydrograph_url || station?.hydrograph_url || '';
    if (hydrographUrl && pageUrl) {
        return `<a class="wx-water-hydrograph-link" href="${_escapeHtml(pageUrl)}" target="_blank" rel="noopener" title="Open NOAA gauge page">`
            + `<img class="wx-water-hydrograph" src="${_escapeHtml(hydrographUrl)}" alt="Hydrograph for ${_escapeHtml(station?.name || station?.site_id || 'gauge')}" loading="lazy">`
            + `</a>`;
    }
    if (!pageUrl) return '';
    const sourceLabel = station?.source === 'NOAA NDBC'
        ? 'NOAA NDBC station page'
        : station?.source === 'NOAA CO-OPS'
        ? 'NOAA Tides & Currents station page'
        : station?.source === 'NOAA NWPS'
        ? 'NOAA NWPS gauge page'
        : 'NOAA river gauge page';
    return `<a class="wx-water-detail-link" href="${_escapeHtml(pageUrl)}" target="_blank" rel="noopener">${_escapeHtml(sourceLabel)}</a>`;
}

function _waterStationDetailHtml(station) {
    if (!station) return '';
    const isCoastal = _isCoastalWaterStation(station);
    const isBuoy = _isBuoyWaterStation(station);
    const latest = _waterLatestTimestamp(station);
    const updatedDate = latest || _asDate(station.updated);
    const updated = updatedDate ? _formatValidTimeLabel(updatedDate.getTime()) : 'No current value';
    const rows = [
        ['Site', station.nwps_lid || station.coops_id || station.ndbc_id || station.site_id || ''],
        ['Network', _waterNetworkLabel(station)],
        ['Type', _waterCapabilityText(station)],
        ['Waterbody', station.waterbody],
        ['Stage', (isCoastal || isBuoy) ? '' : _waterReadingText(station, 'stage')],
        ['Observed', (isCoastal || isBuoy) ? '' : _waterCategoryText(station.observed_category)],
        isCoastal ? _waterReadingRow(station, 'water_level', 'Water Level') : null,
        isCoastal ? _waterReadingRow(station, 'current_speed', 'Speed') : null,
        isCoastal ? _waterReadingRow(station, 'current_direction', 'Direction') : null,
        ['Updated', updated],
        ['WFO / RFC', [station.wfo, station.rfc].filter(Boolean).join(' / ')],
        ['Affiliation', station.affiliation],
        ['County', [station.county, station.state].filter(Boolean).join(', ')],
        ['State', isCoastal ? station.state : ''],
    ]
        .filter(Boolean)
        .filter((row) => row[1])
        .map(([label, value]) => `<dt>${_escapeHtml(label)}</dt><dd>${String(value).includes('<br>') ? value : _escapeHtml(value)}</dd>`)
        .join('');
    return `<div class="water-detail-head"><div><div class="water-detail-eyebrow">NOAA ${_escapeHtml(_waterNetworkLabel(station))} Observation</div><h2 id="water-detail-title">${_escapeHtml(station.name || station.site_id)}</h2></div><button class="water-detail-close" type="button" aria-label="Close water station detail">×</button></div>`
        + `<div class="water-detail-body"><dl class="wx-storm-popup-grid">${rows}</dl>`
        + (!isBuoy && !isCoastal ? _waterStageGaugeHtml(station) : '')
        + (isBuoy ? _waterBuoyCardHtml(station) : '')
        + _waterPopupHydrograph(station)
        + `</div>`;
}

async function _loadWaterStationDetail(siteId, station) {
    if (!siteId) return;
    const requestSeq = ++_waterDetailRequestSeq;
    const markerStyle = _waterMarkerStyle(_waterMarkerStatus(station));
    _openWaterDetail(
        _waterDetailMessageHtml(station?.name || siteId, 'Loading latest station details…'),
        siteId,
        markerStyle.fill,
    );
    try {
        const resp = await fetch(apiUrl(`/api/water/stations/${encodeURIComponent(siteId)}`), { cache: 'no-store' });
        if (requestSeq !== _waterDetailRequestSeq || !_isTypeEnabled('water')) return;
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        if (data?.station) {
            const detailStyle = _waterMarkerStyle(_waterMarkerStatus(data.station));
            _openWaterDetail(_waterStationDetailHtml(data.station), siteId, detailStyle.fill);
        }
    } catch (err) {
        if (requestSeq !== _waterDetailRequestSeq) return;
        _setWaterStatus(`Water station unavailable: ${err.message}`);
        _openWaterDetail(_waterDetailMessageHtml(station?.name || siteId, `Station unavailable: ${err.message}`), siteId, markerStyle.fill);
    }
}

function _waterMarkerStatus(station) {
    if (_isCoastalWaterStation(station)) return 'coastal';
    if (_isBuoyWaterStation(station)) return 'buoy';
    const category = String(station?.observed_category || '').toLowerCase();
    if (category.includes('major')) return 'major';
    if (category.includes('moderate')) return 'moderate';
    if (category.includes('minor')) return 'minor';
    if (category.includes('action')) return 'action';
    return 'normal';
}

function _renderWaterStations(stations) {
    const layer = _ensureWaterLayer();
    layer.clearLayers();
    _waterStations = Array.isArray(stations) ? stations : [];
    _applyWaterFloodFilter(_waterStations).forEach((station) => {
        const lat = Number(station.lat);
        const lon = Number(station.lon);
        if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
        const style = _waterMarkerStyle(_waterMarkerStatus(station));
        const marker = L.circleMarker([lat, lon], {
            pane: 'water-markers',
            radius: 5,
            color: style.stroke,
            weight: style.weight || 1.6,
            fillColor: style.fill,
            fillOpacity: 0.9,
        });
        const isCoastal = _isCoastalWaterStation(station);
        const isBuoy = _isBuoyWaterStation(station);
        marker.bindTooltip(
            isCoastal
                ? `<strong>${_escapeHtml(station.name || station.site_id)}</strong><br>${_escapeHtml(_waterCapabilityText(station) || 'Coastal Gauge')}`
                : isBuoy
                ? `<strong>${_escapeHtml(station.name || station.site_id)}</strong><br>${_escapeHtml(_waterReadingText(station, 'wave_height'))} waves`
                : `<strong>${_escapeHtml(station.name || station.site_id)}</strong><br>Stage ${_escapeHtml(_waterReadingText(station, 'stage'))}`,
            { direction: 'top', className: 'city-name-label' },
        );
        marker.on('click', () => _loadWaterStationDetail(station.site_id, station));
        marker.addTo(layer);
    });
    if (_isTypeEnabled('water') && !map.hasLayer(layer)) layer.addTo(map);
}

async function _loadWaterStations({ force = false } = {}) {
    if (!_isTypeEnabled('water')) return;
    if (_waterStationsInFlight) {
        _waterPendingReload = true;
        return;
    }
    const bbox = _waterRequestBbox();
    const requestSeq = ++_waterRequestSeq;
    _waterStationsInFlight = true;
    _waterPendingReload = false;
    _setWaterStatus('Loading NOAA water stations...');
    try {
        const params = new URLSearchParams({
            bbox,
            max_sites: '15000',
            networks: _selectedWaterNetworks().join(','),
        });
        if (force) params.set('_', String(Date.now()));
        const resp = await fetch(apiUrl(`/api/water/stations?${params.toString()}`), { cache: 'no-store' });
        if (requestSeq !== _waterRequestSeq || !_isTypeEnabled('water')) return;
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        const stations = Array.isArray(data?.stations) ? data.stations : [];
        _renderWaterStations(stations);
        const totalAvailable = Number(data?.total_available || stations.length);
        const cachePrefix = data?.cache_state === 'refreshing' ? 'Cache warming: ' : '';
        const staleSuffix = data?.stale ? ' Cache may be stale.' : '';
        const selectedNetworks = _selectedWaterNetworks();
        const networkLabel = selectedNetworks.length
            ? selectedNetworks.map((value) => (
                value === 'river' ? 'river' : value === 'coastal' ? 'coastal' : 'NDBC'
            )).join(' + ')
            : 'selected';
        const countText = totalAvailable > stations.length
            ? `${stations.length} of ${totalAvailable} cached NOAA ${networkLabel} gauges shown.`
            : `${stations.length} cached NOAA ${networkLabel} gauge${stations.length === 1 ? '' : 's'} loaded.`;
        _setWaterStatus(`${cachePrefix}${data?.message || countText}${staleSuffix}`);
        const latest = stations.map(_waterLatestTimestamp).filter(Boolean).sort((a, b) => b.getTime() - a.getTime())[0];
        if (latest) {
            _setViewerTimestamp(latest.getTime());
            _setReliability('water', 'NOAA water gauges', 'Observed river, coastal, and marine stations', latest.getTime());
            _setTimestampSource('water', 'noaa_water_gauges', latest.getTime());
        }
        const retryAfterSeconds = Number(data?.retry_after_seconds);
        if (
            Number.isFinite(retryAfterSeconds)
            && retryAfterSeconds > 0
            && data?.cache_state !== 'fresh'
        ) {
            _scheduleWaterReload(Math.max(500, retryAfterSeconds * 1000));
        }
    } catch (err) {
        if (requestSeq !== _waterRequestSeq) return;
        _setWaterStatus(`NOAA river gauge data unavailable: ${err.message}`);
    } finally {
        _waterStationsInFlight = false;
        if (requestSeq === _waterRequestSeq && _waterPendingReload && _isTypeEnabled('water')) {
            _waterPendingReload = false;
            _scheduleWaterReload(900);
        }
    }
}

function _scheduleWaterReload(delayMs = 900) {
    if (!_isTypeEnabled('water')) return;
    if (_waterReloadTimer) clearTimeout(_waterReloadTimer);
    _waterReloadTimer = setTimeout(() => {
        _waterReloadTimer = null;
        _loadWaterStations();
    }, delayMs);
}

function _updateWaterFloodPillsVisibility() {
    const riverChecked = !!document.querySelector('.weather-water-network-filter input[value="river"]:checked');
    const row = byId('weather-water-flood-filter-row');
    if (row) row.hidden = !riverChecked;
    if (!riverChecked && _waterFloodFilter !== 'all') {
        _waterFloodFilter = 'all';
        document.querySelectorAll('.wx-water-flood-pill').forEach((pill) => {
            pill.setAttribute('aria-selected', String(pill.dataset.flood === 'all'));
        });
    }
}

async function initialize() {
    renderProductNav(byId('product-nav'), 'Water');
    createSidebarTabs(byId('water-sidebar-tabs'), { defaultTab: 'live' });
    const defaults = await loadDefaultSettings().catch(() => ({}));
    const cityDefaults = defaults?.global?.cityLabels || {};
    const regionSelect = byId('weather-water-region');
    regionSelect.replaceChildren(...Object.entries(REGION_LABELS).map(([code, label]) => new Option(label, code)));
    regionSelect.value = 'CONUS';
    L.DomEvent.disableClickPropagation(byId('weather-water-detail'));
    L.DomEvent.disableScrollPropagation(byId('weather-water-detail'));
    byId('weather-refresh-water').addEventListener('click', () => void _loadWaterStations({ force: true }));
    byId('weather-clear-water').addEventListener('click', () => { _clearWaterLayer(); _setWaterStatus('Water markers cleared.'); });
    regionSelect.addEventListener('change', () => {
        _clearWaterLayer();
        mapCore.fitRegion(regionSelect.value);
        _scheduleWaterReload(0);
    });
    document.querySelectorAll('.weather-water-network-filter input[type="checkbox"]').forEach((checkbox) => checkbox.addEventListener('change', () => {
        _updateWaterFloodPillsVisibility();
        setLegend(_waterLegendHtml());
        void _loadWaterStations({ force: true });
    }));
    byId('weather-water-flood-filters').addEventListener('click', (event) => {
        const pill = event.target.closest('.wx-water-flood-pill');
        if (!pill) return;
        _waterFloodFilter = pill.dataset.flood || 'all';
        document.querySelectorAll('.wx-water-flood-pill').forEach((item) => item.setAttribute('aria-selected', String(item === pill)));
        setLegend(_waterLegendHtml());
        _renderWaterStations(_waterStations);
        if (_waterFloodFilter !== 'all') _setWaterStatus(`Flood filter: ${_applyWaterFloodFilter(_waterStations).length} of ${_waterStations.length} river gauges shown.`);
    });
    byId('water-basemap').addEventListener('change', (event) => mapCore.setBasemap(event.target.value));
    const citySource = ['us', 'world'].includes(cityDefaults.source) ? cityDefaults.source : 'off';
    const cityDensityInput = byId('water-city-density');
    const cityFontSizeInput = byId('water-city-font-size');
    cityDensityInput.value = String(Number(cityDefaults.density) || 0.25);
    cityFontSizeInput.value = String(Number(cityDefaults.fontSize) || 0.6);
    document.querySelector(`input[name="water-cities-source"][value="${citySource}"]`).checked = true;
    const selectedCitySource = () => document.querySelector('input[name="water-cities-source"]:checked')?.value || 'off';
    const updateCityControls = () => {
        const source = selectedCitySource();
        const disabled = source === 'off';
        document.querySelectorAll('[data-city-adjustment]').forEach((row) => {
            row.classList.toggle('is-disabled', disabled);
            row.querySelector('input').disabled = disabled;
        });
        byId('water-city-density-label').textContent = `City Density (${Math.round(mapCore.getCityMinDistanceKm(source, cityDensityInput.value))} km)`;
        byId('water-city-font-size-label').textContent = `City Font Size (${Number(cityFontSizeInput.value).toFixed(2).replace(/\.?0+$/, '')})`;
    };
    document.querySelectorAll('input[name="water-cities-source"]').forEach((input) => input.addEventListener('change', () => {
        updateCityControls();
        void mapCore.setCitySource(selectedCitySource()).catch((error) => _setWaterStatus(`City overlay unavailable: ${error.message}`, 'error'));
    }));
    cityDensityInput.addEventListener('input', () => { mapCore.setCityDensity(cityDensityInput.value); updateCityControls(); });
    cityFontSizeInput.addEventListener('input', () => { mapCore.setCityFontSize(cityFontSizeInput.value); updateCityControls(); });
    mapCore.setCityDensity(cityDensityInput.value);
    mapCore.setCityFontSize(cityFontSizeInput.value);
    updateCityControls();
    void mapCore.setCitySource(citySource).catch((error) => _setWaterStatus(`City overlay unavailable: ${error.message}`, 'error'));
    document.querySelectorAll('[data-map-overlay]').forEach((input) => {
        input.addEventListener('change', () => void mapCore.setOverlayVisible(input.dataset.mapOverlay, input.checked));
        if (input.checked) void mapCore.setOverlayVisible(input.dataset.mapOverlay, true);
    });
    map.on('movestart zoomstart', _closeWaterDetail);
    map.on('moveend', () => _scheduleWaterReload());
    document.addEventListener('keydown', (event) => { if (event.key === 'Escape') _closeWaterDetail(); });
    _updateWaterFloodPillsVisibility();
    setLegend(_waterLegendHtml());
    await _loadWaterStations();
}

initialize().catch((error) => { console.error('[water] startup failed', error); status.setMessage(`Startup failed: ${error.message}`, 'error'); });
