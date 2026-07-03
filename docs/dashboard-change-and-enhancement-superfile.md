# Dashboard Change and Enhancement Superfile

Last updated: 2026-07-02 (Satellite platform view presets)

This file is the canonical planning and status file for dashboard changes,
completed enhancement phases, and future product work. It consolidates the
useful current information from the older roadmap, WPC plan, product-page shell
plan, backend/frontend refactor playbook, and refactor dossier.

Keep separate:

- `docs/architecture.md` for durable system architecture.
- `docs/patterns.md` for coding and implementation patterns.
- `docs/refactor-baseline.md` for the original pre-refactor baseline.
- `docs/next-session-startup-prompt.md` for the short current handoff.

## Current State

- Active repo: `F:\Python\dashboard_2026`.
- The backend route/service refactor is complete enough that product routes and
  services should remain modular. Do not add route logic back to `main.py`.
- The fixed map-first dashboard shell is accepted.
- Canonical product routes serve the shared dashboard shell in product-only mode:
  `/surface`, `/alerts`, `/radar`, `/satellite`, `/spc`, `/rtma`, `/mrms`,
  `/drought`, `/tropical`, `/wpc`, and `/water`.
- `weather.html` remains the combined workspace and should keep working until
  explicitly retired.
- Product engines/pages own product-specific controls, requests, response
  interpretation, and most rendering. `js/weather.js` still owns shared map
  lifecycle, generic archive orchestration, shared scrubber infrastructure, and
  injected callbacks where cross-product state is still coupled.
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
- `/spc` startup must normalize SPC controls and report-filter state before the
  initial `refreshActiveLayers()` call.
- Product-specific code should move only after the route/page has browser proof.
- Keep API paths stable unless a separate API cleanup is explicitly planned.

### Tropical migration

- Tropical is the accepted reference UI for rich product pages.
- `js/tropical-engine.js` owns active-storm list, live detail/advisory requests,
  archive catalog requests, per-storm archive base data, advisory requests, and
  response sequencing.
- `js/tropical-page.js` owns active-system cards, archive selectors/cards,
  advisory/fix scrubber state and controls, inspector rendering, forecast table
  rendering, official product/graphics panels, floater state, NESDIS URL
  generation, availability probing, and modal/pill handlers.
- `js/weather.js` still supplies shared map/layer callbacks and GIS overlay
  rendering where those are tied to the common map lifecycle.

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
- The prominent top navigation uses canonical product routes and preserves the
  hidden `weather-type-*` inputs because existing dashboard event listeners
  still depend on them.

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
- Debug endpoint `/api/radar/debug/meso-raw?site=KXXX` returns raw IEM
  `meso`/`tvs` field values for every cell at a site — use this when tuning
  the rank threshold.
- Radar scrubber auto-update now triggers an on-demand backend render on each
  tick via `?refresh=true` on `/api/radar/live/frames`, then restarts the warm
  poll (~3 s interval, 90 s window) to pick up the new frame as soon as the
  render completes. `RADAR_AUTO_REFRESH_MS` is 90 s (was 3 min) to match the
  L2 chunks polling cadence.
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
- L2 chunks workflow: Level 2 products are sourced from the
  `unidata-nexrad-level2-chunks` S3 bucket via `radar/radar_chunks_utils.py`
  instead of the full-volume NODD path. Chunks are cached individually in
  `cache/radar/live/l2_chunk_cache/{SITE}/{DATE}-{TIME}/`; each worker run
  downloads only new delta chunks (~5–10 per in-progress scan). A `.complete`
  marker prevents any S3 I/O once the end-of-volume chunk (type E) is received.
  Mtime-keyed processed_keys entries ensure partial scans are re-rendered as
  more chunks arrive. End-to-end latency ~1–2 min from scan start vs 6–11 min
  before. Enabled by `LIVE_RADAR_L2_USE_CHUNKS = True` in `radar_config.py`.
- `Wx-Dashboard-Radar-Live` scheduled task is now ENABLED at 1-minute intervals
  (changed from 5 min; was previously disabled). L2 runs every invocation; L3
  is gated by `radar_live_l3` freshness sentinel (~5 min effective cadence).
  Freshness sentinels `radar_live` (3 min) and `radar_live_l3` (15 min) are
  registered in `_HEALTH_THRESHOLDS` in `workers/_freshness.py`. Re-run
  `tools/install_tasks.ps1` after any Task Scheduler reset.

