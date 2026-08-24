# Next Session Startup Prompt

Use this prompt to resume work in `F:\Python\dashboard_2026` without importing
the superseded chronological backlog into active context.

---

Work in `F:\Python\dashboard_2026`.

Read, in order:

1. `AGENTS.md`
2. `docs/next-session-startup-prompt.md`
3. `docs/dashboard-change-and-enhancement-superfile.md`
4. `docs/architecture.md` and `docs/patterns.md` only as needed for the selected
   slice
5. `git status --short --ignored` and the latest commits

`docs/token-saver-maybe.md` is an optional ignored local guide. It is not an
installed skill, does not auto-trigger, and tracked work must not depend on it.

The active plan is the current superfile. Older planning sources are preserved
unchanged under `docs/archive/2026-08-07-consolidation-sources/`; consult them
only when exact history is needed. Do not reactivate a historical proposal
merely because it appears there.

Current boundary:

- The repository-wide retained-tree audit and the documentation consolidation
  are complete.
- Cleanup Waves A through E are complete through implementation checkpoint
  `273f35d`; do not restart them from the historical candidate lists.
- The final cleanup gate passes 604 Python tests plus 42 subtests, all 36 Node
  behavior tests, repo-wide Ruff/compile/diff checks, affected API/runtime
  probes, and controlled Chrome checks for the UI/CSS slices.
- The confirmed post-cleanup Satellite cross-page blocking defect is corrected
  in committed checkpoint `0ac6b23`: tile waits use a Satellite-owned executor, page
  selection ownership cancels queued work on teardown, and an already-running
  render may finish and retain its complete cache artifact. The current gate is
  607 Python tests plus 42 subtests, 37 Node tests, repo-wide Ruff/compile/diff,
  responsive concurrent runtime probes, and controlled Chrome
  Satellite-to-Tropical navigation during an uncached Meteosat z7 render. Final
  owner smoke passed Meteosat-12 Channel 13 current/past-frame loading and
  immediate navigation to another page while past-frame work was active.
- Separate cached-source Meteosat-12 timing measured a three-frame median of
  `7 ms` source resolution, `2.948 s` decode, `52 ms` render/publication, and
  `3.021 s` HTTP time. The earlier `2m39s` source-prefetch observation did no
  tile decode/render; future prefetch runs expose explicit download timing.
- Section 4.2 shared non-Workspace alert monitoring is implemented and
  committed. Every standalone page joins one same-origin
  focused/visible-owner cohort; the fixed six-event national monitor baselines
  existing alerts and deduplicates banners, one sound burst, and one
  alert-colored border flash. An alert is eligible only when its valid issuance
  time is later than both the browser-cohort boundary and the current server
  startup boundary returned by the Alerts API; missing timestamps fail closed.
  Simultaneous batches flash the highest-priority event color. Alerts owns the
  shared On/Off setting and in-place selection;
  other pages open a deep-linked Workspace tab that resolves/selects/zooms
  without depending on monitor ownership. Workspace monitoring remains separate.
  Standalone Alerts keeps its active-warning list and rail counts national;
  only map layers, map counts, and the legend follow the current viewport.
- The Section 4.2 base monitor is committed. Its later server-session cutoff,
  cadence/audio, and national-rail follow-up is committed as `8ffcd14`. The
  isolated staged snapshot passes 615 Python tests plus 42 subtests, all 45 Node
  tests, Ruff, and JavaScript syntax. An isolated in-process API probe returned
  a valid current server-start timestamp. Controlled in-app browser
  checks retain the earlier
  Surface/Radar ownership and cross-tab Alerts On/Off evidence. The corrected
  deep link additionally opened a real Severe Thunderstorm Warning in Workspace,
  consumed the query parameter, drew the selected polygon at z9, opened detail,
  exposed the Projected Arrival radar-site prompt, logged no warnings/errors,
  and did not create a shared monitor host in Workspace. Owner smoke then saw a
  genuinely new Flash Flood Warning notice on Tropical and confirmed that its
  click opened the matching Workspace alert. Alert priority and
  highest-priority color selection are deterministic Node proof; the live smoke
  did not separately record the visual border-flash color.
