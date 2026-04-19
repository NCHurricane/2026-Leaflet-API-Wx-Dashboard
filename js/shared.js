(function () {
    'use strict';

    const API_ORIGIN = window.location.protocol === 'file:'
        ? 'http://127.0.0.1:8000'
        : '';

    const NAV_ITEMS = [
        { id: 'weather', label: 'Weather', href: 'weather.html' },
        { id: 'radar', label: 'Radar', href: 'radar.html' },
        { id: 'satellite', label: 'Satellite', href: 'satellite.html' }
    ];

    function byId(id) {
        return document.getElementById(id);
    }

    function initNav(activeTabId) {
        const nav = byId('main-nav');
        if (!nav) {
            return;
        }

        nav.className = 'nav-bar';
        nav.innerHTML = NAV_ITEMS.map((item) => {
            const activeClass = item.id === activeTabId ? 'active' : '';
            return `<a class="nav-link ${activeClass}" href="${item.href}">${item.label}</a>`;
        }).join('');
    }

    function showProgress(percent, message) {
        const container = byId('progress-container');
        const bar = byId('progress-bar');
        const msg = byId('progress-message');
        if (!container || !bar || !msg) {
            return;
        }

        container.style.display = 'block';
        const safePercent = Math.max(0, Math.min(100, Number(percent) || 0));
        bar.style.width = `${safePercent}%`;
        msg.textContent = message || '';
    }

    function hideProgress() {
        const container = byId('progress-container');
        if (container) {
            container.style.display = 'none';
        }
    }

    function cacheBust(url) {
        const separator = url.includes('?') ? '&' : '?';
        return `${url}${separator}_ts=${Date.now()}`;
    }

    function apiUrl(path) {
        if (!path) {
            return API_ORIGIN || '';
        }

        if (/^https?:\/\//i.test(path)) {
            return path;
        }

        if (path.startsWith('/')) {
            return `${API_ORIGIN}${path}`;
        }

        return API_ORIGIN ? `${API_ORIGIN}/${path}` : `/${path}`;
    }

    function setStatus(message) {
        const status = byId('status-message');
        if (status) {
            status.textContent = message || '';
        }
    }

    function normalizeSourceLabel(rawSource) {
        const source = String(rawSource || '').trim();
        if (!source) {
            return '--';
        }

        const key = source.toLowerCase();
        if (key === 'nws') return 'NWS API';
        if (key === 'iem') return 'IEM';
        if (key === 'aws') return 'AWS NODD';
        if (key === 'gcp') return 'GCP Public Data';
        if (key === 'thredds') return 'THREDDS';
        if (key === 'auto') return 'Auto';
        if (key.includes('aws')) return 'AWS NODD';
        if (key.includes('gcp')) return 'GCP Public Data';
        if (key.includes('thredds')) return 'THREDDS';
        return source;
    }

    function normalizeDataModeLabel(rawMode) {
        const mode = String(rawMode || '').trim();
        if (!mode) {
            return '--';
        }

        const key = mode.toLowerCase();
        if (key === 'archive') return 'Archive';
        if (key === 'recent' || key === 'current') return 'Recent';
        return mode;
    }

    function setOutputMeta(options = {}) {
        const sourceBadge = byId('source-badge');
        const dataModeBadge = byId('data-mode-badge');
        if (!sourceBadge || !dataModeBadge) {
            return;
        }

        const state = String(options.state || '').toLowerCase();
        if (state === 'running') {
            sourceBadge.textContent = 'Source: running...';
            dataModeBadge.textContent = 'Data Mode: running...';
            return;
        }

        if (state === 'unavailable') {
            sourceBadge.textContent = 'Source: unavailable';
            dataModeBadge.textContent = 'Data Mode: unavailable';
            return;
        }

        const sourceText = normalizeSourceLabel(options.source);
        const requestedText = normalizeSourceLabel(options.requestedSource);
        if (requestedText !== '--' && requestedText !== sourceText) {
            sourceBadge.textContent = `Source: ${sourceText} (requested ${requestedText})`;
        } else {
            sourceBadge.textContent = `Source: ${sourceText}`;
        }
        dataModeBadge.textContent = `Data Mode: ${normalizeDataModeLabel(options.dataMode)}`;
    }

    function setOutputMetaFromResponse(data, fallback = {}) {
        const payload = data || {};
        const source = payload.source_used || payload.source || payload.data_source || fallback.source || '--';
        const requestedSource = payload.requested_source || fallback.requestedSource || '';
        const dataMode = payload.data_mode || fallback.dataMode || '--';
        setOutputMeta({ source, requestedSource, dataMode });
    }

    function displayImage(url) {
        const image = byId('result-image');
        const video = byId('result-video');
        if (!image || !video) {
            return;
        }

        video.style.display = 'none';
        image.style.display = 'block';
        image.src = cacheBust(apiUrl(url));
    }

    function displayVideo(url) {
        const image = byId('result-image');
        const video = byId('result-video');
        if (!image || !video) {
            return;
        }

        image.style.display = 'none';
        video.style.display = 'block';
        video.src = cacheBust(apiUrl(url));
        video.load();
    }

    async function pollProgress(requestId, callback) {
        const pollDelayMs = 1200;
        const maxIdleBeforeStart = 5;
        const maxPollMs = 30 * 60 * 1000;
        const startedAtMs = Date.now();
        let seenActiveStage = false;
        let idleCount = 0;

        while (true) {
            let progress = null;
            try {
                const response = await fetch(apiUrl(`/api/progress/${encodeURIComponent(requestId)}`));
                progress = await response.json();
            } catch (error) {
                callback({ percent: 0, message: `Progress polling failed: ${error.message}`, stage: 'error' });
                return;
            }

            callback(progress);
            if (progress && progress.source) {
                setOutputMeta({ source: progress.source, dataMode: 'running...' });
            }

            const stage = String(progress?.stage || 'idle').toLowerCase();
            const percent = Number(progress?.percent || 0);
            const isTerminal = percent >= 100 || stage === 'error' || stage === 'done' || stage === 'complete';
            const isIdle = stage === 'idle';

            if (!isIdle) {
                seenActiveStage = true;
                idleCount = 0;
            } else {
                idleCount += 1;
            }

            // If a task goes idle after becoming active, assume it completed and was purged.
            if (isTerminal || (isIdle && seenActiveStage)) {
                return;
            }

            // Bound startup races/invalid IDs to prevent infinite polling loops.
            if (!seenActiveStage && idleCount >= maxIdleBeforeStart) {
                return;
            }

            if ((Date.now() - startedAtMs) >= maxPollMs) {
                return;
            }

            await new Promise((resolve) => setTimeout(resolve, pollDelayMs));
        }
    }

    async function purgeOldFiles(endpoint) {
        const response = await fetch(apiUrl(endpoint || '/api/purge'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        return response.json();
    }

    function getLabelForInput(inputId) {
        if (!inputId) {
            return null;
        }
        const labels = document.querySelectorAll('label[for]');
        for (const label of labels) {
            if (label.getAttribute('for') === inputId) {
                return label;
            }
        }
        return null;
    }

    function toCardinalDirection(degrees) {
        const labels = ['North', 'Northeast', 'East', 'Southeast', 'South', 'Southwest', 'West', 'Northwest'];
        const normalized = ((Number(degrees) % 360) + 360) % 360;
        const index = Math.round(normalized / 45) % labels.length;
        return labels[index];
    }

    function formatRangeValue(input) {
        if (!input || !input.id) {
            return input?.value;
        }

        const id = input.id;
        const rawValue = String(input.value ?? '');

        if (id === 'radar-sm-dir') {
            return `${rawValue} - ${toCardinalDirection(rawValue)}`;
        }

        if (id === 'radar-sm-speed') {
            return `${rawValue} MPH`;
        }

        return rawValue;
    }

    function updateRangeLabel(input) {
        if (!input || !input.id) {
            return;
        }
        // Weather density sliders are formatted by weather.js in km based on zoom.
        if (input.id === 'weather-obs-density' || input.id === 'weather-cities-density') {
            return;
        }
        const label = getLabelForInput(input.id);
        if (!label) {
            return;
        }

        const baseLabel = label.dataset.baseLabel
            || label.textContent.replace(/\s*\([^)]*\)\s*$/, '').trim();

        label.dataset.baseLabel = baseLabel;
        label.textContent = `${baseLabel} (${formatRangeValue(input)})`;
    }

    function bindRangeValueLabels() {
        const rangeInputs = document.querySelectorAll('input[type="range"]');
        rangeInputs.forEach((input) => {
            if (input.dataset.rangeValueBound === 'true') {
                updateRangeLabel(input);
                return;
            }

            const syncLabel = () => updateRangeLabel(input);
            input.addEventListener('input', syncLabel);
            input.addEventListener('change', syncLabel);
            input.dataset.rangeValueBound = 'true';
            updateRangeLabel(input);
        });
    }

    function initRangeValueLabels() {
        bindRangeValueLabels();

        document.addEventListener('click', (event) => {
            const target = event.target;
            if (!target || !target.id) {
                return;
            }
            if (target.id.endsWith('reset-styles') || target.id.endsWith('reset-controls')) {
                setTimeout(bindRangeValueLabels, 0);
            }
        });
    }

    function setStyleGroupCollapsed(group, collapsed) {
        if (!group) {
            return;
        }

        group.classList.toggle('is-collapsed', collapsed);

        const title = group.querySelector('.group-title');
        if (title) {
            title.setAttribute('aria-expanded', String(!collapsed));
            title.title = collapsed ? 'Expand section' : 'Collapse section';
        }
    }

    function initCollapsibleStyleGroups() {
        const groups = document.querySelectorAll('.style-group');

        groups.forEach((group, index) => {
            if (group.dataset.collapsibleBound === 'true') {
                return;
            }

            const title = Array.from(group.children).find((child) => child.classList?.contains('group-title'));
            if (!title) {
                return;
            }

            const titleText = title.textContent ? title.textContent.trim() : `Group ${index + 1}`;
            const toggleCollapsed = () => {
                const currentlyCollapsed = group.classList.contains('is-collapsed');
                setStyleGroupCollapsed(group, !currentlyCollapsed);
            };

            group.classList.add('is-collapsible');
            title.setAttribute('role', 'button');
            title.setAttribute('tabindex', '0');
            title.setAttribute('aria-label', `${titleText} section`);
            const defaultCollapsed = group.dataset.collapsedDefault === 'true'
                || group.classList.contains('is-collapsed');
            setStyleGroupCollapsed(group, defaultCollapsed);

            title.addEventListener('click', toggleCollapsed);
            title.addEventListener('keydown', (event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    toggleCollapsed();
                }
            });

            group.dataset.collapsibleBound = 'true';
        });
    }

    const ALERT_WFO_CODES = [
        'ABQ', 'AKQ', 'ALY', 'AMA', 'APX', 'ARX', 'BGM', 'BIS', 'BMX', 'BOI',
        'BOU', 'BOX', 'BRO', 'BTV', 'BUF', 'BYZ', 'CAE', 'CAR', 'CHS', 'CLE',
        'CRP', 'CTP', 'CYS', 'DDC', 'DLH', 'DMX', 'DTX', 'DVN', 'EAX', 'EKA',
        'EPZ', 'EWX', 'FFC', 'FGF', 'FGZ', 'FSD', 'FWD', 'GGW', 'GID', 'GJT',
        'GLD', 'GRB', 'GRR', 'GSP', 'GYX', 'HGX', 'HNX', 'HUN', 'ICT', 'ILM',
        'ILN', 'ILX', 'IND', 'IWX', 'JAN', 'JAX', 'JKL', 'KEY', 'LBF', 'LCH',
        'LIX', 'LKN', 'LMK', 'LOT', 'LOX', 'LSX', 'LUB', 'LWX', 'LZK', 'MAF',
        'MEG', 'MFL', 'MFR', 'MHX', 'MKX', 'MLB', 'MOB', 'MPX', 'MQT', 'MRX',
        'MSO', 'MTR', 'OAX', 'OHX', 'OKX', 'OTX', 'OUN', 'PAH', 'PBZ', 'PDT',
        'PHI', 'PIH', 'PQR', 'PSR', 'PUB', 'RAH', 'REV', 'RIW', 'RLX', 'RNK',
        'SEW', 'SGF', 'SGX', 'SHV', 'SJT', 'SLC', 'STO', 'TAE', 'TBW', 'TFX',
        'TOP', 'TSA', 'TWC', 'UNR', 'VEF'
    ];

    function populateAlertWfoSelect(selectId) {
        const select = byId(selectId);
        if (!select) {
            return;
        }

        const selectedValue = String(select.value || '').toUpperCase();
        select.innerHTML = '<option value="">All WFOs (No Filter)</option>';
        ALERT_WFO_CODES.forEach((code) => {
            const option = document.createElement('option');
            option.value = code;
            option.textContent = code;
            if (code === selectedValue) {
                option.selected = true;
            }
            select.appendChild(option);
        });
    }

    const SELECTOR_RADAR_WMS_URL = 'https://nowcoast.noaa.gov/geoserver/observations/weather_radar/wms';
    const SELECTOR_RADAR_WMS_LAYER = 'base_reflectivity_mosaic';

    function createSelectorRadarLayer(radarOpacity) {
        if (!L?.tileLayer?.wms) {
            return null;
        }
        return L.tileLayer.wms(
            SELECTOR_RADAR_WMS_URL,
            {
                layers: SELECTOR_RADAR_WMS_LAYER,
                format: 'image/png',
                transparent: true,
                opacity: radarOpacity,
                attribution: 'NOAA nowCOAST',
                maxZoom: 19,
                pane: 'selectorRadarPane'
            }
        );
    }

    async function refreshExtentSelectorOverlays(map, options = {}) {
        if (!map || typeof L === 'undefined') {
            return;
        }

        if (!map.getPane('selectorRadarPane')) {
            map.createPane('selectorRadarPane');
            map.getPane('selectorRadarPane').style.zIndex = '450';
        }

        if (!map.__selectorLayerState) {
            map.__selectorLayerState = { radar: true, alerts: true };
        }

        if (!map.__selectorOverlayEventsBound) {
            map.on('overlayadd', (event) => {
                if (event?.layer === map.__selectorRadarLayer) {
                    map.__selectorLayerState.radar = true;
                }
                if (event?.layer === map.__selectorAlertLayer) {
                    map.__selectorLayerState.alerts = true;
                }
            });

            map.on('overlayremove', (event) => {
                if (event?.layer === map.__selectorRadarLayer) {
                    map.__selectorLayerState.radar = false;
                }
                if (event?.layer === map.__selectorAlertLayer) {
                    map.__selectorLayerState.alerts = false;
                }
            });

            map.__selectorOverlayEventsBound = true;
        }

        if (!map.__selectorBaseLayerEventsBound) {
            map.on('baselayerchange', (event) => {
                const baseLayers = map.__selectorBaseLayers || {};
                const selectedKey = Object.keys(baseLayers).find((key) => baseLayers[key] === event?.layer);
                if (selectedKey) {
                    map.__selectorBaseLayerKey = selectedKey;
                }
            });
            map.__selectorBaseLayerEventsBound = true;
        }

        const radarOpacity = Number.isFinite(options.radarOpacity)
            ? Math.max(0, Math.min(1, options.radarOpacity))
            : 0.6;

        if (!map.__selectorRadarLayer) {
            map.__selectorRadarLayer = createSelectorRadarLayer(radarOpacity);
            if (!map.__selectorRadarLayer) {
                console.warn('Extent selector radar disabled: no compatible radar tile layer available.');
                map.__selectorLayerState.radar = false;
            }
        }

        if (map.__selectorRadarLayer) {
            map.__selectorRadarLayer.setOpacity(radarOpacity);
        }

        if (map.__selectorRadarLayer && map.__selectorLayerState.radar && !map.hasLayer(map.__selectorRadarLayer)) {
            map.__selectorRadarLayer.addTo(map);
        }
        if (map.__selectorRadarLayer && !map.__selectorLayerState.radar && map.hasLayer(map.__selectorRadarLayer)) {
            map.removeLayer(map.__selectorRadarLayer);
        }

        const existingAlertsVisible = !!(map.__selectorAlertLayer && map.hasLayer(map.__selectorAlertLayer));
        if (existingAlertsVisible) {
            map.__selectorLayerState.alerts = true;
        }

        if (map.__selectorAlertLayer && map.hasLayer(map.__selectorAlertLayer)) {
            map.removeLayer(map.__selectorAlertLayer);
        }

        try {
            const params = new URLSearchParams({
                region: options.region || 'CONUS',
                hazard: options.hazard || 'All Alerts'
            });

            if (options.wfo) {
                params.set('wfo', options.wfo);
            }

            const response = await fetch(apiUrl(`/api/alerts/polygons?${params.toString()}`));
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const data = await response.json();
            const featureCollection = data?.feature_collection || { type: 'FeatureCollection', features: [] };

            map.__selectorAlertLayer = L.geoJSON(featureCollection, {
                style: (feature) => ({
                    color: feature?.properties?.color || '#ffcc00',
                    weight: 2,
                    opacity: 0.9,
                    fillOpacity: 0.2
                }),
                onEachFeature: (feature, layer) => {
                    const eventName = feature?.properties?.event || 'Alert';
                    const headline = feature?.properties?.headline || '';
                    layer.bindPopup(`<b>${eventName}</b>${headline ? `<br>${headline}` : ''}`);
                }
            });

            if (map.__selectorLayerState.alerts) {
                map.__selectorAlertLayer.addTo(map);
            }

            const overlays = {
                'Alerts': map.__selectorAlertLayer
            };
            if (map.__selectorRadarLayer) {
                overlays.Radar = map.__selectorRadarLayer;
            }

            const baseLayers = map.__selectorBaseLayers || {};

            if (map.__selectorLayerControl) {
                map.removeControl(map.__selectorLayerControl);
            }
            map.__selectorLayerControl = L.control.layers(baseLayers, overlays, {
                collapsed: false,
                position: 'topright'
            }).addTo(map);
        } catch (error) {
            console.warn('Could not refresh selector alert overlays:', error);
        }
    }

    function createExtentSelectorModal(options = {}) {
        const modalId = options.modalId || 'map-modal';
        const mapId = options.mapId || 'leaflet-map';
        const closeButtonId = options.closeButtonId || 'map-modal-close';
        const initialCenter = Array.isArray(options.initialCenter) ? options.initialCenter : [35.5, -79.0];
        const initialZoom = Number.isFinite(options.initialZoom) ? options.initialZoom : 6;
        const onBoundsSelected = typeof options.onBoundsSelected === 'function' ? options.onBoundsSelected : null;
        const onOpen = typeof options.onOpen === 'function' ? options.onOpen : null;

        let mapInstance = null;
        let drawLayer = null;

        const close = () => {
            const modal = byId(modalId);
            if (modal) {
                modal.style.display = 'none';
            }
        };

        const ensureMap = () => {
            if (mapInstance || typeof L === 'undefined') {
                return;
            }

            mapInstance = L.map(mapId).setView(initialCenter, initialZoom);
            mapInstance.__selectorBaseLayers = {
                'Basemap: Dark': L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
                    attribution: '&copy; OpenStreetMap &copy; CartoDB',
                    subdomains: 'abcd',
                    maxZoom: 19
                }),
                'Basemap: Light': L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
                    attribution: '&copy; OpenStreetMap &copy; CartoDB',
                    subdomains: 'abcd',
                    maxZoom: 19
                })
            };
            mapInstance.__selectorBaseLayerKey = 'Basemap: Dark';
            mapInstance.__selectorBaseLayers[mapInstance.__selectorBaseLayerKey].addTo(mapInstance);

            drawLayer = new L.FeatureGroup();
            mapInstance.addLayer(drawLayer);
            mapInstance.addControl(new L.Control.Draw({
                draw: {
                    marker: false,
                    circle: false,
                    circlemarker: false,
                    polyline: false,
                    polygon: false,
                    rectangle: true
                },
                edit: { featureGroup: drawLayer, edit: true, remove: true }
            }));

            if (onBoundsSelected) {
                mapInstance.on(L.Draw.Event.CREATED, (event) => {
                    drawLayer.clearLayers();
                    drawLayer.addLayer(event.layer);
                    onBoundsSelected(event.layer.getBounds());
                });
                mapInstance.on(L.Draw.Event.EDITED, (event) => {
                    event.layers.eachLayer((layer) => onBoundsSelected(layer.getBounds()));
                });
            }
        };

        const open = () => {
            const modal = byId(modalId);
            if (!modal) {
                return;
            }

            ensureMap();
            modal.style.display = 'flex';
            if (!mapInstance) {
                return;
            }

            setTimeout(() => {
                mapInstance.invalidateSize();
                onOpen?.(mapInstance);
            }, 100);
        };

        const clear = () => {
            drawLayer?.clearLayers();
        };

        byId(closeButtonId)?.addEventListener('click', close);

        return {
            open,
            close,
            clear,
            getMap: () => mapInstance,
            getDrawLayer: () => drawLayer
        };
    }

    // ── Shared Screenshot Utilities ──────────────────────────────────────────
    /**
     * Downloads a canvas as PNG with automatic timestamped filename
     * @param {HTMLCanvasElement} canvas - The canvas to download
     * @param {string} [prefix='screenshot'] - Filename prefix (default: 'screenshot')
     * @param {string} [product=''] - Product name for filename (default: '')
     */
    function downloadCanvasAsPng(canvas, prefix = 'screenshot', product = '') {
        const dataUrl = canvas.toDataURL('image/png');
        const a = document.createElement('a');
        const stamp = new Date().toISOString().replace(/[:.]/g, '-');
        const filename = product
            ? `${product}_${prefix}_${stamp}.png`
            : `${prefix}_${stamp}.png`;
        a.href = dataUrl;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    }

    /**
     * Creates a Leaflet map screenshot using leaflet-image plugin
     * @param {L.Map} map - Leaflet map instance
     * @param {Object} [options={}] - Options for screenshot
     * @param {Array<L.Layer>} [options.excludeLayers=[]] - Layers to temporarily exclude from screenshot
     * @returns {Promise<HTMLCanvasElement>} Promise that resolves to the screenshot canvas
     */
    function captureLeafletMap(map, options = {}) {
        const { excludeLayers = [] } = options;
        return new Promise((resolve, reject) => {
            if (typeof window.leafletImage !== 'function') {
                reject(new Error('leaflet-image plugin is not available'));
                return;
            }

            let done = false;
            const timeoutId = setTimeout(() => {
                if (done) return;
                done = true;
                excludeLayers.forEach(layer => {
                    if (layer && map.hasLayer(layer)) {
                        layer.addTo(map);
                    }
                });
                reject(new Error('Map capture timed out'));
            }, 12000);

            const removedLayers = [];
            excludeLayers.forEach(layer => {
                if (layer && map.hasLayer(layer)) {
                    map.removeLayer(layer);
                    removedLayers.push(layer);
                }
            });

            try {
                window.leafletImage(map, (err, canvas) => {
                    if (done) return;
                    done = true;
                    clearTimeout(timeoutId);

                    removedLayers.forEach(layer => layer.addTo(map));

                    if (err || !canvas) {
                        reject(new Error(err ? (err.message || String(err)) : 'Unknown rendering error'));
                        return;
                    }

                    resolve(canvas);
                });
            } catch (err) {
                if (done) return;
                done = true;
                clearTimeout(timeoutId);
                removedLayers.forEach(layer => layer.addTo(map));
                reject(new Error(err?.message || String(err)));
            }
        });
    }

    window.initNav = initNav;
    window.showProgress = showProgress;
    window.hideProgress = hideProgress;
    window.displayImage = displayImage;
    window.displayVideo = displayVideo;
    window.pollProgress = pollProgress;
    window.purgeOldFiles = purgeOldFiles;
    window.setStatus = setStatus;
    window.apiUrl = apiUrl;
    window.setOutputMeta = setOutputMeta;
    window.setOutputMetaFromResponse = setOutputMetaFromResponse;
    window.bindRangeValueLabels = bindRangeValueLabels;
    window.initCollapsibleStyleGroups = initCollapsibleStyleGroups;
    window.refreshExtentSelectorOverlays = refreshExtentSelectorOverlays;
    window.createExtentSelectorModal = createExtentSelectorModal;
    window.populateAlertWfoSelect = populateAlertWfoSelect;
    window.downloadCanvasAsPng = downloadCanvasAsPng;
    window.captureLeafletMap = captureLeafletMap;

    function initSharedUi() {
        initRangeValueLabels();
        initCollapsibleStyleGroups();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initSharedUi, { once: true });
    } else {
        initSharedUi();
    }
})();