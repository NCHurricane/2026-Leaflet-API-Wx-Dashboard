# Next Session Startup Prompt

Date prepared: 2026-07-05

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
- DONE 2026-07-04 (late evening), user-tested: L2 blank velocity/SRV/spectrum
  width fix. NEXRAD split-cut VCPs scan low tilts twice at the same fixed
  angle (surveillance sweep = reflectivity only, Doppler sweep = velocity/SW);
  _select_sweep in workers/radar_live_worker.py picked the first (surveillance)
  sweep by angle alone, rendering fully-masked blanks at every site. Now
  field-aware: among sweeps within 0.1 deg of the matched angle it picks the
  one with the most valid data for the rendered field. Also retired
  elevation="auto" for L2: LIVE_RADAR_L2_DEFAULT_ELEVATION="0.5" in
  config/radar_config.py so the scheduled worker and UI share one ELEV_0P5
  cache key (the dual ELEV_AUTO/ELEV_0P5 double-render is gone; stale
  *__ELEV_AUTO dirs are orphaned/deletable). Gotcha: blank frames stay in
  processed_keys.json and will not self-heal; delete affected product folders
  or wait for new scans.
- DONE 2026-07-04 (late evening), user-tested: Meteosat source-prefetch worker.
  New satellite_v2/meteosat_prefetch_worker.py +
  workers/satellite_v2_meteosat_prefetch_worker.py (download-only, no tiles).
  Per run: newest 2 missing frames + 1 oldest-missing backfill inside a 6 h
  window, 7 h keep-prune, per-file atomic/resumable. Config
  SATELLITE_V2_METEOSAT_PREFETCH_* in config/satellite_v2_config.py. Scheduled
  task Wx-Dashboard-Satellite_v2_meteosat_prefetch (10 min, 25-min TimeLimit
  via new per-task TimeLimit support in tools/install_tasks.ps1; installed and
  enabled). EUMETSAT frames are all-channel bundles so one prefetched frame
  warms every product. Result: Meteosat-12 Channel02 FULLDISK on a warm frame
  renders ~250 ms/tile vs 3-4 min cold. Post-install fix: frame list is
  filtered to the lookback window (catalog over-returns) so backfill no longer
  downloads frames the prune immediately deletes. Himawari-9 deliberately
  excluded (per-band files, no bundle bonus).
- DONE 2026-07-05: Surface gradient overlays no longer retain stale worker PNGs
  indefinitely on open pages. `js/weather.js` now refreshes frontend gradient
  metadata after 5 minutes, fetches `/api/data/surface-gradient` with
  `cache: 'no-cache'`, and appends the worker metadata timestamp as an image URL
  version query. `js/surface-engine.js` re-renders the active gradient after a
  successful prime so replaced worker output is applied without a manual
  product toggle. Static validation passed with `node --check` for touched JS;
  browser smoke pending.
- DONE 2026-07-04: Radar site selector now shows all 164 NWS NEXRAD sites
  (vs. previous 7 CONUS-only). Non-CONUS sites (PGUA/Guam, RKSG/South Korea,
  RODN/Japan, etc.) render Level 2 data on-demand; Level 3 products are disabled
  in the UI for non-CONUS sites to reflect AWS/NODD availability (Level III is
  only generated for CONUS per NOAA spec). Changes: new radar/nexrad_coordinates.py
  (164-site fallback mapping), backend radar_live_site_supported() fix via
  importlib fallback, frontend L2_REF default + CONUS filtering + site-change
  auto-switch to L2, and new _radarSiteConusMap to track CONUS status. All
  changes documented in superfile. Browser smoke pending for non-CONUS site
  selection and L2 rendering.
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
- DONE 2026-07-10: corrected the flat scalar reflectance display across all
  satellite providers. The renderer already applied a power law to Channels
  01-03; the actual missing step was contrast-range expansion. All scalar
  reflectance products (Channels 01-06) now use a fixed 0.02-0.90 reflectance
  window followed by sqrt. Fixed bounds prevent tile seams/frame flicker and
  RGB recipes are unchanged. Cache namespaces bumped to products-v3,
  products-ahi2, and products-fci2. Focused unit tests pass; one GOES-18 tile's
  grayscale p5-p95 range increased from 141 to 178. A direct browser request
  to the new local server returned the corrected 256x256 tile; full-page user
  comparison remains for visual acceptance.
- THEN: continue the non-GOES standard product set per the sequencing decision
  (visible/NIR candidates Channel01->vis_04, Channel03->vis_08/vis_09,
  Channel05->nir_16, Channel06->nir_22; composites only after scalar proofs).
  After those are stable: GK2A (noaa-gk2a-pds), then NOAA GMGSI composite
  (noaa-gmgsi-pds).
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
- Satellite runtime config consolidation (2026-07-04): live tile worker count,
  on-demand catalog window, legend sampling counts, renderer/netCDF cache sizes,
  and GOES/AHI/FCI Full Disk source-grid caps now live in
  config/satellite_v2_config.py. Provider/render/service modules import those
  values; adjust that config for future live-render or source-grid tuning.
- Live on-demand satellite supertiles are enabled via
  SATELLITE_V2_LIVE_SUPERTILE_RADIUS=1 by default. A visible tile miss renders
  the requested tile first, then fills the surrounding 3x3 neighborhood while
  skipping existing/negative-cached tiles. Invalid requested tiles return the
  normal transparent invalid response; neighbor fill errors are counted without
  failing the visible tile request.
