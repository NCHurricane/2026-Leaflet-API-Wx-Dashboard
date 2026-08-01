# Satellite & Radar Render Pipeline — File Reference

Archived 2026-07-31 after both optimization tracks and current-dashboard
stabilization acceptance completed. Companion to
`docs/archive/radar-render-optimization-plan.md`; retained as the historical
pipeline map.

Prepared 2026-07-11 for a speed-focused pipeline review (click -> download ->
render -> output). Files are ordered by pipeline stage, not alphabetically.
Config files with the actual tunable knobs (worker counts, cache sizes,
prefetch windows) are called out separately at the end of each section —
start there before touching pipeline code.

## Satellite (`satellite_v2`)

### 1. Frontend — click to request
- `js/satellite-page.js` — selection chain UI (Satellite -> Sector -> View ->
  Product), builds the tile/frame request
- `js/satellite-engine.js` — product engine: request construction, response
  interpretation, tile layer wiring
- `js/weather.js` — shared map lifecycle, scrubber infrastructure, legend
  fetch/render for satellite (search `_fetchSatelliteLegend`,
  `_updateSatelliteLegend`, `_activeSatelliteSatId`)
- `weather.html` — script tag load order / cache-busting versions for the
  above three

### 2. API entry
- `routes/satellite_v2.py` — tile, legend, status, catalog endpoints

### 3. Frame discovery / cache-hit decision
- `satellite_v2/service.py` — legend/status payloads, tile-serve orchestration
- `satellite_v2/catalog.py` — frame discovery/listing

### 4. Source download
- `satellite_v2/providers.py` — shared download orchestration
  (`download_product_source_frames`)
- `satellite_v2/provider_aws.py` — GOES (ABI) source fetch
- `satellite_v2/provider_eumetsat.py` — Meteosat (SEVIRI/FCI) source fetch,
  manifest fast-path
- `satellite_v2/provider_himawari.py` — Himawari (AHI) source fetch

### 5. Instrument-specific parse
- `satellite_v2/seviri_nat.py` — SEVIRI `.nat` parser (Meteosat-9/11)
- `satellite_v2/fci_nc.py` — FCI NetCDF parser (Meteosat-12)
- `satellite_v2/ahi_hsd.py` — AHI HSD parser (Himawari-9)
- GOES/ABI has no dedicated parser file; it's read directly as NetCDF in
  `providers.py`/`renderer.py`

### 6. Render (reproject + colorize)
- `satellite_v2/renderer.py` — NetCDF -> Web Mercator tile rendering,
  `SatelliteTileRenderer`, instrument resolution, renderer cache
- `satellite_v2/composites.py` — RGB composite recipes/math (per-instrument
  stretch windows live here)
- `config/satellite_colormaps.py` — scalar product colormaps

### 7. Tile planning, warming, cache
- `satellite_v2/tiler.py` — tile coordinate planning, single-tile/zoom-canvas
  render, process-pool warm path
- `satellite_v2/cache.py` — tile cache file I/O, negative-tile markers

### 8. Background prewarm workers (affects perceived speed on first click)
- `satellite_v2/rapid_worker.py` — rapid-refresh tile prewarm (GOES/Himawari)
- `satellite_v2/meteosat_prefetch_worker.py` — Meteosat rolling-window
  prefetch (10-min schedule)

### 9. Platform/product config (not perf knobs, but defines what gets fetched/rendered)
- `config/satellite_platforms.py` — platform -> instrument/provider/sector
  descriptors
- `config/satellite_v2_config.py` — product registry, source-channel
  requirements, sector bounds, legends

### Perf knobs (start here)
- `config/satellite_v2_config.py` — search for `_WORKER`, `_CACHE_SIZE`,
  `_PREFETCH`, `_TILE_WORKERS` (e.g.
  `SATELLITE_V2_LIVE_TILE_RENDER_WORKERS`, `SATELLITE_V2_NETCDF_CACHE_SIZE`,
  `SATELLITE_V2_RENDERER_CACHE_SIZE`, `SATELLITE_V2_RAPID_WORKER_*`,
  `SATELLITE_V2_METEOSAT_PREFETCH_*`)

---

## Radar

### 1. Frontend — click to request
- `frontend/pages/radar/radar-page.js` — standalone site/product/elevation,
  map-control, auto-update, and shared scrubber wiring
- `frontend/pages/radar/radar-engine.js` — request construction, response
  interpretation, pooled image overlays, site/NST layers, legends, and value
  inspector
- `frontend/pages/radar/radar.html` / `radar.css` — standalone Option 1A shell
  and Radar-specific layout/styles
- `frontend/core/{map-core,legend,scrubber}.js` — shared map, legend-host, and
  playback primitives used by Radar

### 2. API entry
- `routes/radar.py` — tile, legend, site/product listing endpoints

### 3. Cache/response orchestration
- `services/radar_service.py` — route-facing cache/response logic
- `services/radar_storm_attributes_service.py` — SCIT/storm attribute overlay

### 4. Source download
- `radar/radar_nodd_utils.py` — NEXRAD Open Data (NODD) bucket fetch
- `radar/radar_chunks_utils.py` — chunked Level 2 fetch path; implemented
  then reverted 2026-07-04 (no latency benefit measured over flat NODD
  bucket), left in place unused in case it's revisited

### 5. Decode + render (sweep selection, colorize)
- `workers/radar_live_worker.py` — Level 2/Level 3 decode, field-aware sweep
  selection, tile render
- `radar/radar_colormaps.py` — `.pal` colortable parsing/application
- `config/radar_colortable_utils.py` — colortable lookup/caching helpers
- `radar/radar_utils.py` — shared decode/render helpers
- `radar/nexrad_coordinates.py` — site geometry/coordinate helpers

### 6. Product/site config (not perf knobs, but defines what gets fetched/rendered)
- `config/radar_config.py` — product list, elevation defaults, CONUS vs
  non-CONUS Level 2/3 availability

### Perf knobs (start here)
- `config/radar_config.py` — search for `LIVE_RADAR_*_WORKER_*`,
  `LIVE_RADAR_PARALLEL_WORKERS`, `LIVE_RADAR_*_INTERVAL_MIN`,
  `LIVE_RADAR_L2_USE_CHUNKS`

---

## Shared / cross-cutting
- `js/weather.js` — shared map lifecycle, generic archive orchestration,
  shared scrubber infrastructure for both products (search the
  satellite/radar-prefixed sections rather than reading the whole file)
- `docs/architecture.md` — system boundary conventions (routes vs services vs
  workers) referenced by both pipelines
- `docs/patterns.md` — product/workflow implementation pattern both pipelines
  follow

## Notes for the reviewer
- Product engines (`*-engine.js`) own request construction and response
  interpretation; product pages (`*-page.js`) own the selection-chain UI;
  `js/weather.js` owns only what's still cross-product-coupled (map
  lifecycle, scrubber, legend fetch). Don't expect all rendering logic in
  one file per product.
- `js/satellite.js` exists in the repo but is not loaded by `weather.html`
  or any other page — dead file, skip it.
- Radar Level 2 chunked fetch (`radar_chunks_utils.py`) is present but
  disabled (`LIVE_RADAR_L2_USE_CHUNKS = False`) after benchmarking showed no
  benefit — worth knowing before re-proposing a similar optimization.
