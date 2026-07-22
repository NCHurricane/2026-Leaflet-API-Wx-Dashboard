import { apiUrl } from '../../core/api.js';

function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, (char) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[char]));
}

export const SURFACE_PRODUCTS = Object.freeze([
    { key: 'temperature', label: 'Temperature', unit: '°F' },
    { key: 'feels_like', label: 'Feels Like', unit: '°F' },
    { key: 'dew_point', label: 'Dew Point', unit: '°F' },
    { key: 'relative_humidity', label: 'Relative Humidity', unit: '%' },
    { key: 'wind_speed', label: 'Wind Speed', unit: 'kt' },
    { key: 'wind_gust', label: 'Wind Gust', unit: 'kt' },
    { key: 'altimeter', label: 'Altimeter', unit: 'inHg' },
    { key: 'mslp', label: 'MSLP', unit: 'hPa' },
    { key: 'visibility', label: 'Visibility', unit: 'mi' },
]);

export const SURFACE_PRODUCT_LABELS = Object.freeze(
    Object.fromEntries(SURFACE_PRODUCTS.map(({ key, label }) => [key, label])),
);

export const SURFACE_PRODUCT_UNITS = Object.freeze(
    Object.fromEntries(SURFACE_PRODUCTS.map(({ key, unit }) => [key, unit])),
);

// Client-side colormap anchors (mirror of the server-side _SURFACE_PRODUCTS).
export const SURFACE_COLORMAPS = Object.freeze({
    temperature: [[-60, '#00352C'], [-20, '#c4c4d4'], [0, '#570057'], [32, '#0000ff'], [50, '#c4c403'], [80, '#c20303'], [130, '#000000']],
    feels_like: [[-60, '#00352C'], [-20, '#c4c4d4'], [0, '#570057'], [32, '#0000ff'], [50, '#c4c403'], [80, '#c20303'], [130, '#000000']],
    dew_point: [[-60, '#00352C'], [-20, '#c4c4d4'], [0, '#570057'], [32, '#0000ff'], [50, '#c4c403'], [80, '#c20303'], [130, '#000000']],
    relative_humidity: [[0, '#c8a000'], [20, '#f5dd72'], [40, '#69bb6d'], [60, '#0099cc'], [80, '#0055aa'], [100, '#003377']],
    wind_speed: [[0, '#b0d4f0'], [10, '#70b0e0'], [20, '#3090d0'], [30, '#f5dd72'], [45, '#ff9d2e'], [60, '#ff4f4f']],
    wind_gust: [[0, '#b0d4f0'], [10, '#70b0e0'], [20, '#3090d0'], [30, '#f5dd72'], [45, '#ff9d2e'], [60, '#ff4f4f']],
    altimeter: [[29.5, '#5b1a8f'], [30.0, '#2a6db3'], [30.2, '#2ca58d'], [30.4, '#f5dd72'], [30.6, '#ff9d2e'], [30.8, '#bf2c2c']],
    mslp: [[990, '#5b1a8f'], [1000, '#2a6db3'], [1010, '#2ca58d'], [1020, '#f5dd72'], [1030, '#ff9d2e'], [1040, '#bf2c2c']],
    visibility: [[0, '#7f1d1d'], [1, '#b45309'], [3, '#d97706'], [5, '#65a30d'], [7, '#16a34a'], [10, '#0ea5e9']],
});

// Fixed seam-dissolving blur for the client-canvas gradient fallback; the
// worker PNG path never blurs, so this is not user-adjustable.
const FALLBACK_BLUR_SCALE = 1.0;

// Temporary 32F isotherm diagnostic on the client-canvas gradient fallback.
const FREEZING_ISOTHERM_ENABLED = true;
const FREEZING_ISOTHERM_PRODUCTS = new Set(['temperature', 'feels_like', 'dew_point']);

const VALUE_MARKER_OFFSET_X_PX = 0;
const VALUE_MARKER_OFFSET_Y_PX = -15;

