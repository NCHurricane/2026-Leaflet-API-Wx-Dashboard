# Dashboard Change and Enhancement Superfile

**Canonical status:** current source of truth as of 2026-09-06

**Active path:** `docs/dashboard-change-and-enhancement-superfile.md`. The
same-named file under `docs/archive/2026-08-07-consolidation-sources/` is a frozen
historical source, not a second current roadmap.

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
2. **Completed cleanup program** preserves the Wave A–E audit, execution, and
   validation boundaries as history.
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

An approved/retained proposal is not a claim that its provider access,
feasibility, or benefit has been proven. Unless section 4.8 selects it for the
rendering audit, it remains deferred. Historical sections deliberately retain
old paths, counts, measurements, and execution instructions as dated evidence;
those are not current implementation or deletion orders. Section 5 gives
explicit dispositions to the old observations, including items still needing
runtime reproduction. A documentation cross-check cannot certify those as fixed.

The owner selected a new high-cost rendering-workflow audit on 2026-09-06 and
then broadened its scope to alternative architectures, product-specific Radar
WebGL eligibility, and adaptation to different machines and browser engines.
The baseline is committed as `e200f74` plus docs checkpoint `5096e74`. Section
4.8 records the audit brief; renderer implementation still follows plan review.

## 2. Current truth and invariants

### 2.1 Application and frontend

- FastAPI serves the landing page and canonical extensionless product routes:
  `/alerts`, `/radar`, `/satellite`, `/spc`, `/surface`, `/mrms`, `/rtma`,
  `/drought`, `/tropical`, `/wpc`, `/water`, and `/workspace`.
- `frontend/` is the current UI implementation, including the shared alert
  monitor. Historical file counts are not a current asset inventory.
  Product pages import narrow shared capabilities from
  `frontend/core/`; Workspace composes engine APIs and must not import sibling
  page controllers.
- Standalone product behavior must remain independent of Workspace behavior.
  Workspace is a curated composition, not a new global page controller.
- Workspace currently composes Alerts, Radar, SPC, Satellite, RTMA-RU, MRMS,
  WPC, and Water. Drought remains standalone-only.
- The Workspace shared timeline synchronizes Radar, MRMS, Satellite, and RTMA.
  WPC retains its own issuance/product cadence.
- The owner reconfirmed the current Workspace layer order on 2026-09-06:
  MRMS and SPC remain below Satellite. Proposals to move them above it are
  deferred, not current defects.
- Leaflet and selected browser dependencies are vendored under `frontend/lib/`.
  Product pages still load Font Awesome CSS from an external CDN; full offline
  dependency independence is not implemented. The seven retained fonts are
  local assets. `css/shared.css` remains active for the landing page.
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
  or leaving the page releases it. Work still waiting for render-budget admission
  stops when no page owns the selection, while an already-running render may
  finish and atomically publish its reusable cache artifact.

### 2.3 Product contracts to preserve

These describe the current runtime baseline. Section 4.8 permits proposals to
replace rendering internals, including the PNG/tile architecture, with evidence
of equivalent final quality/correctness and worthwhile resource behavior.

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
  `.cmap` files live in `config/sat_cmaps/`; `BV.pal` remains restored at its
  active Radar path.

### 2.4 Retained development and repository paths

- `.git/` is required for repository history and synchronization.
- `.venv/`, `.ruff_cache/`, `__pycache__/`, `.pytest_cache/`, and runtime
  `cache/` are generated/local paths, not application source. The owner chose to
  retain the present virtual environment and Python bytecode caches.
- `tests/` is retained. Static checks, unit tests, API probes, native decode
  tests, controlled-browser checks, and owner smoke tests are distinct evidence
  categories and must be reported accurately.
- Remaining `tools/` and worker modules are retained because their current
  callers or validation roles survived the completed cleanup program. Any later
  removal requires a new bounded caller/asset trace.
- `pal_preview/` remains a root-dependent standalone utility and may later gain
  Satellite colortable previews.

### 2.5 Accepted September checkpoint and evidence boundary

On 2026-09-06 the owner confirmed that the existing MRMS transition and
Satellite zoom/sharpness changes passed their own checks. The accepted changes
are committed in `e200f74`. Their scope is:

- Satellite request ceilings: CONUS z9, Full Disk z8, and Meso z9.
- Shared CSS preserves discrete Satellite tile and Radar PNG pixels during
  browser scaling; native MRMS loaded tiles are opaque before promotion.
- Incoming MRMS PNGs remain hidden until they own the displayed frame, including
  while the user changes opacity. The old complete image remains visible.
- Product-page CSS versions and corresponding existing tests are reconciled.
- `img/20260831_nchurricane_logo.svg` is retained as an additional owner asset;
  it does not replace the canonical Chuck Copeland Weather branding.

The checkpoint commit and fresh automated results are recorded in the startup
handoff. Owner acceptance is distinct from automated checks; this reconciliation
does not claim a new controlled-browser run or new performance measurements.

## 3. Completed cleanup program (historical execution record)

The Wave A–E bullets below preserve the approved execution boundaries and
validation design. They are not open tasks; the completion record is in section
3.6.

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

## 4. Current-dashboard work and deferred proposals

The cleanup foundation is complete. These proposals remain eligible, but the
current selected focus is the rendering audit in section 4.8. Implementation
still requires an agreed bounded plan.

### 4.1 Radar WebGL expansion

Evaluate every exposed Radar product for a worthwhile WebGL path. The earlier
five-product limit was superseded by the owner's expanded audit scope on
2026-09-06. Previously named candidates remain:

- `L2_RHO` — Level II correlation coefficient
- `L3_N0C` — Level III correlation coefficient
- `L3_DPR` — digital precipitation rate
- `L3_DAA` — digital precipitation accumulation
- `L3_DTA` — digital storm-total accumulation

High-zoom use matters for tornado debris signatures and localized rainfall
assessment. Native resolution alone does not establish a benefit: assess detail,
upload/render/playback cost, color/value parity, no-data handling, legends,
inspector values, frame timing, memory, and browser fallback per product. A
native low-resolution product is not automatically an expansion candidate.

The current PNG path remains the implemented reference/fallback during the
audit. Alternative tile architectures and replacing PNG may now be evaluated;
the prior architectural exclusions no longer limit recommendations. No such
change is implemented or selected merely by widening the audit. A replacement
must retain final quality, data correctness, supported-browser behavior, and
demonstrable resource efficiency.

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

A bounded Meteosat latency overhaul completed through Phase 5 and closed at
`3773d47`. The detailed paragraphs below are completion evidence, not active
tasks. Phase 0 captured a fresh
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
scrubbing jumped ahead of not-yet-rendered animation frames. The correction
committed in `6759832` coalesces drag input to its resting frame and gives each
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

