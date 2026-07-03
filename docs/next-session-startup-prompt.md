# Next Session Startup Prompt

Date prepared: 2026-07-01

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

Recent completed work:
- Himawari-9 satellite pipeline was fully removed (2026-07-01). It used
  satpy/pyresample to ingest raw AHI HSD segments into an intermediate
  lat/lon npz grid, which caused two problems: dask's default threaded
  scheduler oversubscribed all 32 CPU cores per ingest call (stalling the
  whole dashboard under concurrent scrubber load), and the resample-to-grid
  approach was architecturally heavier than needed — AHI is natively
  geostationary with a fixed pixel grid like GOES ABI, so a native-format
  parser could reuse the existing fast GOES SourceRaster/GDAL-warp path
  instead. Removed provider_himawari.py, latlon_grid.py, worker_himawari.py,
  workers/satellite_v2_himawari_worker.py, all Himawari/JAPAN config and
  frontend references, the scheduled task entry, and cached Himawari data.
  GOES is unaffected. A native-AHI-format rewrite (no satpy) remains a real
  option if Himawari coverage is revisited, but has not been started. Full
  detail in docs/dashboard-change-and-enhancement-superfile.md.

Next up:
- DONE 2026-07-02: Himawari-9 rebuilt on a native AHI HSD parser (no
  satpy/pyresample/dask). New: satellite_v2/ahi_hsd.py (parser, calibration,
  Earth-visibility space mask, 0.5km→2km stride cap),
  satellite_v2/provider_himawari.py (noaa-himawari9 S3, FULLDISK 10-min
  slots), satellite_v2/providers.py (platform-descriptor dispatch used by
  catalog/service/tiler), renderer dispatch on .DAT/.DAT.bz2, config +
  frontend re-add (satellite-page.js ?v=20260702c). On-demand only, no warm
  task. Validated on live data incl. coastline geolocation and end-to-end
  resolve_tile. USER BROWSER SMOKE STILL PENDING for the Satellite tab
  Himawari-9 platform. Full detail in the superfile.
- Meteosat scoping DONE 2026-07-02; build order decided: **Meteosat-9 SEVIRI
  first** (Indian Ocean, 45.5E, collection EO:EUM:DAT:MSG:HRSEVIRI-IODC,
  single ~270 MB .nat per 15-min frame with all 12 channels), Meteosat-12
  FCI second (EO:EUM:DAT:0662, NetCDF chunk zip — verify chunk layout
  empirically before designing). Access is EUMETSAT Data Store REST only
  (no public S3): consumer key/secret → OAuth token. DONE 2026-07-02:
  Meteosat-9 `.nat` downloads work after licence/API-token refresh. New:
  satellite_v2/seviri_nat.py (native 10-bit MSG parser, IR BT calibration,
  visible reflectance-factor support, geos transform), EUMETSAT provider loads
  F:\Python\dashboard_2026\.env explicitly, Meteosat-9 marked implemented,
  frontend product list filtered to SEVIRI-compatible products, service tile
  stats report provider=eumetsat. Validated on live
  MSG2-SEVI-MSG15-0100-NA-20260702185739.917000000Z-NA.nat with coastline
  proof images and backend resolve_tile smoke. Browser smoke passed for
  selecting Meteosat-9 in the Satellite tab.
- DONE 2026-07-02: Meteosat-12 initial FCI Full Disk slice validated, then
  expanded to direct scalar IR/WV products. New: satellite_v2/fci_nc.py
  assembles MTG/FCI NetCDF `CHK-BODY` chunks, calibrates FCI radiance to
  brightness temperature or reflectance, and returns the shared
  SourceRaster/geos path. Provider uses collection EO:EUM:DAT:0662 for
  meteosat12 and downloads all body chunks for a selected frame into shared
  `FCI` source cache. Frontend exposes only Full Disk plus direct products
  Channel07, Channel07Fire, Channel08RAMSDIS, Channel09RAMSDIS, and Channel13
  for Meteosat-12; RSS and composite FCI product UI exposure remain deferred
  until proof renders. Validated live frame 20260702T190000Z: 40 chunks,
  791,937,141 bytes, assembled 5568x5568 `ir_105` grid, BT 182.94-308.11 K,
  coastline proof image written under cache/satellite/validation/fci_proofs,
  backend resolve_tile rendered
  `meteosat12/FULLDISK/Channel13/20260702T190000Z/4/8/6.png`. Browser smoke
  passed for Meteosat-12 tab selection.
