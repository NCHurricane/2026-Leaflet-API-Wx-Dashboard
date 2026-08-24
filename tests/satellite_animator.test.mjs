import assert from 'node:assert/strict';
import test from 'node:test';

import { createSatelliteAnimator } from '../frontend/pages/satellite/satellite-anim.js';

globalThis.requestAnimationFrame = (callback) => callback();

function createHarness({ clientId = '' } = {}) {
    const layers = new Set();
    const createdLayers = [];
    const pane = { style: {} };
    const map = {
        getPane: () => pane,
        createPane: () => pane,
        getZoom: () => 5,
        hasLayer: (layer) => layers.has(layer),
        removeLayer: (layer) => layers.delete(layer),
        getBounds: () => ({
            getNorthWest: () => ({ corner: 'north-west' }),
            getSouthEast: () => ({ corner: 'south-east' }),
        }),
        getCenter: () => ({ corner: 'center' }),
        project(point) {
            if (point.corner === 'north-west') return { x: 256, y: 256 };
            if (point.corner === 'south-east') return { x: 512, y: 512 };
            return { x: 384, y: 384 };
        },
    };
    const leaflet = {
        tileLayer(url, options) {
            const handlers = new Map();
            const layer = {
                url,
                options,
                opacity: options.opacity,
                zIndex: null,
                _container: { style: {} },
                _loading: false,
                _tiles: {},
                on(event, handler) {
                    if (!handlers.has(event)) handlers.set(event, new Set());
                    handlers.get(event).add(handler);
                    return layer;
                },
                off(event, handler) {
                    handlers.get(event)?.delete(handler);
                    return layer;
                },
                fire(event) {
                    [...(handlers.get(event) || [])].forEach((handler) => handler());
                },
                addTo() { layers.add(layer); return layer; },
                setOpacity(value) { layer.opacity = value; return layer; },
                setZIndex(value) { layer.zIndex = value; return layer; },
                setUrl(value) { layer.url = value; return layer; },
                redraw() { return layer; },
            };
            createdLayers.push(layer);
            return layer;
        },
    };
    const selection = { satId: 'goes16', sector: 'CONUS', channel: 'Channel13' };
    const visibleFrames = [];
    const animator = createSatelliteAnimator({
        mapCore: { map, leaflet },
        apiUrl: (path) => path,
        clientId,
        getSelection: () => ({ ...selection }),
        getCatalog: () => ({ render_version: 'test-v1', max_native_zoom: 5 }),
        onFrameVisible: (frameKey) => visibleFrames.push(frameKey),
    });
    return { animator, createdLayers, layers, selection, visibleFrames };
}

function markVisible(layer, tileId = 'tile') {
    layer._tiles[tileId] = {
        coords: { z: 5 },
        current: true,
        loaded: true,
        el: { complete: true, naturalWidth: 256, style: {} },
    };
    layer.fire('tileload');
}

test('Satellite animator lets a newer frame defeat an older pending tile wait', async () => {
    const harness = createHarness();
    harness.animator.setFrames([
        { frame_key: 'frame-a', max_native_zoom: 5 },
        { frame_key: 'frame-b', max_native_zoom: 5 },
    ]);

    const first = harness.animator.showFrame(0, { waitForVisibleTile: true, tileTimeoutMs: 1000 });
    assert.equal(harness.createdLayers.length, 1);
    const firstLayer = harness.createdLayers[0];

    assert.equal(await harness.animator.showFrame(1), true);
    const secondLayer = harness.createdLayers[1];
    assert.equal(harness.layers.has(firstLayer), false);
    assert.equal(harness.layers.has(secondLayer), true);

    markVisible(secondLayer, 'second');
    markVisible(firstLayer, 'first');

    assert.equal(await first, false);
    assert.equal(harness.animator.getFrameIndex(), 1);
    assert.deepEqual(harness.visibleFrames, ['frame-b']);
    assert.equal(harness.layers.has(firstLayer), false);
    assert.equal(harness.layers.has(secondLayer), true);

    harness.animator.setOpacity(0.65);
    assert.equal(secondLayer.opacity, 0.65);
    harness.animator.destroy();
    assert.equal(harness.layers.size, 0);
});

test('Satellite tile requests carry their page ownership id', async () => {
    const harness = createHarness({ clientId: 'page-owner' });
    harness.animator.setFrames([{ frame_key: 'frame-a', max_native_zoom: 5 }]);

    assert.equal(await harness.animator.showFrame(0), true);
    assert.match(harness.createdLayers[0].url, /client_id=page-owner/);
    assert.match(harness.createdLayers[0].url, /frame_generation=1/);
    assert.match(harness.createdLayers[0].url, /foreground_frame_key=frame-a/);

    harness.animator.destroy();
});

