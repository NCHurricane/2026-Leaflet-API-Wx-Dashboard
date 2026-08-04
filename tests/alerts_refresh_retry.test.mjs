import assert from 'node:assert/strict';

import { liveAlertRefreshRetryDelayMs } from '../frontend/pages/alerts/alerts-engine.js';


assert.equal(liveAlertRefreshRetryDelayMs([{ refreshing: false }]), 0);
assert.equal(liveAlertRefreshRetryDelayMs([{ refreshing: true }]), 1_000);
assert.equal(
    liveAlertRefreshRetryDelayMs([{ refreshing: true, retry_after_seconds: 2.5 }]),
    2_500,
);
assert.equal(liveAlertRefreshRetryDelayMs([{ refreshing: true }], 29), 1_000);
assert.equal(liveAlertRefreshRetryDelayMs([{ refreshing: true }], 30), 0);

console.log('alerts refresh retry tests passed');
