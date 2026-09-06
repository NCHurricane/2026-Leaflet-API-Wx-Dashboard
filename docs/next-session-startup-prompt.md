# Next Session Startup Prompt

Use this as the bounded handoff for the next dashboard session. It summarizes
current operating truth; archived plans are evidence, not authorization.

Updated 2026-09-06 after owner decisions and checkpoint validation.

## 1. Orient before editing

1. Work only in `F:\Python\dashboard_2026`.
2. Read `AGENTS.md`, this file, `docs/README.md`, and
   `docs/dashboard-change-and-enhancement-superfile.md`.
3. Read `docs/architecture.md` and `docs/patterns.md` only for the selected
   system area.
4. Inspect `git status --short` and recent `git log --oneline`. Preserve all
   unrelated dirty work. Do not commit or push without explicit owner approval.
5. The next focus is already selected: a high-cost rendering-workflow audit of
   Satellite (especially Meteosat), Radar and the five named WebGL proposals,
   MRMS, and RTMA. Agree the audit plan after the accepted checkpoint and docs
   reconciliation are committed. Do not start renderer changes.

## 2. Current checkpoint

The September functional checkpoint `e200f74` records the owner-accepted MRMS
transition and Satellite zoom/sharpness changes, related page/test updates, and the
additional `img/20260831_nchurricane_logo.svg` asset. It follows `3773d47`
(functional) and `c8a4193` (documentation). The owner confirmed acceptance on
2026-09-06:

- Satellite request ceilings are CONUS z9, Full Disk z8, and Meso z9.
- Shared CSS preserves discrete Satellite tile/Radar PNG pixels during scaling
  and removes the native MRMS per-tile fade before promotion.
- MRMS keeps incoming PNGs hidden until display ownership changes; opacity
  controls do not reveal pending images.
- The additional logo is retained as an asset; canonical branding is unchanged.
- MRMS and SPC remain below Satellite in Workspace. The owner deferred the
  older proposals to move them above it.

Fresh verification on 2026-09-06: 77 focused Python tests passed after correcting
three stale CSS-version assertions to match the existing MRMS/Workspace pages.
The full suite passed **662 Python tests plus 42 subtests** and **54 Node tests**;
scoped Ruff, MRMS JavaScript syntax, and the added SVG's XML/embedded-content
checks passed. Diff whitespace checks and all 26 local Markdown links in the
seven active documents passed. Python reported 52 Matplotlib/xarray/NumPy
deprecation warnings.
Owner acceptance is recorded separately; no new controlled-browser run or
rendering benchmark was performed during this reconciliation.

Earlier completed checkpoints remain evidence:

- `3773d47` — Meteosat Phase 5 EUMETSAT acquisition improvements. Search
  pagination, five-minute feature metadata reuse, bounded transient retries, and
  a four-worker hard ceiling were accepted. The full gate passed 662 Python tests
  plus 42 subtests, all 54 Node tests, Ruff, and diff checks. The restarted owner
  smoke passed M12 acquisition, a five-frame catalog, responsive scrubbing, and
  clean terminal/console checks.
- `6020906` — keyless shared Esri basemap catalog and boundary policy. CARTO and
  USGS sources were removed. The four canonical choices are World Dark Gray
  Base, World Light Gray Base, USA Topo Maps, and World Imagery. CONUS-default
  pages keep states visible, show countries below displayed zoom 7, and add
  counties at displayed zoom 8. Tropical/Satellite keep countries visible, add
  states at displayed zoom 5, and counties at displayed zoom 8.
- `0e1eacb` — Meteosat Phase 4 corrections and M11 RSS-tuned selected-product
  workflow. This includes FCI native-read serialization, retained-layer
  generation ownership, delayed-feed catalog anchoring, and accepted RSS
  warming. Restarted M12/M11 owner smokes passed without dashboard lockups or a
  new NetCDF APPCRASH.
- `7bda975`, `7b2d9a5`, and `6759832` — Meteosat render budgeting,
  shared-canvas/zoom-aware rendering, and no-flash/scrub ownership checkpoints.
- `8ffcd14` — alert-only server-session cutoff, notification cadence/audio
  correction, and national Active Warnings rail. Owner smoke notified within 60
  seconds, and rail entries remained national while only the legend followed
  the viewport.

These validation counts describe the completed checkpoints; they are not proof
for later edits. Re-run the narrowest relevant gate after any change.

## 3. Closed work and retained evidence

- Cleanup Waves A through E are complete.
- Worker-free Phases 0–8 and the original Radar WebGL Phases 6–8 are complete.
  The Alerts near-one-second gate passed in its recorded run; older next-phase
  wording is historical. See the superfile section 9.2 closed-gate reference.
- The post-cleanup Satellite cross-page blocking prerequisite is complete.
- The bounded Meteosat latency family is complete through Phase 5. Its execution
  record is
  `docs/archive/meteosat-latency-overhaul-plan-2026-08-26.md`; do not resume it
  as an active plan.
- The superseded handoff that ended before `3773d47` is preserved at
  `docs/archive/next-session-startup-prompt-2026-08-26-pre-reconciliation.md`.
- `docs/perf/` contains phase-specific performance evidence. Preserve its
  recorded environment and validation category; benchmark evidence is not
  browser or owner proof.

## 4. What is active now

`docs/dashboard-change-and-enhancement-superfile.md` is the only active roadmap
for the current dashboard and Version 2 lane. Section 4.8 records the selected
rendering-audit focus. Audit questions include stage costs, first-frame/history
behavior, cache reuse, resource/queue ownership, and standalone/Workspace
presentation. Exact evidence collection and measurement scope remain to be
agreed with the owner; no new bottleneck or performance result is claimed yet.

The five Radar WebGL additions are `L2_RHO`, `L3_N0C`, `L3_DPR`, `L3_DAA`, and
`L3_DTA`. They are included in audit/planning scope, not authorized for
implementation or activation. Other enhancement families, including the unified
Archive workflow, remain deferred. Meteosat request-level retries are already
implemented; interrupted individual streamed-transfer resume is still a proposal.

`docs/nch-weather-studio-greenfield-plan.md` is a separate parked design, not a
dashboard phase. Its documented comparison was refreshed on 2026-09-06; exact
per-family parity, provider/dependency currency, and desktop feasibility still
need verification before any implementation. Greenfield is not the selected
next focus.

## 5. Operating boundaries

- Preserve application-owned refresh coordination and the single-process
  deployment contract unless a new design is explicitly approved.
- Preserve Satellite ready-layer/no-flash ownership, scrub debounce/generation
  cancellation, render budgeting, and FCI native-read serialization; preserve
  the accepted MRMS pending-image/native-tile promotion behavior.
- Keep current Workspace pane ordering and Radar/MRMS PNG authority/fallback.
- Keep Alerts rail entries national; viewport filtering belongs only to the
  legend.
- Keep basemap and boundary behavior shared through `frontend/core/map-core.js`.
- Do not treat archived proposals, directory-audit findings, or evidence files
  as deletion or implementation orders.
- Distinguish static checks, automated tests, runtime probes, controlled-browser
  checks, owner smoke, and deployment proof in every handoff.

## 6. Exact next action

Confirm the committed baseline, then work with the owner to define the rendering
audit plan for the already-selected four product families. Agree evidence and
measurement scope before expensive live runs. Record findings in the superfile
and dated evidence only when produced. Renderer changes follow an
agreed implementation slice after the audit; do not reopen completed phases or
start Greenfield from old handoff language.
