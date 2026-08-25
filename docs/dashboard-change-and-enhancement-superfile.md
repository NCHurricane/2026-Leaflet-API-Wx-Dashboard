# Dashboard Change and Enhancement Superfile

**Canonical status:** current source of truth as of 2026-08-14

**Repository:** `F:\Python\dashboard_2026`

**Baseline at consolidation:** `d6b8238` on `main`

**Execution rule:** this file records decisions and candidates; it does not by
itself authorize implementation or deletion.

This document replaces the former 248 KB chronological superfile as the active
plan. The original and every planning source used to create this file are
preserved unchanged under
[`archive/2026-08-07-consolidation-sources/`](archive/2026-08-07-consolidation-sources/README.md).

## 1. How to use this file

The ledgers below are deliberately separate:

1. **Current truth** describes behavior that must remain functional.
2. **Cleanup program** records audit findings and the safe order for later work.
3. **Current-dashboard enhancements** records proposals that remain eligible.
4. **Version 2 and separate-project lanes** prevent long-range ideas from being
   mistaken for current work.
5. **History and evidence** links to exact source records.

Before changing code, select one bounded slice, trace its callers and assets,
state dependencies and validation, obtain any needed approval, then implement
only that slice. Directory-audit findings are candidates, not deletion orders.

Status vocabulary:

- **Current:** implemented behavior to preserve.
- **Approved proposal:** scope is retained, but implementation still requires a
  selected work slice.
- **Investigate:** evidence or design is incomplete.
- **Parked:** intentionally deferred; do not start incidentally.
- **Rejected:** removed from the plan; do not reintroduce without a new decision.
- **Historical:** completed or superseded evidence only.

## 2. Current truth and invariants

### 2.1 Application and frontend

- FastAPI serves the landing page and canonical extensionless product routes:
  `/alerts`, `/radar`, `/satellite`, `/spc`, `/surface`, `/mrms`, `/rtma`,
  `/drought`, `/tropical`, `/wpc`, `/water`, and `/workspace`.
- `frontend/` is the current UI implementation. All 76 files found in its audit
  are retained, and the shared alert monitor adds one current core module.
  Product pages import narrow shared capabilities from
  `frontend/core/`; Workspace composes engine APIs and must not import sibling
  page controllers.
- Standalone product behavior must remain independent of Workspace behavior.
  Workspace is a curated composition, not a new global page controller.
- Workspace currently composes Alerts, Radar, SPC, Satellite, RTMA-RU, MRMS,
  WPC, and Water. Drought remains standalone-only.
- The Workspace shared timeline synchronizes Radar, MRMS, Satellite, and RTMA.
  WPC retains its own issuance/product cadence.
- Browser dependencies are vendored under `frontend/lib/`. The seven retained
  fonts are active assets. `css/shared.css` remains active for the landing page.
- `frontend/core/branding.js` renders the shared Chuck Copeland Weather header
  logo, while `map-core.js` renders the decorative map duplicate. The landing
  shell uses the same canonical `/img/chuck-copeland-weather-logo.svg` asset.
  Only its identified lightning-bolt group pulses; reduced motion keeps the
  complete logo and bolt visible and static.

### 2.2 Runtime and refresh ownership

- `app_core/refresh_coordinator.py` is the required application-owned refresh
  lifecycle: bounded execution, real-resource-key deduplication, provider
  concurrency and minimum intervals, presence leases, backoff, and pruning.
- The supported runtime is one application process. Multi-worker Uvicorn is not
  supported. Persistent cross-process leases are **closed as unnecessary for
  the current deployment** and may be reconsidered only if deployment changes.
- The former `workers/scheduler.py` compatibility lifecycle hook is removed.
  Optional OS warmers call the running local API and are never a correctness
  dependency.
- There is no Windows background service requirement. Closing all dashboard
  pages ends browser-owned activity; server-owned cache maintenance remains
  bounded by the running application.
- Publishers must expose either the previous complete artifact or the next
  complete artifact. New or changed writers use unique temporary paths,
  bounded locks, and atomic replacement.
- Satellite tile routes await their bounded render futures on a Satellite-owned
  request executor rather than AnyIO's shared synchronous-request workers.
  Standalone and Workspace tile URLs carry page ownership; changing selection
  or leaving the page releases it. Work still waiting for the heavy-render slot
  stops when no page owns the selection, while an already-running render may
  finish and atomically publish its reusable cache artifact.

### 2.3 Product contracts to preserve

- **Alerts:** immutable cache generations, zoom-aware geometry, stale-complete
  service while a deduplicated refresh runs, explicit warming/backoff on a cold
  miss, live Local Storm Reports, a national active-warning rail independent of
  viewport-filtered map/legend content, and detail selection.
- **Shared standalone alert monitor:** every non-Workspace product page joins a
  same-origin browser cohort with one focused/visible polling owner. The fixed
  national six-event allowlist baselines existing alerts and deduplicates
  banners, sound, and an alert-colored border flash across tabs/windows. Alerts
  owns the shared On/Off setting and in-place selection; other pages deep-link
  to a selected/zoomed Workspace view. Workspace monitoring remains independent.
- **Radar:** live cache-first site/product PNG streams, newest-frame-first cold
  behavior, asynchronous bounded history, legends/value inspection, and PNG as
  the authoritative fallback even where WebGL is used.
- **Satellite:** satellite-v2 catalog and Web Mercator tile contract, source and
  channel resolution, product-specific alpha semantics, and implemented
  GOES/Himawari/Meteosat/GK2A/GMGSI behavior.
- **RTMA/MRMS:** overlay frames and metadata remain source-identified and
  bounded. The current UI history is approximately 12 hours. Native MRMS tiles
  coexist with PNG fallback; `latest_source.json` is canonical frame identity.
