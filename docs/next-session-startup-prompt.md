# Next Session Startup Prompt

Date prepared: 2026-07-22

Start in `F:\Python\dashboard_2026`.

```text
Continue Satellite render optimization in F:\Python\dashboard_2026.

Read first:
- docs/dashboard-change-and-enhancement-superfile.md
- docs/phases-25-27-manual-smoke-checklist.md only when checking the older gate
- docs/architecture.md or docs/patterns.md only when the next change crosses
  those boundaries

Current checkpoint:
- The cross-page correction set was committed at `aa05b7d`.
- Satellite render optimization Phase 0 is committed at `a6f5f83`.
  `satellite_v2/bench.py` provides pinned cold-parse,
  warm-parse, and hit scenarios; timing is gated by
  `WX_SATELLITE_V2_BENCH=1`. The full nine-row matrix produced 27 runs / 135
  samples under `docs/perf/2026-07-22-baseline/`. All nine 3x3 scratch golden
  blocks (81 PNGs) passed byte-for-byte comparison.
- Phase 1 is committed at `fc534ba`. The NetCDF
  cache is now a true closing LRU, normal tile hits use PNG size/signature
  validation with deep fallback, and only GeoColor/GeoColorBlkMar allocate
  lon/lat geometry. All 81 final golden comparisons passed. Hit validation
  improved from 1.349–2.603 ms to 0.051–0.067 ms p50; compact results are in
  `docs/perf/2026-07-22-phase1/`.
- Phase 2 is committed at `8ee3a4b`. A 3x3 rasterio
  canvas changed pixels and was rejected by the golden gate. The accepted
  fallback returns the requested byte-stable 1x1 tile first, asynchronously
  warms eight neighbors, and deduplicates paths already in flight. The live
  matrix passed 81/81 goldens; headline cold p50 improved 11.9–14.9%. Compact
  results are in `docs/perf/2026-07-22-phase2/`.
- Phase 3 is committed at `29b83b6`. FCI multi-channel parsing now opens each chunk once;
  AHI uses four segment decode workers and stitches decimated strips. The full
  matrix passed 81/81 goldens. AHI cold p50 improved 49.6% from Phase 2 and FCI
  Nighttime Microphysics improved 43.2%. Results are in
  `docs/perf/2026-07-22-phase3/`.
- Phase 4 is complete locally and awaits its checkpoint commit. The approved
  shared `SourceRaster` LRU uses a 4096 MB default byte budget, is overridden by
  `WX_SATELLITE_V2_SOURCE_RASTER_CACHE_MB`, and evicts dependent renderer
  entries with each source. The full matrix passed 81/81 goldens. On the pinned
  Meteosat-12 frame, Channel13 then NighttimeMicrophysics reused Channel13 by
  identity: three unique grids occupy 354.797 MB instead of 473.062 MB without
  deduplication, saving 118.266 MB and one parse. Results are in
  `docs/perf/2026-07-22-phase4/`.
- The user completed the 2026-07-20 all-page manual smoke and clarified every
  finding. The correction set is implemented; page-by-page browser re-smoke is
  in progress and has not yet covered the full set.
- Page-by-page follow-up began 2026-07-21 with Workspace: its Alerts legend is
  now part of one full-width collapsible tabbed tray shared with Radar, Storm
  Tracks, and Storm Reports. Only available sources show tabs, one legend is
  visible at a time, full alert names wrap, and there is no nested Alerts
  scrollbar. This is a Workspace-only prototype pending browser acceptance
  before reuse elsewhere. Live alert payloads now
  render from bounded browser Cache Storage before a concurrent fresh request,
  and initial Alerts loading no longer waits for the Radar catalog. Browser
  confirmation is pending. Projected Arrival is now shown only for TOR, SVR,
  SMW, and SPS polygon selections; other alerts still open and zoom normally.
  Its right-side Alerts and LSR feeds remain nationwide during map navigation,
  while the map layers and legends continue to use the visible viewport. The
  left alert pills filter only map polygons/legend; the right-rail pills filter
  only nationwide cards, and new-alert notifications compare the nationwide
  feed independently of both pill groups.
- A read-only cross-project legend audit is recorded in the superfile. After the
  Workspace prototype passes browser smoke, extract its tray manager and shell
  into an opt-in shared core primitive; do not duplicate Workspace code. Use
  standalone Alerts as the second proof. Radar, SPC, and Tropical require
  page-specific source-state work first. Keep Surface, Satellite, RTMA, MRMS,
  Drought, WPC, and Water on their single legend hosts.
- Do not alter Surface/RTMA marker coordinates or anchors: the reported mismatch
  is real station coordinates versus city-center coordinates.
- Shared changes include State+County default-on borders, Country+graticule off,
  compact square categorical legend swatches, no pointer-click white focus box,
  no Source row in status cards, amber selected data pills, stronger cyan
  sidebar tabs, shared tooltips, and newest-frame animation holds.
- Surface now uses stale-while-refresh live data, station names in popup headings,
  and a values-only archive scrubber. The endpoint time plus lookback generates
  every 15-minute frame up to 24 hours with no artificial frame thinning.
- Alerts now separates Alerts/LSR legends, reuses cached viewport payloads,
  bounds long tooltips, offsets its detail panel below the logo, adds Zoom to
  Alert, caps alert navigation at z9, and uses one endpoint plus a 5-minute-step
  active-at-time archive lookback up to 6 hours.
- Radar removes `(Live Cache)`, groups Site Tools, and shares the corrected site
  tooltip. Satellite adds a GOES-19+CONUS Southeast US fit-bounds view and removes
  only the GOES-East Full Disk view preset; the Full Disk sector remains.
- RTMA value controls are below Data Stream and value markers show location plus
  the displayed value. MRMS and WPC opacity controls are in Live. WPC stale cache
  refreshes in the background and replaces itself when fresh.
- SPC/Drought selectors are harmonized. Tropical outlook polygons show Area,
  2-day, and 7-day values; Storm Layers opens by default; Issued uses the NHC
  printed local issuance with UTC in parentheses. WPC panels have visible
  semantic headings.
- Cache audit: MRMS already invokes its worker for missing/stale selected-product
  cache; RTMA already resolves/downloads/renders missing selected data on demand.
  Boundary endpoints already share server/browser/disk caching. Keep SPC,
  Drought, Tropical, and Water freshness behavior unchanged.
- Checkbox audit: binary visibility switches can safely retain checkbox state
  underneath, but multi-select products/categories should remain checkboxes and
  exclusive choices should remain pills/radios. Do not convert all controls to
  one visual type.

Validation at handoff:
- Phase 4: full matrix 81/81 byte-identical; the FCI cross-product probe reused
  Channel13 without reparsing and the byte-accounted cache matched unique-grid
  weight exactly.
- Phase 4 focused Satellite tests pass 33/33; full pytest passes 105 tests plus
  42 subtests. Changed Python compiles and `git diff --check` passes.
- Phase 3: full matrix 81/81 byte-identical; headline rows have five samples.
- Phase 3 focused Satellite validation passes. The full run reached 101 tests
  plus 40 subtests, with two unrelated Radar catalog subtests blocked by the
  concurrently missing `RadarScopeBR.pal`; Phase 3 did not touch Radar files.
- Phase 2: full asynchronous matrix 81/81 byte-identical; headline rows have
  five requested-tile samples and passed post-settle golden comparison.
- Phase 2 focused tests pass (15/15); full pytest passes 100 tests plus 42
  subtests.
- Phase 1: four affected GOES LRU reruns and the final 81-tile matrix are
  byte-identical; all nine hit rows have five samples.
- Phase 1 focused tests pass (14/14); full pytest passes 99 tests plus 42
  subtests.
- Phase 0 baseline integrity: 27 runs, five samples per run, nine pinned rows,
  matching cache statuses, no parse stages in warm samples, and 81/81 golden
  tiles byte-identical.
- Bench-disabled MESO1 render matched its golden block and wrote no timing data.
- Phase 0 focused Satellite tests pass (21/21).
- All changed JavaScript passes node --check.
- Changed Python passes py_compile.
- git diff --check passes.
- Focused Workspace + standalone Alerts tests pass (14/14).
- Full pytest after Phase 0: 93 passed plus 42 subtests. The only output was
  existing Radar colormap deprecation warnings and the environment's denied
  `.pytest_cache` write warning.

Next step:
1. Review and commit the Phase 4 code, tests, docs, and compact results.
2. Begin Phase 5 warm-path pool reuse and measure task granularity before
   deciding whether to combine a frame's zoom work.

Guardrails:
- Browser smoke is user-owned; report static versus browser proof honestly.
- Preserve product-specific controls and wiring; use the smallest coherent fix.
- Keep route logic in routes, response/cache behavior in services, and upstream
  refresh behavior in workers.
- Preserve unrelated working-tree changes.
```
