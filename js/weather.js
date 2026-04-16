(function () {
    'use strict';

    const byId = (id) => document.getElementById(id);

    // ── State Bounds [west, east, south, north] from geo_config.py ──────────
    // Leaflet fitBounds expects [[south, west], [north, east]]
    const STATE_BOUNDS = {
        CONUS: [-125, -70, 21, 52],
        AL: [-89.0, -84.4, 29.8, 35.7], AK: [-179.5, -129.6, 50.8, 71.8],
        AZ: [-115.8, -107.7, 29.7, 38.3], AR: [-95.0, -89.3, 32.7, 36.9],
        CA: [-124.9, -113.8, 32.2, 42.4], CO: [-109.4, -101.7, 36.6, 41.4],
        CT: [-74.1, -71.4, 40.6, 42.4],  DE: [-76.1, -74.7, 38.1, 40.2],
        FL: [-88.0, -79.6, 24.0, 31.4],  GA: [-86.0, -80.4, 30.0, 35.4],
        HI: [-160.6, -154.2, 18.2, 22.8], ID: [-117.6, -110.7, 41.6, 49.4],
        IL: [-91.9, -87.1, 36.6, 42.9],  IN: [-88.4, -84.4, 37.4, 42.1],
        IA: [-97.0, -89.8, 40.0, 43.9],  KS: [-102.4, -94.2, 36.6, 40.4],
        KY: [-89.9, -81.6, 36.1, 39.5],  LA: [-94.4, -88.4, 28.5, 33.4],
        ME: [-71.4, -66.5, 42.7, 47.8],  MD: [-79.8, -74.7, 37.5, 40.1],
        MA: [-73.9, -69.5, 40.8, 43.2],  MI: [-90.8, -82.0, 41.3, 48.7],
        MN: [-97.6, -89.1, 43.1, 49.7],  MS: [-92.0, -87.7, 29.8, 35.4],
        MO: [-96.1, -88.7, 35.6, 41.0],  MT: [-116.4, -103.7, 44.0, 49.4],
        NE: [-104.4, -94.9, 39.6, 43.4], NV: [-120.4, -113.7, 34.7, 42.4],
        NH: [-72.9, -70.3, 42.3, 45.7],  NJ: [-75.9, -73.5, 38.6, 41.7],
        NM: [-109.4, -102.7, 31.0, 37.4], NY: [-80.1, -71.4, 40.1, 45.4],
        NC: [-84.8, -74.7, 33.2, 37.3],  ND: [-104.4, -96.2, 45.6, 49.4],
        OH: [-85.2, -80.2, 38.1, 42.3],  OK: [-103.4, -94.1, 33.3, 37.4],
        OR: [-124.9, -116.1, 41.6, 46.6], PA: [-80.9, -74.3, 39.4, 42.6],
        RI: [-72.2, -70.8, 40.8, 42.4],  SC: [-83.7, -78.1, 31.7, 35.6],
        SD: [-104.4, -96.1, 42.1, 46.3], TN: [-90.7, -81.3, 34.6, 37.0],
        TX: [-107.0, -93.1, 25.5, 36.9], UT: [-114.4, -108.7, 36.6, 42.4],
        VT: [-73.8, -71.1, 42.4, 45.4],  VA: [-84.0, -74.8, 36.2, 39.8],
        WA: [-125.2, -116.6, 45.2, 49.4], WV: [-83.0, -77.4, 36.8, 41.0],
        WI: [-93.2, -86.4, 42.1, 47.4],  WY: [-111.4, -103.7, 40.6, 45.4],
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
        ENH:  { fill: '#ff9d2e', stroke: '#c85a00' },
        MDT:  { fill: '#ff4f4f', stroke: '#a00000' },
        HIGH: { fill: '#ff66ff', stroke: '#880088' },
    };

    const SPC_PROB_COLORS = {
        '2':  { fill: '#b5dcb3', stroke: '#5a9e61' },
        '5':  { fill: '#69bb6d', stroke: '#2d7a32' },
        '10': { fill: '#f5dd72', stroke: '#c8a000' },
        '15': { fill: '#ff9d2e', stroke: '#c85a00' },
        '30': { fill: '#ff4f4f', stroke: '#a00000' },
        '45': { fill: '#ff66ff', stroke: '#880088' },
        '60': { fill: '#ff00ff', stroke: '#880088' },
    };

    const SPC_FIRE_COLORS = {
        'Elevated':            { fill: '#FFBF80', stroke: '#FF7F00' },
        'Critical':            { fill: '#FF8080', stroke: '#FF0000' },
        'Extremely Critical':  { fill: '#FF80FF', stroke: '#FF00FF' },
        'Isolated':            { fill: '#FFBF80', stroke: '#FF7F00' },
        'Scattered':           { fill: '#FF8080', stroke: '#FF0000' },
    };

    // ── Alert colors (key event types) ──────────────────────────────────────
    const ALERT_COLORS = {
        'Tornado Warning':            '#FF0000',
        'Tornado Watch':              '#FFFF00',
        'Severe Thunderstorm Warning':'#FFA500',
        'Severe Thunderstorm Watch':  '#DB7093',
        'Flash Flood Warning':        '#8B0000',
        'Flash Flood Watch':          '#2E8B57',
        'Flood Warning':              '#00FF00',
        'Flash Flood Statement':      '#8B0000',
        'Winter Storm Warning':       '#FF69B4',
        'Blizzard Warning':           '#FF4500',
        'Ice Storm Warning':          '#8B008B',
        'Winter Weather Advisory':    '#7B68EE',
        'Hurricane Warning':          '#DC143C',
        'Hurricane Watch':            '#FF00FF',
        'Tropical Storm Warning':     '#B22222',
        'Tropical Storm Watch':       '#F08080',
        'Storm Surge Warning':        '#B524F7',
        'High Wind Warning':          '#DAA520',
        'Wind Advisory':              '#D2B48C',
        'Red Flag Warning':           '#FF1493',
        'Extreme Heat Warning':       '#C71585',
        'Heat Advisory':              '#FF7F50',
        'Dense Fog Advisory':         '#708090',
        'Freeze Warning':             '#483D8B',
        'Special Marine Warning':     '#FFA500',
        'Gale Warning':               '#DDA0DD',
    };
    const ALERT_DEFAULT = '#6699cc';

    // ── Alert category filter map ────────────────────────────────────────────
    const ALERT_CATEGORIES = {
        'Severe Weather Alerts':    ['Tornado Warning','Tornado Watch','Severe Thunderstorm Warning','Severe Thunderstorm Watch'],
        'Severe Weather Warnings':  ['Tornado Warning','Severe Thunderstorm Warning','Flash Flood Warning'],
        'Tropical Cyclone Alerts':  ['Hurricane Warning','Hurricane Watch','Tropical Storm Warning','Tropical Storm Watch','Storm Surge Warning'],
        'Hydrology Alerts':         ['Flood Warning','Flash Flood Warning','Flash Flood Watch','Flash Flood Statement'],
        'Flash Flood Alerts':       ['Flash Flood Warning','Flash Flood Watch','Flash Flood Statement'],
        'Winter Alerts':            ['Winter Storm Warning','Blizzard Warning','Ice Storm Warning','Winter Weather Advisory','Lake Effect Snow Warning'],
        'Cold Alerts':              ['Extreme Cold Warning','Freeze Warning','Frost Advisory','Cold Weather Advisory'],
        'Fire Alerts':              ['Red Flag Warning','Fire Warning'],
        'Heat Alerts':              ['Extreme Heat Warning','Heat Advisory'],
        'Coastal Alerts':           ['Storm Surge Warning','Storm Surge Watch','High Surf Warning','Coastal Flood Warning'],
        'Marine Alerts':            ['Special Marine Warning','Gale Warning','Storm Warning','Hazardous Seas Warning'],
        'Non-Precipitation Alerts': ['High Wind Warning','Wind Advisory','Dense Fog Advisory','Extreme Wind Warning'],
    };

    function matchesCategory(feat, category) {
        if (!category || category === 'All Alerts') return true;
        const events = ALERT_CATEGORIES[category];
        return events ? events.includes(feat?.properties?.event || '') : true;
    }

    // ── Map init ─────────────────────────────────────────────────────────────
    const tileOptions = {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
        subdomains: 'abcd',
        maxZoom: 19,
    };
    const tilesDark  = L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', tileOptions);
    const tilesLight = L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', tileOptions);

    const map = L.map('weather-map', { layers: [tilesDark] });
    map.fitBounds([[21, -125], [52, -70]]);

    L.control.layers({ 'Dark': tilesDark, 'Light': tilesLight }, {}, { position: 'topright' }).addTo(map);

    // ── Layer state ──────────────────────────────────────────────────────────
    let alertsLayer  = null;
    let spcLayer     = null;
    let legendCtrl   = null;
    let alertsOpacity = 0.75;
    let spcOpacity    = 0.60;

    // ── Style functions ──────────────────────────────────────────────────────
    function alertStyle(feat) {
        const color = ALERT_COLORS[feat?.properties?.event || ''] || ALERT_DEFAULT;
        return { color, weight: 1.5, fillColor: color, fillOpacity: alertsOpacity * 0.5, opacity: 0.9 };
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
        const event    = p.event    || 'Unknown Alert';
        const headline = p.headline || '';
        const expires  = p.expires  ? new Date(p.expires).toLocaleString() : '';
        const area     = p.areaDesc || '';
        return `<strong>${event}</strong><br>${headline}${expires ? '<br><em>Expires: ' + expires + '</em>' : ''}<br><small>${area}</small>`;
    }

    function spcPopup(feat) {
        const p     = feat.properties || {};
        const label = p.LABEL2 || p.label2 || p.LABEL || p.label || p.dn || '';
        return `<strong>${label}</strong>`;
    }

    // ── Legend helpers ───────────────────────────────────────────────────────
    function setLegend(html) {
        if (legendCtrl) { map.removeControl(legendCtrl); legendCtrl = null; }
        if (!html) return;
        legendCtrl = L.control({ position: 'bottomright' });
        legendCtrl.onAdd = () => {
            const div = L.DomUtil.create('div', 'map-legend');
            div.innerHTML = html;
            L.DomEvent.disableScrollPropagation(div);
            return div;
        };
        legendCtrl.addTo(map);
    }

    function swatch(color, label) {
        return `<div class="legend-row"><span class="legend-swatch" style="background:${color}"></span>${label}</div>`;
    }

    function buildAlertsLegend(features) {
        const events = [...new Set(features.map(f => f.properties?.event).filter(Boolean))];
        if (!events.length) { setLegend(null); return; }
        const rows = events.map(e => swatch(ALERT_COLORS[e] || ALERT_DEFAULT, e)).join('');
        setLegend('<h4>Active Alerts</h4>' + rows);
    }

    function buildSpcCatLegend() {
        const rows = [
            ['#ff66ff','High'], ['#ff4f4f','Moderate'], ['#ff9d2e','Enhanced'],
            ['#f5dd72','Slight'], ['#69bb6d','Marginal'], ['#b5dcb3','T-Storms'],
        ].map(([c, l]) => swatch(c, l)).join('');
        setLegend('<h4>SPC Categorical</h4>' + rows);
    }

    function buildSpcFireLegend(hazard) {
        if (hazard === 'dryt') {
            const rows = [swatch('#FF8080','Scattered Dry T-Storm'), swatch('#FFBF80','Isolated Dry T-Storm')].join('');
            setLegend('<h4>SPC Fire Wx (Dry T-Storm)</h4>' + rows);
        } else {
            const rows = [swatch('#FF80FF','Extremely Critical'), swatch('#FF8080','Critical'), swatch('#FFBF80','Elevated')].join('');
            setLegend('<h4>SPC Fire Wx (Wind/RH)</h4>' + rows);
        }
    }

    // ── Data loaders ─────────────────────────────────────────────────────────
    function setStatus(msg) {
        const el = byId('weather-map-status');
        if (el) el.textContent = msg;
    }

    async function loadAlerts(category) {
        if (alertsLayer) { map.removeLayer(alertsLayer); alertsLayer = null; }
        setStatus('Loading alerts...');
        try {
            const resp = await fetch(apiUrl('/api/data/alerts'));
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const geojson = await resp.json();

            let features = (geojson.features || []).filter(f => matchesCategory(f, category));
            alertsLayer = L.geoJSON({ type: 'FeatureCollection', features }, {
                style: alertStyle,
                onEachFeature: (feat, layer) => layer.bindPopup(alertPopup(feat)),
            });

            if (byId('weather-show-alerts')?.checked !== false) alertsLayer.addTo(map);
            buildAlertsLegend(features);

            const countEl = byId('weather-alerts-count');
            if (countEl) countEl.textContent = `${features.length} active alert(s)`;
            setStatus(`Alerts updated — ${new Date().toLocaleTimeString()}`);
        } catch (err) {
            console.error('[alerts] Load error:', err);
            setStatus(`Alerts error: ${err.message}`);
        }
    }

    async function loadSpc(day, hazard) {
        if (spcLayer) { map.removeLayer(spcLayer); spcLayer = null; }
        const isFireHazard = hazard === 'windrh' || hazard === 'dryt';
        setStatus(`Loading SPC Day ${day} ${hazard}...`);
        try {
            const resp = await fetch(apiUrl(`/api/data/spc?day=${day}&hazard=${hazard}`));
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const geojson = await resp.json();

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

            if (byId('weather-show-spc')?.checked !== false) spcLayer.addTo(map);

            if (isFireHazard) buildSpcFireLegend(hazard);
            else if (hazard === 'cat') buildSpcCatLegend();
            else setLegend(null);

            const count = (geojson.features || []).length;
            const countEl = byId('weather-spc-count');
            if (countEl) countEl.textContent = `${count} feature(s)`;
            setStatus(`SPC Day ${day} ${hazard} updated — ${new Date().toLocaleTimeString()}`);
        } catch (err) {
            console.error('[spc] Load error:', err);
            setStatus(`SPC error: ${err.message}`);
        }
    }

    // ── Region → fitBounds ───────────────────────────────────────────────────
    function fitRegion(code) {
        const b = leafletBounds((code || 'CONUS').toUpperCase());
        if (b) map.fitBounds(b);
    }

    // ── Product group switching ──────────────────────────────────────────────
    function updateProductOpts() {
        const group = byId('weather-product-group')?.value || 'alerts';
        document.querySelectorAll('.weather-product-opts').forEach(el => { el.style.display = 'none'; });
        const target = byId(`weather-${group}-opts`);
        if (target) target.style.display = '';
    }

    function refreshActiveLayers() {
        const group = byId('weather-product-group')?.value || 'alerts';
        if (group === 'alerts') {
            const cat = byId('weather-alerts-product')?.value || 'All Alerts';
            loadAlerts(cat);
        } else if (group === 'spc') {
            refreshSpc();
        } else if (group === 'surface') {
            const region = byId('weather-region')?.value || 'NC';
            const product = byId('weather-surface-product')?.value || 'temperature';
            loadSurface(region, product);
        } else if (group === 'mrms') {
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
        if (alertsLayer) {
            alertsLayer.setStyle((feat) => alertStyle(feat));
        }
    }

    function applySpcOpacity(val) {
        spcOpacity = parseFloat(val);
        if (spcLayer) {
            const group = byId('weather-product-group')?.value || '';
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
    let surfaceLayer = null;
    let surfaceOpacity = 0.9;
    let _surfaceStations = [];   // full unfiltered station list for re-thinning on zoom

    function surfaceMarkerIcon(value, color, unit, opacity) {
        const label = unit === '°F' || unit === '%' || unit === 'kt'
            ? Math.round(value)
            : value.toFixed(1);
        const alpha = Math.round(opacity * 255).toString(16).padStart(2, '0');
        return L.divIcon({
            className: '',
            html: `<div class="sfc-marker" style="background:${color}${alpha}">${label}</div>`,
            iconSize: [32, 32],
            iconAnchor: [16, 16],
        });
    }

    function _thinStations(stations) {
        const zoom = map.getZoom();
        if (zoom >= 8) return stations;
        if (zoom >= 6) return stations.filter((_, i) => i % 2 === 0);
        return stations.filter((_, i) => i % 4 === 0);
    }

    function _renderSurfaceMarkers(stations) {
        if (surfaceLayer) { map.removeLayer(surfaceLayer); surfaceLayer = null; }
        if (!stations.length) return;

        const thin = _thinStations(stations);
        surfaceLayer = L.layerGroup(
            thin.map(s => {
                const icon = surfaceMarkerIcon(s.value, s.color, s.unit, surfaceOpacity);
                const m = L.marker([s.lat, s.lon], { icon });
                const wdir = s.wind_dir != null ? `${Math.round(s.wind_dir)}°` : '—';
                const wspd = s.wind_speed != null ? `${Math.round(s.wind_speed)} kt` : '—';
                const gust = s.wind_gust != null ? ` G${Math.round(s.wind_gust)}` : '';
                const vis  = s.visibility != null ? `${s.visibility} mi` : '—';
                m.bindPopup(
                    `<strong>${s.id}</strong><br>` +
                    `Temp: ${s.temperature != null ? s.temperature + '°F' : '—'}<br>` +
                    `Feels Like: ${s.feels_like != null ? s.feels_like + '°F' : '—'}<br>` +
                    `Dew Point: ${s.dew_point != null ? s.dew_point + '°F' : '—'}<br>` +
                    `RH: ${s.rh != null ? s.rh + '%' : '—'}<br>` +
                    `Wind: ${wdir} @ ${wspd}${gust}<br>` +
                    `Visibility: ${vis}`
                );
                return m;
            })
        );
        if (byId('weather-show-surface')?.checked !== false) surfaceLayer.addTo(map);
    }

    async function loadSurface(region, product) {
        setStatus(`Loading ${product} for ${region}...`);
        try {
            const url = apiUrl(`/api/data/surface?region=${encodeURIComponent(region)}&product=${encodeURIComponent(product)}`);
            const resp = await fetch(url);
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json();

            _surfaceStations = data.stations || [];
            _renderSurfaceMarkers(_surfaceStations);

            // Legend
            const anchors = _SURFACE_COLORMAPS[product] || _SURFACE_COLORMAPS['temperature'];
            buildSurfaceLegend(data.unit || '°F', anchors, product);

            const countEl = byId('weather-surface-count');
            if (countEl) countEl.textContent = `${_surfaceStations.length} station(s)`;
            setStatus(`${product} updated — ${new Date().toLocaleTimeString()}`);
        } catch (err) {
            console.error('[surface] Load error:', err);
            setStatus(`Surface error: ${err.message}`);
        }
    }

    // Client-side colormap anchors for the legend (mirror of server-side _SURFACE_PRODUCTS)
    const _SURFACE_COLORMAPS = {
        temperature:       [[-60,'#00352C'],[-20,'#c4c4d4'],[0,'#570057'],[32,'#0000ff'],[50,'#c4c403'],[80,'#c20303'],[130,'#000000']],
        feels_like:        [[-60,'#00352C'],[-20,'#c4c4d4'],[0,'#570057'],[32,'#0000ff'],[50,'#c4c403'],[80,'#c20303'],[130,'#000000']],
        dew_point:         [[-60,'#00352C'],[-20,'#c4c4d4'],[0,'#570057'],[32,'#0000ff'],[50,'#c4c403'],[80,'#c20303'],[130,'#000000']],
        relative_humidity: [[0,'#c8a000'],[20,'#f5dd72'],[40,'#69bb6d'],[60,'#0099cc'],[80,'#0055aa'],[100,'#003377']],
        wind_speed:        [[0,'#b0d4f0'],[10,'#70b0e0'],[20,'#3090d0'],[30,'#f5dd72'],[45,'#ff9d2e'],[60,'#ff4f4f']],
        wind_gust:         [[0,'#b0d4f0'],[10,'#70b0e0'],[20,'#3090d0'],[30,'#f5dd72'],[45,'#ff9d2e'],[60,'#ff4f4f']],
    };

    function buildSurfaceLegend(unit, anchors, product) {
        const label = product.replace(/_/g, ' ');
        const rows = [...anchors].reverse().map(([v, c]) => swatch(c, `${v}${unit}`)).join('');
        setLegend(`<h4>Surface: ${label}</h4>${rows}`);
    }

    function applySurfaceOpacity(val) {
        surfaceOpacity = parseFloat(val);
        // Re-render markers with new opacity baked into icon color
        if (_surfaceStations.length) _renderSurfaceMarkers(_surfaceStations);
    }

    // Re-thin on zoom change if surface layer is active
    map.on('zoomend', () => {
        if (_surfaceStations.length && byId('weather-product-group')?.value === 'surface') {
            _renderSurfaceMarkers(_surfaceStations);
        }
    });

    // ── MRMS layer ────────────────────────────────────────────────────────────
    let mrmsOverlay = null;
    let mrmsOpacity = 0.8;

    // composeMrmsProductKey: mirrors Python MRMS_PRODUCTS key structure
    function composeMrmsProductKey() {
        const family = byId('weather-mrms-family')?.value || 'PrecipRate';
        // Standalone products (no sub-selector)
        const standalone = ['PrecipRate', 'PrecipFlag', 'SHI', 'POSH', 'RadarQualityIndex'];
        if (standalone.includes(family)) return family;

        if (family === 'QPE') {
            const src = byId('mrms-qpe-source')?.value || 'MS2';
            const per = byId('mrms-qpe-period')?.value || '01H';
            return `QPE_${src}_${per}`;
        }
        if (family === 'RotationTrack') {
            const lvl  = byId('mrms-rotation-level')?.value || 'LL';
            const time = byId('mrms-rotation-time')?.value  || '60min';
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
        const family = byId('weather-mrms-family')?.value || 'PrecipRate';
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
        const product = composeMrmsProductKey();
        const bounds  = map.getBounds();
        const s = bounds.getSouth().toFixed(4);
        const w = bounds.getWest().toFixed(4);
        const n = bounds.getNorth().toFixed(4);
        const e = bounds.getEast().toFixed(4);

        const statusEl = byId('weather-mrms-status');
        if (statusEl) statusEl.textContent = `Loading ${product}…`;
        setStatus(`Loading MRMS ${product}…`);

        try {
            const url = apiUrl(`/api/data/mrms?product=${encodeURIComponent(product)}&south=${s}&west=${w}&north=${n}&east=${e}`);
            const resp = await fetch(url);
            if (!resp.ok) {
                const err = await resp.json().catch(() => ({ detail: resp.statusText }));
                throw new Error(err.detail || resp.statusText);
            }
            const data = await resp.json();

            if (mrmsOverlay) { map.removeLayer(mrmsOverlay); mrmsOverlay = null; }

            // Leaflet imageOverlay: [[south, west], [north, east]]
            const b = data.bounds; // [west, east, south, north]
            const leafletBounds = [[b[2], b[0]], [b[3], b[1]]];
            mrmsOverlay = L.imageOverlay(data.image_url, leafletBounds, { opacity: mrmsOpacity });
            if (byId('weather-show-mrms')?.checked !== false) mrmsOverlay.addTo(map);

            buildMrmsLegend(data);

            if (statusEl) statusEl.textContent = `${data.full_name} — ${new Date().toLocaleTimeString()}`;
            setStatus(`MRMS ${product} updated — ${new Date().toLocaleTimeString()}`);
        } catch (err) {
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
    byId('weather-region')?.addEventListener('change', (e) => {
        fitRegion(e.target.value);
        refreshActiveLayers();
    });

    byId('weather-product-group')?.addEventListener('change', () => {
        updateProductOpts();
        refreshActiveLayers();
    });

    byId('weather-alerts-product')?.addEventListener('change', () => {
        if ((byId('weather-product-group')?.value || '') === 'alerts') {
            loadAlerts(byId('weather-alerts-product').value);
        }
    });

    byId('weather-spc-day')?.addEventListener('change', refreshSpc);

    byId('weather-spc-convective')?.addEventListener('change', () => {
        _spcLastTouched = 'convective';
        if (byId('weather-spc-fire')) byId('weather-spc-fire').value = '';
        refreshSpc();
    });

    byId('weather-spc-fire')?.addEventListener('change', () => {
        _spcLastTouched = 'fire';
        if (byId('weather-spc-convective')) byId('weather-spc-convective').value = '';
        refreshSpc();
    });

    byId('weather-surface-product')?.addEventListener('change', () => {
        if ((byId('weather-product-group')?.value || '') === 'surface') {
            const region = byId('weather-region')?.value || 'NC';
            const product = byId('weather-surface-product')?.value || 'temperature';
            loadSurface(region, product);
        }
    });

    byId('weather-show-alerts')?.addEventListener('change', (e) => {
        if (!alertsLayer) return;
        e.target.checked ? alertsLayer.addTo(map) : map.removeLayer(alertsLayer);
    });

    byId('weather-show-spc')?.addEventListener('change', (e) => {
        if (!spcLayer) return;
        e.target.checked ? spcLayer.addTo(map) : map.removeLayer(spcLayer);
    });

    byId('weather-show-surface')?.addEventListener('change', (e) => {
        if (!surfaceLayer) return;
        e.target.checked ? surfaceLayer.addTo(map) : map.removeLayer(surfaceLayer);
    });

    byId('weather-opacity-alerts')?.addEventListener('input', (e) => applyAlertsOpacity(e.target.value));
    byId('weather-opacity-spc')?.addEventListener('input', (e) => applySpcOpacity(e.target.value));
    byId('weather-opacity-surface')?.addEventListener('input', (e) => applySurfaceOpacity(e.target.value));
    byId('weather-opacity-mrms')?.addEventListener('input', (e) => applyMrmsOpacity(e.target.value));

    byId('weather-show-mrms')?.addEventListener('change', (e) => {
        if (!mrmsOverlay) return;
        e.target.checked ? mrmsOverlay.addTo(map) : map.removeLayer(mrmsOverlay);
    });

    byId('weather-mrms-family')?.addEventListener('change', () => {
        updateMrmsSubControls();
        if ((byId('weather-product-group')?.value || '') === 'mrms') loadMrms();
    });

    // Wire all MRMS sub-selectors to reload on change
    ['mrms-qpe-source','mrms-qpe-period','mrms-rotation-level','mrms-rotation-time',
     'mrms-mesh-time','mrms-azshear-level','mrms-echotop-threshold','mrms-vil-type',
     'mrms-refl-variant','mrms-lightning-window','mrms-model-field'].forEach(id => {
        byId(id)?.addEventListener('change', () => {
            if ((byId('weather-product-group')?.value || '') === 'mrms') loadMrms();
        });
    });

    byId('weather-refresh-mrms')?.addEventListener('click', loadMrms);

    byId('weather-refresh-alerts')?.addEventListener('click', () => {
        const cat = byId('weather-alerts-product')?.value || 'All Alerts';
        loadAlerts(cat);
    });

    byId('weather-refresh-spc')?.addEventListener('click', refreshSpc);

    byId('weather-refresh-surface')?.addEventListener('click', () => {
        const region = byId('weather-region')?.value || 'NC';
        const product = byId('weather-surface-product')?.value || 'temperature';
        loadSurface(region, product);
    });

    // ── Init ─────────────────────────────────────────────────────────────────
    function init() {
        updateProductOpts();
        updateMrmsSubControls();
        loadAlerts(null);
        loadSpc(1, 'cat');
    }

    init();

}());

