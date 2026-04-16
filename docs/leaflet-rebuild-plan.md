# Plan: Leaflet + FastAPI + Background Workers (In-Place Rebuild)

## TL;DR

Clean the existing 2026-Dashboard directory in-place (backed up). Delete legacy bloat, strip rendering from data modules, add background workers + Leaflet frontend. Three-layer architecture: (1) background Python workers pre-cache weather data, (2) FastAPI serves cached data as instant responses, (3) vanilla Leaflet frontend renders client-side. Cartopy retained only for HD export. Zero import path changes needed since directory structure is preserved.

## Architecture Overview

**Layer 1 — Background Workers (Python, APScheduler):**

- Scheduled tasks pull data from NWS/IEM/NODD/SPC on intervals
- Process via MetPy/scipy/cfgrib, write to cache/ directory as JSON/GeoJSON/PNG
- Current-mode data is always pre-cached or lazy-cached; API never waits for fetches
- Workers run inside the FastAPI process via APScheduler (single process, shared cache)

**Layer 2 — FastAPI Backend:**

- Data endpoints read from cache → instant JSON/GeoJSON/PNG responses
- Archive endpoints fetch on-demand (historical data can't be pre-cached)
- Export endpoints render via Cartopy on-demand (HD social media graphics)
- Radar/Satellite endpoints unchanged

**Layer 3 — Vanilla Leaflet Frontend:**

- Full-page Leaflet map with CartoDB Dark/Light toggle
- Vector products (Alerts, SPC) via L.geoJSON()
- Simple surface values via L.divIcon markers
- Raster products (MRMS, gradients, station plot) via L.imageOverlay()
- ES module organization (no build tool needed)
- Quick screenshot via leaflet-image + HD export via server Cartopy

## Project Structure (In-Place, After Cleanup)

```
2026-Dashboard/                    # Same directory, cleaned
├── main.py                        # GUTTED → clean (~800-1000 lines)
├── workers/                       # NEW — background data workers
│   ├── scheduler.py               # APScheduler config + job registration
│   ├── alerts_worker.py           # NWS national alerts → cache
│   ├── spc_worker.py              # SPC outlook GeoJSON → cache
│   └── mrms_worker.py             # Active GRIB2 product → cache
├── export/                        # NEW — Cartopy for HD export only
│   ├── cartopy_render.py          # Branded 1920×1080 frames with HUD/logo/legend
│   └── animation.py               # MP4 via video_utils
├── cache/                         # NEW — worker output (gitignored)
│   ├── alerts/                    # national.geojson
│   ├── spc/                       # {day}_{hazard}.geojson
│   ├── mrms/                      # {product}/conus.grib2 + region PNGs
│   ├── surface/                   # {region}/data.json (lazy cache)
│   └── station_plot/              # {region}/plot.png (lazy cache)
├── surface/                       # TRIMMED — data-fetch only
│   └── surface_utils.py           # fetch_metar_data, process_dataframe, derived calcs
├── alerts/                        # TRIMMED — data-fetch only
│   └── alerts_utils.py            # fetch_active_alerts, zone resolution, dedup
├── spc/                           # TRIMMED — data-fetch only
│   └── spc_utils.py               # fetch_outlook_geojson, fetch_fire_wx_geojson
├── mrms/                          # TRIMMED — data-fetch only
│   ├── mrms_utils.py              # read_mrms_grib2, crop logic
│   └── mrms_nodd_utils.py         # S3 listing (unchanged)
├── weather/                       # TRIMMED — session mgmt + archive orchestration
├── radar/                         # UNCHANGED — separate workflow
├── satellite/                     # UNCHANGED — separate workflow
├── config/                        # UNCHANGED
│   ├── geo_config.py, style_config.py, surface_config.py
│   ├── alerts_config.py, mrms_config.py, radar_config.py
│   └── satellite_config.py
├── s3_utils.py                    # UNCHANGED (root-level shared utils)
├── listing_cache.py               # UNCHANGED
├── geo_utils.py                   # UNCHANGED
├── city_utils.py                  # UNCHANGED
├── font_utils.py                  # UNCHANGED
├── video_utils.py                 # UNCHANGED
├── weather.html                   # REWRITTEN — Leaflet map page
├── radar.html                     # UNCHANGED
├── satellite.html                 # UNCHANGED
├── index.html                     # UPDATED — nav only
├── js/
│   ├── weather.js                 # REWRITTEN — Leaflet map + layer management
│   ├── radar.js                   # UNCHANGED
│   ├── satellite.js               # UNCHANGED
│   └── shared.js                  # TRIMMED — keep apiUrl, pollProgress
├── css/
│   └── shared.css                 # MODIFIED — add map container + legend styling
├── shapefiles/                    # UNCHANGED
├── fonts/                         # UNCHANGED
├── data/                          # UNCHANGED
├── basemap_cache/                 # UNCHANGED (protected from purge)
└── docs/
    └── architecture.md            # UPDATED for new architecture
```

## Background Worker Design

### Three-Tier Caching Strategy

**Tier 1: Pre-cache nationally (always warm, trivially cheap)**

- Alerts: ONE NWS API call → all US alerts. Cache as national GeoJSON. Frontend filters by map viewport. 2min interval.
- SPC: ~20 small national GeoJSON files (day×hazard). 30min interval.
- Only 2 workers, minimal resource usage.

**Tier 2: Smart GRIB2 caching — download once, crop on request (MRMS)**

- GRIB2 files are CONUS-wide on S3 regardless of user's region
- Worker downloads latest GRIB2 for ONLY the currently-active MRMS product (not all 69)
- When user switches products, first request downloads new GRIB2 (~3-5s), worker pivots to refreshing that product
- Crop to user's viewport is a numpy array slice (~50ms) — panning the map is instant
- 2min interval for the active product only

**Tier 3: Lazy cache (Surface, Station Plot) — no background worker**

- Fetch on first request, cache with 5min TTL
- Subsequent requests within TTL served from cache (instant)
- Station plot: MetPy render on first request (~2-3s), cached PNG served after
- No worker needed — cache-aside pattern in API endpoint
- Optional: CONUS aggregate fetches all 48 states in parallel (~3s) only when user selects CONUS

**Tier 4: Always on-demand (Radar, Satellite, Archive)**

- No caching strategy. Per-site/per-sector/per-date-range. Current flow.

### APScheduler Configuration

```
Only 3 workers total:
├── alerts_worker        → 2 min, always active, 1 HTTP GET
├── spc_worker           → 30 min, always active, ~20 small HTTP GETs
└── mrms_worker          → 2 min, tracks active_product (switchable)
```

### MRMS Active Product Tracking

- FastAPI stores `active_mrms_product` in app state
- When user requests a different MRMS product:
  1. API checks cache for new product's GRIB2
  2. If miss: download on-demand, cache, return cropped PNG
  3. Update active_mrms_product → worker starts refreshing new product
- Worker only downloads ONE product at a time (not 69)

## API Endpoints

### Data Endpoints (serve from cache — instant)

```
GET /api/data/surface?region=NC&product=temperature
  → { stations: [...], colormap: {...}, timestamp, source }

GET /api/data/alerts?state=NC
  → { geojson: FeatureCollection, legend: [{label, color}], timestamp }

GET /api/data/spc?hazard=categorical&day=1
  → { geojson: FeatureCollection, legend: [{label, color}], timestamp }

GET /api/data/mrms?product=QPE_MS2_01H&region=NC
  → { image_url: "/cache/mrms/.../overlay.png", bounds: [[s,w],[n,e]], colormap, timestamp }

GET /api/data/station-plot?region=NC
  → { image_url: "/cache/station_plot/.../plot.png", bounds: [[s,w],[n,e]], timestamp }
```

### Archive Endpoints (on-demand processing)

```
GET /api/archive/surface?region=NC&product=temperature&date_from=...&date_to=...
  → { frames: [{ timestamp, stations: [...] }, ...] }

GET /api/archive/alerts?state=NC&date_from=...&date_to=...
  → { frames: [{ timestamp, geojson: FeatureCollection }, ...] }

GET /api/archive/mrms?product=...&region=...&date_from=...&date_to=...
  → { frames: [{ timestamp, image_url, bounds }, ...] }
```

### Export Endpoints (on-demand Cartopy render)

```
POST /api/export/frame
  → { image_url: "/exports/.../frame.png" }  (1920×1080 branded)

POST /api/export/animation
  → { video_url: "/exports/.../animation.mp4" }
```

### Radar/Satellite Endpoints (unchanged from current project)

```
GET /api/radar, /api/radar/archive, /api/radar/archive/export-animation
GET /api/satellite/current, /api/satellite/archive, etc.
```

### Metadata

```
GET /api/status          → worker health, cache freshness per product
GET /api/progress/{id}   → archive/export progress polling
```

## Implementation Phases

### Phase 0: Cleanup (Delete Bloat)

**0.1** Delete `legacy/` directory entirely (5 HTML + 5 JS files)
**0.2** Delete `checkpoints/` directory
**0.3** Delete `config/geo_config copy.py`
**0.4** Delete `alerts/shapefiles/` (duplicate of root shapefiles/)
**0.5** Delete outdated docs: `docs/surface-unification-roadmap.md`, `docs/mrms-unification-roadmap.md`, `docs/satellite-unification-roadmap.md`, `docs/alerts-national-state-filter-plan.md`
**0.6** Delete dead archive utils: `surface/surface_archive_utils.py`, `alerts/alerts_archive_utils.py`, `mrms/mrms_archive_utils.py`, `spc/spc_archive_utils.py`
**0.7** Delete `surface/generate_basemaps.py` (legacy basemap generator)
**0.8** In `main.py`: delete legacy endpoint handlers for `/api/surface/*`, `/api/alerts/*`, `/api/mrms/*`, `/api/spc/*` and their helper functions (~915 lines)
**0.9** Strip rendering code from data modules (keep data-fetch functions only):

- `surface/surface_utils.py`: keep `fetch_metar_data()`, `process_dataframe()`, derived calc functions. Delete all Cartopy/matplotlib rendering, figure creation, savefig calls.
- `alerts/alerts_utils.py`: keep `fetch_active_alerts_with_source()`, zone geometry resolution, dedup logic, color assignment. Delete all Cartopy rendering.
- `spc/spc_utils.py`: keep `fetch_outlook_geojson()`, `fetch_fire_wx_geojson()`, `_fire_wx_url()`, risk color maps. Delete all Cartopy rendering, legend rendering, ShapelyFeature.
- `mrms/mrms_utils.py`: keep `read_mrms_grib2()`, `_compute_crop_slices()`, decompress. Delete Cartopy pcolormesh/imshow, animation, figure management.
  **0.10** Move Cartopy export code from `weather/weather_utils.py` → `export/cartopy_render.py` (rendering functions for HD export). Strip data-fetching from weather_utils — it will call data modules instead.
  **0.11** Add `cache/` to `.gitignore`

**Phase 0 Verification:**

- `python main.py` still starts (radar/satellite endpoints work)
- No import errors on startup
- Legacy pages/endpoints return 404
- Data-fetch functions still importable: `from surface.surface_utils import fetch_metar_data` works
- Project has ~3,500-4,000 fewer lines

### Phase 1: Leaflet Map + Workers + Alerts

**1.1** Create `workers/scheduler.py` — APScheduler BackgroundScheduler, register jobs, start on FastAPI startup event
**1.2** Create `workers/alerts_worker.py` — calls `alerts.alerts_utils.fetch_active_alerts_with_source()`, writes national GeoJSON to `cache/alerts/national.geojson`
**1.3** Create `workers/spc_worker.py` — calls `spc.spc_utils.fetch_outlook_geojson()` + `fetch_fire_wx_geojson()` for all day/hazard combos, writes to `cache/spc/`
**1.4** Add new data endpoints to `main.py`:

- `GET /api/data/alerts?state={optional}` → serve from cache, optionally filter by state/viewport
- `GET /api/data/spc?hazard=categorical&day=1` → serve from cache
  **1.5** Rewrite `weather.html` — full-page Leaflet map div, CartoDB Dark/Light toggle, left control panel (product group, product, region selectors), center panel (layer visibility/opacity)
  **1.6** Rewrite `js/weather.js` — Leaflet map init, fetch `/api/data/alerts` → `L.geoJSON()` with style function, click popups, legend as `L.Control`, region dropdown → `map.fitBounds()` from `STATE_BOUNDS`
  **1.7** Trim `js/shared.js` — keep `apiUrl()`, `pollProgress()`, nav helpers. Remove PNG layer display functions.
  **1.8** Update `css/shared.css` — add Leaflet map container, legend control, control panel layout
  **1.9** Rewrite `docs/architecture.md` — replace synchronous render pipeline, `/api/weather` single endpoint, Lambert-only projection, layered PNG session model, `active_tasks` progress, legacy/ archival section, and `/img/...` static output with the new Leaflet + workers + cache architecture. Keep Radar/Satellite exception section.
  **1.10** Rewrite `docs/patterns.md` — update Endpoint/Progress Pattern (progress polling now archive/export only), replace Unified Weather Endpoint Pattern (`/api/weather` → `/api/data/*` + `/api/archive/*` + `/api/export/*`), replace Layered Session Pattern (server PNG layers → client Leaflet layers), update Projection Pattern (Web Mercator for Leaflet map, Lambert only for HD export), remove Legacy Migration Pattern (legacy/ deleted), update legend patterns for client-side rendering. Keep patterns that still apply (Two-Tier Dropdown, Animation Encoding, Cache-First, Date Validation, Style Config).

**Phase 1 Verification:**

- `python main.py` starts server + workers
- Workers auto-fetch alerts + SPC within 5 seconds of startup
- `/api/data/alerts` returns GeoJSON instantly (from cache)
- Leaflet map shows styled alert polygons on weather page
- SPC outlooks render with correct risk colors
- Click polygon → popup with details
- Dark/Light basemap toggle works
- Region dropdown pans/zooms map
- Layer toggle shows/hides alerts and SPC independently

### Phase 2: Surface Observations

**2.1** Add lazy-cache pattern to `main.py`: `GET /api/data/surface?region=NC&product=temperature` → calls `surface.surface_utils.fetch_metar_data()` + `process_dataframe()`, caches result in `cache/surface/{region}/data.json` with 5-min TTL, returns JSON station array with colormap hex values
**2.2** Convert matplotlib colormaps from `config/surface_config.py` to JSON hex arrays for frontend use (add helper function or endpoint)
**2.3** Add surface marker rendering to `js/weather.js` — `L.divIcon` factory with colored circle + value text per station
**2.4** Implement zoom-based density thinning — `map.on('zoomend')` adjusts which markers are visible
**2.5** Add `GET /api/data/station-plot?region=NC` — renders MetPy `StationPlot` to transparent PNG + bounds JSON, caches in `cache/station_plot/{region}/`, returns `{image_url, bounds}`
**2.6** Add `GET /api/data/surface-gradient?region=NC&product=temperature` — scipy griddata + gaussian_filter → transparent PNG + bounds, caches
**2.7** Frontend: `L.imageOverlay(url, bounds)` for station plot and gradient products. Opacity sliders.

**Phase 2 Verification:**

- Temperature markers show colored values on map within 1-2s
- Clicking station marker shows full observation popup
- Zooming in reveals more stations
- Station plot PNG overlay aligns with Leaflet basemap
- Gradient overlay renders correctly
- Second request for same region is instant (cache hit)

### Phase 3: MRMS

**3.1** Create `workers/mrms_worker.py` — downloads latest GRIB2 for `active_mrms_product` from S3, stores in `cache/mrms/{product}/conus.grib2`. Tracks active product via FastAPI app state.
**3.2** Add `GET /api/data/mrms?product=QPE_MS2_01H&bounds=s,w,n,e` — reads cached CONUS GRIB2, numpy crop to bounds, apply colormap → transparent PNG, return `{image_url, bounds, colormap_info}`
**3.3** On product switch: if cache miss, download on-demand (~3-5s), update `active_mrms_product` so worker starts refreshing it
**3.4** Frontend: `L.imageOverlay()` with MRMS PNG. Opacity slider. Two-tier dropdown pattern (composeMrmsProductKey logic migrated from current weather.js).
**3.5** Client-side or server-side colorbar legend for MRMS product

**Phase 3 Verification:**

- MRMS QPE overlay georeferenced correctly on Leaflet map
- All 69 products work via two-tier dropdown
- Panning map to new region re-crops from cached CONUS (~50ms)
- Product switch: first load ~3-5s, subsequent refreshes from worker cache
- Opacity slider works
- Colorbar legend accurate

### Phase 4: Archive Mode + Scrubber

**4.1** Add archive endpoints: `GET /api/archive/alerts`, `/api/archive/spc`, `/api/archive/surface`, `/api/archive/mrms` — on-demand fetch for date ranges, returns timestamped frame arrays
**4.2** Session directory management with manifest JSON, TTL cleanup (reuse existing pattern from weather/)
**4.3** Add scrubber to `js/weather.js` — range slider, step buttons, timestamp display, play/pause
**4.4** On frame change: `clearLayers()`/`addData()` for GeoJSON, `setUrl()` for imageOverlay
**4.5** Preload adjacent frames in background for smooth playback

**Phase 4 Verification:**

- Archive date range picker triggers on-demand fetch
- Progress polling works during archive processing
- Scrubber navigates frames without flicker
- Play button auto-advances at configured FPS

### Phase 5: Export

**5.1** Wire `export/cartopy_render.py` — full Cartopy pipeline for branded 1920×1080 frames. Reads current map state (product, region, timestamp), renders server-side with HUD/logo/legend.
**5.2** Wire `export/animation.py` — multi-frame → MP4 via `video_utils.save_animation()`
**5.3** Add `POST /api/export/frame` and `POST /api/export/animation` endpoints
**5.4** Frontend: screenshot button (leaflet-image → canvas → PNG download), HD export button (calls API), animation export button

**Phase 5 Verification:**

- Screenshot captures current Leaflet map view as PNG
- HD export produces branded 1920×1080 PNG
- Animation export produces MP4
- Export progress shown during server-side render

### Phase 6: Polish

**6.1** Remove old `/api/weather` rendering endpoint (replaced by data endpoints)
**6.2** HTTP cache headers on data endpoints (Cache-Control based on product TTL)
**6.3** Frontend: cache GeoJSON in memory for instant re-toggle
**6.4** Loading indicators per layer (not full-page progress bar)
**6.5** Smooth transitions between products

## File Change Manifest

### DELETE (Phase 0)

| Path                                        | Reason                                                                                  |
| ------------------------------------------- | --------------------------------------------------------------------------------------- |
| `legacy/` (entire directory)                | Dead HTML + JS pages                                                                    |
| `checkpoints/` (entire directory)           | Stale refactor snapshot                                                                 |
| `config/geo_config copy.py`                 | Leftover copy                                                                           |
| `alerts/shapefiles/`                        | Duplicate of root shapefiles/                                                           |
| `surface/surface_archive_utils.py`          | Only used by dead legacy endpoints                                                      |
| `alerts/alerts_archive_utils.py`            | Only used by dead legacy endpoints                                                      |
| `mrms/mrms_archive_utils.py`                | Only used by dead legacy endpoints                                                      |
| `spc/spc_archive_utils.py`                  | Only used by dead legacy endpoints                                                      |
| `surface/generate_basemaps.py`              | Legacy basemap generator                                                                |
| `docs/surface-unification-roadmap.md`       | Outdated                                                                                |
| `docs/mrms-unification-roadmap.md`          | Outdated                                                                                |
| `docs/satellite-unification-roadmap.md`     | Outdated                                                                                |
| `docs/alerts-national-state-filter-plan.md` | Outdated                                                                                |
| ~915 lines in `main.py`                     | Dead `/api/surface/*`, `/api/alerts/*`, `/api/mrms/*`, `/api/spc/*` endpoints + helpers |

### TRIM (Phase 0 — strip rendering, keep data-fetch)

| File                       | Keep                                                                           | Remove                                                      |
| -------------------------- | ------------------------------------------------------------------------------ | ----------------------------------------------------------- |
| `surface/surface_utils.py` | `fetch_metar_data()`, `process_dataframe()`, derived calcs (~600 lines)        | Cartopy rendering, matplotlib figures (~1,200 lines)        |
| `alerts/alerts_utils.py`   | `fetch_active_alerts_with_source()`, zone resolution, dedup (~500 lines)       | Cartopy rendering (~1,100 lines)                            |
| `spc/spc_utils.py`         | `fetch_outlook_geojson()`, `fetch_fire_wx_geojson()`, risk colors (~400 lines) | Cartopy rendering, legend, ShapelyFeature (~2,600 lines)    |
| `mrms/mrms_utils.py`       | `read_mrms_grib2()`, `_compute_crop_slices()`, decompress (~400 lines)         | Cartopy pcolormesh/imshow, figure management (~1,000 lines) |

### CREATE (Phases 1-5)

| Path                       | What                                                  |
| -------------------------- | ----------------------------------------------------- |
| `workers/scheduler.py`     | APScheduler config + startup                          |
| `workers/alerts_worker.py` | National alerts → cache                               |
| `workers/spc_worker.py`    | SPC outlooks → cache                                  |
| `workers/mrms_worker.py`   | Active GRIB2 → cache                                  |
| `export/cartopy_render.py` | HD export rendering (extracted from weather_utils.py) |
| `export/animation.py`      | MP4 export                                            |
| `cache/`                   | Worker output directory (gitignored)                  |

### REWRITE

| File                   | What changes                                                                                                                                              |
| ---------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `weather.html`         | PNG layer stack → full-page Leaflet map + control panels                                                                                                  |
| `js/weather.js`        | Cartopy result display → Leaflet map init, L.geoJSON, L.divIcon, L.imageOverlay, scrubber, export                                                         |
| `main.py`              | Gut legacy endpoints, add new data/archive/export endpoints, add scheduler startup                                                                        |
| `docs/architecture.md` | Replace render pipeline / single endpoint / Lambert-only / PNG session model with Leaflet + workers + cache architecture                                  |
| `docs/patterns.md`     | Update progress, endpoint, session, projection, legend patterns for new architecture; remove Legacy Migration Pattern; keep Radar/Satellite-safe patterns |

### MODIFY

| File             | What changes                                              |
| ---------------- | --------------------------------------------------------- |
| `js/shared.js`   | Remove PNG layer helpers, keep apiUrl/pollProgress/nav    |
| `css/shared.css` | Add Leaflet map container, legend control, marker styling |

### UNCHANGED

| Path                                                                                                  | Why                                |
| ----------------------------------------------------------------------------------------------------- | ---------------------------------- |
| `radar/` (entire module)                                                                              | Separate workflow                  |
| `satellite/` (entire module)                                                                          | Separate workflow                  |
| `radar.html`, `satellite.html`                                                                        | Separate workflows                 |
| `js/radar.js`, `js/satellite.js`                                                                      | Separate workflows                 |
| `config/` (all except deleted copy)                                                                   | Import paths unchanged             |
| `s3_utils.py`, `listing_cache.py`, `geo_utils.py`, `city_utils.py`, `font_utils.py`, `video_utils.py` | Root-level, import paths unchanged |
| `shapefiles/`, `fonts/`, `data/`, `basemap_cache/`                                                    | Static assets unchanged            |
| `mrms/mrms_nodd_utils.py`                                                                             | Pure S3 listing, no rendering      |

## Decisions

- **In-place rebuild** — clean existing directory (backed up), not a new project. Zero import path changes.
- **APScheduler inside FastAPI process** — single process, no separate daemon, shared cache
- **Three-tier caching** — Tier 1: national pre-cache (alerts, SPC), Tier 2: smart GRIB2 caching (MRMS), Tier 3: lazy cache on request (surface, station plot)
- **File-based cache** — simple, inspectable, no Redis/DB dependency
- **Vanilla JS + ES modules** — no build tool, no Node.js, no Astro
- **Leaflet CDN** — no npm install for frontend deps
- **Station plot stays server-rendered** — MetPy glyph model too complex for browser JS
- **MRMS stays as server-rendered PNG** — GRIB2 processing too heavy for browser
- **Cartopy only for HD export** — never in the request path for map viewing
- **Radar/Satellite unchanged** — separate workflows, not part of this rebuild
- **Each phase produces a working app** — Phase 0 preserves current radar/satellite, Phase 1+ adds Leaflet incrementally

## Scope Exclusions

- No Astro, React, Vue, or frontend framework
- No Node.js build toolchain
- Radar/Satellite workflows unchanged
- Lightning omitted
- No new data sources
- No database (file-based cache only)