- **SPC/WPC/Tropical/Water/Surface/Drought:** preserve their current standalone
  routes, provider parsing, legitimate-empty states, and page-owned
  controls/legends. Surface owns a bounded 15-minute-to-24-hour recent-lookback
  slider in Live; the latest current frame remains fallback, while older frames
  retain their ASOS-only/no-gradient boundary.
- **Archive UI:** Surface and Alerts expose placeholder Archive tabs with the
  message `Archive tools are planned for a future update.` Alerts has no general
  lookback slider; its 1/6/12/24-hour Local Storm Report pills remain a distinct
  live-data filter. The retained Surface/Alerts archive endpoints are backend
  groundwork, not completed standalone Archive workflows.
- **Shapefiles:** retain the primary state bundle, county bundle, and
  `tl_2025_us_state.*` as the explicit TIGER state fallback.
- **Data:** all reviewed files under `data/` are retained as city/label inputs.
- **Palettes:** Radar palettes live in `config/radar_colortables/`; Satellite
  `.cmap` files live in `config/sat_cmaps/`; `bv.pal` remains restored at its
  active Radar path.

### 2.4 Retained development and repository paths

- `.git/` is required for repository history and synchronization.
- `.venv/`, `.ruff_cache/`, `__pycache__/`, `.pytest_cache/`, and runtime
  `cache/` are generated/local paths, not application source. The owner chose to
  retain the present virtual environment and Python bytecode caches.
- `tests/` is retained. Static checks, unit tests, API probes, native decode
  tests, controlled-browser checks, and owner smoke tests are distinct evidence
  categories and must be reported accurately.
- `tools/` and all reviewed worker modules are retained pending bounded cleanup.
- `pal_preview/` remains a root-dependent standalone utility and may later gain
  Satellite colortable previews.

## 3. Cleanup program

### 3.1 Audit conclusion

The retained-tree audit found **no whole tracked application source file safe to
delete immediately**. Most opportunities are unused symbols, disconnected
branches inside active modules, duplicated helpers, stale comments, or
reliability defects. Large legacy sections in MRMS, Radar, SPC, and Surface
must be removed only with targeted safety tests and coordinated import/caller
changes.

The work order below is intentional. Use the wave names rather than adding a
new numbered “Phase” that could be confused with the completed cleanup phases
in the archive.

### 3.2 Cleanup Wave A — safety nets before destructive cleanup

**Goal:** add tests that constrain active behavior before removing legacy code.

Priority coverage:

1. Surface normalization, required defaults, integer-dtype feels-like behavior,
   relative-humidity output, archive provenance, and representative fixtures.
2. SPC active parser fixtures and product-specific legitimate-empty behavior.
3. Alerts IEM, WPC, Tropical, Water, and Drought provider-parser fixtures.
4. Archive-service end-to-end tests for current retained archive endpoints.
5. Route JSON-serialization matrix for NumPy/datetime/path-like values. This
   must cover the confirmed `/api/mrms/products` NumPy-array 500 defect.
6. RTMA/MRMS decode, geospatial bounds, source identity, missing/corrupt input,
   fallback, and partial-publication failure paths.
7. Himawari AHI, Meteosat SEVIRI/FCI, GK2A/GMGSI, and composite decoder/provider
   fixtures for currently reachable Satellite products.
8. Essential asset-integrity tests for fonts, palettes, colormaps, boundary
   bundles, and page imports.
9. Behavioral JavaScript tests for shared engines, timeline following, legends,
   layer ownership, and page teardown/cancellation.
10. A real controlled-browser smoke suite for critical product pages. Rename or
    clearly label the existing static `browser_smoke` checks so they are not
    mistaken for browser execution.

Lower-priority coverage: config invariants, reusable `lib/` helpers, tool
preview non-mutation, and worker CLI contracts.

**Dependencies:** none beyond stable fixtures and current test dependencies.

**Validation:** narrow tests first, then the full Python and Node suites; browser
success may be claimed only from an actual browser run.

### 3.3 Cleanup Wave B — isolated dead symbols and imports

Remove only after targeted caller searches and relevant Wave A coverage.

- `alerts/alerts_utils.py`: nine unused functions—
  `resolve_alerts_legend_columns`, `normalize_alerts_custom_extent`,
  `fetch_active_alerts`, `plot_cities`, `_normalize_alerts_projection_mode`,
  `_normalize_extent_longitudes`, `draw_alerts_static_layers`,
  `draw_alerts_static_overlays`, and `draw_alerts_state_overlays`.
- `alerts/alerts_iem_utils.py`: unused `json` and `time` imports.
- `app_core/http.py`: `success_payload`, `attach_mode_and_source`, and unused
  `MAX_ARCHIVE_SPAN_DAYS` entries; coordinator `renew_lease` if still uncalled.
- Config candidates: Alerts `NWS_WFO_MAP` and `GEOMETRY_EXCLUDED_EVENTS`; MRMS
  `MRMS_ARCHIVE_START`; Radar `L2_PRODUCTS` and
  `LIVE_RADAR_TILE_WORKER_INTERVAL_MIN`; refresh `CHICAGO`; Satellite
  `FOGDIFF_BLUE_CMAP/NORM`, unused platform helpers, high-resolution/primary
  product sets, and `channel_token`; WPC `SURFACE_VECTOR_PRODUCTS` and
  `SURFACE_PNG_PRODUCTS`.
- `lib/`: `filter_cities_by_density`, `resolve_logo_path`, `cache_stats`,
  `get_international_boundaries`, unused county state-specific helpers/caches,
  and `list_s3_prefix_http`.
