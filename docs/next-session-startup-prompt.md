# Next Session Startup Prompt

Date prepared: 2026-07-29

```text
Continue dashboard work in F:\Python\dashboard_2026.

Read first:
- docs/token-saver-maybe.md
- docs/dashboard-change-and-enhancement-superfile.md
- docs/worker-free-render-plan.md, Phase 8 completion summary only
- docs/satellite-platform-expansion-plan.md
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
- The first Radar Phase 8 family (`L2_VEL` and `L2_SRV`) was separately
  authorized, implemented, and browser-accepted on `/radar` and `/workspace`.
  Artifact `v2` adds product/motion-variant identity and two-byte velocity
  codes while preserving the PNG workflow and fallback. Five-sample
  first-PNG regressions remain below 5%; focused validation passes 79 tests
  plus 42 subtests, four JavaScript tests pass, and full pytest passes 303
  tests plus 42 subtests with only the known stale Workspace assertion.
- The current-source control/candidate PNGs are byte-identical. The exact
  permanent Phase 0 inputs were restored and verified against their committed
  size and SHA-256 contracts; all eight PNG golden rows pass with the family
  enabled. The first Phase 8 family is closed. Evidence is in
  `docs/perf/2026-07-29-radar-phase8-velocity/`.
- The second Radar Phase 8 family (`L3_N0B` and `L3_N0G`) was authorized,
  implemented, and browser-accepted on `/radar` and `/workspace`. Separate
  default-off Level III activation and animation switches preserve the PNG
  workflow and rollback. Five-sample first-PNG regressions remain below 5%;
  representative artifacts are 1.33 MB and 1.73 MB.
- Focused validation passes 85 tests plus 42 subtests, five JavaScript tests
  pass, and all eight permanent PNG golden rows pass. Full pytest passes 310
  tests plus 42 subtests and retains only two pre-existing Workspace
  assertions. Evidence is in
  `docs/perf/2026-07-29-radar-phase8-level3/`.
- Both core-product families and Radar render optimization Phase 8 are closed.
  Other dual-pol, categorical, accumulation, Echo Tops, and VIL products
  remain PNG. All-product conversion, tiles, and PNG retirement remain outside
  this plan.
- A post-Phase 8 live-freshness correction is implemented. `refresh=true`
  activates a separate selected-resource latest-only job every 60 seconds with
  a 180-second lease and one-frame render bound. Latest NODD listings use a
  separate 30-second cache; five-minute bounded history fill and 120-second
  history/archive listing caches remain unchanged.
- The shared Radar client follows a queued latest refresh with bounded
  three-second manifest polls for at most 60 seconds. Manual Refresh uses the
  same path, and current-frame/playback preservation remains authoritative.
  Focused validation passes 38 tests plus 42 subtests and six JavaScript tests;
  full pytest passes 315 tests plus 42 subtests with only the two known stale
  Workspace assertions. A read-only live KSFX/N0B probe returned the current
  key in 0.25 seconds. User-owned browser acceptance then passed with sooner
  Level II and Level III updates across two different radar sites, satisfying
  the remaining arrival-timing gate.
- Workspace Radar interaction follow-up: alert-polygon hover tooltips are now
  suppressed whenever Value Inspector or Storm Tracks is enabled and return
  when both are off. Alert-polygon tooltips are also hidden at zoom 10 and
  above on `/alerts` and `/workspace`; LSR hover tooltips are unaffected by either
  condition. The user confirmed the tool-selection suppression in the browser;
  the zoom threshold has focused static coverage.
- Workspace legend bodies use `padding: 0 15px`, which the user added to remove
  the unwanted legend scrollbar.
- Workspace now has one global `All Active Alerts` polygon pill. It selects the
  same complete category scope as `/alerts` without the narrower Workspace
  event whitelist; choosing any warning or watch pill turns the global pill
  off.
- Storm Tracks checkbox-off behavior now invalidates any in-flight track
  request, immediately removes its marker layer, and rejects a stale response
  that would otherwise repopulate the icons. It deliberately retains
  selected-cell SRV motion state and playback continuity.
- The user confirmed the pending Storm Tracks browser re-smoke passed.
- JavaScript syntax, ten focused Alerts/Workspace tests, and diff checks pass
  for these interaction fixes. The broader Workspace file retains its
  unrelated stale `WORKSPACE_REGION_BOUNDS` assertion.
- All Uvicorn sessions were intentionally stopped. Restart the current API
  before making runtime or browser claims.
- Satellite platform expansion Phase 0 is implemented for GK2A Full Disk
  Channel 13. It adds anonymous NOAA bucket discovery/download, AMI IR
  calibration/georeferencing, isolated `products-ami1` tiles, and the
  standalone Asia-Pacific control path. The focused gate passes 67 tests; the
  full suite passes 318 tests plus 42 subtests with the two known stale
  Workspace assertions. A current live listing and real-source direct PNG
  render pass. User-owned browser acceptance passed: all default-zoom frames
  loaded quickly, and active playback continued while newly requested z9
  frames also loaded quickly. Phase 0 is closed.
- GK2A Phase 1 direct-channel expansion is implemented after explicit
  approval. The filtered product set is `Channel01`, `Channel02`, `Channel03`,
  `Channel05`, `Channel07`, `Channel07Fire`, `Channel08RAMSDIS`,
  `Channel09RAMSDIS`, `Channel13`, and `Channel14`; no composites are exposed.
  Current live source renders pass for every added calibrated family. The
  largest proof, Channel 02, read a 473,301,589-byte native source into a
  bounded 7333 x 7333 raster in 5.538 seconds, rendered its proof tile in
  0.182 seconds, and peaked near 735.5 MiB working set. The focused gate passes
  68 tests. The latest full-suite run has 321 passing tests plus 42 passing
  subtests; the two known stale Workspace assertions and one unrelated
  concurrent shared-border-default assertion fail.
- User-owned GK2A Phase 1 default-zoom acceptance passed. The first Channel 02
  z8 test exposed shared Satellite animator defects: fractional zoom `7.5`
  reached the integer tile route as a 422, and invisible retained frame layers
  began historical live renders during the zoom. The correction enforces
  integer Satellite zooms and detaches inactive pooled layers at zoom start so
  the selected newest frame renders first. The correction-focused gate passes
  27 tests and JavaScript syntax checks. A Codex browser regression on a
  12-frame GOES-19 loop reached z8 with only the selected newest frame
  attached, 16 integer-z8 tile requests, and zero fractional URLs. The
  user-owned GK2A Channel 02 z8/playback re-smoke then passed with no recurring
  fractional-zoom 422s, newest-frame-first generation, and continuous
  playback. Phase 1 is closed.
- GK2A Phase 2 composites are implemented and closed. The selector exposes only
  `GeoColor`, `GeoColorBlkMar`,
  `TrueColor`, `NaturalColor`, `DayCloudPhase`, and `DaySnowFog`; recipes that
  require unmapped AMI bands remain hidden. Composite discovery intersects all
  required bands at one timestamp, and GK2A alone advances to
  `products-ami2`. The existing Black Marble recipe now loads the tracked PNG
  instead of a `.tif` filename that never existed. Synthetic AMI proofs for all
  six recipes, capability/common-time tests, JavaScript syntax, and the focused
  Satellite gate pass. User-owned browser acceptance passed for all six new
  products: renders loaded quickly, GeoColor Black Marble animation had no
  flicker or inter-frame blinking, and the API terminal and browser console
  remained error-free. Phase 2 is closed.
- A later Meteosat-12 Channel 13 North Africa smoke exposed a separate shared
  Satellite playback queue defect. Play advanced every second without waiting
  for the next frame, while invisible pooled layers could also issue live tile
  requests. Meteosat then serialized the accumulated work behind the
  process-wide heavyweight-render slot; Ctrl+C began graceful shutdown while
  already-started work continued, making its logs appear to resume in a burst.
  A first correction that waited for an entire frame was rejected after the
  user correctly noted that it defeated the intended pipelined warm-up. The
  current bounded correction keeps normal cadence for warmed frames, gates a
  cold playback advance only until its first visible tile, detaches inactive
  Leaflet layers, and makes the explicit viewport prefetch generate at most two
  frames ahead and one behind with two concurrent requests. Prefetch requests
  disable redundant server-side supertile neighbor fanout. A 2026-07-31
  first-frame re-smoke then exposed request-thread starvation before Play:
  the current FCI source completed after about 83 seconds and several PNGs
  finished, but their `FileResponse` bodies could not acquire another AnyIO
  worker because synchronous tile routes had filled the pool waiting on queued
  renders. The current correction reads the completed PNG inside the finishing
  route, reduces Leaflet's retained tile buffer from four to one, disables
  redundant neighbor fanout for UI tile requests, and admits live prefetch only
  after the current layer has produced its first visible tile. The subsequent
  user smoke confirmed fast current-frame and playback generation, but exposed
  a blink between fully generated frames on both Meteosat-12 Full Disk and
  GOES-19 CONUS. History showed that the 5 ms crossfade was intact but its
  old-layer-underneath contract had been removed when all inactive layers were
  detached after every swap. The correction restores the historical behavior
  of retaining completed frame layers at opacity zero, without restoring broad
  hidden-frame priming. The first re-smoke showed why completion matters: an
  incomplete Meteosat layer stayed active while a visibility-change catalog
  refresh discovered and selected a newer frame, filling the shared render
  queue and blocking later satellite selections. Incomplete layers are now
  detached, and catalog auto-update waits until the selected frame has a
  visible tile. Zoom-start cleanup and bounded live prefetch are unchanged.
  JavaScript syntax and 20 focused Satellite tests pass. The user-owned
  two-platform render/no-flash playback smoke passed; render speed and
  crossfade behavior are restored.

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
- GK2A Phases 0-2 are closed. GMGSI remains the separate Phase 3 and requires
  explicit authorization before implementation. No authorized Radar
  render-optimization work remains.
```
