import assert from 'node:assert/strict';
import test from 'node:test';

test('workspace RTMA panes wait for image load before replacing the visible layer', async () => {
    globalThis.window = { location: { protocol: 'http:', hostname: 'localhost', port: '8000' } };
    const { createRtmaEngine } = await import('../frontend/pages/rtma/rtma-engine.js');
    const layers = new Set();
    const overlays = [];
    const requests = [];
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
                opacity: options.opacity,
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
            requests.push(url);
            frameNumber += 1;
            return {
                render: { image_url: `/rtma-${frameNumber}.png` },
                bounds: [-130, -60, 21, 52],
                source_data_key: `frame-${frameNumber}`,
                timestamp: `2026-08-02T12:0${frameNumber}:00Z`,
                full_name: 'Temperature',
                units: '°F',
                refreshing: frameNumber === 1,
            };
        },
    };
    const legend = { clear() {}, setHtml() {} };
    const status = { setDataInfo() {}, setMessage() {} };
    const engine = createRtmaEngine({
        api,
        mapCore: { map, leaflet },
        legend,
        status,
        paneName: 'workspace-rtma-overlays',
    });
    const selection = {
        region: 'CONUS',
        stream: 'rtma_rapid_update',
        product: 'temperature',
    };

    const first = await engine.loadLatest(selection);
    assert.equal(first.refreshing, true);
    assert.equal(requests.length, 1, 'value points are skipped while markers are off');
    assert.equal(overlays[0].options.pane, 'workspace-rtma-overlays');
    overlays[0].trigger('load');
    assert.equal(layers.has(overlays[0]), true);

    const second = await engine.loadLatest(selection);
    assert.equal(second.refreshing, false);
    assert.equal(layers.has(overlays[0]), true, 'old image remains during the next load');
    assert.equal(layers.has(overlays[1]), true);
    overlays[1].trigger('load');
    assert.equal(layers.has(overlays[0]), false);
    assert.equal(layers.has(overlays[1]), true);

    engine.clear();
    assert.equal(layers.size, 0);
});

test('workspace RTMA values use their pane without requesting the gradient', async () => {
    globalThis.window = { location: { protocol: 'http:', hostname: 'localhost', port: '8000' } };
    const { createRtmaEngine } = await import('../frontend/pages/rtma/rtma-engine.js');
    const markerOptions = [];
    const requests = [];
    const layers = new Set();
    const map = {
        getZoom: () => 7,
        getBounds: () => ({
            contains: () => true,
            getSouth: () => 20,
            getWest: () => -130,
            getNorth: () => 55,
            getEast: () => -60,
        }),
        hasLayer: (layer) => layers.has(layer),
        removeLayer: (layer) => layers.delete(layer),
    };
    const leaflet = {
        divIcon: (options) => options,
        marker(_latlng, options) {
            markerOptions.push(options);
            return { bindPopup() {} };
        },
        layerGroup() {
            const layer = {
                addTo() {
                    layers.add(layer);
                    return layer;
                },
            };
            return layer;
        },
        imageOverlay() {
            throw new Error('gradient should not be requested');
        },
    };
    const api = {
        apiUrl: (url) => url,
        async fetchJson(url) {
            requests.push(url);
            const isDirection = url.includes('product=wind_direction');
            return {
                points: [{
                    lat: 35,
                    lon: -80,
                    value: isDirection ? 225 : 12.1,
                    city: 'Charlotte',
                    state: 'NC',
                }],
                timestamp: '2026-08-02T12:00:00Z',
                full_name: isDirection ? 'Wind Direction' : 'Wind Speed',
                units: isDirection ? 'deg' : 'm/s',
            };
        },
    };
    const engine = createRtmaEngine({
        api,
        mapCore: { map, leaflet },
        legend: { clear() {}, setHtml() {} },
        status: { setDataInfo() {}, setMessage() {} },
        gradientPaneName: 'workspace-rtma-gradient',
        pointPaneName: 'workspace-rtma-values',
    });
    engine.setShowGradient(false);
    engine.setShowValues(true);

    await engine.loadLatest({
        region: 'CONUS',
        stream: 'rtma_rapid_update',
        product: 'wind_speed',
    });

    assert.equal(requests.length, 1);
    assert.match(requests[0], /\/api\/data\/rtma\/points/);
    assert.equal(markerOptions.length, 1);
    assert.equal(markerOptions[0].pane, 'workspace-rtma-values');

    await engine.loadSecondary({
        region: 'CONUS',
        stream: 'rtma_rapid_update',
        product: 'wind_speed',
    }, 'wind_direction');
    assert.equal(markerOptions.length, 2, 'paired wind uses one replacement composite marker');
    assert.match(markerOptions[1].icon.html, /data-arrow-tail="value-bottom"/);
    assert.match(markerOptions[1].icon.html, /transform="rotate\(225 0 0\)"/);
});