- RTMA: `NOMADS_RTMA_ROOT`, `_inches`, `_RH_ANCHORS`, redundant imports, and the
  unreachable portion of `_crop_grid` after behavioral coverage.
- MRMS: `CACHE_AVAILABLE`, `download_mrms_data`, obsolete path/progress
  branches, unused `product` argument where the public contract permits, and
  stale `__version__` metadata.
- Radar: unused THREDDS import, Montserrat registration, bucket/prefix
  constants, diagnostic helper, and `create_grs_hca_style` when its legacy
  dependency is removed.
- Satellite: dead `warm_frame_tiles`, `_WARM_TILE_RENDERER`, initializer/task,
  and associated import; consolidate duplicate provider/worker helpers later.
- `services/tropical_service.py`: remove the disconnected direct-fetch cluster
  `_TROPICAL_PRODUCTS`, `_write_tropical_cache`, `_fetch_json_url`,
  `_fetch_text_url`, `_normalize_tropical_storms`, `_tropical_wallet`,
  `_tropical_xml_basin_code`, `_extract_xml_item_text`,
  `_parse_tropical_coord`, `_parse_tropical_advisory`,
  `_parse_tropical_track`, `_tropical_product_url`, and
  `_fetch_tropical_products`. Preserve active `_normalize_storm_graphic_urls`.
- Frontend: Tropical `_scrubberPlaybackSpeedIndex` and
  `_hideArchiveScrubberBar`; unused selectors `.alerts-mode-selector`,
  `.alerts-section-head`, `.wpc-panel-note`, and `.core-label`.
- Workers: no-op `run_mrms_live_worker`, `run_rtma_live_worker`; MRMS
  `get_active_product`; RTMA `_PRELOAD_STREAMS`; unused Surface outlier
  constants/function; old Tropical list helper.

**Dependencies:** caller/import search plus the smallest corresponding tests.

**Validation:** import/compile check, targeted tests, then static analysis with
intentional dynamic imports accounted for.

### 3.4 Cleanup Wave C — disconnected large pipelines and assets

These are coordinated refactors, not mechanical deletions.

- **MRMS:** remove the disabled legacy block in `mrms/mrms_utils.py` (roughly
  lines 426–2004 in the audited revision) while retaining active decode/warp
  behavior. Close datasets on every exception path and replace debug prints.
- **Radar:** remove obsolete `radar/radar_utils.py` and its
  `radar_sites.json` dependency only with coordinated runtime-status,
  import, documentation, and test changes. Keep `nexrad_coordinates.py`,
  `radar_nodd_utils.py`, WebGL artifacts/benchmarks, and currently disabled L2
  chunk code until its own decision is made.
- **SPC:** isolate and remove the legacy static Matplotlib renderer after active
  parser/cache paths are proven independent. The audited revision has 55
  unreachable top-level functions (about 2,809 function lines), including the
  disabled `generate_spc_map`/`generate_spc_snapshot_from_range`, obsolete
  MapServer/significant-overlay paths, old SPC/IEM AFOS watch/MD option paths,
  and renderer-only projection/hatching/legend/HUD/city/output helpers. Retain
  active outlook/fire/report/WOU/watch/MD parsers and Census Counties geometry.
- **Surface:** isolate and remove the legacy Matplotlib exporter after current
  API/gradient/archive behavior is covered.
- **Satellite recipes:** remove all unreachable registry entries and their 12
  unreachable composite branches. Historical composite names are
  `BlowingSnow`, `DayCloudConvection`, `DayCloudPhaseEUMETSAT`,
  `DayConvection`, `DayLandCloud`, `DayNightHybrid`,
  `DifferentialWaterVapor`, `NightFogDifference`, `Sandwich`, `SeaSpray`,
  `SplitWindowDifference`, and `WaterVapor`. The audited removal set also
  includes five hidden raw channels and 19 palette variants; enumerate exact
  registry keys from the audited revision before editing.
- **Shapefiles:** remove the separate unused international-boundary TIGER bundle
  only with `get_international_boundaries`; retain county and both state paths.
- **Frontend sources:** resolve the 12 bindings to nonexistent `*-source`
  elements by either removing the disconnected facility or deliberately
  restoring a visible source UI. Do not keep silent half-wiring.

**Dependencies:** Wave A fixtures, import/caller maps, active route probes, and
asset inventories.

**Validation:** targeted unit/API/decode tests, full suites, representative
runtime products, and controlled-browser checks for affected pages.

### 3.5 Cleanup Wave D — reliability and bounded resource ownership

- Fix `/api/mrms/products` JSON serialization.
- Use unique temporary files and atomic replacement for Radar GCP downloads,
  MRMS/RTMA partials, Surface raw CSV, MRMS fallback publication, and retained
  WPC/Tropical/Water/archive writers.
- Ensure failed MRMS datasets close and temporary files are cleaned without
  deleting another job’s in-progress artifact.
- Bound or prune long-lived dictionaries/caches: RTMA locks, Water/SPC caches,
  Tropical archive targets/advisory locks, and similar provider state.
- For Water, replace `_WATER_CACHE` with a locked bounded TTL/LRU without
  changing station balancing or stale-while-refresh. For SPC, canonicalize the
  TOR/SVR/all watch-type set before keying `_SPC_ACTIVE_CACHE` and bound it.
  Safely retire completed `_TROPICAL_ARCHIVE_WARM_TARGETS` while preserving the
  full-versus-window status contract.
- Correct Tropical archive retention so a seven-day parent cleanup policy does
  not erase artifacts whose contract promises longer history.
