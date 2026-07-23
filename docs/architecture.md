# System Architecture

## Source Control (2026-04-16)

Private GitHub repository. Rollback via `git restore`/`git revert`. High-risk refactors should be committed in small checkpoints. PR-based merges to `main` are the preferred gate for structural backend changes.

## Phase 1+ State (Leaflet Map)

The application landing page is `index.html`, served at `/`. The severe-weather
workspace is `frontend/pages/workspace/workspace.html`, served at `/workspace`;
`/weather.html` is now a compatibility redirect.

- Vector GeoJSON overlays (alerts, SPC)
- Pre-rendered raster overlays + frame-locked value points (RTMA)
- Radar live overlays from cache-first per-site/per-product PNG streams

Active root pages and their JS in this checkout:

- `index.html` — main landing page for the dashboard
- `/workspace` — Stage 2 composition page. It imports the Alerts and Radar
  engines (never their page controllers), combines active warnings/LSRs with
  live radar, and owns the Projected Arrival Tool in
  `frontend/pages/workspace/workspace-tools.js`.
- `/drought` — first true Stage 2 standalone page, served from
  `frontend/pages/drought/drought.html`; it loads ES modules from
  `frontend/core/` and its own directory and does not load `js/weather.js`.
  Shared `map-core.js` owns the Leaflet map, basemaps, logo, region fitting,
  Lat/Lon/state/country/county overlays, and cached US/World city-label layers
  with bounded density filtering. It also supplies the shared reset-view and
  numeric-zoom controls. Pages may provide an `onResetView` hook to clear
  product state before the shared Home control refits the active region. The
  Drought page owns its controls and supplies the
  product-specific content for a bottom-left expandable legend;
  `frontend/core/nav.js` owns the icon-bearing
  product navigation. Large static map payloads use `fetchCachedJson()` and
  versioned browser Cache Storage. Boundary builders retain decoded runtime
  cache data in memory, while the routes expose state/county filtering and
  long-lived immutable response caching.
- `frontend/core/sidebar-tabs.js` is the shared standalone-page sidebar
  controller. It keeps tab panels mounted, manages accessible selected/hidden
  state and roving focus, and allows a page-defined optional fourth tab. Shared
  pinned header, tab bar, scrollable content, and pinned footer primitives live
  in `frontend/core/core.css`; product CSS supplies only panel-specific layout.
- `frontend/core/legend.js` owns the standalone-page legend host lifecycle,
  left/center/right alignment, and accessible collapsed state. The host is
  absolutely confined to `.core-map-panel`, so it cannot render over a sidebar.
  `frontend/core/core.css` supplies the shared dark tray, categorical-item, and
  continuous-colorbar/tick primitives; product engines retain ownership of
  legend content, thresholds, colors, labels, and values.
- `frontend/core/core.css` also owns the standalone shell's typography. It loads
  the existing normal and italic Montserrat variable fonts from the root
  `/fonts` static mount and applies the family through `:root`, allowing product
  pages and controls to inherit the original dashboard type treatment.

Planned product-page migration:

- Product-specific pages are the intended post-refactor direction:
  `/alerts`, `/radar`, `/satellite`, `/spc`, `/surface`, `/mrms`, `/rtma`,
  `/drought`, `/tropical`, `/wpc`, and `/water`.
- The Stage 2 frontend interface contract is recorded in
  `docs/frontend-stage2-core-api-inventory.md`. It prohibits a replacement
  global context: pages import narrow `core/*` capabilities, engines own
  product data/layers, and the workspace composes engine APIs without loading
  sibling page controllers.
- Browser-only Stage 2 assets live under `frontend/` and are mounted at
  `/frontend`. Root `lib/` remains a backend Python package and is not exposed
  as static content.
- Legacy `.html` product URLs may be kept as redirects or compatibility routes
  during the transition, but clean extensionless URLs should become canonical.
