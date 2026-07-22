import { apiUrl } from '../../core/api.js';
import { createLegendHost } from '../../core/legend.js';
import { createMapCore } from '../../core/map-core.js';
import { renderProductNav } from '../../core/nav.js';
import { loadDefaultSettings } from '../../core/settings.js';
import { createSidebarTabs } from '../../core/sidebar-tabs.js';
import { createStatusReporter } from '../../core/status.js';

const byId = (id) => document.getElementById(id);
const L = window.L;
const _tropicalEngineFactory = window.NCHTropicalEngine;
const _tropicalPageController = window.NCHTropicalPage;
const mapCore = createMapCore(byId('weather-map'), { region: 'WORLD', basemap: 'Dark (No Labels)' });
const map = mapCore.map;
const legend = createLegendHost(byId('weather-colorbar'), { align: 'left' });
const status = createStatusReporter({
    globalTimestamp: byId('global-timestamp'), message: byId('weather-tropical-status'),
    updated: byId('tropical-updated'), age: byId('tropical-age'),
    provider: byId('tropical-provider'), source: byId('tropical-source'),
});
const sidebarTabs = createSidebarTabs(byId('tropical-sidebar-tabs'), { defaultTab: 'live' });

let _tropicalEngine = null;
let tropicalOutlookLayer = null;
let tropicalActiveSystemsLayer = null;
let graticuleLayer = null;
let _tropicalStorms = [];
let _activeTropicalStorm = null;
let _tropicalRequestSeq = 0;
let _tropicalArchiveCatalog = null;
let _tropicalArchiveSelectedId = null;
let _tropicalArchiveStormBase = null;
let _tropicalArchiveStormId = null;
let _tropicalArchiveStormName = null;
let _tropicalFixMarker = null;
let _tropicalArchiveReliabilityLabel = null;
let _activeOutlookDetail = null;
let _activeOutlookFeature = null;
let _outlookFeatureMap = {};
let _tropicalMapViewMode = 'outlook';
let _tropicalOutlookIssuedTime = null;
let _scrubberPlaybackSpeedIndex = 2;
let _selectedTropicalBasins = new Set(['WORLD']);
let _tropicalBasinFeedSeq = 0;

const SCRUBBER_PLAYBACK_SPEEDS = [0.25, 0.5, 1, 1.5, 2, 3, 4];
const REGION_FIT_BOTTOM_PADDING_PX = 120;
const TROPICAL_DEFAULT_CENTER = [22, -105];
const TROPICAL_DEFAULT_ZOOM = 3;
const ALERT_DEFAULT = '#6699cc';
const ALERT_COLORS = {
    'Hurricane Warning': '#DC143C', 'Hurricane Watch': '#FF00FF',
    'Tropical Storm Warning': '#B22222', 'Tropical Storm Watch': '#F08080',
    'Storm Surge Warning': '#B524F7', 'Storm Surge Watch': '#DB7FF7',
};

function _formatScrubberPlaybackSpeed(speed) {
    if (Number.isInteger(speed)) return `${speed}x`;
    return `${String(speed).replace(/0+$/, '').replace(/\.$/, '')}x`;
}

function escapeHtml(value) {
    return String(value ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;');
}
const _escapeHtml = escapeHtml;
function setLegend(html) { if (html) legend.setHtml(html); else legend.clear(); }
function _setTropicalLegend(title, bodyHtml, meta = '') {
    setLegend(`<div class="core-legend-header">
            <span class="core-legend-provider">NHC</span>
            <div class="core-legend-heading"><div class="core-legend-title">${escapeHtml(title)}</div></div>
            ${meta ? `<span class="core-legend-meta">${escapeHtml(meta)}</span>` : ''}
        </div><div class="core-legend-body">${bodyHtml}</div>`);
}
function setStatus(message) { status.setMessage(message); }
function _isTypeEnabled(type) { return type === 'tropical'; }
function _setViewerTimestamp(value) { if (value) status.setDataInfo({ timestamp: value, provider: 'NOAA NHC', source: 'Tropical' }); }
function _setReliability(_type, _label, provider, timestamp) { status.setDataInfo({ timestamp, provider, source: _label }); }
function _setTimestampSource(_type, source, timestamp) { status.setDataInfo({ timestamp, provider: 'NOAA NHC', source }); }
function _setSystemInspectorVisible(visible) {
    const rail = byId('tropical-system-inspector');
    const reopen = byId('tropical-system-open');
    const show = Boolean(visible && _tropicalMapViewMode === 'system');
    if (rail) rail.hidden = !show;
    document.querySelector('.tropical-app')?.classList.toggle('has-system-inspector', show);
    if (reopen) reopen.hidden = show || _tropicalMapViewMode !== 'system';
    requestAnimationFrame(() => map.invalidateSize({ animate: false }));
}

function _updateSystemInspectorAvailability() {
    _setSystemInspectorVisible(_tropicalMapViewMode === 'system');
}
function fitTropicalDefaultExtent() { map.setView(TROPICAL_DEFAULT_CENTER, TROPICAL_DEFAULT_ZOOM, { animate: false }); }
function _fitTropicalBasinExtent({ preserveSystem = false } = {}) {
    const selectedBasins = _selectedLiveBasinIds();
    const config = {
        AL: { bounds: [[-5, -125], [70, 0]], zoom: 5 }, EP: { bounds: [[0, -165], [60, -80]], zoom: 5 },
        CP: { bounds: [[0, -180], [45, -125]], zoom: 4 },
    }[_selectedTropicalBasins.has('WORLD') || selectedBasins.length !== 1 ? '' : selectedBasins[0]];
    if (!preserveSystem) {
        _setTropicalMapViewMode('both');
        _closeOutlookDetail();
        _closeTropicalDetail();
    }
    if (config) map.setView(L.latLngBounds(config.bounds).getCenter(), config.zoom, { animate: false });
    else fitTropicalDefaultExtent();
}

// ── Tropical Cyclones ───────────────────────────────────────────────────
function _setTropicalStatus(message) {
    const el = byId('weather-tropical-status');
    if (el) el.textContent = message || '';
}

function _selectedLiveBasinIds() {
    return _selectedTropicalBasins.has('WORLD') ? ['AL', 'EP', 'CP'] : [..._selectedTropicalBasins];
}

function _filterLiveStorms(storms) {
    const basins = new Set(_selectedLiveBasinIds());
    return (Array.isArray(storms) ? storms : []).filter((storm) => basins.has(String(storm?.basin || '').toUpperCase()));
}

function _activeTropicalSystemId() {
    return String(byId('weather-tropical-system')?.value || '').trim().toUpperCase();
}

function _setTropicalHubMode(mode) {
    const root = byId('wx-section-tropical');
    if (!root) return;
    root.setAttribute('data-tropical-mode', mode === 'selected' ? 'selected' : 'overview');
}

const TROPICAL_KT_TO_MPH = 1.15078;
const _COMPASS_16 = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
    'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW'];

function _ktToMph(kt) {
    const n = Number(kt);
    return Number.isFinite(n) ? Math.round((n * TROPICAL_KT_TO_MPH) / 5) * 5 : null;
}

function _degToCompass(deg) {
    const n = Number(deg);
    if (!Number.isFinite(n)) return '';
    return _COMPASS_16[Math.round((((n % 360) + 360) % 360) / 22.5) % 16];
}

function _tropicalMotionText(storm) {
    const dirRaw = storm?.movementDir;
    let dir = '';
    if (typeof dirRaw === 'number' || /^\d+$/.test(String(dirRaw ?? '').trim())) {
        dir = _degToCompass(dirRaw);
    } else if (dirRaw) {
        dir = String(dirRaw).toUpperCase();
    }
    const mph = _ktToMph(storm?.movementSpeed);
    if (mph === 0) return 'Stationary';
    if (mph == null) return dir;
    return `${dir} ${mph} mph`.trim();
}

function _highlightSelectedTropicalCard() {
    _tropicalPageController?.highlightSelectedCard?.();
}

function _selectTropicalStormCard(stormId) {
    if (!stormId) return;
    const select = byId('weather-tropical-system');
    if (select) select.value = stormId;
    _setTropicalHubMode('selected');
    _closeTropicalDetail();
    _closeOutlookDetail();
    _setTropicalMapViewMode('system');
    _tropicalEngine?.loadStormDetail(stormId, { fitBounds: false, zoomToLatest: true });
    _highlightSelectedTropicalCard();
}

function _clearFilteredLiveStorm() {
    const select = byId('weather-tropical-system');
    if (select) select.value = '';
    _activeTropicalStorm = null;
    _clearTropicalLayer();
    _renderTropicalSummary(null);
    _setTropicalHubMode('overview');
    _setTropicalMapViewMode('both');
    _highlightSelectedTropicalCard();
    _renderTropicalOutlookLegend();
}

function _wireLiveAccordions() {
    document.querySelectorAll('[data-live-accordion]').forEach((button) => {
        button.addEventListener('click', () => {
            const panel = button.closest('.wx-live-accordion');
            if (!panel) return;
            const open = panel.dataset.open !== 'true';
            panel.dataset.open = String(open);
            button.setAttribute('aria-expanded', String(open));
        });
    });
}

function _syncLiveBasinPills() {
    document.querySelectorAll('[data-live-basin]').forEach((button) => {
        button.setAttribute('aria-pressed', String(_selectedTropicalBasins.has(button.dataset.liveBasin)));
    });
}

