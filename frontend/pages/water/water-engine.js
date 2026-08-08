const WATER_FLOOD_RANKS = Object.freeze({ action: 1, minor: 2, moderate: 3, major: 4 });
const DEFAULT_NETWORKS = Object.freeze(['river', 'coastal', 'buoy']);

const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
}[char]));

function asDate(value) {
    const date = value instanceof Date ? value : new Date(value);
    return Number.isNaN(date.getTime()) ? null : date;
}

function isCoastal(station) {
    return String(station?.network || '').toLowerCase() === 'coastal';
}

function isBuoy(station) {
    return String(station?.network || '').toLowerCase() === 'buoy';
}

function networkLabel(station) {
    if (isCoastal(station)) return 'Coastal';
    if (isBuoy(station)) return 'NDBC';
    return 'River';
}

function categoryText(value) {
    const text = String(value || '').replace(/_/g, ' ').trim();
    return text ? text.replace(/\b\w/g, (char) => char.toUpperCase()) : '';
}

function capabilityText(station) {
    const capabilities = Array.isArray(station?.capabilities) ? station.capabilities : [];
    if (capabilities.length) return capabilities.join(', ');
    const type = String(station?.station_type || '').replace(/_/g, ' ').trim();
    return type ? categoryText(type) : '';
}

function readingText(station, key) {
    const reading = station?.readings?.[key];
    if (!reading || reading.value == null) return '—';
    const value = Number(reading.value);
    const formatted = Number.isFinite(value)
        ? value.toLocaleString(undefined, { maximumFractionDigits: key === 'flow' ? 0 : 2 })
        : String(reading.value);
    return `${formatted} ${reading.units || ''}`.trim();
}

function readingRow(station, key, label) {
    const text = readingText(station, key);
    return text && text !== '—' ? [label, text] : null;
}

function latestTimestamp(station) {
    return Object.values(station?.readings || {})
        .map((reading) => asDate(reading?.timestamp))
        .filter(Boolean)
        .sort((a, b) => b.getTime() - a.getTime())[0] || null;
}

function floodRank(category) {
    const value = String(category || '').toLowerCase();
    if (value.includes('major')) return 4;
    if (value.includes('moderate')) return 3;
    if (value.includes('minor')) return 2;
    if (value.includes('action')) return 1;
    return 0;
}

function markerStatus(station) {
    if (isCoastal(station)) return 'coastal';
    if (isBuoy(station)) return 'buoy';
    const category = String(station?.observed_category || '').toLowerCase();
    if (category.includes('major')) return 'major';
    if (category.includes('moderate')) return 'moderate';
    if (category.includes('minor')) return 'minor';
    if (category.includes('action')) return 'action';
    return 'normal';
}

function markerStyle(status) {
    if (status === 'coastal') return { fill: '#14b8a6', stroke: '#e0f2fe', weight: 2.6 };
    if (status === 'buoy') return { fill: '#2563eb', stroke: '#bfdbfe', weight: 2.6 };
    if (status === 'major') return { fill: '#a855f7', stroke: '#581c87' };
    if (status === 'moderate') return { fill: '#ef4444', stroke: '#991b1b' };
    if (status === 'minor') return { fill: '#f97316', stroke: '#9a3412' };
    if (status === 'action') return { fill: '#facc15', stroke: '#a16207' };
    if (status === 'stale') return { fill: '#64748b', stroke: '#334155' };
    if (status === 'missing') return { fill: '#f59e0b', stroke: '#92400e' };
    return { fill: '#38bdf8', stroke: '#0369a1' };
}

function legendItems(items) {
    return items.map(([label, status]) => {
        const style = markerStyle(status);
        const shadow = status === 'coastal'
            ? 'box-shadow:0 0 0 1px #0f766e;'
            : status === 'buoy' ? 'box-shadow:0 0 0 1px #1d4ed8;' : '';
        return `<div class="legend-item"><span class="legend-swatch" style="background:${style.fill};border-color:${style.stroke};border-radius:50%;${shadow}"></span><span class="legend-text">${label}</span></div>`;
    }).join('');
}

