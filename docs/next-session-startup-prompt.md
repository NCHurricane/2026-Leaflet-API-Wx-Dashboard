# Next Session Startup Prompt

Use this as the bounded handoff for the next dashboard session. It summarizes
current operating truth; archived plans are evidence, not authorization.

## 1. Orient before editing

1. Work only in `F:\Python\dashboard_2026`.
2. Read `AGENTS.md`, this file, `docs/README.md`, and
   `docs/dashboard-change-and-enhancement-superfile.md`.
3. Read `docs/architecture.md` and `docs/patterns.md` only for the selected
   system area.
4. Inspect `git status --short` and recent `git log --oneline`. Preserve all
   unrelated dirty work. Do not commit or push without explicit owner approval.
5. Select one bounded item from the superfile, trace its callers/assets/tests,
   state the validation gate, and obtain any required phase authorization before
   implementation.

## 2. Current checkpoint

The last functional code checkpoint before this documentation-only
reconciliation is `3773d47`; Git HEAD may later include a docs-only checkpoint.
The important recent completed checkpoints are:

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
for the current dashboard and Version 2 lane. No next enhancement is selected by
this handoff. The remaining Satellite proposals include Archive UI, controls
redesign, measured GDAL tuning, explicitly opt-in CONUS warming, Tropical
storm-centered viewport behavior, remaining Meteosat normalization, and robust
large-download resume/retry. Their document order is not priority or approval.

Radar WebGL remains first only in ledger order. The unified cross-page Archive
family remains future work. Choose a family and define a bounded slice before
editing.

`docs/nch-weather-studio-greenfield-plan.md` is a separate parked design, not a
dashboard phase. Its dashboard comparison baseline was last reconciled on
2026-08-09 and must be updated against the current checkpoint before the owner
can authorize any Greenfield implementation.

## 5. Operating boundaries

- Preserve application-owned refresh coordination and the single-process
  deployment contract unless a new design is explicitly approved.
- Preserve Satellite ready-layer/no-flash ownership, scrub debounce/generation
  cancellation, render budgeting, and FCI native-read serialization.
- Keep Alerts rail entries national; viewport filtering belongs only to the
  legend.
- Keep basemap and boundary behavior shared through `frontend/core/map-core.js`.
- Do not treat archived proposals, directory-audit findings, or evidence files
  as deletion or implementation orders.
- Distinguish static checks, automated tests, runtime probes, controlled-browser
  checks, owner smoke, and deployment proof in every handoff.

## 6. Exact next action

At the start of the next work session, confirm Git state and then ask the owner
to select one bounded item from the current-dashboard enhancement ledger. Do not
automatically continue Meteosat, start Greenfield, or infer priority from list
order.
