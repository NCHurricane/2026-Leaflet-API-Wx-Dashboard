# Next Session Startup Prompt

Date prepared: 2026-07-24

Start in `F:\Python\dashboard_2026`.

```text
Continue dashboard enhancement work in F:\Python\dashboard_2026.

Read first:
- docs/dashboard-change-and-enhancement-superfile.md
- docs/worker-free-render-plan.md, Phase 8 only
- docs/phases-25-27-manual-smoke-checklist.md only when checking the older gate
- docs/architecture.md or docs/patterns.md only when the next change crosses
  those boundaries

Mandatory session-start directive:
- Continue worker-free Phase 8 closure only: zero-task whole-system/browser
  acceptance and optional-warmer enabled/disabled acceptance.
- Phase 7 Radar/Satellite is closed after its automated gate and corrected
  user-owned browser/live-provider re-smokes passed.
- Preview and list existing OS tasks before any migration. Do not unregister
  tasks without explicit operator authorization.
- Do not start, investigate, benchmark, or implement Radar optimization Phase 0
  as an alternative track in this session. Worker-free Phase 8 goes first
  unless the user explicitly changes the priority.
- Do not read `docs/radar-render-optimization-plan.md` or
  `docs/satellite-radar-render-pipeline-files.md` at startup unless the user
  explicitly redirects the session to Radar.

Current checkpoint:
- Task-scheduler-free rendering Phase 0 and request-ledger work is complete.
  `app_core/upstream_ledger.py` covers application-owned Requests,
  urllib, and NODD S3 calls without logging query values or credentials. Alerts
  records the required stages and supports
  `python -m workers.alerts_worker --measure-twice`.
- A bounded processed-feature LRU now reuses enriched and simplified per-alert
  serialization by stable alert ID, raw feature digest, and display-policy
  digest; unresolved geometries are retried. The live-NWS remediation warm pass
  reused all 471 alerts and measured 0.504 seconds total, or 0.082 seconds after
  the response. The unchanged near-one-second gate passed and authorized the
  now-complete Phase 1. Evidence is in
  `docs/perf/2026-07-23-worker-free-phase0/alerts-two-pass-remediation.json`.
- Task-scheduler-free Phase 1 is complete. The app-owned refresh coordinator
  supplies a bounded executor/queue, actual-key deduplication, provider
  throttles, 90-second presence leases, exponential backoff, state reporting,
  periodic pruning, and graceful FastAPI-lifespan shutdown. Surface cold/stale
  observations and stale WPC refreshes use it. Surface now keys observations by
  region, fetches upstream once, and atomically publishes every product cache;
  its client retries cold warming. Presence-only records report `idle`. Cache
  cleanup is coordinator-owned every six hours and does not require page
  presence. Gate evidence is in
  `docs/perf/2026-07-23-worker-free-phase1/`.
- Task-scheduler-free Phase 2 is complete. Alerts processes only new/changed
  IDs, preserves native NWS polygons exactly, simplifies only zone/SAME-derived
  geometry below zoom 8, and serves bbox-filtered full geometry at zoom 8+.
  `low/high` is now the shared frontend/backend zoom vocabulary. Stale cache is
  served while one coordinator refresh observes the 35-second `nws-alerts`
  floor; a cold missing cache reports warming instead of empty success. Full,
  low-detail, and compatibility artifacts publish behind one atomic generation
  manifest. The full suite passes 145 tests plus 42 subtests. Runtime cache
  evidence found 36/36 native geometries unchanged and simplified 453 derived
  geometries with a 94.54% vertex reduction; an upstream-failure probe preserved
  the previous generation. Evidence is in
  `docs/perf/2026-07-23-worker-free-phase2/`.
- Task-scheduler-free Phase 3 is complete. `config/refresh_schedules.py`
  resolves SPC CST/CDT and UTC issuance boundaries, NHC routine/intermediate
  advisory and GTWO boundaries, product-specific WPC schedules, and the
  Thursday 08:30 ET USDM publication boundary. SPC refreshes only the selected
  product and cannot be suppressed by the legacy global sentinel; watches/MDs
  share a 90-second TTL. Tropical uses separate advisory/GTWO coordinator keys,
  payload issuance values, warning-driven three-hour intermediates, and a
  ten-minute active-page safety probe; only current-season archive data is
  mutable. WPC no longer uses one 12-hour threshold, and dated USDM caches are
  immutable. The user's first browser smoke and a focused local re-smoke then
  corrected SPC empty-watch status/timestamps and Day 3-8 Fire choices, WPC
  empty/default selection wiring plus River Flood/Surface direct loading,
  Drought's selected-date color, and retired standard NHC cone URLs. The
  user's follow-up browser smoke passed everywhere else. WPC product rows now
  remain exclusive but can be unchecked to clear the overlay; River Flood and
  Surface retain direct loading through an explicit checked row. SigWx now
  carries WPC's issued/valid text, a specific legend, and a clear authoritative
  no-areas state. The supplied current Day 1 shapefile bundle was legitimately
  empty (zero-byte SHP/SHX/DBF), while the parser produced five polygons from a
  non-empty official archived KML. The coordinator log was healthy; no
  issuance-boundary live-upstream proof was performed.
- Task-scheduler-free Phase 4 is complete. Its first browser smoke drove one
  focused scrubber correction, and the corrected re-smoke passed. MRMS
  selected-product coordinator keys enforce a two-minute success interval and
  pass the product explicitly
  through discovery, download, conversion, rendering, and catalog publication.
  Unchanged source keys skip object download/render work, and request paths no
  longer prewarm unrelated products. RTMA uses an hourly success interval and
  a two-hour latest discovery window while retaining direct latest rendering
  and progressive history. A process-wide heavy-render slot serializes MRMS,
  RTMA, live Radar, and on-demand Satellite tile rendering. The original
  focused tests passed 14/14. Isolated runtime validation rendered only selected `PrecipRate` and
  one 17Z RTMA hourly frame; immediate repeats returned `current` with about
  107 and 3,590 seconds remaining. The first browser smoke then found that
  partial MRMS/RTMA caches suppressed full-horizon fills and that RTMA-RU did
  not poll after an initially empty response even though six frames rendered
  server-side. The correction keys history by requested hours, backfills MRMS
  history from NODD, selects newest-first RTMA slices correctly, uses a
  15-minute RTMA-RU cadence, and polls/merges progressive frames every five
  seconds. The corrected Phase 4/coordinator suite passes 19/19 plus Node syntax
  checks. The corrected user browser re-smoke passed after a server restart and
  hard refresh for MRMS, RTMA Hourly, and RTMA-RU, with no other issues found.
  Phase 4 is closed. Evidence is in
  `docs/perf/2026-07-23-worker-free-phase4/`.
- Task-scheduler-free Phase 5 Water is implemented. Missing or
  older-than-30-minute indexes submit one shared coordinator rebuild; missing
  responses report warming, stale responses retain the prior complete index,
  and the client retries from `retry_after_seconds`. One rebuild fetches NWPS,
  CO-OPS, and NDBC once before atomic publication. NWPS/CO-OPS detail calls are
  serialized per provider and share a five-minute, 512-entry LRU with bounded
  backoff. The first browser smoke showed no river markers because the current
  index contained zero river stations. Publication now rejects missing or
  sharply reduced required networks while preserving the prior index; the
  request path also automatically rebuilds a fresh-but-incomplete index and
  returns retry timing. Only the historically unavailable optional CO-OPS
  Current layer may be skipped. A live rebuild published 12,761 river, 301
  coastal, and 894 NDBC stations, and the running CONUS API returned 12,162
  river stations from a fresh generation. The Phase 5 tests pass 10/10 and the
  combined Water run passes 18/18. The corrected user-owned browser re-smoke
  passed on 2026-07-23, so Phase 5 is closed and Phase 6 is authorized.
  Evidence is in `docs/perf/2026-07-23-worker-free-phase5/`.
- Task-scheduler-free Phase 6 Surface gradients is implemented. The endpoint
  serves explicit fresh/stale/warming state and the prior complete image while
  warming one shared region/minute observation snapshot or rendering exactly
  one `(WORLD|CONUS, product)` key. Daily AviationWeather station metadata,
  coordinator-budgeted IEM fallbacks, and a separate one-slot gradient budget
  bound upstream and render work; the client polls until the requested artifact
  is ready. The Phase 6 suite passes 24/24, including all 18 product/region
  artifact paths on isolated reduced scratch grids; broader
  Surface/coordinator tests pass 37/37. The first user-owned browser smoke found
  no product failures and recorded similar render times across products; a
  representative 2,246-point CONUS render took 4.2 seconds. It exposed the
  unmasked client-canvas fallback while the server's baked-mask PNG was
  pending. Warming now uses the prior masked PNG immediately or observations
  alone on a truly cold request; the client fallback remains only for server
  unavailability. Correction-focused validation passes 46/46. Full pytest
  reaches 214 passing tests plus 42 subtests, with only the pre-existing
  Workspace assertion against the concurrently removed
  `WORKSPACE_REGION_BOUNDS`. The corrected user-owned browser re-smoke passed
  for every CONUS and WORLD product on 2026-07-24. Phase 6 is closed and Phase
  7 is authorized next.
  Evidence is in `docs/perf/2026-07-23-worker-free-phase6/`.
- Task-scheduler-free Phase 7 Radar/Satellite is implemented and its automated
  gate passes. Lease-bound recurring coordinator jobs now stop after request
  presence expires. Radar preserves newest-first fallback, keys activity by
  site/level/product/elevation/storm motion, progressively fills history, and
  reports `history_filling`; chunk-prefix discovery has a 30-second process
  cache. Satellite retains live on-demand tiles as first priority, then delays
  selected rapid/Meteosat acceleration by five seconds. Source acquisition is
  deduplicated per frame, EUMETSAT FCI concurrency is one or two, and provider
  access reports `credentials_required` or `license_required`. The focused gate
  passes 53 tests plus 42 subtests; full pytest passes 222 tests plus 42
  subtests and retains only the pre-existing Workspace assertion against
  removed `WORKSPACE_REGION_BOUNDS`. The first Radar browser smoke exposed a
  five-minute success gate that stopped a six-hour request after its initial
  one-hour/12-frame batch; incomplete history now bypasses that cadence and
  succeeded jobs no longer claim they are still filling. A separate stale
  localhost-only server explained the apparent cross-page hang after restart;
  removing it restored Workspace/Radar/Surface/Satellite navigation. Restart
  and Radar re-smoke passed. The first Satellite smoke passed GOES-19 CONUS,
  then exposed invisible/over-generated MESO tiles, live-tile priority
  inversion on Himawari, and six-frame cold FCI fanout on Meteosat-12. Meso
  now fits current frame bounds and uses zooms 5-6; accelerators wait for live
  viewport work; cold neighboring frames prime only when cached. Follow-up
  testing then confirmed that Meteosat-11 RSS continued eight or more frames
  after switching to Meteosat-9 Full Disk. Satellite page instances now
  supersede their prior accelerator between frames while allowing another page
  viewing the old selection to keep it active. The single-worker application
  accelerator also renders in-process, avoiding the Windows child re-import
  that printed a Py-ART banner on Satellite. Restart/hard refresh and repeat
  that exact RSS-to-Full-Disk switch passed: the in-progress RSS frame was the
  allowed boundary, no additional abandoned RSS frames started, and the
  mid-session Py-ART banner did not recur. Phase 7 is closed and Phase 8 is
  authorized next. Evidence is in
  `docs/perf/2026-07-24-worker-free-phase7/`.
- Task-scheduler-free Phase 8 is implemented and awaiting acceptance closure.
  `workers/scheduler.py` registers no broad schedule; startup and
  `/api/health/coordinator` use application/source/cache/coordinator health
  rather than task sentinels. Tropical current-season archive refresh remains
  request-driven and six-hour cleanup is application lifecycle-owned. The task
  script defaults to preview-only and its bounded `core`/`surface` warmers call
  localhost API routes, returning `warmed`, `current`, `already_running`,
  `backoff`, or `failed`. The real preview found all 13 legacy tasks disabled
  and made no changes. Phase 8 focused tests pass 6/6; the combined
  cutover/lifecycle/schedule run passes 18/18. Full pytest reaches 240 passing
  tests plus 42 subtests; its only failure is the pre-existing Workspace
  assertion against the concurrently removed `WORKSPACE_REGION_BOUNDS`.
  A temporary port-8011 API probe returned healthy application-owned state, a
  running single-process coordinator, registered cleanup, and no task-health
  field. The first user-owned zero-task/browser smoke found WPC browser-cached
  charts under unchanged URLs, MRMS opening at the oldest frame, and ambiguous
  Satellite cached-tile/newest-first messaging. WPC now versions image URLs
  with the payload update token; MRMS opens and progressively fills at newest;
  Satellite explicitly keeps newest last, displays it before neighbor priming,
  and explains that visible tiles load from cache or render on demand. A second
  global-timestamp line exposes Loading/Fresh/Stale/Ready without repurposing
  page messages. Correction-focused tests passed 39/39 plus syntax/compile/lint/
  diff checks. A local in-app browser re-smoke confirmed WPC's versioned URL,
  MRMS at 28/28 with the slider at maximum, and Meteosat-12 Channel 13
  requesting 02:00Z before 01:45Z. The next user re-smoke passed WPC
  chart/timestamp parity and newest-first MRMS/Satellite behavior with no other
  product errors. It exposed Channel 14 being selectable but absent from the
  backend registry, timestamp state not appearing on other pages, and Satellite
  Ready preceding any rendered tile. Channel 14 is now registered for every
  supported provider mapping. All standalone pages receive shared
  Loading/Ready state; SPC and Surface additionally report computed stale state.
  Satellite now changes to Ready only after a successful active-layer tile-load
  event. The expanded correction suite passes 42/42 plus 16 Node syntax checks
  and Python compilation. Browser proof held Loading at 0/40 rendered tiles,
  changed to Ready at 23/40, and confirmed Ready on Drought. A fresh temporary
  server accepted Channel 14 legend/catalog validation before unavailable
  outbound NOAA S3 access stopped discovery. The continuing user-owned re-smoke
  now passes Surface, Satellite, Alerts, MRMS, Drought, WPC, and Water. RTMA
  passes the `Stale` to `Ready` transition; its observed cold fresh-data load
  took about 60-75 seconds, consistent with source download/render and possible
  shared heavy-render-slot queueing. Repeated RTMA testing exposed the latest
  refresh and request render concurrently downloading the same GRIB through one
  fixed `.part` path. GRIB acquisition is now serialized per destination and
  rechecks the completed cache after waiting; the focused Phase 4 suite passes
  11/11 plus Ruff and compilation. The corrected RTMA user re-smoke passed
  without the collision recurring, and Radar also passes. Leaving MRMS stopped
  page polling while the already-submitted bounded selected-product history
  batch finished, which is expected; it must not launch new batches after
  departure. SPC and Workspace also pass. Tropical initial refresh exposed a
  missing `setTimeoutFn` dependency in the engine context; the dependency is
  now wired and the focused Tropical/browser gate passes 23/23 plus Node syntax
  and Ruff. The corrected Tropical user re-smoke passes, completing the
  user-owned whole-system browser smoke. Optional-warmer enabled/disabled
  acceptance remains pending.
- Phase 1 supports one application process only. `WEB_CONCURRENCY` and
  `UVICORN_WORKERS` above 1 are rejected; do not use CLI multi-worker settings
  or legacy direct-write Windows tasks until persistent cross-process leases
  and provider budgets are implemented. Coordinator state is available at
  `/api/health/coordinator`.
- All six required isolated Surface/Radar/GOES/Himawari/EUMETSAT cold-render
  measurements are complete under
  `docs/perf/2026-07-23-worker-free-phase0/`. Runtime/worker evidence is
  recorded separately from browser proof; no browser proof was performed.
- The user kept the near-one-second Phase 0 requirement unchanged; the
  remediation passed it without relaxing correctness.
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
- Phase 4 is committed at `39de302`. The approved
  shared `SourceRaster` LRU uses a 4096 MB default byte budget, is overridden by
  `WX_SATELLITE_V2_SOURCE_RASTER_CACHE_MB`, and evicts dependent renderer
  entries with each source. The full matrix passed 81/81 goldens. On the pinned
  Meteosat-12 frame, Channel13 then NighttimeMicrophysics reused Channel13 by
  identity: three unique grids occupy 354.797 MB instead of 473.062 MB without
  deduplication, saving 118.266 MB and one parse. Results are in
  `docs/perf/2026-07-22-phase4/`.
- Phase 5 is committed at `168510f`. The rapid
  worker reuses one process pool across all frames/jobs and skips the trailing
  catalog rebuild for jobs with zero renders and zero errors. A pinned MESO
  two-zoom probe improved from 3514.710 ms to 832.513 ms steady p50 (76.3%).
  Task-per-zoom parallelism remains because cached parsing was only 12.888 ms
  p50. The pool paths produced 40 byte-identical PNGs and matching negative
  markers; results are in `docs/perf/2026-07-22-phase5/`.
- The Satellite render optimization track is closed through Phase 5. Its
  execution plan is archived under `docs/archive/`; the shared pipeline file
  reference is active again for Radar.
  Optional Phase 6 warp threading remains deferred unless later profiling and
  explicit approval reopen it.
- Radar render optimization now has a dedicated measure-first plan. No Radar
  behavior has changed. Phase 0 will add a scratch-only benchmark harness and
  eight-row L2/L3 golden baseline. Later candidates—newest-frame-first response,
  pool reuse, Level II source/decode deduplication, and discovery/finalize I/O—
  remain gated on the baseline. The flat NODD path stays authoritative and
  `LIVE_RADAR_L2_USE_CHUNKS` remains `False`.
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
  and a values-only archive scrubber. Cached gradient PNGs, including their
  embedded land mask, render independently of marker-row availability. The
  endpoint time plus lookback generates every 15-minute frame up to 24 hours
  with no artificial frame thinning.
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
  underneath, while most exclusive choices remain pills/radios. WPC product
  lists are the explicit exception: they use mutually exclusive checkboxes so
  the active product can be unchecked without choosing a replacement. Do not
  convert all controls to one visual type.

Validation at handoff:
- Worker-free Phase 6 focused tests pass 24/24; the broader
  Surface/coordinator run passes 37/37 and the correction-focused run passes
  46/46. Focused Ruff, changed-Python
  compilation, Surface JavaScript syntax, and `git diff --check` pass. The
  complete suite reaches 214 passing tests plus 42 subtests; its only failure
  is the pre-existing Workspace assertion against the concurrently removed
  `WORKSPACE_REGION_BOUNDS`. The first browser smoke otherwise passed and
  measured a representative 4.2-second full-resolution render; corrected
  warming-mask re-smoke passed for every CONUS and WORLD product.
- Worker-free Phase 5 focused tests pass 10/10 and the combined Water run passes
  18/18. Focused Ruff, changed-Python compilation, Water JavaScript syntax, and
  `git diff --check` pass. The complete suite reaches 189 passing tests plus 42
  subtests; the only failure is the already-documented unrelated Workspace
  assertion against concurrent user-owned `fitRegion` edits. The corrected
  user-owned Water browser re-smoke passed.
- The corrected worker-free Phase 4/coordinator suite passes 19/19. The isolated updated API
  registered `noaa-mrms`/`noaa-rtma`, rendered only selected `PrecipRate` and
  one 17Z RTMA hourly frame, and returned `current` on immediate repeats with
  about 107/3,590 seconds remaining. Focused Ruff, changed-Python compilation,
  and `git diff --check` pass. The complete suite reaches 176
  passing tests plus 42 subtests; one unrelated Workspace assertion is stale
  against concurrent user-owned `fitRegion` edits. This is API/runtime and
  automated-test evidence. The user browser re-smoke confirmed the corrected
  MRMS, RTMA Hourly, and RTMA-RU history behavior with no other issues.
- WPC follow-up tests pass 11/11. Browser proof on the running page confirms
  QPF and direct River Flood products load when checked and fully clear when
  unchecked; SigWx uses its product-specific legend. The isolated updated API
  returns the current no-areas message plus issued/valid metadata. A port 8000
  restart is still required before that running browser page can display the
  new backend metadata.
- Worker-free Phase 3 policy/scratch tests pass 13/13, and the focused
  browser-smoke regression set passes 18/18. They cover every
  registered SPC/WPC boundary, SPC CST/CDT conversion, separate NHC/GTWO
  boundaries, the USDM release transition, selected-only SPC recovery despite
  a fresh legacy sentinel, GTWO-only targeting, and immutable dated USDM cache
  reuse. Focused Ruff, changed-Python compilation, changed-JavaScript syntax,
  and `git diff --check` pass; full pytest passes 166 tests plus 42 subtests.
  Local browser proof confirms the reported SPC, WPC, and Drought corrections.
- Worker-free Phase 1 focused tests pass 13/13, covering mixed-product regional
  Surface dedupe/fanout, bounded queue, provider pacing, truthful presence
  state, leases, backoff, periodic cleanup mechanics, atomic shutdown safety,
  FastAPI lifespan, and Surface/WPC migrations. Changed Python compiles,
  focused Ruff checks pass, Surface JavaScript passes `node --check`, the full
  suite passes 135 tests plus 42 subtests, and `git diff --check` passes.
  Browser inspection found and drove the Surface-key and presence-state
  corrections; browser re-verification confirmed both. Browser re-smoke also
  confirmed masked gradients for every Surface product. Altimeter took about
  five seconds on its first load; that cosmetic delay was accepted and needs no
  further change.
- Worker-free Phase 0 is complete. Remediation-focused geometry/cache/ledger
  tests pass 12/12; full pytest passes 121 tests plus 42 subtests. Changed
  Python compiles, focused Ruff checks pass, measurement JSON parses, and `git
  diff --check` passes. The live Alerts and isolated render measurements are
  runtime/worker evidence, not browser proof.
- Phase 5: full matrix 81/81 byte-identical; reusable and owned pool paths
  produced 40 identical PNGs plus the same 75 negative-marker paths.
- Phase 5 focused Satellite tests pass 37/37; full pytest passes 109 tests plus
  42 subtests. Changed Python compiles and `git diff --check` passes.
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
1. Run the Phase 8 whole-system zero-task acceptance and user-owned browser
   smoke with all legacy tasks left disabled.
2. Exercise the optional warmer profiles disabled and enabled, including overlap
   with active API requests. Actual legacy-task unregistration remains a
   separate explicit operator-authorized action.

Radar optimization Phase 0 is not an alternative next step. It stays deferred
behind worker-free Phase 8 unless the user explicitly changes the priority.

Guardrails:
- Browser smoke is user-owned; report static versus browser proof honestly.
- The operator disabled the scheduled workers and restarted port 8000.
  Restarted-API verification returned 489 fresh national low-detail features
  and 25 fresh bbox-filtered full features from the same generation. Keep the
  legacy tasks disabled; browser smoke remains user-owned and unclaimed.
- Preserve optional Windows task warming through `workers.optional_warmer`;
  never run or advertise legacy direct writers concurrently with the
  coordinator. Mixed task/browser acceptance testing is still required.
- Preserve product-specific controls and wiring; use the smallest coherent fix.
- Keep route logic in routes, response/cache behavior in services, and upstream
  refresh behavior in workers.
- Preserve unrelated working-tree changes.
```