function _selectLiveBasin(basin) {
    if (basin === 'WORLD') {
        _selectedTropicalBasins = new Set(['WORLD']);
    } else {
        _selectedTropicalBasins.delete('WORLD');
        if (_selectedTropicalBasins.has(basin)) _selectedTropicalBasins.delete(basin);
        else _selectedTropicalBasins.add(basin);
        if (!_selectedTropicalBasins.size) _selectedTropicalBasins.add('WORLD');
    }
    _syncLiveBasinPills();
    _closeOutlookDetail();
    const selectedStormId = _activeTropicalSystemId();
    const selectedStorm = _tropicalStorms.find((storm) => String(storm?.id || '').toUpperCase() === selectedStormId);
    const selectionRemainsVisible = selectedStorm && _selectedLiveBasinIds().includes(String(selectedStorm?.basin || '').toUpperCase());
    if (selectedStormId && !selectionRemainsVisible) _clearFilteredLiveStorm();
    _fitTropicalBasinExtent({ preserveSystem: Boolean(selectionRemainsVisible) });
    void _tropicalEngine.loadStorms();
}

function _wireLiveBasinPills() {
    document.querySelectorAll('[data-live-basin]').forEach((button) => {
        button.addEventListener('click', () => _selectLiveBasin(button.dataset.liveBasin));
    });
    _syncLiveBasinPills();
}

const _TROPICAL_BASIN_NAMES = { AL: 'Atlantic', EP: 'Eastern Pacific', CP: 'Central Pacific' };

function _outlookChip(pct, category, label) {
    if (pct == null) return '';
    const color = { low: '#ffd400', medium: '#ff8c00', high: '#e60000' }[category?.toLowerCase()] || '#9ca3af';
    return `<span class="wx-tropical-chip" style="--chip-color:${color};">${label} ${pct}%</span>`;
}

function _formatTropicalOutlookText(value) {
    return String(value || '').replace(/Gulf of America/gi, 'Gulf');
}

function _tropicalOutlookAreaCardHtml(area, basin, feature) {
    const name = area?.name || `Disturbance ${area?.disturbance || ''}`;
    const displayName = _formatTropicalOutlookText(name);
    const color = area?.color || '#9ca3af';
    const basinName = _TROPICAL_BASIN_NAMES[basin] || basin;
    const chips = [
        _outlookChip(area?.twoDayPct, area?.twoDayCategory, '2-DAY'),
        _outlookChip(area?.sevenDayPct, area?.sevenDayCategory, '7-DAY'),
    ].filter(Boolean).join('');
    const featureId = feature ? `outlook-${Date.now()}-${Math.random().toString(36).slice(2, 9)}` : '';
    if (featureId && feature) _outlookFeatureMap[featureId] = feature;
    const dataAttr = featureId ? ` data-feature-id="${featureId}"` : '';
    return `
        <button type="button" class="wx-tropical-outlook-card" style="--oc-cat-color:${color};"${dataAttr} aria-label="Open outlook details for ${escapeHtml(displayName)}">
            <span class="wx-tropical-outlook-bar" aria-hidden="true"></span>
            <span class="wx-tropical-outlook-body">
                <span class="wx-tropical-outlook-basin">${escapeHtml(basinName)}</span>
                <span class="wx-tropical-outlook-name">${escapeHtml(displayName)}</span>
                ${chips ? `<span class="wx-tropical-outlook-chips">${chips}</span>` : ''}
            </span>
        </button>`;
}

function _tropicalOutlookQuietCardHtml(basin) {
    return `
        <div class="wx-tropical-outlook-card wx-tropical-outlook-quiet">
            <span class="wx-tropical-outlook-body">
                <span class="wx-tropical-outlook-basin">${escapeHtml(_TROPICAL_BASIN_NAMES[basin] || basin)}</span>
                <span class="wx-tropical-outlook-label">No tropical development expected</span>
                <span class="wx-tropical-outlook-period">Next 7 days</span>
            </span>
        </div>`;
}

function _tropicalOutlookUnavailableCardHtml() {
    return `
        <div class="wx-tropical-empty-card">
            <div class="wx-tropical-empty-title">Outlook unavailable</div>
            <div class="wx-tropical-empty-note">
                Tropical outlook data could not be loaded for the selected regions.
            </div>
        </div>`;
}

function _attachOutlookCardClickHandlers() {
    const cards = document.querySelectorAll('.wx-tropical-outlook-card[data-feature-id]');
    cards.forEach((card) => {
        const featureId = card.getAttribute('data-feature-id');
        card.addEventListener('click', () => {
            const feature = _outlookFeatureMap[featureId];
            if (feature) _highlightOutlookFeature(feature);
        });
    });
}

function _renderTropicalOutlookCards(feedPayloads) {
    const box = byId('weather-tropical-outlook-cards');
    if (!box) return;
    const feeds = Array.isArray(feedPayloads) ? feedPayloads : [feedPayloads].filter(Boolean);
    const count = byId('weather-tropical-outlook-count');
    let activeAreaCount = 0;
    if (!feeds.length) {
        if (count) count.textContent = '0';
        box.innerHTML = _tropicalOutlookUnavailableCardHtml();
        return;
    }
    const cards = feeds.map((feed) => {
        const basin = feed?.basin || '';
        const gtwo = feed?.gtwo;
        if (!gtwo) return _tropicalOutlookQuietCardHtml(basin);
        if (gtwo.notExpected) return _tropicalOutlookQuietCardHtml(basin);
        const geojson = gtwo.geojson;
        const features = (geojson?.features || []).filter((f) => f.geometry?.type === 'Polygon');
        if (!features.length) return _tropicalOutlookQuietCardHtml(basin);
        activeAreaCount += features.length;
        return features.map((feat) => {
            const area = feat.properties || {};
            return _tropicalOutlookAreaCardHtml(area, basin, feat);
        }).join('');
    }).filter(Boolean);
    if (count) count.textContent = String(activeAreaCount);
    box.innerHTML = cards.join('');
}

async function loadTropicalBasinFeeds() {
    if (!_isTypeEnabled('tropical')) return;
    const requestSeq = ++_tropicalBasinFeedSeq;
    const basins = _selectedLiveBasinIds();
    try {
        const payloads = await Promise.all(basins.map(async (basinId) => {
            const resp = await fetch(apiUrl(`/api/tropical/basin/${encodeURIComponent(basinId)}/feeds`), { cache: 'no-store' });
            if (!resp.ok) throw new Error(`${basinId} HTTP ${resp.status}`);
            return resp.json();
        }));
        if (requestSeq !== _tropicalBasinFeedSeq) return;
        _renderTropicalOutlookCards(payloads);
        const allGeojson = payloads
            .flatMap((p) => (p?.gtwo?.geojson?.features || []))
            .filter((f) => f.geometry && f.geometry.type && f.geometry.coordinates);
        if (allGeojson.length) {
            _renderTropicalOutlookLayer({ type: 'FeatureCollection', features: allGeojson });
        }
        _attachOutlookCardClickHandlers();

        // Extract GTWO metadata from first available payload for reliability/timestamp.
        // The KML title carries basin + timestamp ("... - North Atlantic basin - <date>");
        // trim to just the product name since both basins are shown together.
        const gtwoPrimary = payloads.find((p) => p?.gtwo?.updated || p?.gtwo?.issued);
        if (gtwoPrimary?.gtwo) {
            _tropicalOutlookIssuedTime = gtwoPrimary.gtwo.updated;
            // Only refresh the bar/HUD from the outlook when no storm is selected,
            // so a loaded storm advisory's timestamp isn't overwritten by a feed refresh.
            if (!_activeTropicalStorm) _applyOutlookReliability();
        }
    } catch (err) {
        if (requestSeq !== _tropicalBasinFeedSeq) return;
        console.error('[tropical] Basin feed load error:', err);
        _renderTropicalOutlookCards(null);
        _clearTropicalOutlookLayer();
    }
}

function _clearTropicalLayer() {
    _tropicalEngine?.clearLayer?.();
}

function _clearTropicalOutlookLayer() {
    if (tropicalOutlookLayer && map.hasLayer(tropicalOutlookLayer)) map.removeLayer(tropicalOutlookLayer);
    tropicalOutlookLayer = null;
    _activeOutlookFeature = null;
}

function _clearActiveSystemsOverview() {
    if (tropicalActiveSystemsLayer && map.hasLayer(tropicalActiveSystemsLayer)) {
        map.removeLayer(tropicalActiveSystemsLayer);
    }
    tropicalActiveSystemsLayer = null;
}

function _renderActiveSystemsOverview(storms) {
    _clearActiveSystemsOverview();
    const layer = L.layerGroup();
    (Array.isArray(storms) ? storms : []).forEach((storm) => {
        const latlng = _tropicalStormLatLng(storm);
        const stormId = String(storm?.id || '').toUpperCase();
        if (!latlng || !stormId) return;
        const marker = L.marker(latlng, {
            icon: _tropicalCategoryIcon({
                STORMTYPE: storm?.classification,
                MAXWIND: storm?.intensity,
                TAU: 0,
            }),
            zIndexOffset: 900,
        });
        const name = storm?.name || stormId;
        marker.bindTooltip(`${escapeHtml(name)} · ${escapeHtml(_tropicalWindClass(storm?.intensity))}`);
        marker.on('click', () => _selectTropicalStormCard(stormId));
        marker.addTo(layer);
    });
    tropicalActiveSystemsLayer = layer;
    if (layer.getLayers().length) layer.addTo(map);
    if (_tropicalMapViewMode !== 'system') _renderTropicalOutlookLegend();
}