function legendHtml(networks, floodFilter) {
    if (!networks.length) return '';
    const sections = [];
    if (networks.includes('river')) {
        const minRank = WATER_FLOOD_RANKS[floodFilter] || 0;
        const items = [
            ['Major', 'major'], ['Moderate', 'moderate'], ['Minor', 'minor'],
            ['Action Stage', 'action'], ['No Flood / Unknown', 'normal'],
        ].filter(([, status]) => floodFilter === 'all' || floodRank(status) >= minRank);
        sections.push(`<section class="water-legend-section"><div class="water-legend-section-title">River Flood Stage</div><div class="water-legend-row water-legend-river">${legendItems(items)}</div></section>`);
    }
    const otherItems = [];
    if (networks.includes('coastal')) otherItems.push(['Coastal Gauge', 'coastal']);
    if (networks.includes('buoy')) otherItems.push(['NDBC Buoy', 'buoy']);
    if (otherItems.length) {
        sections.push(`<section class="water-legend-section"><div class="water-legend-section-title">Other Networks</div><div class="water-legend-row water-legend-other">${legendItems(otherItems)}</div></section>`);
    }
    return `<div class="core-legend-header"><span class="core-legend-provider">NOAA</span><div class="core-legend-heading"><div class="core-legend-title">Water Observations</div></div><span class="core-legend-meta">${networks.length} network${networks.length === 1 ? '' : 's'}</span></div><div class="core-legend-body"><div class="water-legend-sections">${sections.join('')}</div></div>`;
}

function stageGaugeHtml(station) {
    const reading = station?.readings?.stage;
    const categories = station?.flood?.categories || {};
    const current = reading?.value != null ? Number(reading.value) : null;
    if (!Number.isFinite(current)) return '';
    const thresholds = [
        { key: 'action', color: '#facc15', label: 'Act' },
        { key: 'minor', color: '#f97316', label: 'Min' },
        { key: 'moderate', color: '#ef4444', label: 'Mod' },
        { key: 'major', color: '#a855f7', label: 'Maj' },
    ].map((item) => ({ ...item, stage: Number(categories[item.key]?.stage) }))
        .filter((item) => Number.isFinite(item.stage));
    if (!thresholds.length) return '';
    const scaleMax = Math.max(current * 1.1, thresholds.at(-1).stage * 1.15, 1);
    const pct = (value) => `${Math.min(100, Math.max(0, (value / scaleMax) * 100)).toFixed(1)}%`;
    let zones = `<div class="wx-stage-zone" style="left:0;width:${pct(thresholds[0].stage)};background:#38bdf830;"></div>`;
    thresholds.forEach((item, index) => {
        const end = index + 1 < thresholds.length ? thresholds[index + 1].stage : scaleMax;
        zones += `<div class="wx-stage-zone" style="left:${pct(item.stage)};width:${pct(end - item.stage)};background:${item.color}50;"></div>`;
    });
    const summary = thresholds.map((item) => `${item.label}:${item.stage.toFixed(1)}`).join('  ');
    return `<div class="wx-stage-gauge"><div class="wx-stage-bar">${zones}<div class="wx-stage-marker" style="left:${pct(current)};"></div></div><div class="wx-stage-summary"><span class="wx-stage-cur">&#9650; ${current.toFixed(2)} ${reading?.units || 'ft'}</span><span class="wx-stage-thresh">${summary}</span></div></div>`;
}