- Normalize Surface inputs before calculations; fix integer-dtype feels-like,
  partial relative-humidity output loss, archive source semantics, and the
  dormant broken NWS path. Preserve required default columns.
- Review fixed `.part`, `.tmp`, and `.lock` names and stale-lock recovery across
  workers/services. Locks must be bounded and ownership-safe.
- Preserve real source/frame identity for RTMA/MRMS and never substitute file
  modification time for canonical identity.
- Make `services/archive_service.py` use `CACHE_ROOT`, atomic JSON, and
  structured logging. Resolve the Surface `source` parameter/provenance
  contradiction. Reject reversed Alerts ranges; after the deliberate 72-hour
  spanning-alert fetch, post-filter to interval intersection and reapply the
  requested state after any national fallback.
- Move Drought’s synchronous filesystem/`urlopen` work out of `async def`
  event-loop handlers, either through synchronous FastAPI handlers or bounded
  offload.
- Add provider-friendly bounded backoff, jitter, and `Retry-After` handling to
  SPC `_request_text`; guard malformed watch/MD numeric identifiers and use the
  public standard-library JSON decoder.
- Give `radar_live_worker._read_level3_file` a unique `.nids` scratch file and
  ensure `mrms_live_worker` cleans its unique temporary PNG/sidecars in
  `finally`.

**Dependencies:** Wave A failure-path tests.

**Validation:** concurrency/failure injection, targeted suites, cache artifact
inspection, and route probes; do not infer browser success.

### 3.6 Cleanup Wave E — maintainability and UI residue

- Reduce `css/shared.css` to landing-page rules after browser comparison; most
  audited rules from `.banner-logo` onward and unused font faces/variables
  appear disconnected.
- Remove verified legacy CSS blocks in Tropical, Water, and Workspace.
- Decide whether the unused Leaflet stock-image references should be cleaned or
  the vendored images restored; validate the controls that actually render.
- Decide whether Surface’s 32 °F isotherm is a retained diagnostic/product.
- Reconcile `style_config.py`: preserve active Radar/MRMS settings and remove or
  migrate unused Surface/Alerts/Satellite/SPC/Weather blocks.
- Reconcile `surface_config.py` generated-colormap code with the active bare
  colormap references.
- Standardize worker path bootstraps and the audited `E402` import exceptions
  without breaking module execution.
- Replace ad hoc prints with structured, credential-safe logging and remove
  stale comments, including Lightning and obsolete scheduler/THREDDS language.
- Move private cross-worker MRMS/RTMA/Tropical helpers into neutral product
  modules with named public contracts instead of importing worker internals.
- Remove `workers/scheduler.py` only as a coordinated change with
  `app_core/runtime.py`, tests, and architecture; do not delete the no-op hook
  alone.
- Consolidate the duplicated active SPC/WPC ISO parser and repeated Surface
  station-name enrichment. Prefer one authoritative Surface palette and fail
  visibly on real configuration errors rather than silently changing colors.
- Update retained tools: L2 chunk diagnostic, AHI/SEVIRI validators, Task
  Scheduler preview non-mutation coverage, and an FCI validation path.
- Consider moving the reusable relative-humidity helper to one owned module and
  consolidate duplicate enrichment/provider helpers only after tests.

**Dependencies:** affected UI/worker behavior tests.

**Validation:** style/static checks, full suites, asset integrity, and visual
browser comparison where CSS or controls change.

**Completion status (2026-08-08):** Cleanup Waves A through E are complete.
The validated implementation checkpoint is `273f35d`. Wave E removed the
unused Leaflet stock-image references and Surface 32 °F isotherm, retained the
full authoritative server Surface palette, reduced verified legacy CSS after
controlled Chrome comparisons, removed the scheduler compatibility hook,
standardized structured logging and direct-worker bootstraps, established
public MRMS/RTMA/Tropical product contracts, consolidated Satellite worker
support and shared normalization/weather math, and refreshed the retained
diagnostic tools. The final gate passes 604 Python tests plus 42 subtests, 36
JavaScript tests, repo-wide Ruff/compile/diff checks, direct worker/tool entry
points, affected API probes, and the controlled-browser checks required by the
UI slices. Temporary listeners were closed after every runtime breakpoint.

## 4. Approved current-dashboard enhancement ledger

These items may be selected after the cleanup foundation is stable. Selection
still requires a bounded implementation plan.

### 4.1 Radar WebGL expansion

Expand the existing WebGL path only to:

- `L2_RHO` — Level II correlation coefficient
- `L3_N0C` — Level III correlation coefficient
- `L3_DPR` — digital precipitation rate
- `L3_DAA` — digital precipitation accumulation
- `L3_DTA` — digital storm-total accumulation

High-zoom use matters for tornado debris signatures and localized rainfall
assessment. Preserve the current server-generated PNG as authority/fallback,
and validate color/value parity, no-data handling, legends, inspector values,
frame timing, memory, and browser compatibility. All-product WebGL beyond this
set is **parked**. Retiring PNG and adding a current-dashboard Radar tile server
are **rejected**.

Filtered Reflectivity is **rejected and removed**; custom `.pal` files provide
the desired display alternative.

### 4.2 Shared non-Workspace alert notifications — implemented

The browser-page monitor is implemented and committed on every non-Workspace
dashboard page, including Alerts, with this exact contract:

- It runs only while at least one non-Workspace dashboard tab is open and the
  local server is running. It is not a Windows service and does not use OS
  notifications.
- Scope is national. Use the existing Workspace event allowlist:
  `Tornado Warning`, `Tornado Watch`, `Severe Thunderstorm Warning`,
  `Severe Thunderstorm Watch`, `Flash Flood Warning`, and `Flash Flood Watch`.