// Inject the GTWO hatch patterns into the SVG that actually contains the rendered
// polygon path (svgRoot = path.ownerSVGElement).
// Doing this AFTER the layer is on the map avoids a cold-load race in Chromium/Edge
// where the Leaflet SVG doesn't exist yet and the fill resolves to a missing pattern.
const _TROPICAL_OUTLOOK_PATTERNS = [
    { key: 'low', color: '#ffd400' },
    { key: 'medium', color: '#ff8c00' },
    { key: 'high', color: '#e60000' },
];
function _ensureTropicalPatternDefs(svgRoot) {
    if (!svgRoot) return;
    const svgNS = 'http://www.w3.org/2000/svg';
    let defs = svgRoot.querySelector('defs');
    if (!defs) {
        defs = document.createElementNS(svgNS, 'defs');
        svgRoot.insertBefore(defs, svgRoot.firstChild);
    }
    _TROPICAL_OUTLOOK_PATTERNS.forEach(({ key, color }) => {
        const id = `hatch-outlook-${key}`;
        if (defs.querySelector(`#${id}`)) return;
        const pattern = document.createElementNS(svgNS, 'pattern');
        pattern.setAttribute('id', id);
        pattern.setAttribute('width', '10');
        pattern.setAttribute('height', '10');
        pattern.setAttribute('patternUnits', 'userSpaceOnUse');
        pattern.setAttribute('patternTransform', 'rotate(45)');
        const line = document.createElementNS(svgNS, 'line');
        line.setAttribute('x1', '0');
        line.setAttribute('y1', '0');
        line.setAttribute('x2', '0');
        line.setAttribute('y2', '10');
        line.setAttribute('stroke', color);
        line.setAttribute('stroke-width', '5');
        line.setAttribute('stroke-linecap', 'round');
        pattern.appendChild(line);
        defs.appendChild(pattern);
    });
}

// Apply the hatch fill to each rendered polygon path after the group is on the map.
function _applyTropicalOutlookHatching(group) {
    if (!group || typeof group.eachLayer !== 'function') return;
    const applyTo = (sub) => {
        const props = sub?.feature?.properties;
        if (!sub?._path || !props || sub.feature?.geometry?.type !== 'Polygon') return;
        const cat = props.category && props.category !== 'none' ? props.category : 'low';
        _ensureTropicalPatternDefs(sub._path.ownerSVGElement);
        sub._path.setAttribute('fill', `url(#hatch-outlook-${cat})`);
        sub._path.setAttribute('fill-opacity', '1');
    };
    group.eachLayer((child) => {
        if (typeof child.eachLayer === 'function') child.eachLayer(applyTo);
        else applyTo(child);
    });
}

function _renderTropicalOutlookLayer(geojson) {
    _clearTropicalOutlookLayer();
    if (!geojson || !geojson.features || !geojson.features.length) return;
    const group = L.featureGroup();
    const polygons = geojson.features.filter((f) => f.geometry?.type === 'Polygon');
    const points = geojson.features.filter((f) => f.geometry?.type === 'Point');
    const lines = geojson.features.filter((f) => f.geometry?.type === 'LineString');

    polygons.forEach((feature) => {
        // Solid fallback fill; the hatch pattern is applied after the layer is on the
        // map (see _applyTropicalOutlookHatching) so the SVG/pattern always exist first.
        const color = feature.properties?.color || '#9ca3af';
        const layer = L.geoJSON(feature, {
            style: {
                color: '#555',
                weight: 2,
                opacity: 0.8,
                fill: true,
                fillOpacity: 0.25,
                fillColor: color,
            },
        });
        const props = feature.properties || {};
        const area = props.disturbance || props.area || '';
        const twoDay = props.twoDayPct != null ? `${props.twoDayPct}%` : '—';
        const sevenDay = props.sevenDayPct != null ? `${props.sevenDayPct}%` : '—';
        layer.bindTooltip(
            `<strong>Area ${escapeHtml(area || '—')}</strong><br>2-day: ${escapeHtml(twoDay)}<br>7-day: ${escapeHtml(sevenDay)}`,
            { direction: 'top', className: 'core-city-name-tag' },
        );
        layer.on('click', () => _highlightOutlookFeature(feature));
        group.addLayer(layer);
    });

    points.forEach((feature) => {
        const props = feature.properties || {};
        const disturbance = props.disturbance || '';
        const color = props.color || '#9ca3af';
        const layer = L.geoJSON(feature, {
            pointToLayer: (f, latlng) => {
                const svgSize = 30;
                // Light halo drawn under the colored glyph so the marker stays legible
                // against hatched outlook polygons.
                const svgString = `<svg xmlns="http://www.w3.org/2000/svg" width="${svgSize}" height="${svgSize}" viewBox="0 0 20 20">
                    <line x1="4" y1="4" x2="16" y2="16" stroke="${color}" stroke-width="3"/>
                    <line x1="16" y1="4" x2="4" y2="16" stroke="${color}" stroke-width="3"/>
                </svg>`;
                const icon = L.divIcon({
                    html: svgString,
                    iconSize: [svgSize, svgSize],
                    className: 'tropical-disturbance-marker',
                });
                return L.marker(latlng, { icon });
            },
            onEachFeature: (f, lyr) => {
                if (disturbance) lyr.bindTooltip(`Disturbance ${disturbance}`);
            },
        });
        group.addLayer(layer);
    });

    lines.forEach((feature) => {
        const props = feature.properties || {};
        const color = props.color || '#666';
        const layer = L.geoJSON(feature, {
            style: {
                color: color,
                weight: 2.5,
                opacity: 0.7,
                dashArray: '5, 5',
            },
        });
        group.addLayer(layer);
    });

    if (group.getLayers().length) {
        tropicalOutlookLayer = group;
        if (_tropicalMapViewMode !== 'system') {
            group.addTo(map);
            // Patterns are injected + assigned now that each polygon path exists in the SVG.
            _applyTropicalOutlookHatching(group);
        }
    }
}

function _removeGraticule() {
    if (graticuleLayer && map.hasLayer(graticuleLayer)) {
        map.removeLayer(graticuleLayer);
    }
    graticuleLayer = null;
}

function _setTropicalMapViewMode(mode) {
    _tropicalMapViewMode = mode;
    const showOutlook = mode === 'outlook' || mode === 'both';
    const showSystem = mode === 'system' || mode === 'both';

    // Outlook layer: Leaflet's removeLayer/addLayer destroys and recreates the SVG
    // paths using the solid fallback fill, dropping the manually-assigned
    // url(#hatch-outlook-*) fill. So re-apply the hatching every time it's shown.
    if (tropicalOutlookLayer) {
        if (showOutlook) {
            if (!map.hasLayer(tropicalOutlookLayer)) map.addLayer(tropicalOutlookLayer);
            _applyTropicalOutlookHatching(tropicalOutlookLayer);
        } else if (map.hasLayer(tropicalOutlookLayer)) {
            map.removeLayer(tropicalOutlookLayer);
        }
    }

    _tropicalEngine?.setLayerVisible?.(showSystem);

    _updateSystemInspectorAvailability();
}

function _addGraticule() {
    _removeGraticule();
    const group = L.featureGroup();
    const mainLineStyle = { color: '#cecece', weight: 1.5, opacity: 0.5, dashArray: '2, 2' };
    const lightLineStyle = { color: '#cecece', weight: 1.0, opacity: 0.3, dashArray: '2, 2' };
    const tinyLineStyle = { color: '#cecece', weight: 1.0, opacity: 0.15, dashArray: '5, 5' };

    // Latitude lines (horizontal, every 1 degree from -90 to 90)
    for (let lat = -90; lat <= 90; lat += 1) {
        let style;
        if (lat % 10 === 0) {
            style = mainLineStyle;
        } else if (lat % 5 === 0) {
            style = lightLineStyle;
        } else {
            style = tinyLineStyle;
        }
        const line = L.polyline([[lat, -180], [lat, 180]], style);
        group.addLayer(line);
    }

    // Longitude lines (vertical, every 1 degree from -180 to 180)
    for (let lon = -180; lon < 180; lon += 1) {
        let style;
        if (lon % 10 === 0) {
            style = mainLineStyle;
        } else if (lon % 5 === 0) {
            style = lightLineStyle;
        } else {
            style = tinyLineStyle;
        }
        const line = L.polyline([[-90, lon], [90, lon]], style);
        group.addLayer(line);
    }

    graticuleLayer = group.addTo(map);
}

// Restore the global reliability bar + timestamp HUD to the GTWO outlook source.
// Used whenever the view returns to the outlook (no storm selected).
function _applyOutlookReliability() {
    if (!_tropicalOutlookIssuedTime) return;
    _setReliability('tropical', 'Tropical Weather Outlook', 'NOAA NHC', _tropicalOutlookIssuedTime);
    _setTimestampSource('tropical', 'Graphical Tropical Weather Outlook', _tropicalOutlookIssuedTime);
    _setViewerTimestamp(_tropicalOutlookIssuedTime);
}

