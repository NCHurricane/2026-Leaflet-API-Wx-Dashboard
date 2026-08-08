import assert from 'node:assert/strict';
import test from 'node:test';

globalThis.window = {};
await import('../frontend/pages/tropical/tropical-engine.js');

const { createTropicalEngine } = window.NCHTropicalEngine;

function deferred() {
    let resolve;
    const promise = new Promise((done) => { resolve = done; });
    return { promise, resolve };
}

function response(payload, status = 200) {
    return {
        ok: status >= 200 && status < 300,
        status,
        json: async () => payload,
    };
}

function createHarness(fetchFn) {
    let sequence = 0;
    let archiveBase = null;
    const calls = {
        archiveAdvisories: [],
        archiveMetadata: [],
        archiveModes: [],
        archivePrepared: [],
        archiveStatus: [],
        archiveWarm: [],
        liveMetadata: [],
        liveRendered: [],
        liveResets: 0,
        liveStorms: [],
        status: [],
    };
    const context = {
        apiUrl: (path) => path,
        canApplyResponse: (value) => value === sequence,
        fetchFn,
        getArchiveStormBase: () => archiveBase,
        isCurrentRequest: (value) => value === sequence,
        liveStormLabel: (data) => `${data.stormId} live`,
        nextRequestSeq: () => ++sequence,
        prepareArchiveAdvisoryMode(items) { calls.archiveModes.push([...items]); },
        prepareArchiveBestTrackMode() { calls.archiveModes.push(['best-track']); },
        prepareArchiveStorm(data, atcfId) {
            archiveBase = data;
            calls.archivePrepared.push({ data, atcfId });
        },
        renderArchiveAdvisory(merged, advisory, options) {
            calls.archiveAdvisories.push({ merged, advisory, options });
        },
        renderInitialArchiveFix() {},
        renderLiveStormDetail(data, options) { calls.liveRendered.push({ data, options }); },
        resetLiveArchiveState() { calls.liveResets += 1; },
        setActiveStorm(data) { calls.liveStorms.push(data); },
        setArchiveStatus(message) { calls.archiveStatus.push(message); },
        setStatus(message) { calls.status.push(message); },
        startArchiveWarm(...args) { calls.archiveWarm.push(args); },
        updateArchiveAdvisoryMetadata(...args) { calls.archiveMetadata.push(args); },
        updateArchiveStormMetadata() {},
        updateLiveStormMetadata(data) { calls.liveMetadata.push(data); },
    };
    return { calls, context, engine: createTropicalEngine(context) };
}

test('Tropical live selection prevents a stale archive advisory from rendering or warming', async () => {
    const advisory = deferred();
    const requests = [];
    const harness = createHarness(async (url) => {
        requests.push(url);
        if (url.endsWith('/archive/storm/AL012026')) {
            return response({
                storm: { name: 'Archive Storm' },
                hasAdvisories: true,
                advisories: ['001'],
                gis_layers: {},
            });
        }
        if (url.includes('/archive/storm/AL012026/advisory/001')) return advisory.promise;
        if (url.endsWith('/storm/AL022026')) {
            return response({ stormId: 'AL022026', advisory: { headline: 'Live Storm' } });
        }
        throw new Error(`Unexpected request: ${url}`);
    });

    const archiveLoad = harness.engine.loadArchiveStormDetail('AL012026');
    while (!requests.some((url) => url.includes('/advisory/001'))) {
        await new Promise((resolve) => setImmediate(resolve));
    }
    await harness.engine.loadStormDetail('AL022026', { zoomToLatest: true });
    advisory.resolve(response({ advisoryStep: '001', gis_layers: {} }));
    await archiveLoad;

    assert.equal(harness.calls.liveRendered.length, 1);
    assert.equal(harness.calls.liveStorms[0].stormId, 'AL022026');
    assert.equal(harness.calls.liveResets, 1);
    assert.equal(harness.calls.archiveAdvisories.length, 0);
    assert.equal(harness.calls.archiveMetadata.length, 0);
    assert.equal(harness.calls.archiveWarm.length, 0);
});

test('Tropical archive storm merges best track into its first advisory before warming', async () => {
    const base = {
        storm: { name: 'Archive Storm' },
        hasAdvisories: true,
        advisories: ['005'],
        gis_layers: {
            best_track_line: { geojson: { type: 'FeatureCollection', features: [] } },
            best_track_points: { geojson: { type: 'FeatureCollection', features: [] } },
        },
    };
    const advisory = {
        advisoryStep: '005',
        gis_layers: { cone: { geojson: { type: 'FeatureCollection', features: [] } } },
    };
    const harness = createHarness(async (url) => (
        url.includes('/advisory/005') ? response(advisory) : response(base)
    ));

    await harness.engine.loadArchiveStormDetail('AL012026');

    assert.deepEqual(harness.calls.archiveModes, [['005']]);
    assert.equal(harness.calls.archiveAdvisories.length, 1);
    assert.equal(harness.calls.archiveAdvisories[0].merged.storm, base.storm);
    assert.equal(
        harness.calls.archiveAdvisories[0].merged.gis_layers.best_track_line,
        base.gis_layers.best_track_line,
    );
    assert.equal(
        harness.calls.archiveAdvisories[0].merged.gis_layers.best_track_points,
        base.gis_layers.best_track_points,
    );
    assert.deepEqual(harness.calls.archiveAdvisories[0].options, { fit: true, initial: true });
    assert.deepEqual(harness.calls.archiveMetadata[0], [advisory, '005', 'AL012026']);
    assert.deepEqual(harness.calls.archiveWarm, [['window', '005']]);
});

test('Tropical archive advisory prevents a stale live detail from reclaiming state', async () => {
    const live = deferred();
    const archiveBase = {
        storm: { name: 'Archive Storm' },
        hasAdvisories: false,
        gis_layers: {},
    };
    const harness = createHarness(async (url) => {
        if (url.endsWith('/storm/AL022026')) return live.promise;
        if (url.endsWith('/archive/storm/AL012026')) return response(archiveBase);
        if (url.includes('/archive/storm/AL012026/advisory/010')) {
            return response({ advisoryStep: '010', gis_layers: {} });
        }
        throw new Error(`Unexpected request: ${url}`);
    });
    await harness.engine.loadArchiveStormDetail('AL012026');
    const liveLoad = harness.engine.loadStormDetail('AL022026');
    const archiveApplied = await harness.engine.loadArchiveAdvisory('AL012026', '010');

    live.resolve(response({ stormId: 'AL022026', advisory: { headline: 'Late Live Storm' } }));
    await liveLoad;

    assert.equal(archiveApplied, true);
    assert.equal(harness.calls.archiveAdvisories.length, 1);
    assert.equal(harness.calls.liveRendered.length, 0);
    assert.equal(harness.calls.liveStorms.length, 0);
    assert.equal(harness.calls.liveResets, 0);
});