- `/alerts` serves `frontend/pages/alerts/alerts.html`, which owns active alert
  and Local Storm Report filtering/rendering, the active-warning rail, immersive
  alert detail, in-memory off/on restoration, page-owned combined status,
  severe-warning pulse styling, and default-on 60-second refresh without
  loading `js/weather.js`. Alerts archive plumbing is dormant and its UI is
  hidden pending a unified one-target-datetime plus lookback design. The radar-
  dependent Projected Arrival Tool remains reserved for the severe-weather
  workspace.
- `/radar` serves `frontend/pages/radar/radar.html`, which owns live site/product
  selection, current and cached-frame playback, NST overlays, legends, and the
  value inspector without loading `js/weather.js`. `/radar.html` remains a
  compatibility route and is separate from the canonical extensionless page.
- `/tropical` serves `frontend/pages/tropical/tropical.html`, which composes its
  page-local engine/controller/application modules with `frontend/core/` and
  does not load `js/weather.js` or the removed root `js/tropical-*` modules.
- `/water` serves `frontend/pages/water/water.html`, which owns viewport-aware
  NOAA river/coastal/buoy loading, flood-stage filters, station popups, and the
  Water legend on the shared core utilities without loading `js/weather.js`.
- Browser dependencies are vendored under `frontend/lib/`; all product pages
  use the local Leaflet 1.9.4 CSS/JS instead of a CDN.
- The legacy `weather.html`, `js/weather.js`, product-shell/context scripts,
  dead root JS modules, and `css/dashboard.css` were retired in Phase 27.

Removed in Phase 0:

- `legacy/` pages and JS are retained but unrouted
- Legacy API render endpoints removed from main.py

## Backend Refresh Coordinator and Workers

Task-scheduler-free Phase 1 adds the application-owned coordinator in
`app_core/refresh_coordinator.py`. FastAPI starts and gracefully stops it
through application lifespan. It provides a bounded executor/queue,
actual-resource-key deduplication, provider concurrency and minimum intervals,
90-second request-presence leases, exponential backoff, state pruning, and
credential-safe reporting at `/api/health/coordinator`.

Surface observation cold/stale refresh, WPC, SPC outlook, and Tropical
advisory/GTWO refreshes are migrated request paths. Surface JSON uses the
unique-temp atomic publisher in
`app_core/atomic_io.py`. Its coordinator key identifies the regional upstream
observation set, so one fetch publishes every Surface product cache. A cold
response reports `refreshing` and the standalone Surface engine polls local
state until the cache is ready. Presence-only states report `idle`. Six-hour
cache cleanup is coordinator-owned and does not require an open page.

Phase 1 supports one application process. `WEB_CONCURRENCY` and
`UVICORN_WORKERS` above 1 are rejected, and CLI multi-worker launches are
unsupported until persistent cross-process leases/provider state exist.
Existing direct-write OS tasks are not safe to overlap with migrated paths.
The older broad APScheduler profile remains fallback-only behind
`WX_INPROC_WORKERS=1`.

The post-refactor deployability target is cross-platform:

- Default: app-managed Python worker supervisor that runs on Windows, macOS, and
  Linux.
- Optional: OS scheduler integration for advanced/headless installs.
- Manual: one-off worker module commands for backfill, troubleshooting, and
  cache priming.

This lets non-technical local users run the dashboard without configuring
Windows Task Scheduler or macOS `launchd`, while preserving OS schedulers for
operator-managed deployments.

Current in-process fallback intervals in `workers/scheduler.py`:

| Worker         | Interval | Notes                                             |
| -------------- | -------- | ------------------------------------------------- |
| alerts_worker  | 1 min    | First run immediate when fallback mode is enabled |
| spc_worker     | 30 min   | First run immediate                               |
| rtma_worker    | 15 min   | First run immediate                               |
| mrms_worker    | 15 min   | First run delayed by 30s                          |
| surface_worker | 30 min   | First run immediate                               |

Manual RTMA backfill/preload:

- `workers/rtma_preload.py` primes the full lookback cache (hourly + rapid update)
- Intended for one-time rebuilds and cold-start priming

Current default runtime behavior (no env var): the coordinator and its cleanup
schedule run, while the older broad APScheduler worker profile is not
registered. Unmigrated products retain their existing paths until later phases.

### Local Dev Run Profiles

The default local startup path is currently:

```powershell
python main.py
```

`WX_INPROC_WORKERS=1` enables the legacy broad in-process schedule for fallback
testing. Do not combine migrated application refreshes with existing
direct-write task definitions; optional warmers require the later shared
persistent coordination protocol.

Future launcher expectation:

- A cross-platform app startup path should start the API, start the app-managed
  worker supervisor by default, and open the browser.
- API-only mode should remain available for development and debugging.

## Data Endpoints

```
GET /api/data/alerts?state={STATE}   # optional state filter
GET /api/data/alerts?geometry_mode={full|display}&zoom_bucket={low|high}&west={W}&east={E}&south={S}&north={N}
GET /api/data/alerts/lsr?west={W}&east={E}&south={S}&north={N}&hours={1|6|12|24}
GET /api/health/coordinator
GET /api/data/spc?day={1-8}&hazard={cat|torn|wind|hail|prob|windrh|dryt}
GET /api/overlay/latest?family=rtma&region={REGION}&stream={STREAM}&product={PRODUCT}[&frame_key=YYYY_MM_DD_HH_MM_SS]
GET /api/overlay/frames?family=rtma&region={REGION}&stream={STREAM}&product={PRODUCT}
GET /api/data/rtma/points?region={REGION}&stream={STREAM}&product={PRODUCT}[&source_data_key=...]
GET /api/radar/live/sites
GET /api/radar/live/latest?site={SITE}&product={PRODUCT}[&force=true]
GET /api/radar/live/frames?site={SITE}&product={PRODUCT}[&hours=2]
GET /api/satellite-v2/catalog?sat_id={SAT}&sector={SECTOR}&channel={PRODUCT}
GET /api/satellite-v2/tile/{z}/{x}/{y}?sat_id={SAT}&sector={SECTOR}&channel={PRODUCT}&frame_key={FRAME}
```

Alerts:

1. Read the current immutable generation through
   `cache/alerts/current_generation.json`.
2. Below zoom 8, return the national low-detail payload; at zoom 8+, return
   bbox-filtered full geometry.
3. Serve a stale complete generation immediately and submit one deduplicated
   refresh through the coordinator's 35-second `nws-alerts` provider budget.
4. Return an explicit 503 warming/backoff status on a cold missing cache rather
   than a successful empty GeoJSON collection.

SPC remains on its product cache path, but Phase 3 makes recovery and
post-issuance refresh product-specific. `config/refresh_schedules.py` resolves
official UTC and `America/Chicago` boundaries; the request path never launches
the broad outlook matrix for one selected/missing product. Tropical similarly
uses separate coordinator keys for advisory and GTWO scopes while active page
leases permit a conservative ten-minute special-advisory probe.

RTMA overlay endpoints:

1. Read pre-rendered frame metadata from overlay cache index/frame directories.
2. Return overlay metadata (`render.image_url`, `bounds`, `legend`, `timestamp`, `source_data_key`).
3. Frontend requests points with matching `source_data_key` to avoid frame drift.
4. Derived `apparent_temperature` uses temperature, dew point, and wind speed
   from the same source frame to produce one Feels Like field.

Weather radar live endpoints:

1. Read latest/listed frames from `cache/overlays/radar/{SITE}/{LEVEL}/{PRODUCT}`.
2. On cache miss, trigger bounded on-demand render via `workers/radar_live_worker.py`.
3. Latest endpoint prioritizes first-paint responsiveness by rendering newest-first with a single-frame cap on cold start, then starts async history backfill.
4. Responses include `history_filling` so the frontend can signal that animation history is still warming.
5. The requested `hours` value (0.5-12 h, including the UI's 30-minute
   option) propagates through route/service into the NODD worker. A request
   beyond current cache coverage starts bounded newest-to-oldest background
   fill and retains the expanded live history; the scheduled worker keeps its
   one-hour default. This is not an archive-render workflow.

