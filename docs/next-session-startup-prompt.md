# Next Session Startup Prompt

Date prepared: 2026-07-29

```text
Continue dashboard work in F:\Python\dashboard_2026.

Read first:
- docs/token-saver-maybe.md
- docs/dashboard-change-and-enhancement-superfile.md
- docs/worker-free-render-plan.md, Phase 8 completion summary only
- git status

Current checkpoint:
- Worker-free rendering Phases 0-8 are closed.
- The whole-system user-owned browser smoke passed.
- The optional `core` and `surface` Task Scheduler warmers passed enabled and
  disabled acceptance.
- New `rtma` and `mrms` optional profiles are implemented and registered
  disabled. RTMA targets CONUS Hourly/Rapid Update Temperature latest frames;
  MRMS targets PrecipRate, LL 60-minute Rotation Track, and Instant MESH.
- All four optional warmers are currently disabled for Radar benchmarking.
- Legacy direct-writing `Wx-Dashboard-*` tasks remain retired/disabled. No
  legacy-task unregistration was performed; deletion remains an explicit
  operator action.
- Optional warmers are API-only clients. Dashboard correctness, freshness,
  rendering, health, and cleanup do not depend on Task Scheduler.
- Phase 8 follow-up corrected SPC cold recovery, WPC cold recovery, NHC 304
  ledger classification, SPC issuance-aware Ready/stale display, and bounded
  Surface polling that honors coordinator retry timing.
- User browser proof confirmed SPC Days 1-5 recover to Ready with current
  vectors/overlays and Surface loads quickly with bounded polling.
- Focused post-correction validation passes 42 tests. The earlier combined
  Phase 8 correction run passed 62 tests. JavaScript syntax, Ruff/Python
  compilation where applicable, and diff checks passed. The denied
  `.pytest_cache` write remains an environment-only warning.
- Radar render optimization Phase 0 is complete and behavior-neutral.
  `python -m radar.bench` and focused tests cover scratch confinement,
  structured timing, golden contracts, cache-hit/no-op, the current
  three-frame empty-cache response, and 12-frame backfill.
- All eight KGSP/KFCX golden rows passed five byte-identical fresh-process
  renders. Evidence is in `docs/perf/2026-07-25-radar-baseline/`.
- Headline KGSP L3 N0B p50/p95: API hit 0.313/0.575 ms, current three-frame
  empty-cache response 3.804/4.114 seconds, and backfill-12
  8.230/8.352 seconds. Backfill p95 peak working set is about 2.52 GiB.
- The focused Radar gate passes 36 tests plus 42 subtests. Full pytest passes
  261 tests plus 42 subtests and retains only the pre-existing Workspace
  assertion against removed `WORKSPACE_REGION_BOUNDS`. Ruff, compilation, and
  diff checks pass. No browser proof was needed or claimed for Phase 0.
- Radar render optimization Phase 1 is implemented. An empty `/frames` request
  now renders exactly one newest frame synchronously and uses the existing
  keyed background path for the remaining initial/history frames.
  `OVERLAY_EMPTY_CACHE_SYNC_FRAMES` remains `3`.
- KGSP L3 N0B empty-cache response improved from 3.804/4.114 seconds p50/p95
  to 2.012/2.017 seconds, a 47.1%/51.0% reduction. All eight Phase 0 golden
  comparisons pass. Evidence is in `docs/perf/2026-07-25-radar-phase1/`.
- The Phase 1 focused Radar gate passes 38 tests plus 42 subtests. Full pytest
  passes 263 tests plus 42 subtests with only the pre-existing Workspace
  assertion. Three-site user-owned browser acceptance passed: the scrubber
  stayed on newest while history grew, and playback remained continuous from
  the initial two frames through the completed roughly 14-16-frame loops.
- Radar render optimization Phase 2 is implemented. Scheduled runs share one
  lazily started bounded render-process pool across their site/product batches;
  a selected-product background run owns one pool for its batch. The
  response-critical single-frame path starts no multiprocessing workers.
  Normal completion closes/joins the pool and exceptional completion
  terminates/joins it. `LIVE_RADAR_PARALLEL_WORKERS` remains unchanged.
- KGSP L3 N0B retained-pool backfill-12 measured 7.989/8.271 seconds p50/p95
  versus 8.230/8.352 seconds in Phase 0, a 2.9%/1.0% reduction. Every sample
  created one four-process pool; pool construction and worker-readiness/import
  were recorded separately. p95 peak working set remained about 2.50 GiB.
- All eight Phase 0 golden comparisons pass. Evidence is in
  `docs/perf/2026-07-25-radar-phase2/`. The focused Radar gate passes 49 tests
  plus 42 subtests. Full pytest passes 268 tests plus 42 subtests with only the
  pre-existing Workspace assertion. Ruff, compilation, and diff checks pass.
- Phase 2 user-owned browser acceptance passed on both `/radar` and
  `/workspace`. KGGW and KTFX newest frames appeared before their eight- and
  ten-frame four-process fills; the scrubber stayed on newest, playback
  remained continuous, all Radar frame/PNG requests returned HTTP 200, and no
  pool/render/Radar API errors appeared. Phase 2 is closed.
- Radar render optimization Phase 3 is implemented. Flat Level II volumes now
  use one site-owned `_VOLUME` source spool. Scheduled flat-volume runs
  list/download once per site and render all seven configured products through
  a bounded one-decode consumer seam. Product caches, fields, sweeps, palettes,
  units, SRV motion variants, and failure state remain independent.
- Five fresh-process KGSP samples reduced decode count from seven to one and
  improved all-product wall p50/p95 from 26.270/26.516 seconds to
  16.522/16.558 seconds, a 37.1%/37.6% reduction. Batch p95 peak RSS is
  1.86 GiB, below the Phase 2 backfill envelope. Evidence is in
  `docs/perf/2026-07-26-radar-phase3/`.
- All eight Phase 0 golden comparisons pass. Shared-batch REF, VEL, SRV, and
  ZDR PNG hashes also match their goldens. Focused tests cover canonical and
  legacy source lookup, one-decode fanout, product-failure isolation, and
  restoring field state between consumers. The focused Radar gate passes 56
  tests plus 42 subtests. Full pytest passes 275 tests plus 42 subtests and
  retains only the pre-existing Workspace assertion against removed
  `WORKSPACE_REGION_BOUNDS`. Ruff, compilation, JSON, and diff checks pass. No
  frontend behavior changed, so browser proof was not required or claimed.
  Phase 3 is closed.
- Radar render optimization Phase 4 is implemented. Unchanged source
  directories reuse persisted, validated ordered filenames; changed or invalid
  entries safely rediscover. Serial, parallel, and shared-Level-II paths now
  atomically move same-volume temporary PNGs into the public cache and clean up
  failed renders. Per-frame processed-key/index writes remain because their
  roughly 0.4-0.8 ms Phase 0 cost did not justify weaker crash consistency.
- Ten no-op samples reused discovery with zero rescans and measured
  7.687/11.890 ms p50/p95. Five fresh-process backfill-12 samples measured
  7.573/7.705 seconds versus Phase 2's 7.989/8.271 seconds, a 5.2%/6.8%
  reduction. Eight-row median finalization fell from 6.930 ms to 0.860 ms.
  Evidence is in `docs/perf/2026-07-26-radar-phase4/`.
- All eight Phase 0 golden comparisons pass. The Phase 4 focused Radar gate
  passes 63 tests plus 42 subtests. Full pytest passes 282 tests plus 42
  subtests and retains only the pre-existing Workspace assertion against
  removed `WORKSPACE_REGION_BOUNDS`. Ruff and compilation pass. No frontend
  behavior changed, so browser smoke was not required or performed. Phase 4 is
  closed.
- Radar render optimization Phase 5 is implemented. Same-volume Level II
  products selecting the same sweep reuse one Matplotlib QuadMesh while
  retaining exact geometry, projection, bounds, figure size, DPI, masked data
  semantics, palettes, and limits. The cache is bounded to one decoded-volume
  consumer call and closes before return.
- Five fresh-process KGSP samples improved the seven-product one-decode batch
  from 16.522/16.558 seconds p50/p95 to 11.814/11.995 seconds, a 28.5%/27.6%
  reduction. p95 peak working set fell 13.4% to 1,609.20 MiB. Evidence is in
  `docs/perf/2026-07-26-radar-phase5/`.
- All 35 batch PNGs match the seven-product control byte-for-byte, and all
  eight permanent golden rows pass. The focused Radar gate passes 64 tests
  plus 42 subtests. Full pytest passes 283 tests plus 42 subtests and retains
  only the pre-existing Workspace assertion against removed
  `WORKSPACE_REGION_BOUNDS`. Ruff and compilation pass. No frontend or API
  behavior changed, so browser smoke was not required or performed. Phase 5
  is closed.
- Radar render optimization Phase 6 is implemented behind the default-off
  `LIVE_RADAR_WEBGL_ENABLED` switch and is closed. It adds a separate `v1` L2
  Reflectivity polar artifact produced
  from the existing decode, a gated API route, and one-texture rendering shared
  by `/radar` and `/workspace`. PNG remains the immediate image, full playback
  path, and fallback.
- The representative 720-by-1,832 KGGW artifact is 1,322,700 bytes with zero
  gate-value quantization error. Five-run control/candidate total p50/p95 is
  4,034.155/4,174.683 ms versus 4,045.126/4,106.774 ms; artifact creation is
  8.824/12.785 ms. All eight permanent PNG goldens pass with the feature
  enabled in scratch. Focused validation passes 69 tests plus 42 subtests.
  Evidence is in `docs/perf/2026-07-26-radar-phase6/`.
- User-owned Phase 6 checks pass on `/radar` and `/workspace` for zoom-11+
  activation, a 0.100 ms cached draw, same-frame visible color/mask/geometry
  parity, and PNG-only behavior with the switch disabled. At extreme zoom,
  native WebGL bins correctly follow the radial scan while enlarged legacy PNG
  pixels remain axis-aligned; no constant overlay displacement was found.
- Active-playback and context-loss fallback passed. A throttled KBYX-to-KAMX
  selection change canceled stale browser fetches, and the KBYX overlay never
  reappeared. Phase 6 is closed.
- Radar render optimization Phase 7 is implemented behind the separate
  default-off `LIVE_RADAR_WEBGL_ANIMATION_ENABLED` switch and is closed. The
  rolling L2 Reflectivity window retains current, two upcoming, and one prior
  texture (about 5.04 MiB for four representative Phase 6 R8 textures) with at
  most two artifact fetches in flight. Activation requires the active and two
  forward textures; missing textures remain on PNG without changing playback.
- Focused validation passes 70 tests plus 42 subtests, three JavaScript window
  tests pass, and all eight permanent PNG goldens pass with WebGL enabled in
  scratch. Full pytest passes 292 tests plus 42 subtests and retains only the
  pre-existing Workspace assertion against removed `WORKSPACE_REGION_BOUNDS`.
  Ruff, compilation, JavaScript syntax, and diff checks pass. Evidence is in
  `docs/perf/2026-07-26-radar-phase7/`.
- Codex in-app browser acceptance passes on `/radar` and `/workspace` for
  bounded four-texture animation, zoom-9 PNG-only release, buffered zoom-11
  activation, continuous Workspace playback across its 30-second auto-refresh,
  and KAMX-to-KBYX cancellation without stale identity reappearance.
- Phase 8 core-product WebGL expansion requires separate approval.
  All-product conversion, tiles, and PNG retirement remain out of scope.
- Workspace Radar interaction follow-up: alert-polygon hover tooltips are now
  suppressed whenever Value Inspector or Storm Tracks is enabled and return
  when both are off. LSR hover tooltips are unaffected. The user confirmed this
  behavior in the browser.
- Storm Tracks checkbox-off behavior now invalidates any in-flight track
  request, immediately removes its marker layer, and rejects a stale response
  that would otherwise repopulate the icons. It deliberately retains
  selected-cell SRV motion state and playback continuity.
- JavaScript syntax, two focused Workspace tests, and diff checks pass for
  these interaction fixes. The broader Workspace file retains its unrelated
  stale `WORKSPACE_REGION_BOUNDS` assertion.
- All Uvicorn sessions were intentionally stopped. Restart the current API
  before making runtime or browser claims.

Guardrails:
- Preserve the dirty worktree and unrelated concurrent changes.
- Do not repeat Phase 8 acceptance unless a regression requires it.
- Keep the API at one application process; multi-worker operation remains
  unsupported.
- Do not unregister or delete legacy scheduled tasks without explicit operator
  authorization.
- Distinguish browser proof from tests, API probes, and runtime/log evidence.
- Keep all four optional warmers disabled during Radar benchmark/golden
  capture; RTMA and MRMS share heavyweight render capacity with Radar/Satellite.

Next step:
- After restarting the API, browser re-smoke Storm Tracks both after icons load
  and while a track request is in flight. Confirm unchecking removes icons
  immediately, they do not reappear, and selected-cell SRV playback remains
  continuous.
- Decide whether to authorize the first Phase 8 core-product WebGL family.
  Do not begin Phase 8 without separate explicit authorization.
```
