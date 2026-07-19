(function () {
    'use strict';

    const byId = (id) => document.getElementById(id);
    const _productPageShell = window.NCHProductPageShell || null;
    const _productAppContexts = window.NCHProductAppContexts || null;
    const _tropicalEngineFactory = window.NCHTropicalEngine || null;
    const _tropicalPageController = window.NCHTropicalPage || null;
    const _standaloneProductType = _productPageShell?.standaloneProductType() || null;
    let _tropicalEngine = null;

    function _isStandaloneProductPage(type = _standaloneProductType) {
        return _productPageShell?.isStandaloneProductPage(type) || !!type;
    }

    function _configureStandaloneProductPage(allTypes) {
        if (_productPageShell) {
            _productPageShell.configureStandaloneProductPage({
                allTypes,
                labels: _TAB_TYPE_LABELS,
                getElementById: byId,
            });
            return;
        }

        if (!_isStandaloneProductPage()) return;
    }

    function _asDate(value) {
        if (value == null || value === '') return null;
        if (value instanceof Date) {
            return Number.isNaN(value.getTime()) ? null : value;
        }
        if (typeof value === 'number') {
            const d = new Date(value);
            return Number.isNaN(d.getTime()) ? null : d;
        }
        if (typeof value === 'string') {
            const raw = value.trim();
            if (!raw) return null;
            const iso = new Date(raw);
            if (!Number.isNaN(iso.getTime())) return iso;
            if (/^\d{12}$/.test(raw)) {
                const d = new Date(Date.UTC(
                    Number(raw.slice(0, 4)),
                    Number(raw.slice(4, 6)) - 1,
                    Number(raw.slice(6, 8)),
                    Number(raw.slice(8, 10)),
                    Number(raw.slice(10, 12)),
                ));
                return Number.isNaN(d.getTime()) ? null : d;
            }
        }
        return null;
    }

    function _part(parts, type, fallback = '') {
        return parts.find((p) => p.type === type)?.value || fallback;
    }

    function _formatViewerTimestamp(value) {
        const dt = _asDate(value);
        if (!dt) {
            return '--/--/----, --:-- LOCAL, (--:-- UTC)';
        }
        const localParts = new Intl.DateTimeFormat('en-US', {
            month: '2-digit',
            day: '2-digit',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            hour12: false,
            timeZoneName: 'short',
        }).formatToParts(dt);
        const utcParts = new Intl.DateTimeFormat('en-US', {
            hour: '2-digit',
            minute: '2-digit',
            hour12: false,
            timeZone: 'UTC',
        }).formatToParts(dt);

        const mm = _part(localParts, 'month', '--');
        const dd = _part(localParts, 'day', '--');
        const yyyy = _part(localParts, 'year', '----');
        const hh = _part(localParts, 'hour', '--');
        const min = _part(localParts, 'minute', '--');
        const tz = _part(localParts, 'timeZoneName', 'LOCAL');
        const utcH = _part(utcParts, 'hour', '--');
        const utcM = _part(utcParts, 'minute', '--');

        return `${mm}/${dd}/${yyyy}, ${hh}:${min} ${tz}, (${utcH}:${utcM} UTC)`;
    }

    function _setViewerTimestamp(value) {
        const el = byId('wx-global-timestamp');
        if (!el) return;
        el.innerHTML = `Last Updated: ${_formatViewerTimestamp(value)}`;
    }


    // ── State Bounds [west, east, south, north] from geo_config.py ──────────
    // Leaflet fitBounds expects [[south, west], [north, east]]
    const STATE_BOUNDS = {
        WORLD: [-179.9, 179.9, -85.0, 85.0],
        CONUS: [-140, -65, 21, 52],
        AL: [-89.0, -84.4, 29.8, 35.7], AK: [-179.5, -129.6, 50.8, 71.8],
        AZ: [-115.8, -107.7, 29.7, 38.3], AR: [-95.0, -89.3, 32.7, 36.9],
        CA: [-124.9, -113.8, 32.2, 42.4], CO: [-109.4, -101.7, 36.6, 41.4],
        CT: [-74.1, -71.4, 40.6, 42.4], DE: [-76.1, -74.7, 38.1, 40.2],
        FL: [-88.0, -79.6, 24.0, 31.4], GA: [-86.0, -80.4, 30.0, 35.4],
        HI: [-160.6, -154.2, 18.2, 22.8], ID: [-117.6, -110.7, 41.6, 49.4],
        IL: [-91.9, -87.1, 36.6, 42.9], IN: [-88.4, -84.4, 37.4, 42.1],
        IA: [-97.0, -89.8, 40.0, 43.9], KS: [-102.4, -94.2, 36.6, 40.4],
        KY: [-89.9, -81.6, 36.1, 39.5], LA: [-94.4, -88.4, 28.5, 33.4],
        ME: [-71.4, -66.5, 42.7, 47.8], MD: [-79.8, -74.7, 37.5, 40.1],
        MA: [-73.9, -69.5, 40.8, 43.2], MI: [-90.8, -82.0, 41.3, 48.7],
        MN: [-97.6, -89.1, 43.1, 49.7], MS: [-92.0, -87.7, 29.8, 35.4],
        MO: [-96.1, -88.7, 35.6, 41.0], MT: [-116.4, -103.7, 44.0, 49.4],
        NE: [-104.4, -94.9, 39.6, 43.4], NV: [-120.4, -113.7, 34.7, 42.4],
        NH: [-72.9, -70.3, 42.3, 45.7], NJ: [-75.9, -73.5, 38.6, 41.7],
        NM: [-109.4, -102.7, 31.0, 37.4], NY: [-80.1, -71.4, 40.1, 45.4],
        NC: [-84.8, -74.7, 33.2, 37.3], ND: [-104.4, -96.2, 45.6, 49.4],
        OH: [-85.2, -80.2, 38.1, 42.3], OK: [-103.4, -94.1, 33.3, 37.4],
        OR: [-124.9, -116.1, 41.6, 46.6], PA: [-80.9, -74.3, 39.4, 42.6],
        PR: [-67.4, -65.1, 17.8, 18.6],
        RI: [-72.2, -70.8, 40.8, 42.4], SC: [-83.7, -78.1, 31.7, 35.6],
        SD: [-104.4, -96.1, 42.1, 46.3], TN: [-90.7, -81.3, 34.6, 37.0],
        TX: [-107.0, -93.1, 25.5, 36.9], UT: [-114.4, -108.7, 36.6, 42.4],
        VT: [-73.8, -71.1, 42.4, 45.4], VA: [-84.0, -74.8, 36.2, 39.8],
        WA: [-125.2, -116.6, 45.2, 49.4], WV: [-83.0, -77.4, 36.8, 41.0],
        WI: [-93.2, -86.4, 42.1, 47.4], WY: [-111.4, -103.7, 40.6, 45.4],
    };

    function leafletBounds(code) {
        const b = STATE_BOUNDS[code];
        if (!b) return null;
        return [[b[2], b[0]], [b[3], b[1]]]; // [[south, west], [north, east]]
    }

    // ── Alert colors (synced from config/alerts_config.py ALERT_COLORS) ────
    const ALERT_COLORS = {
        'Tsunami Warning': '#FD6347',
        'Tornado Warning': '#FF0000',
        'Extreme Wind Warning': '#FF8C00',
        'Severe Thunderstorm Warning': '#FFA500',
        'Flash Flood Warning': '#8B0000',
        'Flash Flood Statement': '#8B0000',
        'Severe Weather Statement': '#00FFFF',
        'Civil Danger Warning': '#FFB6C1',
        'Radiological Hazard Warning': '#4B0082',
        'Hazardous Materials Warning': '#4B0082',
        'Fire Warning': '#A0522D',
        'Storm Surge Warning': '#B524F7',
        'Hurricane Force Wind Warning': '#CD5C5C',
        'Hurricane Warning': '#DC143C',
        'Typhoon Warning': '#DC143C',
        'Special Marine Warning': '#FFA500',
        'Blizzard Warning': '#FF4500',
        'Snow Squall Warning': '#C71585',
        'Ice Storm Warning': '#8B008B',
        'Heavy Freezing Spray Warning': '#00BFFF',
        'Winter Storm Warning': '#FF69B4',
        'Lake Effect Snow Warning': '#008B8B',
        'Dust Storm Warning': '#FFE4C4',
        'Blowing Dust Warning': '#FFE4C4',
        'High Wind Warning': '#DAA520',
        'Tropical Storm Warning': '#B22222',
        'Storm Warning': '#9400D3',
        'Tsunami Advisory': '#D2691E',
        'Tsunami Watch': '#FF00FF',
        'Avalanche Warning': '#1E90FF',
        'Earthquake Warning': '#8B4513',
        'Volcano Warning': '#2F4F4F',
        'Ashfall Warning': '#A9A9A9',
        'Flood Warning': '#00FF00',
        'Coastal Flood Warning': '#228B22',
        'Lakeshore Flood Warning': '#228B22',
        'Ashfall Advisory': '#696969',
        'High Surf Warning': '#228B22',
        'Extreme Heat Warning': '#C71585',
        'Tornado Watch': '#FFFF00',
        'Severe Thunderstorm Watch': '#DB7093',
        'Flash Flood Watch': '#2E8B57',
        'Gale Warning': '#DDA0DD',
        'Flood Statement': '#00FF00',
        'Extreme Cold Warning': '#0000FF',
        'Freeze Warning': '#483D8B',
        'Red Flag Warning': '#FF1493',
        'Storm Surge Watch': '#DB7FF7',
        'Hurricane Watch': '#FF00FF',
        'Hurricane Force Wind Watch': '#9932CC',
        'Typhoon Watch': '#FF00FF',
        'Tropical Storm Watch': '#F08080',
        'Storm Watch': '#FFE4B5',
        'Tropical Cyclone Local Statement': '#FFE4B5',
        'Winter Weather Advisory': '#7B68EE',
        'Avalanche Advisory': '#CD853F',
        'Cold Weather Advisory': '#AFEEEE',
        'Heat Advisory': '#FF7F50',
        'Flood Advisory': '#00FF7F',
        'Coastal Flood Advisory': '#7CFC00',
        'Lakeshore Flood Advisory': '#7CFC00',
        'High Surf Advisory': '#BA55D3',
        'Dense Fog Advisory': '#708090',
        'Dense Smoke Advisory': '#F0E68C',
        'Small Craft Advisory': '#D8BFD8',
        'Brisk Wind Advisory': '#D8BFD8',
        'Hazardous Seas Warning': '#D8BFD8',
        'Dust Advisory': '#BDB76B',
        'Blowing Dust Advisory': '#BDB76B',
        'Lake Wind Advisory': '#D2B48C',
        'Wind Advisory': '#D2B48C',
        'Frost Advisory': '#6495ED',
        'Freezing Fog Advisory': '#008080',
        'Freezing Spray Advisory': '#00BFFF',
        'Low Water Advisory': '#A52A2A',
        'Local Area Emergency': '#C0C0C0',
        'Winter Storm Watch': '#4682B4',
        'Rip Current Statement': '#40E0D0',
        'Beach Hazards Statement': '#40E0D0',
        'Gale Watch': '#FFC0CB',
        'Avalanche Watch': '#F4A460',
        'Hazardous Seas Watch': '#483D8B',
        'Heavy Freezing Spray Watch': '#BC8F8F',
        'Flood Watch': '#2E8B57',
        'Coastal Flood Watch': '#66CDAA',
        'Lakeshore Flood Watch': '#66CDAA',
        'High Wind Watch': '#B8860B',
        'Extreme Heat Watch': '#800000',
        'Extreme Cold Watch': '#5F9EA0',
        'Freeze Watch': '#00FFFF',
        'Fire Weather Watch': '#FFDEAD',
        'Extreme Fire Danger': '#E9967A',
        'Coastal Flood Statement': '#6B8E23',
        'Lakeshore Flood Statement': '#6B8E23',
        'Special Weather Statement': '#FFE4B5',
        'Marine Weather Statement': '#FFDAB9',
        'Air Quality Alert': '#808080',
        'Air Stagnation Advisory': '#808080',
        'Hazardous Weather Outlook': '#EEE8AA',
        'Hydrologic Outlook': '#90EE90',
        'Short Term Forecast': '#98FB98',
        // VTEC-derived events not in original NWS list
        'Wind Chill Warning': '#5F9EA0',
        'Wind Chill Watch': '#5F9EA0',
        'Wind Chill Advisory': '#AFEEEE',
        'Hard Freeze Warning': '#9400D3',
        'Hard Freeze Watch': '#4169E1',
        'Freezing Rain Advisory': '#DA70D6',
        'Sleet Warning': '#EE82EE',
        'Sleet Advisory': '#DDA0DD',
        'Ice Storm Watch': '#48D1CC',
        'Heat Warning': '#C71585',
    };
    const ALERT_DEFAULT = '#6699cc';


    // ── Map init ─────────────────────────────────────────────────────────────
    const tileOptions = {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
        subdomains: 'abcd',
        maxZoom: 19,
        noWrap: false,
    };
    // CONUS framing is driven entirely by CONUS_DEFAULT_BOUNDS via fitBounds(),
    // so the visible extent adapts to the viewport size instead of being fixed
    // by a center/zoom pair.
    const CONUS_DEFAULT_BOUNDS = [[23.0, -127.0], [50.5, -65.0]];
    const WORLD_DEFAULT_BOUNDS = [[-60, -179.9], [85, 179.9]];
    const TROPICAL_DEFAULT_CENTER = [33.4183, -87.0313];
    const TROPICAL_DEFAULT_ZOOM = 4;
    const REGION_FIT_BOTTOM_PADDING_PX = 120;
    const USER_SETTINGS_DEFAULTS_URL = '/api/user-settings/defaults';

    let _userSettingsDefaults = null;
    let _productRenderArmed = true;

    const tilesDarkNoLabels = L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png', tileOptions);
    const tilesLightNoLabels = L.tileLayer('https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png', tileOptions);
    const tilesVoyager = L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', tileOptions);
    var USGS_USImagery = L.tileLayer('https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/{z}/{y}/{x}', {
        maxZoom: 20,
        noWrap: false,
        attribution: 'Tiles courtesy of the <a href="https://usgs.gov/">U.S. Geological Survey</a>'
    });
    const tilesSatellite = L.tileLayer(
        'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        {
            attribution: 'Tiles &copy; Esri',
            maxZoom: 19,
            noWrap: false,
        },
    );

    const map = L.map('weather-map', {
        layers: [tilesDarkNoLabels],
        minZoom: 2,
        maxBounds: [[-85, -360], [85, 360]],
        maxBoundsViscosity: 1.0,
    });
    map.fitBounds(CONUS_DEFAULT_BOUNDS, { animate: false });

    // Initialize city font size CSS variable from slider (or default to 0.6)
    const cityFontSizeSlider = byId('weather-cities-font-size');
    if (cityFontSizeSlider) {
        const val = parseFloat(cityFontSizeSlider.value || '0.6');
        document.documentElement.style.setProperty('--city-font-size', String(val));
    }

    function _initLeafletZoomIndicator() {
        const zoomContainer = map.zoomControl?.getContainer?.();
        if (!zoomContainer) return;

        zoomContainer.classList.add('wx-zoom-indicator-enabled');
        let indicator = zoomContainer.querySelector('.wx-leaflet-zoom-indicator');
        if (!indicator) {
            indicator = document.createElement('div');
            indicator.className = 'wx-leaflet-zoom-indicator';
            indicator.setAttribute('role', 'status');
            indicator.setAttribute('aria-live', 'polite');
            zoomContainer.appendChild(indicator);
        }

        const update = () => {
            const leafletZoom = Number(map.getZoom()) || 0;
            indicator.textContent = `z ${Math.round(leafletZoom)}`;
            indicator.title = `Zoom ${leafletZoom.toFixed(2)}`;
        };

        update();
        map.on('zoom zoomend move moveend resize', update);
    }

    _initLeafletZoomIndicator();

    const baseLayers = {
        'Dark (No Labels)': tilesDarkNoLabels,
        'Light (No Labels)': tilesLightNoLabels,
        'Voyager': tilesVoyager,
        'USGS': USGS_USImagery,
        'Satellite': tilesSatellite,
    };
    // Custom compact basemap selector (replaces Leaflet's built-in layer control)
    const BasemapControl = L.Control.extend({
        options: { position: 'topleft' },
        onAdd(m) {
            const container = L.DomUtil.create('div', 'wx-basemap-control leaflet-bar');
            L.DomEvent.disableClickPropagation(container);
            L.DomEvent.disableScrollPropagation(container);

            const btn = L.DomUtil.create('button', 'wx-basemap-btn', container);
            btn.type = 'button';
            btn.title = 'Switch basemap';
            btn.innerHTML = '<i class="fa-solid fa-layer-group fa-xl"></i>';

            const dropdown = L.DomUtil.create('div', 'wx-basemap-dropdown', container);
            let activeLayer = 'Dark (No Labels)';

            for (const name of Object.keys(baseLayers)) {
                const item = L.DomUtil.create('button', 'wx-basemap-item', dropdown);
                item.type = 'button';
                item.textContent = name;
                if (name === activeLayer) item.classList.add('active');
                L.DomEvent.on(item, 'click', () => {
                    for (const layer of Object.values(baseLayers)) {
                        if (m.hasLayer(layer)) m.removeLayer(layer);
                    }
                    baseLayers[name].addTo(m);
                    activeLayer = name;
                    dropdown.querySelectorAll('.wx-basemap-item').forEach((el) => {
                        el.classList.toggle('active', el.textContent === name);
                    });
                    dropdown.classList.remove('open');
                    btn.classList.remove('open');
                });
            }

            L.DomEvent.on(btn, 'click', () => {
                const isOpen = dropdown.classList.toggle('open');
                btn.classList.toggle('open', isOpen);
            });

            // Close on outside click
            L.DomEvent.on(document, 'click', (e) => {
                if (!container.contains(e.target)) {
                    dropdown.classList.remove('open');
                    btn.classList.remove('open');
                }
            });

            return container;
        },
    });
    const ResetViewControl = L.Control.extend({
        options: { position: 'topleft' },
        onAdd(m) {
            const container = L.DomUtil.create('div', 'wx-reset-view-control leaflet-bar');
            L.DomEvent.disableClickPropagation(container);
            const btn = L.DomUtil.create('button', 'wx-reset-view-btn', container);
            btn.type = 'button';
            btn.title = 'Reset to default view';
            btn.innerHTML = '<i class="fa-solid fa-house fa-2xl"></i>';
            L.DomEvent.on(btn, 'click', () => {
                // Tropical tab uses its own default extent; all others use CONUS.
                if (byId('weather-type-tropical')?.checked) {
                    // Clear any selected storm and return to the true default: GTWO
                    // outlook only, at the default extent.
                    _tropicalRequestSeq += 1;
                    _activeTropicalStorm = null;
                    _clearTropicalLayer();
                    _closeTropicalDetail();
                    _closeOutlookDetail();
                    _renderTropicalSummary(null);
                    const sysSelect = byId('weather-tropical-system');
                    if (sysSelect) sysSelect.value = '';
                    _setTropicalHubMode('overview');
                    _highlightSelectedTropicalCard();
                    _setTropicalMapViewMode('outlook');
                    _renderTropicalOutlookLegend();
                    _applyOutlookReliability();
                    fitTropicalDefaultExtent();
                } else {
                    fitRegion(byId('weather-region')?.value || 'CONUS');
                }
            });
            return container;
        },
    });
    new ResetViewControl().addTo(map);
    new BasemapControl().addTo(map);
    map.attributionControl.addAttribution('©2026 ChuckCopeland.com/NCHurricane.com');
    if (!map.getPane('boundary-lines')) {
        // Above overlayPane (400) so borders sit over data fills on every tab,
        // below interactive product markers. The pane gets a CSS drop-shadow
        // halo so the lines read on both dark and light basemaps.
        const boundaryLinesPane = map.createPane('boundary-lines');
        boundaryLinesPane.style.zIndex = '420';
        boundaryLinesPane.style.pointerEvents = 'none';
    }
    if (!map.getPane('water-markers')) {
        const waterMarkersPane = map.createPane('water-markers');
        waterMarkersPane.style.zIndex = '470';
    }
    const LogoControl = L.Control.extend({
        options: { position: 'topright' },
        onAdd() {
            const div = L.DomUtil.create('div', 'leaflet-control-logo');
            const img = L.DomUtil.create('img', '', div);
            img.src = 'img/nchurricane_logo.png';
            img.alt = 'NCHurricane.com';
            img.loading = 'lazy';
            return div;
        },
    });
    new LogoControl().addTo(map);

    // --- Storm Track Icon Legend (topright, below logo) ---
    const NstLegendControl = L.Control.extend({
        options: { position: 'topright' },
        onAdd() {
            const S = 20;
            const hS = S / 2;
            const mkSvg = (inner) =>
                `<svg xmlns="http://www.w3.org/2000/svg" width="${S}" height="${S}" viewBox="0 0 ${S} ${S}">${inner}</svg>`;
            const items = [
                {
                    svg: mkSvg(
                        `<polygon points="1,2 ${S - 1},2 ${hS},${S - 1}" fill="#ef4444" stroke="#020617" stroke-width="2.5" stroke-linejoin="round"/>`
                        + `<polygon points="1,2 ${S - 1},2 ${hS},${S - 1}" fill="#ef4444" stroke="#fff" stroke-width="1" stroke-linejoin="round"/>`
                        + `<text x="${hS}" y="13" text-anchor="middle" font-family="Arial" font-size="7" font-weight="900" fill="#fff" stroke="#020617" stroke-width="1.5" paint-order="stroke fill">T</text>`
                    ),
                    label: 'Tornadic Vortex Signature',
                },
                {
                    svg: mkSvg(
                        `<circle cx="${hS}" cy="${hS}" r="${hS - 1}" fill="#f97316" stroke="#020617" stroke-width="2.5"/>`
                        + `<circle cx="${hS}" cy="${hS}" r="${hS - 2.5}" fill="#f97316" stroke="#fff" stroke-width="1"/>`
                        + `<text x="${hS}" y="13" text-anchor="middle" font-family="Arial" font-size="7" font-weight="900" fill="#fff" stroke="#020617" stroke-width="1.5" paint-order="stroke fill">M</text>`
                    ),
                    label: 'Mesocyclone',
                },
                {
                    svg: mkSvg(
                        `<polygon points="${hS},1 ${S - 1},${S - 2} 1,${S - 2}" fill="#22c55e" stroke="#020617" stroke-width="2.5" stroke-linejoin="round"/>`
                        + `<polygon points="${hS},1 ${S - 1},${S - 2} 1,${S - 2}" fill="#22c55e" stroke="#fff" stroke-width="1" stroke-linejoin="round"/>`
                        + `<text x="${hS}" y="15" text-anchor="middle" font-family="Arial" font-size="7" font-weight="900" fill="#fff" stroke="#020617" stroke-width="1.5" paint-order="stroke fill">H</text>`
                    ),
                    label: 'Confirmed Hail (POSH ≥50%)',
                },
                {
                    svg: mkSvg(
                        `<polygon points="${hS},1 ${S - 1},${S - 2} 1,${S - 2}" fill="#020617" stroke="#22c55e" stroke-width="2.5" stroke-linejoin="round"/>`
                        + `<polygon points="${hS},1 ${S - 1},${S - 2} 1,${S - 2}" fill="#020617" stroke="#fff" stroke-width="1" stroke-linejoin="round"/>`
                    ),
                    label: 'Probable Hail (POH ≥50%)',
                },
                {
                    svg: (() => {
                        const sC = 16; const p = 2;
                        return `<svg xmlns="http://www.w3.org/2000/svg" width="${sC}" height="${sC}" viewBox="0 0 ${sC} ${sC}">`
                            + `<rect x="${p}" y="${p}" width="${sC - p * 2}" height="${sC - p * 2}" rx="1.5" fill="#111827" stroke="#020617" stroke-width="2.5"/>`
                            + `<rect x="${p + 1.5}" y="${p + 1.5}" width="${sC - p * 2 - 3}" height="${sC - p * 2 - 3}" rx="1" fill="#111827" stroke="#facc15" stroke-width="1.5"/>`
                            + `</svg>`;
                    })(),
                    label: 'Storm Cell',
                },
            ];
            const rows = items.map((it) =>
                `<div class="wx-mini-legend-row">${it.svg}<span>${it.label}</span></div>`
            ).join('');
            const div = L.DomUtil.create('div', 'wx-mini-legend leaflet-control');
            div.id = 'wx-mini-legend';
            div.innerHTML = `<div class="wx-mini-legend-title">Storm Tracks</div>${rows}`;
            div.style.display = 'none';
            L.DomEvent.disableClickPropagation(div);
            return div;
        },
    });
    new NstLegendControl().addTo(map);

    // Top-center "Last Updated" badge, anchored to the map wrap.
    (() => {
        const wrap = document.querySelector('.weather-map-wrap');
        if (!wrap || document.getElementById('wx-global-timestamp')) return;
        const ts = document.createElement('div');
        ts.id = 'wx-global-timestamp';
        ts.className = 'wx-global-timestamp wx-global-timestamp-top';
        ts.innerHTML = `Last Updated: ${_formatViewerTimestamp(null)}`;
        wrap.appendChild(ts);
    })();

    // ── Layer state ──────────────────────────────────────────────────────────
    let _scrubberPlaybackSpeedIndex = 2;
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
    let tropicalOutlookLayer = null;
    let graticuleLayer = null;
    let _tropicalStorms = [];

    let _activeTropicalStorm = null;
    let _tropicalRequestSeq = 0;
    // Tropical Archive (HURDAT2 browser).
    let _tropicalArchiveCatalog = null;
    let _tropicalArchiveSelectedId = null;
    // Archive "context": while active we relabel the Layers tab → "Current"
    // as the way back to live mode.
    let _tropicalArchiveContext = false;
    // Phase C — per-advisory scrubber state for a modern archived storm.
    let _tropicalArchiveStormBase = null;   // storm.json (best-track + advisories index)
    let _tropicalArchiveStormId = null;
    let _tropicalArchiveStormName = null;
    let _tropicalFixMarker = null;           // moving intensity glyph at the current fix
    // When set, the reliability bar shows this storm-date label in the "Age"
    // slot instead of a (nonsensical) age for decades-old best-track storms.
    let _tropicalArchiveReliabilityLabel = null;
    let _activeOutlookDetail = null;
    let _activeOutlookFeature = null;
    let _outlookFeatureMap = {};
    let _tropicalMapViewMode = 'outlook'; // 'outlook', 'system', or 'both'
    let _tropicalOutlookIssuedTime = null;
    let statesLayer = null;
    let countiesLayer = null;
    let countriesLayer = null;
    let citiesLayer = null;
    let _citiesData = null;
    const _citiesDataBySource = new Map();
    let _citiesSource = null;
    let _citiesDensity = 1;
    const CITY_LABEL_CHAR_PX = 5.2;
    const CITY_LABEL_HEIGHT_PX = 11;
    const CITY_LABEL_X_PAD = 4;
    const CITY_LABEL_Y_PAD = 2;
    const CITY_SOURCES = {
        us: { path: '/data/us-cities-all.json', label: 'US' },
        world: { path: '/data/world-cities.json', label: 'World' },
    };
    // Reserved for Phase 27 workspace wiring into the preserved arrival tool.
    let _allAlertFeatures = [];
    let _stormTrackLayer = L.layerGroup().addTo(map);
    let _stormTrackProjectionLayer = L.layerGroup().addTo(_stormTrackLayer);
    let _stormTrackHandleLayer = L.layerGroup().addTo(_stormTrackLayer);
    let _stormTrackDrawMode = false;
    let _stormTrackBaseLatLngs = [];
    let _stormTrackSelectedAlert = null;
    let _stormTrackMotion = null;
    let _stormTrackActiveBearingDeg = null;
    let _stormTrackPivotKeyDown = false;
    let _stormTrackDragAnchor = null;
    let _stormTrackDragHandle = null;
    let _stormTrackPlacesOverlayEl = null;
    let _stormTrackPlacesDataPromise = null;
    let _stormTrackPlacesComputeSeq = 0;
    let _stormTrackPlaceRows = [];
    const _STORM_TRACK_PLACE_TYPES = [
        { key: 'city', label: 'Cities' },
        { key: 'town', label: 'Towns' },
        { key: 'village', label: 'Villages' },
        { key: 'hamlet', label: 'Hamlets' },
    ];
    const _stormTrackPlaceTypeFilter = new Set(_STORM_TRACK_PLACE_TYPES.map((t) => t.key));
    let _stormTrackLastCorridorLatLngs = [];
    let _stormTrackOutlineLayer = null;
    // ── Radar Speed Calibrator state ─────────────────────────────────────────
    let _radarCalDrawMode = false;
    let _radarCalLatLngs = [];
    let _radarCalLayer = null;
    const _STORM_TRACK_INTERVAL_MIN = 15;
    const _STORM_TRACK_WIDTH_GROWTH_PER_INTERVAL = 0.10;
    const _STORM_TRACK_PIVOT_MAX_DEG = 45;
    const _STORM_TRACK_MAX_PLACE_ROWS = 50;
    const SCRUBBER_PLAYBACK_SPEEDS = [0.25, 0.5, 1, 1.5, 2, 3, 4];
    const RTMA_SCRUB_PLAY_INTERVAL_MS = 300;
    const RTMA_SCRUB_LOOP_HOLD_MS = 2000;
    const _RADAR_OVERLAY_FRAMES = 4;
    const _RADAR_OVERLAY_STEP_MIN = 5;
    // The Alerts speed estimator treats the legacy radar loop as four 5-minute
    // steps when converting a user-drawn displacement into forward speed.

    // ── Preserved workspace storm-motion tools ───────────────────────────────
    function _ringContainsPoint(ring, lng, lat) {
        let inside = false;
        for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
            const [xi, yi] = ring[i];
            const [xj, yj] = ring[j];
            const intersects = ((yi > lat) !== (yj > lat))
                && (lng < ((xj - xi) * (lat - yi)) / ((yj - yi) || Number.EPSILON) + xi);
            if (intersects) inside = !inside;
        }
        return inside;
    }

    const _CARDINAL_TO_BEARING = {
        N: 0,
        NNE: 22.5,
        NE: 45,
        ENE: 67.5,
        E: 90,
        ESE: 112.5,
        SE: 135,
        SSE: 157.5,
        S: 180,
        SSW: 202.5,
        SW: 225,
        WSW: 247.5,
        W: 270,
        WNW: 292.5,
        NW: 315,
        NNW: 337.5,
    };

    function _normalizeMotionDirection(rawDir) {
        return String(rawDir || '')
            .toUpperCase()
            .replace(/[^A-Z]/g, '');
    }

    function _directionToBearing(rawDir) {
        const norm = _normalizeMotionDirection(rawDir);
        if (_CARDINAL_TO_BEARING[norm] !== undefined) return _CARDINAL_TO_BEARING[norm];

        const words = String(rawDir || '').toUpperCase().replace(/[^A-Z\s]/g, ' ').replace(/\s+/g, ' ').trim();
        const alias = {
            NORTH: 'N',
            NORTHEAST: 'NE',
            EAST: 'E',
            SOUTHEAST: 'SE',
            SOUTH: 'S',
            SOUTHWEST: 'SW',
            WEST: 'W',
            NORTHWEST: 'NW',
        };
        if (alias[words] && _CARDINAL_TO_BEARING[alias[words]] !== undefined) {
            return _CARDINAL_TO_BEARING[alias[words]];
        }
        return null;
    }

    function _extractAlertMotion(feat) {
        const p = feat?.properties || {};
        const params = p.parameters || {};
        // Prefer the human-readable alert text direction first because it is
        // generally the best "storm moving toward" source for this workflow.
        const desc = String(p.description || '');
        const descMatch = desc.match(/MOVING\s+([A-Z\-\s]+?)\s+AT\s+(\d{1,3})\s*(MPH|KTS?|KT)\b/i);
        if (descMatch) {
            const bearing = _directionToBearing(descMatch[1]);
            const speed = Number(descMatch[2]);
            const unit = String(descMatch[3] || '').toUpperCase();
            if (Number.isFinite(bearing) && Number.isFinite(speed) && speed > 0) {
                const speedMps = unit.startsWith('MPH') ? speed * 0.44704 : speed * 0.514444;
                return { bearingDeg: bearing, speedMps, source: 'description' };
            }
        }

        const emd = Array.isArray(params.eventMotionDescription) ? String(params.eventMotionDescription[0] || '') : '';
        const emdMatch = emd.match(/(\d{1,3})\s*DEG[\s.]*?(\d{1,3})\s*K[TN]/i);
        if (emdMatch) {
            const bearing = Number(emdMatch[1]);
            const speedKt = Number(emdMatch[2]);
            if (Number.isFinite(bearing) && Number.isFinite(speedKt) && speedKt > 0) {
                // eventMotionDescription bearings can be encoded opposite the
                // intuitive "toward" direction. Flip by 180 so projected drag
                // aligns with storm-forward motion on the map.
                return {
                    bearingDeg: (((bearing + 180) % 360) + 360) % 360,
                    speedMps: speedKt * 0.514444,
                    source: 'eventMotionDescription',
                };
            }
        }
        return null;
    }

    function _stormTrackFallbackAlert() {
        if (featIsValid(_stormTrackSelectedAlert)) return _stormTrackSelectedAlert;
        const severe = (_allAlertFeatures || []).find((f) => {
            const evt = String(f?.properties?.event || '');
            return evt === 'Tornado Warning' || evt === 'Severe Thunderstorm Warning' || evt === 'Flash Flood Warning';
        });
        return severe || (_allAlertFeatures || [])[0] || null;
    }

    function featIsValid(feat) {
        return !!(feat && feat.type === 'Feature' && feat.properties);
    }

    function _offsetLatLngGeodesic(latlng, bearingDeg, distanceMeters) {
        const R = 6371000;
        const br = (bearingDeg * Math.PI) / 180;
        const lat1 = (latlng.lat * Math.PI) / 180;
        const lon1 = (latlng.lng * Math.PI) / 180;
        const dr = distanceMeters / R;

        const lat2 = Math.asin(
            Math.sin(lat1) * Math.cos(dr)
            + Math.cos(lat1) * Math.sin(dr) * Math.cos(br),
        );
        const lon2 = lon1 + Math.atan2(
            Math.sin(br) * Math.sin(dr) * Math.cos(lat1),
            Math.cos(dr) - Math.sin(lat1) * Math.sin(lat2),
        );

        return L.latLng((lat2 * 180) / Math.PI, (lon2 * 180) / Math.PI);
    }

    function _bearingBetweenLatLng(fromLatLng, toLatLng) {
        const lat1 = (fromLatLng.lat * Math.PI) / 180;
        const lat2 = (toLatLng.lat * Math.PI) / 180;
        const dLon = ((toLatLng.lng - fromLatLng.lng) * Math.PI) / 180;
        const y = Math.sin(dLon) * Math.cos(lat2);
        const x = Math.cos(lat1) * Math.sin(lat2)
            - Math.sin(lat1) * Math.cos(lat2) * Math.cos(dLon);
        const br = (Math.atan2(y, x) * 180) / Math.PI;
        return ((br % 360) + 360) % 360;
    }

    function _signedBearingDeltaDeg(fromBearing, toBearing) {
        let d = (((toBearing - fromBearing) % 360) + 360) % 360;
        if (d > 180) d -= 360;
        return d;
    }

    function _normalizeBearingDeg(bearingDeg) {
        return (((Number(bearingDeg) % 360) + 360) % 360);
    }

    function _pivotedBearingDeg(rawBearingDeg) {
        const baseBearing = _stormTrackMotion?.bearingDeg;
        if (!Number.isFinite(baseBearing)) return null;
        if (!_stormTrackPivotKeyDown) return _normalizeBearingDeg(baseBearing);
        const raw = _normalizeBearingDeg(rawBearingDeg);
        const delta = _signedBearingDeltaDeg(baseBearing, raw);
        const clamped = Math.max(-_STORM_TRACK_PIVOT_MAX_DEG, Math.min(_STORM_TRACK_PIVOT_MAX_DEG, delta));
        return _normalizeBearingDeg(baseBearing + clamped);
    }

    function _projectMetersOnMotion(anchor, point, motionBearingDeg) {
        const distance = anchor.distanceTo(point);
        if (!Number.isFinite(distance) || distance <= 0) return 0;
        const ptBearing = _bearingBetweenLatLng(anchor, point);
        const delta = _signedBearingDeltaDeg(motionBearingDeg, ptBearing);
        const alongPrimary = distance * Math.cos((delta * Math.PI) / 180);
        return Math.max(0, alongPrimary);
    }

    function _stormTrackAnchor(basePts) {
        if (!Array.isArray(basePts) || !basePts.length) return null;
        let sumLat = 0;
        let sumLng = 0;
        for (const pt of basePts) {
            sumLat += pt.lat;
            sumLng += pt.lng;
        }
        return L.latLng(sumLat / basePts.length, sumLng / basePts.length);
    }

    function _stateAbbrFromPlaceRecord(rec) {
        const iso = String(rec?.address?.['ISO3166-2-lvl4'] || '').toUpperCase();
        const m = iso.match(/^US-([A-Z]{2})$/);
        if (m) return m[1];
        return '';
    }

    function _parseNdjsonPlaces(text) {
        const rows = [];
        const lines = String(text || '').split(/\r?\n/);
        for (const line of lines) {
            const raw = line.trim();
            if (!raw) continue;
            try {
                const rec = JSON.parse(raw);
                const loc = Array.isArray(rec?.location) ? rec.location : [];
                const lng = Number(loc[0]);
                const lat = Number(loc[1]);
                if (!Number.isFinite(lat) || !Number.isFinite(lng)) continue;
                const name = String(rec?.name || '').trim();
                if (!name) continue;
                const popRaw = Number(rec?.population);
                rows.push({
                    name,
                    state: _stateAbbrFromPlaceRecord(rec),
                    lat,
                    lng,
                    type: String(rec?.type || '').toLowerCase(),
                    population: Number.isFinite(popRaw) ? popRaw : null,
                });
            } catch (_) {
                // Skip malformed lines.
            }
        }
        return rows;
    }

    async function _loadStormTrackPlacesData() {
        if (_stormTrackPlacesDataPromise) return _stormTrackPlacesDataPromise;
        _stormTrackPlacesDataPromise = (async () => {
            // Categorize by source file, not by each record's heterogeneous OSM
            // `type` (city records are tagged "administrative", etc.).
            const sources = [
                { path: 'data/place_city.ndjson', category: 'city' },
                { path: 'data/place-town.ndjson', category: 'town' },
                { path: 'data/place-village.ndjson', category: 'village' },
                { path: 'data/place-hamlet.ndjson', category: 'hamlet' },
            ];
            const urls = sources.map((s) => apiUrl(s.path));
            const responses = await Promise.all(urls.map((u) => fetch(u, { cache: 'force-cache' })));
            const texts = await Promise.all(responses.map(async (resp, idx) => {
                if (!resp.ok) {
                    const path = sources[idx]?.path || 'places file';
                    throw new Error(`Failed loading ${path} (${resp.status}).`);
                }
                return resp.text();
            }));
            const merged = [];
            texts.forEach((txt, idx) => {
                const category = sources[idx].category;
                for (const rec of _parseNdjsonPlaces(txt)) {
                    rec.type = category;
                    merged.push(rec);
                }
            });
            return merged;
        })().catch((err) => {
            _stormTrackPlacesDataPromise = null;
            const baseMsg = String(err?.message || err || 'unknown error');
            if (window.location.protocol === 'file:') {
                throw new Error(`${baseMsg} Open the dashboard via http://127.0.0.1:8000/weather.html (run python main.py), not via file://.`);
            }
            throw err;
        });
        return _stormTrackPlacesDataPromise;
    }

    function _stormTrackPlaceTimeZone(place) {
        try {
            if (typeof window.tzlookup === 'function') {
                return String(window.tzlookup(place.lat, place.lng) || '').trim();
            }
        } catch (_) {
            // fallback below
        }
        return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
    }

    function _formatStormTrackArrivalMs(ms, ianaTz) {
        const d = new Date(ms);
        try {
            return new Intl.DateTimeFormat(undefined, {
                hour: 'numeric',
                minute: '2-digit',
                timeZone: ianaTz,
                timeZoneName: 'short',
            }).format(d);
        } catch (_) {
            return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
        }
    }

    function _ensureStormTrackPlacesOverlay() {
        const wrap = document.querySelector('.weather-map-wrap');
        if (!wrap) return null;
        if (_stormTrackPlacesOverlayEl?.parentElement === wrap) return _stormTrackPlacesOverlayEl;

        const panel = document.createElement('div');
        panel.className = 'wx-stormtrack-places';
        panel.innerHTML = [
            '<div class="wx-stormtrack-places-head"><span class="wx-stormtrack-places-head-title">Projected Arrival Times</span><button type="button" class="wx-stormtrack-places-close" aria-label="Close projected arrival times">X</button>',
            '<div class="wx-small">Times are approximate</div></div>',
            '<div class="wx-stormtrack-places-body"><div class="wx-stormtrack-empty">No projected arrival times yet.</div></div>',
        ].join('');
        wrap.appendChild(panel);

        const head = panel.querySelector('.wx-stormtrack-places-head');
        const closeBtn = panel.querySelector('.wx-stormtrack-places-close');
        let drag = null;
        const onMove = (evt) => {
            if (!drag) return;
            const x = evt.clientX - drag.wrapLeft - drag.dx;
            const y = evt.clientY - drag.wrapTop - drag.dy;
            panel.style.left = `${x}px`;
            panel.style.top = `${y}px`;
            panel.style.right = 'auto';
        };
        const onUp = () => {
            drag = null;
            document.removeEventListener('pointermove', onMove);
            document.removeEventListener('pointerup', onUp);
        };
        head?.addEventListener('pointerdown', (evt) => {
            if (evt.target && evt.target.closest('.wx-stormtrack-places-close')) return;
            const wrapRect = wrap.getBoundingClientRect();
            const rect = panel.getBoundingClientRect();
            drag = {
                dx: evt.clientX - rect.left,
                dy: evt.clientY - rect.top,
                wrapLeft: wrapRect.left,
                wrapTop: wrapRect.top,
            };
            evt.preventDefault();
            document.addEventListener('pointermove', onMove);
            document.addEventListener('pointerup', onUp);
        });
        closeBtn?.addEventListener('click', (evt) => {
            evt.preventDefault();
            evt.stopPropagation();
            panel.remove();
            if (_stormTrackPlacesOverlayEl === panel) {
                _stormTrackPlacesOverlayEl = null;
            }
        });

        _stormTrackPlacesOverlayEl = panel;
        return panel;
    }

    function _renderStormTrackPlacesRows(rows) {
        const panel = _ensureStormTrackPlacesOverlay();
        if (!panel) return;
        const body = panel.querySelector('.wx-stormtrack-places-body');
        if (!body) return;

        if (!Array.isArray(rows) || !rows.length) {
            body.innerHTML = '<div class="wx-stormtrack-empty">No places inside the current projected polygon.</div>';
            return;
        }

        const knownTypes = new Set(_STORM_TRACK_PLACE_TYPES.map((t) => t.key));
        const visible = rows.filter((r) => !knownTypes.has(r.type) || _stormTrackPlaceTypeFilter.has(r.type));

        const filterBar = _STORM_TRACK_PLACE_TYPES.map((t) => {
            const active = _stormTrackPlaceTypeFilter.has(t.key);
            return `<button type="button" class="wx-stormtrack-filter${active ? ' is-active' : ''}" data-place-type="${t.key}" aria-pressed="${active}">${t.label}</button>`;
        }).join('');

        const listItems = visible.map((r) => {
            const state = r.state ? `, ${r.state}` : '';
            return [
                '<li>',
                `<span class="wx-stormtrack-place-name">${_escapeHtml(r.name)}${_escapeHtml(state)}</span>`,
                `<span class="wx-stormtrack-place-time">${_escapeHtml(r.arrivalLabel)}</span>`,
                '</li>',
            ].join('');
        }).join('');

        const listHtml = visible.length
            ? `<ol class="wx-stormtrack-places-list">${listItems}</ol>`
            : '<div class="wx-stormtrack-empty">No places match the selected types.</div>';
        body.innerHTML = `<div class="wx-stormtrack-filters">${filterBar}</div>${listHtml}`;

        body.querySelectorAll('.wx-stormtrack-filter').forEach((btn) => {
            btn.addEventListener('click', () => {
                const key = btn.getAttribute('data-place-type');
                if (!key) return;
                if (_stormTrackPlaceTypeFilter.has(key)) {
                    _stormTrackPlaceTypeFilter.delete(key);
                } else {
                    _stormTrackPlaceTypeFilter.add(key);
                }
                _renderStormTrackPlacesRows(_stormTrackPlaceRows);
            });
        });
    }

    async function _computeStormTrackPlaceRows(motion, activeBearing, minsAhead, corridorLatLngs) {
        const places = await _loadStormTrackPlacesData();
        const anchor = _stormTrackDragAnchor;
        if (!anchor || !Array.isArray(corridorLatLngs) || corridorLatLngs.length < 3) return [];

        const ring = corridorLatLngs.map((pt) => [pt.lng, pt.lat]);
        const nowMs = Date.now();
        const maxMins = Math.max(0, Number(minsAhead) || 0);
        const speedMps = Number(motion?.speedMps);
        if (!Number.isFinite(speedMps) || speedMps <= 0) return [];

        const rows = [];
        for (const place of places) {
            if (!_ringContainsPoint(ring, place.lng, place.lat)) continue;
            const meters = _projectMetersOnMotion(anchor, L.latLng(place.lat, place.lng), activeBearing);
            const mins = Math.max(0, meters / (speedMps * 60));
            if (mins > maxMins + 1e-6) continue;
            const arrivalMs = nowMs + (mins * 60_000);
            const tz = _stormTrackPlaceTimeZone(place);
            rows.push({
                name: place.name,
                state: place.state,
                arrivalMins: mins,
                arrivalLabel: `${_formatStormTrackArrivalMs(arrivalMs, tz)} (+${Math.round(mins)}m)`,
                population: place.population,
                type: place.type,
            });
        }

        rows.sort((a, b) => {
            const dt = a.arrivalMins - b.arrivalMins;
            if (Math.abs(dt) > 1e-6) return dt;
            const ap = Number.isFinite(a.population) ? a.population : -1;
            const bp = Number.isFinite(b.population) ? b.population : -1;
            return bp - ap;
        });

        return rows.slice(0, _STORM_TRACK_MAX_PLACE_ROWS);
    }

    function _scalePolylineFromCentroid(latLngs, scaleFactor) {
        if (!Array.isArray(latLngs) || latLngs.length < 2) return latLngs;
        const scale = Number(scaleFactor);
        if (!Number.isFinite(scale) || scale <= 0) return latLngs;
        if (Math.abs(scale - 1) < 1e-6) return latLngs.map((pt) => L.latLng(pt.lat, pt.lng));

        const centroid = _stormTrackAnchor(latLngs);
        if (!centroid) return latLngs;

        return latLngs.map((pt) => {
            const distanceMeters = centroid.distanceTo(pt);
            if (!Number.isFinite(distanceMeters) || distanceMeters <= 0) {
                return L.latLng(pt.lat, pt.lng);
            }
            const bearingDeg = _bearingBetweenLatLng(centroid, pt);
            return _offsetLatLngGeodesic(centroid, bearingDeg, distanceMeters * scale);
        });
    }

    function _clearStormTrackProjection() {
        _stormTrackProjectionLayer.clearLayers();
    }

    function _clearStormTrackLayer() {
        _stormTrackProjectionLayer.clearLayers();
        _stormTrackHandleLayer.clearLayers();
        _stormTrackDragHandle = null;
        _stormTrackDragAnchor = null;
        _stormTrackMotion = null;
        _stormTrackActiveBearingDeg = null;
        _stormTrackLastCorridorLatLngs = [];
        _stormTrackPlaceRows = [];
        if (_stormTrackPlacesOverlayEl) {
            _stormTrackPlacesOverlayEl.remove();
            _stormTrackPlacesOverlayEl = null;
        }
        if (_stormTrackOutlineLayer) {
            try { map.removeLayer(_stormTrackOutlineLayer); } catch (_) { /* ignore */ }
            _stormTrackOutlineLayer = null;
        }
    }

    function _setStormTrackDrawMode(enabled) {
        _stormTrackDrawMode = !!enabled;
        const startBtn = byId('wx-stormtrack-start');
        if (startBtn) startBtn.classList.toggle('is-active', _stormTrackDrawMode);
        const container = map?.getContainer?.();
        if (container) container.style.cursor = _stormTrackDrawMode ? 'crosshair' : '';
        if (_stormTrackDrawMode) {
            setStatus('Storm track draw mode: click map points, then click Finish Line.');
        }
    }

    function _renderStormTrackProjectionFromMinutes(aheadMinutes, bearingOverrideDeg = null) {
        if (_stormTrackBaseLatLngs.length < 2) {
            setStatus('Draw at least two points before projecting storm track.');
            return null;
        }
        const motion = _stormTrackMotion;
        if (!motion || !Number.isFinite(motion.speedMps) || motion.speedMps <= 0) {
            setStatus('No valid motion vector available for storm-track projection.');
            return null;
        }

        const basePts = _stormTrackBaseLatLngs.map((pt) => L.latLng(pt.lat, pt.lng));
        const minsAhead = Math.max(0, Number(aheadMinutes) || 0);
        const activeBearing = Number.isFinite(bearingOverrideDeg)
            ? _normalizeBearingDeg(bearingOverrideDeg)
            : (Number.isFinite(_stormTrackActiveBearingDeg)
                ? _normalizeBearingDeg(_stormTrackActiveBearingDeg)
                : _normalizeBearingDeg(motion.bearingDeg));
        _stormTrackActiveBearingDeg = activeBearing;
        const currentMeters = motion.speedMps * minsAhead * 60;
        const widthScaleNow = 1 + (_STORM_TRACK_WIDTH_GROWTH_PER_INTERVAL * (minsAhead / _STORM_TRACK_INTERVAL_MIN));
        const currentFrontRaw = basePts.map((pt) => _offsetLatLngGeodesic(pt, activeBearing, currentMeters));
        const currentFront = _scalePolylineFromCentroid(currentFrontRaw, widthScaleNow);
        const fadeSpanMins = Math.max(_STORM_TRACK_INTERVAL_MIN, minsAhead || _STORM_TRACK_INTERVAL_MIN);
        const nowFadeT = Math.max(0, Math.min(1, minsAhead / fadeSpanMins));
        const currentFrontOpacity = 0.99 - (0.75 * nowFadeT);
        const currentFrontFillOpacity = 0.50 - (0.18 * nowFadeT);

        _clearStormTrackProjection();
        let corridor = [];
        if (minsAhead > 0 && basePts.length >= 2 && currentFront.length === basePts.length) {
            corridor = [...basePts, ...[...currentFront].reverse()];
            L.polygon(corridor, {
                color: '#22e8ff',
                weight: 1,
                opacity: 0.5,
                fillColor: '#22e8ff',
                fillOpacity: Math.max(0.12, currentFrontFillOpacity),
                interactive: false,
            }).addTo(_stormTrackProjectionLayer);
        }
        L.polyline(basePts, {
            color: '#cbd5e1',
            weight: 1.5,
            opacity: 0.55,
            dashArray: '2 6',
        }).addTo(_stormTrackProjectionLayer);

        L.polyline(currentFront, {
            color: '#22e8ff',
            weight: 2.5,
            opacity: Math.max(0.35, currentFrontOpacity),
            dashArray: '9 6',
        }).addTo(_stormTrackProjectionLayer);

        if (minsAhead > 0) {
            const liveAnchor = currentFront[currentFront.length - 1];
            L.marker(liveAnchor, {
                interactive: false,
                icon: L.divIcon({
                    className: 'wx-stormtrack-label',
                    html: `+${Math.round(minsAhead)}m`,
                }),
            }).addTo(_stormTrackProjectionLayer);
        }

        const maxInterval = Math.floor(minsAhead / _STORM_TRACK_INTERVAL_MIN) * _STORM_TRACK_INTERVAL_MIN;
        for (let mins = _STORM_TRACK_INTERVAL_MIN; mins <= maxInterval; mins += _STORM_TRACK_INTERVAL_MIN) {
            const distanceMeters = motion.speedMps * mins * 60;
            const widthScale = 1 + (_STORM_TRACK_WIDTH_GROWTH_PER_INTERVAL * (mins / _STORM_TRACK_INTERVAL_MIN));
            const shiftedRaw = basePts.map((pt) => _offsetLatLngGeodesic(pt, activeBearing, distanceMeters));
            const shifted = _scalePolylineFromCentroid(shiftedRaw, widthScale);
            const fadeT = Math.max(0, Math.min(1, mins / fadeSpanMins));
            const shiftedOpacity = 0.92 - (0.55 * fadeT);
            L.polyline(shifted, {
                color: '#7dd3fc',
                weight: 2,
                opacity: Math.max(0.35, shiftedOpacity),
                dashArray: '7 7',
            }).addTo(_stormTrackProjectionLayer);
            const labelAnchor = shifted[shifted.length - 1];
            L.marker(labelAnchor, {
                interactive: false,
                icon: L.divIcon({
                    className: 'wx-stormtrack-label',
                    html: `+${mins}m`,
                }),
            }).addTo(_stormTrackProjectionLayer);
        }

        _stormTrackLastCorridorLatLngs = corridor;
        return {
            minsAhead,
            activeBearing,
            corridorLatLngs: corridor,
        };
    }

    function _installStormTrackDragHandle() {
        if (!_stormTrackDragAnchor) return;
        _stormTrackHandleLayer.clearLayers();
        const initialMinutes = _STORM_TRACK_INTERVAL_MIN;
        const initialMeters = _stormTrackMotion
            ? _stormTrackMotion.speedMps * initialMinutes * 60
            : 0;
        const initialPos = (_stormTrackMotion && initialMeters > 0)
            ? _offsetLatLngGeodesic(_stormTrackDragAnchor, _stormTrackMotion.bearingDeg, initialMeters)
            : _stormTrackDragAnchor;

        _stormTrackDragHandle = L.marker(initialPos, {
            draggable: true,
            keyboard: false,
            icon: L.divIcon({
                className: 'wx-stormtrack-drag-handle',
                html: '\u25c9',
                iconSize: [32, 32],
                iconAnchor: [16, 16],
            }),
        });
        _stormTrackDragHandle.addTo(_stormTrackHandleLayer);
        _stormTrackDragHandle.on('drag', (evt) => {
            if (!_stormTrackMotion || !_stormTrackDragAnchor) return;
            const handleLatLng = evt?.target?.getLatLng?.();
            if (!handleLatLng) return;
            const rawBearing = _bearingBetweenLatLng(_stormTrackDragAnchor, handleLatLng);
            const activeBearing = _pivotedBearingDeg(rawBearing);
            const meters = Math.max(0, _projectMetersOnMotion(_stormTrackDragAnchor, handleLatLng, activeBearing));
            const snappedLatLng = _offsetLatLngGeodesic(_stormTrackDragAnchor, activeBearing, meters);
            evt.target.setLatLng(snappedLatLng);
            const mins = meters / (_stormTrackMotion.speedMps * 60);
            _renderStormTrackProjectionFromMinutes(mins, activeBearing);
        });
        _stormTrackDragHandle.on('dragend', async (evt) => {
            if (!_stormTrackMotion || !_stormTrackDragAnchor) return;
            const handleLatLng = evt?.target?.getLatLng?.();
            if (!handleLatLng) return;
            const rawBearing = _bearingBetweenLatLng(_stormTrackDragAnchor, handleLatLng);
            const activeBearing = _pivotedBearingDeg(rawBearing);
            const meters = Math.max(0, _projectMetersOnMotion(_stormTrackDragAnchor, handleLatLng, activeBearing));
            const snappedLatLng = _offsetLatLngGeodesic(_stormTrackDragAnchor, activeBearing, meters);
            evt.target.setLatLng(snappedLatLng);
            const mins = meters / (_stormTrackMotion.speedMps * 60);
            const renderState = _renderStormTrackProjectionFromMinutes(mins, activeBearing);
            const baseBearing = _stormTrackMotion?.bearingDeg;
            const pivotDelta = Number.isFinite(baseBearing)
                ? Math.round(_signedBearingDeltaDeg(baseBearing, activeBearing))
                : 0;
            setStatus(`Storm-track projection updated to +${Math.round(mins)} minutes (pivot ${pivotDelta >= 0 ? '+' : ''}${pivotDelta}\u00b0).`);

            if (!renderState?.corridorLatLngs?.length) {
                _stormTrackPlaceRows = [];
                _renderStormTrackPlacesRows(_stormTrackPlaceRows);
                return;
            }
            const reqSeq = ++_stormTrackPlacesComputeSeq;
            setStatus(`Storm-track projection updated to +${Math.round(mins)} minutes (pivot ${pivotDelta >= 0 ? '+' : ''}${pivotDelta}deg). Computing place arrivals...`);
            try {
                const rows = await _computeStormTrackPlaceRows(_stormTrackMotion, activeBearing, mins, renderState.corridorLatLngs);
                if (reqSeq !== _stormTrackPlacesComputeSeq) return;
                _stormTrackPlaceRows = rows;
                _renderStormTrackPlacesRows(rows);
                setStatus(`Storm-track projection updated to +${Math.round(mins)} minutes (pivot ${pivotDelta >= 0 ? '+' : ''}${pivotDelta}deg). ${rows.length} place${rows.length === 1 ? '' : 's'} listed.`);
            } catch (err) {
                if (reqSeq !== _stormTrackPlacesComputeSeq) return;
                _stormTrackPlaceRows = [];
                _renderStormTrackPlacesRows(_stormTrackPlaceRows);
                const msg = String(err?.message || err || 'unknown error');
                setStatus(`Place arrival computation failed: ${msg}`);
            }
        });
    }

    function _activateStormTrackDragProjection() {
        if (_stormTrackBaseLatLngs.length < 2) {
            setStatus('Draw at least two points before finishing storm track.');
            return;
        }
        const alertFeat = _stormTrackFallbackAlert();
        const motion = _extractAlertMotion(alertFeat);
        if (!motion) {
            setStatus('No motion vector found on the selected alert. Open an alert detail first, then try again.');
            return;
        }

        // Apply manual speed override if the field has a valid value.
        const overrideKt = parseFloat(byId('wx-speed-override')?.value || '');
        if (Number.isFinite(overrideKt) && overrideKt > 0) {
            motion.speedMps = overrideKt * 0.514444;
        }

        _stormTrackMotion = motion;
        _stormTrackActiveBearingDeg = motion.bearingDeg;
        _stormTrackDragAnchor = _stormTrackAnchor(_stormTrackBaseLatLngs);
        _renderStormTrackProjectionFromMinutes(_STORM_TRACK_INTERVAL_MIN);
        _installStormTrackDragHandle();

        // Draw cyan selection outline on the alert polygon being used.
        if (_stormTrackOutlineLayer) {
            try { map.removeLayer(_stormTrackOutlineLayer); } catch (_) { /* ignore */ }
            _stormTrackOutlineLayer = null;
        }
        if (alertFeat?.geometry) {
            try {
                _stormTrackOutlineLayer = L.geoJSON({ type: 'Feature', geometry: alertFeat.geometry }, {
                    style: { color: '#22e8ff', weight: 3, opacity: 0.9, fillOpacity: 0 },
                    interactive: false,
                }).addTo(map);
            } catch (_) { /* ignore malformed geometry */ }
        }

        const evt = String(alertFeat?.properties?.event || 'alert');
        const speedNote = (Number.isFinite(overrideKt) && overrideKt > 0)
            ? ` [speed override: ${Math.round(overrideKt)} kt]` : '';
        setStatus(`Drag the marker forward to project ${evt} at ${_STORM_TRACK_INTERVAL_MIN}-minute intervals (${motion.source}).${speedNote} Hold Shift to pivot up to \u00b1${_STORM_TRACK_PIVOT_MAX_DEG}\u00b0.`);
    }

    // ── Radar Speed Calibrator helpers ────────────────────────────────────────

    function _clearSpeedOverride() {
        const input = byId('wx-speed-override');
        if (input) input.value = '';
        const resultEl = byId('wx-radarcal-result');
        if (resultEl) resultEl.textContent = '';
    }

    function _setRadarCalDrawMode(active) {
        _radarCalDrawMode = active;
        const startBtn = byId('wx-radarcal-start');
        if (startBtn) startBtn.classList.toggle('is-active', active);
        map.getContainer().style.cursor = active ? 'crosshair' : '';
    }

    function _clearRadarCalLine() {
        if (_radarCalLayer) {
            try { map.removeLayer(_radarCalLayer); } catch (_) { /* ignore */ }
            _radarCalLayer = null;
        }
        _radarCalLatLngs = [];
        const resultEl = byId('wx-radarcal-result');
        if (resultEl) resultEl.textContent = '';
    }

    function _renderRadarCalLine() {
        if (_radarCalLayer) {
            try { map.removeLayer(_radarCalLayer); } catch (_) { /* ignore */ }
            _radarCalLayer = null;
        }
        if (!_radarCalLatLngs.length) return;
        const layers = [];
        layers.push(L.circleMarker(_radarCalLatLngs[0], {
            radius: 5, color: '#facc15', fillColor: '#facc15', fillOpacity: 1, weight: 1, interactive: false,
        }));
        if (_radarCalLatLngs.length >= 2) {
            layers.push(L.polyline(_radarCalLatLngs, {
                color: '#facc15', weight: 2.5, opacity: 0.9, dashArray: '6 4', interactive: false,
            }));
            layers.push(L.circleMarker(_radarCalLatLngs[_radarCalLatLngs.length - 1], {
                radius: 5, color: '#facc15', fillColor: '#facc15', fillOpacity: 1, weight: 1, interactive: false,
            }));
            _computeRadarCalSpeed();
        }
        _radarCalLayer = L.layerGroup(layers).addTo(map);
    }

    function _computeRadarCalSpeed() {
        if (_radarCalLatLngs.length < 2) return;
        const p1 = _radarCalLatLngs[0];
        const p2 = _radarCalLatLngs[_radarCalLatLngs.length - 1];
        const distKm = _haversineKm(p1.lat, p1.lng, p2.lat, p2.lng);
        const loopMinutes = _RADAR_OVERLAY_FRAMES * _RADAR_OVERLAY_STEP_MIN;
        if (loopMinutes <= 0 || distKm <= 0) return;
        const speedKmh = distKm / (loopMinutes / 60);
        const speedKt = speedKmh / 1.852;
        const rounded = Math.round(speedKt);

        const input = byId('wx-speed-override');
        if (input) input.value = String(rounded);

        const resultEl = byId('wx-radarcal-result');
        if (resultEl) resultEl.textContent = `Est. ${rounded} kt (${Math.round(speedKmh)} km/h) over ${loopMinutes} min`;

        setStatus(`Radar speed estimate: ${rounded} kt — auto-filled speed override. Use Finish Line to project.`);
    }

    // ── Colorbar helpers ─────────────────────────────────────────────────────
    function setLegend(html) {
        const box = byId('weather-colorbar');
        if (!box) return;
        if (!html) {
            box.style.display = 'none';
            box.innerHTML = '';
            return;
        }
        box.style.display = '';
        box.innerHTML = html;
    }


    function swatch(color, label, swatchModifier = '') {
        const modifier = swatchModifier ? ` ${swatchModifier}` : '';
        return `<div class="legend-item"><span class="legend-swatch${modifier}" style="background:${color}"></span><span class="legend-text">${label}</span></div>`;
    }

    function escapeHtml(value) {
        return String(value ?? '')
            .replaceAll('&', '&amp;')
            .replaceAll('<', '&lt;')
            .replaceAll('>', '&gt;')
            .replaceAll('"', '&quot;')
            .replaceAll("'", '&#39;');
    }

    function renderInterpretiveLegend(title, items) {
        const rows = (Array.isArray(items) ? items : [])
            .filter((item) => item?.color && item?.label)
            .map((item) => swatch(item.color, escapeHtml(item.label)))
            .join('');
        if (!rows) return '';
        return `<h4 class="legend-title">${escapeHtml(title)}</h4><div class="legend-flow">${rows}</div>`;
    }

    // Center-of-map "no data" overlay used when an SPC (or similar) layer
    // has no visible features for the current selection.
    function setMapEmptyMessage(msg) {
        const overlay = byId('weather-map-empty-overlay');
        const textEl = byId('weather-map-empty-message');
        if (!overlay || !textEl) return;
        if (msg) {
            textEl.textContent = msg;
            overlay.hidden = false;
        } else {
            textEl.textContent = '';
            overlay.hidden = true;
        }
    }


    // ── Data loaders ─────────────────────────────────────────────────────────
    function setStatus(msg) {
        const el = byId('weather-map-status');
        if (el) el.textContent = msg;
    }

    // ── Reliability bar (Last Update / Data Age / Source) ────────────────────
    const _reliabilityByType = {
        global: { ts: null, source: null, label: null },
        spc: { ts: null, source: null, label: null },
        surface: { ts: null, source: null, label: null },
        rtma: { ts: null, source: null, label: null },
        mrms: { ts: null, source: null, label: null },
        drought: { ts: null, source: null, label: null },
        tropical: { ts: null, source: null, label: null },
        wpc: { ts: null, source: null, label: null },
        satellite: { ts: null, source: null, label: null },
    };
    const _timestampSourceByType = {
        global: { provenance: null, ts: null },
        spc: { provenance: null, ts: null },
        surface: { provenance: null, ts: null },
        rtma: { provenance: null, ts: null },
        mrms: { provenance: null, ts: null },
        drought: { provenance: null, ts: null },
        tropical: { provenance: null, ts: null },
        wpc: { provenance: null, ts: null },
        satellite: { provenance: null, ts: null },
    };
    let _reliabilityTickerStarted = false;
    const _LIVE_DATA_STALE_MS = 90 * 60 * 1000;

    function _formatAge(ms) {
        if (ms == null || !isFinite(ms) || ms < 0) return '—';
        const s = Math.floor(ms / 1000);
        if (s < 60) return `${s}s ago`;
        const m = Math.floor(s / 60);
        if (m < 60) return `${m}m ${s % 60}s ago`;
        const h = Math.floor(m / 60);
        if (h < 24) return `${h}h ${m % 60}m ago`;
        const d = Math.floor(h / 24);
        return `${d}d ${h % 24}h ago`;
    }

    function _activeReliabilityType() {
        if (_isTypeEnabled('drought')) return 'drought';
        if (_isTypeEnabled('tropical')) return 'tropical';
        return 'global';
    }

    function _currentReliabilityEntry() {
        const activeType = _activeReliabilityType();
        return _reliabilityByType[activeType] || _reliabilityByType.global;
    }

    function _renderReliability() {
        const updEl = byId('wx-reliability-updated');
        const ageEl = byId('wx-reliability-age');
        const provEl = byId('wx-reliability-provider');
        const srcEl = byId('wx-reliability-source');
        const entry = _currentReliabilityEntry();
        const activeType = _activeReliabilityType();
        const tsEntry = _timestampSourceByType[activeType] || _timestampSourceByType.global;
        if (updEl) updEl.textContent = Number.isFinite(entry.ts) ? new Date(entry.ts).toLocaleTimeString() : '—';
        // Archive best-track storms can be a century old, so "Age" reads absurd —
        // show the storm's own date range instead while an archive storm is active.
        const archiveAge = (_tropicalArchiveReliabilityLabel && activeType === 'tropical')
            ? _tropicalArchiveReliabilityLabel : null;
        if (ageEl) {
            ageEl.textContent = archiveAge
                || (Number.isFinite(entry.ts) ? _formatAge(Date.now() - entry.ts) : '—');
        }
        if (provEl) provEl.textContent = entry.source || '—';
        if (srcEl) srcEl.textContent = tsEntry.provenance || '—';
    }

    // Accepts epoch ms (number or numeric string) or a date string (ISO/RSS); returns
    // epoch ms or null. Number-first preserves existing callers that pass ms.
    function _toReliabilityTsMs(value) {
        if (value == null) return null;
        const n = Number(value);
        if (Number.isFinite(n)) return n;
        const d = _asDate(value);
        return d ? d.getTime() : null;
    }

    function _setTimestampSource(type, provenance, ts) {
        const key = (type && _timestampSourceByType[type]) ? type : 'global';
        _timestampSourceByType[key].provenance = provenance || null;
        _timestampSourceByType[key].ts = _toReliabilityTsMs(ts);
        _renderReliability();
    }

    function _setReliability(type, label, source, ts) {
        let targetType = type;
        let targetLabel = label;
        let targetSource = source;
        let targetTs = ts;

        // Backward compatibility: _setReliability(label, source, ts)
        if (arguments.length === 3) {
            targetType = 'global';
            targetLabel = type;
            targetSource = label;
            targetTs = source;
        }

        const key = (targetType && _reliabilityByType[targetType]) ? targetType : 'global';
        _reliabilityByType[key].label = targetLabel || null;
        _reliabilityByType[key].source = targetSource || null;
        _reliabilityByType[key].ts = _toReliabilityTsMs(targetTs);
        _renderReliability();
    }

    function _resolveDataTimestampMs(rawTs) {
        const tsMs = _asDate(rawTs)?.getTime();
        return Number.isFinite(tsMs) ? tsMs : null;
    }

    function _formatValidTimeLabel(tsMs) {
        return Number.isFinite(tsMs) ? new Date(tsMs).toLocaleTimeString() : 'unknown time';
    }

    function _staleNoteForTimestamp(tsMs, thresholdMs = _LIVE_DATA_STALE_MS) {
        if (!Number.isFinite(tsMs)) return '';
        const ageMs = Date.now() - tsMs;
        return ageMs > thresholdMs ? ` [stale: ${_formatAge(ageMs)}]` : '';
    }

    function _startReliabilityTicker() {
        if (_reliabilityTickerStarted) return;
        _reliabilityTickerStarted = true;
        _renderReliability();
        setInterval(_renderReliability, 5000);
    }

    // ── Region → fitBounds ───────────────────────────────────────────────────
    function fitRegion(code, options = {}) {
        const regionCode = (code || 'CONUS').toUpperCase();
        const b = regionCode === 'CONUS'
            ? CONUS_DEFAULT_BOUNDS
            : regionCode === 'WORLD'
                ? WORLD_DEFAULT_BOUNDS
                : leafletBounds(regionCode);
        if (b) {
            map.fitBounds(b, {
                paddingTopLeft: [0, 0],
                paddingBottomRight: [0, REGION_FIT_BOTTOM_PADDING_PX],
                animate: options.animate !== undefined ? !!options.animate : true,
            });
        }
    }

    function fitTropicalDefaultExtent() {
        map.setView(TROPICAL_DEFAULT_CENTER, TROPICAL_DEFAULT_ZOOM, {
            animate: false,
        });
    }

    async function _loadUserSettingsDefaults() {
        try {
            const res = await fetch(USER_SETTINGS_DEFAULTS_URL, { cache: 'no-store' });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const payload = await res.json();
            _userSettingsDefaults = payload && typeof payload === 'object' ? payload : null;
        } catch (err) {
            console.warn('[settings] Default user settings unavailable; using built-in startup defaults.', err);
            _userSettingsDefaults = null;
        }
        return _userSettingsDefaults;
    }

    function _currentSettingsPageKey() {
        if (_standaloneProductType === 'current') return 'surface';
        return _standaloneProductType || 'main';
    }

    function _configuredInitialMapView() {
        const pageKey = _currentSettingsPageKey();
        const pageView = _userSettingsDefaults?.pages?.[pageKey]?.mapView;
        const globalView = _userSettingsDefaults?.global?.homeRegion;
        return String(pageView || globalView || 'NC').trim().toUpperCase();
    }

    function _configuredPageAutoLoad() {
        const pageKey = _currentSettingsPageKey();
        const pageConfig = _userSettingsDefaults?.pages?.[pageKey];
        if (pageConfig && Object.prototype.hasOwnProperty.call(pageConfig, 'autoLoad')) {
            return pageConfig.autoLoad !== false;
        }
        return true;
    }

    function _configuredPageAutoLoadCatalog() {
        const pageKey = _currentSettingsPageKey();
        return _userSettingsDefaults?.pages?.[pageKey]?.autoLoadCatalog === true;
    }

    function _configuredTropicalBasin() {
        const basin = _userSettingsDefaults?.pages?.tropical?.basin;
        return String(basin || 'AL').trim().toUpperCase();
    }

    function _armProductRendering() {
        _productRenderArmed = true;
    }

    function _applyConfiguredTropicalBasin() {
        const basinSelect = byId('weather-tropical-basin');
        if (!basinSelect) return;
        const basin = _configuredTropicalBasin();
        const hasOption = Array.from(basinSelect.options || []).some((option) => option.value === basin);
        if (hasOption) basinSelect.value = basin;
    }

    function _applyInitialMapView() {
        const mapView = _configuredInitialMapView();
        if (_isTypeEnabled('tropical') || mapView === 'TROPICAL') {
            if (_activeTropicalBasin() !== 'WORLD') {
                _fitTropicalBasinExtent();
            } else {
                fitTropicalDefaultExtent();
            }
            return;
        }

        const regionSelect = byId('weather-region');
        const hasRegionOption = !!Array.from(regionSelect?.options || [])
            .find((option) => option.value === mapView);
        if (hasRegionOption) {
            regionSelect.value = mapView;
        }
        fitRegion(mapView || regionSelect?.value || 'CONUS', { animate: false });
    }

    function _fitTropicalBasinExtent() {
        const basin = _activeTropicalBasin();
        const configs = {
            AL: { bounds: [[-5, -125], [70, 0]], zoom: 5 },              // Atlantic: 0W to 125W, -5N to 70N
            EP: { bounds: [[0, -165], [60, -80]], zoom: 5 },             // Eastern Pacific: 80W to 165W, 0N to 60N
            CP: { bounds: [[0, -180], [45, -125]], zoom: 4 },            // Central Pacific: 125W to 180W, 0N to 45N
        }[basin];
        _setTropicalMapViewMode('both');
        _closeOutlookDetail();
        _closeTropicalDetail();
        if (configs) {
            const bounds = L.latLngBounds(configs.bounds);
            const center = bounds.getCenter();
            map.setView(center, configs.zoom, { animate: false });
        } else {
            fitTropicalDefaultExtent();
        }
    }

    function _setActiveWeatherType(type) {
        const target = byId(`weather-type-${type}`);
        if (!target) return;
        if (target.checked) return;
        target.checked = true;
        target.dispatchEvent(new Event('change'));
    }

    // ── Top type controls and product visibility ─────────────────────────────
    function _isTypeEnabled(type) {
        return !!byId(`weather-type-${type}`)?.checked;
    }

    function _invalidateMapSizeSoon() {
        requestAnimationFrame(() => {
            if (map && typeof map.invalidateSize === 'function') {
                map.invalidateSize();
            }
        });
    }

    function _updateTypeSections() {
        ['current', 'alerts', 'radar', 'satellite', 'spc', 'rtma', 'mrms', 'drought', 'tropical', 'wpc', 'water'].forEach((type) => {
            const section = byId(`wx-section-${type}`);
            if (section) section.style.display = _isTypeEnabled(type) ? '' : 'none';
        });
        const regionBlock = byId('wx-region-block');
        if (regionBlock) regionBlock.style.display = _isTypeEnabled('tropical') ? 'none' : '';
        const modeControls = byId('wx-mode-controls');
        if (modeControls) modeControls.style.display = _isTypeEnabled('satellite') ? 'none' : '';
        _updateActiveTabName();
        _invalidateMapSizeSoon();
    }

    const _TAB_TYPE_LABELS = {
        current: 'Current',
        alerts: 'Alerts',
        radar: 'Radar',
        satellite: 'Satellite',
        spc: 'SPC',
        rtma: 'RTMA',
        mrms: 'MRMS',
        drought: 'Drought',
        tropical: 'Tropical',
        wpc: 'WPC',
        water: 'Water',
    };

    function _updateActiveTabName() {
        const el = byId('wx-active-tab-name');
        if (!el) return;
        const active = Object.keys(_TAB_TYPE_LABELS).filter((t) => _isTypeEnabled(t));
        el.textContent = active.length
            ? active.map((t) => _TAB_TYPE_LABELS[t]).join(' + ')
            : 'No Layers';
    }

    function _updateRightSidebarGroups() {
        const groups = ['current', 'alerts', 'spc', 'mrms', 'rtma', 'drought', 'wpc'];
        let anyVisible = false;
        groups.forEach((type) => {
            const panel = byId(`wx-side-group-${type}`);
            if (!panel) return;
            const show = _isTypeEnabled(type);
            panel.style.display = show ? '' : 'none';
            if (show) anyVisible = true;
        });
        const empty = byId('wx-side-groups-empty');
        // Tropical has no per-type product group, but the always-present map-layers
        // controls apply, so don't show the "enable a product group" hint for it.
        if (empty) empty.style.display = (anyVisible || _isTypeEnabled('tropical')) ? 'none' : '';
        _updateRightTabsAvailability();
    }

    function _updateSubOptionVisibility() {
        const surfaceOpts = byId('weather-surface-opts');
        if (surfaceOpts) surfaceOpts.style.display = '';
    }

    function _wireRightSidebarTabs() {
        const tabs = document.querySelectorAll('.wx-right-tab[data-right-tab]');
        const panes = {
            layers: byId('wx-right-pane-layers'),
            styling: byId('wx-right-pane-styling'),
            system: byId('wx-right-pane-system'),
        };
        tabs.forEach((btn) => {
            btn.addEventListener('click', () => {
                if (btn.hidden) return;
                const target = btn.getAttribute('data-right-tab');
                if (target === 'layers') {
                    const wasArchive = _tropicalArchiveContext;
                    _exitTropicalArchiveContext();
                    if (wasArchive) _exitArchiveToLiveView();
                }
                tabs.forEach((candidate) => {
                    const active = candidate === btn;
                    candidate.classList.toggle('is-active', active);
                    candidate.setAttribute('aria-selected', active ? 'true' : 'false');
                });
                Object.entries(panes).forEach(([key, pane]) => {
                    if (!pane) return;
                    const active = key === target;
                    pane.hidden = !active;
                    pane.classList.toggle('is-active', active);
                });
            });
        });
    }

    function _updateRightTabsAvailability() {
        const tropicalOn = _isTypeEnabled('tropical');
        const styleModeOn = _isTypeEnabled('current') || _isTypeEnabled('spc');
        const styleBtn = byId('wx-right-tab-btn-styling');
        const systemBtn = byId('wx-right-tab-btn-system');
        const showSystem = tropicalOn && _tropicalMapViewMode === 'system';
        const showStyle = !tropicalOn && styleModeOn;
        if (systemBtn) systemBtn.hidden = !showSystem;
        if (styleBtn) styleBtn.hidden = !showStyle;

        const tabs = [
            { btn: byId('wx-right-tab-btn-layers'), pane: byId('wx-right-pane-layers'), key: 'layers' },
            { btn: styleBtn, pane: byId('wx-right-pane-styling'), key: 'styling' },
            { btn: systemBtn, pane: byId('wx-right-pane-system'), key: 'system' },
        ];
        const active = tabs.find((item) => item.btn?.classList.contains('is-active'));
        if (!active || active.btn.hidden) {
            const fallbackKey = showSystem ? 'system' : 'layers';
            tabs.forEach((item) => {
                if (!item.btn || !item.pane) return;
                const selected = item.key === fallbackKey;
                item.btn.classList.toggle('is-active', selected);
                item.btn.setAttribute('aria-selected', selected ? 'true' : 'false');
                item.pane.hidden = !selected;
                item.pane.classList.toggle('is-active', selected);
            });
        }
    }


    function _clearAllMapLayers() {

        if (waterLayer && map.hasLayer(waterLayer)) map.removeLayer(waterLayer);
        _tropicalEngine?.clearLayer?.();
        if (tropicalOutlookLayer && map.hasLayer(tropicalOutlookLayer)) map.removeLayer(tropicalOutlookLayer);
        waterLayer = null;
        tropicalOutlookLayer = null;
        _waterStations = [];
        _waterSelectedSiteId = '';
        _activeTropicalStorm = null;
        _tropicalArchiveSelectedId = null;
        _tropicalArchiveReliabilityLabel = null;
        _tropicalPageController?.resetArchiveScrubber?.();
        _tropicalArchiveStormBase = null;
        _hideTropicalFloater();
        _setTropicalDetailSectionsVisible(true);
        _exitTropicalArchiveContext();
        _closeTropicalDetail();
        setLegend(null);
    }


    function _resetTransientInteractiveUiForTabChange() {
        // Clear storm-track artifacts and state when changing weather tabs.
        _setStormTrackDrawMode(false);
        _stormTrackBaseLatLngs = [];
        _clearStormTrackLayer();

        // Clear radar speed calibrator line/state; this does not affect radar imagery.
        _setRadarCalDrawMode(false);
        _clearRadarCalLine();
        _clearSpeedOverride();
    }

    function _resetTabControlsToDefaults(type, options = {}) {
        if (!type) return;

        const section = byId(`wx-section-${type}`);
        if (!section) return;

        const controls = section.querySelectorAll('input, select, textarea');
        controls.forEach((el) => {
            let changed = false;
            if (el.tagName === 'SELECT') {
                const opts = Array.from(el.options || []);
                const defaultOpt = opts.find((opt) => opt.defaultSelected) || opts[0];
                const defaultValue = defaultOpt ? defaultOpt.value : '';
                if (el.value !== defaultValue) {
                    el.value = defaultValue;
                    changed = true;
                }
            } else if (el.tagName === 'TEXTAREA') {
                if (el.value !== el.defaultValue) {
                    el.value = el.defaultValue;
                    changed = true;
                }
            } else if (el.tagName === 'INPUT') {
                const inputType = String(el.type || '').toLowerCase();
                if (inputType === 'checkbox' || inputType === 'radio') {
                    if (el.checked !== el.defaultChecked) {
                        el.checked = el.defaultChecked;
                        changed = true;
                    }
                } else if (el.value !== el.defaultValue) {
                    el.value = el.defaultValue;
                    changed = true;
                }
            }

            if (changed && !options.silent) {
                if (el.tagName === 'INPUT' && String(el.type || '').toLowerCase() === 'range') {
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                }
                el.dispatchEvent(new Event('change', { bubbles: true }));
            }
        });
    }

    // Tracks the currently active tab type so we know what to clean up on switch.
    // Initialized lazily on first use by detecting the currently-checked tab.
    let _activeTabType = null;
    function _detectInitialActiveTabType() {
        const candidates = ['current', 'alerts', 'radar', 'satellite', 'spc', 'rtma', 'mrms', 'drought', 'tropical', 'wpc', 'water'];
        for (const t of candidates) {
            if (byId(`weather-type-${t}`)?.checked) return t;
        }
        return null;
    }

    // Halts all timers, cancels in-flight requests, removes overlays, and clears
    // frame arrays for the given tab type. Called when switching away from a tab.
    function _cleanupPreviousTabState(prevType) {
        if (!prevType) return;

        switch (prevType) {

            case 'water':
                _clearWaterLayer();
                setMapEmptyMessage(null);
                break;

            case 'tropical':
                _tropicalRequestSeq += 1;
                _clearTropicalLayer();
                _clearTropicalOutlookLayer();
                _closeOutlookDetail();
                _closeTropicalDetail();
                _activeTropicalStorm = null;
                _tropicalMapViewMode = 'both';
                _tropicalArchiveSelectedId = null;
                _tropicalArchiveReliabilityLabel = null;
                _tropicalPageController?.resetArchiveScrubber?.();
                _tropicalArchiveStormBase = null;
                _hideTropicalFloater();
                _setTropicalDetailSectionsVisible(true);
                _exitTropicalArchiveContext();
                break;
        }
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
        _waterSelectedSiteId = '';
        const detail = byId('weather-water-detail');
        if (detail) {
            detail.hidden = true;
            detail.innerHTML = '';
        }
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

    function _waterLegendHtml() {
        const rows = [
            ['Major', 'major'],
            ['Moderate ', 'moderate'],
            ['Minor', 'minor'],
            ['Action Stage', 'action'],
            ['No Flood / Unknown', 'normal'],
            ['Coastal Gauge', 'coastal'],
            ['NDBC Buoy', 'buoy'],
        ].map(([label, status]) => {
            const style = _waterMarkerStyle(status);
            const shadow = status === 'coastal'
                ? 'box-shadow:0 0 0 1px #0f766e;'
                : status === 'buoy'
                ? 'box-shadow:0 0 0 1px #1d4ed8;'
                : '';
            return `<div class="legend-item"><span class="legend-swatch" style="background:${style.fill};border-color:${style.stroke};border-radius:50%;${shadow}"></span><span class="legend-text">${label}</span></div>`;
        }).join('');
        return `<h4 class="legend-title">River/Coastal/NDBC</h4><div class="legend-flow">${rows}</div>`;
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

    function _waterStationPopupHtml(station) {
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
        return `<div class="wx-storm-popup wx-water-popup">`
            + `<div class="wx-storm-popup-title">${_escapeHtml(station.name || station.site_id)}</div>`
            + `<dl class="wx-storm-popup-grid">${rows}</dl>`
            + (!isBuoy && !isCoastal ? _waterStageGaugeHtml(station) : '')
            + (isBuoy ? _waterBuoyCardHtml(station) : '')
            + _waterPopupHydrograph(station)
            + `</div>`;
    }

    async function _loadWaterStationDetail(siteId, marker) {
        if (!marker) return;
        const requestSeq = ++_waterDetailRequestSeq;
        marker.bindPopup('<div class="wx-storm-popup wx-water-popup"><div class="wx-storm-popup-title">Loading gauge...</div></div>');
        marker.openPopup();
        try {
            const resp = await fetch(apiUrl(`/api/water/stations/${encodeURIComponent(siteId)}`), { cache: 'no-store' });
            if (requestSeq !== _waterDetailRequestSeq || !_isTypeEnabled('water')) return;
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json();
            if (data?.station) {
                _waterSelectedSiteId = siteId;
                marker.setPopupContent(_waterStationPopupHtml(data.station));
                marker.openPopup();
            }
        } catch (err) {
            if (requestSeq !== _waterDetailRequestSeq) return;
            _setWaterStatus(`Water station unavailable: ${err.message}`);
            marker.setPopupContent(`<div class="wx-storm-popup wx-water-popup"><div class="wx-storm-popup-title">Gauge unavailable</div><dl class="wx-storm-popup-grid"><dt>Error</dt><dd>${_escapeHtml(err.message)}</dd></dl></div>`);
            marker.openPopup();
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
            marker.bindPopup(_waterStationPopupHtml(station));
            marker.on('click', () => _loadWaterStationDetail(station.site_id, marker));
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
            const cachePrefix = data?.cache === 'empty' ? 'Cache warming: ' : '';
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

    function refreshActiveLayers(options = {}) {
        if (options.startup) {
            if (!_productRenderArmed) return;
        } else {
            _productRenderArmed = true;
        }
        const waterEnabled = _isTypeEnabled('water');
        const tropicalEnabled = _isTypeEnabled('tropical');

        // Clear legend at the start to ensure old legend doesn't persist when switching products
        setLegend(null);

        if (!waterEnabled && waterLayer && map.hasLayer(waterLayer)) {
            map.removeLayer(waterLayer);
        }
        if (!tropicalEnabled) {
            _clearTropicalLayer();
            _closeOutlookDetail();
            _closeTropicalDetail();
        }

        if (waterEnabled) {
            setLegend(_waterLegendHtml());
            _loadWaterStations();
        }
        if (tropicalEnabled) {
            _tropicalEngine?.loadStorms();
            _tropicalEngine?.loadArchiveCatalog();
            _renderTropicalOutlookLegend();
        }
    }

    // ── Tropical Cyclones ───────────────────────────────────────────────────
    function _setTropicalStatus(message) {
        const el = byId('weather-tropical-status');
        if (el) el.textContent = message || '';
    }

    function _activeTropicalBasin() {
        return String(byId('weather-tropical-basin')?.value || 'WORLD').toUpperCase();
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
        // Jump to the System tab so the selected storm's details are immediately visible.
        // The tab handler no-ops when the button is hidden (i.e. Tropical not active).
        byId('wx-right-tab-btn-system')?.click();
    }

    function _setTropicalLeftTab(tabKey = 'outlooks') {
        const buttons = Array.from(document.querySelectorAll('.wx-tropical-tab[data-tropical-tab]'));
        const panels = Array.from(document.querySelectorAll('.wx-tropical-tab-panel'));
        if (!buttons.length || !panels.length) return;

        const selectedKey = buttons.some((button) => button.dataset.tropicalTab === tabKey)
            ? tabKey
            : 'outlooks';

        buttons.forEach((button) => {
            const isSelected = button.dataset.tropicalTab === selectedKey;
            button.setAttribute('aria-selected', isSelected ? 'true' : 'false');
            button.tabIndex = isSelected ? 0 : -1;
        });

        panels.forEach((panel) => {
            panel.hidden = panel.id !== `wx-tropical-panel-${selectedKey}`;
        });
    }

    function _wireTropicalLeftTabs() {
        const buttons = Array.from(document.querySelectorAll('.wx-tropical-tab[data-tropical-tab]'));
        if (!buttons.length) return;

        buttons.forEach((button, index) => {
            button.addEventListener('click', () => {
                _setTropicalLeftTab(button.dataset.tropicalTab || 'outlooks');
            });
            button.addEventListener('keydown', (event) => {
                if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
                event.preventDefault();

                let nextIndex = index;
                if (event.key === 'ArrowLeft') nextIndex = index === 0 ? buttons.length - 1 : index - 1;
                if (event.key === 'ArrowRight') nextIndex = index === buttons.length - 1 ? 0 : index + 1;
                if (event.key === 'Home') nextIndex = 0;
                if (event.key === 'End') nextIndex = buttons.length - 1;

                const nextButton = buttons[nextIndex];
                if (!nextButton) return;
                _setTropicalLeftTab(nextButton.dataset.tropicalTab || 'outlooks');
                nextButton.focus();
            });
        });

        _setTropicalLeftTab('outlooks');
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
                    Tropical outlook data could not be loaded for the selected basin.
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
        const basin = _activeTropicalBasin();
        const basins = basin === 'WORLD' ? ['AL', 'EP', 'CP'] : [basin];
        try {
            const payloads = await Promise.all(basins.map(async (basinId) => {
                const resp = await fetch(apiUrl(`/api/tropical/basin/${encodeURIComponent(basinId)}/feeds`), { cache: 'no-store' });
                if (!resp.ok) throw new Error(`${basinId} HTTP ${resp.status}`);
                return resp.json();
            }));
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
            tropicalOutlookLayer = group.addTo(map);
            // Patterns are injected + assigned now that each polygon path exists in the SVG.
            _applyTropicalOutlookHatching(group);
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

        // The System tab is only available in storm-selected (system) view; hide it
        // otherwise (the availability helper falls back to the Layers tab).
        _updateRightTabsAvailability();
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
        // Deselect any active storm: clear its System tab content. _setTropicalMapViewMode
        // hides the System tab and the availability fallback returns focus to the Layers tab.
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
        setLegend('<h4 class="legend-title">Tropical Cyclone Intensity</h4><div class="legend-flow">' + items + '</div>');
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
        setLegend('<h4 class="legend-title">7-Day Cyclone Formation Chance</h4>'
            + '<div class="legend-flow">' + chance + notExpected + '</div>');
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
        setLegend('<h4 class="legend-title">Peak Storm Surge Forecast</h4><div class="legend-flow">' + rows + '</div>');
    }

    function _renderWatchesWarningsLegend() {
        const events = [
            ['#DC143C', 'Hurricane Warning'],
            ['#FF00FF', 'Hurricane Watch'],
            ['#B22222', 'Tropical Storm Warning'],
            ['#F08080', 'Tropical Storm Watch'],
        ];
        const rows = events.map(([color, label]) => swatch(color, escapeHtml(label), 'is-wide')).join('');
        setLegend('<h4 class="legend-title">Watches & Warnings</h4><div class="legend-flow">' + rows + '</div>');
    }

    function _renderWindRadiiLegend() {
        const radii = [
            ['#1c54ff', '34 kt (Tropical Depression)'],
            ['#6cc343', '50 kt (Tropical Storm)'],
            ['#ffc309', '64 kt (Category 1)'],
        ];
        const rows = radii.map(([color, label]) => swatch(color, escapeHtml(label), 'is-wide')).join('');
        setLegend('<h4 class="legend-title">Wind Radii</h4><div class="legend-flow">' + rows + '</div>');
    }

    function _renderInitialWindExtentLegend() {
        const windFields = [
            ['#facc15', '34 kt wind extent'],
            ['#fb923c', '50 kt wind extent'],
            ['#ef4444', '64 kt wind extent'],
        ];
        const rows = windFields.map(([color, label]) => swatch(color, escapeHtml(label), 'is-wide')).join('');
        setLegend('<h4 class="legend-title">Initial Wind Extent</h4><div class="legend-flow">' + rows + '</div>');
    }

    function _renderStormSurgeWWLegend() {
        const events = [
            ['#B524F7', 'Storm Surge Warning'],
            ['#DB7FF7', 'Storm Surge Watch'],
        ];
        const rows = events.map(([color, label]) => swatch(color, escapeHtml(label), 'is-wide')).join('');
        setLegend('<h4 class="legend-title">Storm Surge Watches & Warnings</h4><div class="legend-flow">' + rows + '</div>');
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

    function _formatTropicalIssued(iso) {
        // NHC issuance is UTC (…Z); show it unambiguously without timezone conversion.
        const s = String(iso || '');
        return /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(s)
            ? `${s.slice(0, 10)} ${s.slice(11, 16)} UTC`
            : '--';
    }

    function _renderTropicalSummary(data) {
        const head = byId('wx-tropical-summary-head');
        const summary = byId('weather-tropical-summary');
        // Floater is live-storm only; hide by default — the live detail loader
        // re-shows it via _renderTropicalFloater() when a floater exists.
        _hideTropicalFloater();
        // No storm selected: blank the System tab so stale content doesn't linger.
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
                const issued = _formatTropicalIssued(storm.publicAdvisory?.issuance || storm.lastUpdate);
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

    function _setLayersTabLabel(label) {
        const btn = byId('wx-right-tab-btn-layers');
        if (btn) btn.textContent = label;
    }

    // Entering archive context: relabel the Layers tab to "Current" so the user
    // has a clear way back to live mode.
    function _enterTropicalArchiveContext() {
        if (_tropicalArchiveContext) return;
        _tropicalArchiveContext = true;
        _setLayersTabLabel('Current');
    }

    // Leaving archive context: revert the tab label.
    function _exitTropicalArchiveContext() {
        if (!_tropicalArchiveContext) return;
        _tropicalArchiveContext = false;
        _setLayersTabLabel('Layers');
    }

    // Clicking the "Current" (Layers) tab while an archived storm is displayed returns
    // to the live default view: clear the storm/scrubber off the map, blank the System
    // inspector, and restore the GTWO outlook + its reliability HUD.
    function _exitArchiveToLiveView() {
        _stopArchiveScrubPlay();
        _clearArchiveFixHighlight();
        _hideArchiveScrubberBar();
        _clearTropicalLayer();
        _activeTropicalStorm = null;
        _tropicalArchiveStormBase = null;
        _tropicalArchiveSelectedId = null;
        _tropicalArchiveReliabilityLabel = null;
        _tropicalPageController?.resetArchiveScrubber?.();
        _highlightTropicalArchiveCard();
        _closeTropicalDetail();
        _renderTropicalSummary(null);
        _setTropicalDetailSectionsVisible(true);
        _setTropicalMapViewMode('both');
        fitTropicalDefaultExtent();
        _renderTropicalOutlookLegend();
        _applyOutlookReliability();
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
        _enterTropicalArchiveContext();
        _tropicalArchiveSelectedId = atcfId;
        _highlightTropicalArchiveCard();
        _closeTropicalDetail();
        _closeOutlookDetail();
        _setTropicalMapViewMode('system');
        _tropicalEngine?.loadArchiveStormDetail(atcfId);
        // Reveal the storm in the System inspector, like clicking a live card.
        byId('wx-right-tab-btn-system')?.click();
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


    // ── Distance-based filtering ──────────────────────────────────────────────

    function _haversineKm(lat1, lon1, lat2, lon2) {
        const R = 6371;
        const dLat = (lat2 - lat1) * Math.PI / 180;
        const dLon = (lon2 - lon1) * Math.PI / 180;
        const a = Math.sin(dLat / 2) ** 2
            + Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.sin(dLon / 2) ** 2;
        return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    }

    function _cityDistanceRangeKm(source, zoom) {
        if (source === 'world') {
            if (zoom >= 10) return { min: 4, max: 80 };
            if (zoom >= 9) return { min: 8, max: 160 };
            if (zoom >= 8) return { min: 18, max: 350 };
            if (zoom >= 7) return { min: 40, max: 800 };
            if (zoom >= 6) return { min: 85, max: 1600 };
            if (zoom >= 5) return { min: 175, max: 2500 };
            if (zoom >= 4) return { min: 350, max: 3500 };
            if (zoom >= 3) return { min: 700, max: 5000 };
            return { min: 1200, max: 6000 };
        }

        if (zoom >= 9) return { min: 5, max: 60 };
        if (zoom >= 7) return { min: 40, max: 600 };
        if (zoom >= 5) return { min: 150, max: 1500 };
        return { min: 180, max: 2500 };
    }

    function _cityMinDistKm(zoom, density = _citiesDensity) {
        const source = _readCitiesSource() || _citiesSource || 'us';
        const { min, max } = _cityDistanceRangeKm(source, zoom);
        const t = Math.max(0, Math.min(1, Number(density) || 0));
        return max - ((max - min) * t);
    }

    // Filters items so no two are closer than minDistKm.
    // Items are processed in order (rank-first for pre-sorted data).
    // Uses a lat/lon bucket grid for O(n) average performance.
    function _filterByMinDistKm(items, getLatFn, getLonFn, minDistKm) {
        if (!items.length || minDistKm <= 0) return items;
        const cellDeg = minDistKm / 111;
        const grid = new Map();
        const accepted = [];

        for (const item of items) {
            const lat = getLatFn(item);
            const lon = getLonFn(item);
            if (!Number.isFinite(lat) || !Number.isFinite(lon)) continue;

            const row = Math.floor(lat / cellDeg);
            const col = Math.floor(lon / cellDeg);
            let tooClose = false;

            outer: for (let dr = -2; dr <= 2; dr++) {
                for (let dc = -2; dc <= 2; dc++) {
                    const bucket = grid.get(`${row + dr}:${col + dc}`);
                    if (!bucket) continue;
                    for (const [bLat, bLon] of bucket) {
                        if (_haversineKm(lat, lon, bLat, bLon) < minDistKm) {
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

    function _formatSurfaceTick(value) {
        return Number.isInteger(value) ? String(value) : value.toFixed(1);
    }

    function renderContinuousLegend(title, axisLabel, anchors, ticks = null, options = {}) {
        const normalized = (Array.isArray(anchors) ? anchors : [])
            .map((item) => Array.isArray(item)
                ? [Number(item[0]), item[1], item[2]]
                : [Number(item?.value), item?.color, item?.label])
            .filter(([value, color]) => Number.isFinite(value) && color);
        if (!normalized.length) return '';

        const min = normalized[0][0];
        const max = normalized[normalized.length - 1][0];
        const range = Math.max(1, max - min);
        const gradient = normalized.map(([value, color]) => {
            const pct = ((value - min) / range) * 100;
            return `${color} ${pct.toFixed(2)}%`;
        }).join(', ');
        const normalizedTicks = (Array.isArray(ticks) && ticks.length ? ticks : normalized)
            .map((item) => Array.isArray(item)
                ? [Number(item[0]), item[2] ?? item[0]]
                : [Number(item?.value), item?.label ?? item?.value])
            .filter(([value]) => Number.isFinite(value));
        const tickHtml = normalizedTicks.map(([value, label]) => (
            `<span class="legend-text surface-colorbar-tick">${escapeHtml(label ?? _formatSurfaceTick(value))}</span>`
        )).join('');

        const barHtml =
            `<div class="surface-colorbar-bar" style="background: linear-gradient(to right, ${gradient});"></div>` +
            `<div class="surface-colorbar-ticks">${tickHtml}</div>`;

        // Optional discrete swatch (e.g. AOD "No Data") shown left of the bar.
        const swatch = options?.leadingSwatch;
        const barBlock = swatch
            ? `<div class="legend-colorbar-row">` +
                `<div class="legend-colorbar-swatch">` +
                    `<div class="legend-colorbar-swatch-box" style="background: ${swatch.color};"></div>` +
                    `<span class="legend-text legend-colorbar-swatch-label">${escapeHtml(swatch.label)}</span>` +
                `</div>` +
                `<div class="legend-colorbar-main">${barHtml}</div>` +
              `</div>`
            : barHtml;

        return (
            `<h4 class="legend-title">${escapeHtml(title)}</h4>` +
            `<div class="surface-colorbar">` +
            barBlock +
            `<div class="legend-text surface-colorbar-label">${escapeHtml(axisLabel)}</div>` +
            `</div>`
        );
    }
    map.on('zoomend', () => {
        _updateCitiesDensityLabel();
        _refreshCitiesIfVisible();
    });



    function _activeScrubberPlaybackSpeed() {
        const speed = SCRUBBER_PLAYBACK_SPEEDS[_scrubberPlaybackSpeedIndex];
        return Number.isFinite(speed) && speed > 0 ? speed : 1;
    }

    function _scrubberPlaybackDelay(baseMs, minMs = 60) {
        const base = Math.max(1, Number(baseMs) || 1);
        const min = Math.max(1, Number(minMs) || 1);
        return Math.max(min, Math.round(base / _activeScrubberPlaybackSpeed()));
    }

    function _formatScrubberPlaybackSpeed(speed) {
        if (Number.isInteger(speed)) return `${speed}x`;
        return `${String(speed).replace(/0+$/, '').replace(/\.$/, '')}x`;
    }

    function _updateScrubberPlaybackSpeedUi() {
        const speed = _activeScrubberPlaybackSpeed();
        const label = byId('scrubber-speed-label');
        if (label) label.textContent = _formatScrubberPlaybackSpeed(speed);
    }

    function _setScrubberPlaybackSpeedIndex(index) {
        const safeIndex = Math.max(0, Math.min(SCRUBBER_PLAYBACK_SPEEDS.length - 1, Number(index) || 0));
        if (safeIndex === _scrubberPlaybackSpeedIndex) return;
        _scrubberPlaybackSpeedIndex = safeIndex;
        _updateScrubberPlaybackSpeedUi();
        if (_archivePlayTimer) {
            clearInterval(_archivePlayTimer);
            _archivePlayTimer = null;
            startScrubberPlay();
        }
    }

    function _adjustScrubberPlaybackSpeed(delta) {
        _setScrubberPlaybackSpeedIndex(_scrubberPlaybackSpeedIndex + (Number(delta) || 0));
    }

    // ── Event wiring ─────────────────────────────────────────────────────────

    async function _ensureBoundaryLayers() {
        if (statesLayer && countiesLayer) return;
        try {
            const resp = await fetch(apiUrl('/api/overlay/us-boundaries'));
            if (!resp.ok) return;
            const geojson = await resp.json();
            const allFeatures = Array.isArray(geojson?.features) ? geojson.features : [];
            const states = {
                type: 'FeatureCollection',
                features: allFeatures.filter((feat) => feat?.properties?.layer === 'state'),
            };
            const counties = {
                type: 'FeatureCollection',
                features: allFeatures.filter((feat) => feat?.properties?.layer === 'county'),
            };

            statesLayer = L.geoJSON(states, {
                pane: 'boundary-lines',
                style: { color: '#dbe6ef', weight: 1, opacity: 0.8, fillOpacity: 0 },
                interactive: false,
            });
            countiesLayer = L.geoJSON(counties, {
                pane: 'boundary-lines',
                style: { color: '#8aa2b6', weight: 0.5, opacity: 0.45, fillOpacity: 0 },
                interactive: false,
            });
        } catch {
            setStatus('State/county boundary overlay unavailable.');
        }
    }

    async function _ensureCountriesLayer() {
        if (countriesLayer) return;
        try {
            const resp = await fetch(apiUrl('/api/overlay/world-borders'));
            if (!resp.ok) return;
            const countriesRaw = await resp.json();
            const countries = _normalizeGeoJsonForDateline(countriesRaw);
            countriesLayer = L.geoJSON(countries, {
                pane: 'boundary-lines',
                style: { color: '#aac4d8', weight: 1, opacity: 0.7, fillOpacity: 0 },
                interactive: false,
            });
        } catch {
            setStatus('Country border overlay unavailable.');
        }
    }

    function _unwrapRingLongitudes(ring) {
        if (!Array.isArray(ring) || ring.length < 2) return ring;
        const out = [ring[0].slice()];
        let prevLon = Number(ring[0][0]);
        let offset = 0;

        for (let i = 1; i < ring.length; i += 1) {
            const pt = ring[i];
            if (!Array.isArray(pt) || pt.length < 2) continue;

            let lon = Number(pt[0]) + offset;
            const lat = Number(pt[1]);
            if (!Number.isFinite(lon) || !Number.isFinite(lat)) continue;

            const delta = lon - prevLon;
            if (delta > 180) {
                offset -= 360;
                lon = Number(pt[0]) + offset;
            } else if (delta < -180) {
                offset += 360;
                lon = Number(pt[0]) + offset;
            }

            out.push([lon, lat]);
            prevLon = lon;
        }

        return out;
    }

    function _normalizeGeometryForDateline(geometry) {
        if (!geometry || !geometry.type || !geometry.coordinates) return geometry;

        if (geometry.type === 'LineString') {
            return { ...geometry, coordinates: _unwrapRingLongitudes(geometry.coordinates) };
        }
        if (geometry.type === 'MultiLineString') {
            return {
                ...geometry,
                coordinates: geometry.coordinates.map((line) => _unwrapRingLongitudes(line)),
            };
        }
        if (geometry.type === 'Polygon') {
            return {
                ...geometry,
                coordinates: geometry.coordinates.map((ring) => _unwrapRingLongitudes(ring)),
            };
        }
        if (geometry.type === 'MultiPolygon') {
            return {
                ...geometry,
                coordinates: geometry.coordinates.map((poly) => (
                    poly.map((ring) => _unwrapRingLongitudes(ring))
                )),
            };
        }
        if (geometry.type === 'GeometryCollection' && Array.isArray(geometry.geometries)) {
            return {
                ...geometry,
                geometries: geometry.geometries.map((g) => _normalizeGeometryForDateline(g)),
            };
        }
        return geometry;
    }

    function _normalizeGeoJsonForDateline(geojson) {
        if (!geojson || typeof geojson !== 'object') return geojson;

        if (geojson.type === 'FeatureCollection' && Array.isArray(geojson.features)) {
            return {
                ...geojson,
                features: geojson.features.map((feature) => ({
                    ...feature,
                    geometry: _normalizeGeometryForDateline(feature.geometry),
                })),
            };
        }
        if (geojson.type === 'Feature') {
            return {
                ...geojson,
                geometry: _normalizeGeometryForDateline(geojson.geometry),
            };
        }
        return _normalizeGeometryForDateline(geojson);
    }

    function _readCitiesSource() {
        const selected = document.querySelector('input[name="weather-cities-mode"]:checked')?.value || 'off';
        return CITY_SOURCES[selected] ? selected : null;
    }

    function _clearCitiesLayer() {
        if (citiesLayer) {
            map.removeLayer(citiesLayer);
            citiesLayer = null;
        }
    }

    function _syncCitiesModeControls() {
        const disabled = !_readCitiesSource();
        document.querySelectorAll('.wx-cities-density').forEach((row) => {
            row.classList.toggle('is-disabled', disabled);
            row.querySelectorAll('input').forEach((input) => {
                input.disabled = disabled;
            });
        });
    }

    async function _ensureCitiesLayer() {
        const sourceKey = _readCitiesSource();
        if (!sourceKey) {
            _clearCitiesLayer();
            return;
        }
        if (_citiesSource !== sourceKey) {
            _citiesSource = sourceKey;
            _citiesData = _citiesDataBySource.get(sourceKey) || null;
            _clearCitiesLayer();
        }
        if (_citiesData && citiesLayer) return;
        try {
            if (!_citiesData) {
                const resp = await fetch(apiUrl(CITY_SOURCES[sourceKey].path));
                if (!resp.ok) return;
                _citiesData = await resp.json();
                _citiesDataBySource.set(sourceKey, _citiesData);
            }
            _rebuildCitiesLayer();
        } catch {
            setStatus('City overlay unavailable.');
        }
    }

    function _readCitiesDensity() {
        const raw = parseFloat(byId('weather-cities-density')?.value || '1');
        if (!Number.isFinite(raw)) return 1;
        return Math.max(0.01, Math.min(1, raw));
    }

    function _updateCitiesDensityLabel() {
        const label = document.querySelector('label[for="weather-cities-density"]');
        if (!label) return;
        const zoom = map?.getZoom() ?? 5;
        const distKm = Math.round(_cityMinDistKm(zoom));
        const baseLabel = label.dataset.baseLabel || 'City Density';
        label.dataset.baseLabel = baseLabel;
        label.textContent = `${baseLabel} (${distKm} km)`;
    }

    function _escapeHtml(text) {
        return String(text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function _cityLabelMarker(c) {
        const lat = Number(c.latitude);
        const lon = Number(c.longitude);
        const cityName = String(c.city || c.name || '');
        const width = Math.max(14, Math.min(220, cityName.length * CITY_LABEL_CHAR_PX + CITY_LABEL_X_PAD * 2));
        const height = CITY_LABEL_HEIGHT_PX + CITY_LABEL_Y_PAD * 2;
        return L.marker([lat, lon], {
            interactive: false,
            keyboard: false,
            icon: L.divIcon({
                className: 'city-name-tag',
                html: `<span>${_escapeHtml(cityName)}</span>`,
                iconSize: [width, height],
                iconAnchor: [Math.round(width / 2), Math.round(height / 2)],
            }),
        });
    }

    function _cityInBounds(city, bounds) {
        const lat = Number(city.latitude);
        const lon = Number(city.longitude);
        if (!Number.isFinite(lat) || !Number.isFinite(lon)) return false;
        return lat >= bounds.getSouth() && lat <= bounds.getNorth()
            && lon >= bounds.getWest() && lon <= bounds.getEast();
    }

    function _computeCitySubset() {
        if (!_citiesData?.length) return [];
        const inView = _citiesData.filter((c) => _cityInBounds(c, map.getBounds().pad(0.1)));
        if (!inView.length) return [];
        const zoom = map.getZoom();
        const minDistKm = _cityMinDistKm(zoom);
        return _filterByMinDistKm(inView, c => Number(c.latitude), c => Number(c.longitude), minDistKm);
    }

    function _buildCityRenderLayer(markers) {
        return L.layerGroup(markers);
    }

    function _rebuildCitiesLayer() {
        if (!_citiesData?.length) return;
        const wasVisible = !!(citiesLayer && map.hasLayer(citiesLayer));
        if (citiesLayer) map.removeLayer(citiesLayer);
        const subset = _computeCitySubset();
        const markers = subset.map(_cityLabelMarker);
        citiesLayer = _buildCityRenderLayer(markers);
        if (wasVisible) citiesLayer.addTo(map);
    }

    function _refreshCitiesIfVisible() {
        if (!_readCitiesSource()) return;
        if (!_citiesData) return;
        _rebuildCitiesLayer();
    }

    async function _syncRightSidebarLayers() {
        const showStates = byId('weather-toggle-states')?.checked;
        const showCounties = byId('weather-toggle-counties')?.checked;
        const showCities = !!_readCitiesSource();
        const showCountries = byId('weather-toggle-countries')?.checked;

        await _ensureBoundaryLayers();
        if (showCities) await _ensureCitiesLayer();
        else _clearCitiesLayer();
        await _ensureCountriesLayer();

        if (countriesLayer) {
            if (showCountries) countriesLayer.addTo(map); else map.removeLayer(countriesLayer);
        }
        if (statesLayer) {
            if (showStates) statesLayer.addTo(map); else map.removeLayer(statesLayer);
        }
        if (countiesLayer) {
            if (showCounties) countiesLayer.addTo(map); else map.removeLayer(countiesLayer);
        }
        if (citiesLayer) {
            if (showCities) citiesLayer.addTo(map); else map.removeLayer(citiesLayer);
        }

    }

    // Helper function to show/hide network filters based on region
    byId('weather-region')?.addEventListener('change', (e) => {
        const nextRegion = String(e.target.value || '').toUpperCase();
        fitRegion(nextRegion);
        _clearSpeedOverride();
        _clearRadarCalLine();
        refreshActiveLayers();
    });

    byId('weather-tropical-basin')?.addEventListener('change', () => {
        if (!_isTypeEnabled('tropical')) return;
        _armProductRendering();
        const sysSelect = byId('weather-tropical-system');
        if (sysSelect) sysSelect.value = '';
        _activeTropicalStorm = null;
        _setTropicalHubMode('overview');
        _clearTropicalLayer();
        _closeTropicalDetail();
        _fitTropicalBasinExtent();
        _tropicalEngine?.loadStorms(true);
    });

    byId('weather-tropical-system')?.addEventListener('change', () => {
        if (!_isTypeEnabled('tropical')) return;
        _armProductRendering();
        _closeTropicalDetail();
        _tropicalEngine?.loadStormDetail(
            _activeTropicalSystemId(),
            { fitBounds: false, zoomToLatest: true },
        );
    });

    byId('weather-refresh-tropical')?.addEventListener('click', () => {
        if (!_isTypeEnabled('tropical')) return;
        _armProductRendering();
        const sysSelect = byId('weather-tropical-system');
        if (sysSelect) sysSelect.value = '';
        _activeTropicalStorm = null;
        _setTropicalHubMode('overview');
        _closeOutlookDetail();
        _closeTropicalDetail();
        _setTropicalMapViewMode('both');
        fitTropicalDefaultExtent();
        _tropicalEngine?.loadStorms(true);
    });

    byId('weather-tropical-graticule')?.addEventListener('change', (e) => {
        if (e.target.checked) {
            _addGraticule();
        } else {
            _removeGraticule();
        }
    });

    byId('wx-tropical-inspector-layers')?.addEventListener('change', (event) => {
        const input = event.target;
        const layerId = input?.getAttribute?.('data-tc-layer');
        if (!layerId) return;
        _tropicalEngine?.handleLayerToggle?.(layerId, input.checked);
    });

    // Collapsible accordion sections in the System tab.
    byId('weather-tropical-inspector')?.addEventListener('click', (event) => {
        const header = event.target.closest('.wx-accordion-header');
        if (!header) return;
        const section = header.closest('.wx-accordion');
        if (!section) return;
        const isOpen = section.getAttribute('data-open') === 'true';
        section.setAttribute('data-open', isOpen ? 'false' : 'true');
    });


    ['current', 'alerts', 'radar', 'satellite', 'spc', 'rtma', 'mrms', 'drought', 'tropical', 'wpc', 'water'].forEach((type) => {
        byId(`weather-type-${type}`)?.addEventListener('change', (e) => {
            // Enforce single active weather type for all tabs
            const allTypes = ['current', 'alerts', 'radar', 'satellite', 'spc', 'rtma', 'mrms', 'drought', 'tropical', 'wpc', 'water'];
            // Capture previous tab BEFORE uncheck loop runs (otherwise the DOM
            // state would already reflect the new selection).
            if (_activeTabType === null) _activeTabType = _detectInitialActiveTabType();
            const prevType = _activeTabType;
            if (e.target.checked) {
                // Uncheck all other weather type tabs
                allTypes.forEach((otherType) => {
                    if (otherType !== type) {
                        const el = byId(`weather-type-${otherType}`);
                        if (el) el.checked = false;
                    }
                });
            }
            if (e.target.checked) {
                if (prevType && prevType !== type) {
                    _cleanupPreviousTabState(prevType);
                    _resetTabControlsToDefaults(prevType, { silent: true });
                }
                _resetTransientInteractiveUiForTabChange();
                _resetTabControlsToDefaults(type);
                _activeTabType = type;
                if (type === 'tropical') {
                    fitTropicalDefaultExtent();
                } else {
                    fitRegion(byId('weather-region')?.value || 'CONUS');
                }
                if (['rtma', 'drought', 'tropical', 'wpc', 'water'].includes(type)) {
                    _setViewerTimestamp(null);
                }
            }
            _updateTypeSections();
            _updateRightSidebarGroups();
            refreshActiveLayers();
        });
    });


    byId('weather-refresh-water')?.addEventListener('click', () => {
        _armProductRendering();
        if (_isTypeEnabled('water')) _loadWaterStations({ force: true });
    });

    byId('weather-clear-water')?.addEventListener('click', () => {
        _clearWaterLayer();
        _setWaterStatus('Water markers cleared.');
    });

    function _updateWaterFloodPillsVisibility() {
        const riverChecked = !!document.querySelector('.weather-water-network-filter input[value="river"]:checked');
        const row = byId('weather-water-flood-filter-row');
        if (row) row.hidden = !riverChecked;
        if (!riverChecked && _waterFloodFilter !== 'all') {
            _waterFloodFilter = 'all';
            document.querySelectorAll('.wx-water-flood-pill').forEach((p) => {
                p.setAttribute('aria-selected', String(p.dataset.flood === 'all'));
            });
        }
    }

    document.querySelectorAll('.weather-water-network-filter input[type="checkbox"]').forEach((checkbox) => {
        checkbox.addEventListener('change', () => {
            _updateWaterFloodPillsVisibility();
            if (_isTypeEnabled('water')) _loadWaterStations({ force: true });
        });
    });

    _updateWaterFloodPillsVisibility();

    byId('weather-water-flood-filters')?.addEventListener('click', (evt) => {
        const pill = evt.target.closest('.wx-water-flood-pill');
        if (!pill) return;
        _waterFloodFilter = pill.dataset.flood || 'all';
        document.querySelectorAll('.wx-water-flood-pill').forEach((p) => {
            p.setAttribute('aria-selected', String(p === pill));
        });
        _renderWaterStations(_waterStations);
        if (_waterFloodFilter !== 'all') {
            const visible = _applyWaterFloodFilter(_waterStations).length;
            _setWaterStatus(`Flood filter: ${visible} of ${_waterStations.length} river gauges shown.`);
        }
    });


    byId('wx-stormtrack-start')?.addEventListener('click', () => {
        _clearStormTrackLayer();
        _stormTrackBaseLatLngs = [];
        _setStormTrackDrawMode(true);
    });

    byId('wx-stormtrack-finish')?.addEventListener('click', () => {
        _setStormTrackDrawMode(false);
        _activateStormTrackDragProjection();
    });

    byId('wx-stormtrack-clear')?.addEventListener('click', () => {
        _setStormTrackDrawMode(false);
        _stormTrackBaseLatLngs = [];
        _clearStormTrackLayer();
        setStatus('Storm track projection cleared.');
    });

    byId('wx-radarcal-start')?.addEventListener('click', () => {
        _clearRadarCalLine();
        _setRadarCalDrawMode(true);
        setStatus('Click on the map to mark where the cell was at the start of the radar loop, then click again at its current position.');
    });

    byId('wx-radarcal-clear')?.addEventListener('click', () => {
        _setRadarCalDrawMode(false);
        _clearRadarCalLine();
        _clearSpeedOverride();
        setStatus('Radar speed calibration cleared.');
    });

    byId('wx-speed-override-clear')?.addEventListener('click', () => {
        _clearSpeedOverride();
    });

    document.addEventListener('keydown', (evt) => {
        if (evt.key === 'Shift') _stormTrackPivotKeyDown = true;
    });
    document.addEventListener('keyup', (evt) => {
        if (evt.key === 'Shift') _stormTrackPivotKeyDown = false;
    });

    map.on('click', (evt) => {
        // Radar speed calibrator draw mode — independent of storm-track projection.
        if (_radarCalDrawMode) {
            const latlng = evt?.latlng;
            if (!latlng) return;
            _radarCalLatLngs.push(L.latLng(latlng.lat, latlng.lng));
            _renderRadarCalLine();
            // Auto-finish after two points (start + end of cell movement).
            if (_radarCalLatLngs.length >= 2) _setRadarCalDrawMode(false);
            return;
        }

        if (!_stormTrackDrawMode) {
            const hasProjection = !!_stormTrackMotion
                || !!_stormTrackDragHandle
                || (_stormTrackProjectionLayer.getLayers().length > 0)
                || !!_stormTrackPlacesOverlayEl;
            if (hasProjection) {
                _stormTrackBaseLatLngs = [];
                _clearStormTrackLayer();
                setStatus('Storm track projection cleared.');
            }
            return;
        }
        const latlng = evt?.latlng;
        if (!latlng) return;
        _stormTrackBaseLatLngs.push(L.latLng(latlng.lat, latlng.lng));
        _clearStormTrackProjection();
        _stormTrackHandleLayer.clearLayers();
        if (_stormTrackBaseLatLngs.length >= 2) {
            L.polyline(_stormTrackBaseLatLngs, {
                color: '#f8fafc',
                weight: 2.5,
                opacity: 0.95,
            }).addTo(_stormTrackProjectionLayer);
        } else {
            L.circleMarker(_stormTrackBaseLatLngs[0], {
                radius: 4,
                color: '#f8fafc',
                fillColor: '#f8fafc',
                fillOpacity: 1,
                weight: 1,
            }).addTo(_stormTrackProjectionLayer);
        }
    });




    document.querySelectorAll('input[name="weather-cities-mode"]').forEach((input) => {
        input.addEventListener('change', () => {
            _syncCitiesModeControls();
            _updateCitiesDensityLabel();
            _syncRightSidebarLayers();
        });
    });
    byId('weather-cities-density')?.addEventListener('input', () => {
        _citiesDensity = _readCitiesDensity();
        _updateCitiesDensityLabel();
        if (_citiesData) _rebuildCitiesLayer();
    });
    byId('weather-cities-font-size')?.addEventListener('input', (e) => {
        const val = parseFloat(e.target.value || '0.6');
        document.documentElement.style.setProperty('--city-font-size', String(val));
    });
    _citiesDensity = _readCitiesDensity();
    _updateCitiesDensityLabel();
    _syncCitiesModeControls();
    byId('weather-toggle-states')?.addEventListener('change', _syncRightSidebarLayers);
    byId('weather-toggle-counties')?.addEventListener('change', _syncRightSidebarLayers);
    byId('weather-toggle-countries')?.addEventListener('change', _syncRightSidebarLayers);

    map.on('moveend', () => {
        _refreshCitiesIfVisible();
        if (_productRenderArmed && _isTypeEnabled('water')) {
            _scheduleWaterReload();
        }
    });


    // ── Init ─────────────────────────────────────────────────────────────────
    async function init() {
        // Normalize tab checkbox state to HTML defaults at startup. Browsers
        // (both Firefox and Edge) restore form state from previous sessions,
        // which can leave multiple weather-type checkboxes checked and cause
        // background tabs to silently load data (e.g. MRMS PrecipFlag firing
        // on a "Current" tab load because the user had MRMS active before
        // refreshing).
        const allTypes = ['current', 'alerts', 'radar', 'satellite', 'spc', 'rtma', 'mrms', 'drought', 'tropical', 'wpc', 'water'];
        _configureStandaloneProductPage(allTypes);
        allTypes.forEach((t) => {
            const el = byId(`weather-type-${t}`);
            if (el) el.checked = el.defaultChecked;
        });
        // Surface startup also depends on the default product being active.
        // Restore both product and gradient controls before the first refresh
        // so browser-restored form state cannot suppress initial initialization.
        document.querySelectorAll('.weather-surface-product, .weather-surface-gradient').forEach((cb) => {
            cb.checked = cb.defaultChecked;
        });

        _updateTypeSections();
        _updateRightSidebarGroups();
        _updateSubOptionVisibility();
        _wireRightSidebarTabs();
        _wireTropicalLeftTabs();
        _citiesDensity = _readCitiesDensity();
        _updateCitiesDensityLabel();
        await _loadUserSettingsDefaults();
        _productRenderArmed = _configuredPageAutoLoad();
        _applyConfiguredTropicalBasin();
        _syncRightSidebarLayers();
        _setViewerTimestamp(null);
        _applyInitialMapView();
        refreshActiveLayers({ startup: true });
        if (!_productRenderArmed && _isTypeEnabled('tropical') && _configuredPageAutoLoadCatalog()) {
            _tropicalEngine?.loadArchiveCatalog();
        }
        _startReliabilityTicker();
    }

    function _registerProductAppContexts() {

        if (_tropicalPageController?.configureTropicalPage) {
            _tropicalPageController.configureTropicalPage({
                categoryColor: _tropicalCategoryColor,
                categoryFromProperties: (properties) => (
                    TROPICAL_CATEGORIES[_tropicalCategoryKey(properties)] || TROPICAL_CATEGORIES.OTHER
                ),
                categoryFromWind: (windKt) => (
                    TROPICAL_CATEGORIES[_tropicalCategoryKeyFromWind(windKt)] || TROPICAL_CATEGORIES.OTHER
                ),
                categoryKeyFromProperties: _tropicalCategoryKey,
                categoryKeyFromWind: _tropicalCategoryKeyFromWind,
                closeAlertDetail: () => {},
                createImage: () => new Image(),
                escapeHtml,
                clearArchiveFixHighlight: _clearArchiveFixHighlight,
                formatFixDate: _formatFixDTG,
                formatLatLon: _formatLatLon,
                formatPlaybackSpeed: _formatScrubberPlaybackSpeed,
                floaterCacheBust: () => Math.floor(Date.now() / 300000),
                getArchiveCatalog: () => _tropicalArchiveCatalog,
                getArchiveStormName: () => _tropicalArchiveStormName,
                getActiveStorm: () => _activeTropicalStorm,
                getTropicalGisGeoJson: _tropicalGisGeoJson,
                getPlaybackSpeeds: () => SCRUBBER_PLAYBACK_SPEEDS,
                getSelectedArchiveId: () => _tropicalArchiveSelectedId,
                ktToMph: _ktToMph,
                motionText: _tropicalMotionText,
                pointColor: _tropicalPointColor,
                loadArchiveAdvisory: (step, options) => (
                    _tropicalEngine?.loadArchiveAdvisory(
                        _tropicalArchiveStormId,
                        step,
                        options,
                    )
                ),
                loadArchiveFix: _loadArchiveFix,
                openGraphicDetail: _openTropicalGraphicDetail,
                openProductDetail: _openTropicalProductDetail,
                selectArchiveStorm: _selectTropicalArchiveStorm,
                selectStorm: _selectTropicalStormCard,
                setArchiveStatus: _setTropicalArchiveStatus,
                setStatus: _setTropicalStatus,
                setTimeoutFn: (callback, delay) => setTimeout(callback, delay),
                windClass: _tropicalWindClass,
            });
            _tropicalPageController.wireArchiveControls?.();
            _tropicalPageController.wireArchiveScrubberControls?.();
            _tropicalPageController.wireFloaterControls?.();
        }


        const tropicalContext = _productAppContexts?.registerProductContext('tropical', {
            alertColors: ALERT_COLORS,
            alertDefault: ALERT_DEFAULT,
            apiUrl,
            canApplyResponse: (requestSeq) => (
                requestSeq === _tropicalRequestSeq && _isTypeEnabled('tropical')
            ),
            clearActiveStorm: () => { _activeTropicalStorm = null; },
            clearLiveStormDetail: () => {
                _activeTropicalStorm = null;
                _clearTropicalLayer();
                _renderTropicalSummary(null);
                _renderTropicalOutlookLegend();
            },
            clearTropicalLayer: _clearTropicalLayer,
            categoryColor: _tropicalCategoryColor,
            categoryIcon: _tropicalCategoryIcon,
            categoryKey: _tropicalCategoryKey,
            fetchFn: (url, options) => fetch(url, options),
            getActiveBasin: _activeTropicalBasin,
            getActiveStorm: () => _activeTropicalStorm,
            getArchiveCatalog: () => _tropicalArchiveCatalog,
            getArchiveStormBase: () => _tropicalArchiveStormBase,
            getSelectedStormId: _activeTropicalSystemId,
            isCurrentRequest: (requestSeq) => requestSeq === _tropicalRequestSeq,
            isTypeEnabled: _isTypeEnabled,
            leaflet: L,
            loadBasinFeeds: loadTropicalBasinFeeds,
            liveStormLabel: (data) => {
                const summaryStorm = _tropicalStorms.find((storm) => (
                    String(storm?.id || '').toUpperCase() === String(data?.stormId || '').toUpperCase()
                ));
                return summaryStorm?.name
                    ? `${summaryStorm.name} — ${_tropicalWindClass(summaryStorm.intensity)}`
                    : (data.advisory?.headline || `${data.stormId} advisory loaded`);
            },
            nextRequestSeq: () => {
                _tropicalRequestSeq += 1;
                return _tropicalRequestSeq;
            },
            map,
            openProductDetail: _openTropicalProductDetail,
            pointCategory: _tropicalPointCategory,
            pointColor: _tropicalPointColor,
            prepareArchiveAdvisoryMode: (advisories) => {
                _tropicalPageController?.setArchiveAdvisoryMode?.(advisories);
            },
            prepareArchiveBestTrackMode: () => {
                _tropicalPageController?.setArchiveBestTrackMode?.();
            },
            prepareArchiveStorm: (data, atcfId) => {
                _stopArchiveScrubPlay();
                _clearArchiveFixHighlight();
                _tropicalArchiveStormBase = data;
                _tropicalArchiveStormId = atcfId;
                _tropicalArchiveStormName = data.storm?.name || atcfId;
                _tropicalPageController?.setArchiveFixes?.(
                    data.gis_layers?.best_track_points?.geojson?.features || [],
                );
            },
            renderOutlookLegend: _renderTropicalOutlookLegend,
            renderLayerLegend: (layerId, checked) => {
                const legendRenderers = {
                    peak_surge: _renderPeakSurgeLegend,
                    watches_warnings: _renderWatchesWarningsLegend,
                    wind_radii: _renderWindRadiiLegend,
                    initial_wind_extent: _renderInitialWindExtentLegend,
                    storm_surge: _renderStormSurgeWWLegend,
                };
                if (checked && legendRenderers[layerId]) {
                    legendRenderers[layerId]();
                } else if (!checked && _activeTropicalStorm) {
                    _renderTropicalLegend();
                }
            },
            renderLiveStormDetail: (data, options) => {
                _renderTropicalSummary(data);
                _renderTropicalFloater(data.stormId);
                _highlightSelectedTropicalCard();
                _tropicalEngine?.setLayerToggles?.({
                    cone: true,
                    forecast_points: true,
                    forecast_track: false,
                });
                _renderTropicalLayer(data, options);
                _renderTropicalLegend();
                if (options.zoomToLatest) {
                    _zoomTropicalToLatest(data);
                }
            },
            renderArchiveCatalog: (catalog) => _tropicalPageController?.renderArchiveCatalog?.(catalog),
            renderArchiveAdvisory: _renderArchiveAdvisory,
            renderInitialArchiveFix: () => {
                _loadArchiveFix(0, { fit: true, initial: true });
            },
            renderStormList: (storms) => _tropicalPageController?.renderStormList?.(storms),
            renderSummary: _renderTropicalSummary,
            resetLiveArchiveState: () => {
                _tropicalArchiveReliabilityLabel = null;
                _tropicalArchiveSelectedId = null;
                _tropicalPageController?.resetArchiveScrubber?.();
                _setTropicalDetailSectionsVisible(true);
                _exitTropicalArchiveContext();
                _highlightTropicalArchiveCard();
            },
            setActiveStorm: (data) => { _activeTropicalStorm = data; },
            setArchiveCatalog: (catalog) => { _tropicalArchiveCatalog = catalog; },
            setArchiveStatus: _setTropicalArchiveStatus,
            setHubMode: _setTropicalHubMode,
            setStatus: _setTropicalStatus,
            setStorms: (storms) => { _tropicalStorms = storms; },
            selectStorm: _selectTropicalStormCard,
            syncLayerPills: (keys, toggles) => {
                const layersRoot = byId('wx-tropical-inspector-layers');
                if (!layersRoot) return;
                keys.forEach((key) => {
                    const checkbox = layersRoot.querySelector(`[data-tc-layer="${key}"]`);
                    if (checkbox) checkbox.checked = !!toggles[key];
                });
            },
            updateLiveStormMetadata: (data) => {
                const updated = data.updated || Date.now();
                _setViewerTimestamp(updated);
                _setReliability('tropical', 'Tropical Cyclones', 'NOAA NHC', updated);
                _setTimestampSource('tropical', 'NHC Public Advisory', updated);
            },
            updateArchiveAdvisoryMetadata: (advisory, step, atcfId) => {
                _tropicalArchiveReliabilityLabel = advisory.issued || null;
                const advisoryLabel = `Advisory ${advisory.advisoryStep || step}`;
                const updated = advisory.updated || Date.now();
                _setReliability('tropical', `${advisoryLabel} — NHC Archive`, 'NOAA NHC', updated);
                _setTimestampSource('tropical', `${advisoryLabel} — NHC Archive`, updated);
                _setTropicalArchiveStatus(
                    `${_tropicalArchiveStormName || atcfId} — ${advisoryLabel}`,
                );
            },
            updateArchiveStormMetadata: (data) => {
                _setViewerTimestamp(data.updated || Date.now());
            },
            regionFitBottomPaddingPx: REGION_FIT_BOTTOM_PADDING_PX,
            watchWarningEvent: (code) => _TROPICAL_WW_EVENT[code],
            windClass: _tropicalWindClass,
            escapeHtml,
        });
        if (tropicalContext && _tropicalEngineFactory?.createTropicalEngine) {
            _tropicalEngine = _tropicalEngineFactory.createTropicalEngine(tropicalContext);
        }
    }


    _registerProductAppContexts();
    init().catch((err) => {
        console.error('[startup] Dashboard initialization failed:', err);
        setStatus(`Startup error: ${err.message}`);
    });

}());
