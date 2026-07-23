import { fetchCachedJson } from './api.js';

export const REGION_LABELS = Object.freeze({
    CONUS: 'CONUS', WORLD: 'World', NC: 'North Carolina', SC: 'South Carolina',
    VA: 'Virginia', TN: 'Tennessee', AL: 'Alabama', AK: 'Alaska', AZ: 'Arizona',
    AR: 'Arkansas', CA: 'California', CO: 'Colorado', CT: 'Connecticut',
    DE: 'Delaware', FL: 'Florida', GA: 'Georgia', HI: 'Hawaii', ID: 'Idaho',
    IL: 'Illinois', IN: 'Indiana', IA: 'Iowa', KS: 'Kansas', KY: 'Kentucky',
    LA: 'Louisiana', ME: 'Maine', MD: 'Maryland', MA: 'Massachusetts',
    MI: 'Michigan', MN: 'Minnesota', MS: 'Mississippi', MO: 'Missouri',
    MT: 'Montana', NE: 'Nebraska', NV: 'Nevada', NH: 'New Hampshire',
    NJ: 'New Jersey', NM: 'New Mexico', NY: 'New York', ND: 'North Dakota',
    OH: 'Ohio', OK: 'Oklahoma', OR: 'Oregon', PA: 'Pennsylvania',
    RI: 'Rhode Island', SD: 'South Dakota', TX: 'Texas', UT: 'Utah',
    VT: 'Vermont', WA: 'Washington', WV: 'West Virginia', WI: 'Wisconsin',
    WY: 'Wyoming', PR: 'Puerto Rico',
});

const REGION_BOUNDS = Object.freeze({
    WORLD: [-179.9, 179.9, -85.0, 85.0], CONUS: [-140, -65, 21, 52],
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
    PR: [-67.4, -65.1, 17.8, 18.6], RI: [-72.2, -70.8, 40.8, 42.4],
    SC: [-83.7, -78.1, 31.7, 35.6], SD: [-104.4, -96.1, 42.1, 46.3],
    TN: [-90.7, -81.3, 34.6, 37.0], TX: [-107.0, -93.1, 25.5, 36.9],
    UT: [-114.4, -108.7, 36.6, 42.4], VT: [-73.8, -71.1, 42.4, 45.4],
    VA: [-84.0, -74.8, 36.2, 39.8], WA: [-125.2, -116.6, 45.2, 49.4],
    WV: [-83.0, -77.4, 36.8, 41.0], WI: [-93.2, -86.4, 42.1, 47.4],
    WY: [-111.4, -103.7, 40.6, 45.4],
});

const BASEMAPS = Object.freeze({
    'Light (No Labels)': ['https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png', '© OpenStreetMap © CARTO'],
    'Dark (No Labels)': ['https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png', '© OpenStreetMap © CARTO'],
    Voyager: ['https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', '© OpenStreetMap © CARTO'],
    USGS: ['https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/{z}/{y}/{x}', 'Tiles courtesy of the U.S. Geological Survey'],
    Satellite: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', 'Tiles © Esri'],
});

const CITY_SOURCES = Object.freeze({
    us: '/data/us-cities-all.json',
    world: '/data/world-cities.json',
});
const CITY_LABEL_CHAR_PX = 5.2;
const CITY_LABEL_HEIGHT_PX = 11;
const CITY_LABEL_X_PAD = 4;
const CITY_LABEL_Y_PAD = 2;

function cityDistanceRangeKm(source, zoom) {
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

function haversineKm(lat1, lon1, lat2, lon2) {
    const radiusKm = 6371;
    const toRadians = Math.PI / 180;
    const dLat = (lat2 - lat1) * toRadians;
    const dLon = (lon2 - lon1) * toRadians;
    const a = Math.sin(dLat / 2) ** 2
        + Math.cos(lat1 * toRadians) * Math.cos(lat2 * toRadians) * Math.sin(dLon / 2) ** 2;
    return radiusKm * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function filterCitiesByDistance(cities, minDistanceKm) {
    if (!cities.length || minDistanceKm <= 0) return cities;
    const cellDegrees = minDistanceKm / 111;
    const grid = new Map();
    const accepted = [];
    for (const city of cities) {
        const latitude = Number(city.latitude);
        const longitude = Number(city.longitude);
        if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) continue;
        const row = Math.floor(latitude / cellDegrees);
        const column = Math.floor(longitude / cellDegrees);
        let tooClose = false;
        outer: for (let rowOffset = -2; rowOffset <= 2; rowOffset += 1) {
            for (let columnOffset = -2; columnOffset <= 2; columnOffset += 1) {
                const bucket = grid.get(`${row + rowOffset}:${column + columnOffset}`);
                if (!bucket) continue;
                for (const [otherLatitude, otherLongitude] of bucket) {
                    if (haversineKm(latitude, longitude, otherLatitude, otherLongitude) < minDistanceKm) {
                        tooClose = true;
                        break outer;
                    }
                }
            }
        }
        if (!tooClose) {
            accepted.push(city);
            const key = `${row}:${column}`;
            const bucket = grid.get(key);
            if (bucket) bucket.push([latitude, longitude]);
            else grid.set(key, [[latitude, longitude]]);
        }
    }
    return accepted;
}

function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, (character) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[character]));
}