- Satellite animation prefetch is cache-only; visible Leaflet tile misses still
  live-render, but background prefetch uses render_live=0 so high-resolution
  Full Disk frame setup does not block the first static view.
- New isolated rapid-sector worker:
  `satellite_v2/rapid_worker.py` plus `workers/satellite_v2_rapid_worker.py`.
  It warms GOES-19/18 MESO1/MESO2, Himawari-9 JAPAN, and Meteosat-11 RSS for
  Channel02/Channel13 only. The old broad Satellite v2 workers were removed;
  Full Disk and broad CONUS use live render, supertiles, and cache reuse.
  `tools/install_tasks.ps1 -IncludeSatellite` registers the new
  Wx-Dashboard-Satellite_v2_rapid task and removes legacy Satellite_v2 task
  names. Optional future CONUS light-warm should be separate and opt-in: latest
  1-2 GOES CONUS frames, Channel02/Channel13, zooms 5/6, 1-2 tile workers.
- Legacy IEM alert-radar loop removed from the product shell: no
  weather-alert-radar-enable checkbox, no weather-opacity-alert-radar slider,
  and no _alertRadar* frontend timer/tile/freshness path. /radar should stay on
  the cache-first /api/radar/live/* workflow. The old /api/radar/tiles/*
  endpoints still exist only for API compatibility.
- City labels now use a Layers-pane `Off | US | World` segmented control.
  `US` keeps `data/us-cities-all.json`; `World` uses `data/world-cities.json`.
  The same density slider applies to both sources through bounded per-source,
  per-zoom km ranges in `js/weather.js`.
- Startup map defaults now read from `config/user_settings.default.json` through
  `GET /api/user-settings/defaults` before the first map fit/product refresh.
  The frontend updates `weather-region` when the configured map view is a valid
  region option, so product loads follow the configured initial region.
- Product route startup respects per-page `autoLoad`; most pages open with
  map/default controls/background metadata only. Current exceptions: Alerts
  autoloads Severe Weather Warnings with TOR/SVR/FFW filters; Tropical starts
  in Atlantic and features the first active storm, falling back to Tropical
  Outlook when none are active. Drought loads release-week date metadata without
  drawing a layer.
- Default-on context controls are state borders, country borders, Surface
  networks, and Radar Sites. Surface and RTMA can still be empty: unchecking
  their selected product/stream/field clears stale map values instead of forcing
  a fallback. Selecting a Surface product auto-checks its matching Gradient
  toggle, which can still be turned off independently. RTMA field checkboxes
  stay disabled until a stream is selected, with 24-hour temperature change
  still Hourly-only. WPC group pills are navigation only and clear the previous
  WPC overlay until the user selects a day/product.
- SPC probabilistic hazards auto-enable their matching Significant/CIG hatch
  layer. Drought release-week pills populate without a highlighted week;
  selecting a week turns on all five drought categories before drawing.
- User browser smoke passed on 2026-07-04 for these startup/default-control
  changes.
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
- L2 radar chunks workflow (unidata-nexrad-level2-chunks bucket via
  radar/radar_chunks_utils.py) was REVERTED 2026-07-04. LIVE_RADAR_L2_USE_CHUNKS
  is now False; L2 uses the same flat-bucket path as L3 (radar/radar_nodd_utils.py).
  Reason: benchmarked chunk-completion timestamps against the flat bucket's
  LastModified for the same scans and they matched to the second -- the flat
  file is posted by the same upstream pipeline the instant the chunk stream
  finishes, so chunks bought zero latency benefit for any completed scan (only
  up to one volume-interval, ~5-6 min, of early visibility into the
  currently-in-progress scan). Not worth the complexity after fixing three
  rounds of chunk-discovery/performance bugs in one session. See the
  "L2 chunks bucket: bugs, latency benchmark, and revert" entry (2026-07-04) in
  docs/dashboard-change-and-enhancement-superfile.md for full details.
  radar_chunks_utils.py is left in place, unused, in case the flag is ever
  flipped back on.
- RADAR_AUTO_REFRESH_MS is 90 s in weather.js (was 3 min); unaffected by the
  chunks revert.
- Wx-Dashboard-Radar-Live scheduled task is now ENABLED at 1-minute intervals
  (changed from 5 min, was previously disabled). L2 runs every invocation; L3
  is gated by radar_live_l3 freshness sentinel (~5 min effective cadence). Re-run
  tools/install_tasks.ps1 after any Task Scheduler reset.
- Radar scrubber warm-poll fix (2026-07-04): Level 2 Play required a manual
  Refresh click to show backfilled frames because (1) render batches write to
  index.json atomically at the end, so a poll mid-render saw zero progress and
  the warm-poll gave up after ~12s -- fixed with an accurate `refreshing` flag
  via app_core/background_render.py's is_live_render_inflight(); and (2) L2's
  elevation <select> auto-resolves from '' to a concrete value on the first
  response, which broke the warm-poll's stale-context guard in js/weather.js
  for any elevation-selectable product. Fixed in js/radar-engine.js by
  re-syncing the stored context key right after updateElevationOptions() runs.
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
