import { createRadarWebglLayer } from './radar-webgl-layer.js?v=20260729a';

const SITE_STATUS_COLORS = Object.freeze({
    online: '#22c55e', required: '#f59e0b', mandatory: '#f97316',
    startup: '#60a5fa', configured: '#facc15', unconfigured: '#64748b',
});
const LATEST_REFRESH_POLL_LIMIT = 20;

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
    const frameKey = String(frame?.frame_key || frame?.timestamp || frame?.image_url || '');
    if (!frameKey) return '';
    const site = String(frame?.site || '');
    const product = String(frame?.product || '');
    const elevation = String(frame?.selected_elevation ?? frame?.elevation ?? '');
    return `${site}|${product}|${elevation}|${frameKey}`;
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

export function selectRadarWebglWindow(frames, index, textureBudget = 4, minForward = 2) {
    if (!Array.isArray(frames) || !frames.length || index < 0 || index >= frames.length) return [];
    const budget = Math.max(1, Math.min(8, Number(textureBudget) || 1));
    const forward = Math.max(0, Math.min(budget - 1, Number(minForward) || 0));
    const desired = [];
    const seen = new Set();
    const add = (frame) => {
        const identity = frameIdentity(frame);
        if (!identity || seen.has(identity) || desired.length >= budget) return;
        seen.add(identity);
        desired.push(frame);
    };
    add(frames[index]);
    for (let offset = 1; offset <= forward; offset += 1) {
        add(frames[(index + offset) % frames.length]);
    }
    add(frames[(index - 1 + frames.length) % frames.length]);
    for (let offset = forward + 1; desired.length < budget && offset < frames.length; offset += 1) {
        add(frames[(index + offset) % frames.length]);
    }
    return desired;
}

export function selectRadarFrameIndex(frames, currentFrame, preserveKey = null) {
    if (!Array.isArray(frames) || !frames.length) return 0;
    const key = preserveKey ?? frameIdentity(currentFrame);
    if (key) {
        const preserved = frames.findIndex((frame) => frameIdentity(frame) === key);
        if (preserved >= 0) return preserved;
    }
    return frames.length - 1;
}

export function radarFramePollMode(
    data,
    refreshRequested = false,
    latestPollAttempt = 0,
) {
    if (data?.history_filling) return 'history';
    if (
        data?.latest_refreshing
        && (refreshRequested || latestPollAttempt > 0)
        && latestPollAttempt < LATEST_REFRESH_POLL_LIMIT
    ) {
        return 'latest';
    }
    return '';
}

