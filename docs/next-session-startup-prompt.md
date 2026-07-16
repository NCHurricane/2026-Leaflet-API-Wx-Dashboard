# Next Session Startup Prompt

Date prepared: 2026-07-16

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

Satellite v2 status (2026-07-16) — Meteosat recipe work DONE; GOES aerosol/fire
products (ADP/AOD/FRP) added 2026-07-16; next focus is GK2A + GMGSI:
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
- NEXT UP (starting 2026-07-12): GK2A (arn:aws:s3:::noaa-gk2a-pds) and NOAA
  GMGSI Meteosat composite (noaa-gmgsi-pds). Meteosat recipe work is done, so
  the team is moving past Meteosat now. No provider/parser work has begun on
  either -- this is greenfield, same as Himawari/Meteosat were before their
  provider modules existed.
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