- Current satellite sequencing decision: finish the existing non-GOES platforms
  before adding more sources. For Himawari-9, Meteosat-9, and Meteosat-12,
  expose a small standard product set only: Visible, Enhanced IR, Water Vapor,
  Shortwave IR/Fire, Night Microphysics, Dust, Ash, and SO2, with proof renders
  before UI exposure. Defer CIRA GeoColor / True Color / Natural Color and
  other RGB parity to V2. DONE 2026-07-02: satellite platform/sector switches
  now auto-fit named frontend view presets for GOES, Himawari-9, Meteosat-9,
  and Meteosat-12 after the user picks a sector. Switching satellites clears
  the sector selection first, preventing catalog/tile work until the new sector
  is explicitly selected; product/channel switches preserve user pan/zoom.
  DONE 2026-07-02: added a user-facing `View` select filtered by platform;
  changing it only fits the map and does not generate tiles. Meteosat-12
  Europe/Africa was tightened after browser testing so it no longer opens as a
  near-world view. DONE 2026-07-03: warm/prefetch planning is viewport-aware
  without blocking direct Leaflet tile requests. Frontend animation prefetch
  uses current map bounds plus a one-tile buffer and reschedules on map bounds
  changes; backend warm planning has opt-in `tile_bounds` + `tile_buffer`
  support and worker CLI `--bounds west,south,east,north --tile-buffer 1`.
  Scheduled warmers remain unchanged unless explicit bounds are configured.
  Next non-NOAA visible-products step: Meteosat-12 `Channel02` -> FCI `vis_06`
  proof render first, then expose only that proven visible product; later
  candidates are `Channel01` -> `vis_04`, `Channel03` -> `vis_08`/`vis_09`,
  `Channel05` -> `nir_16`, and `Channel06` -> `nir_22`, with composites
  deferred until scalar source proofs pass. After current direct products and
  proof renders are stable, add GK2A from
  `arn:aws:s3:::noaa-gk2a-pds` and NOAA GMGSI Meteosat composite from
  `noaa-gmgsi-pds`.
- Satellite tab no-auto-load / blank-default UX: both sat-id and sector selects
  default to blank; tab entry and change events do not load tiles until both
  are selected; _fetchSatelliteFrameSet throws early when either is blank,
  preventing 500s from tile requests with empty sat_id/sector params. Channel
  13 remains the default channel and does not require a blank option. Browser
  native form restoration persists blank selection across hard refresh.
- Satellite warm/render lifecycle: Ctrl+C stops server-owned scheduler/live tile
  pool hooks, but does not clear cache or stop external Windows Task Scheduler
  jobs. Reopening the same product after restart can resume missing tile renders
  through /api/satellite-v2/tile because resolve_tile(..., allow_render=True)
  renders cache misses on demand.
