# Next Session Startup Prompt

Date prepared: 2026-07-11

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
- Canonical product routes serve product-only dashboard mode: /surface, /alerts,
  /radar, /satellite, /spc, /rtma, /mrms, /drought, /tropical, /wpc, and /water.
- /weather.html remains the combined workspace and must keep working until it is
  explicitly retired.
- Product engines/pages own product-specific controls, requests, response
  interpretation, and most rendering.
- js/weather.js still owns shared map lifecycle, generic archive orchestration,
  shared scrubber infrastructure, and injected callbacks where cross-product
  state remains coupled.
- Backend route logic should stay in routes/*.py, route-facing cache/response
  behavior should stay in services/*_service.py, and upstream/cache refresh
  behavior should stay in workers/*_worker.py.

Satellite v2 status (2026-07-11) — the current focus area:
- GOES (goes18/goes19), Himawari-9, Meteosat-9 (SEVIRI), and Meteosat-12 (FCI)
  are all implemented and browser-smoke-tested. Meteosat-11 (RSS) shares the
  SEVIRI parser/composite path with Meteosat-9 but has no cached RSS proof yet.
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
- Not started: GK2A (arn:aws:s3:::noaa-gk2a-pds) and NOAA GMGSI Meteosat
  composite (noaa-gmgsi-pds). These are the next planned satellite sources
  once the team is ready to move past Meteosat. No provider/parser work has
  begun on either.
- Untracked file docs/token-saver-maybe.md has been sitting in the working
  tree for several sessions (a Claude Code skill definition, not dashboard
  documentation). The .gitignore entry added 2026-07-10 points at
  .claude/token-saver-maybe.md, which does not match this file's actual path,
  so it still shows as untracked. Needs a decision: move it, retarget the
  gitignore line, or commit it intentionally.

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
- Preserve unrelated working-tree changes.

Validation defaults:
- Run the narrowest meaningful static check first, such as node --check for
  touched JavaScript and py_compile for touched Python.
- Browser smoke is user-owned for current dashboard work unless explicitly
  requested. Keep claims limited to static/import validation when no browser
  proof was run.
```
