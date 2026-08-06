# Dashboard Change and Enhancement Superfile

Last updated: 2026-08-05 (Task-scheduler-free rendering Phases 0-8 are closed.
The zero-task browser matrix and optional-warmer enabled/disabled acceptance
passed. Radar render optimization Phases 1-7 are implemented and
golden-validated; the Phase 1-2 browser acceptance passed and the backend-only
Phases 3-5 required no browser smoke. Phase 5 same-sweep QuadMesh reuse reduces
the seven-product L2 batch p50/p95 by 28.5%/27.6%. The reversible high-zoom
WebGL L2 Reflectivity pilot is default-off; two-page activation, redraw,
visible-parity, PNG-only, fallback, and cancellation checks pass. Phase 7 adds
default-off four-texture L2 Reflectivity animation; its automated, golden, and
two-page browser gates pass. Phase 7 is closed. Both separately authorized
Phase 8 core-product families—L2 Velocity/SRV and L3 N0B/N0G—are
browser-accepted, pass all eight permanent PNG golden rows, and are closed.
Radar render optimization Phase 8 is complete. Workspace expansion Phase 1
adds curated Day 1 SPC composition and is user-accepted. Phase 2 adds a bounded
one-hour GOES Satellite overlay with shared Workspace playback and is
user-accepted and closed. Phase 3 adds curated CONUS RTMA-RU live composition
and is user-accepted and closed. Phase 4 is authorized for curated MRMS live
composition and is implemented and user-accepted. A
separately authorized follow-up adds selected RTMA/MRMS one-hour history to the
shared Workspace timeline and is user-accepted. MRMS native-detail tiles are
also browser-accepted on Workspace and standalone MRMS. Workspace expansion
Phase 5 adds curated WPC composition; its initial gate and requested control
refinement re-smoke passed, so Phase 5 is user-accepted and closed. Workspace
expansion Phase 6 adds the full existing Water observation feature through one
shared engine. Its initial browser gate and requested Workspace-only
network-pill refinement re-smoke passed, so Phase 6 is user-accepted and closed.
The Workspace-wide layer-group disclosure follow-up also passed its user
re-smoke. Drought is explicitly excluded from Workspace expansion and remains a
standalone product. Project cleanup Phase 1 removed the 33-file audited set,
retired the empty root `js` mount and broken `/radar.html` route, centralized
generated telemetry under `cache`, fixed browser ISO archive timestamps, and
passed the complete automated and 13-page browser gates. Project cleanup Phase
2 Batch A removes the unused compatibility-only IEM Radar tile API while
preserving `/api/radar/live/*`; Batch B1 removes seven unused non-debug API
endpoints and their dedicated helpers; Batch B2 removes the unused raw-IEM
Radar diagnostic route while preserving storm-track internals; Batch C removes
the disconnected MRMS/SPC archive-result and progress workflow while retaining
Alerts and Surface archive routes.)

This file is the canonical planning and status file for dashboard changes,
completed enhancement phases, and future product work. It consolidates the
useful current information from the older roadmap, WPC plan, product-page shell
plan, backend/frontend refactor playbook, and refactor dossier.

Keep separate:

- `docs/architecture.md` for durable system architecture.
- `docs/patterns.md` for coding and implementation patterns.
- `docs/archive/refactor-baseline.md` for the original pre-refactor baseline.
- `docs/next-session-startup-prompt.md` for the short current handoff.
- The former Phases 25-27 manual smoke checklist was intentionally retired on
  2026-07-25 after the user-owned whole-system smoke passed. Do not restore it
  as an active gate; use the current stabilization scope below.
- `docs/archive/satellite-render-optimization-plan.md` for historical Satellite
  optimization execution detail.
- `docs/archive/satellite-platform-expansion-plan.md` for the completed GK2A +
  GMGSI platform-expansion track.
- `docs/archive/radar-render-optimization-plan.md` for the completed Radar
  latency track.
- `docs/archive/satellite-radar-render-pipeline-files.md` for the historical
  shared pipeline file reference.

## Project Cleanup Phase 1 (2026-08-05)

The first implementation slice from the user-interface-focused project audit
is complete and committed at `628c3cf`:

- Deleted the clean-room-validated 33-file set: 11 obsolete Python modules,
  the unused vendored TopoJSON client, the unused root favicon, 12 superseded
  image assets, four unused alert-specific sounds, and four obsolete/test city
  data files. The tracked reduction is 58,609,963 bytes (55.89 MiB).
- Removed the empty root `js` mount and directory, the broken `/radar.html`
  route, and the dead landing-page purge client/CSS. Required borders, runtime
  city files, `img/favicon.ico`, `img/nchurricane_logo.png`, station legend,
  fonts, and `sounds/weather_alert.mp3` remain.
- Moved the upstream ledger, Phase 0 measurement output, and headless-worker
  log defaults beneath `cache`. Existing root logs were preserved by moving
  254,352,783 bytes to `cache/metrics/` and `cache/logs/`; obsolete external
  generated-directory ignore rules were removed.
- Fixed the shared archive date parser for `Date.toISOString()` values such as
  `2026-08-05T20:00:00.000Z`. Refreshed stale Workspace assertions to the
  shared core region table/current timeline wiring and corrected the TOR/SVR/FLD
  Watch grid to three columns.
- Validation: changed-file Ruff (excluding the intentional import-order
  pattern), Python compilation, 382 pytest tests plus 42 subtests, 13-page HTTP
  and browser initialization, the landing navigation, and Workspace Watch
  filter interaction all pass. The 52 warnings are existing dependency
  deprecations. The user's subsequent full manual pass covered every page and
  product; every product loaded and animated where applicable with no errors.
  Non-blocking wiring/layout observations are recorded in
  `docs/post-refactor-follow-ups.md`.

At this checkpoint, Scheduled Task tooling/definitions, compatibility-only API
routes, and the standalone palette-preview area required separate approval.
Phase 2 subsequently received bounded authorization for the API cleanup only.

## Project Cleanup Phase 2 Audit and Batches A/B1/B2/C (2026-08-05)

The separately authorized audit and implementation batches are committed at
`795b9c1` and recorded in `docs/project-cleanup-phase2-audit.md`. No scheduled
tasks were changed.

- The preview-only task inspection found no registered `Wx-Dashboard-*` tasks
  on the current machine. Retain the installer's 13-name legacy removal
  allowlist and four optional API-warmer profiles; there is no current task
  definition cleanup to perform.
- Static inspection covered 89 FastAPI route decorators. Current page/runtime
  routes, dynamic MRMS tile URLs, standardized product-catalog contracts, the
  `/weather.html` redirect, and scheduler lifecycle hooks remain retained.
- Batch A removes the compatibility-only IEM Radar tile GET/HEAD route and its
  freshness route, their route-only service helpers, and the unused tile
  response import. The production Radar and Workspace engines remain on
  `/api/radar/live/*`.
- Ruff, Python compilation, 61 focused automated tests plus 42 subtests, and
  `git diff --check` pass. The 28 Matplotlib warnings and denied pytest cache
  write are existing/environment-only. The user-owned focused `/radar` and
  `/workspace` browser smoke passed current Radar loading and playback. Batch A
  is closed.
- The user confirmed this is a single-user application with no external API
  consumers. Batch B1 removes the seven unused non-debug endpoints listed in
  the audit, their dedicated route-only helpers, the dead Alerts selector and
  RTMA grid-JSON paths, and the Satellite catalog-status wrapper. The README API
  quick reference is reconciled to current routes.
- Batch B1 passes changed-file Ruff and compilation, 112 focused tests, and the
  complete Python suite of 387 tests plus 42 subtests. The 52 warnings are
  existing dependency deprecations. No live browser check was performed because
  the removed endpoints had no current frontend callers.
- Batch B2 removes `/api/radar/debug/meso-raw` and its route-local response
  shaping. The internal IEM fetch, radar-site normalization, storm-cell
  classification, and `/api/radar/live/storm-tracks` workflow remain intact.
  Ruff/compilation, 70 focused tests plus 42 subtests, and the full 387-test
  Python suite plus 42 subtests pass with the same 52 existing warnings. No
  browser check was needed because the debug route had no frontend caller.
- Batch C removes `/api/archive/mrms`, `/api/archive/result`,
  `/api/archive/spc`, and `/api/progress/{task_id}`, their MRMS/SPC
  render-session/result implementation, and the now-unused
  `app_core/progress.py` state module. Active Alerts and Surface archive routes
  remain unchanged. Changed-file Ruff/compilation, 66 focused retention tests,
  and the full 389-test Python suite pass with 31 existing dependency
  deprecation warnings. Static caller inspection and route tests establish that
  no frontend workflow was removed, so no browser check is required. The route
  inventory is now 74 decorators.

Recommended next authorization: a bounded Phase 3 removal of four tracked,
unreferenced research/diagnostic outputs totaling 2,672,966 bytes
(`tmp/pdfs/*` and `tools/KRAX_chunk_assembled.png`), plus recurrence prevention
for generated diagnostic output. Keep task tooling/definitions and palette
preview deferred.

## Active Tracks (2026-08-05)

Track numbers preserve the existing roadmap grouping. Track 3 Radar render
optimization Phases 3-5 are closed with byte-identical golden output,
one-decode Level II product fanout, persisted discovery reuse, and atomic PNG
publication. Phase 5 reuses one same-volume QuadMesh per selected sweep and
passes its benchmark, memory, lifecycle, regression, and golden gates. Phase 6
is closed after passing its automated payload/latency/golden gates and
user-owned two-page activation, redraw, visible-parity, PNG-only, fallback,
and cancellation checks. WebGL remains additive and independently revertible
to PNG-only behavior.

1. Frontend True Split (Stage 2) + Severe Weather Workspace — planned in
   this file (section below). Phases 18-24 are complete and user-confirmed.
   Phases 25-27 are complete and statically validated. `/workspace` composes
   Alerts and Radar engine APIs, owns the preserved arrival/speed tools, and
   replaces the deleted legacy shell/monolith. The former consolidated browser
   checklist was retired after the 2026-07-25 whole-system smoke passed. The
   bounded current-dashboard stabilization gate completed on 2026-07-31.
   Workspace expansion Phase 1 was authorized on 2026-08-01 and completed for
   curated SPC products. Phase 2 is complete for a curated one-hour GOES
   Satellite overlay with shared Workspace playback; its user-owned browser
   gate passed on 2026-08-02. Phase 3 is implemented for curated CONUS RTMA-RU
   live composition; its user-owned browser gate passed on 2026-08-02. Phase 4
   is implemented and user-accepted for curated MRMS live composition. The
   authorized shared-timeline follow-up is implemented and user-accepted for
   selected MRMS and RTMA-RU history. MRMS native-detail tiles are accepted on
   both Workspace and standalone MRMS. Phase 5 WPC and its mutually exclusive
   day/product control refinement are implemented, committed at `1180b74`,
   user-accepted, and closed. Phase 6 Water is implemented through the shared
   standalone engine. Its initial browser gate and Workspace-only network-pill
   refinement re-smoke passed; Phase 6 is user-accepted and closed. The shared
   layer-group disclosure follow-up also passed user re-smoke. Drought is not
   part of Workspace expansion and remains standalone-only.
2. Task-scheduler-free refresh/rendering — Phases 0-8 are complete under
   `docs/archive/worker-free-render-plan.md`. Application-owned HTTP and NODD S3 calls
   emit a credential-safe ledger, all required isolated cold renders are
   recorded, and the remediated live-NWS warm pass reused 471/471 alerts. It
   completed in 0.504 seconds total and 0.082 seconds after the response, so
   the Phase 0 gate passed. The Phase 1 bounded coordinator, provider policies,
   backoff/state reporting, atomic writes, lifespan ownership, cleanup schedule,
   and Surface/WPC migrations passed their focused gate. Phase 2 adds
   changed-alert processing, provenance-safe low-detail geometry, aligned
   `low/high` zoom selection, bbox-filtered full geometry at zoom 8+, a
   35-second NWS provider floor, stale-while-revalidate, and atomic
   multi-artifact generations. Phase 3 adds the tested issuance registry,
   targeted SPC recovery, separate NHC advisory/GTWO scopes, current-season-only
   archive refresh, product-specific WPC cadence, and publication-aware
   immutable USDM keys. The first Phase 3 browser smoke also corrected SPC
   empty-watch/Fire selection behavior, WPC empty and direct-load wiring,
   Drought selected-date styling, and retired standard NHC cone URLs. Phase 4
   carries selected MRMS products through one two-minute coordinator key,
   no-ops unchanged source keys, keeps hourly RTMA on an hourly success cadence,
   and serializes heavyweight MRMS/RTMA/Radar/Satellite rendering. Its first
   browser smoke exposed partial-history and empty-response polling defects.
   The correction passes focused tests and the user's restart/hard-refresh
   re-smoke for MRMS, RTMA Hourly, and RTMA-RU. Phase 5 Water is implemented:
   missing/stale station indexes now use one shared coordinator rebuild,
   stale data remains available, the client honors response retry timing,
   provider detail requests use a bounded five-minute cache with serialization
   and backoff, and network balancing fills available capacity. Its automated
   gate passes. The first browser smoke exposed an incomplete index with zero
   river stations. Required-network validation now prevents partial publication,
   the request path automatically rebuilds even a fresh incomplete index, and a
   corrected live rebuild restored 12,761 river stations. The corrected user
   browser re-smoke passed, closing Phase 5. Phase 6 Surface gradients is
   implemented: requests warm one shared region/minute observation snapshot,
   retain the last complete image, and render only the requested
   `(WORLD|CONUS, product)` under an independent one-slot budget. Daily
   AviationWeather station metadata and coordinator-budgeted IEM fallbacks
   bound provider traffic. Its automated gate passes. The first user-owned
   browser smoke found similar per-product render times (a representative
   2,246-point CONUS render took 4.2 seconds) and no other issues, but exposed
   the unmasked client fallback before the baked-mask PNG arrived. Warming now
   uses the prior masked PNG or observations alone. The corrected user-owned
   CONUS/WORLD all-product re-smoke passed on 2026-07-24, closing Phase 6.
   Phase 7 adds lease-bound coordinator activity for selected Radar/Satellite
   work, progressive Radar history state, selected application-owned Satellite
   acceleration, source deduplication, bounded EUMETSAT concurrency, and
   explicit provider capability responses. Its automated gate passes. Corrected
   user-owned Radar and representative GOES/Himawari/EUMETSAT re-smokes passed,
   including Satellite first-view priority and stopping an abandoned
   Meteosat-11 RSS accelerator between frames. Phase 7 is closed. Phase 8
   implements the zero-task cutover: broad scheduling is retired, health is
   application/source/cache based, current-season Tropical and cleanup remain
   application-owned, and optional task profiles delegate through localhost.
   Its focused automated gate, whole-system browser smoke, and optional-warmer
   enabled/disabled acceptance pass. Phase 8 is closed.
3. Radar render pipeline latency optimization — execution-grade plan prepared
   in `docs/archive/radar-render-optimization-plan.md`. Phase 0 is complete. Phase 1
   returns one newest frame before the existing keyed background fill; its
   focused, benchmark, golden, and browser gates pass. Phase 2 reusable pools
   also pass automated/golden validation and browser acceptance on `/radar`
   and `/workspace`. Phase 3 site-owned Level II sources and one-decode bounded
   product fanout pass automated/benchmark/golden validation. Phase 4
   persisted discovery reuse and atomic PNG publication also pass their
   automated, benchmark, recovery, pruning, and golden gates. Phase 5
   same-sweep QuadMesh reuse passes benchmark, memory, lifecycle, regression,
   and golden gates. Phases 6-7 add separately gated high-zoom WebGL L2
   Reflectivity activation and bounded animation while preserving PNG as the
   complete workflow and fallback. Phase 8 extends that path through two
   separately gated core-product families: L2 Velocity/SRV and L3 N0B/N0G.
   Product/motion-scoped `v2` artifacts, separate default-off activation and
   animation switches, measured latency/payload, focused/full regression,
   rollback, both-page browser gates, and all eight permanent Phase 0 PNG
   golden rows pass. Both families and Radar render optimization Phase 8 are
   closed.
4. Satellite render pipeline latency optimization — complete through Phase 5
   and archived. Optional Phase 6 warp threading is deferred unless later
   real-run profiling and explicit approval reopen it.
5. GK2A + GMGSI new platforms — closed under
   `docs/archive/satellite-platform-expansion-plan.md`. Phase 0 implemented the
   bounded GK2A Full Disk Channel 13 live-on-demand proof in the migrated
   standalone Satellite page and passed user-owned browser acceptance. Phase 1 is
   implemented after explicit approval with ten filtered direct products
   spanning visible/near-IR, shortwave IR, water vapor, and longwave IR; it
   exposes no composites. Live source renders pass for every added family. The
   focused gate passes 68 tests. The latest full-suite run has 321 passing
   tests plus 42 passing subtests; the two known stale Workspace assertions and
   one unrelated concurrent shared-border-default assertion fail. Default-zoom
   acceptance passed. The first z8 Channel 02 smoke
   exposed fractional tile-route 422s and historical pooled layers generating
   before the newest frame. The shared animator correction now enforces
   integer zooms and detaches inactive layers during zoom. The user-owned
   Channel 02 z8/playback re-smoke passed, so Phase 1 is closed. Phase 2 is
   implemented with six physically mapped composites under `products-ami2`.
   User-owned acceptance passed for all six products: renders loaded quickly,
   GeoColor Black Marble animation had no flicker or inter-frame blinking, and
   the API terminal and browser console remained error-free. Phase 2 is closed.
   A later Meteosat-12
   Channel 13 North Africa smoke exposed shared Satellite request fanout:
   playback did not await a frame and invisible pooled layers could request
   live tiles, accumulating serialized heavyweight render work. A full-frame
   playback wait was rejected because it defeated pipelined warm-up. The
   current correction keeps normal cadence for warmed frames, waits only for
   the first visible tile on a cold playback advance, detaches inactive Leaflet
   layers, and explicitly live-prefetches a bounded two-ahead/one-behind
   viewport window with two concurrent requests and no redundant server-side
   neighbor fanout. A 2026-07-31 re-smoke exposed a second queue layer before
   Play: synchronous tile routes occupied every AnyIO worker waiting on render
   futures, so completed PNG `FileResponse` bodies could not acquire a worker
   to reach Leaflet. The corrected route reads the PNG before returning;
   Leaflet keeps only a one-tile buffer, UI requests disable redundant neighbor
   fanout, and live prefetch starts only after the current frame has a visible
   tile. The user-owned restart/hard-refresh re-smoke then confirmed that the
   Meteosat current frame and playback tiles generate quickly, but exposed a
   blink between even fully generated frames on both Meteosat-12 Full Disk and
   GOES-19 CONUS. Git history confirmed that the crossfade still existed while
   its old-layer-underneath invariant had been removed: every inactive Leaflet
   layer was detached after each swap, forcing its tile DOM to be rebuilt on
   the next loop. The correction restores the historical retained-mounted-layer
   branch at opacity zero without restoring broad hidden-frame priming. Its
   first re-smoke exposed that retaining an incomplete cold frame let an
   immediate visibility-change catalog refresh enqueue a newer frame alongside
   it, filling the shared render queue and blocking later satellite selections.
   Retention is now limited to layers fully ready at the current zoom, and
   catalog auto-update cannot replace the selected frame until that frame has
   produced a visible tile. Zoom-start cleanup and bounded live prefetch remain.
   JavaScript syntax and 20 focused Satellite tests pass. The user-owned
   two-platform render/no-flash smoke passed. GMGSI Phase 3 is implemented on
   its own hourly `gmgsi/GLOBAL` provider path and `products-gmgsi1` namespace.
   The four direct visible, shortwave IR, water-vapor, and longwave IR products
   pass current NOAA listing/download/nonblank-render proofs. Ruff,
   compilation, JavaScript syntax, and the 63-test focused Satellite gate pass;
   The first user-owned page acceptance rendered the current frame for all four
   products but exposed a one-frame default catalog budget, so animation could
   not start. Global now requests `hours + 1` hourly frames, giving the default
   one-hour view a bounded two-frame loop. A live default-window probe returned
   chronological 19Z and 20Z frames for all four GMGSI products. The corrected
   user-owned re-smoke generated and played a three-hour Channel 13 animation.
   The user accepted this representative shared-path result without separately
   looping Channels 02, 07, and 09; all four current frames had already
   rendered. GMGSI animation acceptance passed and Phase 3 is closed.

### Completed current-dashboard phase — stabilization acceptance

This phase was authorized and completed on 2026-07-31. It added no products and
no Archive UI work.

1. Reconcile the historical pending browser notes against later accepted smoke
   evidence; do not restore the retired Phases 25-27 checklist wholesale.
2. Run focused user-owned browser acceptance only where closure is not explicit:
   the Workspace tabbed legend/map-versus-rail behavior and Projected Arrival
   interactions; Water Region/legend/draggable-detail follow-ups; Tropical
   Live/Archive/System-inspector workflow; and the final GOES GeoColor white-
   point/low-sun/midtone visual check.
3. Run a shallow regression sweep on the remaining standalone routes: load one
   representative current product, change one map/style control, and confirm
   status/legend updates without console errors. Satellite provider acceptance
   is already closed; do not exercise or implement placeholder Archive panels.
4. Convert any observed failure into a page-scoped correction and re-smoke only
   that surface. If the gate passes, record a new accepted current-dashboard
   baseline before selecting backlog or workspace-expansion work.

Shallow regression progress (2026-07-31):

- Surface passed its representative current-data, control, status, and legend
  smoke.
- Alerts passed except that Alerts and Workspace replayed already-active alerts
  as "New Alert" notifications during startup. The shared Alerts engine now
  records its startup time, requires an unseen alert's issuance time to be
  later than that boundary, and retains a session-wide union of seen IDs so
  filtered or viewport refreshes cannot replay earlier alerts. Existing alerts
  still render normally. Cachebusters are `alerts-engine.js?v=20260731b`,
  `alerts-page.js?v=20260731b`, and `workspace-app.js?v=20260731c`. Eight Alerts
  tests, two focused Workspace tests, Ruff, and JavaScript syntax checks pass;
  the user confirmed the startup-notification re-smoke passed on the shared
  Alerts/Workspace path. Two broader Workspace assertions remain stale against
  already-accepted region/watch-control changes and are unrelated. Alerts
  shallow regression acceptance is complete.
- Radar, SPC, RTMA, MRMS, Drought, and WPC each passed the representative
  current-product, map/style-control, status/legend, and no-console-error smoke.

The focused Workspace, Water, Tropical, and GOES GeoColor gates plus the full
shallow standalone-page sweep are complete. This establishes the accepted
current-dashboard baseline as of 2026-07-31. Select any subsequent backlog,
workspace expansion, or Archive work as a separately authorized phase.

Workspace acceptance passed 2026-07-31. The tabbed legend tray and independent
map-versus-national-rail filters passed as implemented. Projected Arrival is now
visible only when both a qualifying alert polygon and radar site are selected;
the alert remains its data source. Alert refresh reconciliation checks both
viewport and nationwide payloads and gives Workspace one missed-refresh grace,
so a transient feed omission cannot clear an active projection. The user drew
an arrival polygon, observed three updates including two new-alert notices, and
confirmed that the selected alert, polygon, tools, and ability to redraw all
remained intact. JavaScript syntax, diff checks, and 15 focused tests pass.
Water post-baseline UI acceptance passed 2026-07-31. Region placement, default
CONUS behavior, map refit/reload, and detail close on region change passed.
The Water legend now separates `River Flood Stage` from `Other Networks` and
tracks River, Coastal, and NDBC network toggles; it hides when all networks are
off. Its river swatches also track the Minimum Flood Stage pills while Coastal
and NDBC remain unaffected. The user confirmed both dynamic legend behaviors
in browser smoke. The draggable station-detail panel passed opening, header
dragging, continued usability, and close behavior through its button, Escape,
Clear, and map navigation. Tropical full-workflow acceptance is in progress.

Tropical Live startup and basin-filter acceptance passed 2026-07-31. Live
defaults to World, and World, ATL, E PAC, and C PAC are independent
single-select views: choosing one replaces the prior selection, and one basin
is always active. Country Borders is now the only border overlay enabled on
Tropical startup; the user confirmed the corrected default. Live System
selection and inspector acceptance passed using an active Eastern Pacific
storm: selection opened the inspector, closing and reopening preserved the
same system, and switching to an out-of-basin view cleared the selection.
Archive workflow acceptance also passed. Entering Archive clears Live storm,
overview, outlook, legend, and inspector state. Advisory requests are
serialized and rapid manual scrub actions coalesce to the latest requested
frame; Best Track remains local and immediately scrubbable. Selecting an
advisory-capable archived storm warms a five-frame server cache window after
the first foreground advisory loads. Pressing Play upgrades the same
deduplicated job to sequential full-storm warming through the shared NHC
provider budget, with atomic advisory publication and visible progress. The
user confirmed manual Advisory and Best Track scrubbing, playback, and both
warm-path corrections. Archive entry now clears the prior Live timestamp;
Advisory frames use normalized NHC issuance time and Best Track frames use each
fix's UTC `DTG`, updating the global timestamp while scrubbing. The user
confirmed both historical timestamp paths. Tropical full-workflow acceptance
is complete.

### Workspace expansion Phase 1 — curated SPC composition

Authorized, implemented, and closed 2026-08-01. The functional browser gate and
final presentation re-smoke both passed.

- SPC is off and collapsed by default. The Workspace exposes only Day 1
  Categorical, Tornado, Wind, and Hail outlooks. Tornado/Wind/Hail selections
  automatically include the applicable CIG significant-threat overlay.
- Active Mesoscale Discussions and active Tornado/Severe Thunderstorm Watches
  can render simultaneously with the selected outlook. Each watch type retains
  the standalone polygon-versus-counties mutual exclusion.
- Workspace-only presentation uses `CAT`, `TOR`, `Wind`, and `Hail` outlook
  pills plus `TOR`/`SVR` watch labels. Fill opacity defaults to `0.5`; stroke
  opacity is fixed at `0.1` with no stroke slider. The SPC legend uses the
  Workspace Radar legend's swatch/card treatment in a five-column flow, and the
  automatic CIG-pairing note lives below the legend entries instead of in the
  controls.
- Days 2-8, Fire Weather, SPC Storm Reports, and SPC Archive behavior are not
  part of this phase. Existing Workspace Local Storm Reports remain unchanged.
- The Workspace reuses the standalone SPC engine, renderer, outlook/impacts
  detail, and MD/watch text-detail behavior. A Workspace-local reusable context
  carousel collects overlapping SPC features at the clicked location, opens
  the clicked feature first, and provides dots, previous/next buttons,
  Left/Right keyboard navigation, and touch swiping. Alert selections and the
  Projected Arrival state remain preserved while an SPC page is visible.
- Focused automated validation passes 43 tests: 15 Workspace tests plus 28
  browser-regression/Alerts/layout tests. JavaScript syntax and diff
  checks pass. The full Workspace file retains its two known stale assertions
  against removed `WORKSPACE_REGION_BOUNDS` and the removed aggregate watch
  pill; those failures are unrelated to Phase 1.
- Functional browser gate passed: SPC initially off, the Day 1 outlook/CIG,
  MD, watch, simultaneous-overlay, detail, and overlap-carousel paths work as
  intended, and disabling SPC preserves Alert/Radar/Projected Arrival behavior.
  The final re-smoke also passed for Workspace-only opacity defaults, shortened
  labels, hidden stroke control, and the Radar-style SPC legend. Phase 1 is
  closed.

### Workspace expansion Phase 2 — curated Satellite composition

Authorized and implemented 2026-08-01. Automated validation and user-owned
browser acceptance pass; Phase 2 closed 2026-08-02.

- Satellite is off and collapsed by default. The Workspace imports the shared
  Satellite engine and animator, never the standalone page controller. The
  explicit pane order is Satellite `330`, SPC `400`, Radar `410`, boundaries
  `420`, and Alerts `430+`.
- The bounded severe-weather set is GOES-19 and GOES-18 plus CONUS, AK, HI,
  and PR region pills. AK/HI/PR use the required Full Disk source internally,
  but Full Disk is not exposed as a Workspace option. PR framing is capped at
  z9. Platform changes clear Region/Product; Region changes clear Product.
- The redundant View dropdown remains removed. Satellite region pills are
  source selectors rather than viewport controls. They preserve the current
  center, zoom, selected alert, and Radar state; the Workspace Region dropdown
  and Home control own deliberate recentering/reset. Products remain a compact
  dropdown: GeoColor, clean IR, water vapor, shortwave IR/fire, and visible.
  Satellite opacity defaults to `0.7`.
- This phase requests bounded one-hour history: up to 12 CONUS frames or six
  Full Disk frames. The existing bottom scrubber is a single Workspace timeline:
  Satellite drives it when Radar has no frames; when both layers have frames,
  Radar is the master clock and Satellite displays the newest scan at or before
  each Radar timestamp. Repeated Satellite frames across faster Radar steps are
  intentional, and a missing prior Satellite frame is never replaced by future
  imagery. The shared animator prefetches adjacent tiles and playback waits for
  the first visible Satellite tile when advancing to a different Satellite scan.
