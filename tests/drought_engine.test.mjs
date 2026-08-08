import assert from 'node:assert/strict';
import test from 'node:test';

globalThis.window = {
    location: { protocol: 'http:', hostname: '127.0.0.1', port: '8000' },
};

const { createDroughtEngine } = await import('../frontend/pages/drought/drought-engine.js');

function deferred() {
    let resolve;
    const promise = new Promise((done) => { resolve = done; });
    return { promise, resolve };
}

function createHarness(fetchJson) {
    const layers = new Set();
    const map = {
        hasLayer: (layer) => layers.has(layer),
        removeLayer: (layer) => layers.delete(layer),
    };
    const createdLayers = [];
    const leaflet = {
        geoJSON(geojson, options) {
            const featureLayers = (geojson.features || []).map((feature) => {
                const featureLayer = {
                    feature,
                    styles: [],
                    bindTooltip() { return featureLayer; },
                    setStyle(style) { featureLayer.styles.push(style); },
                };
                options.onEachFeature(feature, featureLayer);
                return featureLayer;
            });
            const layer = {
                featureLayers,
                addTo() { layers.add(layer); return layer; },
                eachLayer(callback) { featureLayers.forEach(callback); },
            };
            createdLayers.push(layer);
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
        clearCount: 0,
        setMessage(message, state) { status.messages.push({ message, state }); },
        setDataInfo(info) { status.dataInfo = info; },
        clear() { status.clearCount += 1; },
    };
    const engine = createDroughtEngine({
        api: { fetchJson },
        mapCore: { map, leaflet },
        legend,
        status,
    });
    return { createdLayers, engine, layers, legend, status };
}

test('Drought engine owns its layer, filters, visibility, and legend lifecycle', async () => {
    const requests = [];
    const geojson = {
        type: 'FeatureCollection',
        features: [
            { type: 'Feature', properties: { DM: 0 }, geometry: null },
            { type: 'Feature', properties: { DM: 2 }, geometry: null },
        ],
    };
    const harness = createHarness(async (path) => {
        requests.push(path);
        if (path.endsWith('/dates')) return { dates: ['2026-08-05'] };
        return geojson;
    });

    const result = await harness.engine.load({ categories: [2], opacity: 0.6 });

    assert.deepEqual(result, { date: '2026-08-05', stats: null });
    assert.deepEqual(requests, [
        '/api/data/drought/dates',
        '/api/data/drought?date=2026-08-05',
    ]);
    assert.equal(harness.layers.size, 1);
    assert.match(harness.legend.html, /U\.S\. Drought Monitor/);
    assert.match(harness.legend.html, /D0, Abnormally Dry, disabled/);
    assert.equal(harness.createdLayers[0].featureLayers[0].styles.at(-1).fillOpacity, 0);
    assert.equal(harness.createdLayers[0].featureLayers[1].styles.at(-1).fillOpacity, 0.6);

    harness.engine.setVisible(false);
    assert.equal(harness.layers.size, 0);
    harness.engine.setVisible(true);
    assert.equal(harness.layers.size, 1);

    harness.engine.clear();
    assert.equal(harness.layers.size, 0);
    assert.equal(harness.legend.html, '');
    assert.equal(harness.legend.clearCount, 1);
    assert.equal(harness.status.clearCount, 1);
});

test('Drought teardown during date discovery prevents a later data fetch or layer attachment', async () => {
    const dates = deferred();
    const requests = [];
    const harness = createHarness(async (path) => {
        requests.push(path);
        if (path.endsWith('/dates')) return dates.promise;
        return { type: 'FeatureCollection', features: [] };
    });

    const pending = harness.engine.load({ date: '2026-08-05' });
    harness.engine.destroy();
    dates.resolve({ dates: ['2026-08-05'] });

    assert.equal(await pending, null);
    assert.deepEqual(requests, ['/api/data/drought/dates']);
    assert.equal(harness.createdLayers.length, 0);
    assert.equal(harness.layers.size, 0);
    assert.equal(harness.legend.clearCount, 1);
    assert.equal(harness.status.clearCount, 1);
});