test('Satellite advances foreground ownership when a newer cold frame is selected', async () => {
    const harness = createHarness({ clientId: 'page-owner' });
    harness.animator.setFrames([
        { frame_key: 'frame-a', max_native_zoom: 5 },
        { frame_key: 'frame-b', max_native_zoom: 5 },
    ]);

    assert.equal(await harness.animator.showFrame(0), true);
    markVisible(harness.createdLayers[0], 'ready-first');
    const pending = harness.animator.showFrame(1, { tileTimeoutMs: 1000 });
    const secondLayer = harness.createdLayers[1];

    assert.match(secondLayer.url, /frame_generation=2/);
    assert.match(secondLayer.url, /foreground_frame_key=frame-b/);
    markVisible(secondLayer, 'ready-second');
    secondLayer.fire('load');
    assert.equal(await pending, true);
    harness.animator.destroy();
});

test('Satellite keeps the prior frame visible until the replacement is fully ready', async () => {
    const harness = createHarness();
    harness.animator.setFrames([
        { frame_key: 'frame-a', max_native_zoom: 5 },
        { frame_key: 'frame-b', max_native_zoom: 5 },
    ]);

    assert.equal(await harness.animator.showFrame(0), true);
    const firstLayer = harness.createdLayers[0];
    markVisible(firstLayer, 'ready-first');
    const pendingSwap = harness.animator.showFrame(1, { tileTimeoutMs: 1000 });
    const secondLayer = harness.createdLayers[1];

    let settled = false;
    void pendingSwap.then(() => { settled = true; });
    secondLayer._loading = true;
    markVisible(secondLayer, 'partial-second');
    await new Promise((resolve) => setImmediate(resolve));

    assert.equal(settled, false);
    assert.equal(harness.layers.has(firstLayer), true);
    assert.equal(firstLayer.opacity, 1);
    assert.equal(secondLayer.opacity, 0);

    secondLayer._loading = false;
    secondLayer.fire('load');

    assert.equal(await pendingSwap, true);
    assert.equal(harness.layers.has(firstLayer), true);
    assert.equal(harness.layers.has(secondLayer), true);
    assert.equal(firstLayer.opacity, 0);
    assert.equal(secondLayer.opacity, 1);

    assert.equal(await harness.animator.showFrame(0), true);
    assert.equal(harness.layers.has(firstLayer), true);
    assert.equal(harness.layers.has(secondLayer), true);
    assert.equal(firstLayer.opacity, 1);
    assert.equal(secondLayer.opacity, 0);
    harness.animator.destroy();
});

test('Satellite teardown aborts active neighbor prefetch and removes its pooled layer', async () => {
    const originalFetch = globalThis.fetch;
    const requests = [];
    globalThis.fetch = (url, options) => new Promise((_resolve, reject) => {
        const request = { url, signal: options.signal, aborted: false };
        requests.push(request);
        options.signal.addEventListener('abort', () => {
            request.aborted = true;
            const error = new Error('aborted');
            error.name = 'AbortError';
            reject(error);
        }, { once: true });
    });

    try {
        const harness = createHarness({ clientId: 'page-owner' });
        harness.animator.setFrames([
            { frame_key: 'frame-a', max_native_zoom: 5 },
            { frame_key: 'frame-b', max_native_zoom: 5 },
            { frame_key: 'frame-c', max_native_zoom: 5 },
        ]);
        assert.equal(await harness.animator.showFrame(0), true);
        markVisible(harness.createdLayers[0]);
        harness.animator.schedulePrefetch(0);
        await new Promise((resolve) => setTimeout(resolve, 10));

        assert.equal(requests.length, 2);
        assert.equal(requests.every(({ url }) => url.includes('render_neighbors=0')), true);
        assert.equal(requests.every(({ url }) => url.includes('frame_key=frame-b')), true);
        assert.equal(requests.every(({ url }) => url.includes('frame_generation=1')), true);
        assert.equal(requests.every(({ url }) => url.includes('foreground_frame_key=frame-a')), true);
        assert.equal(new Set(requests.map(({ url }) => url)).size, 2);
        assert.equal(requests.every(({ signal }) => signal.aborted === false), true);

        harness.animator.destroy();
        await new Promise((resolve) => setImmediate(resolve));

        assert.equal(requests.every(({ aborted }) => aborted), true);
        assert.equal(harness.layers.size, 0);
    } finally {
        globalThis.fetch = originalFetch;
    }
});