- Transient refresh failures retain the current history. The shared 30-second
  Workspace refresh loop admits Satellite catalog refresh no more than every
  five minutes; live-edge playback advances while a scrubbed historical frame is
  preserved when it remains in the refreshed catalog. Satellite Archive remains
  on the standalone `/satellite` page.
- Region changes and Home reset disable Satellite and clear dependent state.
  Turning the layer off removes imagery and its tabbed legend without changing
  Radar, Alerts, SPC, or Projected Arrival state.
- JavaScript syntax, diff checks, one Node time-join unit, and 36 focused
  Workspace/browser/layout Pytest checks pass when the two documented stale
  Workspace assertions are excluded. Those
  assertions still target removed `WORKSPACE_REGION_BOUNDS` and the removed
  aggregate watch pill and were not changed for Phase 2.
- User-owned browser acceptance passed for default-off controls, platform and
  source-sector selection, hidden Full Disk routing, all curated products,
  one-hour Satellite-only playback, Radar-master time matching, opacity and
  refresh retention, Satellite < SPC < Radar < Alerts stacking, viewport/alert/
  Radar preservation on source-sector changes, and Satellite-off/Region/Home
  cleanup. Phase 2 is closed.

### Workspace expansion Phase 3 — curated RTMA-RU composition

Authorized, implemented, and user-accepted 2026-08-02. Phase 3 is closed.

- RTMA is off and collapsed by default. Workspace composes the shared RTMA
  engine, never the standalone page controller, and fixes the stream to the
  CONUS-only 15-minute Rapid Update analysis. Hourly RTMA, 24-hour change,
  extended lookback, and Archive behavior remain on `/rtma`; a later authorized
  follow-up adds the selected RTMA-RU field to Workspace's rolling hour.
- The compact field control is a two-column, three-row pill grid ordered
  Temperature, Feels Like, Dew Point, Winds, Wind Gust, and Visibility. The
  combined Winds pill loads wind-speed values plus direction barbs. Independent
  Values and Gradient pills can each be enabled or disabled; every new field
  selection defaults to Values on and Gradient off. Marker density and gradient
  opacity remain Workspace-local controls.
- The accepted Phase 3 baseline was latest-only. The separately authorized
  timeline follow-up below supersedes that presentation rule while retaining
  the natural 15-minute refresh cadence and bounded coordinator follow-up.
- Workspace owns separate RTMA panes: Gradient `350` remains below SPC `400`,
  Radar `410`, and boundaries `420`; Values `425` stays above map borders but
  below Alerts `430+`. The shared RTMA engine accepts independent gradient/value
  panes and retains the old gradient image until its replacement loads. It also
  skips the points request when Values is off and a pre-rendered gradient is
  available. Matched Winds speed/direction points now render as one composite
  marker: the direction arrow tail is centered 4-6 px below the value and the
  arrow rotates around that fixed tail to point at the reported bearing.
  Unmatched/standalone direction points retain the prior arrow fallback.
  Standalone RTMA retains its default pane and controls.
- Workspace Region changes reload the selected field for CONUS. AK, HI, and PR
  clear RTMA imagery and report that RTMA-RU is CONUS-only; returning to CONUS
  restores the selected live field. Home reset and the RTMA header switch clear
  RTMA without changing Radar, Alerts, SPC, or Satellite state.
- JavaScript syntax and diff checks pass. Three Node behavior tests cover the
  shared Satellite timeline, RTMA loaded-image pane swap, and Values-only pane
  request path. The focused gate
  passes 57 tests with the two documented stale Workspace assertions excluded.
  Full pytest passes 359 tests plus 42 subtests and fails only those same stale
  assertions against removed `WORKSPACE_REGION_BOUNDS` and aggregate-watch
  markup. User-owned smoke confirmed all six field pills, Values-first loading,
  independent Values/Gradient toggles, split pane order, and the combined Winds
  marker. The accepted Winds arrow begins at the centered bottom of its speed
  value with a small gap and points at the reported direction. Phase 3 is
  closed.
- Cold-start correction 2026-08-03: foreground RTMA Values generation and the
  application-owned latest render had entered cfgrib concurrently even though
  the bundled Windows ecCodes runtime reports thread support disabled. RTMA and
  MRMS now share one process-wide decoder gate; RTMA point/grid output is keyed
  and published through unique temporary files. The reported 1597 x 2345
  RTMA-RU file passes a real concurrent Temperature/Dew Point decode. Shared
  Alerts also performs bounded follow-up reads when a stale response reports
  `refreshing`, eliminating reliance on the next 30-second cycle or manual
  Refresh Active Layers. Radar process children no longer load the Alerts zone
  cache as an import side effect, Py-ART child banners are quiet, SPC uses one
  versioned engine identity, and Workspace declares the tracked favicon. The
  correction gate passes 63 focused Python tests, Alerts/RTMA/MRMS Node
  coverage, JavaScript syntax, native concurrent
  GRIB decode, and diff checks.
- Post-correction runtime evidence 2026-08-03: the user's restart and 15-20
  minute idle `/workspace` soak completed without exceptions, HTTP 4xx/5xx
  responses, ecCodes failures, or unselected Radar/RTMA/MRMS work. Alerts
  refreshed normally with one lazy zone-cache load; Py-ART banners stayed
  suppressed, the favicon returned `200`, and SPC loaded one versioned engine
  module. One Alerts enrichment cycle reached about 16 seconds and recovered;
  monitor it only if the outlier becomes recurrent. This idle soak does not
  satisfy the Phase 4 MRMS interaction gate.

### Workspace expansion Phase 4 — curated MRMS composition

Authorized and implemented 2026-08-02. Automated validation and the user-owned
browser acceptance gate pass; this phase closed on 2026-08-04.

- MRMS is off and collapsed by default. Workspace composes the shared MRMS
  engine, never the standalone page controller, and exposes six fixed CONUS
  products in a two-column pill grid: low-level 30-minute Rotation Track,
  Instant MESH, 30-minute MESH, 30-minute Lightning Probability, Surface
  Precipitation Type, and Base Reflectivity QC. The
  standalone product matrix, extended lookback, and other accumulation windows
  remain on `/mrms`.
- The accepted initial Phase 4 implementation was latest-only. The separately
  authorized timeline follow-up below adds the selected product's rolling hour
  while retaining its natural two-minute cadence, bounded coordinator
  follow-up, and default `0.7` opacity.
- Workspace owns the MRMS overlay pane at `375`, above RTMA Gradient `350` and
  below SPC `400`, Radar `410`, boundaries `420`, RTMA Values `425`, and Alerts
  `430+`. The shared MRMS engine accepts an optional pane without changing the
  standalone default. Replacement imagery must load before the prior image is
  removed; failed or stale requests cannot discard the last loaded overlay.
- MRMS is CONUS-only. AK, HI, and PR clear its imagery and report the
  limitation; returning to CONUS reloads the selected product. Home reset and
  the MRMS header switch clear MRMS without changing Radar, Alerts, SPC,
  Satellite, or RTMA state. MRMS has its own tab in the Workspace legend tray.
- JavaScript syntax and diff checks pass. Four Node behavior tests cover the
  MRMS loaded-image pane swap, RTMA pane/value behavior, and Satellite timeline
  matching. The focused Python gate passes 40 tests with the two documented
  stale Workspace assertions excluded. Full pytest passes 360 tests plus 42
  subtests and fails only those same assertions against removed
  `WORKSPACE_REGION_BOUNDS` and aggregate-watch markup.
- The user confirmed the original four products loaded without errors. Surface
  Precipitation Type was then added through the existing `PrecipFlag` path for
  winter-event composition, followed by Base Reflectivity QC through the
  existing `Refl_BaseQC` path. JavaScript syntax, its Node check, 20 focused
  Workspace tests with the two known stale assertions excluded, and a live
  latest-overlay/PNG probe for each added product pass. User-owned browser
  proof now passes for all six products and their animation. Final user-owned
  acceptance on 2026-08-04 also passed opacity and legend updates, stacking,
  shared-timeline behavior, CONUS-only region behavior, layer-off/Region/Home
  cleanup, auto-refresh retention, and representative standalone `/mrms` and
  `/rtma` load/scrubs. Satellite now uses Workspace pane `405`, above RTMA
  Gradient `350`, MRMS `375`, and SPC `400`, while remaining below Radar `410`,
  boundaries `420`, RTMA Values `425`, and Alerts `430+`.

### MRMS native-detail tile optimization

Authorized, implemented, and browser-accepted 2026-08-04.

- NOAA `noaa-mrms-pds` GRIB2 remains the sole data source. Each freshly decoded
  frame now also writes a versioned, block-compressed native scalar GeoTIFF;
  historical frames build that source on demand from the retained GRIB. Tile
  rendering reads only the requested raster window and uses the same masking
  and palette as the existing overlay renderer.
- `/api/overlay/latest` and `/api/overlay/frames` advertise an additive
  `mrms-v1` tile template and prepare URL. Standard 0.01-degree products use
  native zoom 7; 0.005-degree Rotation Track and Azimuthal Shear use native
  zoom 8. Generated sources and 256-pixel PNG tiles live under the existing
  24-hour `cache/mrms` retention policy.
- The shared `createMrmsEngine()` keeps the 4096-pixel CONUS PNG as the
  immediate, low-zoom, and error fallback. At zoom 7 or higher it prepares the
  selected frame without blocking the loaded PNG, promotes the tile layer only
  after its visible tiles load, and restores the PNG below the threshold or on
  any tile error. This one shared change applies to both `/mrms` and
  `/workspace`, including their historical scrubbers and Workspace pane 375.
- Focused Python tests cover source creation, versioned metadata, native zooms,
  palette parity, tile generation/cache reuse, and PNG metadata retention. Node
  tests cover loaded-image frame swaps, on-demand prepare, tile promotion,
  pane/opacity behavior, low-zoom fallback, and cleanup. A real cached Instant
  MESH GRIB produced its native source in 9.877 seconds and a requested tile in
  0.021 seconds. This is backend/runtime evidence, not browser proof.
- Browser acceptance passed at storm scale and across multiple frames/products
  in both `/mrms` and `/workspace`: PNG-to-tile promotion had no opacity
  stacking or blank flash. Flag-off behavior remains available through
  `MRMS_TILES_ENABLED=0`.
- First standalone browser evidence 2026-08-04: Base Reflectivity changed from
  PNG to tiles at zoom 7 with acceptable speed. Rotation Track tiled 20 frames;
  four more completed source preparation after the scrubber had already moved,
  and one false `21:12:10` frame repeatedly returned 404 because the legacy
  latest path had indexed the GRIB download mtime instead of NOAA's canonical
  `21:12:00` timestamp. The correction now persists canonical source time,
  hides only near-duplicate frames without a retained GRIB/tile source, retains
  successful prepare metadata in the client, and writes history tile sources
  during the existing GRIB decode. The two known false cached entries were
  verified as filtered without deleting cache files. The restarted,
  cache-busted Rotation Track re-smoke passed with canonical timestamps and
  complete tile promotion.

### Workspace shared timeline extension — MRMS + RTMA-RU

Authorized and implemented 2026-08-03. Automated validation and user-owned
browser acceptance pass; this follow-up closed on 2026-08-04.

- The existing bottom scrubber now selects its clock source in the stable order
  Radar, MRMS, Satellite, then RTMA. Radar therefore remains master whenever it
  has frames; without Radar, two-minute MRMS takes precedence over Satellite,
  and 15-minute RTMA-RU is the final fallback.
- Every non-master time layer displays only its newest frame at or before the
  master time. No future MRMS, Satellite, or RTMA analysis is borrowed. Repeated
  slower-source frames are intentional.
- Workspace requests only the selected MRMS product and selected RTMA-RU field
  for a rolling one-hour window through the existing `/api/overlay/frames`
  coordinator path. Empty/partial histories fill progressively, poll at five
  seconds while pending, append by stable frame identity, and retain a scrubbed
  position while live-edge users follow new frames. No product-family preload
  or Task Scheduler dependency was added.
- MRMS uses the shared engine's existing image-load-before-swap and two-frame
  prefetch behavior. RTMA historical rendering keeps Values and Gradient modes
  synchronized with the selected frame and never reveals a disabled gradient.
  Winds joins direction only when its source key or timestamp exactly matches
  the historical wind-speed analysis; a missing pair clears direction rather
  than mixing analysis times.
- Product, layer, Home, and region changes cancel the old client generation,
  clear its frame registry, and reject stale results. A bounded coordinator job
  already accepted by the backend may finish and populate cache. Standalone
  `/mrms` and `/rtma` retain their own controls, lookback choices, and scrubber
  workflows.
- RTMA follower history also retains one hidden predecessor analysis before the
  visible one-hour boundary. The API accepts whole-hour lookbacks, so Workspace
  requests a bounded two-hour selected-field source window, discards all but
  the newest pre-window frame, and exposes only the normal one-hour frames to
  the scrubber. Strict at-or-before matching can therefore render the prior
  analysis at the first master step instead of leaving RTMA blank until its
  next observation. Historical wind direction uses the same anchor rule.
- JavaScript syntax passes for the six affected modules. Six focused Node
  tests plus the Satellite timeline script pass. The focused Python gate passes
  45 tests with the two documented stale Workspace assertions excluded. Live
  `/api/overlay/frames` probes returned chronological progressive histories for
  MRMS Base Reflectivity QC (21 frames) and RTMA-RU Temperature (three frames);
  this is API/runtime evidence, not browser proof. After the predecessor
  correction, a live two-hour RTMA-RU request completed with seven chronological
  frames from 19:45 through 21:15 local and `refreshing=false`.
- User-owned browser acceptance passed for each layer alone, Radar-master
  four-layer matching, MRMS-master behavior without Radar, RTMA repeated-frame
  behavior, Values/Gradient and historical Winds, live-edge versus scrubbed
  refresh, product-switch cancellation, and layer-off/Region/Home cleanup.

### Workspace expansion Phase 5 — curated WPC composition

Authorized, implemented, committed at `1180b74`, and user-accepted 2026-08-04.
The initial browser gate and the requested selection-control follow-up re-smoke
passed. Phase 5 is closed without changing the standalone WPC behavior.

- WPC is off and collapsed by default. Workspace imports the shared
  `createWpcEngine()` through `workspace-wpc.js`, never the standalone page
  controller. The curated families are Excessive Rainfall Outlooks Days 1-3,
  multi-day QPF Days 1-2/1-3/1-5/1-7, active Mesoscale Precipitation
  Discussions, and the existing Days 1-3 winter snow/ice catalog. River Flood,
  6-hour/24-hour QPF, Significant Weather, Surface Analysis/Forecast, and future
  WPC increments remain standalone-only.
- Family pills are navigation-only and mutually exclusive. ERO Days 1-3 and
  the four multi-day QPF periods use mutually exclusive product pills. Selecting
  MPD immediately loads the active discussions/polygons. Winter first exposes
  mutually exclusive Days 1-3 pills, then limits its single product dropdown to
  that day. Every family/day/product change clears the prior WPC overlay, so no
  two WPC products can remain selected together. The catalog loads lazily only
  after WPC is enabled; disabled WPC performs no catalog/product work. The
  selected product refreshes on WPC's natural 30-minute cadence and does not
  join the Radar/MRMS/Satellite/RTMA shared timeline.
- WPC is CONUS-only in Workspace. AK/HI/PR clear it and show the limitation;
  returning to CONUS reloads the selected product. Layer-off, Region, and Home
  clear WPC without changing the other composed layers. Standalone `/wpc`
  retains its complete product matrix, controls, and scrubber behavior.
- The shared WPC engine accepts an optional pane for both image and GeoJSON
  overlays. Workspace uses pane `390`, below SPC `400`, Satellite `405`, Radar
  `410`, boundaries `420`, RTMA Values `425`, and Alerts `440+`; WPC therefore
  cannot obscure the user-specified Radar, Satellite, or Alert layers. The
  standalone engine retains the default Leaflet overlay pane.
- WPC has its own Workspace legend tab, opacity defaults to `0.55`, and WPC
  forecast/detail clicks reuse the Workspace detail panel with WPC-specific
  labeling. Focused Workspace/WPC tests and JavaScript syntax pass. The initial
  browser acceptance passed all listed functional/stacking/lifecycle checks.
  Post-refinement focused tests, syntax checks, and controlled-browser runtime
  checks pass. The user re-smoke also passed exclusive ERO/QPF pills, automatic
  MPD loading, Winter day filtering, and single-selection/single-overlay behavior.
  Phase 5 is closed.

### Workspace expansion Phase 6 — Water composition

Authorized and implemented 2026-08-04. The initial user-owned browser gate and
the requested Workspace-only control-refinement re-smoke passed. Phase 6 is
user-accepted and closed. Standalone `/water` behavior remains unchanged.

- Water is off and collapsed by default. Enabling it loads all three existing
  observation networks—River, Coastal, and NDBC Buoys—against the current map
  viewport. Workspace exposes three independent `RIVER | COAST | BUOY` pills,
  and no network is queried while all three are off. The Workspace Minimum
  Flood Stage control and its wiring are removed; standalone `/water` retains
  its checkbox network controls and complete flood-stage filter behavior.
- Water network pills use `aria-pressed` as the selection source of truth;
  pressed pills receive the bright active treatment and unpressed pills remain
  dark/muted. A controlled-browser state/style check passes this correction.
- The Water legend updates from the selected Workspace network pills and
  occupies its own Workspace legend tab.
- `frontend/pages/water/water-engine.js` now owns station requests, provider
  retry hints, filtering, marker rendering, legend content, and River/Coastal/
  NDBC detail rendering. Standalone `water-app.js` and Workspace
  `workspace-water.js` are thin controllers over that shared engine; neither
  imports the other page controller.
- Water is latest-only and does not join the Radar/MRMS/Satellite/RTMA shared
  timeline. Workspace auto-refresh is throttled to five minutes, while viewport
  changes and server retry hints retain the accepted bounded reload behavior.
- Workspace uses marker pane `470`. Station clicks open the existing draggable
  Water detail treatment and close competing Alert/LSR/SPC/WPC detail. Layer
  off, Region changes, and Home clear markers, legend, pending detail, and stale
  requests without disturbing other composed layers.
- JavaScript syntax passes for the four affected modules. The Water engine Node
  behavior check passes. Focused Python validation passes 31 Workspace/
  standalone checks with the two documented stale Workspace assertions
  deselected, plus 21 Water worker/browser-regression checks. `git diff --check`
  passes. The corrected active/inactive pill treatment passed a controlled-
  browser check, 32 Water-focused tests, and the final user-owned re-smoke.
- Workspace-wide disclosure follow-up: every layer group with an enable switch
  now stays collapsed while that switch is off, opens when switched on, and
  closes when switched off. The shared guard changes disclosure only; existing
  product enable/disable handlers remain authoritative. Projected Arrival keeps
  its separate selection-driven visibility. JavaScript syntax, 31 focused
  Workspace/browser-regression tests, diff checks, and controlled-browser Water
  and Radar lifecycle checks pass. The focused user re-smoke passed.

## Current State

- Active repo: `F:\Python\dashboard_2026`.
- Worker-free Phase 0 is complete: the shared credential-safe JSONL
  request ledger covers application-owned HTTP and NODD S3 paths, and the six
  required isolated cold renders are recorded in
  `docs/perf/2026-07-23-worker-free-phase0/`. Alerts no longer reads or writes
  the 322 MB enriched-geometry disk cache; its bounded process-local LRU reduced
  warm enrichment to 0.024 seconds and peak RSS to 1.022 GB. A bounded
  processed-feature LRU now reuses enriched and simplified per-alert
  serialization while retrying unresolved geometry. The remediation warm pass
  reused 471/471 alerts, took 0.504 seconds total and 0.082 seconds after the
  NWS response, and passed the unchanged near-one-second continuation gate.
  That authorized the now-complete Phase 1. No browser proof was performed.
- Worker-free Phase 1 is complete: `app_core/refresh_coordinator.py` owns a
  bounded executor/queue, actual-key deduplication, provider concurrency and
  minimum intervals, 90-second request leases, exponential backoff, status
  snapshots, periodic pruning, and graceful shutdown through FastAPI lifespan.
  Surface cold/stale observations and stale WPC refreshes use it instead of
  daemon threads. One region-level Surface job fetches observations once and
  publishes every product JSON through the shared atomic writer; its client
  retries cold warming. Presence-only records report `idle`. Coordinator-owned
  cache cleanup runs every six hours without page presence.
  `/api/health/coordinator` reports safe state.
  The supported configuration is one application process until persistent
  leases exist; legacy direct-write tasks are not compatible. The focused Phase
  1 gate and the full 135-test plus 42-subtest suite pass. Browser inspection
  found and drove the Surface-key and presence-state corrections, and browser
  re-verification confirmed both. Browser re-smoke also confirmed masked
  gradients for every Surface product; the roughly five-second first Altimeter
  load was accepted as cosmetic. Compact evidence is in
  `docs/perf/2026-07-23-worker-free-phase1/`.
- Worker-free Phase 2 is complete: Alerts uses its bounded processed-feature
  LRU as the new/changed-ID boundary, marks geometry provenance, preserves all
  native NWS polygons, and simplifies only zone/SAME-derived geometry below
  zoom 8. Low zoom reads one national low-detail payload; zoom 8+ uses
  bbox-filtered full geometry. Stale reads submit one coordinator job under a
  35-second `nws-alerts` floor, cold missing cache reports warming/backoff, and
  full/low/compatibility artifacts publish behind one atomic generation
  manifest. The full suite passes 145 tests plus 42 subtests. A live 489-alert
  generation kept 36 native geometries byte-equivalent and simplified all 453
  derived geometries for a 94.54% vertex reduction; a forced network-failure
  run preserved the prior generation. The operator then disabled the scheduled
  workers and restarted port 8000. API verification returned 489 fresh
  national low-detail features and 25 fresh bbox-filtered full features from
  the same generation. Browser proof remains pending. Evidence is in
  `docs/perf/2026-07-23-worker-free-phase2/`.
- Worker-free Phase 4 is complete: selected MRMS products use explicit
  coordinator/discovery/download/render/catalog keys with a two-minute
  success interval, unchanged source keys skip object download and rendering,
  and request paths no longer prewarm unrelated products. RTMA uses an hourly
  success interval with a two-hour latest-source discovery window while
  preserving its direct latest and progressive-history paths. MRMS, RTMA,
  live Radar, and on-demand Satellite tile rendering share one process-wide
  heavy-render slot by default. The corrected Phase 4/coordinator suite passes
  19/19. Isolated runtime
  validation rendered only selected `PrecipRate` plus one 17Z RTMA hourly
  frame; immediate repeats returned `current` with about 107 and 3,590 seconds
  remaining. The first user browser smoke found partial MRMS/RTMA lookbacks and
  an RTMA-RU page that stopped polling after the empty first response. History
  fills are now horizon-specific, MRMS fills missing NODD objects, RTMA selects
  the newest end of discovery, RTMA-RU uses a 15-minute cadence, and both pages
  poll/merge progressive frames chronologically. The complete suite reaches
  176 passing tests plus 42 subtests; the one failure is an unrelated stale
  Workspace assertion against concurrent user-owned `fitRegion` edits. The
  corrected browser re-smoke passed for MRMS, RTMA Hourly, and RTMA-RU with no
  other issues found, closing Phase 4. Evidence is in
  `docs/perf/2026-07-23-worker-free-phase4/`.
- Worker-free Phase 5 is implemented: a missing or older-than-30-minute Water
  station index submits one coordinator rebuild while missing responses report
  warming and stale responses retain the prior complete index. The client
  retries from `retry_after_seconds`; the shared worker fetches NWPS, CO-OPS,
  and NDBC once per rebuild before atomic publication. NWPS/CO-OPS detail calls
  are serialized per provider and share a five-minute, 512-entry LRU with
  bounded backoff. The first browser smoke showed no river markers because a
  partial rebuild had published zero river stations. Publication now rejects
  missing or greater-than-50% reduced required networks while retaining the
  prior index; the request path also treats fresh-but-incomplete indexes as
  rebuild-worthy and returns retry timing. The optional unavailable CO-OPS
  Current layer remains skippable. A corrected live rebuild published 12,761
  river, 301 coastal, and 894 NDBC stations, and the CONUS API returned 12,162
  river stations from a fresh generation. The focused Phase 5 tests pass 10/10
  and the combined Water run passes 18/18. The corrected user-owned browser
  re-smoke passed on 2026-07-23, closing Phase 5 and authorizing Phase 6.
  Evidence is in
  `docs/perf/2026-07-23-worker-free-phase5/`.
- Worker-free Phase 6 is complete: the Surface-gradient endpoint now returns
  explicit fresh/stale/warming state, preserves the prior complete image during
  work, and submits only the requested region/product key. Observations share
  one process snapshot per region/minute; station metadata is cached daily and
  IEM fallback traffic uses the shared provider budget. Gradient work uses its
  own bounded render slot and the client polls until the requested image is
  ready. The Phase 6 suite passes 24/24, including all 18 product/region paths
  on isolated reduced scratch grids; broader Surface/coordinator tests pass
  37/37. The first user-owned browser smoke found no product failures and
  recorded a representative 4.2-second, 2,246-point CONUS render. It exposed
  the unmasked client-canvas fallback while the baked-mask PNG was pending.
  That fallback is now suppressed during warming: stale-while-refresh adopts
  the prior masked PNG immediately, while a truly cold request shows
  observations alone. Correction-focused validation passes 46/46. Full pytest
  reaches 214 passing tests plus 42 subtests; only the pre-existing Workspace
  assertion against concurrently removed `WORKSPACE_REGION_BOUNDS` fails.
  The corrected user-owned browser re-smoke passed for every CONUS and WORLD
  product on 2026-07-24. Phase 6 is closed and Phase 7 is authorized next.
  Evidence is in `docs/perf/2026-07-23-worker-free-phase6/`.
- Worker-free Phase 7 is closed after corrected user-owned browser/live-provider
  re-smokes. The coordinator can retain a recurring selected-product
  job only while its 90-second presence lease is active. Radar keys include
  site, level, product, elevation, and storm-motion variant; newest-first
  fallback remains synchronous, history fills progressively, responses expose
  `history_filling`, and Level 2 chunk-prefix discovery is cached for 30
  seconds. Satellite retains on-demand tiles as the first-view path and delays
  selected rapid-sector/Meteosat acceleration by five seconds. Source downloads
  deduplicate per platform/sector/frame; EUMETSAT FCI downloads are limited to
  one or two; missing credentials and licence access report explicit capability
  states. The focused gate passes 53 tests plus 42 subtests; full pytest passes
  222 tests plus 42 subtests and retains only the pre-existing Workspace
  assertion against the concurrently removed `WORKSPACE_REGION_BOUNDS`. Evidence is in
  `docs/perf/2026-07-24-worker-free-phase7/`.
- Worker-free Phase 8 is closed after whole-system/browser and optional-warmer
  enabled/disabled acceptance.
  `workers/scheduler.py` registers no broad jobs, startup health no longer reads
  scheduled-task sentinels, and `/api/health/coordinator` reports
  application-owned source/cache/coordinator plus maintenance state. Tropical
  current-season archive refresh remains request-driven and six-hour cleanup
  remains lifecycle-owned. `tools/install_tasks.ps1` defaults to a non-mutating
  preview; its bounded optional `core` and `surface` profiles call the running
  localhost API and expose standardized warmer outcomes. The real preview found
  13 legacy tasks, all disabled, and changed none. Phase 8 focused tests pass
  6/6; combined cutover/lifecycle/schedule tests pass 18/18. Full pytest reaches
  240 passing tests plus 42 subtests and retains only the pre-existing Workspace
  assertion against the concurrently removed `WORKSPACE_REGION_BOUNDS`.
  A temporary port-8011 runtime probe returned healthy application-owned state,
  a running single-process coordinator, registered cleanup, and no task-health
  field. The first user-owned zero-task/browser smoke found three follow-up
  defects. WPC now versions unchanged image paths with the payload update token
  so a new timestamp cannot retain yesterday's browser-cached chart. MRMS opens
  at the newest frame and follows the newest frame while progressive history
  fills. Satellite explicitly orders catalogs oldest-to-newest, displays the
  final/newest frame before neighbor priming, and replaces the aggregate
  cached-tile count with a clear visible-tile cache-or-render-on-demand message.
  A separate second global-timestamp line now reports Loading, Fresh, Stale, or
  Ready state while preserving every existing page message element. The
  correction suite passed 39/39 plus syntax/compile/lint/diff checks. A local
  in-app browser re-smoke confirmed WPC's versioned image URL, MRMS at 28/28
  with its scrubber at maximum, and Meteosat-12 Channel 13 requesting the
  02:00Z newest frame before 01:45Z. The next user-owned re-smoke passed WPC
  chart/timestamp parity and newest-first MRMS/Satellite behavior, with no other
  product errors. It exposed Channel 14 being present in the UI but absent from
  the backend product registry and timestamp state appearing only on the three
  corrected pages. Channel 14 is now registered for all supported provider
  mappings. Every standalone page receives the shared Loading/Ready state, and
  SPC/Surface also publish their computed stale state. Satellite Ready is now
  driven only by a successful tile-load event for the active frame. The
  expanded correction suite passes 42/42 plus 16 Node syntax checks and Python
  compilation. Browser proof held Loading at 0/40 rendered Satellite tiles,
  changed to Ready at 23/40, and showed Ready on Drought. A fresh temporary
  server accepted Channel 14 legend/catalog validation before the sandbox's
  unavailable outbound NOAA S3 access stopped discovery. The continuing
  user-owned re-smoke now passes Surface, Satellite, Alerts, MRMS, Drought, WPC,
  and Water. RTMA passes the `Stale` to `Ready` state transition; its observed
  cold fresh-data load took about 60-75 seconds, consistent with source
  download/render and possible shared heavy-render-slot queueing. Repeated RTMA
  testing exposed the latest refresh and request render concurrently downloading
  the same GRIB through one fixed `.part` path. GRIB acquisition is now
  serialized per destination and rechecks the completed cache after waiting;
  the focused Phase 4 suite passes 11/11 plus Ruff and compilation. The
  corrected RTMA user re-smoke passed without the collision recurring, and
  Radar also passes. Leaving MRMS stopped page polling while the
  already-submitted bounded selected-product history batch finished, which is
  expected; it must not launch new batches after departure. SPC also passes.
  Workspace also passes. Tropical initial refresh exposed a missing
  `setTimeoutFn` dependency in the engine context; the dependency is now wired
  and the focused Tropical/browser gate passes 23/23 plus Node syntax and Ruff.
  The corrected Tropical user re-smoke passes, completing the user-owned
  whole-system browser smoke. The installed `core` and `surface` optional
  warmers then passed enabled API-delegating runs. With both disabled, their
  logs did not advance across the Core five-minute interval, coordinator health
  remained application-owned, and Surface, Alerts, Radar, SPC, Tropical, and
  Water remained browser-functional. The final SPC correction replaced a
  universal 90-minute stale rule with issuance-aware API state and displays the
  outlook issue time. Surface now honors coordinator retry timing rather than
  downloading its full observation payload every second during backoff. The
  user's corrected re-smoke passed SPC Days 1-5 and showed bounded Surface
  polling. Focused post-correction validation passes 42 tests plus JavaScript
  syntax and diff checks. No legacy-task unregistration was performed. Phase 8
  is closed.