function _highlightOutlookFeature(feature) {
    _activeOutlookFeature = feature;
    if (!feature.geometry || feature.geometry.type !== 'Polygon') return;
    const coords = feature.geometry.coordinates[0];
    if (!coords || !coords.length) return;
    const bounds = L.latLngBounds(coords.map((c) => [c[1], c[0]]));
    map.fitBounds(bounds, { padding: [60, 60], maxZoom: 6 });
    _closeTropicalDetail();
    // Deselect any active storm and close the contextual System inspector.
    _renderTropicalSummary(null);
    _setTropicalMapViewMode('outlook');
    _renderTropicalOutlookLegend();
    _applyOutlookReliability();
    _openOutlookDetail(feature);
}

function _closeOutlookDetail() {
    if (!_activeOutlookDetail) return;
    const { panel, keyHandler, dragCleanup } = _activeOutlookDetail;
    document.removeEventListener('keydown', keyHandler);
    if (dragCleanup) dragCleanup();
    panel?.remove();
    _activeOutlookDetail = null;
}

function _openOutlookDetail(feature) {
    const props = feature?.properties || {};
    const name = _formatTropicalOutlookText(props.name || 'Formation Area');
    const discussion = _formatTropicalOutlookText(props.discussion || '');
    const issued = props.issued || '';
    const twoDayPct = props.twoDayPct;
    const sevenDayPct = props.sevenDayPct;
    const twoDayCategory = props.twoDayCategory || '';
    const sevenDayCategory = props.sevenDayCategory || '';
    const disturbance = _formatTropicalOutlookText(props.disturbance || '');
    const titleText = disturbance ? `Area ${disturbance}: ${name}` : name;

    _closeOutlookDetail();
    const wrap = document.querySelector('.weather-map-wrap');
    if (!wrap) return;
    const panel = document.createElement('div');
    panel.id = 'wx-outlook-detail-panel';
    panel.className = 'wx-nad-panel is-right';
    panel.innerHTML = `
        <div class="wx-nad-header">
            <div class="wx-nad-title">${escapeHtml(titleText)}</div>
            <button class="wx-nad-close" type="button" aria-label="Close">×</button>
        </div>
        <div class="wx-nad-content">
            ${issued ? `<div class="wx-nad-issued">Issued: ${escapeHtml(issued)}</div>` : ''}
            <div class="wx-nad-chips">
                ${twoDayPct != null ? `<span class="wx-nad-chip" data-severity="info">2-DAY ${twoDayPct}%</span>` : ''}
                ${sevenDayPct != null ? `<span class="wx-nad-chip" data-severity="info">7-DAY ${sevenDayPct}%</span>` : ''}
            </div>
            <div class="wx-nad-text">${escapeHtml(discussion)}</div>
        </div>`;
    wrap.appendChild(panel);

    let drag = null;
    const onDragMove = (evt) => {
        if (!drag) return;
        panel.style.left = `${evt.clientX - drag.wrapLeft - drag.dx}px`;
        panel.style.top = `${evt.clientY - drag.wrapTop - drag.dy}px`;
        panel.style.right = 'auto';
        panel.style.transform = 'none';
        panel.classList.remove('is-right', 'is-left');
    };
    const onDragUp = () => {
        drag = null;
        document.removeEventListener('pointermove', onDragMove);
        document.removeEventListener('pointerup', onDragUp);
    };
    const dragCleanup = () => {
        document.removeEventListener('pointermove', onDragMove);
        document.removeEventListener('pointerup', onDragUp);
    };

    const keyHandler = (e) => {
        if (e.key === 'Escape') _closeOutlookDetail();
    };
    document.addEventListener('keydown', keyHandler);

    panel.querySelector('.wx-nad-close')?.addEventListener('click', _closeOutlookDetail);
    panel.querySelector('.wx-nad-header')?.addEventListener('pointerdown', (evt) => {
        if (evt.target && evt.target.closest('.wx-nad-close, a, button')) return;
        const wrapRect = wrap.getBoundingClientRect();
        const rect = panel.getBoundingClientRect();
        panel.style.left = `${rect.left - wrapRect.left}px`;
        panel.style.top = `${rect.top - wrapRect.top}px`;
        panel.style.right = 'auto';
        panel.style.transform = 'none';
        panel.classList.remove('is-right', 'is-left');
        drag = {
            dx: evt.clientX - rect.left,
            dy: evt.clientY - rect.top,
            wrapLeft: wrapRect.left,
            wrapTop: wrapRect.top,
        };
        evt.preventDefault();
        document.addEventListener('pointermove', onDragMove);
        document.addEventListener('pointerup', onDragUp);
    });

    _activeOutlookDetail = { panel, keyHandler, dragCleanup };
}

function _tropicalStormLatLng(storm) {
    const lat = Number(storm?.latitudeNumeric ?? storm?.lat);
    const lon = Number(storm?.longitudeNumeric ?? storm?.lon ?? storm?.lng);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null;
    return [lat, lon];
}

function _tropicalWindClass(windKt) {
    const kt = Number(windKt);
    if (!Number.isFinite(kt)) return 'System';
    if (kt >= 137) return 'Category 5';
    if (kt >= 113) return 'Category 4';
    if (kt >= 96) return 'Category 3';
    if (kt >= 83) return 'Category 2';
    if (kt >= 64) return 'Category 1';
    if (kt >= 34) return 'Tropical Storm';
    return 'Depression';
}

// Saffir-Simpson + tropical classification palette (coast.noaa.gov hurricane viewer aligned).
// Single source of truth for marker icons, storm-card bars, and the Inspector legend.
const TROPICAL_CATEGORIES = {
    '5': { color: '#bd00ff', label: 'Category 5', icon: 'hurricane' },
    '4': { color: '#e80cae', label: 'Category 4', icon: 'hurricane' },
    '3': { color: '#e83b0c', label: 'Category 3', icon: 'hurricane' },
    '2': { color: '#ff7209', label: 'Category 2', icon: 'hurricane' },
    '1': { color: '#ffc309', label: 'Category 1', icon: 'hurricane' },
    TS: { color: '#6cc343', label: 'Tropical Storm', icon: 'tropical-storm' },
    TD: { color: '#1c54ff', label: 'Tropical Depression', icon: 'circle' },
    OTHER: { color: '#aaaaaa', label: 'Post/Extratropical', icon: 'x-circle' },
};
const TROPICAL_CATEGORY_ORDER = ['5', '4', '3', '2', '1', 'TS', 'TD', 'OTHER'];

// Bootstrap-icon glyph paths (fill set per-category). White halo toggles via TROPICAL_ICON_HALO
// (flip to false for flat, un-haloed icons).
const TROPICAL_ICON_HALO = true;
const _TROPICAL_ICON_PATHS = {
    hurricane: '<path d="M6.999 2.6A5.5 5.5 0 0 1 15 7.5a.5.5 0 0 0 1 0 6.5 6.5 0 1 0-13 0 5 5 0 0 0 6.001 4.9A5.5 5.5 0 0 1 1 7.5a.5.5 0 0 0-1 0 6.5 6.5 0 1 0 13 0 5 5 0 0 0-6.001-4.9M10 7.5a2 2 0 1 1-4 0 2 2 0 0 1 4 0"/>',
    'tropical-storm': '<path d="M8 9.5a2 2 0 1 0 0-4 2 2 0 0 0 0 4"/><path d="M9.5 2c-.9 0-1.75.216-2.501.6A5 5 0 0 1 13 7.5a6.5 6.5 0 1 1-13 0 .5.5 0 0 1 1 0 5.5 5.5 0 0 0 8.001 4.9A5 5 0 0 1 3 7.5a6.5 6.5 0 0 1 13 0 .5.5 0 0 1-1 0A5.5 5.5 0 0 0 9.5 2M8 3.5a4 4 0 1 0 0 8 4 4 0 0 0 0-8"/>',
    circle: '<circle cx="8" cy="8" r="8"/>',
    'x-circle': '<path d="M8 15A7 7 0 1 1 8 1a7 7 0 0 1 0 14m0 1A8 8 0 1 0 8 0a8 8 0 0 0 0 16"/><path d="M4.646 4.646a.5.5 0 0 1 .708 0L8 7.293l2.646-2.647a.5.5 0 0 1 .708.708L8.707 8l2.647 2.646a.5.5 0 0 1-.708.708L8 8.707l-2.646 2.647a.5.5 0 0 1-.708-.708L7.293 8 4.646 5.354a.5.5 0 0 1 0-.708"/>',
};

function _tropicalCategoryKeyFromWind(windKt) {
    const kt = Number(windKt);
    if (!Number.isFinite(kt)) return 'OTHER';
    if (kt >= 137) return '5';
    if (kt >= 113) return '4';
    if (kt >= 96) return '3';
    if (kt >= 83) return '2';
    if (kt >= 64) return '1';
    if (kt >= 34) return 'TS';
    return 'TD';
}

function _tropicalCategoryKey(props = {}) {
    const stormType = String(props.STORMTYPE || props.TCDVLP || '').trim().toUpperCase();
    if (stormType.includes('REMNANT') || stormType === 'LO'
        || stormType.includes('EXTRATROPICAL') || stormType === 'EX'
        || stormType.includes('POST') || stormType === 'PT' || stormType === 'PTC') {
        return 'OTHER';
    }
    const ssnum = Number(props.SSNUM ?? props.SS);
    if (Number.isFinite(ssnum) && ssnum >= 1 && ssnum <= 5) return String(ssnum);
    // Best-track segments carry STORMTYPE + SS but no MAXWIND; classify by type so a
    // tropical-storm/depression segment isn't mis-colored as "other".
    if (stormType === 'TS' || stormType === 'SS' || stormType.includes('STORM')) return 'TS';
    if (stormType === 'TD' || stormType === 'SD' || stormType === 'DB' || stormType === 'WV') return 'TD';
    return _tropicalCategoryKeyFromWind(props.MAXWIND);
}