- Owner smoke on 2026-08-24 observed a Severe Thunderstorm Warning but found
  roughly two minutes of issuance-to-notice latency and a clipped sound
  opening. Cache evidence showed the 30-second poll and 35-second TTL producing
  roughly 60-second refresh steps. The committed alert-only correction
  exposes the TTL, caps ordinary polling at 20 seconds, schedules the stale
  check at the TTL boundary, and preloads/unlocks audio on first interaction.
  Seven focused Node tests and 81 focused Python tests pass. The full combined
  gate passes 623 Python tests plus 42 subtests, all 48 Node tests, Ruff, and
  diff checks. The restarted owner smoke passed on 2026-08-24; a naturally
  issued alert notified within 60 seconds of issuance.
- Satellite section 4.4 checkpoint `6759832` adds the Meteosat latency overhaul
  plan, Phase 0 benchmark/tolerance evidence, and Phase 1 pure-waste removal
  without a pixel or render-version change.
- Phase 1 owner smoke on 2026-08-14 passed Meteosat-12 Channel 13 loading,
  sidebar loading state, scrubbing, selection changes, Satellite-to-Radar
  navigation during a Meteosat load, and clean consoles. It found Himawari-9
  Target using the generic West Pacific view and an opacity flash between every
  satellite frame in standalone Satellite and Workspace. First re-smoke passed
  the Target fix but confirmed that replacement readiness alone did not change
  the flash. Restoring the last known working rule then passed owner re-smoke:
  completed Leaflet frame layers remain mounted at opacity 0, incomplete layers
  detach, and visible ownership still waits for replacement readiness.
- That successful re-smoke exposed a separate GOES-19 Meso 2 queue-starvation
  case: dragging ahead of frames still rendering paused playback as designed,
  but every intermediate slider event requested a frame and obsolete renders
  retained selection-level ownership. The current cache-busted tree coalesces
  manual drag input to its resting frame and adds per-page foreground-frame
  generations, allowing superseded queued renders to cancel before the heavy
  render slot. The no-flash pool is unchanged. The full gate passes 623 Python
  tests plus 42 subtests and all 48 Node tests. Owner browser re-smoke passed on
  2026-08-24 in standalone Satellite and Workspace.
- Meteosat Phase 2a/2b/2d is implemented in the current uncommitted tree. Live
  neighbor rendering uses one canvas warp for the 3x3 supertile and the shared
  atomic crop/publication helper. Source-grid caps are keyed by destination
  zoom (2048 at z1–4, 4096 at z5–6, existing platform cap at z7+), and the
  default/GK2A/GMGSI/Himawari/Meteosat-12 namespaces advance to
  `products-v9`/`products-ami3`/`products-gmgsi2`/`products-ahi5`/`products-fci5`.
  Direct FCI hyperslab slicing (2c) was measured and rejected: it did not help
  Channel13 parse and slowed the pinned three-channel parse. On the same
  2026-08-24 frames, final z5 cold/warm p50s improve from 3401/546 ms to
  2915/179 ms for Meteosat-12 Channel13, from 5750/1423 ms to 3856/375 ms for
  NighttimeMicrophysics, and from 606/327 ms to 469/179 ms for Meteosat-9
  Channel13. The no-decimation Meteosat-12 z7 golden row stays within max delta
  2. The automated gate passes 631 Python tests plus 42 subtests, all 48 Node
  tests, repo-wide Ruff/compile, and diff checks. Owner smoke passed on
  2026-08-24 for Channel13 and NighttimeMicrophysics at z3/z4/z5/z7, including
  current/past frames, seams, detail, transitions, and clean consoles. Phase 2
  is accepted and ready for its independent commit.
- Audit findings remain historical evidence, not authorization for additional
  deletion or refactoring beyond the completed cleanup program.
- Preserve unrelated dirty work. Do not commit unless explicitly asked.
- Section 4.2's base monitor and its server-session correction are committed.
- The 2026-08-24 tree was reconciled and committed as separate logical
  checkpoints. Alert checkpoint `8ffcd14` contains the server-session cutoff,
  cache-aware notification cadence/audio unlock, national Alerts rail, all
  standalone monitor imports/cache bumps, and their alert tests/docs. Satellite
  checkpoint `6759832` contains Meteosat Phase 0/1, scrub coalescing/foreground
  cancellation, retained no-flash layers, Himawari Target fit, and their
  satellite tests/docs. `satellite-page.js`, `satellite.html`,
  `test_satellite_gmgsi.py`, `test_worker_free_phase7_radar_satellite.py`,
  `test_phase8_browser_smoke_corrections.py`, and `test_workspace_page.py`
  required hunk-level separation. This prompt and the superfile were held for
  the final handoff update. The Alert checkpoint used intermediate entry version
  `20260824a`; Satellite advanced the final entry to `20260824b`.
  `docs/README.md` and `docs/nch-weather-studio-greenfield-plan.md` stayed
  outside both and are committed separately as `db0984d`.
