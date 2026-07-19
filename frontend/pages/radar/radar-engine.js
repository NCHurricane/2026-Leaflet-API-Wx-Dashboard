const SITE_STATUS_COLORS = Object.freeze({
    online: '#22c55e', required: '#f59e0b', mandatory: '#f97316',
    startup: '#60a5fa', configured: '#facc15', unconfigured: '#64748b',
});

function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, (char) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[char]));
}

function timestampMs(value) {
    const ms = new Date(value || '').getTime();
    return Number.isFinite(ms) ? ms : null;
}

function frameIdentity(frame) {
    return String(frame?.frame_key || frame?.timestamp || frame?.image_url || '');
}

function normalizeFrames(rawFrames, site, product) {
    const seen = new Set();
    return (Array.isArray(rawFrames) ? rawFrames : [])
        .filter((frame) => frame?.image_url && Array.isArray(frame?.bounds) && frame.bounds.length === 4)
        .map((frame) => ({ ...frame, site: frame.site || site, product: frame.product || product }))
        .filter((frame) => {
            const key = frameIdentity(frame);
            if (!key || seen.has(key)) return false;
            seen.add(key);
            return true;
        })
        .sort((a, b) => (timestampMs(a.timestamp) || 0) - (timestampMs(b.timestamp) || 0));
}

function siteStatusClass(info, configured) {
    const operability = String(info?.operabilityStatus || '').toLowerCase();
    const status = String(info?.status || '').toLowerCase();
    if (operability.includes('on-line')) return 'online';
    if (operability.includes('maintenance action mandatory')) return 'mandatory';
    if (operability.includes('maintenance action required')) return 'required';
    if (status === 'start-up') return 'startup';
    return configured ? 'configured' : 'unconfigured';
}

function legendHeader(title, meta = '') {
    return `<div class="core-legend-header">
        <span class="core-legend-provider">Radar</span>
        <div class="core-legend-heading"><div class="core-legend-title">${escapeHtml(title)}</div></div>
        ${meta ? `<span class="core-legend-meta">${escapeHtml(meta)}</span>` : ''}
    </div>`;
}

function siteLegendHtml() {
    const items = [
        ['online', 'Online'], ['required', 'Maintenance Required'],
        ['mandatory', 'Maintenance Mandatory'], ['startup', 'Startup'],
        ['configured', 'Configured / Unknown'], ['unconfigured', 'Unconfigured'],
    ].map(([key, label]) => `<div class="core-legend-category">
        <span class="core-legend-color" style="background:${SITE_STATUS_COLORS[key]}"></span>
        <div class="core-legend-category-copy"><span class="core-legend-category-code">${escapeHtml(label)}</span></div>
    </div>`).join('');
    return `${legendHeader('Radar Sites (All NWS NEXRAD)')}
        <div class="core-legend-body"><div class="core-legend-categories radar-site-legend">${items}</div></div>`;
}

function productLegendHtml(productId, product, table) {
    const entries = Array.isArray(table?.entries) ? table.entries : [];
    if (!entries.length) return '';
    const min = Number(table.legend_vmin ?? table.vmin);
    const max = Number(table.vmax);
    const range = max - min || 1;
    const gradient = entries.map((entry) => {
        const pct = ((Number(entry.value) - min) / range) * 100;
        return `${entry.color} ${Math.max(0, Math.min(100, pct)).toFixed(2)}%`;
    }).join(', ');
    const tickEntries = entries.filter((_, index) => index % 2 === 0 || index === entries.length - 1);
    const ticks = tickEntries.map((entry) => {
        const pct = ((Number(entry.value) - min) / range) * 100;
        return `<span class="core-legend-tick" style="left:${Math.max(0, Math.min(100, pct)).toFixed(2)}%">${escapeHtml(entry.label)}</span>`;
    }).join('');
    return `${legendHeader(product?.label || productId, product?.units || '')}
        <div class="core-legend-body">
            <div class="core-legend-colorbar" style="background:linear-gradient(to right, ${gradient})"></div>
            <div class="core-legend-ticks">${ticks}</div>
        </div>`;
}