function _tropicalCategoryColor(key) {
    return (TROPICAL_CATEGORIES[key] || TROPICAL_CATEGORIES.OTHER).color;
}

function _tropicalPointColor(windKt) {
    return _tropicalCategoryColor(_tropicalCategoryKeyFromWind(windKt));
}

function _tropicalPointCategory(props = {}) {
    const stormType = String(props.STORMTYPE || props.TCDVLP || '').trim().toUpperCase();
    const ssnum = Number(props.SSNUM ?? props.SS);
    const windKt = Number(props.MAXWIND);
    if (stormType.includes('REMNANT') || stormType === 'LO') return 'R';
    if (stormType.includes('EXTRATROPICAL') || stormType === 'EX') return 'E';
    if (stormType.includes('POST') || stormType === 'PT' || stormType === 'PTC') return 'P';
    if (Number.isFinite(ssnum) && ssnum >= 3) return 'M';
    if (Number.isFinite(windKt) && windKt >= 96) return 'M';
    if (stormType.includes('HURRICANE') || stormType === 'HU' || (Number.isFinite(windKt) && windKt >= 64)) return 'H';
    if (stormType.includes('STORM') || stormType === 'TS' || stormType === 'SS' || (Number.isFinite(windKt) && windKt >= 34)) return 'S';
    return 'D';
}

function _tropicalCategoryIcon(props = {}) {
    const cat = TROPICAL_CATEGORIES[_tropicalCategoryKey(props)] || TROPICAL_CATEGORIES.OTHER;
    const tau = Number(props.TAU);
    const size = tau === 0 ? 33 : 26;
    const haloClass = TROPICAL_ICON_HALO ? ' wx-tc-halo' : '';
    return L.divIcon({
        className: 'wx-tropical-category-icon',
        html: `<span class="wx-tc-glyph${haloClass}" style="--tc-size:${size}px;">`
            + `<svg viewBox="0 0 16 16" width="${size}" height="${size}" fill="${cat.color}" aria-hidden="true">${_TROPICAL_ICON_PATHS[cat.icon]}</svg></span>`,
        iconSize: [size, size],
        iconAnchor: [size / 2, size / 2],
    });
}

// Floating map legend, matching the SPC/MRMS style (shared setLegend panel) but using the
// tinted marker glyphs instead of square swatches so the legend matches the map 1:1.
function _renderTropicalLegend() {
    if (_tropicalMapViewMode !== 'system') return;
    const items = TROPICAL_CATEGORY_ORDER.map((key) => {
        const cat = TROPICAL_CATEGORIES[key];
        const glyph = `<svg viewBox="0 0 16 16" fill="${cat.color}" class="legend-swatch is-icon wx-tc-legend-glyph" aria-hidden="true">${_TROPICAL_ICON_PATHS[cat.icon]}</svg>`;
        return `<div class="legend-item">${glyph}<span class="legend-text">${escapeHtml(cat.label)}</span></div>`;
    }).join('');
    _setTropicalLegend('Tropical Cyclone Intensity', '<div class="legend-flow">' + items + '</div>', 'System');
}

// Hatched oval swatch matching the GTWO formation-area fill (diagonal lines in `color`).
function _tropicalOutlookHatchSwatch(color, key) {
    const w = 30;
    const h = 16;
    const patternId = `legend-hatch-outlook-${key}`;
    return `<svg width="${w}" height="${h}" class="legend-swatch is-outlook" style="filter:drop-shadow(0 0 1.2px rgba(0,0,0,0.7));" aria-hidden="true">`
        + `<defs><pattern id="${patternId}" patternUnits="userSpaceOnUse" width="6" height="6" patternTransform="rotate(45)">`
        + `<line x1="0" y1="0" x2="0" y2="6" stroke="${color}" stroke-width="3"/></pattern></defs>`
        + `<ellipse cx="${w / 2}" cy="${h / 2}" rx="${w / 2 - 1}" ry="${h / 2 - 1}" `
        + `fill="url(#${patternId})" stroke="${color}" stroke-width="1.2"/></svg>`;
}

function _renderTropicalOutlookLegend() {
    const chance = [
        ['#ffd400', 'low', '&lt; 40%'],
        ['#ff8c00', 'medium', '40-60%'],
        ['#e60000', 'high', '&gt; 60%'],
    ].map(([color, key, label]) => (
        `<div class="legend-item">${_tropicalOutlookHatchSwatch(color, key)}<span class="legend-text">${label}</span></div>`
    )).join('');
    const xGlyph = `<svg viewBox="0 0 16 16" fill="#9ca3af" class="legend-swatch is-icon wx-tc-legend-glyph" aria-hidden="true">${_TROPICAL_ICON_PATHS['x-circle']}</svg>`;
    const notExpected = `<div class="legend-item">${xGlyph}<span class="legend-text">Development not expected</span></div>`;
    const activeKeys = [...new Set(_tropicalStorms.map((storm) => _tropicalCategoryKeyFromWind(storm?.intensity)))];
    const active = activeKeys.map((key) => {
        const cat = TROPICAL_CATEGORIES[key] || TROPICAL_CATEGORIES.OTHER;
        const glyph = `<svg viewBox="0 0 16 16" fill="${cat.color}" class="legend-swatch is-icon wx-tc-legend-glyph" aria-hidden="true">${_TROPICAL_ICON_PATHS[cat.icon]}</svg>`;
        return `<div class="legend-item">${glyph}<span class="legend-text">${escapeHtml(cat.label)}</span></div>`;
    }).join('');
    _setTropicalLegend('Tropical Overview',
        '<div class="tropical-legend-section-label">7-Day Cyclone Formation Chance</div>'
        + '<div class="legend-flow">' + chance + notExpected + '</div>'
        + (active ? '<div class="tropical-legend-section-label">Active Systems</div><div class="legend-flow">' + active + '</div>' : ''),
        'Live');
}

function _renderPeakSurgeLegend() {
    const ranges = [
        ['blue', '1-3 ft'],
        ['yellow', '3-5 ft'],
        ['orange', '4-7 ft'],
        ['orange', '5-8 ft'],
        ['red', '6-10 ft'],
        ['red', '8-12 ft'],
        ['purple', '10-15 ft'],
        ['purple', '15-20 ft'],
    ];
    const rows = ranges.map(([color, label]) => swatch(color, escapeHtml(label), 'is-wide')).join('');
    _setTropicalLegend('Peak Storm Surge Forecast', '<div class="legend-flow">' + rows + '</div>', 'System');
}

function _renderWatchesWarningsLegend() {
    const events = [
        ['#DC143C', 'Hurricane Warning'],
        ['#FF00FF', 'Hurricane Watch'],
        ['#B22222', 'Tropical Storm Warning'],
        ['#F08080', 'Tropical Storm Watch'],
    ];
    const rows = events.map(([color, label]) => swatch(color, escapeHtml(label), 'is-wide')).join('');
    _setTropicalLegend('Watches & Warnings', '<div class="legend-flow">' + rows + '</div>', 'System');
}

function _renderWindRadiiLegend() {
    const radii = [
        ['#1c54ff', '34 kt (Tropical Depression)'],
        ['#6cc343', '50 kt (Tropical Storm)'],
        ['#ffc309', '64 kt (Category 1)'],
    ];
    const rows = radii.map(([color, label]) => swatch(color, escapeHtml(label), 'is-wide')).join('');
    _setTropicalLegend('Wind Radii', '<div class="legend-flow">' + rows + '</div>', 'System');
}

function _renderInitialWindExtentLegend() {
    const windFields = [
        ['#facc15', '34 kt wind extent'],
        ['#fb923c', '50 kt wind extent'],
        ['#ef4444', '64 kt wind extent'],
    ];
    const rows = windFields.map(([color, label]) => swatch(color, escapeHtml(label), 'is-wide')).join('');
    _setTropicalLegend('Initial Wind Extent', '<div class="legend-flow">' + rows + '</div>', 'System');
}

function _renderStormSurgeWWLegend() {
    const events = [
        ['#B524F7', 'Storm Surge Warning'],
        ['#DB7FF7', 'Storm Surge Watch'],
    ];
    const rows = events.map(([color, label]) => swatch(color, escapeHtml(label), 'is-wide')).join('');
    _setTropicalLegend('Storm Surge Watches & Warnings', '<div class="legend-flow">' + rows + '</div>', 'System');
}

function _tropicalGisGeoJson(data, layerId) {
    return _tropicalEngine?.getGisGeoJson?.(data, layerId) || null;
}

// NHC coastal watch/warning codes (TCWW field on the _ww_wwlin shapefile) → ALERT_COLORS
// event names, so the lines match the Alerts tab palette.
const _TROPICAL_WW_EVENT = {
    HWR: 'Hurricane Warning',
    HWA: 'Hurricane Watch',
    TWR: 'Tropical Storm Warning',
    TWA: 'Tropical Storm Watch',
    SSW: 'Storm Surge Warning',
    SSA: 'Storm Surge Watch',
};

function _renderTropicalLayer(data, options = {}) {
    _tropicalEngine?.renderLayer?.(data, options);
}

