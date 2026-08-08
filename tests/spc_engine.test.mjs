import assert from 'node:assert/strict';
import test from 'node:test';

globalThis.window = {
    location: { protocol: 'http:', hostname: '127.0.0.1', port: '8000' },
    setTimeout,
};

const { createSpcEngine } = await import('../frontend/pages/spc/spc-engine.js');

function deferred() {
    let resolve;
    const promise = new Promise((done) => { resolve = done; });
    return { promise, resolve };
}

function supplemental(overrides = {}) {
    return {
        reportsEnabled: false,
        reportTypes: ['torn', 'wind', 'hail'],
        reportsDays: ['today'],
        mdsEnabled: false,
        watchesEnabled: false,
        watchLayers: [],
        ...overrides,
    };
}

function selection(overrides = {}) {
    return {
        day: 1,
        fireDay: 1,
        hazards: [],
        supplemental: supplemental(),
        ...overrides,
    };
}

function feature(id, properties = {}) {
    return { type: 'Feature', id, properties, geometry: null };
}

function createHarness(fetchJson) {
    const renderCalls = [];
    const renderer = {
        clearCount: 0,
        clear() { renderer.clearCount += 1; },
        render(payload) { renderCalls.push(payload); },
        featuresInView(features) {
            return (features || []).filter((item) => item.properties?.in_view !== false);
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
    const counts = [];
    const emptyMessages = [];
    const engine = createSpcEngine({
        api: { fetchJson },
        renderer,
        legend,
        status,
        onCount: (count) => counts.push(count),
        onEmptyMessage: (message) => emptyMessages.push(message),
    });
    return { counts, emptyMessages, engine, legend, renderer, renderCalls, status };
}

test('SPC supplemental load deduplicates watches and owns MD/watch legend and status', async () => {
    const requests = [];
    const tornadoWatch = feature('watch-101', {
        watch_type: 'Tornado Watch', watch_number: '101', in_view: true,
    });
    const severeWatch = feature('watch-202', {
        watch_type: 'Severe Thunderstorm Watch', watch_number: '202', in_view: false,
    });
    const harness = createHarness(async (path, options) => {
        requests.push({ path, options });
        if (path === '/api/data/spc/active?product=mds') {
            return {
                type: 'FeatureCollection',
                _updated: '2026-08-07T12:00:00Z',
                features: [feature('md-1', { product_type: 'Mesoscale Discussion' })],
            };
        }
        if (path.includes('watch_types=tornado')) {
            return {
                type: 'FeatureCollection',
                _updated: '2026-08-07T13:00:00Z',
                features: [tornadoWatch, { ...tornadoWatch }],
            };
        }
        return {
            type: 'FeatureCollection',
            _updated: '2026-08-07T14:00:00Z',
            features: [severeWatch],
        };
    });

    await harness.engine.load(selection({
        supplemental: supplemental({
            mdsEnabled: true,
            watchesEnabled: true,
            watchLayers: [
                { type: 'tornado', mode: 'counties' },
                { type: 'severe', mode: 'counties' },
            ],
        }),
    }));

    assert.deepEqual(requests.map(({ path }) => path), [
        '/api/data/spc/active?product=mds',
        '/api/data/spc/active?product=watches&watch_mode=counties&watch_types=tornado',
        '/api/data/spc/active?product=watches&watch_mode=counties&watch_types=severe',
    ]);
    assert.equal(requests.every(({ options }) => options.signal.aborted === false), true);
    assert.equal(harness.renderCalls.length, 1);
    assert.equal(harness.renderCalls[0].mds.features.length, 1);
    assert.deepEqual(harness.renderCalls[0].watches.features.map((item) => item.id), [
        'watch-101', 'watch-202',
    ]);
    assert.match(harness.legend.html, /Watches In View/);
    assert.match(harness.legend.html, /Tornado Watch \(1\)/);
    assert.doesNotMatch(harness.legend.html, /Severe Thunderstorm Watch/);
    assert.deepEqual(harness.counts, [3]);
    assert.equal(harness.emptyMessages.at(-1), null);
    assert.deepEqual(harness.status.dataInfo, {
        timestamp: '2026-08-07T14:00:00.000Z',
        provider: 'NOAA SPC',
        stale: false,
    });

    severeWatch.properties.in_view = true;
    harness.engine.refreshWatchesLegend();
    assert.match(harness.legend.html, /Severe Thunderstorm Watch \(1\)/);
});

test('SPC CIG overlays retain raw payloads while excluding placeholders and CIG from base counts', async () => {
    const requests = [];
    const harness = createHarness(async (path) => {
        requests.push(path);
        if (path.includes('hazard=cigtorn')) {
            return {
                type: 'FeatureCollection',
                _issued: '2026-08-07T13:00:00Z',
                features: [
                    feature('cig-placeholder', { DN: 0, LABEL: 'NO CIG' }),
                    feature('cig-1', { DN: 1, LABEL: 'CIG 1' }),
                ],
            };
        }
        return {
            type: 'FeatureCollection',
            _issued: '2026-08-07T12:00:00Z',
            features: [
                feature('prob-placeholder', { DN: 0, LABEL: 'LESS THAN 2%' }),
                feature('prob-5', { DN: 5, LABEL: '5%' }),
                feature('embedded-cig', { DN: 10, LABEL: 'CIG 1' }),
            ],
        };
    });

    await harness.engine.load(selection({ hazards: ['torn', 'cigtorn'] }));

    assert.deepEqual(requests, [
        '/api/data/spc?day=1&hazard=torn',
        '/api/data/spc?day=1&hazard=cigtorn',
    ]);
    assert.deepEqual(harness.renderCalls[0].outlooks.map(({ hazard }) => hazard), ['torn', 'cigtorn']);
    assert.deepEqual(harness.counts, [1]);
    assert.match(harness.legend.html, /Tornado Outlook/);
    assert.match(harness.legend.html, /Intensity/);
    assert.equal(harness.emptyMessages.at(-1), null);
    assert.equal(harness.status.dataInfo.timestamp, '2026-08-07T13:00:00.000Z');
});

test('SPC teardown aborts a supplemental request and prevents stale rendering', async () => {
    const pendingMds = deferred();
    let requestSignal = null;
    const harness = createHarness(async (_path, options) => {
        requestSignal = options.signal;
        return pendingMds.promise;
    });
    const pending = harness.engine.load(selection({
        supplemental: supplemental({ mdsEnabled: true }),
    }));

    harness.engine.destroy();
    assert.equal(requestSignal.aborted, true);

    pendingMds.resolve({
        type: 'FeatureCollection',
        features: [feature('late-md')],
    });
    await pending;

    assert.equal(harness.renderCalls.length, 0);
    assert.equal(harness.legend.html, '');
    assert.equal(harness.status.clearCount, 1);
    assert.equal(harness.counts.at(-1), 0);
    assert.equal(harness.emptyMessages.at(-1), null);
});
