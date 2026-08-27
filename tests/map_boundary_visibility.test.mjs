import assert from 'node:assert/strict';
import test from 'node:test';

globalThis.window = {
    location: { protocol: 'http:', hostname: '127.0.0.1', port: '8000' },
};

const { getBoundaryVisibilityForZoom } = await import('../frontend/core/map-core.js');

test('CONUS maps keep states visible and transition countries/counties at z7/z8', () => {
    assert.deepEqual(getBoundaryVisibilityForZoom('conus', 6.49), {
        countries: true, states: true, counties: false,
    });
    assert.deepEqual(getBoundaryVisibilityForZoom('conus', 6.5), {
        countries: false, states: true, counties: false,
    });
    assert.deepEqual(getBoundaryVisibilityForZoom('conus', 7.5), {
        countries: false, states: true, counties: true,
    });
});

test('world maps retain countries and transition states/counties at z5/z8', () => {
    assert.deepEqual(getBoundaryVisibilityForZoom('world', 4.49), {
        countries: true, states: false, counties: false,
    });
    assert.deepEqual(getBoundaryVisibilityForZoom('world', 4.5), {
        countries: true, states: true, counties: false,
    });
    assert.deepEqual(getBoundaryVisibilityForZoom('world', 7.5), {
        countries: true, states: true, counties: true,
    });
});

test('maps without a boundary mode retain manual overlay behavior', () => {
    assert.equal(getBoundaryVisibilityForZoom(null, 8), null);
});
