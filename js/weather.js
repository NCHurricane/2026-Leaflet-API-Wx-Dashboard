(function () {
    'use strict';

    const byId = (id) => document.getElementById(id);

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
        el.innerHTML = `Last Updated:<br>${_formatViewerTimestamp(value)}`;
    }

    // Wire up event handlers for SPC controls (Fire Weather UI parity)
    function _wireSpcUiParityHandlers() {
        const spcDaySelect = byId('weather-spc-day');
        if (spcDaySelect) {
            spcDaySelect.addEventListener('change', () => {
                _syncSpcConvectiveOptions(_shouldResetSpcConvectiveDaySelection());
                refreshSpc();
            });
        }
        const fireDaySelect = byId('weather-spc-fire-day');
        if (fireDaySelect) {
            fireDaySelect.addEventListener('change', () => {
                _syncSpcFireWeatherOptions(_shouldResetSpcFireDaySelection());
                refreshSpc();
            });
        }
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
        // CIG intensity levels (SPC March 2026 enhancement)
        'CIG1': { fill: '#ffa040', stroke: '#cc5500' },
        'CIG2': { fill: '#ff3300', stroke: '#aa0000' },
        'CIG3': { fill: '#cc0099', stroke: '#880066' },
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

    // Synced from config/alerts_config.py ALERT_PRIORITY
    const ALERT_PRIORITY = {
        'Tsunami Warning': 1,
        'Tornado Warning': 2,
        'Extreme Wind Warning': 3,
        'Severe Thunderstorm Warning': 4,
        'Flash Flood Warning': 5,
        'Flash Flood Statement': 6,
        'Severe Weather Statement': 7,
        'Civil Danger Warning': 8,
        'Radiological Hazard Warning': 9,
        'Hazardous Materials Warning': 10,
        'Fire Warning': 11,
        'Storm Surge Warning': 12,
        'Hurricane Force Wind Warning': 13,
        'Hurricane Warning': 14,
        'Typhoon Warning': 15,
        'Special Marine Warning': 16,
        'Blizzard Warning': 17,
        'Snow Squall Warning': 18,
        'Ice Storm Warning': 19,
        'Heavy Freezing Spray Warning': 20,
        'Winter Storm Warning': 21,
        'Lake Effect Snow Warning': 22,
        'Dust Storm Warning': 23,
        'Blowing Dust Warning': 24,
        'High Wind Warning': 25,
        'Tropical Storm Warning': 26,
        'Storm Warning': 27,
        'Tsunami Advisory': 28,
        'Tsunami Watch': 29,
        'Avalanche Warning': 30,
        'Earthquake Warning': 31,
        'Volcano Warning': 32,
        'Ashfall Warning': 33,
        'Flood Warning': 34,
        'Coastal Flood Warning': 35,
        'Lakeshore Flood Warning': 36,
        'Ashfall Advisory': 37,
        'High Surf Warning': 38,
        'Extreme Heat Warning': 39,
        'Tornado Watch': 40,
        'Severe Thunderstorm Watch': 41,
        'Flash Flood Watch': 42,
        'Gale Warning': 43,
        'Flood Statement': 44,
        'Extreme Cold Warning': 45,
        'Freeze Warning': 46,
        'Red Flag Warning': 47,
        'Storm Surge Watch': 48,
        'Hurricane Watch': 49,
        'Hurricane Force Wind Watch': 50,
        'Typhoon Watch': 51,
        'Tropical Storm Watch': 52,
        'Storm Watch': 53,
        'Tropical Cyclone Local Statement': 54,
        'Winter Weather Advisory': 55,
        'Avalanche Advisory': 56,
        'Cold Weather Advisory': 57,
        'Heat Advisory': 58,
        'Flood Advisory': 59,
        'Coastal Flood Advisory': 60,
        'Lakeshore Flood Advisory': 61,
        'High Surf Advisory': 62,
        'Dense Fog Advisory': 63,
        'Dense Smoke Advisory': 64,
        'Small Craft Advisory': 65,
        'Brisk Wind Advisory': 66,
        'Hazardous Seas Warning': 67,
        'Dust Advisory': 68,
        'Blowing Dust Advisory': 69,
        'Lake Wind Advisory': 70,
        'Wind Advisory': 71,
        'Frost Advisory': 72,
        'Freezing Fog Advisory': 73,
        'Freezing Spray Advisory': 74,
        'Low Water Advisory': 75,
        'Local Area Emergency': 76,
        'Winter Storm Watch': 77,
        'Rip Current Statement': 78,
        'Beach Hazards Statement': 79,
        'Gale Watch': 80,
        'Avalanche Watch': 81,
        'Hazardous Seas Watch': 82,
        'Heavy Freezing Spray Watch': 83,
        'Flood Watch': 84,
        'Coastal Flood Watch': 85,
        'Lakeshore Flood Watch': 86,
        'High Wind Watch': 87,
        'Extreme Heat Watch': 88,
        'Extreme Cold Watch': 89,
        'Freeze Watch': 90,
        'Fire Weather Watch': 91,
        'Extreme Fire Danger': 92,
        'Coastal Flood Statement': 93,
        'Lakeshore Flood Statement': 94,
        'Special Weather Statement': 95,
        'Marine Weather Statement': 96,
        'Air Quality Alert': 97,
        'Air Stagnation Advisory': 98,
        'Hazardous Weather Outlook': 99,
        'Hydrologic Outlook': 100,
        'Short Term Forecast': 101,
    };

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
        'Non-Precipitation Alerts': ['High Wind Warning', 'High Wind Watch', 'Wind Advisory', 'Dense Fog Advisory', 'Dense Smoke Advisory', 'Dust Storm Warning', 'Blowing Dust Warning', 'Blowing Dust Advisory', 'Air Quality Alert', 'Ashfall Warning', 'Ashfall Advisory', 'Air Stagnation Advisory', 'Dust Advisory', 'Lake Wind Advisory'],
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

    function _applyDefaultAlertSelection() {
        const allEl = byId('weather-alerts-all');
        const defaultCategory = 'Severe Weather Warnings';

        _getAlertCategoryCheckboxes().forEach((el) => {
            if (el === allEl) return;
            el.checked = el.value === defaultCategory;
        });

        document.querySelectorAll('.wx-warn-filter-ck').forEach((el) => {
            el.checked = true;
        });

        _syncAllAlertsMaster();
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
    // CONUS framing is driven entirely by CONUS_DEFAULT_BOUNDS via fitBounds(),
    // so the visible extent adapts to the viewport size instead of being fixed
    // by a center/zoom pair.
    const CONUS_DEFAULT_BOUNDS = [[23.0, -127.0], [50.5, -65.0]];
    const WORLD_DEFAULT_BOUNDS = [[-60, -179.9], [85, 179.9]];
    const REGION_FIT_BOTTOM_PADDING_PX = 120;

    const tilesDarkNoLabels = L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png', tileOptions);
    const tilesLightNoLabels = L.tileLayer('https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png', tileOptions);
    const tilesVoyager = L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', tileOptions);
    var USGS_USImagery = L.tileLayer('https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/{z}/{y}/{x}', {
        maxZoom: 20,
        attribution: 'Tiles courtesy of the <a href="https://usgs.gov/">U.S. Geological Survey</a>'
    });
    const tilesSatellite = L.tileLayer(
        'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        {
            attribution: 'Tiles &copy; Esri',
            maxZoom: 19,
        },
    );

    const map = L.map('weather-map', { layers: [tilesDarkNoLabels] });
    map.fitBounds(CONUS_DEFAULT_BOUNDS, { animate: false });

    function _normalizedLonSpanDegrees(west, east) {
        let span = Number(east) - Number(west);
        if (!Number.isFinite(span)) return 0;
        while (span < 0) span += 360;
        while (span > 360) span -= 360;
        return span;
    }

    function _effectiveViewportZoom() {
        const bounds = map.getBounds();
        const widthPx = Math.max(1, Number(map.getSize()?.x || 0));
        const lonSpan = Math.max(
            1e-6,
            _normalizedLonSpanDegrees(bounds.getWest(), bounds.getEast())
        );
        // Web Mercator x is linear in longitude, and zoom 0 is 256 px wide.
        const zoom = Math.log2((360 * widthPx) / (256 * lonSpan));
        return Number.isFinite(zoom) ? zoom : (Number(map.getZoom()) || 0);
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
            const effectiveZoom = _effectiveViewportZoom();
            const leafletZoom = Number(map.getZoom()) || 0;
            indicator.textContent = `z ${effectiveZoom.toFixed(2)}`;
            indicator.title = `Viewport ${effectiveZoom.toFixed(2)} | Leaflet ${leafletZoom.toFixed(2)}`;
        };

        update();
        map.on('zoom zoomend move moveend resize', update);
    }

    _initLeafletZoomIndicator();

    function _ensureSpcCigPatternDefs(svgRoot) {
        if (!svgRoot) return;
        let defs = svgRoot.querySelector('defs');
        if (!defs) {
            defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
            svgRoot.insertBefore(defs, svgRoot.firstChild);
        }

        const hasPattern = (id) => !!defs.querySelector(`#${id}`);

        if (!hasPattern('hatch-cig-1')) {
            // Intensity 1: dashed diagonal lines at 45°
            const pattern1 = document.createElementNS('http://www.w3.org/2000/svg', 'pattern');
            pattern1.setAttribute('id', 'hatch-cig-1');
            pattern1.setAttribute('patternUnits', 'userSpaceOnUse');
            pattern1.setAttribute('width', '10');
            pattern1.setAttribute('height', '10');
            pattern1.setAttribute('patternTransform', 'rotate(45)');
            const line1 = document.createElementNS('http://www.w3.org/2000/svg', 'line');
            line1.setAttribute('x1', '0');
            line1.setAttribute('y1', '0');
            line1.setAttribute('x2', '0');
            line1.setAttribute('y2', '10');
            line1.setAttribute('stroke', 'black');
            line1.setAttribute('stroke-width', '4');
            line1.setAttribute('stroke-dasharray', '4,6');
            pattern1.appendChild(line1);
            defs.appendChild(pattern1);
        }

        if (!hasPattern('hatch-cig-2')) {
            // Intensity 2: solid diagonal lines at 45° (matches Intensity 1 spacing/width)
            const pattern2 = document.createElementNS('http://www.w3.org/2000/svg', 'pattern');
            pattern2.setAttribute('id', 'hatch-cig-2');
            pattern2.setAttribute('patternUnits', 'userSpaceOnUse');
            pattern2.setAttribute('width', '18');
            pattern2.setAttribute('height', '18');
            pattern2.setAttribute('patternTransform', 'rotate(-45)');
            const line2 = document.createElementNS('http://www.w3.org/2000/svg', 'line');
            line2.setAttribute('x1', '0');
            line2.setAttribute('y1', '0');
            line2.setAttribute('x2', '0');
            line2.setAttribute('y2', '18');
            line2.setAttribute('stroke', 'black');
            line2.setAttribute('stroke-width', '4');
            pattern2.appendChild(line2);
            defs.appendChild(pattern2);
        }

        if (!hasPattern('hatch-cig-3')) {
            // Intensity 3: cross-hatch (two perpendicular sets of solid 45° diagonals)
            const pattern3 = document.createElementNS('http://www.w3.org/2000/svg', 'pattern');
            pattern3.setAttribute('id', 'hatch-cig-3');
            pattern3.setAttribute('patternUnits', 'userSpaceOnUse');
            pattern3.setAttribute('width', '18');
            pattern3.setAttribute('height', '18');
            pattern3.setAttribute('patternTransform', 'rotate(45)');

            const lineA = document.createElementNS('http://www.w3.org/2000/svg', 'line');
            lineA.setAttribute('x1', '0');
            lineA.setAttribute('y1', '0');
            lineA.setAttribute('x2', '0');
            lineA.setAttribute('y2', '18');
            lineA.setAttribute('stroke', 'black');
            lineA.setAttribute('stroke-width', '4');

            const lineB = document.createElementNS('http://www.w3.org/2000/svg', 'line');
            lineB.setAttribute('x1', '0');
            lineB.setAttribute('y1', '0');
            lineB.setAttribute('x2', '18');
            lineB.setAttribute('y2', '0');
            lineB.setAttribute('stroke', 'black');
            lineB.setAttribute('stroke-width', '4');

            pattern3.appendChild(lineA);
            pattern3.appendChild(lineB);
            defs.appendChild(pattern3);
        }
    }

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
            L.DomEvent.on(btn, 'click', () => _clearRadarSiteAndZoomConus());
            return container;
        },
    });
    new ResetViewControl().addTo(map);
    new BasemapControl().addTo(map);
    map.attributionControl.addAttribution('©2026 ChuckCopeland.com/NCHurricane.com');
    if (!map.getPane('radar-overlays')) {
        const radarOverlayPane = map.createPane('radar-overlays');
        radarOverlayPane.style.zIndex = '360';
        radarOverlayPane.style.pointerEvents = 'none';
    }
    if (!map.getPane('radar-sites')) {
        const radarSitesPane = map.createPane('radar-sites');
        radarSitesPane.style.zIndex = '460';
    }
    if (!map.getPane('mrms-radar-sites')) {
        const mrmsRadarSitesPane = map.createPane('mrms-radar-sites');
        mrmsRadarSitesPane.style.zIndex = '451';
        mrmsRadarSitesPane.style.pointerEvents = 'none';
    }
    if (!map.getPane('satellite-overlays')) {
        const satelliteOverlayPane = map.createPane('satellite-overlays');
        satelliteOverlayPane.style.zIndex = '330';
        satelliteOverlayPane.style.pointerEvents = 'none';
    }
    const LogoControl = L.Control.extend({
        options: { position: 'topright' },
        onAdd() {
            const div = L.DomUtil.create('div', 'leaflet-control-logo');
            const img = L.DomUtil.create('img', '', div);
            img.src = 'img/nchurricane_logo.png';
            img.alt = 'NCHurricane.com';
            img.loading = 'lazy';
            const ts = L.DomUtil.create('div', 'wx-global-timestamp', div);
            ts.id = 'wx-global-timestamp';
            ts.innerHTML = `Last Updated:<br>${_formatViewerTimestamp(null)}`;
            return div;
        },
    });
    new LogoControl().addTo(map);

    // ── Layer state ──────────────────────────────────────────────────────────
    let alertsLayer = null;
    let spcLayer = null;
    let surfaceLayer = null;
    let radarLiveOverlay = null;
    let satelliteOverlay = null;
    let _satelliteFrames = [];
    let _satelliteFrameIndex = 0;
    let _satelliteRequestSeq = 0;
    let _satelliteAutoRefreshTimer = null;
    let _satelliteScrubMode = false;
    let _satelliteScrubPlayTimer = null;
    let _satelliteScrubFrameAdvanceInFlight = false;
    let _satelliteScrubResumeAfterZoom = false;
    let _satelliteScrubLoadSeq = 0;
    let _satelliteScrubRenderSeq = 0;
    let _satelliteBackgroundWarmSeq = 0;
    let _satellitePendingSwapToken = 0;
    let _satelliteApiMode = 'v2';
    let _satelliteCatalog = null;
    let _satelliteAnimateNewFrameTimer = null;
    let _satelliteAnimateAutoRefreshEnabled = false;
    let _satelliteAnimateAutoRefreshTimer = null;
    let _satelliteAnimateAutoRefreshInFlight = false;
    let _satelliteAutoRefreshFlashActive = false;
    let _satelliteTileRefreshToken = 0;
    let _satelliteProgressiveRedrawSeq = 0;
    let _satelliteProgressiveRedrawTimers = [];
    let _satellitePrefetchTimer = null;
    let _satellitePrefetchSeq = 0;
    let _satellitePrefetchQueue = [];
    let _satellitePrefetchActive = 0;
    let _satellitePrefetchController = null;
    let _satellitePrefetchContextKey = '';
    const _satellitePrefetchSeenUrls = new Map();
    let _satelliteFetchController = null;
    let _satelliteScrubFetchController = null;
    let _satelliteLookbackReloadTimer = null;
    let _satelliteManualScrubTimer = null;
    let _satelliteLayerZCounter = 0;
    let _scrubberPlaybackSpeedIndex = 2;
    const _satelliteLayerPool = new Map(); // frameKey → L.tileLayer
    const _satelliteLegendCache = new Map();
    let radarSiteLayer = null;
    let radarSiteHighlightLayer = null;
    let radarBackdropLayer = null;
    let _radarSitesLoaded = false;
    let _radarSiteConfiguredMap = new Map();
    let _radarSiteStatusMap = new Map();
    let _radarSiteRequestSeq = 0;
    let _radarLiveRequestSeq = 0;
    const _radarColortableCache = new Map();
    const _radarMultiSites = new Set();     // siteIds selected via Shift+click
    const _radarSiteOverlays = new Map();   // siteId → L.imageOverlay (multi-site mode)
    let _radarScrubMode = false;
    let _radarScrubFrames = [];
    let _radarScrubIsTimeMode = false;
    let _radarScrubTimelineMs = [];
    let _radarScrubFramesBySite = new Map();
    let _radarScrubContextKey = '';
    let _radarScrubFrameIndex = 0;
    let _radarScrubRenderSeq = 0;
    let _radarScrubLoadSeq = 0;
    let _radarScrubPlayTimer = null;
    let _radarHistoryFillTimer = null;
    let _radarScrubWarmPollTimer = null;
    let _radarScrubWarmPollDeadlineMs = 0;
    let _radarScrubWarmStablePolls = 0;
    let _radarLatestRetryTimer = null;
    let _radarLatestRetryDeadlineMs = 0;
    let _radarLatestRetrySite = '';
    let _radarLatestRetryProduct = '';
    const _radarSiteCoords = new Map();
    let _radarTabVisitedOnce = false;
    let rtmaOverlay = null;
    let rtmaPointLayer = null;
    let rtmaGradientLayer = null;
    let _rtmaPointsAll = [];
    let _rtmaPointsUnits = '';
    let _rtmaPointsKey = null;
    // GRIB-subgrid gradient state (replaces IDW on live view)
    let _rtmaGridPoints = [];   // [[lat, lon, value], ...]
    let _rtmaGridKey = null;    // region|stream|product key for cache invalidation
    let _rtmaGridSeq = 0;
    let _rtmaGridInFlightKey = null;
    let mrmsOverlay = null;
    let mrmsRadarSiteLayer = null;
    let droughtLayer = null;
    let _droughtDates = [];
    let _activeDroughtDate = null;
    let _lastDroughtStateStats = null;
    let _lastDroughtStateCode = null;
    const _droughtStateStatsCache = new Map();
    let statesLayer = null;
    let countiesLayer = null;
    let countriesLayer = null;
    let citiesLayer = null;
    let _citiesData = null;
    let _citiesDensity = 1;
    let _surfaceDensity = 1;
    let _gradientBlurScale = 0;
    const CITY_LABEL_CHAR_PX = 5.2;
    const CITY_LABEL_HEIGHT_PX = 11;
    const CITY_LABEL_X_PAD = 4;
    const CITY_LABEL_Y_PAD = 2;
    let _allAlertFeatures = [];        // Full geometry — used for all interactions (hover, click, pager)
    let _alertsDisplayFeatures = [];   // Simplified display geometry — used for map rendering only
    let _alertsFullBaseFeatures = [];      // Full geometry after cancel/expire filtering (before category filtering)
    let _alertsDisplayBaseFeatures = [];   // Display geometry after cancel/expire filtering (before category filtering)
    let _lastAlertsZoomBucket = null;  // Tracks current bucket; null = uninitialized
    let _knownAlertIds = null; // null = first load; Set<string> after first load
    let _activeAlertsPopup = null;
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
    let alertsOpacity = 0.75;
    let spcOpacity = 0.60;
    let spcStrokeOpacity = 1.0;
    let surfaceValueOpacity = 0.9;
    let surfaceGradientOpacity = 0.9;
    let rtmaOpacity = 0.82;
    let rtmaGradientOpacity = 0.9;
    // _rtmaGradientBlurScale removed — RTMA gradients are pre-rendered PNGs, no canvas blur.
    let mrmsOpacity = 0.8;
    let _alertsRequestSeq = 0;
    let _spcRequestSeq = 0;
    let _spcAbortController = null;
    let _spcReportsRequestSeq = 0;
    let _spcMdsRequestSeq = 0;
    let _spcWatchesRequestSeq = 0;
    let _surfaceRequestSeq = 0;
    let _rtmaRequestSeq = 0;
    let _rtmaPointsSeq = 0;
    let _rtmaPointsDebounceTimer = null;
    let _rtmaPointsInFlightKey = null;
    let _lastRtmaPointsFetchKey = null;
    let _lastRtmaPointsFetchMs = 0;
    let _rtmaScrubMode = false;
    let _rtmaScrubFrames = [];
    let _rtmaScrubFrameIndex = 0;
    let _rtmaScrubRenderSeq = 0;
    let _rtmaScrubLoadSeq = 0;
    let _rtmaScrubPlayTimer = null;
    let _mrmsScrubMode = false;
    let _mrmsScrubFrames = [];
    let _mrmsScrubFrameIndex = 0;
    let _mrmsScrubRenderSeq = 0;
    let _mrmsScrubLoadSeq = 0;
    let _mrmsScrubPlayTimer = null;
    const _rtmaScrubFrameCache = new Map();
    const _rtmaScrubFrameErrors = new Set();
    let _mrmsRequestSeq = 0;
    const _MRMS_RADAR_SITE_POINT_STYLE = Object.freeze({
        radius: 2.8,
        color: '#f8f8f8',
        weight: 1.1,
        opacity: 0.95,
        fillColor: '#ff3b30',
        fillOpacity: 0.9,
        pane: 'mrms-radar-sites',
        interactive: false,
        bubblingMouseEvents: false,
    });
    const _SPC_PRIMARY_TIMEOUT_MS = 10_000;
    const _SPC_SUPPLEMENTAL_TIMEOUT_MS = 20_000;

    function _resolveMrmsRadarSiteBounds(bounds) {
        if (Array.isArray(bounds) && bounds.length === 4) {
            return bounds.map((value) => Number(value));
        }
        if (mrmsOverlay && typeof mrmsOverlay.getBounds === 'function') {
            const overlayBounds = mrmsOverlay.getBounds();
            if (overlayBounds && typeof overlayBounds.getWest === 'function') {
                return [
                    overlayBounds.getWest(),
                    overlayBounds.getEast(),
                    overlayBounds.getSouth(),
                    overlayBounds.getNorth(),
                ];
            }
        }
        return null;
    }

    function _getMrmsRadarSiteLocations(bounds) {
        const sites = Array.isArray(window.RADAR_SITE_LOCATIONS)
            ? window.RADAR_SITE_LOCATIONS
            : [];
        const siteBounds = _resolveMrmsRadarSiteBounds(bounds);
        if (!siteBounds || siteBounds.some((value) => !Number.isFinite(value))) {
            return [];
        }

        const [west, east, south, north] = siteBounds;
        return sites.filter((site) => {
            const lat = Number(site?.lat);
            const lon = Number(site?.lon);
            return Number.isFinite(lat)
                && Number.isFinite(lon)
                && lon >= west
                && lon <= east
                && lat >= south
                && lat <= north;
        });
    }

    function _ensureMrmsRadarSiteLayer() {
        if (mrmsRadarSiteLayer) return mrmsRadarSiteLayer;
        mrmsRadarSiteLayer = L.layerGroup();
        return mrmsRadarSiteLayer;
    }

    function _syncMrmsRadarSiteOverlay(bounds) {
        if (!_isTypeEnabled('mrms') || !mrmsOverlay) {
            if (mrmsRadarSiteLayer && map.hasLayer(mrmsRadarSiteLayer)) {
                map.removeLayer(mrmsRadarSiteLayer);
            }
            return;
        }

        const layer = _ensureMrmsRadarSiteLayer();
        layer.clearLayers();
        _getMrmsRadarSiteLocations(bounds).forEach((site) => {
            layer.addLayer(L.circleMarker([site.lat, site.lon], _MRMS_RADAR_SITE_POINT_STYLE));
        });
        if (!map.hasLayer(layer)) {
            layer.addTo(map);
        }
        if (typeof layer.bringToFront === 'function') {
            layer.bringToFront();
        }
    }
    const _SPC_REPORT_COLORS = {
        torn: '#ff4d4f',
        wind: '#26a9ff',
        hail: '#66e06a',
        other: '#f5d06b',
    };
    const RTMA_POINTS_DEBOUNCE_MS = 180;
    const RTMA_POINTS_MIN_FETCH_INTERVAL_MS = 500;
    const SCRUBBER_PLAYBACK_SPEEDS = [0.25, 0.5, 1, 1.5, 2, 3, 4];
    const RTMA_SCRUB_PLAY_INTERVAL_MS = 300;
    const RTMA_SCRUB_LOOP_HOLD_MS = 2000;
    const RTMA_SCRUB_SWAP_FADE_MS = 90;
    const RADAR_CROSSFADE_MS = 10;
    const SATELLITE_CROSSFADE_MS = RADAR_CROSSFADE_MS;
    const SATELLITE_LOOKBACK_HOURS_MAX = 12;
    const SATELLITE_FRAME_REQUEST_MAX = 360;
    const SATELLITE_LOOKBACK_RELOAD_DEBOUNCE_MS = 250;
    const SATELLITE_MANUAL_SCRUB_DEBOUNCE_MS = 80;
    const SATELLITE_TILE_READY_TIMEOUT_MS = 15000;
    const SATELLITE_INITIAL_TILE_READY_TIMEOUT_MS = 45000;
    const SATELLITE_HOT_FRAME_RADIUS = 3;
    const SATELLITE_PROGRESSIVE_REDRAW_DELAYS_MS = [2500, 6000, 12000, 20000];
    const SATELLITE_ANIMATION_RETAIN_LAYER_LIMIT = 72;
    const SATELLITE_PREFETCH_AHEAD_FRAMES = 8;
    const SATELLITE_PREFETCH_BEHIND_FRAMES = 2;
    const SATELLITE_PREFETCH_MAX_CONCURRENT = 2;
    const SATELLITE_PREFETCH_MAX_TILES_PER_FRAME = 32;
    const SATELLITE_PREFETCH_MAX_QUEUE_TILES = 180;
    const SATELLITE_PREFETCH_DEBOUNCE_MS = 220;
    const SATELLITE_PREFETCH_RETRY_AFTER_MS = 20000;
    const SATELLITE_PREFETCH_SEEN_LIMIT = 1200;
    const RTMA_SCRUB_POINTS_ONLY = false;
    const RADAR_AUTO_REFRESH_MS = 3 * 60 * 1000; // 3 minutes
    const SATELLITE_AUTO_REFRESH_MS = 5 * 60 * 1000;
    const SATELLITE_ANIMATE_AUTO_REFRESH_MS = SATELLITE_AUTO_REFRESH_MS;
    const RADAR_MULTI_SITE_MAX = 5;
    const RADAR_MULTI_SITE_Z_BASE = 320;
    const RADAR_MULTI_SITE_Z_STEP = 1;
    const RADAR_MULTI_SITE_Z_MIN = 304;
    const IEM_RADAR_OVERLAY_REFRESH_MS = 5 * 60 * 1000;
    const RTMA_STREAM_MAX_HOURS = {
        rtma_hourly: 24,
        rtma_rapid_update: 6,
    };
    const _FREEZING_ISOTHERM_ENABLED = true; // temporary diagnostic overlay
    const _FREEZING_ISOTHERM_PRODUCTS = new Set(['station_plot', 'temperature', 'feels_like', 'dew_point']);

    // ── Style functions ──────────────────────────────────────────────────────
    function alertStyle(feat) {
        const event = feat?.properties?.event || '';
        const color = ALERT_COLORS[event] || ALERT_DEFAULT;
        // Z-order: Tornado > Severe Thunderstorm > Flash Flood > others
        let zIndex = 200; // default for all other alerts
        if (event === 'Flash Flood Warning') zIndex = 220;
        if (event === 'Severe Thunderstorm Warning') zIndex = 240;
        if (event === 'Tornado Warning') zIndex = 260;
        return { color, weight: 1.5, fillColor: color, fillOpacity: alertsOpacity * 0.5, opacity: alertsOpacity, zIndex };
    }

    function _spcFeatureColors(feat, fallback) {
        const stroke = feat?.properties?.stroke || feat?.properties?.STROKE || fallback.stroke;
        const fill = feat?.properties?.fill || feat?.properties?.FILL || fallback.fill;
        return { stroke, fill };
    }

    function spcCatStyle(feat) {
        const label = (feat?.properties?.LABEL || feat?.properties?.label || '').toUpperCase();
        const c = _spcFeatureColors(feat, SPC_CAT_COLORS[label] || { fill: '#aaaaaa', stroke: '#555' });
        return { color: c.stroke, weight: 1, fillColor: c.fill, fillOpacity: spcOpacity, opacity: spcStrokeOpacity };
    }

    function spcFireStyle(feat) {
        const label = feat?.properties?.LABEL || feat?.properties?.label || '';
        const c = _spcFeatureColors(feat, SPC_FIRE_COLORS[label] || { fill: '#aaaaaa', stroke: '#555' });
        return { color: c.stroke, weight: 1, fillColor: c.fill, fillOpacity: spcOpacity, opacity: spcStrokeOpacity };
    }

    function spcProbStyle(feat) {
        const dn = String(feat?.properties?.dn || feat?.properties?.DN || '');
        const label = (feat?.properties?.LABEL || '').replace('%', '');
        const key = dn || label;
        const c = _spcFeatureColors(feat, SPC_PROB_COLORS[key] || { fill: '#aaaaaa', stroke: '#555' });
        return { color: c.stroke, weight: 1, fillColor: c.fill, fillOpacity: spcOpacity, opacity: spcStrokeOpacity };
    }

    // Style function for both probability and CIG zones
    // CIG zones get SVG hatch pattern fills based on intensity level (1, 2, or 3)
    // Probabilistic zones get solid fills
    function _spcProbCigStyle(feat) {
        const dn = String(feat?.properties?.dn ?? feat?.properties?.DN ?? '').trim();
        const label = String(feat?.properties?.LABEL || feat?.properties?.label || '').toUpperCase();
        const label2 = String(feat?.properties?.LABEL2 || feat?.properties?.label2 || '').toUpperCase();
        const labelDigits = (label.match(/CIG\s*([123])/) || [])[1] || '';
        const isCig = !!labelDigits || label2.includes('CONDITIONAL INTENSITY');
        const key = isCig
            ? `CIG${labelDigits || '1'}`
            : (dn || label.replace('%', ''));
        const c = _spcFeatureColors(feat, SPC_PROB_COLORS[key] || { fill: '#aaaaaa', stroke: '#555555' });

        // For CIG zones, apply hatching pattern with base color underneath
        // For probabilistic zones, use solid fill
        if (isCig) {
            return {
                color: c.stroke,
                weight: 2,
                fillColor: c.fill,
                fillOpacity: spcOpacity,
                opacity: spcStrokeOpacity,
            };
        }

        return {
            color: c.stroke,
            weight: 1,
            fillColor: c.fill,
            fillOpacity: spcOpacity,
            opacity: spcStrokeOpacity,
        };
    }

    // ── Popup builders ───────────────────────────────────────────────────────
    function _alertMessagePreview(props, maxLines = 8) {
        const raw = String(
            props?.description
            || props?.summary
            || props?.instruction
            || '',
        ).trim();
        if (!raw) return '';
        const lines = raw
            .split(/\r?\n+/)
            .map((line) => line.trim())
            .filter(Boolean)
            .slice(0, Math.max(1, maxLines));
        return lines.map((line) => _escapeHtml(line)).join('<br>');
    }

    function _alertFeatureCenterLatLng(feat) {
        const geom = feat?.geometry;
        if (!geom) return null;

        const bounds = { minLat: Infinity, maxLat: -Infinity, minLng: Infinity, maxLng: -Infinity };
        const visit = (node) => {
            if (!Array.isArray(node)) return;
            if (node.length >= 2 && Number.isFinite(node[0]) && Number.isFinite(node[1])) {
                const lng = Number(node[0]);
                const lat = Number(node[1]);
                bounds.minLat = Math.min(bounds.minLat, lat);
                bounds.maxLat = Math.max(bounds.maxLat, lat);
                bounds.minLng = Math.min(bounds.minLng, lng);
                bounds.maxLng = Math.max(bounds.maxLng, lng);
                return;
            }
            for (const child of node) visit(child);
        };

        visit(geom.coordinates);
        if (!Number.isFinite(bounds.minLat) || !Number.isFinite(bounds.minLng)) return null;
        return {
            lat: (bounds.minLat + bounds.maxLat) / 2,
            lng: (bounds.minLng + bounds.maxLng) / 2,
        };
    }

    function _alertForecastUrl(feat, preferredLatLng = null) {
        const p = feat?.properties || {};
        const ugcList = Array.isArray(p?.geocode?.UGC) ? p.geocode.UGC : [];
        const sameList = Array.isArray(p?.geocode?.SAME) ? p.geocode.SAME : [];

        const zone = ugcList.find((code) => /^[A-Z]{2}Z\d{3}$/.test(String(code || '').trim())) || '';
        const stateFromUgc = zone ? zone.slice(0, 2) : '';
        const same = sameList.find((code) => /^\d{6}$/.test(String(code || '').trim())) || '';
        const county = (stateFromUgc && same)
            ? `${stateFromUgc}C${same.slice(3)}`
            : '';

        const latlng = preferredLatLng && Number.isFinite(preferredLatLng.lat) && Number.isFinite(preferredLatLng.lng)
            ? preferredLatLng
            : _alertFeatureCenterLatLng(feat);

        if (!zone || !latlng) return '';

        const params = new URLSearchParams();
        params.set('warnzone', zone);
        if (county) params.set('warncounty', county);
        params.set('firewxzone', zone);
        const firstArea = String(p.areaDesc || '').split(';')[0].trim();
        if (firstArea) params.set('local_place1', stateFromUgc ? `${firstArea} ${stateFromUgc}` : firstArea);
        params.set('product1', String(p.event || 'Hazard Alert'));
        params.set('lat', Number(latlng.lat).toFixed(4));
        params.set('lon', Number(latlng.lng).toFixed(4));
        return `https://forecast.weather.gov/showsigwx.php?${params.toString()}`;
    }

    function _alertCwaCode(feat) {
        const p = feat?.properties || {};
        const awips = Array.isArray(p?.parameters?.AWIPSidentifier)
            ? String(p.parameters.AWIPSidentifier[0] || '').trim().toUpperCase()
            : '';
        if (awips.length >= 3) {
            return awips.slice(-3);
        }

        const wmo = Array.isArray(p?.parameters?.WMOidentifier)
            ? String(p.parameters.WMOidentifier[0] || '').trim().toUpperCase()
            : '';
        const wmoMatch = wmo.match(/\bK([A-Z]{3})\b/);
        if (wmoMatch) {
            return wmoMatch[1];
        }

        const sender = String(p?.sender || '').trim().toUpperCase();
        const senderMatch = sender.match(/([A-Z]{3})@/);
        if (senderMatch) {
            return senderMatch[1];
        }

        return '';
    }

    function _alertWwaFallbackUrl(feat) {
        const p = feat?.properties || {};
        const cwa = _alertCwaCode(feat);
        const eventName = String(p?.event || '').trim();
        if (!cwa || !eventName) return '';

        const params = new URLSearchParams();
        params.set('cwa', cwa);
        params.set('wwa', eventName.toLowerCase());
        return `https://forecast.weather.gov/wwamap/wwatxtget.php?${params.toString()}`;
    }

    function _alertExternalUrl(feat, preferredLatLng = null) {
        const forecastUrl = _alertForecastUrl(feat, preferredLatLng);
        if (forecastUrl) return forecastUrl;
        const wwaUrl = _alertWwaFallbackUrl(feat);
        if (wwaUrl) return wwaUrl;
        // Fallback: use source_url (e.g. SPC watch/MD detail page)
        const sourceUrl = String(feat?.properties?.source_url || '').trim();
        return sourceUrl || '';
    }

    function _alertExternalLinkHtml(feat, preferredLatLng = null) {
        const url = _alertExternalUrl(feat, preferredLatLng);
        if (!url) return '';
        return `<br><small><a href="${_escapeHtml(url)}" target="_blank" rel="noopener noreferrer">View full alert text</a></small>`;
    }

    function _alertActionLinkHtml(feat, preferredLatLng = null) {
        const url = _alertExternalUrl(feat, preferredLatLng);
        if (!url) return '';
        return `<a class="wx-alert-action-link" href="${_escapeHtml(url)}" target="_blank" rel="noopener noreferrer">View Full Alert Text</a>`;
    }

    function alertPopup(feat) {
        const p = feat.properties || {};
        const event = p.event || 'Unknown Alert';
        const headline = p.headline || '';
        const expires = p.expires ? new Date(p.expires).toLocaleString() : '';
        const preview = _alertMessagePreview(p);
        const externalLink = _alertExternalLinkHtml(feat);
        return `<strong>${event}</strong><br>${headline}${expires ? '<br><em>Expires: ' + expires + '</em>' : ''}${preview ? '<br><small>' + preview + '</small>' : ''}${externalLink}`;
    }

    function _ringContainsPoint(ring, lng, lat) {
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

    function _polygonContainsPoint(coords, lng, lat) {
        if (!Array.isArray(coords) || !coords.length) return false;
        if (!_ringContainsPoint(coords[0], lng, lat)) return false;
        for (let i = 1; i < coords.length; i++) {
            if (_ringContainsPoint(coords[i], lng, lat)) return false;
        }
        return true;
    }

    // Returns the zoom-bucket string for the current map zoom level.
    // Used to select between full and simplified display geometry on the alerts endpoint.
    // Threshold ≤5 matches CONUS-level view where simplification provides the most benefit.
    function _alertsZoomBucket() {
        return map.getZoom() <= 5 ? 'low' : 'high';
    }

    function _alertsViewportPadForZoom(zoom) {
        if (zoom >= 9) return 0.2;
        if (zoom >= 7) return 0.28;
        return 0.35;
    }

    function _alertsViewportParams() {
        try {
            const zoom = map.getZoom();
            const pad = _alertsViewportPadForZoom(zoom);
            const b = map.getBounds().pad(pad);
            return {
                west: b.getWest().toFixed(4),
                east: b.getEast().toFixed(4),
                south: b.getSouth().toFixed(4),
                north: b.getNorth().toFixed(4),
            };
        } catch (_) {
            return {};
        }
    }

    function _alertsRequestScopeFromRegion() {
        const regionCode = String(byId('weather-region')?.value || 'CONUS').toUpperCase();
        const stateCode = /^[A-Z]{2}$/.test(regionCode) ? regionCode : null;
        if (!stateCode) {
            return { stateCode, extraParams: {} };
        }
        // State-region views use buffered viewport filtering instead of strict state-only.
        return {
            stateCode: null,
            extraParams: _alertsViewportParams(),
        };
    }

    // Filter out NWS test products from map display.
    function _isTestAlertFeature(feat) {
        const p = feat?.properties || {};
        const status = String(p.status || '').toLowerCase().trim();
        const messageType = String(p.messageType || '').toLowerCase().trim();
        const event = String(p.event || '').toLowerCase().trim();
        const headline = String(p.headline || '').toLowerCase().trim();
        return (
            status === 'test'
            || messageType === 'test'
            || event === 'test message'
            || headline.startsWith('test message')
        );
    }

    // Remove canceled/expired alerts. Shared by full and display collections.
    function _stripInactiveAlerts(rawFeatures) {
        return (rawFeatures || []).filter((f) => {
            if (_isTestAlertFeature(f)) return false;
            if (f?.properties?.messageType === 'Cancel') return false;
            const action = _vtecAction(f);
            return action !== 'CAN' && action !== 'EXP';
        });
    }

    function _filterAlertsByCategories(rawFeatures, checkedCategories) {
        return (rawFeatures || []).filter((f) => _matchesCheckedCategories(f, checkedCategories) && _matchesWarningSubtypeFilter(f));
    }

    function _matchesWarningSubtypeFilter(feat) {
        const event = String(feat?.properties?.event || '');
        if (event === _WARN_FILTER_EVENT_TYPES.tor) return _warningsFilterEnabled.has('tor');
        if (event === _WARN_FILTER_EVENT_TYPES.svr) return _warningsFilterEnabled.has('svr');
        if (event === _WARN_FILTER_EVENT_TYPES.ffw) return _warningsFilterEnabled.has('ffw');
        return true;
    }

    function _buildAlertsLayer(displayFeatures) {
        return L.geoJSON({ type: 'FeatureCollection', features: displayFeatures }, {
            style: alertStyle,
            onEachFeature: (feat, layer) => {
                layer.on('click', (e) => {
                    if (_stormTrackDrawMode) return;
                    if (e?.latlng) {
                        _setRegionAlertLocationState();
                        _openAlertsPagerAt(e.latlng);
                    }
                });
                // Throttled hover — PIP is expensive at CONUS scale with many polygons.
                // Click is immediate; hover is deduplicated within _HOVER_THROTTLE_MS window.
                // Use mousemove so the tooltip recomputes as the cursor crosses overlapping
                // polygons (e.g. a Severe Tstorm Warning sitting inside a Tornado Watch).
                layer.on('mousemove', _makeThrottledHoverHandler(() => feat, () => layer));
                layer.on('mouseout', () => layer.closeTooltip());
                // Pulse high-priority polygons.
                if (ALERT_PULSE_EVENTS.has(feat?.properties?.event || '')) {
                    layer.on('add', () => layer.getElement?.()?.classList.add('wx-alert-pulse'));
                }
            },
        });
    }

    // Atomic layer swap: keep old layer visible until the replacement is ready.
    function _swapAlertsLayer(nextLayer) {
        const prevLayer = alertsLayer;
        alertsLayer = nextLayer || null;
        if (alertsLayer) alertsLayer.addTo(map);
        if (prevLayer && map.hasLayer(prevLayer)) map.removeLayer(prevLayer);
    }

    // Re-apply alert category filters from in-memory datasets without waiting on network.
    function _applyInMemoryAlertCategoryFilter() {
        const checkedCategories = _getCheckedAlertCategories();
        if (!checkedCategories.length) {
            _allAlertFeatures = [];
            _alertsDisplayFeatures = [];
            _swapAlertsLayer(null);
            const countEl = byId('weather-alerts-count');
            if (countEl) countEl.textContent = '0 active alert(s)';
            setLegend(null);
            _renderActiveWarningsPanel();
            return;
        }

        const fullFeatures = _filterAlertsByCategories(_alertsFullBaseFeatures, checkedCategories);
        const displayFeatures = _filterAlertsByCategories(_alertsDisplayBaseFeatures, checkedCategories);

        _allAlertFeatures = fullFeatures;
        _alertsDisplayFeatures = displayFeatures;

        const nextLayer = _buildAlertsLayer(displayFeatures);
        _swapAlertsLayer(nextLayer);

        buildAlertsLegend(fullFeatures);
        const countEl = byId('weather-alerts-count');
        if (countEl) countEl.textContent = `${fullFeatures.length} active alert(s)`;
        _renderActiveWarningsPanel();
    }

    // Re-fetch only the display geometry and swap the Leaflet render layer.
    // Called on zoom-bucket transitions to update the display without re-fetching full data.
    async function _refreshAlertsDisplayLayer() {
        if (!_alertsFullBaseFeatures.length || !_canApplyAlertsResponse()) return;
        const checkedCategories = _getCheckedAlertCategories();
        if (!checkedCategories.length) return;

        const scope = _alertsRequestScopeFromRegion();
        const zoomBucket = _alertsZoomBucket();

        try {
            const displayUrl = _buildAlertsUrl(scope.stateCode, {
                geometry_mode: 'display',
                zoom_bucket: zoomBucket,
                ...scope.extraParams,
            });
            const resp = await fetch(displayUrl, { cache: 'no-store' });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const displayGeojson = await resp.json();

            if (!_canApplyAlertsResponse()) return;

            _alertsDisplayBaseFeatures = _stripInactiveAlerts(displayGeojson.features);
            const displayFeatures = _filterAlertsByCategories(_alertsDisplayBaseFeatures, checkedCategories);
            const fullFeatures = _filterAlertsByCategories(_alertsFullBaseFeatures, checkedCategories);

            _allAlertFeatures = fullFeatures;
            _alertsDisplayFeatures = displayFeatures;

            const nextLayer = _buildAlertsLayer(displayFeatures);
            _swapAlertsLayer(nextLayer);

            buildAlertsLegend(fullFeatures);
            _renderActiveWarningsPanel();
            const countEl = byId('weather-alerts-count');
            if (countEl) countEl.textContent = `${fullFeatures.length} active alert(s)`;
        } catch (err) {
            // On failure, keep the current layer — do not clear it.
            console.warn('[alerts] Display layer refresh failed:', err.message);
        }
    }

    // Compute the axis-aligned bounding box for a feature geometry.
    // Result is cached on the feature object to avoid repeated traversal.
    function _featureBbox(feat) {
        if (feat._bbox) return feat._bbox;
        const coords = [];
        const geom = feat?.geometry;
        if (!geom) return null;
        const collect = (ring) => { for (const [x, y] of ring) coords.push([x, y]); };
        if (geom.type === 'Polygon') {
            for (const ring of (geom.coordinates || [])) collect(ring);
        } else if (geom.type === 'MultiPolygon') {
            for (const poly of (geom.coordinates || []))
                for (const ring of poly) collect(ring);
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

    function _featureContainsLatLng(feat, latlng) {
        const geom = feat?.geometry;
        if (!geom || !latlng) return false;
        const lng = latlng.lng;
        const lat = latlng.lat;
        if (!Number.isFinite(lng) || !Number.isFinite(lat)) return false;

        // Fast bbox rejection before the full ray-cast PIP traversal.
        const bb = _featureBbox(feat);
        if (bb && (lng < bb.minX || lng > bb.maxX || lat < bb.minY || lat > bb.maxY)) return false;

        if (geom.type === 'Polygon') {
            return _polygonContainsPoint(geom.coordinates, lng, lat);
        }
        if (geom.type === 'MultiPolygon') {
            return (geom.coordinates || []).some((poly) => _polygonContainsPoint(poly, lng, lat));
        }
        return false;
    }

    // Throttle limit (ms) for alert polygon hover hit-testing.
    // Prevents expensive _sortedAlertsForPoint PIP scans from running on every
    // mouseover event during rapid pointer movement; click is never throttled.
    const _HOVER_THROTTLE_MS = 80;
    let _hoverThrottleTimer = null;

    // Returns a mousemove handler that throttles the expensive PIP call.
    // `layerRef` is expected to have .bindTooltip() / .openTooltip() methods.
    function _makeThrottledHoverHandler(getFeat, getLayer) {
        return function (e) {
            if (_hoverThrottleTimer !== null) return;   // still within throttle window
            _hoverThrottleTimer = setTimeout(() => { _hoverThrottleTimer = null; }, _HOVER_THROTTLE_MS);
            const lyr = getLayer();
            if (!lyr) return;
            const feat = getFeat();
            const alerts = _sortedAlertsForPoint(e.latlng);
            const lines = (alerts.length ? alerts : [feat])
                .map(f => {
                    const ev = f?.properties?.event || 'Unknown';
                    const color = ALERT_COLORS[ev] || ALERT_DEFAULT;
                    return `<span style="color:${color};font-weight:700">\u25cf</span> ${_escapeHtml(ev)}`;
                }).join('<br>');
            // If the tooltip already exists on this layer, update its content in
            // place so overlapping polygons recompute as the cursor moves; only
            // bind on first hover.
            if (lyr.getTooltip()) {
                lyr.setTooltipContent(lines);
            } else {
                lyr.bindTooltip(lines, { sticky: true, opacity: 0.95, className: 'wx-alert-hover-tip' });
            }
            lyr.openTooltip(e.latlng);
        };
    }

    function _alertPriorityValue(feat) {
        const p = feat?.properties || {};
        const priorityRaw = Number(p.priority);
        if (Number.isFinite(priorityRaw)) return priorityRaw;
        return ALERT_PRIORITY[p.event] ?? 999;
    }

    function _alertExpiresTs(feat) {
        const expires = Date.parse(feat?.properties?.expires || '');
        return Number.isFinite(expires) ? expires : Number.MAX_SAFE_INTEGER;
    }

    // Extract the VTEC action code (NEW, CON, EXT, CAN, EXP, …) from a feature.
    function _vtecAction(feat) {
        const vtecArr = feat?.properties?.parameters?.VTEC;
        if (!Array.isArray(vtecArr) || !vtecArr.length) return null;
        const m = String(vtecArr[0]).match(/\/O\.([A-Z]{3})\./);
        return m ? m[1] : null;
    }

    // Return a human-readable "X min" / "Xh Ym" string for time remaining until isoStr.
    function _relExpires(isoStr) {
        if (!isoStr) return '';
        const diffMs = Date.parse(isoStr) - Date.now();
        if (!Number.isFinite(diffMs) || diffMs < 0) return 'expired';
        const mins = Math.round(diffMs / 60_000);
        if (mins < 60) return `${mins} min`;
        const hrs = Math.floor(mins / 60);
        const rem = mins % 60;
        return rem ? `${hrs}h ${rem}m` : `${hrs}h`;
    }

    function _sortedAlertsForPoint(latlng) {
        return (_allAlertFeatures || [])
            .filter((feat) => _featureContainsLatLng(feat, latlng))
            .sort((a, b) => {
                const pDiff = _alertPriorityValue(a) - _alertPriorityValue(b);
                if (pDiff !== 0) return pDiff;
                const eDiff = _alertExpiresTs(a) - _alertExpiresTs(b);
                if (eDiff !== 0) return eDiff;
                const aEvent = a?.properties?.event || '';
                const bEvent = b?.properties?.event || '';
                return aEvent.localeCompare(bEvent);
            });
    }

    function _buildAlertsPagerContent(features, pageIndex, preferredLatLng = null) {
        const total = features.length;
        const idx = Math.max(0, Math.min(pageIndex, total - 1));
        const feat = features[idx] || {};
        const p = feat?.properties || {};
        const event = p.event || 'Unknown Alert';
        const headline = p.headline || '';
        const expires = p.expires ? new Date(p.expires).toLocaleString() : '';
        const expiresRel = _relExpires(p.expires);
        const metaBadge = [p.severity, p.urgency, p.certainty].filter(Boolean).join(' · ');
        const preview = _alertMessagePreview(p);
        const actionLink = _alertActionLinkHtml(feat, preferredLatLng);
        const navDisabled = total <= 1 ? 'disabled' : '';
        const dots = features.map((_, i) => {
            const active = i === idx ? ' is-active' : '';
            const aria = `Alert ${i + 1} of ${total}`;
            return `<button type="button" class="wx-alert-page-dot${active}" data-alert-page="${i}" aria-label="${aria}" title="${aria}"></button>`;
        }).join('');
        const expiresHtml = expires
            ? '<br><em>Expires: ' + expires + (expiresRel ? ' <span class="wx-alert-rel-time">(in ' + expiresRel + ')</span>' : '') + '</em>'
            : '';
        const actionsHtml = (
            `<div class="wx-alert-actions">`
            + (actionLink || '')
            + `<button type="button" class="wx-alert-action-zoom" data-alert-zoom="1">Zoom To Alert</button>`
            + `</div>`
        );

        return (
            `<div class="wx-alert-pager" data-alert-pager="1">`
            + `<div class="wx-alert-page">`
            + `<strong>${event}</strong>`
            + (metaBadge ? `<div class="wx-alert-meta">${_escapeHtml(metaBadge)}</div>` : '')
            + `<br>${headline}${expiresHtml}${preview ? '<br><small>' + preview + '</small>' : ''}${actionsHtml}`
            + `</div>`
            + `<div class="wx-alert-page-controls">`
            + `<button type="button" class="wx-alert-page-nav" data-alert-nav="prev" aria-label="Previous alert" ${navDisabled}>&lsaquo;</button>`
            + `<div class="wx-alert-page-dots">${dots}</div>`
            + `<button type="button" class="wx-alert-page-nav" data-alert-nav="next" aria-label="Next alert" ${navDisabled}>&rsaquo;</button>`
            + `</div>`
            + `</div>`
        );
    }

    function _updateAlertsPager(newIndex) {
        if (!_activeAlertsPopup?.popup || !_activeAlertsPopup?.features?.length) return;
        const total = _activeAlertsPopup.features.length;
        _activeAlertsPopup.index = ((newIndex % total) + total) % total;
        _activeAlertsPopup.popup.setContent(
            _buildAlertsPagerContent(
                _activeAlertsPopup.features,
                _activeAlertsPopup.index,
                _activeAlertsPopup.latlng || null,
            ),
        );
    }

    function _openAlertsPagerAt(latlng) {
        const features = _sortedAlertsForPoint(latlng);
        if (!features.length) return;
        // Unified popup style: every alert click opens the immersive detail
        // panel. Pagination across overlapping alerts at the click point uses
        // the panel's built-in next/prev nav. The New Alert flow continues to
        // call _openNewAlertDetail directly with its own source feature.
        _openNewAlertDetail(latlng, features[0]);
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
        if (featIsValid(_activeNewAlertDetail?.features?.[_activeNewAlertDetail.index])) {
            return _activeNewAlertDetail.features[_activeNewAlertDetail.index];
        }
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
            const paths = ['data/place-town.ndjson', 'data/place-village.ndjson'];
            const urls = paths.map((p) => apiUrl(p));
            const responses = await Promise.all(urls.map((u) => fetch(u, { cache: 'force-cache' })));
            const texts = await Promise.all(responses.map(async (resp, idx) => {
                if (!resp.ok) {
                    const path = paths[idx] || 'places file';
                    throw new Error(`Failed loading ${path} (${resp.status}).`);
                }
                return resp.text();
            }));
            const merged = [];
            for (const txt of texts) merged.push(..._parseNdjsonPlaces(txt));
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

        const listItems = rows.map((r) => {
            const state = r.state ? `, ${r.state}` : '';
            return [
                '<li>',
                `<span class="wx-stormtrack-place-name">${_escapeHtml(r.name)}${_escapeHtml(state)}</span>`,
                `<span class="wx-stormtrack-place-time">${_escapeHtml(r.arrivalLabel)}</span>`,
                '</li>',
            ].join('');
        }).join('');
        body.innerHTML = `<ol class="wx-stormtrack-places-list">${listItems}</ol>`;
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

    // ── Immersive new-alert detail panel ─────────────────────────────────────
    let _activeNewAlertDetail = null;

    function _firstParam(p, key) {
        const arr = p?.parameters?.[key];
        if (Array.isArray(arr) && arr.length) {
            const v = String(arr[0] || '').trim();
            return v || '';
        }
        return '';
    }

    function _formatSentExpires(p) {
        const fmt = (iso) => {
            if (!iso) return '';
            try {
                return new Date(iso).toLocaleString([], {
                    month: 'short', day: 'numeric',
                    hour: 'numeric', minute: '2-digit',
                });
            } catch (_) { return ''; }
        };
        return { sent: fmt(p?.sent), expires: fmt(p?.expires) };
    }

    function _buildThreatChips(p) {
        const chips = [];
        const push = (label, value) => {
            const v = String(value || '').trim();
            if (v && v.toLowerCase() !== 'none') chips.push({ label, value: v });
        };
        push('Tornado', _firstParam(p, 'tornadoDetection') || _firstParam(p, 'tornadoThreat'));
        const hailThreat = _firstParam(p, 'hailThreat');
        const maxHail = _firstParam(p, 'maxHailSize');
        if (hailThreat || maxHail) {
            const parts = [hailThreat, maxHail ? `max ${maxHail}\u2033` : ''].filter(Boolean);
            push('Hail', parts.join(' · '));
        }
        const windThreat = _firstParam(p, 'windThreat');
        const maxWind = _firstParam(p, 'maxWindGust');
        if (windThreat || maxWind) {
            const parts = [windThreat, maxWind ? `max ${maxWind}` : ''].filter(Boolean);
            push('Wind', parts.join(' · '));
        }
        push('Flash Flood', _firstParam(p, 'flashFloodDetection'));
        return chips;
    }

    function _splitDescriptionSections(rawDesc) {
        const text = String(rawDesc || '').trim();
        if (!text) return { intro: '', locations: '' };
        // NWS uses "* LOCATIONS IMPACTED INCLUDE..." or "...LOCATIONS IMPACTED INCLUDE..."
        const m = text.match(/(?:^|\n)\s*\*?\s*LOCATIONS IMPACTED INCLUDE[\s\S]*$/i);
        if (m) {
            const intro = text.slice(0, m.index).trim();
            const locBlock = m[0].replace(/^[\s\*]*LOCATIONS IMPACTED INCLUDE[\.\s]*/i, '').trim();
            return { intro, locations: locBlock };
        }
        return { intro: text, locations: '' };
    }

    function _formatTextBlock(text) {
        // Convert NWS plain-text to safe HTML: preserve paragraphs (blank lines), join wrapped lines.
        const paras = String(text || '')
            .split(/\n\s*\n/)
            .map((para) => para.replace(/\s*\n\s*/g, ' ').trim())
            .filter(Boolean);
        return paras.map((para) => `<p>${_escapeHtml(para)}</p>`).join('');
    }

    function _formatLocationsImpacted(text) {
        const cleaned = String(text || '').replace(/\s+/g, ' ').trim();
        if (!cleaned) return '';
        return `<p>${_escapeHtml(cleaned)}</p>`;
    }

    function _extractSpcMdPeakChips(rawText) {
        let text = String(rawText || '');
        if (!text) return { chips: [], cleanedText: '' };
        text = text.replace(/\r\n?/g, '\n');

        const specs = [
            {
                label: 'Tornado',
                re: /MOST\s+PROBABLE\s+PEAK\s+TORNADO\s+INTENSITY\.{3}\s*([^\n\r]+?)(?=\s+MOST\s+PROBABLE\s+PEAK\s+|$)/i,
            },
            {
                label: 'Wind Gust',
                re: /MOST\s+PROBABLE\s+PEAK\s+WIND\s+GUST\.{3}\s*([^\n\r]+?)(?=\s+MOST\s+PROBABLE\s+PEAK\s+|$)/i,
            },
            {
                label: 'Hail Size',
                re: /MOST\s+PROBABLE\s+PEAK\s+HAIL\s+SIZE\.{3}\s*([^\n\r]+?)(?=\s+MOST\s+PROBABLE\s+PEAK\s+|$)/i,
            },
        ];

        const chips = [];
        for (const spec of specs) {
            const match = text.match(spec.re);
            if (!match) continue;
            const value = String(match[1] || '').replace(/\s+/g, ' ').trim();
            if (value) chips.push({ label: spec.label, value });
            text = text.replace(match[0], ' ');
        }

        return {
            chips,
            // Preserve newlines so bulletin sections can be parsed/rendered.
            cleanedText: text
                .replace(/[^\S\n]{2,}/g, ' ')
                .replace(/\n{3,}/g, '\n\n')
                .trim(),
        };
    }

    function _extractSpcMdSections(text) {
        const raw = String(text || '').replace(/\r\n?/g, '\n').trim();
        if (!raw) return { preface: '', summary: '', discussion: '' };

        const summaryMatch = raw.match(/\bSUMMARY\.{3}\s*([\s\S]*?)(?=\n\s*DISCUSSION\.{3}|$)/i);
        const discussionMatch = raw.match(/\bDISCUSSION\.{3}\s*([\s\S]*?)(?=\n\s*\.\.[A-Za-z]|\n\s*ATTN\.{3}|\n\s*LAT\.{3}|$)/i);

        const summaryIdx = raw.search(/\bSUMMARY\.{3}/i);
        const preface = summaryIdx > 0 ? raw.slice(0, summaryIdx).trim() : '';

        return {
            preface,
            summary: summaryMatch ? String(summaryMatch[1] || '').trim() : '',
            discussion: discussionMatch ? String(discussionMatch[1] || '').trim() : '',
        };
    }

    function _renderSpcMdBodyHtml(text) {
        const sections = _extractSpcMdSections(text);
        const prefaceHtml = sections.preface ? _formatTextBlock(sections.preface) : '';
        const summaryHtml = sections.summary ? `<section class="wx-nad-section"><h4>Summary</h4>${_formatTextBlock(sections.summary)}</section>` : '';
        const discussionHtml = sections.discussion ? `<section class="wx-nad-section"><h4>Discussion</h4>${_formatTextBlock(sections.discussion)}</section>` : '';
        const structured = summaryHtml || discussionHtml;
        if (!structured) return _formatTextBlock(text);
        return `${prefaceHtml}${summaryHtml}${discussionHtml}`;
    }

    function _buildNewAlertDetailHtml(feat, index, total) {
        const p = feat?.properties || {};
        const event = p.event || 'Alert';
        const color = ALERT_COLORS[event] || ALERT_DEFAULT;
        const badges = [p.severity, p.urgency, p.certainty]
            .filter(Boolean)
            .map((b) => `<span class="wx-nad-badge">${_escapeHtml(String(b))}</span>`)
            .join('');
        const { sent, expires } = _formatSentExpires(p);
        const expRel = _relExpires(p?.expires);
        const senderName = String(p.senderName || '').trim();
        const issuedLine = [
            sent ? `Issued ${_escapeHtml(sent)}` : '',
            expires ? `until ${_escapeHtml(expires)}` : '',
            senderName ? `by ${_escapeHtml(senderName)}` : '',
        ].filter(Boolean).join(' ');
        const expiresLine = expires
            ? `Expires: ${_escapeHtml(expires)}${expRel ? ` <span class="wx-nad-countdown">(in ${_escapeHtml(expRel)})</span>` : ''}`
            : '';
        const mdPeak = _extractSpcMdPeakChips(p.description);
        const descriptionForBody = mdPeak.cleanedText || String(p.description || '');
        const { intro, locations } = _splitDescriptionSections(descriptionForBody);
        const isSpcMd = /mesoscale discussion/i.test(String(p.event || ''));
        const descHtml = isSpcMd ? _renderSpcMdBodyHtml(intro) : _formatTextBlock(intro);
        const locHtml = locations ? _formatLocationsImpacted(locations) : '';
        const instrHtml = _formatTextBlock(p.instruction || '');
        const threatChips = _buildThreatChips(p);
        const allChips = threatChips.concat(mdPeak.chips);
        const chipsHeading = mdPeak.chips.length
            ? '<h4 class="wx-nad-peaks-title">Most Probable Peak</h4>'
            : '';
        const chipsHtml = allChips.length
            ? `${chipsHeading}<div class="wx-nad-chips">${allChips.map((c) => `<span class="wx-nad-chip"><strong>${_escapeHtml(c.label)}:</strong> ${_escapeHtml(c.value)}</span>`).join('')}</div>`
            : '';
        const fullUrl = _alertExternalUrl(feat);
        const linkHtml = fullUrl
            ? `<a class="wx-nad-fulllink" href="${_escapeHtml(fullUrl)}" target="_blank" rel="noopener noreferrer">View Full NWS Alert Text</a>`
            : '';
        const showZoomLink = map.getZoom() < 9;
        const zoomLinkHtml = showZoomLink
            ? `<button type="button" class="wx-nad-zoomlink" data-nad-zoom="1">Zoom to Alert</button>`
            : '';
        const navDisabled = total <= 1;
        const counter = total > 1 ? `<span class="wx-nad-counter">${index + 1} / ${total}</span>` : '';

        return [
            `<div class="wx-nad-header" style="border-color:${color}">`,
            `  <div class="wx-nad-title" style="color:${color}">${_escapeHtml(event)}</div>`,
            `  <button type="button" class="wx-nad-close" aria-label="Close">×</button>`,
            `</div>`,
            badges ? `<div class="wx-nad-badges">${badges}</div>` : '',
            issuedLine ? `<div class="wx-nad-issued">${issuedLine}</div>` : '',
            expiresLine ? `<div class="wx-nad-expires">${expiresLine}</div>` : '',
            chipsHtml ? `<div class="wx-nad-section">${chipsHtml}</div>` : '',
            `<div class="wx-nad-scroll">`,
            descHtml ? `<section class="wx-nad-section">${descHtml}</section>` : '',
            locHtml ? `<section class="wx-nad-section"><h4>Locations Impacted</h4>${locHtml}</section>` : '',
            instrHtml ? `<section class="wx-nad-section"><h4>Precautionary / Preparedness Actions</h4>${instrHtml}</section>` : '',
            `</div>`,
            linkHtml ? `<div class="wx-nad-footer">${linkHtml}${zoomLinkHtml ? '<br>' + zoomLinkHtml : ''}</div>` : (zoomLinkHtml ? `<div class="wx-nad-footer">${zoomLinkHtml}</div>` : ''),
            (!navDisabled || counter)
                ? `<div class="wx-nad-nav">
                       <button type="button" class="wx-nad-nav-btn" data-nad-nav="prev" aria-label="Previous alert"${navDisabled ? ' disabled' : ''}>‹</button>
                       ${counter}
                       <button type="button" class="wx-nad-nav-btn" data-nad-nav="next" aria-label="Next alert"${navDisabled ? ' disabled' : ''}>›</button>
                   </div>`
                : '',
        ].join('');
    }

    function _positionNewAlertDetail(panel, latlng) {
        const wrap = panel.parentElement;
        if (!wrap) return;
        const wrapRect = wrap.getBoundingClientRect();
        let preferRight = true;
        try {
            const pt = map.latLngToContainerPoint(latlng);
            preferRight = pt.x < (wrapRect.width / 2);
        } catch (_) { /* fallback right */ }
        panel.classList.toggle('is-right', preferRight);
        panel.classList.toggle('is-left', !preferRight);
    }

    function _closeNewAlertDetail() {
        const ctx = _activeNewAlertDetail;
        if (!ctx) return;
        const { panel, keyHandler, mapClickHandler, mapMoveHandler, dragCleanup } = ctx;
        if (keyHandler) document.removeEventListener('keydown', keyHandler);
        if (mapClickHandler) map.off('click', mapClickHandler);
        if (mapMoveHandler) map.off('movestart zoomstart', mapMoveHandler);
        if (dragCleanup) dragCleanup();
        if (panel?.parentElement) panel.parentElement.removeChild(panel);
        _activeNewAlertDetail = null;
    }

    // Auto-enable the persistent Radar Overlay when the user zooms into a new
    // alert polygon.
    function _ensureRadarOverlayOn() {
        const cb = byId('weather-alerts-radar');
        if (!cb || cb.checked) return;
        cb.checked = true;
        cb.dispatchEvent(new Event('change'));
    }

    function _renderNewAlertDetail() {
        const ctx = _activeNewAlertDetail;
        if (!ctx) return;
        const { panel, features, latlng } = ctx;
        const idx = ctx.index;
        panel.innerHTML = _buildNewAlertDetailHtml(features[idx], idx, features.length);
        panel.querySelector('.wx-nad-close')?.addEventListener('click', _closeNewAlertDetail);
        const zoomBtn = panel.querySelector('[data-nad-zoom]');
        if (zoomBtn) {
            zoomBtn.addEventListener('click', () => {
                const feat = ctx.features?.[ctx.index];
                const center = _alertFeatureCenterLatLng(feat) || latlng;
                if (!center) return;
                _setRegionAlertLocationState();
                map.flyTo(center, 9, { duration: 0.9 });
                _ensureRadarOverlayOn();
            });
        }
        panel.querySelectorAll('[data-nad-nav]').forEach((btn) => {
            btn.addEventListener('click', () => {
                const dir = btn.getAttribute('data-nad-nav');
                const total = ctx.features.length;
                if (total <= 1) return;
                ctx.index = dir === 'next'
                    ? (ctx.index + 1) % total
                    : (ctx.index - 1 + total) % total;
                _renderNewAlertDetail();
            });
        });
        // Anchor stays put per spec; only refresh side classification on initial mount.
        if (!ctx._positioned) {
            _positionNewAlertDetail(panel, latlng);
            ctx._positioned = true;
        }
    }

    function _openNewAlertDetail(latlng, sourceFeat, options = {}) {
        const ensureRadar = options.ensureRadar !== false;
        const useAlertStack = options.useAlertStack !== false;
        _stormTrackSelectedAlert = sourceFeat || null;
        // Clear the speed override when switching to an alert's own motion data.
        _clearSpeedOverride();
        _closeNewAlertDetail();
        // Close any normal alerts pager so views don't stack.
        if (_activeAlertsPopup?.popup) {
            try { map.closePopup(_activeAlertsPopup.popup); } catch (_) { /* ignore */ }
            _activeAlertsPopup = null;
        }

        const wrap = document.querySelector('.weather-map-wrap');
        if (!wrap) return;

        let features = [];
        let startIdx = 0;
        if (useAlertStack) {
            // Step through all alerts containing this point, but make sure the
            // triggering alert is shown first.
            features = _sortedAlertsForPoint(latlng);
            if (!features.length) features = [sourceFeat];
            const sourceId = sourceFeat?.id || sourceFeat?.properties?.id;
            startIdx = features.findIndex((f) => (f?.id || f?.properties?.id) === sourceId);
            if (startIdx < 0) {
                features = [sourceFeat, ...features.filter((f) => (f?.id || f?.properties?.id) !== sourceId)];
                startIdx = 0;
            }
        } else {
            features = Array.isArray(options.features) && options.features.length
                ? options.features
                : [sourceFeat];
        }

        const panel = document.createElement('div');
        panel.id = 'wx-new-alert-detail';
        panel.className = 'wx-new-alert-detail';
        panel.addEventListener('click', (e) => e.stopPropagation());
        wrap.appendChild(panel);

        // Make the detail panel draggable by its header, mirroring the
        // projected-arrivals panel behavior.
        let drag = null;
        const onDragMove = (evt) => {
            if (!drag) return;
            const x = evt.clientX - drag.wrapLeft - drag.dx;
            const y = evt.clientY - drag.wrapTop - drag.dy;
            panel.style.left = `${x}px`;
            panel.style.top = `${y}px`;
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
            if (e.key === 'Escape') _closeNewAlertDetail();
        };
        document.addEventListener('keydown', keyHandler);
        const mapClickHandler = () => {
            // Don't close while the user is placing storm-track or radar-cal points.
            if (_stormTrackDrawMode || _radarCalDrawMode) return;
            _closeNewAlertDetail();
        };
        // Defer by one tick so the click that opened this panel doesn't
        // immediately bubble to the map and close it.
        setTimeout(() => {
            if (!_activeNewAlertDetail) return;
            map.on('click', mapClickHandler);
        }, 0);
        // Close the panel if the user pans or zooms away (including the Home
        // button). Bind on the next tick so the initial flyTo's tail-end
        // movement doesn't immediately dismiss the panel we just opened.
        let mapMoveHandler = null;
        setTimeout(() => {
            if (!_activeNewAlertDetail) return;
            mapMoveHandler = () => _closeNewAlertDetail();
            _activeNewAlertDetail.mapMoveHandler = mapMoveHandler;
            map.on('movestart zoomstart', mapMoveHandler);
        }, 250);

        _activeNewAlertDetail = {
            panel,
            features,
            index: startIdx,
            latlng,
            keyHandler,
            mapClickHandler,
            mapMoveHandler: null,
            dragCleanup,
            _positioned: false,
        };
        _renderNewAlertDetail();

        const headerEl = panel.querySelector('.wx-nad-header');
        headerEl?.addEventListener('pointerdown', (evt) => {
            if (evt.target && evt.target.closest('.wx-nad-close, .wx-nad-nav-btn, a, button')) return;
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
        if (ensureRadar) _ensureRadarOverlayOn();
    }

    function _spcReportTypeKey(eventText) {
        const event = String(eventText || '').toLowerCase();
        if (event.includes('torn')) return 'torn';
        if (event.includes('wind')) return 'wind';
        if (event.includes('hail')) return 'hail';
        return 'other';
    }

    // FA icon class for tornado/wind; null = use circleMarker
    const _SPC_REPORT_FA_ICON = {
        torn: 'fa-solid fa-tornado',
        wind: 'fa-solid fa-wind',
    };

    function _spcReportMarker(feat, latlng) {
        const key = _spcReportTypeKey(feat?.properties?.event);
        const color = _SPC_REPORT_COLORS[key] || _SPC_REPORT_COLORS.other;
        const faClass = _SPC_REPORT_FA_ICON[key];
        if (faClass) {
            const icon = L.divIcon({
                className: '',
                html: `<i class="${faClass}" style="color:${color};font-size:16px;-webkit-text-stroke:0.5px #08111d;text-shadow:0 0 3px rgba(0,0,0,0.7);"></i>`,
                iconSize: [16, 16],
                iconAnchor: [8, 8],
                popupAnchor: [0, -10],
            });
            return L.marker(latlng, { icon });
        }
        return L.circleMarker(latlng, {
            radius: 5,
            color: '#08111d',
            weight: 1,
            fillColor: color,
            fillOpacity: 0.95,
            opacity: 1,
        });
    }

    function _spcReportPopup(feat) {
        const p = feat?.properties || {};
        const event = p.event || 'Storm Report';
        const magnitude = p.magnitude ? ` (${_escapeHtml(p.magnitude)})` : '';
        const place = [p.location, p.county, p.state].filter(Boolean).join(', ');
        const when = p.time ? `<br><em>Time:</em> ${_escapeHtml(p.time)}` : '';
        const where = place ? `<br><em>Location:</em> ${_escapeHtml(place)}` : '';
        const remarks = p.remarks ? `<br><small>${_escapeHtml(p.remarks)}</small>` : '';
        return `<strong>${_escapeHtml(event)}${magnitude}</strong>${when}${where}${remarks}`;
    }

    function _openSpcTextDetail(latlng, feat) {
        if (!latlng || !feat) return;
        _openNewAlertDetail(latlng, feat, { ensureRadar: false, useAlertStack: false });
    }

    function _spcWatchStyle(feat) {
        const type = String(feat?.properties?.watch_type || feat?.properties?.event || '').toLowerCase();
        const isTor = type.includes('tornado');
        const edge = isTor ? '#ffe066' : '#ff8ec7';
        const fill = isTor ? '#ffe066' : '#ff8ec7';
        return {
            color: edge,
            weight: 2,
            fillColor: fill,
            fillOpacity: 0.16,
            opacity: 1,
        };
    }

    function _spcMdStyle() {
        return {
            color: '#63d8ff',
            weight: 1.8,
            fillColor: '#63d8ff',
            fillOpacity: 0.12,
            opacity: 1,
        };
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

    function escapeHtml(value) {
        return String(value ?? '')
            .replaceAll('&', '&amp;')
            .replaceAll('<', '&lt;')
            .replaceAll('>', '&gt;')
            .replaceAll('"', '&quot;')
            .replaceAll("'", '&#39;');
    }

    function renderMrmsLegendTitle(legend) {
        const title = escapeHtml(legend?.title || 'MRMS');
        const stat = legend?.stat
            ? `<span class="mrms-legend-stat">${escapeHtml(legend.stat.label)}: ${escapeHtml(legend.stat.text)}</span>`
            : '';
        return `<div class="mrms-legend-head"><h4>${title}</h4>${stat}</div>`;
    }

    function renderMrmsScaleLegend(legend) {
        const scale = Array.isArray(legend?.scale) ? legend.scale : [];
        if (!scale.length) return '';
        const segments = scale
            .map((item) => `<span class="mrms-legend-segment" style="background:${item.color}"></span>`)
            .join('');
        const labels = scale
            .map((item) => `<span class="mrms-legend-tick">${escapeHtml(item.label)}</span>`)
            .join('');
        const units = legend?.display_units
            ? `<div class="mrms-legend-units">${escapeHtml(legend.display_units)}</div>`
            : '';
        return `<div class="mrms-legend-scale">${units}<div class="mrms-legend-scale-bar">${segments}</div><div class="mrms-legend-scale-labels">${labels}</div></div>`;
    }

    function renderMrmsCategoricalLegend(legend) {
        const items = Array.isArray(legend?.items) ? legend.items : [];
        if (!items.length) return '';
        const isPrecipType = String(legend?.title || '').toLowerCase().includes('surface precipitation type');
        const colClass = Number(legend?.columns) === 3 || isPrecipType
            ? 'legend-grid legend-grid-3'
            : 'legend-grid';
        return `<div class="${colClass}">${items.map((item) => swatch(item.color, escapeHtml(item.label))).join('')}</div>`;
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
        const colClass = events.length > 20 ? 'legend-grid legend-grid-6'
            : events.length > 16 ? 'legend-grid legend-grid-5'
                : events.length > 12 ? 'legend-grid legend-grid-4'
                    : events.length > 8 ? 'legend-grid legend-grid-3'
                        : events.length > 4 ? 'legend-grid' : '';
        const wrap = colClass ? `<div class="${colClass}">${rows}</div>` : rows;
        setLegend('<h4>Alerts In View</h4>' + wrap);
    }

    function buildSpcCatLegend() {
        const items = [
            ['#ff66ff', 'High'], ['#ff4f4f', 'Moderate'], ['#ff9d2e', 'Enhanced'],
            ['#f5dd72', 'Slight'], ['#69bb6d', 'Marginal'], ['#b5dcb3', 'General Thunderstorms'],
        ].map(([c, l]) => swatch(c, l)).join('');
        setLegend('<h4>SPC Categorical</h4><div class="legend-grid-2">' + items + '</div>');
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

    function buildSpcReportsLegend(reportTypes) {
        const allTypes = ['torn', 'wind', 'hail'];
        const active = Array.isArray(reportTypes) && reportTypes.length ? reportTypes : allTypes;
        const labels = { torn: 'Tornado', wind: 'Wind', hail: 'Hail', other: 'Other' };
        const rows = active.map((t) => {
            const color = _SPC_REPORT_COLORS[t] || _SPC_REPORT_COLORS.other;
            const label = labels[t] || t;
            const faClass = _SPC_REPORT_FA_ICON[t];
            if (faClass) {
                return `<div class="legend-row"><i class="${faClass}" style="color:${color};font-size:14px;width:16px;text-align:center;flex-shrink:0;"></i>&nbsp;${label}</div>`;
            }
            return swatch(color, label);
        }).join('');
        setLegend('<h4>SPC Storm Reports</h4>' + rows);
    }

    function buildRadarSiteMarkerLegend() {
        if (!_isTypeEnabled('radar') || !byId('weather-radar-show-sites')?.checked) {
            setLegend(null);
            return;
        }

        // Status color legend
        const statusItems = [
            ['#22c55e', 'Online'],
            ['#f59e0b', 'Maintenance Required'],
            ['#f97316', 'Maintenance Mandatory'],
            ['#60a5fa', 'Startup'],
            ['#facc15', 'Configured/Unknown'],
            ['#64748b', 'Unconfigured'],
        ].map(([c, l]) =>
            `<span style="display:inline-flex;align-items:center;gap:5px;white-space:nowrap;"><span class="legend-swatch" style="background:${c};border-radius:50%;"></span>${l}</span>`
        ).join('');
        const statusSection = `<div class="legend-row" style="display:flex;flex-wrap:wrap;gap:6px 14px;margin-top:4px;border-radius:50%;">${statusItems}</div>`;

        // Marker symbol legend
        const markerSection = `<div class="legend-row" style="margin-top:4px;display:flex;gap:16px;">
            <div style="display:flex;align-items:center;gap:6px;"><span style="display:inline-block;width:17px;height:17px;background-image:url('data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%2220%22 height=%2220%22 viewBox=%220 0 14 14%22%3E%3Cpolygon points=%227,1 8.65,5.01 13,5.15 9.82,7.74 10.97,12.09 7,9.66 3.03,12.09 4.18,7.74 1,5.15 5.35,5.01%22 fill=%22%2322c55e%22 stroke=%22%2316a34a%22 stroke-width=%220.9%22/%3E%3C/svg%3E');background-size:contain;background-repeat:no-repeat;"></span><span>Configured/Pre-warmed Site</span></div>
        </div>`;

        setLegend(`<h4>Radar Sites (CONUS)</h4>${statusSection}${markerSection}`);
    }

    async function _fetchRadarColortable(palKey) {
        if (_radarColortableCache.has(palKey)) return _radarColortableCache.get(palKey);
        const resp = await fetch(`/api/radar/colortable?product=${encodeURIComponent(palKey)}`);
        if (!resp.ok) throw new Error(`Colortable fetch failed: ${resp.status}`);
        const data = await resp.json();
        _radarColortableCache.set(palKey, data);
        return data;
    }

    async function buildRadarProductLegend(product) {
        if (!product) { setLegend(null); return; }

        const isVelocity = /vel|n0u|n1u|n0g|n0s|nvw/i.test(product);
        const palKey = isVelocity ? 'BV' : 'BR';
        const title = isVelocity ? 'Base Velocity' : 'Base Reflectivity';

        let ct;
        try {
            ct = await _fetchRadarColortable(palKey);
        } catch (_err) {
            // Silently skip legend if API unavailable
            return;
        }

        const entries = ct.entries || [];
        const units = isVelocity ? 'kts' : 'dBZ';
        const vmin = ct.vmin;
        const vmax = ct.vmax;

        // Continuous color bar rendered as a linear-gradient
        const stops = entries.map(e => {
            const pct = ((e.value - vmin) / (vmax - vmin) * 100).toFixed(1);
            return `${e.color} ${pct}%`;
        }).join(', ');
        const gradient = `linear-gradient(to right, ${stops})`;

        // Tick labels: show every other entry to avoid crowding
        const tickEntries = entries.filter((_, i) => i % 2 === 0 || i === entries.length - 1);
        const labelsHtml = `<div style="display:flex;justify-content:space-between;font-size:10px;color:#666;margin-top:3px;">`
            + tickEntries.map(e => `<span>${e.label}</span>`).join('')
            + `</div>`;

        const html = `<h4>${title}</h4>
            <div style="height:20px;border:1px solid rgba(0,0,0,0.2);border-radius:2px;background:${gradient};margin-bottom:2px;"></div>
            ${labelsHtml}
            <div style="text-align:right;font-size:10px;color:#888;margin-top:2px;">${units}</div>`;
        setLegend(html);
    }

    const _DROUGHT_COLORS = {
        0: '#FFFF00',
        1: '#FCD37F',
        2: '#FFAA00',
        3: '#E60000',
        4: '#730000',
    };
    const _DROUGHT_LABELS = {
        0: 'D0 – Abnormally Dry',
        1: 'D1 – Moderate Drought',
        2: 'D2 – Severe Drought',
        3: 'D3 – Extreme Drought',
        4: 'D4 – Exceptional Drought',
    };

    function _activeDroughtRegionState() {
        const code = String(byId('weather-region')?.value || '').toUpperCase();
        return /^[A-Z]{2}$/.test(code) ? code : null;
    }

    function _formatDroughtPct(value) {
        const num = Number(value);
        return Number.isFinite(num) ? `${num.toFixed(1)}%` : '—';
    }

    async function _fetchDroughtStateStats(date, stateCode) {
        if (!date || !stateCode) return null;
        const cacheKey = `${stateCode}|${date}`;
        if (_droughtStateStatsCache.has(cacheKey)) {
            return _droughtStateStatsCache.get(cacheKey);
        }
        const url = `/api/data/drought/state-stats?date=${encodeURIComponent(date)}&state=${encodeURIComponent(stateCode)}`;
        const resp = await fetch(url);
        if (!resp.ok) {
            throw new Error(`state stats ${resp.status}`);
        }
        const data = await resp.json();
        _droughtStateStatsCache.set(cacheKey, data);
        return data;
    }

    function buildDroughtLegend(enabledCats, stateStats, stateCode) {
        const cats = [0, 1, 2, 3, 4];
        const activeCats = enabledCats || cats;

        // CONUS/non-state views use the original levels-only legend.
        if (!stateCode) {
            const simpleRows = activeCats
                .map((dm) => swatch(_DROUGHT_COLORS[dm], _DROUGHT_LABELS[dm]))
                .join('');
            setLegend('<h4>U.S. Drought Monitor</h4>' + simpleRows);
            return;
        }

        const cumulative = stateStats?.cumulative || {};
        const individual = stateStats?.individual || {};
        const rows = cats.map((dm) => {
            const cumKey = dm === 4 ? 'D4' : `D${dm}-D4`;
            const indKey = `D${dm}`;
            const cumVal = _formatDroughtPct(cumulative[cumKey]);
            const indVal = _formatDroughtPct(individual[indKey]);
            const enabled = activeCats.includes(dm);
            return `
                <div class="drought-legend-row${enabled ? '' : ' is-disabled'}">
                    <div class="drought-legend-level"><span class="legend-swatch" style="background:${_DROUGHT_COLORS[dm]}"></span>${_DROUGHT_LABELS[dm]}</div>
                    <div class="drought-legend-value">${cumKey}: ${cumVal}</div>
                    <div class="drought-legend-value">${indKey}: ${indVal}</div>
                </div>
            `;
        }).join('');

        const dsci = Number(stateStats?.dsci);
        const dsciText = Number.isFinite(dsci) ? dsci.toFixed(1) : '—';
        const subtitle = `<div class="drought-legend-subtitle">${escapeHtml(stateCode)} stats for ${escapeHtml(_activeDroughtDate || '')}</div>`;

        setLegend(
            '<h4>U.S. Drought Monitor</h4>'
            + subtitle
            + '<div class="drought-legend-head">'
            + '<div>Level</div><div>Cumulative</div><div>Individual</div>'
            + '</div>'
            + rows
            + `<div class="drought-legend-dsci"><span>DSCI</span><span>${dsciText}</span></div>`,
        );
    }

    async function loadDroughtLayer() {
        const statusEl = byId('weather-drought-date-status');

        // Fetch available dates if not already loaded
        if (!_droughtDates.length) {
            try {
                const resp = await fetch('/api/data/drought/dates');
                if (resp.ok) {
                    const data = await resp.json();
                    _droughtDates = data.dates || [];
                    _activeDroughtDate = _activeDroughtDate || (_droughtDates[0] ?? null);
                    _renderDroughtDateButtons();
                }
            } catch (_) { /* ignore */ }
        }

        const date = _activeDroughtDate || (_droughtDates[0] ?? null);
        if (!date) {
            if (statusEl) statusEl.textContent = 'No dates available.';
            return;
        }

        if (statusEl) statusEl.textContent = 'Loading…';

        try {
            const resp = await fetch(`/api/data/drought?date=${encodeURIComponent(date)}`);
            if (!resp.ok) {
                if (statusEl) statusEl.textContent = `Error ${resp.status}`;
                return;
            }
            const geojson = await resp.json();

            const enabledCats = _activeDroughtCategories();
            const opacity = parseFloat(byId('weather-opacity-drought')?.value ?? 0.75);

            if (droughtLayer && map.hasLayer(droughtLayer)) map.removeLayer(droughtLayer);

            droughtLayer = L.geoJSON(geojson, {
                filter: (feature) => enabledCats.includes(Number(feature.properties?.DM)),
                style: (feature) => {
                    const dm = Number(feature.properties?.DM);
                    return {
                        fillColor: _DROUGHT_COLORS[dm] ?? '#cccccc',
                        fillOpacity: opacity,
                        color: _DROUGHT_COLORS[dm] ?? '#cccccc',
                        weight: 0.5,
                        opacity: 0.8,
                    };
                },
                onEachFeature: (feature, layer) => {
                    const dm = Number(feature.properties?.DM);
                    layer.bindTooltip(
                        `<strong>${_DROUGHT_LABELS[dm] ?? `DM ${dm}`}</strong>`,
                        { sticky: true, className: 'wx-tooltip' },
                    );
                },
            }).addTo(map);

            const stateCode = _activeDroughtRegionState();
            let stateStats = null;
            if (stateCode) {
                try {
                    stateStats = await _fetchDroughtStateStats(date, stateCode);
                } catch (err) {
                    console.warn('[drought] state stats unavailable', err);
                }
            }

            _lastDroughtStateCode = stateCode;
            _lastDroughtStateStats = stateStats;
            buildDroughtLegend(enabledCats, stateStats, stateCode);

            const tsMs = _resolveDataTimestampMs(date + 'T12:00:00Z');
            _setReliability('drought', 'USDM Drought', 'USDM/NDMC', tsMs);
            _setTimestampSource('drought', 'usdm_valid_date', tsMs);
            if (statusEl) statusEl.textContent = `Valid: ${date}`;
        } catch (err) {
            if (statusEl) statusEl.textContent = 'Load failed.';
            console.error('[drought] load failed', err);
        }
    }

    function _activeDroughtCategories() {
        return Array.from(document.querySelectorAll('.drought-cat-check'))
            .filter((el) => el.checked)
            .map((el) => Number(el.value));
    }

    function _renderDroughtDateButtons() {
        const container = byId('weather-drought-dates');
        if (!container) return;
        container.innerHTML = '';
        _droughtDates.forEach((d) => {
            const btn = document.createElement('button');
            btn.className = 'wx-drought-date-btn' + (d === _activeDroughtDate ? ' active' : '');
            btn.type = 'button';
            // Show as MM/DD (short label)
            const [y, mo, day] = d.split('-');
            btn.textContent = `${mo}/${day}`;
            btn.title = d;
            btn.dataset.date = d;
            btn.addEventListener('click', () => {
                _activeDroughtDate = d;
                container.querySelectorAll('.wx-drought-date-btn').forEach((b) => {
                    b.classList.toggle('active', b.dataset.date === d);
                });
                if (_isTypeEnabled('drought')) loadDroughtLayer();
            });
            container.appendChild(btn);
        });
    }

    // Authoritative SPC probabilistic fill colors (per-hazard scale).
    // Colors taken from SPC's published outlook legends.
    const _SPC_PROB_HAZARD_COLORS = {
        torn: [
            ['60%', '#104E8B'],
            ['45%', '#912CEE'],
            ['30%', '#FF00FF'],
            ['15%', '#FF9696'],
            ['10%', '#FFEB7F'],
            ['5%', '#BD998A'],
            ['2%', '#79BA7A'],
        ],
        hail: [
            ['60%', '#912CEE'],
            ['45%', '#FF00FF'],
            ['30%', '#FF0000'],
            ['15%', '#FFEB7F'],
            ['5%', '#C5A392'],
        ],
        wind: [
            ['90%', '#00FFFF'],
            ['75%', '#104E8B'],
            ['60%', '#912CEE'],
            ['45%', '#FF00FF'],
            ['30%', '#FF0000'],
            ['15%', '#FFEB7F'],
            ['5%', '#C5A392'],
        ],
    };

    const _SPC_HAZARD_TITLES = { torn: 'Tornado', hail: 'Hail', wind: 'Wind' };

    // How many CIG intensity levels exist for each hazard (hail has 1-2, others 1-3).
    const _SPC_HAZARD_CIG_LEVELS = { torn: 3, hail: 2, wind: 3 };

    function _spcInlineSwatch(color, label) {
        return `<span class="legend-row" style="margin:0 6px 0 0;">`
            + `<span class="legend-swatch" style="background:${color}"></span>${label}</span>`;
    }

    // Small inline swatch rendering the SVG hatch pattern used on the map, so
    // the legend matches the polygon fill exactly.
    function _spcHatchSwatch(intensity, label) {
        const size = 22;
        const patternId = `legend-hatch-cig-${intensity}`;
        let patternBody = '';
        if (intensity === 1) {
            // Legend: 25% tighter than map pattern (tile 10 → 7.5, dasharray scaled)
            patternBody = `
                <pattern id="${patternId}" patternUnits="userSpaceOnUse" width="7.5" height="7.5" patternTransform="rotate(45)">
                    <line x1="0" y1="0" x2="0" y2="7.5" stroke="black" stroke-width="4" stroke-dasharray="3,4.5"/>
                </pattern>`;
        } else if (intensity === 2) {
            // Legend: 50% tighter than map pattern (tile 18 → 9)
            patternBody = `
                <pattern id="${patternId}" patternUnits="userSpaceOnUse" width="9" height="9" patternTransform="rotate(-45)">
                    <line x1="0" y1="0" x2="0" y2="9" stroke="black" stroke-width="4"/>
                </pattern>`;
        } else {
            // Legend: 50% tighter than map pattern (tile 18 → 9)
            patternBody = `
                <pattern id="${patternId}" patternUnits="userSpaceOnUse" width="9" height="9" patternTransform="rotate(45)">
                    <line x1="0" y1="0" x2="0" y2="9" stroke="black" stroke-width="4"/>
                    <line x1="0" y1="0" x2="9" y2="0" stroke="black" stroke-width="4"/>
                </pattern>`;
        }
        const svg = `<svg width="${size}" height="${size}" style="vertical-align:middle;border:1px solid rgba(0,0,0,0.4);border-radius:2px;background:#fff;">`
            + `<defs>${patternBody}</defs>`
            + `<rect width="${size}" height="${size}" fill="url(#${patternId})"/>`
            + `</svg>`;
        return `<span class="legend-row" style="margin:0 6px 0 0;">${svg}&nbsp;${label}</span>`;
    }

    function buildSpcProbLegend(hazard, day = null) {
        // Allow day override for Day 3 and Days 4-8
        let title = _SPC_HAZARD_TITLES[hazard] || 'Probabilistic';
        let colors = _SPC_PROB_HAZARD_COLORS[hazard] || [];
        let cigLevels = _SPC_HAZARD_CIG_LEVELS[hazard] || 0;

        // Day 3 Probabilistic: 60, 45, 30, 15, 5; Intensity 1 & 2 only
        if (day === 3) {
            colors = [
                ['60%', '#104E8B'],
                ['45%', '#912CEE'],
                ['30%', '#FF00FF'],
                ['15%', '#FF9696'],
                ['5%', '#BD998A'],
            ];
            cigLevels = 2;
        }
        // Days 4-8: Only 30% and 15%, no intensity
        if (day >= 4 && day <= 8) {
            colors = [
                ['30%', '#FF00FF'],
                ['15%', '#FF9696'],
            ];
            cigLevels = 0;
            title = 'Severe Weather Outlook';
        }

        const probRow = colors.map(([label, color]) => _spcInlineSwatch(color, label)).join('');
        const intensityRow = Array.from({ length: cigLevels }, (_, i) => i + 1)
            .map((lvl) => _spcHatchSwatch(lvl, String(lvl)))
            .join('');

        let html = `<h4>SPC ${title}</h4>`;
        html += `<div style="font-weight:600;font-size:0.66rem;margin:2px 0 2px;">Probability</div>`;
        html += `<div style="display:flex;flex-wrap:wrap;">${probRow}</div>`;
        if (intensityRow) {
            html += `<div style="font-weight:600;font-size:0.66rem;margin:6px 0 2px;">Intensity</div>`;
            html += `<div style="display:flex;flex-wrap:wrap;">${intensityRow}</div>`;
        }
        setLegend(html);
    }

    // ── Data loaders ─────────────────────────────────────────────────────────
    function setStatus(msg) {
        const el = byId('weather-map-status');
        if (el) el.textContent = msg;
    }

    let _radarWorkflowToastTimer = null;
    function _showRadarWorkflowToast(message, timeoutMs = 3200) {
        const stack = byId('wx-radar-toast-stack');
        if (!stack) return;
        let toast = stack.querySelector('.wx-radar-toast');
        if (!toast) {
            toast = document.createElement('div');
            toast.className = 'wx-radar-toast';
            stack.appendChild(toast);
        }
        toast.textContent = String(message || '').trim();
        toast.classList.remove('is-active');
        // Force reflow so repeated messages replay entrance transition.
        void toast.offsetWidth;
        toast.classList.add('is-active');

        if (_radarWorkflowToastTimer) {
            clearTimeout(_radarWorkflowToastTimer);
            _radarWorkflowToastTimer = null;
        }
        _radarWorkflowToastTimer = setTimeout(() => {
            toast.classList.remove('is-active');
            _radarWorkflowToastTimer = null;
        }, Math.max(1200, Number(timeoutMs) || 3200));
    }

    // ── Reliability bar (Last Update / Data Age / Source) ────────────────────
    const _reliabilityByType = {
        global: { ts: null, source: null, label: null },
        alerts: { ts: null, source: null, label: null },
        spc: { ts: null, source: null, label: null },
        surface: { ts: null, source: null, label: null },
        rtma: { ts: null, source: null, label: null },
        mrms: { ts: null, source: null, label: null },
    };
    const _timestampSourceByType = {
        global: { provenance: null, ts: null },
        alerts: { provenance: null, ts: null },
        spc: { provenance: null, ts: null },
        surface: { provenance: null, ts: null },
        rtma: { provenance: null, ts: null },
        mrms: { provenance: null, ts: null },
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
        if ((_mrmsScrubMode || _isTypeEnabled('mrms')) && _activeMrmsProduct()) return 'mrms';
        if ((_rtmaScrubMode || _isTypeEnabled('rtma')) && _activeRtmaStream() && _activeRtmaProduct()) return 'rtma';
        if (_isTypeEnabled('spc') && byId('weather-show-spc')?.checked) return 'spc';
        if (_isTypeEnabled('alerts') && _getCheckedAlertCategories().length) return 'alerts';
        if (_isTypeEnabled('drought')) return 'drought';
        if (_isTypeEnabled('current') && _activeSurfaceProduct()) return 'surface';
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
        if (ageEl) ageEl.textContent = Number.isFinite(entry.ts) ? _formatAge(Date.now() - entry.ts) : '—';
        if (provEl) provEl.textContent = entry.source || '—';
        if (srcEl) srcEl.textContent = tsEntry.provenance || '—';
    }

    function _setTimestampSource(type, provenance, ts) {
        const key = (type && _timestampSourceByType[type]) ? type : 'global';
        const tsMs = ts != null ? Number(ts) : NaN;
        _timestampSourceByType[key].provenance = provenance || null;
        _timestampSourceByType[key].ts = Number.isFinite(tsMs) ? tsMs : null;
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
        const tsMs = targetTs != null ? Number(targetTs) : NaN;
        _reliabilityByType[key].ts = Number.isFinite(tsMs) ? tsMs : null;
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

    function _canApplyAlertsResponse() {
        return !_archiveMode
            && !_rtmaScrubMode
            && !_mrmsScrubMode
            && _isTypeEnabled('alerts')
            && _getCheckedAlertCategories().length > 0;
    }

    function _canApplySpcResponse() {
        return !_archiveMode
            && !_rtmaScrubMode
            && !_mrmsScrubMode
            && _isTypeEnabled('spc')
            && !!byId('weather-show-spc')?.checked;
    }

    function _canApplyMrmsResponse() {
        return !_archiveMode
            && !_rtmaScrubMode
            && !_mrmsScrubMode
            && _isTypeEnabled('mrms')
            && !!_activeMrmsProduct();
    }

    function _canApplyRtmaResponse() {
        return !_archiveMode
            && !_rtmaScrubMode
            && !_mrmsScrubMode
            && _isTypeEnabled('rtma')
            && !!_activeRtmaStream()
            && !!_activeRtmaProduct();
    }

    // ── New-alert notification banners ───────────────────────────────────────
    const ALERT_NOTIFY_EVENTS = new Set([
        'Tornado Warning',
        'Severe Thunderstorm Warning',
        'Special Marine Warning',
        'Flash Flood Warning',
    ]);
    const ALERT_NOTIFY_DISMISS_MS = 20_000;
    // Polygons for these events pulse on the map to draw attention.
    const ALERT_PULSE_EVENTS = new Set([
        'Tornado Warning',
        'Severe Thunderstorm Warning',
        'Flash Flood Warning',
        'Special Marine Warning',
    ]);

    function _triggerNewAlertBorderFlash(color) {
        const flash = byId('wx-new-alert-border-flash');
        if (!flash) return;
        flash.style.borderColor = color || '#ffffff';
        flash.classList.remove('is-active');
        // Force reflow so rapid successive alerts replay the animation.
        void flash.offsetWidth;
        flash.classList.add('is-active');
    }

    let _newAlertAudio = null;
    function _playNewAlertSound() {
        try {
            if (!_newAlertAudio) {
                _newAlertAudio = new Audio('sounds/weather_alert.mp3');
                _newAlertAudio.preload = 'auto';
                _newAlertAudio.volume = 0.8;
            }
            _newAlertAudio.currentTime = 0;
            const p = _newAlertAudio.play();
            if (p && typeof p.catch === 'function') p.catch(() => { /* autoplay blocked */ });
        } catch (_) { /* ignore */ }
    }

    // Severity gate for the immersive new-alert detail flow. Banners still emit for
    // any ALERT_NOTIFY_EVENTS entry; the View action only opens the detail panel for
    // Severe/Extreme severities (warnings) — lesser severities fall back to the
    // standard pager popup.
    const ALERT_DETAIL_SEVERITIES = new Set(['Severe', 'Extreme']);
    function _alertQualifiesForDetail(feat) {
        const p = feat?.properties || {};
        const event = String(p.event || '');
        const severity = String(p.severity || '');
        return ALERT_NOTIFY_EVENTS.has(event) && ALERT_DETAIL_SEVERITIES.has(severity);
    }

    // Dismiss every queued new-alert banner. Optionally skip one (the banner
    // whose own dismiss path is being run by the caller).
    function _dismissAllNewAlertBanners(except) {
        const stack = byId('wx-new-alert-stack');
        if (!stack) return;
        const banners = stack.querySelectorAll('.wx-new-alert-banner');
        banners.forEach((banner) => {
            if (banner === except) return;
            if (banner.classList.contains('is-dismissing')) return;
            if (banner._dismissTimer) clearTimeout(banner._dismissTimer);
            banner.classList.add('is-dismissing');
            banner.addEventListener('animationend', () => {
                banner.remove();
                _updateBannerOverflowIndicator();
            }, { once: true });
        });
    }

    // ── Spatial dedup for cross-CWA duplicate warnings ───────────────────────
    // When a storm sits on a forecast-office boundary, multiple offices issue
    // independent warnings with their own UUIDs but near-identical polygons.
    // Suppress subsequent banners whose bbox IoU >= threshold matches one we
    // already showed within the lookback window.
    const _ALERT_BANNER_DEDUP_IOU = 0.6;
    const _ALERT_BANNER_DEDUP_MS = 10 * 60_000;
    const _recentBannerLedger = []; // { event, bbox, ts }

    function _alertBbox(feat) {
        const geom = feat?.geometry;
        if (!geom) return null;
        let minLat = Infinity, maxLat = -Infinity, minLng = Infinity, maxLng = -Infinity;
        const visit = (node) => {
            if (!Array.isArray(node)) return;
            if (node.length >= 2 && Number.isFinite(node[0]) && Number.isFinite(node[1])) {
                const lng = Number(node[0]);
                const lat = Number(node[1]);
                if (lat < minLat) minLat = lat;
                if (lat > maxLat) maxLat = lat;
                if (lng < minLng) minLng = lng;
                if (lng > maxLng) maxLng = lng;
                return;
            }
            for (const child of node) visit(child);
        };
        visit(geom.coordinates);
        if (!Number.isFinite(minLat)) return null;
        return { minLat, maxLat, minLng, maxLng };
    }

    function _bboxArea(b) {
        return Math.max(0, b.maxLat - b.minLat) * Math.max(0, b.maxLng - b.minLng);
    }

    function _bboxIoU(a, b) {
        const iLat0 = Math.max(a.minLat, b.minLat);
        const iLat1 = Math.min(a.maxLat, b.maxLat);
        const iLng0 = Math.max(a.minLng, b.minLng);
        const iLng1 = Math.min(a.maxLng, b.maxLng);
        if (iLat1 <= iLat0 || iLng1 <= iLng0) return 0;
        const inter = (iLat1 - iLat0) * (iLng1 - iLng0);
        const union = _bboxArea(a) + _bboxArea(b) - inter;
        return union > 0 ? inter / union : 0;
    }

    function _isDuplicateBanner(feat) {
        const event = String(feat?.properties?.event || '');
        const bbox = _alertBbox(feat);
        if (!event || !bbox) return false;
        const now = Date.now();
        // Drop expired ledger entries first.
        for (let i = _recentBannerLedger.length - 1; i >= 0; i--) {
            if (now - _recentBannerLedger[i].ts > _ALERT_BANNER_DEDUP_MS) {
                _recentBannerLedger.splice(i, 1);
            }
        }
        for (const entry of _recentBannerLedger) {
            if (entry.event !== event) continue;
            if (_bboxIoU(entry.bbox, bbox) >= _ALERT_BANNER_DEDUP_IOU) return true;
        }
        return false;
    }

    function _recordBannerLedger(feat) {
        const event = String(feat?.properties?.event || '');
        const bbox = _alertBbox(feat);
        if (!event || !bbox) return;
        _recentBannerLedger.push({ event, bbox, ts: Date.now() });
    }

    function _showNewAlertBanner(feat) {
        if (!_isTypeEnabled('alerts')) return;
        const stack = byId('wx-new-alert-stack');
        if (!stack) return;
        // Suppress cross-CWA duplicates that describe substantially the same
        // threat area as a banner already shown in the recent window.
        if (_isDuplicateBanner(feat)) return;
        _recordBannerLedger(feat);
        const p = feat?.properties || {};
        const event = p.event || 'Unknown Alert';
        const color = ALERT_COLORS[event] || ALERT_DEFAULT;
        const testDismissMs = Number(p.__testDismissMs);
        const dismissMs = Number.isFinite(testDismissMs) && testDismissMs > 0
            ? testDismissMs
            : ALERT_NOTIFY_DISMISS_MS;

        _triggerNewAlertBorderFlash(color);
        _playNewAlertSound();

        const banner = document.createElement('div');
        banner.className = 'wx-new-alert-banner';
        banner.style.borderColor = color;
        const bannerItem = document.createElement('div');
        bannerItem.className = 'wx-new-alert-item';
        const closeBtn = document.createElement('button');
        closeBtn.type = 'button';
        closeBtn.className = 'wx-new-alert-close';
        closeBtn.setAttribute('aria-label', 'Dismiss alert');
        closeBtn.textContent = '\u00d7';
        // Compose location summary using _summarizeAreaDesc for consistency with sidebar
        let locText = p.areaDesc || p.locations || '';
        let summary = _summarizeAreaDesc(locText);
        // Always render the location div, even if empty, for debugging
        let locHtml = `<div class="wx-new-alert-pill-location">${_escapeHtml(summary || '')}</div>`;

        banner.innerHTML = [
            `<span class="wx-new-alert-pill-label" style="color:yellow">New Alert:</span>`,
            `<span class="wx-new-alert-pill-event" style="color:${color}">${_escapeHtml(event)}</span>`,
            `<button type="button" class="wx-new-alert-banner-view" style="color:${color}">View</button>`,
            `<div class="wx-new-alert-pill-text">${locHtml}</div>`,
            `<div class="wx-new-alert-banner-progress" style="background:${color};animation-duration:${dismissMs}ms"></div>`,
        ].join('');

        const dismiss = () => {
            if (banner._dismissTimer) clearTimeout(banner._dismissTimer);
            banner.classList.add('is-dismissing');
            banner.addEventListener('animationend', (evt) => {
                if (evt.animationName !== 'wx-alert-slide-out') return;
                bannerItem.remove();
                _updateBannerOverflowIndicator();
            });
        };

        const activateBannerAction = () => {
            const center = _alertFeatureCenterLatLng(feat);
            if (!center) return;
            // Dismiss every other queued banner — user committed to this one.
            _dismissAllNewAlertBanners(banner);
            dismiss();
            _setRegionAlertLocationState();
            map.flyTo(center, Math.max(map.getZoom(), 9), { duration: 1.0 });
            map.once('moveend', () => {
                if (_alertQualifiesForDetail(feat)) {
                    _openNewAlertDetail(center, feat);
                } else {
                    _openAlertsPagerAt(center);
                }
            });
        };

        // Explicitly wire the View button to the same action path used by banner clicks.
        const viewBtn = banner.querySelector('.wx-new-alert-banner-view');
        if (viewBtn) {
            viewBtn.addEventListener('click', (evt) => {
                evt.preventDefault();
                evt.stopPropagation();
                activateBannerAction();
            });
        }

        // Click anywhere on the banner to zoom — inner View button still works
        // because both now call the same shared action path.
        banner.style.cursor = 'pointer';
        banner.addEventListener('click', (evt) => {
            // Ignore clicks on the progress bar (purely decorative).
            if (evt.target.closest('.wx-new-alert-banner-progress')) return;
            activateBannerAction();
        });

        closeBtn.addEventListener('click', (evt) => {
            evt.preventDefault();
            evt.stopPropagation();
            dismiss();
        });

        banner._dismissTimer = setTimeout(dismiss, dismissMs);
        bannerItem.appendChild(banner);
        bannerItem.appendChild(closeBtn);
        stack.appendChild(bannerItem);
        _updateBannerOverflowIndicator();
    }

    // Stacked pill banners are capped at MAX_VISIBLE; older queued banners hide
    // and a "+N more" pill replaces them. Banners self-dismiss on timeout.
    const _BANNER_MAX_VISIBLE = 2;
    function _updateBannerOverflowIndicator() {
        const stack = byId('wx-new-alert-stack');
        if (!stack) return;
        const items = Array.from(stack.querySelectorAll('.wx-new-alert-item'))
            .filter((item) => !item.querySelector('.wx-new-alert-banner')?.classList.contains('is-dismissing'));
        let overflow = stack.querySelector('.wx-new-alert-overflow');
        items.forEach((item, i) => {
            item.style.display = i < _BANNER_MAX_VISIBLE ? '' : 'none';
        });
        const hidden = Math.max(0, items.length - _BANNER_MAX_VISIBLE);
        if (hidden > 0) {
            if (!overflow) {
                overflow = document.createElement('div');
                overflow.className = 'wx-new-alert-overflow';
                stack.appendChild(overflow);
            } else if (overflow.parentNode !== stack || overflow !== stack.lastElementChild) {
                stack.appendChild(overflow);
            }
            overflow.textContent = `+${hidden} more new alert${hidden === 1 ? '' : 's'}`;
        } else if (overflow) {
            overflow.remove();
        }
    }

    // ── Active Warnings Panel (third sidebar column) ─────────────────────────
    // Persistent index of currently-active warnings. Populated from
    // _allAlertFeatures whenever alerts refresh. Auto-shows when ≥1 row
    // matches the active filter; user-collapsed state is preserved.
    const ACTIVE_WARNING_SEVERE_EVENTS = new Set([
        'Tornado Warning',
        'Severe Thunderstorm Warning',
        'Flash Flood Warning',
    ]);
    // Per-pill event matchers for the Warnings tab (TOR / SVR / FFW / ALL).
    const _WARN_FILTER_EVENT_TYPES = {
        tor: 'Tornado Warning',
        svr: 'Severe Thunderstorm Warning',
        ffw: 'Flash Flood Warning',
    };
    const _warningsFilterEnabled = new Set(['tor', 'svr', 'ffw']); // all enabled by default
    let _warningsPanelFilter = 'all';
    const _warningsKnownIds = new Set(); // ids we've already rendered (to flag is-new)

    function _formatRelativeTime(ms) {
        if (!Number.isFinite(ms)) return '';
        const sec = Math.round(ms / 1000);
        const abs = Math.abs(sec);
        if (abs < 60) return `${sec}s`;
        const min = Math.round(sec / 60);
        if (Math.abs(min) < 60) return `${min}m`;
        const hr = Math.round(min / 60);
        if (Math.abs(hr) < 24) return `${hr}h`;
        const day = Math.round(hr / 24);
        return `${day}d`;
    }

    // Format an absolute timestamp as "HH:mm TZ" (24-hr, browser locale TZ
    // abbreviation, e.g. "14:32 EDT"). Used by the Warnings list "Issued ..."
    // line so users see both relative age and exact issuance time.
    function _formatLocalTimeWithTz(ms) {
        if (!Number.isFinite(ms)) return '';
        const d = new Date(ms);
        const hh = String(d.getHours()).padStart(2, '0');
        const mm = String(d.getMinutes()).padStart(2, '0');
        let tz = '';
        try {
            const parts = new Intl.DateTimeFormat(undefined, { timeZoneName: 'short' }).formatToParts(d);
            tz = parts.find(p => p.type === 'timeZoneName')?.value || '';
        } catch (_) { /* fallback to no tz */ }
        return tz ? `${hh}:${mm} ${tz}` : `${hh}:${mm}`;
    }

    function _formatExpiresInVerbose(ms) {
        if (!Number.isFinite(ms) || ms <= 0) return 'Expired';
        const totalMinutes = Math.max(0, Math.ceil(ms / 60_000));
        const hours = Math.floor(totalMinutes / 60);
        const minutes = totalMinutes - (hours * 60);
        if (hours < 1) {
            const minuteLabel = minutes === 1 ? 'minute' : 'minutes';
            return `Expires in ${minutes} ${minuteLabel}`;
        }
        const hourLabel = hours === 1 ? 'hour' : 'hours';
        if (minutes === 0) {
            return `Expires in ${hours} ${hourLabel}`;
        }
        const minuteLabel = minutes === 1 ? 'minute' : 'minutes';
        return `Expires in ${hours} ${hourLabel}, and ${minutes} ${minuteLabel}`;
    }

    function _summarizeAreaDesc(areaDesc) {
        const raw = String(areaDesc || '').replace(/\s*;\s*/g, ', ').trim();
        if (!raw) return '';
        const parts = raw.split(',').map((s) => s.trim()).filter(Boolean);
        const byState = new Map();
        const states = [];
        let lastState = null;
        for (const part of parts) {
            const m = part.match(/^([A-Z]{2})$/);
            if (m) {
                lastState = m[1];
                if (!byState.has(lastState)) {
                    byState.set(lastState, []);
                    states.push(lastState);
                }
                continue;
            }
            // County name preceding a state token; we'll attach it when we hit one.
            if (lastState === null) lastState = '__';
            if (!byState.has(lastState)) {
                byState.set(lastState, []);
                states.push(lastState);
            }
            byState.get(lastState).push(part);
        }
        // Fall back if parsing yielded nothing useful.
        if (!states.length) return raw;
        const stateNames = states.filter((s) => s !== '__');
        const stateLabel = stateNames.length ? stateNames.join(' · ') : '';
        // Show first up to 3 counties across all states; truncate with "+N".
        const allCounties = states.flatMap((s) => byState.get(s) || []);
        const head = allCounties.slice(0, 3).join(', ');
        const more = allCounties.length > 3 ? ` +${allCounties.length - 3}` : '';
        const counties = head ? `${head}${more}` : '';
        if (counties && stateLabel) return `${counties} · ${stateLabel}`;
        return counties || stateLabel || raw;
    }

    function _activeAlertsForWarningsPanel() {
        const features = Array.isArray(_alertsFullBaseFeatures) && _alertsFullBaseFeatures.length
            ? _alertsFullBaseFeatures
            : (Array.isArray(_allAlertFeatures) ? _allAlertFeatures : []);
        const now = Date.now();
        const filtered = features.filter((f) => {
            const p = f?.properties || {};
            const expiresMs = p.expires ? Date.parse(p.expires) : NaN;
            if (Number.isFinite(expiresMs) && expiresMs <= now) return false;
            if (_warningsPanelFilter === 'all') return true;
            const event = String(p.event || '');
            return event === _WARN_FILTER_EVENT_TYPES[_warningsPanelFilter];
        });
        filtered.sort((a, b) => {
            const sa = Date.parse(a?.properties?.sent || '') || 0;
            const sb = Date.parse(b?.properties?.sent || '') || 0;
            return sb - sa;
        });
        return filtered;
    }

    function _warningPanelEmptyText() {
        if (_warningsPanelFilter === 'tor') return 'No active tornado warnings.';
        if (_warningsPanelFilter === 'svr') return 'No active severe thunderstorm warnings.';
        if (_warningsPanelFilter === 'ffw') return 'No active flash flood warnings.';
        return 'No active alerts.';
    }

    // Refresh the tiny count badge on each warning-filter pill (TOR/SVR/FFW/ALL).
    // Counts ignore the active filter so users can see all buckets at a glance.
    function _warningPanelCounts(alertsEnabled) {
        const features = (alertsEnabled && Array.isArray(_alertsFullBaseFeatures) && _alertsFullBaseFeatures.length)
            ? _alertsFullBaseFeatures
            : ((alertsEnabled && Array.isArray(_allAlertFeatures)) ? _allAlertFeatures : []);
        const now = Date.now();
        const counts = { all: 0, tor: 0, svr: 0, ffw: 0 };
        for (const f of features) {
            const p = f?.properties || {};
            const expiresMs = p.expires ? Date.parse(p.expires) : NaN;
            if (Number.isFinite(expiresMs) && expiresMs <= now) continue;
            counts.all += 1;
            const event = String(p.event || '');
            if (event === _WARN_FILTER_EVENT_TYPES.tor) counts.tor += 1;
            else if (event === _WARN_FILTER_EVENT_TYPES.svr) counts.svr += 1;
            else if (event === _WARN_FILTER_EVENT_TYPES.ffw) counts.ffw += 1;
        }
        return counts;
    }

    function _updateWarningFilterCounts(alertsEnabled) {
        const counts = _warningPanelCounts(alertsEnabled);
        document.querySelectorAll('[data-warn-filter-count], [data-warn-panel-filter-count]').forEach((el) => {
            const key = el.getAttribute('data-warn-filter-count') || el.getAttribute('data-warn-panel-filter-count');
            el.textContent = String(counts[key] ?? 0);
        });
    }

    function _updateWarningFilterRowVisibility() {
        const filterRow = byId('wx-warn-filter-row');
        if (!filterRow) return;
        const checkedCategories = _getCheckedAlertCategories();
        // Only show filter row if ONLY "Severe Weather Warnings" is checked
        const onlyShowSWW = checkedCategories.length === 1 && checkedCategories[0] === 'Severe Weather Warnings';
        filterRow.style.display = onlyShowSWW ? 'flex' : 'none';
    }

    function _updateAlertFilterOptionsVisibility() {
        const filterContainer = byId('weather-alerts-filter-options');
        if (!filterContainer) return;
        filterContainer.hidden = false;
        _updateWarningFilterRowVisibility();
    }

    function _renderActiveWarningsPanel() {
        const list = byId('wx-warnings-list');
        const empty = byId('wx-warnings-empty');
        const countEl = byId('wx-warnings-count');
        const tabBtn = byId('wx-right-tab-btn-warnings');
        if (!list) return;

        const alertsEnabled = _isTypeEnabled('alerts');
        const items = alertsEnabled ? _activeAlertsForWarningsPanel() : [];

        // Update per-pill counts (TOR/SVR/FFW/ALL) and the tab badge.
        _updateWarningFilterCounts(alertsEnabled);

        // Sync right panel buttons with current filter state
        document.querySelectorAll('#wx-right-pane-warnings [data-warn-filter], #wx-right-pane-warnings [data-warn-panel-filter]').forEach((el) => {
            const key = el.getAttribute('data-warn-panel-filter') || el.getAttribute('data-warn-filter');
            const isActive = key === _warningsPanelFilter;
            el.classList.toggle('is-active', isActive);
            el.setAttribute('aria-pressed', isActive ? 'true' : 'false');
        });

        // Update count badge on the Warnings tab.
        if (countEl) {
            if (items.length > 0) {
                countEl.textContent = String(items.length);
                countEl.hidden = false;
            } else {
                countEl.hidden = true;
            }
        }

        if (items.length === 0) {
            list.innerHTML = '';
            if (empty) empty.textContent = _warningPanelEmptyText();
            if (empty) empty.style.display = 'block';
            if (tabBtn) tabBtn.classList.remove('has-attention');
            _warningsKnownIds.clear();
            return;
        }
        if (empty) empty.style.display = 'none';

        // Pulse the Warnings tab when a brand-new severe row arrives while the
        // user is on a different tab.
        const prevIds = new Set(_warningsKnownIds);
        const hasNewSevere = items.some((feat) => {
            const p = feat?.properties || {};
            const id = feat.id || `${p.event || ''}|${p.sent || ''}|${p.areaDesc || ''}`;
            return ACTIVE_WARNING_SEVERE_EVENTS.has(String(p.event || '')) && !prevIds.has(id);
        });
        if (tabBtn) {
            const active = tabBtn.classList.contains('is-active');
            if (hasNewSevere && !active) tabBtn.classList.add('has-attention');
        }

        const now = Date.now();
        const seenIdsThisRender = new Set();
        list.innerHTML = items.map((feat) => {
            const p = feat.properties || {};
            const id = feat.id || `${p.event || ''}|${p.sent || ''}|${p.areaDesc || ''}`;
            seenIdsThisRender.add(id);
            const isNew = !_warningsKnownIds.has(id);
            const event = p.event || 'Unknown Alert';
            const color = ALERT_COLORS[event] || ALERT_DEFAULT;
            const area = _summarizeAreaDesc(p.areaDesc);
            const expiresMs = p.expires ? Date.parse(p.expires) : NaN;
            const sentMs = p.sent ? Date.parse(p.sent) : NaN;
            const countdownMs = Number.isFinite(expiresMs) ? expiresMs - now : NaN;
            const urgent = Number.isFinite(countdownMs) && countdownMs <= 15 * 60_000;
            const issuedRel = Number.isFinite(sentMs) ? `Issued ${_formatRelativeTime(now - sentMs)} ago at ${_formatLocalTimeWithTz(sentMs)}` : '';
            return [
                `<div class="wx-warn-row${isNew ? ' is-new' : ''}" data-feat-id="${_escapeHtml(id)}" style="border-left-color:${color}">`,
                `  <div class="wx-warn-row-head">`,
                `    <span class="wx-warn-event" style="color:${color}">${_escapeHtml(event)}</span>`,
                `  </div>`,
                area ? `  <div class="wx-warn-area">${_escapeHtml(area)}</div>` : '',
                `  <div class="wx-warn-actions">`,
                `    <span class="wx-warn-issued">${_escapeHtml(issuedRel)}</span>`,
                `    <span class="wx-warn-expires${urgent ? ' is-urgent' : ''}">${_escapeHtml(_formatExpiresInVerbose(countdownMs))}</span>`,
                `    <button type="button" class="wx-warn-zoom" data-warn-zoom="${_escapeHtml(id)}">Zoom To Alert</button>`,
                `  </div>`,
                `</div>`,
            ].join('');
        }).join('');

        // Refresh known-ids set so next render only flashes truly new rows.
        _warningsKnownIds.clear();
        seenIdsThisRender.forEach((id) => _warningsKnownIds.add(id));
    }

    function _wireActiveWarningsPanel() {
        const pane = byId('wx-right-pane-warnings');
        const list = byId('wx-warnings-list');
        if (!pane || !list) return;

        // Filter buttons in the right pane
        const filterBtns = pane.querySelectorAll('[data-warn-filter], [data-warn-panel-filter]');
        filterBtns.forEach((btn) => {
            btn.addEventListener('click', () => {
                const key = btn.getAttribute('data-warn-panel-filter') || btn.getAttribute('data-warn-filter');
                if (key !== 'all' && key !== 'tor' && key !== 'svr' && key !== 'ffw') return;
                _warningsPanelFilter = key;
                _warningsKnownIds.clear();
                _renderActiveWarningsPanel();
            });
        });

        // Zoom-to-alert delegation — clicking anywhere on the row triggers the
        // same action as the inner Zoom button (which still works via bubbling).
        list.addEventListener('click', (evt) => {
            const row = evt.target.closest('.wx-warn-row');
            if (!row) return;
            evt.preventDefault();
            const id = row.getAttribute('data-feat-id');
            if (!id) return;
            const idMatch = (f) => {
                const fId = f.id || `${f.properties?.event || ''}|${f.properties?.sent || ''}|${f.properties?.areaDesc || ''}`;
                return fId === id;
            };
            // Search the unfiltered base list first so clicks work even when
            // the alert's category filter is currently off.
            const feat = (_alertsFullBaseFeatures || []).find(idMatch)
                || (_allAlertFeatures || []).find(idMatch);
            if (!feat) return;

            // If this alert's category is not currently enabled, auto-enable it
            // so the layer renders and the pager can find the feature.
            const event = feat?.properties?.event || '';
            const checkedCategories = _getCheckedAlertCategories();
            const isVisible = !ALERT_CATEGORY_EVENT_SET.has(event)
                || checkedCategories.some((cat) => (ALERT_CATEGORIES[cat] || []).includes(event));
            if (!isVisible) {
                const matchingCat = Object.entries(ALERT_CATEGORIES)
                    .find(([, events]) => events.includes(event))?.[0];
                if (matchingCat) {
                    const ckBox = [...document.querySelectorAll('.weather-alerts-category')]
                        .find((el) => el.value === matchingCat);
                    if (ckBox) {
                        ckBox.checked = true;
                        _syncAllAlertsMaster();
                        _applyInMemoryAlertCategoryFilter();
                    }
                }
            }

            const center = _alertFeatureCenterLatLng(feat);
            if (!center) return;
            _setRegionAlertLocationState();
            map.flyTo(center, Math.max(map.getZoom(), 9), { duration: 1.0 });
            map.once('moveend', () => {
                _openAlertsPagerAt(center);
                _ensureRadarOverlayOn();
            });
        });
    }

    function _wireSidebarWarningFilterCheckboxes() {
        const filterCheckboxes = document.querySelectorAll('.wx-warn-filter-ck');
        if (!filterCheckboxes.length) return;
        filterCheckboxes.forEach((ck) => {
            ck.addEventListener('change', () => {
                const key = ck.getAttribute('data-warn-filter');
                if (ck.checked) {
                    _warningsFilterEnabled.add(key);
                } else {
                    _warningsFilterEnabled.delete(key);
                }
                _warningsKnownIds.clear();
                if (_alertsFullBaseFeatures.length || _alertsDisplayBaseFeatures.length) {
                    _applyInMemoryAlertCategoryFilter();
                } else {
                    _renderActiveWarningsPanel();
                }
            });
        });
    }

    function _wireRightSidebarTabs() {
        const tabs = document.querySelectorAll('.wx-right-tab[data-right-tab]');
        if (!tabs.length) return;
        const panes = {
            layers: byId('wx-right-pane-layers'),
            warnings: byId('wx-right-pane-warnings'),
            styling: byId('wx-right-pane-styling'),
        };
        tabs.forEach((btn) => {
            btn.addEventListener('click', () => {
                if (btn.hidden) return;
                const target = btn.getAttribute('data-right-tab');
                tabs.forEach((b) => {
                    const active = b === btn;
                    b.classList.toggle('is-active', active);
                    b.setAttribute('aria-selected', active ? 'true' : 'false');
                    if (active) b.classList.remove('has-attention');
                });
                Object.entries(panes).forEach(([key, el]) => {
                    if (!el) return;
                    const show = key === target;
                    el.hidden = !show;
                    el.classList.toggle('is-active', show);
                });
            });
        });
    }

    // Show/hide secondary tabs based on which weather mode is active.
    // Alerts mode -> Warnings tab; Current/SPC/MRMS -> Styling placeholder.
    // If the currently active tab becomes hidden, fall back to Layers.
    function _updateRightTabsAvailability() {
        const alertsOn = _isTypeEnabled('alerts');
        const styleModeOn = _isTypeEnabled('current') || _isTypeEnabled('spc') || _isTypeEnabled('mrms');

        const warnBtn = byId('wx-right-tab-btn-warnings');
        const styleBtn = byId('wx-right-tab-btn-styling');
        const warnPane = byId('wx-right-pane-warnings');
        const stylePane = byId('wx-right-pane-styling');

        const showWarn = alertsOn;
        const showStyle = !alertsOn && styleModeOn;

        if (warnBtn) warnBtn.hidden = !showWarn;
        if (styleBtn) styleBtn.hidden = !showStyle;

        // If active tab is now hidden, switch to Layers.
        const tabs = [
            { btn: byId('wx-right-tab-btn-layers'), pane: byId('wx-right-pane-layers'), key: 'layers' },
            { btn: warnBtn, pane: warnPane, key: 'warnings' },
            { btn: styleBtn, pane: stylePane, key: 'styling' },
        ];
        const active = tabs.find((t) => t.btn?.classList.contains('is-active'));
        if (active && active.btn?.hidden) {
            tabs.forEach((t) => {
                if (!t.btn || !t.pane) return;
                const isLayers = t.key === 'layers';
                t.btn.classList.toggle('is-active', isLayers);
                t.btn.setAttribute('aria-selected', isLayers ? 'true' : 'false');
                t.pane.hidden = !isLayers;
                t.pane.classList.toggle('is-active', isLayers);
            });
        }
    }

    // Ticker: refresh the panel once a minute so countdown text stays current
    // even between alert refreshes.
    setInterval(() => {
        if (byId('wx-right-pane-warnings')) {
            _renderActiveWarningsPanel();
        }
    }, 60_000);

    // ── Console test helpers (always exposed on window) ──────────────────────
    // _testAlertBanner(eventOrFeat?, areaDesc?, severity?)
    //   - With no args: synthetic Tornado Warning at the current map center.
    //   - First arg can be an event name string OR a real GeoJSON Feature.
    //   - Pass severity='Severe' (or 'Extreme') to trigger the immersive
    //     new-alert detail panel from the View button.
    function _testAlertBanner(eventOrFeat, areaDesc, severity) {
        let feat;
        if (eventOrFeat && typeof eventOrFeat === 'object' && eventOrFeat.geometry) {
            feat = eventOrFeat;
            // Allow caller to override severity on a real feature too.
            if (severity) {
                feat = JSON.parse(JSON.stringify(feat));
                feat.properties = feat.properties || {};
                feat.properties.severity = severity;
            }
        } else {
            const event = (typeof eventOrFeat === 'string' && eventOrFeat) || 'Tornado Warning';
            const c = map.getCenter();
            const d = 0.4; // ~½° box around center
            feat = {
                type: 'Feature',
                id: `test-${Date.now()}`,
                geometry: {
                    type: 'Polygon',
                    coordinates: [[
                        [c.lng - d, c.lat - d],
                        [c.lng + d, c.lat - d],
                        [c.lng + d, c.lat + d],
                        [c.lng - d, c.lat + d],
                        [c.lng - d, c.lat - d],
                    ]],
                },
                properties: {
                    event,
                    headline: `${event} (TEST)`,
                    areaDesc: areaDesc || 'Test Area',
                    severity: severity || 'Severe',
                    urgency: 'Immediate',
                    certainty: 'Observed',
                    sent: new Date().toISOString(),
                    expires: new Date(Date.now() + 30 * 60_000).toISOString(),
                    senderName: 'NWS Test Office',
                    description:
                        `At ${new Date().toLocaleTimeString()}, severe weather was indicated by radar.\n\n`
                        + `HAZARD...60 mph wind gusts and quarter size hail.\n\n`
                        + `SOURCE...Radar indicated.\n\n`
                        + `IMPACT...Hail damage to vehicles is expected. Expect wind damage to roofs, siding, and trees.\n\n`
                        + `LOCATIONS IMPACTED INCLUDE...\n${areaDesc || 'Test City, Test Town, Other Place'}.`,
                    instruction:
                        `For your protection move to an interior room on the lowest floor of a building.`,
                    parameters: {
                        hailThreat: ['RADAR INDICATED'],
                        maxHailSize: ['1.00'],
                        windThreat: ['RADAR INDICATED'],
                        maxWindGust: ['60 MPH'],
                    },
                },
            };
        }
        _showNewAlertBanner(feat);
        return feat;
    }

    // Single toggle for all top-bar "Test New Alert" UI behavior.
    const ENABLE_TEST_ALERT_UI = false;

    // Built-in test sample used when file:// fetches are blocked by browser CORS.
    const _TEST_STW_ALERT_COLLECTION = {
        type: 'FeatureCollection',
        features: [
            {
                id: 'https://api.weather.gov/alerts/urn:oid:2.49.0.1.840.0.76c0a170e6903c6a299dd412c2961289702eb43b.001.1',
                type: 'Feature',
                geometry: {
                    type: 'Polygon',
                    coordinates: [[[-81.03, 25.33], [-80.88, 25.41], [-80.77, 25.29], [-80.94, 25.2], [-81.03, 25.33]]],
                },
                properties: {
                    id: 'urn:oid:2.49.0.1.840.0.76c0a170e6903c6a299dd412c2961289702eb43b.001.1',
                    areaDesc: 'Miami-Dade, FL; Monroe, FL',
                    sent: '2026-04-20T18:07:00-04:00',
                    effective: '2026-04-20T18:07:00-04:00',
                    onset: '2026-04-20T18:07:00-04:00',
                    expires: '2026-04-20T18:22:44-04:00',
                    ends: '2026-04-20T18:30:00-04:00',
                    status: 'Actual',
                    messageType: 'Cancel',
                    category: 'Met',
                    severity: 'Minor',
                    certainty: 'Observed',
                    urgency: 'Past',
                    event: 'Severe Thunderstorm Warning',
                    senderName: 'NWS Miami FL',
                    headline: 'The Severe Thunderstorm Warning has been cancelled.',
                    description: 'The Severe Thunderstorm Warning has been cancelled and is no longer in effect.',
                    instruction: null,
                    response: 'AllClear',
                    parameters: {
                        AWIPSidentifier: ['SVSMFL'],
                        WMOidentifier: ['WWUS52 KMFL 202207'],
                        NWSheadline: ['THE SEVERE THUNDERSTORM WARNING FOR SOUTHERN MAINLAND MONROE AND MIAMI-DADE COUNTIES IS CANCELLED'],
                        eventMotionDescription: ['2026-04-20T22:05:00-00:00...storm...323DEG...15KT...25.29,-80.91'],
                        BLOCKCHANNEL: ['EAS', 'NWEM', 'CMAS'],
                        'EAS-ORG': ['WXR'],
                        VTEC: ['/O.CAN.KMFL.SV.W.0020.000000T0000Z-260420T2230Z/'],
                        eventEndingTime: ['2026-04-20T18:30:00-04:00'],
                    },
                    eventCode: {
                        SAME: ['SVS'],
                        NationalWeatherService: ['SVW'],
                    },
                },
            },
        ],
    };

    // _testAlertBannerFromJson(sourceOrUrl, severityOverride?)
    //   Fires a banner for every feature in a FeatureCollection. Accepts a URL
    //   or an inline GeoJSON object. Pass severityOverride to force the
    //   immersive detail flow regardless of the source severity.
    async function _testAlertBannerFromJson(sourceOrUrl, severityOverride, dismissMsOverride) {
        let coll = sourceOrUrl;
        if (typeof sourceOrUrl === 'string') {
            const resp = await fetch(sourceOrUrl, { cache: 'no-store' });
            coll = await resp.json();
        }
        const feats = Array.isArray(coll?.features) ? coll.features : [];
        feats.forEach((f) => {
            const nextProps = { ...(f.properties || {}) };
            if (severityOverride) nextProps.severity = severityOverride;
            if (Number.isFinite(dismissMsOverride) && dismissMsOverride > 0) {
                nextProps.__testDismissMs = dismissMsOverride;
            }
            const feat = { ...f, properties: nextProps };
            _showNewAlertBanner(feat);
        });
        return feats.length;
    }

    try {
        window._testAlertBanner = _testAlertBanner;
        window._testAlertBannerFromJson = _testAlertBannerFromJson;
    } catch (_) { /* non-browser */ }

    // Build an alerts API URL with given query params. stateCode is optional.
    function _buildAlertsUrl(stateCode, extraParams = {}) {
        const base = apiUrl('/api/data/alerts');
        const sep = base.includes('?') ? '&' : '?';
        const params = new URLSearchParams({
            ...(stateCode ? { state: stateCode } : {}),
            ...extraParams,
            _ts: String(Date.now()),
        });
        return `${base}${sep}${params.toString()}`;
    }

    async function loadAlerts(options = {}) {
        const { silentStatus = false } = options;
        const requestSeq = ++_alertsRequestSeq;
        const checkedCategories = _getCheckedAlertCategories();
        if (!checkedCategories.length) {
            _allAlertFeatures = [];
            _alertsDisplayFeatures = [];
            _swapAlertsLayer(null);
            const countEl = byId('weather-alerts-count');
            if (countEl) countEl.textContent = '0 active alert(s)';
            setLegend(null);
            _renderActiveWarningsPanel();
            return;
        }
        if (!silentStatus) setStatus('Loading alerts...');
        try {
            const scope = _alertsRequestScopeFromRegion();
            const zoomBucket = _alertsZoomBucket();

            // Fetch full geometry (interaction) and display geometry (rendering) in parallel.
            // Full is always fetched; display is fetched with zoom-based bucket.
            const fullUrl = _buildAlertsUrl(scope.stateCode, {
                geometry_mode: 'full',
                zoom_bucket: zoomBucket,
                ...scope.extraParams,
            });
            const displayUrl = _buildAlertsUrl(scope.stateCode, {
                geometry_mode: 'display',
                zoom_bucket: zoomBucket,
                ...scope.extraParams,
            });

            const [fullResp, displayResp] = await Promise.all([
                fetch(fullUrl, { cache: 'no-store' }),
                fetch(displayUrl, { cache: 'no-store' }),
            ]);

            if (!fullResp.ok) throw new Error(`HTTP ${fullResp.status}`);
            const fullGeojson = await fullResp.json();

            // Display fetch is best-effort: fall back to full on failure.
            let displayGeojson = fullGeojson;
            if (displayResp.ok) {
                try { displayGeojson = await displayResp.json(); } catch (_) { /* use full */ }
            }

            if (requestSeq !== _alertsRequestSeq || !_canApplyAlertsResponse()) return;

            // Keep non-category-filtered in-memory base collections for instant local re-filter.
            _alertsFullBaseFeatures = _stripInactiveAlerts(fullGeojson.features);
            _alertsDisplayBaseFeatures = _stripInactiveAlerts(displayGeojson.features);
            const fullFeatures = _filterAlertsByCategories(_alertsFullBaseFeatures, checkedCategories);
            const displayFeatures = _filterAlertsByCategories(_alertsDisplayBaseFeatures, checkedCategories);

            // ID tracking and banners always use the canonical full features.
            // _knownAlertIds === null means this is the first load — populate silently.
            const prevIds = _knownAlertIds;
            const newIdSet = new Set(fullFeatures.map(f => f.id).filter(Boolean));
            _knownAlertIds = newIdSet;

            if (prevIds !== null) {
                for (const feat of fullFeatures) {
                    if (!feat.id) continue;
                    if (prevIds.has(feat.id)) continue;
                    const event = feat?.properties?.event || '';
                    if (ALERT_NOTIFY_EVENTS.has(event)) {
                        _showNewAlertBanner(feat);
                    }
                }
            }

            _lastAlertsZoomBucket = zoomBucket;

            // Update state: full for interactions, display for rendering.
            _allAlertFeatures = fullFeatures;
            _alertsDisplayFeatures = displayFeatures;

            // Build replacement layer off-screen and swap only when ready.
            const nextLayer = _buildAlertsLayer(displayFeatures);
            _swapAlertsLayer(nextLayer);

            // Legend and count always reflect the full canonical feature set.
            buildAlertsLegend(fullFeatures);
            const countEl = byId('weather-alerts-count');
            if (countEl) countEl.textContent = `${fullFeatures.length} active alert(s)`;
            _renderActiveWarningsPanel();
            const alertsTsMs = _resolveDataTimestampMs(fullGeojson?._updated || displayGeojson?._updated);
            const alertsStaleNote = _staleNoteForTimestamp(alertsTsMs);
            if (!silentStatus) setStatus(`Alerts valid ${_formatValidTimeLabel(alertsTsMs)}.${alertsStaleNote}`);
            _setViewerTimestamp(alertsTsMs);
            _setReliability('alerts', 'Alerts', 'NWS, IEM', alertsTsMs);
            _setTimestampSource('alerts', 'alerts_cache_updated', alertsTsMs);
        } catch (err) {
            if (requestSeq !== _alertsRequestSeq) return;
            console.error('[alerts] Load error:', err);
            if (!silentStatus) setStatus(`Alerts error: ${err.message}`);
        }
    }

    const _SPC_CONVECTIVE_LABELS = {
        cat: 'Categorical',
        torn: 'Tornado Probabilistic',
        cigtorn: 'Tornado Significant',
        wind: 'Wind Probabilistic',
        cigwind: 'Wind Significant',
        hail: 'Hail Probabilistic',
        cighail: 'Hail Significant',
        prob: 'Probabilistic',
    };

    const _SPC_CIG_OVERLAY_BY_HAZARD = {
        torn: 'cigtorn',
        wind: 'cigwind',
        hail: 'cighail',
    };

    function _isSpcFireHazard(hazard) {
        return ['windrh', 'dryt', 'drytcat', 'drytprob', 'windrhcat', 'windrhprob'].includes(hazard);
    }

    function _getSpcStyleFn(hazard) {
        if (_isSpcFireHazard(hazard)) return spcFireStyle;
        if (hazard === 'prob' || hazard === 'torn' || hazard === 'wind' || hazard === 'hail' || _isSpcCigOverlayHazard(hazard)) {
            return _spcProbCigStyle;
        }
        return spcCatStyle;
    }

    function _isSpcCigOverlayHazard(hazard) {
        // CIG hazards (cigtorn/cigwind/cighail) render with hatch patterns and
        // always require non-zero DN filtering (their .lyr.geojson includes a
        // placeholder DN=0 feature when no Sig threat exists).
        return hazard === 'cigtorn' || hazard === 'cigwind' || hazard === 'cighail';
    }

    // Map the user's selected hazards to the single hazard whose prob legend
    // should be shown. cigtorn/cigwind/cighail map back to their base hazard.
    function _getSpcProbLegendHazard(hazards) {
        const cigToBase = { cigtorn: 'torn', cigwind: 'wind', cighail: 'hail' };
        const probHazards = ['torn', 'wind', 'hail', 'prob'];
        for (const h of hazards) {
            if (probHazards.includes(h)) return h === 'prob' ? 'torn' : h;
            if (cigToBase[h]) return cigToBase[h];
        }
        return null;
    }

    function _spcNonZeroDn(feat) {
        const raw = feat?.properties?.DN ?? feat?.properties?.dn;
        const value = Number(raw);
        return Number.isFinite(value) ? value !== 0 : true;
    }

    function _spcFeatureIsCig(feat) {
        const label = String(feat?.properties?.LABEL || feat?.properties?.label || '').toUpperCase();
        const label2 = String(feat?.properties?.LABEL2 || feat?.properties?.label2 || '').toUpperCase();
        return /CIG\s*[123]/.test(label) || label2.includes('CONDITIONAL INTENSITY');
    }

    function _applySpcCigPattern(feat, layer) {
        // Extract CIG intensity from feature properties
        const label = String(feat?.properties?.LABEL || feat?.properties?.label || '').toUpperCase();
        const label2 = String(feat?.properties?.LABEL2 || feat?.properties?.label2 || '').toUpperCase();
        const labelDigits = (label.match(/CIG\s*([123])/) || [])[1] || '';
        const isCig = !!labelDigits || label2.includes('CONDITIONAL INTENSITY');

        if (!isCig) return; // Only apply patterns to CIG zones

        const intensity = labelDigits || '1';
        const patternUrl = `url(#hatch-cig-${intensity})`;

        if (layer?._path) {
            const svgRoot = layer._path.ownerSVGElement;
            _ensureSpcCigPatternDefs(svgRoot);
            layer._path.setAttribute('fill', patternUrl);
            layer._path.setAttribute('fill-opacity', String(spcOpacity));
        }
    }

    function _applySpcCigPatternsToGroup(group) {
        if (!group || typeof group.eachLayer !== 'function') return;
        group.eachLayer((child) => {
            if (typeof child.eachLayer === 'function') {
                child.eachLayer((sub) => _applySpcCigPattern(sub?.feature, sub));
            } else {
                _applySpcCigPattern(child?.feature, child);
            }
        });
    }

    function _buildSpcRequestHazards(day, hazards) {
        // Each requested hazard is fetched directly. CIG hazards (cigtorn/cigwind/cighail)
        // are independent selections in the UI, not auto-overlays, so no derived requests
        // are added here.
        return hazards.map((hazard) => ({ hazard, overlay: false }));
    }

    function _spcGeojsonHasCigFeatures(geojson) {
        return (geojson?.features || []).some((feat) => {
            const label = String(feat?.properties?.LABEL || feat?.properties?.label || '').toUpperCase();
            return label.includes('CIG');
        });
    }

    function _getSpcDay() {
        return parseInt(byId('weather-spc-day')?.value || '1', 10);
    }

    function _getSpcFireDay() {
        return parseInt(byId('weather-spc-fire-day')?.value || '1', 10);
    }

    function _getAllowedSpcConvectiveHazards(day = _getSpcDay()) {
        if (day <= 2) return ['cat', 'torn', 'cigtorn', 'wind', 'cigwind', 'hail', 'cighail'];
        if (day === 3) return ['cat', 'prob'];
        return ['cat'];
    }

    function _getDefaultSpcConvectiveHazards(day = _getSpcDay()) {
        return ['cat'];
    }

    function _getSpcConvectiveLabel(hazard, day = _getSpcDay()) {
        if (hazard === 'cat' && day >= 4) return 'Severe Weather Outlook';
        return _SPC_CONVECTIVE_LABELS[hazard] || hazard;
    }

    function _getCheckedSpcConvectiveHazards() {
        return Array.from(document.querySelectorAll('.weather-spc-convective-toggle:checked')).map((el) => el.value);
    }

    function _getCheckedSpcFireHazards() {
        return Array.from(document.querySelectorAll('.weather-spc-fire-toggle:checked')).map((el) => el.value);
    }

    function _getSelectedSpcHazards(day = _getSpcDay()) {
        const fireHazards = _getCheckedSpcFireHazards();
        if (fireHazards.length) return fireHazards;
        const allowed = new Set(_getAllowedSpcConvectiveHazards(day));
        return _getCheckedSpcConvectiveHazards().filter((hazard) => allowed.has(hazard));
    }

    function _getPrimarySpcHazard(day = _getSpcDay()) {
        return _getSelectedSpcHazards(day)[0] || _getDefaultSpcConvectiveHazards(day)[0] || 'cat';
    }

    function _syncSpcConvectiveOptions(resetSelection = false) {
        const day = _getSpcDay();
        const allowed = new Set(_getAllowedSpcConvectiveHazards(day));
        const defaults = new Set(_getDefaultSpcConvectiveHazards(day));
        document.querySelectorAll('.weather-spc-convective-row').forEach((row) => {
            const hazard = row.dataset.hazard || '';
            const enabled = allowed.has(hazard);
            row.style.display = enabled ? '' : 'none';

            const input = row.querySelector('.weather-spc-convective-toggle');
            if (input) {
                if (!enabled) input.checked = false;
                else if (resetSelection) input.checked = defaults.has(hazard);
            }

            const label = row.querySelector('.weather-spc-convective-label');
            if (label) label.textContent = _getSpcConvectiveLabel(hazard, day);
        });

        if (resetSelection) {
            // Clear all fire weather checkboxes
            document.querySelectorAll('.weather-spc-fire-toggle').forEach((el) => { el.checked = false; });
        }
    }

    function _syncSpcFireWeatherOptions(resetSelection = false) {
        const fireDay = parseInt(byId('weather-spc-fire-day')?.value || '1', 10);
        const fireList = byId('weather-spc-fire-list');
        if (!fireList) return;

        // Show categorical fire weather products only for Days 3–8
        fireList.querySelectorAll('.weather-spc-fire-row[data-categorical="1"]').forEach((row) => {
            const visible = fireDay >= 3 && fireDay <= 8;
            row.style.display = visible ? '' : 'none';
            if (!visible) {
                const input = row.querySelector('input[type="checkbox"]');
                if (input) input.checked = false;
            }
        });

        if (resetSelection) {
            fireList.querySelectorAll('.weather-spc-fire-toggle').forEach((el) => { el.checked = false; });
        }
    }

    function _spcSupplementalSelections() {
        const reportsDays = [];
        if (byId('weather-spc-reports-today')?.checked) reportsDays.push('today');
        if (byId('weather-spc-reports-yesterday')?.checked) reportsDays.push('yesterday');

        const reportTypes = [];
        if (byId('weather-spc-report-type-torn')?.checked) reportTypes.push('torn');
        if (byId('weather-spc-report-type-wind')?.checked) reportTypes.push('wind');
        if (byId('weather-spc-report-type-hail')?.checked) reportTypes.push('hail');

        const watchLayers = [];
        if (byId('weather-spc-watch-tor-polygon')?.checked) watchLayers.push({ type: 'tor', mode: 'polygon' });
        else if (byId('weather-spc-watch-tor-counties')?.checked) watchLayers.push({ type: 'tor', mode: 'counties' });
        if (byId('weather-spc-watch-svr-polygon')?.checked) watchLayers.push({ type: 'svr', mode: 'polygon' });
        else if (byId('weather-spc-watch-svr-counties')?.checked) watchLayers.push({ type: 'svr', mode: 'counties' });

        return {
            reportsEnabled: reportsDays.length > 0 && reportTypes.length > 0,
            reportsDays,
            reportTypes,
            mdsEnabled: !!byId('weather-spc-show-mds')?.checked,
            watchesEnabled: watchLayers.length > 0,
            watchLayers,
        };
    }

    function _clearSpcConvectiveSelections() {
        document.querySelectorAll('.weather-spc-convective-toggle').forEach((el) => {
            el.checked = false;
        });
    }

    function _clearSpcWatchSelections() {
        [
            'weather-spc-watch-tor-polygon',
            'weather-spc-watch-tor-counties',
            'weather-spc-watch-svr-polygon',
            'weather-spc-watch-svr-counties',
        ].forEach((id) => {
            const el = byId(id);
            if (el) el.checked = false;
        });
    }

    function _clearSpcMdSelection() {
        const el = byId('weather-spc-show-mds');
        if (el) el.checked = false;
    }

    function _updateSpcReportFilterState() {
        const hasReportDay = !!byId('weather-spc-reports-today')?.checked
            || !!byId('weather-spc-reports-yesterday')?.checked;
        ['weather-spc-report-type-torn', 'weather-spc-report-type-wind', 'weather-spc-report-type-hail']
            .forEach((filterId) => {
                const filterEl = byId(filterId);
                if (!filterEl) return;
                if (!hasReportDay) filterEl.checked = false;
                filterEl.disabled = !hasReportDay;
            });
    }

    function _hasActiveSpcSupplementalSelections() {
        const supplemental = _spcSupplementalSelections();
        return supplemental.reportsEnabled || supplemental.mdsEnabled || supplemental.watchesEnabled;
    }

    function _shouldResetSpcConvectiveDaySelection() {
        return !_getCheckedSpcFireHazards().length && !_hasActiveSpcSupplementalSelections();
    }

    function _shouldResetSpcFireDaySelection() {
        return !_getCheckedSpcConvectiveHazards().length && !_hasActiveSpcSupplementalSelections();
    }

    function _clearSpcReportSelections() {
        ['weather-spc-reports-today', 'weather-spc-reports-yesterday'].forEach((id) => {
            const el = byId(id);
            if (el) el.checked = false;
        });
        _updateSpcReportFilterState();
    }

    function _clearSpcFireSelections(keepTarget = null) {
        document.querySelectorAll('.weather-spc-fire-toggle').forEach((el) => {
            if (keepTarget && el === keepTarget) return;
            el.checked = false;
        });
    }

    function _clearSpcExclusivePeers(group, options = {}) {
        if (group !== 'convective') _clearSpcConvectiveSelections();
        if (group !== 'watches') _clearSpcWatchSelections();
        if (group !== 'mds') _clearSpcMdSelection();
        if (group !== 'reports') _clearSpcReportSelections();
        if (group !== 'fire') _clearSpcFireSelections(options.keepFireTarget || null);
    }

    function _normalizeSpcWatchLayersForKey(watchLayers) {
        return (watchLayers || [])
            .map((w) => `${String(w?.type || '').toLowerCase()}:${String(w?.mode || '').toLowerCase()}`)
            .sort();
    }

    function _spcSelectionKey(day, fireDay, hazards, supplemental) {
        const sortedHazards = (hazards || []).map((h) => String(h)).sort();
        const watchLayers = _normalizeSpcWatchLayersForKey(supplemental?.watchLayers || []);
        const reportsDays = [...(supplemental?.reportsDays || [])].map((d) => String(d)).sort();
        const reportTypes = [...(supplemental?.reportTypes || [])].map((t) => String(t)).sort();
        return JSON.stringify({
            day: Number(day || 1),
            fireDay: Number(fireDay || 1),
            hazards: sortedHazards,
            reportsDays,
            reportTypes,
            mdsEnabled: !!supplemental?.mdsEnabled,
            watchesEnabled: !!supplemental?.watchesEnabled,
            watchLayers,
        });
    }

    function _currentSpcSelectionKey() {
        const day = _getSpcDay();
        const fireDay = _getSpcFireDay();
        const hazards = _getSelectedSpcHazards(day);
        const supplemental = _spcSupplementalSelections();
        return _spcSelectionKey(day, fireDay, hazards, supplemental);
    }

    function _isActiveSpcRequest(requestSeq, selectionKey) {
        return requestSeq === _spcRequestSeq
            && _canApplySpcResponse()
            && selectionKey === _currentSpcSelectionKey();
    }

    function _isAbortLikeError(err) {
        if (!err) return false;
        const name = String(err.name || '');
        if (name === 'AbortError' || name === 'TimeoutError') return true;
        const msg = String(err.message || '').toLowerCase();
        return msg.includes('abort') || msg.includes('timed out');
    }

    async function _fetchJsonWithTimeout(url, options = {}) {
        const parentSignal = options.signal || null;
        const timeoutMs = Number.isFinite(options.timeoutMs) ? options.timeoutMs : 10_000;
        const controller = new AbortController();
        let timeoutId = null;
        const abortFromParent = () => controller.abort();

        if (parentSignal) {
            if (parentSignal.aborted) controller.abort();
            else parentSignal.addEventListener('abort', abortFromParent, { once: true });
        }

        if (timeoutMs > 0) {
            timeoutId = setTimeout(() => controller.abort(), timeoutMs);
        }

        try {
            const resp = await fetch(url, { signal: controller.signal, cache: 'no-store' });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            return await resp.json();
        } catch (err) {
            const parentAborted = !!(parentSignal && parentSignal.aborted);
            const timedOut = !!(timeoutId && !parentAborted && controller.signal.aborted);
            if (timedOut) {
                const timeoutErr = new Error(`Request timed out after ${Math.round(timeoutMs / 1000)}s`);
                timeoutErr.name = 'TimeoutError';
                throw timeoutErr;
            }
            throw err;
        } finally {
            if (timeoutId) clearTimeout(timeoutId);
            if (parentSignal) parentSignal.removeEventListener('abort', abortFromParent);
        }
    }

    async function _fetchSpcReportsGeoJson(requestSeq, selectionKey, signal, dayKey, reportType) {
        const url = apiUrl(
            `/api/data/spc/reports?day=${encodeURIComponent(dayKey)}`
            + `&report_type=${encodeURIComponent(reportType || 'all')}`
            + `&report_mode=filtered`
        );
        const geojson = await _fetchJsonWithTimeout(url, {
            signal,
            timeoutMs: _SPC_SUPPLEMENTAL_TIMEOUT_MS,
        });
        if (!_isActiveSpcRequest(requestSeq, selectionKey)) return null;
        return geojson;
    }

    async function _fetchSpcActiveProductGeoJson(requestSeq, selectionKey, signal, product, query = '') {
        const url = apiUrl(`/api/data/spc/active?product=${encodeURIComponent(product)}${query}`);
        const geojson = await _fetchJsonWithTimeout(url, {
            signal,
            timeoutMs: _SPC_SUPPLEMENTAL_TIMEOUT_MS,
        });
        if (!_isActiveSpcRequest(requestSeq, selectionKey)) return null;
        return geojson;
    }

    async function _fetchSpcHazardGeoJson(requestSeq, selectionKey, signal, day, hazard) {
        const geojson = await _fetchJsonWithTimeout(
            apiUrl(`/api/data/spc?day=${day}&hazard=${hazard}`),
            {
                signal,
                timeoutMs: _SPC_PRIMARY_TIMEOUT_MS,
            },
        );
        if (!_isActiveSpcRequest(requestSeq, selectionKey)) return null;
        return { hazard, geojson };
    }

    async function refreshSpc() {
        const day = _getSpcDay();
        const fireDay = _getSpcFireDay();
        const hazards = _getSelectedSpcHazards(day);
        const supplemental = _spcSupplementalSelections();
        const hasSupplementalLayers = supplemental.reportsEnabled
            || supplemental.mdsEnabled
            || supplemental.watchesEnabled;
        const requestSeq = ++_spcRequestSeq;
        const selectionKey = _spcSelectionKey(day, fireDay, hazards, supplemental);
        if (_spcAbortController) {
            _spcAbortController.abort();
        }
        _spcAbortController = new AbortController();
        const requestSignal = _spcAbortController.signal;
        if (spcLayer) { map.removeLayer(spcLayer); spcLayer = null; }

        const countEl = byId('weather-spc-count');
        if (!hazards.length && !hasSupplementalLayers) {
            if (countEl) countEl.textContent = '0 feature(s)';
            setLegend(null);
            setMapEmptyMessage(null);
            setStatus('SPC selection cleared.');
            return;
        }

        // Fire hazards use the fire day selector; convective hazards use the convective day
        const areFireHazards = hazards.length > 0 && hazards.every((h) => _isSpcFireHazard(h));
        const effectiveDay = areFireHazards ? fireDay : day;
        const loadingParts = [];
        if (hazards.length) loadingParts.push(`day ${effectiveDay} (${hazards.join(', ')})`);
        if (supplemental.reportsEnabled) {
            const reportTypesLabel = supplemental.reportTypes.length === 3
                ? 'all'
                : supplemental.reportTypes.join(',');
            loadingParts.push(`reports:${supplemental.reportsDays.join('+')}/${reportTypesLabel}`);
        }
        if (supplemental.mdsEnabled) loadingParts.push('mds');
        if (supplemental.watchesEnabled) {
            loadingParts.push(`watches:${supplemental.watchLayers.map((w) => `${w.type}-${w.mode}`).join(',')}`);
        }
        setStatus(`Loading SPC ${loadingParts.join(' + ')}...`);
        if (!hazards.length && hasSupplementalLayers) {
            setMapEmptyMessage('Loading SPC supplemental overlays...');
        }
        try {
            const requestedHazards = hazards.length ? _buildSpcRequestHazards(effectiveDay, hazards) : [];
            const results = requestedHazards.length
                ? await Promise.allSettled(
                    requestedHazards.map((item) =>
                        _fetchSpcHazardGeoJson(requestSeq, selectionKey, requestSignal, effectiveDay, item.hazard)
                            .then((value) => ({ ...item, value }))
                    )
                )
                : [];

            if (!_isActiveSpcRequest(requestSeq, selectionKey)) return;

            const failures = results.filter((result) => result.status === 'rejected');
            failures.forEach((result) => {
                if (_isAbortLikeError(result.reason)) return;
                console.error('[spc] Load error:', result.reason);
            });

            const payloads = results
                .filter((result) => result.status === 'fulfilled' && result.value?.value)
                .map((result) => result.value);

            const reportsFeatureMap = new Map();
            let reportsGeojson = null;
            let mdsGeojson = null;
            const watchFeatureMap = new Map();
            let watchesGeojson = null;
            const supplementalFetches = [];
            let supplementalTimedOut = false;
            if (supplemental.reportsEnabled) {
                const reportTypeQueries = supplemental.reportTypes.length === 3
                    ? ['all']
                    : supplemental.reportTypes;
                supplemental.reportsDays.forEach((dayKey) => {
                    reportTypeQueries.forEach((reportType) => {
                        supplementalFetches.push(
                            _fetchSpcReportsGeoJson(requestSeq, selectionKey, requestSignal, dayKey, reportType)
                                .then((geojson) => {
                                    (geojson?.features || []).forEach((feat) => {
                                        const props = feat?.properties || {};
                                        const coords = Array.isArray(feat?.geometry?.coordinates)
                                            ? feat.geometry.coordinates
                                            : [];
                                        const dedupeKey = [
                                            dayKey,
                                            props.event || '',
                                            props.time || '',
                                            coords[0] ?? '',
                                            coords[1] ?? '',
                                            props.location || '',
                                            props.county || '',
                                            props.state || '',
                                        ].join('|');
                                        if (!reportsFeatureMap.has(dedupeKey)) {
                                            reportsFeatureMap.set(dedupeKey, {
                                                ...feat,
                                                properties: { ...props, report_day: props.report_day || dayKey },
                                            });
                                        }
                                    });
                                })
                        );
                    });
                });
            }
            if (supplemental.mdsEnabled) {
                supplementalFetches.push(
                    _fetchSpcActiveProductGeoJson(requestSeq, selectionKey, requestSignal, 'mds')
                        .then((geojson) => { mdsGeojson = geojson; })
                );
            }
            if (supplemental.watchesEnabled) {
                supplemental.watchLayers.forEach((watchCfg) => {
                    const q = `&watch_mode=${encodeURIComponent(watchCfg.mode)}`
                        + `&watch_types=${encodeURIComponent(watchCfg.type)}`;
                    supplementalFetches.push(
                        _fetchSpcActiveProductGeoJson(requestSeq, selectionKey, requestSignal, 'watches', q)
                            .then((geojson) => {
                                (geojson?.features || []).forEach((feat) => {
                                    const props = feat?.properties || {};
                                    const dedupeKey = String(
                                        feat?.id
                                        || `${props.id || ''}|${props.watch_type || ''}|${watchCfg.type}|${watchCfg.mode}`,
                                    );
                                    if (!watchFeatureMap.has(dedupeKey)) watchFeatureMap.set(dedupeKey, feat);
                                });
                            })
                    );
                });
            }
            if (supplementalFetches.length) {
                const supplementalResults = await Promise.allSettled(supplementalFetches);
                supplementalResults
                    .filter((r) => r.status === 'rejected')
                    .forEach((r) => {
                        if (_isAbortLikeError(r.reason)) {
                            if (String(r.reason?.name || '') === 'TimeoutError') {
                                supplementalTimedOut = true;
                            }
                            return;
                        }
                        console.error('[spc] Supplemental overlay load error:', r.reason);
                    });
            }

            if (!_isActiveSpcRequest(requestSeq, selectionKey)) return;

            if (reportsFeatureMap.size) {
                reportsGeojson = {
                    type: 'FeatureCollection',
                    features: Array.from(reportsFeatureMap.values()),
                };
            }
            if (watchFeatureMap.size) {
                watchesGeojson = {
                    type: 'FeatureCollection',
                    features: Array.from(watchFeatureMap.values()),
                };
            }

            if (!payloads.length && !hasSupplementalLayers) {
                const err = failures[0]?.reason || new Error('No SPC data returned');
                throw err;
            }

            const layerGroup = L.layerGroup();
            let count = 0;

            // Base probabilistic layers (torn/wind/hail) frequently include embedded
            // CIG features in their .lyr.geojson source. Always strip them so they only
            // render when the dedicated cigtorn/cigwind/cighail layer is also selected.
            const baseStripsCig = new Set(Object.keys(_SPC_CIG_OVERLAY_BY_HAZARD));

            // When all features get filtered out because of DN=0 placeholders,
            // capture the SPC LABEL text (e.g. "Less Than 2% All Areas") so we
            // can surface SPC's own wording in the empty-state overlay.
            const placeholderLabels = [];

            payloads.forEach(({ hazard, overlay, value }) => {
                const geojson = value.geojson;
                const isFireHazard = _isSpcFireHazard(hazard);
                const isCigOverlay = overlay || _isSpcCigOverlayHazard(hazard);
                const stripCigFromBase = !overlay && baseStripsCig.has(hazard);
                const isBaseProbOrCat = !overlay && ['cat', 'torn', 'wind', 'hail', 'prob'].includes(hazard);
                const visibleFeatures = (geojson.features || []).filter((feat) => {
                    if (isFireHazard) return _spcNonZeroDn(feat);
                    if (isCigOverlay) {
                        if (!_spcNonZeroDn(feat)) {
                            const lbl = String(feat?.properties?.LABEL || '').trim();
                            if (lbl) placeholderLabels.push(lbl);
                            return false;
                        }
                        return true;
                    }
                    // Base categorical/probabilistic outlooks include a DN=0 placeholder
                    // feature (e.g. "Less Than 2% All Areas") when no threat is present.
                    // Treat it as empty so the no-data overlay can be shown.
                    if (isBaseProbOrCat && !_spcNonZeroDn(feat)) {
                        const lbl = String(feat?.properties?.LABEL || '').trim();
                        if (lbl) placeholderLabels.push(lbl);
                        return false;
                    }
                    if (stripCigFromBase && _spcFeatureIsCig(feat)) return false;
                    return true;
                });
                if (!isCigOverlay) count += visibleFeatures.length;

                const styleFn = isCigOverlay ? _spcProbCigStyle : _getSpcStyleFn(hazard);

                const geoLayer = L.geoJSON(geojson, {
                    style: styleFn,
                    filter: (feat) => {
                        if (isFireHazard) return _spcNonZeroDn(feat);
                        if (isCigOverlay) return _spcNonZeroDn(feat);
                        if (isBaseProbOrCat && !_spcNonZeroDn(feat)) return false;
                        if (stripCigFromBase && _spcFeatureIsCig(feat)) return false;
                        return true;
                    },
                    onEachFeature: (feat, layer) => {
                        layer.bindPopup(spcPopup(feat));
                        // _path is created when layer is added to map; defer pattern application
                        layer.on('add', () => _applySpcCigPattern(feat, layer));
                    },
                });
                geoLayer._spcHazard = hazard;
                geoLayer._spcStyleFn = styleFn;
                layerGroup.addLayer(geoLayer);
            });

            if (reportsGeojson?.features?.length) {
                const reportsLayer = L.geoJSON(reportsGeojson, {
                    pointToLayer: (feat, latlng) => _spcReportMarker(feat, latlng),
                    onEachFeature: (feat, layer) => {
                        layer.bindPopup(_spcReportPopup(feat));
                    },
                });
                count += reportsGeojson.features.length;
                layerGroup.addLayer(reportsLayer);
            }

            if (watchesGeojson?.features?.length) {
                const watchesLayer = L.geoJSON(watchesGeojson, {
                    style: _spcWatchStyle,
                    onEachFeature: (feat, layer) => {
                        layer.on('click', (evt) => _openSpcTextDetail(evt?.latlng, feat));
                        layer.bindTooltip(String(feat?.properties?.short_label || feat?.properties?.event || 'Watch'), {
                            sticky: true,
                            opacity: 0.9,
                            className: 'wx-alert-hover-tip',
                        });
                    },
                });
                count += watchesGeojson.features.length;
                layerGroup.addLayer(watchesLayer);
            }

            if (mdsGeojson?.features?.length) {
                const mdsLayer = L.geoJSON(mdsGeojson, {
                    style: _spcMdStyle,
                    onEachFeature: (feat, layer) => {
                        layer.on('click', (evt) => _openSpcTextDetail(evt?.latlng, feat));
                        layer.bindTooltip(String(feat?.properties?.short_label || feat?.properties?.event || 'MD'), {
                            sticky: true,
                            opacity: 0.9,
                            className: 'wx-alert-hover-tip',
                        });
                    },
                });
                count += mdsGeojson.features.length;
                layerGroup.addLayer(mdsLayer);
            }

            spcLayer = layerGroup;
            if (byId('weather-show-spc')?.checked) {
                spcLayer.addTo(map);
                _applySpcCigPatternsToGroup(spcLayer);
            }

            if (supplemental.reportsEnabled && !hazards.length) {
                buildSpcReportsLegend(supplemental.reportTypes);
            } else if (hazards.length === 1 && _isSpcFireHazard(hazards[0])) {
                buildSpcFireLegend(hazards[0]);
            } else {
                if (hazards.includes('cat')) {
                    // For Day 4–8, use unique legend; otherwise, use categorical
                    if (effectiveDay >= 4 && effectiveDay <= 8) {
                        buildSpcProbLegend('cat', effectiveDay);
                    } else {
                        buildSpcCatLegend();
                    }
                } else {
                    // Pick a single hazard-specific prob legend based on the base
                    // probabilistic hazard selected (cigtorn etc. map back to torn).
                    const baseProbHazard = _getSpcProbLegendHazard(hazards);
                    if (baseProbHazard) buildSpcProbLegend(baseProbHazard, effectiveDay);
                    else setLegend(null);
                }
            }

            if (countEl) countEl.textContent = `${count} feature(s)`;
            if (count === 0) {
                // Prefer the SPC source LABEL (e.g. "Less Than 2% All Areas")
                // when the outlook returned a placeholder feature.
                const uniqueLabels = Array.from(new Set(placeholderLabels));
                const hazardLabels = hazards.map((h) => _getSpcConvectiveLabel(h, effectiveDay) || h).join(', ');
                let msg = '';
                if (hazards.length > 0) {
                    msg = uniqueLabels.length
                        ? `SPC Day ${effectiveDay} ${hazardLabels}: ${uniqueLabels.join(' · ')}`
                        : `No SPC data available for Day ${effectiveDay} ${hazardLabels}`;
                } else {
                    msg = supplementalTimedOut
                        ? 'SPC supplemental overlays timed out. Try again.'
                        : 'No SPC supplemental overlays available for the current selection.';
                }
                if (_isActiveSpcRequest(requestSeq, selectionKey)) {
                    setMapEmptyMessage(msg);
                }
            } else {
                if (_isActiveSpcRequest(requestSeq, selectionKey)) {
                    setMapEmptyMessage(null);
                }
            }
            const statusBits = [];
            if (hazards.length) statusBits.push(`Day ${effectiveDay}: ${hazards.join(', ')}`);
            if (supplemental.reportsEnabled) {
                const reportTypesLabel = supplemental.reportTypes.length === 3
                    ? 'all'
                    : supplemental.reportTypes.join(',');
                statusBits.push(`Reports ${supplemental.reportsDays.join('+')}/${reportTypesLabel}`);
            }
            if (supplemental.mdsEnabled) statusBits.push('MDs');
            if (supplemental.watchesEnabled) {
                statusBits.push(`Watches ${supplemental.watchLayers.map((w) => `${w.type}-${w.mode}`).join(',')}`);
            }
            const spcUpdatedRaw = payloads.map(({ value }) => value?.geojson?._updated).find(Boolean)
                || mdsGeojson?._updated
                || watchesGeojson?._updated;
            const spcTsMs = _resolveDataTimestampMs(spcUpdatedRaw);
            const spcStaleNote = _staleNoteForTimestamp(spcTsMs);
            setStatus(`SPC ${statusBits.join(' + ')} valid ${_formatValidTimeLabel(spcTsMs)}.${spcStaleNote}`);
            _setViewerTimestamp(spcTsMs);
            _setReliability('spc', `SPC ${statusBits.join(' + ')}`, 'NOAA SPC', spcTsMs);
            _setTimestampSource('spc', 'spc_cache_updated', spcTsMs);
        } catch (err) {
            if (!_isActiveSpcRequest(requestSeq, selectionKey)) return;
            if (_isAbortLikeError(err)) return;
            console.error('[spc] Load error:', err);
            setMapEmptyMessage(null);
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

    function _clearRadarSiteAndZoomConus() {
        const radarSiteSelect = byId('weather-radar-site');
        if (radarSiteSelect) radarSiteSelect.value = '';
        const regionSelect = byId('weather-region');
        const sentinelOpt = regionSelect?.querySelector('option[value="__RADAR_SITE_SELECTED__"]');
        if (sentinelOpt) sentinelOpt.remove();
        if (regionSelect) regionSelect.value = 'CONUS';
        if (_radarScrubMode) _exitRadarScrubMode(false);
        // Keep national IEM radar overlay workflow consistent for Home + CONUS paths.
        _ensureMrmsRadarOverlayEnabled();
        // Recompute tab control visibility (including Animate button) after clearing site.
        _updateTypeSections();
        fitRegion('CONUS');
        buildRadarSiteMarkerLegend();
        _updateObsDensityLabel();
        _updateGradientBlurControlVisibility();
        _clearSpeedOverride();
        _clearRadarCalLine();
        _syncRtmaStreamForRegion();
        _syncRtmaProductForStream();
        refreshActiveLayers();
    }

    function _setRegionAlertLocationState() {
        const regionSelect = byId('weather-region');
        if (!regionSelect) return;
        let sentinelOpt = regionSelect.querySelector('option[value="__ALERT_LOCATION__"]');
        if (!sentinelOpt) {
            sentinelOpt = document.createElement('option');
            sentinelOpt.value = '__ALERT_LOCATION__';
            sentinelOpt.textContent = 'Alert Selected';
            const conusOpt = regionSelect.querySelector('option[value="CONUS"]');
            if (conusOpt?.nextSibling) {
                regionSelect.insertBefore(sentinelOpt, conusOpt.nextSibling);
            } else {
                regionSelect.appendChild(sentinelOpt);
            }
        }
        regionSelect.value = '__ALERT_LOCATION__';
    }

    function _setRegionRadarSiteSelectedState() {
        const regionSelect = byId('weather-region');
        if (!regionSelect) return;

        let sentinelOpt = regionSelect.querySelector('option[value="__RADAR_SITE_SELECTED__"]');
        if (!sentinelOpt) {
            sentinelOpt = document.createElement('option');
            sentinelOpt.value = '__RADAR_SITE_SELECTED__';
            sentinelOpt.textContent = 'Radar Site Selected';
            const conusOpt = regionSelect.querySelector('option[value="CONUS"]');
            if (conusOpt?.nextSibling) {
                regionSelect.insertBefore(sentinelOpt, conusOpt.nextSibling);
            } else {
                regionSelect.appendChild(sentinelOpt);
            }
        }
        regionSelect.value = '__RADAR_SITE_SELECTED__';
    }

    function _setActiveWeatherType(type) {
        const target = byId(`weather-type-${type}`);
        if (!target) return;
        if (target.checked) return;
        target.checked = true;
        target.dispatchEvent(new Event('change'));
    }

    function _ensureMrmsRadarOverlayEnabled() {
        const radarOverlayToggle = byId('weather-alerts-radar');
        if (!radarOverlayToggle) return;
        if (!radarOverlayToggle.checked) {
            radarOverlayToggle.checked = true;
            radarOverlayToggle.dispatchEvent(new Event('change'));
            return;
        }
        _syncMrmsRadarOverlay();
    }

    function _ensureMrmsRadarOverlayDisabled() {
        const radarOverlayToggle = byId('weather-alerts-radar');
        if (!radarOverlayToggle) return;
        if (!radarOverlayToggle.checked) return;
        radarOverlayToggle.checked = false;
        radarOverlayToggle.dispatchEvent(new Event('change'));
    }

    // ── Top type controls and product visibility ─────────────────────────────
    function _isTypeEnabled(type) {
        return !!byId(`weather-type-${type}`)?.checked;
    }

    function _updateGradientBlurLabel() {
        const label = document.querySelector('label[for="weather-gradient-blur"]');
        if (!label) return;
        const baseLabel = label.dataset.baseLabel || 'Gradient Blur';
        label.dataset.baseLabel = baseLabel;
        label.textContent = `${baseLabel} (${_gradientBlurScale.toFixed(2)}x)`;
    }

    function _activeSurfaceProduct() {
        return document.querySelector('.weather-surface-product:checked')?.value || null;
    }

    function _activeSurfaceGradient() {
        const product = _activeSurfaceProduct();
        if (!product) return false;
        const grad = document.querySelector(`.weather-surface-gradient[data-product="${product}"]`);
        return !!grad?.checked;
    }

    function _updateGradientBlurControlVisibility() {
        const wrap = byId('weather-gradient-blur-wrap');
        if (!wrap) return;
        const show = _isTypeEnabled('current') && _activeSurfaceGradient();
        wrap.style.display = show ? '' : 'none';
    }

    function _updateTypeSections() {
        ['current', 'alerts', 'radar', 'satellite', 'spc', 'rtma', 'mrms', 'drought', 'tropical'].forEach((type) => {
            const section = byId(`wx-section-${type}`);
            if (section) section.style.display = _isTypeEnabled(type) ? '' : 'none';
        });
        const rtmaActive = _isTypeEnabled('rtma');
        const mrmsActive = _isTypeEnabled('mrms');
        const radarActive = _isTypeEnabled('radar');
        const animBtn = byId('weather-rtma-load-scrubber');
        const animWin = byId('rtma-animate-window');
        const modeControls = byId('wx-mode-controls');
        const radarOnly = radarActive && !rtmaActive && !mrmsActive;
        const radarHasSite = !!_activeRadarSite();
        const radarProductLabel = document.querySelector('label[for="weather-radar-product"]');
        const radarProductWrap = byId('wx-radar-select');
        const showRadarProductControls = radarActive && radarHasSite;
        if (modeControls) modeControls.style.display = _isTypeEnabled('satellite') ? 'none' : '';
        if (radarProductLabel) radarProductLabel.style.display = showRadarProductControls ? '' : 'none';
        if (radarProductWrap) radarProductWrap.style.display = showRadarProductControls ? '' : 'none';
        const showAnim = (rtmaActive || mrmsActive) || (radarActive && (!radarOnly || radarHasSite));
        if (animBtn) {
            animBtn.style.display = showAnim ? '' : 'none';
            if (!showAnim) animBtn.classList.remove('active');
        }
        if (animWin && !showAnim) animWin.style.display = 'none';
        _updateActiveTabName();
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
        const groups = ['current', 'alerts', 'spc', 'mrms', 'rtma', 'drought'];
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
        _updateRightTabsAvailability();
    }

    function _updateSubOptionVisibility() {
        const spcOpts = byId('weather-spc-opts');
        if (spcOpts) spcOpts.style.display = byId('weather-show-spc')?.checked ? '' : 'none';

        const surfaceOpts = byId('weather-surface-opts');
        if (surfaceOpts) surfaceOpts.style.display = '';

        const alertsOpts = byId('weather-alerts-opts');
        if (alertsOpts) alertsOpts.style.display = '';
    }

    function _clearAllMapLayers() {
        _stopSatelliteScrubPlay();
        if (alertsLayer && map.hasLayer(alertsLayer)) map.removeLayer(alertsLayer);

        if (spcLayer && map.hasLayer(spcLayer)) map.removeLayer(spcLayer);
        if (surfaceLayer && map.hasLayer(surfaceLayer)) map.removeLayer(surfaceLayer);
        if (radarLiveOverlay && map.hasLayer(radarLiveOverlay)) map.removeLayer(radarLiveOverlay);
        if (satelliteOverlay && map.hasLayer(satelliteOverlay)) map.removeLayer(satelliteOverlay);
        if (radarBackdropLayer && map.hasLayer(radarBackdropLayer)) map.removeLayer(radarBackdropLayer);
        if (radarSiteLayer && map.hasLayer(radarSiteLayer)) map.removeLayer(radarSiteLayer);
        if (rtmaOverlay && map.hasLayer(rtmaOverlay)) map.removeLayer(rtmaOverlay);
        if (rtmaGradientLayer && map.hasLayer(rtmaGradientLayer)) map.removeLayer(rtmaGradientLayer);
        if (rtmaPointLayer && map.hasLayer(rtmaPointLayer)) map.removeLayer(rtmaPointLayer);
        if (mrmsOverlay && map.hasLayer(mrmsOverlay)) map.removeLayer(mrmsOverlay);
        if (mrmsRadarSiteLayer && map.hasLayer(mrmsRadarSiteLayer)) map.removeLayer(mrmsRadarSiteLayer);
        if (droughtLayer && map.hasLayer(droughtLayer)) map.removeLayer(droughtLayer);
        droughtLayer = null;
        alertsLayer = null;
        spcLayer = null;
        surfaceLayer = null;
        radarLiveOverlay = null;
        satelliteOverlay = null;
        _clearSatelliteLayerPool();
        rtmaOverlay = null;
        rtmaGradientLayer = null;
        rtmaPointLayer = null;
        mrmsOverlay = null;
        _satelliteFrames = [];
        _satelliteFrameIndex = 0;
        _surfaceStations = [];
        setLegend(null);
    }

    function _resetTransientAlertUiForTabChange() {
        _closeNewAlertDetail();
        _dismissAllNewAlertBanners();
        if (_activeAlertsPopup?.popup) {
            try { map.closePopup(_activeAlertsPopup.popup); } catch (_) { /* ignore */ }
        }
        _activeAlertsPopup = null;
    }

    function _resetTransientInteractiveUiForTabChange() {
        _resetTransientAlertUiForTabChange();

        // Clear storm-track artifacts and state when changing weather tabs.
        _setStormTrackDrawMode(false);
        _stormTrackBaseLatLngs = [];
        _clearStormTrackLayer();

        // Clear radar speed calibrator line/state; this does not affect radar imagery.
        _setRadarCalDrawMode(false);
        _clearRadarCalLine();
        _clearSpeedOverride();
    }

    function _resetTabControlsToDefaults(type) {
        if (!type) return;
        if (type === 'alerts') {
            _applyDefaultAlertSelection();
            return;
        }

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

            if (changed) {
                if (el.tagName === 'INPUT' && String(el.type || '').toLowerCase() === 'range') {
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                }
                el.dispatchEvent(new Event('change', { bubbles: true }));
            }
        });
    }

    function _activeRadarSite() {
        return String(byId('weather-radar-site')?.value || '').trim().toUpperCase();
    }

    function _activeRadarProduct() {
        return String(byId('weather-radar-product')?.value || 'L3_N0B').trim().toUpperCase();
    }

    function _setRadarStatus(message) {
        const el = byId('weather-radar-status');
        if (el) el.textContent = message || '';
    }

    const _MRMS_RADAR_OVERLAY_ALLOWED_TYPES = new Set(['current', 'alerts', 'spc', 'rtma', 'radar']);
    const _MRMS_RADAR_REFRESH_INTERVAL_MS = 120000; // 2 minutes (MRMS update cadence)
    let _mrmsRadarOverlayState = null;
    let _mrmsRadarOverlayStarting = false;

    function _activeWeatherType() {
        const allTypes = ['current', 'alerts', 'radar', 'satellite', 'spc', 'rtma', 'mrms', 'drought', 'tropical'];
        return allTypes.find((type) => _isTypeEnabled(type)) || '';
    }

    function _mrmsRadarOverlayAllowedInContext() {
        if (_archiveMode || _rtmaScrubMode || _mrmsScrubMode || _radarScrubMode) {
            return false;
        }
        return _MRMS_RADAR_OVERLAY_ALLOWED_TYPES.has(_activeWeatherType());
    }

    async function _mrmsRadarOverlayFetchImageUrl() {
        try {
            const resp = await fetch(apiUrl('/api/data/mrms?product=Refl_BaseQC'));
            if (!resp.ok) return null;
            const data = await resp.json();
            return data?.image_url ? apiUrl(data.image_url) : null;
        } catch (_) {
            return null;
        }
    }

    function _mrmsRadarOverlayStop() {
        const s = _mrmsRadarOverlayState;
        if (!s) return;
        if (s.refreshTimer) clearInterval(s.refreshTimer);
        if (s.layer && map.hasLayer(s.layer)) {
            try {
                map.removeLayer(s.layer);
            } catch (_) {
                // ignore layer removal errors
            }
        }
        _mrmsRadarOverlayState = null;
    }

    async function _mrmsRadarOverlayRefresh() {
        const s = _mrmsRadarOverlayState;
        if (!s || !s.layer) return;
        if (!_mrmsRadarOverlayAllowedInContext()) {
            _mrmsRadarOverlayStop();
            return;
        }
        const newUrl = await _mrmsRadarOverlayFetchImageUrl();
        if (newUrl) s.layer.setUrl(newUrl);
    }

    function _mrmsRadarOverlaySetOpacity(value) {
        const s = _mrmsRadarOverlayState;
        if (!s || !s.layer) return;
        const op = parseFloat(value);
        if (!Number.isFinite(op)) return;
        s.opacity = op;
        s.layer.setOpacity(op);
    }

    async function _mrmsRadarOverlayStart(initialOpacity) {
        if (_mrmsRadarOverlayStarting || _mrmsRadarOverlayState) return; // prevent race conditions
        _mrmsRadarOverlayStarting = true;
        _mrmsRadarOverlayStop();

        try {
            const opacity = Number.isFinite(initialOpacity) ? initialOpacity : 0.6;
            const bounds = [[21.0, -130.0], [52.0, -60.0]]; // [[south, west], [north, east]]

            const imageUrl = await _mrmsRadarOverlayFetchImageUrl();
            if (!imageUrl) {
                console.warn('[MRMS Overlay] Failed to fetch initial image URL');
                return;
            }

            const layer = L.imageOverlay(imageUrl, bounds, {
                opacity,
                zIndex: 300,
                alt: 'MRMS Refl_BaseQC',
                interactive: false,
            });
            layer.addTo(map);

            const state = {
                layer,
                opacity,
                refreshTimer: null,
            };

            state.refreshTimer = setInterval(() => {
                _mrmsRadarOverlayRefresh();
            }, _MRMS_RADAR_REFRESH_INTERVAL_MS);

            _mrmsRadarOverlayState = state;
        } finally {
            _mrmsRadarOverlayStarting = false;
        }
    }

    function _syncMrmsRadarOverlay() {
        const cb = byId('weather-alerts-radar');
        const opacitySlider = byId('weather-alerts-radar-opacity');
        if (!cb || !cb.checked) {
            _mrmsRadarOverlayStop();
            return;
        }
        if (!_mrmsRadarOverlayAllowedInContext()) {
            _mrmsRadarOverlayStop();
            return;
        }
        const opacity = parseFloat(opacitySlider?.value ?? 0.6);
        if (!_mrmsRadarOverlayState && !_mrmsRadarOverlayStarting) {
            _mrmsRadarOverlayStart(opacity); // async, but fire-and-forget
            return;
        }
        if (_mrmsRadarOverlayState) {
            _mrmsRadarOverlaySetOpacity(opacity);
        }
    }

    function _ensureRadarBackdropLayer() {
        if (radarBackdropLayer && map.hasLayer(radarBackdropLayer)) {
            map.removeLayer(radarBackdropLayer);
        }
        radarBackdropLayer = null;
    }

    function _ensureRadarSiteLayer() {
        if (!radarSiteLayer) radarSiteLayer = L.layerGroup();
        return radarSiteLayer;
    }

    function _ensureRadarSiteHighlightLayer() {
        if (!radarSiteHighlightLayer) radarSiteHighlightLayer = L.layerGroup();
        return radarSiteHighlightLayer;
    }

    function _selectedRadarSites() {
        if (_radarMultiSites.size > 0) return [..._radarMultiSites];
        const site = _activeRadarSite();
        return site ? [site] : [];
    }

    function _syncRadarSiteSelectionHighlight() {
        const highlightLayer = _ensureRadarSiteHighlightLayer();
        highlightLayer.clearLayers();

        const show = _isTypeEnabled('radar') && !!byId('weather-radar-show-sites')?.checked;
        if (!show) {
            if (map.hasLayer(highlightLayer)) map.removeLayer(highlightLayer);
            return;
        }

        const selectedSites = _selectedRadarSites();
        selectedSites.forEach((siteId) => {
            const coords = _radarSiteCoords.get(siteId);
            if (!coords) return;
            const [lat, lon] = coords;
            const outerRing = L.circleMarker([lat, lon], {
                pane: 'radar-sites',
                radius: 10,
                color: '#f8fafc',
                weight: 2.2,
                opacity: 0.98,
                fillOpacity: 0,
                interactive: false,
                bubblingMouseEvents: false,
            });
            const innerRing = L.circleMarker([lat, lon], {
                pane: 'radar-sites',
                radius: 7,
                color: '#38bdf8',
                weight: 1.8,
                opacity: 0.95,
                fillColor: '#38bdf8',
                fillOpacity: 0.08,
                interactive: false,
                bubblingMouseEvents: false,
            });
            highlightLayer.addLayer(outerRing);
            highlightLayer.addLayer(innerRing);
        });

        if (!map.hasLayer(highlightLayer)) highlightLayer.addTo(map);
        if (typeof highlightLayer.bringToFront === 'function') highlightLayer.bringToFront();
    }

    function _bringBoundaryLayersAboveRadarOverlays() {
        // Keep boundary lines above radar image overlays only while on Radar tab,
        // so layering in other weather tabs remains unchanged.
        if (_activeWeatherType() !== 'radar') return;
        [countriesLayer, statesLayer, countiesLayer].forEach((layer) => {
            if (!layer || !map.hasLayer(layer)) return;
            if (typeof layer.bringToFront === 'function') layer.bringToFront();
        });
    }

    function _bringRadarSitesAboveRadarOverlays() {
        _bringBoundaryLayersAboveRadarOverlays();
        _syncRadarSiteLayerVisibility();
        _syncRadarSiteSelectionHighlight();
    }

    function _syncRadarSiteLayerVisibility() {
        const show = _isTypeEnabled('radar') && !!byId('weather-radar-show-sites')?.checked;
        const layer = _ensureRadarSiteLayer();
        const highlightLayer = _ensureRadarSiteHighlightLayer();
        if (show) {
            if (!map.hasLayer(layer)) layer.addTo(map);
            if (typeof layer.bringToFront === 'function') layer.bringToFront();
            _syncRadarSiteSelectionHighlight();
            if (map.hasLayer(highlightLayer) && typeof highlightLayer.bringToFront === 'function') {
                highlightLayer.bringToFront();
            }
        } else if (map.hasLayer(layer)) {
            map.removeLayer(layer);
            if (map.hasLayer(highlightLayer)) map.removeLayer(highlightLayer);
        }
    }

    function _radarSiteStatusClass(siteId) {
        const s = _radarSiteStatusMap.get(siteId);
        if (!s) return 'unknown';
        const ops = (s.operabilityStatus || '').toLowerCase();
        const sts = (s.status || '').toLowerCase();
        if (ops.includes('on-line')) return 'online';
        if (ops.includes('maintenance action mandatory')) return 'maint-mandatory';
        if (ops.includes('maintenance action required')) return 'maint-required';
        if (sts === 'start-up') return 'startup';
        return 'unknown';
    }

    function _radarSiteStatusColors(siteId, configured) {
        switch (_radarSiteStatusClass(siteId)) {
            case 'online': return { fill: '#22c55e', stroke: '#16a34a', weight: 1.5 };
            case 'maint-mandatory': return { fill: '#f97316', stroke: '#c2410c', weight: 1.5 };
            case 'maint-required': return { fill: '#f59e0b', stroke: '#b45309', weight: 1.5 };
            case 'startup': return { fill: '#60a5fa', stroke: '#1d4ed8', weight: 1.5 };
            default: return configured
                ? { fill: '#facc15', stroke: '#fef08a', weight: 1 }
                : { fill: '#64748b', stroke: '#94a3b8', weight: 1 };
        }
    }

    function _radarSiteMarkerStyle(siteId, configured) {
        const c = _radarSiteStatusColors(siteId, configured);
        return {
            pane: 'radar-sites',
            radius: 5,
            color: c.stroke,
            weight: c.weight,
            fillColor: c.fill,
            fillOpacity: 0.9,
        };
    }

    function _radarSiteStarIcon(siteId) {
        const c = _radarSiteStatusColors(siteId, true);
        // 5-pointed star, 15×15 px (~5% larger), outer r=6, inner r=2.4, centred at (7,7)
        const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 14 14">`
            + `<polygon points="7,1 8.65,5.01 13,5.15 9.82,7.74 10.97,12.09 7,9.66 3.03,12.09 4.18,7.74 1,5.15 5.35,5.01"`
            + ` fill="${c.fill}" stroke="${c.stroke}" stroke-width="0.9"/></svg>`;
        return L.divIcon({ html: svg, iconSize: [21, 21], iconAnchor: [8, 8], className: '' });
    }

    function _radarSiteTooltipContent(siteId) {
        const s = _radarSiteStatusMap.get(siteId);
        if (!s) return siteId;
        const parts = [`<strong>${siteId}</strong>`];
        if (s.operabilityStatus) parts.push(s.operabilityStatus);
        if (s.alarmSummary && s.alarmSummary !== 'No Alarms') parts.push(`⚠ ${s.alarmSummary}`);
        if (s.volumeCoveragePattern) parts.push(`VCP ${s.volumeCoveragePattern}`);
        return parts.join('<br>');
    }

    async function _loadRadarSites(force = false) {
        if (_radarSitesLoaded && !force) {
            _syncRadarSiteLayerVisibility();
            return;
        }
        const requestSeq = ++_radarSiteRequestSeq;
        try {
            const [sitesResult, statusResult] = await Promise.allSettled([
                fetch(apiUrl('/api/radar/live/sites')),
                fetch(apiUrl('/api/radar/status')),
            ]);

            if (requestSeq !== _radarSiteRequestSeq) return;

            if (sitesResult.status !== 'fulfilled' || !sitesResult.value.ok) {
                throw new Error(`Sites fetch failed: HTTP ${sitesResult.value?.status ?? 'network error'}`);
            }
            const data = await sitesResult.value.json();
            if (requestSeq !== _radarSiteRequestSeq) return;

            // Populate status map (best-effort — marker colours degrade gracefully if unavailable)
            if (statusResult.status === 'fulfilled' && statusResult.value.ok) {
                try {
                    const statusData = await statusResult.value.json();
                    const newStatusMap = new Map();
                    const stations = statusData?.stations || {};
                    Object.entries(stations).forEach(([id, info]) => {
                        newStatusMap.set(String(id).toUpperCase(), info);
                    });
                    _radarSiteStatusMap = newStatusMap;
                } catch (_) { /* status is best-effort */ }
            }

            const sites = Array.isArray(data?.sites) ? data.sites : [];
            _radarSiteCoords.clear();
            const configuredMap = new Map();
            sites.forEach((site) => {
                const siteId = String(site?.site || '').toUpperCase();
                if (!siteId) return;
                configuredMap.set(siteId, !!site?.configured);
            });
            _radarSiteConfiguredMap = configuredMap;

            const select = byId('weather-radar-site');
            if (select) {
                const keepValue = _activeRadarSite();
                select.innerHTML = '<option value="">National Composite</option>';
                const added = new Set();
                sites.forEach((site) => {
                    const siteId = String(site?.site || '').toUpperCase();
                    if (!siteId || added.has(siteId)) return;
                    added.add(siteId);
                    const option = document.createElement('option');
                    option.value = siteId;
                    option.textContent = site.configured ? `${siteId} (Live Cache)` : siteId;
                    select.appendChild(option);
                });
                if (keepValue && added.has(keepValue)) select.value = keepValue;
            }

            const layer = _ensureRadarSiteLayer();
            layer.clearLayers();
            sites.forEach((site) => {
                const lat = Number(site?.lat);
                const lon = Number(site?.lon);
                const siteId = String(site?.site || '').toUpperCase();
                if (!Number.isFinite(lat) || !Number.isFinite(lon) || !siteId) return;
                _radarSiteCoords.set(siteId, [lat, lon]);
                const marker = site.configured
                    ? L.marker([lat, lon], { icon: _radarSiteStarIcon(siteId), pane: 'radar-sites' })
                    : L.circleMarker([lat, lon], _radarSiteMarkerStyle(siteId, false));
                marker.bindTooltip(_radarSiteTooltipContent(siteId), {
                    direction: 'top',
                    className: 'city-name-label',
                });
                marker.on('click', (e) => {
                    if (e.originalEvent?.shiftKey) {
                        const wasScrubbing = _radarScrubMode;
                        if (wasScrubbing) {
                            _exitRadarScrubMode(false);
                            _setRtmaScrubberStatus('Site selection changed. Press Animate again to rebuild timeline.');
                            _showRadarWorkflowToast('Site selection changed. Press Animate again.');
                        }
                        // Shift+click: toggle this site in multi-selection
                        if (_radarMultiSites.has(siteId)) {
                            // Remove this site
                            _radarMultiSites.delete(siteId);
                            const removing = _radarSiteOverlays.get(siteId);
                            if (removing && map.hasLayer(removing)) map.removeLayer(removing);
                            _radarSiteOverlays.delete(siteId);
                            if (_radarMultiSites.size <= 1) {
                                // Collapse to single-site (or no-site)
                                const remaining = _radarMultiSites.size === 1
                                    ? [..._radarMultiSites][0] : null;
                                _clearRadarMultiSiteOverlays();
                                _radarMultiSites.clear();
                                if (remaining) {
                                    const sel = byId('weather-radar-site');
                                    if (sel) sel.value = remaining;
                                    _setRegionRadarSiteSelectedState();
                                }
                                _syncRadarSiteSelectionHighlight();
                                loadRadarLiveLatest();
                                return;
                            }
                            // Still 2+ sites — refresh remaining
                            _syncRadarSiteSelectionHighlight();
                            _loadAllMultiSiteOverlays();
                        } else {
                            // Add site to multi-selection
                            // Seed with the current active single site on first Shift+click
                            if (_radarMultiSites.size === 0) {
                                const cur = _activeRadarSite();
                                if (cur) _radarMultiSites.add(cur);
                            }
                            if (!_radarMultiSites.has(siteId) && _radarMultiSites.size >= RADAR_MULTI_SITE_MAX) {
                                const msg = `Maximum of ${RADAR_MULTI_SITE_MAX} radar sites can be animated together.`;
                                _setRtmaScrubberStatus(msg);
                                _showRadarWorkflowToast(`Multi-site limit reached (${RADAR_MULTI_SITE_MAX}).`);
                                setStatus(msg);
                                return;
                            }
                            _radarMultiSites.add(siteId);
                            // Park the single live overlay so multi overlays take over
                            if (radarLiveOverlay && map.hasLayer(radarLiveOverlay)) {
                                map.removeLayer(radarLiveOverlay);
                                radarLiveOverlay = null;
                            }
                            _syncRadarSiteSelectionHighlight();
                            _loadAllMultiSiteOverlays();
                        }
                    } else {
                        // Normal click: clear multi-selection, select this site
                        const wasScrubbing = _radarScrubMode;
                        if (wasScrubbing) {
                            _exitRadarScrubMode(false);
                            _setRtmaScrubberStatus('Site selection changed. Press Animate again to rebuild timeline.');
                            _showRadarWorkflowToast('Site selection changed. Press Animate again.');
                        }
                        _clearRadarMultiSiteOverlays();
                        _radarMultiSites.clear();
                        if (_isTypeEnabled('radar')) {
                            map.flyTo([lat, lon], Math.max(map.getZoom(), 9), { duration: 0.6 });
                        }
                        const sel = byId('weather-radar-site');
                        if (sel) sel.value = siteId;
                        _ensureMrmsRadarOverlayDisabled();
                        _setRegionRadarSiteSelectedState();
                        _updateTypeSections();
                        _syncRadarSiteSelectionHighlight();
                        loadRadarLiveLatest();
                    }
                });
                layer.addLayer(marker);
            });

            _radarSitesLoaded = true;
            _syncRadarSiteLayerVisibility();
        } catch (err) {
            console.error('[radar] Site load error:', err);
        }
    }

    function _canApplyRadarResponse(site, product) {
        if (_archiveMode || _radarScrubMode || !_isTypeEnabled('radar')) return false;
        if (_activeRadarProduct() !== product) return false;
        if (_radarMultiSites.size > 0) return _radarMultiSites.has(site);
        return _activeRadarSite() === site;
    }

    function _radarMultiSiteZIndex(siteId, siteOrder = null) {
        const selectedOrder = [..._radarMultiSites];
        let rank = selectedOrder.indexOf(siteId);
        if (rank < 0 && siteOrder instanceof Map) {
            rank = Number(siteOrder.get(siteId));
        }
        if (!Number.isFinite(rank) || rank < 0) rank = 0;
        const z = RADAR_MULTI_SITE_Z_BASE - (rank * RADAR_MULTI_SITE_Z_STEP);
        return Math.max(RADAR_MULTI_SITE_Z_MIN, z);
    }

    function _radarOverlayUrl(rawUrl) {
        const value = String(rawUrl || '').trim();
        if (!value) return '';

        if (/^https?:\/\//i.test(value)) {
            try {
                const parsed = new URL(value);
                const normalizedPath = `${parsed.pathname || ''}${parsed.search || ''}${parsed.hash || ''}`;
                return apiUrl(normalizedPath || value);
            } catch (_) {
                return apiUrl(value);
            }
        }

        return apiUrl(value);
    }

    async function _crossfadeOverlays(oldOverlay, newOverlay, targetOpacity, typeEnabledCheck, canContinue = () => true, fadeDurationMs = RADAR_CROSSFADE_MS, options = {}) {
        if (!oldOverlay || !newOverlay || !typeEnabledCheck()) return true;

        const keepNewAtTarget = options?.keepNewAtTarget === true;
        const removeOldAfterFade = options?.removeOldAfterFade !== false;
        newOverlay.setOpacity(keepNewAtTarget ? targetOpacity : 0);
        await new Promise((resolve) => requestAnimationFrame(resolve));
        await new Promise((resolve) => requestAnimationFrame(resolve));

        if (!canContinue()) {
            if (map.hasLayer(newOverlay)) map.removeLayer(newOverlay);
            return false;
        }

        const transitionElements = (overlay) => {
            const elements = [];
            const root = typeof overlay.getElement === 'function'
                ? overlay.getElement()
                : (typeof overlay.getContainer === 'function' ? overlay.getContainer() : overlay._container || null);
            if (root) elements.push(root);
            Object.values(overlay._tiles || {}).forEach((rec) => {
                if (rec?.el) elements.push(rec.el);
            });
            return elements;
        };
        const oldElements = transitionElements(oldOverlay);
        const newElements = transitionElements(newOverlay);
        oldElements.forEach((el) => { el.style.transition = `opacity ${fadeDurationMs}ms linear`; });
        newElements.forEach((el) => { el.style.transition = `opacity ${fadeDurationMs}ms linear`; });

        if (map.hasLayer(oldOverlay)) oldOverlay.setOpacity(0);
        if (!keepNewAtTarget) newOverlay.setOpacity(targetOpacity);

        setTimeout(() => {
            if (removeOldAfterFade && oldOverlay && map.hasLayer(oldOverlay)) map.removeLayer(oldOverlay);
            oldElements.forEach((el) => { el.style.transition = ''; });
            newElements.forEach((el) => { el.style.transition = ''; });
        }, fadeDurationMs);

        return true;
    }

    async function _crossfadeRadarOverlays(oldOverlay, newOverlay, canContinue = () => true) {
        return _crossfadeOverlays(oldOverlay, newOverlay, 0.9, () => _isTypeEnabled('radar'), canContinue, RADAR_CROSSFADE_MS);
    }

    async function _crossfadeSatelliteLayers(oldLayer, newLayer, canContinue = () => true) {
        return _crossfadeOverlays(
            oldLayer,
            newLayer,
            0.92,
            () => _isTypeEnabled('satellite'),
            canContinue,
            SATELLITE_CROSSFADE_MS,
            { removeOldAfterFade: !_satelliteScrubMode },
        );
    }

    function _clearRadarMultiSiteOverlays() {
        _radarSiteOverlays.forEach((overlay) => {
            if (overlay && map.hasLayer(overlay)) map.removeLayer(overlay);
        });
        _radarSiteOverlays.clear();
    }

    function _clearRadarLiveLayers() {
        if (radarLiveOverlay && map.hasLayer(radarLiveOverlay)) map.removeLayer(radarLiveOverlay);
        radarLiveOverlay = null;
        _clearRadarMultiSiteOverlays();
        _radarMultiSites.clear();
    }

    function _clearRadarLoadedOverlaysOnly() {
        _radarLiveRequestSeq += 1;
        _clearRadarLatestRetry();

        if (_radarScrubMode) {
            _exitRadarScrubMode(false);
        } else {
            _stopRadarScrubPlay();
        }

        _clearRadarLiveLayers();

        if (radarBackdropLayer && map.hasLayer(radarBackdropLayer)) {
            map.removeLayer(radarBackdropLayer);
            radarBackdropLayer = null;
        }
        _mrmsRadarOverlayStop();

        _setRadarStatus('Radar overlays cleared.');
        _setRtmaScrubberStatus('Radar overlays cleared.');
        setStatus('Cleared radar overlays for current selection.');
    }

    function _clearRadarLatestRetry() {
        if (_radarLatestRetryTimer) {
            clearTimeout(_radarLatestRetryTimer);
            _radarLatestRetryTimer = null;
        }
        _radarLatestRetryDeadlineMs = 0;
        _radarLatestRetrySite = '';
        _radarLatestRetryProduct = '';
    }

    function _scheduleRadarLatestRetry(site, product) {
        const retryIntervalMs = 5000;
        const retryWindowMs = 90_000;
        const now = Date.now();

        if (_radarLatestRetrySite !== site || _radarLatestRetryProduct !== product) {
            _clearRadarLatestRetry();
            _radarLatestRetrySite = site;
            _radarLatestRetryProduct = product;
            _radarLatestRetryDeadlineMs = now + retryWindowMs;
        }

        if (now >= _radarLatestRetryDeadlineMs) {
            _clearRadarLatestRetry();
            return;
        }

        if (_radarLatestRetryTimer) clearTimeout(_radarLatestRetryTimer);
        _radarLatestRetryTimer = setTimeout(() => {
            _radarLatestRetryTimer = null;
            if (!_canApplyRadarResponse(site, product)) {
                _clearRadarLatestRetry();
                return;
            }
            loadRadarLiveLatest();
        }, retryIntervalMs);
    }

    async function _loadAllMultiSiteOverlays() {
        if (_radarMultiSites.size === 0) return;
        const product = _activeRadarProduct();
        const requestSeq = ++_radarLiveRequestSeq;
        const sites = [..._radarMultiSites];
        const siteOrder = new Map(sites.map((site, idx) => [site, idx]));

        _setRadarStatus(`Loading ${sites.length} radar sites (${product})...`);
        setStatus(`Loading ${sites.length} radar sites for ${product}...`);

        await Promise.allSettled(sites.map(async (site) => {
            try {
                const siteConfigured = _radarSiteConfiguredMap.has(site)
                    ? !!_radarSiteConfiguredMap.get(site) : true;
                const params = new URLSearchParams({ site, product });
                if (!siteConfigured) params.set('force', '1');
                const resp = await fetch(apiUrl(`/api/radar/live/latest?${params.toString()}`), {
                    cache: 'no-store',
                });

                if (requestSeq !== _radarLiveRequestSeq || !_radarMultiSites.has(site) || !_isTypeEnabled('radar')) return;
                if (!resp.ok) return;

                const data = await resp.json();
                if (requestSeq !== _radarLiveRequestSeq || !_radarMultiSites.has(site) || !_isTypeEnabled('radar')) return;

                const imageUrl = data?.image_url;
                const bounds = Array.isArray(data?.bounds) ? data.bounds : null;
                if (!imageUrl || !bounds || bounds.length !== 4) return;

                await new Promise((resolve) => {
                    const img = new Image();
                    img.onload = resolve;
                    img.onerror = resolve;
                    img.src = _radarOverlayUrl(imageUrl);
                });

                if (requestSeq !== _radarLiveRequestSeq || !_radarMultiSites.has(site) || !_isTypeEnabled('radar')) return;

                const leafletBnds = [[bounds[2], bounds[0]], [bounds[3], bounds[1]]];
                const oldOverlay = _radarSiteOverlays.get(site);
                const newOverlay = L.imageOverlay(_radarOverlayUrl(imageUrl), leafletBnds, {
                    opacity: oldOverlay ? 0 : 0.9,
                    pane: 'radar-overlays',
                    zIndex: _radarMultiSiteZIndex(site, siteOrder),
                });
                if (_isTypeEnabled('radar')) {
                    newOverlay.addTo(map);
                    _bringRadarSitesAboveRadarOverlays();
                }

                if (oldOverlay && _isTypeEnabled('radar')) {
                    const applied = await _crossfadeRadarOverlays(
                        oldOverlay,
                        newOverlay,
                        () => requestSeq === _radarLiveRequestSeq && _radarMultiSites.has(site) && _isTypeEnabled('radar'),
                    );
                    if (!applied) return;
                } else if (oldOverlay && map.hasLayer(oldOverlay)) {
                    map.removeLayer(oldOverlay);
                }

                _radarSiteOverlays.set(site, newOverlay);

                if (typeof data?.configured === 'boolean') {
                    _radarSiteConfiguredMap.set(site, data.configured);
                }
            } catch (_) {
                // per-site failure is non-fatal in multi-site mode
            }
        }));

        if (requestSeq !== _radarLiveRequestSeq || !_isTypeEnabled('radar')) return;
        _setRadarStatus(`${sites.length} radar sites loaded (${product}).`);
        setStatus(`${sites.length} radar sites loaded for ${product}.`);
        buildRadarProductLegend(product);
    }

    async function loadRadarLiveLatest() {
        const site = _activeRadarSite();
        const product = _activeRadarProduct();
        const siteConfigured = _radarSiteConfiguredMap.has(site)
            ? !!_radarSiteConfiguredMap.get(site)
            : true;
        const requestSeq = ++_radarLiveRequestSeq;
        if (_radarLatestRetrySite && (_radarLatestRetrySite !== site || _radarLatestRetryProduct !== product)) {
            _clearRadarLatestRetry();
        }
        _syncRadarSiteLayerVisibility();
        _ensureRadarBackdropLayer();

        if (!site) {
            _clearRadarLatestRetry();
            _clearRadarLiveLayers();
            _setRadarStatus('');
            setStatus('Radar tab: IEM overlay is off.');
            // Show site marker legend when viewing CONUS (no site selected)
            buildRadarSiteMarkerLegend();
            return;
        }

        _setRadarStatus(
            siteConfigured
                ? `Loading ${site} ${product} live radar...`
                : `Loading ${site} ${product} live radar (on-demand L3 render)...`,
        );
        setStatus(`Loading radar site ${site} (${product})...`);

        try {
            const params = new URLSearchParams({ site, product });
            if (!siteConfigured) params.set('force', '1');
            const resp = await fetch(apiUrl(`/api/radar/live/latest?${params.toString()}`), {
                cache: 'no-store',
            });

            if (requestSeq !== _radarLiveRequestSeq || !_canApplyRadarResponse(site, product)) return;

            let data = null;
            try {
                data = await resp.json();
            } catch (_) {
                data = null;
            }

            if (!resp.ok) {
                const detail = String(data?.detail || data?.error || `HTTP ${resp.status}`);
                throw new Error(detail);
            }

            if (typeof data?.configured === 'boolean') {
                _radarSiteConfiguredMap.set(site, data.configured);
            }

            const imageUrl = data?.image_url;
            const bounds = Array.isArray(data?.bounds) ? data.bounds : null;
            if (!imageUrl || !bounds || bounds.length !== 4) {
                throw new Error('Live radar image/bounds unavailable.');
            }

            await new Promise((resolve) => {
                const img = new Image();
                img.onload = resolve;
                img.onerror = resolve;
                img.src = _radarOverlayUrl(imageUrl);
            });

            if (requestSeq !== _radarLiveRequestSeq || !_canApplyRadarResponse(site, product)) return;

            const oldOverlay = radarLiveOverlay;
            const leafletBounds = [[bounds[2], bounds[0]], [bounds[3], bounds[1]]];
            const newOverlay = L.imageOverlay(_radarOverlayUrl(imageUrl), leafletBounds, {
                opacity: oldOverlay ? 0 : 0.9,
                pane: 'radar-overlays',
                zIndex: 320,
            });
            if (_isTypeEnabled('radar')) {
                newOverlay.addTo(map);
                _bringRadarSitesAboveRadarOverlays();
            }

            if (oldOverlay && _isTypeEnabled('radar')) {
                const applied = await _crossfadeRadarOverlays(
                    oldOverlay,
                    newOverlay,
                    () => requestSeq === _radarLiveRequestSeq && _canApplyRadarResponse(site, product),
                );
                if (!applied) return;
            } else if (oldOverlay && map.hasLayer(oldOverlay)) {
                map.removeLayer(oldOverlay);
            }

            radarLiveOverlay = newOverlay;
            _clearRadarLatestRetry();

            const tsMs = _resolveDataTimestampMs(data?.timestamp);
            _setViewerTimestamp(tsMs);
            _setReliability('radar', `Radar ${product}`, data?.full_name || `Radar ${product}`, tsMs);
            buildRadarProductLegend(product); // async — fires and forgets intentionally
            _setTimestampSource('radar', 'radar_live_latest', tsMs);

            const provider = String(data?.source || 'live_cache').replaceAll('_', ' ');
            _setRadarStatus(`${site} ${product} live radar loaded.`);
            setStatus(`${site} ${product} ${_formatValidTimeLabel(tsMs)} (${provider}).`);

            if (data.history_filling) {
                _startRadarHistoryPoll(site, product);
            } else {
                if (_radarHistoryFillTimer) { clearTimeout(_radarHistoryFillTimer); _radarHistoryFillTimer = null; }
                _setAnimateButtonFilling(false);
            }
        } catch (err) {
            if (requestSeq !== _radarLiveRequestSeq || !_canApplyRadarResponse(site, product)) return;
            _clearRadarLiveLayers();
            const detail = String(err?.message || '');
            const noFrameYet = /no live radar frame cached yet|latest live radar image is missing/i.test(detail);
            if (noFrameYet) {
                _setRadarStatus(`Warming ${site} ${product} live radar...`);
                setStatus(`Radar ${site}/${product} is warming cache. Retrying automatically...`);
                _scheduleRadarLatestRetry(site, product);
                return;
            }
            _setRadarStatus(`Unable to load ${site} ${product} live radar.`);
            setStatus(`Radar live load failed for ${site}/${product}: ${err.message}`);
        }
    }

    function _setAnimateButtonFilling(filling, loadedCount = null, targetCount = null) {
        const btn = byId('weather-rtma-load-scrubber');
        if (!btn) return;
        if (filling) {
            if (_radarAnimateNewFrameTimer) { clearTimeout(_radarAnimateNewFrameTimer); _radarAnimateNewFrameTimer = null; }
            btn.classList.remove('radar-animate-newframe');
            const hasProgress = Number.isFinite(loadedCount) && Number.isFinite(targetCount) && targetCount > 0;
            const clampedLoaded = hasProgress ? Math.max(0, Math.min(Number(loadedCount), Number(targetCount))) : 0;
            btn.classList.add('radar-animate-filling');
            btn.textContent = hasProgress
                ? `Loading Frames... (${clampedLoaded}/${targetCount})`
                : 'Loading Frames...';
            btn.title = 'History loading in background \u2014 animation will be ready shortly';
        } else {
            if (_radarAnimateNewFrameTimer) { clearTimeout(_radarAnimateNewFrameTimer); _radarAnimateNewFrameTimer = null; }
            btn.classList.remove('radar-animate-newframe');
            btn.classList.remove('radar-animate-filling');
            btn.textContent = 'Animate';
            btn.title = '';
        }
    }

    function _stopRadarScrubWarmPoll() {
        if (_radarScrubWarmPollTimer) {
            clearTimeout(_radarScrubWarmPollTimer);
            _radarScrubWarmPollTimer = null;
        }
        _radarScrubWarmPollDeadlineMs = 0;
        _radarScrubWarmStablePolls = 0;
    }

    function _startRadarScrubWarmPoll(site, product) {
        _stopRadarScrubWarmPoll();
        _radarScrubWarmPollDeadlineMs = Date.now() + 90_000;
        _radarScrubWarmStablePolls = 0;

        const tick = async () => {
            _radarScrubWarmPollTimer = null;
            if (!_radarScrubMode || !_isTypeEnabled('radar')) {
                _stopRadarScrubWarmPoll();
                return;
            }
            if (_activeRadarSite() !== site || _activeRadarProduct() !== product) {
                _stopRadarScrubWarmPoll();
                return;
            }

            const appended = await _tryAppendNewRadarFrames();
            if (appended > 0) {
                _radarScrubWarmStablePolls = 0;
            } else {
                _radarScrubWarmStablePolls += 1;
            }

            if (Date.now() >= _radarScrubWarmPollDeadlineMs || _radarScrubWarmStablePolls >= 4) {
                _stopRadarScrubWarmPoll();
                return;
            }

            _radarScrubWarmPollTimer = setTimeout(tick, 3000);
        };

        _radarScrubWarmPollTimer = setTimeout(tick, 3000);
    }

    function _startRadarHistoryPoll(site, product) {
        if (_radarHistoryFillTimer) clearTimeout(_radarHistoryFillTimer);
        const deadline = Date.now() + 90_000;
        const readyFrameCount = 24;
        let lastCount = 0;
        _setAnimateButtonFilling(true, 1, readyFrameCount);

        async function poll() {
            if (_activeRadarSite() !== site || _activeRadarProduct() !== product) {
                _setAnimateButtonFilling(false);
                return;
            }
            try {
                const params = new URLSearchParams({ site, product, hours: '3' });
                const resp = await fetch(apiUrl(`/api/radar/live/frames?${params.toString()}`), { cache: 'no-store' });
                if (resp.ok) {
                    const data = await resp.json();
                    const count = data.frame_count || 0;
                    _setAnimateButtonFilling(true, count, readyFrameCount);
                    // End loading state as soon as animation is meaningfully ready.
                    if (count >= readyFrameCount) {
                        _setAnimateButtonFilling(false);
                        return;
                    }
                    // Fallback for sparse streams: stop when count is stable across polls.
                    if (count > 1 && count === lastCount) {
                        _setAnimateButtonFilling(false);
                        return;
                    }
                    lastCount = count;
                }
            } catch (_) { }
            if (Date.now() < deadline) {
                _radarHistoryFillTimer = setTimeout(poll, 3000);
            } else {
                _setAnimateButtonFilling(false);
            }
        }

        _radarHistoryFillTimer = setTimeout(poll, 3000);
    }

    function _reloadRadarForCurrentSelection() {
        if (!_isTypeEnabled('radar')) return;
        if (_radarScrubMode) {
            loadRadarScrubberFrames();
            return;
        }
        if (_radarMultiSites.size > 1) {
            _loadAllMultiSiteOverlays();
            return;
        }
        loadRadarLiveLatest();
    }

    function _stopRadarScrubPlay() {
        if (_radarScrubPlayTimer) {
            clearInterval(_radarScrubPlayTimer);
            _radarScrubPlayTimer = null;
        }
        const btn = byId('scrubber-play');
        if (btn) btn.textContent = '▶';
    }

    function _startRadarScrubPlay() {
        const frameCount = _radarScrubIsTimeMode ? _radarScrubTimelineMs.length : _radarScrubFrames.length;
        if (!frameCount || _radarScrubPlayTimer) return;
        const btn = byId('scrubber-play');
        if (btn) btn.textContent = '⏸';

        const tick = async () => {
            const totalFrames = _radarScrubIsTimeMode ? _radarScrubTimelineMs.length : _radarScrubFrames.length;
            if (!_radarScrubPlayTimer || !totalFrames) return;
            const atLast = _radarScrubFrameIndex >= totalFrames - 1;

            if (atLast) {
                // Pause on the last frame before restarting
                if (!_radarScrubPlayTimer || !totalFrames) return;
                _radarScrubPlayTimer = setTimeout(async () => {
                    if (_radarScrubPlayTimer) {
                        await _renderRadarScrubFrame(0);
                        if (_radarScrubPlayTimer) {
                            _radarScrubPlayTimer = setTimeout(tick, _scrubberPlaybackDelay(RTMA_SCRUB_PLAY_INTERVAL_MS));
                        }
                    }
                }, _scrubberPlaybackDelay(RTMA_SCRUB_LOOP_HOLD_MS, 350));
            } else {
                // Advance to next frame
                const next = _radarScrubFrameIndex + 1;
                await _renderRadarScrubFrame(next);
                const stillFrames = _radarScrubIsTimeMode ? _radarScrubTimelineMs.length : _radarScrubFrames.length;
                if (!_radarScrubPlayTimer || !stillFrames) return;
                _radarScrubPlayTimer = setTimeout(tick, _scrubberPlaybackDelay(RTMA_SCRUB_PLAY_INTERVAL_MS));
            }
        };

        _radarScrubPlayTimer = setTimeout(tick, _scrubberPlaybackDelay(RTMA_SCRUB_PLAY_INTERVAL_MS));
    }

    function _radarScrubFrameTsMs(frame) {
        return _resolveDataTimestampMs(frame?.timestamp);
    }

    function _normalizeRadarScrubFrames(rawFrames, site, product) {
        const normalized = (Array.isArray(rawFrames) ? rawFrames : [])
            .filter((f) => f && f.image_url && Array.isArray(f.bounds) && f.bounds.length === 4)
            .map((f) => ({
                frame_key: f.frame_key || '',
                source_data_key: f.source_data_key || '',
                image_url: f.image_url || '',
                bounds: f.bounds || null,
                timestamp: f.timestamp || '',
                ts_ms: _radarScrubFrameTsMs(f),
                site,
                product,
            }))
            .filter((f) => Number.isFinite(f.ts_ms))
            .sort((a, b) => a.ts_ms - b.ts_ms);
        return normalized;
    }

    function _buildRadarTimeTimelineMs(framesBySite) {
        let minTs = Number.POSITIVE_INFINITY;
        let maxTs = Number.NEGATIVE_INFINITY;
        framesBySite.forEach((frames) => {
            frames.forEach((frame) => {
                if (!Number.isFinite(frame?.ts_ms)) return;
                if (frame.ts_ms < minTs) minTs = frame.ts_ms;
                if (frame.ts_ms > maxTs) maxTs = frame.ts_ms;
            });
        });
        if (!Number.isFinite(minTs) || !Number.isFinite(maxTs)) return [];

        const minuteMs = 60_000;
        const start = Math.floor(minTs / minuteMs) * minuteMs;
        const end = Math.floor(maxTs / minuteMs) * minuteMs;
        const ticks = [];
        for (let ts = start; ts <= end; ts += minuteMs) ticks.push(ts);
        return ticks;
    }

    function _frameAtOrBeforeTick(frames, tickMs) {
        let pick = null;
        for (let i = 0; i < frames.length; i += 1) {
            const frame = frames[i];
            if (!Number.isFinite(frame?.ts_ms)) continue;
            if (frame.ts_ms <= tickMs) pick = frame;
            else break;
        }
        return pick;
    }

    function _canApplyRadarScrubResponse(renderSeq) {
        return renderSeq === _radarScrubRenderSeq && _radarScrubMode && _isTypeEnabled('radar');
    }

    function _radarCurrentScrubContextKey(productOverride = null) {
        const product = String(productOverride || _activeRadarProduct() || '').toUpperCase();
        const sites = _radarMultiSites.size > 1
            ? [..._radarMultiSites].map((s) => String(s || '').toUpperCase()).filter(Boolean).sort()
            : [String(_activeRadarSite() || '').toUpperCase()].filter(Boolean);
        return `${product}|${sites.join(',')}`;
    }

    async function _renderRadarScrubFrame(index) {
        const totalFrames = _radarScrubIsTimeMode ? _radarScrubTimelineMs.length : _radarScrubFrames.length;
        if (!totalFrames || !_radarScrubMode || !_isTypeEnabled('radar')) return;
        const liveContextKey = _radarCurrentScrubContextKey();
        if (_radarScrubContextKey && liveContextKey && _radarScrubContextKey !== liveContextKey) {
            _exitRadarScrubMode(false);
            _setRtmaScrubberStatus('Site selection changed. Press Animate again to rebuild timeline.');
            _showRadarWorkflowToast('Selection changed. Press Animate again.');
            setStatus('Radar selection changed. Press Animate again to rebuild animation timeline.');
            return;
        }
        _radarScrubFrameIndex = Math.max(0, Math.min(index, totalFrames - 1));
        _updateRtmaScrubberUi();
        const renderSeq = ++_radarScrubRenderSeq;

        try {
            if (_radarScrubIsTimeMode) {
                const tickMs = _radarScrubTimelineMs[_radarScrubFrameIndex];
                if (!Number.isFinite(tickMs)) throw new Error('Invalid timeline tick.');

                if (radarLiveOverlay && map.hasLayer(radarLiveOverlay)) {
                    map.removeLayer(radarLiveOverlay);
                    radarLiveOverlay = null;
                }

                const sites = [..._radarScrubFramesBySite.keys()];
                const selectedSiteOrder = new Map([..._radarMultiSites].map((site, idx) => [site, idx]));
                let renderedSites = 0;
                for (let i = 0; i < sites.length; i += 1) {
                    const site = sites[i];
                    const frames = _radarScrubFramesBySite.get(site) || [];
                    const frame = _frameAtOrBeforeTick(frames, tickMs);
                    if (!frame) continue;

                    const imageUrl = frame.image_url;
                    const bounds = Array.isArray(frame.bounds) ? frame.bounds : null;
                    if (!imageUrl || !bounds || bounds.length !== 4) continue;

                    await new Promise((resolve) => {
                        const img = new Image();
                        img.onload = resolve;
                        img.onerror = resolve;
                        img.src = _radarOverlayUrl(imageUrl);
                    });
                    if (!_canApplyRadarScrubResponse(renderSeq)) return;

                    const oldOverlay = _radarSiteOverlays.get(site) || null;
                    const leafletBounds = [[bounds[2], bounds[0]], [bounds[3], bounds[1]]];
                    const newOverlay = L.imageOverlay(_radarOverlayUrl(imageUrl), leafletBounds, {
                        opacity: oldOverlay ? 0 : 0.9,
                        pane: 'radar-overlays',
                        zIndex: _radarMultiSiteZIndex(site, selectedSiteOrder),
                    });
                    if (_isTypeEnabled('radar')) {
                        newOverlay.addTo(map);
                        _bringRadarSitesAboveRadarOverlays();
                    }

                    if (oldOverlay && _isTypeEnabled('radar')) {
                        const applied = await _crossfadeRadarOverlays(
                            oldOverlay,
                            newOverlay,
                            () => _canApplyRadarScrubResponse(renderSeq),
                        );
                        if (!applied) return;
                    } else if (oldOverlay && map.hasLayer(oldOverlay)) {
                        map.removeLayer(oldOverlay);
                    }

                    _radarSiteOverlays.set(site, newOverlay);
                    renderedSites += 1;
                }

                _setViewerTimestamp(tickMs);
                _setReliability('radar', `Radar ${_activeRadarProduct()}`, 'Radar live frames', tickMs);
                _setTimestampSource('radar', 'radar_live_frames', tickMs);
                _setRtmaScrubberStatus(`${_radarScrubFrameIndex + 1} / ${_radarScrubTimelineMs.length} ticks (${renderedSites}/${sites.length} sites).`);
                setStatus(`Radar multi-site scrub ${_formatValidTimeLabel(tickMs)}.`);
                return;
            }

            const frame = _radarScrubFrames[_radarScrubFrameIndex];
            const imageUrl = frame?.image_url;
            const bounds = Array.isArray(frame?.bounds) ? frame.bounds : null;
            if (!imageUrl || !bounds || bounds.length !== 4) throw new Error('Frame has no image/bounds.');

            await new Promise((resolve) => {
                const img = new Image();
                img.onload = resolve;
                img.onerror = resolve;
                img.src = _radarOverlayUrl(imageUrl);
            });
            if (!_canApplyRadarScrubResponse(renderSeq)) return;

            const oldOverlay = radarLiveOverlay;
            const leafletBounds = [[bounds[2], bounds[0]], [bounds[3], bounds[1]]];
            const newOverlay = L.imageOverlay(_radarOverlayUrl(imageUrl), leafletBounds, {
                opacity: oldOverlay ? 0 : 0.9,
                pane: 'radar-overlays',
                zIndex: 320,
            });
            if (_isTypeEnabled('radar')) {
                newOverlay.addTo(map);
                _bringRadarSitesAboveRadarOverlays();
            }

            if (oldOverlay && _isTypeEnabled('radar')) {
                const applied = await _crossfadeRadarOverlays(
                    oldOverlay,
                    newOverlay,
                    () => _canApplyRadarScrubResponse(renderSeq),
                );
                if (!applied) return;
            } else if (oldOverlay && map.hasLayer(oldOverlay)) {
                map.removeLayer(oldOverlay);
            }

            radarLiveOverlay = newOverlay;
            const tsMs = _resolveDataTimestampMs(frame?.timestamp);
            _setViewerTimestamp(tsMs);
            _setReliability('radar', `Radar ${_activeRadarProduct()}`, 'Radar live frames', tsMs);
            _setTimestampSource('radar', 'radar_live_frames', tsMs);
            _setRtmaScrubberStatus(`${_radarScrubFrameIndex + 1} / ${_radarScrubFrames.length} frames.`);
            setStatus(`Radar scrub ${_formatValidTimeLabel(tsMs)}.`);
        } catch (err) {
            if (!_canApplyRadarScrubResponse(renderSeq)) return;
            setStatus(`Radar scrubber error: ${err.message}`);
            _setRtmaScrubberStatus(`Frame unavailable: ${err.message}`);
        }
    }

    function _exitRadarScrubMode(shouldRefresh = true) {
        if (_radarHistoryFillTimer) { clearTimeout(_radarHistoryFillTimer); _radarHistoryFillTimer = null; }
        _stopRadarScrubWarmPoll();
        _setAnimateButtonFilling(false);
        _stopRadarScrubPlay();
        _radarScrubLoadSeq += 1;
        _radarScrubRenderSeq += 1;
        _radarScrubMode = false;
        _radarScrubFrames = [];
        _radarScrubIsTimeMode = false;
        _radarScrubTimelineMs = [];
        _radarScrubFramesBySite = new Map();
        _radarScrubContextKey = '';
        _radarScrubFrameIndex = 0;
        _setArchiveProgress(false);
        _setArchiveScrubber(false);
        _setScrubberControlsEnabled(false);
        _setRtmaScrubberStatus('');
        byId('weather-rtma-load-scrubber')?.classList.remove('active');
        byId('weather-mode-current')?.classList.add('active');
        const rtmaWin = byId('rtma-animate-window');
        const mrmsWin = byId('mrms-animate-window');
        if (rtmaWin) rtmaWin.style.display = 'none';
        if (mrmsWin) mrmsWin.style.display = 'none';
        _showRadarAutoUpdateRow(false);
        _updateRadarNextUpdateCountdown();
        if (shouldRefresh) loadRadarLiveLatest();
    }

    async function loadRadarScrubberFrames() {
        if (_rtmaScrubMode) _exitRtmaScrubMode(false);
        if (_mrmsScrubMode) _exitMrmsScrubMode(false);
        _stopRadarScrubWarmPoll();

        const loadSeq = ++_radarScrubLoadSeq;
        const site = _activeRadarSite();
        const product = _activeRadarProduct();
        const contextKey = _radarCurrentScrubContextKey(product);
        if (!site) {
            _setArchiveScrubber(true);
            _setScrubberControlsEnabled(false);
            _setRtmaScrubberStatus('Select a radar site to animate scrubber frames.');
            _setRadarStatus(`Select a radar site to animate ${product}.`);
            setStatus('Select a radar site first (National Composite has no frame scrubber).');
            return;
        }

        _radarScrubMode = true;
        _stopRadarScrubPlay();
        _radarScrubRenderSeq += 1;
        _radarScrubFrames = [];
        _radarScrubIsTimeMode = false;
        _radarScrubTimelineMs = [];
        _radarScrubFramesBySite = new Map();
        _radarScrubContextKey = contextKey;
        _radarScrubFrameIndex = 0;
        _setArchiveScrubber(true);
        _setArchiveProgress(true, 10, 'Loading Radar frame list...');
        _setScrubberControlsEnabled(false);
        _setRadarStatus(`Loading ${site} ${product} radar animation frames...`);
        _updateRtmaScrubberUi();

        const rtmaSlider = document.querySelector('#rtma-animate-slider');
        const maxHours = Math.max(1, rtmaSlider ? Number(rtmaSlider.value) : 3);
        const multiSites = _radarMultiSites.size > 1 ? [..._radarMultiSites] : [];

        try {
            if (multiSites.length > 1) {
                _setRadarStatus(`Loading multi-site ${product} timeline...`);
                const siteResults = await Promise.allSettled(multiSites.map(async (siteId) => {
                    const params = new URLSearchParams({ site: siteId, product, hours: String(maxHours) });
                    const resp = await fetch(apiUrl(`/api/radar/live/frames?${params.toString()}`), {
                        cache: 'no-store',
                    });
                    if (!resp.ok) return { siteId, frames: [] };
                    const data = await resp.json();
                    const frames = _normalizeRadarScrubFrames(data.frames, siteId, product);
                    return { siteId, frames };
                }));

                if (loadSeq !== _radarScrubLoadSeq || !_radarScrubMode || !_isTypeEnabled('radar')) return;

                const framesBySite = new Map();
                siteResults.forEach((result) => {
                    if (result.status !== 'fulfilled') return;
                    const siteId = String(result.value?.siteId || '').toUpperCase();
                    const frames = Array.isArray(result.value?.frames) ? result.value.frames : [];
                    if (!siteId || !frames.length) return;
                    framesBySite.set(siteId, frames);
                });

                const timeline = _buildRadarTimeTimelineMs(framesBySite);
                if (!timeline.length || !framesBySite.size) {
                    _setArchiveProgress(false);
                    _setArchiveScrubber(true);
                    _setScrubberControlsEnabled(false);
                    _updateRtmaScrubberUi();
                    _setRtmaScrubberStatus('No radar timeline frames found for selected sites/product/window.');
                    _setRadarStatus(`No multi-site radar animation frames for ${product}.`);
                    setStatus(`No multi-site radar frames found (${maxHours}h window).`);
                    return;
                }

                _radarScrubIsTimeMode = true;
                _radarScrubFramesBySite = framesBySite;
                _radarScrubTimelineMs = timeline;

                _setArchiveProgress(false);
                _setScrubberControlsEnabled(true);
                _setRtmaScrubberStatus(`${timeline.length} timeline ticks loaded (${framesBySite.size} sites, ${product}, ${maxHours}h window).`);
                _setRadarStatus(`Multi-site ${product} radar timeline loaded.`);
                _showRadarAutoUpdateRow(true);
                _updateRadarNextUpdateCountdown();
                await _renderRadarScrubFrame(0);
                return;
            }

            const params = new URLSearchParams({ site, product, hours: String(maxHours) });
            const resp = await fetch(apiUrl(`/api/radar/live/frames?${params.toString()}`), {
                cache: 'no-store',
            });
            if (loadSeq !== _radarScrubLoadSeq || !_radarScrubMode || !_isTypeEnabled('radar')) return;

            if (!resp.ok) {
                const err = await resp.json().catch(() => ({ detail: resp.statusText }));
                throw new Error(err.detail || resp.statusText);
            }

            const data = await resp.json();
            _radarScrubFrames = _normalizeRadarScrubFrames(data.frames, site, product);

            if (loadSeq !== _radarScrubLoadSeq || !_radarScrubMode || !_isTypeEnabled('radar')) return;
            if (!_radarScrubFrames.length) {
                _setArchiveProgress(false);
                _setArchiveScrubber(true);
                _setScrubberControlsEnabled(false);
                _updateRtmaScrubberUi();
                _setRtmaScrubberStatus('No radar frames found for selected site/product/window.');
                _setRadarStatus(`No radar animation frames for ${site} ${product}.`);
                setStatus(`No radar frames found for ${site} ${product} (${maxHours}h window).`);
                _startRadarScrubWarmPoll(site, product);
                return;
            }

            _setArchiveProgress(false);
            _setScrubberControlsEnabled(true);
            _setRtmaScrubberStatus(`${_radarScrubFrames.length} radar frames loaded (${site} ${product}, ${maxHours}h window).`);
            _setRadarStatus(`${site} ${product} radar animation loaded.`);
            _showRadarAutoUpdateRow(true);
            _updateRadarNextUpdateCountdown();
            // Start Animate at the first frame so scrubber position and image align.
            await _renderRadarScrubFrame(0);
            _startRadarScrubWarmPoll(site, product);
        } catch (err) {
            if (loadSeq !== _radarScrubLoadSeq || !_radarScrubMode || !_isTypeEnabled('radar')) return;
            _setArchiveProgress(false);
            _setScrubberControlsEnabled(false);
            _setRtmaScrubberStatus(`Error: ${err.message}`);
            _setRadarStatus(`Unable to load ${site} ${product} radar animation.`);
            setStatus(`Radar scrubber load error: ${err.message}`);
        }
    }

    // ── Radar auto-refresh ───────────────────────────────────────────────────
    let _radarAutoRefreshTimer = null;
    let _radarAutoRefreshCountdownTimer = null;
    let _radarAutoRefreshNextAtMs = 0;
    let _radarAutoUpdateStatusTimer = null;
    let _radarAnimateNewFrameTimer = null;

    function _isRadarAutoUpdateEnabled() {
        return !!byId('wx-radar-auto-update')?.checked;
    }

    function _setRadarAutoUpdateStatus(msg, clearAfterMs = 0) {
        const el = byId('wx-radar-auto-update-status');
        if (!el) return;
        el.textContent = msg ? `— ${msg}` : '';
        if (_radarAutoUpdateStatusTimer) { clearTimeout(_radarAutoUpdateStatusTimer); _radarAutoUpdateStatusTimer = null; }
        if (clearAfterMs > 0) {
            _radarAutoUpdateStatusTimer = setTimeout(() => {
                const still = byId('wx-radar-auto-update-status');
                if (still) still.textContent = '';
            }, clearAfterMs);
        }
    }

    function _showRadarAutoUpdateRow(visible) {
        const row = byId('wx-radar-auto-update-row');
        if (row) row.style.display = visible ? '' : 'none';
    }

    function _setRadarNextUpdateStatus(text, visible = true) {
        const el = byId('wx-radar-next-update-status');
        if (!el) return;
        if (!visible) {
            el.style.display = 'none';
            el.textContent = '';
            return;
        }
        el.style.display = 'block';
        el.textContent = text;
    }

    function _formatCountdownMs(ms) {
        const totalSec = Math.max(0, Math.ceil(ms / 1000));
        const min = Math.floor(totalSec / 60);
        const sec = totalSec % 60;
        return `${String(min).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
    }

    function _updateRadarNextUpdateCountdown() {
        const shouldShow = _isTypeEnabled('radar')
            && !_archiveMode
            && _radarScrubMode
            && _isRadarAutoUpdateEnabled()
            && !!_radarAutoRefreshTimer;
        if (!shouldShow) {
            _setRadarNextUpdateStatus('', false);
            return;
        }
        if (document.hidden) {
            _setRadarNextUpdateStatus('Time Until Next Update: Paused (tab hidden)', true);
            return;
        }
        const remainingMs = Math.max(0, _radarAutoRefreshNextAtMs - Date.now());
        _setRadarNextUpdateStatus(`Next Check for New Scans: ${_formatCountdownMs(remainingMs)}`, true);
    }

    function _flashAnimateNewFrame() {
        const btn = byId('weather-rtma-load-scrubber');
        if (!btn) return;
        if (btn.classList.contains('radar-animate-filling')) return;

        if (_radarAnimateNewFrameTimer) {
            clearTimeout(_radarAnimateNewFrameTimer);
            _radarAnimateNewFrameTimer = null;
        }

        btn.classList.add('radar-animate-newframe');
        btn.textContent = 'New Frame Added';
        btn.title = 'New radar frame received';

        _radarAnimateNewFrameTimer = setTimeout(() => {
            const stillBtn = byId('weather-rtma-load-scrubber');
            if (!stillBtn) return;
            stillBtn.classList.remove('radar-animate-newframe');
            stillBtn.textContent = 'Animate';
            stillBtn.title = '';
            _radarAnimateNewFrameTimer = null;
        }, 3000);
    }

    async function _tryAppendNewRadarFrames() {
        if (!_radarScrubMode || !_isTypeEnabled('radar')) return 0;
        if (!_isRadarAutoUpdateEnabled()) return 0;
        const product = _activeRadarProduct();
        const site = _activeRadarSite();
        if (!_radarScrubIsTimeMode && !site) return 0;
        const liveContextKey = _radarCurrentScrubContextKey(product);
        if (_radarScrubContextKey && liveContextKey && _radarScrubContextKey !== liveContextKey) {
            _exitRadarScrubMode(false);
            _setRtmaScrubberStatus('Site selection changed. Press Animate again to rebuild timeline.');
            _showRadarWorkflowToast('Selection changed. Press Animate again.');
            setStatus('Radar selection changed. Press Animate again to rebuild animation timeline.');
            return 0;
        }

        try {
            const rtmaSlider = document.querySelector('#rtma-animate-slider');
            const maxHours = Math.max(1, rtmaSlider ? Number(rtmaSlider.value) : 3);

            if (_radarScrubIsTimeMode) {
                const sites = _radarScrubFramesBySite.size
                    ? [..._radarScrubFramesBySite.keys()]
                    : [..._radarMultiSites];
                if (sites.length < 2) return 0;

                const existingKeys = new Set();
                _radarScrubFramesBySite.forEach((frames, siteId) => {
                    frames.forEach((frame) => existingKeys.add(`${siteId}|${frame.frame_key || ''}|${frame.timestamp || ''}`));
                });

                const siteResults = await Promise.allSettled(sites.map(async (siteId) => {
                    const params = new URLSearchParams({ site: siteId, product, hours: String(maxHours) });
                    const resp = await fetch(apiUrl(`/api/radar/live/frames?${params.toString()}`), { cache: 'no-store' });
                    if (!resp.ok) return { siteId, frames: [] };
                    const data = await resp.json();
                    return { siteId, frames: _normalizeRadarScrubFrames(data.frames, siteId, product) };
                }));
                if (!_radarScrubMode || !_isTypeEnabled('radar') || !_radarScrubIsTimeMode) return 0;

                let appendedCount = 0;
                const nextFramesBySite = new Map();
                siteResults.forEach((result) => {
                    if (result.status !== 'fulfilled') return;
                    const siteId = String(result.value?.siteId || '').toUpperCase();
                    const frames = Array.isArray(result.value?.frames) ? result.value.frames : [];
                    if (!siteId || !frames.length) return;
                    nextFramesBySite.set(siteId, frames);
                    frames.forEach((frame) => {
                        const key = `${siteId}|${frame.frame_key || ''}|${frame.timestamp || ''}`;
                        if (!existingKeys.has(key)) appendedCount += 1;
                    });
                });
                if (!nextFramesBySite.size) return 0;

                const oldTickMs = _radarScrubTimelineMs[_radarScrubFrameIndex] || null;
                const nextTimeline = _buildRadarTimeTimelineMs(nextFramesBySite);
                if (!nextTimeline.length) return 0;

                _radarScrubFramesBySite = nextFramesBySite;
                _radarScrubTimelineMs = nextTimeline;
                if (Number.isFinite(oldTickMs)) {
                    let nextIdx = 0;
                    for (let i = 0; i < nextTimeline.length; i += 1) {
                        if (nextTimeline[i] <= oldTickMs) nextIdx = i;
                        else break;
                    }
                    _radarScrubFrameIndex = Math.max(0, Math.min(nextIdx, nextTimeline.length - 1));
                } else {
                    _radarScrubFrameIndex = 0;
                }

                if (!appendedCount) return 0;
                _updateRtmaScrubberUi();
                _setScrubberControlsEnabled(true);
                _setRadarAutoUpdateStatus(`+${appendedCount} new`, 4000);
                _flashAnimateNewFrame();
                _setRtmaScrubberStatus(`${_radarScrubFrameIndex + 1} / ${_radarScrubTimelineMs.length} ticks.`);
                return appendedCount;
            }

            const params = new URLSearchParams({ site, product, hours: String(maxHours) });
            const resp = await fetch(apiUrl(`/api/radar/live/frames?${params.toString()}`), { cache: 'no-store' });
            if (!resp.ok) return 0;
            const data = await resp.json();
            if (!_radarScrubMode || !_isTypeEnabled('radar')) return 0;

            const newFrames = _normalizeRadarScrubFrames(data.frames, site, product);

            if (!newFrames.length) return 0;

            const existingKeys = new Set(_radarScrubFrames.map((f) => f.frame_key));
            const appended = newFrames.filter((f) => !existingKeys.has(f.frame_key));
            if (!appended.length) return 0;

            if (!_radarScrubFrames.length) {
                _radarScrubFrames = appended;
                _radarScrubFrameIndex = 0;
                _updateRtmaScrubberUi();
                _setScrubberControlsEnabled(true);
                _setRadarAutoUpdateStatus(`+${appended.length} new`, 4000);
                _flashAnimateNewFrame();
                _setRtmaScrubberStatus(`${_radarScrubFrameIndex + 1} / ${_radarScrubFrames.length} frames.`);
                await _renderRadarScrubFrame(0);
                return appended.length;
            }

            // Append new frames at the tail, drop the same count from the head.
            const combined = [..._radarScrubFrames, ...appended];
            const dropped = Math.min(appended.length, _radarScrubFrames.length);
            const trimmed = combined.slice(dropped);

            // Keep scrub index stable — shift back by number of dropped frames.
            _radarScrubFrameIndex = Math.max(0, _radarScrubFrameIndex - dropped);
            _radarScrubFrames = trimmed;

            _updateRtmaScrubberUi();
            _setScrubberControlsEnabled(true);
            _setRadarAutoUpdateStatus(`+${appended.length} new`, 4000);
            _flashAnimateNewFrame();
            _setRtmaScrubberStatus(`${_radarScrubFrameIndex + 1} / ${_radarScrubFrames.length} frames.`);
            return appended.length;
        } catch (_) {
            return 0;
        }
    }

    async function _radarAutoRefreshTick() {
        if (!_isTypeEnabled('radar')) return;
        if (_archiveMode) return;
        if (document.hidden) return;
        if (!_isRadarAutoUpdateEnabled()) return;

        try {
            if (_radarScrubMode) {
                await _tryAppendNewRadarFrames();
                return;
            }

            // Live single-frame view.
            const site = _activeRadarSite();
            if (_radarMultiSites.size > 1) {
                _loadAllMultiSiteOverlays();
            } else if (site) {
                loadRadarLiveLatest();
            } else {
                // National Composite — refresh MRMS overlay via cache-bust.
                if (_mrmsRadarOverlayState) {
                    _mrmsRadarOverlayRefresh();
                    _setRadarAutoUpdateStatus('updated', 4000);
                }
            }
        } finally {
            _radarAutoRefreshNextAtMs = Date.now() + RADAR_AUTO_REFRESH_MS;
            _updateRadarNextUpdateCountdown();
        }
    }

    function _restartRadarAutoRefreshInterval() {
        if (_radarAutoRefreshTimer) { clearInterval(_radarAutoRefreshTimer); _radarAutoRefreshTimer = null; }
        _radarAutoRefreshTimer = setInterval(() => { _radarAutoRefreshTick(); }, RADAR_AUTO_REFRESH_MS);
        _radarAutoRefreshNextAtMs = Date.now() + RADAR_AUTO_REFRESH_MS;
    }

    function _startRadarAutoRefresh() {
        if (_radarAutoRefreshTimer) return;
        _radarAutoRefreshTimer = setInterval(() => { _radarAutoRefreshTick(); }, RADAR_AUTO_REFRESH_MS);
        _radarAutoRefreshNextAtMs = Date.now() + RADAR_AUTO_REFRESH_MS;
        if (!_radarAutoRefreshCountdownTimer) {
            _radarAutoRefreshCountdownTimer = setInterval(() => {
                _updateRadarNextUpdateCountdown();
            }, 1000);
        }
        _updateRadarNextUpdateCountdown();
    }

    function _stopRadarAutoRefresh() {
        if (_radarAutoRefreshTimer) { clearInterval(_radarAutoRefreshTimer); _radarAutoRefreshTimer = null; }
        if (_radarAutoRefreshCountdownTimer) { clearInterval(_radarAutoRefreshCountdownTimer); _radarAutoRefreshCountdownTimer = null; }
        _radarAutoRefreshNextAtMs = 0;
        _setRadarNextUpdateStatus('', false);
    }

    function _activeSatelliteSatId() {
        return String(byId('weather-satellite-sat-id')?.value || 'goes19').trim() || 'goes19';
    }

    function _activeSatelliteSector() {
        return String(byId('weather-satellite-sector')?.value || 'CONUS').trim() || 'CONUS';
    }

    function _activeSatelliteChannel() {
        return String(byId('weather-satellite-channel')?.value || 'Channel13').trim() || 'Channel13';
    }

    async function _fetchSatelliteLegend(channel) {
        const key = String(channel || '').trim() || 'Channel13';
        if (_satelliteLegendCache.has(key)) return _satelliteLegendCache.get(key);

        const resp = await fetch(apiUrl(`/api/satellite-v2/legend?channel=${encodeURIComponent(key)}`), { cache: 'no-store' });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok || data.status !== 'success') {
            throw new Error(data.detail || data.message || resp.statusText || 'Satellite legend request failed');
        }
        _satelliteLegendCache.set(key, data);
        return data;
    }

    async function _updateSatelliteLegend() {
        if (!_isTypeEnabled('satellite')) return;
        const channel = _activeSatelliteChannel();
        try {
            const legend = await _fetchSatelliteLegend(channel);
            if (!_isTypeEnabled('satellite') || _activeSatelliteChannel() !== channel) return;
            if (!legend?.available || !Array.isArray(legend.anchors) || !legend.anchors.length) {
                setLegend(null);
                return;
            }

            const title = legend.title ? `Satellite: ${legend.title}` : 'Satellite';
            const units = legend.units ? `Brightness Temperature (${legend.units})` : 'Brightness Temperature';
            setLegend(renderContinuousLegend(title, units, legend.anchors, legend.ticks));
        } catch (err) {
            console.warn('[satellite-v2] Legend unavailable:', err?.message || err);
            if (_isTypeEnabled('satellite') && _activeSatelliteChannel() === channel) setLegend(null);
        }
    }

    function _activeSatelliteLookbackHours() {
        const slider = byId('weather-satellite-lookback-slider');
        const hours = Number(slider?.value || _recommendedSatelliteLookbackHours());
        if (!Number.isFinite(hours) || hours <= 0) return _recommendedSatelliteLookbackHours();
        return Math.max(1, Math.min(SATELLITE_LOOKBACK_HOURS_MAX, Math.round(hours)));
    }

    function _recommendedSatelliteLookbackHours() {
        const sector = _activeSatelliteSector().toUpperCase();
        if (sector === 'MESO1' || sector === 'MESO2') {
            return 1;
        }
        return 1; // CONUS: 1 hour default
    }

    function _setSatelliteLookbackHours(hours) {
        const slider = byId('weather-satellite-lookback-slider');
        const displayEl = byId('weather-satellite-lookback-value');
        const safeHours = Math.max(1, Math.min(SATELLITE_LOOKBACK_HOURS_MAX, Math.round(Number(hours) || 1)));
        if (slider) slider.value = String(safeHours);
        if (displayEl) displayEl.textContent = `${safeHours}h`;
    }

    function _satelliteMaxFramesForRequest(hours) {
        const sector = _activeSatelliteSector().toUpperCase();
        const safeHours = Math.max(1, Math.min(SATELLITE_LOOKBACK_HOURS_MAX, Math.round(Number(hours) || 1)));
        if (sector === 'MESO1' || sector === 'MESO2') {
            return Math.min(SATELLITE_FRAME_REQUEST_MAX, safeHours * 60);
        }
        if (sector === 'FULLDISK') {
            return Math.min(SATELLITE_FRAME_REQUEST_MAX, safeHours * 6);
        }
        return Math.min(SATELLITE_FRAME_REQUEST_MAX, safeHours * 12);
    }

    function _currentSatelliteFrameRequestWindow() {
        const hours = _activeSatelliteLookbackHours();
        return {
            hours,
            maxFrames: _satelliteMaxFramesForRequest(hours),
        };
    }

    function _satelliteCurrentFrameRequestWindows() {
        const activeHours = _activeSatelliteLookbackHours();
        const candidates = [activeHours, 3, 6, SATELLITE_LOOKBACK_HOURS_MAX];
        const seen = new Set();
        return candidates
            .map((hours) => Math.max(1, Math.min(SATELLITE_LOOKBACK_HOURS_MAX, Math.round(Number(hours) || 1))))
            .filter((hours) => {
                if (seen.has(hours)) return false;
                seen.add(hours);
                return true;
            })
            .map((hours) => ({
                hours,
                maxFrames: _satelliteMaxFramesForRequest(hours),
            }));
    }

    function _activeSatelliteWarmZoomMax() {
        const sector = _activeSatelliteSector().toUpperCase();
        if (sector === 'FULLDISK') return 6;
        return (sector === 'MESO1' || sector === 'MESO2') ? 10 : 8;
    }

    function _setSatelliteStatus(message) {
        const el = byId('weather-satellite-status');
        if (el) el.textContent = message || '';
    }

    function _setSatelliteAnimateControlsVisible(visible) {
        const wrap = byId('weather-satellite-lookback-wrap');
        if (wrap) wrap.style.display = visible ? '' : 'none';
        _syncSatelliteAnimateAutoRefresh();
    }

    function _setSatelliteModeActive(mode) {
        byId('weather-satellite-current')?.classList.toggle('active', mode === 'current');
        byId('weather-satellite-animate')?.classList.toggle('active', mode === 'animate');
        _setSatelliteAnimateControlsVisible(mode === 'animate');
        if (mode === 'current') {
            _setArchiveScrubber(false);
            _setScrubberControlsEnabled(false);
        }
    }

    function _setSatelliteAnimateButtonFilling(filling, loadedCount = null, targetCount = null) {
        const btn = byId('weather-satellite-animate');
        if (!btn) return;
        if (filling) {
            if (_satelliteAnimateNewFrameTimer) {
                clearTimeout(_satelliteAnimateNewFrameTimer);
                _satelliteAnimateNewFrameTimer = null;
            }
            btn.classList.remove('radar-animate-newframe');
            const hasProgress = Number.isFinite(loadedCount) && Number.isFinite(targetCount) && targetCount > 0;
            const clampedLoaded = hasProgress ? Math.max(0, Math.min(Number(loadedCount), Number(targetCount))) : 0;
            btn.classList.add('radar-animate-filling');
            btn.textContent = hasProgress
                ? `Loading Frames... (${clampedLoaded}/${targetCount})`
                : 'Loading Frames...';
            btn.title = 'Satellite frames are rendering in background.';
        } else {
            if (_satelliteAnimateNewFrameTimer) {
                clearTimeout(_satelliteAnimateNewFrameTimer);
                _satelliteAnimateNewFrameTimer = null;
            }
            btn.classList.remove('radar-animate-newframe');
            btn.classList.remove('radar-animate-filling');
            btn.textContent = 'Animate';
            btn.title = '';
        }
    }

    function _flashSatelliteAnimateNewFrame(addedCount = 1) {
        const label = Number(addedCount) === 1 ? 'New Frame Added' : 'New Frames Added';
        const autoBtn = byId('weather-satellite-auto-refresh');
        if (autoBtn && _satelliteAnimateAutoRefreshEnabled) {
            _satelliteAutoRefreshFlashActive = true;
            autoBtn.classList.add('radar-animate-newframe');
            autoBtn.textContent = label;
            autoBtn.title = label;
        }

        const btn = byId('weather-satellite-animate');
        if (btn) {
            btn.classList.remove('radar-animate-filling');
            btn.classList.add('radar-animate-newframe');
            btn.textContent = label;
        }

        if (_satelliteAnimateNewFrameTimer) clearTimeout(_satelliteAnimateNewFrameTimer);
        _satelliteAnimateNewFrameTimer = setTimeout(() => {
            const stillAutoBtn = byId('weather-satellite-auto-refresh');
            if (stillAutoBtn) {
                _satelliteAutoRefreshFlashActive = false;
                stillAutoBtn.classList.remove('radar-animate-newframe');
            }

            const stillBtn = byId('weather-satellite-animate');
            if (stillBtn) {
                stillBtn.classList.remove('radar-animate-newframe');
                stillBtn.textContent = 'Animate';
            }
            _satelliteAnimateNewFrameTimer = null;
            _syncSatelliteAnimateAutoRefreshUi();
        }, 1400);
    }

    function _syncSatelliteAnimateAutoRefreshUi() {
        const btn = byId('weather-satellite-auto-refresh');
        if (!btn) return;
        const visible = _satelliteScrubMode && _isTypeEnabled('satellite');
        btn.classList.toggle('is-visible', visible);
        btn.classList.toggle('is-active', _satelliteAnimateAutoRefreshEnabled);
        btn.disabled = !visible;
        btn.setAttribute('aria-pressed', _satelliteAnimateAutoRefreshEnabled ? 'true' : 'false');
        if (!_satelliteAutoRefreshFlashActive) {
            btn.textContent = _satelliteAnimateAutoRefreshEnabled ? 'Auto On' : 'Auto';
            btn.title = _satelliteAnimateAutoRefreshEnabled
                ? 'Auto refresh is on for satellite animation frames.'
                : 'Auto refresh satellite animation frames.';
        }
    }

    function _stopSatelliteAnimateAutoRefresh() {
        if (_satelliteAnimateAutoRefreshTimer) {
            clearInterval(_satelliteAnimateAutoRefreshTimer);
            _satelliteAnimateAutoRefreshTimer = null;
        }
    }

    function _startSatelliteAnimateAutoRefresh() {
        if (_satelliteAnimateAutoRefreshTimer) return;
        _satelliteAnimateAutoRefreshTimer = setInterval(() => {
            if (document.hidden) return;
            if (!_satelliteAnimateAutoRefreshEnabled || !_satelliteScrubMode || !_isTypeEnabled('satellite')) return;
            void _refreshSatelliteAnimationFrames({ auto: true, silent: true });
        }, SATELLITE_ANIMATE_AUTO_REFRESH_MS);
    }

    function _syncSatelliteAnimateAutoRefresh() {
        const shouldRun = _satelliteAnimateAutoRefreshEnabled
            && _satelliteScrubMode
            && _isTypeEnabled('satellite');
        if (shouldRun) {
            _startSatelliteAnimateAutoRefresh();
        } else {
            _stopSatelliteAnimateAutoRefresh();
        }
        _syncSatelliteAnimateAutoRefreshUi();
    }

    function _setSatelliteAnimateAutoRefreshEnabled(enabled) {
        _satelliteAnimateAutoRefreshEnabled = !!enabled;
        _syncSatelliteAnimateAutoRefresh();
    }

    async function _refreshSatelliteAnimationFrames(options = {}) {
        if (!_satelliteScrubMode || !_isTypeEnabled('satellite')) return false;
        if (_satelliteAnimateAutoRefreshInFlight) return false;
        if (_satelliteLookbackReloadTimer || _satelliteManualScrubTimer) return false;

        const loadSeq = _satelliteScrubLoadSeq;
        const previousFrameKey = _satelliteFrames[_satelliteFrameIndex]?.frame_key || '';
        const previousKeys = new Set(_satelliteFrames.map((frame) => String(frame?.frame_key || '')).filter(Boolean));
        const requestWindow = _currentSatelliteFrameRequestWindow();
        const controller = new AbortController();
        _satelliteAnimateAutoRefreshInFlight = true;

        try {
            if (!options.silent) {
                _setRtmaScrubberStatus(`Checking for new satellite frames (${requestWindow.hours}h window)...`);
            }
            const frameSet = await _fetchSatelliteFrameSet({
                hours: requestWindow.hours,
                maxFrames: requestWindow.maxFrames,
                signal: controller.signal,
                refresh: options.auto === true,
                requireTiles: false,
                minFrames: 0,
            });
            if (!_satelliteScrubMode || loadSeq !== _satelliteScrubLoadSeq || !_isTypeEnabled('satellite')) return false;
            _setSatelliteApiMode(frameSet.mode, frameSet.data);

            const nextFrames = frameSet.frames;
            if (!nextFrames.length) return false;

            const addedCount = nextFrames.filter((frame) => {
                const key = String(frame?.frame_key || '');
                return key && !previousKeys.has(key);
            }).length;

            _satelliteFrames = nextFrames;
            _satelliteFrameIndex = addedCount > 0
                ? _satelliteFrameIndexForReload(_satelliteFrames)
                : _satelliteFrameIndexForReload(_satelliteFrames, previousFrameKey);
            _primeSatelliteAnimationLayers(_satelliteFrameIndex);
            _scheduleSatelliteTilePrefetch();
            _updateSatelliteScrubberUi();
            _updateRtmaScrubberUi();

            const activeFrameKey = _satelliteFrames[_satelliteFrameIndex]?.frame_key || '';
            if (!previousFrameKey || activeFrameKey !== previousFrameKey || !satelliteOverlay) {
                await _setSatelliteFrame(_satelliteFrameIndex, { waitForTiles: false });
            }

            if (addedCount > 0) {
                _flashSatelliteAnimateNewFrame(addedCount);
                _setRtmaScrubberStatus(`${addedCount} new satellite frame${addedCount === 1 ? '' : 's'} added to the loop.`);
                _setSatelliteStatus('Satellite animation auto-refresh added new frames.');
                return true;
            }

            if (!options.silent) {
                _setRtmaScrubberStatus(`${_satelliteFrames.length} satellite frames current (${requestWindow.hours}h window).`);
            }
            return false;
        } catch (err) {
            if (err.name === 'AbortError') return false;
            if (!_satelliteScrubMode || loadSeq !== _satelliteScrubLoadSeq) return false;
            if (!options.silent) {
                _setRtmaScrubberStatus(`Satellite auto-refresh error: ${err.message}`);
            }
            console.warn('[satellite] Animation auto-refresh failed:', err.message);
            return false;
        } finally {
            _satelliteAnimateAutoRefreshInFlight = false;
            _syncSatelliteAnimateAutoRefreshUi();
        }
    }

    function _satelliteFrameTileCount(frame) {
        const counts = frame?.tile_counts || {};
        return Object.values(counts).reduce((sum, value) => {
            const parsed = Number(value);
            return sum + (Number.isFinite(parsed) ? parsed : 0);
        }, 0);
    }

    function _satelliteExpectedReadyZoom(frame = null) {
        const configuredZoom = Number(frame?.max_native_zoom ?? _satelliteCatalog?.max_native_zoom);
        if (Number.isFinite(configuredZoom) && configuredZoom > 0) return Math.round(configuredZoom);
        return _activeSatelliteWarmZoomMax();
    }

    function _satelliteFrameReadyTileCount(frame) {
        const counts = frame?.tile_counts || {};
        const readyZoom = _satelliteExpectedReadyZoom(frame);
        const parsed = Number(counts[String(readyZoom)]);
        return Number.isFinite(parsed) ? parsed : 0;
    }

    function _satelliteFrameHasTiles(frame) {
        return _satelliteFrameReadyTileCount(frame) > 0;
    }

    function _satelliteFrameTimestampMs(frame) {
        return _resolveDataTimestampMs(frame?.timestamp_utc || frame?.frame_key || null);
    }

    function _satelliteLatestFrame(frames) {
        if (!Array.isArray(frames) || !frames.length) return null;
        return frames.reduce((latest, frame) => {
            if (!latest) return frame;
            const frameMs = _satelliteFrameTimestampMs(frame);
            const latestMs = _satelliteFrameTimestampMs(latest);
            if (!Number.isFinite(latestMs)) return frame;
            if (!Number.isFinite(frameMs)) return latest;
            return frameMs >= latestMs ? frame : latest;
        }, null);
    }

    function _satelliteLatestReadyFrame(frames) {
        return _satelliteLatestFrame((Array.isArray(frames) ? frames : []).filter(_satelliteFrameHasTiles));
    }

    function _satelliteFrameAgeLabel(ms) {
        const minutes = Math.max(0, Math.round(Number(ms || 0) / 60000));
        if (minutes < 60) return `${minutes} min`;
        const hours = Math.floor(minutes / 60);
        const rem = minutes % 60;
        return rem ? `${hours}h ${rem}m` : `${hours}h`;
    }

    function _satelliteFrameIndexForReload(frames, preferredFrameKey = '') {
        if (!Array.isArray(frames) || !frames.length) return 0;
        const preferredKey = String(preferredFrameKey || '');
        if (preferredKey) {
            const preferredIndex = frames.findIndex((frame) => String(frame?.frame_key || '') === preferredKey);
            if (preferredIndex >= 0) return preferredIndex;
        }
        return frames.length - 1;
    }

    function _satelliteFrameMaxNativeZoom(frame) {
        const configuredZoom = Number(frame?.max_native_zoom ?? _satelliteCatalog?.max_native_zoom);
        if (Number.isFinite(configuredZoom)) return configuredZoom;
        const zooms = Array.isArray(frame?.available_zooms)
            ? frame.available_zooms.map(Number).filter(Number.isFinite)
            : [];
        if (zooms.length) return Math.max(...zooms);
        const counts = frame?.tile_counts || {};
        const countZooms = Object.entries(counts)
            .filter(([, count]) => Number(count) > 0)
            .map(([zoom]) => Number(zoom))
            .filter(Number.isFinite);
        return countZooms.length ? Math.max(...countZooms) : null;
    }

    function _satelliteMinNativeZoomForSector(sector) {
        const s = String(sector || '').toUpperCase();
        if (s === 'FULLDISK') return 1;
        if (s === 'MESO1' || s === 'MESO2') return 7;
        return 5; // CONUS
    }

    function _satelliteActiveFrameByKey(frameKey) {
        return _satelliteFrames.find((frame) => String(frame?.frame_key || '') === String(frameKey || '')) || null;
    }

    function _setSatelliteApiMode(mode, catalog = null) {
        const nextMode = 'v2';
        if (_satelliteApiMode !== nextMode) {
            _clearSatelliteLayerPool();
        }
        _satelliteApiMode = nextMode;
        _satelliteCatalog = catalog;
    }

    function _satelliteLayerPoolKey(frameKey) {
        return [
            _satelliteApiMode,
            _activeSatelliteSatId(),
            _activeSatelliteSector(),
            _activeSatelliteChannel(),
            String(frameKey || ''),
        ].join('|');
    }

    function _satelliteTileTemplate(frameKey) {
        const key = String(frameKey || '');
        const params = new URLSearchParams({
            sat_id: _activeSatelliteSatId(),
            sector: _activeSatelliteSector(),
            channel: _activeSatelliteChannel(),
            frame_key: key,
            render_live: '1',
            rv: String(_satelliteCatalog?.render_version || 'products'),
            t: String(_satelliteTileRefreshToken || 0),
        });
        return apiUrl(`/api/satellite-v2/tile/{z}/{x}/{y}?${params.toString()}`);
    }

    function _satelliteTileUrlForCoords(frameKey, zoomLevel, tileX, tileY) {
        return _satelliteTileTemplate(frameKey)
            .replace('{z}', String(zoomLevel))
            .replace('{x}', String(tileX))
            .replace('{y}', String(tileY));
    }

    function _satelliteEffectiveTileZoom(frame = null) {
        const maxNativeZoom = Number(_satelliteFrameMaxNativeZoom(frame));
        const minNativeZoom = Number(_satelliteMinNativeZoomForSector(_activeSatelliteSector()));
        let zoomLevel = Math.round(map.getZoom());
        if (Number.isFinite(maxNativeZoom)) zoomLevel = Math.min(zoomLevel, maxNativeZoom);
        if (Number.isFinite(minNativeZoom)) zoomLevel = Math.max(zoomLevel, minNativeZoom);
        return Math.max(0, zoomLevel);
    }

    function _satelliteViewportTileCoords(zoomLevel) {
        if (!Number.isFinite(zoomLevel) || !map.getBounds) return [];
        const bounds = map.getBounds();
        const northWest = map.project(bounds.getNorthWest(), zoomLevel);
        const southEast = map.project(bounds.getSouthEast(), zoomLevel);
        const tileSize = 256;
        const maxTileIndex = Math.max(0, (2 ** Math.round(zoomLevel)) - 1);
        const minTileX = Math.max(0, Math.floor(Math.min(northWest.x, southEast.x) / tileSize) - 1);
        const maxTileX = Math.min(maxTileIndex, Math.floor(Math.max(northWest.x, southEast.x) / tileSize) + 1);
        const minTileY = Math.max(0, Math.floor(Math.min(northWest.y, southEast.y) / tileSize) - 1);
        const maxTileY = Math.min(maxTileIndex, Math.floor(Math.max(northWest.y, southEast.y) / tileSize) + 1);
        const centerPoint = map.project(map.getCenter(), zoomLevel);
        const centerTileX = centerPoint.x / tileSize;
        const centerTileY = centerPoint.y / tileSize;
        const coords = [];
        for (let tileY = minTileY; tileY <= maxTileY; tileY += 1) {
            for (let tileX = minTileX; tileX <= maxTileX; tileX += 1) {
                coords.push({ tileX, tileY });
            }
        }
        coords.sort((left, right) => {
            const leftDistance = Math.abs(left.tileX - centerTileX) + Math.abs(left.tileY - centerTileY);
            const rightDistance = Math.abs(right.tileX - centerTileX) + Math.abs(right.tileY - centerTileY);
            return leftDistance - rightDistance;
        });
        return coords.slice(0, SATELLITE_PREFETCH_MAX_TILES_PER_FRAME);
    }

    function _satellitePrefetchFrameIndexes(activeIndex = _satelliteFrameIndex) {
        const frameCount = _satelliteFrames.length;
        const indexes = [];
        if (!_satelliteScrubMode || frameCount < 2) return indexes;
        const active = Math.max(0, Math.min(frameCount - 1, Number(activeIndex) || 0));
        const seen = new Set([active]);
        for (let offset = 1; offset <= SATELLITE_PREFETCH_AHEAD_FRAMES; offset += 1) {
            const frameIndex = (active + offset) % frameCount;
            if (!seen.has(frameIndex)) {
                seen.add(frameIndex);
                indexes.push(frameIndex);
            }
        }
        for (let offset = 1; offset <= SATELLITE_PREFETCH_BEHIND_FRAMES; offset += 1) {
            const frameIndex = (active - offset + frameCount) % frameCount;
            if (!seen.has(frameIndex)) {
                seen.add(frameIndex);
                indexes.push(frameIndex);
            }
        }
        return indexes;
    }

    function _currentSatellitePrefetchContextKey() {
        if (!_satelliteScrubMode || !_satelliteFrames.length || !_isTypeEnabled('satellite')) return '';
        const zoomLevel = Math.round(map.getZoom());
        const bounds = map.getBounds();
        const northWest = map.project(bounds.getNorthWest(), zoomLevel);
        const southEast = map.project(bounds.getSouthEast(), zoomLevel);
        const tileSize = 256;
        const minTileX = Math.floor(Math.min(northWest.x, southEast.x) / tileSize);
        const maxTileX = Math.floor(Math.max(northWest.x, southEast.x) / tileSize);
        const minTileY = Math.floor(Math.min(northWest.y, southEast.y) / tileSize);
        const maxTileY = Math.floor(Math.max(northWest.y, southEast.y) / tileSize);
        return [
            _satelliteApiMode,
            _activeSatelliteSatId(),
            _activeSatelliteSector(),
            _activeSatelliteChannel(),
            zoomLevel,
            minTileX,
            maxTileX,
            minTileY,
            maxTileY,
        ].join('|');
    }

    function _cancelSatelliteTilePrefetch() {
        _satellitePrefetchSeq += 1;
        if (_satellitePrefetchTimer) {
            clearTimeout(_satellitePrefetchTimer);
            _satellitePrefetchTimer = null;
        }
        if (_satellitePrefetchController) {
            try { _satellitePrefetchController.abort(); } catch (_) { /* ignore */ }
            _satellitePrefetchController = null;
        }
        _satellitePrefetchQueue = [];
        _satellitePrefetchActive = 0;
        _satellitePrefetchContextKey = '';
        _satellitePrefetchSeenUrls.clear();
    }

    function _enqueueSatelliteTilePrefetch(seq) {
        if (seq !== _satellitePrefetchSeq || !_satelliteScrubMode || !_satelliteFrames.length || !_isTypeEnabled('satellite')) return;
        const nowMs = Date.now();
        const queuedUrls = new Set(_satellitePrefetchQueue.map((item) => item.url));
        const frameIndexes = _satellitePrefetchFrameIndexes(_satelliteFrameIndex);
        for (const frameIndex of frameIndexes) {
            const frame = _satelliteFrames[frameIndex];
            const frameKey = frame?.frame_key || '';
            if (!frameKey) continue;
            const zoomLevel = _satelliteEffectiveTileZoom(frame);
            const coords = _satelliteViewportTileCoords(zoomLevel);
            for (const coord of coords) {
                if (_satellitePrefetchQueue.length >= SATELLITE_PREFETCH_MAX_QUEUE_TILES) return;
                const url = _satelliteTileUrlForCoords(frameKey, zoomLevel, coord.tileX, coord.tileY);
                const lastSeenMs = Number(_satellitePrefetchSeenUrls.get(url));
                if (queuedUrls.has(url) || (Number.isFinite(lastSeenMs) && nowMs - lastSeenMs < SATELLITE_PREFETCH_RETRY_AFTER_MS)) continue;
                queuedUrls.add(url);
                _satellitePrefetchSeenUrls.set(url, nowMs);
                if (_satellitePrefetchSeenUrls.size > SATELLITE_PREFETCH_SEEN_LIMIT) {
                    const oldestUrl = _satellitePrefetchSeenUrls.keys().next().value;
                    if (oldestUrl) _satellitePrefetchSeenUrls.delete(oldestUrl);
                }
                _satellitePrefetchQueue.push({ url });
            }
        }
    }

    function _pumpSatelliteTilePrefetch(seq) {
        if (seq !== _satellitePrefetchSeq || !_satelliteScrubMode || !_isTypeEnabled('satellite')) return;
        if (typeof fetch !== 'function') return;
        if (!_satellitePrefetchController) {
            _satellitePrefetchController = new AbortController();
        }
        const signal = _satellitePrefetchController.signal;
        while (_satellitePrefetchActive < SATELLITE_PREFETCH_MAX_CONCURRENT && _satellitePrefetchQueue.length) {
            const item = _satellitePrefetchQueue.shift();
            _satellitePrefetchActive += 1;
            fetch(item.url, { cache: 'force-cache', signal })
                .then((response) => {
                    if (!response.ok) return null;
                    return response.blob();
                })
                .catch(() => { })
                .finally(() => {
                    if (seq !== _satellitePrefetchSeq) return;
                    _satellitePrefetchActive = Math.max(0, _satellitePrefetchActive - 1);
                    _pumpSatelliteTilePrefetch(seq);
                });
        }
    }

    function _scheduleSatelliteTilePrefetch(delayMs = SATELLITE_PREFETCH_DEBOUNCE_MS) {
        if (!_satelliteScrubMode || !_satelliteFrames.length || !_isTypeEnabled('satellite')) {
            _cancelSatelliteTilePrefetch();
            return;
        }
        const contextKey = _currentSatellitePrefetchContextKey();
        if (!contextKey) return;
        if (contextKey !== _satellitePrefetchContextKey) {
            _cancelSatelliteTilePrefetch();
            _satellitePrefetchContextKey = contextKey;
        }
        if (_satellitePrefetchTimer) clearTimeout(_satellitePrefetchTimer);
        const seq = _satellitePrefetchSeq;
        _satellitePrefetchTimer = setTimeout(() => {
            _satellitePrefetchTimer = null;
            _enqueueSatelliteTilePrefetch(seq);
            _pumpSatelliteTilePrefetch(seq);
        }, Math.max(0, Number(delayMs) || 0));
    }

    async function _fetchSatelliteFrameSet({ hours, maxFrames, signal, refresh = false, requireTiles = false, minFrames = 1 }) {
        const v2Params = new URLSearchParams({
            sat_id: _activeSatelliteSatId(),
            sector: _activeSatelliteSector(),
            channel: _activeSatelliteChannel(),
            hours: String(hours),
            max_frames: String(maxFrames),
            refresh: refresh ? 'true' : 'false',
        });
        const resp = await fetch(apiUrl(`/api/satellite-v2/catalog?${v2Params.toString()}`), { cache: 'no-store', signal });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok || (data.status !== 'success' && data.status !== 'stale')) {
            throw new Error(data.detail || data.message || resp.statusText || 'Satellite catalog request failed');
        }
        const frames = Array.isArray(data.frames)
            ? data.frames.filter((frame) => frame && frame.frame_key)
            : [];
        const playableFrames = requireTiles ? frames.filter(_satelliteFrameHasTiles) : frames;
        const requiredFrameCount = Math.max(0, Number.isFinite(Number(minFrames)) ? Number(minFrames) : 1);
        if (playableFrames.length < requiredFrameCount) {
            throw new Error('Satellite catalog does not have enough frames yet.');
        }
        return { mode: 'v2', data, frames: playableFrames };
    }

    function _updateSatelliteScrubberUi() {
        // Left sidebar scrubber removed - update bottom archive scrubber instead
        const slider = byId('scrubber-slider');
        const countEl = byId('scrubber-frame-count');
        const tsEl = byId('scrubber-timestamp');
        const n = _satelliteFrames.length;
        const frame = n ? _satelliteFrames[_satelliteFrameIndex] : null;
        if (slider) {
            slider.min = '0';
            slider.max = String(Math.max(0, n - 1));
            slider.value = String(Math.max(0, Math.min(_satelliteFrameIndex, Math.max(0, n - 1))));
            slider.disabled = n < 1;
        }
        if (countEl) {
            countEl.textContent = n ? `${_satelliteFrameIndex + 1}/${n}` : '0/0';
        }
        if (tsEl) {
            if (!frame?.timestamp_utc) {
                tsEl.textContent = '--';
            } else {
                try {
                    tsEl.textContent = new Date(frame.timestamp_utc).toLocaleString(undefined, {
                        month: 'short',
                        day: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit',
                        timeZoneName: 'short',
                    });
                } catch {
                    tsEl.textContent = frame.timestamp_utc;
                }
            }
        }
    }

    function _scheduleSatelliteScrubberReload() {
        if (!_satelliteScrubMode || !_isTypeEnabled('satellite')) return;
        if (_satelliteLookbackReloadTimer) clearTimeout(_satelliteLookbackReloadTimer);
        _satelliteScrubLoadSeq += 1;
        _satelliteScrubRenderSeq += 1;
        _satelliteBackgroundWarmSeq += 1;
        if (_satelliteScrubFetchController) {
            _satelliteScrubFetchController.abort();
            _satelliteScrubFetchController = null;
        }
        if (_satelliteManualScrubTimer) {
            clearTimeout(_satelliteManualScrubTimer);
            _satelliteManualScrubTimer = null;
        }
        _stopSatelliteScrubPlay();
        _cancelSatellitePendingSwap();
        _cancelSatelliteTilePrefetch();
        _setScrubberControlsEnabled(false);
        const requestWindow = _currentSatelliteFrameRequestWindow();
        _setRtmaScrubberStatus(`Updating satellite frames for ${requestWindow.hours}h window...`);
        _satelliteLookbackReloadTimer = setTimeout(() => {
            _satelliteLookbackReloadTimer = null;
            loadSatelliteScrubberFrames();
        }, SATELLITE_LOOKBACK_RELOAD_DEBOUNCE_MS);
    }

    function _scheduleSatelliteManualScrubFrame(index) {
        if (!_satelliteScrubMode || !_satelliteFrames.length || !_isTypeEnabled('satellite')) return;
        const target = Math.max(0, Math.min(_satelliteFrames.length - 1, Number(index) || 0));
        _stopSatelliteScrubPlay();
        if (_satelliteManualScrubTimer) clearTimeout(_satelliteManualScrubTimer);
        _setRtmaScrubberStatus(`Preparing frame ${target + 1} / ${_satelliteFrames.length}...`);
        _satelliteManualScrubTimer = setTimeout(async () => {
            _satelliteManualScrubTimer = null;
            await _setSatelliteFrame(target, { waitForTiles: false });
        }, SATELLITE_MANUAL_SCRUB_DEBOUNCE_MS);
    }

    function _satelliteLayerHasLoadedTilesForZoom(layer, zoomLevel) {
        if (!layer || !Number.isFinite(zoomLevel)) return false;
        const maxNativeZoom = Number(layer?.options?.maxNativeZoom);
        const minNativeZoom = Number(layer?.options?.minNativeZoom);
        let targetZoom = Math.round(zoomLevel);
        if (Number.isFinite(maxNativeZoom)) targetZoom = Math.min(targetZoom, maxNativeZoom);
        if (Number.isFinite(minNativeZoom)) targetZoom = Math.max(targetZoom, minNativeZoom);
        const tiles = layer._tiles || {};
        const targetTiles = Object.values(tiles).filter((rec) => (
            rec?.coords?.z === targetZoom && rec.current !== false
        ));
        if (!targetTiles.length) return false;
        return targetTiles.every((rec) => {
            const element = rec?.el;
            const imageOk = !element || (element.complete !== false && Number(element.naturalWidth || 0) > 0);
            return rec?.loaded && imageOk;
        });
    }

    function _satelliteLayerHasAnyLoadedTileForZoom(layer, zoomLevel) {
        if (!layer || !Number.isFinite(zoomLevel)) return false;
        const maxNativeZoom = Number(layer?.options?.maxNativeZoom);
        const minNativeZoom = Number(layer?.options?.minNativeZoom);
        let targetZoom = Math.round(zoomLevel);
        if (Number.isFinite(maxNativeZoom)) targetZoom = Math.min(targetZoom, maxNativeZoom);
        if (Number.isFinite(minNativeZoom)) targetZoom = Math.max(targetZoom, minNativeZoom);
        const tiles = layer._tiles || {};
        return Object.values(tiles).some((rec) => {
            if (rec?.coords?.z !== targetZoom || rec.current === false || !rec?.loaded) return false;
            const element = rec?.el;
            return !element || (element.complete !== false && Number(element.naturalWidth || 0) > 0);
        });
    }

    function _satelliteLayerReadyForSwap(layer, zoomLevel) {
        return _satelliteLayerHasLoadedTilesForZoom(layer, zoomLevel) && layer._loading !== true;
    }

    function _setSatelliteLayerZIndex(layer, active = false) {
        if (!layer || typeof layer.setZIndex !== 'function') return;
        if (active) {
            _satelliteLayerZCounter += 1;
            layer.setZIndex(1000 + _satelliteLayerZCounter);
            return;
        }
        layer.setZIndex(1);
    }

    function _satelliteHotFrameIndexes(activeIndex = _satelliteFrameIndex) {
        const count = _satelliteFrames.length;
        const indexes = new Set();
        if (!_satelliteScrubMode || !count) return indexes;
        const center = Math.max(0, Math.min(count - 1, Number(activeIndex) || 0));
        const radius = Math.max(0, Math.min(SATELLITE_HOT_FRAME_RADIUS, count - 1));
        if (count <= radius * 2 + 1) {
            for (let idx = 0; idx < count; idx += 1) indexes.add(idx);
            return indexes;
        }
        for (let offset = -radius; offset <= radius; offset += 1) {
            indexes.add((center + offset + count) % count);
        }
        return indexes;
    }

    function _satelliteShouldRetainAnimationLayers() {
        return _satelliteScrubMode
            && _satelliteFrames.length > 0
            && _satelliteFrames.length <= SATELLITE_ANIMATION_RETAIN_LAYER_LIMIT;
    }

    function _refreshSatelliteHotFrameWindow(activeIndex = _satelliteFrameIndex, keepLayers = new Set()) {
        if (!_satelliteScrubMode || !_satelliteFrames.length || !_isTypeEnabled('satellite')) return;
        const active = Math.max(0, Math.min(_satelliteFrames.length - 1, Number(activeIndex) || 0));
        const hotIndexes = _satelliteHotFrameIndexes(active);
        const hotLayers = new Set(keepLayers);
        hotIndexes.forEach((idx) => {
            const frame = _satelliteFrames[idx];
            const frameKey = frame?.frame_key || '';
            if (!frameKey) return;
            const layer = _getOrCreateSatelliteLayer(frameKey);
            if (!map.hasLayer(layer)) layer.addTo(map);
            if (typeof layer.setOpacity === 'function') {
                layer.setOpacity(idx === active ? 0.92 : 0);
            }
            _setSatelliteLayerZIndex(layer, idx === active);
            hotLayers.add(layer);
        });
        _satelliteLayerPool.forEach((layer) => {
            if (!layer || hotLayers.has(layer)) return;
            if (_satelliteShouldRetainAnimationLayers() && map.hasLayer(layer)) {
                if (typeof layer.setOpacity === 'function') layer.setOpacity(0);
                _setSatelliteLayerZIndex(layer, false);
                return;
            }
            if (map.hasLayer(layer)) map.removeLayer(layer);
        });
    }

    function _primeSatelliteAnimationLayers(activeIndex = _satelliteFrameIndex) {
        _refreshSatelliteHotFrameWindow(activeIndex);
    }

    function _hideInactiveSatelliteAnimationLayers(activeLayer, previousLayer = null) {
        if (!_satelliteScrubMode) return;
        _refreshSatelliteHotFrameWindow(_satelliteFrameIndex, new Set([activeLayer, previousLayer].filter(Boolean)));
    }

    function _cancelSatellitePendingSwap() {
        _satellitePendingSwapToken += 1;
        _satelliteScrubFrameAdvanceInFlight = false;
    }

    function _cancelSatelliteProgressiveRedraws() {
        _satelliteProgressiveRedrawSeq += 1;
        _satelliteProgressiveRedrawTimers.forEach((timerId) => clearTimeout(timerId));
        _satelliteProgressiveRedrawTimers = [];
    }

    function _scheduleSatelliteProgressiveRedraws(layer, frameKey, options = {}) {
        if (!layer || !frameKey || !_isTypeEnabled('satellite')) return;
        const forceRetry = options?.force === true;
        const retryKey = `${frameKey}|${Math.round(map.getZoom())}`;
        const retainAnimationLayer = _satelliteShouldRetainAnimationLayers();
        if (forceRetry) {
            layer._wxSatelliteProgressiveRetryKey = '';
            layer._wxSatelliteLoadCompleteKey = '';
        }
        if (!forceRetry && retainAnimationLayer && layer._wxSatelliteProgressiveRetryKey === retryKey) return;
        if (!forceRetry && _satelliteScrubMode && layer._wxSatelliteLoadCompleteKey === retryKey) return;
        if (!retainAnimationLayer) {
            _cancelSatelliteProgressiveRedraws();
        }
        layer._wxSatelliteProgressiveRetryKey = retryKey;
        const markLayerLoaded = () => {
            if (!_satelliteLayerReadyForSwap(layer, map.getZoom())) return;
            layer._wxSatelliteLoadCompleteKey = retryKey;
            layer._wxSatelliteTileErrorCount = 0;
            layer.off('load', markLayerLoaded);
        };
        if (_satelliteScrubMode && _satelliteLayerReadyForSwap(layer, map.getZoom())) {
            markLayerLoaded();
            return;
        }
        layer.on('load', markLayerLoaded);
        const redrawSeq = _satelliteProgressiveRedrawSeq;
        const timers = SATELLITE_PROGRESSIVE_REDRAW_DELAYS_MS.map((delayMs) => setTimeout(() => {
            if (redrawSeq !== _satelliteProgressiveRedrawSeq) return;
            if (!_isTypeEnabled('satellite') || !map.hasLayer(layer)) return;
            if (!retainAnimationLayer && satelliteOverlay !== layer) return;
            if (_satelliteScrubMode && layer._wxSatelliteLoadCompleteKey === retryKey) return;
            _satelliteTileRefreshToken = Date.now();
            if (typeof layer.setUrl === 'function') {
                layer.setUrl(_satelliteTileTemplate(frameKey), false);
                return;
            }
            if (typeof layer.redraw === 'function') {
                layer.redraw();
            }
        }, delayMs));
        _satelliteProgressiveRedrawTimers.push(...timers);
    }

    function _canApplySatelliteFrame(renderSeq) {
        return renderSeq === _satelliteScrubRenderSeq && _isTypeEnabled('satellite');
    }

    async function _waitForSatelliteLayerReady(layer, zoomLevel, renderSeq, timeoutMs = 5000) {
        if (!layer || _satelliteLayerReadyForSwap(layer, zoomLevel)) return true;

        return new Promise((resolve) => {
            let settled = false;
            let timeoutId = null;

            const finish = (ready) => {
                if (settled) return;
                settled = true;
                layer.off('load', onLoad);
                clearTimeout(timeoutId);
                resolve(ready);
            };

            const onLoad = () => finish(_satelliteLayerHasLoadedTilesForZoom(layer, zoomLevel));

            timeoutId = setTimeout(() => {
                finish(_satelliteLayerHasLoadedTilesForZoom(layer, zoomLevel));
            }, timeoutMs);

            if (!_canApplySatelliteFrame(renderSeq)) {
                finish(false);
                return;
            }

            layer.on('load', onLoad);
        });
    }

    async function _setSatelliteFrame(index, options = {}) {
        if (!_satelliteFrames.length || !_isTypeEnabled('satellite')) return;
        const waitForTiles = options?.waitForTiles === true;
        const forceReloadSameLayer = options?.forceReloadSameLayer === true;
        const requestedTileTimeoutMs = Number(options?.tileTimeoutMs);
        const tileTimeoutMs = Number.isFinite(requestedTileTimeoutMs)
            ? Math.max(1000, requestedTileTimeoutMs)
            : SATELLITE_TILE_READY_TIMEOUT_MS;
        const clamped = Math.max(0, Math.min(_satelliteFrames.length - 1, Number(index) || 0));
        const frame = _satelliteFrames[clamped];
        const frameKey = frame?.frame_key || '';
        if (!frameKey) return;

        const nextLayer = _getOrCreateSatelliteLayer(frameKey);
        const targetZoom = map.getZoom();
        const prevLayer = satelliteOverlay;
        const renderSeq = ++_satelliteScrubRenderSeq;
        _satelliteScrubFrameAdvanceInFlight = waitForTiles;

        const updateFrameUi = () => {
            satelliteOverlay = nextLayer;
            _satelliteFrameIndex = clamped;

            _updateSatelliteScrubberUi();

            const tsMs = _resolveDataTimestampMs(frame.timestamp_utc || frame.frame_key || null);
            _setViewerTimestamp(tsMs);
            if (_satelliteScrubMode) {
                _setRtmaScrubberStatus(`${_satelliteFrameIndex + 1} / ${_satelliteFrames.length} frames.`);
            } else {
                _setSatelliteStatus(`Current frame loaded (${_satelliteFrameIndex + 1}/${_satelliteFrames.length}).`);
            }
            _scheduleSatelliteProgressiveRedraws(nextLayer, frameKey);
            _scheduleSatelliteTilePrefetch();
        };

        if (prevLayer === nextLayer) {
            if (forceReloadSameLayer && typeof nextLayer.setUrl === 'function') {
                nextLayer.setUrl(_satelliteTileTemplate(frameKey), false);
                if (typeof nextLayer.redraw === 'function') {
                    nextLayer.redraw();
                }
            }
            _satelliteScrubFrameAdvanceInFlight = false;
            if (!_canApplySatelliteFrame(renderSeq)) return false;
            updateFrameUi();
            return true;
        }

        const swapToken = ++_satellitePendingSwapToken;

        if (!map.hasLayer(nextLayer)) nextLayer.addTo(map);
        if (typeof nextLayer.setOpacity === 'function') {
            nextLayer.setOpacity(prevLayer ? 0 : 0.92);
        }
        _setSatelliteLayerZIndex(nextLayer, true);
        _hideInactiveSatelliteAnimationLayers(nextLayer, prevLayer);

        const ready = waitForTiles
            ? await _waitForSatelliteLayerReady(nextLayer, targetZoom, renderSeq, tileTimeoutMs)
            : true;
        if (!ready || swapToken !== _satellitePendingSwapToken || !_canApplySatelliteFrame(renderSeq)) {
            if (!prevLayer && ready === false && _satelliteLayerHasAnyLoadedTileForZoom(nextLayer, targetZoom) && swapToken === _satellitePendingSwapToken && _canApplySatelliteFrame(renderSeq)) {
                _satelliteScrubFrameAdvanceInFlight = false;
                updateFrameUi();
                return true;
            }
            if (map.hasLayer(nextLayer)) map.removeLayer(nextLayer);
            _satelliteScrubFrameAdvanceInFlight = false;
            return false;
        }

        if (prevLayer && map.hasLayer(prevLayer)) {
            const applied = await _crossfadeSatelliteLayers(
                prevLayer,
                nextLayer,
                () => swapToken === _satellitePendingSwapToken && _canApplySatelliteFrame(renderSeq),
            );
            if (!applied) {
                _satelliteScrubFrameAdvanceInFlight = false;
                return false;
            }
        } else if (typeof nextLayer.setOpacity === 'function') {
            nextLayer.setOpacity(0.92);
        }

        if (swapToken !== _satellitePendingSwapToken || !_canApplySatelliteFrame(renderSeq)) {
            _satelliteScrubFrameAdvanceInFlight = false;
            return false;
        }
        _satelliteScrubFrameAdvanceInFlight = false;
        updateFrameUi();
        _hideInactiveSatelliteAnimationLayers(nextLayer);
        return true;
    }

    function _clearSatelliteLayer(clearFrames = false) {
        _cancelSatelliteProgressiveRedraws();
        _cancelSatelliteTilePrefetch();
        _clearSatelliteLayerPool();
        if (clearFrames) {
            _satelliteFrames = [];
            _satelliteFrameIndex = 0;
            _updateSatelliteScrubberUi();
        }
    }

    function _getOrCreateSatelliteLayer(frameKey) {
        const poolKey = _satelliteLayerPoolKey(frameKey);
        if (!_satelliteLayerPool.has(poolKey)) {
            const frame = _satelliteActiveFrameByKey(frameKey);
            const maxNativeZoom = _satelliteFrameMaxNativeZoom(frame);
            const minNativeZoom = _satelliteMinNativeZoomForSector(_activeSatelliteSector());
            const layer = L.tileLayer(_satelliteTileTemplate(frameKey), {
                pane: 'satellite-overlays',
                maxZoom: 19,
                ...(Number.isFinite(maxNativeZoom) ? { maxNativeZoom } : {}),
                minNativeZoom,
                opacity: 0.92,
                updateWhenIdle: false,
                updateWhenZooming: false,
                keepBuffer: 4,
                crossOrigin: true,
            });
            layer.on('tileerror', () => {
                layer._wxSatelliteLoadCompleteKey = '';
                const retryCount = Number(layer._wxSatelliteTileErrorCount || 0) + 1;
                layer._wxSatelliteTileErrorCount = retryCount;
                if (retryCount > 8 || !_isTypeEnabled('satellite') || !map.hasLayer(layer)) return;
                if (layer._wxSatelliteTileErrorRetryTimer) {
                    clearTimeout(layer._wxSatelliteTileErrorRetryTimer);
                }
                const retryDelayMs = Math.min(6000, 900 + retryCount * 500);
                layer._wxSatelliteTileErrorRetryTimer = setTimeout(() => {
                    layer._wxSatelliteTileErrorRetryTimer = null;
                    if (!_isTypeEnabled('satellite') || !map.hasLayer(layer)) return;
                    _satelliteTileRefreshToken = Date.now();
                    if (typeof layer.setUrl === 'function') {
                        layer.setUrl(_satelliteTileTemplate(frameKey), false);
                        _scheduleSatelliteProgressiveRedraws(layer, frameKey, { force: true });
                        return;
                    }
                    if (typeof layer.redraw === 'function') {
                        layer.redraw();
                        _scheduleSatelliteProgressiveRedraws(layer, frameKey, { force: true });
                    }
                }, retryDelayMs);
            });
            _satelliteLayerPool.set(poolKey, layer);
        }
        return _satelliteLayerPool.get(poolKey);
    }

    function _clearSatelliteLayerPool() {
        _cancelSatellitePendingSwap();
        _cancelSatelliteProgressiveRedraws();
        _cancelSatelliteTilePrefetch();
        _satelliteLayerPool.forEach((layer) => {
            if (layer?._wxSatelliteTileErrorRetryTimer) {
                clearTimeout(layer._wxSatelliteTileErrorRetryTimer);
                layer._wxSatelliteTileErrorRetryTimer = null;
            }
            if (map.hasLayer(layer)) map.removeLayer(layer);
        });
        _satelliteLayerPool.clear();
        _satelliteLayerZCounter = 0;
        satelliteOverlay = null;
    }

    function _canApplySatelliteResponse(requestSeq) {
        return requestSeq === _satelliteRequestSeq
            && _isTypeEnabled('satellite')
            && !_archiveMode
            && !_radarScrubMode
            && !_rtmaScrubMode
            && !_mrmsScrubMode
            && (!_satelliteScrubMode || _isTypeEnabled('satellite'));
    }

    function _stopSatelliteAutoRefresh() {
        if (_satelliteAutoRefreshTimer) {
            clearInterval(_satelliteAutoRefreshTimer);
            _satelliteAutoRefreshTimer = null;
        }
    }

    function _startSatelliteAutoRefresh() {
        if (_satelliteAutoRefreshTimer) return;
        _satelliteAutoRefreshTimer = setInterval(() => {
            if (document.hidden) return;
            if (!_isTypeEnabled('satellite')) return;
            if (_archiveMode || _radarScrubMode || _rtmaScrubMode || _mrmsScrubMode || _satelliteScrubMode) return;
            loadSatelliteCurrentFrame({ silent: true });
        }, SATELLITE_AUTO_REFRESH_MS);
    }

    function _syncSatelliteAutoRefresh() {
        if (_isTypeEnabled('satellite')
            && !_archiveMode
            && !_radarScrubMode
            && !_rtmaScrubMode
            && !_mrmsScrubMode
            && !_satelliteScrubMode) {
            _startSatelliteAutoRefresh();
        } else {
            _stopSatelliteAutoRefresh();
        }
    }

    function _stopSatelliteScrubPlay() {
        if (_satelliteScrubPlayTimer) {
            clearTimeout(_satelliteScrubPlayTimer);
            _satelliteScrubPlayTimer = null;
        }
        _cancelSatellitePendingSwap();
        if (_satelliteScrubMode) {
            const btn = byId('scrubber-play');
            if (btn) btn.textContent = '▶';
        }
    }

    function _startSatelliteScrubPlay() {
        if (!_satelliteFrames.length || !_satelliteScrubMode) return;
        if (_satelliteScrubPlayTimer) return;
        if (_satelliteManualScrubTimer) {
            clearTimeout(_satelliteManualScrubTimer);
            _satelliteManualScrubTimer = null;
        }
        const btn = byId('scrubber-play');
        if (btn) btn.textContent = '⏸';

        let _stalledTicks = 0;

        const tick = async () => {
            if (!_satelliteScrubPlayTimer || !_satelliteFrames.length || !_satelliteScrubMode) return;

            if (_satelliteScrubFrameAdvanceInFlight) {
                _satelliteScrubPlayTimer = setTimeout(tick, _scrubberPlaybackDelay(220, 120));
                return;
            }

            const atLast = _satelliteFrameIndex >= _satelliteFrames.length - 1;
            if (atLast) {
                _satelliteScrubPlayTimer = setTimeout(async () => {
                    if (!_satelliteScrubPlayTimer || !_satelliteFrames.length || !_satelliteScrubMode) return;
                    const advanced = await _setSatelliteFrame(0, { waitForTiles: false });
                    if (!_satelliteScrubPlayTimer || !_satelliteFrames.length || !_satelliteScrubMode) return;
                    if (advanced) {
                        _stalledTicks = 0;
                        _updateRtmaScrubberUi();
                        _satelliteScrubPlayTimer = setTimeout(tick, _scrubberPlaybackDelay(650, 120));
                        return;
                    }
                    _satelliteScrubPlayTimer = setTimeout(tick, _scrubberPlaybackDelay(220, 120));
                }, _scrubberPlaybackDelay(RTMA_SCRUB_LOOP_HOLD_MS, 350));
                return;
            }

            const next = _satelliteFrameIndex + 1;
            const advanced = await _setSatelliteFrame(next, { waitForTiles: false });
            if (!_satelliteScrubPlayTimer || !_satelliteFrames.length || !_satelliteScrubMode) return;
            if (advanced) {
                _stalledTicks = 0;
                _updateRtmaScrubberUi();
                _satelliteScrubPlayTimer = setTimeout(tick, _scrubberPlaybackDelay(650, 120));
                return;
            }

            _stalledTicks += 1;
            if (_stalledTicks >= 8) {
                _stalledTicks = 0;
                _setRtmaScrubberStatus(`Frame ${next + 1} / ${_satelliteFrames.length}; tiles are filling.`);
                _satelliteScrubPlayTimer = setTimeout(tick, _scrubberPlaybackDelay(650, 120));
                return;
            }

            _satelliteScrubPlayTimer = setTimeout(tick, _scrubberPlaybackDelay(220, 120));
        };

        _satelliteScrubPlayTimer = setTimeout(tick, _scrubberPlaybackDelay(650, 120));
    }

    function _exitSatelliteScrubMode(restoreCurrent = true) {
        if (_satelliteLookbackReloadTimer) {
            clearTimeout(_satelliteLookbackReloadTimer);
            _satelliteLookbackReloadTimer = null;
        }
        if (_satelliteManualScrubTimer) {
            clearTimeout(_satelliteManualScrubTimer);
            _satelliteManualScrubTimer = null;
        }
        if (_satelliteScrubFetchController) {
            _satelliteScrubFetchController.abort();
            _satelliteScrubFetchController = null;
        }
        _stopSatelliteScrubPlay();
        _satelliteScrubMode = false;
        _satelliteScrubLoadSeq += 1;
        _satelliteScrubRenderSeq += 1;
        _satelliteBackgroundWarmSeq += 1;
        _cancelSatelliteTilePrefetch();
        _setArchiveScrubber(false);
        _setScrubberControlsEnabled(false);
        _setRtmaScrubberStatus('');
        _setSatelliteAnimateButtonFilling(false);
        _setSatelliteModeActive('current');
        _clearSatelliteLayerPool();
        _syncSatelliteAutoRefresh();
        if (restoreCurrent && _isTypeEnabled('satellite')) {
            loadSatelliteCurrentFrame({ silent: true });
        }
    }

    async function _warmSatelliteFramesInBackground(loadSeq, _pollParams) {
        if (!_satelliteScrubMode || loadSeq !== _satelliteScrubLoadSeq) return;
        const catalogAge = Number(_satelliteCatalog?.catalog_age_seconds);
        const ageLabel = Number.isFinite(catalogAge) ? ` • catalog age ${Math.round(catalogAge)}s` : '';
        const totalTiles = _satelliteFrames.reduce((sum, frame) => sum + _satelliteFrameTileCount(frame), 0);
        _setSatelliteAnimateButtonFilling(false);
        _setRtmaScrubberStatus(`${_satelliteFrames.length} v2 frames loaded (${totalTiles} cached tiles${ageLabel}); tiles fill as they render.`);
    }

    async function loadSatelliteCurrentFrame(options = {}) {
        if (!_isTypeEnabled('satellite')) return;
        if (_satelliteScrubMode) return;
        _setSatelliteModeActive('current');
        void _updateSatelliteLegend();
        const silent = options.silent === true;
        const refreshCatalog = options.refresh === true || silent;
        const previousFrameKey = _satelliteFrames[_satelliteFrameIndex]?.frame_key || '';
        const requestSeq = ++_satelliteRequestSeq;

        // F7: cancel any in-flight frame-list request before starting a new one
        if (_satelliteFetchController) _satelliteFetchController.abort();
        _satelliteFetchController = new AbortController();
        const { signal } = _satelliteFetchController;

        try {
            if (!silent) {
                _setSatelliteStatus('Loading current satellite frame...');
            }
            let frameSet = null;
            let requestWindow = null;
            let lastFrameSetError = null;
            for (const candidateWindow of _satelliteCurrentFrameRequestWindows()) {
                try {
                    frameSet = await _fetchSatelliteFrameSet({
                        hours: candidateWindow.hours,
                        maxFrames: candidateWindow.maxFrames,
                        signal,
                        refresh: refreshCatalog,
                        requireTiles: false,
                        minFrames: 1,
                    });
                    requestWindow = candidateWindow;
                    break;
                } catch (err) {
                    if (err.name === 'AbortError') throw err;
                    lastFrameSetError = err;
                }
            }
            if (!frameSet || !requestWindow) {
                throw lastFrameSetError || new Error('Satellite catalog does not have enough frames yet.');
            }
            if (!_canApplySatelliteResponse(requestSeq)) return;
            _setSatelliteApiMode(frameSet.mode, frameSet.data);

            _satelliteFrames = Array.isArray(frameSet.frames) ? frameSet.frames : [];

            if (!_satelliteFrames.length) {
                _clearSatelliteLayer(true);
                _setSatelliteStatus('No current satellite frame available for this selection.');
                return;
            }

            _satelliteFrameIndex = _satelliteFrameIndexForReload(_satelliteFrames);
            const currentFrameKey = _satelliteFrames[_satelliteFrameIndex]?.frame_key || '';
            const forceReloadSameLayer = (
                silent
                && Boolean(currentFrameKey)
                && currentFrameKey === previousFrameKey
            );
            if (forceReloadSameLayer) {
                _satelliteTileRefreshToken = Date.now();
            }
            _primeSatelliteAnimationLayers(_satelliteFrameIndex);
            const frameDisplayed = await _setSatelliteFrame(_satelliteFrameIndex, {
                waitForTiles: false,
                tileTimeoutMs: SATELLITE_INITIAL_TILE_READY_TIMEOUT_MS,
                forceReloadSameLayer,
            });
            if (frameDisplayed) {
                const fallbackLabel = requestWindow.hours > _activeSatelliteLookbackHours()
                    ? `; latest found within ${requestWindow.hours}h`
                    : '';
                _setSatelliteStatus(`Current satellite frame loaded; tiles will fill as needed (${_satelliteFrameTileCount(_satelliteFrames[_satelliteFrameIndex])} cached tiles${fallbackLabel}).`);
            } else {
                _setSatelliteStatus('Satellite frame listed; tiles will fill as they render.');
            }
            _syncSatelliteAutoRefresh();
        } catch (err) {
            if (err.name === 'AbortError') return;
            if (!_canApplySatelliteResponse(requestSeq)) return;
            _setSatelliteStatus(`Satellite error: ${err.message}`);
        }
    }

    async function loadSatelliteScrubberFrames() {
        if (!_isTypeEnabled('satellite')) return;
        const previousFrameKey = _satelliteFrames[_satelliteFrameIndex]?.frame_key || '';
        if (_satelliteLookbackReloadTimer) {
            clearTimeout(_satelliteLookbackReloadTimer);
            _satelliteLookbackReloadTimer = null;
        }
        if (_satelliteManualScrubTimer) {
            clearTimeout(_satelliteManualScrubTimer);
            _satelliteManualScrubTimer = null;
        }
        if (_radarScrubMode) _exitRadarScrubMode(false);
        if (_rtmaScrubMode) _exitRtmaScrubMode(false);
        if (_mrmsScrubMode) _exitMrmsScrubMode(false);

        const loadSeq = ++_satelliteScrubLoadSeq;
        _satelliteBackgroundWarmSeq = loadSeq;
        if (_satelliteScrubFetchController) {
            _satelliteScrubFetchController.abort();
        }
        _satelliteScrubFetchController = new AbortController();
        const { signal } = _satelliteScrubFetchController;
        _satelliteScrubMode = true;
        _satelliteScrubRenderSeq += 1;
        _stopSatelliteAutoRefresh();
        _stopSatelliteScrubPlay();
        _setSatelliteModeActive('animate');
        void _updateSatelliteLegend();
        byId('weather-mode-current')?.classList.remove('active');
        byId('weather-mode-archive')?.classList.remove('active');
        _setArchiveScrubber(true);
        _setScrubberControlsEnabled(false);
        _satelliteFrames = [];
        _satelliteFrameIndex = 0;
        _updateSatelliteScrubberUi();
        _setRtmaScrubberStatus('Loading satellite animation frames...');

        try {
            const requestWindow = _currentSatelliteFrameRequestWindow();
            const frameSet = await _fetchSatelliteFrameSet({
                hours: requestWindow.hours,
                maxFrames: requestWindow.maxFrames,
                signal,
                requireTiles: false,
                minFrames: 0,
            });
            if (!_satelliteScrubMode || loadSeq !== _satelliteScrubLoadSeq) return;
            _setSatelliteApiMode(frameSet.mode, frameSet.data);

            _satelliteFrames = frameSet.frames;

            if (!_satelliteFrames.length) {
                _setScrubberControlsEnabled(false);
                _updateSatelliteScrubberUi();
                _setRtmaScrubberStatus('No frames found for selected lookback window.');
                _setSatelliteStatus('No animation frames available for this selection.');
                _setSatelliteAnimateButtonFilling(false);
                return;
            }

            _satelliteFrameIndex = _satelliteFrameIndexForReload(_satelliteFrames, previousFrameKey);
            // Show frame count and enable scrubber handle immediately — don't wait for tiles.
            _updateRtmaScrubberUi();
            _setScrubberControlsEnabled(true);
            _primeSatelliteAnimationLayers(_satelliteFrameIndex);
            let frameDisplayed = await _setSatelliteFrame(_satelliteFrameIndex, {
                waitForTiles: false,
                tileTimeoutMs: SATELLITE_INITIAL_TILE_READY_TIMEOUT_MS,
            });
            if (!frameDisplayed) {
                const fallbackIndex = _satelliteFrameIndexForReload(_satelliteFrames);
                if (fallbackIndex !== _satelliteFrameIndex) {
                    _satelliteFrameIndex = fallbackIndex;
                    _updateRtmaScrubberUi();
                    _primeSatelliteAnimationLayers(_satelliteFrameIndex);
                    frameDisplayed = await _setSatelliteFrame(_satelliteFrameIndex, {
                        waitForTiles: false,
                        tileTimeoutMs: SATELLITE_INITIAL_TILE_READY_TIMEOUT_MS,
                    });
                }
            }
            if (!_satelliteScrubMode || loadSeq !== _satelliteScrubLoadSeq) return;
            _updateRtmaScrubberUi();
            if (frameDisplayed) {
                _setRtmaScrubberStatus(`${_satelliteFrames.length} v2 frames loaded (${requestWindow.hours}h window); tiles fill as they render.`);
                _setSatelliteStatus('Animate mode loaded. Press Play to start scrubbing while tiles fill.');
            } else {
                _setRtmaScrubberStatus(`${_satelliteFrames.length} v2 frames listed (${requestWindow.hours}h window).`);
                _setSatelliteStatus('Satellite animation frames listed; tiles will fill as requested.');
            }

            _warmSatelliteFramesInBackground(loadSeq, null);
        } catch (err) {
            if (err.name === 'AbortError') return;
            if (!_satelliteScrubMode || loadSeq !== _satelliteScrubLoadSeq) return;
            _satelliteFrames = [];
            _satelliteFrameIndex = 0;
            _updateSatelliteScrubberUi();
            _setScrubberControlsEnabled(false);
            _setRtmaScrubberStatus(`Error: ${err.message}`);
            _setSatelliteStatus(`Satellite animate error: ${err.message}`);
            _setSatelliteAnimateButtonFilling(false);
        } finally {
            if (_satelliteScrubFetchController?.signal === signal) {
                _satelliteScrubFetchController = null;
            }
        }
    }

    function refreshActiveLayers() {
        if (_archiveMode || _rtmaScrubMode || _mrmsScrubMode || _radarScrubMode || _satelliteScrubMode) return;
        const alertsEnabled = _isTypeEnabled('alerts') && _getCheckedAlertCategories().length > 0;
        const spcEnabled = _isTypeEnabled('spc') && byId('weather-show-spc')?.checked;
        const surfaceProduct = _activeSurfaceProduct();
        const surfaceEnabled = _isTypeEnabled('current') && !!surfaceProduct;
        const radarEnabled = _isTypeEnabled('radar');
        const satelliteEnabled = _isTypeEnabled('satellite');
        const rtmaEnabled = _isTypeEnabled('rtma') && !!_activeRtmaStream() && !!_activeRtmaProduct();
        const mrmsEnabled = _isTypeEnabled('mrms') && !!_activeMrmsProduct();

        const droughtEnabled = _isTypeEnabled('drought');

        // Clear legend at the start to ensure old legend doesn't persist when switching products
        setLegend(null);

        if (!alertsEnabled && alertsLayer && map.hasLayer(alertsLayer)) map.removeLayer(alertsLayer);
        if (!spcEnabled && spcLayer && map.hasLayer(spcLayer)) map.removeLayer(spcLayer);
        if (!surfaceEnabled && surfaceLayer && map.hasLayer(surfaceLayer)) map.removeLayer(surfaceLayer);
        if (!radarEnabled && radarLiveOverlay && map.hasLayer(radarLiveOverlay)) map.removeLayer(radarLiveOverlay);
        if (!satelliteEnabled && satelliteOverlay && map.hasLayer(satelliteOverlay)) map.removeLayer(satelliteOverlay);
        if (!radarEnabled && radarBackdropLayer && map.hasLayer(radarBackdropLayer)) map.removeLayer(radarBackdropLayer);
        if (!radarEnabled && radarSiteLayer && map.hasLayer(radarSiteLayer)) map.removeLayer(radarSiteLayer);
        if (!radarEnabled && radarSiteHighlightLayer && map.hasLayer(radarSiteHighlightLayer)) map.removeLayer(radarSiteHighlightLayer);
        if (!rtmaEnabled && rtmaOverlay && map.hasLayer(rtmaOverlay)) map.removeLayer(rtmaOverlay);
        if (!rtmaEnabled && rtmaGradientLayer && map.hasLayer(rtmaGradientLayer)) { map.removeLayer(rtmaGradientLayer); rtmaGradientLayer = null; }
        if (!rtmaEnabled && rtmaPointLayer && map.hasLayer(rtmaPointLayer)) { map.removeLayer(rtmaPointLayer); rtmaPointLayer = null; }
        if (!mrmsEnabled && mrmsOverlay && map.hasLayer(mrmsOverlay)) map.removeLayer(mrmsOverlay);
        if (!mrmsEnabled && mrmsRadarSiteLayer && map.hasLayer(mrmsRadarSiteLayer)) map.removeLayer(mrmsRadarSiteLayer);
        if (!droughtEnabled && droughtLayer && map.hasLayer(droughtLayer)) { map.removeLayer(droughtLayer); droughtLayer = null; }

        if (!spcEnabled) {
            if (_spcAbortController) {
                _spcAbortController.abort();
                _spcAbortController = null;
            }
            setMapEmptyMessage(null);
        }

        // Hide warnings panel when alerts are disabled.
        if (!alertsEnabled) _renderActiveWarningsPanel();

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
        if (radarEnabled) {
            _loadRadarSites();
            loadRadarLiveLatest();
        }
        if (satelliteEnabled) {
            loadSatelliteCurrentFrame({ silent: true });
        } else {
            _exitSatelliteScrubMode(false);
            _stopSatelliteAutoRefresh();
        }
        if (rtmaEnabled) {
            loadRtma();
        }
        if (mrmsEnabled) {
            loadMrms();
        }
        if (droughtEnabled) {
            loadDroughtLayer();
        }
    }

    // ── Opacity helpers ──────────────────────────────────────────────────────
    function applyAlertsOpacity(val) {
        alertsOpacity = parseFloat(val);
        if (alertsLayer) alertsLayer.setStyle(alertStyle);
    }

    function applySpcOpacity(val) {
        spcOpacity = parseFloat(val);
        if (spcLayer) {
            if (typeof spcLayer.eachLayer === 'function') {
                spcLayer.eachLayer((layer) => {
                    if (typeof layer.setStyle === 'function') {
                        const styleFn = layer._spcStyleFn || _getSpcStyleFn(layer._spcHazard || 'cat');
                        layer.setStyle(styleFn);
                    }
                });
                _applySpcCigPatternsToGroup(spcLayer);
            } else if (typeof spcLayer.setStyle === 'function') {
                spcLayer.setStyle(_getSpcStyleFn(_getPrimarySpcHazard()));
            }
        }
    }

    function applySpcStrokeOpacity(val) {
        const parsed = parseFloat(val);
        if (!Number.isFinite(parsed)) return;
        spcStrokeOpacity = parsed;
        if (spcLayer) {
            if (typeof spcLayer.eachLayer === 'function') {
                spcLayer.eachLayer((layer) => {
                    if (typeof layer.setStyle === 'function') {
                        const styleFn = layer._spcStyleFn || _getSpcStyleFn(layer._spcHazard || 'cat');
                        layer.setStyle(styleFn);
                    }
                });
                _applySpcCigPatternsToGroup(spcLayer);
            } else if (typeof spcLayer.setStyle === 'function') {
                spcLayer.setStyle(_getSpcStyleFn(_getPrimarySpcHazard()));
            }
        }
    }

    // ── Surface layer state ───────────────────────────────────────────────────
    let _surfaceStations = [];   // full unfiltered station list for re-thinning on zoom
    let _surfaceGradientStations = []; // cached source stations for gradient interpolation
    let _surfaceGradientProduct = null;
    let _surfaceGradientRegion = null;
    const _surfaceGradientOverlayCache = new Map();
    const _surfaceGradientOverlayInflight = new Map();

    function _getGradientSourceRegion(regionCode = null) {
        const region = (regionCode || byId('weather-region')?.value || 'CONUS').toUpperCase();
        // WORLD should interpolate from WORLD observations, not CONUS.
        return region === 'WORLD' ? 'WORLD' : 'CONUS';
    }

    // ── Wind direction barb icon ─────────────────────────────────────────────
    // Renders a meteorological arrow: shaft + arrowhead pointing FROM the wind
    // origin (e.g. dirDeg=270 → westerly wind → arrow points left/west).
    // The SVG is rotated via the SVG transform attribute so no CSS quirks.
    function windDirectionBarbIcon(dirDeg, opacity) {
        const zoom = map?.getZoom() ?? 5;
        const zoomMin = 5, zoomMax = 9;
        const t = Math.max(0, Math.min(1, (zoom - zoomMin) / (zoomMax - zoomMin)));
        const size = Math.round(22 + t * 18); // 22px @ z5 → 40px @ z9+
        const alpha = Math.max(0, Math.min(1, opacity));
        // Clamp to 0-360
        const rot = ((dirDeg % 360) + 360) % 360;
        // viewBox is 20×20; center is (10,10).
        // Arrow drawn pointing UP (from-north = 0°); rotate by rot degrees around center.
        const svg =
            `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" ` +
            `width="${size}" height="${size}" style="overflow:visible;opacity:${alpha};" ` +
            `role="img" aria-label="Wind from ${Math.round(rot)}°">` +
            `<defs>` +
            `<filter id="wdb-shadow" x="-60%" y="-60%" width="220%" height="220%">` +
            `<feDropShadow dx="0" dy="0" stdDeviation="1.4" flood-color="black" flood-opacity="0.95"/>` +
            `</filter>` +
            `</defs>` +
            `<g transform="rotate(${rot},10,10)" filter="url(#wdb-shadow)">` +
            `<line x1="10" y1="18" x2="10" y2="7" stroke="white" stroke-width="2.5" stroke-linecap="round"/>` +
            `<polygon points="10,1 5,9 15,9" fill="white"/>` +
            `</g>` +
            `</svg>`;
        return L.divIcon({
            className: '',
            html: `<div style="width:${size}px;height:${size}px;">${svg}</div>`,
            iconSize: [size, size],
            iconAnchor: [Math.round(size / 2), Math.round(size / 2)],
        });
    }

    function surfaceColoredTextIcon(value, unit, opacity, forceInteger = false) {
        const label = forceInteger || unit === '°F' || unit === '%' || unit === 'kt'
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
        if (zoom >= 9) return 10;
        if (zoom >= 7) return 30;
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
            : (zoom <= 5 ? 0.36 : 0.28);
        const floorKm = region === 'WORLD' ? (zoom <= 3 ? 16 : 14) : 8;
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
            if (zoom <= 5) return 12;
            // Higher world zoom: tighten grid for better local fidelity.
            return 8;
        }
        // Non-world low zoom: moderate coarsening for responsiveness.
        if (zoom <= 5) return 8;
        // Regional/state zoom: finer cells for best detail.
        return 6;
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
    function _renderGradientSurface(stations, product, canvasAlpha = surfaceGradientOpacity, blurScale = _gradientBlurScale) {
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
        const blurPx = Math.round(Math.max(cellWidth, cellHeight) * 1.2 * blurScale);
        ctx.filter = blurPx > 0 ? `blur(${blurPx}px)` : 'none';
        ctx.globalAlpha = Math.max(0, Math.min(1, canvasAlpha));
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

    /**
     * Render a gradient ImageOverlay directly from GRIB-subgrid points.
     * Skips IDW entirely: each point is projected to canvas coordinates and painted
     * as a filled cell, giving a pixel-accurate representation of the GRIB analysis.
     *
     * @param {Array} gridPoints - array of [lat, lon, value] from /api/data/rtma/grid
     * @param {string} product   - RTMA product key
     * @param {number} canvasAlpha
     * @param {number} blurScale
     * @returns {L.ImageOverlay|null}
     */
    function _renderGradientFromGribGrid(gridPoints, product, canvasAlpha = 1.0, blurScale = 0.35) {
        if (!gridPoints || !gridPoints.length) return null;

        const bounds = map.getBounds();
        const canvasSize = map.getSize();
        const canvas = document.createElement('canvas');
        canvas.width = canvasSize.x;
        canvas.height = canvasSize.y;

        // Estimate cell size in pixels from the nominal GRIB stride spacing (~10km for stride=8).
        // Use Leaflet's meters-per-pixel at the grid center latitude for accuracy.
        const refLat = gridPoints[Math.floor(gridPoints.length / 2)][0];
        const cosLat = Math.max(0.1, Math.cos(refLat * Math.PI / 180));
        const zoom = map.getZoom();
        const metersPerPx = 40075016 * cosLat / Math.pow(2, zoom + 8);
        // Nominal stride spacing: stride=8 × 2.5km/cell = 20km; add 20% overlap to fill gaps.
        const NOMINAL_SPACING_M = 20000;
        const cellPx = Math.max(3, (NOMINAL_SPACING_M / metersPerPx) * 1.2);

        const offscreen = document.createElement('canvas');
        offscreen.width = canvas.width;
        offscreen.height = canvas.height;
        const offCtx = offscreen.getContext('2d');

        let minVal = Infinity;
        let maxVal = -Infinity;
        for (const pt of gridPoints) {
            const v = pt[2];
            if (v < minVal) minVal = v;
            if (v > maxVal) maxVal = v;
        }

        const half = cellPx / 2;
        for (const pt of gridPoints) {
            const px = map.latLngToContainerPoint([pt[0], pt[1]]);
            offCtx.fillStyle = _getColorAtValue(pt[2], minVal, maxVal, product);
            offCtx.fillRect(px.x - half, px.y - half, cellPx, cellPx);
        }

        const ctx = canvas.getContext('2d');
        const blurPx = Math.round(cellPx * 1.2 * blurScale);
        ctx.filter = blurPx > 0 ? `blur(${blurPx}px)` : 'none';
        ctx.globalAlpha = Math.max(0, Math.min(1, canvasAlpha));
        ctx.drawImage(offscreen, 0, 0);
        ctx.filter = 'none';
        ctx.globalAlpha = 1.0;

        const imageUrl = canvas.toDataURL();
        return L.imageOverlay(imageUrl, bounds, {
            opacity: 1.0,
            className: 'surface-gradient-overlay'
        });
    }

    function _surfaceGradientCacheKey(product, regionCode = null) {
        const sourceRegion = _getGradientSourceRegion(regionCode);
        return `${sourceRegion}|${product}`;
    }

    async function _primeSurfaceGradientOverlayCache(product, regionCode = null) {
        if (_archiveMode || !product) return null;
        const key = _surfaceGradientCacheKey(product, regionCode);
        if (_surfaceGradientOverlayCache.has(key)) {
            return _surfaceGradientOverlayCache.get(key);
        }
        if (_surfaceGradientOverlayInflight.has(key)) {
            return _surfaceGradientOverlayInflight.get(key);
        }

        const sourceRegion = _getGradientSourceRegion(regionCode);
        const fetchPromise = (async () => {
            try {
                const url = apiUrl(`/api/data/surface-gradient?region=${encodeURIComponent(sourceRegion)}&product=${encodeURIComponent(product)}`);
                const resp = await fetch(url);
                if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
                const meta = await resp.json();
                if (meta && meta.image_url && Array.isArray(meta.bounds) && meta.bounds.length === 4) {
                    _surfaceGradientOverlayCache.set(key, meta);
                    return meta;
                }
            } catch (_err) {
                // Keep silent and allow client-side fallback interpolation.
            }
            return null;
        })();

        _surfaceGradientOverlayInflight.set(key, fetchPromise);
        try {
            return await fetchPromise;
        } finally {
            _surfaceGradientOverlayInflight.delete(key);
        }
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
            const gradientCacheKey = _surfaceGradientCacheKey(product, gradientSourceRegion);
            const cachedGradientMeta = _surfaceGradientOverlayCache.get(gradientCacheKey) || null;
            const gradientStations = _archiveMode
                ? stations
                : (
                    _surfaceGradientProduct === product
                        && _surfaceGradientRegion === gradientSourceRegion
                        && _surfaceGradientStations.length
                        ? _surfaceGradientStations
                        : stations
                );
            let gradientLayer = null;

            if (
                cachedGradientMeta
                && cachedGradientMeta.image_url
                && Array.isArray(cachedGradientMeta.bounds)
                && cachedGradientMeta.bounds.length === 4
            ) {
                const b = cachedGradientMeta.bounds;
                const leafletBounds = [[b[2], b[0]], [b[3], b[1]]];
                gradientLayer = L.imageOverlay(apiUrl(cachedGradientMeta.image_url), leafletBounds, {
                    opacity: surfaceGradientOpacity,
                    className: 'surface-gradient-overlay',
                });
            } else if (gradientStations.length) {
                gradientLayer = _renderGradientSurface(gradientStations, product);
            }
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

    async function _ensureGradientStations(product, regionCode = null, prefetchedStations = null) {
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
            let allStations;
            if (prefetchedStations) {
                // Reuse stations already fetched by loadSurface — avoids a duplicate request.
                allStations = prefetchedStations;
            } else {
                const url = apiUrl(`/api/data/surface?region=${encodeURIComponent(sourceRegion)}&product=${encodeURIComponent(product)}`);
                const resp = await fetch(url);
                if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
                const data = await resp.json();
                allStations = Array.isArray(data?.stations) ? data.stations : [];
            }
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
            const url = apiUrl(`/api/data/surface?region=${encodeURIComponent(region)}` +
                `&product=${encodeURIComponent(product)}`);
            const resp = await fetch(url);
            if (!resp.ok) {
                const e = await resp.json().catch(() => ({}));
                throw new Error(e.detail || resp.statusText);
            }
            const data = await resp.json();
            if (!_canApplySurfaceResponse(region, product)) return;

            const stations = Array.isArray(data?.stations) ? data.stations : [];
            _surfaceStations = stations;
            _renderSurfaceMarkers(stations);

            const unit = _SURFACE_PRODUCTS_UNITS[product] || '';
            const anchors = _SURFACE_COLORMAPS[product] || _SURFACE_COLORMAPS.temperature;
            buildSurfaceLegend(unit, anchors, product);

            const countEl = byId('weather-surface-count');
            if (countEl) countEl.textContent = `${stations.length} station(s)`;
            const surfaceTsMs = _resolveDataTimestampMs(data?.timestamp);
            const surfaceStaleNote = _staleNoteForTimestamp(surfaceTsMs);
            setStatus(`Surface ${product} for ${region} valid ${_formatValidTimeLabel(surfaceTsMs)}.${surfaceStaleNote}`);
            _setViewerTimestamp(surfaceTsMs);
            _setReliability('surface', `Surface ${product}`, 'IEM', surfaceTsMs);
            _setTimestampSource('surface', data?.timestamp_source || 'station_valid', surfaceTsMs);

            // Pass the already-fetched stations so _ensureGradientStations
            // doesn't fire a duplicate request for the same endpoint.
            await _ensureGradientStations(product, region, stations);

            // Warm worker-rendered gradient cache. If it becomes available,
            // redraw once so product switches use cached high-res overlays.
            const before = _surfaceGradientOverlayCache.has(_surfaceGradientCacheKey(product, region));
            await _primeSurfaceGradientOverlayCache(product, region);
            const after = _surfaceGradientOverlayCache.has(_surfaceGradientCacheKey(product, region));
            if (!before && after && _canApplySurfaceResponse(region, product) && _activeSurfaceGradient()) {
                _renderSurfaceMarkers(_surfaceStations);
            }
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
        temperature_change_24h: [[-40, '#4c1d95'], [-30, '#312e81'], [-20, '#1d4ed8'], [-10, '#0ea5e9'], [0, '#f8fafc'], [10, '#f59e0b'], [20, '#ef4444'], [30, '#b91c1c'], [40, '#7f1d1d']],
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

    function renderContinuousLegend(title, axisLabel, anchors, ticks = null) {
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
            `<span>${escapeHtml(label ?? _formatSurfaceTick(value))}</span>`
        )).join('');

        return (
            `<h4>${escapeHtml(title)}</h4>` +
            `<div class="surface-colorbar">` +
            `<div class="surface-colorbar-bar" style="background: linear-gradient(to right, ${gradient});"></div>` +
            `<div class="surface-colorbar-ticks">${tickHtml}</div>` +
            `<div class="surface-colorbar-label">${escapeHtml(axisLabel)}</div>` +
            `</div>`
        );
    }

    function buildSurfaceLegend(unit, anchors, product) {
        if (!anchors?.length) {
            setLegend(null);
            return;
        }

        const label = _SURFACE_PRODUCT_LABELS[product] || product.replace(/_/g, ' ');
        const axisLabel = unit ? `${label} (${unit})` : label;
        setLegend(renderContinuousLegend(`Surface: ${label}`, axisLabel, anchors));
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
        if (_isTypeEnabled('rtma')) {
            const key = `${_activeRtmaRegion()}|${_activeRtmaStream()}|${_activeRtmaProduct()}`;
            if (_rtmaPointsAll.length && _rtmaPointsKey === key) _renderRtmaPoints();
            else _scheduleRtmaPointsLoad();
        }
        // Swap display geometry when crossing the zoom-bucket threshold (low ↔ high).
        // Full geometry (_allAlertFeatures) is unchanged; only the render layer is swapped.
        if (!_archiveMode && _isTypeEnabled('alerts') && _allAlertFeatures.length) {
            const newBucket = _alertsZoomBucket();
            if (newBucket !== _lastAlertsZoomBucket) {
                _lastAlertsZoomBucket = newBucket;
                _refreshAlertsDisplayLayer();
            }
        }
    });

    // ── MRMS layer ────────────────────────────────────────────────────────────

    // ── MRMS helpers ─────────────────────────────────────────────────────────
    function _activeMrmsProduct() {
        return document.querySelector('.mrms-product-check:checked')?.value || null;
    }

    function _activeRtmaStream() {
        return document.querySelector('.weather-rtma-stream:checked')?.value || null;
    }

    function _activeRtmaProduct() {
        return document.querySelector('.weather-rtma-product:checked')?.value || null;
    }

    function _syncRtmaProductForStream() {
        const stream = _activeRtmaStream();
        const delta24h = document.querySelector('.weather-rtma-product[value="temperature_change_24h"]');
        if (!delta24h) return;

        const supported = stream === 'rtma_hourly';
        delta24h.disabled = !supported;

        const row = delta24h.closest('.rtma-product-row');
        if (row) row.style.opacity = supported ? '' : '0.55';

        if (!supported && delta24h.checked) {
            delta24h.checked = false;
            const fallback = document.querySelector('.weather-rtma-product[value="temperature"]')
                || document.querySelector('.weather-rtma-product');
            if (fallback) fallback.checked = true;
            setStatus('24-hour temp change is only available on RTMA Hourly.');
        }
    }

    function _syncRtmaStreamForRegion() {
        const region = _activeRtmaRegion();
        const rapid = document.querySelector('.weather-rtma-stream[value="rtma_rapid_update"]');
        const hourly = document.querySelector('.weather-rtma-stream[value="rtma_hourly"]');
        if (!rapid) return;

        const rapidSupported = region === 'CONUS';
        rapid.disabled = !rapidSupported;

        if (!rapidSupported && rapid.checked) {
            rapid.checked = false;
            if (hourly) hourly.checked = true;
            setStatus('RTMA Rapid Update is only available for CONUS.');
        }
    }

    function _activeRtmaRegion() {
        const selectedRegion = String(byId('weather-region')?.value || 'CONUS').toUpperCase();
        // RTMA regions are CONUS, AK, HI, PR. For any state selection, load CONUS product
        const rtmaRegions = ['CONUS', 'AK', 'HI', 'PR'];
        return rtmaRegions.includes(selectedRegion) ? selectedRegion : 'CONUS';
    }

    let _lastMrmsWorkerProductSet = null;

    async function _setMrmsWorkerProduct(product) {
        if (!product) return;
        if (_lastMrmsWorkerProductSet === product) return;
        try {
            const resp = await fetch(apiUrl(`/api/mrms/set-product?product=${encodeURIComponent(product)}`));
            if (resp.ok) {
                _lastMrmsWorkerProductSet = product;
            }
        } catch (err) {
            console.warn('[mrms] Could not set worker active product:', err?.message || err);
        }
    }

    // composeMrmsProductKey: mirrors Python MRMS_PRODUCTS key structure
    function composeMrmsProductKey() {
        const family = _activeMrmsProduct();
        if (!family) return null;
        const standalone = ['PrecipRate', 'PrecipFlag', 'SHI', 'POSH', 'RadarQualityIndex'];
        if (standalone.includes(family)) return family;

        if (family === 'QPE') {
            const src = document.querySelector('input[name="mrms-qpe-source"]:checked')?.value || 'MS2';
            const per = document.querySelector('input[name="mrms-qpe-period"]:checked')?.value || '01H';
            return `QPE_${src}_${per}`;
        }
        if (family === 'RotationTrack') {
            const lvl = document.querySelector('input[name="mrms-rotation-level"]:checked')?.value || 'LL';
            const time = document.querySelector('input[name="mrms-rotation-time"]:checked')?.value || '60min';
            return `RotationTrack_${lvl}_${time}`;
        }
        if (family === 'MESH') {
            const t = document.querySelector('input[name="mrms-mesh-time"]:checked')?.value || 'Instant';
            return t === 'Instant' ? 'MESH_Instant' : `MESH_${t}`;
        }
        if (family === 'AzShear') {
            const lvl = document.querySelector('input[name="mrms-azshear-level"]:checked')?.value || 'Low';
            return `AzShear_${lvl}`;
        }
        if (family === 'EchoTop') {
            const thr = document.querySelector('input[name="mrms-echotop-threshold"]:checked')?.value || '18';
            return `EchoTop_${thr}`;
        }
        if (family === 'VIL') {
            const t = document.querySelector('input[name="mrms-vil-type"]:checked')?.value || 'Instant';
            return t === 'Instant' ? 'VIL_Instant' : `VIL_${t}`;
        }
        if (family === 'Reflectivity') {
            const v = document.querySelector('input[name="mrms-refl-variant"]:checked')?.value || 'HSR';
            return `Refl_${v}`;
        }
        if (family === 'Lightning') {
            const w = document.querySelector('input[name="mrms-lightning-window"]:checked')?.value || '30min';
            return `Lightning_${w}`;
        }
        if (family === 'Model') {
            const f = document.querySelector('input[name="mrms-model-field"]:checked')?.value || 'FreezingLevel';
            return `Model_${f}`;
        }
        return family;
    }

    // Show/hide sub-panels for the active MRMS product
    function updateMrmsSubControls() {
        const family = _activeMrmsProduct();
        document.querySelectorAll('.mrms-sub-panel').forEach((el) => { el.style.display = 'none'; });
        if (!family) return;
        const subMap = {
            QPE: 'mrms-sub-qpe', RotationTrack: 'mrms-sub-rotation',
            MESH: 'mrms-sub-mesh', AzShear: 'mrms-sub-azshear',
            EchoTop: 'mrms-sub-echotop', VIL: 'mrms-sub-vil',
            Reflectivity: 'mrms-sub-reflectivity', Lightning: 'mrms-sub-lightning',
            Model: 'mrms-sub-model',
        };
        const subId = subMap[family];
        if (subId) {
            const sub = byId(subId);
            if (sub) sub.style.display = '';
        }
    }

    async function loadMrms() {
        const MRMS_STALE_MS = 90 * 60 * 1000;
        const requestSeq = ++_mrmsRequestSeq;
        const product = composeMrmsProductKey();
        if (!product) return;

        const statusEl = byId('weather-mrms-status');
        if (statusEl) statusEl.textContent = `Loading ${product}...`;
        setStatus(`Loading MRMS ${product}...`);

        try {
            // Keep the backend worker aligned to the current UI MRMS key.
            await _setMrmsWorkerProduct(product);

            // ── Try pre-rendered overlay first (populated by mrms_worker) ───
            let data = null;
            const overlayResp = await fetch(
                apiUrl(`/api/overlay/latest?family=mrms&region=CONUS&stream=default&product=${encodeURIComponent(product)}`)
            );
            if (overlayResp.ok) {
                const overlayData = await overlayResp.json();
                // Normalise to the shape expected by the rest of this handler.
                data = {
                    image_url: (overlayData?.render?.image_url) ?? '',
                    bounds: overlayData?.bounds ?? [],
                    legend: overlayData?.legend ?? null,
                    full_name: overlayData?.full_name ?? product,
                    units: overlayData?.units ?? '',
                    vmin: overlayData?.vmin ?? null,
                    vmax: overlayData?.vmax ?? null,
                    timestamp: overlayData?.timestamp ?? null,
                };

                const overlayTsMs = _asDate(data?.timestamp)?.getTime() || 0;
                const overlayIsStale = !overlayTsMs || (Date.now() - overlayTsMs) > MRMS_STALE_MS;
                if (overlayIsStale) {
                    // If cached overlay is stale, force a fresh on-demand path.
                    data = null;
                }
            }

            // ── Fall back to legacy on-demand endpoint (cold cache / stale cache / 404) ───
            if (!data || !data.image_url) {
                const bounds = map.getBounds();
                const s = bounds.getSouth().toFixed(4);
                const w = bounds.getWest().toFixed(4);
                const n = bounds.getNorth().toFixed(4);
                const e = bounds.getEast().toFixed(4);
                const legacyResp = await fetch(
                    apiUrl(`/api/data/mrms?product=${encodeURIComponent(product)}&south=${s}&west=${w}&north=${n}&east=${e}`)
                );
                if (!legacyResp.ok) {
                    const err = await legacyResp.json().catch(() => ({ detail: legacyResp.statusText }));
                    throw new Error(err.detail || legacyResp.statusText);
                }
                data = await legacyResp.json();
            }

            if (requestSeq !== _mrmsRequestSeq || !_canApplyMrmsResponse()) return;

            if (mrmsOverlay) { map.removeLayer(mrmsOverlay); mrmsOverlay = null; }

            // Leaflet imageOverlay: [[south, west], [north, east]]
            const b = data.bounds; // [west, east, south, north]
            const leafletBounds = [[b[2], b[0]], [b[3], b[1]]];
            mrmsOverlay = L.imageOverlay(apiUrl(data.image_url), leafletBounds, { opacity: mrmsOpacity });
            if (_activeMrmsProduct()) mrmsOverlay.addTo(map);
            _syncMrmsRadarSiteOverlay(b);

            buildMrmsLegend(data);

            const dataTsMs = _resolveDataTimestampMs(data?.timestamp);
            const staleNote = _staleNoteForTimestamp(dataTsMs, MRMS_STALE_MS);

            if (statusEl) statusEl.textContent = `${data.full_name} valid ${_formatValidTimeLabel(dataTsMs)}${staleNote}`;
            setStatus(`MRMS ${product} valid ${_formatValidTimeLabel(dataTsMs)}.${staleNote}`);
            _setViewerTimestamp(dataTsMs);
            _setReliability('mrms', `MRMS ${product}`, 'NOAA MRMS', dataTsMs);
            _setTimestampSource('mrms', data?.timestamp_source || 'grib_data_timestamp', dataTsMs);
        } catch (err) {
            if (requestSeq !== _mrmsRequestSeq) return;
            console.error('[mrms] Load error:', err);
            if (statusEl) statusEl.textContent = `Error: ${err.message}`;
            setStatus(`MRMS error: ${err.message}`);
        }
    }

    function buildRtmaLegend(data) {
        if (!_isTypeEnabled('rtma')) return;
        const legend = data?.legend;
        const title = escapeHtml(data?.full_name || 'RTMA');
        const units = escapeHtml(data?.units || '');
        const anchors = Array.isArray(legend?.anchors) ? legend.anchors : [];
        if (anchors.length) {
            const axisLabel = units ? `${title} (${units})` : title;
            setLegend(renderContinuousLegend(`RTMA: ${title}`, axisLabel, anchors));
            return;
        }
        const range = Number.isFinite(Number(data?.vmin)) && Number.isFinite(Number(data?.vmax))
            ? `<div class="mrms-legend-units">${escapeHtml(String(data.vmin))} to ${escapeHtml(String(data.vmax))} ${units}</div>`
            : '';
        setLegend(`<div class="mrms-legend-head"><h4>${title}</h4></div>${range}`);
    }

    function _rtmaStaleThresholdMs(stream, product) {
        if (stream === 'rtma_rapid_update') return 3 * 60 * 60 * 1000;
        return 12 * 60 * 60 * 1000;
    }

    async function loadRtma() {
        const requestSeq = ++_rtmaRequestSeq;
        const region = _activeRtmaRegion();
        const stream = _activeRtmaStream();
        const product = _activeRtmaProduct();
        if (!region || !stream || !product) return;

        setStatus(`Loading ${region} ${stream} ${product}...`);

        // ── Try the pre-rendered overlay first ────────────────────────────────
        // Wind direction has no scalar gradient overlay — barb arrows only.
        let usedPrerender = false;
        let pointsSourceDataKey = '';
        try {
            if (product === 'wind_direction') throw new Error('no-overlay');
            const overlayResp = await fetch(
                apiUrl(`/api/overlay/latest?family=rtma&region=${encodeURIComponent(region)}&stream=${encodeURIComponent(stream)}&product=${encodeURIComponent(product)}`)
            );

            if (overlayResp.ok) {
                const overlayData = await overlayResp.json();
                if (requestSeq !== _rtmaRequestSeq || !_canApplyRtmaResponse()) return;

                const imageUrl = overlayData?.render?.image_url;
                const bounds = overlayData?.bounds; // [west, east, south, north]
                pointsSourceDataKey = (typeof overlayData?.source_data_key === 'string')
                    ? overlayData.source_data_key
                    : '';

                if (imageUrl && Array.isArray(bounds) && bounds.length === 4) {
                    if (rtmaGradientLayer) { map.removeLayer(rtmaGradientLayer); rtmaGradientLayer = null; }
                    if (rtmaOverlay) { map.removeLayer(rtmaOverlay); rtmaOverlay = null; }

                    const leafletBounds = [[bounds[2], bounds[0]], [bounds[3], bounds[1]]];
                    rtmaGradientLayer = L.imageOverlay(apiUrl(imageUrl), leafletBounds, {
                        opacity: rtmaGradientOpacity,
                        className: 'surface-gradient-overlay',
                    });
                    if (_isTypeEnabled('rtma')) rtmaGradientLayer.addTo(map);

                    buildRtmaLegend(overlayData);

                    const dataTsMs = _resolveDataTimestampMs(overlayData?.timestamp);
                    const staleNote = _staleNoteForTimestamp(
                        dataTsMs,
                        _rtmaStaleThresholdMs(stream, product)
                    );
                    const title = overlayData?.full_name || product;
                    setStatus(`RTMA ${title} valid ${_formatValidTimeLabel(dataTsMs)}${staleNote}.`);
                    _setViewerTimestamp(dataTsMs);
                    _setReliability('rtma', `RTMA ${title}`, `NOAA ${stream}`, dataTsMs);
                    _setTimestampSource('rtma', 'overlay_meta_timestamp', dataTsMs);
                    usedPrerender = true;
                }
            }
        } catch (_preErr) {
            // Pre-render fetch failed — fall through to on-demand path below.
        }

        // ── Fallback to on-demand RTMA overlay render if cache is missing ───
        if (!usedPrerender && product !== 'wind_direction') {
            try {
                const viewBounds = map.getBounds();
                const south = Number(viewBounds.getSouth()).toFixed(4);
                const west = Number(viewBounds.getWest()).toFixed(4);
                const north = Number(viewBounds.getNorth()).toFixed(4);
                const east = Number(viewBounds.getEast()).toFixed(4);
                const dataResp = await fetch(
                    apiUrl(
                        `/api/data/rtma?region=${encodeURIComponent(region)}&stream=${encodeURIComponent(stream)}` +
                        `&product=${encodeURIComponent(product)}&south=${south}&west=${west}&north=${north}&east=${east}`
                    )
                );
                if (dataResp.ok) {
                    const data = await dataResp.json();
                    if (requestSeq !== _rtmaRequestSeq || !_canApplyRtmaResponse()) return;

                    if (rtmaGradientLayer) { map.removeLayer(rtmaGradientLayer); rtmaGradientLayer = null; }
                    if (rtmaOverlay) { map.removeLayer(rtmaOverlay); rtmaOverlay = null; }

                    const bounds = data?.bounds;
                    const imageUrl = data?.image_url;
                    pointsSourceDataKey = (typeof data?.source_data_key === 'string')
                        ? data.source_data_key
                        : '';

                    if (imageUrl && Array.isArray(bounds) && bounds.length === 4) {
                        const leafletBounds = [[bounds[2], bounds[0]], [bounds[3], bounds[1]]];
                        rtmaGradientLayer = L.imageOverlay(apiUrl(imageUrl), leafletBounds, {
                            opacity: rtmaGradientOpacity,
                            className: 'surface-gradient-overlay',
                        });
                        if (_isTypeEnabled('rtma')) rtmaGradientLayer.addTo(map);

                        buildRtmaLegend(data);

                        const dataTsMs = _resolveDataTimestampMs(data?.timestamp);
                        const staleNote = _staleNoteForTimestamp(
                            dataTsMs,
                            _rtmaStaleThresholdMs(stream, product)
                        );
                        const title = data?.full_name || product;
                        setStatus(`RTMA ${title} valid ${_formatValidTimeLabel(dataTsMs)}${staleNote}.`);
                        _setViewerTimestamp(dataTsMs);
                        _setReliability('rtma', `RTMA ${title}`, `NOAA ${stream}`, dataTsMs);
                        _setTimestampSource('rtma', data?.timestamp_source || 'rtma_data_endpoint', dataTsMs);
                        usedPrerender = true;
                    }
                }
            } catch (_fallbackErr) {
                // If this also fails, points-only fallback below still runs.
            }
        }

        // ── Always load value-point markers (dynamic, not baked into raster) ──

        try {
            const url = apiUrl(
                `/api/data/rtma/points?region=${encodeURIComponent(region)}&stream=${encodeURIComponent(stream)}&product=${encodeURIComponent(product)}`
                + (pointsSourceDataKey ? `&source_data_key=${encodeURIComponent(pointsSourceDataKey)}` : '')
            );
            const resp = await fetch(url);
            if (!resp.ok) {
                const err = await resp.json().catch(() => ({ detail: resp.statusText }));
                throw new Error(err.detail || resp.statusText);
            }
            const data = await resp.json();

            if (requestSeq !== _rtmaRequestSeq || !_canApplyRtmaResponse()) return;

            // Only clear the overlay if we're still using the on-demand canvas path.
            if (!usedPrerender && rtmaOverlay) { map.removeLayer(rtmaOverlay); rtmaOverlay = null; }

            _rtmaPointsAll = Array.isArray(data.points) ? data.points : [];
            _rtmaPointsUnits = data.units || '';
            _rtmaPointsKey = `${region}|${stream}|${product}|${pointsSourceDataKey || 'latest'}`;
            _lastRtmaPointsFetchKey = _rtmaPointsKey;
            _lastRtmaPointsFetchMs = Date.now();

            // Render value markers regardless of whether the pre-rendered raster
            // was applied. When cache is available the PNG overlay is already on
            // the map; when not yet built we show markers only (no canvas gradient).
            _renderRtmaPoints();

            if (usedPrerender) {
                // Legend + status already set from overlay meta above.
            } else {
                // Cache not yet built for this product — show markers-only notice.
                buildRtmaLegend(data);
                const dataTsMs = _resolveDataTimestampMs(data?.timestamp);
                const title = data?.full_name || product;
                setStatus(`RTMA ${title} — overlay cache not yet built (markers only).`);
                _setViewerTimestamp(dataTsMs);
                _setReliability('rtma', `RTMA ${title}`, `NOAA ${stream}`, dataTsMs);
                _setTimestampSource('rtma', data?.timestamp_source || 'points_source_timestamp', dataTsMs);
            }
        } catch (err) {
            if (requestSeq !== _rtmaRequestSeq) return;
            console.error('[rtma] Load error:', err);
            if (!usedPrerender) {
                if (rtmaGradientLayer && map.hasLayer(rtmaGradientLayer)) { map.removeLayer(rtmaGradientLayer); rtmaGradientLayer = null; }
                if (rtmaPointLayer && map.hasLayer(rtmaPointLayer)) { map.removeLayer(rtmaPointLayer); rtmaPointLayer = null; }
                setLegend(null);
                setStatus(`RTMA error: ${err.message}`);
            }
        }
    }

    function _scheduleRtmaPointsLoad(delayMs = RTMA_POINTS_DEBOUNCE_MS, forceReload = false) {
        if (_rtmaPointsDebounceTimer) clearTimeout(_rtmaPointsDebounceTimer);
        _rtmaPointsDebounceTimer = setTimeout(() => {
            _rtmaPointsDebounceTimer = null;
            loadRtmaPoints(forceReload);
        }, Math.max(0, delayMs));
    }

    function _thinRtmaPoints(points) {
        if (!Array.isArray(points) || !points.length) return [];
        const zoom = map.getZoom();
        const region = (byId('weather-region')?.value || '').toUpperCase();
        const minDistKm = _baseDistKm(zoom, region) / _surfaceDensity;
        const bounds = map.getBounds();
        const inView = points.filter((p) => bounds.contains([p.lat, p.lon]));
        return _filterByMinDistKm(inView, p => p.lat, p => p.lon, minDistKm);
    }

    function _renderRtmaPoints() {
        // Gradient is now pre-rendered server-side and applied as an imageOverlay
        // in loadRtma() / _renderRtmaScrubFrame(). This function only renders
        // the optional city-value markers on top.
        if (rtmaPointLayer) { map.removeLayer(rtmaPointLayer); rtmaPointLayer = null; }
        if (!_rtmaPointsAll.length) return;

        if (byId('weather-rtma-show-values')?.checked) {
            const isWindDir = _rtmaPointsUnits === 'deg';
            const rtmaProduct = _activeRtmaProduct();
            const integerLabelProducts = new Set(['temperature', 'dew_point']);
            const useIntegerLabels = integerLabelProducts.has(rtmaProduct);
            const thin = _thinRtmaPoints(_rtmaPointsAll);
            if (thin.length) {
                const markers = thin.map(p => {
                    const icon = isWindDir
                        ? windDirectionBarbIcon(p.value, 0.9)
                        : surfaceColoredTextIcon(p.value, _rtmaPointsUnits, 0.9, useIntegerLabels);
                    return L.marker([p.lat, p.lon], { icon });
                });
                rtmaPointLayer = L.layerGroup(markers);
                if (_isTypeEnabled('rtma')) rtmaPointLayer.addTo(map);
            }
        }
    }

    async function loadRtmaPoints(forceReload = false) {
        if (!byId('weather-rtma-show-values')?.checked) {
            if (rtmaPointLayer) { map.removeLayer(rtmaPointLayer); rtmaPointLayer = null; }
            return;
        }
        const requestSeq = ++_rtmaPointsSeq;
        const region = _activeRtmaRegion();
        const stream = _activeRtmaStream();
        const product = _activeRtmaProduct();
        if (!region || !stream || !product) return;

        const queryKey = `${region}|${stream}|${product}`;
        const now = Date.now();

        if (!forceReload && _rtmaPointsKey === queryKey && _rtmaPointsAll.length) {
            _renderRtmaPoints();
            return;
        }

        if (_rtmaPointsInFlightKey === queryKey) {
            return;
        }
        if (
            !forceReload
            &&
            _lastRtmaPointsFetchKey === queryKey
            && now - _lastRtmaPointsFetchMs < RTMA_POINTS_MIN_FETCH_INTERVAL_MS
        ) {
            if (_rtmaPointsKey === queryKey && _rtmaPointsAll.length) _renderRtmaPoints();
            return;
        }

        try {
            _rtmaPointsInFlightKey = queryKey;
            const url = apiUrl(
                `/api/data/rtma/points?region=${encodeURIComponent(region)}&stream=${encodeURIComponent(stream)}&product=${encodeURIComponent(product)}`
            );
            const resp = await fetch(url);
            if (!resp.ok) {
                const err = await resp.json().catch(() => ({ detail: resp.statusText }));
                throw new Error(err.detail || resp.statusText);
            }
            const data = await resp.json();
            if (requestSeq !== _rtmaPointsSeq || !_canApplyRtmaResponse()) return;
            _rtmaPointsAll = Array.isArray(data.points) ? data.points : [];
            _rtmaPointsUnits = data.units || '';
            _rtmaPointsKey = queryKey;
            _renderRtmaPoints();
            _lastRtmaPointsFetchKey = queryKey;
            _lastRtmaPointsFetchMs = Date.now();
        } catch (err) {
            if (requestSeq !== _rtmaPointsSeq) return;
            console.error('[rtma points] Load error:', err);
        } finally {
            if (_rtmaPointsInFlightKey === queryKey) _rtmaPointsInFlightKey = null;
        }
    }

    /**
     * Formerly fetched GRIB-subgrid data for canvas gradient rendering.
     * Gradients are now pre-rendered server-side as PNG overlays; this
     * function is intentionally disabled.
     */
    function loadRtmaGrid() {
        // No-op: on-demand canvas gradient generation removed.
        // Overlay PNGs are served from the pre-render cache instead.
    }

    function _setRtmaScrubberStatus(message) {
        const el = byId('wx-scrubber-status');
        if (!el) return;
        const text = message || '';
        el.textContent = text;
        el.style.display = text ? 'block' : 'none';
    }

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

    function _setScrubberControlsEnabled(enabled) {
        [
            'scrubber-step-back',
            'scrubber-play',
            'scrubber-step-fwd',
            'scrubber-speed-down',
            'scrubber-speed-up',
            'scrubber-slider',
        ].forEach((id) => {
            const el = byId(id);
            if (el) el.disabled = !enabled;
        });
    }

    function _updateRtmaScrubberUi() {
        const slider = byId('scrubber-slider');
        const tsEl = byId('scrubber-timestamp');
        const cntEl = byId('scrubber-frame-count');
        const activeFrames = (_radarScrubMode && !_radarScrubIsTimeMode)
            ? _radarScrubFrames
            : (_mrmsScrubMode ? _mrmsScrubFrames : (_satelliteScrubMode ? _satelliteFrames : _rtmaScrubFrames));
        const activeIndex = _radarScrubMode
            ? _radarScrubFrameIndex
            : (_mrmsScrubMode ? _mrmsScrubFrameIndex : (_satelliteScrubMode ? _satelliteFrameIndex : _rtmaScrubFrameIndex));
        const n = (_radarScrubMode && _radarScrubIsTimeMode)
            ? _radarScrubTimelineMs.length
            : activeFrames.length;
        if (slider) {
            slider.min = '0';
            slider.max = String(n > 0 ? n - 1 : 0);
            slider.value = String(activeIndex);
        }
        if (cntEl) cntEl.textContent = n > 0 ? `${activeIndex + 1}/${n}` : '0/0';
        if (!n) {
            if (tsEl) tsEl.textContent = 'No frames found';
            return;
        }
        if (_radarScrubMode && _radarScrubIsTimeMode) {
            const tickMs = _radarScrubTimelineMs[activeIndex];
            if (tsEl) {
                if (Number.isFinite(tickMs)) {
                    try {
                        tsEl.textContent = new Date(tickMs).toLocaleString(undefined, {
                            month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
                            timeZone: 'UTC', timeZoneName: 'short',
                        });
                    } catch {
                        tsEl.textContent = String(tickMs);
                    }
                } else {
                    tsEl.textContent = '--';
                }
            }
            return;
        }
        const frame = activeFrames[activeIndex];
        const frameTs = frame?.timestamp || frame?.timestamp_utc || frame?.frame_key || null;
        if (tsEl) {
            try {
                tsEl.textContent = new Date(frameTs).toLocaleString(undefined, {
                    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZoneName: 'short',
                });
            } catch {
                tsEl.textContent = frameTs || '--';
            }
        }
    }

    function _stopRtmaScrubPlay() {
        if (_rtmaScrubPlayTimer) {
            clearInterval(_rtmaScrubPlayTimer);
            _rtmaScrubPlayTimer = null;
        }
        const btn = byId('scrubber-play');
        if (btn) btn.textContent = '▶';
    }

    function _startRtmaScrubPlay() {
        if (!_rtmaScrubFrames.length || _rtmaScrubPlayTimer) return;
        const btn = byId('scrubber-play');
        if (btn) btn.textContent = '⏸';

        const tick = async () => {
            if (!_rtmaScrubPlayTimer || !_rtmaScrubFrames.length) return;
            const atLast = _rtmaScrubFrameIndex >= _rtmaScrubFrames.length - 1;

            if (atLast) {
                // Pause on the last frame before restarting
                if (!_rtmaScrubPlayTimer || !_rtmaScrubFrames.length) return;
                _rtmaScrubPlayTimer = setTimeout(async () => {
                    if (_rtmaScrubPlayTimer) {
                        await _renderRtmaScrubFrame(0);
                        if (_rtmaScrubPlayTimer) {
                            _rtmaScrubPlayTimer = setTimeout(tick, _scrubberPlaybackDelay(RTMA_SCRUB_PLAY_INTERVAL_MS));
                        }
                    }
                }, _scrubberPlaybackDelay(RTMA_SCRUB_LOOP_HOLD_MS, 350));
            } else {
                // Advance to next frame
                const next = _rtmaScrubFrameIndex + 1;
                await _renderRtmaScrubFrame(next);
                if (!_rtmaScrubPlayTimer || !_rtmaScrubFrames.length) return;
                _rtmaScrubPlayTimer = setTimeout(tick, _scrubberPlaybackDelay(RTMA_SCRUB_PLAY_INTERVAL_MS));
            }
        };

        _rtmaScrubPlayTimer = setTimeout(tick, _scrubberPlaybackDelay(RTMA_SCRUB_PLAY_INTERVAL_MS));
    }

    function _canApplyRtmaScrubResponse(renderSeq) {
        return renderSeq === _rtmaScrubRenderSeq
            && _rtmaScrubMode
            && _isTypeEnabled('rtma');
    }

    function _exitRtmaScrubMode(shouldRefresh = true) {
        _stopRtmaScrubPlay();
        _rtmaScrubLoadSeq += 1;
        _rtmaScrubRenderSeq += 1;
        _rtmaScrubMode = false;
        _rtmaScrubFrames = [];
        _rtmaScrubFrameIndex = 0;
        _rtmaScrubFrameCache.clear();
        _setArchiveProgress(false);
        _setArchiveScrubber(false);
        _setScrubberControlsEnabled(false);
        _setRtmaScrubberStatus('');
        byId('weather-rtma-load-scrubber')?.classList.remove('active');
        byId('weather-mode-current')?.classList.add('active');
        const rtmaWin = byId('rtma-animate-window');
        const mrmsWin = byId('mrms-animate-window');
        if (rtmaWin) rtmaWin.style.display = 'none';
        if (mrmsWin) mrmsWin.style.display = 'none';
        if (shouldRefresh) {
            refreshActiveLayers();
        }
    }

    function _stopMrmsScrubPlay() {
        if (_mrmsScrubPlayTimer) {
            clearInterval(_mrmsScrubPlayTimer);
            _mrmsScrubPlayTimer = null;
        }
        const btn = byId('scrubber-play');
        if (btn) btn.textContent = '▶';
    }

    function _startMrmsScrubPlay() {
        if (!_mrmsScrubFrames.length || _mrmsScrubPlayTimer) return;
        const btn = byId('scrubber-play');
        if (btn) btn.textContent = '⏸';

        const tick = async () => {
            if (!_mrmsScrubPlayTimer || !_mrmsScrubFrames.length) return;
            const atLast = _mrmsScrubFrameIndex >= _mrmsScrubFrames.length - 1;

            if (atLast) {
                // Pause on the last frame before restarting
                if (!_mrmsScrubPlayTimer || !_mrmsScrubFrames.length) return;
                _mrmsScrubPlayTimer = setTimeout(async () => {
                    if (_mrmsScrubPlayTimer) {
                        await _renderMrmsScrubFrame(0);
                        if (_mrmsScrubPlayTimer) {
                            _mrmsScrubPlayTimer = setTimeout(tick, _scrubberPlaybackDelay(RTMA_SCRUB_PLAY_INTERVAL_MS));
                        }
                    }
                }, _scrubberPlaybackDelay(RTMA_SCRUB_LOOP_HOLD_MS, 350));
            } else {
                // Advance to next frame
                const next = _mrmsScrubFrameIndex + 1;
                await _renderMrmsScrubFrame(next);
                if (!_mrmsScrubPlayTimer || !_mrmsScrubFrames.length) return;
                _mrmsScrubPlayTimer = setTimeout(tick, _scrubberPlaybackDelay(RTMA_SCRUB_PLAY_INTERVAL_MS));
            }
        };

        _mrmsScrubPlayTimer = setTimeout(tick, _scrubberPlaybackDelay(RTMA_SCRUB_PLAY_INTERVAL_MS));
    }

    function _canApplyMrmsScrubResponse(renderSeq) {
        return renderSeq === _mrmsScrubRenderSeq
            && _mrmsScrubMode
            && _isTypeEnabled('mrms');
    }

    function _exitMrmsScrubMode(shouldRefresh = true) {
        _stopMrmsScrubPlay();
        _mrmsScrubLoadSeq += 1;
        _mrmsScrubRenderSeq += 1;
        _mrmsScrubMode = false;
        _mrmsScrubFrames = [];
        _mrmsScrubFrameIndex = 0;
        _setArchiveProgress(false);
        _setArchiveScrubber(false);
        _setScrubberControlsEnabled(false);
        _setRtmaScrubberStatus('');
        byId('weather-rtma-load-scrubber')?.classList.remove('active');
        byId('weather-mode-current')?.classList.add('active');
        const rtmaWin = byId('rtma-animate-window');
        const mrmsWin = byId('mrms-animate-window');
        if (rtmaWin) rtmaWin.style.display = 'none';
        if (mrmsWin) mrmsWin.style.display = 'none';
        if (shouldRefresh) {
            refreshActiveLayers();
        }
    }

    async function _fetchRtmaFramePayload(frame) {
        // Use the stream/region/product embedded in the frame object, not the
        // live UI selectors. This prevents a mismatch when the user changes
        // the stream/product after the scrubber frames were loaded.
        const region = frame.region || _activeRtmaRegion();
        const stream = frame.stream || _activeRtmaStream();
        const product = frame.product || _activeRtmaProduct();
        const cacheKey = `${region}|${stream}|${product}|${frame.source_data_key || frame.frame_key}`;
        const existing = _rtmaScrubFrameCache.get(cacheKey);
        if (existing) return existing;

        const pointsUrl = apiUrl(
            `/api/data/rtma/points?region=${encodeURIComponent(region)}&stream=${encodeURIComponent(stream)}` +
            `&product=${encodeURIComponent(product)}` +
            (frame.source_data_key ? `&source_data_key=${encodeURIComponent(frame.source_data_key)}` : '')
        );

        // ── Try pre-rendered overlay first (instant — no GRIB parsing) ────────
        if (!RTMA_SCRUB_POINTS_ONLY && frame.frame_key) {
            try {
                const [preResp, pointsResp] = await Promise.all([
                    fetch(apiUrl(
                        `/api/overlay/latest?family=rtma&region=${encodeURIComponent(region)}` +
                        `&stream=${encodeURIComponent(stream)}&product=${encodeURIComponent(product)}` +
                        `&frame_key=${encodeURIComponent(frame.frame_key)}`
                    )),
                    fetch(pointsUrl),
                ]);
                if (preResp.ok) {
                    const overlayData = await preResp.json();
                    const pointsData = pointsResp.ok ? await pointsResp.json() : null;
                    // Normalise to the same payload shape as the on-demand path.
                    const payload = {
                        overlay: {
                            image_url: (overlayData.render || {}).image_url,
                            bounds: overlayData.bounds,
                            full_name: overlayData.full_name,
                            units: overlayData.units,
                            legend: overlayData.legend,
                            timestamp: overlayData.timestamp,
                        },
                        points: pointsData,
                        _fromPrerender: true,
                    };
                    _rtmaScrubFrameCache.set(cacheKey, payload);
                    return payload;
                }
                // 404 → pre-render not yet cached for this frame.
                // Fall through to points-only (no canvas gradient).
            } catch (_preErr) {
                // Network error — fall through to points-only.
            }
        }

        // ── Cache miss: fetch city-point markers only (no GRIB render) ──────
        // The pre-rendered PNG for this frame is not yet available. Show value
        // markers without a raster overlay rather than triggering on-demand
        // server-side GRIB parsing.
        try {
            const pointsResp = await fetch(pointsUrl);
            if (!pointsResp.ok) {
                const err = await pointsResp.json().catch(() => ({ detail: pointsResp.statusText }));
                throw new Error(err.detail || pointsResp.statusText);
            }
            const pointsData = await pointsResp.json();
            const payload = { overlay: null, points: pointsData, _fromPrerender: false };
            _rtmaScrubFrameCache.set(cacheKey, payload);
            return payload;
        } catch (err) {
            throw err;
        }
    }

    async function _renderRtmaScrubFrame(index) {
        if (!_rtmaScrubFrames.length || !_rtmaScrubMode || !_isTypeEnabled('rtma')) return;
        _rtmaScrubFrameIndex = Math.max(0, Math.min(index, _rtmaScrubFrames.length - 1));
        _updateRtmaScrubberUi();
        const renderSeq = ++_rtmaScrubRenderSeq;

        const frame = _rtmaScrubFrames[_rtmaScrubFrameIndex];
        try {
            const payload = await _fetchRtmaFramePayload(frame);
            if (!_canApplyRtmaScrubResponse(renderSeq)) return;
            const data = payload.overlay || payload.points || {};
            const pointsData = payload.points;

            // Preload the new image into the browser cache before swapping layers.
            // Without this the new imageOverlay is transparent until the PNG arrives,
            // causing a visible blink even if we add-before-remove.
            const oldGradientLayer = rtmaGradientLayer;
            let newGradientLayer = null;
            const imageUrl = data?.image_url || (payload._fromPrerender ? data?.image_url : null);
            const imageBounds = data?.bounds;
            if (!RTMA_SCRUB_POINTS_ONLY && imageUrl && Array.isArray(imageBounds)) {
                await new Promise((resolve) => {
                    const img = new Image();
                    img.onload = resolve;
                    img.onerror = resolve; // still swap on error rather than freezing
                    img.src = apiUrl(imageUrl);
                });
                if (!_canApplyRtmaScrubResponse(renderSeq)) return;
                const b = imageBounds;
                const leafletBounds = [[b[2], b[0]], [b[3], b[1]]];
                newGradientLayer = L.imageOverlay(apiUrl(imageUrl), leafletBounds, {
                    opacity: oldGradientLayer ? 0 : rtmaGradientOpacity,
                    className: 'surface-gradient-overlay',
                });
                // Image is already in browser cache — add new then remove old for instant swap.
                if (_isTypeEnabled('rtma')) newGradientLayer.addTo(map);

            }

            if (rtmaOverlay) { map.removeLayer(rtmaOverlay); rtmaOverlay = null; }
            if (oldGradientLayer && oldGradientLayer !== newGradientLayer) {
                if (newGradientLayer && _isTypeEnabled('rtma')) {
                    const applied = await _crossfadeOverlays(
                        oldGradientLayer,
                        newGradientLayer,
                        rtmaGradientOpacity,
                        () => _isTypeEnabled('rtma'),
                        () => _canApplyRtmaScrubResponse(renderSeq),
                        RADAR_CROSSFADE_MS,
                    );
                    if (!applied) return;
                } else if (map.hasLayer(oldGradientLayer)) {
                    map.removeLayer(oldGradientLayer);
                }
            }
            rtmaGradientLayer = newGradientLayer;

            _rtmaPointsAll = Array.isArray(pointsData?.points) ? pointsData.points : [];
            _rtmaPointsUnits = pointsData?.units || '';
            _rtmaPointsKey = `${frame.region || _activeRtmaRegion()}|${frame.stream || _activeRtmaStream()}|${frame.product || _activeRtmaProduct()}`;

            // Render value markers on top of the raster.
            if (rtmaPointLayer) { map.removeLayer(rtmaPointLayer); rtmaPointLayer = null; }
            if (byId('weather-rtma-show-values')?.checked && _rtmaPointsAll.length) {
                const isWindDir = _rtmaPointsUnits === 'deg';
                const rtmaProduct = frame.product || _activeRtmaProduct();
                const integerLabelProducts = new Set(['temperature', 'dew_point']);
                const useIntegerLabels = integerLabelProducts.has(rtmaProduct);
                const thin = _thinRtmaPoints(_rtmaPointsAll);
                if (thin.length) {
                    const markers = thin.map(p => {
                        const icon = isWindDir
                            ? windDirectionBarbIcon(p.value, 0.9)
                            : surfaceColoredTextIcon(p.value, _rtmaPointsUnits, 0.9, useIntegerLabels);
                        return L.marker([p.lat, p.lon], { icon });
                    });
                    rtmaPointLayer = L.layerGroup(markers);
                    if (_isTypeEnabled('rtma')) rtmaPointLayer.addTo(map);
                }
            }

            buildRtmaLegend(pointsData || data);
            const dataTsMs = _resolveDataTimestampMs(pointsData?.timestamp || data?.timestamp || frame.timestamp);
            const title = pointsData?.full_name || data?.full_name || frame.product || _activeRtmaProduct();
            const renderNote = payload._fromPrerender ? 'pre-rendered' : 'cache pending';
            setStatus(`RTMA scrub ${title} (${renderNote}) ${_formatValidTimeLabel(dataTsMs)}.`);
            _setViewerTimestamp(dataTsMs);
            _setReliability('rtma', `RTMA ${title}`, `NOAA ${frame.stream || _activeRtmaStream()}`, dataTsMs);
            _setTimestampSource('rtma', payload._fromPrerender ? 'overlay_meta_timestamp' : 'points_source_timestamp', dataTsMs);
            _setRtmaScrubberStatus(`${_rtmaScrubFrameIndex + 1} / ${_rtmaScrubFrames.length} frames.`);
        } catch (err) {
            if (!_canApplyRtmaScrubResponse(renderSeq)) return;
            console.error('[rtma scrub] Frame render error:', err);
            const frameKey = frame?.source_data_key || frame?.frame_key;
            if (frameKey) _rtmaScrubFrameErrors.add(frameKey);
            // Auto-skip to the next valid frame rather than freezing on error.
            const nextIndex = _rtmaScrubFrames.findIndex(
                (f, i) => i > _rtmaScrubFrameIndex && !_rtmaScrubFrameErrors.has(f.source_data_key)
            );
            if (nextIndex !== -1) {
                _setRtmaScrubberStatus(`Frame unavailable, skipping…`);
                _renderRtmaScrubFrame(nextIndex);
            } else {
                setStatus(`RTMA scrubber error: ${err.message}`);
                _setRtmaScrubberStatus(`Frame unavailable: ${err.message}`);
            }
        }
    }

    async function loadRtmaScrubberFrames() {
        if (_mrmsScrubMode) _exitMrmsScrubMode(false);
        const loadSeq = ++_rtmaScrubLoadSeq;
        const region = _activeRtmaRegion();
        const stream = _activeRtmaStream();
        const product = _activeRtmaProduct();
        if (!region || !stream || !product) {
            setStatus('Select an RTMA stream and product first.');
            return;
        }

        _rtmaScrubMode = true;
        _stopRtmaScrubPlay();
        _rtmaScrubRenderSeq += 1;
        _rtmaScrubFrames = [];
        _rtmaScrubFrameErrors.clear();
        _rtmaScrubFrameIndex = 0;
        _rtmaScrubFrameCache.clear();
        _setArchiveScrubber(true);
        _setArchiveProgress(true, 10, 'Loading RTMA frame list...');
        _setScrubberControlsEnabled(false);
        _updateRtmaScrubberUi();

        const streamMax = RTMA_STREAM_MAX_HOURS[stream] || 24;
        const rtmaSlider = document.querySelector('#rtma-animate-slider');
        const maxHours = Math.min(rtmaSlider ? Number(rtmaSlider.value) : streamMax, streamMax);
        const cutoffMs = Date.now() - maxHours * 60 * 60 * 1000;

        try {
            // ── Try pre-render cache first (disk read, instant) ───────────────
            let usedCache = false;
            try {
                const cacheUrl = apiUrl(
                    `/api/overlay/frames?family=rtma&region=${encodeURIComponent(region)}` +
                    `&stream=${encodeURIComponent(stream)}&product=${encodeURIComponent(product)}`
                );
                const cacheResp = await fetch(cacheUrl);
                if (loadSeq !== _rtmaScrubLoadSeq || !_rtmaScrubMode || !_isTypeEnabled('rtma')) return;
                if (cacheResp.ok) {
                    const cacheData = await cacheResp.json();
                    const rawFrames = Array.isArray(cacheData.frames) ? cacheData.frames : [];

                    // Filter to the selected time window and normalise shape.
                    const filtered = rawFrames.filter((f) => {
                        if (!f.timestamp) return true; // keep if no timestamp to filter on
                        const tsMs = _asDate(f.timestamp)?.getTime();
                        return !tsMs || tsMs >= cutoffMs;
                    });

                    if (filtered.length > 0) {
                        // Normalise: add region/stream/product so _fetchRtmaFramePayload
                        // doesn't need to fall back to the live UI selectors.
                        _rtmaScrubFrames = filtered.map((f) => ({
                            frame_key: f.frame_key,
                            source_data_key: f.source_data_key || '',
                            timestamp: f.timestamp || '',
                            region,
                            stream,
                            product,
                            // Pre-attach image_url and bounds so _renderRtmaScrubFrame
                            // can use them directly without a second API call when
                            // the image is already embedded in the frame list.
                            _image_url: f.image_url || null,
                            _bounds: f.bounds || null,
                        }));
                        usedCache = true;
                    }
                }
            } catch (_cacheErr) {
                // Cache fetch failed — fall through to S3 path.
            }

            // ── Fall back to S3 HEAD-check frame list ─────────────────────────
            if (!usedCache) {
                const url = apiUrl(
                    `/api/data/rtma/frames?region=${encodeURIComponent(region)}` +
                    `&stream=${encodeURIComponent(stream)}&product=${encodeURIComponent(product)}` +
                    `&max_hours=${encodeURIComponent(maxHours)}`
                );
                const resp = await fetch(url);
                if (loadSeq !== _rtmaScrubLoadSeq || !_rtmaScrubMode || !_isTypeEnabled('rtma')) return;
                if (!resp.ok) {
                    const err = await resp.json().catch(() => ({ detail: resp.statusText }));
                    throw new Error(err.detail || resp.statusText);
                }
                const data = await resp.json();
                _rtmaScrubFrames = Array.isArray(data.frames) ? data.frames : [];
            }

            if (loadSeq !== _rtmaScrubLoadSeq || !_rtmaScrubMode || !_isTypeEnabled('rtma')) return;

            if (!_rtmaScrubFrames.length) {
                _setArchiveProgress(false);
                _setArchiveScrubber(true);
                _setScrubberControlsEnabled(false);
                _updateRtmaScrubberUi();
                _setRtmaScrubberStatus('No frames found for selected product/stream/window.');
                setStatus('No RTMA frames found for the selected settings.');
                return;
            }

            _setArchiveProgress(false);
            _setScrubberControlsEnabled(true);
            const sourceLabel = usedCache ? 'pre-rendered cache' : 'S3';
            _setRtmaScrubberStatus(`${_rtmaScrubFrames.length} frames from ${sourceLabel} (${maxHours}h window).`);
            await _renderRtmaScrubFrame(0);
        } catch (err) {
            if (loadSeq !== _rtmaScrubLoadSeq || !_rtmaScrubMode || !_isTypeEnabled('rtma')) return;
            _setArchiveProgress(false);
            _setScrubberControlsEnabled(false);
            _setRtmaScrubberStatus(`Error: ${err.message}`);
            setStatus(`RTMA scrubber load error: ${err.message}`);
        }
    }

    async function _renderMrmsScrubFrame(index) {
        if (!_mrmsScrubFrames.length || !_mrmsScrubMode || !_isTypeEnabled('mrms')) return;
        _mrmsScrubFrameIndex = Math.max(0, Math.min(index, _mrmsScrubFrames.length - 1));
        _updateRtmaScrubberUi();
        const renderSeq = ++_mrmsScrubRenderSeq;

        const frame = _mrmsScrubFrames[_mrmsScrubFrameIndex];
        try {
            if (!_canApplyMrmsScrubResponse(renderSeq)) return;
            const oldOverlay = mrmsOverlay;
            let newOverlay = null;
            const imageUrl = frame?.image_url || '';
            const bounds = Array.isArray(frame?.bounds) ? frame.bounds : null;

            if (imageUrl && bounds && bounds.length === 4) {
                await new Promise((resolve) => {
                    const img = new Image();
                    img.onload = resolve;
                    img.onerror = resolve;
                    img.src = apiUrl(imageUrl);
                });
                if (!_canApplyMrmsScrubResponse(renderSeq)) return;

                const leafletBounds = [[bounds[2], bounds[0]], [bounds[3], bounds[1]]];
                newOverlay = L.imageOverlay(apiUrl(imageUrl), leafletBounds, {
                    opacity: oldOverlay ? 0 : mrmsOpacity,
                });
                if (_isTypeEnabled('mrms')) newOverlay.addTo(map);
            }

            if (oldOverlay && oldOverlay !== newOverlay) {
                if (newOverlay && _isTypeEnabled('mrms')) {
                    const applied = await _crossfadeOverlays(
                        oldOverlay,
                        newOverlay,
                        mrmsOpacity,
                        () => _isTypeEnabled('mrms'),
                        () => _canApplyMrmsScrubResponse(renderSeq),
                        RADAR_CROSSFADE_MS,
                    );
                    if (!applied) return;
                } else if (map.hasLayer(oldOverlay)) {
                    map.removeLayer(oldOverlay);
                }
            }
            mrmsOverlay = newOverlay;
            _syncMrmsRadarSiteOverlay(bounds);

            buildMrmsLegend(frame);
            const tsMs = _resolveDataTimestampMs(frame?.timestamp);
            const product = frame?.product || composeMrmsProductKey() || 'MRMS';
            setStatus(`MRMS scrub ${product} ${_formatValidTimeLabel(tsMs)}.`);
            _setViewerTimestamp(tsMs);
            _setReliability('mrms', `MRMS ${product}`, 'NOAA MRMS', tsMs);
            _setTimestampSource('mrms', 'overlay_frame_timestamp', tsMs);
            _setRtmaScrubberStatus(`${_mrmsScrubFrameIndex + 1} / ${_mrmsScrubFrames.length} frames.`);

            // Prefetch next 2 frames in parallel into browser cache (fire-and-forget)
            const prefetchCount = Math.min(2, _mrmsScrubFrames.length - _mrmsScrubFrameIndex - 1);
            const prefetchPromises = [];
            for (let i = 1; i <= prefetchCount; i++) {
                const nextFrame = _mrmsScrubFrames[_mrmsScrubFrameIndex + i];
                if (nextFrame?.image_url) {
                    prefetchPromises.push(
                        new Promise((resolve) => {
                            const img = new Image();
                            img.onload = resolve;
                            img.onerror = resolve;
                            img.src = apiUrl(nextFrame.image_url);
                        })
                    );
                }
            }
            Promise.all(prefetchPromises).catch(() => {}); // Silent fail
        } catch (err) {
            if (!_canApplyMrmsScrubResponse(renderSeq)) return;
            setStatus(`MRMS scrubber error: ${err.message}`);
            _setRtmaScrubberStatus(`Frame unavailable: ${err.message}`);
        }
    }

    async function loadMrmsScrubberFrames() {
        if (_rtmaScrubMode) _exitRtmaScrubMode(false);
        const loadSeq = ++_mrmsScrubLoadSeq;
        const product = composeMrmsProductKey();
        if (!product) {
            setStatus('Select an MRMS product first.');
            return;
        }

        await _setMrmsWorkerProduct(product);

        _mrmsScrubMode = true;
        _stopMrmsScrubPlay();
        _mrmsScrubRenderSeq += 1;
        _mrmsScrubFrames = [];
        _mrmsScrubFrameIndex = 0;
        _setArchiveScrubber(true);
        _setArchiveProgress(true, 10, 'Loading MRMS frame list...');
        _setScrubberControlsEnabled(false);
        _updateRtmaScrubberUi();

        const mrmsSlider = document.querySelector('#mrms-animate-slider');
        const maxHours = Math.max(1, mrmsSlider ? Number(mrmsSlider.value) : 1);
        const cutoffMs = Date.now() - maxHours * 60 * 60 * 1000;

        try {
            const url = apiUrl(`/api/overlay/frames?family=mrms&region=CONUS&stream=default&product=${encodeURIComponent(product)}`);
            const resp = await fetch(url);
            if (loadSeq !== _mrmsScrubLoadSeq || !_mrmsScrubMode || !_isTypeEnabled('mrms')) return;
            if (!resp.ok) {
                const err = await resp.json().catch(() => ({ detail: resp.statusText }));
                throw new Error(err.detail || resp.statusText);
            }

            const data = await resp.json();
            const rawFrames = Array.isArray(data.frames) ? data.frames : [];
            _mrmsScrubFrames = rawFrames
                .filter((f) => {
                    if (!f.timestamp) return true;
                    const tsMs = _asDate(f.timestamp)?.getTime();
                    return !tsMs || tsMs >= cutoffMs;
                })
                .map((f) => ({
                    frame_key: f.frame_key,
                    source_data_key: f.source_data_key || '',
                    image_url: f.image_url || '',
                    bounds: f.bounds || null,
                    timestamp: f.timestamp || '',
                    legend: f.legend || null,
                    full_name: f.full_name || product,
                    units: f.units || '',
                    vmin: f.vmin ?? null,
                    vmax: f.vmax ?? null,
                    product,
                }));

            if (loadSeq !== _mrmsScrubLoadSeq || !_mrmsScrubMode || !_isTypeEnabled('mrms')) return;
            if (!_mrmsScrubFrames.length) {
                _setArchiveProgress(false);
                _setArchiveScrubber(true);
                _setScrubberControlsEnabled(false);
                _updateRtmaScrubberUi();
                _setRtmaScrubberStatus('No MRMS frames found for selected window/product.');
                setStatus('No MRMS frames found for the selected settings.');
                return;
            }

            _setArchiveProgress(false);
            _setScrubberControlsEnabled(true);
            _setRtmaScrubberStatus(`${_mrmsScrubFrames.length} MRMS frames from cache (${maxHours}h window).`);
            await _renderMrmsScrubFrame(0);
        } catch (err) {
            if (loadSeq !== _mrmsScrubLoadSeq || !_mrmsScrubMode || !_isTypeEnabled('mrms')) return;
            _setArchiveProgress(false);
            _setScrubberControlsEnabled(false);
            _setRtmaScrubberStatus(`Error: ${err.message}`);
            setStatus(`MRMS scrubber load error: ${err.message}`);
        }
    }

    function buildMrmsLegend(data) {
        if (!_isTypeEnabled('mrms')) return;
        const legend = data?.legend;
        if (!legend) {
            const rows = [
                swatch('#b0d4f0', `≤ ${data.vmin} ${data.units}`),
                swatch('#ff4f4f', `≥ ${data.vmax} ${data.units}`),
            ].join('');
            setLegend(`<h4>${escapeHtml(data.full_name)}</h4>${rows}`);
            return;
        }

        const body = legend.kind === 'categorical'
            ? renderMrmsCategoricalLegend(legend)
            : renderMrmsScaleLegend(legend);
        setLegend(`${renderMrmsLegendTitle(legend)}${body}`);
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

    function _activeArchiveProduct() {
        // Returns the active archive-supported product type: 'mrms', 'alerts', 'spc', 'surface', or null.
        // Satellite is intentionally excluded (live-only type).
        if (_isTypeEnabled('mrms') && _activeMrmsProduct()) return 'mrms';
        if (_isTypeEnabled('alerts') && _getCheckedAlertCategories().length) return 'alerts';
        if (_isTypeEnabled('spc') && byId('weather-show-spc')?.checked) return 'spc';
        if (_isTypeEnabled('current') && _activeSurfaceProduct()) return 'surface';
        return null;
    }

    function enterArchiveMode() {
        _archiveMode = true;
        // Disable live radar overlay — it would show current radar against historical data
        _mrmsRadarOverlayStop();
        const radarCb = byId('weather-alerts-radar');
        if (radarCb && radarCb.checked) radarCb.dispatchEvent(new Event('change'));
        if (radarCb) radarCb.disabled = true;
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
        _mrmsRadarOverlayStop();
        const radarCb = byId('weather-alerts-radar');
        if (radarCb) radarCb.disabled = false;
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
            _setViewerTimestamp(frame?.timestamp || null);
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
            mrmsOverlay.setUrl(apiUrl(frame.image_url));
        } else {
            mrmsOverlay = L.imageOverlay(apiUrl(frame.image_url), leafletBounds, { opacity: mrmsOpacity });
            mrmsOverlay.addTo(map);
        }
        _syncMrmsRadarSiteOverlay(b);
    }

    function _renderArchiveGeoJsonFrame(frame, layerType) {
        const feats = frame?.features || [];

        if (layerType === 'alerts') {
            // Apply category checkbox filters (same as live alerts)
            const checked = _getCheckedAlertCategories();
            const active = _stripInactiveAlerts(feats);
            const filtered = checked.length
                ? active.filter(f => _matchesCheckedCategories(f, checked))
                : [];
            const geojson = { type: 'FeatureCollection', features: filtered };
            if (alertsLayer) { map.removeLayer(alertsLayer); alertsLayer = null; }
            alertsLayer = L.geoJSON(geojson, {
                style: alertStyle,
                onEachFeature(feat, layer) {
                    layer.on('click', (e) => {
                        if (e?.latlng) {
                            _setRegionAlertLocationState();
                            _openAlertsPagerAt(e.latlng);
                        }
                    });
                },
            });
            alertsLayer.addTo(map);
            _reloadRadarForCurrentSelection();
        } else if (layerType === 'spc') {
            if (spcLayer) { map.removeLayer(spcLayer); spcLayer = null; }
            const hazard = _getPrimarySpcHazard();
            const styleFn = _getSpcStyleFn(hazard);
            spcLayer = L.geoJSON(geojson, {
                style: styleFn,
                onEachFeature(feat, layer) {
                    layer.bindPopup(spcPopup(feat));
                    layer.on('add', () => _applySpcCigPattern(feat, layer));
                },
            });
            if (byId('weather-show-spc')?.checked) {
                spcLayer.addTo(map);
                _applySpcCigPatternsToGroup(spcLayer);
            }
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
            `&date_from=${encodeURIComponent(dtFrom)}` +
            `&date_to=${encodeURIComponent(dtTo)}` +
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
        const hazard = _getPrimarySpcHazard(day);
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
        }, _scrubberPlaybackDelay(ARCHIVE_PLAY_INTERVAL_MS));
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
        if (_radarScrubMode) {
            _exitRadarScrubMode(true);
            return;
        }
        if (_satelliteScrubMode) {
            _exitSatelliteScrubMode(true);
            return;
        }
        if (_rtmaScrubMode) {
            _exitRtmaScrubMode(true);
            return;
        }
        if (_mrmsScrubMode) {
            _exitMrmsScrubMode(true);
            return;
        }
        if (_archiveMode) exitArchiveMode();
    });
    byId('weather-mode-archive')?.addEventListener('click', () => {
        if (_isTypeEnabled('satellite')) {
            setStatus('Archive mode is disabled on the Satellite tab. Use live scrubber controls instead.');
            return;
        }
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

    byId('scrubber-speed-down')?.addEventListener('click', () => {
        _adjustScrubberPlaybackSpeed(-1);
    });

    byId('scrubber-speed-up')?.addEventListener('click', () => {
        _adjustScrubberPlaybackSpeed(1);
    });

    byId('weather-satellite-auto-refresh')?.addEventListener('click', () => {
        if (!_satelliteScrubMode || !_isTypeEnabled('satellite')) return;
        const enabled = !_satelliteAnimateAutoRefreshEnabled;
        _setSatelliteAnimateAutoRefreshEnabled(enabled);
        if (enabled) {
            void _refreshSatelliteAnimationFrames({ auto: true, silent: false });
        } else {
            _setRtmaScrubberStatus(`${_satelliteFrames.length} satellite frames loaded. Auto refresh off.`);
        }
    });

    _updateScrubberPlaybackSpeedUi();

    byId('scrubber-play')?.addEventListener('click', () => {
        if (_radarScrubMode) {
            if (_radarScrubPlayTimer) {
                _stopRadarScrubPlay();
            } else {
                _startRadarScrubPlay();
            }
            return;
        }
        if (_satelliteScrubMode) {
            if (_satelliteScrubPlayTimer) {
                _stopSatelliteScrubPlay();
            } else {
                _startSatelliteScrubPlay();
            }
            return;
        }
        if (_rtmaScrubMode) {
            if (_rtmaScrubPlayTimer) {
                _stopRtmaScrubPlay();
            } else {
                _startRtmaScrubPlay();
            }
            return;
        }
        if (_mrmsScrubMode) {
            if (_mrmsScrubPlayTimer) {
                _stopMrmsScrubPlay();
            } else {
                _startMrmsScrubPlay();
            }
            return;
        }
        if (_archivePlayTimer) { stopScrubberPlay(); } else { startScrubberPlay(); }
    });

    byId('scrubber-step-back')?.addEventListener('click', async () => {
        if (_radarScrubMode) {
            _stopRadarScrubPlay();
            _renderRadarScrubFrame(_radarScrubFrameIndex - 1);
            return;
        }
        if (_satelliteScrubMode) {
            _stopSatelliteScrubPlay();
            await _setSatelliteFrame(_satelliteFrameIndex - 1, { waitForTiles: false });
            return;
        }
        if (_rtmaScrubMode) {
            _stopRtmaScrubPlay();
            _renderRtmaScrubFrame(_rtmaScrubFrameIndex - 1);
            return;
        }
        if (_mrmsScrubMode) {
            _stopMrmsScrubPlay();
            _renderMrmsScrubFrame(_mrmsScrubFrameIndex - 1);
            return;
        }
        stopScrubberPlay();
        renderArchiveFrame(_archiveFrameIndex - 1);
    });

    byId('scrubber-step-fwd')?.addEventListener('click', async () => {
        if (_radarScrubMode) {
            _stopRadarScrubPlay();
            _renderRadarScrubFrame(_radarScrubFrameIndex + 1);
            return;
        }
        if (_satelliteScrubMode) {
            _stopSatelliteScrubPlay();
            await _setSatelliteFrame(_satelliteFrameIndex + 1, { waitForTiles: false });
            return;
        }
        if (_rtmaScrubMode) {
            _stopRtmaScrubPlay();
            _renderRtmaScrubFrame(_rtmaScrubFrameIndex + 1);
            return;
        }
        if (_mrmsScrubMode) {
            _stopMrmsScrubPlay();
            _renderMrmsScrubFrame(_mrmsScrubFrameIndex + 1);
            return;
        }
        stopScrubberPlay();
        renderArchiveFrame(_archiveFrameIndex + 1);
    });

    byId('scrubber-slider')?.addEventListener('input', async (e) => {
        if (_radarScrubMode) {
            _stopRadarScrubPlay();
            _renderRadarScrubFrame(parseInt(e.target.value, 10));
            return;
        }
        if (_satelliteScrubMode) {
            _scheduleSatelliteManualScrubFrame(parseInt(e.target.value, 10));
            return;
        }
        if (_rtmaScrubMode) {
            _stopRtmaScrubPlay();
            _renderRtmaScrubFrame(parseInt(e.target.value, 10));
            return;
        }
        if (_mrmsScrubMode) {
            _stopMrmsScrubPlay();
            _renderMrmsScrubFrame(parseInt(e.target.value, 10));
            return;
        }
        stopScrubberPlay();
        renderArchiveFrame(parseInt(e.target.value, 10));
    });

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
        try {
            const resp = await fetch(apiUrl('/api/overlay/world-borders'));
            if (!resp.ok) return;
            const countriesRaw = await resp.json();
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

    function _setObsDensity(rawValue) {
        const raw = parseFloat(String(rawValue));
        if (!Number.isFinite(raw)) return;
        const clamped = Math.max(0.01, Math.min(1, raw));
        const primary = byId('weather-obs-density');
        const rtma = byId('weather-rtma-obs-density');
        if (primary) primary.value = String(clamped);
        if (rtma) rtma.value = String(clamped);
        _surfaceDensity = clamped;
        _updateObsDensityLabel();
        if (_surfaceStations?.length) {
            _renderSurfaceMarkers(_surfaceStations);
        }
        if (_isTypeEnabled('rtma')) {
            const key = `${_activeRtmaRegion()}|${_activeRtmaStream()}|${_activeRtmaProduct()}`;
            if (_rtmaPointsAll.length && _rtmaPointsKey === key) _renderRtmaPoints();
            else _scheduleRtmaPointsLoad();
        }
    }

    function _readGradientBlurScale() {
        const raw = parseFloat(byId('weather-gradient-blur')?.value || '0');
        if (!Number.isFinite(raw)) return 0.35;
        return Math.max(0, Math.min(2, raw));
    }

    function _updateObsDensityLabel() {
        const labels = [
            document.querySelector('label[for="weather-obs-density"]'),
            document.querySelector('label[for="weather-rtma-obs-density"]'),
        ].filter(Boolean);
        if (!labels.length) return;
        const zoom = map?.getZoom() ?? 5;
        const region = (byId('weather-region')?.value || '').toUpperCase();
        const distKm = Math.round(_baseDistKm(zoom, region) / _surfaceDensity);
        labels.forEach((label) => {
            const baseLabel = label.dataset.baseLabel || 'Station Density';
            label.dataset.baseLabel = baseLabel;
            label.textContent = `${baseLabel} (${distKm} km)`;
        });
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

        if (_activeWeatherType() === 'radar') {
            _bringRadarSitesAboveRadarOverlays();
        }
    }

    byId('weather-region')?.addEventListener('change', (e) => {
        const nextRegion = String(e.target.value || '').toUpperCase();
        const regionSelect = byId('weather-region');
        if (nextRegion !== '__RADAR_SITE_SELECTED__') {
            const sentinelOpt = regionSelect?.querySelector('option[value="__RADAR_SITE_SELECTED__"]');
            if (sentinelOpt) sentinelOpt.remove();
        }
        if (nextRegion !== '__ALERT_LOCATION__') {
            const alertSentinel = regionSelect?.querySelector('option[value="__ALERT_LOCATION__"]');
            if (alertSentinel) alertSentinel.remove();
        }
        if (nextRegion === 'CONUS') {
            _clearRadarSiteAndZoomConus();
            return;
        }
        fitRegion(nextRegion);
        _updateObsDensityLabel();
        _updateGradientBlurControlVisibility();
        _clearSpeedOverride();
        _clearRadarCalLine();
        _syncRtmaStreamForRegion();
        _syncRtmaProductForStream();
        if (_rtmaScrubMode) {
            loadRtmaScrubberFrames();
            return;
        }
        if (_mrmsScrubMode) {
            loadMrmsScrubberFrames();
            return;
        }
        if (_radarScrubMode) {
            loadRadarScrubberFrames();
            return;
        }
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
            // Enforce single active weather type for all tabs
            const allTypes = ['current', 'alerts', 'radar', 'satellite', 'spc', 'rtma', 'mrms', 'drought', 'tropical'];
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
                // RTMA animate/scrub is tab-specific. Leaving RTMA must tear it
                // down immediately, otherwise refreshActiveLayers() no-ops while
                // _rtmaScrubMode is true and stale RTMA legend/layers can linger.
                if (type !== 'rtma' && _rtmaScrubMode) {
                    _exitRtmaScrubMode(false);
                }
                if (type !== 'mrms' && _mrmsScrubMode) {
                    _exitMrmsScrubMode(false);
                }
                if (type !== 'radar' && _radarScrubMode) {
                    _exitRadarScrubMode(false);
                }
                if (type !== 'satellite' && _satelliteScrubMode) {
                    _exitSatelliteScrubMode(false);
                }
                if (type !== 'radar') _stopRadarAutoRefresh();
                if (type === 'radar') _startRadarAutoRefresh();
                _resetTransientInteractiveUiForTabChange();
                _resetTabControlsToDefaults(type);
                if (type === 'radar' && !_radarTabVisitedOnce) {
                    _ensureMrmsRadarOverlayEnabled();
                    _radarTabVisitedOnce = true;
                }
                fitRegion(byId('weather-region')?.value || 'CONUS');
                if (['radar', 'satellite', 'rtma', 'drought', 'tropical'].includes(type)) {
                    _setViewerTimestamp(null);
                }
                if (type === 'satellite') {
                    _setSatelliteLookbackHours(_recommendedSatelliteLookbackHours());
                    _setSatelliteModeActive(_satelliteScrubMode ? 'animate' : 'current');
                    if (!_satelliteScrubMode) {
                        _setRtmaScrubberStatus('');
                        _setArchiveScrubber(false);
                        _setScrubberControlsEnabled(false);
                        loadSatelliteCurrentFrame({ silent: false });
                    }
                }
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
            _syncMrmsRadarOverlay();
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
            _updateAlertFilterOptionsVisibility();
            _updateWarningFilterRowVisibility();
            if (_archiveMode && _archiveProductType === 'alerts' && _archiveFrames.length) {
                renderArchiveFrame(_archiveFrameIndex);
            } else if (_isTypeEnabled('alerts')) {
                if (_alertsFullBaseFeatures.length || _alertsDisplayBaseFeatures.length) {
                    _applyInMemoryAlertCategoryFilter();
                    loadAlerts({ silentStatus: true });
                } else {
                    loadAlerts();
                }
            }
        });
    });

    byId('weather-spc-day')?.addEventListener('change', () => {
        _syncSpcConvectiveOptions(_shouldResetSpcConvectiveDaySelection());
        if (_isTypeEnabled('spc') && byId('weather-show-spc')?.checked) refreshSpc();
    });

    document.querySelectorAll('.weather-spc-convective-toggle').forEach((el) => {
        el.addEventListener('change', () => {
            if (el.checked) _clearSpcExclusivePeers('convective');
            const BASE_HAZARDS = ['cat', 'torn', 'wind', 'hail'];
            const day = _getSpcDay();
            // For Day 3, make Categorical and Probabilistic mutually exclusive
            if (day === 3 && (el.value === 'cat' || el.value === 'prob')) {
                if (el.checked) {
                    document.querySelectorAll('.weather-spc-convective-toggle').forEach((other) => {
                        if (other === el) return;
                        if ((other.value === 'cat' || other.value === 'prob') && other.checked) {
                            other.checked = false;
                        }
                    });
                }
            } else if (el.checked && BASE_HAZARDS.includes(el.value)) {
                const keepCig = _SPC_CIG_OVERLAY_BY_HAZARD[el.value] || null;
                document.querySelectorAll('.weather-spc-convective-toggle').forEach((other) => {
                    if (other === el) return;
                    const val = other.value;
                    if (BASE_HAZARDS.includes(val)) {
                        if (other.checked) other.checked = false;
                    } else if (val && val.startsWith('cig') && val !== keepCig) {
                        if (other.checked) other.checked = false;
                    }
                });
            }
            // Auto-select the matching CIG (Significant) checkbox when a base
            // probabilistic hazard is checked on Day 1 or Day 2. Users can still
            // uncheck it manually to hide the Sig layer.
            if (el.checked) {
                if (day <= 2) {
                    const cigHazard = _SPC_CIG_OVERLAY_BY_HAZARD[el.value];
                    if (cigHazard) {
                        const cigEl = document.querySelector(
                            `.weather-spc-convective-toggle[value="${cigHazard}"]`,
                        );
                        if (cigEl && !cigEl.checked && !cigEl.disabled) cigEl.checked = true;
                    }
                }
            }
            if (_isTypeEnabled('spc') && byId('weather-show-spc')?.checked) refreshSpc();
        });
    });

    const _refreshSpcIfVisible = () => {
        if (_isTypeEnabled('spc') && byId('weather-show-spc')?.checked) refreshSpc();
    };

    const _enforceMutuallyExclusiveChecks = (idA, idB) => {
        const elA = byId(idA);
        const elB = byId(idB);
        if (!elA || !elB) return;
        elA.addEventListener('change', () => {
            if (elA.checked) {
                elB.checked = false;
                _clearSpcExclusivePeers('watches');
            }
            _refreshSpcIfVisible();
        });
        elB.addEventListener('change', () => {
            if (elB.checked) {
                elA.checked = false;
                _clearSpcExclusivePeers('watches');
            }
            _refreshSpcIfVisible();
        });
    };

    _enforceMutuallyExclusiveChecks('weather-spc-watch-tor-polygon', 'weather-spc-watch-tor-counties');
    _enforceMutuallyExclusiveChecks('weather-spc-watch-svr-polygon', 'weather-spc-watch-svr-counties');

    ['weather-spc-reports-today', 'weather-spc-reports-yesterday'].forEach((id) => {
        byId(id)?.addEventListener('change', (evt) => {
            if (evt?.target?.checked) {
                _clearSpcExclusivePeers('reports');
                ['weather-spc-report-type-torn', 'weather-spc-report-type-wind', 'weather-spc-report-type-hail']
                    .forEach((filterId) => {
                        const filterEl = byId(filterId);
                        if (filterEl) filterEl.checked = true;
                    });
            }
            _updateSpcReportFilterState();
            _refreshSpcIfVisible();
        });
    });

    [
        'weather-spc-show-mds',
        'weather-spc-report-type-torn',
        'weather-spc-report-type-wind',
        'weather-spc-report-type-hail',
    ].forEach((id) => {
        byId(id)?.addEventListener('change', (evt) => {
            if (id === 'weather-spc-show-mds' && evt?.target?.checked) {
                _clearSpcExclusivePeers('mds');
            }
            _refreshSpcIfVisible();
        });
    });

    document.querySelectorAll('.weather-spc-fire-toggle').forEach((el) => {
        el.addEventListener('change', () => {
            if (el.checked) {
                _clearSpcExclusivePeers('fire', { keepFireTarget: el });
            }
            _refreshSpcIfVisible();
        });
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

    document.querySelectorAll('.weather-rtma-stream').forEach((el) => {
        el.addEventListener('change', (evt) => {
            if (evt.target.checked) {
                document.querySelectorAll('.weather-rtma-stream').forEach((other) => {
                    if (other !== evt.target) other.checked = false;
                });
            }

            if (!_activeRtmaStream()) evt.target.checked = true;
            _syncRtmaStreamForRegion();
            _syncRtmaProductForStream();
            if (_rtmaScrubMode) {
                loadRtmaScrubberFrames();
                return;
            }
            refreshActiveLayers();
        });
    });

    document.querySelectorAll('.weather-rtma-product').forEach((el) => {
        el.addEventListener('change', (evt) => {
            if (evt.target.checked) {
                if (evt.target.value === 'temperature_change_24h' && _activeRtmaStream() !== 'rtma_hourly') {
                    const hourly = document.querySelector('.weather-rtma-stream[value="rtma_hourly"]');
                    const rapid = document.querySelector('.weather-rtma-stream[value="rtma_rapid_update"]');
                    if (hourly) hourly.checked = true;
                    if (rapid) rapid.checked = false;
                    _syncRtmaProductForStream();
                }
                document.querySelectorAll('.weather-rtma-product').forEach((other) => {
                    if (other !== evt.target) other.checked = false;
                });
            }

            if (!_activeRtmaProduct()) evt.target.checked = true;
            if (_rtmaScrubMode) {
                loadRtmaScrubberFrames();
                return;
            }
            refreshActiveLayers();
        });
    });

    byId('weather-rtma-load-scrubber')?.addEventListener('click', () => {
        if (!_isTypeEnabled('radar') && !_isTypeEnabled('rtma') && !_isTypeEnabled('mrms')) {
            setStatus('Select Radar, RTMA, or MRMS to use Animate.');
            return;
        }
        byId('weather-mode-current')?.classList.remove('active');
        byId('weather-mode-archive')?.classList.remove('active');
        byId('weather-rtma-load-scrubber')?.classList.add('active');

        // Hide both animate windows first
        const rtmaWin = byId('rtma-animate-window');
        const mrmsWin = byId('mrms-animate-window');
        if (rtmaWin) rtmaWin.style.display = 'none';
        if (mrmsWin) mrmsWin.style.display = 'none';

        if (_isTypeEnabled('radar')) {
            _restartRadarAutoRefreshInterval();
            _updateRadarNextUpdateCountdown();
            if (rtmaWin) rtmaWin.style.display = '';
            loadRadarScrubberFrames();
            return;
        }
        if (_isTypeEnabled('mrms')) {
            if (mrmsWin) mrmsWin.style.display = '';
            loadMrmsScrubberFrames();
            return;
        }
        if (rtmaWin) rtmaWin.style.display = '';
        loadRtmaScrubberFrames();
    });

    // RTMA slider handler
    const rtmaSlider = byId('rtma-animate-slider');
    if (rtmaSlider) {
        rtmaSlider.addEventListener('input', () => {
            const displayValue = Number(rtmaSlider.value);
            const displayText = displayValue === Math.floor(displayValue) ?
                Math.floor(displayValue) + 'H' :
                displayValue + 'H';
            const valueDisplay = byId('rtma-animate-slider-value');
            if (valueDisplay) valueDisplay.textContent = displayText;
        });
        rtmaSlider.addEventListener('change', () => {
            if (_rtmaScrubMode) loadRtmaScrubberFrames();
            if (_radarScrubMode) loadRadarScrubberFrames();
        });
    }

    // MRMS slider handler
    const mrmsSlider = byId('mrms-animate-slider');
    if (mrmsSlider) {
        mrmsSlider.addEventListener('input', () => {
            const displayValue = Number(mrmsSlider.value);
            const displayText = displayValue === Math.floor(displayValue) ?
                Math.floor(displayValue) + 'H' :
                displayValue + 'H';
            const valueDisplay = byId('mrms-animate-slider-value');
            if (valueDisplay) valueDisplay.textContent = displayText;
        });
        mrmsSlider.addEventListener('change', () => {
            if (_mrmsScrubMode) loadMrmsScrubberFrames();
        });
    }

    byId('weather-rtma-show-values')?.addEventListener('change', () => {
        if (!_isTypeEnabled('rtma')) return;
        // Gradient always shows; this toggle only adds/removes text markers.
        if (_rtmaPointsAll.length) {
            _renderRtmaPoints();
        } else {
            _scheduleRtmaPointsLoad(0);
        }
    });

    byId('weather-show-spc')?.addEventListener('change', () => {
        _updateSubOptionVisibility();
        refreshActiveLayers();
    });
    document.querySelectorAll('.mrms-product-check').forEach((cb) => {
        cb.addEventListener('change', () => {
            if (cb.checked) {
                document.querySelectorAll('.mrms-product-check').forEach((other) => {
                    if (other !== cb) other.checked = false;
                });
            }
            updateMrmsSubControls();
            if (_mrmsScrubMode) {
                loadMrmsScrubberFrames();
                return;
            }
            refreshActiveLayers();
            if (cb.checked && _isTypeEnabled('mrms')) loadMrms();
        });
    });

    document.querySelectorAll('.mrms-sub-radio').forEach((radio) => {
        radio.addEventListener('change', () => {
            if (_mrmsScrubMode) {
                loadMrmsScrubberFrames();
                return;
            }
            if (_isTypeEnabled('mrms') && _activeMrmsProduct()) loadMrms();
        });
    });

    byId('weather-refresh-mrms')?.addEventListener('click', loadMrms);

    byId('weather-refresh-drought')?.addEventListener('click', () => {
        if (_isTypeEnabled('drought')) loadDroughtLayer();
    });
    document.querySelectorAll('.drought-cat-check').forEach((cb) => {
        cb.addEventListener('change', () => {
            if (!_isTypeEnabled('drought')) return;
            // Re-apply filter without re-fetching
            if (droughtLayer) {
                const enabledCats = _activeDroughtCategories();
                const opacity = parseFloat(byId('weather-opacity-drought')?.value ?? 0.75);
                droughtLayer.eachLayer((l) => {
                    const dm = Number(l.feature?.properties?.DM);
                    if (enabledCats.includes(dm)) {
                        l.setStyle({ fillOpacity: opacity, opacity: 0.8 });
                        if (!map.hasLayer(droughtLayer)) droughtLayer.addTo(map);
                    } else {
                        l.setStyle({ fillOpacity: 0, opacity: 0, weight: 0 });
                    }
                });
                buildDroughtLegend(enabledCats, _lastDroughtStateStats, _lastDroughtStateCode);
            }
        });
    });
    byId('weather-opacity-drought')?.addEventListener('input', (e) => {
        const opacity = parseFloat(e.target.value);
        if (droughtLayer) {
            const enabledCats = _activeDroughtCategories();
            droughtLayer.eachLayer((l) => {
                const dm = Number(l.feature?.properties?.DM);
                if (enabledCats.includes(dm)) {
                    l.setStyle({ fillOpacity: opacity, opacity: 0.8 });
                }
            });
        }
    });

    byId('weather-opacity-alerts')?.addEventListener('input', (e) => applyAlertsOpacity(e.target.value));
    byId('weather-opacity-spc')?.addEventListener('input', (e) => applySpcOpacity(e.target.value));
    byId('weather-opacity-spc-stroke')?.addEventListener('input', (e) => applySpcStrokeOpacity(e.target.value));
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
                    await _primeSurfaceGradientOverlayCache(product, region);
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
        _setObsDensity(e.target.value);
    });
    byId('weather-rtma-obs-density')?.addEventListener('input', (e) => {
        _setObsDensity(e.target.value);
    });
    byId('weather-rtma-gradient-opacity')?.addEventListener('input', (e) => {
        rtmaGradientOpacity = parseFloat(e.target.value);
        if (rtmaGradientLayer) rtmaGradientLayer.setOpacity(rtmaGradientOpacity);
    });
    byId('weather-refresh-alerts')?.addEventListener('click', () => loadAlerts());

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
    document.addEventListener('visibilitychange', () => {
        if (!document.hidden && _isTypeEnabled('radar') && !_archiveMode) {
            _radarAutoRefreshTick();
        }
        if (!document.hidden && _isTypeEnabled('satellite') && !_archiveMode && !_satelliteScrubMode) {
            loadSatelliteCurrentFrame({ silent: true });
        }
        if (!document.hidden && _satelliteAnimateAutoRefreshEnabled && _satelliteScrubMode && _isTypeEnabled('satellite')) {
            void _refreshSatelliteAnimationFrames({ auto: true, silent: true });
        }
        _updateRadarNextUpdateCountdown();
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

    const _testNewAlertBtn = byId('weather-test-new-alert');
    if (_testNewAlertBtn) {
        if (!ENABLE_TEST_ALERT_UI) {
            _testNewAlertBtn.style.display = 'none';
        } else {
            _testNewAlertBtn.addEventListener('click', async () => {
                if (!_isTypeEnabled('alerts')) {
                    setStatus('Enable Alerts first to test New Alert banners.');
                    return;
                }
                try {
                    const testDismissMs = 2 * 10_000;
                    let count = 0;
                    try {
                        count = await _testAlertBannerFromJson('data/test_severe_thunderstorm_warning.json', 'Severe', testDismissMs);
                    } catch (_) {
                        count = await _testAlertBannerFromJson(_TEST_STW_ALERT_COLLECTION, 'Severe', testDismissMs);
                    }
                    setStatus(`Test New Alert fired (${count} feature${count === 1 ? '' : 's'}), held for 2 minutes.`);
                } catch (err) {
                    setStatus(`Test New Alert failed: ${err?.message || err}`);
                }
            });
        }
    }

    byId('weather-alerts-radar')?.addEventListener('change', function () {
        const opacityLabel = byId('weather-alerts-radar-opacity-label');
        const opacitySlider = byId('weather-alerts-radar-opacity');
        if (opacityLabel) opacityLabel.style.display = this.checked ? '' : 'none';
        if (opacitySlider) opacitySlider.style.display = this.checked ? '' : 'none';

        _syncMrmsRadarOverlay();

        if (this.checked && !_mrmsRadarOverlayAllowedInContext()) {
            setStatus('Radar overlay is available on Current, Alerts, SPC, RTMA, and Radar tabs only.');
        }

        if (_isTypeEnabled('radar') && !_activeRadarSite()) {
            if (this.checked && _mrmsRadarOverlayAllowedInContext()) {
                _setRadarStatus('National Composite overlay (MRMS Refl_BaseQC).');
                setStatus('Radar tab: national composite MRMS overlay active.');
            } else {
                _setRadarStatus('Radar overlay is off.');
                setStatus('Radar tab: MRMS overlay is off.');
            }
        }
    });

    byId('weather-alerts-radar-opacity')?.addEventListener('input', function () {
        _mrmsRadarOverlaySetOpacity(this.value);
    });

    byId('weather-alerts-nowcoast')?.addEventListener('change', function () {
        const opacityLabel = byId('weather-alerts-nowcoast-opacity-label');
        const opacitySlider = byId('weather-alerts-nowcoast-opacity');
        if (this.checked) {
            const opacity = parseFloat(opacitySlider?.value ?? 0.55);
            nowcoastAlertsLayer = L.tileLayer.wms(NOWCOAST_ALERTS_WMS_URL, {
                layers: NOWCOAST_ALERTS_LAYER,
                format: 'image/png',
                transparent: true,
                version: '1.3.0',
                opacity,
                zIndex: 290,
                attribution: '&copy; NOAA/NWS nowCOAST',
            });
            nowcoastAlertsLayer.addTo(map);
            if (opacityLabel) opacityLabel.style.display = '';
            if (opacitySlider) opacitySlider.style.display = '';
            _nowcoastAlertsRefreshTimer = setInterval(() => {
                if (nowcoastAlertsLayer) nowcoastAlertsLayer.setParams({ _ts: Date.now() }, false);
            }, NOWCOAST_ALERTS_REFRESH_MS);
        } else {
            if (nowcoastAlertsLayer && map.hasLayer(nowcoastAlertsLayer)) { map.removeLayer(nowcoastAlertsLayer); nowcoastAlertsLayer = null; }
            if (_nowcoastAlertsRefreshTimer) { clearInterval(_nowcoastAlertsRefreshTimer); _nowcoastAlertsRefreshTimer = null; }
            if (opacityLabel) opacityLabel.style.display = 'none';
            if (opacitySlider) opacitySlider.style.display = 'none';
        }
    });

    byId('weather-alerts-nowcoast-opacity')?.addEventListener('input', function () {
        if (nowcoastAlertsLayer) nowcoastAlertsLayer.setOpacity(parseFloat(this.value));
    });

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

    byId('weather-radar-site')?.addEventListener('change', () => {
        // Dropdown selection always collapses multi-site mode
        if (_radarMultiSites.size > 0) {
            _clearRadarMultiSiteOverlays();
            _radarMultiSites.clear();
        }
        if (!_activeRadarSite()) {
            _setActiveWeatherType('radar');
            _clearRadarSiteAndZoomConus();
            _ensureMrmsRadarOverlayEnabled();
            _updateTypeSections();
            _syncRadarSiteSelectionHighlight();
            return;
        }
        // Zoom to selected site location
        const siteId = _activeRadarSite();
        const coords = _radarSiteCoords.get(siteId);
        if (coords && _isTypeEnabled('radar')) {
            const [lat, lon] = coords;
            map.flyTo([lat, lon], Math.max(map.getZoom(), 9), { duration: 0.6 });
        }
        _ensureMrmsRadarOverlayDisabled();
        _setRegionRadarSiteSelectedState();
        _updateTypeSections();
        _syncRadarSiteSelectionHighlight();
        _reloadRadarForCurrentSelection();
    });

    byId('weather-radar-product')?.addEventListener('change', () => {
        _reloadRadarForCurrentSelection();
    });

    byId('weather-radar-show-sites')?.addEventListener('change', () => {
        _syncRadarSiteLayerVisibility();
        if (_isTypeEnabled('radar') && !_activeRadarSite()) {
            if (byId('weather-radar-show-sites')?.checked) buildRadarSiteMarkerLegend();
            else setLegend(null);
        }
    });

    byId('weather-refresh-radar')?.addEventListener('click', () => {
        if (!_isTypeEnabled('radar')) {
            setStatus('Enable the Radar tab first.');
            return;
        }
        _reloadRadarForCurrentSelection();
    });

    byId('weather-clear-radar')?.addEventListener('click', () => {
        if (!_isTypeEnabled('radar')) {
            setStatus('Enable the Radar tab first.');
            return;
        }
        _clearRadarLoadedOverlaysOnly();
    });

    byId('weather-satellite-current')?.addEventListener('click', () => {
        if (!_isTypeEnabled('satellite')) {
            setStatus('Enable the Satellite tab first.');
            return;
        }
        if (_satelliteScrubMode) {
            _exitSatelliteScrubMode(false);
        }
        loadSatelliteCurrentFrame({ silent: false });
    });

    byId('weather-satellite-animate')?.addEventListener('click', () => {
        if (!_isTypeEnabled('satellite')) {
            setStatus('Enable the Satellite tab first.');
            return;
        }
        loadSatelliteScrubberFrames();
    });

    [
        'weather-satellite-sat-id',
        'weather-satellite-sector',
        'weather-satellite-channel',
    ].forEach((id) => {
        byId(id)?.addEventListener('change', () => {
            if (_isTypeEnabled('satellite')) {
                _clearSatelliteLayerPool();
                if (_satelliteScrubMode) {
                    loadSatelliteScrubberFrames();
                    return;
                }
                loadSatelliteCurrentFrame({ silent: false });
            }
        });
    });

    byId('weather-satellite-lookback-slider')?.addEventListener('input', (event) => {
        const hours = parseInt(event.target.value, 10);
        _setSatelliteLookbackHours(hours);
        if (_satelliteScrubMode && _isTypeEnabled('satellite')) {
            _scheduleSatelliteScrubberReload();
        }
    });

    // Left sidebar satellite lookback and scrubber controls removed - functionality moved to bottom archive bar


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
        if (_satelliteScrubMode && _satelliteFrames.length && _isTypeEnabled('satellite')) {
            _scheduleSatelliteTilePrefetch(350);
        }
    });

    map.on('zoomstart', () => {
        if (!_satelliteScrubMode) return;
        _satelliteScrubResumeAfterZoom = !!_satelliteScrubPlayTimer;
        if (_satelliteScrubPlayTimer) {
            _stopSatelliteScrubPlay();
        }
        _cancelSatellitePendingSwap();
        _cancelSatelliteTilePrefetch();
        _setRtmaScrubberStatus('Zooming... preparing animation tiles.');
    });

    map.on('zoomend', () => {
        if (!_satelliteScrubMode || !_satelliteFrames.length || !_isTypeEnabled('satellite')) return;

        _setSatelliteFrame(_satelliteFrameIndex, { waitForTiles: false });
        _scheduleSatelliteTilePrefetch(450);
        _updateRtmaScrubberUi();

        if (_satelliteScrubResumeAfterZoom) {
            _satelliteScrubResumeAfterZoom = false;
            setTimeout(() => {
                if (_satelliteScrubMode && !_satelliteScrubPlayTimer) {
                    _startSatelliteScrubPlay();
                }
            }, 450);
            return;
        }

        _setRtmaScrubberStatus(`${_satelliteFrameIndex + 1} / ${_satelliteFrames.length} frames.`);
    });

    // Close active alerts pager when the user pans/zooms the map.
    map.on('movestart zoomstart', () => {
        if (!_activeAlertsPopup?.popup) return;
        map.closePopup(_activeAlertsPopup.popup);
    });

    map.on('popupopen', (evt) => {
        const popupRoot = evt?.popup?.getElement?.();
        if (!popupRoot) return;

        // Keep popup interactions inside the popup; avoid map-level click close.
        if (L?.DomEvent) {
            L.DomEvent.disableClickPropagation(popupRoot);
            L.DomEvent.disableScrollPropagation(popupRoot);
        }

        if (popupRoot.dataset.alertPagerBound === '1') return;
        popupRoot.dataset.alertPagerBound = '1';

        popupRoot.addEventListener('click', (clickEvt) => {
            const pagerEl = clickEvt.target.closest('[data-alert-pager="1"]');
            if (!pagerEl) return;

            const zoomBtn = clickEvt.target.closest('[data-alert-zoom]');
            if (zoomBtn) {
                clickEvt.preventDefault();
                clickEvt.stopPropagation();
                const feat = _activeAlertsPopup?.features?.[_activeAlertsPopup?.index || 0];
                const center = _alertFeatureCenterLatLng(feat) || _activeAlertsPopup?.latlng || null;
                if (!center) return;
                _setRegionAlertLocationState();
                map.flyTo(center, Math.max(map.getZoom(), 9), { duration: 0.9 });
                map.once('moveend', () => {
                    _openAlertsPagerAt(center);
                    _ensureRadarOverlayOn();
                });
                return;
            }

            const navBtn = clickEvt.target.closest('[data-alert-nav]');
            if (navBtn) {
                clickEvt.preventDefault();
                clickEvt.stopPropagation();
                const dir = navBtn.getAttribute('data-alert-nav');
                const delta = dir === 'next' ? 1 : -1;
                _updateAlertsPager((_activeAlertsPopup?.index || 0) + delta);
                return;
            }
            const dotBtn = clickEvt.target.closest('[data-alert-page]');
            if (!dotBtn) return;
            clickEvt.preventDefault();
            clickEvt.stopPropagation();
            const nextIndex = Number(dotBtn.getAttribute('data-alert-page'));
            if (!Number.isFinite(nextIndex)) return;
            _updateAlertsPager(nextIndex);
        });
    });

    map.on('popupclose', () => {
        _activeAlertsPopup = null;
    });

    // ── Init ─────────────────────────────────────────────────────────────────
    function init() {
        _applyDefaultAlertSelection();
        const radarCb = byId('weather-alerts-radar');
        const radarOpacityLabel = byId('weather-alerts-radar-opacity-label');
        const radarOpacitySlider = byId('weather-alerts-radar-opacity');
        if (radarOpacityLabel) radarOpacityLabel.style.display = radarCb?.checked ? '' : 'none';
        if (radarOpacitySlider) radarOpacitySlider.style.display = radarCb?.checked ? '' : 'none';
        _syncSpcConvectiveOptions(false);
        _syncSpcFireWeatherOptions(false);
        _updateTypeSections();
        _updateRightSidebarGroups();
        _updateSubOptionVisibility();
        updateMrmsSubControls();
        _wireSidebarToggle('weather-side-left', 'weather-side-toggle-left', '‹', '›');
        _wireSidebarToggle('weather-side-right', 'weather-side-toggle-right', '›', '‹');
        _wireRightSidebarTabs();
        _wireActiveWarningsPanel();
        _wireSidebarWarningFilterCheckboxes();
        _updateAlertFilterOptionsVisibility();
        _updateWarningFilterRowVisibility();
        _wireSpcUiParityHandlers();
        _citiesDensity = _readCitiesDensity();
        _updateCitiesDensityLabel();
        _surfaceDensity = _readObsDensity();
        if (byId('weather-rtma-obs-density')) {
            byId('weather-rtma-obs-density').value = String(_surfaceDensity);
        }
        _updateObsDensityLabel();
        _gradientBlurScale = _readGradientBlurScale();
        _updateGradientBlurLabel();
        _updateGradientBlurControlVisibility();
        _syncRtmaStreamForRegion();
        _syncRtmaProductForStream();
        _loadRadarSites();
        _startRadarAutoRefresh();
        byId('wx-radar-auto-update')?.addEventListener('change', () => {
            if (byId('wx-radar-auto-update')?.checked) {
                _setRadarAutoUpdateStatus('');
                _restartRadarAutoRefreshInterval();
            }
            _updateRadarNextUpdateCountdown();
        });
        _syncRightSidebarLayers();
        _setViewerTimestamp(null);
        refreshActiveLayers();
        _syncMrmsRadarOverlay();
        _startReliabilityTicker();
    }

    // ── Auto-refresh alerts every 30s to match the OS-task backend cadence ──
    const ALERTS_AUTO_REFRESH_MS = 30_000;
    setInterval(() => {
        if (_archiveMode || _rtmaScrubMode || _mrmsScrubMode || _radarScrubMode) return;
        if (!_isTypeEnabled('alerts')) return;
        if (!_getCheckedAlertCategories().length) return;
        loadAlerts();
    }, ALERTS_AUTO_REFRESH_MS);

    // Keep active SPC MD/watch overlays current so newly issued items appear
    // and expired products are removed without a manual refresh.
    const SPC_AUTO_REFRESH_MS = 60_000;
    setInterval(() => {
        if (_archiveMode || _rtmaScrubMode || _mrmsScrubMode || _radarScrubMode) return;
        if (!_isTypeEnabled('spc')) return;
        if (!byId('weather-show-spc')?.checked) return;
        const supplemental = _spcSupplementalSelections();
        const needsActiveRefresh = supplemental.mdsEnabled
            || supplemental.watchesEnabled;
        if (!needsActiveRefresh) return;
        refreshSpc();
    }, SPC_AUTO_REFRESH_MS);

    init();

    _updateSpcReportFilterState();

}());

