# Next Session Startup Prompt

Date prepared: 2026-07-25

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
- The Radar plan now keeps Phases 3-5 PNG-only. Phase 3 may establish a bounded
  decoded-sweep consumer seam for a future polar artifact but does not
  implement WebGL or permit a second Py-ART decode. Phase 5 remains optional
  and may be deferred if profiling does not justify more PNG-internal work.
- Separately authorized Phase 6 may pilot feature-flagged high-zoom WebGL for
  active, paused L2 Reflectivity. Below zoom 10 the client remains PNG-only;
  zoom 10 keeps PNG visible while prefetching the active texture; zoom 11
  crossfades only when ready. The existing PNG remains the first image,
  playback layer, per-frame compatibility fallback, and immediate
  configuration-first rollback. Separate polar artifacts cannot overwrite PNG
  caches/indexes.
- Separately authorized Phase 7 may add bounded L2 Reflectivity WebGL animation
  with the same thresholds. PNG playback starts immediately and continues
  until the active and minimum forward texture buffer is ready; missing
  textures fall back to PNG without pausing, skipping, restarting, or moving
  the scrubber. Retain only current, one prior, and two or three upcoming
  textures. Phase 8 core-product expansion requires another approval.
  All-product conversion, tiles, and PNG retirement remain out of scope.

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
- Review the amended Radar plan, then implement Phase 3 only after explicit
  authorization. Do not begin Phase 6/WebGL work during Phase 3.
```