function _tropicalGisInitLatLng(data) {
    const geojson = _tropicalGisGeoJson(data, 'forecast_points');
    const features = geojson?.features;
    if (!Array.isArray(features)) return null;
    let best = null;
    features.forEach((feature) => {
        const coords = feature?.geometry?.coordinates;
        if (!Array.isArray(coords) || coords.length < 2) return;
        const lat = Number(coords[1]);
        const lon = Number(coords[0]);
        if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
        const tauRaw = Number(feature?.properties?.TAU);
        const tau = Number.isFinite(tauRaw) ? tauRaw : Infinity;
        if (best === null || tau < best.tau) best = { tau, lat, lon };
    });
    return best ? [best.lat, best.lon] : null;
}

function _tropicalLatestLatLng(data) {
    // Prefer the archive-stable GIS initial (TAU 0) point: it matches the rendered
    // markers and the authoritative current position. Advisory text is a fallback only.
    const gisInit = _tropicalGisInitLatLng(data);
    if (gisInit) return gisInit;

    const loc = data?.advisory?.location;
    const locLat = Number(loc?.lat);
    const locLon = Number(loc?.lon);
    if (Number.isFinite(locLat) && Number.isFinite(locLon)) {
        return [locLat, locLon];
    }

    const track = Array.isArray(data?.track) ? data.track : [];
    const init = track.find((pt) => String(pt?.hour || '').toUpperCase() === 'INIT') || track[0];
    const trackLat = Number(init?.lat);
    const trackLon = Number(init?.lon);
    if (Number.isFinite(trackLat) && Number.isFinite(trackLon)) {
        return [trackLat, trackLon];
    }

    const listStorm = _tropicalStorms.find((storm) => {
        return String(storm?.id || '').toUpperCase() === String(data?.stormId || '').toUpperCase();
    });
    return _tropicalStormLatLng(listStorm);
}

function _zoomTropicalToLatest(data) {
    const latlng = _tropicalLatestLatLng(data);
    if (!latlng) return;
    map.flyTo(latlng, Math.max(map.getZoom(), 6), { duration: 0.7 });
}

function _formatLatLon(lat, lon) {
    const a = Number(lat);
    const o = Number(lon);
    if (!Number.isFinite(a) || !Number.isFinite(o)) return '--';
    return `${Math.abs(a).toFixed(1)}${a >= 0 ? 'N' : 'S'} ${Math.abs(o).toFixed(1)}${o >= 0 ? 'E' : 'W'}`;
}

function _formatTropicalIssued(iso, advisoryText = '') {
    const s = String(iso || '');
    if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(s)) return '--';
    const utc = new Date(s);
    const utcLabel = Number.isFinite(utc.getTime())
        ? `${String(utc.getUTCHours()).padStart(2, '0')}:${String(utc.getUTCMinutes()).padStart(2, '0')} UTC`
        : `${s.slice(11, 16)} UTC`;
    const localMatch = String(advisoryText || '').match(
        /\b(\d{1,4})\s+(AM|PM)\s+([A-Z]{2,5})\s+\w{3}\s+([A-Z][a-z]{2})\s+(\d{1,2})\s+(\d{4})\b/,
    );
    if (!localMatch) return `${s.slice(5, 7)}-${s.slice(8, 10)}-${s.slice(0, 4)} ${s.slice(11, 16)} UTC`;
    const [, rawTime, meridiem, zone, monthName, day, year] = localMatch;
    const months = { Jan: '01', Feb: '02', Mar: '03', Apr: '04', May: '05', Jun: '06', Jul: '07', Aug: '08', Sep: '09', Oct: '10', Nov: '11', Dec: '12' };
    const padded = rawTime.padStart(4, '0');
    const localTime = `${Number(padded.slice(0, -2))}:${padded.slice(-2)}`;
    return `${months[monthName] || '--'}-${String(day).padStart(2, '0')}-${year} ${localTime} ${meridiem} ${zone} (${utcLabel})`;
}

function _renderTropicalSummary(data) {
    const head = byId('wx-tropical-summary-head');
    const summary = byId('weather-tropical-summary');
    // Floater is live-storm only; hide by default — the live detail loader
    // re-shows it via _renderTropicalFloater() when a floater exists.
    _hideTropicalFloater();
    // No storm selected: blank the System inspector so stale content doesn't linger.
    if (!data) {
        if (head) head.innerHTML = '';
        if (summary) summary.innerHTML = '';
        _tropicalPageController?.clearTropicalDetailLists?.();
        return;
    }
    // Archive best-track fix view: per-fix summary grid + the ◀ Fix N/T ▶ stepper.
    if (data?._fixScrub) {
        _renderTropicalFixSummaryHead(data, head, summary);
    // Archive advisory view: per-advisory summary grid + the ◀/▶ stepper.
    } else if (data?.advisoryStep) {
        _renderTropicalAdvisorySummaryHead(data, head, summary);
    // Archive (HURDAT2) storms aren't in the live overview list and have no
    // advisory snapshot, so summarize the whole best-track history instead.
    } else if (data?.source === 'HURDAT2') {
        _renderTropicalArchiveSummaryHead(data, head, summary);
    } else {
        // Source everything from the archive-stable overview storm object (advisory .shtml URLs
        // are bin-latest, so they can describe a different storm when replaying past seasons).
        const storm = _tropicalStorms.find((s) => (
            String(s?.id || '').toUpperCase() === String(data?.stormId || '').toUpperCase()
        )) || {};
        const cat = TROPICAL_CATEGORIES[_tropicalCategoryKeyFromWind(storm.intensity)] || TROPICAL_CATEGORIES.OTHER;

        if (head) {
            const name = storm.name || data?.stormId || 'System';
            head.innerHTML = `<span class="wx-tropical-sum-name">${escapeHtml(name)}</span>`
                + `<span class="wx-tropical-cat-badge" style="--tc-cat:${cat.color}">`
                + `<span class="wx-tropical-cat-dot" aria-hidden="true"></span>${escapeHtml(cat.label)}</span>`;
        }

        if (summary) {
            const windMph = _ktToMph(storm.intensity);
            const pressure = Number(storm.pressure);
            const motion = _tropicalMotionText(storm);
            const advNum = storm.publicAdvisory?.advNum || storm.forecastAdvisory?.advNum;
            const advNumText = advNum ? String(parseInt(advNum, 10) || advNum) : '--';
            const issued = _formatTropicalIssued(
                storm.publicAdvisory?.issuance || storm.lastUpdate,
                data?.products?.TCP?.text,
            );
            const locationText = data?.advisory?.location?.text || '';
            summary.innerHTML = [
                ['Issued', issued, ' is-wide'],
                ['Wind', windMph != null ? `${windMph} mph` : '--', ''],
                ['Pressure', Number.isFinite(pressure) ? `${pressure} mb` : '--', ''],
                ['Motion', motion || '--', ''],
                ['Advisory #', advNumText, ''],
                ...(locationText ? [['Location', locationText, ' is-wide']] : []),
            ].map(([label, value, mod]) => (
                `<div class="wx-tropical-metric${mod}"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`
            )).join('');
        }
    }

    _tropicalPageController?.renderTropicalProducts?.(data);
    _tropicalPageController?.renderTropicalTrack?.(data);
    _tropicalPageController?.renderTropicalGraphics?.(data);
}

function _closeTropicalDetail() {
    _tropicalPageController?.closeTropicalDetail?.();
}

function _openTropicalProductDetail(productCode = 'TCP') {
    _tropicalPageController?.openTropicalProductDetail?.(productCode);
}

function _openTropicalGraphicDetail(url, label) {
    _tropicalPageController?.openTropicalGraphicDetail?.(url, label);
}

function _hideTropicalFloater() {
    _tropicalPageController?.hideTropicalFloater?.();
}

// Reveal the floater product pills if the active storm has a NESDIS floater
// (probe GeoColor — all products exist whenever the floater does). On error
// (no active floater, e.g. archived storms) the whole section stays hidden.
function _renderTropicalFloater(stormId) {
    _tropicalPageController?.renderTropicalFloater?.(stormId);
}

// ── Tropical Archive (HURDAT2 browser) ───────────────────────────────────
function _setTropicalArchiveStatus(message) {
    const el = byId('wx-archive-status');
    if (el) el.textContent = message || '';
}

// Summarize a whole best-track history (no advisory snapshot exists) into the
// System inspector header + metric grid. Track table is rendered by the caller.
function _renderTropicalArchiveSummaryHead(data, head, summary) {
    _tropicalPageController?.renderArchiveSummaryHead?.(data, head, summary);
}

// Per-advisory summary (live System layout) + the in-cell ◀ Adv NNN ▶ stepper.
function _renderTropicalAdvisorySummaryHead(data, head, summary) {
    _tropicalPageController?.renderArchiveAdvisorySummaryHead?.(data, head, summary);
}

function _renderArchiveScrubberBar() {
    _tropicalPageController?.renderArchiveScrubberBar?.();
}

function _hideArchiveScrubberBar() {
    _tropicalPageController?.hideArchiveScrubberBar?.();
}

function _stopArchiveScrubPlay() {
    _tropicalPageController?.stopArchiveScrubPlay?.();
}

function _highlightTropicalArchiveCard() {
    _tropicalPageController?.highlightSelectedArchiveCard?.();
}

