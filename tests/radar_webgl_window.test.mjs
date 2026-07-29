import assert from 'node:assert/strict';
import test from 'node:test';

import {
    selectRadarFrameIndex,
    selectRadarWebglWindow,
} from '../frontend/pages/radar/radar-engine.js';

function frame(key) {
    return {
        site: 'KGGW',
        product: 'L2_REF',
        selected_elevation: 0.5,
        frame_key: key,
    };
}

test('rolling window is current, two upcoming, then one prior', () => {
    const frames = ['a', 'b', 'c', 'd', 'e'].map(frame);
    assert.deepEqual(
        selectRadarWebglWindow(frames, 2).map((item) => item.frame_key),
        ['c', 'd', 'e', 'b'],
    );
});

test('rolling window wraps without duplicates and honors the texture budget', () => {
    const frames = ['a', 'b', 'c'].map(frame);
    assert.deepEqual(
        selectRadarWebglWindow(frames, 2).map((item) => item.frame_key),
        ['c', 'a', 'b'],
    );
    assert.equal(selectRadarWebglWindow(frames, 1, 2, 1).length, 2);
});

test('refresh preserves the frame active when the response completes', () => {
    const frames = ['a', 'b', 'c', 'd'].map(frame);
    assert.equal(selectRadarFrameIndex(frames, frames[2]), 2);
    assert.equal(selectRadarFrameIndex(frames, frames[2], 'missing'), 3);
});