Satellite v2 tile endpoints:

1. Resolve a platform/provider frame catalog, download/cache required source
   channels, and render missing Web Mercator tiles on demand.
2. Tile paths include a platform render-version namespace so display-recipe
   changes can invalidate old pixels without deleting source downloads.
3. Filled satellite images own the basemap inside valid coverage (PNG alpha
   255); invalid/off-disk pixels remain transparent. ADP, AOD, and FRP retain
   product-specific sparse-overlay alpha.

Cache served as static files via `/cache` mount (StaticFiles).

## Frontend Architecture

Standalone product pages use ES modules under `frontend/core/` and
`frontend/pages/{product}/`. The legacy combined workspace described below is
transitional and is not the owner of canonical standalone product routes.

`js/weather.js` — transitional combined-workspace IIFE, no framework, ES6+,
async/await.

Responsibilities:

- Leaflet map init with CartoDB Dark/Light basemap toggle
- `loadAlerts(category)` — fetches `/api/data/alerts`, renders `L.geoJSON`, builds legend
- `loadSpc(day, hazard)` — fetches `/api/data/spc`, renders `L.geoJSON`, builds legend
- `loadRtma()` — fetches `/api/overlay/latest` first, applies `L.imageOverlay`, then fetches frame-locked points
- `loadRtmaScrubberFrames()` — fetches `/api/overlay/frames` for instant frame list
- Radar live site/product selection with multi-site map overlays
- Radar time-mode playback from `/api/radar/live/frames` with context invalidation when selection changes
- Radar clear control that clears loaded radar overlays and exits animate mode back to current without resetting map view
- Satellite tile layers render at Leaflet opacity 1.0; transparency is encoded
  per pixel by the backend rather than applied as a second layer-wide dimming
  pass.
- Region → `fitBounds` mapping (all 50 states + CONUS)
- Layer visibility and opacity sliders (no page reload)
- SPC three-way dropdown: convective / fire / other (tracks `_spcLastTouched`)
- Alert category filter applied client-side against `properties.event`

`js/shared.js` — exports `window.apiUrl`, `window.initNav`, and progress/output helpers (progress helpers are no-ops for the weather page since weather no longer uses the render pipeline).

Standalone Alerts interaction model:

- Clicking an alert polygon or Active Warnings card opens the same draggable,
  height-bounded immersive detail panel.
- Clicking a Latest Storm Reports card zooms to its marker and opens its popup.
- The right rail is absent when neither dataset is selected, shows only the
  applicable panel for a single dataset, and splits Alerts above LSRs when both
  are selected.
- The panel closes on outside map click, Escape, or map move/zoom start.
- TOR/SVR/FFW/SMW polygons pulse fill and border by default; the Style selector
  toggles existing paths without a data reload.
- Official NWS colors remain the polygon/border/legend source of truth. FFW uses
  a separate lighter presentation-only text color on dark UI surfaces.
- Projected Arrival controls are no longer part of Alerts. Their implementation
  belongs to the severe-weather workspace, where radar and alert context coexist.
- The former Radar Speed Estimator was removed project-wide because its assumed
  fixed four-frame, five-minute radar loop no longer exists.

## Pipeline Separation

Weather workflow is mixed by product family:

- Alerts/SPC: data-only endpoints, Leaflet vector rendering
- RTMA: server-side pre-rendered PNG overlays + cached points, Leaflet imageOverlay + markers
  - Feels Like is a derived RTMA product: wind chill at <= 50 F with wind >= 3
    mph, heat index at >= 80 F, otherwise actual temperature.