function stormCellIcon(leaflet, priority) {
    const styles = {
        tvs: ['#ef4444', 'T'], meso: ['#f97316', 'M'],
        pos_hail: ['#22c55e', 'H'], prob_hail: ['#020617', 'H?'], cell: ['#cfcfcf', ''],
    };
    const [color, label] = styles[priority] || styles.cell;
    return leaflet.divIcon({
        className: '', iconSize: [30, 30], iconAnchor: [15, 15],
        html: `<svg width="30" height="30" viewBox="0 0 30 30" aria-hidden="true">
            <circle cx="15" cy="15" r="11" fill="${color}" stroke="#fff" stroke-width="2"/>
            <text x="15" y="19" text-anchor="middle" font-size="11" font-weight="900" fill="#fff" stroke="#020617" paint-order="stroke">${label}</text>
        </svg>`,
    });
}

function stormPopupHtml(properties) {
    const rows = [];
    const add = (label, value) => { if (value != null && value !== '') rows.push(`<dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd>`); };
    add('Motion', Number.isFinite(Number(properties.speed_kt)) && Number.isFinite(Number(properties.motion_to_degrees))
        ? `${Math.round(Number(properties.speed_kt))} kt toward ${Math.round(Number(properties.motion_to_degrees))}°` : '—');
    add('Max dBZ', properties.max_dbz);
    add('VIL', properties.vil);
    add('Top', properties.top_kft != null ? `${properties.top_kft} kft` : null);
    add('POH', properties.poh != null ? `${properties.poh}%` : null);
    add('POSH', properties.posh != null ? `${properties.posh}%` : null);
    return `<div><div class="radar-storm-popup-title">Storm Cell ${escapeHtml(properties.cell_id || '')}</div>
        <dl class="radar-storm-popup-grid">${rows.join('')}</dl></div>`;
}

