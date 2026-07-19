# Next Session Startup Prompt

Date prepared: 2026-07-19

Start in:

```text
F:\Python\dashboard_2026
```

Use this prompt:

```text
We are continuing dashboard work in F:\Python\dashboard_2026.

Read first:
- docs/dashboard-change-and-enhancement-superfile.md
- docs/architecture.md when touching system boundaries
- docs/patterns.md when implementing a product/workflow pattern

Current status:
- The fixed map-first dashboard shell is accepted.
- All canonical product routes, including /tropical and /water, now serve true
  standalone pages from frontend/pages/.
- /workspace is the new severe-weather workspace. /weather.html redirects to it.
- The initial Workspace smoke found and fixed mismatched core shell classes plus
  a legacy map grid-area collision. The Radar/Alerts Workspace slice was accepted
  by the user on 2026-07-19 after iterative KGSP smoke testing; all tests reported
  by the user passed.
- Workspace UX follow-up removes the redundant Live Radar checkbox, pins only
  CONUS/AK/HI/PR, centers CONUS with page-owned bounds, defaults alerts to TOR+SVR
  with independently combinable TOR/SVR/FFW/SMW filters that turn `All` off,
  plus report type/time pills with a 1-hour default, adds
  independent header switches with adjacent counts, and
  separate compact collapsible legends. Styling remains Workspace-local. Storm
  Reports default off; Storm Tracks and
  Value Inspector are site-dependent and reset on region/Home defaults. The
  redundant radar helper text is removed and the footer refresh action is now
  full width. A split right rail now mirrors the standalone Alerts warning/report
  cards, counts, sorting, and card filters; each half is visible only when its
  corresponding Workspace layer switch is enabled. Rail `ALL` includes every
  selected active alert, warning-card zoom is capped at level 9, and report
  popups clear on layer-off or Workspace view/product changes instead of
  reopening from cached selection. A visible default-on 60-second auto-update
  refreshes enabled alert/report data and selected radar frames. New TOR/SVR/FFW
  warnings and watches produce 15-second dismissible map notices and one
  `sounds/weather_alert.mp3` playback per notification burst; SMW and other alert
  types do not notify. First load, filter changes, and viewport/region changes
  do not produce false notices. Alert cards sort newest-issued first, and radar
  site hover labels have a Workspace-only translucent high-contrast background.
  Alert polygons/cards and LSR markers/cards now open the shared draggable detail
  panel; LSR detail includes location/time/magnitude/WFO/source/remarks and no
  longer uses a Leaflet popup on pages that provide the panel. Workspace polygon
  and alert-card navigation are both capped at zoom 9. LSR markers show compact
  260 px responsive sticky hover tooltips with type/magnitude/location. Leaflet overlay focus
  rings are hidden for pointer clicks and retained only for keyboard focus-visible
  navigation.
  A KGSP radar-site smoke found four follow-ups now corrected: the shared value
  inspector request queue is restored to remove mousemove abort churn; NST tracks
  use the established icons/tooltips plus a separate Workspace legend; Projected
  Arrival drawing no longer opens/zooms an alert detail; and radar history frames
  now populate a visible shared scrubber. This correction set is included in the
  accepted 2026-07-19 Radar/Alerts closure.
  Layers groups are independently collapsible. Radar starts open; Active Alerts,
  Storm Reports, and the SPC/Satellite/RTMA/MRMS/WPC/Water composition placeholders
  start collapsed.
  Workspace does not expose radar elevation selection; it requests the explicit
  0.5-degree Level II default. The advanced selector remains Radar-page-only,
  where 0.5 degrees is also the initial default.
  Radar has a default-on header switch and Level 2/Level 3 pills below Site; the
  pills and Product field appear only after site selection, and Product shows
  only catalog entries for that level. Level 3 is unavailable for non-CONUS sites.
  Projected Arrival has its own Workspace group immediately below Active Alerts;
  the group is hidden until an alert polygon, rail card, or new-alert notice is
  selected, then appears expanded with the selected alert named. There is no
  separate Tools sidebar tab. Its inline help text is retained in the superfile
  as future FAQ/Wiki copy. The former Radar Speed Estimator and all of its wiring
  were removed because the fixed loop timing it assumed no longer exists.
  The map Home control now performs a full Workspace context reset before fitting
  CONUS: it clears the selected radar/site frames and scrubber, restores Level 2
  Base Reflectivity, clears the selected alert/projection, and hides Projected
  Arrival while preserving the user's layer visibility preferences.
  The Radar/Alerts Workspace update cycle is closed for now.
- Next session: diagnose and correct the known standalone Water page UI issues.
  Keep the completed Workspace Radar/Alerts behavior stable while doing so.
- Product engines/pages own product-specific controls, requests, response
  interpretation, and most rendering.
- weather.html, js/weather.js, the obsolete root js modules, and
  css/dashboard.css are deleted. The Projected Arrival Tool now lives in
  frontend/pages/workspace/workspace-tools.js.
- Backend route logic should stay in routes/*.py, route-facing cache/response
  behavior should stay in services/*_service.py, and upstream/cache refresh
  behavior should stay in workers/*_worker.py.

Active track order (2026-07-19):
1. Frontend True Split Stage 2. Phases 18-20 are complete; `/drought` and
   `/surface` are true standalone pages under `frontend/`. The accepted shared
    sidebar reference is Option 1A (pinned status/region, Data/Overlays/Style
    tabs via `frontend/core/sidebar-tabs.js`, pinned message/Refresh footer)
    and the shared legend is the collapsible dark map-panel tray in
    `frontend/core/legend.js`. Surface (Phase 20, user-smoked 2026-07-17)
    proved the second consumer: page-local renderer module, worker-PNG
    gradients with client-canvas IDW fallback, network filters, density
    thinning, and a continuous-colorbar legend on the core primitives.
    Decisions to remember: the Gradient Blur control was dropped (fallback
    uses fixed FALLBACK_BLUR_SCALE 1.0) and surface archive was retired
    entirely rather than rebuilt — surface no longer participates in the
    shared archive scrubber, whose component rewrite remains Phase 22. All
    surface code was deleted from js/weather.js and weather.html
    (weather.js?v=20260717a); shared helpers used by RTMA/cities/satellite
    legends were kept. Phase 21 (SPC, WPC) is COMPLETE. SPC: standalone
    page at frontend/pages/spc/, user smoke passed 2026-07-17, ~1,700
    lines of monolith SPC code deleted (weather.js?v=20260718a; MD/watch
    text chip helpers kept for the alerts detail path). WPC: standalone
    page at frontend/pages/wpc/, monolith WPC code deleted 2026-07-18
    (~230 lines from js/weather.js, the wx-section-wpc/wx-side-group-wpc/
    wpc-scrubber-bar blocks from weather.html, plus js/wpc-engine.js,
    js/wpc-page.js, and js/scrubber.js; weather.js?v=20260718b; user
    smoke PASSED 2026-07-18). Phase 22 (MRMS + RTMA + scrubber-as-component) is
    COMPLETE 2026-07-18 under the same authorization: the WPC page's
    scrubber was promoted to frontend/core/scrubber.js (index-preserving
    setFrames options added), standalone pages were built at
    frontend/pages/mrms/ and frontend/pages/rtma/ (routes switched), and
    the monolith MRMS/RTMA code was deleted (~2,000 lines from
    js/weather.js, weather.html sections, js/{mrms,rtma}-{engine,page}.js;
    weather.js?v=20260718c). User parity smokes PASSED 2026-07-18 for
    /wpc, /mrms, and /rtma. The shared archive-scrubber chrome
    (_setRtmaScrubberStatus/_updateRtmaScrubberUi/_setArchiveScrubber,
    RTMA_SCRUB_* constants, slimmed _exitMrms/RtmaScrubMode, stubbed
    hasMrms/RtmaScrubFrames) was later removed with the Radar cutover; archive
    mode in weather.html is Alerts-only. Phase 23 (satellite) COMPLETE
    2026-07-18 — built + monolith-deleted
    under the same build+delete-before-smoke authorization: standalone page
    at frontend/pages/satellite/ (satellite.html, satellite-page.js,
    satellite-engine.js, satellite-anim.js, satellite.css) on the core
    shells + frontend/core/scrubber.js; ~1,723 lines of satellite code
    deleted from js/weather.js (now 9,250 lines), wx-section-satellite +
    scrubber Auto button removed from weather.html, js/satellite-{engine,
    page}.js deleted (weather.js?v=20260718d). User parity smoke PASSED
    2026-07-18. The reported continuous-legend bottom scrollbar was traced to
    long endpoint labels centered outside the 0%/100% bounds; the endpoints
    are now aligned inward (`satellite.css?v=20260718c`). The shared
    `.core-map-legend` bottom position is user-accepted globally at 50px so it
    clears bottom scrubbers. Phase 24 (radar) is COMPLETE + USER PARITY SMOKE
    PASSED 2026-07-18 under the same authorization: standalone page at
    frontend/pages/radar/ on the core map/sidebar/legend/scrubber primitives;
    complete API-driven site/product catalog, operational site markers,
    CONUS-aware L2/L3 filtering, elevation pills, current + 0.5-12 h frames,
    pooled overlays, 90 s auto-update, `.pal` legends, NST tracks + selected-
    cell SRV motion, and the value inspector. About 2,006 Radar lines were
    deleted from js/weather.js (now 7,244); the Radar controls/scripts were
    removed from weather.html; js/radar-{engine,page}.js and
    js/radar-site-locations.js were deleted. The Projected Arrival Tool remained
    preserved in the legacy workspace for Phase 27, but is no longer part of
    Alerts (`weather.js?v=20260718e`). See the
    superfile for the deliberate smoke deltas. Post-smoke UI follow-up makes
    the desktop site-status legend one row and gives Home, Region change, and
    Clear one complete Radar reset path; the user confirmed this follow-up.
    Phase 25 Alerts is BUILT 2026-07-18 at frontend/pages/alerts/ and `/alerts`
    now serves it. It includes live categories/subtype filtering, LSRs, the
    active-warning rail, immersive detail, map/style controls, and auto-update.
    Alerts archive UI is hidden pending the unified archive design. It
    intentionally excludes the radar-dependent Projected Arrival Tool above.
    Initial user parity smoke PASSED. A focused follow-up now uses
    a full-width compact Alerts/LSR legend, collapsible Alert Categories,
    TOR/SVR/FFW/SMW filters, Severe/All/Off new-alert notice selection, and a
    bounded draggable detail panel with restored threat chips and official NWS
    text-product links. Follow-up `v=20260718c` nests TOR/SVR/FFW/SMW directly
    under Severe Weather Warnings, adds the wired 1-hour LSR option, hides
    Archive, and ensures warning links use the event product (SVR, not an SVS
    continuation code). Unified archive UI will use one target datetime plus a
    lookback, not a date range. Follow-up `v=20260718d` makes the right rail
    disappear when neither Alerts nor LSRs are selected and split into Active
    Warnings (top) plus Latest Storm Reports (bottom) when both are active. LSR
    cards are newest-first with All/Tornado/Hail/Wind/Other filters and
    click-to-zoom/open-popup behavior. `v=20260718e` fixes delayed/missing
    re-display after off/on toggles: subtype inputs are isolated from category
    queries, empty selections retain the last successful payload, LSRs filter
    from a viewport+window cache, and only scope changes/manual refresh/auto-
    update refetch. Later corrections make the footer status page-owned and
    selection-aware; use marker icons in a deterministic Tornado-first LSR
    legend; restore default-on TOR/SVR/FFW/SMW fill/border pulsing with a Style
    toggle; retain the official FFW color while using a lighter text-only dark-
    UI presentation color; and enable Auto-Update by default at 60 seconds.
    User parity and complete focused follow-up smoke PASSED 2026-07-19. Legacy
    Alerts cleanup is COMPLETE and statically validated: combined-workspace
    controls, rendering/load/archive paths, and obsolete js/alerts-* modules
    were removed while the Projected Arrival Tool remained reserved for Phase
    27. Phase 26 Tropical is also COMPLETE and
    statically validated: `/tropical` now serves frontend/pages/tropical/ on
    the core shell, and the Tropical UI/state/bridge plus js/tropical-* modules
    were removed from the monolith. Browser parity smoke is deferred to the
    consolidated final checklist. Phase 26 Water is also COMPLETE and statically
    validated at frontend/pages/water/; its legacy monolith/UI paths are removed.
    Phase 27 is COMPLETE and statically validated: /workspace composes Alerts
    and Radar engine APIs, preserves the Projected Arrival Tool, redirects the
    legacy /weather.html URL, vendors browser libraries under frontend/lib, and
    retires the monolith/root shell assets. The user closed the Radar/Alerts
    Workspace slice on 2026-07-19 with all tests reported passing. Begin the next
    session with the known standalone Water UI issues; keep the consolidated
    checklist as regression reference. Additional product-engine composition
    (SPC/MRMS/RTMA/Satellite/Drought/WPC) remains a later workspace expansion.
    Minor UI spacing polish
    across the new standalone pages remains deferred to the end of the
    superplan by user decision.
2. Satellite render-pipeline latency optimization. This backend-only track may
   interleave with Track 1 while their files remain disjoint.
3. GK2A + GMGSI after the satellite-page migration boundary is safe.

Satellite v2 status (2026-07-16) — Meteosat recipe work DONE; GOES aerosol/fire
products (ADP/AOD/FRP) and GeoColor display corrections added 2026-07-16:
- DONE 2026-07-16 (GOES-18/19 only): three new single-instant GOES ABI L2
  products. AerosolDetection (ABI-L2-ADP smoke/dust mask, confidence-graded via
  DQF bit-fields -> opacity), AerosolOpticalDepth (ABI-L2-AOD, high+medium DQF
  quality, turbo 0-1 with a value-driven alpha ramp + a discrete "No Data"
  legend swatch), and FireRadiativePower (ABI-L2-FDC Power, sparse fires dilated
  for CONUS-zoom visibility, YlOrRd 0-150 MW). All reuse the GOES geos georef
  and the single-instant render path via pseudo source-channels ADP/AOD/FRP
  (registered in normalize_source_channel; kinds categorical/aod/frp resolved
  in _product_kind before channel_number_from_key). provider_aws._aws_family_
  prefix maps them to ABI-L2 family prefixes (ADPC/F/M, AODC/F, FDCC/F), token
  filter skipped, _filename_matches_sector generalized to M1-M/M2-M. Gated
  GOES-only in satellite-page.js (GOES_ONLY_CHANNELS) — no AHI/SEVIRI/FCI
  equivalent is published. Changed AOD/ADP tiles were cleared surgically by
  deleting tiles/products-v3/goes*/{AerosolDetection,AerosolOpticalDepth} (no
  render-version bump). Full detail in the superfile's "GOES aerosol and fire
  products: ADP, AOD, FRP" section. weather.js?v=20260716c,
  satellite-page.js?v=20260716b, dashboard.css?v=20260716a.
- DONE 2026-07-16: GOES GeoColor and Black Marble daytime RGB now use bounded
  ABI Rayleigh correction, CIRA log stretch, solar-zenith blending from frame
  geometry, a 0.85 display white point, and 1.08 saturation. Filled satellite
  imagery is opaque in both rendered tiles and Leaflet; ADP/AOD/FRP retain
  their specialized alpha behavior. Current render versions are products-v5
  (GOES/default), products-ahi3 (Himawari), and products-fci3 (Meteosat-12).
  Colors and opacity are user-confirmed; the final white-point brightness lift
  still needs browser confirmation. Current weather.js cachebuster is
  v=20260716d.
- GOES (goes18/goes19), Himawari-9, Meteosat-9 (SEVIRI), Meteosat-12 (FCI),
  and Meteosat-11 (RSS) are all implemented and browser-smoke-tested.
  Meteosat-11 RSS full product set (4 scalars + Night Microphysics/Dust/Ash)
  user-confirmed loading correctly 2026-07-11. RSS proofing is DONE.
- DONE + user-confirmed 2026-07-11: SEVIRI/FCI RGB recipe correction for
  NighttimeMicrophysics/Dust/Ash. These 3 composites previously reused the
  NOAA/CIRA (GOES-tuned) stretch windows on every platform. They now use
  EUMETSAT's own published stretch windows (source: EUMETSAT "Compilation
  of RGB Recipes" PDF) when rendering on SEVIRI/FCI instruments, while
  GOES/Himawari (ABI/AHI) keep the original CIRA windows unchanged. This
  required threading `sat_id` -> `instrument` (via
  `config/satellite_platforms.SATELLITE_PLATFORMS`) through
  `SatelliteTileRenderer.from_sources`/`from_source` in
  satellite_v2/renderer.py, into the renderer cache key, and finally into
  `render_composite_rgb(..., instrument=...)` in satellite_v2/composites.py,
  which branches on `instrument in {"SEVIRI", "FCI"}` for those 3 product
  keys only. All 3 `SatelliteTileRenderer.from_sources` call sites in
  satellite_v2/tiler.py (single-tile, zoom-canvas, and the process-pool warm
  path incl. the pool initializer) now pass `sat_id` through. If you add
  another instrument-specific recipe override, follow this same
  `instrument` plumbing rather than inventing a new path.
- Verified (analysis, not a code change): the static interpretive legend
  swatches in `SATELLITE_V2_INTERPRETIVE_LEGENDS`
  (config/satellite_v2_config.py) and their JS mirror
  (`_SATELLITE_INTERPRETIVE_LEGENDS` in js/weather.js) do NOT need
  per-instrument variants. Gamma-per-beam is unchanged between the CIRA and
  EUMETSAT windows for all 3 affected products, and swatch color is a pure
  function of the normalized fraction (`(value-min)/(max-min)`, then gamma)
  -- changing only min/max does not change what color a given fraction
  renders as. The existing swatches were confirmed (by inverting their hex
  back to fractions) to already be fraction-space qualitative picks, not
  physical-value-tied renders, so they remain valid on both instrument
  families. Don't revisit this unless the swatch-generation approach itself
  changes (e.g. if gamma starts differing per instrument).
- Standard non-GOES product set is DONE at 7 of 8 for Meteosat-9/11/12:
  Visible, Enhanced IR, Water Vapor, Shortwave IR/Fire, Night Microphysics,
  Dust, and Ash are all live and user-confirmed (2026-07-10/11). SO2 is
  INTENTIONALLY SKIPPED for Meteosat: the recipe's red beam is C09-C10, and
  SEVIRI/FCI's channel-alias tables can't represent that without breaking the
  exposed C09 water-vapor scalar. Doing it right needs per-instrument
  recipe-level channel overrides -- not started, low priority.
- Visible/NIR reflectance stretch fix (fixed 0.02-0.90 window + sqrt, shared
  renderer path) is DONE and user-confirmed satisfying on GOES, Himawari, and
  FCI. Render versions bumped (products-v3 / products-ahi2 / products-fci2).
  New reflectance-calibrated platforms get this for free -- do not add a
  per-platform stretch.
- Satellite sidebar now enforces a strict selection chain: Satellite -> Sector
  -> View -> Product. Each control is disabled (native <select disabled>)
  until its prerequisite is chosen, and each defaults to a "-- Choose X --"/
  "-- Select X --" placeholder so nothing auto-loads on partial selection.
  "Full Disk" is the default View option now (was missing). This is recent
  (2026-07-10/11) and only lightly exercised -- if you touch satellite-page.js
  selection wiring, re-verify the whole chain by hand (set each control via
  the browser and confirm the next one enables, not just via DOM inspection).
- Product dropdown is filtered per satellite via PLATFORM_CHANNELS in
  js/satellite-page.js: Himawari-9 shows the full GOES list (identical ABI,
  same render cost); Meteosat-9/11/12 show only the proven scalar + 3
  composite set above -- do not add more Meteosat products to that Set
  without a proof render first (see the pattern in the superfile's Meteosat
  sections for what "proof" means here: correlate against a Satpy/GOES
  reference, check reflectance/BT ranges, confirm coastline alignment).
- Meteosat source downloads are cache-first and efficient: SEVIRI is one
  ~270 MB .nat per 15-min frame (all 12 channels), FCI is ~40 body chunks
  downloaded in parallel with a manifest fast path that skips the EUMETSAT
  search entirely once a frame is fully cached. A background prefetch worker
  (satellite_v2_meteosat_prefetch_worker, 10-min schedule) keeps a rolling
  window warm so cold-tile latency is rare in practice.
- Known FCI gotcha if you touch fci_nc.py again: Channel14 and Channel15 map
  to ir_105 and ir_123 (not ir_133, the 13.3 um CO2 band) -- this aliasing
  mirrors SEVIRI's C13/C14->IR_108 trick and is required for the Night
  Microphysics/Dust/Ash recipes to reduce to the correct EUMETSAT RGBs. Do
  not "correct" these to nearest-wavelength without re-deriving the composite
  math.
- TRACK 3: GK2A (arn:aws:s3:::noaa-gk2a-pds) and NOAA GMGSI Meteosat composite
  (noaa-gmgsi-pds). No provider/parser work has begun on either. Start this
  after the satellite-page migration boundary is safe so the integration is
  not implemented twice across the frontend split.
- docs/token-saver-maybe.md (a Claude Code skill definition, not dashboard
  documentation) is intentionally untracked; the .gitignore entry now
  correctly targets docs/token-saver-maybe.md. RESOLVED 2026-07-18 — no
  action needed.

Other recent completed work (pre-satellite-focus, still relevant context):
- DONE 2026-07-04 (late evening), user-tested: L2 blank velocity/SRV/spectrum
  width fix. NEXRAD split-cut VCPs scan low tilts twice at the same fixed
  angle (surveillance sweep = reflectivity only, Doppler sweep = velocity/SW);
  _select_sweep in workers/radar_live_worker.py is now field-aware. Elevation
  "auto" was retired for L2 in favor of a fixed 0.5 deg default
  (LIVE_RADAR_L2_DEFAULT_ELEVATION in config/radar_config.py).
- DONE 2026-07-05: Surface gradient overlays no longer retain stale worker
  PNGs indefinitely on open pages (5-minute metadata refresh + cache-busting
  URL versioning in js/weather.js / js/surface-engine.js).
- DONE 2026-07-04: Radar site selector shows all 164 NWS NEXRAD sites (was
  7 CONUS-only); non-CONUS sites get Level 2 only (Level III is CONUS-only
  per NOAA spec).
- L2 chunks workflow (unidata-nexrad-level2-chunks) was implemented, then
  REVERTED 2026-07-04 after benchmarking showed zero latency benefit over the
  flat NODD bucket for completed scans. LIVE_RADAR_L2_USE_CHUNKS = False.
  radar_chunks_utils.py is left in place unused in case this flips back on.
- DONE 2026-07-16: Radar lookback is live-cache-aware from 30 minutes through
  12 hours. Requested fractional hours now reach the NODD worker, cache coverage
  gaps start bounded newest-to-oldest background batches, and expanded history
  is retained without changing the scheduled worker's one-hour download default.
  Do not route this back through the archive renderer.
- Himawari-9 was fully removed 2026-07-01 (satpy/dask oversubscription +
  unnecessary resample-to-grid architecture), then REBUILT 2026-07-02 on a
  native AHI HSD parser with zero satpy/pyresample/dask (see
  satellite_v2/ahi_hsd.py). GOES was unaffected by either change.

Important guardrails:
- Keep API paths stable unless a separate API cleanup is explicitly planned.
- Keep /spc startup ordering intact: normalize SPC controls and report-filter
  state before the first refreshActiveLayers() call.
- Confirm product engine/page script tags when adding a new product module; a
  missing window.NCH*Engine or window.NCH*Page silently prevents engine creation.
- When changing Satellite page control wiring, bump the relevant script query
  strings in weather.html so browser cache does not mask the new behavior.
- Make bounded, reviewable changes and update the superfile when roadmap or
  phase state materially changes.
- Standalone Alerts footer status is page-owned as of `v=20260718f`; preserve
  its combined selected Alerts/LSR count rather than restoring per-loader
  success messages in `alerts-engine.js`.
- Standalone Alerts LSR legend entries use the shared marker icon/color mapping
  and deterministic category ordering (Tornado first when present) as of
  `alerts-engine.js?v=20260718h`.
- TOR/SVR/FFW/SMW polygon fill and borders pulse by default as of
  `alerts-engine.js?v=20260718i`; the Styles-tab selector toggles the animation
  on the existing layer without refetching.
- Standalone Alerts uses a presentation-only lighter FFW text color while
  retaining the official NWS core color, and Auto-Update defaults on at a
  60-second interval as of `alerts-page.js?v=20260719a`.
- Alerts category cards use a page-specific 180-220 px auto-fill grid as of
  `alerts.css?v=20260719b`; do not move that sizing into shared core CSS.
- Preserve unrelated working-tree changes.

Validation defaults:
- Run the narrowest meaningful static check first, such as node --check for
  touched JavaScript and py_compile for touched Python.
- Browser smoke and all proofing/correlation checks (satellite recipe proofs,
  visual comparisons, etc.) are user-owned. Do not drive the browser preview
  tools for this project's verification. After a static check passes, say the
  edit is ready and stop -- the user runs the manual smoke test/proof and
  reports back. Keep claims limited to static/import validation until the
  user confirms.
```