- Legacy IEM alert-radar loop removed from the product shell: no
  weather-alert-radar-enable checkbox, no weather-opacity-alert-radar slider,
  and no _alertRadar* frontend timer/tile/freshness path. /radar should stay on
  the cache-first /api/radar/live/* workflow. The old /api/radar/tiles/*
  endpoints still exist only for API compatibility.
- Shared categorical legends now wrap whole swatch/label items using
  .legend-flow, labels can wrap without painting into neighboring swatches, and
  the Alerts legend uses the five-column helper. User browser smoke passed on
  2026-06-28.
- Satellite GOES composite products were exposed in the Satellite selector:
  Fire Temperature, Air Mass, Day Cloud Phase, Day Land Cloud/Fire,
  Day Snow/Fog, Nighttime Microphysics, Dust, Ash, and Sulfur Dioxide.
  Renderer-matched interpretive legends were added for these RGB composites,
  with a frontend fallback so legends stay visible when switching
  satellite/sector/product controls without a hard refresh. Scalar satellite
  colorbars remain for brightness-temperature channels only.
- Docs were consolidated into docs/dashboard-change-and-enhancement-superfile.md.
  Superseded planning docs were moved to docs/archive/.
- Storm Tracks (NST) icon accuracy: IEM meso rank threshold raised to ≥ 4
  (constant _MESO_MIN_RANK in services/radar_storm_attributes_service.py).
  Ranks 1–3 are weak shear not shown by professional tools; verified against
  Radarscope on a live event (KRAX, 2026-06-28).
- Storm-cell icon set redesigned: Storm Cell icon is now a small dark square
  with yellow border (was a circle); Probable Hail hollow green triangle has
  no label (question mark removed from both map icon and mini-legend).
- Floating Storm Tracks mini-legend added as a Leaflet topright control
  (NstLegendControl in weather.js), shown/hidden with the Storm Tracks toggle.
  CSS class .wx-mini-legend is reusable for similar legends on other pages.
- Radar site markers now have a black outline on all status variants for
  legibility on dark basemaps. Selected-site highlight rings unchanged.
- Debug endpoint /api/radar/debug/meso-raw?site=KXXX added to routes/radar.py
  for inspecting raw IEM meso/tvs field values during threshold tuning.
- Level 2 radar super-res products (L2_REF, L2_VEL, L2_SRV, L2_SW, L2_ZDR,
  L2_RHO, L2_PHI, L3_N0B, L3_N0G) render at figure_size_inches=22 (4400px);
  all other L3 products remain at 12in (2400px). Configured per-product in
  LIVE_RADAR_PRODUCTS in radar_config.py.
- Elevation selection always picks the lowest available tilt (min fixed_angle)
  by default. The Auto option was removed from the UI; the seed <option> in
  weather.html has value="" and no text. L3 products never show elevation pills
  (single fixed sweep) — this is correct, not a bug.
- L2 radar now uses the unidata-nexrad-level2-chunks S3 bucket via
  radar/radar_chunks_utils.py. Individual chunks are cached locally in
  cache/radar/live/l2_chunk_cache/ so each 60s worker run only downloads delta
  chunks (~5-10 per in-progress scan). Complete scans get a .complete marker
  and skip S3 entirely. Enabled by LIVE_RADAR_L2_USE_CHUNKS=True in
  radar_config.py. End-to-end latency ~1-2 min from scan start vs 6-11 min before.
- RADAR_AUTO_REFRESH_MS changed from 3 min to 90 s in weather.js to match
  the L2 chunks polling cadence.
- Wx-Dashboard-Radar-Live scheduled task is now ENABLED at 1-minute intervals
  (changed from 5 min, was previously disabled). L2 runs every invocation; L3
  is gated by radar_live_l3 freshness sentinel (~5 min effective cadence). Re-run
  tools/install_tasks.ps1 after any Task Scheduler reset.
- "Next Update" countdown (wx-radar-next-update-status) removed; Last Update in
  the reliability row is the freshness indicator.
- BR.pal reflectivity colormap rewritten: Radarscope-inspired green (5–25 dBZ)
  → yellow (25–30) → orange (30–45) → red (45–55) → pink/magenta (55–70) →
  white (70–75+). cache_variant bumped to br_min5dbz_v4.
- Reflectivity legend colorbar now starts at min_value (5 dBZ) via legend_vmin
  in /api/radar/colortable response; logic in radar_colortable_utils.py and
  radar_service.py.

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