- Post-closure optional-warmer extension: separate `rtma` and `mrms` profiles
  now target CONUS Hourly/Rapid Update Temperature latest frames and the
  PrecipRate, LL 60-minute Rotation Track, and Instant MESH MRMS keys. Both
  tasks were registered disabled. Keep every optional warmer disabled during
  Radar Phase 0 benchmark capture; RTMA/MRMS share heavyweight render capacity
  with Radar/Satellite.
- Radar render optimization Phase 0 is complete and behavior-neutral.
  `python -m radar.bench` writes raw evidence only below
  `cache/radar/.bench/<run_id>/`; compact evidence is in
  `docs/perf/2026-07-25-radar-baseline/`. All eight required golden rows passed
  five byte-identical fresh-process renders. The current KGSP L3 N0B
  three-frame empty-cache response measured 3.804/4.114 seconds p50/p95 versus
  2.194/2.208 seconds for `render-one`; 12-frame backfill measured
  8.230/8.352 seconds and about 2.52 GiB p95 peak working set. The focused
  Radar gate passes 36 tests plus 42 subtests. Full pytest passes 261 tests plus
  42 subtests and retains only the pre-existing Workspace assertion against the
  removed `WORKSPACE_REGION_BOUNDS`. Ruff, Python compilation, and diff checks
  pass. That baseline approved Phase 1. Later candidates remain process-pool
  reuse, Level II source/decode deduplication, discovery/finalize I/O, and
  optional renderer internals.
- Radar render optimization Phase 1 is implemented. Empty `/frames` requests
  render exactly one newest frame synchronously, then the existing keyed
  background path fills the remaining initial/history frames.
  `OVERLAY_EMPTY_CACHE_SYNC_FRAMES` remains `3`. KGSP L3 N0B improved from
  3.804/4.114 seconds p50/p95 to 2.012/2.017 seconds, a 47.1%/51.0%
  reduction. All eight Phase 0 golden comparisons pass. The focused Radar gate
  passes 38 tests plus 42 subtests; full pytest passes 263 tests plus 42
  subtests and retains only the pre-existing Workspace assertion against
  removed `WORKSPACE_REGION_BOUNDS`. Evidence is in
  `docs/perf/2026-07-25-radar-phase1/`. Three-site user-owned browser acceptance
  passed: the scrubber stayed on newest while history grew and playback
  remained continuous through the completed roughly 14-16-frame loops.
- Radar render optimization Phase 2 is implemented. Scheduled runs share one
  lazily started bounded render pool across site/product batches; a selected
  product background run owns one pool for its batch. The response-critical
  single-frame path starts no multiprocessing workers. Normal completion
  closes/joins the pool and exceptional completion terminates/joins it.
  `LIVE_RADAR_PARALLEL_WORKERS` remains unchanged. KGSP L3 N0B retained-pool
  `backfill-12` measured 7.989/8.271 seconds p50/p95 versus 8.230/8.352
  seconds in Phase 0, a 2.9%/1.0% reduction, with about 2.50 GiB p95 peak
  working set. Every sample created one four-process pool; pool construction
  and readiness/import were recorded separately. All eight golden rows pass.
  The focused gate passes 49 tests plus 42 subtests; full pytest passes 268
  tests plus 42 subtests with only the pre-existing Workspace assertion.
  Evidence is in `docs/perf/2026-07-25-radar-phase2/`. User-owned browser
  acceptance passed on both `/radar` and `/workspace`: KGGW and KTFX newest
  frames preceded their eight- and ten-frame four-process background fills,
  the scrubber stayed on newest, playback remained continuous, frame/PNG
  requests returned HTTP 200, and no pool/render/Radar API errors appeared.
  Phase 2 is closed.
- Radar render optimization Phase 3 is implemented. Flat Level II volumes use
  one site-owned `_VOLUME` spool, and scheduled product batches render all
  seven configured products from one Py-ART decode while preserving independent
  caches, sweeps, palettes, units, failure handling, and SRV motion variants.
  Five fresh-process samples improved all-product wall p50/p95 by 37.1%/37.6%;
  all eight goldens and the shared-batch REF/VEL/SRV/ZDR hashes pass. Evidence
  is in `docs/perf/2026-07-26-radar-phase3/`. The focused gate passes 56 tests
  plus 42 subtests; full pytest passes 275 tests plus 42 subtests with only the
  pre-existing Workspace assertion. No frontend behavior changed, so browser
  proof was not required or claimed. Phase 3 is closed.
- Radar render optimization Phase 4 is implemented. Unchanged directories reuse
  persisted validated discovery lists, and all render paths atomically publish
  same-volume temporary PNGs while preserving failure cleanup and immediate
  visibility. No-op p50/p95 improved 10.6%/11.9%, backfill-12 improved
  5.2%/6.8% over Phase 2, and eight-row median finalization fell 87.6%. All
  eight goldens pass; focused validation passes 63 tests plus 42 subtests and
  full pytest passes 282 tests plus 42 subtests with only the pre-existing
  Workspace assertion. Evidence is in
  `docs/perf/2026-07-26-radar-phase4/`. Phase 4 is closed without a browser
  smoke because no frontend behavior changed.
- Radar render optimization Phase 5 is implemented. Same-volume Level II
  products selecting the same sweep reuse one Matplotlib QuadMesh while
  retaining exact geometry, projection, bounds, DPI, masked data semantics,
  palettes, and limits. The cache is bounded to one decoded-volume consumer
  call and closes before return. Five fresh-process KGSP samples improved the
  seven-product batch from 16.522/16.558 seconds p50/p95 to 11.814/11.995
  seconds, a 28.5%/27.6% reduction; p95 peak working set fell 13.4% to
  1,609.20 MiB. All 35 batch outputs and all eight permanent golden rows pass
  byte-identically. Evidence is in `docs/perf/2026-07-26-radar-phase5/`.
  Focused validation passes 64 tests plus 42 subtests; full pytest passes 283
  tests plus 42 subtests with only the pre-existing Workspace assertion. No
  frontend or API behavior changed, so browser proof was not required or
  claimed. Phase 5 is closed.
- Radar render optimization Phase 6 is implemented behind the default-off
  `LIVE_RADAR_WEBGL_ENABLED` switch. A separate `v1` L2 Reflectivity artifact
  is emitted from the existing decoded sweep and served only while enabled.
  The shared client stays PNG-only below zoom 10, prefetches/uploads the active
  paused frame at zoom 10, and activates its one WebGL texture at zoom 11 only
  after readiness. Playback, failure, context loss, selection changes, and
  threshold reversal restore PNG immediately.
- The representative 720-by-1,832 KGGW artifact is 1,322,700 bytes with zero
  gate-value quantization error. Five-run control/candidate total p50/p95 is
  4,034.155/4,174.683 ms versus 4,045.126/4,106.774 ms; all ten PNGs and all
  eight permanent golden rows remain byte-identical. Focused validation passes
  69 tests plus 42 subtests. Evidence is in
  `docs/perf/2026-07-26-radar-phase6/`.
- User-owned Phase 6 checks pass on `/radar` and `/workspace` for zoom-11+
  activation, a 0.100 ms cached draw, same-frame visible shader parity, and
  PNG-only behavior with the switch disabled. Native WebGL bins correctly
  follow the radial scan; enlarged legacy PNG pixels remain screen-axis
  aligned, and no constant overlay displacement was found. Active-playback and
  context-loss fallback passed. A throttled KBYX-to-KAMX selection change
  canceled the stale fetches without the KBYX overlay reappearing. Phase 6 is
  closed.
- Radar render optimization Phase 7 is implemented behind the separate
  default-off `LIVE_RADAR_WEBGL_ANIMATION_ENABLED` switch. It retains current,
  two upcoming, and one prior L2 Reflectivity texture, bounded to about
  5.04 MiB for four representative R8 textures, with at most two artifact
  fetches in flight. PNG playback remains immediate and authoritative; WebGL
  activates only after the active and two forward textures are ready.
- Focused validation passes 70 tests plus 42 subtests, three JavaScript window
  tests pass, and all eight permanent PNG goldens pass. Full pytest passes 292
  tests plus 42 subtests with only the pre-existing Workspace assertion.
  Evidence is in `docs/perf/2026-07-26-radar-phase7/`.
- Codex in-app browser acceptance passes on both pages for bounded animation,
  zoom-threshold fallback/release, buffered activation, Workspace continuity
  across auto-refresh, and KAMX-to-KBYX stale-window cancellation. Phase 7 is
  closed.
- Radar render optimization Phase 8's first family is implemented for
  `L2_VEL` and `L2_SRV` behind separate default-off activation and animation
  switches. Artifact `v2` keeps Reflectivity's one-byte encoding and adds
  two-byte Velocity/SRV codes, 512 palette entries, product identity, and
  normalized SRV motion-variant isolation. The four-texture window is about
  10.08 MiB and retains the two-load concurrency limit.
- Five fresh-process first-PNG regressions remain below the 5% ceiling:
  Velocity is +2.84%/+1.24% p50/p95 and SRV is +3.35%/+3.75%.
  Current-source control/candidate PNG hashes are byte-identical. Focused
  validation passes 79 tests plus 42 subtests, four JavaScript tests pass, and
  full pytest passes 303 tests plus 42 subtests with only the known stale
  Workspace assertion.
- Codex in-app browser acceptance passes on `/radar` and `/workspace` for both
  products, four-texture playback, Velocity-to-SRV stale-work cancellation,
  and flag-off PNG-only playback. The restored permanent Phase 0 inputs pass
  all eight PNG golden rows, so this family is closed. Evidence is in
  `docs/perf/2026-07-29-radar-phase8-velocity/`.
- Radar render optimization Phase 8's second core family is implemented for
  `L3_N0B` and `L3_N0G` behind separate default-off activation and animation
  switches. N0B uses the exact one-byte reflectivity encoding; N0G uses the
  two-byte velocity encoding and 512-entry palette. Representative
  four-texture windows are 5.07 MiB and 6.61 MiB.
- Five fresh-process first-PNG regressions remain below the 5% ceiling: N0B is
  -1.71%/-7.00% p50/p95 and N0G is +1.29%/+2.26%. Control/candidate PNG hashes
  are byte-identical. Focused validation passes 85 tests plus 42 subtests,
  five JavaScript tests pass, and all eight permanent PNG goldens pass. Full
  pytest passes 310 tests plus 42 subtests with only two pre-existing
  Workspace assertion failures.
- Codex in-app browser acceptance passes on `/radar` and `/workspace` for both
  products, four-texture playback, N0B-to-N0G stale-work cancellation, and
  family-flag-off PNG-only playback. Evidence is in
  `docs/perf/2026-07-29-radar-phase8-level3/`. Both core-product families and
  Radar render optimization Phase 8 are closed.
- DONE 2026-07-29: The post-Phase 8 live-freshness correction restores the
  documented meaning of `/api/radar/live/frames?refresh=true` without coupling
  newest-frame discovery to history backfill. Active selections use a separate
  keyed latest-only job at a 60-second cadence with a 180-second presence lease;
  it probes/renders at most one newest unprocessed source while incomplete
  lookbacks retain their bounded five-minute/12-frame history path.
- Latest-mode NODD listings use an isolated 30-second cache; archive/history
  listings retain 120 seconds. Workspace and Radar keep their 30/90-second UI
  cadences. A queued latest refresh triggers bounded three-second manifest
  polling for at most 60 seconds, preserves the active frame identity and
  playback state, and exposes `latest_refreshing` separately from
  `history_filling`. Manual Refresh uses the same path. The operational target
  is no more than roughly two minutes from S3 publication to an active
  scrubber. Focused validation passes 38 tests plus 42 subtests and six
  JavaScript tests; full pytest passes 315 tests plus 42 subtests with only the
  two documented stale Workspace assertions. A read-only live KSFX/N0B probe
  returned the current `SFX_N0B_2026_07_30_00_21_02` key in 0.25 seconds.
  User-owned browser acceptance then passed with sooner updates for both Level
  II and Level III across two different radar sites, satisfying the remaining
  arrival-timing gate and closing the freshness correction.
- The post-Phase 2 high-zoom investigation found that the representative KGGW
  L2 sweep retains 720 radials, 1,832 gates, 250-meter range spacing, and about
  0.486-degree azimuth spacing, while its 4,380-by-4,400 full-site PNG spans
  roughly 1,110 km. At Leaflet zoom 11, each PNG pixel is enlarged to about
  five screen pixels. Increasing full-site DPI is rejected because matching
  zoom 11 would require roughly a 22,000-pixel-square image and about 25 times
  the current pixel workload.
- The approved implementation keeps Phases 3-5 PNG-only. Phase 3 established
  the bounded decoded-volume consumer seam without adding a second Py-ART
  decode, and Phase 5 reuses same-sweep renderer geometry inside that seam.
  Phase 6 now emits its separate feature-gated artifact from that seam for
  active, paused L2 Reflectivity. Below zoom 10 the client remains PNG-only;
  zoom 10 keeps PNG visible while prefetching one texture; zoom 11 activates
  WebGL only when ready. Phase 7 extends that path to a bounded current,
  one-prior, two-upcoming animation window while PNG continues as the complete
  loop and per-frame fallback. Phase 8 may expand only to explicitly approved
  core product families. All-product WebGL conversion, tiles, and PNG
  retirement remain outside the plan.
- Satellite optimization Phase 0 was committed at `a6f5f83`; Phase 1 was
  committed at `fc534ba`: NetCDF LRU correctness, cheap PNG hit validation, and a
  geometry-aware composite meshgrid gate. The full 81-tile golden comparison
  passed, while hit validation improved from 1.349–2.603 ms to 0.051–0.067 ms
  p50. Results live under `docs/perf/2026-07-22-phase1/`.
- Phase 2 is complete locally: a proposed single canvas failed pixel identity
  and was discarded; the safe fallback returns the requested tile before
  asynchronously warming byte-stable neighbors with in-flight deduplication.
  All 81 goldens passed and headline cold p50 improved 11.9–14.9%. Results live
  under `docs/perf/2026-07-22-phase2/`; committed at `8ee3a4b`.
- Phase 3 is committed at `29b83b6`: FCI multi-channel chunk parsing and four-worker
  AHI segment decoding passed the full 81-tile golden matrix. AHI improved
  49.6% from Phase 2 and FCI Nighttime Microphysics improved 43.2%. Results
  live under `docs/perf/2026-07-22-phase3/`.
- Phase 4 is committed at `39de302`: the approved 4096 MB byte-budgeted shared
  `SourceRaster` LRU passed all 81 goldens. Channel13 followed by FCI Nighttime
  Microphysics reused Channel13 without reparsing and reduced unique grid
  weight from 473.062 MB to 354.797 MB. Results live under
  `docs/perf/2026-07-22-phase4/`.
- Phase 5 is committed at `168510f`: the rapid worker owns one process pool per run,
  and no-op jobs skip their trailing catalog rebuild. The pinned two-zoom MESO
  probe improved from 3514.710 ms to 832.513 ms steady p50 (76.3%); task-per-
  zoom parallelism remains. Results live under
  `docs/perf/2026-07-22-phase5/`.
- Phase 0 delivered env-gated
  timing hooks, safe benchmark CLI, nine-row/three-scenario baseline, manifests,
  summaries, and 81 byte-identical golden-tile checks. Baseline artifacts live
  under `docs/perf/2026-07-22-baseline/`.
- The 2026-07-20 consolidated manual smoke is complete. Its correction set is
  implemented and awaits user browser re-smoke. Shared changes: State + County
  borders default on while Country + graticule default off; status cards omit
  Source; pointer-click focus boxes are suppressed while keyboard focus remains;
  categorical legend swatches are compact squares; data-selection pills use an
  amber active state while sidebar navigation remains cyan; and every shared
  scrubber pauses at the newest frame before wrapping.
- Workspace follow-up 2026-07-21: the Active Alerts legend now expands to a
  full-width tray, reflows categories into additional columns, and removes its
  nested content scrollbar. Alert category columns have a wider minimum and
  names wrap instead of being truncated with ellipses. Radar, Storm Tracks,
  Alerts, and Storm Reports now share that one collapsible tray: tabs appear
  only when their legend has content, one legend is visible at a time, tab
  selection survives refreshes, and newly activated legend sources take focus
  after initial startup. This is the Workspace prototype for possible reuse on
  other pages after browser acceptance. Live alert payloads use a bounded
  browser Cache Storage stale-while-revalidate path: cached active features render first on
  reload/Home/manual refresh, the disk-backed API request runs concurrently,
  and the fresh payload replaces cache/render state when it arrives. Workspace
  also starts the initial Alerts request concurrently with the Radar catalog
  instead of waiting for catalog completion. Projected Arrival is now exposed
  only when the selected feature is a TOR, SVR, SMW, or SPS polygon; selecting
  watches, advisories, or other alerts clears and hides the tool while retaining
  normal alert detail and zoom behavior. The right-side Active Alerts and Local
  Storm Reports feeds now retain nationwide results under map pan/zoom, while
  polygon/marker rendering and both legends remain viewport-bounded. Map moves
  refresh only the viewport data; manual/scheduled updates and filter or LSR-time
  changes refresh the nationwide feeds. The left-side
  `workspace-warning-filters` now affect only map polygons and their legend;
  nationwide alert cards are affected only by `workspace-rail-warning-filters`.
  New-alert comparison also uses the unfiltered nationwide feed, with the
  existing notification event allowlist deciding which new records produce a
  notice and sound. This awaits user browser re-smoke.
- Product follow-ups from that smoke are implemented: Surface uses stale-while-
  refresh live data, station-name popup headings, and a values-only 15-minute
  archive scrubber up to 24 hours. Its cached gradient PNG and embedded land
  mask now render even when marker rows are temporarily unavailable; Alerts has
  separate legends, cached viewport
  payload reuse, bounded tooltips, a clear detail-panel offset, Zoom to Alert,
  zoom level 9, and an active-at-time archive scrubber with exact 5-minute steps
  up to 6 hours; Radar removes `(Live Cache)`, labels Site Tools, and shares the
  corrected tooltip treatment; Satellite has harmonized Auto Update/Lookback
  controls plus a GOES-19 CONUS-only Southeast US fit-bounds view and no
  GOES-East Full Disk view preset (the Full Disk sector is unchanged); RTMA
  groups value controls below Data Stream and value markers now open a location
  + displayed-value popup; MRMS and WPC place opacity in Live; WPC refreshes
  stale product cache in the background; SPC/Drought selector styling is
  harmonized; and Tropical outlook polygons show Area/2-day/7-day tooltips,
  Storm Layers opens by default, and Issued uses the printed NHC local issuance
  with UTC in parentheses.
- Cache lifecycle audit result: Surface and WPC needed the changes above. MRMS
  already invokes its worker for missing/stale selected-product cache, and RTMA
  already resolves/downloads and renders missing selected frames on demand.
  Boundary requests consistently use the shared cached overlay endpoints and
  browser/disk caching, so no boundary architecture change was made. Radar,
  Alerts, Satellite, SPC, Drought, Tropical, and Water retain their approved
  page-specific freshness policies.
- Checkbox feasibility result: do not convert every checkbox indiscriminately.
  Binary visibility/auto-update controls can use switch presentation without
  changing their checked-state wiring, but multi-select products/categories
  should remain checkboxes and exclusive choices should remain pills/radios.
- The backend route/service refactor is complete enough that product routes and
  services should remain modular. Do not add route logic back to `main.py`.
- The fixed map-first dashboard shell is accepted.
- `/drought`, `/surface`, `/spc`, `/wpc`, `/mrms`, `/rtma`, `/satellite`,
  `/radar`, `/alerts`, `/tropical`, and `/water` serve true standalone pages
  from `frontend/pages/`. No canonical product route depends on the shared
  dashboard shell in product-only mode.
- `/workspace` serves `frontend/pages/workspace/workspace.html`. The compatibility
  `/weather.html` route redirects there; the old root file no longer exists.
- Product engines/pages own product-specific controls, requests, response
  interpretation, and rendering. The workspace imports Alerts and Radar engines
  without importing their page controllers. `weather.html`, `js/weather.js`,
  the root `js/` modules, and `css/dashboard.css` are deleted.
- Standalone pages that expose city labels use the shared `map-core.js`
  Off/US/World source, bounded density, and font-size implementation.
- Standalone sidebar controls were harmonized on 2026-07-19 using Workspace as
  the styling reference. Surface, Alerts, Radar, Satellite, SPC, RTMA, and MRMS
  use `Live / Settings / Archive`; Alerts and Surface own functional Archive
  panels while the other Archive panels are explicit placeholders. Drought, WPC, and Water
  intentionally remain `Live / Settings`, and Tropical intentionally retains
  `Live / Archive / Settings`. Settings sections use the shared order Basemap,
  opacity controls when the product has them, Cities, Map Overlays, then any
  page-only settings.
- Radar Live controls now follow the Workspace selection model: Site, Level 2/3
  pills, then a level-filtered Product selector. Level 3 is available only for
  U.S. sites; product options and site-dependent controls remain hidden until a
  site is selected. Satellite uses a staged Satellite -> Sector -> Product flow;
  View remains visible after sector selection as an independent future-facing
  map preset, not a product prerequisite. Satellite, region, and Home/reset
  changes clear dependent selections safely.
- Surface Station Density now follows Products; RTMA and MRMS Lookback precedes
  Auto Update. Alerts starts Local Storm Reports collapsed and keeps All Alerts
  as the first item in the dynamically populated category list. Water now uses
  the shared Cities controls but intentionally has no opacity control.
- Validation for the 2026-07-20 correction pass: all changed JavaScript passed
  `node --check`, changed Python passed `py_compile`, `git diff --check` passed,
  and all 85 current repository tests passed. The formerly failing Radar catalog,
  unit-conversion, cache-key, and storm-icon assertions were confirmed as stale
  expectations and synchronized with the active production configuration before
  browser re-smoke. Browser-visible corrections still require user re-smoke.
- `config/user_settings.default.json` is the tracked baseline for user-facing
  dashboard preferences. `GET /api/user-settings/defaults` serves this file,
  and standalone pages read it through `frontend/core/settings.js`. It separates
  global preferences such as home region and
  city labels from per-page defaults such as Satellite, Tropical, WPC, and
  Drought map views. A future writable user settings file should merge over
  this baseline rather than replacing built-in fallbacks.
- Most per-page `autoLoad` defaults are `false`, so product routes open to the
  configured map view with controls/background metadata initialized but no
  rendered product overlay. Current exceptions are Alerts, which renders Severe
  Weather Warnings with TOR/SVR/FFW/SMW filters enabled and starts 60-second
  auto-update, and Tropical, which starts
  in the Atlantic basin and features the first active storm when present or the
  Tropical Outlook when no active storm exists. Drought is also an exception:
  its standalone page selects and draws the latest available release on load.
- Startup controls now reflect intentional always/default-on context: state and
  country borders are checked by default but remain user-selectable; Surface
  networks start all-on with no selected surface product; Radar Sites start on;
  WPC group pills clear any previous WPC overlay and selection until the user
  selects a day/product. River Flood and Surface are the two direct-product
  exceptions and load as soon as their group pill is selected. WPC product
  rows are mutually exclusive checkboxes: selecting one replaces its peer, and
  unchecking the active row removes the overlay. The direct-product exceptions
  expose a checked row after loading so they can also be turned off.
- Surface and RTMA support true empty product states. Unchecking the selected
  Surface product or the selected RTMA stream/field clears stale values and
  invalidates in-flight layer responses instead of forcing a fallback product.
  Selecting a Surface product auto-enables its matching Gradient toggle, which
  can still be turned off independently. RTMA field checkboxes stay disabled
  until a stream is selected; 24-hour temperature change remains Hourly-only
  and clears when switching to Rapid Update.
- Surface gradient overlays are worker-generated at stable cache paths, so the
  frontend refreshes cached gradient metadata after 5 minutes and appends the
  worker timestamp as an image URL version query. This prevents open `/surface`
  pages from retaining stale gradient PNGs after the worker replaces files.
- SPC probabilistic hazards auto-enable their matching Significant/CIG hatch
  layer when selected, while Significant toggles remain unavailable on their
  own. Drought selects the latest release week on startup and turns on all five
  drought categories; selecting another week resets all five categories on.
- Phase 3 browser remediation passed a focused local re-smoke on 2026-07-23:
  empty SPC Watches shows no Unix-epoch timestamp and a watch-specific empty
  message; Fire Days 3-8 expose only valid categorical/probabilistic products;
  WPC grouped products remain empty until explicitly selected while River Flood
  and Surface load directly; and Drought uses the shared amber selected style.
- The user's follow-up smoke passed the rest of the affected pages. WPC's
  follow-up adds uncheck-to-clear behavior for every product and makes SigWx
  empty issuance explicit. The attached current Day 1 SigWx ZIP contained
  zero-byte SHP/SHX/DBF members, matching WPC's current KML declaration that no
  significant-weather areas are expected. The same parser produced five
  polygons from a non-empty official archived KML, so the missing map area was
  upstream empty data rather than a parser failure. SigWx responses now include
  issued/valid text and the no-areas marker; the frontend has a SigWx-specific
  legend and click-detail content for non-empty polygons.
- User browser smoke passed on 2026-07-04 for the startup/default-control
  changes above.
- Shared categorical legends now wrap whole swatch/label items using
  `.legend-flow`; labels can wrap without painting into neighboring swatches.
  The Alerts legend uses the five-column helper. User browser smoke passed on
  2026-06-28.

## Completed Major Work

### Backend route/service refactor

- `main.py` was split by route family using `APIRouter`.
- Product-facing cache reads, response shaping, and worker fallback logic moved
  into service modules.
- Shared app infrastructure lives under `app_core/`.
- Public/local endpoint URLs were kept stable during the refactor.
- Worker-to-`main` coupling was removed from the alert worker path.
- Product-page routing stays separate from API routing.

Current boundaries:

- `routes/*.py`: FastAPI route declarations.
- `services/*_service.py`: route-facing cache reads, response shaping, and
  fallback calls.
- `workers/*_worker.py`: upstream fetch, parsing, cache generation, and
  scheduled refresh.
- `app_core/*`: shared paths, static serving, runtime, progress, and HTTP
  helpers.

### Product-page shell and frontend split

- The fixed dashboard grid shell replaced the older floating/collapsible panel
  model.
- Top navigation and product-only route metadata are managed through the shared
  product shell.
- Route-level standalone candidates were accepted for Surface, Alerts, Radar,
  Satellite, SPC, RTMA, MRMS, Drought, Tropical, WPC, and Water.
- Phase 15 clean-cut completed for Drought, Surface, MRMS, RTMA, SPC, Alerts,
  Satellite, Radar, and Tropical wrappers that no longer needed fallback bodies.
- Phase 16 archive extraction completed for Tropical, Alerts, Surface, MRMS,
  SPC, and Radar.
- Phase 17 cleanup completed on 2026-06-18. Obsolete wrappers, declaration-only
  helpers, stale state, and unused dependencies were removed from `js/weather.js`
  and `weather.html`.
- All-page browser smoke passed for the Phase 16/17 completion set on
  2026-06-18.