- Greenfield NCH Weather Studio is a separate project.

Default next discussion:

- The Alert follow-up owner smoke passed: a naturally issued alert notified
  within 60 seconds of issuance. Preserve that evidence with the Alert
  checkpoint without mixing the Satellite boundary.
- Meteosat Phase 2 automated validation and owner smoke are complete. Reconcile
  and commit it as one independent checkpoint when explicitly authorized.
- Do not begin Phase 3 merely because Phase 2 automated validation is green;
  it changes the memory/concurrency guard and requires separate authorization.
- The Satellite prerequisite is closed and does not choose that enhancement.
  Radar WebGL is first only by document order. Section 4.7 is a future unified
  cross-page Archive workflow, not an independent Surface-only completion.
- State exact scope, dependencies, verification, rollback/fallback behavior,
  and exclusions before editing. Cleanup completion alone does not authorize an
  enhancement family.

Decisions that must not drift:

- Radar WebGL’s retained expansion is exactly `L2_RHO`, `L3_N0C`, `L3_DPR`,
  `L3_DAA`, and `L3_DTA`; PNG remains authority/fallback. Broader WebGL is
  parked, and Radar PNG retirement/tile-server migration are rejected.
- Filtered Reflectivity and AWS notifications are removed from the plan.
- The shared Alerts monitor is browser-page-only, national, deduplicated across
  non-Workspace tabs, and active only while a non-Workspace dashboard page and
  the local server are open. It uses the existing six-event Workspace allowlist.
  It never announces an alert issued before the later of the browser-cohort or
  current server-session start boundaries.
  Alerts-page clicks select/zoom in place; other-page clicks open `/workspace`
  in a new tab and select/zoom so its operational tools are available around the
  polygon. Workspace keeps its own notifications and does not join the shared
  monitor cohort. There is no Windows background service or OS notification path.
- Shared notification flashes use the highest-priority newly observed alert
  color in this order: Tornado Warning, Severe Thunderstorm Warning, Flash Flood
  Warning, Tornado Watch, Severe Thunderstorm Watch, Flash Flood Watch.
- Keep current bounded RTMA/MRMS history; only a measured bounded 24/48-hour
  option remains eligible. Unbounded retention is rejected.
- Remove unreachable Satellite registry recipes/branches as cleanup candidates;
  do not preserve them as speculative products.
- Keep `tl_2025_us_state.*`; only the separate dead international-boundary
  bundle is a removal candidate.
- Persistent cross-process leases are closed unless deployment changes.
- Surface's 32 °F isotherm and disconnected `*-source` UI are removed. Surface
  colors come from the full authoritative server palette; do not restore a
  simplified browser palette.
- Surface's 15-minute-to-24-hour lookback remains in Live. Surface and Alerts
  Archive tabs show `Archive tools are planned for a future update.` Alerts has
  no general lookback slider; its Local Storm Report time pills remain separate
  live filters. Retained archive endpoints are groundwork for a later unified
  cross-page workflow, not supported standalone Archive products.
- Unused Leaflet stock-image references were removed rather than restoring the
  missing vendored images.

Validation language must stay exact:

- Unit/static/API/native-decode tests are not controlled-browser proof.
- A static `browser_smoke` suite is not an executed browser test.
- Runtime checks should restart/probe the actual listener, confirm no detached
  `127.0.0.1:8000` probe is shadowing the intended `0.0.0.0:8000` server, and
  use cache-busted assets before browser claims.
- Inspect frame/source metadata when diagnosing RTMA/MRMS fallback.

Begin by reporting Git state and confirming checkpoints `8ffcd14` and `6759832`
remain present. Then report the next bounded slice you intend to work on.
Ask only if a missing choice would materially change scope; otherwise inspect
and proceed within the selected authorization.

---

The documentation consolidation and Cleanup Waves A through E are committed.
If Git state contradicts this handoff, stop and reconcile the unexpected state
before selecting enhancement work.
