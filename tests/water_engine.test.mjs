import assert from 'node:assert/strict';
import { createWaterEngine } from '../frontend/pages/water/water-engine.js';

const mapLayers = new Set();
const map = {
    getBounds: () => ({ getSouth: () => 30, getNorth: () => 40, getWest: () => -90, getEast: () => -80 }),
    hasLayer: (layer) => mapLayers.has(layer),
    on() {},
    off() {},
    removeLayer(layer) { mapLayers.delete(layer); },
};
let activeLayer = null;
const leaflet = {
    layerGroup() {
        const layer = {
            markers: [],
            addTo() { mapLayers.add(layer); activeLayer = layer; return layer; },
            clearLayers() { layer.markers = []; },
        };
        return layer;
    },
    circleMarker(_latlng, options) {
        return {
            options,
            addTo(layer) { layer.markers.push(this); return this; },
            bindTooltip() { return this; },
            on() { return this; },
        };
    },
    DomEvent: { disableClickPropagation() {}, disableScrollPropagation() {} },
};

globalThis.window = { L: leaflet };
globalThis.document = { addEventListener() {}, removeEventListener() {} };
let fetchCount = 0;
globalThis.fetch = async () => {
    fetchCount += 1;
    return {
        ok: true,
        json: async () => ({
            cache_state: 'fresh',
            stations: [
                { site_id: 'river-1', lat: 35, lon: -85, network: 'river', observed_category: 'minor', readings: { stage: { value: 4, units: 'ft', timestamp: '2026-08-05T00:00:00Z' } } },
                { site_id: 'buoy-1', lat: 36, lon: -84, network: 'buoy', readings: { wave_height: { value: 2, units: 'm', timestamp: '2026-08-05T00:01:00Z' } } },
            ],
        }),
    };
};

let legendHtml = '';
const legend = { clear() { legendHtml = ''; }, setHtml(value) { legendHtml = value; } };
const messages = [];
const status = { setDataInfo() {}, setMessage(value) { messages.push(value); } };
const engine = createWaterEngine({
    api: { apiUrl: (value) => value },
    mapCore: { map, leaflet },
    legend,
    status,
});

await engine.setEnabled(true);
assert.equal(fetchCount, 1);
assert.equal(activeLayer.markers.length, 2);
assert.match(legendHtml, /River Flood Stage/);
assert.match(legendHtml, /Other Networks/);

engine.setFloodFilter('major');
assert.equal(activeLayer.markers.length, 1, 'the buoy remains visible when the river threshold filters the river gauge');

await engine.setNetworks(['river']);
assert.equal(fetchCount, 2);
assert.equal(engine.getFloodFilter(), 'major');
assert.doesNotMatch(legendHtml, /Other Networks/);

await engine.setNetworks([]);
assert.equal(fetchCount, 2, 'an empty network selection does not call the API');
assert.equal(activeLayer.markers.length, 0);
assert.equal(legendHtml, '');
assert.match(messages.at(-1), /Select at least one Water network/);

await engine.setEnabled(false);
assert.equal(mapLayers.size, 0);
assert.equal(legendHtml, '');
engine.destroy();

console.log('water engine behavior checks passed');