Important retained rules:

- Product page modules must be included before `js/weather.js`; a missing
  `window.NCH*Engine` or `window.NCH*Page` silently prevents engine creation.
  (Retires with Frontend Split Stage 2 when the monolith is deleted.)
- `/spc` startup must normalize SPC controls and report-filter state before the
  initial `refreshActiveLayers()` call.
- Product-specific code should move only after the route/page has browser proof.
- Keep API paths stable unless a separate API cleanup is explicitly planned.

### Tropical migration

- Tropical is the accepted reference UI for rich product pages and now serves
  from `frontend/pages/tropical/tropical.html` without `js/weather.js`.
- `frontend/pages/tropical/tropical-engine.js` owns active-storm list, live detail/advisory requests,
  archive catalog requests, per-storm archive base data, advisory requests, and
  response sequencing.
- `frontend/pages/tropical/tropical-controller.js` owns active-system cards, archive selectors/cards,
  advisory/fix scrubber state and controls, inspector rendering, forecast table
  rendering, official product/graphics panels, floater state, NESDIS URL
  generation, availability probing, and modal/pill handlers.
- `frontend/pages/tropical/tropical-app.js` composes those modules with the core
  map, navigation, sidebar, status, and legend utilities. The old Tropical UI,
  bridge, state, event wiring, and `js/tropical-*` modules are removed from the
  combined workspace. Static/automated validation passed on 2026-07-19; a later
  corrected Tropical re-smoke completed the 2026-07-25 whole-system acceptance.
  Normal page loads, basin changes, Refresh actions, basin overlay/vector reads,
  and storm-detail reads now consume the latest worker-written disk cache without
  polling NHC; the scheduled Tropical worker remains the update owner, while an
  absent cache or explicit API `force=true` request can still invoke it. The
  Settings tab again exposes the shared Cities controls (Off/US/World, zoom-aware
  density, and font size) after they were restored from the pre-refactor UI.
  The left sidebar is now `LIVE | ARCHIVE | SETTINGS`. Live defaults to World,
  provides independent single-select World, ATL, E PAC, and C PAC views,
  filters one cached World storm summary locally, and loads only the selected
  cached outlook feeds with stale-response protection. Active Systems and
  Tropical Outlooks are independent collapsible panels, both open by default;
  storms require explicit selection and carry basin badges. World and regional
  extents render both outlook areas and clickable active-system overview markers
  directly from the cached summary, and every basin-pill action resets the map
  to the matching extent while retaining any still-valid System selection.
  Archive keeps its
  independent basin/season browser. The canonical System inspector opens
  contextually on the right without replacing either left workflow. It is a
  third rail on wide screens, an overlay drawer below 1400 px, and can be
  closed/reopened without clearing selection.
  The refactor's startup blockers were corrected by restoring the scrubber
  playback-speed formatter and the standalone map container sizing; the page
  now initializes and renders its Leaflet map. Full Tropical workflow smoke is
  accepted as described in the current stabilization section above.
  The focused boundary suite passed 14 tests. The repository-wide suite reached
  49 passed with five unrelated Radar expectation failures in
  `test_radar_product_catalog.py` and `test_radar_storm_attributes_service.py`;
  Phase 26 did not change those Radar backend/config paths.

### RTMA Feels Like

- Separate Wind Chill and Heat Index selectors were replaced by one
  `apparent_temperature` product labeled Feels Like.
- The derived value uses temperature, dew point, and wind speed from the same
  RTMA frame.
- The derived-product PNG path uses the shared RTMA grid loader rather than a
  native GRIB variable path.

### CSS extraction and navigation

- The large inline `weather.html` style block was lifted into
  `css/dashboard.css`.
- A later per-product CSS split was intentionally deferred because many
  selectors are shared or interleaved across product families.
  (Superseded 2026-07-16: un-deferred as part of Frontend Split Stage 2.)
- The prominent top navigation uses canonical product routes and preserves the
  hidden `weather-type-*` inputs because existing dashboard event listeners
  still depend on them. (Retires with Frontend Split Stage 2 along with the
  shared shell.)

## Frontend True Split (Stage 2) and Severe Weather Workspace

Planned 2026-07-16. Active track 1. This continues the completed Phase 15-17
product-page shell work and is recorded here before implementation so the
plan survives between sessions.

### Why Stage 2 exists

Phases 15-17 produced per-product files but not per-product boundaries:

- `js/weather.js` is ~16,000 lines — roughly 68% of all frontend JS.
- Every canonical product route serves the same `weather.html` (via
  `serve_product_shell_page()` meta injection, other products' controls
  disabled), so every page loads all ~25 scripts including the monolith.
- Engines receive `context` objects built inside `js/weather.js`; across all
  engines that surface is ~206 distinct members — a porthole into the
  monolith, not an interface.
- The scrubber is a global mode with cross-product coupling (for example,
  `mrms-engine.js` calls `context.exitRtmaScrubMode()` and
  `context.updateRtmaScrubberUi()`).

Stage 2 finishes the separation: each page owns its directory, shared code
shrinks to a small explicit core, and the combined view is rebuilt at the
end as a composition of the same modules.

### Target structure

```text
frontend/              browser-only assets; avoids the existing Python lib/
  core/                the ONLY shared frontend code
    api.js             apiUrl(), fetch wrappers, progress polling
    map-core.js        Leaflet init, basemap toggle, region fitBounds
    scrubber.js        generic single-product frame scrubber COMPONENT
                       (per-page instances; no global modes)
    legend.js          legend builder
    status.js          status line + staleness/timestamp helpers
    nav.js             product nav (absorbs product-page-shell.js)
    settings.js        user settings load/save
    core.css           app chrome (shared.css + shared dashboard CSS)
  pages/
    alerts/            alerts.html, alerts-page.js, alerts-engine.js,
                       alerts-tools.js, alerts-panel.js, alerts.css
    radar/ satellite/ spc/ surface/ mrms/ rtma/ drought/ tropical/ wpc/ water/
                       same pattern: {page}.html, {page}-page.js,
                       {page}-engine.js, {page}.css
    workspace/         combined severe-weather view; built LAST
  lib/                 vendored Leaflet, topojson-client, tz-lookup
```

Deleted at completion: `js/weather.js`, `weather.html`,
`js/product-page-shell.js`, `js/product-app-context.js`, `css/dashboard.css`
(split into `core/core.css` + per-page CSS), and the `js/` directory itself.
The dead `js/satellite.js` is deleted early (never loaded by any page).
Backend layout is unchanged — `routes/`, `services/`, and `workers/` are
already split; `serve_product_shell_page()` meta injection is replaced by
serving each page's own HTML. The display side stays a pure cache/API
reader, so a future feeder/display split (workers on another machine)
remains compatible without changes to this plan.

### Ownership rules

1. A page's HTML loads exactly `frontend/lib/*`, `frontend/core/*`, and its
   own `frontend/pages/{product}/` directory — never a sibling page's files.