- Radar (weather tab): cache-first pre-rendered PNG overlays (latest + frames), with bounded on-demand fallback rendering
- Satellite v2: cache-first source/channel resolution plus on-demand Web
  Mercator PNG tiles. Filled imagery is opaque; sparse analytical products
  retain per-product alpha ramps.

Radar/Satellite archive workflows: unchanged — synchronous render pipeline, Lambert projection, server-side image generation, layered PNG scrubber.

## Cache Layout

```
cache/
  alerts/
    national.geojson
    national_full.geojson
    national_display_low.geojson
    current_generation.json
    generations/{generation}/
  rtma/
    points/
      {REGION}/{stream}/{product}__{source_data_key}.geojson
    grib/
      ...
  spc/
    1_cat.geojson
    1_torn.geojson
    ...
    fire_1_windrh.geojson
    fire_1_dryt.geojson
    ...
  overlays/
    index/
      rtma.json
      radar.json
    rtma/
      {REGION}/{stream}/{product}/{frame_key}/
        overlay.png
        meta.json
        bounds.json
    radar/
      {SITE}/{LEVEL}/{PRODUCT}/
        {frame_key}.png
        processed.json
  satellite/
    catalog/{satellite}/{sector}/{product}.json
    source/{satellite}/{sector}/{source_channel}/{frame_key}/...
    tiles/{render_version}/{satellite}/{sector}/{product}/{frame_key}/{z}/{x}/{y}.png
  .workers/
    rtma.last_run
    radar_live.last_run
```

## Python Module Map

| Module                         | Role                                                                          |
| ------------------------------ | ----------------------------------------------------------------------------- |
| `main.py`                      | FastAPI app assembly, middleware, static mounts, router registration, lifecycle events |
| `app_core/http.py`             | Shared HTTP/date validation helpers                                           |
| `app_core/paths.py`            | Runtime path constants and directory creation                                 |
| `app_core/runtime.py`          | Startup/shutdown orchestration                                                |
| `app_core/static_assets.py`    | Cache-aware static file serving                                               |
| `routes/*.py`                  | Product/page API route registration via `APIRouter`                           |
| `services/*.py`                | Product cache, render, worker-fallback, and serialization logic               |
| `app_core/refresh_coordinator.py` | Bounded request refresh, leases, provider policies, backoff, and status     |
| `app_core/atomic_io.py`        | Unique-temp atomic text/JSON publication                                       |
| `config/refresh_schedules.py`  | Issuance boundaries and due-window policy for Phase 3 products                  |
| `workers/scheduler.py`         | APScheduler setup and lifecycle                                               |
| `workers/alerts_worker.py`     | NWS alerts fetch → cache                                                      |
| `workers/spc_worker.py`        | SPC outlook fetch → cache                                                     |
| `workers/rtma_worker.py`       | RTMA points + pre-render overlay refresh                                      |
| `workers/rtma_preload.py`      | One-time RTMA backfill/preload                                                |
| `workers/radar_live_worker.py` | Live radar cache renderer for weather radar endpoints                          |
| `satellite_v2/renderer.py`     | Source-raster loading, Web Mercator reprojection, PNG alpha policy, composite dispatch |
| `satellite_v2/composites.py`   | RGB recipes, including solar-aware/Rayleigh-corrected GOES GeoColor                     |
| `satellite_v2/cache.py`        | Versioned catalog/source/tile cache paths and tile validation                            |
| `alerts/alerts_utils.py`       | `fetch_active_alerts_with_source()`                                           |
| `spc/spc_utils.py`             | `fetch_outlook_geojson()`, `fetch_fire_wx_geojson()`                          |
| `radar/radar_nodd_utils.py`    | NODD radar key listing + downloads with race-tolerant retries                 |
| `rtma_utils.py`                | RTMA source resolution, grid extraction, pre-render generation, point caching |
| `cache/overlay_cache_utils.py` | Overlay frame paths/index/meta helpers                                        |
| `config/geo_config.py`         | `STATE_BOUNDS` dict (used in weather.js)                                      |
| `config/alerts_config.py`      | `ALERT_COLORS` dict                                                           |