function _zoomTropicalArchiveToTrack(data) {
    const fixes = (Array.isArray(data?.track) ? data.track : [])
        .filter((p) => p.lat != null && p.lon != null);
    if (!fixes.length) return;
    const lons = fixes.map((p) => p.lon);
    // Dateline-crossing (EP/CP) tracks: shift western lons into a continuous
    // 0–360° frame so the bounds hug the storm instead of spanning the globe.
    // Leaflet accepts out-of-range longitudes and wraps them on display.
    const crossesDateline = Math.max(...lons) - Math.min(...lons) > 180;
    const pts = fixes.map((p) => [p.lat, crossesDateline && p.lon < 0 ? p.lon + 360 : p.lon]);
    const bounds = L.latLngBounds(pts);
    if (bounds.isValid()) {
        map.fitBounds(bounds.pad(0.4), { paddingBottomRight: [0, REGION_FIT_BOTTOM_PADDING_PX] });
    }
}

function _selectTropicalArchiveStorm(atcfId) {
    if (!atcfId) return;
    _tropicalArchiveSelectedId = atcfId;
    _highlightTropicalArchiveCard();
    _closeTropicalDetail();
    _closeOutlookDetail();
    _setTropicalMapViewMode('system');
    _tropicalEngine?.loadArchiveStormDetail(atcfId);
}

function _renderArchiveAdvisory(merged, adv, options = {}) {
    _activeTropicalStorm = merged;
    _clearArchiveFixHighlight();  // advisory mode has no fix glyph
    _setTropicalDetailSectionsVisible(true);

    // Only seed the default layer toggles on the FIRST advisory (storm open).
    // On subsequent steps we respect the user's current toggle choices so
    // turning a layer (e.g. best track) off persists as the scrubber advances.
    if (options.initial) {
        _tropicalEngine?.setLayerToggles?.({
            best_track: true,
            cone: !!adv.gis_layers?.cone,
            forecast_track: !!adv.gis_layers?.forecast_track,
            forecast_points: !!adv.gis_layers?.forecast_points,
        });
    }

    _renderTropicalSummary(merged);
    _renderTropicalLayer(merged, { fitBounds: false });
    if (options.fit) _zoomTropicalArchiveToTrack(_tropicalArchiveStormBase || {});
    _renderTropicalLegend();
    _renderArchiveScrubberBar();
}

// Forecast / Storm Layers / Products / Graphics are advisory-specific; hide them
// in best-track fix mode (pre-2008 storms or modern "Track Only") so there are no
// empty/irrelevant sections, and restore them for advisory and live storms.
const _TROPICAL_ADVISORY_SECTIONS = [
    'wx-tropical-inspector-forecast',
    'wx-tropical-inspector-layers',
    'wx-tropical-inspector-products',
    'wx-tropical-inspector-graphics',
];

function _setTropicalDetailSectionsVisible(visible) {
    _TROPICAL_ADVISORY_SECTIONS.forEach((id) => {
        const el = byId(id);
        if (el) el.style.display = visible ? '' : 'none';
    });
}

// ── Best-track fix scrubber (pre-2008 storms + modern alt mode) ──────────
const _FIX_MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

function _formatFixDTG(dtg) {
    const s = String(dtg || '');
    if (s.length < 10) return s || '--';
    const mon = _FIX_MONTHS[Number(s.slice(4, 6)) - 1] || s.slice(4, 6);
    return `${mon} ${Number(s.slice(6, 8))}, ${s.slice(0, 4)} · ${s.slice(8, 10)}Z`;
}

function _clearArchiveFixHighlight() {
    if (_tropicalFixMarker && map.hasLayer(_tropicalFixMarker)) map.removeLayer(_tropicalFixMarker);
    _tropicalFixMarker = null;
}

function _setArchiveFixHighlight(feature) {
    _clearArchiveFixHighlight();
    const coords = feature?.geometry?.coordinates;
    if (!Array.isArray(coords)) return;
    // TAU:0 makes _tropicalCategoryIcon render the larger (33px) glyph variant.
    const icon = _tropicalCategoryIcon({ ...(feature.properties || {}), TAU: 0 });
    _tropicalFixMarker = L.marker([coords[1], coords[0]], {
        icon, zIndexOffset: 1000, interactive: false,
    }).addTo(map);
}

function _loadArchiveFix(index, options = {}) {
    const base = _tropicalArchiveStormBase || {};
    const fixes = _tropicalPageController?.archiveFixes?.() || [];
    const feature = fixes[index];
    if (!feature) return;
    const fixData = { ...base, _fixScrub: true, _fixFeature: feature };
    _activeTropicalStorm = fixData;

    if (options.initial) {
        _tropicalEngine?.setLayerToggles?.({
            best_track: true,
            cone: false,
            forecast_track: false,
            forecast_points: false,
        });
    }

    _setTropicalDetailSectionsVisible(false);  // fix mode → hide advisory sections
    _renderTropicalSummary(fixData);
    _renderTropicalLayer(fixData, { fitBounds: false });
    if (options.fit) _zoomTropicalArchiveToTrack(base);
    _setArchiveFixHighlight(feature);
    _renderTropicalLegend();
    _renderArchiveScrubberBar();

    const issued = _formatFixDTG(feature.properties?.DTG);
    _tropicalArchiveReliabilityLabel = issued;
    _setReliability('tropical', 'Best Track — HURDAT2', 'NOAA NHC', base.updated || Date.now());
    _setTimestampSource('tropical', 'Best Track — HURDAT2', base.updated || Date.now());
    _setTropicalArchiveStatus(`${_tropicalArchiveStormName || ''} — Fix ${index + 1}/${fixes.length}`);
}

// Per-fix summary (live System layout) + the in-cell ◀ Fix N/T ▶ stepper.
function _renderTropicalFixSummaryHead(data, head, summary) {
    _tropicalPageController?.renderArchiveFixSummaryHead?.(data, head, summary);
}

