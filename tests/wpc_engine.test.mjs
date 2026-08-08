import assert from 'node:assert/strict';
import test from 'node:test';

globalThis.window = {
    location: { protocol: 'http:', hostname: '127.0.0.1', port: '8000' },
    setTimeout,
};

const { createWpcEngine } = await import('../frontend/pages/wpc/wpc-engine.js');

function deferred() {
    let resolve;
    const promise = new Promise((done) => { resolve = done; });
    return { promise, resolve };
}

function vectorPayload(overrides = {}) {
    return {
        type: 'FeatureCollection',
        product_label: 'Day 1 Excessive Rainfall Outlook',
        _updated: '2026-08-07T12:00:00Z',
        features: [{
            type: 'Feature',
            id: 'risk-1',
            properties: { category: 'MRGL', label: 'Marginal Risk', color: '#00ff00' },
            geometry: null,
        }],
        ...overrides,
    };
}

function createHarness(fetchJson) {
    const layers = new Set();
    const vectors = [];
    const images = [];
    const map = {
        hasLayer: (layer) => layers.has(layer),
        removeLayer: (layer) => layers.delete(layer),
    };
    const leaflet = {
        geoJSON(geojson, options) {
            const children = (geojson.features || []).map((feature) => {
                const handlers = new Map();
                const child = {
                    feature,
                    handlers,
                    styles: [options.style(feature)],
                    bindTooltip() { return child; },
                    on(event, handler) { handlers.set(event, handler); return child; },
                    setStyle(style) { child.styles.push(style); },
                };
                options.onEachFeature(feature, child);
                return child;
            });
            const layer = {
                children,
                options,
                addTo() { layers.add(layer); return layer; },
                eachLayer(callback) { children.forEach(callback); },
            };
            vectors.push(layer);
            return layer;
        },
        imageOverlay(url, bounds, options) {
            const layer = {
                url,
                bounds,
                options,
                opacity: options.opacity,
                addTo() { layers.add(layer); return layer; },
                setOpacity(value) { layer.opacity = value; },
            };
            images.push(layer);
            return layer;
        },
    };
    const legend = {
        html: '',
        clearCount: 0,
        setHtml(html) { legend.html = html; },
        clear() { legend.html = ''; legend.clearCount += 1; },
    };
    const status = {
        messages: [],
        dataInfo: null,
        dataStates: [],
        setMessage(message, state) { status.messages.push({ message, state }); },
        setDataInfo(info) { status.dataInfo = info; },
        setDataState(message, state) { status.dataStates.push({ message, state }); },
    };
    const emptyMessages = [];
    const details = [];
    const engine = createWpcEngine({
        api: { apiUrl: (path) => path, fetchJson },
        mapCore: { map, leaflet },
        legend,
        status,
        onEmptyMessage: (message) => emptyMessages.push(message),
        onDetail: (...args) => details.push(args),
        paneName: 'test-wpc-pane',
    });
    return { details, emptyMessages, engine, images, layers, legend, status, vectors };
}

test('WPC vector load owns its layer, legend, opacity, and forecast detail callback', async () => {
    const requests = [];
    const harness = createHarness(async (path, options) => {
        requests.push({ path, options });
        return vectorPayload();
    });

    await harness.engine.load({ group: 'ero', day: 1, product: '' });

    assert.equal(requests[0].path, '/api/data/wpc?group=ero&day=1');
    assert.equal(requests[0].options.signal.aborted, false);
    assert.equal(harness.layers.size, 1);
    assert.equal(harness.vectors[0].options.pane, 'test-wpc-pane');
    assert.match(harness.legend.html, /Day 1 Excessive Rainfall Outlook/);
    assert.match(harness.legend.html, /Marginal \(≥5%\)/);
    assert.deepEqual(harness.status.dataInfo, {
        timestamp: '2026-08-07T12:00:00.000Z',
        provider: 'NOAA/WPC',
        source: 'WPC cache updated',
    });
    assert.deepEqual(harness.status.dataStates.at(-1), { message: 'Fresh data', state: 'fresh' });

    harness.engine.setOpacity(0.7);
    assert.equal(harness.vectors[0].children[0].styles.at(-1).fillOpacity, 0.7);

    harness.vectors[0].children[0].handlers.get('click')({ latlng: { lat: 35, lng: -80 } });
    assert.equal(harness.details.length, 1);
    assert.equal(harness.details[0][1].properties.wpc_forecast, true);
    assert.equal(harness.details[0][1].properties.wpc_group, 'ero');
});

test('WPC keeps the current layer until a raster replacement is ready', async () => {
    const raster = deferred();
    let requestCount = 0;
    const harness = createHarness(async () => {
        requestCount += 1;
        return requestCount === 1 ? vectorPayload() : raster.promise;
    });
    await harness.engine.load({ group: 'ero', day: 1, product: '' });
    const vectorLayer = harness.vectors[0];

    const pending = harness.engine.load({ group: 'surface', day: 1, product: 'fronts' });
    assert.equal(harness.layers.has(vectorLayer), true);

    raster.resolve({
        product_label: 'WPC Surface Analysis',
        image_url: '/cache/wpc-surface.png',
        bounds: { west: -130, east: -60, south: 20, north: 55 },
        _updated: '2026-08-07T13:00:00Z',
    });
    await pending;

    assert.equal(harness.layers.has(vectorLayer), false);
    assert.equal(harness.layers.has(harness.images[0]), true);
    assert.equal(harness.images[0].url, '/cache/wpc-surface.png?v=2026-08-07T13%3A00%3A00Z');
    assert.deepEqual(harness.images[0].bounds, [[20, -130], [55, -60]]);
    assert.equal(harness.images[0].options.pane, 'test-wpc-pane');
    assert.equal(harness.legend.html, '');

    harness.engine.setOpacity(0.8);
    assert.equal(harness.images[0].opacity, 0.8);
});

test('WPC legitimate-empty state clears the layer and stale responses cannot reclaim it', async () => {
    const stale = deferred();
    let requestCount = 0;
    let staleSignal = null;
    const harness = createHarness(async (_path, options) => {
        requestCount += 1;
        if (requestCount === 1) return vectorPayload();
        if (requestCount === 2) {
            staleSignal = options.signal;
            return stale.promise;
        }
        return vectorPayload({
            product_label: 'Day 2 Significant Weather',
            issued_text: 'Issued 1200 UTC',
            valid_text: 'Valid Day 2',
            empty_message: 'No significant weather is forecast.',
            features: [],
        });
    });
    await harness.engine.load({ group: 'ero', day: 1, product: '' });
    const staleLoad = harness.engine.load({ group: 'ero', day: 2, product: '' });
    await harness.engine.load({ group: 'sigwx', day: 2, product: '' });

    assert.equal(staleSignal.aborted, true);
    assert.equal(harness.layers.size, 0);
    assert.match(harness.legend.html, /Day 2 Significant Weather/);
    assert.match(harness.emptyMessages.at(-1), /No significant weather is forecast/);
    assert.match(harness.emptyMessages.at(-1), /Issued 1200 UTC • Valid Day 2/);

    stale.resolve(vectorPayload({ product_label: 'Late stale response' }));
    await staleLoad;

    assert.equal(harness.layers.size, 0);
    assert.doesNotMatch(harness.legend.html, /Late stale response/);
});