- Deduplicate banner, one sound burst, and one border flash across
  non-Workspace tabs so one alert is not announced by every open page. The
  flash matches the alert color; simultaneous alerts use this priority:
  Tornado Warning, Severe Thunderstorm Warning, Flash Flood Warning, Tornado
  Watch, Severe Thunderstorm Watch, then Flash Flood Watch.
- On a non-Alerts page, clicking the notice opens `/workspace` in a new tab,
  selects the active alert, and zooms to it so Workspace tools are available
  around the warned polygon.
- On `/alerts`, clicking selects and zooms in the current tab.
- Alerts exposes one shared persisted On/Off control. The prior page-local
  `Severe / All Selected / Off` selector is retired because its expanded event
  semantics conflict with the fixed cross-page allowlist.
- Workspace keeps its separate Workspace-specific notification system because
  it may split from the main dashboard in Version 2.

Implementation boundary: one same-origin focused/visible owner polls and
presents; owner handoff preserves bounded seen IDs. `BroadcastChannel` and
expiring `localStorage` presence provide coordination/fallback. If neither is
available, notifications fail closed. A destination `/workspace?alert=` performs
its own one-time national lookup so click-through selection does not depend on
polling ownership or add Workspace to the shared monitor cohort. Different
browsers/profiles/private contexts/origins remain separate cohorts by browser
security. The Alerts API supplies the current server-session start time. An
alert is eligible to notify only when its valid issuance timestamp is later
than both that server boundary and the current browser-cohort boundary;
missing timestamps fail closed.

The Section 4.2 base monitor is committed. Its later server-session cutoff,
cadence/audio, and national-rail follow-up is committed as `8ffcd14`. Its
isolated staged snapshot passes 615 Python tests plus 42 subtests, all 45 Node
tests, Ruff, and JavaScript syntax. An isolated in-process API probe returned a
valid current server-start timestamp with the national alert payload.
Controlled in-app browser
checks confirmed the earlier Surface/Radar ownership and cross-tab Alerts
On/Off behavior; the corrected active-alert deep link additionally opened a
real Severe Thunderstorm Warning in Workspace, removed the query parameter,
drew the selected polygon at z9, opened detail, exposed the Projected Arrival
radar-site prompt, logged no warnings/errors, and added no shared monitor host
to Workspace. Owner smoke then observed a genuinely new Flash Flood Warning on
Tropical and confirmed that its notice opened the matching alert in Workspace.
Priority ordering and the highest-priority alert-color flash remain
deterministic Node proof; the live smoke did not separately record the visual
border-flash color.

Owner smoke on 2026-08-24 observed a new Severe Thunderstorm Warning but found
roughly two minutes of issuance-to-notice latency and a clipped sound opening.
The retained generations showed the 30-second monitor cadence combining with
the 35-second cache TTL into roughly 60-second refresh steps. The committed
alert-only correction exposes cache TTL in the API, caps ordinary owner
polling at 20 seconds, schedules the next stale check at the actual TTL
boundary, and preloads/unlocks the sound on first interaction. Seven focused
Node cases and 81 focused Python cases pass. The full combined gate passes 623
Python tests plus 42 subtests, all 48 Node tests, Ruff, and diff checks. The
restarted owner smoke passed on 2026-08-24: a naturally issued alert notified
within 60 seconds of issuance.

AWS notifications, OS-level/background notifications, and Windows always-on
monitoring are **rejected**.

### 4.3 International Radar

Long-range current-dashboard enhancement: investigate official/usable sources
and licensing for ECCC Canada, DWD Germany, and BOM Australia. Preserve provider
cadence, projection, legends, geographic metadata, and graceful source failure.

### 4.4 Satellite

A bounded Meteosat latency overhaul is in progress. Phase 0 captured a fresh
benchmark matrix and tolerance-capable golden harness; Phase 1 removed
redundant tile cache-busting, corrected native-zoom floors, detached inactive
frame layers, reduced redundant selection releases, deferred success copy until
imagery is visible, memoized catalog lookups, and made permanent negative tiles
cacheable. Phase 0/1 is committed as `6759832` without a pixel or render-version
change.

Owner smoke on 2026-08-14 passed Meteosat-12 Channel 13 loading, sidebar state,
scrubbing, selection changes, Satellite-to-Radar navigation during a Meteosat
load, and clean consoles. It found Himawari-9 Target using the wrong preset and
an all-platform frame-transition opacity flash in Satellite and Workspace.
First re-smoke passed the Target fix but found no visual change from a complete
replacement-readiness gate. Restoring the last known working contract then
passed owner re-smoke: completed Leaflet frame layers stay mounted at opacity 0,
incomplete/abandoned layers detach, and replacements remain readiness-gated.
That re-smoke exposed a separate GOES-19 Meso 2 starvation case when manual
scrubbing jumped ahead of not-yet-rendered animation frames. The current
cache-busted tree coalesces drag input to its resting frame and gives each
foreground frame a monotonic page generation, so superseded queued renders lose
ownership before entering the heavy render slot. Playback still pauses on
manual input and the retained no-flash layer pool is unchanged. The automated
gate passes 623 Python tests plus 42 subtests and all 48 Node tests; the
scrub-ahead reproduction passed owner re-smoke on 2026-08-24 in Satellite and
Workspace.