2. Core only accepts code that two or more pages already use (not "might
   use someday" — that is how `weather.js` happened).
3. Workspace exception: `frontend/pages/workspace/` may import sibling pages'
   `*-engine.js` files (and engine-side tool modules), never their
   `*-page.js` controllers. It is the single sanctioned cross-page consumer.

Anything the workspace needs must therefore live on the engine side of a
product's page/engine boundary.

### Config-driven engines

Engines take their product catalog as an instantiation option instead of
hardcoding it. A standalone page passes the full catalog; the workspace
passes a trimmed one:

```js
createSatelliteEngine(map, {
    satellites: ['goes18', 'goes19'],
    sectors: ['CONUS'],
    channels: ['Channel02', 'Channel08', 'Channel13'],
});
```

### Migration order (strangler-fig)

`weather.html` stays untouched and working until the end. Per product:
build the real standalone page (own HTML/scripts/CSS) -> reach parity ->
delete that product's code from `js/weather.js`. Each step is independently
shippable, so an interrupted session still leaves the repo better than it
found it.

- Phase 18: **COMPLETE 2026-07-16.** Core API inventory and interface contract
  are in `docs/archive/frontend-stage2-core-api-inventory.md`. The audit found 578
  injected entries / 390 unique names, defined the `core/*`, page, engine, and
  workspace boundaries, and identified the cross-product scrubber coupling
  that must not survive migration.
- Phase 19: **COMPLETE 2026-07-16.** Drought is the proof-of-pattern at
  `frontend/pages/drought/`. `/drought` now serves its own HTML, ES-module page
  controller, DOM-free engine, and Drought CSS with only the minimum shared
  API/settings/map/nav/legend/status core. The old Drought controller/engine,
  HTML controls, and `js/weather.js` implementation were removed after parity.
  Browser smoke proved date loading, NC statistics, category filtering,
  opacity, basemap changes, five rendered GeoJSON paths, and no console errors;
  the remaining `weather.html` shell also loaded without errors. Follow-up
  parity corrections added shared Lat/Lon, state, country, and county overlay
  controls; restored the map logo and global last-updated HUD; moved Data
  Status into the controls sidebar; moved the expandable legend onto the map;
  restored the Off/US/World city source, bounded density, and font-size controls
  through the shared map core; and made the initially highlighted latest release
  load automatically. A final pre-split UI audit restored the Data Age row,
  reset-view control, numeric zoom indicator, USGS and no-label basemap choices,
  dashboard attribution, and product-navigation icons. Unrelated WWA/product
  panes and the developer-only test-alert button are intentionally not part of
  the standalone Drought page. Boundary startup was then corrected after a
  hard-refresh regression exposed ~53 MB of repeated GeoJSON downloads:
  generated boundary files remain in the gitignored `cache/overlays/` runtime
  cache, the server now retains decoded payloads in memory and serves week-long
  immutable cache headers, and `frontend/core/api.js` persists versioned map
  payloads in browser Cache Storage. State startup requests no longer include
  county geometry; counties download only when enabled. The client also filters
  returned U.S. features by their declared layer and uses boundary cache version
  4, preventing a response cached from an older unfiltered API process from
  crossing state and county toggle behavior. Dark is the standalone
  page and shared map-core default basemap, matching the pre-split shell.
  Option 1A from the Drought sidebar design handoff established the accepted
  300px shell with pinned Data Status/Region header, accessible tabs, a
  scrollable mounted-panel area, and a pinned message/Refresh footer.
  `frontend/core/sidebar-tabs.js` owns stable-DOM switching plus click and
  keyboard navigation. The completed 2026-07-19 control pass supersedes the
  original Data/Overlays/Style grouping: standalone pages now use the semantic
  Live/Settings/Archive pattern documented under Current State, with intentional
  two-tab and Tropical-order exceptions. Controls remain mounted while hidden so
  existing IDs, listeners, and state survive tab changes.
  Browser smoke passed tab switching, keyboard Home navigation, retained control
  state, default Dark basemap, automatic latest-release data, and pinned layout
  geometry. The accepted legend treatment is now a shared, map-panel-confined
  dark glass tray in `frontend/core/legend.js` and `core.css`. It supports
  left/center/right alignment, an accessible collapse control, compact
  categorical entries, and reusable continuous-colorbar/tick primitives while
  leaving product labels, thresholds, and values with the product engine.
  Drought uses the bottom-left alignment, keeps all five official USDM classes
  visible, and expands in place for state cumulative/individual percentages and
  DSCI. Browser smoke verified national, collapsed, and NC-stat states and proved
  the tray remained wholly inside the map panel without crossing the sidebar.
  The standalone core shell also retains the dashboard's original Montserrat
  typography through the existing self-hosted normal and italic variable fonts;
  `core.css` owns the shared family declaration and product CSS inherits it.
  The corrected wiring passed module syntax, focused lint, eleven standalone and
  boundary-cache tests, and live local API payload checks.
- Phase 20: **COMPLETE 2026-07-17.** Surface is the second consumer of the
  accepted shells at `frontend/pages/surface/` (Option 1A tabbed sidebar,
  ES-module page controller, DOM-free engine, page-local renderer module,
  per-page CSS). Ported from the monolith with parity: colored value markers
  with zoom scaling and station popups, ASOS/COOP/DCP/RWIS network filters
  (hidden on CONUS/WORLD), zoom-aware station-density thinning with a km
  readout, worker-PNG gradient overlays with 5-minute metadata TTL and URL
  cache-busting, the IDW client-canvas gradient fallback with the 32F
  isotherm diagnostic, and a continuous-colorbar legend on the shared
  core-legend primitives with a Stations count. The Gradient Blur control was
  intentionally dropped after user review: worker PNGs never blurred, so the
  slider only affected the rarely-seen canvas fallback, which now uses a
  fixed `FALLBACK_BLUR_SCALE = 1.0`. Decision (Option B): the surface archive
  mode was NOT rebuilt on the standalone page — surface support was removed
  from the shared archive scrubber entirely (product type list, archive load
  branch, frame rendering); the scrubber-as-component rewrite remains
  Phase 22. After user parity smoke, ~1,000 lines of surface implementation
  were deleted from `js/weather.js` (shared helpers kept because RTMA,
  cities, and satellite legends use them: `windDirectionBarbIcon`,
  `surfaceColoredTextIcon`, `_filterByMinDistKm`, `_haversineKm`,
  `renderContinuousLegend`, `_formatSurfaceTick`), the `wx-section-current`
  controls and `wx-side-group-current` styling blocks were removed from
  `weather.html`, and `js/surface-engine.js` + `js/surface-page.js` were
  deleted. `weather.js?v=20260717a`. Superseded 2026-07-20: a bounded,
  standalone values-only Surface archive was restored using one endpoint time
  plus a 15-minute-step lookback (maximum 24 hours) and the shared scrubber;
  it does not restore the old monolith archive path.
- Phase 21: spc, wpc. **SPC half COMPLETE 2026-07-18.** User parity smoke
  passed 2026-07-17 (minor UI spacing issues noted; deferred with the other
  pages' polish to the end of the superplan). The monolith deletion then
  landed: ~1,700 lines of SPC implementation removed from `js/weather.js`
  (colors, style fns, CIG pattern defs, legends, control-state/sync
  functions, fetchers, refreshSpc, opacity appliers, auto-refresh interval,
  archive branches — archive product types are now MRMS and Alerts only),
  the `wx-section-spc` controls and `wx-side-group-spc` styling blocks
  removed from `weather.html`, and `js/spc-engine.js` + `js/spc-page.js`
  deleted (`weather.js?v=20260718a`). Kept in the monolith because the
  alerts/WPC detail panel uses them: `_extractSpcMdPeakChips`,
  `_buildSpcWatchChips`, `_spcWatchTitle`, `_extractSpcMdSections`,
  `_renderSpcMdBodyHtml`, and `_openSpcTextDetail` (WPC's `openWpcDetail`).
  The hidden `weather-type-spc` input and nav link remain per the retained
  shell rules. The SPC standalone page is at `frontend/pages/spc/` on the
  accepted shells: Option 1A tabbed sidebar, ES-module page controller, a
  DOM-free engine (`spc-engine.js`, which also exports the SPC colors and
  DN/CIG predicates the renderer shares), a page-local Leaflet renderer
  (`spc-render.js`), a page-local detail-panel module (`spc-detail.js`), and
  per-page CSS. Ported with parity: Day 1-8 convective outlooks with the
  base-hazard/Day-3 cat-prob exclusivity rules, Significant (CIG) auto-enable
  and SVG hatch patterns, fire weather outlooks (categorical rows Days 3-8),
  storm reports (dedupe + Font Awesome markers + popups), mesoscale
  discussions, watches (polygon/counties mutual exclusion), the exclusive
  product-family clearing across the four SPC subtabs, the outlook/MD/watch
  detail panel (Outlook/Impacts tabs, impacts table, Most Probable Peak and
  Watch Probability chips, source links), all five legend variants on the
  shared core-legend tray (categorical, per-hazard probabilistic with hatch
  intensity swatches, fire, reports, watches-in-view with moveend refresh),
  the center-map empty state with SPC placeholder wording, fill/stroke
  opacity, and the 60 s MD/watch auto-refresh (which now keeps an open detail
  panel open). `/spc` serves the standalone HTML (routes/pages.py). SPC code
  has NOT yet been deleted from `js/weather.js`/`weather.html` — deletion
  happens after user smoke, per the strangler-fig rule. Deliberate deltas to
  review during smoke: (a) SPC archive mode was not rebuilt (same Option B
  treatment as Surface; the disconnected `/api/archive/spc` backend workflow
  was later removed in cleanup Phase 2), (b) detail-panel drag
  and prev/next alert-stack navigation were dropped (SPC details are always
  single-feature), (c) "Zoom to Outlook Area" fits the clicked feature's
  bounds instead of flyTo(center, z9), (d) the boundary bring-to-front hack
  is unnecessary because the core boundary pane (z-420) already sits above
  the overlay pane. **WPC half BUILT 2026-07-18 (awaiting user parity
  smoke).** The WPC standalone page is at `frontend/pages/wpc/` on the same
  shells: `wpc.html` (Option 1A sidebar; Data tab hosts the 8 group pills —
  Excess Rain / QPF / Winter / River Flood / Meso Disc / SigWx / Surface /
  Forecast — with per-group panels), `wpc-page.js` (controller; ports the
  shell's selection state, group-pill navigation-only semantics, QPF/Winter
  sub-tabs, ERO/snow day pills, catalog-driven radio lists, and the
  forecast/QPF-6hr bottom scrubber), `wpc-engine.js` (drought-style engine:
  fetch + Leaflet render for both vector GeoJSON and raster image-overlay
  products, legend HTML on the core tray incl. ERO/MPD/FOP/winter/QPF
  variants with is-disabled dimming, cached/stale/unavailable status notes),
  `wpc-detail.js` (page-local detail panel for MPDs and ERO/winter areas:
  MD Summary/Discussion sections, WFO/RFC and Forecast Details chips,
  prev/next nav across winter probability areas, zoom-to-bounds),
  `wpc-scrubber.js` (ES-module port of the shell's NCHScrubber; promote to
  core in the Phase 22 scrubber-component rewrite), and `wpc.css`. `/wpc`
  now serves the standalone HTML. Static checks passed (node --check all
  modules, py_compile, serve_page resolution); the dev server was down at
  the end of the session so live route curls could not be re-run — restart
  it before smoking. WPC monolith code (~330 lines in js/weather.js incl.
  buildWpcLegend, the wx-section-wpc/wx-side-group-wpc blocks in
  weather.html, js/wpc-engine.js, js/wpc-page.js, js/scrubber.js if nothing
  else uses it) is deleted only after user smoke, same as SPC. FOP/MPD/
  Surface groups load via the Refresh button (parity with the shell's
  group-pills-are-navigation-only decision). **WPC half COMPLETE
  2026-07-18 — monolith deletion landed WITHOUT the user parity smoke, on
  explicit user authorization ("Delete without smoke tests. Do this for any
  other completed phases until I return"). User parity smoke PASSED
  2026-07-18.**
  Deleted: ~230 lines of WPC implementation from `js/weather.js` (engine/
  page factory refs, `wpcLayer`/`_wpcRequestSeq` state, `_openSpcTextDetail`
  (its only remaining caller was WPC; the alerts detail path uses the
  MD/watch chip helpers directly, which are kept), the `_WPC_*` legend
  tables + `buildWpcLegend`, the reliability-chain branch, the
  `_cleanupPreviousTabState` case, the refreshActiveLayers branches, the
  opacity handler, `configureWpcPage` wiring, and the wpc product context +
  engine creation), the `wx-section-wpc` controls, `wx-side-group-wpc`
  styling block, and `#wpc-scrubber-bar` from `weather.html`, and files
  `js/wpc-engine.js`, `js/wpc-page.js`, `js/scrubber.js` (NCHScrubber's
  only consumer was js/wpc-page.js). Kept per the retained-shell rules: the
  `/wpc` nav link, hidden `weather-type-wpc` input, `'wpc'` entries in the
  shared type arrays/label maps/reliability dicts, the inert
  `isWpcMpd`/`isWpcForecast` branches inside the shared alert detail
  renderer, and the dead WPC rules in `css/dashboard.css` (same treatment
  as SPC's). `weather.js?v=20260718b`. This completes Phase 21.
- Phase 22: mrms + rtma, including the scrubber-as-component rewrite.
  **COMPLETE 2026-07-18 — built and monolith-deleted in one session under
  the user's standing "delete without smoke tests" authorization. User
  parity smoke PASSED 2026-07-18 for both /mrms and /rtma.**
  Scrubber-as-component: `frontend/pages/wpc/wpc-scrubber.js` was promoted
  to `frontend/core/scrubber.js` (per-page instances, no global modes; WPC
  imports the core module; `.nch-scrubber` CSS moved to `core.css`), and
  gained `setFrames(frames, {index, silent, keepPlaying})` + `getIndex()`/
  `isPlaying()` so auto-update can append frames without restarting
  playback. MRMS standalone (`frontend/pages/mrms/`): Option 1A sidebar,
  the five product sub-tabs with mutually-exclusive product checks and
  per-product sub-option radios (`composeProductKey` ported unchanged incl.
  QPE/Rotation/MESH/AzShear/EchoTop/VIL/Refl/Lightning/Model keys),
  lookback slider (1-12 h), 90 s auto-update append capped at 400 frames,
  frames from `/api/overlay/frames` with `/api/overlay/latest` →
  `/api/data/mrms` fallback when no frames are cached, worker product set
  via `/api/mrms/set-product`, scale/categorical/fallback legends on the
  core tray, next-2 frame prefetch. RTMA standalone
  (`frontend/pages/rtma/`): stream/product exclusivity rules ported (wind
  speed+direction pair, 24 h temp change hourly-only, Rapid Update
  CONUS-only), pre-rendered gradient overlay with on-demand and points-only
  fallbacks, zoom-responsive value markers (colored text + wind barbs) with
  density thinning and viewport-driven refresh, wind-pair secondary
  markers, continuous-anchor legend, per-frame scrub rendering (prerender
  overlay + points in parallel, error auto-skip), 90 s auto-update append
  capped at 150 frames. Both routes serve standalone HTML. Monolith
  deletion (~2,000 lines from `js/weather.js`, the MRMS/RTMA blocks from
  `weather.html`, and js/{mrms,rtma}-{engine,page}.js) kept the shared
  archive-scrubber chrome — `_setRtmaScrubberStatus`,
  `_updateRtmaScrubberUi`, `_setArchiveScrubber`, RTMA_SCRUB_* playback
  constants (all still used by radar/satellite), `_exitMrmsScrubMode`/
  `_exitRtmaScrubMode` slimmed to chrome-only resets for the radar/
  satellite engine contexts, and `hasMrms/RtmaScrubFrames` context
  accessors stubbed to `false` (alerts/satellite engines hard-require
  them). Archive mode in the retained shell is now Alerts-only. Deliberate
  deltas for the eventual smoke: (a) MRMS date-range archive was not
  rebuilt (same Option B treatment as SPC/Surface — the lookback scrubber
  is the animation story), (b) the 3 s in-play warm poll and the animate-
  button "filling" indicator were dropped (the 90 s auto-update append
  covers frame growth), (c) RTMA marker density initializes from the
  slider default 0.25 instead of the monolith's untouched-slider value 1.
- Phase 23: satellite. **COMPLETE 2026-07-18 — built + monolith-deleted under
  the user-approved build+delete-before-smoke authorization; user parity smoke
  PASSED 2026-07-18. Fix gaps forward in `frontend/pages/satellite/`, never
  restore monolith code.** Standalone page at `frontend/pages/satellite/`
  on the Option 1A shells: `satellite.html`, `satellite-page.js` (controller:
  strict Satellite → Sector → View → Product chain ported verbatim incl.
  PLATFORM_SECTORS/PLATFORM_CHANNELS/GOES_ONLY_CHANNELS filtering, auto view
  presets, dynamic himawari-target-current fit via
  `/api/satellite-v2/frame-bounds`, per-sector frame budgets), `satellite-
  engine.js` (catalog fetch via `/api/satellite-v2/catalog`, legend fetch +
  interpretive-legend tables, continuous/interpretive legend HTML on the core
  tray incl. the AOD "No Data" leading swatch), `satellite-anim.js` (tile-
  layer animator ported from the shell: pooled per-frame layers with hot-frame
  window ±3, ready-gated swaps w/ renderSeq + swapToken, 5 ms crossfade with
  old-layer-underneath, progressive-redraw retries, tileerror backoff,
  viewport prefetch queue w/ renderLive=0), and `satellite.css`. Frames drive
  `frontend/core/scrubber.js`; zoom pauses/resumes playback and re-renders;
  moveend reschedules prefetch. Deliberate deltas for the smoke: (a) the
  separate Current/Animate modes were collapsed — the page always loads the
  scrubber loop with the newest frame shown (the shell's html no longer had
  mode buttons anyway), (b) auto-refresh is a sidebar Auto-Update checkbox
  (5-min cadence, keepPlaying append, jump-to-newest on new frames) instead
  of the scrubber-bar Auto pill, (c) scrubber speeds are the core component's
  0.5–4x steps (shell had 0.25–4x in 7 steps), (d) an Imagery Opacity slider
  was added in Style (shell was fixed 1.0), (e) empty-chain partial
  selections never auto-pick Channel13 (strict placeholder retained).
  Monolith deletion (~1,723 lines from `js/weather.js` → 9,250 lines): all
  `_satellite*` state/constants/functions incl. the whole animation block,
  `_crossfadeSatelliteLayers`, `_SAT_DISPLAY_NAMES`/`_SAT_SOURCES`/
  `_satelliteReliabilityMeta`, the `satellite-overlays` pane, engine-context
  registration + configureSatellitePage wiring, scrubber-bar satellite
  branches (play/step/slider/auto-refresh), tab-change/visibilitychange/
  moveend/zoomstart/zoomend branches, and the archive-button satellite guard;
  `wx-section-satellite` (127 lines) + the scrubber-bar Auto button + script
  tags removed from `weather.html`; `js/satellite-engine.js` +
  `js/satellite-page.js` deleted. Kept per retained-shell rules: nav link,
  hidden `weather-type-satellite` input, `'satellite'` entries in type
  arrays/label maps/reliability dicts, dead satellite CSS in
  `css/dashboard.css`, and the unrelated tropical Satellite Floater.
  `weather.js?v=20260718d`. Archive mode remains Alerts-only. Smoke follow-up:
  the continuous legend's longer temperature endpoint labels exposed the
  core tray's horizontal overflow because the labels were centered at 0% and
  100%. Satellite now aligns the first label inward from 0% and the last label
  inward from 100% (`satellite.css?v=20260718c`) so the unwanted bottom
  scrollbar is removed without clipping either endpoint. The shared
  `.core-map-legend` bottom position is now 50px (user-accepted globally) so
  legend trays clear the bottom scrubber instead of overlapping it.
- Phase 24: radar. **COMPLETE + USER PARITY SMOKE PASSED 2026-07-18. Built and
  monolith-deleted under the standing build+delete-before-smoke authorization.
  Fix gaps forward in `frontend/pages/radar/`, never restore the monolith
  implementation.** Standalone page at `frontend/pages/radar/`:
  `radar.html`, `radar-page.js`, `radar-engine.js`, and `radar.css` on the
  Option 1A shell, shared map/legend/sidebar cores, and
  `frontend/core/scrubber.js`. Preserved behavior includes the complete
  API-driven 164-site NEXRAD selector with operational-status marker colors;
  CONUS-aware Level 2/Level 3 product filtering; response-driven L2 elevation
  pills; parallel current-frame + 0.5-12 h cached-frame loading; pooled image
  overlays; 90 s on-demand auto-update; continuous `.pal` legends; radar-site
  legend; map opacity; NST cells/tracks; selected-cell motion parameters for
  L2 SRV; and the throttled `/api/radar/live/value` inspector. The route now
  serves the standalone HTML. Monolith deletion removed ~2,006 lines from
  `js/weather.js` (now 7,244 lines), `wx-section-radar` and Radar script tags
  from `weather.html`, and obsolete `js/radar-engine.js`, `js/radar-page.js`,
  and `js/radar-site-locations.js`. The Projected Arrival Tool / Radar Speed
  Estimator remains in `weather.html`/`js/weather.js` as workspace-reserved
  functionality for Phase 27; it is no longer part of the Alerts workflow.
  `weather.js?v=20260718e`. Deliberate
  smoke points: (a) a site is now explicitly required instead of showing the
  non-loading `National Composite` sentinel, (b) the dead/unwired multi-site
  state was not rebuilt, (c) the core scrubber owns playback at 0.5-4x, and
  (d) history-fill follow-up is a bounded refresh plus the 90 s auto-update
  path rather than the monolith's separate scrubber chrome/warm indicator.
  Post-smoke UI follow-up: the six site-status categories now occupy one row on
  desktop (two columns at the existing mobile breakpoint). Home, Region change,
  and Clear share one reset path that pauses and empties the scrubber, clears
  the selected site/elevation/overlay/highlight and stale requests, restores
  the default L2 reflectivity selection, and returns the legend to Radar Sites
  when site markers are enabled. User browser confirmation PASSED 2026-07-18:
  several radar sites passed the parity smoke, and the one-row legend plus all
  three reset triggers worked correctly while playback was active.
- Phase 25: alerts. **COMPLETE 2026-07-19. STANDALONE BUILD + USER
  PARITY/FOLLOW-UP SMOKE PASSED; LEGACY MONOLITH CLEANUP STATICALLY
  VALIDATED. Preserve the Projected Arrival Tool as a workspace-owned Phase 27
  capability. Fix future gaps forward in
  `frontend/pages/alerts/`.** Legacy cleanup removed the Alerts controls,
  warning rail, banners/detail/pager, live/LSR loaders, archive path, product
  context, and obsolete `js/alerts-{engine,page}.js` from the combined
  workspace (about 4,000 deleted lines). The storm-motion extraction,
  projection/place-arrival and drawing implementation remains in
  `weather.html`/`js/weather.js` for Phase 27. Validation: `node --check` on
  the monolith and all standalone Alerts modules, focused standalone-boundary
  tests (11 passed with the Drought regression set), an unresolved
  internal-helper scan, legacy-reference searches, and `git diff --check`. Per the user's
  multi-phase authorization, no additional browser smoke was run at this
  boundary; later whole-system acceptance closed the retired Phase 27 gate. The
  standalone page uses the Option 1A core map/sidebar/legend/status/scrubber
  shell plus a dedicated active-warning rail. Preserved behavior includes the
  complete alert-category selector with TOR/SVR/FFW subtype filters; viewport-
  and region-scoped full/display geometry requests; in-memory category changes;
  active-alert counts and in-view legends; clickable polygons; the immersive
  detail panel with headline, description, instructions, timing, and official
  NWS link; active-warning filtering and zoom; LSR categories, map markers,
  counts, 1/6/12/24 h windows, and legends; bounded visual new-alert notices;
  polygon opacity; map overlays/cities;
  manual refresh; default-on 60-second auto-update; and dormant Alerts archive
  plumbing on the shared scrubber (UI hidden pending the unified archive
  design). `/alerts` now serves
  `frontend/pages/alerts/alerts.html` and loads only core + Alerts modules.
  Clarified scope decision: the Projected Arrival Tool depended on the removed
  IEM radar overlay, so it is not part of standalone Alerts. Preserve its
  existing implementation as a workspace-owned capability for Phase 27, when
  the severe-weather workspace (eventually the
  primary `/weather` page) can supply radar imagery and playback context.
  Initial-smoke follow-up (`alerts.css`/`alerts-page.js?v=20260718b`): the
  page-specific legend now spans the map width, uses compact responsive
  auto-fit columns, and allows a taller tray before scrolling; Alert Categories
  is collapsible like LSRs. Severe subtype controls remain visible whenever
  either Severe Weather Alerts or Severe Weather Warnings is selected and now
  include SMW in addition to TOR/SVR/FFW; the warning rail has the same SMW
  filter. New-alert notices default to those four severe warnings only, with an
  explicit Style choice for Severe, All Selected, or Off. The immersive detail
  is height-bounded with an internal scroll area, draggable by its header,
  restores severity/urgency/certainty badges and NWS threat-detail chips,
  structures hazard/source/impact and locations/instructions sections, and
  builds the official `forecast.weather.gov/product.php` text-product URL from
  the alert event + issuing office instead of linking to the API feature. A
  second focused follow-up (`alerts.css`/`alerts-page.js?v=20260718c`) nests the
  TOR/SVR/FFW/SMW controls directly below Severe Weather Warnings and shows them
  only when that category is checked (including through All Alerts); adds the
  wired 1-hour LSR window; hides the Alerts Archive mode until archive UI is
  implemented consistently across pages; and makes event product codes take
  precedence over continuation/update AWIPS codes so a Severe Thunderstorm
  Warning always links to SVR rather than SVS. Future unified archive UI must
  select one target datetime plus a lookback duration, not a from/to range.
  Third focused follow-up (`alerts.css`/`alerts-page.js?v=20260718d`): the right
  rail now removes its grid column when neither alert categories nor LSR
  categories are selected. With one dataset selected it shows only that panel;
  with both selected it splits into independently scrolling Active Warnings
  (top) and Latest Storm Reports (bottom). The LSR half reuses the compact pill
  pattern with All/Tornado/Hail/Wind/Other counts, where Other groups every
  non-tornado/hail/wind report. Reports sort newest-first; selecting a report
  zooms to its marker and opens the report popup, including after the resulting
  viewport refresh replaces the marker layer.
  Toggle-delay correction (`alerts-page.js`/`alerts-engine.js?v=20260718e`):
  nesting the severe subtype controls beneath the category list had allowed
  TOR/SVR/FFW/SMW inputs to leak into category/master queries; category inputs
  now have a dedicated selector and subtype changes no longer double-fire the
  category handler. Empty selections hide layers without discarding the last
  successful alert/LSR payload. Re-enabling categories therefore renders from
  memory immediately; LSR data is keyed by viewport + time window and only
  refetched when that scope changes or Refresh/auto-update explicitly requests
  fresh data. Empty valid responses are cached too. This also prevents the rail
  grid resize/moveend cycle from erasing cached polygons while products are off.
  Footer-status correction (`alerts-page.js`/`alerts-engine.js?v=20260718f`):
  the page now owns one combined status message derived from the currently
  selected datasets and their displayed counts. Parallel Alert and LSR loads
  can no longer overwrite each other, and deselecting LSR immediately removes
  the stale Local Storm Reports-only message.
  LSR legend refinement (`alerts.css?v=20260718e`/`alerts-engine.js?v=20260718g`):
  Local Storm Report entries now use the same type-specific Font Awesome icon
  and color mapping as their map markers instead of generic color swatches.
  As of `alerts-engine.js?v=20260718h`, entries follow the configured category
  order rather than report arrival order, keeping Tornado first when present.
  Severe-polygon pulse restoration (`alerts.css?v=20260718f`/
  `alerts-engine.js?v=20260718i`): TOR, SVR, FFW, and SMW polygons again pulse
  both fill and border. A Settings-tab On/Off selector is enabled by default and
  updates the existing polygon layer immediately without a data reload.
  Contrast/refresh follow-up (`alerts-page.js?v=20260719a`): Flash Flood Warning
  text uses a lighter presentation-only red on dark UI surfaces while its
  official NWS polygon, border, and legend color remains unchanged. Auto-Update
  is now enabled by default and refreshes the selected live data every 60 seconds.
  User browser confirmation PASSED 2026-07-19 for the complete focused follow-up,
  including the final FFW text-contrast correction. This satisfies the smoke
  gate for legacy Alerts removal; it does not authorize deleting the preserved
  arrival/speed workspace tools.
  Final legend sizing polish (`alerts.css?v=20260719b`) remains page-specific:
  categorical tracks auto-fill at 180-220 px and align left, preventing a small
  number of cards from stretching across the full-width tray while retaining
  dense wrapping for many categories. The existing narrow-screen rule keeps
  two fluid columns, so shared core legends and mobile responsiveness are not
  changed.
- Phase 26: complete. Tropical and Water now serve independently from
  `frontend/pages/{tropical,water}/`, and their UI/state/load/render paths are
  removed from `weather.html` and `js/weather.js`. Focused static/automated
  validation passed. Water baseline browser parity PASSED 2026-07-19 after correcting its
  obsolete core-shell class names and missing two-column grid; the user confirmed
  layout, data, detail content, and loading with no errors. Tropical and Water legend
  content now uses the refactored core header/body tray with provider badges,
  shared collapse controls, compact page-scoped rows, and hidden-empty startup.
  The Tropical Archive Advisory/Best Track scrubber is anchored to the bottom
  of the map viewport after the right-inspector layout refactor.
  A later corrected Tropical re-smoke completed the 2026-07-25 whole-system
  acceptance; the former consolidated checklist was then retired.
  Water station selection now opens River, Coastal, and NDBC details in a
  draggable map-level panel matching the Alerts detail interaction; the former
  Leaflet popup path is removed. The shared Region selector is restored in the
  Water sidebar header and reloads observations for the selected map extent;
  Data, Overlays, and Style labels/check rows now follow the shared refactored
  sidebar typography, spacing, and control sizing. Page-scoped selectors
  explicitly override the retained legacy `.wx-block label` rule so Network and
  Map Overlay rows remain full-width with right-aligned checkboxes. The focused
  Water suite passes 8 tests; these post-baseline UI changes await browser smoke.
- Phase 27: complete. `/workspace` composes Alerts and Radar engine modules,
  active warnings/LSRs, live radar site/product/elevation controls, NST tracks,
  and the value inspector on one core map. The validated Projected Arrival Tool
  moved to `workspace-tools.js` and is wired to selected workspace alerts.
  `/weather.html` redirects to `/workspace`;
  `weather.html`, `js/weather.js`, obsolete root JS modules, and
  `css/dashboard.css` are deleted. Leaflet 1.9.4, topojson-client 3, and
  tz-lookup 6.1.25 are vendored under `frontend/lib/`, and all standalone HTML
  pages use local Leaflet assets. Initial smoke follow-up now uses
  radar site selection as the live-radar activation, a centered CONUS preset
  plus AK/HI/PR, a TOR+SVR default with independently combinable
  TOR/SVR/FFW/SMW filters that are mutually exclusive with `All`,
  report type/time pills with a 1-hour default, independent layer switches with adjacent counts, and
  separate compact collapsible
  Radar/Warnings/Storm Reports legends. These presentation rules
  remain scoped to `frontend/pages/workspace/workspace.css`. Storm Reports now
  default off; Storm Tracks and Value Inspector remain hidden until a radar site
  is selected and reset on region/Home defaults. Sidebar field labels/footer
  typography and the full-width refresh action received Workspace-only polish.
  Workspace also reuses the standalone Alerts split right-rail pattern: Active
  Warning and Latest Report cards have independent rail filters and counts,
  share the engine-provided feature collections, and appear only while their
  corresponding map layer switch is enabled. With both layers enabled, the two
  card sections split the rail; with one enabled, that section uses the rail.
  The Workspace rail's `ALL` warning filter shows every alert in the active map
  selection while TOR/SVR/FFW/SMW remain severe-only filters, and alert-card
  navigation is capped at map zoom 9. Report-card popup selection is cleared
  when the report layer is disabled or the Workspace region/radar context
  changes, so a cached popup cannot reopen when reports are enabled again.
  Workspace auto-update is visible and enabled by default at 30 seconds. Each
  cycle refreshes enabled Alerts/LSR data and selected-site radar frames without
  polling inactive layers, static overlays, or the radar catalog. Newly issued
  Tornado, Severe Thunderstorm, and Flash Flood warnings/watches produce up to
  three dismissible 15-second map notices and play
  `/sounds/weather_alert.mp3` once per notification burst. SMW and all other
  alert types do not notify. Opening a notice selects the alert for Workspace
  tools and uses the same level-9 zoom cap. Initial loads and view/filter/layer
  context changes establish a notification baseline without mislabeling existing
  alerts as new. Workspace alert rail cards sort newest-issued first (`sent`,
  then `effective`/`onset` fallback). Radar-site hover labels use a Workspace-only
  translucent dark tooltip with light text/border for contrast over any basemap.
  The shared draggable Alerts detail panel now opens from Workspace alert
  polygons, alert rail cards, LSR markers, and LSR rail cards. Its LSR mode shows
  event, location, report time, magnitude, WFO, source, and remarks, replacing
  the small Leaflet report popup. Disabling/changing report context closes only
  an open LSR detail, while alert details remain independently managed. Both
  polygon and alert-card navigation are capped at map zoom 9.
  LSR markers retain a compact sticky hover tooltip with report type, optional
  magnitude, and location; its Workspace layout uses a responsive 260 px card
  width so abbreviations and locations wrap as phrases rather than single words.
  Clicking continues to open the full report detail.
  Workspace overlay focus indicators are input-aware: pointer-click focus rings
  are suppressed on Leaflet vectors/markers, while keyboard `:focus-visible`
  navigation retains a deliberate cyan outline.
  The KGSP radar-site smoke then exposed four Workspace composition gaps. Radar
  history frames now drive a visible shared scrubber; Projected Arrival drawing
  suppresses alert-detail activation so clicks reach the drawing tool; NST storm
  tracks use the established TVS/mesocyclone/hail/cell symbols, styled tooltips,
  and a separate collapsible legend; and the shared Radar value inspector again
  queues one pending sample behind the in-flight request instead of aborting and
  restarting on every mousemove. Static validation passed, followed by the user's
  iterative KGSP smoke/testing cycle.
  Workspace interaction follow-up (2026-07-28/29): while either Value Inspector
  or Storm Tracks is enabled, alert-polygon hover tooltips are suppressed so
  they cannot compete with Radar inspection/track interaction; LSR hover
  tooltips remain available. Alert-polygon tooltips are additionally hidden at
  zoom 10 and above on both Alerts and Workspace, without changing the existing
  tool-selection suppression. The user browser-confirmed the tool-selection
  behavior; the zoom threshold has focused static coverage.
  Disabling Storm Tracks now also increments the track request generation,
  clears/removes the mounted marker layer immediately, and rejects an older
  in-flight response when it returns, preventing stale icons from reappearing.
  This visibility-only toggle preserves selected-cell SRV motion identity and
  playback state. The user confirmed the focused Storm Tracks browser re-smoke.
  Workspace legend bodies now use `padding: 0 15px`, removing the unwanted
  legend scrollbar. A single global `All Active Alerts` polygon pill now
  selects the same complete category scope as `/alerts`; any narrower warning
  or watch selection deactivates it. JavaScript syntax, ten focused
  Alerts/Workspace tests, and diff checks pass; all Uvicorn sessions were
  intentionally stopped at session end.
  The Layers sidebar now presents Radar, Active Alerts, and Storm Reports as
  independently collapsible groups. Radar starts open; Active Alerts, Storm
  Reports, and the SPC/Satellite/RTMA/MRMS/WPC/Water placeholders start collapsed.
  Elevation selection remains a standalone Radar-page advanced control; Workspace
  uses the explicit 0.5-degree Level II default internally. This matches the
  scheduled worker cache key and the lowest practical tilt expected by most users.
  The Workspace Radar group has a default-on header switch plus Level 2/Level 3
  pills directly below Site. Product options are filtered from the API catalog
  to the active level; the pills and Product field remain hidden until a site is
  selected, and Level 3 remains disabled for non-CONUS sites.
  The Projected Arrival Tool now has its own collapsible Workspace group directly
  below Active Alerts; the redundant standalone Tools sidebar tab is removed.
  The entire group stays hidden until an alert polygon, rail card, or new-alert
  notice is selected, then appears expanded and identifies the selected alert.
  Disabling Alerts or changing Workspace region clears and hides it again.
  Workspace now supplies the shared map Home control with a page reset callback.
  Home clears the selected radar/site frames and scrubber, restores Level 2 Base
  Reflectivity, clears the selected alert/projection, hides Projected Arrival,
  resets the Region selector, and fits the default CONUS view while retaining
  layer visibility preferences.
  Inline explanatory copy was removed to keep the panel compact. Preserve this
  wording for a future FAQ/Wiki:
  - Projected Arrival Tool: "Select an alert polygon, draw its motion line, then
    finish the projection. Hold Shift while dragging the handle to pivot."
  The Radar Speed Estimator was subsequently removed project-wide, including its
  UI, map-click draw mode, fixed-loop calculation/autofill wiring, stale styles,
  and tests. It assumed a fixed four-frame, five-minute radar loop that no longer
  exists. Projected Arrival and its manual Speed Override are unaffected.
  Final quick filter follow-up: Active Alerts now includes a default-off `SPS`
  pill for exact `Special Weather Statement` matching. SPS remains informational:
  it is not added to severe-warning notification, pulse, or standalone Alerts
  defaults. Projected Arrival remains available for SPS polygons alongside TOR,
  SVR, and SMW polygons, but is hidden for every other alert event and for
  non-polygon alert features.
  Radar loop timing follow-up: Workspace and standalone Radar opt into the shared
  scrubber's `holdAtEnd` behavior, so the longer loop pause occurs on the newest
  frame before wraparound instead of on the oldest frame after wraparound. Other
  scrubber consumers retain their existing timing.
  Workspace legend follow-up: the formerly stacked Radar, Storm Tracks, Alerts,
  and Storm Reports panels were consolidated into one full-width, collapsible,
  keyboard-navigable tabbed tray. Only available legend sources expose tabs and
  the selected tab determines the single visible legend.
  **Shared tabbed-legend adoption plan (reviewed 2026-07-21; deferred until the
  Workspace prototype passes browser smoke):** do not copy the Workspace-local
  manager and CSS into individual pages. Promote the outer tray, dynamic tabs,
  shared collapse state, keyboard navigation, selected-tab lifecycle, and source
  registration into an opt-in companion to `createLegendHost` in
  `frontend/core/legend.js`, with shared shell styling in `frontend/core/core.css`.
  Product engines retain ownership of their legend HTML, swatches, scales,
  statistics, and viewport semantics.
  - Standalone Alerts is the next and lowest-risk proof because it already has
    independent Alerts and Local Storm Reports legend hosts. Consolidate those
    into one full-width two-tab tray without changing either viewport filter.
  - Standalone Radar requires moderate source-state work before adoption: Site
    Status and product color legends currently replace one another, and Storm
    Tracks does not expose a separate standalone legend callback.
  - SPC requires moderate source-state work because `applyLegend()` currently
    chooses one winner by precedence among outlook, reports, watches, and fire
    content. Tabs require independently retained legend sources.
  - Tropical requires the most page-specific adaptation because overview,
    intensity, surge, watches/warnings, and wind-layer renderers overwrite one
    shared host. Add a keyed legend registry tied to layer activation before
    adopting the shared tray.
  - Surface, Satellite, RTMA, MRMS, Drought, WPC, and Water should retain the
    existing single collapsible legend host. They may share compatible full-width
    shell styling later, but a one-tab tray adds no useful interaction.
  Treat successful Workspace plus standalone Alerts browser smoke as the gate
  before considering Radar, SPC, or Tropical conversion.
  **Radar/Alerts Workspace closure (2026-07-19):** the user accepted this slice
  for now and reported all tests passed. Treat the current Radar, Alerts, Storm
  Reports, scrubber, value-inspector, storm-track, Projected Arrival, and Home-reset
  behavior as the stable baseline. A focused post-closure user smoke also passed
  for the Workspace Settings/Basemap/Cities and border defaults, per-layer opacity
  controls, alert/LSR detail placement, left-side Projected Arrival Times panel,
  repeat draw-after-close lifecycle, and immediate radar product switching. The
  radar overlay pool now keys frames by site/product/elevation/frame to prevent
  same-scan cross-product image reuse. The deferred standalone Water shell issue
  was subsequently corrected and user-smoked without reopening this slice.
  Subsequent authorized Workspace expansion implemented SPC, Satellite, RTMA,
  MRMS, WPC, and Water composition. Drought remains standalone-only by product
  decision; all standalone pages remain canonical and linked in navigation.
  Static boundary tests
  passed (23 focused tests). The final repository-wide suite reached 58 passed
  with the same five unrelated Radar expectation failures already recorded
  above; Phase 27 did not modify those Radar backend/config behaviors. Browser
  proof and focused follow-up history are summarized in this superfile and the
  archived `docs/archive/next-session-startup-prompt-2026-07-24-phase8.md`; the
  former manual checklist was retired after whole-system acceptance.

Definition of done (mechanically checkable): each product route loads only
third-party libraries plus `frontend/core/* + frontend/pages/{product}/*`;
no engine references another product's functions; `js/weather.js` no longer
exists. The currently pinned Leaflet CDN asset must move to `frontend/lib/`
before Phase 27 completes.

### Severe Weather Workspace spec

Purpose: a one-stop severe-weather visualization page (US only) able to
show multiple products at once during extreme weather events. Not all
dashboard products — a curated subset:

- Radar: Level 2/3, per site.
- Satellite: GOES-18/19 CONUS only; Channel02, Channel07 or Channel08,
  Channel13.
- RTMA-RU: temperature, dew point, wind (speed/gust/direction), visibility,
  Feels Like.
- Alerts: active alerts with storm reports, Arrival Tool, and Speed
  Estimator.
- SPC: outlooks, MDs, watches.
- MRMS: rotational tracks, MESH, lightning (instant or 30-min variants
  only).
- WPC: excessive rain, QPF, meso discussions, winter weather.
- Water: River, Coastal, and NDBC Buoy observations.

Excluded: Tropical and Drought stay separate pages. No additional product
family remains in the active Workspace expansion plan.

### Workspace time-sync design (two-tier layer model)

Timeline tier — radar and satellite only:

- One time-based master clock (not frame-index): a continuous slider over a
  rolling ~60-minute window.
- At scrub time T each timeline layer independently shows its last frame at
  or before T — never a frame newer than T.
- Right edge = live mode; new frames auto-advance the display. Scrubbed
  back, the view freezes at T while ingest continues in the background.
- Prominent state indicator: LIVE vs -N MIN.

Live tier — everything else, including alerts:

- Always latest available. Alerts are ACTIVE ONLY and never scrubbed
  (decision 2026-07-16): expired warning polygons redrawn during an event
  read as current no matter how they are labeled — misleading in exactly
  the situations the workspace exists for. This also removes any need for
  alert-history retention in the workers.
- Refresh: poll each product's lightweight index/latest metadata at its
  natural cadence; swap the overlay only when its timestamp or
  `source_data_key` changed; swap on image load (no flicker). No
  client-side persistence — memory plus browser HTTP cache only.
- Every live layer displays its valid time using the existing staleness
  helpers; silent refresh must never hide staleness.

New workspace-local components: a layer manager (z-order, per-layer
opacity/toggles), compact stacked legends, and `timeline.js` (the master
clock). These live in `pages/workspace/` and may graduate to `core/` only
under ownership rule 2.

### Supersessions (2026-07-16)

- The per-product CSS split deferral (CSS extraction section above) is
  un-deferred; per-page CSS is part of Stage 2.
- Retained rule "product page modules must be included before
  `js/weather.js`" retires when the monolith is deleted.
- Retained rule "preserve hidden `weather-type-*` inputs" retires with the
  shared shell.
- Backlog item "cross-product severe-weather workspace" is promoted into
  this section.

## Product Enhancement Roadmap

### Domestic NEXRAD radar

Phase 1 is complete.

- The backend catalog owns live product labels, fields, palettes, units, ranges,
  masks, capabilities, and cache IDs.
- The Radar selector is populated from the backend catalog.
- Unsupported or stale static product options were removed or corrected.
- Level II products include reflectivity, velocity, spectrum width, ZDR,
  correlation coefficient, differential phase, and Level II-derived
  storm-relative velocity.
- Level II elevation selection supports `auto` and explicit nearest-angle
  requests, with cache isolation by requested elevation.
- Level III expansion includes storm-relative velocity, ZDR, correlation
  coefficient, KDP, hydrometeor classification, digital precipitation rate,
  one-hour accumulation, storm-total precipitation, echo tops, and VIL.
- MetPy fallback decoding is available for digital Level III products Py-ART
  cannot read reliably.
- Standardized `/api/{service}/products` endpoints exist across product families.

Completed radar enhancements:

- Radar loop blink reduction.
- Radar Inspector hover values through `/api/radar/live/value`.
- Live `.pal` upload and preview in the standalone `pal_preview/` tool.
- IEM-backed Level III storm-attribute overlays with storm tracking, hail,
  mesocyclone, TVS, and structure attributes.
- Storm-cell icon set: TVS = red triangle (T), Meso = orange circle (M),
  Confirmed Hail = solid green triangle (H), Probable Hail = hollow green
  triangle (no label), Storm Cell = small dark square with yellow border.
- Floating Storm Tracks mini-legend (`.wx-mini-legend`) appears in the
  topright map corner below the logo when Storm Tracks are enabled; hidden
  when disabled. The `.wx-mini-legend` CSS class is global and reusable on
  other pages.
- Radar site markers now use a black (`#020617`) outline on all status colors
  for legibility against the dark basemap. Selected-site highlight rings are
  unchanged.
- IEM `meso` rank threshold: only cells with rank ≥ 4 (out of 1–25) receive
  the Meso icon. Ranks 1–3 are weak rotational shear; below this threshold
  the cell falls back to its hail/default icon. Constant `_MESO_MIN_RANK`
  in `services/radar_storm_attributes_service.py`.
- The former raw-IEM meso/TVS debug route was removed in Project Cleanup Phase
  2 Batch B2. Threshold behavior remains covered by the storm-attributes
  service and its focused tests.
- Radar scrubber auto-update sends `?refresh=true` on
  `/api/radar/live/frames`. The selected-resource coordinator keeps one
  deduplicated latest-only probe active at a 60-second cadence and the client
  polls the manifest every three seconds, bounded to 60 seconds, while that
  probe runs. `RADAR_AUTO_REFRESH_MS` is 90 s (was 3 min); Workspace remains
  30 s. Full history backfill stays separate and bounded.
- DONE 2026-07-16: Live radar lookback requests now propagate from
  `/api/radar/live/frames?hours=` into the NODD worker instead of only filtering
  its fixed one-hour cache. The scheduled worker still defaults to one hour;
  a 0.5-12 h UI request starts a coverage-aware background fill when needed,
  downloads and renders missing scans newest-to-oldest in bounded 12-frame
  batches, and preserves the expanded rolling history up to the bounded target.
  Manual history polling continues even when Radar Auto-update is off. The
  slider includes `30M` and preserves fractional hours through route, service,
  and worker wiring. This remains the live-cache path; do not route expanded
  lookback through the archive renderer or restore the old archive logic.
- The "Next Update" countdown element (`wx-radar-next-update-status`) was
  removed; the reliability row "Last Update" timestamp serves as the freshness
  indicator instead.
- The legacy IEM alert-radar loop was removed from the product shell. The
  `weather-alert-radar-enable` checkbox, `weather-opacity-alert-radar` slider,
  and `_alertRadar*` frontend tile/timer/freshness path were deleted from
  `weather.html`, `js/weather.js`, and alert UI test fixtures. `/radar` now
  uses the cache-first `/api/radar/live/*` workflow only; do not reintroduce
  the IEM overlay as a fallback for site/product radar.
- BR.pal reflectivity colormap rewritten with a Radarscope-inspired green scale:
  dark green (5–10 dBZ) → medium green (10–20) → lime (20–25) → yellow (25–30)
  → golden yellow/orange (30–45) → dark-to-bright red (45–55) → pink/mauve
  (55–65) → magenta (65–70) → white (70–75+). `cache_variant` bumped to
  `br_min5dbz_v4` to invalidate stale cached frames.
- Reflectivity legend colorbar now honors the `min_value` floor: products with
  `min_value` defined in the catalog report `legend_vmin` from
  `/api/radar/colortable`, and the colorbar starts at that value (5 dBZ for
  L2_REF / L3_N0B) rather than `vmin` (−30). Logic lives in
  `config/radar_colortable_utils.py` (`_build_legend`, `get_radar_colortable`,
  `get_legend_json`) and `services/radar_service.py` (`get_radar_colortable_data`).
- Super-Res render resolution: Level 2 and L3 Super-Res products (L2_REF,
  L2_VEL, L2_SRV, L2_SW, L2_ZDR, L2_RHO, L2_PHI, L3_N0B, L3_N0G) use
  `figure_size_inches: 22` → ~4400×4400 px at DPI 200, matching their 0.25 km
  gate spacing. All other L3 derived products stay at 12 in (2400 px), which
  already oversamples their 1 km gate spacing. Configured via `figure_size_inches`
  per product in `LIVE_RADAR_PRODUCTS` in `config/radar_config.py`.
- Elevation selection: `_select_sweep` always picks the lowest available tilt
  (`min(fixed_angles)`) as default. The "Auto" option was removed from the UI —
  the seed `<option>` in `weather.html` is `value=""` with no label. L3 products
  have a single fixed sweep and never show elevation pills; that is correct
  behavior (was previously a display bug where the Auto pill appeared for L3).
- L2 chunks workflow (`radar/radar_chunks_utils.py`, `unidata-nexrad-level2-chunks`
  bucket) was **reverted 2026-07-04** — see dated entry below. `LIVE_RADAR_L2_USE_CHUNKS`
  is `False`; the module is left in place but unused should the flag ever flip back.
- `Wx-Dashboard-Radar-Live` scheduled task is now ENABLED at 1-minute intervals
  (changed from 5 min; was previously disabled). L2 runs every invocation; L3
  is gated by `radar_live_l3` freshness sentinel (~5 min effective cadence).
  Freshness sentinels `radar_live` (3 min) and `radar_live_l3` (15 min) are
  registered in `_HEALTH_THRESHOLDS` in `workers/_freshness.py`. Re-run
  `tools/install_tasks.ps1` after any Task Scheduler reset.

#### L2 chunks bucket: bugs, latency benchmark, and revert — 2026-07-04

L2 live radar stopped loading (`unidata-nexrad-level2-chunks` discovery
returning "no recent scans" for sites with heavy chunk history). Root-caused
and fixed a chain of issues in `radar/radar_chunks_utils.py`, then benchmarked
the chunks approach against the flat bucket and reverted:

- **Discovery bug**: `_list_site_chunks` listed the flat `SITE/` prefix with
  `MaxItems=1000`; S3 returns keys in lexicographic order across every VCP
  subfolder a site has ever had, so once a site accumulates enough historical
  subfolders the newest chunks never made it into the capped page. Fixed by
  discovering VCP subfolder names first (cheap `Delimiter="/"` listing) and
  walking them newest-first (`_list_recent_site_chunks`).
- **Poll-performance regression**: the newest-first walk re-listed every
  folder in the lookback window from S3 on every single poll (~30+ calls for
  a 3h window). Fixed with an in-process memo (`_COMPLETE_VCP_CACHE`,
  `_VCP_SCAN_TIME_CACHE`) so folders already confirmed complete are served
  from memory; only the front of the walk (in-progress folders) hits S3.
- **Orphan-folder edge case**: the VCP counter is not perfectly monotonic
  with time — an isolated stray folder (e.g. one leftover chunk from days
  earlier) can sort numerically after the true newest folder and halt the
  newest-first walk immediately. Fixed by requiring 3 consecutive stale
  folders (not 1) before giving up, with a final cutoff filter for safety.
- **Sequential chunk downloads**: `_download_new_chunks` issued one
  `s3_client.get_object` per chunk sequentially; a cold backfill (~10 scans,
  ~700+ chunks) took 50+ seconds. Parallelized with a 16-worker
  `ThreadPoolExecutor` (`_download_one_chunk`) — same backfill dropped to
  ~13s.
- **Latency benchmark, then revert**: compared chunk-completion timestamps
  against the flat bucket's `LastModified` for the same scans — they matched
  to the second. The flat `unidata-nexrad-level2` file is generated by the
  same upstream pipeline the moment the chunk stream finishes, so chunks buy
  **zero** latency benefit for any completed scan. The only real benefit is
  up to one volume-interval (~5-6 min) of early visibility into the
  *currently in-progress* scan. Given that plus the bug history above, L2 was
  reverted to the flat-bucket path (`radar/radar_nodd_utils.py`, same code L3
  already uses) via `LIVE_RADAR_L2_USE_CHUNKS = False` in `radar_config.py`.
  `_resolve_radar_data_utils` in `workers/radar_live_worker.py` is the single
  routing switch; no other code assumes chunks-specific behavior.
- **Scrubber warm-poll bug (separate, frontend-only)**: after the bucket
  revert, Level 2 Play still required a manual Refresh click to pick up
  backfilled frames (L3 worked fine). Two causes, both fixed:
  1. Backend render batches write to `index.json` atomically at the end of
     the whole batch, so a poll mid-render sees zero progress. The frontend
     warm-poll (`_startRadarScrubWarmPoll` in `js/weather.js`) gave up after
     4 consecutive "nothing changed" polls (~12s) — well before a 15-50s
     batch finishes. Added `is_live_render_inflight()` in
     `app_core/background_render.py` (read-only check of the existing dedup
     set) so `get_radar_live_frames_data` in `services/radar_service.py`
     reports an accurate `refreshing` flag on *every* poll, not just the one
     that happened to trigger the render; the frontend now resets its
     stable-poll counter whenever `refreshing` is true.
  2. The real blocker: L2 products have `elevation_selection: True`, so the
     very first `/frames` response calls `updateElevationOptions()`, which
     snaps the elevation `<select>` from `''` (auto) to a concrete value
     (e.g. `"0.5"`). The warm-poll's stale-context guard
     (`_tryAppendNewRadarFrames` in `js/weather.js`) recomputes its context
     key from that same live DOM element on every tick and silently bails
     out once it no longer matches the key captured before the dropdown
     changed — so L2 never auto-polled at all, while L3 (no elevation
     dropdown change) was unaffected. Fixed in `js/radar-engine.js`
     (`loadScrubberFrames`) by re-syncing the stored context key immediately
     after `updateElevationOptions()` runs.
- Cache-busted `js/radar-engine.js` (was stale at `?v=20260623c`) and
  `js/weather.js` in `weather.html`.

2026-07-04 — L2 blank velocity/SRV/SW fix + auto-elevation removal:

- L2 Velocity, Storm-Relative Velocity, and Spectrum Width rendered blank PNGs
  at every site while reflectivity worked. Root cause: NEXRAD split-cut VCPs
  scan the low tilts twice at the same fixed angle — a surveillance sweep
  (reflectivity only) and a Doppler sweep (velocity/spectrum width).
  `_select_sweep` in `workers/radar_live_worker.py` picked purely by fixed
  angle and always landed on the first (surveillance) sweep, where Doppler
  moments are 100% masked. Fixed by making sweep selection field-aware: among
  sweeps within 0.1° of the matched angle, pick the one with the most valid
  data for the field being rendered (`_sweep_valid_count`). Verified on live
  KMPX and PGUA volumes.
- The scheduled worker rendered L2 at `elevation="auto"` (`ELEV_AUTO` dirs)
  while the UI requested `0.5` (`ELEV_0P5` dirs) — a cache-key mismatch that
  made every UI request a miss and triggered a second full on-demand render
  pass per site/product. Added `LIVE_RADAR_L2_DEFAULT_ELEVATION = "0.5"` in
  `config/radar_config.py`; `run_radar_live_worker` now passes it for L2 so
  worker and UI share one cache key. `auto` is no longer used by the UI or
  the worker; stale `*__ELEV_AUTO` directories are orphaned and safe to
  delete.
- Gotcha: blank frames stay listed in `processed_keys.json`, so a fix like
  this does not re-render them — delete the affected product folders or wait
  for new scans.

Current radar notes:

- IEM storm attributes replaced the earlier AWS-NST/AWS-NMD/TGFTP approach.
- `radar_nst_service.py` was removed after the storm-attribute service replaced
  its remaining role.
- Selected-cell SRV and storm-track overlay visibility must remain decoupled so
  hiding tracks does not invalidate the active SRV animation context.
- IEM meso rank 1–3 = weak shear only; do not lower `_MESO_MIN_RANK` below 4
  without comparing against a reference tool (e.g. Radarscope) on a live event.
- The `Wx-Dashboard-Radar-Live` scheduled task runs every 1 minute. L2 products
  use the flat `unidata-nexrad-level2` NODD path; L3 products are internally
  gated by the `radar_live_l3` sentinel and only re-download/render every
  ~5 minutes. On-demand rendering via `?refresh=true` still works as a full
  fallback when the task is not running.
- Do not bump `cache_variant` for BR products without also updating the comment
  in `radar_config.py` and confirming the pal file change is intentional; stale
  frames from the old variant accumulate on disk but are ignored automatically.
- The unused compatibility-only IEM `/api/radar/tiles/*` proxy and freshness
  endpoints were removed in Project Cleanup Phase 2 Batch A. Production Radar
  remains on the cache-first `/api/radar/live/*` contract.

### Satellite and lightning

Completed enhancements (2026-06-28):

- Implemented GOES composites were exposed in the Satellite product selector:
  Fire Temperature, Air Mass, Day Cloud Phase, Day Land Cloud/Fire,
  Day Snow/Fog, Nighttime Microphysics, Dust, Ash, and Sulfur Dioxide.
- Renderer-matched interpretive legends were added for those RGB composites,
  with frontend fallback metadata so legends remain visible through
  satellite/sector/product switches without requiring a hard refresh. Scalar
  colorbars remain limited to brightness-temperature channels.

Completed display updates (2026-07-16):

- GOES `GeoColor` and `GeoColorBlkMar` daytime rendering now uses a CIRA
  logarithmic visible stretch after a bounded ABI Rayleigh-scattering
  correction. GOES frame observation time and projection longitude/height are
  carried through `SourceRaster` into the composite so the day/night blend is
  based on solar zenith (day through 80 degrees, transition to night by
  95 degrees) instead of treating dark ocean/land as nighttime. The established
  CIMSS/Kaba simulated-green coefficients remain in place; NOAA's AHI-derived
  green LUT is not bundled.
- The corrected daytime RGB receives a small saturation adjustment (`1.08`)
  and a GeoColor-only display white point (`0.85`) after the CIRA stretch. The
  latter raises the product into the full display luminance range without
  changing the deep-ocean black point or affecting nighttime RGB/other
  products. User confirmed the corrected hues, and the 2026-07-31 RealEarth
  comparison confirmed the final white-point lift.
- Low-sun follow-up (2026-07-31): a RealEarth comparison confirmed that the
  daytime cloud brightness and `0.85` white point match closely, but exposed
  crushed shadow detail over the late-day Northeast. Solar geometry confirmed
  that this area still had full daytime blend weight; the bounded Rayleigh
  estimate, not the 80-95 degree day/night blend, caused the darkening.
  Rayleigh correction now remains full through 60 degrees solar zenith and
  smoothsteps to zero by 85 degrees. The white point and day/night blend are
  unchanged.
- A same-frame GOES-18 follow-up showed that the ABI daytime midtones remained
  darker than RealEarth, especially for thin clouds approaching the eastern
  transition. ABI GeoColor now applies a mild `0.85` midtone gamma after the
  existing white-point transform. Zero and full-white endpoints are preserved,
  and non-ABI satellite recipes are unchanged. The GOES/default render
  namespace is `products-v8`; focused validation passes 21 GeoColor/GK2A tests
  plus Ruff.
  A cached 2026-07-31 22:36 UTC Northeast tile probe reduced near-black pixels
  from 67.1% to 22.5%. On the 2026-08-01 01:56 UTC GOES-18 cyclone tile, the
  ABI-only midtone lift raised mean luminance from 0.516 to 0.568 without moving
  the black/white endpoints. The user confirmed the final GOES-18 RealEarth
  comparison passed; the shared GOES-18/19 GeoColor visual gate is complete.
- Filled satellite imagery now renders with PNG alpha 255 and Leaflet layer
  opacity 1.0. Pixels outside valid coverage remain transparent. Sparse
  analytical products retain product-owned transparency: ADP uses
  confidence-graded alpha, AOD keeps its value-driven ramp, and FRP remains a
  translucent sparse overlay. Black Marble city lights are composited into the
  generated RGB before PNG alpha is assigned, so full tile opacity preserves
  rather than hides them. User confirmed the opacity correction.
- Current satellite tile namespaces are `products-v5` (GOES plus the default
  platform path), `products-ahi3` (Himawari-9), and `products-fci3`
  (Meteosat-12). These bumps prevent older partially transparent/corrected
  tiles from masking the new output. `weather.js?v=20260716d` forces the
  matching frontend opacity policy to load.

Completed enhancements (2026-07-16, GOES aerosol/fire products):

- Three new single-instant GOES ABI L2 products added for GOES-18/19:
  **AerosolDetection** (ABI-L2-ADP smoke & dust mask, confidence-graded),
  **AerosolOpticalDepth** (ABI-L2-AOD, high/medium DQF quality, with a discrete
  "No Data" legend swatch), and **FireRadiativePower** (ABI-L2-FDC). Gated
  GOES-only in `js/satellite-page.js`. See the dated "GOES aerosol and fire
  products: ADP, AOD, FRP" section below for the full implementation.

Planned/enhancement direction:

- Replace flat satellite tabs with filtered Region, Platform, Sector, and
  Product controls.

### Water page

V1 is active implementation.

Resolved follow-up (2026-07-19): the standalone Water page used obsolete core
shell class names and lacked an explicit two-column grid, producing the same
full-width-sidebar/map displacement first found during Workspace smoke testing.
The active core header/sidebar/tab/content/status/timestamp contracts and a
page-local 330 px sidebar + map grid now own the layout. Focused tests passed;
the user confirmed the baseline layout, River/Coastal/NDBC data, detail content,
and loading with no errors before the later UI follow-ups described below.

- `/water` serves `frontend/pages/water/water.html` on the Stage 2 core map,
  navigation, sidebar, status, and legend utilities without `js/weather.js`.
- `workers/water_worker.py` builds a local marker cache from:
  - NWS ArcGIS river gauges.
  - NOS CO-OPS active water-level stations.
  - NDBC latest observations.
- `/api/water/stations?bbox=...&max_sites=...&networks=...` filters the local
  marker cache by viewport and selected networks.
- `/api/water/stations/{site_id}` enriches river gauges through NOAA NWPS on
  click; CO-OPS stations now also receive a live CO-OPS API fetch (water level
  or current speed/direction) with a 3-minute in-memory cache; NDBC stations
  resolve from the local cache.
- River gauge colors are observed flood stage only: Major, Moderate, Minor,
  Action, or default no-flood/not-given.
- Coastal and NDBC stations have distinct marker styles and render in the
  dedicated `water-markers` Leaflet pane.
- The Water legend uses the shared collapsible core legend header/body shell.
  Labeled `River Flood Stage` and `Other Networks` rows track the active River,
  Coastal, and NDBC network controls, and the river row tracks the active
  Minimum Flood Stage threshold.
- A shared Region selector lives in the pinned sidebar header, defaults to
  CONUS, refits the map, closes selected-station detail, and reloads the new
  viewport immediately.
- Network and Map Overlay controls use shared-style section headings and compact
  full-width label/checkbox rows; the checkbox stays right-aligned despite the
  retained legacy Water stylesheet.
- River, CO-OPS, and NDBC marker selection uses a draggable map-level detail
  panel rather than a Leaflet popup. It closes through its button, Escape,
  Clear, or map navigation and invalidates an outstanding detail response.
- Leaflet world-wrap bbox edge cases are normalized/clamped instead of returning
  422s at world view.
- Basemap tile layers may wrap horizontally (`noWrap: false`) to avoid empty
  side gutters at low/world zooms. Weather overlays, vectors, value/place
  markers, and country borders remain single-instance overlays; dateline bbox
  edge cases are still normalized/clamped instead of duplicating data layers.

Completed enhancements (2026-06-28):

- River Flood Filter pills (All / Action+ / Minor+ / Moderate+ / Major) added to
  the water sidebar. Client-side filter; coastal and NDBC markers always remain
  visible. Pills are hidden when the River network is unchecked and the filter
  resets to All automatically.
- Stage gauge bar added to river gauge details when flood threshold data is
  available. Shows color-coded zones (normal / action / minor / moderate / major)
  with a white current-stage marker and a threshold summary line.
- CO-OPS click enrichment: on-click live fetch from the CO-OPS API populates
  Water Level (or Current Speed / Direction) in the coastal station detail panel.
- NDBC buoy detail replaced flat reading rows with a grouped card layout:
  Wind / Waves / Atmos / Temp / Other.
- Removed `impacts`, `historic_crests`, and `recent_crests` parsing from the
  NWPS detail fetch path (`_parse_nwps_gauge`); the `_nwps_crests` helper was
  deleted.

Future Water enhancements, possibly V2:

These are deferred from the active V1 agenda unless a separate Water V2 slice is
started.

- Clustering or density controls if full-cache rendering is heavy.
- Optional WPC Excessive Rainfall Outlook and Real-Time Flood Impact overlays.
- USGS streamflow percentile context (WaterWatch API) on river gauge click.
- Interactive NWPS hydrograph chart replacing the static image.

### WPC page

Base WPC product page is complete.

- Source decision: WPC KML/KMZ feed is the primary source.
- Completed product groups:
  - Excessive Rainfall Outlook, Days 1-3.
  - QPF: 6-hour, 24-hour, and multi-day products through Day 7.
  - Winter Weather: snow greater than 4, 8, and 12 inches plus ice greater than
    0.25 inches, Days 1-3.
  - Five-Day River Flood Outlook.
- Completed operational behavior:
  - Cache-first worker, API, catalog, and 30-minute scheduled task.
  - Per-product source availability, stale metadata, and last-valid-cache
    preservation.
  - WPC-authored no-significant-area overlays for ERO and Winter products.
  - Responsive WPC legends, opacity control, request sequencing, and tab cleanup.
- Manual browser smoke completed by the user on 2026-06-18.

WPC expansion status:

- Active MPDs are code-complete; the prior note still marked manual browser
  smoke pending.
- WPC UI polish is complete: group pills, day pills, sub-tabs, reliability bar,
  default sub-tab selection, and shared bottom scrubber.
- Surface Analysis and Forecast overlays are complete using WPC transparent PNG
  products and KML bounds.

Future WPC increments:

1. Probabilistic QPF.
2. Expanded Days 1-3 winter guidance.
3. Day 4-7 winter outlook.
4. Day 1-3 Significant Weather.
5. Day 3-7 Heat Index.

Deferred:

- SigWx mixed-geometry products remain optional.

### Satellite tab UX: blank-default / no-auto-load — completed 2026-06-30

Previously the satellite tab defaulted to GOES-19 CONUS and began loading tiles
immediately on page load or tab entry, wasting resources when the user intended
to view a different platform.

Changes:

- **`weather.html`**: both `#weather-satellite-sat-id` and
  `#weather-satellite-sector` selects now have a `<option value="" selected>—
  Select —</option>` as their first option. The GOES-19 and CONUS buttons have
  `aria-selected="false"` by default. Browser native form restoration persists
  the blank selection across hard refreshes — no `localStorage` code needed.
- **`js/satellite-page.js`**:
  - `activeSatId()` and `activeSector()` return `''` when nothing is selected
    (fallbacks to `'goes19'`/`'CONUS'` removed).
  - `syncSectorVisibility()` returns early when `satId` is blank.
  - `syncChannelVisibility()` skips the channel fallback reset when `satId` is
    blank (channel stays at its last value).
  - The `change` event handler on all three selects returns early (after calling
    `clearSatelliteLayerPool`) when either `satId` or `sector` is blank.
- **`js/weather.js`**:
  - `_fetchSatelliteFrameSet` throws `'No satellite or sector selected.'` before
    making any API call when either `_activeSatelliteSatId()` or
    `_activeSatelliteSector()` is blank. This is the single choke point that
    prevents tile requests with `sat_id=&sector=` (which returned 500s).
  - Tab-activation site (satellite tab entry): `loadCurrentFrame` and
    `loadScrubberFrames` are skipped when sat or sector is blank.
  - `_startSatelliteAutoRefresh` and the visibility-change handler already
    guarded on `_satelliteFrames.length > 0`; the `_fetchSatelliteFrameSet`
    throw provides defense-in-depth for any other path.

User experience: on page load, the satellite tab shows the map with no tiles
and both selects at `— Select —`. Selecting a satellite AND a sector triggers a
normal frame load. Deselecting either (returning to `— Select —`) clears the
tile pool. Channel 13 remains the default and does not need a blank option.

### Satellite warm/render lifecycle note — added 2026-07-01

Satellite tile generation can appear to continue after a Ctrl+C and server
restart because the work is cache-backed and restart-triggered:

- `/api/satellite-v2/tile/{z}/{x}/{y}` calls
  `satellite_v2.service.resolve_tile(..., allow_render=True)`. Missing or
  invalid tiles submit an on-demand render to the satellite live tile thread
  pool, so reopening the same product after restart can resume filling missing
  tiles from existing source/catalog cache.
- `app_core.runtime.shutdown_runtime()` calls
  `satellite_v2_service.shutdown_live_tile_pool()` and `stop_scheduler()`.
  These stop server-owned live tile threads and in-process scheduler work on
  app shutdown, but they do not delete cache artifacts.
- OS Task Scheduler workers are separate from the Uvicorn/web process. Stopping
  the server does not stop enabled scheduled tasks such as satellite cache
  refresh jobs. To prove all work is stopped, inspect/stop matching dashboard
  Python processes and relevant Windows scheduled tasks.

### Satellite runtime config consolidation — added 2026-07-04

Satellite backend runtime policy is now centralized in
`config/satellite_v2_config.py`:

- `SATELLITE_V2_LIVE_TILE_RENDER_WORKERS` replaces the hardcoded live tile
  thread count in `satellite_v2/service.py`.
- `SATELLITE_V2_LIVE_SUPERTILE_RADIUS` controls live on-demand neighbor fill.
  The default radius is `1`, so one visible cache miss renders a 3x3 tile
  neighborhood after the requested tile has rendered, skipping already-valid
  tiles and negative-cache markers.
- `SATELLITE_V2_ON_DEMAND_CATALOG_HOURS`,
  `SATELLITE_V2_ON_DEMAND_CATALOG_MAX_FRAMES`,
  `SATELLITE_V2_LEGEND_ANCHOR_COUNT`, and
  `SATELLITE_V2_LEGEND_TICK_COUNT` replace local service constants.
- `SATELLITE_V2_NETCDF_CACHE_SIZE` and
  `SATELLITE_V2_RENDERER_CACHE_SIZE` replace renderer-local env parsing.
- `SATELLITE_V2_GOES_FULLDISK_MAX_GRID`, `SATELLITE_V2_AHI_MAX_GRID`, and
  `SATELLITE_V2_FCI_MAX_GRID` are the provider-specific Full Disk source-grid
  caps for GOES, Himawari AHI, and Meteosat FCI. Provider/parser modules import
  these values directly, so future high-resolution tuning should start in this
  config file.
- Frontend satellite animation prefetch is cache-only as of 2026-07-04. The
  active Leaflet layer still live-renders visible tile misses, but background
  prefetch requests use `render_live=0` so Himawari/Meteosat Full Disk frame
  setup does not compete with the first visible static image.
- Live supertile testing passed for Himawari Full Disk, GOES CONUS, and GOES
  Meso1 Channel02. A bug found during testing where requested invalid/off-disk
  tiles could keep filling neighbors and produce a 500 was fixed; requested
  invalid tiles now return the normal transparent invalid response, and neighbor
  fill errors are counted as `supertile_errors` without poisoning the visible
  tile request.

### Satellite rapid-sector worker — added 2026-07-04

A new isolated rapid warmer replaced the broad Satellite v2 scheduled workers:

- Entry points: `satellite_v2/rapid_worker.py` and
  `workers/satellite_v2_rapid_worker.py`.
- Default jobs: GOES-19/18 `MESO1`/`MESO2`, Himawari-9 `JAPAN`, and
  Meteosat-11 `RSS`.
- Default products: `Channel02` and `Channel13`.
- Default policy: latest 12 frames, low tile-worker count (`2`), cache-first
  canvas warming, and small per-sector zoom targets (`MESO` 7/8, `JAPAN` and
  `RSS` 6/7).
- Himawari `TARGET` is intentionally not warmed by default because it is
  dynamically retasked and the catalog does not yet publish per-frame bounds.
  Add it only after implementing target-frame bounds or accepting a broad
  guessed warm box.
- Full Disk and broad CONUS prewarming remain excluded; those paths should use
  live rendering, supertiles, and cross-session cache reuse.
- Removed old broad-worker modules/launchers and old worker config profiles:
  `satellite_v2/worker.py`, `satellite_v2/worker_new.py`,
  `workers/satellite_v2_worker.py`, `workers/satellite_v2_meso_worker.py`,
  `workers/satellite_v2_light_composites_worker.py`, and
  `workers/satellite_v2_geocolor_worker.py`.
- `workers/scheduler.py` now registers only the rapid worker in the optional
  in-process fallback scheduler. `workers/_freshness.py` now expects only the
  `satellite_v2_rapid` sentinel for Satellite v2. `tools/install_tasks.ps1`
  registers `Wx-Dashboard-Satellite_v2_rapid` and unregisters legacy
  `Wx-Dashboard-Satellite_v2*` broad-worker task names when run.

### Meteosat source-prefetch worker — added 2026-07-04

Cold Meteosat loads took 3-4 minutes because the first product on a frame
pays the full EUMETSAT download (~790 MB FCI chunk set per Meteosat-12 frame,
~270 MB SEVIRI `.nat` per Meteosat-9 frame). EUMETSAT frames are all-channel
bundles, so one prefetched frame warms every product — switching channels on
a warm frame is near-instant (parse + warp only).

- New `satellite_v2/meteosat_prefetch_worker.py` +
  `workers/satellite_v2_meteosat_prefetch_worker.py` entrypoint. Download-only:
  fills the shared source cache via `providers.download_product_source_frames`;
  renders nothing.
- Per run: downloads the newest N missing frames (default 2 = current + 1),
  then up to 1 oldest missing frame inside the lookback window (default 6 h),
  so animation depth backfills gradually across runs. Completeness checks use
  the FCI `manifest.json` (all chunks present) or the SEVIRI `.nat` size.
- Prunes source frame dirs older than the keep window (default 7 h). ~6 h of
  both platforms ≈ 35 GB of source cache at steady state.
- Config in `config/satellite_v2_config.py`
  (`SATELLITE_V2_METEOSAT_PREFETCH_*`): jobs (meteosat12/meteosat9 FULLDISK),
  frames/backfill per run, lookback, keep hours, fresh window. All
  env-overridable.
- Scheduled task `Wx-Dashboard-Satellite_v2_meteosat_prefetch` (10 min cadence,
  25-min ExecutionTimeLimit — `install_tasks.ps1` now supports per-task
  `TimeLimit`). Registered ENABLED by default. Also added to the in-process
  fallback scheduler and `_freshness.py` health thresholds (45 min, generous
  because a cold backfill run legitimately downloads for 15+ min).
- Interrupted runs are safe: per-file atomic downloads (tmp + rename) and the
  FCI manifest is only written after all chunks land, so a killed run resumes
  where it left off.
- Himawari-9 deliberately excluded: AHI segments are per-band files (no
  all-channel bundle bonus) and per-band downloads are small; revisit only if
  Himawari cold loads become a complaint.
- Validated against the live EUMETSAT catalog: frames downloaded during the
  2026-07-04 browser session report cached=True; missing frames report False.
- User browser smoke passed 2026-07-04 (late evening): Meteosat-12 Channel02
  FULLDISK on a prefetched frame rendered at ~250 ms/tile ("faster by
  minutes" vs the cold-download flow). Off-disk tiles at low zoom correctly
  return the negative-cached invalid/transparent response — `result=invalid`
  in the tile log for space-only tiles is expected, not an error.
- Post-install fix: the EUMETSAT catalog search returns frames older than the
  requested lookback window, so the backfill was repeatedly downloading
  frames the keep-window prune deleted on the same run (~790 MB wasted per
  run). The worker now filters the frame list to the lookback window before
  selecting downloads.

Optional future CONUS light-warm plan:

- Keep it separate from the rapid default. CONUS currently works well with live
  rendering, supertiles, and cache reuse.
- If first-load latency becomes worth the background cost, add a disabled/opt-in
  light worker for GOES-19/18 `CONUS` only, latest 1-2 frames, `Channel02` and
  `Channel13`, zooms `(5, 6)`, and `tile_workers=1-2`.
- Do not reintroduce broad CONUS product/profile warming; the light worker
  should remain cache-first, current-frame biased, and easy to disable.

### Global satellite coverage

#### Himawari-9 — removed 2026-07-01

The Himawari-9 pipeline (built 2026-06-29/30) was fully removed. It relied on
satpy/pyresample to ingest raw AHI HSD segments and resample them to an
intermediate equirectangular lat/lon npz grid before tiling. Two problems
drove the removal rather than an incremental fix:

- `dask`'s default threaded scheduler grabs all CPU cores (32 on this host)
  for every single satpy `Scene.load()`/`.resample()` call, with no cap
  configured. Ingest calls already ran inside our own on-demand
  `ThreadPoolExecutor`, so concurrent new-frame requests (e.g. scrubber
  prefetch) caused massive thread oversubscription — tens to 100+ threads
  fighting over 32 physical cores — which stalled the entire dashboard
  process, not just the satellite tab.
- More fundamentally, satpy's resample-to-lat/lon-grid approach was
  architecturally heavier than necessary: AHI HSD files are natively
  geostationary with a fixed pixel grid (COFF/CFAC/LOFF/LFAC), the same way
  GOES ABI NetCDF is, so the ingest could instead parse the raw format
  directly and reuse the existing fast GOES `SourceRaster`/GDAL-warp render
  path with no satpy/pyresample/dask involved at all.

Removed: `satellite_v2/provider_himawari.py`, `satellite_v2/latlon_grid.py`,
`satellite_v2/worker_himawari.py`, `workers/satellite_v2_himawari_worker.py`,
the `SatelliteTileRenderer.from_latlon_npz` classmethod and
`render_frame_tile_himawari`/`warm_himawari_frame_tiles`/
`_get_or_load_himawari_renderer` in `satellite_v2/tiler.py`, all Himawari/AHI
config in `config/satellite_v2_config.py` and `config/satellite_platforms.py`
(including the `JAPAN` sector), the `Satellite_v2_himawari` scheduled task
entry in `tools/install_tasks.ps1`, and all frontend Himawari references in
`js/satellite-page.js` / `js/weather.js` / `weather.html`. Himawari cache
directories under `cache/satellite/{catalog,source,tiles}/**himawari9**` were
deleted. GOES (`goes18`/`goes19`) is unaffected — it never used the
lat/lon-grid path.

A native-AHI-format rewrite (no satpy) remains a real option if Himawari
coverage is revisited, but has not been started.

#### Himawari-9 — rebuilt on native AHI HSD parser 2026-07-02

Himawari-9 FULLDISK is live again on a clean-sheet native pipeline with zero
satpy/pyresample/dask involvement:

- `satellite_v2/ahi_hsd.py` (new): pure-numpy JMA HSD parser. Reads header
  blocks 1/2/3/5/7 (basic/data/projection/calibration/segment), decompresses
  bz2 transparently, calibrates counts to GOES-CMI-equivalent semantics
  (reflectance factor for bands 1-6 via the c' coefficient, brightness
  temperature for bands 7-16 via inverse Planck + JMA quadratic correction
  using constants stored in block 5), stitches the 10 FLDK segments, and
  returns a north-up grid + rasterio geos transform/CRS
  (`+proj=geos +h=35785863 +lon_0=140.7 +sweep=y`). Two hard guards:
  - 1 km/0.5 km bands are strided to the 2 km 5500-px grid on load
    (`AHI_MAX_GRID`) — the 484 MP FULLDISK visible OOM class is
    structurally impossible.
  - A geostationary Earth-visibility mask (ray-ellipsoid discriminant) NaNs
    deep-space pixels; JMA leaves instrument noise counts (~60-165 K after
    calibration) off-Earth instead of flagging them like GOES CMI does.
- `satellite_v2/provider_himawari.py` (new): `noaa-himawari9` S3 listing
  (`AHI-L1b-FLDK/YYYY/MM/DD/HHMM/`, 10-minute timeslots), complete-slot
  detection (all 10 segments present), FULLDISK-only validation. A frame's
  `source_keys` store the S01 segment key per source channel; the other
  segment keys are derived from the filename `SnnNN` token at download time.
- `satellite_v2/providers.py` (new): provider dispatch by platform
  descriptor (`config/satellite_platforms.py`, first real consumer of the
  Phase-1 abstraction). `catalog.py`/`service.py`/`tiler.py` now import
  `list_recent_frames`/`download_product_source_frames` from here.
- `satellite_v2/renderer.py`: `_load_source_raster` dispatches on `.DAT`/
  `.DAT.bz2` to an AHI loader that globs sibling segments from the frame's
  source-cache dir and wraps them in the same `SourceRaster`; the GDAL-warp
  `render_zoom_canvas` path is untouched and shared with GOES. The renderer
  LRU keyed on the S01 file signature keeps the parsed 121 MB grid in memory
  across tiles of the same frame (~3.8 s cold incl. download, ~65 ms after).
- Config: `himawari9` added to `SATELLITE_V2_SUPPORTED_SATELLITES` and
  `satellite_platforms.py` (implemented, FULLDISK only, lon_0 140.7,
  provider `aws_himawari`); `AHI_BAND_FOR_ABI_CHANNEL` maps ABI-named
  product keys to AHI bands (C02→B03 red visible, C03→B04 veggie, others
  1:1) so all product keys stay ABI-named everywhere; render version for
  himawari9 is `products-ahi1`.
- Frontend: Himawari-9 platform button + select option restored in
  `weather.html`, `himawari9` added to `PLATFORM_SECTORS` (FullDisk only) and
  `IMPLEMENTED_SATELLITES` in `js/satellite-page.js` (`?v=20260702c`). All
  channels/composites are enabled — every ABI source channel used by the
  dashboard products has an AHI equivalent. Dead `Japan` sector option
  removed from the sector select.
- Operational model: on-demand rendering only (same as GOES FULLDISK — no
  scheduled warm task, no worker profile). Warm paths are unreachable for
  himawari9, so the GOES-centric FULLDISK sector bounds are never consulted
  for it.

Validation (2026-07-02, live data): header fields match the JMA spec across
2 km and 0.5 km grids; B13 BT range 185.9-300.6 K after the Earth mask; B03
reflectance 0-1.19 with the sunlit crescent on the correct (east) limb;
geolocation checked against basemap coastlines (Australia, Timor, PNG) with
no flip/mirror/offset; end-to-end catalog→download→tile through
`service.resolve_tile` with disk-cache hit on repeat; GOES listing regression
passed through the new dispatch layer. Standalone validator:
`tools/validate_ahi_native.py --band N --out DIR`. Browser smoke is
user-owned and still pending.

Planned:

- Add Meteosat platforms by operational role:
  - Meteosat-12: Europe/Africa full disk.
  - Meteosat-11: rapid-scan Europe and North Africa.
  - Meteosat-9: Indian Ocean.
- Do not expose Meteosat-10 initially.
- Generalize the GOES-specific provider/channel/projection/sector/cache model
  into platform descriptors and capability matrices.
- Use optional server-side EUMETSAT credentials and hide unavailable platforms
  cleanly when credentials are absent.

Current international-satellite product direction:

- Finish the current non-GOES platforms before adding more sources:
  Himawari-9, Meteosat-9, and Meteosat-12 should expose a small standard
  product set rather than every possible raw channel/RGB.
- Standard non-GOES product set, in priority order: Visible, Enhanced IR,
  Water Vapor, Shortwave IR/Fire, Night Microphysics, Dust, Ash, and SO2.
  Each product must have explicit per-instrument channel mapping and at least
  one proof render before appearing in the UI.
  Status 2026-07-10: 7 of 8 complete for Meteosat-9/11/12 (see the
  "Meteosat standard composites" section below). SO2 is intentionally
  dropped for Meteosat: the recipe's red beam is `C09 − C10`, SEVIRI aliases
  both to WV_073 (red ≡ constant), and FCI cannot map C09/C10 faithfully
  without corrupting the exposed Channel09 WV scalar. Doing SO2 right needs
  per-instrument recipe-level channel overrides — V2 if ever.
- Defer CIRA GeoColor / True Color / Natural Color / other RGB parity to V2.
  Full-disk RGB source loading can be expensive, especially for FCI and
  high-resolution visible channels, so RGB should wait until standard products,
  auto-centering, and named extent presets are stable.
- DONE 2026-07-02: Added frontend named view presets for satellite
  platform/sector switches. `js/satellite-page.js` now maps platform+sector
  pairs to fitted map bounds for GOES Full Disk/CONUS/Meso defaults,
  Himawari-9 Full Disk, Meteosat-12 Full Disk, and Meteosat-9 Full Disk.
  `js/weather.js` exposes the existing Leaflet map through
  `fitSatelliteViewPreset(...)`, and `weather.html` bumps
  `satellite-page.js` to `?v=20260702e`. Satellite platform changes now clear
  the sector selection first, so moving between platforms such as Himawari-9
  and GOES-18 does not start catalog/tile work until the user explicitly picks
  a sector. The auto-fit runs only after a sector is selected; product/channel
  changes preserve user pan/zoom while browsing products.
- DONE 2026-07-02: Added a user-facing `View` select separate from data
  sectors. The control is filtered by selected platform and fits named extents
  without triggering catalog or tile generation. Sector selection still
  auto-selects the matching default view. `weather.html` now loads
  `satellite-page.js?v=20260702h`. Browser testing tightened the Meteosat-12
  Europe/Africa view from the full disk footprint to a practical
  `[-38,-35]`-to-`[62,48]` inspection extent so it does not zoom out to a
  near-world view. Browser smoke passed for Himawari-9, Meteosat-9, and
  Meteosat-12 platform selection, sector clearing, view presets, and first
  tile load.
- DONE 2026-07-03: Warm/prefetch planning is viewport-aware without blocking
  direct tile requests. Frontend animation prefetch uses current map bounds
  plus an explicit one-tile buffer and reschedules on `moveend`/`zoomend`.
  Direct Leaflet `/api/satellite-v2/tile/{z}/{x}/{y}` requests still render
  normally if requested. Backend warm planning now has an opt-in bounds filter:
  `satellite_v2.tiler.planning_tile_coords(...)` keeps existing sector-wide
  behavior by default, while `warm_frame_tiles(...)` /
  `warm_frame_tiles_from_canvas(...)` accept `tile_bounds` + `tile_buffer`.
  Explicit worker runs can pass named-view bounds with
  `--bounds west,south,east,north --tile-buffer 1`; scheduled runs pass no
  bounds and are unchanged until intentionally configured.
- Possible current-plan or V2 enhancement: reuse the same viewport-aware
  satellite bounds logic from the Tropical page. When a user opens an active
  system, Tropical could derive a storm-centered extent from the latest
  reported fix (or track/cone bounds), fit the map there, and let live
  on-demand satellite rendering plus animation prefetch fill only that
  viewport+buffer. If first-frame readiness proves too slow, add a thin async
  bounded warm helper later that accepts storm bounds, selected satellite,
  sector, product, and frame count. Prefer the live-on-demand version first
  because it needs less orchestration and cannot warm stale or wrong storm
  locations.
- GK2A + GMGSI expansion is complete under the archived
  `docs/archive/satellite-platform-expansion-plan.md`.
  - GK2A Phase 0 adds the public `noaa-gk2a-pds` AMI Full Disk Channel 13 path:
    10-minute discovery, atomic source download, packed-pixel quality masking,
    file-coefficient brightness-temperature calibration, native GEOS
    georeferencing, isolated `products-ami1` tiles, and an Asia-Pacific page
    preset. The focused gate passes 67 tests, and a live listing plus
    real-source PNG render pass. The full suite passes 318 tests plus 42
    subtests with the two known stale Workspace assertions. User-owned browser
    acceptance passed 2026-07-29: all default-zoom frames loaded quickly, and
    playback continued while newly requested z9 frames also loaded quickly.
    Phase 0 is closed.
  - GK2A Phase 1 is implemented after explicit approval. The standalone page
    filters GK2A to ten mapped direct products: `Channel01`, `Channel02`,
    `Channel03`, `Channel05`, `Channel07`, `Channel07Fire`,
    `Channel08RAMSDIS`, `Channel09RAMSDIS`, `Channel13`, and `Channel14`.
    Visible/near-IR reflectance calibration, bounded high-resolution reads,
    and the additional thermal mappings have live-source proof renders. The
    largest test used a 473,301,589-byte Channel 02 source, produced a bounded
    7333 x 7333 working raster in 5.538 seconds, rendered a proof tile in
    0.182 seconds, and peaked near 735.5 MiB working set. The focused gate
    passes 68 tests. The latest full-suite run has 321 passing tests plus 42
    passing subtests; the two known stale Workspace assertions and one
    unrelated concurrent shared-border-default assertion fail.
  - User-owned Phase 1 default-zoom acceptance passed 2026-07-29. The first
    Channel 02 z8 smoke exposed two shared animator defects: Leaflet could send
    fractional zoom `7.5` to the integer-only tile route, producing 422s, and
    retained invisible layers could initiate historical live renders during
    zoom before the selected newest frame completed. The correction snaps and
    sanitizes Satellite zooms to integers and detaches inactive pooled layers
    at zoom start. A focused correction gate passes 27 tests plus JavaScript
    syntax checks. Codex browser regression on a 12-frame GOES-19 loop reached
    z8 with only the selected newest frame attached, 16 integer-z8 tile
    requests, and no fractional URLs. The user-owned GK2A Channel 02
    z8/playback re-smoke then passed with no recurring fractional-zoom 422s,
    newest-frame-first generation, and continuous playback. Phase 1 is closed.
  - GK2A Phase 2 composites are implemented and closed after explicit approval.
    The selector exposes the six physically
    mapped existing recipes: `GeoColor`, `GeoColorBlkMar`, `TrueColor`,
    `NaturalColor`, `DayCloudPhase`, and `DaySnowFog`; recipes needing unmapped
    AMI bands remain hidden. Composite discovery requires a common timestamp
    across all recipe bands. The existing Black Marble loader now targets the
    tracked `BlackMarble_2016_3km_geo.png` instead of the never-present `.tif`,
    and GK2A alone advances to `products-ami2`. Synthetic render proofs for all
    six recipes, capability/common-time coverage, JavaScript syntax, and the
    focused Satellite gate pass. User-owned browser acceptance passed for all
    six products: fast renders, no GeoColor Black Marble animation flicker or
    inter-frame blinking, and no API-terminal or browser-console errors.
  - NOAA GMGSI Phase 3 is implemented separately from GK2A. The anonymous
    `noaa-gmgsi-pds` provider lists one hourly global frame and exposes only
    visible (`Channel02`), shortwave IR (`Channel07`), water vapor
    (`Channel09RAMSDIS`), and longwave IR (`Channel13`) under `gmgsi/GLOBAL`.
    Its dedicated loader handles the 4,999 x 3,000 coordinate grid, Date Line
    wrap, quality mask, visible scaling, and mode-A IR/WV count-to-Kelvin
    conversion. Tiles use the independent `products-gmgsi1` namespace. A
    current `20260731T200000Z` listing/download/nonblank-render proof passes for
    all four products. Ruff, compilation, JavaScript syntax, and 63 focused
    Satellite tests pass. The full suite has 336 passing tests plus 42 passing
    subtests and retains only the three stable unrelated failures after a
    transient coordinator timing failure passed in isolation. User-owned
    browser acceptance rendered every current frame but found the default
    one-hour catalog capped at one frame. The Global budget now includes the
    interval-start frame (`hours + 1`) so the default view has a two-frame
    animation. A live corrected-window probe returned chronological 19Z and
    20Z frames for all four products. The corrected user-owned re-smoke
    generated and played a three-hour Channel 13 animation. The user accepted
    this representative shared-path result without separately looping Channels
    02, 07, and 09; all four current frames had already rendered. GMGSI
    animation acceptance passed and Phase 3 is closed.

#### Meteosat-9 — native SEVIRI `.nat` validation completed 2026-07-02

Meteosat-9 IODC is live on the native Satellite v2 path:

- `satellite_v2/provider_eumetsat.py`: EUMETSAT OAuth/search/download works
  with credentials loaded explicitly from `F:\Python\dashboard_2026\.env`
  (supports `EUMETSAT_CONSUMER_*` and `WX_EUMETSAT_CONSUMER_*`). The provider
  downloads the HRSEVIRI-IODC `.nat` entry and stores one shared SEVIRI source
  bundle per frame.
- `satellite_v2/seviri_nat.py` (new): pure-numpy MSG native parser for 3712 px
  VIS/IR full disk. It reads the archive/header fields needed for Meteosat-9,
  unpacks 10-bit channel lines, flips the native south/east grid to north-up
  west-east, calibrates IR channels to brightness temperature and visible
  channels to GOES-like reflectance factors, and returns a rasterio geos
  transform/CRS (`+proj=geos +h=35785831 +lon_0=45.5 +sweep=y`).
- `config/satellite_platforms.py` and `js/satellite-page.js`: Meteosat-9 is
  marked implemented. The frontend product select is filtered to
  SEVIRI-compatible products only.
- `satellite_v2/service.py`: tile diagnostics now report the platform provider
  (`eumetsat`) instead of the old hardcoded `aws` label.

Validation (2026-07-02, live data): downloaded
`MSG2-SEVI-MSG15-0100-NA-20260702185739.917000000Z-NA.nat` (271,175,723 bytes)
and parsed Channel 13/IR_108 with BT range 182.70-307.55 K, mean 278.52 K,
74.0% finite disk coverage. Native unpack/calibration was numerically checked
against Satpy for the same file before removing Satpy from the parser path.
Standalone proof command:
`tools/validate_seviri_native.py --nat cache\satellite\validation\eumetsat\satellite\source\meteosat9\FULLDISK\SEVIRI\20260702T184500Z\MSG2-SEVI-MSG15-0100-NA-20260702185739.917000000Z-NA.nat --out cache\satellite\validation\seviri_proofs`.
Proof images show correct disk/India coastline alignment with no flip or
offset. End-to-end backend smoke passed through
`service.get_catalog_payload(...)` and `service.resolve_tile(...)`, rendering
tile `meteosat9/FULLDISK/Channel13/20260702T190000Z/5/21/15.png` (97,803
bytes) and then cache-hitting it with provider `eumetsat`.

#### Meteosat-12 — FCI Full Disk direct products validated 2026-07-02

Meteosat-12 Full Disk is live for the first direct FCI scalar products:

- `satellite_v2/provider_eumetsat.py`: `meteosat12` uses collection
  `EO:EUM:DAT:0662`. Unlike Meteosat-9, each frame is a set of numbered
  NetCDF `CHK-BODY` chunks; the provider downloads all body chunks for the
  selected full-disk frame into a shared `FCI` source-cache directory.
- `satellite_v2/fci_nc.py` (new): stitches FCI body chunks for one requested
  channel, calibrates IR radiance to brightness temperature using per-file
  conversion constants, flips the native grid to north-up west-east, and
  returns a rasterio geos transform/CRS (`+proj=geos +h=35786400 +lon_0=0
  +sweep=y`).
- FCI source-channel mapping now covers direct IR/WV channels needed for the
  standard scalar product set: ABI `Channel07` -> FCI `ir_38`, `Channel08` ->
  `wv_63`, `Channel09` -> `wv_73`, `Channel10` -> `ir_97`, `Channel11` ->
  `ir_87`, `Channel13` -> `ir_105`, `Channel14` -> `ir_123`, and
  `Channel15` -> `ir_133`. `js/satellite-page.js` exposes Meteosat-12
  `Channel07`, `Channel07Fire`, `Channel08RAMSDIS`, `Channel09RAMSDIS`, and
  `Channel13` only. Composite products that become technically source-mapped
  (AirMass, Night Microphysics, Dust, Ash, SO2, etc.) stay hidden from the UI
  until each has a proof render. RSS remains deferred.
- `config/satellite_platforms.py`: Meteosat-12 is marked implemented with
  instrument `FCI`, provider `eumetsat`, sector `FULLDISK`.

Validation (2026-07-02, live data): cataloged
`EO:EUM:DAT:0662` frame `20260702T190000Z` and downloaded 40 FCI body chunks
totaling 791,937,141 bytes. The assembled `ir_105` grid is 5568x5568 with BT
range 182.94-308.11 K, mean 280.61 K, 74.5% finite disk coverage. End-to-end
backend smoke passed through `service.resolve_tile(...)`, rendering
`meteosat12/FULLDISK/Channel13/20260702T190000Z/4/8/6.png` (82,043 bytes)
and cache-hitting it with provider `eumetsat`. Coastline proof image:
`cache\satellite\validation\fci_proofs\fci_channel13_20260702T190000Z_disk_z3.png`;
visual check shows Europe/Africa alignment with no obvious flip or offset.
Cached extraction smoke (2026-07-02 frame `20260702T174500Z`) confirmed
`Channel07`/`ir_38`, `Channel08`/`wv_63`, `Channel09`/`wv_73`, and
`Channel13`/`ir_105` all load as 5568x5568 grids with 74.5% finite disk
coverage before UI exposure.
Browser smoke passed for selecting Meteosat-12 in the Satellite tab.

#### Meteosat pipeline efficiency pass + FCI orientation fix — 2026-07-03

Efficiency changes mirroring the Himawari optimizations:

- `satellite_v2/provider_eumetsat.py`: `_download_fci_chunks` now writes a
  `manifest.json` (chunk filename list) into the frame's `FCI` source dir
  after all chunks are verified on disk. When the manifest is present and
  every listed chunk exists, the loader returns immediately (~2 ms) instead
  of re-running the EUMETSAT OpenSearch on every renderer load — previously
  every FCI renderer construction made a live API call even on full cache
  hit. An incomplete manifest or missing chunk falls through to the normal
  search+download path, so interrupted downloads can never render partial
  strips. Missing chunks download in parallel (`_FCI_DOWNLOAD_WORKERS = 4`),
  cutting the ~792 MB / 40-chunk cold-frame download several-fold. SEVIRI
  (.nat) needed no changes: single file, exists-check before download.
- `satellite_v2/fci_nc.py`: `FCI_MAX_GRID = 5500` stride cap, mirroring
  `AHI_MAX_GRID` and the GOES FULLDISK stride. Strips are strided on load,
  so FDHSI 1 km channels (vis_06 = 11136² ≈ 500 MB float32) assemble at
  5568² and the full-resolution array is never materialised. 2 km IR
  channels are unaffected (stride 1). Strided sampling verified bit-exact
  against full-resolution assembly + decimation on live cached vis_06 data.
  This unblocks the planned `Channel02` → `vis_06` exposure memory-wise.

Correctness bug found during verification — FCI disk was east-west MIRRORED:

- The original loader flipped both axes (`[::-1, ::-1]`) assuming the MSG
  SEVIRI south-east origin. FCI L1c actually stores columns already
  west→east; the x coordinate variable's positive fixed-grid scan angle
  points WEST (opposite PROJ geos +x=east), so the descending x axis had
  masked the mirror. All Meteosat-12 tiles rendered before 2026-07-03 were
  east-west mirrored (the 2026-07-02 coastline proof was misjudged).
- Fix in `load_fci_raster`: flip rows only (`[::-1, :]`) and negate the x
  axis (`-(x_raw * height)`) instead of reversing it — negation is also
  exact for strided offset-center sampling where reversal would shift the
  grid by one source pixel.
- Verified: Meteosat-12 ir_105 vs Satpy-validated Meteosat-9 IR_108 for the
  same 17:45 UTC slot warped to one lon/lat grid correlates 0.933 as-is
  (0.188 mirrored; the pre-fix code scored the reverse). Solar terminator
  checks on 17:45/19:45/00:45 UTC frames put the lit side west+north as
  physics requires; the 00:45 disk is fully dark.
- `config/satellite_v2_config.py`: `SATELLITE_V2_RENDER_VERSION_METEOSAT12 =
  "products-fci1"` orphans all mirrored cached tiles; GOES/Himawari/
  Meteosat-9 tile caches are untouched (SEVIRI orientation was validated
  numerically against Satpy and is correct).

Browser smoke for Meteosat-12 after the mirror fix completed 2026-07-03.
Initial animation load (6 frames over Africa, zoom 5) takes ~60 sec because
each frame requires an independent EUMETSAT catalog search + 40-chunk download
(~10–15 sec per frame); GOES/Himawari benefit from AWS S3 edge caching that
EUMETSAT lacks. Manifest cache accelerates repeat plays of the same timeslot
and manual scrubbing. Tiles persist and render correctly post-fix.

#### Meteosat standard composites: Night Microphysics, Dust, Ash — 2026-07-10

The last three implementable products of the standard non-GOES set are live
on Meteosat-9, Meteosat-11, and Meteosat-12. All three are IR-only, so they
work day and night and add **no download cost** — every source channel
already ships inside the frame's single `.nat` (SEVIRI) or shared FCI chunk
set; only the extra channel extraction and composite math are new.

- `config/satellite_v2_config.py`: FCI aliases corrected — `Channel14 →
  ir_105` (was `ir_123`) and `Channel15 → ir_123` (was `ir_133`, the 13.3 µm
  CO2 band, physically wrong for split-window recipes). With the aliases,
  the goes2go Night Microphysics / Dust / Ash recipes reduce exactly to the
  canonical EUMETSAT MTG RGBs, mirroring the SEVIRI table's `C13/C14 →
  IR_108` trick. Nothing exposed or prefetched used FCI C14/C15, so no
  render-version bump was needed.
- `js/satellite-page.js` (`?v=20260710b`): `NighttimeMicrophysics`, `Dust`,
  `Ash` added to `PLATFORM_CHANNELS` for `meteosat9`, `meteosat11`, and
  `meteosat12`.
- SO2 is intentionally skipped for Meteosat (see the standard-set note in
  the planning section above): SEVIRI's alias table makes the recipe's red
  beam a constant, and FCI can't map it without breaking the exposed C09 WV
  scalar. Requires recipe-level per-instrument overrides — deferred.
- Proofs (2026-07-11T0100Z-ish cached frames, night over Africa): all 3
  composites × both instruments render 100% opaque with healthy variance in
  every band; palette behavior matches a GOES-19 CONUS Night Microphysics
  reference rendered through the same recipe, and M9 Dust shows the
  canonical look (warm land pink, convective cores dark red, cold Southern
  Ocean olive). Proof PNGs in `cache\satellite\validation\fci_proofs\`
  (`meteosat{9,12}_{NighttimeMicrophysics,Dust,Ash}_proof_z3.png` plus the
  GOES reference). Meteosat-11 has no cached RSS source to proof against,
  but it shares the SEVIRI parser and composite path with Meteosat-9
  end-to-end; browser spot-check of one RSS composite is user-owned.
- Legends: interpretive RGB legends are keyed by product, so the existing
  GOES legends for these three composites apply to Meteosat automatically
  (verified via `get_legend_payload`).

Browser smoke passed 2026-07-10: user tested the three RGB composites on
the Meteosat platforms and confirmed the output, and separately confirmed
satisfaction with visible-channel reflectance rendering (the shared
scalar-reflectance stretch), closing out that follow-up.

#### Satellite UI dependency chain + Meteosat visible channel — 2026-07-03

UI dependency chain: **Satellite → Sector → View → Product**

All selections must be explicit; tiles do not load until all four are chosen.

- `weather.html`: Added "Full Disk" as default view option; added
  "— Choose Product —" placeholder as default Product option (prevents
  auto-load with fallback channel).
- `js/satellite-page.js`: View dropdown disabled until Sector selected;
  Product dropdown disabled until View selected. New functions
  `syncViewPresetEnabled()` and `syncChannelEnabled()` manage the
  disabled state. `activeChannel()` now returns empty string when no
  product selected (was defaulting to Channel13). Tile-loading check
  requires all four selections non-empty. Verified: correct enable/disable
  sequence and no auto-load until product explicitly chosen.

Meteosat-12 `Channel02` → FCI `vis_06` visible scalar added:

- `config/satellite_v2_config.py`: Added `"Channel02": "vis_06"` to
  `FCI_CHANNEL_FOR_ABI_CHANNEL` mapping.
- `js/satellite-page.js`: Exposed `Channel02` in Meteosat-12 product list;
  pruned composites from Meteosat-9 and Meteosat-12 (deferred to V2).
  Himawari-9 retained full GOES product list (identical ABI).
- Proof validation (2026-07-03T194500Z frame): reflectance range 0–0.7633 K,
  68.8% disk coverage, 9.7% bright pixels (correct for 19:45 UTC sunset);
  cloud detail over West Africa coast visible; calibration verified.
- Product dropdown now correctly filters by satellite:
  - Himawari-9: All GOES products (ABI-identical rendering speed)
  - Meteosat-12: Channel02, 07, 07Fire, 08RAMSDIS, 09RAMSDIS, 13 only
  - Meteosat-9: Channel02, 03, 07, 07Fire, 08RAMSDIS, 09RAMSDIS, 13 only
  - GOES: Full product list (unchanged)

Next visible-products sequence for non-NOAA satellites:

1. ✅ Meteosat-12 `Channel02` → `vis_06` proof completed and exposed.
   Daylight browser smoke passed 2026-07-04; night full-disk smoke passed the
   same evening on a prefetched frame (~250 ms/tile).
2. ✅ Reflectance display stretch completed 2026-07-10. User evaluation
   confirmed that visible imagery from Meteosat had the same flat appearance
   as the other providers, with too little distinction between darker and
   lighter image areas. The renderer already applied a power-law stretch to
   Channels 01-03, so the missing step was contrast-range expansion rather
   than a second gamma adjustment. All scalar reflectance products
   (Channels 01-06) now use one provider-independent display transform: clip
   linear reflectance to a fixed 0.02-0.90 window, normalize it to 0-1, then
   apply `sqrt`. Fixed bounds avoid tile seams and animation flicker; RGB
   recipes remain unchanged. Render namespaces advanced to `products-v3`,
   `products-ahi2`, and `products-fci2` so old tiles do not mask the change.
   Focused tests passed, and a direct browser smoke against the new local
   server returned a valid 256x256 GOES-18 Channel02 tile. On the same tile,
   the grayscale p5-p95 span increased from 141 to 178 levels. Full-page user
   comparison remains the final visual acceptance step. Optional later:
   solar-zenith normalization.
3. Continue with Meteosat-9 visible channels if `Channel02`/`Channel03` mapping
   is needed; otherwise defer to next visible band (Shortwave IR/Fire) in
   the standard product set.
4. Expand cautiously after the first visible proof. Candidate mappings:
   `Channel01` -> FCI `vis_04`, `Channel03` -> FCI `vis_08` or `vis_09`,
   `Channel05` -> FCI `nir_16`, and `Channel06` -> FCI `nir_22`.
5. Revisit composites only after their source mappings have individual scalar
   proof renders. Candidate follow-ups include Day Cloud Phase, Fire
   Temperature, Natural/True Color, and related RGB products. Meteosat-9
   already has SEVIRI visible-equivalent support, so Meteosat-12 FCI visible
   exposure is the larger near-term gap.

Himawari (deferred): checked the `AHI-L1b-Target` S3 prefix for rapid-scan
target areas — `R301`-`R304` are a single persistent ~1000km volcanic-watch
box near 142°E/26.6°N (Izu/Bonin arc), not a general-purpose movable sector,
so it was not worth adding even before the pipeline itself was removed.

#### Meteosat-11 Rapid Scan Service (RSS) — validated 2026-07-03

Meteosat-11 RSS is live, giving the dashboard a 5-minute-cadence
Europe/North Africa product alongside the 15-minute Meteosat-9/12 full disks:

- EUMETSAT collection `EO:EUM:DAT:MSG:MSG15-RSS`. Product IDs use the
  `MSG4` prefix (satellite_id 324 in the native header) — EUMETSAT's
  currently-operating RSS satellite, publicly branded Meteosat-11.
  Calibration constants for platform 324 already existed in
  `satellite_v2/seviri_nat.py` (reused from the Meteosat-9 work), so no new
  calibration table was needed.
- `satellite_v2/provider_eumetsat.py`: `_SLOT_MINUTES` changed from a single
  module constant to a per-satellite dict (5 min for RSS vs 15 min for full
  disk); `_require_fulldisk` generalized to `_require_supported_sector` so
  each platform can declare its own allowed sector (`RSS` for Meteosat-11).
  New `RSS` sector key added to `SATELLITE_V2_SUPPORTED_SECTORS`.
- Real bug found and fixed during validation: RSS products are a cropped
  northern strip (3712 columns x 1392 lines, not the full 3712x3712 disk).
  `seviri_nat.py`'s `_source_georef` assumed the grid is always centered on
  the sub-satellite point, which is true for full disk but placed the RSS
  strip incorrectly near the equator instead of its actual ~13-68N position
  at 9.5E. Fixed by reading the native header's
  `SouthLineSelectedRectangle`/`NorthLineSelectedRectangle`/`East`/
  `WestColumnSelectedRectangle` fields and computing bounds relative to the
  full 3712-line/column reference grid rather than the cropped array's own
  dimensions. Verified with a coastline ghost-overlay proof render over
  Europe before wiring the UI.
- `config/satellite_platforms.py`: new `meteosat11` descriptor (instrument
  SEVIRI, provider eumetsat, sectors `["RSS"]`, lon_0 9.5).
- Frontend: platform button, `PLATFORM_SECTORS.meteosat11 = ['RSS']`,
  `PLATFORM_CHANNELS.meteosat11` (same scalar set as Meteosat-9), and a new
  `europe-rss` named view preset. The RSS sector toggle button and native
  `<option value="RSS">` already existed pre-hidden in `weather.html` from
  earlier scaffolding; only needed un-hiding via the existing
  `PLATFORM_SECTORS`-driven visibility logic. `weather.html` bumped to
  `satellite-page.js?v=20260703a`.
- User browser-tested and confirmed working 2026-07-03.

#### Himawari-9 Japan Area and Target Area sectors — added 2026-07-03

Investigated after confirming Himawari-9's `AHI-L1b-Target` prefix is not
always the fixed Izu/Bonin volcanic-watch box noted earlier: JMA dynamically
retasks it (observed pointed at a typhoon near the Vietnam/Hainan coast,
`ObsMode=TY`, center ~109.7E/18.5N). A second prefix, `AHI-L1b-Japan`, had
not been examined before and turned out to be a genuine fixed-box rapid-scan
product.

- S3 bucket structure: `noaa-himawari9` has exactly three top-level AHI-L1b
  prefixes — `FLDK` (full disk, already implemented), `Japan`, and `Target`.
- Both `Japan` (`JP01`..`JP04`) and `Target` (`R301`..`R304`) are **repeat
  scans of one fixed grid**, not spatial quadrants: parsing all 4 headers
  for the same 10-min timeslot showed identical `coff`/`loff`/`n_cols`/
  `n_lines` across all 4 scenes, each `total_segments=1`. This gives ~2.5-min
  effective cadence (JMA scans the box 4x within each 10-min block).
  Difference between the two: Japan's box is permanently fixed over
  Japan/nearby seas; Target's box changes per JMA tasking and can be a
  storm, a volcano, or empty.
- No parser bug this time (unlike Meteosat RSS): AHI's `coff`/`loff` are
  self-describing per-file/per-crop (small values matching that crop's own
  local grid, e.g. Target's `coff=1755.5, loff=1220.5` on a 500x500 grid),
  not full-disk-relative like MSG's line/column numbering. `ahi_hsd.py`'s
  existing `load_ahi_raster` worked unmodified. Verified with a coastline
  ghost-overlay proof: a live Target frame (2026-07-03) showed a very cold
  BT core (183-190K, consistent with overshooting convective tops) correctly
  positioned over the Vietnam coast near Hue, matching JMA's published
  target coordinates.
- `satellite_v2/provider_himawari.py`: generalized from FULLDISK-only to a
  `_SECTOR_INFO` dict (`FULLDISK`/`JAPAN`/`TARGET` → S3 root + whether the
  sector is "multi-scene" i.e. each scene within a 10-min slot is its own
  frame rather than being segment-stitched). `_SEGMENT_RE` widened to match
  the `FLDK|JP0[1-4]|R30[1-4]` scene token. Frame keys for multi-scene
  sectors embed the scene suffix (e.g. `20260703T235000Z_R304`) since 4
  distinct frames exist per 10-min slot. The exact per-scene scan time isn't
  in the S3 filename (only the 10-min slot); frame `timestamp_utc` uses a
  150s-per-scene-index approximation for scrubber ordering/display, not
  JMA's true `ObsStartTime`.
- `config/satellite_v2_config.py`: `JAPAN`/`TARGET` added to
  `SATELLITE_V2_SUPPORTED_SECTORS`. `config/satellite_platforms.py`:
  himawari9 `sectors` expanded to `["FULLDISK", "JAPAN", "TARGET"]`.
- Frontend: new sector toggle buttons (`#satellite-sector-japan`,
  `#satellite-sector-target`) and native `<option>`s in `weather.html`;
  `PLATFORM_SECTORS.himawari9` includes `Japan`/`Target`. Japan gets a real
  computed named view preset `himawari-japan` (bounds derived from the
  JP01 header's actual geolocated corners, `[[18,100],[55,157]]`). Target's
  box moves per JMA tasking, so V1 reuses the existing wide `west-pacific`
  full-disk preset as a fallback rather than auto-centering — user pans
  manually to find the current target. Auto-centering on the live target
  box is a possible V2 follow-up. `weather.html` bumped to
  `satellite-page.js?v=20260703b`.
- Verified end-to-end (catalog + live tile render, both sectors) via direct
  API calls against an isolated test server; the app's normal dev workflow
  always proxies API calls to the long-running `main.py` on port 8000
  (see `js/shared.js`'s `resolveApiOrigin`), so a manual restart of that
  process is needed before this is testable in the live dashboard.
- User confirmed both Japan and Target sectors working live 2026-07-04.

#### Himawari-9 "Current Target Area" auto-fit view — added 2026-07-04

Because JMA retasks the Target Area dynamically, the static named view
presets used elsewhere don't work for it (the box moves). Added a
dynamic-fit alternative instead of requiring the user to manually pan from
the wide West Pacific fallback:

- New endpoint `GET /api/satellite-v2/frame-bounds?sat_id=&sector=&channel=`
  (`routes/satellite_v2.py` → `satellite_v2.service.get_frame_bounds`)
  returns the real-world lon/lat bounds of the most recent frame, or
  `{"bounds": null}` if no frame currently exists for that sector (nothing
  tasked). Implementation: lists the latest frame, downloads its single
  small source file, loads it through the existing generic
  `renderer._load_source_raster` dispatch (same one used for tile
  rendering, so no per-format special-casing), then samples a 9x9 interior
  pixel grid through the raster's `src_transform`/`src_crs` with
  `pyproj.Transformer`, keeping only finite lon/lat results before taking
  min/max. Interior sampling (not just the 4 corners) matters because
  full-disk-shaped sectors have off-Earth corners that transform to
  infinity, while cropped regional sectors are fully on-Earth — the same
  function needs to handle both without extra branching.
- Frontend: new View option "Current Target Area"
  (`himawari-target-current`) in `weather.html`. Unlike the static presets
  in `SATELLITE_NAMED_VIEW_PRESETS`, this entry has `bounds: null` and
  `dynamic: true`; `js/satellite-page.js`'s `setActiveViewPreset` checks
  for that flag and calls the new async `fitDynamicViewPreset`, which
  fetches `/api/satellite-v2/frame-bounds` via the shared `window.apiUrl`
  helper and fits the map to the returned box, or shows a status message
  if nothing is currently tasked or the request fails.
  `weather.html` bumped to `satellite-page.js?v=20260703c`.
- Verified end-to-end in-browser: temporarily pointed `window.apiUrl` at
  the isolated test server (since the real port-8000 process wasn't
  restarted yet for this addition either) and confirmed selecting "Current
  Target Area" re-tiled the map to a tight z5 cluster bracketing the
  target's actual longitude/latitude box, instead of the wide West Pacific
  fallback extent.

#### GOES GeoColor recipe and satellite opacity policy — updated 2026-07-16

The former GeoColor path was a gamma-stretched synthetic true-color RGB whose
red reflectance also doubled as the day/night mask. That made dark daytime
water and land blend toward the synthetic night palette, while the missing
Rayleigh correction left the result flatter than the NOAA/CIRA reference.

- `satellite_v2/renderer.py` now reads the GOES observation time from NetCDF
  metadata (ABI filename fallback) and retains the projection origin/height on
  `SourceRaster`. The renderer passes those values plus the existing canvas
  lon/lat grid to `render_composite_rgb`.
- `satellite_v2/composites.py` computes local solar and geostationary viewing
  geometry, applies a bounded wavelength-dependent Rayleigh path-reflectance
  correction to Channels 1/2/3, constructs the established simulated green,
  and applies the CIRA log stretch. Solar geometry owns the day/night mask;
  surface brightness is used only as a legacy fallback for sources without
  frame-time metadata.
- The 2026-07-31 low-sun refinement keeps that correction at full strength
  through 60 degrees solar zenith, then smoothsteps it to zero by 85 degrees
  so the compact estimate does not crush late-day shadow detail before the
  separate 80-95 degree day/night transition.
- A GeoColor-only `0.85` display white point and `1.08` saturation adjustment
  finish the daytime RGB. Both `GeoColor` and `GeoColorBlkMar` share this path.
  The Black Marble background remains an internal RGB input, not a basemap
  layer.
- ABI GeoColor additionally applies a mild `0.85` midtone gamma after the
  white-point transform. It preserves black and full white while recovering
  thin-cloud detail; non-ABI platform recipes are unchanged.
- Filled RGB/scalar satellite products use alpha 255. ADP/AOD/FRP retain
  specialized sparse-overlay transparency, and invalid/off-disk pixels stay
  alpha 0. The main dashboard and the retained standalone satellite JS path
  use Leaflet opacity 1.0, leaving per-pixel PNG alpha as the sole transparency
  authority.
- Focused validation: 13 satellite tests pass (GeoColor geometry/stretch/tone,
  timestamp parsing, scalar reflectance, and filled-vs-sparse opacity), plus
  Ruff, Python compilation, and `node --check` for both satellite viewer paths.
  Browser visual proof is user-owned; corrected colors, opacity, daytime white
  point, low-sun behavior, and ABI midtones are user-confirmed.

#### GOES aerosol and fire products: ADP, AOD, FRP — added 2026-07-16

Three new single-instant GOES ABI L2 products for GOES-18/19, added to support a
live Canadian-wildfire smoke event. All three reuse the existing GOES
geostationary georeferencing (`goes_imager_projection` + `x`/`y` scan coords,
2 km grid) — identical to CMIP imagery — so no new projection code was needed.
They are GOES-only: NOAA publishes no AHI/SEVIRI/FCI aerosol or fire equivalent
(the `noaa-himawari9` bucket has only AHI-L2 Clouds/ISatSS/Winds), so
`js/satellite-page.js` gates all three behind a `GOES_ONLY_CHANNELS` set
(visible for goes18/goes19, hidden for every other platform).

- **AerosolDetection (ABI-L2-ADP, "Smoke & Dust")** — categorical smoke/dust
  mask. `_load_adp_source_raster` folds the binary Smoke and Dust flags plus
  their DQF confidence into one code band (`category*10 + confidence`; category
  1/2/3 = smoke/dust/both, confidence 0/1/2 = high/medium/low decoded from DQF
  bit-fields — smoke `(DQF>>2)&3`, dust `(DQF>>4)&3`; a DQF field == 3 "bad" is
  treated as no detection). `_colorize_categorical` maps category → hue (smoke
  teal `#39d0d8`, dust amber `#e8a33d`, both purple `#c44dff`) and confidence →
  opacity (`_ADP_CONFIDENCE_ALPHA = (210, 140, 80)`). Categorical products
  render with `Resampling.nearest` so the integer codes never blend into
  fractional values. Interpretive legend in `SATELLITE_V2_INTERPRETIVE_LEGENDS`
  (config) and its JS mirror `_SATELLITE_INTERPRETIVE_LEGENDS` (js/weather.js).
- **AerosolOpticalDepth (ABI-L2-AOD, "AOD")** — continuous 550 nm field, turbo
  colormap, norm 0–1.0. `_load_aod_source_raster` filters to high+medium DQF
  quality (drops `DQF > 1` to NaN — low-quality was the main clear-sky speckle
  source, matching NESDIS AerosolWatch imagery). `_colorize_aod` applies a
  value-driven alpha ramp (transparent at/below 0.10, opaque at/above 0.40 AOD)
  so clear air stays see-through and plumes read opaque as an overlay. Scalar
  legend (kind `aod`) with numeric ticks and axis label. The AOD legend also
  renders a discrete black "No Data" swatch left of the gradient (NESDIS
  convention) via a new optional `leadingSwatch` param on
  `renderContinuousLegend` in js/weather.js plus `.legend-colorbar-*` CSS —
  no-retrieval pixels render transparent on the map, not black.
- **FireRadiativePower (ABI-L2-FDC, "FRP")** — sparse fire field (MW). Not an
  aerosol product, but the same single-instant architecture and directly
  relevant as the smoke's source fires. `_load_frp_source_raster` reads the
  `Power` variable (finite only at fire pixels) and `_dilate_sparse(radius=1)`
  grows each 2 km fire to a ~6 km block so it is visible at CONUS zoom. Flows
  through the default `_colorize_scalar` (valid mask = fire pixels), YlOrRd
  colormap, norm 0–150 MW, scalar legend kind `frp` (MW ticks).

Shared plumbing (all inside the existing single-instant render path — no new
render model was introduced):

- Pseudo source-channels `ADP`/`AOD`/`FRP` (the same trick SEVIRI/FCI bundle
  tokens use) registered in `normalize_source_channel`; each product's `req`
  list points at its pseudo-channel. `_product_kind` returns
  `categorical`/`aod`/`frp` *before* calling `channel_number_from_key`, which
  would otherwise throw on a numberless key.
- `provider_aws._aws_family_prefix` maps the pseudo-channel to its ABI-L2
  family prefix (`ADPC/ADPF/ADPM`, `AODC/AODF`, `FDCC/FDCF`); these products
  skip the `C##` imagery token filter, and `_filename_matches_sector` was
  generalized from `CMIPM1/CMIPM2` to `M1-M`/`M2-M` so it matches both CMIP and
  ADP mesoscale files. AOD has no mesoscale on AWS (AODM 404s); ADP and FDC do.
- `renderer._load_source_raster` dispatches on the pseudo-channel to the new
  loaders; the shared `_geos_scan_source_raster` helper builds the SourceRaster
  (deliberately duplicating ~25 lines of georef rather than refactoring the hot
  CMIP path).
- The aerosol/fire products themselves needed no render-version bump: the tile
  cache path keys on channel, so changed AOD/ADP output was cleared surgically
  by deleting `tiles/products-v3/goes*/{AerosolDetection,AerosolOpticalDepth}`.
  The same-day GeoColor recipe change (above) separately re-namespaced all GOES
  tiles to `products-v5`, so current aerosol/fire tiles live under that
  namespace.
- Skipped as not worth it: the AOD file's Angstrom Exponent (particle size,
  fine smoke vs coarse dust) is over-water only (~24% coverage), useless over
  CONUS land smoke.

Verified (static + backend render, per project convention — browser smoke is
user-owned): all four Python modules `py_compile`; `node --check` on
js/weather.js passes; catalog → download → render for ADP/AOD/FRP on both
GOES-18 and GOES-19 returns non-blank tiles. Live values 2026-07-16 (GOES-19):
ADP 26k smoke / 106k dust pixels, AOD max 5.0 with ~405k px > 0.5, FDC 41 fires
up to 552 MW in the Pacific NW. Frontend cachebusters at add time:
`weather.js?v=20260716c`, `satellite-page.js?v=20260716b`,
`dashboard.css?v=20260716a` (weather.js later advanced to `v=20260716d` by the
GeoColor opacity work).

### Satellite render pipeline latency optimization — registered 2026-07-16

Completed track 3 (see Active Tracks). Status: Phase 0 committed at `a6f5f83`,
Phase 1 at `fc534ba`, Phase 2 at `8ee3a4b`, Phase 3 at `29b83b6`, Phase 4 at `39de302`, and Phase 5 at `168510f`. The archived standalone
execution plan is `docs/archive/satellite-render-optimization-plan.md` (prepared
2026-07-11). The shared file reference is archived at
`docs/archive/satellite-radar-render-pipeline-files.md`. The
archived Satellite plan retains its benchmark CLI, golden matrix, and phase
decisions; this superfile carries the durable final status.

- Goal: minimize end-to-end tile latency at high zoom with **bit-identical**
  pixel output; no render-version bumps; protected knobs untouched.
- Phase 0 golden tiles and the committed baseline must be captured from the
  post-GeoColor/opacity renderer, using `products-v5` for the GOES/default
  namespace. Do not compare optimized output against pre-v5 translucent or
  pre-Rayleigh tiles.
- Phase 0 result: 27 runs / 135 samples across the complete nine-row matrix;
  nine 3x3 scratch golden blocks (81 PNGs) passed byte-for-byte comparison.
  Consolidated results and the environment/pinned-frame manifest are in
  `docs/perf/2026-07-22-baseline/`. The scratch goldens remain ignored. Focused
  Satellite tests pass 21/21; the full suite passes 93 tests plus 42 subtests.
- Phase 1 result: NetCDF handles now follow a true closing LRU; normal PNG hits
  avoid full decode while retaining deep fallback; non-geographic composites
  skip lon/lat allocation. All 81 goldens remain byte-identical, hit validation
  is 22.4–45.8x faster, and the full suite passes 99 tests plus 42 subtests.
- Phase 2 result: single-canvas rendering failed pixel identity and was
  rejected. Respond-first per-tile rendering passed 81/81 goldens, settled
  neighbors asynchronously, and reduced headline cold p50 by 11.9–14.9%.
- Phase 3 result: FCI chunks are opened once for multi-channel products and AHI
  segment decode is threaded with bounded full-buffer residency. The full
  matrix remains byte-identical; headline p50 improved 43.2–49.6%.
- Phase 4 result: a byte-budgeted per-process source-raster LRU shares grids
  across renderer entries and evicts dependent renderers with each source. The
  full matrix remains byte-identical; the pinned FCI cross-product sequence
  saved one 118.266 MB Channel13 grid and one parse.
- Phase 5 result: the rapid worker reuses one process pool across all
  frames/jobs and avoids the trailing catalog rebuild after no-op jobs. A
  pinned MESO two-zoom workload improved 76.3% at steady warm p50; reusable and
  per-call pool outputs were byte-identical.
- Phases: 0 benchmark harness + committed baseline; 1 hit-path validation
  cheapening + `_NETCDF_CACHE` LRU bugfix; 2 supertile single-canvas +
  respond-first; 3 multi-channel single-pass parse + AHI threaded segment
  decompress; 4 shared source-raster cache; 5 warm-path process-pool reuse;
  6 (optional, measure-first) GDAL warp threads.
- The pre-identified `_NETCDF_CACHE` plain-dict eviction bug is fixed in the
  locally complete Phase 1 slice.
- The Phase 4 byte-budget knob was approved. Phase 6 is now deferred: the
  current rapid policy tops at z7 and the representative Phase 5 steady warm
  path is below one second. Reopen warp threading only after a real rapid-run
  profile and explicit approval for its new knob.

### Radar render pipeline latency optimization — registered 2026-07-22

Completed as Track 3 (see Active Tracks). The execution plan is archived at
`docs/archive/radar-render-optimization-plan.md`; the historical pipeline map
is `docs/archive/satellite-radar-render-pipeline-files.md`. Phases 0-8 and the
post-phase freshness correction are complete.
Phase 1 includes three-site user-owned browser acceptance, and Phase 2 includes
`/radar` and `/workspace` browser acceptance. Phases 3-5 are backend-only and
golden-validated. Future WebGL work is additive and cannot replace PNG
correctness or fallback.

- Goal: reduce first usable newest-frame latency and background loop-fill time
  while preserving byte-identical PNGs and exact bounds, timestamps, frame
  order, elevations, sweep selection, palettes, masks, units, and cache keys.
- Phase 0: add a scratch-only `radar.bench` harness, structured stage timings,
  process working-set evidence, and an eight-row L2/L3 golden matrix. Complete;
  evidence is in `docs/perf/2026-07-25-radar-baseline/`.
- Phase 1: on an empty frame cache, return one newest frame before the remaining
  initial/history renders continue through the existing deduplicated background
  path. Implemented; evidence is in
  `docs/perf/2026-07-25-radar-phase1/`. Three-site browser acceptance passed.
- Phase 2: reuse one lazily started, bounded render-process pool across an
  owning scheduled run's batches and explicitly own the pool for a background
  selected-product run without changing `LIVE_RADAR_PARALLEL_WORKERS`.
  Implemented and golden-validated; evidence is in
  `docs/perf/2026-07-25-radar-phase2/`. Both-page browser acceptance passed.
- Phase 3 result: byte-identical Level II volumes use one site-owned source
  spool, and a bounded decoded-volume consumer seam renders the configured
  product set with one Py-ART decode. Dynamic SRV variants remain separate
  render/cache products. The five-sample wall p50/p95 improvement is
  37.1%/37.6%; all eight goldens pass. No WebGL artifact or endpoint was added.
- Phase 4 result: persisted validated discovery lists avoid unchanged-directory
  rescans, and same-volume temporary PNGs are atomically published with tested
  interruption cleanup, visibility, ordering, and pruning. No-op p50/p95
  improved 10.6%/11.9%, backfill-12 improved 5.2%/6.8% over Phase 2, all eight
  goldens pass, and evidence is in `docs/perf/2026-07-26-radar-phase4/`.
- Phase 5 result: same-volume Level II products selecting the same sweep reuse
  one bounded Matplotlib QuadMesh. The seven-product one-decode batch improves
  28.5%/27.6% p50/p95 and uses 13.4% less p95 peak working set. All 35
  five-sample batch PNGs and all eight permanent goldens pass byte-identically;
  evidence is in `docs/perf/2026-07-26-radar-phase5/`.
- Phase 6 result: the separately authorized active-paused-frame L2 Reflectivity
  pilot is implemented behind a default-off switch. It uses one versioned
  1,322,700-byte KGGW polar artifact and one client texture, adds no second
  decode, preserves all PNG goldens, and passes the first-PNG latency gate.
  Below zoom 10 remains PNG-only, zoom 10 prefetches behind PNG, and zoom 11
  crossfades only after readiness. User-owned two-page activation, 0.100 ms
  cached redraw, same-frame visible parity, PNG-only, active-playback fallback,
  context-loss fallback, and stale-selection cancellation checks pass. Phase 6
  is closed.
- Phase 7 result: the separately gated L2 Reflectivity animation retains a
  four-texture current/two-upcoming/one-prior window with two-load concurrency.
  PNG playback starts immediately, WebGL waits for the active plus two forward
  textures, and missing frames fall back without changing cadence or scrubber
  position. Both-page browser acceptance, all eight PNG goldens, and focused
  validation pass. Phase 7 is closed.
- Phase 8 first-family result: L2 Velocity/SRV is implemented and
  browser-accepted behind separate default-off family switches. Its
  `v2` artifacts preserve PNG identity, pass the measured 5% latency ceiling,
  remain bounded to four textures/two loads, and pass all eight permanent PNG
  golden rows. This family is closed.
- Phase 8 second-family result: L3 N0B/N0G is implemented and browser-accepted
  behind separate default-off family switches. Its product-scoped `v2`
  artifacts pass value/palette, payload, latency, bounded-window, cancellation,
  flag-off, full golden, and both-page browser gates. This family and Radar
  render optimization Phase 8 are closed.
  All-product WebGL conversion, PNG retirement, and server-rendered tiles
  require a new migration plan.
- `LIVE_RADAR_L2_USE_CHUNKS` remains `False`. The prior chunks experiment showed
  no latency advantage for completed scans and is not part of this track.

### International radar

Deferred to V2. Keep the US dashboard enhancement path focused on NEXRAD,
satellite, Water, WPC, SPC, alerts, and storm reports before adding
provider-specific radar adapters.

Preferred rollout order:

1. Canada through ECCC GeoMet radar services.
2. Germany through DWD open radar composites and supported site data.
3. Australia through Bureau of Meteorology five-minute rendered radar imagery.

Each provider should declare supported products, animation interval, projection,
attribution, archive depth, and whether data are native grids or rendered
imagery.

## Backlog

1. Dedicated Marine workspace building on the Water page's NDBC and CO-OPS
   inventory with marine-specific products, trends, and forecast context.
2. Fire/Smoke page using NASA FIRMS detections and NOAA smoke analysis.
3. Cross-product severe-weather workspace — promoted 2026-07-16 to the
   "Frontend True Split (Stage 2) and Severe Weather Workspace" section,
   which fully specifies it (product curation, two-tier time-sync, engine
   composition).
4. User preference persistence:
   - Add backend read/patch endpoints that merge a writable user settings file
     over `config/user_settings.default.json` with validation and safe fallback
     behavior.
   - Add frontend page actions such as "Use this as default for this page" and
     "Reset page defaults" after the initial map-default behavior is stable.
   - Save stable product concepts only: map view, Satellite platform/sector/
     product/lookback, Tropical basin, city label source/density, and similar
     UI preferences. Keep provider names, cache namespaces, render versions,
     function names, and implementation internals in code or operator config.
5. Workspace RTMA Winds composite marker polish (deferred): the current
   speed-plus-direction marker is accepted. Revisit only after higher-priority
   expansion work for possible arrow sizing/gap, collision handling, pairing
   tolerance, or bearing-presentation refinements; preserve the centered-tail
   and reported-bearing contract.

### Radar: All NWS NEXRAD Sites + L2-Only Filtering

**Context:** NOAA NEXRAD documentation confirms Level III products are only generated
for CONUS sites. Non-CONUS/remote sites (Alaska, Hawaii, Puerto Rico, US territories,
overseas military bases) have Level II base data on AWS but no Level III in standard
LDM feeds due to satellite-routing latency isolation from CONUS internet relays.

**Changes (2026-07-04):**

- **Backend (`services/radar_service.py`)**:
  - Added `_is_conus_site(site)` function to identify CONUS (lat 21–52°N, lon −140 to −65°W)
    vs non-CONUS sites using their coordinates.
  - Updated `get_radar_live_sites_data()` to include a `"conus": bool` flag for each
    site in the `/api/radar/live/sites` response.
  - Fixed `_radar_live_site_supported()` to recognize all non-CONUS sites via fallback
    coordinates from the new `radar/nexrad_coordinates.py` module.
  - Created `radar/__init__.py` to make the radar directory a Python package.

- **Frontend (`js/weather.js`)**:
  - Added `_radarSiteConusMap` to track CONUS status for each site.
  - Changed default product from `L3_N0B` to `L2_REF` in two locations:
    `_activeRadarProduct()` fallback and `_loadRadarSites()` initial selection logic.
  - Disabled Level 3 products in dropdown for non-CONUS sites (greyed out with note).
  - Site selection change handler auto-switches to L2 when non-CONUS site selected.

- **Data (`radar/nexrad_coordinates.py`)**:
  - New comprehensive NEXRAD site coordinate mapping for all 164 NWS WSR-88D sites,
    including 121 CONUS, 7 Alaska, 4 Hawaii, Puerto Rico, Guam, and 3 overseas military.
  - Serves as fallback when Py-ART's NEXRAD_LOCATIONS lacks a site's coordinates.

**Result:**
- Radar site selector now shows all 164 NWS sites (vs. previous 7 CONUS-only).
- Non-CONUS sites (PGUA/Guam, RKSG/South Korea, RODN/Japan, etc.) render **Level 2 data**
  on-demand from AWS; Level 3 options are disabled to reflect unavailability.
- Default product `L2_REF` works universally across all sites.
- No 404 errors or confusion about missing Level 3 data for remote sites.

## Verification Expectations

- Use narrow syntax checks first, such as `node --check` for touched JavaScript
  files and targeted `py_compile` for touched Python modules.
- Browser smoke is user-owned for current dashboard work; keep automated
  validation to narrow syntax/import checks unless the user asks otherwise.
- For map label/value placement, preserve source coordinates and move rendered
  anchors when the goal is visual offset.
- Keep scrubber continuity and worker/preloader coverage as acceptance criteria
  for derived or replacement UI behavior.
- When browser proof is unavailable, keep claims scoped to static validation.

Representative checks:

```powershell
node --check js\weather.js
node --check js\wpc-page.js
node --check js\wpc-engine.js
.\.venv\Scripts\python.exe -m py_compile main.py routes\*.py services\*.py workers\*.py
```

Representative browser smoke:

- `/weather.html` combined workspace still loads.
- Canonical product routes return 200 and render nonblank maps.
- Product controls populate and trigger the expected API calls.
- Layers clear on tab/product switch without leaking stale overlays.
- Legends render without swatch/label overlap.
- Archive/scrubber workflows keep frame continuity where applicable.

## Archived Source Docs

These superseded planning files were consolidated into this superfile and moved
to `docs/archive/`:

- `dashboard-product-enhancement-roadmap.md`
- `wpc-page-plan.md`
- `product-page-shell-plan.md`
- `refactor-playbook.md`
- `refactor-dossier.md`
- `satellite-render-optimization-plan.md`

Keep archived files for historical detail. Prefer this superfile for current
planning and status.
