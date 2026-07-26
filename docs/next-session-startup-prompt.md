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
  disabled acceptance. They are currently enabled.
- New `rtma` and `mrms` optional profiles are implemented and registered
  disabled. RTMA targets CONUS Hourly/Rapid Update Temperature latest frames;
  MRMS targets PrecipRate, LL 60-minute Rotation Track, and Instant MESH.
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

Guardrails:
- Preserve the dirty worktree and unrelated concurrent changes.
- Do not repeat Phase 8 acceptance unless a regression requires it.
- Keep the API at one application process; multi-worker operation remains
  unsupported.
- Do not unregister or delete legacy scheduled tasks without explicit operator
  authorization.
- Distinguish browser proof from tests, API probes, and runtime/log evidence.
- Disable all four optional warmers before Radar Phase 0 benchmark capture;
  RTMA and MRMS share heavyweight render capacity with Radar/Satellite.

Next step:
- Implement Radar render optimization Phase 0 only, following
  docs/radar-render-optimization-plan.md and
  docs/satellite-radar-render-pipeline-files.md.
- Keep Phase 0 behavior-neutral: add the scratch-only benchmark/timing harness
  and eight-row golden baseline, then stop for review before Phase 1.
```
