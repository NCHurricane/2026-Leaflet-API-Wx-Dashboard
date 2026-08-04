import assert from 'node:assert/strict';
import test from 'node:test';

import {
    workspaceFrameIndexAtOrBefore,
    workspaceFrameWindowWithPredecessor,
    workspaceTimelineSource,
} from '../frontend/pages/workspace/workspace-timeline.js';

test('workspace timeline matches the newest frame at or before the master time', () => {
    const frames = [
        { timestamp: '2026-08-04T00:00:00Z' },
        { timestamp: '2026-08-04T00:02:00Z' },
        { timestamp: '2026-08-04T00:04:00Z' },
    ];
    assert.equal(workspaceFrameIndexAtOrBefore(frames, '2026-08-04T00:03:00Z'), 1);
    assert.equal(workspaceFrameIndexAtOrBefore(frames, '2026-08-04T00:04:00Z'), 2);
    assert.equal(workspaceFrameIndexAtOrBefore(frames, '2026-08-03T23:59:00Z'), -1);
});

test('workspace timeline priority preserves Radar and prefers MRMS by cadence', () => {
    assert.equal(workspaceTimelineSource({ radar: [{}], mrms: [{}], satellite: [{}], rtma: [{}] }), 'radar');
    assert.equal(workspaceTimelineSource({ radar: [], mrms: [{}], satellite: [{}], rtma: [{}] }), 'mrms');
    assert.equal(workspaceTimelineSource({ radar: [], mrms: [], satellite: [{}], rtma: [{}] }), 'satellite');
    assert.equal(workspaceTimelineSource({ radar: [], mrms: [], satellite: [], rtma: [{}] }), 'rtma');
    assert.equal(workspaceTimelineSource({}), '');
});

test('workspace follower history retains one hidden predecessor frame', () => {
    const frames = [
        { timestamp: '2026-08-04T08:00:00Z' },
        { timestamp: '2026-08-04T08:30:00Z' },
        { timestamp: '2026-08-04T08:46:00Z' },
    ];
    const window = workspaceFrameWindowWithPredecessor(frames, '2026-08-04T08:14:00Z');

    assert.deepEqual(
        window.renderFrames.map((frame) => frame.timestamp),
        ['2026-08-04T08:00:00Z', '2026-08-04T08:30:00Z', '2026-08-04T08:46:00Z'],
    );
    assert.deepEqual(
        window.timelineFrames.map((frame) => frame.timestamp),
        ['2026-08-04T08:30:00Z', '2026-08-04T08:46:00Z'],
    );
    assert.equal(workspaceFrameIndexAtOrBefore(window.renderFrames, '2026-08-04T08:14:00Z'), 0);
});
