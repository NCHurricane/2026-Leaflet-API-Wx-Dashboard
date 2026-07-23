# Worker-Free Phase 5 Evidence

Date: 2026-07-23

Scope: Water station-index stale-while-refresh, shared rebuild coordination,
client retry timing, shared provider fetches, bounded station-detail caching,
and network balancing.

## Implementation status

Phase 5 is complete. Its automated gate and corrected user-owned Water browser
re-smoke pass.

- A missing or older-than-30-minute station index submits one
  `("water", "station-index")` refresh through the shared coordinator.
- Missing responses report warming and stale responses retain the prior
  complete index. Both expose `refreshing`, `cache_state`, and
  `retry_after_seconds`.
- A newly written index is not considered fresh when any required river,
  coastal, or buoy network is absent; the API automatically enqueues recovery
  and reports the missing networks to the client.
- The Water client retries from `retry_after_seconds` while a build is running
  or backed off.
- One worker rebuild fetches the NWPS river layer, both shared CO-OPS layers,
  and NDBC `latest_obs.txt` once before atomically replacing the index.
- NWPS and CO-OPS detail requests are serialized per provider, use bounded
  exponential failure backoff, and share a five-minute, 512-entry LRU.
- Multi-network limiting reserves an initial fair share and then fills unused
  capacity without dropping available stations.

## Browser finding and remediation

The first user browser smoke showed coastal and NDBC markers but no river
gauges even though River was selected. The published index confirmed the UI was
not filtering them: it contained 301 coastal and 894 NDBC stations but zero
river stations. Earlier worker logs showed the normal river source returning
12,761 features, so a later incomplete rebuild had replaced the complete index.

Publication now requires non-empty river, coastal, and buoy networks and rejects
any network that falls below half its prior count. ArcGIS error payloads abort
required layers; the historically unavailable optional CO-OPS Current layer may
still be skipped after the required CO-OPS Water Level layer succeeds. The API
also detects a fresh-but-incomplete index and automatically starts the shared
rebuild instead of waiting for the age threshold.

A corrected live rebuild published 13,956 stations: 12,761 river, 301 coastal,
and 894 NDBC. The running port 8000 CONUS API returned `fresh`, with 12,162
river, 244 coastal, and 649 NDBC stations inside the requested viewport. This is
live worker/API evidence. The user then confirmed the corrected Water browser
re-smoke passed.

## Automated validation

- `tests/test_worker_free_phase5_water.py` passes 10/10. It covers ten concurrent
  cold callers deduplicating into one build, warming-to-fresh publication,
  stale serving, fresh-but-incomplete recovery, response retry timing, shared
  source fetch counts, atomic publication, incomplete-network rejection,
  optional CO-OPS handling, balanced limiting, and bounded detail-fetch
  deduplication.
- The combined focused Water run passes 18/18.
- Focused Ruff, changed-Python compilation, Water JavaScript syntax, and
  `git diff --check` pass.
- The complete suite reaches 189 passing tests plus 42 subtests. One unrelated
  Workspace assertion remains stale against concurrent user-owned `fitRegion`
  edits and expects the removed `WORKSPACE_REGION_BOUNDS` constant.

These are automated/API-path checks; the separate browser proof is recorded
above.

## Browser gate result

Passed by the user on 2026-07-23 after the corrected rebuild and
fresh-but-incomplete recovery fix. Phase 5 is closed and Phase 6 is authorized.