function buoyCardHtml(station) {
    const readings = station?.readings || {};
    const text = (key) => {
        const reading = readings[key];
        if (!reading || reading.value == null) return null;
        const value = Number(reading.value);
        const formatted = Number.isFinite(value) ? value.toLocaleString(undefined, { maximumFractionDigits: 1 }) : String(reading.value);
        return `${formatted}${reading.units ? ' ' + reading.units : ''}`;
    };
    const groups = [
        { label: 'Wind', items: [['Speed', text('wind_speed')], ['Gust', text('wind_gust')], ['Dir', readings.wind_direction?.value != null ? `${Number(readings.wind_direction.value).toFixed(0)}°T` : null]] },
        { label: 'Waves', items: [['Height', text('wave_height')], ['Period', text('dominant_wave_period')], ['Dir', readings.mean_wave_direction?.value != null ? `${Number(readings.mean_wave_direction.value).toFixed(0)}°T` : null]] },
        { label: 'Atmos', items: [['Pressure', text('pressure')], ['Tendency', text('pressure_tendency')]] },
        { label: 'Temp', items: [['Air', text('air_temperature')], ['Water', text('water_temperature')], ['Dew Pt', text('dewpoint')]] },
        { label: 'Other', items: [['Visibility', text('visibility')], ['Tide', text('tide')]] },
    ].map((group) => ({ ...group, items: group.items.filter(([, value]) => value != null) }))
        .filter((group) => group.items.length);
    if (!groups.length) return '';
    return `<div class="wx-buoy-card">${groups.map((group) => `<div class="wx-buoy-group"><span class="wx-buoy-group-label">${escapeHtml(group.label)}</span><dl class="wx-storm-popup-grid">${group.items.map(([label, value]) => `<dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd>`).join('')}</dl></div>`).join('')}</div>`;
}

function sourceLinkHtml(station) {
    const pageUrl = station?.source_url || '';
    const hydrographUrl = station?.floodcat_hydrograph_url || station?.hydrograph_url || '';
    if (hydrographUrl && pageUrl) {
        return `<a class="wx-water-hydrograph-link" href="${escapeHtml(pageUrl)}" target="_blank" rel="noopener" title="Open NOAA gauge page"><img class="wx-water-hydrograph" src="${escapeHtml(hydrographUrl)}" alt="Hydrograph for ${escapeHtml(station?.name || station?.site_id || 'gauge')}" loading="lazy"></a>`;
    }
    if (!pageUrl) return '';
    const label = station?.source === 'NOAA NDBC'
        ? 'NOAA NDBC station page'
        : station?.source === 'NOAA CO-OPS'
        ? 'NOAA Tides & Currents station page'
        : station?.source === 'NOAA NWPS'
        ? 'NOAA NWPS gauge page'
        : 'NOAA river gauge page';
    return `<a class="wx-water-detail-link" href="${escapeHtml(pageUrl)}" target="_blank" rel="noopener">${escapeHtml(label)}</a>`;
}

function stationDetailHtml(station) {
    if (!station) return '';
    const coastal = isCoastal(station);
    const buoy = isBuoy(station);
    const updatedDate = latestTimestamp(station) || asDate(station.updated);
    const rows = [
        ['Site', station.nwps_lid || station.coops_id || station.ndbc_id || station.site_id || ''],
        ['Network', networkLabel(station)], ['Type', capabilityText(station)], ['Waterbody', station.waterbody],
        ['Stage', (coastal || buoy) ? '' : readingText(station, 'stage')],
        ['Observed', (coastal || buoy) ? '' : categoryText(station.observed_category)],
        coastal ? readingRow(station, 'water_level', 'Water Level') : null,
        coastal ? readingRow(station, 'current_speed', 'Speed') : null,
        coastal ? readingRow(station, 'current_direction', 'Direction') : null,
        ['Updated', updatedDate ? updatedDate.toLocaleString() : 'No current value'],
        ['WFO / RFC', [station.wfo, station.rfc].filter(Boolean).join(' / ')],
        ['Affiliation', station.affiliation], ['County', [station.county, station.state].filter(Boolean).join(', ')],
        ['State', coastal ? station.state : ''],
    ].filter(Boolean).filter((row) => row[1])
        .map(([label, value]) => `<dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd>`).join('');
    return `<div class="water-detail-head"><div><div class="water-detail-eyebrow">NOAA ${escapeHtml(networkLabel(station))} Observation</div><h2 id="water-detail-title">${escapeHtml(station.name || station.site_id)}</h2></div><button class="water-detail-close" type="button" aria-label="Close water station detail">×</button></div><div class="water-detail-body"><dl class="wx-storm-popup-grid">${rows}</dl>${!buoy && !coastal ? stageGaugeHtml(station) : ''}${buoy ? buoyCardHtml(station) : ''}${sourceLinkHtml(station)}</div>`;
}