Phase 4's core implementation landed in `68aeb72`. Meteosat-9/12 presence
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
diff checks. The first restarted owner smoke on 2026-08-25 found that a catalog
refresh could advance foreground ownership while a ready retained layer kept
its prior tile URL; subsequent pan/zoom misses therefore returned transparent
`CANCELLED` tiles. The correction later committed in `0e1eacb` advances that retained
URL without redrawing mounted tiles. Its correction gate passes 647 Python
tests plus 42 subtests and all 49 Node tests, and a controlled browser
refresh/zoom loaded z5 256x256 tiles at the new generation while health stayed
responsive and the console stayed clean. The next owner run loaded and scrubbed
M12 without flashing, but the server then disappeared twice without a Python
traceback. Windows Event Viewer recorded both failures as `python.exe` access
violations in the bundled NetCDF DLL (`0xc0000005`), at 20:45 and 21:10 on
2026-08-25. The alert refresh at the end of the captured terminal output was a
timing coincidence, not the crash owner. Different destination zooms use distinct
FCI raster-cache keys and could therefore enter native NetCDF-C/HDF5 reads
concurrently. The correction committed in `0e1eacb` serializes only FCI native file
access process-wide; calibration, canvas rendering, and unrelated Satellite
families retain concurrency. The focused FCI gate passes five tests, including a
two-thread/different-grid-cap ownership regression. A real-source probe loaded all
40 crash-frame chunks through simultaneous 2048/4096 callers in 5.0 seconds. An
isolated server returned 200 for simultaneous cold z6/z7 M12 renders; a second run
overlapped alert refresh with two more cold renders, all requests returned 200, all
80 health probes over 40 seconds passed, and Windows recorded no new native crash.
The next restarted owner run on 2026-08-26 did not crash: the server continued
returning 200 for z4-z7 tile generations and alerts, `/health` stayed responsive,
and Windows recorded no new NetCDF APPCRASH. A notification activation loaded
`/workspace?alert=...`; presentation alone does not navigate. Rapid scrubbing
instead exposed a frontend ownership race. The prior retained-layer correction
suppressed redraw for incomplete reused layers as well as completed layers, so
superseded requests could finish as transparent `CANCELLED` PNGs and still satisfy
Leaflet's loaded-image check. An older pending swap could also detach the same
layer after a newer scrub request reclaimed it. The correction committed in
`0e1eacb` preserves
completed retained tile DOM without redraw, restarts incomplete layers at the new
generation, and lets only the current pending owner detach an abandoned layer.
Two deterministic animator regressions failed before the correction and pass
after it. A cache-busted controlled browser repeated three-frame z7 scrubbing;
all retained layers stayed attached, exactly one stayed at opacity 1, its tiles
were 256x256 PNGs, `/health` returned 200, and the console stayed clean. The
complete gate passes 648 Python tests plus 42 subtests, all 51 Node tests,
repo-wide Ruff/compile, and diff checks.
The next owner re-smoke on 2026-08-26 confirmed that rapid scrubbing and stopping
on an older M12 frame no longer locks the dashboard. It also exposed a catalog-window
defect: at 21:51Z the one-hour request returned only the 21:00Z and 21:15Z frames,
while a three-hour request showed the intact 15-minute sequence from 19:00Z through
21:15Z. The cached-catalog path measured the requested hour from wall-clock time, so
the provider's 36-minute publication delay consumed most of the animation window.
The correction committed in `0e1eacb` anchors fresh and cached lookback filtering to the
newest available frame, capped at the current time. A regression covers a 40-minute
delayed feed and passes for both catalog paths. Subsequent owner smoke loaded M12
Channel09, Channel02, and Dust quickly; each showed five frames, rapid scrubbing stayed
responsive, and an alert notification arrived without terminal errors, console errors,
blank tiles, or a lockup. This cleared the alert-overlap check. The later final restarted
M12 owner check also verified the corrected catalog window.

The `0e1eacb` checkpoint also adds an RSS-tuned selected-product workflow for
Meteosat-11. Channel02 and Channel13 retain their existing 12-frame z6-z7 rapid tail;
other selected channels and composites use a separate `meteosat-rss-tiles` job. It limits
source prefetch to the newest two frames with no older backfill, then uses the reused
Meteosat pool to warm the newest four frames at z4-z7 over RSS bounds. The 225-second job
retains three hours, yields to live work, cancels with selection ownership, and enters the
shared byte budget. The bounded plan is 1,276 tiles per frame / 5,104 per four-frame tail.
Pixels and render versions do not change. The complete gate now passes 654 Python tests
plus 42 subtests and all 51 Node tests, repo-wide Ruff/compile, and diff checks.

The restarted M11 RSS owner re-smoke passed on 2026-08-26. Channel13 remained on the
rapid path and completed six frames / 6,581 rendered tiles in 2m12s with zero errors;
the invalid counts were expected off-footprint tiles. Selecting NighttimeMicrophysics
activated the new RSS source stage, which considered only the newest two frames, found
both cached, downloaded nothing, pruned four stale source and four stale tile-frame
directories, and completed with zero errors. Current and older-frame z5 requests returned
200 while alert refreshes overlapped, and scrubbing and zooming caused no lockup. Softer
imagery when zoomed is expected from the native 3712-column SEVIRI VIS/IR grid; RSS changes
cadence and the workflow changes delivery, not source spatial detail. The RSS extension
is accepted.

The final restarted M12 owner check passed on 2026-08-26: the one-hour catalog showed five
frames, several FCI products loaded and remained responsive, and Windows Event Viewer's
Application log contained no new NetCDF error or APPCRASH. Together with the prior
automated, controlled-browser, runtime, alert-overlap, scrub, and RSS evidence, Phase 4
is accepted as a whole. Its remaining corrections and RSS tuning are committed in `0e1eacb`.

On 2026-08-26, before Phase 5, the shared dashboard basemap catalog was moved off
unauthenticated CARTO raster tiles after CARTO began rendering an `API KEY REQUIRED`
watermark. USGS sources were removed. All canonical map pages now expose the same four
owner-selected Esri services: World Dark Gray Base, World Light Gray Base, USA Topo Maps,
and World Imagery. No separate Esri reference/label layer is added; World Imagery is the
label-free imagery choice, while USA Topo has labels baked into its source cartography and
the gray base services retain Esri's minimal built-in reference detail. The Dark selection
applies a layer-scoped dark-navy filter to the keyless Esri raster; data tiles and the other
three basemaps retain their source colors. Shared boundary overlays were also softened and
moved from thousands of SVG paths to one Leaflet canvas. CONUS-default pages keep states on,
show countries below displayed zoom 7, and add counties at displayed zoom 8. Satellite and
Tropical retain countries at every zoom, add states at displayed zoom 5, and add counties at
displayed zoom 8. Hidden boundary datasets are not fetched solely to turn them off. The full
automated gate passes 655 Python tests plus 42 subtests and all 54 Node tests. Controlled
in-app browser checks loaded 256-pixel tiles from each intended Esri service in Workspace
with no `API KEY REQUIRED` text; later Workspace, Tropical, and Satellite checks confirmed
the family-specific z5/z7/z8 boundary transitions, one-canvas rendering, and no console
warnings/errors. The owner cross-page smoke passed and the basemap/boundary checkpoint is
committed in `6020906`.

Meteosat latency Phase 5 is committed in `3773d47`. EUMETSAT searches
now page through the requested window with the live API's zero-based `si` offset; complete
FCI feature metadata is retained for five minutes so the immediate download path does not
repeat a 12-hour search; 5xx responses, timeouts, and connection errors receive three bounded
0.5 / 1 / 2 second retries while the existing one-time 401 token refresh remains; and the
FCI download default is raised from two to a hard ceiling of four. A live 12-hour M11 RSS
probe returned 156 unique products across two pages. Five M12 samples cut the catalog-plus-
feature request count from two to one and improved p50/p95 from 3.871/4.537 seconds to
1.341/1.505 seconds. The full gate passes 662 Python tests plus 42 subtests, all 54 Node
tests, repo-wide Ruff, and diff checks. No render code, pixels, or render version changed.
The restarted owner smoke passed the newly available M12 acquisition, five-frame catalog,
responsive scrubbing, and clean terminal/console checks. Phase 5 is accepted and the
bounded latency family is complete.

Remaining Satellite scope is below. Rendering-specific items may be assessed
under section 4.8; Archive and standalone control redesign remain deferred:

- Satellite Archive UI on the active satellite-v2 contract.
- Controls redesign without changing page/engine ownership.
- Optional measured GDAL warp-thread tuning; adopt only with repeatable gains
  and output parity.
- Optional CONUS light warming, explicitly opt-in and measured.
- Storm-centered Satellite viewport behavior for Tropical.
- Investigate remaining Meteosat SO2 recipe differences and reachable non-NOAA
  visible/composite/solar normalization. EUMETSAT-specific recipe handling
  already exists in `satellite_v2/composites.py`; inventory actual gaps before
  treating the whole normalization family as unimplemented.
- Recovery/resume for interrupted large Meteosat streamed transfers. Phase 5
  already provides bounded connection/timeout/5xx request retries and reuse of
  completed FCI chunks; partial individual transfers are discarded on failure.
  Define the remaining transfer-level contract before proposing further work.

Unreachable registry recipes and their disconnected composite branches were
removed in Cleanup Wave C (`c0e6ced`). They are completed cleanup history, not
remaining candidates or future placeholders.

### 4.5 RTMA and MRMS retention

Keep the current bounded approximately 12-hour UI history. A measured, bounded
24- or 48-hour option may be considered later if operational need, upstream
availability, disk use, cold-start time, and UI value justify it. Unbounded
retention is **rejected**.

### 4.6 Water, WPC, and shared UI

**Code/documentation reconciliation, 2026-09-06:** WPC Significant Weather
Days 1–3 plus the combined Days 1–3 product are implemented in the catalog,
parser, service, and frontend; this is not future base-product work.
`config/wpc_config.py` defines Winter probabilities for Days 1–3 (snow over
4/8/12 inches and ice over 0.25 inch). Later-day buttons in the page do not
establish catalog support for Days 4–7. Water already displays provider
hydrograph images linked to the gauge page. These are static source findings,
not a fresh live-provider or browser acceptance run.

Remaining deferred proposals:

- Water: station clustering/density, WPC/flood-impact overlays, WaterWatch
  percentiles, and an interactive NWPS time-series hydrograph beyond the
  existing linked image. City-label density is already a separate control.
- WPC: probabilistic QPF; specifically identified Winter additions beyond the
  existing Days 1–3 thresholds and an investigated Days 4–7 source contract;
  Days 3–7 Heat Index; and non-polygon/mixed-geometry Significant Weather
  beyond the existing polygon parser. Do not relist implemented base products
  as enhancements. Source availability and feasibility need verification when
  selected.
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

### 4.8 High-cost rendering-workflow audit — owner brief, plan review next

Owner decisions, 2026-09-06: audit Satellite (especially Meteosat), Radar, MRMS,
and RTMA for efficient modern rendering, including approaches that replace the
existing architecture. Evaluate all Radar products for worthwhile WebGL benefits;
the earlier five-product list is a starting point. Adapt to users' available
resources rather than treating the owner's high-end CPU/DRAM/VRAM as universal.
Support modern Blink/Chromium, WebKit, and Gecko browsers with compatibility
extending at least a couple of years. Baseline commits are `e200f74` and
`5096e74`; their acceptance does not exempt current caps or architecture from
review. No implementation or new performance measurements have been performed.

#### Scope and quality criteria

- Trace acquisition, decoding, reprojection/resampling, rendering, publication,
  cache reuse, queue ownership, transfer/upload, and browser presentation.
  Cover first frames, cached frames, history/playback, and concurrent standalone
  and Workspace use. Compare current and candidate work at equal output quality.
- Review Satellite resolution end to end for each platform, channel/composite,
  sector, location, and display scale: native source detail, loader decimation,
  projection geometry, tile zoom ceilings/floors, default views, device pixel
  ratio, and browser scaling. Identify both premature caps that discard available
  detail and higher zooms that only enlarge the same source pixels. Do not
  equate a higher tile zoom or a sharper-looking filter with new source detail.
- Preserve meaningful native detail, values, palette/legend/inspector agreement,
  projection alignment, coverage/alpha, frame identity, and requested time
  semantics. No efficiency claim may rely on degraded final output or hidden
  frame dropping. Existing no-flash behavior and navigation responsiveness are
  acceptance outcomes, while their internal implementation may be reconsidered.
- Compare total CPU/GPU work, wall time, peak/resident memory, cache footprint,
  and I/O at the same workload. More concurrency or a larger cache alone does
  not prove greater efficiency. Report tradeoffs instead of collapsing them into
  one speed number. Implementation remains a separate decision after findings.

#### Resource adaptation — proposed audit design

- Budget the Python/backend host and each browser client separately, including
  shared-machine competition. Do not infer client GPU capacity from server RAM.
