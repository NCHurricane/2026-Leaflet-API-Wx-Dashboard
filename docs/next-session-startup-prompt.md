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
  in the current working tree: tile waits use a Satellite-owned executor, page
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
  alert-colored border flash. Simultaneous batches flash the highest-priority
  event color. Alerts owns the shared On/Off setting and in-place selection;
  other pages open a deep-linked Workspace tab that resolves/selects/zooms
  without depending on monitor ownership. Workspace monitoring remains separate.
- The isolated Section 4.2 commit snapshot passes 613 Python tests plus 42
  subtests, all 44 Node tests, focused Ruff, JavaScript syntax, and diff checks.
  The combined working tree separately passes 620 Python tests plus 42 subtests
  and all 45 Node tests. Runtime verification confirmed a healthy national
  Alerts API. Controlled in-app browser checks retain the earlier
  Surface/Radar ownership and cross-tab Alerts On/Off evidence. The corrected
  deep link additionally opened a real Severe Thunderstorm Warning in Workspace,
  consumed the query parameter, drew the selected polygon at z9, opened detail,
  exposed the Projected Arrival radar-site prompt, logged no warnings/errors,
  and did not create a shared monitor host in Workspace. Alert priority and
  highest-priority color selection are deterministic Node proof; a live new
  issuance was not fabricated, so there is no visual browser-flash claim.
- Audit findings remain historical evidence, not authorization for additional
  deletion or refactoring beyond the completed cleanup program.
- Preserve unrelated dirty work. Do not commit unless explicitly asked.
- Greenfield NCH Weather Studio is a separate project.

Default next discussion:

- Select one bounded item from the approved current-dashboard enhancement
  ledger in section 4 of the canonical superfile.
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

Begin by reporting the Git state and whether Section 4.2 is still uncommitted.
If it is complete and committed, report the next bounded slice you intend to work on.
Ask only if a missing choice would materially change scope; otherwise inspect
and proceed within the selected authorization.

---

The documentation consolidation and Cleanup Waves A through E are committed.
If Git state contradicts this handoff, stop and reconcile the unexpected state
before selecting enhancement work.
