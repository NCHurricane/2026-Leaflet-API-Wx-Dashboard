import assert from 'node:assert/strict';
import test from 'node:test';

globalThis.window = {
    location: { protocol: 'http:', hostname: 'localhost', port: '8000' },
};

const {
    MONITORED_ALERT_COLORS,
    MONITORED_ALERT_EVENTS,
    chooseAlertMonitorOwner,
    filterMonitoredAlerts,
    monitoredAlertActivationUrl,
    monitoredAlertBatchPresentation,
    monitoredAlertPollDelayMs,
    reconcileMonitoredAlertSnapshot,
    sharedAlertFeatureId,
} = await import('../frontend/core/non-workspace-alert-monitor.js');

const NOW = Date.parse('2026-08-09T12:00:00Z');

function alert(event, id, options = {}) {
    return {
        type: 'Feature',
        id,
        properties: {
            event,
            sent: options.sent || '2026-08-09T11:59:00Z',
            expires: options.expires || '2026-08-09T13:00:00Z',
            status: options.status || 'Actual',
            messageType: options.messageType || 'Alert',
            areaDesc: options.areaDesc || 'Test County',
            parameters: options.parameters || {},
        },
        geometry: options.geometry || {
            type: 'Polygon',
            coordinates: [[[-80, 35], [-79, 35], [-79, 36], [-80, 35]]],
        },
    };
}

test('monitor scope and priority are the approved six alert events', () => {
    assert.deepEqual(MONITORED_ALERT_EVENTS, [
        'Tornado Warning',
        'Severe Thunderstorm Warning',
        'Flash Flood Warning',
        'Tornado Watch',
        'Severe Thunderstorm Watch',
        'Flash Flood Watch',
    ]);
    const batch = monitoredAlertBatchPresentation([
        alert('Flash Flood Watch', 'watch'),
        alert('Flash Flood Warning', 'ffw'),
        alert('Tornado Warning', 'tor'),
        alert('Severe Thunderstorm Warning', 'svr'),
    ]);
    assert.equal(batch.highestPriorityAlert.id, 'tor');
    assert.equal(batch.flashColor, MONITORED_ALERT_COLORS['Tornado Warning']);
    assert.deepEqual(batch.alerts.map((feature) => feature.id), ['tor', 'svr', 'ffw', 'watch']);
});

test('monitor filters unsupported, expired, test, cancel, and duplicate alerts', () => {
    const features = filterMonitoredAlerts([
        alert('Tornado Warning', 'tor', { sent: '2026-08-09T11:58:00Z' }),
        alert('Tornado Warning', 'tor', { sent: '2026-08-09T11:59:30Z' }),
        alert('Special Marine Warning', 'smw'),
        alert('Severe Thunderstorm Warning', 'expired', { expires: '2026-08-09T11:00:00Z' }),
        alert('Flash Flood Warning', 'test', { status: 'Test' }),
        alert('Tornado Watch', 'cancel', { messageType: 'Cancel' }),
        alert('Flash Flood Watch', 'vtec-cancel', { parameters: { VTEC: ['/O.CAN.KWNS.FF.A.0001/'] } }),
    ], NOW);
    assert.deepEqual(features.map((feature) => feature.id), ['tor']);
    assert.equal(features[0].properties.sent, '2026-08-09T11:59:30Z');
});

test('initial snapshot establishes a baseline and later snapshots notify once', () => {
    const initial = alert('Tornado Watch', 'initial', { sent: '2026-08-09T11:55:00Z' });
    const baseline = reconcileMonitoredAlertSnapshot(null, [initial], { now: NOW, baseline: true });
    assert.deepEqual(baseline.fresh, []);

    const newAlert = alert('Severe Thunderstorm Warning', 'new', { sent: '2026-08-09T12:01:00Z' });
    const next = reconcileMonitoredAlertSnapshot(baseline.state, [initial, newAlert], {
        now: Date.parse('2026-08-09T12:02:00Z'),
    });
    assert.deepEqual(next.fresh.map((feature) => feature.id), ['new']);

    const repeated = reconcileMonitoredAlertSnapshot(next.state, [newAlert], {
        now: Date.parse('2026-08-09T12:03:00Z'),
    });
    assert.deepEqual(repeated.fresh, []);
});

test('owner election favors the focused visible tab and fails over deterministically', () => {
    const peers = [
        { tabId: 'surface', heartbeatAt: NOW, startedAt: NOW - 5_000, focusAt: NOW - 500, visible: true, focused: false },
        { tabId: 'radar', heartbeatAt: NOW, startedAt: NOW - 4_000, focusAt: NOW - 100, visible: true, focused: true },
        { tabId: 'alerts', heartbeatAt: NOW - 10_000, startedAt: NOW - 3_000, focusAt: NOW, visible: true, focused: true },
    ];
    assert.equal(chooseAlertMonitorOwner(peers, NOW), 'radar');
    assert.equal(chooseAlertMonitorOwner(peers.filter((peer) => peer.tabId !== 'radar'), NOW), 'surface');
});

test('poll cadence honors stale-refresh hints and bounded failure backoff', () => {
    assert.equal(monitoredAlertPollDelayMs({}), 30_000);
    assert.equal(monitoredAlertPollDelayMs({ refreshing: true }), 1_000);
    assert.equal(monitoredAlertPollDelayMs({ refreshing: true, retry_after_seconds: 2.5 }), 2_500);
    assert.equal(monitoredAlertPollDelayMs({ refreshing: true }, 0, 30), 30_000);
    assert.equal(monitoredAlertPollDelayMs(null, 1), 5_000);
    assert.equal(monitoredAlertPollDelayMs(null, 5), 60_000);
});

test('activation URL carries the stable feature identity to Workspace', () => {
    const feature = alert('Flash Flood Warning', 'urn:oid:example alert');
    assert.equal(sharedAlertFeatureId(feature), 'urn:oid:example alert');
    assert.equal(monitoredAlertActivationUrl(feature), '/workspace?alert=urn%3Aoid%3Aexample%20alert');
});