Current radar notes:

- IEM storm attributes replaced the earlier AWS-NST/AWS-NMD/TGFTP approach.
- `radar_nst_service.py` was removed after the storm-attribute service replaced
  its remaining role.
- Selected-cell SRV and storm-track overlay visibility must remain decoupled so
  hiding tracks does not invalidate the active SRV animation context.
- IEM meso rank 1–3 = weak shear only; do not lower `_MESO_MIN_RANK` below 4
  without comparing against a reference tool (e.g. Radarscope) on a live event.
- The `Wx-Dashboard-Radar-Live` scheduled task runs every 1 minute. L2 products
  use the chunks path (cheap per-run); L3 products are internally gated by the
  `radar_live_l3` sentinel and only re-download/render every ~5 minutes. On-demand
  rendering via `?refresh=true` still works as a full fallback when the task is
  not running.
- Do not bump `cache_variant` for BR products without also updating the comment
  in `radar_config.py` and confirming the pal file change is intentional; stale
  frames from the old variant accumulate on disk but are ignored automatically.
- Legacy `/api/radar/tiles/{z}/{x}/{y}` and `/api/radar/tiles/freshness`
  endpoints still exist in `routes/radar.py` / `services/radar_service.py` for
  API compatibility, but the production frontend no longer calls them.

### Satellite and lightning

Completed enhancements (2026-06-28):

- Implemented GOES composites were exposed in the Satellite product selector:
  Fire Temperature, Air Mass, Day Cloud Phase, Day Land Cloud/Fire,
  Day Snow/Fog, Nighttime Microphysics, Dust, Ash, and Sulfur Dioxide.
- Renderer-matched interpretive legends were added for those RGB composites,
  with frontend fallback metadata so legends remain visible through
  satellite/sector/product switches without requiring a hard refresh. Scalar
  colorbars remain limited to brightness-temperature channels.

Planned/enhancement direction:

- Replace flat satellite tabs with filtered Region, Platform, Sector, and
  Product controls.

### Water page

V1 is active implementation.

- `/water` is registered in the shared product shell and navigation.
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
- The sidebar `Networks` selector follows the Surface page pattern.
- Leaflet world-wrap bbox edge cases are normalized/clamped instead of returning
  422s at world view.
- Map is constrained to a single world copy: `noWrap: true` on all basemap tile
  layers, `maxBounds` set to the world extent, `maxBoundsViscosity: 1.0`, and
  `minZoom: 2`.

Completed enhancements (2026-06-28):

- River Flood Filter pills (All / Action+ / Minor+ / Moderate+ / Major) added to
  the water sidebar. Client-side filter; coastal and NDBC markers always remain
  visible. Pills are hidden when the River network is unchecked and the filter
  resets to All automatically.
- Stage gauge bar added to river gauge popups when flood threshold data is
  available. Shows color-coded zones (normal / action / minor / moderate / major)
  with a white current-stage marker and a threshold summary line.
- CO-OPS click enrichment: on-click live fetch from the CO-OPS API populates
  Water Level (or Current Speed / Direction) in the coastal station popup.
- NDBC buoy popup replaced flat reading rows with a grouped card layout:
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
- After the current platforms, auto-center, standard products, and extent
  presets are complete, add these future sources:
  - GK2A from `arn:aws:s3:::noaa-gk2a-pds`.
  - NOAA GMGSI Meteosat composite from `noaa-gmgsi-pds`.

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

Next visible-products sequence for non-NOAA satellites:

1. Start with a Meteosat-12 visible scalar proof. First target:
   ABI-style `Channel02` -> FCI `vis_06`.
2. Validate cached/live FCI extraction before UI exposure. Confirm reflectance
   calibration works, ranges are sane, finite coverage is expected, and a proof
   render aligns with coastlines.
3. Expose only proven products in the Meteosat-12 frontend filter. Add
   `Channel02` after the proof render passes; do not expose additional visible
   or RGB products by source mapping alone.
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
3. Cross-product severe-weather workspace combining Radar, warnings, SPC
   outlooks, storm reports, and possibly a broader current-weather workspace.

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

Keep archived files for historical detail. Prefer this superfile for current
planning and status.