Phase 2a/2b/2d is committed as `7b2d9a5`: one live canvas
warp now feeds a 3x3 supertile through the shared atomic crop/publication path;
zoom-aware source caps use 2048 at z1–4, 4096 at z5–6, and the platform cap at
z7+; and all platform render namespaces are bumped. The candidate direct FCI
hyperslab slice (2c) was measured and rejected because it did not improve the
single-channel parse stage and slowed the pinned three-channel parse. Against
the same 2026-08-24 frames and archived `d1451f9` code, final z5 cold/warm p50s
change from 3401/546 ms to 2915/179 ms for Meteosat-12 Channel13, from
5750/1423 ms to 3856/375 ms for NighttimeMicrophysics, and from 606/327 ms to
469/179 ms for Meteosat-9 Channel13. The no-decimation Meteosat-12 z7 golden
row stays within max channel delta 2. Low-zoom decimation and one-pixel shifts
of thin colored reference overlays were retained as the owner visual gate. Automated
validation passes 631 Python tests plus 42 subtests, all 48 Node tests,
repo-wide Ruff/compile, and diff checks. Owner smoke passed on 2026-08-24 for
Meteosat-12 Channel13 and NighttimeMicrophysics at z3/z4/z5/z7, including the
requested current/past-frame, seam, detail, transition, and console checks.
Phase 2 is accepted and committed as its independent checkpoint.

Phase 3 is committed as `7bda975`. Satellite live misses
and the app-owned rapid accelerator now use a fair process-local byte budget
(`WX_SATELLITE_RENDER_BUDGET_MB`, default 16384 MB) based on conservative
float32 source-grid dimensions times unique product channel count. Concurrent
work is admitted while cumulative estimates fit; an oversized request runs
alone, and queued ownership cancellation releases its queue position. Radar
retains the existing `heavy_render_slot`, so the two families no longer wait on
the same semaphore. A four-render real-source probe reached four concurrent
Satellite admissions and 757 MB estimated in flight; process RSS moved from
205.9 MB to a 503.6 MB peak and settled at 451.1 MB with zero final active,
queued, or reserved work. Committed Phase 2 and Phase 3 matched all 18
same-source GOES/Meteosat PNG hashes. The automated gate passes 639 Python tests
plus 42 subtests, all 48 Node tests, repo-wide Ruff/compile, and diff checks. The
restarted simultaneous Satellite/Radar owner smoke passed on 2026-08-24: both
products loaded and remained responsive, Satellite scrub-ahead did not freeze
or flash, and the browser console stayed clean. A direct response probe
confirmed the estimated-memory header on a cache hit. Phase 3 is accepted.

Phase 4 is implemented in the current uncommitted tree. Meteosat-9/12 presence
jobs chain source prefetch into selected-product warming for the newest two
frames at z1–z6 using platform-longitude disk bounds and a reusable two-process
pool. Zooms are scheduled incrementally; selection release or new live tile
work stops further scheduling, while already-running canvases may finish and
publish atomically. Current-version warmed tile frames prune with the seven-hour
source window. A two-worker Meteosat-12 NighttimeMicrophysics temporary-cache
probe completed in 88.4 seconds, peaked 6.28 GiB above baseline, and settled at
964.2 MiB parent-plus-worker RSS. Warmed/live center-tile deltas stayed within
the accepted shared-canvas/low-zoom envelope. The automated gate passes 647
Python tests plus 42 subtests, all 48 Node tests, repo-wide Ruff/compile, and
diff checks. Restarted owner smoke remains required before Phase 4 is accepted
or committed; Phase 5 has not started.

- Satellite Archive UI on the active satellite-v2 contract.
- Controls redesign without changing page/engine ownership.
- Optional measured GDAL warp-thread tuning; adopt only with repeatable gains
  and output parity.
- Optional CONUS light warming, explicitly opt-in and measured.
- Storm-centered Satellite viewport behavior for Tropical.
- Meteosat SO2 recipe overrides and remaining reachable non-NOAA
  visible/composite/solar normalization.
- Robust resume/retry for large Meteosat downloads after incomplete transfers
  and upstream 503s.

Unreachable registry recipes are not future placeholders; they belong to
Cleanup Wave C unless the owner explicitly selects a named recipe first.

### 4.5 RTMA and MRMS retention

Keep the current bounded approximately 12-hour UI history. A measured, bounded
24- or 48-hour option may be considered later if operational need, upstream
availability, disk use, cold-start time, and UI value justify it. Unbounded
retention is **rejected**.

### 4.6 Water, WPC, and shared UI

- Water: clustering/density, WPC/flood-impact overlays, WaterWatch percentiles,
  and an interactive NWPS hydrograph.
- WPC: probabilistic QPF, expanded Days 1–3 and Days 4–7 Winter guidance,
  Days 1–3 Significant Weather, Days 3–7 Heat Index, and optional
  mixed-geometry Significant Weather.
- Promote the shared tabbed legend pattern where product semantics support it.
- Marine and Fire/Smoke product research.
- User preference persistence with explicit reset/migration behavior.
- RTMA wind-marker polish and Projected Arrival Tool FAQ/wiki material.

### 4.7 Unified cross-page Archive workflow

Archive tooling is one future cross-page family for every eligible product with
retained archived source files or provider access. Do not complete Surface or
Alerts as isolated Archive products before that shared workflow is selected.

Current UI boundary:

- Surface and Alerts Archive tabs are placeholders with the exact message
  `Archive tools are planned for a future update.`
- Surface's bounded recent lookback belongs to Live and ends at the current
  time; it is not an arbitrary-date Archive workflow.
- Alerts has no general lookback slider. Local Storm Report time-window pills
  remain live filtering, not Archive controls.
- Retain the existing Surface/Alerts archive endpoints, provider helpers,
  deterministic caches, and tests as groundwork; do not present them as a
  supported page workflow.

