(function () {
    'use strict';

    const byId = (id) => document.getElementById(id);

    // ── State Bounds [west, east, south, north] from geo_config.py ──────────
    // Leaflet fitBounds expects [[south, west], [north, east]]
    const STATE_BOUNDS = {
        WORLD: [-179.9, 179.9, -85.0, 85.0],
        CONUS: [-125, -70, 21, 52],
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

    // ── SPC risk colors ──────────────────────────────────────────────────────
    const SPC_CAT_COLORS = {
        TSTM: { fill: '#b5dcb3', stroke: '#5a9e61' },
        MRGL: { fill: '#69bb6d', stroke: '#2d7a32' },
        SLGT: { fill: '#f5dd72', stroke: '#c8a000' },
        ENH: { fill: '#ff9d2e', stroke: '#c85a00' },
        MDT: { fill: '#ff4f4f', stroke: '#a00000' },
        HIGH: { fill: '#ff66ff', stroke: '#880088' },
    };

    const SPC_PROB_COLORS = {
        '2': { fill: '#b5dcb3', stroke: '#5a9e61' },
        '5': { fill: '#69bb6d', stroke: '#2d7a32' },
        '10': { fill: '#f5dd72', stroke: '#c8a000' },
        '15': { fill: '#ff9d2e', stroke: '#c85a00' },
        '30': { fill: '#ff4f4f', stroke: '#a00000' },
        '45': { fill: '#ff66ff', stroke: '#880088' },
        '60': { fill: '#ff00ff', stroke: '#880088' },
    };

    const SPC_FIRE_COLORS = {
        'Elevated': { fill: '#FFBF80', stroke: '#FF7F00' },
        'Critical': { fill: '#FF8080', stroke: '#FF0000' },
        'Extremely Critical': { fill: '#FF80FF', stroke: '#FF00FF' },
        'Isolated': { fill: '#FFBF80', stroke: '#FF7F00' },
        'Scattered': { fill: '#FF8080', stroke: '#FF0000' },
    };

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

    // ── Alert category filter map (mirrors HAZARD_CATEGORIES from alerts_config.py) ──
    const ALERT_CATEGORIES = {
        'Severe Weather Alerts': ['Tornado Warning', 'Severe Thunderstorm Warning', 'Flash Flood Warning', 'Tornado Watch', 'Severe Thunderstorm Watch', 'Extreme Wind Warning', 'Severe Weather Statement'],
        'Severe Weather Warnings': ['Tornado Warning', 'Severe Thunderstorm Warning', 'Flash Flood Warning', 'Severe Weather Statement', 'Special Marine Warning'],
        'Severe Weather Watches': ['Tornado Watch', 'Severe Thunderstorm Watch', 'Flash Flood Watch'],
        'Hydrology Alerts': ['Flash Flood Warning', 'Flood Warning', 'Flash Flood Watch', 'Flood Watch', 'Flood Advisory', 'Flash Flood Statement', 'Flood Statement', 'Hydrologic Outlook', 'Coastal Flood Statement', 'Lakeshore Flood Advisory', 'Lakeshore Flood Statement', 'Lakeshore Flood Warning', 'Lakeshore Flood Watch'],
        'Flash Flood Alerts': ['Flash Flood Warning', 'Flash Flood Watch', 'Flash Flood Statement'],
        'Winter Alerts': ['Winter Storm Warning', 'Blizzard Warning', 'Ice Storm Warning', 'Winter Weather Advisory', 'Winter Storm Watch', 'Lake Effect Snow Warning', 'Snow Squall Warning', 'Freeze Warning', 'Freeze Watch', 'Frost Advisory', 'Extreme Cold Warning', 'Extreme Cold Watch', 'Heavy Freezing Spray Warning', 'Avalanche Advisory', 'Avalanche Watch', 'Avalanche Warning', 'Freezing Fog Advisory', 'Heavy Freezing Spray Watch'],
        'Cold Alerts': ['Extreme Cold Warning', 'Extreme Cold Watch', 'Freeze Warning', 'Freeze Watch', 'Frost Advisory', 'Cold Weather Advisory'],
        'Fire Alerts': ['Red Flag Warning', 'Fire Weather Watch', 'Extreme Fire Danger', 'Fire Warning'],
        'Heat Alerts': ['Heat Advisory', 'Extreme Heat Warning', 'Extreme Heat Watch'],
        'Coastal Alerts': ['Coastal Flood Warning', 'Coastal Flood Watch', 'Coastal Flood Advisory', 'High Surf Warning', 'High Surf Advisory', 'Rip Current Statement', 'Storm Surge Warning', 'Storm Surge Watch', 'Beach Hazards Statement'],
        'Marine Alerts': ['Special Marine Warning', 'Marine Weather Statement', 'Gale Warning', 'Gale Watch', 'Hurricane Force Wind Warning', 'Storm Warning', 'Small Craft Advisory', 'Hazardous Seas Warning', 'Hazardous Seas Watch', 'Heavy Freezing Spray Warning', 'Brisk Wind Advisory', 'Freezing Spray Advisory', 'Low Water Advisory', 'Storm Watch'],
        'Tropical Cyclone Alerts': ['Hurricane Warning', 'Hurricane Watch', 'Tropical Storm Warning', 'Tropical Storm Watch', 'Storm Surge Warning', 'Storm Surge Watch', 'Extreme Wind Warning', 'Tropical Cyclone Local Statement', 'Hurricane Force Wind Warning', 'Hurricane Force Wind Watch', 'Typhoon Warning', 'Typhoon Watch'],
        'Non-Precipitation Alerts': ['High Wind Warning', 'High Wind Watch', 'Wind Advisory', 'Dense Fog Advisory', 'Dense Smoke Advisory', 'Dust Storm Warning', 'Blowing Dust Advisory', 'Air Quality Alert', 'Ashfall Warning', 'Ashfall Advisory', 'Air Stagnation Advisory', 'Blowing Dust Warning', 'Dust Advisory', 'Lake Wind Advisory'],
        'Geophysical Alerts': ['Earthquake Warning', 'Tsunami Advisory', 'Tsunami Watch', 'Tsunami Warning', 'Volcano Warning'],
        'Public Safety Alerts': ['Civil Danger Warning', 'Hazardous Materials Warning', 'Local Area Emergency', 'Radiological Hazard Warning'],
        'Informational Alerts': ['Hazardous Weather Outlook', 'Short Term Forecast', 'Special Weather Statement'],
    };

    const ALERT_CATEGORY_EVENT_SET = new Set(Object.values(ALERT_CATEGORIES).flat());

    function _getAlertCategoryCheckboxes() {
        return [...document.querySelectorAll('.weather-alerts-category')];
    }

    function _setAllAlertCategories(checked) {
        _getAlertCategoryCheckboxes().forEach((el) => {
            el.checked = checked;
        });
    }

    function _syncAllAlertsMaster() {
        const allEl = byId('weather-alerts-all');
        if (!allEl) return;
        const childEls = _getAlertCategoryCheckboxes().filter((el) => el !== allEl);
        const allChecked = childEls.length > 0 && childEls.every((el) => el.checked);
        const noneChecked = childEls.every((el) => !el.checked);
        allEl.checked = allChecked;
        allEl.indeterminate = !allChecked && !noneChecked;
    }

    function _getCheckedAlertCategories() {
        return [...document.querySelectorAll('.weather-alerts-category:checked')]
            .map((el) => el.value)
            .filter((val) => val !== 'All Alerts');
    }

    function _matchesCheckedCategories(feat, checkedCategories) {
        if (!checkedCategories.length) return false;
        const event = feat?.properties?.event || '';
        const isCategorized = ALERT_CATEGORY_EVENT_SET.has(event);
        if (!isCategorized) return true;
        return checkedCategories.some((cat) => (ALERT_CATEGORIES[cat] || []).includes(event));
    }

    // ── Map init ─────────────────────────────────────────────────────────────
    const tileOptions = {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
        subdomains: 'abcd',
        maxZoom: 19,
    };
    const INITIAL_VIEW_CENTER = [35.74674, -96.70241];
    const INITIAL_VIEW_ZOOM = 5;
    const CONUS_DEFAULT_BOUNDS = [[17.81173, -143.8777], [50.4017, -49.52712]];
    const WORLD_DEFAULT_BOUNDS = [[-60, -179.9], [85, 179.9]];
    const REGION_FIT_BOTTOM_PADDING_PX = 120;

    const tilesDark = L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', tileOptions);
    const tilesLight = L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', tileOptions);
    const tilesDarkNoLabels = L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png', tileOptions);
    const tilesLightNoLabels = L.tileLayer('https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png', tileOptions);
    const tilesVoyager = L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', tileOptions);
    const tilesOsm = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>',
        maxZoom: 19,
    });
    const tilesSatellite = L.tileLayer(
        'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        {
            attribution: 'Tiles &copy; Esri',
            maxZoom: 19,
        },
    );

    const map = L.map('weather-map', { layers: [tilesDarkNoLabels] });
    map.setView(INITIAL_VIEW_CENTER, INITIAL_VIEW_ZOOM);

    const baseLayers = {
        'Dark': tilesDark,
        'Dark (No Labels)': tilesDarkNoLabels,
        'Light': tilesLight,
        'Light (No Labels)': tilesLightNoLabels,
        'Voyager': tilesVoyager,
        'OpenStreetMap': tilesOsm,
        'Satellite': tilesSatellite,
    };
    L.control.layers(baseLayers, {}, { position: 'topright' }).addTo(map);
    map.attributionControl.addAttribution('©2026 ChuckCopeland.com/NCHurricane.com');
    const LogoControl = L.Control.extend({
        options: { position: 'bottomright' },
        onAdd() {
            const div = L.DomUtil.create('div', 'leaflet-control-logo');
            const img = L.DomUtil.create('img', '', div);
            img.src = 'img/nchurricane_logo.png';
            img.alt = 'NCHurricane.com';
            img.style.height = '40px';       // adjust as needed
            img.loading = 'lazy';
            return div;
        },
    });
    new LogoControl().addTo(map);

    // ── Layer state ──────────────────────────────────────────────────────────
    let alertsLayer = null;
    let spcLayer = null;
    let surfaceLayer = null;
    let mrmsOverlay = null;
    let statesLayer = null;
    let countiesLayer = null;
    let countriesLayer = null;
    let citiesLayer = null;
    let _citiesData = null;
    let _citiesDensity = 1;
    let _surfaceDensity = 1;
    let _gradientBlurScale = 0.35;
    const CITY_LABEL_CHAR_PX = 5.2;
    const CITY_LABEL_HEIGHT_PX = 11;
    const CITY_LABEL_X_PAD = 4;
    const CITY_LABEL_Y_PAD = 2;
    let _allAlertFeatures = [];
    let alertsOpacity = 0.75;
    let spcOpacity = 0.60;
    let surfaceValueOpacity = 0.9;
    let surfaceGradientOpacity = 0.9;
    let mrmsOpacity = 0.8;
    let _alertsRequestSeq = 0;
    let _spcRequestSeq = 0;
    let _surfaceRequestSeq = 0;
    let _mrmsRequestSeq = 0;
    const _FREEZING_ISOTHERM_ENABLED = true; // temporary diagnostic overlay
    const _FREEZING_ISOTHERM_PRODUCTS = new Set(['station_plot', 'temperature', 'feels_like', 'dew_point']);

    // ── Style functions ──────────────────────────────────────────────────────
    function alertStyle(feat) {
        const color = ALERT_COLORS[feat?.properties?.event || ''] || ALERT_DEFAULT;
        return { color, weight: 1.5, fillColor: color, fillOpacity: alertsOpacity * 0.5, opacity: alertsOpacity };
    }

    function spcCatStyle(feat) {
        const label = (feat?.properties?.LABEL || feat?.properties?.label || '').toUpperCase();
        const c = SPC_CAT_COLORS[label] || { fill: '#aaaaaa', stroke: '#555' };
        return { color: c.stroke, weight: 1, fillColor: c.fill, fillOpacity: spcOpacity, opacity: 1 };
    }

    function spcFireStyle(feat) {
        const label = feat?.properties?.LABEL || feat?.properties?.label || '';
        const c = SPC_FIRE_COLORS[label] || { fill: '#aaaaaa', stroke: '#555' };
        return { color: c.stroke, weight: 1, fillColor: c.fill, fillOpacity: spcOpacity, opacity: 1 };
    }

    function spcProbStyle(feat) {
        const dn = String(feat?.properties?.dn || feat?.properties?.DN || '');
        const label = (feat?.properties?.LABEL || '').replace('%', '');
        const key = dn || label;
        const c = SPC_PROB_COLORS[key] || { fill: '#aaaaaa', stroke: '#555' };
        return { color: c.stroke, weight: 1, fillColor: c.fill, fillOpacity: spcOpacity, opacity: 1 };
    }

    // ── Popup builders ───────────────────────────────────────────────────────
    function alertPopup(feat) {
        const p = feat.properties || {};
        const event = p.event || 'Unknown Alert';
        const headline = p.headline || '';
        const expires = p.expires ? new Date(p.expires).toLocaleString() : '';
        const area = p.areaDesc || '';
        return `<strong>${event}</strong><br>${headline}${expires ? '<br><em>Expires: ' + expires + '</em>' : ''}<br><small>${area}</small>`;
    }

    function spcPopup(feat) {
        const p = feat.properties || {};
        const label = p.LABEL2 || p.label2 || p.LABEL || p.label || p.dn || '';
        return `<strong>${label}</strong>`;
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

    function swatch(color, label) {
        return `<div class="legend-row"><span class="legend-swatch" style="background:${color}"></span>${label}</div>`;
    }

    function _featureIntersectsBounds(feat, bounds) {
        try {
            const layer = L.geoJSON(feat);
            return layer.getBounds().intersects(bounds);
        } catch {
            return false;
        }
    }

    function buildAlertsLegend(features) {
        const bounds = map.getBounds();
        const inExtent = features.filter((f) => _featureIntersectsBounds(f, bounds));
        const counts = {};
        for (const f of inExtent) {
            const ev = f.properties?.event;
            if (ev) counts[ev] = (counts[ev] || 0) + 1;
        }
        const events = Object.keys(counts).sort((a, b) => a.localeCompare(b));
        if (!events.length) { setLegend(null); return; }
        const rows = events.map((e) => swatch(ALERT_COLORS[e] || ALERT_DEFAULT, `${e} (${counts[e]})`)).join('');
        const colClass = events.length > 25 ? 'legend-grid legend-grid-6'
            : events.length > 20 ? 'legend-grid legend-grid-5'
                : events.length > 15 ? 'legend-grid legend-grid-4'
                    : events.length > 10 ? 'legend-grid legend-grid-3'
                        : events.length > 5 ? 'legend-grid' : '';
        const wrap = colClass ? `<div class="${colClass}">${rows}</div>` : rows;
        setLegend('<h4>Alerts In View</h4>' + wrap);
    }

    function buildSpcCatLegend() {
        const rows = [
            ['#ff66ff', 'High'], ['#ff4f4f', 'Moderate'], ['#ff9d2e', 'Enhanced'],
            ['#f5dd72', 'Slight'], ['#69bb6d', 'Marginal'], ['#b5dcb3', 'T-Storms'],
        ].map(([c, l]) => swatch(c, l)).join('');
        setLegend('<h4>SPC Categorical</h4>' + rows);
    }

    function buildSpcFireLegend(hazard) {
        if (hazard === 'dryt') {
            const rows = [swatch('#FF8080', 'Scattered Dry T-Storm'), swatch('#FFBF80', 'Isolated Dry T-Storm')].join('');
            setLegend('<h4>SPC Fire Wx (Dry T-Storm)</h4>' + rows);
        } else {
            const rows = [swatch('#FF80FF', 'Extremely Critical'), swatch('#FF8080', 'Critical'), swatch('#FFBF80', 'Elevated')].join('');
            setLegend('<h4>SPC Fire Wx (Wind/RH)</h4>' + rows);
        }
    }

    // ── Data loaders ─────────────────────────────────────────────────────────
    function setStatus(msg) {
        const el = byId('weather-map-status');
        if (el) el.textContent = msg;
    }

    function _canApplyAlertsResponse() {
        return !_archiveMode
            && _isTypeEnabled('alerts')
            && _getCheckedAlertCategories().length > 0;
    }

    function _canApplySpcResponse() {
        return !_archiveMode
            && _isTypeEnabled('spc')
            && !!byId('weather-show-spc')?.checked;
    }

    function _canApplyMrmsResponse() {
        return !_archiveMode
            && _isTypeEnabled('mrms')
            && !!byId('weather-show-mrms')?.checked;
    }

    async function loadAlerts() {
        const requestSeq = ++_alertsRequestSeq;
        if (alertsLayer) { map.removeLayer(alertsLayer); alertsLayer = null; }
        const checkedCategories = _getCheckedAlertCategories();
        if (!checkedCategories.length) {
            _allAlertFeatures = [];
            const countEl = byId('weather-alerts-count');
            if (countEl) countEl.textContent = '0 active alert(s)';
            setLegend(null);
            return;
        }
        setStatus('Loading alerts...');
        try {
            const alertsUrl = `${apiUrl('/api/data/alerts')}${apiUrl('/api/data/alerts').includes('?') ? '&' : '?'}_ts=${Date.now()}`;
            const resp = await fetch(alertsUrl, { cache: 'no-store' });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const geojson = await resp.json();

            if (requestSeq !== _alertsRequestSeq || !_canApplyAlertsResponse()) return;

            const features = (geojson.features || []).filter(f => _matchesCheckedCategories(f, checkedCategories));
            _allAlertFeatures = features;
            alertsLayer = L.geoJSON({ type: 'FeatureCollection', features }, {
                style: alertStyle,
                onEachFeature: (feat, layer) => layer.bindPopup(alertPopup(feat)),
            });
            alertsLayer.addTo(map);
            buildAlertsLegend(features);

            const countEl = byId('weather-alerts-count');
            if (countEl) countEl.textContent = `${features.length} active alert(s)`;
            setStatus(`Alerts updated at ${new Date().toLocaleTimeString()}.`);
        } catch (err) {
            if (requestSeq !== _alertsRequestSeq) return;
            console.error('[alerts] Load error:', err);
            setStatus(`Alerts error: ${err.message}`);
        }
    }

    async function loadSpc(day, hazard) {
        const requestSeq = ++_spcRequestSeq;
        if (spcLayer) { map.removeLayer(spcLayer); spcLayer = null; }
        const isFireHazard = hazard === 'windrh' || hazard === 'dryt';
        setStatus(`Loading SPC day ${day} (${hazard})...`);
        try {
            const resp = await fetch(apiUrl(`/api/data/spc?day=${day}&hazard=${hazard}`));
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const geojson = await resp.json();

            if (requestSeq !== _spcRequestSeq || !_canApplySpcResponse()) return;

            const styleFn = isFireHazard ? spcFireStyle
                : hazard === 'prob' ? spcProbStyle
                    : spcCatStyle;

            spcLayer = L.geoJSON(geojson, {
                style: styleFn,
                filter: (feat) => isFireHazard
                    ? feat.properties?.dn !== 0
                    : true,
                onEachFeature: (feat, layer) => layer.bindPopup(spcPopup(feat)),
            });

            if (byId('weather-show-spc')?.checked) spcLayer.addTo(map);

            if (isFireHazard) buildSpcFireLegend(hazard);
            else if (hazard === 'cat') buildSpcCatLegend();
            else setLegend(null);

            const count = (geojson.features || []).length;
            const countEl = byId('weather-spc-count');
            if (countEl) countEl.textContent = `${count} feature(s)`;
            setStatus(`SPC day ${day} (${hazard}) updated at ${new Date().toLocaleTimeString()}.`);
        } catch (err) {
            if (requestSeq !== _spcRequestSeq) return;
            console.error('[spc] Load error:', err);
            setStatus(`SPC error: ${err.message}`);
        }
    }

    // ── Region → fitBounds ───────────────────────────────────────────────────
    function fitRegion(code) {
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
            });
        }
    }

    // ── Top type controls and product visibility ─────────────────────────────
    function _isTypeEnabled(type) {
        return !!byId(`weather-type-${type}`)?.checked;
    }

    function _activeSurfaceProduct() {
        const checked = Array.from(document.querySelectorAll('.weather-surface-product:checked'));
        if (!checked.length) return null;
        return checked[0].value || null;
    }

    function _activeSurfaceGradient() {
        const product = _activeSurfaceProduct();
        if (!product) return false;
        const el = document.querySelector(`.weather-surface-gradient[data-product="${product}"]`);
        return el?.checked ?? false;
    }

    function _readGradientBlurScale() {
        const raw = parseFloat(byId('weather-gradient-blur')?.value || '0.35');
        if (!Number.isFinite(raw)) return 0.35;
        return Math.max(0, Math.min(2, raw));
    }

    function _updateGradientBlurLabel() {
        const label = document.querySelector('label[for="weather-gradient-blur"]');
        if (!label) return;
        const baseLabel = label.dataset.baseLabel || 'Gradient Blur';
        label.dataset.baseLabel = baseLabel;
        label.textContent = `${baseLabel} (${_gradientBlurScale.toFixed(2)}x)`;
    }

    function _updateGradientBlurControlVisibility() {
        const wrap = byId('weather-gradient-blur-wrap');
        if (!wrap) return;
        const show = _isTypeEnabled('current') && _activeSurfaceGradient();
        wrap.style.display = show ? '' : 'none';
    }

    function _activeArchiveProduct() {
        const enabled = [];
        if (_isTypeEnabled('current') && _activeSurfaceProduct()) enabled.push('surface');
        if (_isTypeEnabled('mrms') && byId('weather-show-mrms')?.checked) enabled.push('mrms');
        if (_isTypeEnabled('alerts') && _getCheckedAlertCategories().length > 0) enabled.push('alerts');
        if (_isTypeEnabled('spc') && byId('weather-show-spc')?.checked) enabled.push('spc');
        if (enabled.length === 1) return enabled[0];
        if (enabled.includes('mrms')) return 'mrms';
        if (enabled.includes('alerts')) return 'alerts';
        if (enabled.includes('spc')) return 'spc';
        if (enabled.includes('surface')) return 'surface';
        return null;
    }

    function _updateTypeSections() {
        ['current', 'alerts', 'spc', 'mrms'].forEach((type) => {
            const section = byId(`wx-section-${type}`);
            if (section) section.style.display = _isTypeEnabled(type) ? '' : 'none';
        });
    }

    function _updateRightSidebarGroups() {
        const groups = ['current', 'alerts', 'spc', 'mrms'];
        let anyVisible = false;
        groups.forEach((type) => {
            const panel = byId(`wx-side-group-${type}`);
            if (!panel) return;
            const show = _isTypeEnabled(type);
            panel.style.display = show ? '' : 'none';
            if (show) anyVisible = true;
        });
        const empty = byId('wx-side-groups-empty');
        if (empty) empty.style.display = anyVisible ? 'none' : '';
    }

    function _updateSubOptionVisibility() {
        const spcOpts = byId('weather-spc-opts');
        if (spcOpts) spcOpts.style.display = byId('weather-show-spc')?.checked ? '' : 'none';

        const mrmsOpts = byId('weather-mrms-opts');
        if (mrmsOpts) mrmsOpts.style.display = byId('weather-show-mrms')?.checked ? '' : 'none';

        const surfaceOpts = byId('weather-surface-opts');
        if (surfaceOpts) surfaceOpts.style.display = '';

        const alertsOpts = byId('weather-alerts-opts');
        if (alertsOpts) alertsOpts.style.display = '';
    }

    function _clearAllMapLayers() {
        if (alertsLayer && map.hasLayer(alertsLayer)) map.removeLayer(alertsLayer);
        if (spcLayer && map.hasLayer(spcLayer)) map.removeLayer(spcLayer);
        if (surfaceLayer && map.hasLayer(surfaceLayer)) map.removeLayer(surfaceLayer);
        if (mrmsOverlay && map.hasLayer(mrmsOverlay)) map.removeLayer(mrmsOverlay);
        alertsLayer = null;
        spcLayer = null;
        surfaceLayer = null;
        mrmsOverlay = null;
        _surfaceStations = [];
        setLegend(null);
    }

    function refreshActiveLayers() {
        if (_archiveMode) return;
        const alertsEnabled = _isTypeEnabled('alerts') && _getCheckedAlertCategories().length > 0;
        const spcEnabled = _isTypeEnabled('spc') && byId('weather-show-spc')?.checked;
        const surfaceProduct = _activeSurfaceProduct();
        const surfaceEnabled = _isTypeEnabled('current') && !!surfaceProduct;
        const mrmsEnabled = _isTypeEnabled('mrms') && byId('weather-show-mrms')?.checked;

        // Clear legend at the start to ensure old legend doesn't persist when switching products
        setLegend(null);

        if (!alertsEnabled && alertsLayer && map.hasLayer(alertsLayer)) map.removeLayer(alertsLayer);
        if (!spcEnabled && spcLayer && map.hasLayer(spcLayer)) map.removeLayer(spcLayer);
        if (!surfaceEnabled && surfaceLayer && map.hasLayer(surfaceLayer)) map.removeLayer(surfaceLayer);
        if (!mrmsEnabled && mrmsOverlay && map.hasLayer(mrmsOverlay)) map.removeLayer(mrmsOverlay);

        if (alertsEnabled) {
            loadAlerts();
        }
        if (spcEnabled) {
            refreshSpc();
        }
        if (surfaceEnabled) {
            const region = byId('weather-region')?.value || 'NC';
            loadSurface(region, surfaceProduct || 'temperature');
        }
        if (mrmsEnabled) {
            loadMrms();
        }
    }

    // SPC: determine which dropdown was last used
    let _spcLastTouched = 'convective';

    function refreshSpc() {
        const day = parseInt(byId('weather-spc-day')?.value || '1', 10);
        let hazard;
        if (_spcLastTouched === 'fire') {
            hazard = byId('weather-spc-fire')?.value;
        } else {
            hazard = byId('weather-spc-convective')?.value;
        }
        if (hazard) loadSpc(day, hazard);
    }

    // ── Opacity helpers ──────────────────────────────────────────────────────
    function applyAlertsOpacity(val) {
        alertsOpacity = parseFloat(val);
        if (alertsLayer) alertsLayer.setStyle(alertStyle);
    }

    function applySpcOpacity(val) {
        spcOpacity = parseFloat(val);
        if (spcLayer) {
            const hazard = _spcLastTouched === 'fire'
                ? byId('weather-spc-fire')?.value || ''
                : byId('weather-spc-convective')?.value || '';
            const isFireHazard = hazard === 'windrh' || hazard === 'dryt';
            const styleFn = isFireHazard ? spcFireStyle
                : hazard === 'prob' ? spcProbStyle
                    : spcCatStyle;
            spcLayer.setStyle(styleFn);
        }
    }

    // ── Surface layer state ───────────────────────────────────────────────────
    let _surfaceStations = [];   // full unfiltered station list for re-thinning on zoom
    let _surfaceGradientStations = []; // cached source stations for gradient interpolation
    let _surfaceGradientProduct = null;
    let _surfaceGradientRegion = null;

    function _getGradientSourceRegion(regionCode = null) {
        const region = (regionCode || byId('weather-region')?.value || 'CONUS').toUpperCase();
        // WORLD should interpolate from WORLD observations, not CONUS.
        return region === 'WORLD' ? 'WORLD' : 'CONUS';
    }

    function surfaceColoredTextIcon(value, unit, opacity) {
        const label = unit === '°F' || unit === '%' || unit === 'kt'
            ? Math.round(value)
            : value.toFixed(1);
        const alpha = Math.max(0, Math.min(1, opacity));

        // Make value markers grow as zoom increases (reverse-responsive behavior).
        const zoom = map?.getZoom() ?? 5;
        const zoomMin = 5;
        const zoomMax = 9;
        const t = Math.max(0, Math.min(1, (zoom - zoomMin) / (zoomMax - zoomMin)));
        const fontSizePx = Math.round(16 + t * 22); // 16px @ z5 -> 38px @ z9+
        const strokePx = Math.max(1, Math.round(fontSizePx * 0.1));
        const iconWidth = Math.max(32, Math.round(fontSizePx * (label.length * 0.62 + 0.8)));
        const iconHeight = Math.max(20, Math.round(fontSizePx * 1.25));

        return L.divIcon({
            className: '',
            // Apply opacity at the element level so text fill and outline fade together.
            html: `<div style="opacity:${alpha};color:rgb(255,255,0);font-weight:800;font-size:${fontSizePx}px;line-height:1;font-family:Montserrat-ExtraBold, sans-serif;text-align:center;-webkit-text-stroke:${strokePx}px black;paint-order:stroke fill;">${label}</div>`,
            iconSize: [iconWidth, iconHeight],
            iconAnchor: [Math.round(iconWidth / 2), Math.round(iconHeight / 2)],
        });
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

    function _wrappedLonDeltaDeg(a, b) {
        const raw = Math.abs(a - b);
        return raw > 180 ? 360 - raw : raw;
    }

    function _haversineKmWrapped(lat1, lon1, lat2, lon2) {
        const R = 6371;
        const dLat = (lat2 - lat1) * Math.PI / 180;
        const dLon = _wrappedLonDeltaDeg(lon2, lon1) * Math.PI / 180;
        const phi1 = lat1 * Math.PI / 180;
        const phi2 = lat2 * Math.PI / 180;
        const a = Math.sin(dLat / 2) ** 2
            + Math.cos(phi1) * Math.cos(phi2) * Math.sin(dLon / 2) ** 2;
        return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    }

    // Returns base minimum separation (km) based on zoom level.
    // CONUS-level zooms use large defaults; state-level zooms use tighter ones.
    function _baseDistKm(zoom, regionCode = null) {
        const region = (regionCode || byId('weather-region')?.value || '').toUpperCase();
        // WORLD needs an additional coarse thinning tier due very dense global obs.
        if (region === 'WORLD') {
            if (zoom >= 9) return 20;
            if (zoom >= 7) return 40;
            if (zoom >= 5) return 60;
            if (zoom >= 3) return 420;
            return 320;
        }
        if (zoom >= 9) return 10;
        if (zoom >= 7) return 30;
        if (zoom >= 5) return 50;
        return 150;
    }

    // City labels need heavier thinning than station plots at the same zoom.
    function _baseCityDistKm(zoom) {
        if (zoom >= 9) return 30;
        if (zoom >= 7) return 60;
        if (zoom >= 5) return 150;
        return 180;
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

    function _thinStations(stations) {
        const zoom = map.getZoom();
        const region = (byId('weather-region')?.value || '').toUpperCase();
        const minDistKm = _baseDistKm(zoom, region) / _surfaceDensity;
        return _filterByMinDistKm(stations, s => s.lat, s => s.lon, minDistKm);
    }

    // Keep gradient interpolation denser than marker plots so large-scale fields
    // track station values more closely at low zoom/world extents.
    function _thinGradientStations(stations) {
        const zoom = map.getZoom();
        const region = (byId('weather-region')?.value || '').toUpperCase();
        // Gradient thinning is independent of the density slider so that the
        // interpolated surface stays stable when the user adjusts marker density.
        const baseKm = _baseDistKm(zoom, region);
        const factor = region === 'WORLD'
            ? (zoom <= 3 ? 0.42 : zoom <= 5 ? 0.40 : 0.38)
            : (zoom <= 5 ? 0.48 : 0.38);
        const floorKm = region === 'WORLD' ? (zoom <= 3 ? 16 : 14) : 12;
        const minDistKm = Math.max(floorKm, baseKm * factor);
        return _filterByMinDistKm(stations, s => s.lat, s => s.lon, minDistKm);
    }

    function _gradientNeighborConfig() {
        const zoom = map.getZoom();
        const region = (byId('weather-region')?.value || '').toUpperCase();
        if (region === 'WORLD') {
            if (zoom <= 3) {
                // Sector-balanced: 2 per 8 sectors → directionally fair selection.
                // Wide influence so sparse cold stations are reachable.
                return { maxNeighbors: 16, maxInfluenceKm: 1200, idwPower: 2.5, prefilterMultiplier: 1.3, sectorBalance: true };
            }
            if (zoom <= 5) {
                return { maxNeighbors: 16, maxInfluenceKm: 1000, idwPower: 2.5, prefilterMultiplier: 1.3, sectorBalance: true };
            }
            return { maxNeighbors: 12, maxInfluenceKm: 950, idwPower: 2.4, prefilterMultiplier: 1.2 };
        }
        if (zoom <= 5) return { maxNeighbors: 14, maxInfluenceKm: 900, idwPower: 2.0, prefilterMultiplier: 1.35 };
        return { maxNeighbors: 16, maxInfluenceKm: 1100, idwPower: 2.0, prefilterMultiplier: 1.35 };
    }

    function _gradientGridResolution() {
        const zoom = map.getZoom();
        const region = (byId('weather-region')?.value || '').toUpperCase();
        if (region === 'WORLD') {
            // WORLD default extent: larger cells to cap render cost.
            if (zoom <= 3) return 10;
            // Mid-world zoom: slightly coarser than regional views.
            if (zoom <= 5) return 15;
            // Higher world zoom: tighten grid for better local fidelity.
            return 10;
        }
        // Non-world low zoom: moderate coarsening for responsiveness.
        if (zoom <= 5) return 12;
        // Regional/state zoom: finer cells for best detail.
        return 10;
    }

    // ── Gradient Interpolation Functions ──────────────────────────────────────

    // ── Mercator helpers (match Leaflet's EPSG:3857 projection) ─────────────
    function _latToMercY(latDeg) {
        const latRad = latDeg * Math.PI / 180;
        return Math.log(Math.tan(Math.PI / 4 + latRad / 2));
    }
    function _mercYToLat(mercY) {
        return (2 * Math.atan(Math.exp(mercY)) - Math.PI / 2) * 180 / Math.PI;
    }

    /**
     * IDW (Inverse Distance Weighting) interpolation for a single point.
     * @param {number} x - target x (longitude)
     * @param {number} y - target y (latitude)
     * @param {Array} stations - array of {lat, lon, value}
     * @param {Object} cfg - pre-resolved config from _gradientNeighborConfig()
     * @returns {number} interpolated value
     */
    function _idwInterpolate(x, y, stations, cfg) {
        if (!stations.length) return NaN;

        const {
            maxNeighbors,
            maxInfluenceKm,
            idwPower = 2,
            prefilterMultiplier = 1.35,
            sectorBalance = false,
            _maxLatDeltaDeg,
            _prefilterKm,
        } = cfg;
        const nearStationKm = 8;
        const maxLatDeg = _maxLatDeltaDeg;
        const preKm = _prefilterKm;
        let fallbackApproxKm = Infinity;
        let fallbackValue = NaN;

        // Sector-balanced mode: maintain 8 angular sector buffers so that
        // sparse cold-latitude stations get equal representation against
        // dense warm-latitude clusters.
        const NUM_SECTORS = 8;
        const SECTOR_SIZE = (2 * Math.PI) / NUM_SECTORS;
        const perSector = Math.max(1, Math.ceil(maxNeighbors / NUM_SECTORS));
        const sectors = sectorBalance
            ? Array.from({ length: NUM_SECTORS }, () => [])
            : null;
        // Standard mode: flat nearest-N buffer.
        const nearest = sectorBalance ? null : [];

        const cosLat = Math.max(0.2, Math.cos(y * Math.PI / 180));

        for (const s of stations) {
            const latDelta = Math.abs(s.lat - y);
            if (latDelta > maxLatDeg) continue;

            const lonDelta = _wrappedLonDeltaDeg(s.lon, x);
            const approxKm = Math.sqrt(latDelta ** 2 + (lonDelta * cosLat) ** 2) * 111;

            // Fast prefilter before expensive trig distance.
            if (approxKm > preKm) {
                if (approxKm < fallbackApproxKm) {
                    fallbackApproxKm = approxKm;
                    fallbackValue = s.value;
                }
                continue;
            }

            if (approxKm < fallbackApproxKm) {
                fallbackApproxKm = approxKm;
                fallbackValue = s.value;
            }

            const distKm = _haversineKmWrapped(y, x, s.lat, s.lon);
            if (!Number.isFinite(distKm)) continue;
            if (distKm <= nearStationKm) return s.value;

            if (sectorBalance) {
                // Assign station to an angular compass sector.
                let dLon = s.lon - x;
                if (dLon > 180) dLon -= 360;
                if (dLon < -180) dLon += 360;
                let angle = Math.atan2(s.lat - y, dLon * cosLat);
                if (angle < 0) angle += 2 * Math.PI;
                const sIdx = Math.min(NUM_SECTORS - 1, Math.floor(angle / SECTOR_SIZE));

                const sector = sectors[sIdx];
                if (sector.length < perSector) {
                    sector.push({ distKm, value: s.value });
                } else {
                    let farIdx = 0;
                    for (let i = 1; i < sector.length; i++) {
                        if (sector[i].distKm > sector[farIdx].distKm) farIdx = i;
                    }
                    if (distKm < sector[farIdx].distKm) {
                        sector[farIdx] = { distKm, value: s.value };
                    }
                }
            } else {
                // Standard nearest-N selection.
                if (nearest.length < maxNeighbors) {
                    nearest.push({ distKm, value: s.value });
                    continue;
                }
                let farIdx = 0;
                let farDist = nearest[0].distKm;
                for (let i = 1; i < nearest.length; i++) {
                    if (nearest[i].distKm > farDist) {
                        farDist = nearest[i].distKm;
                        farIdx = i;
                    }
                }
                if (distKm < farDist) {
                    nearest[farIdx] = { distKm, value: s.value };
                }
            }
        }

        const finalNearest = sectorBalance ? sectors.flat() : nearest;

        if (!finalNearest.length) {
            return Number.isFinite(fallbackValue) ? fallbackValue : NaN;
        }

        let sumWeights = 0;
        let sumWeightedValues = 0;
        for (const item of finalNearest) {
            if (item.distKm > maxInfluenceKm) continue;
            const weight = 1 / (item.distKm ** idwPower);
            sumWeights += weight;
            sumWeightedValues += item.value * weight;
        }

        if (sumWeights > 0) return sumWeightedValues / sumWeights;

        // Fallback if all nearest stations were beyond influence radius.
        let best = finalNearest[0];
        for (let i = 1; i < finalNearest.length; i++) {
            if (finalNearest[i].distKm < best.distKm) best = finalNearest[i];
        }
        return best.value;
    }

    /**
     * Interpolate values on a grid across map bounds.
     * @param {Array} stations - array of {lat, lon, value}
     * @param {number} gridResolution - pixels per grid cell (lower = more detail but slower)
     * @returns {Object} {grid: 2D array, bounds: LatLngBounds, minVal, maxVal}
     */
    function _interpolateGridValues(stations, gridResolution = 0) {
        if (!stations.length) return null;

        const bounds = map.getBounds();
        const sw = bounds.getSouthWest();
        const ne = bounds.getNorthEast();

        const canvasSize = map.getSize();
        const cols = Math.ceil(canvasSize.x / gridResolution);
        const rows = Math.ceil(canvasSize.y / gridResolution);

        const lonRange = ne.lng - sw.lng;

        // Sample latitudes in Mercator Y space so canvas pixels align
        // with Leaflet's Web Mercator (EPSG:3857) projection.  Linear
        // latitude stepping causes an increasing northward shift at
        // high latitudes because Mercator stretches polar regions.
        const neMercY = _latToMercY(Math.min(ne.lat, 85));
        const swMercY = _latToMercY(Math.max(sw.lat, -85));
        const mercYRange = neMercY - swMercY;

        // Resolve config once for the entire grid rather than per-cell.
        const cfg = _gradientNeighborConfig();
        cfg._maxLatDeltaDeg = cfg.maxInfluenceKm / 111;
        cfg._prefilterKm = cfg.maxInfluenceKm * (cfg.prefilterMultiplier || 1.35);

        const grid = [];
        let minVal = Infinity;
        let maxVal = -Infinity;

        for (let row = 0; row < rows; row++) {
            const gridRow = [];
            const mercY = neMercY - (row / rows) * mercYRange;
            const lat = _mercYToLat(mercY);

            for (let col = 0; col < cols; col++) {
                const lon = sw.lng + (col / cols) * lonRange;
                const val = _idwInterpolate(lon, lat, stations, cfg);

                if (!isNaN(val)) {
                    gridRow.push(val);
                    minVal = Math.min(minVal, val);
                    maxVal = Math.max(maxVal, val);
                } else {
                    gridRow.push(null);
                }
            }
            grid.push(gridRow);
        }

        return { grid, bounds, minVal, maxVal, cols, rows };
    }

    /**
     * Map a value to a color using the current surface colormap anchors.
     * @param {number} value - data value
     * @param {number} minVal - minimum value in dataset
     * @param {number} maxVal - maximum value in dataset
     * @param {string} product - product key (e.g., 'temperature')
     * @returns {string} hex color
     */
    function _getColorAtValue(value, minVal, maxVal, product) {
        const anchors = _SURFACE_COLORMAPS[product] || _SURFACE_COLORMAPS['temperature'];
        if (!anchors.length) return '#cccccc';

        const min = anchors[0][0];
        const max = anchors[anchors.length - 1][0];

        // Clamp value to colormap range
        const clampedVal = Math.max(min, Math.min(max, value));

        // Find surrounding anchor colors
        for (let i = 0; i < anchors.length - 1; i++) {
            const [v0, c0] = anchors[i];
            const [v1, c1] = anchors[i + 1];

            if (clampedVal >= v0 && clampedVal <= v1) {
                if (v1 === v0) return c0;
                const frac = (clampedVal - v0) / (v1 - v0);
                return _interpolateHexColor(c0, c1, frac);
            }
        }

        return anchors[anchors.length - 1][1];
    }

    /**
     * Interpolate between two hex colors.
     * @param {string} hex1 - start color (e.g., '#ff0000')
     * @param {string} hex2 - end color
     * @param {number} frac - interpolation factor [0, 1]
     * @returns {string} interpolated hex color
     */
    function _interpolateHexColor(hex1, hex2, frac) {
        const h1 = hex1.replace('#', '');
        const h2 = hex2.replace('#', '');

        const r = parseInt(h1.substr(0, 2), 16);
        const g = parseInt(h1.substr(2, 2), 16);
        const b = parseInt(h1.substr(4, 2), 16);

        const r2 = parseInt(h2.substr(0, 2), 16);
        const g2 = parseInt(h2.substr(2, 2), 16);
        const b2 = parseInt(h2.substr(4, 2), 16);

        const newR = Math.round(r + (r2 - r) * frac);
        const newG = Math.round(g + (g2 - g) * frac);
        const newB = Math.round(b + (b2 - b) * frac);

        return `#${newR.toString(16).padStart(2, '0')}${newG.toString(16).padStart(2, '0')}${newB.toString(16).padStart(2, '0')}`;
    }

    function _drawIsothermFromGrid(ctx, grid, cols, rows, cellWidth, cellHeight, thresholdF) {
        const lerpPoint = (a, b, va, vb) => {
            if (va === vb) return [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
            const t = (thresholdF - va) / (vb - va);
            return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
        };

        ctx.save();
        ctx.strokeStyle = 'rgba(0, 22, 122, 0.9)';
        ctx.lineWidth = 0.75;
        ctx.lineJoin = 'round';
        ctx.lineCap = 'round';
        ctx.beginPath();

        for (let row = 0; row < rows - 1; row++) {
            for (let col = 0; col < cols - 1; col++) {
                const v00 = grid[row][col];
                const v10 = grid[row][col + 1];
                const v01 = grid[row + 1][col];
                const v11 = grid[row + 1][col + 1];

                if (![v00, v10, v01, v11].every(v => Number.isFinite(v))) continue;

                const x0 = col * cellWidth;
                const y0 = row * cellHeight;
                const x1 = (col + 1) * cellWidth;
                const y1 = (row + 1) * cellHeight;

                const pTopL = [x0, y0];
                const pTopR = [x1, y0];
                const pBotL = [x0, y1];
                const pBotR = [x1, y1];

                const points = [];
                const crosses = (a, b) => (a - thresholdF) * (b - thresholdF) <= 0 && a !== b;

                if (crosses(v00, v10)) points.push(lerpPoint(pTopL, pTopR, v00, v10));
                if (crosses(v10, v11)) points.push(lerpPoint(pTopR, pBotR, v10, v11));
                if (crosses(v01, v11)) points.push(lerpPoint(pBotL, pBotR, v01, v11));
                if (crosses(v00, v01)) points.push(lerpPoint(pTopL, pBotL, v00, v01));

                if (points.length === 2) {
                    ctx.moveTo(points[0][0], points[0][1]);
                    ctx.lineTo(points[1][0], points[1][1]);
                } else if (points.length === 4) {
                    ctx.moveTo(points[0][0], points[0][1]);
                    ctx.lineTo(points[1][0], points[1][1]);
                    ctx.moveTo(points[2][0], points[2][1]);
                    ctx.lineTo(points[3][0], points[3][1]);
                }
            }
        }

        ctx.stroke();
        ctx.restore();
    }

    /**
     * Render an interpolated gradient surface on canvas.
     * @param {Array} stations - array of {lat, lon, value}
     * @param {string} product - product key for colormap
     */
    function _renderGradientSurface(stations, product) {
        if (!stations.length) return null;

        // Use denser thinning for interpolation than for markers.
        const thin = _thinGradientStations(stations);
        if (!thin.length) return null;

        // Interpolate grid values
        const gridResolution = _gradientGridResolution();
        const gridData = _interpolateGridValues(thin, gridResolution);
        if (!gridData) return null;

        const { grid, bounds, minVal, maxVal, cols, rows } = gridData;

        // Create canvas
        const canvas = document.createElement('canvas');
        const canvasSize = map.getSize();
        canvas.width = canvasSize.x;
        canvas.height = canvasSize.y;

        const ctx = canvas.getContext('2d');
        const cellWidth = canvas.width / cols;
        const cellHeight = canvas.height / rows;

        // Render gradient cells to an offscreen canvas, then composite with
        // a Gaussian blur to eliminate hard cell-boundary seams (vertical lines).
        const offscreen = document.createElement('canvas');
        offscreen.width = canvas.width;
        offscreen.height = canvas.height;
        const offCtx = offscreen.getContext('2d');

        for (let row = 0; row < rows; row++) {
            for (let col = 0; col < cols; col++) {
                const val = grid[row][col];
                if (val !== null && !isNaN(val)) {
                    offCtx.fillStyle = _getColorAtValue(val, minVal, maxVal, product);
                    offCtx.fillRect(col * cellWidth, row * cellHeight, Math.ceil(cellWidth), Math.ceil(cellHeight));
                }
            }
        }

        // Blur radius ~= cell size to fully dissolve seams
        const blurPx = Math.round(Math.max(cellWidth, cellHeight) * 1.2 * _gradientBlurScale);
        ctx.filter = blurPx > 0 ? `blur(${blurPx}px)` : 'none';
        ctx.globalAlpha = Math.max(0, Math.min(1, surfaceGradientOpacity));
        ctx.drawImage(offscreen, 0, 0);
        ctx.filter = 'none';
        ctx.globalAlpha = 1.0;

        // Temporary 32F isotherm line for gradient diagnostics.
        if (_FREEZING_ISOTHERM_ENABLED && _FREEZING_ISOTHERM_PRODUCTS.has(product)) {
            _drawIsothermFromGrid(ctx, grid, cols, rows, cellWidth, cellHeight, 32);
        }

        // Convert canvas to ImageOverlay and return it
        const imageUrl = canvas.toDataURL();
        return L.imageOverlay(imageUrl, bounds, {
            opacity: 1.0,
            className: 'surface-gradient-overlay'
        });
    }

    function _renderSurfaceMarkers(stations) {
        if (surfaceLayer) { map.removeLayer(surfaceLayer); surfaceLayer = null; }
        if (!stations.length) return;

        const product = _activeSurfaceProduct();
        if (!product) return;

        // Build layer group containing gradient (if enabled) + markers
        const layers = [];

        // Add gradient background if enabled
        if (_activeSurfaceGradient()) {
            const currentRegion = (byId('weather-region')?.value || 'CONUS').toUpperCase();
            const gradientSourceRegion = _getGradientSourceRegion(currentRegion);
            const gradientStations = _archiveMode
                ? stations
                : (
                    _surfaceGradientProduct === product
                        && _surfaceGradientRegion === gradientSourceRegion
                        && _surfaceGradientStations.length
                        ? _surfaceGradientStations
                        : stations
                );
            const gradientLayer = gradientStations.length
                ? _renderGradientSurface(gradientStations, product)
                : null;
            if (gradientLayer) {
                layers.push(gradientLayer);
            }
        }

        // Add colored text value markers (works for both gradient and standard modes)
        const thin = _thinStations(stations);
        const markerGroup = L.layerGroup(
            thin.map(s => {
                const icon = surfaceColoredTextIcon(s.value, s.unit, surfaceValueOpacity);
                const m = L.marker([s.lat, s.lon], { icon });
                const wdir = s.wind_dir != null ? `${Math.round(s.wind_dir)}°` : '—';
                const wspd = s.wind_speed != null ? `${Math.round(s.wind_speed)} kt` : '—';
                const gust = s.wind_gust != null ? ` G${Math.round(s.wind_gust)}` : '';
                const vis = s.visibility != null ? `${s.visibility} mi` : '—';
                const stationName = s.name ? `${s.name} (${s.id})` : s.id;
                const stationId = String(s.id || '').trim().toUpperCase();
                const timeseriesSite = stationId.length === 3 ? `K${stationId}` : stationId;
                const timeseriesUrl = `https://www.weather.gov/wrh/timeseries?site=${encodeURIComponent(timeseriesSite)}`;
                m.bindPopup(
                    `<strong>${stationName}</strong><br>` +
                    `Temp: ${s.temperature != null ? s.temperature + '°F' : '—'}<br>` +
                    `Feels Like: ${s.feels_like != null ? s.feels_like + '°F' : '—'}<br>` +
                    `Dew Point: ${s.dew_point != null ? s.dew_point + '°F' : '—'}<br>` +
                    `RH: ${s.rh != null ? s.rh + '%' : '—'}<br>` +
                    `Wind: ${wdir} @ ${wspd}${gust}<br>` +
                    `Visibility: ${vis}<br>` +
                    `<a href="${timeseriesUrl}" target="_blank" rel="noopener" style="color:#7dd3fc;text-decoration:none;">View Time Series</a>`
                );
                return m;
            })
        );
        layers.push(markerGroup);

        // Combine all layers into a single layer group
        surfaceLayer = L.layerGroup(layers);
        if (_isTypeEnabled('current') && _activeSurfaceProduct()) {
            surfaceLayer.addTo(map);
        }
    }

    async function _ensureGradientStations(product, regionCode = null) {
        if (_archiveMode || !product) return;
        const sourceRegion = _getGradientSourceRegion(regionCode);
        if (
            _surfaceGradientProduct === product
            && _surfaceGradientRegion === sourceRegion
            && _surfaceGradientStations.length
        ) {
            return;
        }

        try {
            const url = apiUrl(`/api/data/surface?region=${encodeURIComponent(sourceRegion)}&product=${encodeURIComponent(product)}`);
            const resp = await fetch(url);
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json();
            const allStations = Array.isArray(data?.stations) ? data.stations : [];
            // Use ASOS-only for gradient interpolation — more reliable sensors,
            // fewer outliers from COOP/DCP/RWIS that can distort the surface.
            _surfaceGradientStations = allStations.filter(s => (s.network || 'ASOS') === 'ASOS');
            _surfaceGradientProduct = product;
            _surfaceGradientRegion = sourceRegion;
        } catch (err) {
            console.warn(`[surface] ${sourceRegion} gradient source unavailable, falling back to regional stations:`, err);
        }
    }

    function _canApplySurfaceResponse(region, product) {
        return !_archiveMode
            && _isTypeEnabled('current')
            && _activeSurfaceProduct() === product
            && (byId('weather-region')?.value || '').toUpperCase() === String(region || '').toUpperCase();
    }

    async function loadSurface(region, product) {
        const requestSeq = ++_surfaceRequestSeq;
        setStatus(`Loading surface ${product} for ${region}...`);
        try {
            const url = apiUrl(`/api/data/surface?region=${encodeURIComponent(region)}&product=${encodeURIComponent(product)}`);
            const resp = await fetch(url);
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json();

            // Ignore stale responses that complete after product/tab changes.
            if (requestSeq !== _surfaceRequestSeq || !_canApplySurfaceResponse(region, product)) return;

            _surfaceStations = data.stations || [];
            if (_activeSurfaceGradient()) {
                await _ensureGradientStations(product, region);
                if (requestSeq !== _surfaceRequestSeq || !_canApplySurfaceResponse(region, product)) return;
            }
            _renderSurfaceMarkers(_surfaceStations);

            // Legend
            const anchors = _SURFACE_COLORMAPS[product] || _SURFACE_COLORMAPS['temperature'];
            buildSurfaceLegend(data.unit || '°F', anchors, product);

            const countEl = byId('weather-surface-count');
            if (countEl) countEl.textContent = `${_surfaceStations.length} station(s)`;
            setStatus(`Surface ${product} updated at ${new Date().toLocaleTimeString()}.`);
        } catch (err) {
            if (requestSeq !== _surfaceRequestSeq) return;
            console.error('[surface] Load error:', err);
            setStatus(`Surface error: ${err.message}`);
        }
    }

    // Client-side colormap anchors for the legend (mirror of server-side _SURFACE_PRODUCTS)
    const _SURFACE_COLORMAPS = {
        station_plot: [[-60, '#00352C'], [-20, '#c4c4d4'], [0, '#570057'], [32, '#0000ff'], [50, '#c4c403'], [80, '#c20303'], [130, '#000000']],
        temperature: [[-60, '#00352C'], [-20, '#c4c4d4'], [0, '#570057'], [32, '#0000ff'], [50, '#c4c403'], [80, '#c20303'], [130, '#000000']],
        feels_like: [[-60, '#00352C'], [-20, '#c4c4d4'], [0, '#570057'], [32, '#0000ff'], [50, '#c4c403'], [80, '#c20303'], [130, '#000000']],
        dew_point: [[-60, '#00352C'], [-20, '#c4c4d4'], [0, '#570057'], [32, '#0000ff'], [50, '#c4c403'], [80, '#c20303'], [130, '#000000']],
        relative_humidity: [[0, '#c8a000'], [20, '#f5dd72'], [40, '#69bb6d'], [60, '#0099cc'], [80, '#0055aa'], [100, '#003377']],
        wind_speed: [[0, '#b0d4f0'], [10, '#70b0e0'], [20, '#3090d0'], [30, '#f5dd72'], [45, '#ff9d2e'], [60, '#ff4f4f']],
        wind_gust: [[0, '#b0d4f0'], [10, '#70b0e0'], [20, '#3090d0'], [30, '#f5dd72'], [45, '#ff9d2e'], [60, '#ff4f4f']],
        altimeter: [[29.5, '#5b1a8f'], [30.0, '#2a6db3'], [30.2, '#2ca58d'], [30.4, '#f5dd72'], [30.6, '#ff9d2e'], [30.8, '#bf2c2c']],
        mslp: [[990, '#5b1a8f'], [1000, '#2a6db3'], [1010, '#2ca58d'], [1020, '#f5dd72'], [1030, '#ff9d2e'], [1040, '#bf2c2c']],
        visibility: [[0, '#7f1d1d'], [1, '#b45309'], [3, '#d97706'], [5, '#65a30d'], [7, '#16a34a'], [10, '#0ea5e9']],
    };

    const _SURFACE_PRODUCT_LABELS = {
        temperature: 'Temperature',
        feels_like: 'Feels Like',
        dew_point: 'Dew Point',
        relative_humidity: 'Relative Humidity',
        wind_speed: 'Wind Speed',
        wind_gust: 'Wind Gust',
        altimeter: 'Altimeter',
        mslp: 'MSLP',
        visibility: 'Visibility',
    };

    function _formatSurfaceTick(value) {
        return Number.isInteger(value) ? String(value) : value.toFixed(1);
    }

    function buildSurfaceLegend(unit, anchors, product) {
        if (!anchors?.length) {
            setLegend(null);
            return;
        }

        const label = _SURFACE_PRODUCT_LABELS[product] || product.replace(/_/g, ' ');
        const min = anchors[0][0];
        const max = anchors[anchors.length - 1][0];
        const range = Math.max(1, max - min);
        const gradient = anchors.map(([value, color]) => {
            const pct = ((value - min) / range) * 100;
            return `${color} ${pct.toFixed(2)}%`;
        }).join(', ');
        const ticks = anchors.map(([value]) => (
            `<span>${_formatSurfaceTick(value)}</span>`
        )).join('');
        const axisLabel = unit ? `${label} (${unit})` : label;

        setLegend(
            `<h4>Surface: ${label}</h4>` +
            `<div class="surface-colorbar">` +
            `<div class="surface-colorbar-bar" style="background: linear-gradient(to right, ${gradient});"></div>` +
            `<div class="surface-colorbar-ticks">${ticks}</div>` +
            `<div class="surface-colorbar-label">${axisLabel}</div>` +
            `</div>`
        );
    }

    function applySurfaceValueOpacity(val) {
        surfaceValueOpacity = parseFloat(val);
        // Re-render markers/values with new opacity baked into rendering
        if (_surfaceStations.length) _renderSurfaceMarkers(_surfaceStations);
    }

    function applySurfaceGradientOpacity(val) {
        surfaceGradientOpacity = parseFloat(val);
        // Re-render gradient with new opacity baked into rendering
        if (_surfaceStations.length) _renderSurfaceMarkers(_surfaceStations);
    }

    // Re-thin on zoom change if surface layer is active
    map.on('zoomend', () => {
        _updateObsDensityLabel();
        _updateCitiesDensityLabel();
        _refreshCitiesIfVisible();
        if (_surfaceStations.length && _isTypeEnabled('current') && _activeSurfaceProduct()) {
            _renderSurfaceMarkers(_surfaceStations);
        }
    });

    // ── MRMS layer ────────────────────────────────────────────────────────────

    // composeMrmsProductKey: mirrors Python MRMS_PRODUCTS key structure
    function composeMrmsProductKey() {
        const family = byId('weather-mrms-family')?.value || 'PrecipFlag';
        // Standalone products (no sub-selector)
        const standalone = ['PrecipRate', 'PrecipFlag', 'SHI', 'POSH', 'RadarQualityIndex'];
        if (standalone.includes(family)) return family;

        if (family === 'QPE') {
            const src = byId('mrms-qpe-source')?.value || 'MS2';
            const per = byId('mrms-qpe-period')?.value || '01H';
            return `QPE_${src}_${per}`;
        }
        if (family === 'RotationTrack') {
            const lvl = byId('mrms-rotation-level')?.value || 'LL';
            const time = byId('mrms-rotation-time')?.value || '60min';
            return `RotationTrack_${lvl}_${time}`;
        }
        if (family === 'MESH') {
            const t = byId('mrms-mesh-time')?.value || 'Instant';
            return t === 'Instant' ? 'MESH_Instant' : `MESH_${t}`;
        }
        if (family === 'AzShear') {
            const lvl = byId('mrms-azshear-level')?.value || 'Low';
            return `AzShear_${lvl}`;
        }
        if (family === 'EchoTop') {
            const thr = byId('mrms-echotop-threshold')?.value || '18';
            return `EchoTop_${thr}`;
        }
        if (family === 'VIL') {
            const t = byId('mrms-vil-type')?.value || 'Instant';
            return t === 'Instant' ? 'VIL' : `VIL_${t}`;
        }
        if (family === 'Reflectivity') {
            const v = byId('mrms-refl-variant')?.value || 'HSR';
            return `Reflectivity_${v}`;
        }
        if (family === 'Lightning') {
            const w = byId('mrms-lightning-window')?.value || '30min';
            return `LightningProbability_${w}`;
        }
        if (family === 'Model') {
            const f = byId('mrms-model-field')?.value || 'FreezingLevel';
            return `Model_${f}`;
        }
        return family;
    }

    // Show/hide sub-selectors for the selected MRMS family
    function updateMrmsSubControls() {
        const family = byId('weather-mrms-family')?.value || 'PrecipFlag';
        const subMap = {
            QPE: 'mrms-sub-qpe', RotationTrack: 'mrms-sub-rotation',
            MESH: 'mrms-sub-mesh', AzShear: 'mrms-sub-azshear',
            EchoTop: 'mrms-sub-echotop', VIL: 'mrms-sub-vil',
            Reflectivity: 'mrms-sub-reflectivity', Lightning: 'mrms-sub-lightning',
            Model: 'mrms-sub-model',
        };
        document.querySelectorAll('.mrms-sub').forEach(el => { el.style.display = 'none'; });
        const subId = subMap[family];
        if (subId) {
            const sub = byId(subId);
            if (sub) sub.style.display = '';
        }
    }

    async function loadMrms() {
        const requestSeq = ++_mrmsRequestSeq;
        const product = composeMrmsProductKey();
        const bounds = map.getBounds();
        const s = bounds.getSouth().toFixed(4);
        const w = bounds.getWest().toFixed(4);
        const n = bounds.getNorth().toFixed(4);
        const e = bounds.getEast().toFixed(4);

        const statusEl = byId('weather-mrms-status');
        if (statusEl) statusEl.textContent = `Loading ${product}...`;
        setStatus(`Loading MRMS ${product}...`);

        try {
            const url = apiUrl(`/api/data/mrms?product=${encodeURIComponent(product)}&south=${s}&west=${w}&north=${n}&east=${e}`);
            const resp = await fetch(url);
            if (!resp.ok) {
                const err = await resp.json().catch(() => ({ detail: resp.statusText }));
                throw new Error(err.detail || resp.statusText);
            }
            const data = await resp.json();

            if (requestSeq !== _mrmsRequestSeq || !_canApplyMrmsResponse()) return;

            if (mrmsOverlay) { map.removeLayer(mrmsOverlay); mrmsOverlay = null; }

            // Leaflet imageOverlay: [[south, west], [north, east]]
            const b = data.bounds; // [west, east, south, north]
            const leafletBounds = [[b[2], b[0]], [b[3], b[1]]];
            mrmsOverlay = L.imageOverlay(data.image_url, leafletBounds, { opacity: mrmsOpacity });
            if (byId('weather-show-mrms')?.checked) mrmsOverlay.addTo(map);

            buildMrmsLegend(data);

            if (statusEl) statusEl.textContent = `${data.full_name} at ${new Date().toLocaleTimeString()}`;
            setStatus(`MRMS ${product} updated at ${new Date().toLocaleTimeString()}.`);
        } catch (err) {
            if (requestSeq !== _mrmsRequestSeq) return;
            console.error('[mrms] Load error:', err);
            if (statusEl) statusEl.textContent = `Error: ${err.message}`;
            setStatus(`MRMS error: ${err.message}`);
        }
    }

    function buildMrmsLegend(data) {
        // Simple min/max legend bar; colormap-specific entries added in Phase 4
        const rows = [
            swatch('#b0d4f0', `≤ ${data.vmin} ${data.units}`),
            swatch('#ff4f4f', `≥ ${data.vmax} ${data.units}`),
        ].join('');
        setLegend(`<h4>${data.full_name}</h4>${rows}`);
    }

    function applyMrmsOpacity(val) {
        mrmsOpacity = parseFloat(val);
        if (mrmsOverlay) mrmsOverlay.setOpacity(mrmsOpacity);
    }

    // ── Event wiring ─────────────────────────────────────────────────────────
    // ── Phase 4: Archive Mode + Scrubber ─────────────────────────────────────

    let _archiveMode = false;
    let _archiveFrames = [];
    let _archiveFrameIndex = 0;
    let _archivePlayTimer = null;
    let _archiveSessionId = null;
    let _archiveProductType = null;
    let _archiveSurfaceProduct = 'temperature';
    const ARCHIVE_PLAY_INTERVAL_MS = 800;

    function enterArchiveMode() {
        _archiveMode = true;
        _clearAllMapLayers();
        const fromEl = byId('archive-from');
        const toEl = byId('archive-to');
        if (fromEl && toEl && !fromEl.value && !toEl.value) {
            _applyArchivePreset(3);
        }
        const curTab = byId('weather-mode-current');
        const arcTab = byId('weather-mode-archive');
        if (curTab) curTab.classList.remove('active');
        if (arcTab) arcTab.classList.add('active');
        const acts = byId('wx-archive-actions');
        if (acts) acts.style.display = 'block';
    }

    function _applyArchivePreset(hours) {
        const fromEl = byId('archive-from');
        const toEl = byId('archive-to');
        if (!fromEl || !toEl) return;
        const group = _activeArchiveProduct();
        const to = new Date();
        const from = new Date(to.getTime() - hours * 60 * 60 * 1000);
        if (group === 'surface') {
            toEl.value = _snapToHour(_toLocalDatetimeInput(to), 'floor');
            fromEl.value = _snapToHour(_toLocalDatetimeInput(from), 'floor');
        } else {
            toEl.value = _toLocalDatetimeInput(to);
            fromEl.value = _toLocalDatetimeInput(from);
        }
        _setActivePreset(String(hours));
    }

    function _applyArchiveSnapshot() {
        const fromEl = byId('archive-from');
        const toEl = byId('archive-to');
        if (!fromEl) return;
        const now = new Date();
        const group = _activeArchiveProduct();
        if (group === 'surface') {
            fromEl.value = _snapToHour(_toLocalDatetimeInput(now), 'floor');
        } else {
            fromEl.value = _toLocalDatetimeInput(now);
        }
        if (toEl) toEl.value = '';
        _setActivePreset('snapshot');
    }

    function _setActivePreset(value) {
        const btns = document.querySelectorAll('.wx-preset-btn');
        btns.forEach((btn) => {
            btn.classList.toggle('active', btn.dataset.hours === value);
        });
    }

    function _toLocalDatetimeInput(d) {
        const local = new Date(d.getTime() - d.getTimezoneOffset() * 60000);
        return local.toISOString().slice(0, 16);
    }

    function _toArchiveApiDatetime(localValue) {
        if (!localValue) return '';
        const localDate = new Date(localValue);
        if (Number.isNaN(localDate.getTime())) return '';
        const pad2 = (n) => String(n).padStart(2, '0');
        const yyyy = localDate.getFullYear();
        const mm = pad2(localDate.getMonth() + 1);
        const dd = pad2(localDate.getDate());
        const hh = pad2(localDate.getHours());
        const mi = pad2(localDate.getMinutes());
        const ss = pad2(localDate.getSeconds());

        // getTimezoneOffset is minutes behind UTC (e.g. EDT = 240).
        const tzMinutes = -localDate.getTimezoneOffset();
        const sign = tzMinutes >= 0 ? '+' : '-';
        const tzAbs = Math.abs(tzMinutes);
        const tzH = pad2(Math.floor(tzAbs / 60));
        const tzM = pad2(tzAbs % 60);
        const tz = `${sign}${tzH}:${tzM}`;

        // Example: 2026-04-16T19:00:00-04:00 (no fractional seconds)
        return `${yyyy}-${mm}-${dd}T${hh}:${mi}:${ss}${tz}`;
    }

    /**
     * Snap a datetime-local input value to the top of the hour.
     * direction: 'floor' rounds down, 'ceil' rounds up (only if minutes > 0).
     * Returns a string suitable for datetime-local input, or '' on failure.
     */
    function _snapToHour(localValue, direction = 'floor') {
        if (!localValue) return '';
        const d = new Date(localValue);
        if (Number.isNaN(d.getTime())) return '';
        if (d.getMinutes() !== 0 || d.getSeconds() !== 0) {
            d.setSeconds(0, 0);
            if (direction === 'ceil') {
                d.setMinutes(0);
                d.setHours(d.getHours() + 1);
            } else {
                d.setMinutes(0);
            }
        }
        return _toLocalDatetimeInput(d);
    }

    function exitArchiveMode() {
        stopScrubberPlay();
        _archiveMode = false;
        _archiveFrames = [];
        _archiveFrameIndex = 0;
        _archiveSessionId = null;
        _archiveProductType = null;

        _setArchiveProgress(false);
        _setArchiveScrubber(false);

        const curTab = byId('weather-mode-current');
        const arcTab = byId('weather-mode-archive');
        if (curTab) curTab.classList.add('active');
        if (arcTab) arcTab.classList.remove('active');
        const acts = byId('wx-archive-actions');
        if (acts) acts.style.display = 'none';

        refreshActiveLayers();   // reload live data
    }

    function _setArchiveProgress(visible, pct, msg) {
        const row = byId('archive-progress-row');
        if (!row) return;
        row.style.display = visible ? '' : 'none';
        if (visible) {
            const fill = byId('archive-progress-fill');
            const text = byId('archive-progress-text');
            if (fill) fill.style.width = `${pct || 0}%`;
            if (text) text.textContent = msg || '';
        }
    }

    function _setArchiveScrubber(visible) {
        const row = byId('archive-scrubber-row');
        if (row) row.style.display = visible ? '' : 'none';
    }

    function _wireSidebarToggle(sideId, buttonId, expandedSymbol, collapsedSymbol) {
        const side = byId(sideId);
        const btn = byId(buttonId);
        if (!side || !btn) return;

        const updateButton = () => {
            const expanded = !side.classList.contains('collapsed');
            btn.textContent = expanded ? expandedSymbol : collapsedSymbol;
            btn.setAttribute('aria-expanded', expanded ? 'true' : 'false');
        };

        btn.addEventListener('click', () => {
            side.classList.toggle('collapsed');
            updateButton();
        });

        updateButton();
    }

    function _updateScrubberUI() {
        const slider = byId('scrubber-slider');
        const tsEl = byId('scrubber-timestamp');
        const cntEl = byId('scrubber-frame-count');
        const n = _archiveFrames.length;
        if (slider) {
            slider.max = String(n > 0 ? n - 1 : 0);
            slider.value = String(_archiveFrameIndex);
        }
        if (cntEl) cntEl.textContent = n > 0 ? `${_archiveFrameIndex + 1}/${n}` : '';
        if (tsEl && n > 0) {
            const frame = _archiveFrames[_archiveFrameIndex];
            if (frame?.timestamp) {
                try {
                    tsEl.textContent = new Date(frame.timestamp).toLocaleString(
                        undefined, {
                        month: 'short', day: 'numeric', hour: '2-digit',
                        minute: '2-digit', timeZoneName: 'short'
                    }
                    );
                } catch { tsEl.textContent = frame.timestamp; }
            } else {
                tsEl.textContent = '—';
            }
        }
    }

    function renderArchiveFrame(idx) {
        if (!_archiveFrames.length) return;
        _archiveFrameIndex = Math.max(0, Math.min(idx, _archiveFrames.length - 1));
        const frame = _archiveFrames[_archiveFrameIndex];
        _updateScrubberUI();

        if (_archiveProductType === 'mrms') {
            _renderArchiveMrmsFrame(frame);
        } else if (_archiveProductType === 'alerts') {
            _renderArchiveGeoJsonFrame(frame, 'alerts');
        } else if (_archiveProductType === 'spc') {
            _renderArchiveGeoJsonFrame(frame, 'spc');
        } else if (_archiveProductType === 'surface') {
            _renderArchiveSurfaceFrame(frame);
        }
        _preloadArchiveNeighbors(_archiveFrameIndex);
    }

    function _preloadArchiveNeighbors(idx) {
        if (_archiveProductType !== 'mrms') return;
        [idx - 1, idx + 1, idx + 2].forEach((i) => {
            if (i < 0 || i >= _archiveFrames.length) return;
            const url = _archiveFrames[i]?.image_url;
            if (!url) return;
            const img = new Image();
            img.src = url;
        });
    }

    function _renderArchiveMrmsFrame(frame) {
        if (!frame?.image_url) return;
        const b = frame.bounds;   // [west, east, south, north]
        const leafletBounds = [[b[2], b[0]], [b[3], b[1]]];
        if (mrmsOverlay) {
            mrmsOverlay.setBounds(leafletBounds);
            mrmsOverlay.setUrl(frame.image_url);
        } else {
            mrmsOverlay = L.imageOverlay(frame.image_url, leafletBounds, { opacity: mrmsOpacity });
            mrmsOverlay.addTo(map);
        }
    }

    function _renderArchiveGeoJsonFrame(frame, layerType) {
        const feats = frame?.features || [];

        if (layerType === 'alerts') {
            // Apply category checkbox filters (same as live alerts)
            const checked = _getCheckedAlertCategories();
            const filtered = checked.length
                ? feats.filter(f => _matchesCheckedCategories(f, checked))
                : [];
            const geojson = { type: 'FeatureCollection', features: filtered };
            if (alertsLayer) { map.removeLayer(alertsLayer); alertsLayer = null; }
            alertsLayer = L.geoJSON(geojson, {
                style: alertStyle,
                onEachFeature(feat, layer) { layer.bindPopup(alertPopup(feat)); },
            });
            alertsLayer.addTo(map);
            _allAlertFeatures = filtered;
            buildAlertsLegend(filtered);
        } else if (layerType === 'spc') {
            if (spcLayer) { map.removeLayer(spcLayer); spcLayer = null; }
            const hazard = _spcLastTouched === 'fire'
                ? byId('weather-spc-fire')?.value || ''
                : byId('weather-spc-convective')?.value || 'cat';
            const styleFn = hazard === 'prob' ? spcProbStyle
                : hazard === 'windrh' || hazard === 'dryt' ? spcFireStyle
                    : spcCatStyle;
            spcLayer = L.geoJSON(geojson, {
                style: styleFn,
                onEachFeature(feat, layer) { layer.bindPopup(spcPopup(feat)); },
            });
            if (byId('weather-show-spc')?.checked) spcLayer.addTo(map);
        }
    }

    function _renderArchiveSurfaceFrame(frame) {
        const stations = frame?.stations || [];
        _surfaceStations = stations;
        _renderSurfaceMarkers(stations);

        const product = frame?.product || _archiveSurfaceProduct || 'temperature';
        const unit = frame?.unit || (_SURFACE_PRODUCTS_UNITS[product] || '');
        const anchors = _SURFACE_COLORMAPS[product] || _SURFACE_COLORMAPS.temperature;
        buildSurfaceLegend(unit, anchors, product);
    }

    const _SURFACE_PRODUCTS_UNITS = {
        station_plot: '\u00b0F',
        temperature: '\u00b0F',
        feels_like: '\u00b0F',
        dew_point: '\u00b0F',
        relative_humidity: '%',
        wind_speed: 'kt',
        wind_gust: 'kt',
        altimeter: 'inHg',
        mslp: 'hPa',
        visibility: 'mi',
    };

    async function loadArchive() {
        const group = _activeArchiveProduct();
        const dtFromLocal = byId('archive-from')?.value;
        let dtToLocal = byId('archive-to')?.value;
        if (!dtFromLocal) {
            setStatus('Set at least the From date/time field.');
            return;
        }
        if (!dtToLocal) dtToLocal = dtFromLocal;

        const dtFrom = _toArchiveApiDatetime(dtFromLocal);
        const dtTo = _toArchiveApiDatetime(dtToLocal);
        if (!dtFrom || !dtTo) {
            setStatus('Archive time parse error: use valid local date/time values.');
            return;
        }

        _setArchiveProgress(true, 0, 'Loading archive data...');
        _setArchiveScrubber(false);
        _archiveProductType = group;
        _archiveFrames = [];
        _archiveFrameIndex = 0;
        _archiveSessionId = null;
        stopScrubberPlay();

        if (!group) {
            setStatus('Enable a supported data type (Surface, MRMS, Alerts, or SPC) before loading archive.');
            _setArchiveProgress(false);
            return;
        }
        if (group === 'mrms') {
            await _loadArchiveMrms(dtFrom, dtTo);
        } else if (group === 'surface') {
            await _loadArchiveSurface(dtFrom, dtTo);
        } else if (group === 'alerts') {
            await _loadArchiveAlerts(dtFrom, dtTo);
        } else if (group === 'spc') {
            await _loadArchiveSpc(dtFrom, dtTo);
        } else {
            setStatus('Archive mode not supported for this product type.');
            _setArchiveProgress(false);
        }
    }

    async function _loadArchiveMrms(dtFrom, dtTo) {
        const product = composeMrmsProductKey();
        const bounds = map.getBounds();
        const reqId = `arc_mrms_${Date.now()}`;
        const url = apiUrl(
            `/api/archive/mrms?product=${encodeURIComponent(product)}` +
            `&date_from=${encodeURIComponent(dtFrom)}&date_to=${encodeURIComponent(dtTo)}` +
            `&max_frames=12&south=${bounds.getSouth().toFixed(4)}&west=${bounds.getWest().toFixed(4)}` +
            `&north=${bounds.getNorth().toFixed(4)}&east=${bounds.getEast().toFixed(4)}` +
            `&request_id=${reqId}`
        );
        try {
            const resp = await fetch(url);
            if (!resp.ok) { const e = await resp.json().catch(() => ({})); throw new Error(e.detail || resp.statusText); }
            const data = await resp.json();
            _archiveSessionId = data.session_id;
            if (data.status === 'success') {
                _onArchiveFramesReady(data.frames);
            } else {
                // Poll progress then retrieve result
                await _pollArchiveProgress(data.request_id || reqId, data.session_id);
            }
        } catch (err) {
            _setArchiveProgress(true, 0, `Error: ${err.message}`);
            setStatus(`Archive MRMS error: ${err.message}`);
        }
    }

    async function _loadArchiveAlerts(dtFrom, dtTo) {
        const state = byId('weather-region')?.value;
        const stParam = (state && state !== 'CONUS') ? `&state=${encodeURIComponent(state)}` : '';
        const url = apiUrl(
            `/api/archive/alerts?date_from=${encodeURIComponent(dtFrom)}` +
            `&date_to=${encodeURIComponent(dtTo)}${stParam}`
        );
        try {
            _setArchiveProgress(true, 50, 'Fetching archived alerts...');
            const resp = await fetch(url);
            if (!resp.ok) { const e = await resp.json().catch(() => ({})); throw new Error(e.detail || resp.statusText); }
            const data = await resp.json();
            const frames = _sliceAlertsIntoFrames(data.features, data.date_from, data.date_to);
            _onArchiveFramesReady(frames);
        } catch (err) {
            _setArchiveProgress(true, 0, `Error: ${err.message}`);
            setStatus(`Archive Alerts error: ${err.message}`);
        }
    }

    /**
     * Time-slice alert features into hourly frames.
     * An alert is "active" in a frame if its onset < frameEnd AND expires > frameStart.
     */
    function _sliceAlertsIntoFrames(features, isoFrom, isoTo) {
        const STEP_MS = 60_000;         // 1-minute frames
        const from = new Date(isoFrom);
        const to = new Date(isoTo);
        if (isNaN(from) || isNaN(to) || to <= from) {
            return [{ timestamp: isoFrom, features, type: 'FeatureCollection' }];
        }

        /** Parse ISO or IEM YYYYMMDDHHMM timestamp. */
        function parseTS(s) {
            if (!s) return null;
            const d = new Date(s);
            if (!isNaN(d)) return d;
            // IEM raw format: YYYYMMDDHHMM
            if (/^\d{12}$/.test(s)) {
                const dt = new Date(Date.UTC(
                    +s.slice(0, 4), +s.slice(4, 6) - 1, +s.slice(6, 8),
                    +s.slice(8, 10), +s.slice(10, 12)));
                if (!isNaN(dt)) return dt;
            }
            return null;
        }

        // Pre-parse onset/expires for each feature once
        const parsed = features.map(f => {
            const onset = parseTS(f.properties.onset);
            const expires = parseTS(f.properties.expires);
            return {
                feature: f,
                onset: onset || from,
                expires: expires || to,
            };
        });

        // Snap start down to the nearest minute
        const cursor = new Date(from);
        cursor.setSeconds(0, 0);
        if (cursor < from) cursor.setTime(cursor.getTime() + STEP_MS);

        const frames = [];
        while (cursor <= to) {
            const frameStart = new Date(cursor);
            const frameEnd = new Date(cursor.getTime() + STEP_MS);
            const active = parsed
                .filter(p => p.onset < frameEnd && p.expires > frameStart)
                .map(p => p.feature);
            frames.push({
                timestamp: frameStart.toISOString(),
                features: active,
                type: 'FeatureCollection',
            });
            cursor.setTime(cursor.getTime() + STEP_MS);
        }

        // Fallback: if no frames produced (very short range), return single frame
        if (!frames.length) {
            return [{ timestamp: isoFrom, features, type: 'FeatureCollection' }];
        }
        return frames;
    }

    async function _loadArchiveSurface(dtFrom, dtTo) {
        const region = byId('weather-region')?.value || 'NC';
        const product = _activeSurfaceProduct() || 'temperature';
        _archiveSurfaceProduct = product;

        // Surface data is hourly — snap From/To to the top of the hour
        const fromEl = byId('archive-from');
        const toEl = byId('archive-to');
        const rawFrom = fromEl?.value || '';
        const rawTo = toEl?.value || rawFrom;
        const snappedFrom = _snapToHour(rawFrom, 'floor');
        const snappedTo = _snapToHour(rawTo, 'ceil');
        if (fromEl && snappedFrom) fromEl.value = snappedFrom;
        if (toEl && snappedTo) toEl.value = snappedTo;
        const apiFrom = _toArchiveApiDatetime(snappedFrom || rawFrom);
        const apiTo = _toArchiveApiDatetime(snappedTo || rawTo);

        const url = apiUrl(
            `/api/archive/surface?region=${encodeURIComponent(region)}` +
            `&product=${encodeURIComponent(product)}` +
            `&date_from=${encodeURIComponent(apiFrom)}` +
            `&date_to=${encodeURIComponent(apiTo)}` +
            `&max_frames=24&source=iem&network=ASOS`
        );
        try {
            _setArchiveProgress(true, 40, 'Fetching archived surface observations...');
            const resp = await fetch(url);
            if (!resp.ok) {
                const e = await resp.json().catch(() => ({}));
                throw new Error(e.detail || resp.statusText);
            }
            const data = await resp.json();
            _archiveSessionId = null;
            _onArchiveFramesReady(data.frames || []);
        } catch (err) {
            _setArchiveProgress(true, 0, `Error: ${err.message}`);
            setStatus(`Archive Surface error: ${err.message}`);
        }
    }

    async function _loadArchiveSpc(dtFrom, dtTo) {
        const day = parseInt(byId('weather-spc-day')?.value || '1', 10);
        const hazard = _spcLastTouched === 'fire'
            ? (byId('weather-spc-fire')?.value || 'cat')
            : (byId('weather-spc-convective')?.value || 'cat');
        const localFrom = byId('archive-from')?.value || '';
        const date = (localFrom.slice(0, 10) || dtFrom.slice(0, 10));
        const url = apiUrl(
            `/api/archive/spc?day=${day}&hazard=${encodeURIComponent(hazard)}&date=${date}`
        );
        try {
            _setArchiveProgress(true, 50, 'Fetching archived SPC outlook...');
            const resp = await fetch(url);
            if (!resp.ok) { const e = await resp.json().catch(() => ({})); throw new Error(e.detail || resp.statusText); }
            const data = await resp.json();
            _onArchiveFramesReady([{
                timestamp: `${data.date}T12:00:00Z`,
                features: data.features,
                type: 'FeatureCollection',
            }]);
        } catch (err) {
            _setArchiveProgress(true, 0, `Error: ${err.message}`);
            setStatus(`Archive SPC error: ${err.message}`);
        }
    }

    async function _pollArchiveProgress(requestId, sessionId) {
        const MAX_POLLS = 120;
        let polls = 0;
        return new Promise((resolve) => {
            const timer = setInterval(async () => {
                polls++;
                if (polls > MAX_POLLS) {
                    clearInterval(timer);
                    _setArchiveProgress(true, 0, 'Archive request timed out.');
                    resolve();
                    return;
                }
                try {
                    const pResp = await fetch(apiUrl(`/api/progress/${encodeURIComponent(requestId)}`));
                    if (pResp.ok) {
                        const p = await pResp.json();
                        _setArchiveProgress(true, p.percent || 0, p.message || '');
                        if (p.stage === 'success' || p.stage === 'error' || p.percent >= 100) {
                            clearInterval(timer);
                            if (p.stage === 'error') {
                                _setArchiveProgress(true, 0, `Error: ${p.message}`);
                                resolve();
                                return;
                            }
                            // Fetch result
                            const rResp = await fetch(apiUrl(`/api/archive/result?session_id=${encodeURIComponent(sessionId)}`));
                            if (rResp.ok) {
                                const r = await rResp.json();
                                if (r.status === 'success') {
                                    _onArchiveFramesReady(r.frames);
                                } else {
                                    _setArchiveProgress(true, 0, r.error || 'Archive failed.');
                                }
                            }
                            resolve();
                        }
                    }
                } catch { /* network blip, keep polling */ }
            }, 1500);
        });
    }

    function _onArchiveFramesReady(frames) {
        _archiveFrames = frames || [];
        if (!_archiveFrames.length) {
            _setArchiveProgress(true, 100, 'No frames available for that time range.');
            return;
        }
        _setArchiveProgress(false);
        const slider = byId('scrubber-slider');
        if (slider) {
            slider.min = '0';
            slider.max = String(_archiveFrames.length - 1);
            slider.value = '0';
        }
        _setArchiveScrubber(true);
        renderArchiveFrame(0);
        setStatus(`Archive loaded: ${_archiveFrames.length} frames.`);
    }

    function startScrubberPlay() {
        if (!_archiveFrames.length) return;
        if (_archivePlayTimer) return;
        const btn = byId('scrubber-play');
        if (btn) btn.textContent = '⏸';
        _archivePlayTimer = setInterval(() => {
            const next = (_archiveFrameIndex + 1) % _archiveFrames.length;
            renderArchiveFrame(next);
        }, ARCHIVE_PLAY_INTERVAL_MS);
    }

    function stopScrubberPlay() {
        if (_archivePlayTimer) {
            clearInterval(_archivePlayTimer);
            _archivePlayTimer = null;
        }
        const btn = byId('scrubber-play');
        if (btn) btn.textContent = '▶';
    }

    // ── Archive event wiring ──────────────────────────────────────────────────
    byId('weather-mode-current')?.addEventListener('click', () => {
        if (_archiveMode) exitArchiveMode();
    });
    byId('weather-mode-archive')?.addEventListener('click', () => {
        if (!_archiveMode) enterArchiveMode();
    });

    byId('archive-load-btn')?.addEventListener('click', loadArchive);

    // Preset buttons
    document.querySelectorAll('.wx-preset-btn').forEach((btn) => {
        btn.addEventListener('click', () => {
            const hours = btn.dataset.hours;
            if (hours === 'custom') {
                _setActivePreset('custom');
            } else if (hours === 'snapshot') {
                _applyArchiveSnapshot();
            } else {
                _applyArchivePreset(Number(hours));
            }
        });
    });

    // Manual edits switch highlight to Custom
    byId('archive-from')?.addEventListener('input', () => _setActivePreset('custom'));
    byId('archive-to')?.addEventListener('input', () => _setActivePreset('custom'));

    byId('scrubber-play')?.addEventListener('click', () => {
        if (_archivePlayTimer) { stopScrubberPlay(); } else { startScrubberPlay(); }
    });

    byId('scrubber-step-back')?.addEventListener('click', () => {
        stopScrubberPlay();
        renderArchiveFrame(_archiveFrameIndex - 1);
    });

    byId('scrubber-step-fwd')?.addEventListener('click', () => {
        stopScrubberPlay();
        renderArchiveFrame(_archiveFrameIndex + 1);
    });

    byId('scrubber-slider')?.addEventListener('input', (e) => {
        stopScrubberPlay();
        renderArchiveFrame(parseInt(e.target.value, 10));
    });

    async function _ensureBoundaryLayers() {
        if (statesLayer && countiesLayer) return;
        if (typeof window.topojson === 'undefined') return;
        try {
            const resp = await fetch('https://cdn.jsdelivr.net/npm/us-atlas@3/counties-10m.json');
            if (!resp.ok) return;
            const topo = await resp.json();
            const states = window.topojson.feature(topo, topo.objects.states);
            const counties = window.topojson.feature(topo, topo.objects.counties);

            statesLayer = L.geoJSON(states, {
                style: { color: '#dbe6ef', weight: 1, opacity: 0.8, fillOpacity: 0 },
                interactive: false,
            });
            countiesLayer = L.geoJSON(counties, {
                style: { color: '#8aa2b6', weight: 0.5, opacity: 0.45, fillOpacity: 0 },
                interactive: false,
            });
        } catch {
            setStatus('State/county boundary overlay unavailable.');
        }
    }

    async function _ensureCountriesLayer() {
        if (countriesLayer) return;
        if (typeof window.topojson === 'undefined') return;
        try {
            const resp = await fetch('https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json');
            if (!resp.ok) return;
            const topo = await resp.json();
            const countriesRaw = window.topojson.feature(topo, topo.objects.countries);
            const countries = _normalizeGeoJsonForDateline(countriesRaw);
            countriesLayer = L.geoJSON(countries, {
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

    async function _ensureCitiesLayer() {
        if (_citiesData && citiesLayer) return;
        try {
            if (!_citiesData) {
                const resp = await fetch(apiUrl('/data/us-cities-all.json'));
                if (!resp.ok) return;
                _citiesData = await resp.json();
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
        const distKm = Math.round(_baseCityDistKm(zoom) / _citiesDensity);
        const baseLabel = label.dataset.baseLabel || 'City Density';
        label.dataset.baseLabel = baseLabel;
        label.textContent = `${baseLabel} (${distKm} km)`;
    }

    function _readObsDensity() {
        const raw = parseFloat(byId('weather-obs-density')?.value || '1');
        if (!Number.isFinite(raw)) return 1;
        return Math.max(0.01, Math.min(1, raw));
    }

    function _updateObsDensityLabel() {
        const label = document.querySelector('label[for="weather-obs-density"]');
        if (!label) return;
        const zoom = map?.getZoom() ?? 5;
        const region = (byId('weather-region')?.value || '').toUpperCase();
        const distKm = Math.round(_baseDistKm(zoom, region) / _surfaceDensity);
        const baseLabel = label.dataset.baseLabel || 'Station Density';
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
        const minDistKm = _baseCityDistKm(zoom) / _citiesDensity;
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
        if (!byId('weather-toggle-cities')?.checked) return;
        if (!_citiesData) return;
        _rebuildCitiesLayer();
    }

    async function _syncRightSidebarLayers() {
        const showStates = byId('weather-toggle-states')?.checked;
        const showCounties = byId('weather-toggle-counties')?.checked;
        const showCities = byId('weather-toggle-cities')?.checked;
        const showCountries = byId('weather-toggle-countries')?.checked;

        await _ensureBoundaryLayers();
        await _ensureCitiesLayer();
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

    byId('weather-region')?.addEventListener('change', (e) => {
        fitRegion(e.target.value);
        _updateObsDensityLabel();
        _updateGradientBlurControlVisibility();
        refreshActiveLayers();
    });

    // Network filter initialization and event listeners
    const NETWORKS = ['ASOS', 'COOP', 'DCP', 'RWIS'];
    let _networkFilters = {};

    // Load network filters from localStorage
    function _loadNetworkFilters() {
        const saved = localStorage.getItem('wxNetworkFilters');
        if (saved) {
            try {
                _networkFilters = JSON.parse(saved);
            } catch (e) {
                _networkFilters = Object.fromEntries(NETWORKS.map(n => [n, true]));
            }
        } else {
            _networkFilters = Object.fromEntries(NETWORKS.map(n => [n, true]));
        }
    }

    function _saveNetworkFilters() {
        localStorage.setItem('wxNetworkFilters', JSON.stringify(_networkFilters));
    }

    function _getFilteredStations(stations) {
        if (!Array.isArray(stations)) return [];
        return stations.filter(s => _networkFilters[s.network || 'ASOS']);
    }

    // Load and apply saved filter state to checkboxes
    _loadNetworkFilters();
    NETWORKS.forEach(net => {
        const checkbox = document.querySelector(`.weather-network-filter input[value="${net}"]`);
        if (checkbox) {
            checkbox.checked = _networkFilters[net];
        }
    });

    // Add event listeners to network filter checkboxes
    document.querySelectorAll('.weather-network-filter').forEach(checkbox => {
        checkbox.addEventListener('change', (e) => {
            _networkFilters[e.target.value] = e.target.checked;
            _saveNetworkFilters();
            // Re-render surface markers with updated filter
            if (_surfaceStations.length) {
                _renderSurfaceMarkers(_getFilteredStations(_surfaceStations));
            }
        });
    });

    // Wrap _renderSurfaceMarkers to apply network filtering
    const _originalRenderSurfaceMarkers = _renderSurfaceMarkers;
    _renderSurfaceMarkers = function (stations) {
        const filtered = _getFilteredStations(stations);
        _originalRenderSurfaceMarkers(filtered);
    };

    ['current', 'alerts', 'radar', 'satellite', 'spc', 'rtma', 'mrms', 'drought', 'tropical'].forEach((type) => {
        byId(`weather-type-${type}`)?.addEventListener('change', (e) => {
            // Enforce single active product group for main sidebar groups
            const mainGroups = ['current', 'alerts', 'spc', 'mrms'];
            if (mainGroups.includes(type) && e.target.checked) {
                // Uncheck other main product groups
                mainGroups.forEach((group) => {
                    if (group !== type) {
                        const el = byId(`weather-type-${group}`);
                        if (el) el.checked = false;
                    }
                });
            }
            _updateTypeSections();
            _updateRightSidebarGroups();
            if (_archiveMode) {
                // Switching tabs while in archive mode: exit archive, clear layers,
                // reset to Current mode, and load live data for the new tab.
                _clearAllMapLayers();
                exitArchiveMode();
            } else {
                refreshActiveLayers();
            }
        });
    });

    _getAlertCategoryCheckboxes().forEach((el) => {
        el.addEventListener('change', () => {
            const allEl = byId('weather-alerts-all');
            if (el === allEl) {
                _setAllAlertCategories(!!allEl?.checked);
            } else {
                _syncAllAlertsMaster();
            }
            if (_archiveMode && _archiveProductType === 'alerts' && _archiveFrames.length) {
                renderArchiveFrame(_archiveFrameIndex);
            } else if (_isTypeEnabled('alerts')) {
                loadAlerts();
            }
        });
    });

    byId('weather-spc-day')?.addEventListener('change', () => {
        if (_isTypeEnabled('spc') && byId('weather-show-spc')?.checked) refreshSpc();
    });

    byId('weather-spc-convective')?.addEventListener('change', () => {
        _spcLastTouched = 'convective';
        if (byId('weather-spc-fire')) byId('weather-spc-fire').value = '';
        if (_isTypeEnabled('spc') && byId('weather-show-spc')?.checked) refreshSpc();
    });

    byId('weather-spc-fire')?.addEventListener('change', () => {
        _spcLastTouched = 'fire';
        if (byId('weather-spc-convective')) byId('weather-spc-convective').value = '';
        if (_isTypeEnabled('spc') && byId('weather-show-spc')?.checked) refreshSpc();
    });

    document.querySelectorAll('.weather-surface-product').forEach((el) => {
        el.addEventListener('change', (evt) => {
            if (evt.target.checked) {
                document.querySelectorAll('.weather-surface-product').forEach((other) => {
                    if (other !== evt.target) {
                        other.checked = false;
                        const grad = document.querySelector(`.weather-surface-gradient[data-product="${other.value}"]`);
                        if (grad) grad.checked = false;
                    }
                });
            }
            _updateGradientBlurControlVisibility();
            refreshActiveLayers();
        });
    });

    byId('weather-show-spc')?.addEventListener('change', () => {
        _updateSubOptionVisibility();
        refreshActiveLayers();
    });
    byId('weather-show-mrms')?.addEventListener('change', () => {
        _updateSubOptionVisibility();
        refreshActiveLayers();
    });

    byId('weather-opacity-alerts')?.addEventListener('input', (e) => applyAlertsOpacity(e.target.value));
    byId('weather-opacity-spc')?.addEventListener('input', (e) => applySpcOpacity(e.target.value));
    byId('weather-opacity-surface-values')?.addEventListener('input', (e) => applySurfaceValueOpacity(e.target.value));
    byId('weather-opacity-surface-gradient')?.addEventListener('input', (e) => applySurfaceGradientOpacity(e.target.value));
    byId('weather-opacity-mrms')?.addEventListener('input', (e) => applyMrmsOpacity(e.target.value));

    document.querySelectorAll('.weather-surface-gradient').forEach((el) => {
        el.addEventListener('change', async () => {
            _updateGradientBlurControlVisibility();
            if (_surfaceStations?.length && _isTypeEnabled('current')) {
                const product = _activeSurfaceProduct();
                if (el.checked && product && el.dataset.product === product) {
                    const region = byId('weather-region')?.value || 'CONUS';
                    await _ensureGradientStations(product, region);
                }
                _renderSurfaceMarkers(_surfaceStations);
            }
        });
    });

    byId('weather-gradient-blur')?.addEventListener('input', () => {
        _gradientBlurScale = _readGradientBlurScale();
        _updateGradientBlurLabel();
        if (_surfaceStations?.length && _activeSurfaceGradient()) {
            _renderSurfaceMarkers(_surfaceStations);
        }
    });

    byId('weather-obs-density')?.addEventListener('input', (e) => {
        _surfaceDensity = _readObsDensity();
        _updateObsDensityLabel();
        if (_surfaceStations?.length) {
            _renderSurfaceMarkers(_surfaceStations);
        }
    });

    byId('weather-mrms-family')?.addEventListener('change', () => {
        updateMrmsSubControls();
        if (_isTypeEnabled('mrms') && byId('weather-show-mrms')?.checked) loadMrms();
    });

    ['mrms-qpe-source', 'mrms-qpe-period', 'mrms-rotation-level', 'mrms-rotation-time',
        'mrms-mesh-time', 'mrms-azshear-level', 'mrms-echotop-threshold', 'mrms-vil-type',
        'mrms-refl-variant', 'mrms-lightning-window', 'mrms-model-field'].forEach((id) => {
            byId(id)?.addEventListener('change', () => {
                if (_isTypeEnabled('mrms') && byId('weather-show-mrms')?.checked) loadMrms();
            });
        });

    byId('weather-refresh-mrms')?.addEventListener('click', loadMrms);
    byId('weather-refresh-alerts')?.addEventListener('click', () => loadAlerts());
    byId('weather-refresh-spc')?.addEventListener('click', refreshSpc);
    byId('weather-refresh-surface')?.addEventListener('click', () => {
        const region = byId('weather-region')?.value || 'NC';
        const product = _activeSurfaceProduct();
        if (!product) {
            setStatus('Select a surface observation type first.');
            return;
        }
        loadSurface(region, product);
    });


    byId('weather-toggle-cities')?.addEventListener('change', _syncRightSidebarLayers);
    byId('weather-cities-density')?.addEventListener('input', () => {
        _citiesDensity = _readCitiesDensity();
        _updateCitiesDensityLabel();
        if (_citiesData) _rebuildCitiesLayer();
    });
    byId('weather-toggle-states')?.addEventListener('change', _syncRightSidebarLayers);
    byId('weather-toggle-counties')?.addEventListener('change', _syncRightSidebarLayers);
    byId('weather-toggle-countries')?.addEventListener('change', _syncRightSidebarLayers);

    map.on('moveend', () => {
        _refreshCitiesIfVisible();
        if (
            _surfaceStations.length
            && _isTypeEnabled('current')
            && _activeSurfaceProduct()
            && _activeSurfaceGradient()
        ) {
            // Gradient is a bounds-sized image overlay; rebuild it after panning.
            _renderSurfaceMarkers(_surfaceStations);
        }
        if (_isTypeEnabled('alerts') && _getCheckedAlertCategories().length > 0 && _allAlertFeatures.length) {
            buildAlertsLegend(_allAlertFeatures);
        }
    });

    // ── Init ─────────────────────────────────────────────────────────────────
    function init() {
        _setAllAlertCategories(true);
        _syncAllAlertsMaster();
        _updateTypeSections();
        _updateRightSidebarGroups();
        _updateSubOptionVisibility();
        updateMrmsSubControls();
        _wireSidebarToggle('weather-side-left', 'weather-side-toggle-left', '‹', '›');
        _wireSidebarToggle('weather-side-right', 'weather-side-toggle-right', '›', '‹');
        _citiesDensity = _readCitiesDensity();
        _updateCitiesDensityLabel();
        _surfaceDensity = _readObsDensity();
        _updateObsDensityLabel();
        _gradientBlurScale = _readGradientBlurScale();
        _updateGradientBlurLabel();
        _updateGradientBlurControlVisibility();
        _syncRightSidebarLayers();
        refreshActiveLayers();
    }

    // ── Auto-refresh alerts every 2 min (matches backend worker interval) ──
    const ALERTS_AUTO_REFRESH_MS = 60_000;
    setInterval(() => {
        if (_archiveMode) return;
        if (!_isTypeEnabled('alerts')) return;
        if (!_getCheckedAlertCategories().length) return;
        loadAlerts();
    }, ALERTS_AUTO_REFRESH_MS);

    init();

}());