// Base minimum station separation (km) by zoom level; WORLD gets an extra
// coarse tier because global observations are very dense.
export function baseDistKm(zoom, region) {
    if (String(region || '').toUpperCase() === 'WORLD') {
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

function haversineKm(lat1, lon1, lat2, lon2) {
    const R = 6371;
    const dLat = (lat2 - lat1) * Math.PI / 180;
    const dLon = (lon2 - lon1) * Math.PI / 180;
    const a = Math.sin(dLat / 2) ** 2
        + Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.sin(dLon / 2) ** 2;
    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function wrappedLonDeltaDeg(a, b) {
    const raw = Math.abs(a - b);
    return raw > 180 ? 360 - raw : raw;
}

function haversineKmWrapped(lat1, lon1, lat2, lon2) {
    const R = 6371;
    const dLat = (lat2 - lat1) * Math.PI / 180;
    const dLon = wrappedLonDeltaDeg(lon2, lon1) * Math.PI / 180;
    const phi1 = lat1 * Math.PI / 180;
    const phi2 = lat2 * Math.PI / 180;
    const a = Math.sin(dLat / 2) ** 2
        + Math.cos(phi1) * Math.cos(phi2) * Math.sin(dLon / 2) ** 2;
    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

// Filters items so no two are closer than minDistKm, processed in order.
// Uses a lat/lon bucket grid for O(n) average performance.
function filterByMinDistKm(items, minDistKm) {
    if (!items.length || minDistKm <= 0) return items;
    const cellDeg = minDistKm / 111;
    const grid = new Map();
    const accepted = [];

    for (const item of items) {
        const lat = item.lat;
        const lon = item.lon;
        if (!Number.isFinite(lat) || !Number.isFinite(lon)) continue;

        const row = Math.floor(lat / cellDeg);
        const col = Math.floor(lon / cellDeg);
        let tooClose = false;

        outer: for (let dr = -2; dr <= 2; dr += 1) {
            for (let dc = -2; dc <= 2; dc += 1) {
                const bucket = grid.get(`${row + dr}:${col + dc}`);
                if (!bucket) continue;
                for (const [bLat, bLon] of bucket) {
                    if (haversineKm(lat, lon, bLat, bLon) < minDistKm) {
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

// ── Mercator helpers (match Leaflet's EPSG:3857 projection) ─────────────────
function latToMercY(latDeg) {
    const latRad = latDeg * Math.PI / 180;
    return Math.log(Math.tan(Math.PI / 4 + latRad / 2));
}

function mercYToLat(mercY) {
    return (2 * Math.atan(Math.exp(mercY)) - Math.PI / 2) * 180 / Math.PI;
}

function gradientNeighborConfig(zoom, region) {
    if (region === 'WORLD') {
        if (zoom <= 3) {
            // Sector-balanced: directionally fair selection with wide influence
            // so sparse cold stations are reachable.
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

function gradientGridResolution(zoom, region) {
    if (region === 'WORLD') {
        if (zoom <= 3) return 10;
        if (zoom <= 5) return 12;
        return 8;
    }
    if (zoom <= 5) return 8;
    return 6;
}

// IDW (Inverse Distance Weighting) interpolation for a single point.
function idwInterpolate(x, y, stations, cfg) {
    if (!stations.length) return NaN;

    const {
        maxNeighbors,
        maxInfluenceKm,
        idwPower = 2,
        sectorBalance = false,
        _maxLatDeltaDeg,
        _prefilterKm,
    } = cfg;
    const nearStationKm = 8;
    let fallbackApproxKm = Infinity;
    let fallbackValue = NaN;

    // Sector-balanced mode keeps 8 angular buffers so sparse cold-latitude
    // stations get equal representation against dense warm clusters.
    const NUM_SECTORS = 8;
    const SECTOR_SIZE = (2 * Math.PI) / NUM_SECTORS;
    const perSector = Math.max(1, Math.ceil(maxNeighbors / NUM_SECTORS));
    const sectors = sectorBalance ? Array.from({ length: NUM_SECTORS }, () => []) : null;
    const nearest = sectorBalance ? null : [];

    const cosLat = Math.max(0.2, Math.cos(y * Math.PI / 180));

    for (const s of stations) {
        const latDelta = Math.abs(s.lat - y);
        if (latDelta > _maxLatDeltaDeg) continue;

        const lonDelta = wrappedLonDeltaDeg(s.lon, x);
        const approxKm = Math.sqrt(latDelta ** 2 + (lonDelta * cosLat) ** 2) * 111;

        // Fast prefilter before expensive trig distance.
        if (approxKm > _prefilterKm) {
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

        const distKm = haversineKmWrapped(y, x, s.lat, s.lon);
        if (!Number.isFinite(distKm)) continue;
        if (distKm <= nearStationKm) return s.value;

        if (sectorBalance) {
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
                for (let i = 1; i < sector.length; i += 1) {
                    if (sector[i].distKm > sector[farIdx].distKm) farIdx = i;
                }
                if (distKm < sector[farIdx].distKm) {
                    sector[farIdx] = { distKm, value: s.value };
                }
            }
        } else if (nearest.length < maxNeighbors) {
            nearest.push({ distKm, value: s.value });
        } else {
            let farIdx = 0;
            let farDist = nearest[0].distKm;
            for (let i = 1; i < nearest.length; i += 1) {
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
    for (let i = 1; i < finalNearest.length; i += 1) {
        if (finalNearest[i].distKm < best.distKm) best = finalNearest[i];
    }
    return best.value;
}

function interpolateHexColor(hex1, hex2, frac) {
    const h1 = hex1.replace('#', '');
    const h2 = hex2.replace('#', '');
    const channel = (hex, index) => parseInt(hex.substr(index, 2), 16);
    const mix = (a, b) => Math.round(a + (b - a) * frac);
    const r = mix(channel(h1, 0), channel(h2, 0));
    const g = mix(channel(h1, 2), channel(h2, 2));
    const b = mix(channel(h1, 4), channel(h2, 4));
    return `#${r.toString(16).padStart(2, '0')}${g.toString(16).padStart(2, '0')}${b.toString(16).padStart(2, '0')}`;
}

export function colorAtValue(value, product) {
    const anchors = SURFACE_COLORMAPS[product] || SURFACE_COLORMAPS.temperature;
    if (!anchors.length) return '#cccccc';

    const min = anchors[0][0];
    const max = anchors[anchors.length - 1][0];
    const clampedVal = Math.max(min, Math.min(max, value));

    for (let i = 0; i < anchors.length - 1; i += 1) {
        const [v0, c0] = anchors[i];
        const [v1, c1] = anchors[i + 1];
        if (clampedVal >= v0 && clampedVal <= v1) {
            if (v1 === v0) return c0;
            return interpolateHexColor(c0, c1, (clampedVal - v0) / (v1 - v0));
        }
    }
    return anchors[anchors.length - 1][1];
}

function drawIsothermFromGrid(ctx, grid, cols, rows, cellWidth, cellHeight, threshold) {
    const lerpPoint = (a, b, va, vb) => {
        if (va === vb) return [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
        const t = (threshold - va) / (vb - va);
        return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
    };

    ctx.save();
    ctx.strokeStyle = 'rgba(0, 22, 122, 0.9)';
    ctx.lineWidth = 0.75;
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';
    ctx.beginPath();

    for (let row = 0; row < rows - 1; row += 1) {
        for (let col = 0; col < cols - 1; col += 1) {
            const v00 = grid[row][col];
            const v10 = grid[row][col + 1];
            const v01 = grid[row + 1][col];
            const v11 = grid[row + 1][col + 1];
            if (![v00, v10, v01, v11].every((v) => Number.isFinite(v))) continue;

            const x0 = col * cellWidth;
            const y0 = row * cellHeight;
            const x1 = (col + 1) * cellWidth;
            const y1 = (row + 1) * cellHeight;
            const points = [];
            const crosses = (a, b) => (a - threshold) * (b - threshold) <= 0 && a !== b;

            if (crosses(v00, v10)) points.push(lerpPoint([x0, y0], [x1, y0], v00, v10));
            if (crosses(v10, v11)) points.push(lerpPoint([x1, y0], [x1, y1], v10, v11));
            if (crosses(v01, v11)) points.push(lerpPoint([x0, y1], [x1, y1], v01, v11));
            if (crosses(v00, v01)) points.push(lerpPoint([x0, y0], [x0, y1], v00, v01));

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

export function gradientImageUrl(meta) {
    const imageUrl = meta?.image_url;
    if (!imageUrl) return '';
    const version = meta.timestamp || meta.generated_at || meta.updated_at || '';
    if (!version) return apiUrl(imageUrl);
    const separator = String(imageUrl).includes('?') ? '&' : '?';
    return apiUrl(`${imageUrl}${separator}v=${encodeURIComponent(version)}`);
}

export function createSurfaceRenderer(mapCore) {
    const { leaflet, map } = mapCore;
    let layer = null;

    function coloredTextIcon(value, unit, opacity) {
        const label = unit === '°F' || unit === '%' || unit === 'kt'
            ? String(Math.round(value))
            : value.toFixed(1);
        const alpha = Math.max(0, Math.min(1, opacity));

        // Value markers grow as zoom increases (reverse-responsive behavior).
        const zoom = map.getZoom() ?? 5;
        const t = Math.max(0, Math.min(1, (zoom - 5) / 4));
        const fontSizePx = Math.round(16 + t * 22); // 16px @ z5 -> 38px @ z9+
        const strokePx = Math.max(1, Math.round(fontSizePx * 0.1));
        const iconWidth = Math.max(32, Math.round(fontSizePx * (label.length * 0.62 + 0.8)));
        const iconHeight = Math.max(20, Math.round(fontSizePx * 1.25));

        return leaflet.divIcon({
            className: '',
            // Opacity at the element level so text fill and outline fade together.
            html: `<div style="opacity:${alpha};color:rgb(255,255,0);font-weight:800;font-size:${fontSizePx}px;line-height:1;font-family:'Montserrat',sans-serif;text-align:center;-webkit-text-stroke:${strokePx}px black;paint-order:stroke fill;">${label}</div>`,
            iconSize: [iconWidth, iconHeight],
            iconAnchor: [
                Math.round(iconWidth / 2 - VALUE_MARKER_OFFSET_X_PX),
                Math.round(iconHeight / 2 - VALUE_MARKER_OFFSET_Y_PX),
            ],
        });
    }

    function thinStations(stations, view) {
        const minDistKm = baseDistKm(map.getZoom(), view.region) / view.density;
        return filterByMinDistKm(stations, minDistKm);
    }

    // Gradient interpolation thins independently of the marker density slider
    // so the interpolated field stays stable when marker density changes.
    function thinGradientStations(stations, view) {
        const zoom = map.getZoom();
        const region = String(view.region || '').toUpperCase();
        const baseKm = baseDistKm(zoom, region);
        const factor = region === 'WORLD'
            ? (zoom <= 3 ? 0.42 : zoom <= 5 ? 0.40 : 0.38)
            : (zoom <= 5 ? 0.36 : 0.28);
        const floorKm = region === 'WORLD' ? (zoom <= 3 ? 16 : 14) : 8;
        return filterByMinDistKm(stations, Math.max(floorKm, baseKm * factor));
    }

    function interpolateGridValues(stations, view) {
        if (!stations.length) return null;

        const zoom = map.getZoom();
        const region = String(view.region || '').toUpperCase();
        const bounds = map.getBounds();
        const sw = bounds.getSouthWest();
        const ne = bounds.getNorthEast();
        const canvasSize = map.getSize();
        const gridResolution = gradientGridResolution(zoom, region);
        const cols = Math.ceil(canvasSize.x / gridResolution);
        const rows = Math.ceil(canvasSize.y / gridResolution);
        const lonRange = ne.lng - sw.lng;

        // Sample latitudes in Mercator Y space so canvas pixels align with
        // Leaflet's Web Mercator projection; linear latitude stepping shifts
        // northward at high latitudes.
        const neMercY = latToMercY(Math.min(ne.lat, 85));
        const swMercY = latToMercY(Math.max(sw.lat, -85));
        const mercYRange = neMercY - swMercY;

        const cfg = gradientNeighborConfig(zoom, region);
        cfg._maxLatDeltaDeg = cfg.maxInfluenceKm / 111;
        cfg._prefilterKm = cfg.maxInfluenceKm * (cfg.prefilterMultiplier || 1.35);

        const grid = [];
        for (let row = 0; row < rows; row += 1) {
            const gridRow = [];
            const mercY = neMercY - (row / rows) * mercYRange;
            const lat = mercYToLat(mercY);
            for (let col = 0; col < cols; col += 1) {
                const lon = sw.lng + (col / cols) * lonRange;
                const val = idwInterpolate(lon, lat, stations, cfg);
                gridRow.push(Number.isNaN(val) ? null : val);
            }
            grid.push(gridRow);
        }

        return { grid, bounds, cols, rows };
    }

    // Client-canvas gradient fallback used when no worker PNG is cached.
    function renderGradientCanvas(stations, view) {
        const thin = thinGradientStations(stations, view);
        if (!thin.length) return null;

        const gridData = interpolateGridValues(thin, view);
        if (!gridData) return null;
        const { grid, bounds, cols, rows } = gridData;

        const canvas = document.createElement('canvas');
        const canvasSize = map.getSize();
        canvas.width = canvasSize.x;
        canvas.height = canvasSize.y;
        const ctx = canvas.getContext('2d');
        const cellWidth = canvas.width / cols;
        const cellHeight = canvas.height / rows;

        // Render cells offscreen, then composite through a Gaussian blur to
        // dissolve hard cell-boundary seams.
        const offscreen = document.createElement('canvas');
        offscreen.width = canvas.width;
        offscreen.height = canvas.height;
        const offCtx = offscreen.getContext('2d');

        for (let row = 0; row < rows; row += 1) {
            for (let col = 0; col < cols; col += 1) {
                const val = grid[row][col];
                if (val !== null && !Number.isNaN(val)) {
                    offCtx.fillStyle = colorAtValue(val, view.product);
                    offCtx.fillRect(col * cellWidth, row * cellHeight, Math.ceil(cellWidth), Math.ceil(cellHeight));
                }
            }
        }

        const blurPx = Math.round(Math.max(cellWidth, cellHeight) * 1.2 * FALLBACK_BLUR_SCALE);
        ctx.filter = blurPx > 0 ? `blur(${blurPx}px)` : 'none';
        ctx.globalAlpha = Math.max(0, Math.min(1, view.gradientOpacity));
        ctx.drawImage(offscreen, 0, 0);
        ctx.filter = 'none';
        ctx.globalAlpha = 1.0;

        if (FREEZING_ISOTHERM_ENABLED && FREEZING_ISOTHERM_PRODUCTS.has(view.product)) {
            drawIsothermFromGrid(ctx, grid, cols, rows, cellWidth, cellHeight, 32);
        }

        return leaflet.imageOverlay(canvas.toDataURL(), bounds, {
            opacity: 1.0,
            className: 'surface-gradient-overlay',
        });
    }

    function stationPopupHtml(s) {
        const wdir = s.wind_dir != null ? `${Math.round(s.wind_dir)}°` : '—';
        const wspd = s.wind_speed != null ? `${Math.round(s.wind_speed)} kt` : '—';
        const gust = s.wind_gust != null ? ` G${Math.round(s.wind_gust)}` : '';
        const vis = s.visibility != null ? `${s.visibility} mi` : '—';
        const stationName = String(s.name || '').trim() || s.id;
        const stationId = String(s.id || '').trim().toUpperCase();
        const timeseriesSite = stationId.length === 3 ? `K${stationId}` : stationId;
        const timeseriesUrl = `https://www.weather.gov/wrh/timeseries?site=${encodeURIComponent(timeseriesSite)}`;
        return (
            `<strong>${escapeHtml(stationName)}</strong><br>`
            + `Temp: ${s.temperature != null ? `${s.temperature}°F` : '—'}<br>`
            + `Feels Like: ${s.feels_like != null ? `${s.feels_like}°F` : '—'}<br>`
            + `Dew Point: ${s.dew_point != null ? `${s.dew_point}°F` : '—'}<br>`
            + `RH: ${s.rh != null ? `${s.rh}%` : '—'}<br>`
            + `Wind: ${wdir} @ ${wspd}${gust}<br>`
            + `Visibility: ${vis}<br>`
            + `<a href="${timeseriesUrl}" target="_blank" rel="noopener" style="color:#7dd3fc;text-decoration:none;">View Time Series</a>`
        );
    }

    // stations: network-filtered marker stations.
    // view: { product, region, density, valueOpacity, gradientEnabled,
    //         gradientOpacity, gradientMeta, gradientStations }
    function render(stations, view) {
        clear();
        if (!stations.length || !view.product) return;

        const layers = [];

        if (view.gradientEnabled) {
            const meta = view.gradientMeta;
            let gradientLayer = null;
            if (meta?.image_url && Array.isArray(meta.bounds) && meta.bounds.length === 4) {
                const b = meta.bounds;
                gradientLayer = leaflet.imageOverlay(gradientImageUrl(meta), [[b[2], b[0]], [b[3], b[1]]], {
                    opacity: view.gradientOpacity,
                    className: 'surface-gradient-overlay',
                });
            } else {
                const source = view.gradientStations?.length ? view.gradientStations : stations;
                gradientLayer = renderGradientCanvas(source, view);
            }
            if (gradientLayer) layers.push(gradientLayer);
        }

        const thin = thinStations(stations, view);
        layers.push(leaflet.layerGroup(thin.map((s) => {
            const marker = leaflet.marker([s.lat, s.lon], {
                icon: coloredTextIcon(s.value, s.unit, view.valueOpacity),
            });
            marker.bindPopup(stationPopupHtml(s));
            return marker;
        })));

        layer = leaflet.layerGroup(layers).addTo(map);
    }

    function clear() {
        if (layer && map.hasLayer(layer)) map.removeLayer(layer);
        layer = null;
    }

    return Object.freeze({ clear, render });
}