export function createWaterEngine({ api, mapCore, legend, status, detailRoot, paneName = 'water-markers', onBeforeDetail = () => {} }) {
    const map = mapCore.map;
    const leaflet = mapCore.leaflet || window.L;
    let layer = null;
    let stations = [];
    let networks = [...DEFAULT_NETWORKS];
    let floodFilter = 'all';
    let enabled = false;
    let requestSeq = 0;
    let detailRequestSeq = 0;
    let reloadTimer = null;
    let stationsInFlight = false;
    let pendingReload = false;

    function setMessage(message, level) {
        status?.setMessage?.(message || '', level);
    }

    function updateLegend() {
        const html = enabled ? legendHtml(networks, floodFilter) : '';
        if (html) legend.setHtml(html);
        else legend.clear();
    }

    function installDetailDrag(handle) {
        if (!detailRoot || !handle) return;
        let drag = null;
        handle.addEventListener('pointerdown', (event) => {
            if (event.target.closest('button, a')) return;
            const parentRect = detailRoot.parentElement.getBoundingClientRect();
            const rect = detailRoot.getBoundingClientRect();
            detailRoot.style.left = `${rect.left - parentRect.left}px`;
            detailRoot.style.top = `${rect.top - parentRect.top}px`;
            detailRoot.style.right = 'auto';
            drag = { x: event.clientX, y: event.clientY, left: rect.left - parentRect.left, top: rect.top - parentRect.top };
            handle.setPointerCapture(event.pointerId);
            event.preventDefault();
        });
        handle.addEventListener('pointermove', (event) => {
            if (!drag) return;
            const parent = detailRoot.parentElement.getBoundingClientRect();
            detailRoot.style.left = `${Math.max(0, Math.min(Math.max(0, parent.width - detailRoot.offsetWidth), drag.left + event.clientX - drag.x))}px`;
            detailRoot.style.top = `${Math.max(0, Math.min(Math.max(0, parent.height - detailRoot.offsetHeight), drag.top + event.clientY - drag.y))}px`;
        });
        const end = () => { drag = null; };
        handle.addEventListener('pointerup', end);
        handle.addEventListener('pointercancel', end);
    }

    function closeDetail() {
        detailRequestSeq += 1;
        if (!detailRoot) return;
        detailRoot.replaceChildren();
        detailRoot.hidden = true;
    }

    function openDetail(html, color = '#38bdf8') {
        if (!detailRoot) return;
        detailRoot.style.setProperty('--water-detail-color', color);
        detailRoot.style.left = 'auto';
        detailRoot.style.right = '12px';
        detailRoot.style.top = '12px';
        detailRoot.innerHTML = html;
        detailRoot.hidden = false;
        detailRoot.querySelector('.water-detail-close')?.addEventListener('click', closeDetail);
        installDetailDrag(detailRoot.querySelector('.water-detail-head'));
    }

    function detailMessageHtml(title, message) {
        return `<div class="water-detail-head"><div><div class="water-detail-eyebrow">NOAA Water Observation</div><h2 id="water-detail-title">${escapeHtml(title)}</h2></div><button class="water-detail-close" type="button" aria-label="Close water station detail">×</button></div><div class="water-detail-body"><p class="water-detail-message">${escapeHtml(message)}</p></div>`;
    }

    async function loadDetail(siteId, station) {
        if (!siteId || !enabled) return;
        onBeforeDetail();
        const sequence = ++detailRequestSeq;
        const style = markerStyle(markerStatus(station));
        openDetail(detailMessageHtml(station?.name || siteId, 'Loading latest station details…'), style.fill);
        try {
            const response = await fetch(api.apiUrl(`/api/water/stations/${encodeURIComponent(siteId)}`), { cache: 'no-store' });
            if (sequence !== detailRequestSeq || !enabled) return;
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();
            if (data?.station) openDetail(stationDetailHtml(data.station), markerStyle(markerStatus(data.station)).fill);
        } catch (error) {
            if (sequence !== detailRequestSeq || !enabled) return;
            setMessage(`Water station unavailable: ${error.message}`, 'error');
            openDetail(detailMessageHtml(station?.name || siteId, `Station unavailable: ${error.message}`), style.fill);
        }
    }

    function ensureLayer() {
        if (!layer) layer = leaflet.layerGroup();
        return layer;
    }

    function filteredStations() {
        const selected = stations.filter((station) => {
            const network = isCoastal(station) ? 'coastal' : isBuoy(station) ? 'buoy' : 'river';
            return networks.includes(network);
        });
        if (floodFilter === 'all') return selected;
        const minRank = WATER_FLOOD_RANKS[floodFilter] || 0;
        return selected.filter((station) => isCoastal(station) || isBuoy(station) || floodRank(station.observed_category) >= minRank);
    }

    function render() {
        const markerLayer = ensureLayer();
        markerLayer.clearLayers();
        filteredStations().forEach((station) => {
            const lat = Number(station.lat);
            const lon = Number(station.lon);
            if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
            const style = markerStyle(markerStatus(station));
            const marker = leaflet.circleMarker([lat, lon], {
                pane: paneName, radius: 5, color: style.stroke, weight: style.weight || 1.6,
                fillColor: style.fill, fillOpacity: 0.9,
            });
            const tooltip = isCoastal(station)
                ? `<strong>${escapeHtml(station.name || station.site_id)}</strong><br>${escapeHtml(capabilityText(station) || 'Coastal Gauge')}`
                : isBuoy(station)
                ? `<strong>${escapeHtml(station.name || station.site_id)}</strong><br>${escapeHtml(readingText(station, 'wave_height'))} waves`
                : `<strong>${escapeHtml(station.name || station.site_id)}</strong><br>Stage ${escapeHtml(readingText(station, 'stage'))}`;
            marker.bindTooltip(tooltip, { direction: 'top', className: 'city-name-label' });
            marker.on('click', () => void loadDetail(station.site_id, station));
            marker.addTo(markerLayer);
        });
        if (enabled && !map.hasLayer(markerLayer)) markerLayer.addTo(map);
    }

    function requestBbox() {
        const bounds = map.getBounds();
        const south = Math.max(-90, bounds.getSouth());
        const north = Math.min(90, bounds.getNorth());
        const span = bounds.getEast() - bounds.getWest();
        const west = span >= 360 ? -180 : Math.max(-180, bounds.getWest());
        const east = span >= 360 ? 180 : Math.min(180, bounds.getEast());
        return [west, south, east, north].map((value) => value.toFixed(4)).join(',');
    }

    function scheduleReload(delayMs = 900) {
        if (!enabled) return;
        if (reloadTimer) clearTimeout(reloadTimer);
        reloadTimer = setTimeout(() => {
            reloadTimer = null;
            void load();
        }, delayMs);
    }

    async function load({ force = false } = {}) {
        if (!enabled || !networks.length) {
            stations = [];
            render();
            updateLegend();
            if (enabled) setMessage('Select at least one Water network.');
            return;
        }
        if (stationsInFlight) {
            pendingReload = true;
            return;
        }
        const sequence = ++requestSeq;
        stationsInFlight = true;
        pendingReload = false;
        setMessage('Loading NOAA water stations…');
        try {
            const params = new URLSearchParams({ bbox: requestBbox(), max_sites: '15000', networks: networks.join(',') });
            if (force) params.set('_', String(Date.now()));
            const response = await fetch(api.apiUrl(`/api/water/stations?${params.toString()}`), { cache: 'no-store' });
            if (sequence !== requestSeq || !enabled) return;
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();
            stations = Array.isArray(data?.stations) ? data.stations : [];
            render();
            const total = Number(data?.total_available || stations.length);
            const cachePrefix = data?.cache_state === 'refreshing' ? 'Cache warming: ' : '';
            const staleSuffix = data?.stale ? ' Cache may be stale.' : '';
            const names = networks.map((value) => value === 'river' ? 'river' : value === 'coastal' ? 'coastal' : 'NDBC').join(' + ');
            const countText = total > stations.length
                ? `${stations.length} of ${total} cached NOAA ${names} gauges shown.`
                : `${stations.length} cached NOAA ${names} gauge${stations.length === 1 ? '' : 's'} loaded.`;
            setMessage(`${cachePrefix}${data?.message || countText}${staleSuffix}`);
            const latest = stations.map(latestTimestamp).filter(Boolean).sort((a, b) => b.getTime() - a.getTime())[0];
            if (latest) status?.setDataInfo?.({ timestamp: latest.getTime(), provider: 'NOAA' });
            const retryAfterSeconds = Number(data?.retry_after_seconds);
            if (Number.isFinite(retryAfterSeconds) && retryAfterSeconds > 0 && data?.cache_state !== 'fresh') {
                scheduleReload(Math.max(500, retryAfterSeconds * 1000));
            }
        } catch (error) {
            if (sequence === requestSeq && enabled) setMessage(`NOAA water station data unavailable: ${error.message}`, 'error');
        } finally {
            stationsInFlight = false;
            if (pendingReload && enabled) {
                pendingReload = false;
                scheduleReload(900);
            }
        }
    }

    function clear() {
        requestSeq += 1;
        if (reloadTimer) clearTimeout(reloadTimer);
        reloadTimer = null;
        pendingReload = false;
        if (layer) {
            layer.clearLayers();
            if (map.hasLayer(layer)) map.removeLayer(layer);
        }
        stations = [];
        closeDetail();
    }

    function setEnabled(value, { loadNow = true } = {}) {
        enabled = Boolean(value);
        if (!enabled) {
            clear();
            updateLegend();
            return Promise.resolve();
        }
        updateLegend();
        return loadNow ? load() : Promise.resolve();
    }

    function setNetworks(values, { refresh = true } = {}) {
        networks = DEFAULT_NETWORKS.filter((network) => values?.includes(network));
        if (!networks.includes('river')) floodFilter = 'all';
        updateLegend();
        render();
        return enabled && refresh ? load({ force: true }) : Promise.resolve();
    }

    function setFloodFilter(value) {
        floodFilter = Object.hasOwn(WATER_FLOOD_RANKS, value) ? value : 'all';
        updateLegend();
        render();
        if (floodFilter !== 'all') setMessage(`Flood filter: ${filteredStations().length} of ${stations.length} stations shown.`);
        return floodFilter;
    }

    function setRegion() {
        clear();
        scheduleReload(0);
    }

    const onMapMoveStart = () => closeDetail();
    const onMapMoveEnd = () => scheduleReload();
    const onEscape = (event) => { if (event.key === 'Escape') closeDetail(); };
    map.on('movestart zoomstart', onMapMoveStart);
    map.on('moveend', onMapMoveEnd);
    document.addEventListener('keydown', onEscape);
    if (detailRoot) {
        leaflet.DomEvent.disableClickPropagation(detailRoot);
        leaflet.DomEvent.disableScrollPropagation(detailRoot);
    }

    return Object.freeze({
        clear,
        closeDetail,
        destroy() {
            enabled = false;
            clear();
            legend.clear();
            map.off('movestart zoomstart', onMapMoveStart);
            map.off('moveend', onMapMoveEnd);
            document.removeEventListener('keydown', onEscape);
        },
        getFloodFilter: () => floodFilter,
        getNetworks: () => [...networks],
        hasSelection: () => networks.length > 0,
        isEnabled: () => enabled,
        refresh: load,
        setEnabled,
        setFloodFilter,
        setNetworks,
        setRegion,
    });
}
