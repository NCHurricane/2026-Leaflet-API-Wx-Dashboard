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
    assert.equal(overlays[1].options.opacity, 0, 'incoming image cannot stack over the displayed frame');
    engine.setOpacity(0.6);
    assert.equal(overlays[0].opacity, 0.6);
    assert.equal(overlays[1].opacity, undefined, 'opacity changes do not expose a pending image');
    overlays[1].trigger('load');
    const second = await secondPromise;
    assert.equal(second.refreshing, false);
    assert.equal(layers.has(overlays[0]), false);
    assert.equal(layers.has(overlays[1]), true);
    assert.equal(overlays[1].opacity, 0.6);

    engine.clear();
    assert.equal(layers.size, 0);
});

test('shared MRMS engine promotes loaded native tiles at high zoom and restores PNG below threshold', async () => {
    globalThis.window = { location: { protocol: 'http:', hostname: 'localhost', port: '8000' } };
    globalThis.fetch = async () => ({ ok: true });
    const { createMrmsEngine } = await import('../frontend/pages/mrms/mrms-engine.js');
    const layers = new Set();
    const mapHandlers = new Map();
    const images = [];
    const tiles = [];
    let prepareCalls = 0;
    let zoom = 7;

    function fakeLayer(url, bounds, options) {
        const handlers = new Map();
        const persistentHandlers = new Map();
        const layer = {
            url,
            bounds,
            options,
            once(event, handler) { handlers.set(event, handler); return layer; },
            on(event, handler) { persistentHandlers.set(event, handler); return layer; },
            addTo() { layers.add(layer); return layer; },
            setOpacity(value) { layer.opacity = value; },
            trigger(event) {
                persistentHandlers.get(event)?.();
                const handler = handlers.get(event);
                handlers.delete(event);
                handler?.();
            },
        };
        return layer;
    }

    const map = {
        hasLayer: (layer) => layers.has(layer),
        removeLayer: (layer) => layers.delete(layer),
        getZoom: () => zoom,
        on: (event, handler) => mapHandlers.set(event, handler),
        off: (event, handler) => {
            if (mapHandlers.get(event) === handler) mapHandlers.delete(event);
        },
    };
    const leaflet = {
        imageOverlay(url, bounds, options) {
            const layer = fakeLayer(url, bounds, options);
            images.push(layer);
            return layer;
        },
        tileLayer(url, options) {
            const layer = fakeLayer(url, null, options);
            tiles.push(layer);
            return layer;
        },
    };
    const api = {
        apiUrl: (url) => url,
        async fetchJson(url, options = {}) {
            if (url.startsWith('/api/mrms/tiles/prepare')) {
                prepareCalls += 1;
                assert.equal(options.method, 'POST');
                return {
                    tile: {
                        ready: true,
                        min_zoom: 7,
                        max_native_zoom: 8,
                        url_template: '/api/mrms/tiles/mrms-v1/RotationTrack_LL_30min/frame/{z}/{x}/{y}.png',
                    },
                };
            }
            assert.match(url, /\/api\/overlay\/latest\?family=mrms/);
            return {
                frame_key: '2026_08_04_12_00_00',
                render: {
                    image_url: '/mrms.png',
                    tile: {
                        ready: false,
                        min_zoom: 7,
                        max_native_zoom: 8,
                        prepare_url: '/api/mrms/tiles/prepare?product=RotationTrack_LL_30min&frame_key=frame',
                        url_template: '/api/mrms/tiles/mrms-v1/RotationTrack_LL_30min/frame/{z}/{x}/{y}.png',
                    },
                },
                bounds: [-130, -60, 21, 52],
                timestamp: new Date().toISOString(),
                full_name: 'Rotation Track',
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

    const loadPromise = engine.loadLatest('RotationTrack_LL_30min');
    await new Promise((resolve) => setImmediate(resolve));
    images[0].trigger('load');
    const loaded = await loadPromise;
    await new Promise((resolve) => setImmediate(resolve));

    assert.equal(tiles.length, 1);
    assert.equal(prepareCalls, 1);
    assert.equal(tiles[0].options.pane, 'workspace-mrms-overlays');
    assert.equal(tiles[0].options.maxNativeZoom, 8);
    assert.equal(images[0].opacity, 0.8, 'PNG stays visible while tiles load');

    tiles[0].trigger('load');
    assert.equal(tiles[0].opacity, 0.8);
    assert.equal(images[0].opacity, 0, 'loaded tiles replace the PNG without stacking opacity');

    const repeatPromise = engine.renderFrame(loaded.data);
    await new Promise((resolve) => setImmediate(resolve));
    images[1].trigger('load');
    await repeatPromise;
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(prepareCalls, 1, 'a prepared frame remembers its ready tile metadata');
    assert.equal(tiles.length, 2);
    tiles[1].trigger('load');

    zoom = 6;
    mapHandlers.get('zoomend')();
    assert.equal(layers.has(tiles[1]), false);
    assert.equal(images[1].opacity, 0.8, 'PNG fallback returns below native tile zoom');

    engine.destroy();
    assert.equal(mapHandlers.has('zoomend'), false);
    assert.equal(layers.size, 0);
});
