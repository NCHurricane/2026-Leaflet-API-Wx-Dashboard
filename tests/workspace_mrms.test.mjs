import assert from 'node:assert/strict';
import test from 'node:test';

test('workspace MRMS pane retains the loaded image until its replacement loads', async () => {
    globalThis.window = { location: { protocol: 'http:', hostname: 'localhost', port: '8000' } };
    globalThis.fetch = async () => ({ ok: true });
    const { createMrmsEngine } = await import('../frontend/pages/mrms/mrms-engine.js');
    const layers = new Set();
    const overlays = [];
    const map = {
        hasLayer: (layer) => layers.has(layer),
        removeLayer: (layer) => layers.delete(layer),
    };
    const leaflet = {
        imageOverlay(url, bounds, options) {
            const handlers = new Map();
            const overlay = {
                url,
                bounds,
                options,
                once(event, handler) {
                    handlers.set(event, handler);
                    return overlay;
                },
                addTo() {
                    layers.add(overlay);
                    return overlay;
                },
                setOpacity(value) { overlay.opacity = value; },
                trigger(event) { handlers.get(event)?.(); },
            };
            overlays.push(overlay);
            return overlay;
        },
    };
    let frameNumber = 0;
    const api = {
        apiUrl: (url) => url,
        async fetchJson(url) {
            assert.match(url, /\/api\/overlay\/latest\?family=mrms/);
            frameNumber += 1;
            return {
                frame_key: `frame-${frameNumber}`,
                source_data_key: `source-${frameNumber}`,
                render: { image_url: `/mrms-${frameNumber}.png` },
                bounds: [-130, -60, 21, 52],
                timestamp: new Date(Date.now() + frameNumber * 1000).toISOString(),
                full_name: 'Rotation Track',
                units: '0.001/s',
                refreshing: frameNumber === 1,
            };
        },
    };
    const engine = createMrmsEngine({
        api,
        mapCore: { map, leaflet },
        legend: { clear() {}, setHtml() {} },
        status: { setDataInfo() {} },
        paneName: 'workspace-mrms-overlays',
    });

    const firstPromise = engine.loadLatest('RotationTrack_LL_30min');
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(overlays[0].options.pane, 'workspace-mrms-overlays');
    overlays[0].trigger('load');
    const first = await firstPromise;
    assert.equal(first.refreshing, true);
    assert.equal(layers.has(overlays[0]), true);

    const secondPromise = engine.loadLatest('RotationTrack_LL_30min');
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(layers.has(overlays[0]), true, 'old MRMS image remains while the replacement loads');
    assert.equal(layers.has(overlays[1]), true);
    overlays[1].trigger('load');
    const second = await secondPromise;
    assert.equal(second.refreshing, false);
    assert.equal(layers.has(overlays[0]), false);
    assert.equal(layers.has(overlays[1]), true);

    engine.clear();
    assert.equal(layers.size, 0);
});