- Evaluate conservative startup budgets, bounded calibration, live performance
  observations, and explicit user overrides. On the backend, inspect available
  memory and effective CPU resources; treat browser hardware hints as optional
  and approximate. WebGL exposes no portable total/free-VRAM query, and browser
  memory/core hints are not reliable complete inventories. See
  [MDN device memory](https://developer.mozilla.org/en-US/docs/Web/API/Navigator/deviceMemory),
  [hardware concurrency](https://developer.mozilla.org/en-US/docs/Web/API/Navigator/hardwareConcurrency),
  and [WebGL memory budgeting](https://developer.mozilla.org/en-US/docs/Web/API/WebGL_API/WebGL_best_practices#estimate_a_per-pixel_vram_budget).
- Scale concurrency, cache residency, prefetch, and background warming within
  measured budgets, keeping foreground work responsive and leaving headroom for
  other applications. Under pressure, reduce speculative work/residency first;
  do not silently lower final resolution, alter values, or shorten requested
  history. A weaker machine may complete the same work more slowly.
- Include lower-resource/integrated-GPU and ordinary midrange systems alongside
  the owner's high-end machine in the planned evidence matrix. Resource limits
  on the owner's rig are useful stress probes, not proof for other hardware.
  Provider concurrency/rate ceilings remain independent of machine capacity.

#### Browser support — proposed acceptance policy

- Cover Blink/Chromium, WebKit, and Gecko through representative Chrome/Edge,
  Safari, and Firefox runs; include applicable mobile/OS combinations when
  claiming those targets. A shared engine name alone is not complete browser
  or GPU-driver proof. Record exact browser/OS/GPU evidence and untested gaps.
- Use Baseline **Widely available** as the default feature floor. It means a
  feature has been interoperable across the core browser set for 30 months,
  not that every release from the last 30 months has been tested. This is a
  compatibility guide, not a universal support mandate. See
  [Web Platform Baseline](https://web.dev/baseline).
- Propose a rolling 30-month browser-release compatibility target to make
  "at least a couple of years" concrete. Pin representative oldest/current
  versions and supported ESR/OS combinations in the execution plan; enumerate
  coverage rather than claiming every release was exercised.
- Feature-detect and validate optional acceleration, with a quality-equivalent
  compatible path when APIs/extensions are unavailable, a context cannot be
  created, or GPU work fails. Newly available capabilities may be optional
  candidates; an API existing does not establish useful performance.

Historical phase acceptances remain closed and retain their recorded evidence.
Prior rendering choices, caps, and rejected architectures may be reassessed with
fresh evidence under this new scope. Current Workspace layer order remains
unchanged. Other enhancement families and the separate Greenfield project stay
deferred. Agree the bounded audit execution/measurement plan before expensive
live runs, then select implementation slices from its findings.

#### Bounded audit and measurement plan — proposed 2026-09-06

**Review status:** draft for owner review. This adds a plan to the existing
working-tree brief, not authorization to run benchmarks or change renderers.
Git inspection confirmed HEAD `5096e74` immediately after `e200f74`, with the
five expected documentation files modified. Findings below come from read-only
source tracing and primary-source research; no app startup, native decode,
provider acquisition, timing run, or browser test was performed in this audit.

**Recommended order:** resolve source-detail and resource-accounting questions
first, capture a small baseline second, then select at most two architecture
experiments across the four families. Do not expand every combination of
platform, product, zoom, cache state, browser, and machine into a benchmark.

##### A. What is known, and what still needs evidence

| Area | Verified source behavior | Question for the audit |
| --- | --- | --- |
| Satellite request policy | `max_native_zoom_for_product` in `config/satellite_v2_config.py` uses sector only: Full Disk/Global z8; Meso z9; other sectors, including RSS/Japan/Target, z9. The channel argument does not affect the result. | Where do these limits discard visible source detail, and where do they request larger images without additional information? |
| Satellite floors and views | `frontend/pages/satellite/satellite-anim.js` uses Full Disk floor z1, Global z2, RSS/Target z4, and z5 otherwise; 256-pixel tiles can be displayed through z19. Standalone presets include GMGSI z2, GK2A z3, M12/RSS z4, M9 z5, Japan z6, and dynamic Meso/Target bounds. Workspace reuses the animator but has its own curated selections and map view. | Check actual opening zoom after container sizing, sector aliases, bounds fitting, fractional zoom, and DPR. Warming zooms, catalog availability, request floors, and displayed zoom are different controls. |
| Satellite loading and warping | `satellite_v2/renderer.py` applies 2048/4096 source caps at z1–4/z5–6 and platform caps at z7+. ABI decimation applies to Full Disk; AHI/AMI/FCI enforce caps in their loaders. SEVIRI/GMGSI retain their separate native paths. Scalar channels use bilinear warp, categorical ADP uses nearest; composites combine warped channels. Live misses normally produce a 3x3 supertile. | Measure sampling loss/aliasing before warp, duplicate decode across zoom-cap keys, and the useful fraction of neighbor tiles. Does selective window reading or a reusable native grid beat repeated decode without changing output? |
| FCI detail and admission estimate | FCI defaults to a 10848 grid cap and chooses a power-of-two stride. An input with 11136 columns would therefore retain 5568 even at z7+. The admission estimator assumes an FCI side no larger than 5568; native access is serialized inside each process. | Verify actual channel dimensions in the selected `EO:EUM:DAT:0662` files. Check visible/NIR loss and whether higher configured caps make the estimator undercount. Full chunk reads precede the current stride; retained-array bytes are not peak decode memory. This is a conditional code finding, not a newly reproduced image defect. |
| Backend and browser budgets | Defaults include 16 GiB Satellite in-flight admission, 4 GiB source-raster cache, ten live tile request workers, two Meteosat warming processes, and up to 72 retained Satellite layers. Oversized Satellite admissions can run alone. Radar/MRMS/RTMA heavy work uses a separate semaphore. | Count parent/child caches, transient native arrays, renderer references, GDAL buffers, other families, decoded images and GPU allocations together. Neither an admission estimate nor a frame-count limit establishes a whole-machine memory bound. Verify effective settings rather than assuming defaults are active. |
| Radar | `radar/webgl_artifact.py` supports `L2_REF`, `L2_VEL`, `L2_SRV`, `L3_N0B`, and `L3_N0G`; configuration defaults their acceleration switches off. PNG rendering precedes optional artifact publication. Current thresholds are prefetch z10/activation z11, four textures/two loads; canvas DPR is capped at 2. | Compare full PNG plus artifact cost with alternatives, including upload and first display. Trace actual ray/gate geometry, encoding precision, masks, and palette behavior for all 19 configured products. A nominal PNG dimension does not prove native polar detail is retained. |
| MRMS | `mrms/mrms_tiles.py` already writes a tiled float32 GeoTIFF and warps source bands to 256-pixel PNG tiles with nearest sampling. Tiles start at z7; RotationTrack/AzShear cap at z8 and other products at z7. The whole-overlay fallback is capped at 4096 pixels. | Establish high-zoom tile/fallback detail, repeated preparation cost, source reuse, and whether any scalar GPU path would repay its extra preparation and transfer. The tiled source is not yet evidence that a COG conversion would help. |
| MRMS first display | Workspace calls `loadLatest` before starting history. Standalone calls `loadFrames` first and uses `loadLatest` when no frames return. | Measure each page's response-to-display path. This call order does not establish that standalone waits for the entire history to render. Trace coordinator work and PNG/native-tile promotion separately. |
| RTMA | For 2D coordinates, `rtma/rtma_utils.py` uses four-neighbor inverse-distance interpolation onto latitude/longitude, with `cKDTree.query(workers=-1)`, then another warp to Mercator using the shared 4096 cap. Points are source-frame-locked. | Can valid native CRS/transform metadata support one direct warp? Otherwise can a reusable geolocation mapping reduce work? Check all regions and derived products; do not assume every grid is affine or that the intermediate interpolation is expendable without quality evidence. |

Source-resolution checks must distinguish the instrument's best capability
from the particular delivered channel/collection. For example, the
[EUMETSAT FCI guide](https://user.eumetsat.int/resources/user-guides/mtg-fci-level-1c-data-guide)
distinguishes normal/high-resolution channels, while the
[ABI specification](https://www.goes-r.gov/spacesegment/abi.html) and
[JMA AHI table](https://www.data.jma.go.jp/mscweb/en/himawari89/space_segment/spsg_ahi.html)
show differing visible/IR resolutions. Actual file dimensions, calibration,
projection, channel mapping and scan mode must populate the inventory.

GMGSI needs an explicit provenance check: the loader comment describes an 8 km
Mercator grid, whereas the current
[NOAA product page](https://www.ospo.noaa.gov/products/imagery/gmgsi/) describes
approximately 3 km imagery. These may describe different deliverables. Inspect
the actual `noaa-gmgsi-pds` NetCDF dimensions/coordinates before assigning either
number to the app or interpreting the reported small z3 tiles.

Observation dispositions remain intact. Include testing-batch items 7–10, 16
and 26 in this audit. Use item 6 only for the selected layers' legend parity
and item 19 for MRMS value/statistic provenance. Items 15/28 are regression
contracts/historical measurements, not newly open defects. Item 14 remains a
deferred standalone RTMA control proposal. MRMS/SPC stay below Satellite;
unrelated observations, Archive and Greenfield remain deferred.

##### B. Inventory and representative cases

Finish a lightweight inventory of every exposed Satellite platform/sector and
product recipe, all Radar products, and MRMS/RTMA grid/product classes. Group
identical paths after recording exceptions; do not benchmark every channel.
For Satellite, each inventory row should contain:

- Provider/collection, native channel names, source shape/dtype/calibration,
  scan footprint, source CRS/transform and local pixel footprints.
- Loader stride and sampling offset at each cap transition, retained shape,
  unique composite inputs, resampling rule and alpha/no-data treatment.
- Opening view, fit limits, request floor/ceiling, cached/warmed zooms, display
  zoom, tile size, viewport CSS pixels, physical pixels/DPR, and browser scaling.
- Requested versus actually useful source samples and output pixels; identify
  which stage loses detail or enlarges already sampled data.

Compare local source pixel footprints with destination pixel footprints in both
axes, including near the geostationary limb. For orientation, a 256-pixel
Mercator tile has approximately `156543.03 * cos(latitude) / 2^z` ground metres
per pixel; use the actual transforms for decisions. Track physical display
sampling separately. A larger tile zoom, DPR, or nearest-looking CSS filter
does not recover samples discarded by the loader. Conversely, avoiding
upscaling must not prevent useful map zooming; native imagery can be enlarged
for inspection without generating redundant source requests.
[Leaflet's native zoom controls](https://leafletjs.com/reference.html#gridlayer-maxnativezoom)
explicitly scale tiles above/below their native limits.

| Case family | Required representative coverage | Initial timing selection |
| --- | --- | --- |
| M12 FCI | Channel13 IR, Channel02 visible, NighttimeMicrophysics multi-channel; default view, z4/5 and z6/7 transitions, z8 and display above the cap; disk interior and limb/chunk seam | Three cells: IR z5, visible z8, composite z5 |
| M9/M11 SEVIRI | M9 Full Disk scalar/composite; M11 RSS rapid Channel13 and selected non-rapid composite; cropped coverage and current/history ownership | One cell: RSS non-rapid composite at z5 |
| GOES-18/19 ABI | Full Disk highest-detail visible and IR; CONUS and both Meso defaults; mixed-resolution RGB; sparse ADP/AOD/FRP alpha/value checks | One cell: Full Disk Channel02 at z8 |
| Himawari/GK2A/GMGSI | AHI Full Disk visible plus Japan/Target fit; AMI visible/mixed-resolution RGB; all four GMGSI products' metadata, z2/z3 view and longitude seam | One cell: GMGSI Channel13 at z3; promote AHI/AMI only if their trace differs materially |
| Radar | Existing `L2_REF` WebGL control; `L2_RHO`/`L3_N0C` debris-signature detail; `L3_DPR`/`L3_DAA`/`L3_DTA` precipitation precision/range; categorical `L3_N0H`; native coarse `L3_EET`/`L3_DVL` controls; near/far range and azimuth seam | Two cells: `L2_REF` at z11 and `L2_RHO` PNG at z11; later candidate choice may substitute a precipitation product |
| MRMS | Standard-grid MESH and finer RotationTrack/AzShear; CONUS versus local z7/8/above-cap; latest, history, pending PNG and tile promotion | Two cells: MESH z7 and one RotationTrack z8 |
| RTMA | CONUS hourly temperature; rapid-update Workspace Winds; AK plus one small HI/PR grid for geometry; Feels Like and one time-difference product for input reuse | Two cells: CONUS temperature and rapid-update Winds at the selected default view |

The initial selection is **12 timing cells**, not a claim that the other
coverage rows have been exercised. Metadata/small quality samples cover the
exceptions; a newly identified path replaces a timing cell or returns for
review instead of silently expanding the matrix. Pin exact available source
IDs/times/hashes and map coordinates before running. Favor retained fixtures;
do not assume an old source still exists or substitute today's changing feed
inside a comparison. Choose a small-feature scene for detail and a masked or
edge scene for coverage; reuse files across products where possible.

##### C. Measurement protocol and stopping limits

After owner review, the first measurement pass would use existing renderers
and existing instrumentation. Review `satellite_v2/bench.py`,
`satellite_v2/_bench_timing.py`, `radar/bench.py`, tile response headers and
coordinator metrics before adding instrumentation. Satellite's CLI can purge
target frame tiles; always give it a verified, isolated scratch cache. Preserve
owner caches, historical goldens, listeners and optional-warmer settings.

1. **Cache states:** (a) local source present, fresh renderer process and no
   derived artifact; (b) decoded source warm but requested derived artifact
   absent; (c) derived artifact hit. If a family has no decoded-cache state,
   mark it not applicable. Browser HTTP cache and decoded-image/texture state
   are separate labels. A fresh process is not a cold OS filesystem cache.
2. **Bounds:** at most three repetitions per applicable state per timing cell
   (108 samples maximum), 45 minutes of active measurement and 10 GiB of new
   scratch artifacts on the first host, stopping at whichever limit occurs
   first. No new provider downloads in this initial pass; missing fixtures
   become evidence gaps. Stop on native crash, OOM, sustained paging or
   responsiveness failure and preserve the trace rather than retrying blindly.
3. **Acquisition:** if missing-source latency matters after local results,
   propose a separate named-source batch with bytes/request/time ceilings
   before downloads. Measure catalog, transfer, retries and publication delay
   separately; do not call source-prefetch time a render benchmark.
4. **Attribution:** record queue/admission wait, download, native decode and
   calibration, source-to-target warp, composite/colorization, encoding,
   atomic publication, response transfer, browser decode, texture upload, and
   first complete visible frame. Preserve critical-path wall time and aggregate
   CPU-seconds/process-tree memory; overlapping stage durations must not simply
   be added and reported as elapsed time.
5. **Resources:** record peak and settled process-tree RSS/private memory,
   host available memory/commit/paging, effective threads/processes, source and
   derived disk bytes, bytes read/written/transferred, cache hit/miss/eviction,
   useful versus speculative tiles, cancelled/stale work, and browser process,
   decoded-image and estimated texture bytes. JS heap alone is insufficient.
   Use GPU timers/counters where available; label CPU submission time and
   estimated allocations honestly when actual GPU duration/residency is absent.
6. **Interaction:** on four anchors (M12, existing Radar WebGL, MRMS, RTMA),
   observe current-first load, a fixed up-to-12-frame sequence at source cadence,
   play/pause, rapid scrub and release, pan/zoom, product switch, teardown and
   navigation. Then run one Workspace combination plus one same-source
   standalone tab to expose reuse, contention and multi-client cancellation.
   Keep frame IDs/counts constant across comparisons; shorter diagnostic loops
   do not alter the application's requested history. Include one bounded full
   existing MRMS/RTMA history request to test history scheduling when fixtures
   exist. Browser work is a separate, capped 20-minute trace batch on the first
   available configuration, not nine configurations times the full benchmark.
7. **Statistics:** three samples establish ranges/medians and identify missing
   instrumentation, not a reliable p95. Only a promising comparison earns a
   follow-up batch of at least 20 paired runs, with alternating control/candidate
   order and variability reported. Estimate interaction tails from many events
   within the fixed trace, labeled separately from frame-load sample counts.

Produce a new dated `docs/perf/` evidence record only when measurements exist:
manifest, commands/configuration, source hashes, raw timings/resource samples,
quality comparisons, browser/OS/GPU identities, unavailable metrics and the
exact coverage gaps. Historical results remain dated context, never the fresh
control for a different scene, machine or renderer.

##### D. Architecture comparison to carry into the findings

These are hypotheses to rank, not preselected implementations. Compare both
time-to-first-use and total work over the same completed workload; include
preparation, cache storage, publication and fallback costs.

| Option | Where it could help | Cost or correctness question |
| --- | --- | --- |
| Direct bounded CPU warp with reusable geometry, decoded channels and viewport-aligned canvases | RTMA's intermediate interpolation; repeated Satellite/MRMS transforms; Radar mesh reuse | Verify native grid geometry and halo/seam handling. Benchmark reuse lifetime and invalidation by grid/sector, not just product name. Nested threads and larger supertiles can increase total work. |
| Decode once into native scalar blocks, optionally with selected overviews; generate lossless tiles on demand | Large FCI/AHI/AMI sources, repeated pan/zoom/history; compare with MRMS's existing tiled GeoTIFF | Include first-frame preparation, extra disk writes and duplicate caches. Overviews must use product-appropriate sampling and retain original detail; building every level for short-lived frames may never repay its cost. |
| Native polar WebGL for Radar; scalar tiles plus palette shader for suitable grids | High-zoom Radar gates, palette reuse, avoiding oversized whole-frame transfers | Preserve units, category codes, sentinel masks, precision, geometry and frame identity. Measure client upload/draw cost and total server work; the existing PNG-plus-artifact path still pays PNG cost. Keep low-resolution products on the simpler path if it wins. |
| Worker/OffscreenCanvas processing with transferable buffers and bounded uploads | Browser main-thread stalls during decode/preparation/presentation | Moving work can improve responsiveness without reducing CPU work; account for copies, worker startup and memory. Test the exact context/API combination and retain a compatible presentation path. |
| Optional WebGPU or backend GPU compute | A demonstrated warp/composite bottleneck with enough reuse to amortize transfer | Include upload/readback, driver support, device loss and implementation complexity. No required GPU baseline; rank below simpler options unless measurements justify it. |
| Lossless delivery alternatives and progressive preparation | Encoding/transfer bottlenecks; current-frame-first versus speculative history | Compare decoded pixels/alpha, decode latency and size. A lower-detail preview may precede completion, but final quality and explicit frame timing remain mandatory; lossy delivery or hidden dropped frames cannot establish a win. |

Research basis: Rasterio supports
[direct source/destination reprojection](https://rasterio.readthedocs.io/en/stable/topics/reproject.html);
GDAL documents [bounded warp memory and threading](https://gdal.org/en/stable/programs/gdalwarp.html)
and [tiled COG layouts/overview controls](https://gdal.org/en/stable/drivers/raster/cog.html).
These capabilities establish feasible comparisons, not speedups in this app.
[OffscreenCanvas transfer](https://developer.mozilla.org/en-US/docs/Web/API/HTMLCanvasElement/transferControlToOffscreen)
is broadly available, but each worker rendering path needs its own probe.
[WebGPU](https://developer.mozilla.org/en-US/docs/Web/API/WebGPU_API) remains an
optional capability with secure-context and platform constraints. The prior
FCI hyperslab experiment remains a measured rejection of that implementation;
only a materially different, explained approach should consume a new trial.

##### E. Hardware adaptation and browser matrix

Use separate backend and per-client budgets, with an aggregate cap when they
share a host. Proposed hardware targets are an 8 GiB, 2–4 effective-core
integrated-GPU machine; a 16 GiB, 4–8 effective-core ordinary machine; and the
owner's high-end machine. These are measurement profiles, not certified minimum
requirements. Include an 8 GiB Apple Silicon Mac for real WebKit evidence if
available. Record storage, GPU/driver, power mode, free memory, viewport/DPR and
network topology. Start on an ordinary machine where available; constrained
owner-machine runs are only surrogates until real lower-resource evidence exists.

Budget design to evaluate:

- Begin with one heavy foreground job and no speculative warming when capacity
  is unknown. Estimate peak working sets from source metadata plus measured
  transient overhead, and reserve host headroom before choosing concurrency.
  Bound process pools, native-library threads and all family caches together;
  `workers=-1` and independent family semaphores need explicit accounting.
- Increase concurrency/cache only after bounded observations show headroom and
  stable responsiveness; back off with hysteresis under pressure. Keep provider
  ceilings independent. Allow user caps and a conservative override, recording
  effective settings so comparisons remain reproducible.
- On clients, count bytes for current/incoming imagery, adjacent frames,
  backbuffers and tiles, including DPR-squared growth and resize. Feature-probe
  texture limits; do not infer usable VRAM from browser core/memory hints or
  display size alone. Start from a tested conservative byte ceiling and reduce
  prefetch/residency before affecting foreground work.
- For work that cannot fit even when run alone, compare block/window processing
  or disk-backed intermediates that preserve samples. The current oversized-job
  exception is not a sufficient low-memory policy. If no quality-preserving
  path fits, report the unsupported workload explicitly; do not silently lower
  final resolution, shorten history or churn until the process fails.

The browser policy retains two independent requirements: a default Baseline
Widely available feature floor and a rolling 30-month release-compatibility
target. [Baseline](https://web.dev/baseline) describes feature maturity across
its core browsers; it is not proof that a browser version, OS or GPU was tested.
For this dated plan the window reaches **2024-03-06**. Include the stable
version available at that boundary even when its release slightly predates it.

| Engine/browser | Proposed release coverage | OS/hardware and evidence scope |
| --- | --- | --- |
| Chromium: Chrome and Edge | Chrome 122 and Edge 122 boundary smoke; current stable of each at execution | Windows 11 x64, integrated GPU plus ordinary/high-end profiles; run four fixture anchors, do deeper timing only on the selected performance host |
| Gecko: Firefox | Firefox 123 boundary; current stable and supported ESR at execution | Windows 11 x64 on the same ordinary/integrated-GPU host for engine comparison; pin ESR versions during any release overlap |
| WebKit: Safari | Safari 17.4 boundary; current stable at execution | Real macOS/Safari on a compatible Apple Silicon machine; Safari 17.4/macOS 14.4 is a proposed historical pair; pin the current supported pair at execution |
| Mobile browser clients | Proposed extension: current Android Chrome/Firefox and iOS/iPadOS Safari, plus boundary equivalents if mobile support is claimed | Real devices connected to the Windows backend; DPR 2/3, touch, resize and memory-pressure coverage. Outside the initial desktop timing batch; desktop emulation cannot certify these targets |

Boundary sources:
[Chrome 122](https://chromereleases.googleblog.com/2024/02/stable-channel-update-for-desktop_20.html),
[Edge 122](https://learn.microsoft.com/en-ca/deployedge/microsoft-edge-relnotes-security),
[Firefox 123](https://developer.mozilla.org/en-US/docs/Mozilla/Firefox/Releases/123),
and [Safari 17.4](https://developer.apple.com/documentation/safari-release-notes/safari-17_4-release-notes).
Pin full browser builds, OS builds, GPU/driver and test-harness versions in the
execution manifest. Do not guess future current-stable/ESR numbers or equate a
planned row with available hardware. Unavailable historical binaries/Macs remain
explicit gaps. Use historical browsers only with isolated local fixtures for
compatibility work, not as the recommended daily browser. Do not inherit the
parked Greenfield platform matrix as a current-dashboard support promise.

Use engine automation for deterministic coverage, followed by real browser
checks for promotion, sharpness and GPU behavior. In particular,
[Playwright WebKit](https://playwright.dev/docs/browsers#webkit) is a patched
WebKit build, not the shipping Safari browser. Add an intermediate release only
when a capability/driver change or failure warrants it; the plan does not claim
every release in the window was exercised.

**Fallback acceptance:** probe context creation, shader/texture support and
actual rendered output; test acceleration disabled, context/device loss,
oversized textures, worker failure, memory pressure and fractional-DPR resize.
Keep the last complete frame until the same requested frame is ready on the
fallback, then restore appropriate opacity and inspector/legend identity.
A native-detail server tile or bounded CPU render is a candidate compatible
path. Existing Radar/MRMS capped PNGs remain current runtime fallbacks, but
cannot automatically be called quality-equivalent at high zoom. If they lose
meaningful detail against the chosen reference, a replacement proposal must
include a suitable fallback before acceleration can be accepted. Missing
`deviceMemory`, worker context support or GPU timers must not block basic use.
MDN documents [approximate memory hints](https://developer.mozilla.org/en-US/docs/Web/API/Navigator/deviceMemory),
[optional core-count limits](https://developer.mozilla.org/en-US/docs/Web/API/Navigator/hardwareConcurrency)
and [WebGL memory/limit constraints](https://developer.mozilla.org/en-US/docs/Web/API/WebGL_API/WebGL_best_practices).

##### F. Proposed success criteria and next decision

- **Quality is mandatory:** compare identical source/frame/viewport inputs
  against both the accepted renderer and a bounded full-native reference.
  Existing decimated output alone cannot certify native-detail preservation.
  Require exact category/no-data codes, source timestamps, units, palette and
  inspector contracts. Same-algorithm output should match decoded RGBA exactly;
  genuinely changed resampling requires a separately agreed, product-specific
  numeric/spatial tolerance and visual acceptance before performance can count.
  Report scalar error, masks, thin features, extrema, seams, limb/antimeridian
  alignment and alpha; do not use a single image similarity score or a global
  RGB tolerance to hide local damage.
- **Responsiveness targets for review:** p95 input-to-feedback at or below
  100 ms and no renderer-caused main-thread stall above 200 ms in the fixed
  interaction trace; warm requested-frame promotion within 250 ms; existing
  160 ms Satellite scrub coalescing measured separately from render time.
  Cold work may take longer but must preserve controls and an honest loading
  state. Page navigation must remain usable during warming. No flash, stale
  promotion, hidden frame dropping or publication of incomplete artifacts.
- **Efficiency threshold for review:** on an ordinary/lower-resource profile,
  a candidate should improve its declared dominant cost by at least 20% and
  beyond observed run-to-run variation. Report first-complete-frame latency,
  CPU work, GPU work where measurable, peak/settled memory, I/O and history cost
  alongside it. A default replacement should not regress other critical costs
  by more than 5% outside measurement noise; a larger tradeoff needs an explicit
  owner decision. Faster first paint bought with more total work is a tradeoff,
  not an unqualified efficiency win. Three baseline samples cannot pass this
  threshold as a statistical certification.
- **Resource behavior:** every profile completes the same selected workload
  within its declared budgets/headroom or produces an explicit evidence gap.
  No crash/OOM, sustained paging, runaway speculative queues or monotonic cache
  growth across three identical selection/play/teardown cycles. Residual memory
  must be accounted for as bounded cache, not assumed to be a leak or ignored.
- **Compatibility:** each claimed browser/OS row passes the four anchors and
  fallback checks at final quality; acceleration may differ by capability.
  Browser execution and owner visual acceptance remain separate evidence.

The review decision is whether to accept this inventory, 12-cell baseline,
hardware/browser targets and provisional thresholds. Approval of that bounded
measurement pass would not authorize renderer implementation or an unrestricted
benchmark campaign. Return its findings with a product-specific recommendation:
retain the existing path, improve its scheduling/reuse, or propose a different
renderer. Select at most two subsequent experiments with exact workload,
quality reference, resource limits and rollback scope for another review.
No commit, push, layer-order change or Greenfield work is included.

## 5. Post-refactor observation register

These observations originated on 2026-08-05. Their dated dispositions below
govern whether they are corrected history, deferred proposals, audit topics,
or reports that still need reproduction. They are not a blanket list of
confirmed current defects or approved implementation tasks.

Reconciliation, 2026-09-06: **Corrected** entries remain closed; **Historical**
entries retain dated evidence; **Deferred proposal** is not a current defect;
**Unverified report** still needs runtime reproduction; **Partly superseded**
identifies current code that has overtaken part of an old observation. The
source review did not reproduce every workflow. Rendering-related reports may
inform section 4.8, but their presence does not preselect a fix.

The 2026-08-08 post-cleanup owner smoke passed the global shell, Surface display
and product behavior, Satellite, Tropical, Water, Workspace, and the quick
cross-page regression sweep. It confirmed the exceptions and timing evidence
recorded below.

General observations:

1. **Unverified report:** Workspace Alerts loading time. Distinguish page load
   from the already-closed worker refresh timing gate when reproducing it.
2. **Deferred proposal:** first-frame and last-frame buttons on project
   scrubbers. The shared scrubber currently has previous/next/play controls;
   do not treat the desired extra buttons as an implemented feature.

Testing batch:

1. **Unverified report with code support:** Workspace Home clears the selected
   LSR detail, but its reset handler does not uncheck the LSR-enabled control.
   Reproduce the intended reset behavior before calling this fixed or changing it.
2. **Deferred by owner, 2026-09-06:** retain SPC/Mesoscale Discussions below
   Satellite; moving them above it is not requested at this time.
3. **Deferred proposal:** move WPC Day pills above family pills and make the
   workflow day-first. Current controls remain family-first.
4. **Unverified report:** WPC products/day pills may not load or activate.
   Identify the actual group/day/product; section 4.6 distinguishes unsupported
   later-day Winter selections from already implemented products.
5. **Deferred by owner, 2026-09-06:** retain MRMS below Satellite.
6. **Unverified report:** check combined legend membership for every enabled
   layer; the shared tray already exists, so this is a coverage check.
7. **Partly superseded:** standalone Satellite already has dynamic current-bound
   fitting for GOES Meso and Himawari Target plus a Meteosat RSS preset.
   Recheck other platform/sector defaults under the new resolution/view audit;
   this is not a blanket missing-fit feature.
8. **Partially implemented:** Phase 5 added bounded request retries, including
   503s. Interrupted streamed-transfer recovery/resume remains eligible under
   section 4.4; the new rendering audit may assess its current cost.
9. **Unselected view proposal:** GMGSI's actual sector is Global. The old
   proposed bounds `[-228.69, 103.01, -69.35, 62.27]`, center `[-8.67, -62.84]`,
   zoom `3` are not the current preset (`[0, 0]`, z2). Reassess during the audit.
10. **Unverified report:** unusually small GMGSI Global Z3 tiles; assess source
    detail and projection before inferring an incorrect render size.
11. **Deferred proposal:** generalize Loading/Stale/Legitimate Empty UX after
    defining each product's existing behavior and retained-image policy.
12. **Unverified report:** latest Mesoscale Discussions after warming/loading.
13. **Deferred proposal:** separate standalone SPC Mesoscale Discussion and
    Storm Report pills; the current page groups them under Reports/MDs.
14. **Deferred standalone RTMA proposal:** selecting Wind Speed also selects
    independently removable Wind Direction. The current standalone page allows
    the pair without auto-selecting the second checkbox; Workspace already has
    a combined Winds product. Do not conflate the two page contracts.
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
16. **Partly superseded / measurement pending:** Workspace MRMS loads the latest
    image before starting history. Check standalone behavior and actual cold
    timing under section 4.8 before claiming full-history blocking or its absence.
17. **Deferred proposal:** MESH zoom to the location behind `Largest Hail`.
18. **Deferred proposal:** dual useful units in `mrms-legend-units`.
19. **Unverified report:** Rotation Track statistic provenance (underlying data
    versus legend-scale maximum).
20. **Unverified report:** Drought gaps; collect a specific reproduction before
    selecting work.
21. **Deferred proposal:** isolate a Tropical Outlook card's element. The current
    handler selects/zooms/opens its detail; isolated rendering needs separate
    verification/design.
22. **Unselected Atlantic viewport proposal:** bounds
    `[-98.48, -17.36, 8.02, 46.35]`, center
    `[28.92, -57.92]`, zoom `5`.
23. **Unselected Eastern Pacific viewport proposal:** bounds
    `[-155.74, -74.62, -1.85, 39.1]`, center
    `[19.93, -115.18]`, zoom `5`.
24. **Unselected Central Pacific viewport proposal:** bounds
    `[-225.06, -110.33, -11.89, 45.21]`, center
    `[19.05, -167.69]`, zoom `4.5`.
    Items 22–24 are historical proposed coordinates, not current defaults in
    `frontend/pages/tropical/tropical-app.js`.
25. **Partly superseded / deferred UX proposal:** standalone WPC now builds
    catalog-driven product lists and a QPF6-hour scrubber; the old dropdown
    description is stale. Any remaining time-range-pill redesign needs a new
    comparison against the current page.
26. **Audit measurement topic:** current-frame-first loading with user-triggered
    lookback warming, across the selected rendering families in section 4.8.
27. **Corrected product boundary, 2026-08-08:** the July 1 Surface probe exposed
    an unsupported partial UI, not a Cleanup Wave regression. Surface now keeps
    its bounded recent lookback in Live; Surface and Alerts Archive tabs are
    placeholders, and Alerts has no general lookback slider. The backend
    limitation remains useful evidence for the unified section 4.7 family: AWC
    archive requests cap `hours` at 24 even for older targets, state fallback to
    IEM is decided before nearest-time filtering, CONUS has no historical IEM
    fallback, and the service can cache empty provider frames as
    `status: success`.
28. **Historical measurement, 2026-08-09:** later accepted Meteosat Phases 0–5
    supersede this as a candidate optimization starting point. Tile responses
    and logs expose source/download,
    decode/renderer construction, and final tile render/publication separately.
    Three uncached z6 Meteosat-12 Channel 13 tiles from distinct cached-source
    frames recorded median HTTP `3.021 s`, source resolution `7 ms`, decode
    `2.948 s`, and render/publication `52 ms` (decode range `2.919-3.787 s`).
    The earlier `jobs=1 downloaded=3 errors=0 pruned=27 elapsed=0h 2m 39s`
    result came from the source-prefetch worker, which does not decode or render
    tiles; its old total also includes catalog/prune overhead and cannot be
    reconstructed more finely. The implemented source-prefetch telemetry reports
    `download_ms`. Keep both observations separate and preserve output parity;
    neither is by itself an optimization baseline.

## 6. Version 2 lane

These are incremental evolutions of the existing dashboard and remain parked
until a specific design is selected:

The rendering-specific portions of resource adaptation, memory budgets, and GPU
research are now audit topics in section 4.8. This does not start the broader
Version 2 settings, diagnostics, or desktop-project programs below.

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

The NCH Weather Studio Greenfield plan is a **separate parked project design**,
not Version 2 of this repository and not part of the current dashboard backlog.
Its documented dashboard comparison was refreshed on 2026-09-06 for accepted
rendering/display contracts, shared basemaps, and alert routing/cutoffs. Exact
per-family parity, provider/dependency currency, and target-platform feasibility
still need verification before any implementation phase. This was a limited
documentation reconciliation, not Greenfield implementation readiness. The design is
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
- Radar WebGL beyond the named five: reopened for product-specific evaluation
  under section 4.8; no blanket conversion decision.
- Radar PNG retirement and server tile migration: previous exclusions
  superseded for audit recommendations on 2026-09-06. The current PNG runtime
  remains intact until an evidenced replacement plan is accepted.
- Unbounded retention for RTMA/MRMS: rejected.
- Persistent cross-process leases for the current single-process deployment:
  closed unless deployment changes.
- The unreachable Satellite registry entries and 12 unreachable composite
  branches: removed in `c0e6ced`, not remaining cleanup or a dormant roadmap.
- Removing `tl_2025_us_state.*`: rejected; it is the retained state fallback.

## 9. History, evidence, and document ownership

### 9.1 Active documents

- [`README.md`](README.md) — documentation map.
- This file — decisions, dispositions, evidence, and the selected audit brief;
  proposal list order does not establish priority.
- [`next-session-startup-prompt.md`](next-session-startup-prompt.md) — concise
  startup procedure.
- [`nch-weather-studio-greenfield-plan.md`](nch-weather-studio-greenfield-plan.md)
  — parked design for the separate Greenfield project; reconcile its dashboard
  parity baseline before authorization.
- [`architecture.md`](architecture.md) — implemented architecture only.
- [`patterns.md`](patterns.md) — reusable implemented patterns only.

### 9.2 Closed gate reference

- Worker-free Phases 0–8 were accepted and archived. The Alerts near-one-second
  Phase 0 gate explicitly passed with 0.082 seconds of post-response work in
  its recorded run; it is not an outstanding continuation prerequisite. See
  [`archive/worker-free-render-plan.md`](archive/worker-free-render-plan.md).
- Original Radar WebGL Phases 6–8 are closed. Earlier performance READMEs that
  say the next phase is gated are historical snapshots; the later Phase 8
  completion record governs that family. Further products in section 4.1
  remain audit/implementation candidates, not completed work.
- Cleanup Waves A–E and Meteosat Phases 0–5 are closed. Meteosat Phase 2c FCI
  hyperslab pushdown was measured and rejected, not left unfinished.
- Single-process ownership, bounded resources, publication safety, output
  parity, and applicable browser/owner validation remain current contracts.
  PNG is the existing fallback; section 4.8 explicitly permits evidenced
  replacement proposals. Closed gates do not require blanket reruns for
  unrelated work or prohibit reassessing the old rendering architecture.

These are historical acceptance records, not a fresh performance certification.

### 9.3 Preserved planning sources

The consolidation source archive contains the former superfile/startup prompt,
post-refactor observations, Version 2 proposals, Greenfield plan, and completed
cleanup Phase 2/4 records. Its README records hashes. Separately, `docs/archive/`
contains the completed Meteosat Phase 0–5 execution plan and the superseded
pre-`3773d47` startup handoff. Existing material under `docs/archive/` remains
historical and unchanged after it is placed there.

### 9.4 Performance evidence

All reviewed `docs/perf/` evidence remains retained and tracked. Every reviewed
phase directory has a README, and all JSON/JSONL records parsed during the
2026-08-07 audit. Performance evidence supports only the exact environment and
gate recorded with it; it is not browser proof.

Four older Radar evidence directories cited by planning text are unavailable
and were never tracked; see the consolidation-source README for their names.

### 9.5 Local-only token guide

`docs/token-saver-maybe.md` is intentionally ignored and local-only. It is not
an installed skill, cannot auto-trigger, and must never be a prerequisite for a
tracked startup prompt. Keep it short and subordinate to current system,
developer, repository, user, and selected-skill instructions.

## 10. Choosing the next slice

Cleanup Waves A through E are complete. The accepted functional/docs baseline
is `e200f74` plus `5096e74`. The owner has supplied the expanded rendering-audit
brief in section 4.8; turn it into the bounded execution/measurement plan for
review. Do not ask the owner to select the product families again or start
renderer changes from the ledger order.

The post-cleanup Satellite cross-page blocking prerequisite is complete. A
separate bounded Meteosat latency family was selected; its Phase 0/1 baseline,
no-flash, and scrub-ahead work is committed as Satellite-only checkpoint
`6759832`. Its required scrub-ahead re-smoke passed. Phase 2a/2b/2d and its
owner visual review are committed as `7b2d9a5`; Phase 2c was rejected by its
measurement gate. Phase 3 and its passed simultaneous Satellite/Radar owner
smoke are committed as `7bda975`. Phase 4's core implementation landed in
`68aeb72`; its retained-layer generation corrections, FCI native-read serialization
correction, and accepted RSS tuning are committed in `0e1eacb`. The complete automated gate,
isolated cold-render/alert-overlap server smoke, controlled z7 rapid-scrub regression, and
restarted M12/M11 owner smokes pass. Phase 4 is accepted. Phase 5 was separately authorized
on 2026-08-26, passed its automated and bounded live gates, and is committed in `3773d47`.
Its restarted M12 acquisition owner smoke also passed. Phase 5 and the bounded Meteosat
latency family are closed; the execution plan is preserved under `docs/archive/`.
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

Before the audit, confirm current Git status and agree its bounded evidence and
measurement scope. Implementation, validation gates, and rollback/fallback
decisions follow the findings and a separately selected work slice. Preserve
unrelated work throughout.