When selected, the unified family must inventory eligible pages and define
shared ending-date/time and timezone behavior, maximum span and historical age,
provider/source limits, cache/versioning, cancellation, retry/backoff, source
provenance, and page-specific rendering/playback contracts. It must distinguish
loading, legitimate no-data, unsupported range, and provider failure rather
than returning false-empty success. Surface specifically still requires a
bounded older-observation strategy because AWC's practical 24-hour window
cannot satisfy older targets and IEM access must avoid unbounded
per-state/per-frame request multiplication.

## 5. Post-refactor observation register

These observations were collected on 2026-08-05. They are preserved as
**unverified/open observations**, not confirmed current defects unless a later
owner-smoke note says otherwise. Reproduce and reconcile each against current
code before implementation.

The 2026-08-08 post-cleanup owner smoke passed the global shell, Surface display
and product behavior, Satellite, Tropical, Water, Workspace, and the quick
cross-page regression sweep. It confirmed the exceptions and timing evidence
recorded below.

General observations:

1. Investigate Workspace Alerts loading time.
2. Add first-frame and last-frame buttons to every project scrubber.

Testing batch:

1. Workspace Home may not turn off selected Storm Reports.
2. Place SPC products and Mesoscale Discussions above Satellite.
3. Put WPC Day pills above family pills and make the workflow day-first.
4. WPC products may not load and Day pills may not activate; reconcile with 3.
5. Ensure MRMS layers appear above Satellite.
6. Ensure every enabled active layer has a combined-tabbed-legend entry.
7. Standalone Satellite should fit Target, Mesoscale, and Rapid sectors.
8. Add retry/resume handling for incomplete/503 Meteosat downloads.
9. GMGSI Full Disk target: bounds `[-228.69, 103.01, -69.35, 62.27]`, center
   `[-8.67, -62.84]`, zoom `3`.
10. Investigate unusually small GMGSI Global Z3 tiles.
11. Generalize clear Loading/Stale/Legitimate Empty product UX after owner
    clarification, including whether the old product remains visible.
12. Mesoscale Discussions should load latest after warming/loading.
13. Separate Mesoscale Discussion and Storm Report pills.
14. RTMA Wind Speed should select Wind Direction; Direction remains independently
    removable and follows Wind Speed in the control order.
15. **Corrected 2026-08-09 after the confirmed 2026-08-08 smoke failure:**
    Satellite tile waits no longer occupy AnyIO's shared synchronous-request
    workers. Tile and prefetch requests carry the same per-page client identity
    as the catalog; teardown releases selection ownership, queued heavy renders
    stop when no other page owns that selection, and a render that already owns
    the heavy slot may finish and retain its completed cache artifact. On the
    restarted listener, nine simultaneous uncached Meteosat tile requests
    (eight renders and one legitimate off-disk tile) left `/api/status`,
    `/tropical`, and cache-busted CSS responsive in 23 ms, 111 ms, and 109 ms.
    A release probe returned all ten abandoned tile requests as
    `CANCELLED` in about one second and retained exactly the already-running
    artifact. Controlled Chrome selected Meteosat-12 Full Disk, forced uncached
    z7 work from a fresh process, and reached a fully loaded Tropical DOM in
    3.083 seconds with no captured console warnings/errors. Final owner smoke
    loaded Meteosat-12 Channel 13 current/past frames, then switched to another
    page while past-frame work was active; both frame loading and immediate
    cross-page navigation passed.
16. Determine whether MRMS blocks current display on full animation warming.
17. Research zooming MESH to the location behind `Largest Hail`.
18. Consider dual useful units in `mrms-legend-units`.
19. Verify whether Rotation Track’s statistic uses underlying data or legend
    scale maximum.
20. Investigate filling Drought gaps; obtain screenshots when selected.
21. Tropical Outlook card selection should show only that card’s element.
22. Atlantic viewport: bounds `[-98.48, -17.36, 8.02, 46.35]`, center
    `[28.92, -57.92]`, zoom `5`.
23. Eastern Pacific viewport: bounds `[-155.74, -74.62, -1.85, 39.1]`, center
    `[19.93, -115.18]`, zoom `5`.
24. Central Pacific viewport: bounds `[-225.06, -110.33, -11.89, 45.21]`, center
    `[19.05, -167.69]`, zoom `4.5`.
25. Replace WPC QPF subproduct dropdown repetition with time-range pills.
26. Measure current-frame-first loading with user-triggered lookback warming.
27. **Corrected product boundary, 2026-08-08:** the July 1 Surface probe exposed
    an unsupported partial UI, not a Cleanup Wave regression. Surface now keeps
    its bounded recent lookback in Live; Surface and Alerts Archive tabs are
    placeholders, and Alerts has no general lookback slider. The backend
    limitation remains useful evidence for the unified section 4.7 family: AWC
    archive requests cap `hours` at 24 even for older targets, state fallback to
    IEM is decided before nearest-time filtering, CONUS has no historical IEM
    fallback, and the service can cache empty provider frames as
    `status: success`.
28. **Measured 2026-08-09:** tile responses and logs now expose source/download,
    decode/renderer construction, and final tile render/publication separately.
    Three uncached z6 Meteosat-12 Channel 13 tiles from distinct cached-source
    frames recorded median HTTP `3.021 s`, source resolution `7 ms`, decode
    `2.948 s`, and render/publication `52 ms` (decode range `2.919-3.787 s`).
    The earlier `jobs=1 downloaded=3 errors=0 pruned=27 elapsed=0h 2m 39s`
    result came from the source-prefetch worker, which does not decode or render
    tiles; its old total also includes catalog/prune overhead and cannot be
    reconstructed more finely. Future source-prefetch runs now report explicit
    `download_ms`. Keep both observations separate and preserve output parity;
    neither is by itself an optimization baseline.

## 6. Version 2 lane

