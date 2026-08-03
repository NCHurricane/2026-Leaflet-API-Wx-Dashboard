import assert from 'node:assert/strict';

import { satelliteFrameIndexAtOrBefore } from '../frontend/pages/workspace/workspace-satellite.js';

const frames = [
    { frame_key: 'a', timestamp_utc: '2026-08-01T12:00:00Z' },
    { frame_key: 'b', timestamp_utc: '2026-08-01T12:05:00Z' },
    { frame_key: 'c', timestamp_utc: '2026-08-01T12:10:00Z' },
];

assert.equal(satelliteFrameIndexAtOrBefore(frames, '2026-08-01T11:59:59Z'), -1);
assert.equal(satelliteFrameIndexAtOrBefore(frames, '2026-08-01T12:00:00Z'), 0);
assert.equal(satelliteFrameIndexAtOrBefore(frames, '2026-08-01T12:08:00Z'), 1);
assert.equal(satelliteFrameIndexAtOrBefore(frames, '2026-08-01T12:15:00Z'), 2);
assert.equal(satelliteFrameIndexAtOrBefore(frames, 'not-a-time'), -1);

console.log('workspace satellite timeline tests passed');