export function createRadarEngine(options) {
    const { api, mapCore, legend, status, getSelection, onCatalog, onElevationData,
        onFrames, onFrameIndex, onSitePicked, onMessage } = options;
    const { leaflet, map } = mapCore;
    const radarPane = map.createPane('radar-overlays');
    radarPane.style.zIndex = '210';
    radarPane.style.pointerEvents = 'none';
    const sitesPane = map.createPane('radar-sites');
    sitesPane.style.zIndex = '460';

    const siteLayer = leaflet.layerGroup();
    const highlightLayer = leaflet.layerGroup();
    const stormLayer = leaflet.layerGroup();
    const siteCoords = new Map();
    const configuredSites = new Map();
    const conusSites = new Map();
    const products = new Map();
    const colortableCache = new Map();
    const overlayPool = new Map();
    let statusMap = new Map();
    let frames = [];
    let currentOverlay = null;
    let currentFrame = null;
    let selectedCell = null;
    let requestSequence = 0;
    let trackSequence = 0;
    let renderSequence = 0;
    let opacity = 0.9;
    let sitesVisible = true;
    let tracksVisible = false;
    let inspectorVisible = false;
    let historyTimer = null;
    let retryTimer = null;
    let inspectorTimer = null;
    let inspectorController = null;
    let inspectorElement = null;
    let lastInspectorRequest = 0;

    const message = (text, tone = '') => onMessage?.(text, tone);
    const selectionMatches = (snapshot) => {
        const current = getSelection();
        return current.site === snapshot.site && current.product === snapshot.product;
    };

    function selectedMotion() {
        const selection = getSelection();
        if (selection.product !== 'L2_SRV' || selectedCell?.site !== selection.site) return null;
        const speed = Number(selectedCell.speed_kt);
        const direction = Number(selectedCell.motion_to_degrees);
        if (!Number.isFinite(speed) || !Number.isFinite(direction)) return null;
        return { speed, direction, cellId: String(selectedCell.cell_id || '') };
    }

    function appendMotionParams(params) {
        const motion = selectedMotion();
        if (!motion) return;
        params.set('storm_motion_speed_kt', String(Math.round(motion.speed)));
        params.set('storm_motion_to_degrees', String(Math.round(motion.direction)));
        params.set('storm_motion_source', 'NST');
        if (motion.cellId) params.set('storm_cell_id', motion.cellId);
    }

    function overlayUrl(rawUrl) {
        return api.apiUrl(String(rawUrl || ''));
    }

    async function preload(url) {
        await new Promise((resolve) => {
            const image = new Image();
            image.onload = resolve;
            image.onerror = resolve;
            image.src = url;
        });
    }

    function getOrCreateOverlay(frame) {
        const key = frameIdentity(frame);
        if (!key) return null;
        let record = overlayPool.get(key);
        if (record) return record;
        const bounds = frame.bounds;
        const layer = leaflet.imageOverlay(overlayUrl(frame.image_url), [[bounds[2], bounds[0]], [bounds[3], bounds[1]]], {
            pane: 'radar-overlays', opacity: 0, zIndex: 320,
        });
        record = { key, layer };
        overlayPool.set(key, record);
        return record;
    }

    function trimOverlayPool(activeKey) {
        const allowed = new Set(frames.slice(-8).map(frameIdentity));
        if (activeKey) allowed.add(activeKey);
        overlayPool.forEach((record, key) => {
            if (allowed.has(key)) return;
            if (map.hasLayer(record.layer)) map.removeLayer(record.layer);
            overlayPool.delete(key);
        });
    }

    async function renderFrame(frame, index = -1) {
        if (!frame?.image_url || !Array.isArray(frame.bounds)) return;
        const seq = ++renderSequence;
        const record = getOrCreateOverlay(frame);
        if (!record) return;
        await preload(overlayUrl(frame.image_url));
        if (seq !== renderSequence) return;
        const oldLayer = currentOverlay;
        if (!map.hasLayer(record.layer)) record.layer.addTo(map);
        record.layer.setOpacity(opacity);
        currentOverlay = record.layer;
        currentFrame = frame;
        if (oldLayer && oldLayer !== record.layer) oldLayer.setOpacity(0);
        trimOverlayPool(record.key);
        if (index >= 0) onFrameIndex?.(index);
        const ts = frame.timestamp;
        status.setDataInfo({ timestamp: ts, provider: 'NEXRAD', source: frame.source || 'live cache' });
        message(`${frame.site || getSelection().site} ${frame.product || getSelection().product} ${new Date(ts).toLocaleString()}.`);
        if (tracksVisible) void loadStormTracks(ts);
    }

    function clearOverlays() {
        requestSequence += 1;
        trackSequence += 1;
        renderSequence += 1;
        clearTimeout(historyTimer);
        clearTimeout(retryTimer);
        overlayPool.forEach(({ layer }) => { if (map.hasLayer(layer)) map.removeLayer(layer); });
        overlayPool.clear();
        currentOverlay = null;
        currentFrame = null;
        selectedCell = null;
        frames = [];
        onFrames?.([], { index: 0 });
        stormLayer.clearLayers();
        if (map.hasLayer(stormLayer)) map.removeLayer(stormLayer);
        hideInspector();
        legend.clear();
    }

    function syncHighlights(siteId = getSelection().site) {
        highlightLayer.clearLayers();
        if (!sitesVisible || !siteId || !siteCoords.has(siteId)) {
            if (map.hasLayer(highlightLayer)) map.removeLayer(highlightLayer);
            return;
        }
        const [lat, lon] = siteCoords.get(siteId);
        leaflet.circleMarker([lat, lon], {
            pane: 'radar-sites', radius: 10, color: '#f8fafc', weight: 2.2,
            fillOpacity: 0, interactive: false,
        }).addTo(highlightLayer);
        if (!map.hasLayer(highlightLayer)) highlightLayer.addTo(map);
    }

    function syncSiteVisibility() {
        if (sitesVisible) {
            if (!map.hasLayer(siteLayer)) siteLayer.addTo(map);
            syncHighlights();
        } else {
            if (map.hasLayer(siteLayer)) map.removeLayer(siteLayer);
            if (map.hasLayer(highlightLayer)) map.removeLayer(highlightLayer);
        }
    }

    async function loadCatalog() {
        const [siteData, radarStatus] = await Promise.all([
            api.fetchJson('/api/radar/live/sites', { cache: 'no-store' }),
            api.fetchJson('/api/radar/status', { cache: 'no-store' }).catch(() => ({ stations: {} })),
        ]);
        const rawStatus = radarStatus?.stations || {};
        statusMap = new Map(Object.entries(rawStatus).map(([key, value]) => [String(key).toUpperCase(), value]));
        const sites = Array.isArray(siteData?.sites) ? siteData.sites : [];
        Object.entries(siteData?.products || {}).forEach(([key, value]) => products.set(String(key).toUpperCase(), value));
        siteLayer.clearLayers();
        sites.forEach((site) => {
            const id = String(site?.site || '').toUpperCase();
            const lat = Number(site?.lat);
            const lon = Number(site?.lon);
            if (!id || !Number.isFinite(lat) || !Number.isFinite(lon)) return;
            siteCoords.set(id, [lat, lon]);
            configuredSites.set(id, !!site.configured);
            conusSites.set(id, !!site.conus);
            const color = SITE_STATUS_COLORS[siteStatusClass(statusMap.get(id), !!site.configured)];
            const marker = leaflet.circleMarker([lat, lon], {
                pane: 'radar-sites', radius: 5, color: '#020617', weight: 1.5,
                fillColor: color, fillOpacity: 0.9,
            });
            const info = statusMap.get(id);
            marker.bindTooltip(`<strong>${escapeHtml(id)}</strong>${info?.operabilityStatus ? `<br>${escapeHtml(info.operabilityStatus)}` : ''}`, {
                direction: 'top', className: 'core-city-name-tag',
            });
            marker.on('click', () => onSitePicked?.(id, [lat, lon]));
            marker.addTo(siteLayer);
        });
        syncSiteVisibility();
        onCatalog?.({ sites, products: Object.fromEntries(products) });
        return { sites, products: Object.fromEntries(products) };
    }

    async function updateProductLegend(productId) {
        const product = products.get(productId);
        if (!productId || !product) { legend.clear(); return; }
        try {
            let table = colortableCache.get(productId);
            if (!table) {
                table = await api.fetchJson(`/api/radar/colortable?product=${encodeURIComponent(productId)}`);
                colortableCache.set(productId, table);
            }
            legend.setHtml(productLegendHtml(productId, product, table));
        } catch (_) { legend.clear(); }
    }

    function showSiteLegend() { legend.setHtml(siteLegendHtml()); }

    async function loadLatest() {
        const selection = { ...getSelection() };
        if (!selection.site || !selection.product) return;
        const seq = ++requestSequence;
        message(`Loading ${selection.site} ${selection.product} live radar…`);
        const params = new URLSearchParams({
            site: selection.site, product: selection.product, elevation: selection.elevation || 'auto',
        });
        appendMotionParams(params);
        if (!configuredSites.get(selection.site)) params.set('force', '1');
        try {
            const data = await api.fetchJson(`/api/radar/live/latest?${params}`, { cache: 'no-store' });
            if (seq !== requestSequence || !selectionMatches(selection)) return;
            onElevationData?.(data);
            await renderFrame({ ...data, site: selection.site, product: selection.product }, -1);
            await updateProductLegend(selection.product);
            if (data?.history_filling) scheduleHistoryRefresh();
        } catch (error) {
            if (seq !== requestSequence || !selectionMatches(selection)) return;
            const warming = /no live radar frame cached yet|latest live radar image is missing/i.test(error.message);
            message(warming ? `${selection.site}/${selection.product} is warming; retrying…` : `Radar load failed: ${error.message}`, warming ? '' : 'error');
            if (warming) {
                clearTimeout(retryTimer);
                retryTimer = setTimeout(() => void loadLatest(), 3000);
            }
        }
    }

    async function loadFrames({ refresh = false, preserveKey = '' } = {}) {
        const selection = { ...getSelection() };
        if (!selection.site || !selection.product) return [];
        const seq = requestSequence;
        const params = new URLSearchParams({
            site: selection.site, product: selection.product,
            elevation: selection.elevation || 'auto', hours: String(selection.hours || 1),
        });
        if (refresh) params.set('refresh', 'true');
        appendMotionParams(params);
        try {
            const data = await api.fetchJson(`/api/radar/live/frames?${params}`, { cache: 'no-store' });
            if (seq !== requestSequence || !selectionMatches(selection)) return [];
            onElevationData?.(data);
            const nextFrames = normalizeFrames(data?.frames, selection.site, selection.product);
            frames = nextFrames;
            let index = frames.length - 1;
            if (preserveKey) {
                const preserved = frames.findIndex((frame) => frameIdentity(frame) === preserveKey);
                if (preserved >= 0) index = preserved;
            }
            onFrames?.(frames, { index: Math.max(0, index) });
            if (frames.length && index >= 0) await renderFrame(frames[index], index);
            if (!frames.length) message(`No radar frames found for ${selection.site}/${selection.product}.`);
            if (data?.history_filling) scheduleHistoryRefresh();
            return frames;
        } catch (error) {
            if (selectionMatches(selection)) message(`Radar frame load failed: ${error.message}`, 'error');
            return [];
        }
    }

    function scheduleHistoryRefresh() {
        clearTimeout(historyTimer);
        historyTimer = setTimeout(() => {
            const preserveKey = frameIdentity(currentFrame);
            void loadFrames({ preserveKey });
        }, 3000);
    }

    async function refreshAll() {
        if (!getSelection().site) return;
        requestSequence += 1;
        const latestPromise = loadLatest();
        const framesPromise = loadFrames();
        await Promise.allSettled([latestPromise, framesPromise]);
    }

    async function loadStormTracks(frameTimestamp = null) {
        const selection = getSelection();
        const seq = ++trackSequence;
        stormLayer.clearLayers();
        if (!tracksVisible || !selection.site) {
            if (map.hasLayer(stormLayer)) map.removeLayer(stormLayer);
            return;
        }
        try {
            const params = new URLSearchParams({ site: selection.site, hours: String(Math.max(1, selection.hours || 1)) });
            if (frameTimestamp) params.set('timestamp', String(frameTimestamp));
            const data = await api.fetchJson(`/api/radar/live/storm-tracks?${params}`, { cache: 'no-store' });
            if (seq !== trackSequence || getSelection().site !== selection.site) return;
            const features = data?.feature_collection?.features || [];
            features.forEach((feature) => {
                const geometry = feature?.geometry || {};
                const properties = feature?.properties || {};
                if (geometry.type === 'LineString') {
                    const latlngs = (geometry.coordinates || []).map((coord) => [Number(coord[1]), Number(coord[0])]);
                    if (latlngs.length >= 2) leaflet.polyline(latlngs, {
                        pane: 'radar-sites', color: '#facc15', weight: 2, opacity: 0.85,
                        dashArray: '5 4', interactive: false,
                    }).addTo(stormLayer);
                    return;
                }
                if (geometry.type !== 'Point' || properties.kind !== 'nst_cell') return;
                const marker = leaflet.marker([Number(geometry.coordinates[1]), Number(geometry.coordinates[0])], {
                    pane: 'radar-sites', icon: stormCellIcon(leaflet, properties.icon_priority || 'cell'),
                });
                marker.bindTooltip(`NST ${escapeHtml(properties.cell_id || '')}`, { direction: 'top' });
                marker.bindPopup(stormPopupHtml(properties));
                marker.on('click', () => {
                    selectedCell = {
                        site: selection.site, cell_id: properties.cell_id || '', speed_kt: properties.speed_kt,
                        motion_to_degrees: properties.motion_to_degrees,
                    };
                    if (getSelection().product === 'L2_SRV') void refreshAll();
                });
                marker.addTo(stormLayer);
            });
            if (!map.hasLayer(stormLayer)) stormLayer.addTo(map);
        } catch (_) {
            message(`NST storm tracks unavailable for ${selection.site}.`);
        }
    }

    function hideInspector() {
        inspectorController?.abort();
        inspectorController = null;
        if (inspectorElement) inspectorElement.remove();
        inspectorElement = null;
    }

    async function requestInspector(latlng) {
        const selection = getSelection();
        if (!inspectorVisible || !currentOverlay || !selection.site) return;
        inspectorController?.abort();
        inspectorController = new AbortController();
        const params = new URLSearchParams({
            site: selection.site, product: selection.product, elevation: selection.elevation || 'auto',
            lat: String(latlng.lat), lon: String(latlng.lng),
        });
        if (currentFrame?.frame_key) params.set('frame_key', String(currentFrame.frame_key));
        appendMotionParams(params);
        try {
            const data = await api.fetchJson(`/api/radar/live/value?${params}`, {
                cache: 'no-store', signal: inspectorController.signal,
            });
            if (!inspectorVisible || data?.status !== 'success') return;
            if (!inspectorElement) {
                inspectorElement = document.createElement('div');
                inspectorElement.className = 'radar-inspector-readout';
                map.getContainer().appendChild(inspectorElement);
            }
            const value = Number(data.value);
            inspectorElement.innerHTML = `<strong>${Number.isFinite(value) ? value.toFixed(Math.abs(value) < 10 ? 1 : 0) : '—'} ${escapeHtml(data.units || '')}</strong>
                <span>${escapeHtml(data.label || data.product || 'Radar')}</span>`;
            const point = map.latLngToContainerPoint(latlng);
            inspectorElement.style.transform = `translate(${Math.round(point.x + 14)}px, ${Math.round(point.y - 14)}px)`;
        } catch (error) {
            if (error?.name !== 'AbortError') hideInspector();
        }
    }

    function onMouseMove(event) {
        if (!inspectorVisible) return;
        const elapsed = Date.now() - lastInspectorRequest;
        clearTimeout(inspectorTimer);
        inspectorTimer = setTimeout(() => {
            lastInspectorRequest = Date.now();
            void requestInspector(event.latlng);
        }, Math.max(0, 90 - elapsed));
    }
    map.on('mousemove', onMouseMove);

    return Object.freeze({
        clear: clearOverlays,
        configuredForSite(site) { return configuredSites.get(site) === true; },
        destroy() {
            requestSequence += 1;
            trackSequence += 1;
            clearTimeout(historyTimer); clearTimeout(retryTimer); clearTimeout(inspectorTimer);
            hideInspector(); clearOverlays();
            map.off('mousemove', onMouseMove);
            [siteLayer, highlightLayer, stormLayer].forEach((layer) => { if (map.hasLayer(layer)) map.removeLayer(layer); });
        },
        frameAt(index) { return frames[index] || null; },
        frameIdentity,
        getFrames() { return [...frames]; },
        isConusSite(site) { return conusSites.get(site) !== false; },
        loadCatalog,
        loadFrames,
        loadLatest,
        refreshAll,
        renderFrameAt(index) { const frame = frames[index]; return frame ? renderFrame(frame, index) : Promise.resolve(); },
        setInspectorVisible(value) { inspectorVisible = !!value; if (!inspectorVisible) hideInspector(); },
        setOpacity(value) {
            opacity = Math.max(0.1, Math.min(1, Number(value) || 0.9));
            if (currentOverlay) currentOverlay.setOpacity(opacity);
            return opacity;
        },
        setSitesVisible(value) { sitesVisible = !!value; syncSiteVisibility(); if (!sitesVisible) legend.clear(); },
        setStormTracksVisible(value) {
            tracksVisible = !!value;
            if (tracksVisible) void loadStormTracks(currentFrame?.timestamp);
            else { stormLayer.clearLayers(); if (map.hasLayer(stormLayer)) map.removeLayer(stormLayer); }
        },
        showProductLegend: updateProductLegend,
        showSiteLegend,
        siteCoords(site) { return siteCoords.get(site) || null; },
        syncHighlights,
    });
}