## Satellite v2 GeoColor and display-alpha contract (2026-07-16)

GOES GeoColor needs observation and viewing geometry in addition to channel
arrays. GOES NetCDF loading therefore stores `observation_time`, projection
longitude, and satellite height on `SourceRaster`; `render_zoom_canvas()` passes
those values with the canvas lon/lat grid into `render_composite_rgb()`.

The daytime path in `satellite_v2/composites.py` is:

1. Normalize ABI Channels 1, 2, and 3 while retaining bright-cloud
   reflectance above 1.0.
2. Apply a bounded, wavelength-dependent Rayleigh path-reflectance correction
   using solar and geostationary viewing geometry.
3. Construct the established CIMSS/Kaba simulated green.
4. Apply the CIRA logarithmic visible stretch, a GeoColor-only `0.85` display
   white point, and the small `1.08` saturation adjustment.
5. Blend day/night by solar zenith rather than visible surface brightness.

`GeoColorBlkMar` uses the same daytime path. Its static Black Marble city-light
image is sampled and composited into nighttime RGB before PNG encoding; it is
not the Leaflet basemap and is not hidden by full tile opacity.

Alpha ownership is deliberately split by product semantics:

- Filled RGB and scalar imagery: alpha 255 for valid pixels, 0 outside valid
  coverage; Leaflet layer opacity 1.0.
- ADP: categorical confidence alpha.
- AOD: value-driven alpha ramp.
- FRP: sparse overlay alpha.

Current render namespaces carrying this contract are `products-v5` for the
default/GOES path, `products-ahi3` for Himawari-9, and `products-fci3` for
Meteosat-12. Any pixel-output optimization must establish golden tiles from
these namespaces before changing the render pipeline.

## Radar / Satellite Product Pages (Planned / Needs Revalidation)

The intended product-page split includes independent `radar.html` and
`satellite.html` pages. Those pages may retain or reintroduce:

- Synchronous render pipeline
- Lambert conformal conic projection
- Layered PNG scrubber
- `/api/radar`, `/api/satellite` endpoints
- `active_tasks` progress tracking

Those root HTML files are not present in this checkout yet. Treat this section
as a planned migration target until the pages and endpoints are revalidated.
The standalone Radar page is on the cache-first live overlay contract via
`/api/radar/live/*`.

Planned direction:

- Continue migrating relevant tabs (Surface, MRMS, archive Radar, Satellite) toward the cache-first pre-render contract.
- Alerts remain on the existing vector GeoJSON workflow.

## Weather Radar Live Notes (2026-05-05)

- Cold-start latest requests now prioritize immediate first frame: newest-first, single-frame synchronous render, then async history backfill.
- History backfill is guarded by a per-site/per-product fallback lock to avoid duplicate warm passes.
- `radar_nodd_utils.py` download loop tolerates expected Windows file races (`FileExistsError`, `PermissionError`) with retry + race-resolved success detection.
- Frontend radar controls now include explicit `Clear` behavior (clear loaded radar overlays only, do not reset map view) and site legend visibility tracks the `Show Radar Sites` toggle.

## MRMS Overlay Cache — Rollout Status (2026-05-01)

Backend infrastructure complete; frontend scrubber not yet built.

**Completed:**

- `workers/mrms_worker.py` writes each rendered CONUS PNG to the overlay cache after every 15-min cycle. Accepts `keep_n: int | None` to defer pruning during batch writes.
- `workers/mrms_preload.py` backfills all 14 products across their full lookback windows using `list_mrms_files`. Per-product pruning happens once at the end of each batch.
- `routes/overlays.py` / `services/overlay_service.py` — `mrms` is included in
  the `allowed_families` allowlist on both `/api/overlay/latest` and
  `/api/overlay/frames`.