export function radarWebglProductEnabled(config, product, playback = false) {
    const productId = String(product || '').toUpperCase();
    const products = Array.isArray(config?.products)
        ? config.products.map((value) => String(value).toUpperCase())
        : [String(config?.product || '').toUpperCase()].filter(Boolean);
    if (config?.enabled !== true || !products.includes(productId)) return false;
    if (!playback) return true;
    const animationProducts = Array.isArray(config?.animation_products)
        ? config.animation_products.map((value) => String(value).toUpperCase())
        : (config?.animation_enabled === true ? products : []);
    return animationProducts.includes(productId);
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

function stormCellSvg(priority, size = 34) {
    const half = size / 2;
    const label = (text, y, fontSize = 12) => `<text x="${half}" y="${y}" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="${fontSize}" font-weight="900" fill="#fff" stroke="#020617" stroke-width="2.6" paint-order="stroke fill">${text}</text>`;
    if (priority === 'tvs') return `<polygon points="2,4 ${size - 2},4 ${half},${size - 2}" fill="#ef4444" stroke="#020617" stroke-width="4" stroke-linejoin="round"/><polygon points="2,4 ${size - 2},4 ${half},${size - 2}" fill="#ef4444" stroke="#fff" stroke-width="1.8" stroke-linejoin="round"/>${label('T', Math.round(size * 0.56))}`;
    if (priority === 'meso') return `<circle cx="${half}" cy="${half}" r="${half - 2}" fill="#f97316" stroke="#020617" stroke-width="4"/><circle cx="${half}" cy="${half}" r="${half - 4}" fill="#f97316" stroke="#fff" stroke-width="1.6"/><path d="M8 15 A9 9 0 0 1 25 11" fill="none" stroke="#fff" stroke-width="3.2" stroke-linecap="round"/><path d="M25 11 L25 6 L30 6" fill="none" stroke="#fff" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"/><path d="M26 19 A9 9 0 0 1 9 23" fill="none" stroke="#fff" stroke-width="3.2" stroke-linecap="round"/><path d="M9 23 L9 28 L4 28" fill="none" stroke="#fff" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"/>${label('M', 21, 9)}`;
    if (priority === 'pos_hail') return `<polygon points="${half},2 ${size - 2},${size - 4} 2,${size - 4}" fill="#22c55e" stroke="#020617" stroke-width="4" stroke-linejoin="round"/><polygon points="${half},2 ${size - 2},${size - 4} 2,${size - 4}" fill="#22c55e" stroke="#fff" stroke-width="1.8" stroke-linejoin="round"/>${label('H', 25)}`;
    if (priority === 'prob_hail') return `<polygon points="${half},2 ${size - 2},${size - 4} 2,${size - 4}" fill="#020617" stroke="#22c55e" stroke-width="4" stroke-linejoin="round"/><polygon points="${half},2 ${size - 2},${size - 4} 2,${size - 4}" fill="#020617" stroke="#fff" stroke-width="1.3" stroke-linejoin="round"/>`;
    const inset = 4;
    return `<rect x="${inset}" y="${inset}" width="${size - inset * 2}" height="${size - inset * 2}" rx="2" fill="#cfcfcf" stroke="#020617" stroke-width="2"/><rect x="${inset + 2}" y="${inset + 2}" width="${size - inset * 2 - 4}" height="${size - inset * 2 - 4}" rx="1" fill="#111827" stroke="#facc15" stroke-width="2"/>`;
}

function stormCellIcon(leaflet, priority) {
    const size = priority === 'cell' ? 26 : 34;
    return leaflet.divIcon({
        className: '', iconSize: [size, size], iconAnchor: [size / 2, size / 2],
        html: `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" aria-hidden="true">${stormCellSvg(priority, size)}</svg>`,
    });
}

function stormTrackLegendHtml() {
    const items = [
        ['tvs', 'Tornadic Vortex Signature'], ['meso', 'Mesocyclone'],
        ['pos_hail', 'Confirmed Hail (POSH ≥50%)'], ['prob_hail', 'Probable Hail (POH ≥50%)'],
        ['cell', 'Storm Cell'],
    ].map(([priority, label]) => `<div class="core-legend-category"><span class="radar-storm-legend-icon"><svg width="20" height="20" viewBox="0 0 34 34" aria-hidden="true">${stormCellSvg(priority, 34)}</svg></span><div class="core-legend-category-copy"><span class="core-legend-category-code">${escapeHtml(label)}</span></div></div>`).join('');
    return `${legendHeader('Storm Tracks (NST)')}<div class="core-legend-body"><div class="core-legend-categories radar-storm-track-legend">${items}</div></div>`;
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
        onFrames, onFrameIndex, onSitePicked, onMessage, onStormTrackLegend } = options;
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
    let inspectorSequence = 0;
    let inspectorInFlight = false;
    let inspectorPending = false;
    let inspectorLatestLatLng = null;
    let inspectorSuppressed = false;
    let webglConfig = {
        enabled: false,
        animation_enabled: false,
        product: 'L2_REF',
        products: ['L2_REF'],
        animation_products: [],
        prefetch_zoom: 10,
        activate_zoom: 11,
        release_grace_ms: 1500,
        texture_budget: 4,
        min_forward_textures: 2,
        max_concurrent_loads: 2,
    };
    let webglLayer = null;
    const webglLoads = new Map();
    const webglFailedIdentities = new Set();
    let webglDesiredFrames = [];
    let webglScopeKey = '';
    let webglReleaseTimer = null;
    let webglCrossfadeTimer = null;
    let webglActive = false;
    let webglAnimationReady = false;
    let playbackActive = false;

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

    function restorePng() {
        clearTimeout(webglCrossfadeTimer);
        webglCrossfadeTimer = null;
        webglActive = false;
        webglLayer?.setActive(false);
        if (currentOverlay) currentOverlay.setOpacity(opacity);
    }

    function releaseWebgl() {
        clearTimeout(webglReleaseTimer);
        webglReleaseTimer = null;
        webglLoads.forEach(({ controller }) => controller.abort());
        webglLoads.clear();
        webglDesiredFrames = [];
        webglScopeKey = '';
        webglAnimationReady = false;
        restorePng();
        webglLayer?.release();
    }

    function ensureWebglLayer() {
        if (webglLayer) return webglLayer;
        webglLayer = createRadarWebglLayer({
            leaflet,
            map,
            paneName: 'radar-overlays',
            maxTextures: Math.max(1, Number(webglConfig.texture_budget) || 1),
            animationEnabled: true,
            onFailure() {
                const identity = frameIdentity(currentFrame);
                if (identity) webglFailedIdentities.add(identity);
                releaseWebgl();
            },
        });
        return webglLayer;
    }

    function webglSelectionSupported(frame) {
        return radarWebglProductEnabled(
            webglConfig,
            frame?.product || getSelection().product,
            playbackActive,
        );
    }

    function canUseWebgl(frame) {
        return webglSelectionSupported(frame) && !!frame?.webgl_artifact?.url;
    }

    function webglSelectionKey() {
        const selection = getSelection();
        const motion = selectedMotion();
        return [
            selection.site,
            selection.product,
            selection.elevation || 'auto',
            selection.hours || 1,
            motion?.speed ?? '',
            motion?.direction ?? '',
            motion?.cellId ?? '',
        ].join('|');
    }

    function cancelStaleWebglWork() {
        const scopeKey = webglSelectionKey();
        if (!webglScopeKey || webglScopeKey === scopeKey) return;
        releaseWebgl();
        webglFailedIdentities.clear();
    }

    function currentFrameIndex() {
        const identity = frameIdentity(currentFrame);
        return identity ? frames.findIndex((frame) => frameIdentity(frame) === identity) : -1;
    }

    function desiredWebglFrames() {
        const index = currentFrameIndex();
        if (index < 0 || !frames.length) return currentFrame ? [currentFrame] : [];
        if (
            !playbackActive
            || !radarWebglProductEnabled(webglConfig, getSelection().product, true)
            || frames.length < 2
        ) {
            return [frames[index]];
        }
        return selectRadarWebglWindow(
            frames,
            index,
            webglConfig.texture_budget,
            webglConfig.min_forward_textures,
        );
    }

    function hasMinimumForwardBuffer(index) {
        if (index < 0 || !webglLayer?.isReady(frameIdentity(frames[index]))) return false;
        const required = Math.min(
            Math.max(0, Number(webglConfig.min_forward_textures) || 0),
            Math.max(0, frames.length - 1),
        );
        for (let offset = 1; offset <= required; offset += 1) {
            if (!webglLayer.isReady(frameIdentity(frames[(index + offset) % frames.length]))) return false;
        }
        return true;
    }

    function activateWebgl(frame) {
        const identity = frameIdentity(frame);
        if (!identity || frameIdentity(currentFrame) !== identity || map.getZoom() < webglConfig.activate_zoom) return;
        if (!webglLayer?.isReady(identity)) return;
        if (playbackActive) {
            if (!radarWebglProductEnabled(webglConfig, getSelection().product, true)) return;
            if (!webglAnimationReady) {
                if (!hasMinimumForwardBuffer(currentFrameIndex())) return;
                webglAnimationReady = true;
            }
        }
        if (!webglLayer.setActive(true, opacity, identity)) return;
        webglActive = true;
        clearTimeout(webglCrossfadeTimer);
        webglCrossfadeTimer = setTimeout(() => {
            if (webglActive && frameIdentity(currentFrame) === identity && currentOverlay) {
                currentOverlay.setOpacity(0);
            }
        }, 150);
    }

    function pumpWebglLoads() {
        const layer = ensureWebglLayer();
        const maxLoads = Math.max(
            1,
            Math.min(4, Number(webglConfig.max_concurrent_loads) || 1),
        );
        for (const frame of webglDesiredFrames) {
            if (webglLoads.size >= maxLoads) break;
            const identity = frameIdentity(frame);
            if (
                !identity
                || layer.isReady(identity)
                || webglLoads.has(identity)
                || webglFailedIdentities.has(identity)
            ) continue;
            const controller = new AbortController();
            webglLoads.set(identity, { controller });
            void layer.load(
                overlayUrl(frame.webgl_artifact.url),
                identity,
                controller.signal,
                {
                    version: frame.webgl_artifact.version,
                    product: frame.webgl_artifact.product || frame.product,
                },
            )
                .then(() => {
                    if (webglDesiredFrames.some((item) => frameIdentity(item) === identity)) {
                        activateWebgl(currentFrame);
                    }
                })
                .catch((error) => {
                    if (error?.name !== 'AbortError') webglFailedIdentities.add(identity);
                })
                .finally(() => {
                    webglLoads.delete(identity);
                    pumpWebglLoads();
                });
        }
    }

    function warmWebglWindow() {
        webglDesiredFrames = desiredWebglFrames().filter(canUseWebgl);
        const desiredIdentities = webglDesiredFrames.map(frameIdentity);
        const allowed = new Set(desiredIdentities);
        webglLoads.forEach(({ controller }, identity) => {
            if (!allowed.has(identity)) controller.abort();
        });
        ensureWebglLayer().retain(desiredIdentities);
        pumpWebglLoads();
        activateWebgl(currentFrame);
    }

    function syncWebgl() {
        const zoom = map.getZoom();
        if (!currentFrame || !webglSelectionSupported(currentFrame)) {
            releaseWebgl();
            return;
        }
        const scopeKey = webglSelectionKey();
        cancelStaleWebglWork();
        webglScopeKey = scopeKey;
        if (zoom < webglConfig.activate_zoom) restorePng();
        if (zoom < webglConfig.prefetch_zoom) {
            if (!webglReleaseTimer) {
                webglReleaseTimer = setTimeout(
                    releaseWebgl,
                    Math.max(0, Number(webglConfig.release_grace_ms) || 0),
                );
            }
            return;
        }
        clearTimeout(webglReleaseTimer);
        webglReleaseTimer = null;
        warmWebglWindow();
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
        restorePng();
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
        syncWebgl();
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
        webglFailedIdentities.clear();
        releaseWebgl();
        selectedCell = null;
        frames = [];
        onFrames?.([], { index: 0 });
        stormLayer.clearLayers();
        if (map.hasLayer(stormLayer)) map.removeLayer(stormLayer);
        hideInspector();
        onStormTrackLegend?.(null);
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
            api.fetchJson('/api/radar/live/sites?config_revision=2', { cache: 'no-store' }),
            api.fetchJson('/api/radar/status', { cache: 'no-store' }).catch(() => ({ stations: {} })),
        ]);
        const rawStatus = radarStatus?.stations || {};
        statusMap = new Map(Object.entries(rawStatus).map(([key, value]) => [String(key).toUpperCase(), value]));
        const sites = Array.isArray(siteData?.sites) ? siteData.sites : [];
        Object.entries(siteData?.products || {}).forEach(([key, value]) => products.set(String(key).toUpperCase(), value));
        webglConfig = { ...webglConfig, ...(siteData?.webgl || {}) };
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

    async function loadFrames({
        refresh = false,
        preserveKey = null,
        latestPollAttempt = 0,
    } = {}) {
        const selection = { ...getSelection() };
        if (!selection.site || !selection.product) return [];
        cancelStaleWebglWork();
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
            const index = selectRadarFrameIndex(frames, currentFrame, preserveKey);
            onFrames?.(frames, { index: Math.max(0, index) });
            if (frames.length && index >= 0) await renderFrame(frames[index], index);
            if (!frames.length) message(`No radar frames found for ${selection.site}/${selection.product}.`);
            const pollMode = radarFramePollMode(data, refresh, latestPollAttempt);
            if (pollMode === 'history') {
                scheduleHistoryRefresh();
            } else if (pollMode === 'latest') {
                scheduleLatestRefresh(frameIdentity(currentFrame), latestPollAttempt);
            }
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

    function scheduleLatestRefresh(preserveKey, attempt) {
        clearTimeout(historyTimer);
        historyTimer = setTimeout(() => {
            void loadFrames({
                preserveKey,
                latestPollAttempt: attempt + 1,
            });
        }, 3000);
    }

    async function refreshAll({ refresh = true } = {}) {
        if (!getSelection().site) return;
        cancelStaleWebglWork();
        requestSequence += 1;
        const latestPromise = loadLatest();
        const framesPromise = loadFrames({ refresh });
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
            if (seq !== trackSequence || !tracksVisible || getSelection().site !== selection.site) return;
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
                const priority = properties.icon_priority || 'cell';
                const tooltipLabel = priority === 'tvs' ? `TVS Cell ${properties.cell_id || ''}`
                    : priority === 'meso' ? `Meso Cell ${properties.cell_id || ''}`
                    : priority === 'pos_hail' ? `Hail+ Cell ${properties.cell_id || ''}`
                    : priority === 'prob_hail' ? `Hail? Cell ${properties.cell_id || ''}`
                    : `NST ${properties.cell_id || ''}`;
                marker.bindTooltip(escapeHtml(tooltipLabel), { direction: 'top', className: 'core-city-name-tag' });
                marker.bindPopup(stormPopupHtml(properties));
                marker.on('mouseover', () => { inspectorSuppressed = true; hideInspector(); });
                marker.on('mouseout', () => { inspectorSuppressed = false; });
                marker.on('popupopen', () => { inspectorSuppressed = true; hideInspector(); });
                marker.on('popupclose', () => { inspectorSuppressed = false; });
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

    function cancelInspectorRequest() {
        inspectorSequence += 1;
        clearTimeout(inspectorTimer);
        inspectorTimer = null;
        inspectorController?.abort();
        inspectorController = null;
        inspectorInFlight = false;
        inspectorPending = false;
    }

    function hideInspector() {
        cancelInspectorRequest();
        if (inspectorElement) inspectorElement.remove();
        inspectorElement = null;
    }

    function positionInspector(latlng) {
        if (!inspectorElement || !latlng) return;
        const point = map.latLngToContainerPoint(latlng);
        inspectorElement.style.transform = `translate(${Math.round(point.x + 14)}px, ${Math.round(point.y - 14)}px)`;
    }

    async function requestInspector() {
        inspectorTimer = null;
        const selection = getSelection();
        if (!inspectorVisible || inspectorSuppressed || !currentOverlay || !selection.site || !inspectorLatestLatLng) return;
        if (inspectorInFlight) { inspectorPending = true; return; }
        const latlng = inspectorLatestLatLng;
        const seq = ++inspectorSequence;
        inspectorInFlight = true;
        inspectorPending = false;
        lastInspectorRequest = Date.now();
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
            if (seq !== inspectorSequence || !inspectorVisible || inspectorSuppressed || data?.status !== 'success') return;
            if (!inspectorElement) {
                inspectorElement = document.createElement('div');
                inspectorElement.className = 'radar-inspector-readout';
                map.getContainer().appendChild(inspectorElement);
            }
            const value = Number(data.value);
            inspectorElement.innerHTML = `<strong>${Number.isFinite(value) ? value.toFixed(Math.abs(value) < 10 ? 1 : 0) : '—'} ${escapeHtml(data.units || '')}</strong>
                <span>${escapeHtml(data.label || data.product || 'Radar')}</span>`;
            positionInspector(inspectorLatestLatLng || latlng);
        } catch (error) {
            if (error?.name !== 'AbortError') hideInspector();
        } finally {
            if (seq === inspectorSequence) {
                inspectorInFlight = false;
                inspectorController = null;
                if (inspectorPending && inspectorVisible && !inspectorSuppressed) scheduleInspector(0);
            }
        }
    }

    function scheduleInspector(delayOverride = null) {
        if (inspectorTimer) return;
        if (inspectorInFlight) { inspectorPending = true; return; }
        const elapsed = Date.now() - lastInspectorRequest;
        inspectorTimer = setTimeout(() => void requestInspector(), delayOverride ?? Math.max(0, 90 - elapsed));
    }

    function onMouseMove(event) {
        if (!inspectorVisible || inspectorSuppressed) return;
        inspectorLatestLatLng = event.latlng;
        positionInspector(event.latlng);
        scheduleInspector();
    }
    map.on('mousemove', onMouseMove);
    map.on('mouseout movestart zoomstart', hideInspector);
    map.on('zoomend', syncWebgl);

    return Object.freeze({
        clear: clearOverlays,
        configuredForSite(site) { return configuredSites.get(site) === true; },
        destroy() {
            requestSequence += 1;
            trackSequence += 1;
            clearTimeout(historyTimer); clearTimeout(retryTimer); clearTimeout(inspectorTimer);
            hideInspector(); clearOverlays();
            map.off('mousemove', onMouseMove);
            map.off('mouseout movestart zoomstart', hideInspector);
            map.off('zoomend', syncWebgl);
            webglLayer?.destroy();
            webglLayer = null;
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
            if (webglActive) webglLayer?.setActive(true, opacity);
            else if (currentOverlay) currentOverlay.setOpacity(opacity);
            return opacity;
        },
        setPlaybackActive(value) {
            playbackActive = !!value;
            webglAnimationReady = false;
            if (
                playbackActive
                && !radarWebglProductEnabled(webglConfig, getSelection().product, true)
            ) releaseWebgl();
            else syncWebgl();
        },
        setSitesVisible(value) { sitesVisible = !!value; syncSiteVisibility(); if (!sitesVisible) legend.clear(); },
        setStormTracksVisible(value) {
            tracksVisible = !!value;
            onStormTrackLegend?.(tracksVisible ? stormTrackLegendHtml() : null);
            if (tracksVisible) void loadStormTracks(currentFrame?.timestamp);
            else {
                trackSequence += 1;
                stormLayer.clearLayers();
                if (map.hasLayer(stormLayer)) map.removeLayer(stormLayer);
            }
        },
        showProductLegend: updateProductLegend,
        showSiteLegend,
        siteCoords(site) { return siteCoords.get(site) || null; },
        syncHighlights,
    });
}