These are incremental evolutions of the existing dashboard and remain parked
until a specific design is selected:

- Measured performance profiles and conservative automatic worker guidance.
- Browser/server memory budgets, bounded caches, and diagnostics.
- Developer diagnostics for latency, queues, cache, resources, tiles, browser
  performance, and source health.
- Settings/control center, supported user configuration, and page overrides.
- Branding/design tokens, shared components, component showcase, accessibility,
  and visual regression coverage.
- Broadcast/presenter mode while OBS remains responsible for encoding/scenes.
- Plugin/provider extension research with explicit trust and compatibility
  boundaries.
- GPU/MapLibre/WebGPU research after current bottlenecks are measured.
- Multi-machine or remote-worker research, themes, and optional cloud sync.
- Licensing decision before public release.

Version 2 does not silently authorize multi-process refresh ownership. If the
deployment changes, persistent coordination must receive a new design and
decision.

## 7. Separate Greenfield project

The NCH Weather Studio Greenfield plan is a **separate project**, not Version 2
of this repository and not part of the current dashboard backlog. Its active,
current-dashboard-aware plan is
[`nch-weather-studio-greenfield-plan.md`](nch-weather-studio-greenfield-plan.md).
The superseded 2026-06-30 plan remains unchanged at
[`archive/2026-08-07-consolidation-sources/nch-weather-studio-greenfield-plan.md`](archive/2026-08-07-consolidation-sources/nch-weather-studio-greenfield-plan.md).
Ideas may be compared explicitly, but implementation work must not cross
project boundaries without an explicit owner decision.

## 8. Closed and rejected proposals

- Filtered Reflectivity implementation: rejected; use custom Radar palettes.
- AWS notification infrastructure: rejected.
- Windows service or always-on background monitoring: rejected.
- Shared notification ownership inside Workspace: rejected; Workspace stays
  separate.
- Current-dashboard all-product Radar WebGL: parked beyond the named five.
- Current-dashboard Radar PNG retirement: rejected.
- Current-dashboard Radar server tile migration: rejected.
- Unbounded retention for RTMA/MRMS: rejected.
- Persistent cross-process leases for the current single-process deployment:
  closed unless deployment changes.
- The 36 unreachable Satellite registry entries and 12 unreachable composite
  branches: approved cleanup candidates, not a dormant product roadmap.
- Removing `tl_2025_us_state.*`: rejected; it is the retained state fallback.

## 9. History, evidence, and document ownership

### 9.1 Active documents

- [`README.md`](README.md) — documentation map.
- This file — decisions, active candidates, and ordered work.
- [`next-session-startup-prompt.md`](next-session-startup-prompt.md) — concise
  startup procedure.
- [`nch-weather-studio-greenfield-plan.md`](nch-weather-studio-greenfield-plan.md)
  — active plan for the separate Greenfield project; it does not authorize
  current-dashboard or Greenfield implementation by itself.
- [`architecture.md`](architecture.md) — implemented architecture only.
- [`patterns.md`](patterns.md) — reusable implemented patterns only.

### 9.2 Preserved planning sources

The consolidation source archive contains the former superfile/startup prompt,
post-refactor observations, Version 2 proposals, Greenfield plan, and completed
cleanup Phase 2/4 records. Its README records hashes. Existing material under
`docs/archive/` remains historical and unchanged.

### 9.3 Performance evidence

All reviewed `docs/perf/` evidence remains retained and tracked. Every reviewed
phase directory has a README, and all JSON/JSONL records parsed during the
2026-08-07 audit. Performance evidence supports only the exact environment and
gate recorded with it; it is not browser proof.

Four older Radar evidence directories cited by planning text are unavailable
and were never tracked; see the consolidation-source README for their names.

### 9.4 Local-only token guide

`docs/token-saver-maybe.md` is intentionally ignored and local-only. It is not
an installed skill, cannot auto-trigger, and must never be a prerequisite for a
tracked startup prompt. Keep it short and subordinate to current system,
developer, repository, user, and selected-skill instructions.

## 10. Choosing the next slice

Cleanup Waves A through E are complete. The default next decision is to select
one bounded item from the approved current-dashboard enhancement ledger in
section 4. The ledger order does not establish priority or authorization; name
the selected family and define its exact implementation boundary before editing.

The post-cleanup Satellite cross-page blocking prerequisite is complete. A
separate bounded Meteosat latency family was selected; its Phase 0/1 baseline,
no-flash, and scrub-ahead work is committed as Satellite-only checkpoint
`6759832`. Its required scrub-ahead re-smoke passed. Phase 2a/2b/2d and its
owner visual review are committed as `7b2d9a5`; Phase 2c was rejected by its
measurement gate. Phase 3 and its passed simultaneous Satellite/Radar owner
smoke are committed as `7bda975`. Phase 4 is implemented with green automated
and temporary-cache runtime evidence in the current uncommitted tree; restarted
owner smoke remains required. Do not begin Phase 5 without separate
authorization.
The Section 4.2 base
monitor and its
server-session cutoff plus notification-cadence/audio correction and national
Alerts rail are committed as separate alert-only checkpoint `8ffcd14`. Shared
page-entry and test files received hunk-level separation: Alert used intermediate
entry cache version `20260824a`, and Satellite advanced the final version to
`20260824b`. Alert owner smoke passed with notification within 60 seconds of
issuance.
Radar WebGL remains listed first without priority. Section 4.7 retains one
future unified cross-page Archive family, not an independently selectable
Surface-only completion.

Before starting, confirm current Git status, inspect only the named paths and
their callers, define validation and rollback/fallback behavior, state explicit
exclusions, and keep unrelated work untouched.