- `js/weather.js` `loadMrms()` — tries `/api/overlay/latest?family=mrms&...` first; falls back to legacy `/api/data/mrms` on failure.

**Required before 24-hour MRMS scrubber works:**

1. **Raise `keep_n` in `mrms_worker.py`** — current default is `keep_n=3`. At 15-min worker cadence a 24-hour scrubber needs `keep_n=96`. Increase to at least 96 (or a config constant).

2. **Raise preload lookback + `_keep_n` in `mrms_preload.py`** — `_lookback_minutes` returns 120 min for high-cadence products. For 24-hour backfill set it to `24 * 60`. `_keep_n` for high-cadence should match worker target (96+).

3. **Add MRMS scrubber to `js/weather.js`** — port the RTMA scrubber pattern:
   - `loadMrmsFrames()` calls `/api/overlay/frames?family=mrms&region=CONUS&stream=default&product={product}` to populate the frame list.
   - Scrubber slider maps frame index → `frame_key`, then calls `/api/overlay/latest?...&frame_key={key}`.
   - Overlay and legend update on slide; no points endpoint needed (MRMS has no value-point layer).

The overlay cache contract and endpoints are identical to RTMA, so the scrubber implementation is a direct port with no backend changes required.

**Future enhancement — variable-depth scrubbing:**

The overlay cache is already structured to support arbitrarily deep scrubbing. Frames are stored as independent timestamp-keyed directories; `prune_overlay_frames` only trims the oldest down to `keep_n`. To let a user scrub through as many days as they have cached:

- Pass `keep_n=None` to skip pruning entirely, or set `keep_n` to a value matching the desired retention depth (e.g. `keep_n=None` for unbounded, `keep_n=672` for 7 days at 15-min cadence).
- Raise `STREAM_MAX_HOURS` (RTMA) or `_lookback_minutes` (MRMS) to match the desired cold-start backfill depth.
- No frontend changes required — `loadRtmaScrubberFrames()` / `loadMrmsFrames()` already call `/api/overlay/frames`, which returns whatever is in the cache; the scrubber slider auto-sizes to the available frame count.

The only practical constraints are local disk space and the S3 source data availability window (NODD retains RTMA/MRMS data for a rolling 2–7 days depending on product).

## Radar Filtered Reflectivity — Future Enhancement (2026-05-05)

**Planned Feature:**

Dual-render filtered reflectivity output to reduce ground clutter and clear-air artifacts. Worker generates two overlay PNGs per frame:

- `{PRODUCT}_full.png` — original data (current behavior)
- `{PRODUCT}_filtered.png` — clutter masked

Filtering logic (to be implemented in `workers/radar_live_worker.py`):

```python
mask = (
    (cc < 0.82) &  # Low correlation coefficient targets non-precipitation
    (reflectivity < 40)  # Weak reflectivity targets clutter + weak returns
)
reflectivity[mask] = np.nan  # PyART-compatible masking
```

**Requirements:**

1. Verify correlation coefficient (CC) field availability in NEXRAD Level 2 via PyART (field name: `correlation_coefficient`)
2. Modify `_render_overlay_png()` to apply mask before colormap rendering
3. Store both frame variants in cache; update metadata schema to track `{full,filtered}` frames
4. Add `/api/radar/live/frames?filter=true|false` query parameter to endpoint
5. Frontend toggle in Radar sidebar; update legend title/annotation when filtered mode active
6. State persistence strategy (preserve toggle across site/product switches or reset per interaction)

**Design Trade-offs:**

- **Dual-render (recommended)**: 2x cache storage, instant toggle UX (~0ms latency)
- **On-demand filtering endpoint**: Lighter cache, ~500ms latency on first toggle if not pre-cached
- **Frontend canvas masking**: Zero backend changes, but requires CC pixel-data and complex JS canvas logic

**Threshold Validation:**

CC < 0.82 and reflectivity < 40 dBZ are scientifically sound but may require regional tuning. Consider making thresholds user-configurable if adopted.