// --- Dev tool: viewport extents logger (opt-in, global across every map page) --
// Enable from the browser console with mapViewportLog(true); turn off with (false).
// The flag lives in localStorage, so it survives page navigation and reloads. While
// on, panning or zooming any map prints the current view as a REGION_BOUNDS-ready
// [W, E, S, N] array plus center and zoom — for dialing in the default extents.
const VIEWPORT_LOG_KEY = 'nch:mapViewportLog';
const viewportLoggers = new Set();

function viewportLoggingEnabled() {
    try {
        return window.localStorage.getItem(VIEWPORT_LOG_KEY) === '1';
    } catch {
        return false;
    }
}

if (typeof window !== 'undefined' && typeof window.mapViewportLog !== 'function') {
    window.mapViewportLog = (on = true) => {
        const enabled = Boolean(on);
        try {
            window.localStorage.setItem(VIEWPORT_LOG_KEY, enabled ? '1' : '0');
        } catch {
            // localStorage blocked — logging still works for this page's session.
        }
        console.log(`[viewport] logging ${enabled ? 'ON — pan or zoom to capture a view' : 'OFF'}`);
        if (enabled) viewportLoggers.forEach((log) => log());
        return enabled;
    };
}

export function createMapCore(element, options = {}) {
    const leaflet = window.L;
    if (!leaflet) throw new Error('Leaflet failed to load.');
    const map = leaflet.map(element, { minZoom: 2, maxBounds: [[-85, -360], [85, 360]] });
    let baseLayer = null;
    let statePayloadPromise = null;
    let countyPayloadPromise = null;
    let countryPayloadPromise = null;
    let cityLayer = null;
    let citySource = 'off';
    let cityDensity = 0.25;
    let cityRequestSequence = 0;
    let activeRegion = String(options.region || 'CONUS').toUpperCase();
    const cityDataBySource = new Map();
    const overlays = new Map();

    const boundaryPane = map.createPane('boundary-lines');
    boundaryPane.style.zIndex = '420';
    boundaryPane.style.pointerEvents = 'none';

    const LogoControl = leaflet.Control.extend({
        options: { position: 'topright' },
        onAdd() {
            const root = leaflet.DomUtil.create('div', 'core-map-logo leaflet-control');
            const image = leaflet.DomUtil.create('img', '', root);
            image.src = '/img/nchurricane_logo.png';
            image.alt = 'NCHurricane.com';
            image.loading = 'lazy';
            return root;
        },
    });
    new LogoControl().addTo(map);

    const ResetViewControl = leaflet.Control.extend({
        options: { position: 'topleft' },
        onAdd() {
            const root = leaflet.DomUtil.create('div', 'core-reset-view leaflet-bar');
            const button = leaflet.DomUtil.create('button', '', root);
            button.type = 'button';
            button.title = 'Reset to selected region';
            button.setAttribute('aria-label', 'Reset to selected region');
            button.textContent = '⌂';
            leaflet.DomEvent.disableClickPropagation(root);
            leaflet.DomEvent.on(button, 'click', () => {
                options.onResetView?.();
                fitRegion(activeRegion);
            });
            return root;
        },
    });
    new ResetViewControl().addTo(map);

    const zoomContainer = map.zoomControl?.getContainer?.();
    const zoomIndicator = zoomContainer ? leaflet.DomUtil.create('div', 'core-zoom-indicator', zoomContainer) : null;
    if (zoomIndicator) {
        zoomIndicator.setAttribute('role', 'status');
        zoomIndicator.setAttribute('aria-live', 'polite');
    }
    const updateZoomIndicator = () => {
        if (!zoomIndicator) return;
        const zoom = Number(map.getZoom()) || 0;
        zoomIndicator.textContent = `z ${Math.round(zoom)}`;
        zoomIndicator.title = `Zoom ${zoom.toFixed(2)}`;
    };
    map.on('zoom zoomend resize', updateZoomIndicator);

    // Prints the current view in REGION_BOUNDS order ([W, E, S, N]) so the numbers can
    // be pasted straight into that table, plus center/zoom for setView-style defaults.
    function logViewport() {
        const bounds = map.getBounds();
        const round = (value) => Number(value.toFixed(2));
        const center = map.getCenter();
        console.log(
            `%c[viewport]%c ${activeRegion}  [W, E, S, N] = `
            + `[${round(bounds.getWest())}, ${round(bounds.getEast())}, `
            + `${round(bounds.getSouth())}, ${round(bounds.getNorth())}]`
            + `  center [${round(center.lat)}, ${round(center.lng)}]  zoom ${round(map.getZoom())}`,
            'color:#38bdf8;font-weight:700',
            'color:inherit',
        );
    }
    const logViewportIfEnabled = () => { if (viewportLoggingEnabled()) logViewport(); };
    map.on('moveend', logViewportIfEnabled);
    viewportLoggers.add(logViewport);

    function setBasemap(name) {
        const selected = BASEMAPS[name] ? name : 'Dark (No Labels)';
        if (baseLayer) map.removeLayer(baseLayer);
        const [url, attribution] = BASEMAPS[selected];
        baseLayer = leaflet.tileLayer(url, {
            attribution, maxZoom: 19, subdomains: 'abcd', noWrap: false,
        }).addTo(map);
        return selected;
    }

    function fitRegion(code, fitOptions = {}) {
        activeRegion = REGION_BOUNDS[String(code || '').toUpperCase()]
            ? String(code).toUpperCase() : 'CONUS';
        const bounds = REGION_BOUNDS[activeRegion];
        map.fitBounds([[bounds[2], bounds[0]], [bounds[3], bounds[1]]], {
            animate: fitOptions.animate === true,
            padding: fitOptions.padding || [16, 16],
        });
    }

    async function ensureUsBoundaryLayer(name) {
        const isCounty = name === 'counties';
        const layerName = isCounty ? 'county' : 'state';
        if (isCounty && !countyPayloadPromise) {
            countyPayloadPromise = fetchCachedJson('/api/overlay/us-boundaries?layer=county&v=4');
        }
        if (!isCounty && !statePayloadPromise) {
            statePayloadPromise = fetchCachedJson('/api/overlay/us-boundaries?layer=state&v=4');
        }
        const payload = await (isCounty ? countyPayloadPromise : statePayloadPromise);
        const features = Array.isArray(payload?.features)
            ? payload.features.filter((feature) => feature?.properties?.layer === layerName)
            : [];
        if (overlays.has(name)) return;
        overlays.set(name, leaflet.geoJSON({ type: 'FeatureCollection', features }, {
            pane: 'boundary-lines',
            style: isCounty
                ? { color: '#a9bfd0', weight: 0.5, opacity: 0.5, fillOpacity: 0 }
                : { color: '#f4f8fb', weight: 1.1, opacity: 0.9, fillOpacity: 0 },
            interactive: false,
        }));
    }

    async function ensureCountries() {
        if (!countryPayloadPromise) {
            countryPayloadPromise = fetchCachedJson('/api/overlay/world-borders?v=3');
        }
        const payload = await countryPayloadPromise;
        if (!overlays.has('countries')) {
            overlays.set('countries', leaflet.geoJSON(payload, {
                pane: 'boundary-lines',
                style: { color: '#d7e5ef', weight: 1.1, opacity: 0.8, fillOpacity: 0 },
                interactive: false,
            }));
        }
    }

    function ensureGraticule() {
        if (overlays.has('graticule')) return;
        const group = leaflet.featureGroup();
        for (let latitude = -85; latitude <= 85; latitude += 5) {
            group.addLayer(leaflet.polyline([[latitude, -180], [latitude, 180]], {
                color: '#d8e3eb',
                weight: latitude % 10 === 0 ? 1 : 0.6,
                opacity: latitude % 10 === 0 ? 0.48 : 0.28,
                dashArray: '3, 4',
                interactive: false,
            }));
        }
        for (let longitude = -180; longitude < 180; longitude += 5) {
            group.addLayer(leaflet.polyline([[-85, longitude], [85, longitude]], {
                color: '#d8e3eb',
                weight: longitude % 10 === 0 ? 1 : 0.6,
                opacity: longitude % 10 === 0 ? 0.48 : 0.28,
                dashArray: '3, 4',
                interactive: false,
            }));
        }
        overlays.set('graticule', group);
    }

    async function setOverlayVisible(name, visible) {
        if (name === 'states' || name === 'counties') await ensureUsBoundaryLayer(name);
        else if (name === 'countries') await ensureCountries();
        else if (name === 'graticule') ensureGraticule();
        else throw new Error(`Unknown map overlay: ${name}`);

        const layer = overlays.get(name);
        if (visible && layer && !map.hasLayer(layer)) layer.addTo(map);
        if (!visible && layer && map.hasLayer(layer)) map.removeLayer(layer);
    }

    function getCityMinDistanceKm(source = citySource, density = cityDensity) {
        const selectedSource = CITY_SOURCES[source] ? source : 'us';
        const selectedDensity = Math.max(0.01, Math.min(1, Number(density) || 0.25));
        const { min, max } = cityDistanceRangeKm(selectedSource, map.getZoom());
        return max - ((max - min) * selectedDensity);
    }

    function removeCityLayer() {
        if (cityLayer && map.hasLayer(cityLayer)) map.removeLayer(cityLayer);
        cityLayer = null;
    }

    function createCityMarker(city) {
        const cityName = String(city.city || city.name || '');
        const width = Math.max(14, Math.min(220, cityName.length * CITY_LABEL_CHAR_PX + CITY_LABEL_X_PAD * 2));
        const height = CITY_LABEL_HEIGHT_PX + CITY_LABEL_Y_PAD * 2;
        return leaflet.marker([Number(city.latitude), Number(city.longitude)], {
            interactive: false,
            keyboard: false,
            icon: leaflet.divIcon({
                className: 'core-city-name-tag',
                html: `<span>${escapeHtml(cityName)}</span>`,
                iconSize: [width, height],
                iconAnchor: [Math.round(width / 2), Math.round(height / 2)],
            }),
        });
    }

    function rebuildCityLayer() {
        removeCityLayer();
        const cityData = cityDataBySource.get(citySource);
        if (!cityData?.length) return;
        const bounds = map.getBounds().pad(0.1);
        const visibleCities = cityData.filter((city) => {
            const latitude = Number(city.latitude);
            const longitude = Number(city.longitude);
            return Number.isFinite(latitude) && Number.isFinite(longitude)
                && latitude >= bounds.getSouth() && latitude <= bounds.getNorth()
                && longitude >= bounds.getWest() && longitude <= bounds.getEast();
        });
        const thinnedCities = filterCitiesByDistance(visibleCities, getCityMinDistanceKm());
        cityLayer = leaflet.layerGroup(thinnedCities.map(createCityMarker)).addTo(map);
    }

    async function setCitySource(source) {
        const selectedSource = CITY_SOURCES[source] ? source : 'off';
        citySource = selectedSource;
        cityRequestSequence += 1;
        const requestSequence = cityRequestSequence;
        removeCityLayer();
        if (selectedSource === 'off') return;
        if (!cityDataBySource.has(selectedSource)) {
            const payload = await fetchCachedJson(`${CITY_SOURCES[selectedSource]}?v=1`);
            if (requestSequence !== cityRequestSequence) return;
            cityDataBySource.set(selectedSource, Array.isArray(payload) ? payload : []);
        }
        if (requestSequence === cityRequestSequence && citySource === selectedSource) rebuildCityLayer();
    }

    function setCityDensity(value) {
        cityDensity = Math.max(0.01, Math.min(1, Number(value) || 0.25));
        if (citySource !== 'off' && cityDataBySource.has(citySource)) rebuildCityLayer();
        return cityDensity;
    }

    function setCityFontSize(value) {
        const fontSize = Math.max(0.4, Math.min(1.2, Number(value) || 0.6));
        map.getContainer().style.setProperty('--city-font-size', String(fontSize));
        return fontSize;
    }

    setBasemap(options.basemap || 'Dark (No Labels)');
    fitRegion(options.region || 'CONUS');
    map.attributionControl.addAttribution('©2026 ChuckCopeland.com/NCHurricane.com');
    updateZoomIndicator();
    map.on('moveend', rebuildCityLayer);

    return Object.freeze({
        leaflet,
        map,
        fitRegion,
        getCityMinDistanceKm,
        setBasemap,
        setCityDensity,
        setCityFontSize,
        setCitySource,
        setOverlayVisible,
        destroy() {
            map.off('moveend', rebuildCityLayer);
            map.off('moveend', logViewportIfEnabled);
            map.off('zoom zoomend resize', updateZoomIndicator);
            viewportLoggers.delete(logViewport);
            map.remove();
        },
    });
}