function configureProductModules() {
    _tropicalPageController.configureTropicalPage({
        categoryColor: _tropicalCategoryColor,
        categoryFromProperties: (properties) => TROPICAL_CATEGORIES[_tropicalCategoryKey(properties)] || TROPICAL_CATEGORIES.OTHER,
        categoryFromWind: (windKt) => TROPICAL_CATEGORIES[_tropicalCategoryKeyFromWind(windKt)] || TROPICAL_CATEGORIES.OTHER,
        categoryKeyFromProperties: _tropicalCategoryKey, categoryKeyFromWind: _tropicalCategoryKeyFromWind,
        closeAlertDetail: () => {}, createImage: () => new Image(), escapeHtml,
        clearArchiveFixHighlight: _clearArchiveFixHighlight, formatFixDate: _formatFixDTG,
        formatLatLon: _formatLatLon, formatPlaybackSpeed: _formatScrubberPlaybackSpeed,
        floaterCacheBust: () => Math.floor(Date.now() / 300000), getArchiveCatalog: () => _tropicalArchiveCatalog,
        getArchiveStormName: () => _tropicalArchiveStormName, getActiveStorm: () => _activeTropicalStorm,
        getTropicalGisGeoJson: _tropicalGisGeoJson, getPlaybackSpeeds: () => SCRUBBER_PLAYBACK_SPEEDS,
        getSelectedArchiveId: () => _tropicalArchiveSelectedId, ktToMph: _ktToMph,
        motionText: _tropicalMotionText, pointColor: _tropicalPointColor,
        loadArchiveAdvisory: (step, options) => _tropicalEngine?.loadArchiveAdvisory(_tropicalArchiveStormId, step, options),
        loadArchiveFix: _loadArchiveFix, openGraphicDetail: _openTropicalGraphicDetail,
        openProductDetail: _openTropicalProductDetail, selectArchiveStorm: _selectTropicalArchiveStorm,
        selectStorm: _selectTropicalStormCard, setArchiveStatus: _setTropicalArchiveStatus,
        setStatus: _setTropicalStatus, setTimeoutFn: (callback, delay) => setTimeout(callback, delay), windClass: _tropicalWindClass,
    });
    _tropicalPageController.wireArchiveControls();
    _tropicalPageController.wireArchiveScrubberControls();
    _tropicalPageController.wireFloaterControls();

    _tropicalEngine = _tropicalEngineFactory.createTropicalEngine({
        alertColors: ALERT_COLORS, alertDefault: ALERT_DEFAULT, apiUrl,
        canApplyResponse: (seq) => seq === _tropicalRequestSeq, clearActiveStorm: () => { _activeTropicalStorm = null; },
        clearLiveStormDetail: () => { _activeTropicalStorm = null; _clearTropicalLayer(); _renderTropicalSummary(null); _renderTropicalOutlookLegend(); },
        clearTropicalLayer: _clearTropicalLayer, categoryColor: _tropicalCategoryColor,
        categoryIcon: _tropicalCategoryIcon, categoryKey: _tropicalCategoryKey,
        fetchFn: (url, options) => fetch(url, options), getActiveBasin: () => 'WORLD',
        getActiveStorm: () => _activeTropicalStorm, getArchiveCatalog: () => _tropicalArchiveCatalog,
        getArchiveStormBase: () => _tropicalArchiveStormBase, getSelectedStormId: _activeTropicalSystemId,
        isCurrentRequest: (seq) => seq === _tropicalRequestSeq, isTypeEnabled: _isTypeEnabled,
        leaflet: L, loadBasinFeeds: loadTropicalBasinFeeds,
        liveStormLabel: (data) => _tropicalStorms.find((storm) => String(storm?.id).toUpperCase() === String(data?.stormId).toUpperCase())?.name || data.advisory?.headline || `${data.stormId} advisory loaded`,
        nextRequestSeq: () => ++_tropicalRequestSeq, map, openProductDetail: _openTropicalProductDetail,
        pointCategory: _tropicalPointCategory, pointColor: _tropicalPointColor,
        prepareArchiveAdvisoryMode: (items) => _tropicalPageController.setArchiveAdvisoryMode(items),
        prepareArchiveBestTrackMode: () => _tropicalPageController.setArchiveBestTrackMode(),
        prepareArchiveStorm: (data, atcfId) => { _stopArchiveScrubPlay(); _clearArchiveFixHighlight(); _tropicalArchiveStormBase = data; _tropicalArchiveStormId = atcfId; _tropicalArchiveStormName = data.storm?.name || atcfId; _tropicalPageController.setArchiveFixes(data.gis_layers?.best_track_points?.geojson?.features || []); },
        renderOutlookLegend: _renderTropicalOutlookLegend,
        renderLayerLegend: (layerId, checked) => { const renderers = { peak_surge: _renderPeakSurgeLegend, watches_warnings: _renderWatchesWarningsLegend, wind_radii: _renderWindRadiiLegend, initial_wind_extent: _renderInitialWindExtentLegend, storm_surge: _renderStormSurgeWWLegend }; if (checked && renderers[layerId]) renderers[layerId](); else if (!checked && _activeTropicalStorm) _renderTropicalLegend(); },
        renderLiveStormDetail: (data, options) => { _renderTropicalSummary(data); _renderTropicalFloater(data.stormId); _highlightSelectedTropicalCard(); _tropicalEngine.setLayerToggles({ cone: true, forecast_points: true, forecast_track: false }); _renderTropicalLayer(data, options); _renderTropicalLegend(); if (options.zoomToLatest) _zoomTropicalToLatest(data); },
        renderArchiveCatalog: (catalog) => _tropicalPageController.renderArchiveCatalog(catalog),
        renderArchiveAdvisory: _renderArchiveAdvisory, renderInitialArchiveFix: () => _loadArchiveFix(0, { fit: true, initial: true }),
        filterStorms: _filterLiveStorms, clearFilteredStorm: _clearFilteredLiveStorm,
        renderStormList: (storms) => _tropicalPageController.renderStormList(storms),
        renderActiveStorms: _renderActiveSystemsOverview, renderSummary: _renderTropicalSummary,
        resetLiveArchiveState: () => { _tropicalArchiveReliabilityLabel = null; _tropicalArchiveSelectedId = null; _tropicalPageController.resetArchiveScrubber(); _setTropicalDetailSectionsVisible(true); _highlightTropicalArchiveCard(); },
        setActiveStorm: (data) => { _activeTropicalStorm = data; }, setArchiveCatalog: (catalog) => { _tropicalArchiveCatalog = catalog; },
        setArchiveStatus: _setTropicalArchiveStatus, setHubMode: _setTropicalHubMode, setStatus: _setTropicalStatus,
        setStorms: (storms) => { _tropicalStorms = storms; }, selectStorm: _selectTropicalStormCard,
        syncLayerPills: (keys, toggles) => keys.forEach((key) => { const input = byId('wx-tropical-inspector-layers')?.querySelector(`[data-tc-layer="${key}"]`); if (input) input.checked = !!toggles[key]; }),
        updateLiveStormMetadata: (data) => { const updated = data.updated || Date.now(); _setReliability('tropical', 'Tropical Cyclones', 'NOAA NHC', updated); _setTimestampSource('tropical', 'NHC Public Advisory', updated); },
        updateArchiveAdvisoryMetadata: (advisory, step, atcfId) => { _tropicalArchiveReliabilityLabel = advisory.issued || null; const label = `Advisory ${advisory.advisoryStep || step}`; const updated = advisory.updated || Date.now(); _setReliability('tropical', `${label} — NHC Archive`, 'NOAA NHC', updated); _setTimestampSource('tropical', `${label} — NHC Archive`, updated); _setTropicalArchiveStatus(`${_tropicalArchiveStormName || atcfId} — ${label}`); },
        updateArchiveStormMetadata: (data) => _setViewerTimestamp(data.updated || Date.now()),
        regionFitBottomPaddingPx: REGION_FIT_BOTTOM_PADDING_PX, watchWarningEvent: (code) => _TROPICAL_WW_EVENT[code], windClass: _tropicalWindClass, escapeHtml,
    });
}

async function initialize() {
    renderProductNav(byId('product-nav'), 'Tropical');
    configureProductModules();
    _wireLiveAccordions();
    _wireLiveBasinPills();
    const defaults = await loadDefaultSettings().catch(() => ({}));
    const cityDefaults = defaults?.global?.cityLabels || {};
    byId('weather-tropical-system').addEventListener('change', () => { _closeTropicalDetail(); void _tropicalEngine.loadStormDetail(_activeTropicalSystemId(), { fitBounds: false, zoomToLatest: true }); });
    byId('weather-refresh-tropical').addEventListener('click', () => {
        if (sidebarTabs.activeTab === 'archive') void _tropicalEngine.loadArchiveCatalog();
        else void _tropicalEngine.loadStorms();
    });
    byId('weather-tropical-graticule').addEventListener('change', (event) => event.target.checked ? _addGraticule() : _removeGraticule());
    byId('wx-tropical-inspector-layers').addEventListener('change', (event) => { const layerId = event.target?.dataset?.tcLayer; if (layerId) _tropicalEngine.handleLayerToggle(layerId, event.target.checked); });
    byId('weather-tropical-inspector').addEventListener('click', (event) => { const section = event.target.closest('.wx-accordion-header')?.closest('.wx-accordion'); if (section) section.dataset.open = section.dataset.open === 'true' ? 'false' : 'true'; });
    byId('tropical-system-close').addEventListener('click', () => _setSystemInspectorVisible(false));
    byId('tropical-system-open').addEventListener('click', () => _setSystemInspectorVisible(true));
    byId('tropical-basemap').addEventListener('change', (event) => mapCore.setBasemap(event.target.value));

    const citySource = ['us', 'world'].includes(cityDefaults.source) ? cityDefaults.source : 'off';
    const cityDensity = Number(cityDefaults.density);
    const cityFontSize = Number(cityDefaults.fontSize);
    const cityDensityInput = byId('tropical-city-density');
    const cityFontSizeInput = byId('tropical-city-font-size');
    cityDensityInput.value = String(cityDensity >= 0.01 && cityDensity <= 1 ? cityDensity : 0.25);
    cityFontSizeInput.value = String(cityFontSize >= 0.4 && cityFontSize <= 1.2 ? cityFontSize : 0.6);
    const initialCitySourceInput = document.querySelector(`input[name="tropical-cities-source"][value="${citySource}"]`);
    if (initialCitySourceInput) initialCitySourceInput.checked = true;

    const selectedCitySource = () => document.querySelector('input[name="tropical-cities-source"]:checked')?.value || 'off';
    function updateCityControlLabels() {
        const source = selectedCitySource();
        const disabled = source === 'off';
        document.querySelectorAll('[data-city-adjustment]').forEach((row) => {
            row.classList.toggle('is-disabled', disabled);
            row.querySelector('input').disabled = disabled;
        });
        const distanceKm = Math.round(mapCore.getCityMinDistanceKm(source, cityDensityInput.value));
        byId('tropical-city-density-label').textContent = `City Density (${distanceKm} km)`;
        const fontSizeLabel = Number(cityFontSizeInput.value).toFixed(2).replace(/\.?0+$/, '');
        byId('tropical-city-font-size-label').textContent = `City Font Size (${fontSizeLabel})`;
    }
    document.querySelectorAll('input[name="tropical-cities-source"]').forEach((input) => {
        input.addEventListener('change', () => {
            updateCityControlLabels();
            void mapCore.setCitySource(selectedCitySource()).catch((error) => {
                status.setMessage(`City overlay unavailable: ${error.message}`, 'error');
            });
        });
    });
    cityDensityInput.addEventListener('input', () => {
        mapCore.setCityDensity(cityDensityInput.value);
        updateCityControlLabels();
    });
    cityFontSizeInput.addEventListener('input', () => {
        mapCore.setCityFontSize(cityFontSizeInput.value);
        updateCityControlLabels();
    });
    map.on('zoomend', updateCityControlLabels);
    mapCore.setCityDensity(cityDensityInput.value);
    mapCore.setCityFontSize(cityFontSizeInput.value);
    updateCityControlLabels();
    void mapCore.setCitySource(citySource).catch((error) => {
        status.setMessage(`City overlay unavailable: ${error.message}`, 'error');
    });

    document.querySelectorAll('[data-map-overlay]').forEach((input) => { input.addEventListener('change', () => void mapCore.setOverlayVisible(input.dataset.mapOverlay, input.checked)); if (input.checked) void mapCore.setOverlayVisible(input.dataset.mapOverlay, true); });
    fitTropicalDefaultExtent();
    _renderTropicalOutlookLegend();
    await Promise.all([_tropicalEngine.loadStorms(), _tropicalEngine.loadArchiveCatalog()]);
}

initialize().catch((error) => { console.error('[tropical] startup failed', error); status.setMessage(`Startup failed: ${error.message}`, 'error'); });
