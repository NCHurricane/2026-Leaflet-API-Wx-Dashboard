import assert from 'node:assert/strict';
import test from 'node:test';

globalThis.window = {
    location: { protocol: 'http:', hostname: '127.0.0.1', port: '8000' },
};

const { createSurfaceEngine } = await import('../frontend/pages/surface/surface-engine.js');

function deferred() {
    let resolve;
    const promise = new Promise((done) => { resolve = done; });
    return { promise, resolve };
}

function view(overrides = {}) {
    return {
        region: 'NC',
        product: 'temperature',
        gradientEnabled: false,
        networks: new Set(['ASOS']),
        density: 0.5,
        valueOpacity: 0.9,
        gradientOpacity: 0.45,
        ...overrides,
    };
}

function station(id, network = 'ASOS') {
    return { id, network, lat: 35, lon: -80, temperature: 70 };
}

function createHarness(fetchJson) {
    const renderCalls = [];
    const renderer = {
        clearCount: 0,
        render(stations, options) {
            renderCalls.push({ stations: [...stations], options: { ...options } });
        },
        clear() { renderer.clearCount += 1; },
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
    const stationCounts = [];
    const engine = createSurfaceEngine({
        api: { fetchJson },
        renderer,
        legend,
        status,
        onStationCount: (count) => stationCounts.push(count),
    });
    return { engine, legend, renderer, renderCalls, stationCounts, status };
}

test('Surface live load filters selected networks and updates product legend and status', async () => {
    const requests = [];
    const timestamp = new Date().toISOString();
    const harness = createHarness(async (path, options) => {
        requests.push({ path, options });
        return {
            cache_state: 'fresh',
            timestamp,
            timestamp_source: 'station_valid',
            stations: [station('airport'), station('coop', 'COOP')],
        };
    });

    await harness.engine.load(view());

    assert.equal(requests.length, 1);
    assert.equal(requests[0].path, '/api/data/surface?region=NC&product=temperature');
    assert.equal(requests[0].options.signal.aborted, false);
    assert.deepEqual(harness.renderCalls.at(-1).stations.map((item) => item.id), ['airport']);
    assert.equal(harness.renderCalls.at(-1).options.product, 'temperature');
    assert.equal(harness.renderCalls.at(-1).options.gradientEnabled, false);
    assert.match(harness.legend.html, /Surface: Temperature/);
    assert.match(harness.legend.html, /2 stations/);
    assert.deepEqual(harness.stationCounts, [2]);
    assert.deepEqual(harness.status.dataInfo, {
        timestamp,
        provider: 'IEM',
        stale: false,
    });
    assert.match(harness.status.messages.at(-1).message, /2 stations/);
    assert.equal(harness.engine.hasStations, true);
});

test('Surface gradient uses the retained source region and ASOS-only interpolation stations', async () => {
    const requests = [];
    const harness = createHarness(async (path) => {
        requests.push(path);
        if (path.startsWith('/api/data/surface-gradient')) {
            return {
                image_url: '/cache/surface-gradient.png',
                bounds: [-90, -70, 30, 40],
                refreshing: false,
            };
        }
        return {
            cache_state: 'fresh',
            timestamp: new Date().toISOString(),
            stations: [station('airport'), station('coop', 'COOP')],
        };
    });

    await harness.engine.load(view({ gradientEnabled: true }));

    assert.deepEqual(requests, [
        '/api/data/surface?region=NC&product=temperature',
        '/api/data/surface-gradient?region=CONUS&product=temperature',
    ]);
    const rendered = harness.renderCalls.at(-1);
    assert.equal(rendered.options.gradientPending, false);
    assert.equal(rendered.options.gradientMeta.image_url, '/cache/surface-gradient.png');
    assert.deepEqual(rendered.options.gradientStations.map((item) => item.id), ['airport']);
});

test('Surface archive frame cancels an unresolved live load and remains authoritative', async () => {
    const live = deferred();
    let liveSignal = null;
    const harness = createHarness(async (_path, options) => {
        liveSignal = options.signal;
        return live.promise;
    });
    const pending = harness.engine.load(view());

    const archiveStation = station('archive');
    harness.engine.renderArchiveFrame(
        { timestamp: '2026-08-05T12:00:00Z', stations: [archiveStation] },
        view({ gradientEnabled: true }),
    );

    assert.equal(liveSignal.aborted, true);
    assert.equal(harness.renderCalls.length, 1);
    assert.deepEqual(harness.renderCalls[0].stations, [archiveStation]);
    assert.equal(harness.renderCalls[0].options.gradientEnabled, false);
    assert.match(harness.status.messages.at(-1).message, /Surface archive: 1 stations/);

    live.resolve({
        cache_state: 'fresh',
        timestamp: new Date().toISOString(),
        stations: [station('late-live')],
    });
    await pending;

    assert.equal(harness.renderCalls.length, 1, 'the stale live response cannot replace the archive frame');
    assert.equal(harness.engine.rerender({ density: 0.8 }), true);
    assert.deepEqual(harness.renderCalls.at(-1).stations, [archiveStation]);
});
