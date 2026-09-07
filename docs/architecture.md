# System Architecture

## Source Control (2026-04-16)

Private GitHub repository. Rollback uses `git restore`/`git revert` as
appropriate. High-risk refactors should be committed in small, independently
revertible checkpoints after the required validation and explicit owner
authorization.

## Current State (Leaflet Map)

The application landing page is `index.html`, served at `/`. The severe-weather
workspace is `frontend/pages/workspace/workspace.html`, served at `/workspace`;
`/weather.html` is now a compatibility redirect.

- Vector GeoJSON overlays (alerts, SPC, WPC)
- Newest-frame Satellite XYZ raster overlay composed above forecast guidance
  but below Radar; the Workspace pane order is RTMA Gradient 350, MRMS 375,
  WPC 390, SPC 400, Satellite 405, Radar 410, boundaries 420, RTMA Values 425,
  and Alerts 440+
- Pre-rendered raster overlays + frame-locked value points (RTMA)
- Radar live overlays from cache-first per-site/per-product PNG streams

The owner reconfirmed this Workspace pane order on 2026-09-06. MRMS and SPC
remain below Satellite; older observations proposing a different order are
deferred.

Active root pages and their JS in this checkout:

- `index.html` — main landing page for the dashboard
- `/workspace` — Stage 2 composition page. It imports the Alerts, Radar,
  curated SPC, bounded one-hour Satellite, RTMA-RU, MRMS, and WPC engines/renderers
  (never their page controllers), combines active warnings/LSRs, live radar,
  SPC outlooks/MDs/watches, optional GOES imagery, RTMA/MRMS analysis, and
  curated WPC ERO, multi-day QPF, active-MPD, and day-filtered Winter guidance,
  and owns the Projected
  Arrival Tool in `frontend/pages/workspace/workspace-tools.js`.
  Overlapping SPC features use the Workspace-local paged context carousel;
  one shared bottom timeline synchronizes Radar, MRMS, Satellite, and RTMA.
  WPC retains its issuance/product cadence and does not join that timeline.
  Satellite sector pills
  select imagery sources without changing the Workspace viewport; Region and
  Home own recentering/reset. Dedicated product controls remain page-owned;
  a unified cross-page Archive workflow is future work in the superfile.
- `/drought` — first true Stage 2 standalone page, served from
  `frontend/pages/drought/drought.html`; it loads ES modules from
  `frontend/core/` and its own directory and does not load `js/weather.js`.
  Shared `map-core.js` owns the Leaflet map, basemaps, decorative map logo,
  region fitting,
  Lat/Lon/state/country/county overlays, and cached US/World city-label layers
  with bounded density filtering. It also supplies the shared reset-view and
  numeric-zoom controls. Pages may provide an `onResetView` hook to clear
  product state before the shared Home control refits the active region. The
  Drought page owns its controls and supplies the
  product-specific content for a bottom-left expandable legend;
  `frontend/core/branding.js` owns the canonical Chuck Copeland Weather asset
  metadata and product-header logo rendering; `frontend/core/nav.js` owns the
  icon-bearing product navigation and invokes that shared header renderer.
  Large static map payloads use `fetchCachedJson()` and
  versioned browser Cache Storage. Boundary builders retain decoded runtime
  cache data in memory, while the routes expose state/county filtering and
  long-lived immutable response caching.
  The shared keyless basemap catalog contains Esri World Dark Gray Base, World
  Light Gray Base, USA Topo Maps, and World Imagery. No separate label/reference
  layer is composed over them; only Dark receives the layer-scoped navy filter.
  Boundary lines share one Leaflet canvas. Pages using `boundaryMode: 'conus'`
  keep states visible, show countries below displayed zoom 7, and show counties
  at displayed zoom 8+. Pages using `boundaryMode: 'world'` keep countries
  visible, show states at displayed zoom 5+, and show counties at zoom 8+.
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
- `frontend/core/non-workspace-alert-monitor.js` is explicitly initialized by
  every standalone product page and excluded from Workspace. Same-origin tabs
  and windows elect one focused/visible owner through `BroadcastChannel` plus
  expiring `localStorage` presence. That owner polls the national alert feed,
  baselines existing alerts, and only announces alerts issued after both the
  browser cohort and current server session began. It deduplicates banner,
  sound, and one-shot alert-colored border flashes. The Alerts page exposes the
  shared On/Off preference and handles its own notice clicks in place; other
  standalone pages open a Workspace `?alert=` link in a new tab. Workspace
  resolves that link to a selected polygon/detail without joining the shared
  monitor cohort.

Product-page architecture (migration completed in Phase 27):

- All product routes are live and canonical (extensionless), served by
  `routes/pages.py`: `/alerts`, `/radar`, `/satellite`, `/spc`, `/surface`,
  `/mrms`, `/rtma`, `/drought`, `/tropical`, `/wpc`, `/water`, and `/workspace`.
  `/weather.html` 307-redirects to `/workspace`.
- The Stage 2 frontend interface contract is recorded in
  `docs/archive/frontend-stage2-core-api-inventory.md`. It prohibits a replacement
  global context: pages import narrow `core/*` capabilities, engines own
  product data/layers, and the workspace composes engine APIs without loading
  sibling page controllers.
- Browser-only Stage 2 assets live under `frontend/` and are mounted at
  `/frontend`. Root `lib/` remains a backend Python package and is not exposed
  as static content.
- Clean extensionless product URLs are canonical. Only explicitly retained
  compatibility redirects, such as `/weather.html` to `/workspace`, remain.
- `/alerts` serves `frontend/pages/alerts/alerts.html`, which owns active alert
  and Local Storm Report filtering/rendering, a national active-warning rail
  independent of the map viewport, immersive alert detail, in-memory off/on
  restoration, page-owned combined status,
  severe-warning pulse styling, and default-on 60-second refresh without
  loading `js/weather.js`. Its Settings tab owns the persisted On/Off control
  for the separate shared standalone-page alert monitor. Deep-linked monitored
  alerts receive one direct national lookup, selected-polygon rendering, detail
  display, and zoom independent of which tab owns ongoing monitoring. Its
  cache-age-aware monitor schedules refresh at the Alerts API TTL boundary and
  preloads/unlocks its notification sound on the first user interaction. Its
  Archive tab is an explicit future-tools placeholder; Alerts has no general
  lookback slider. The radar-dependent Projected Arrival Tool remains reserved
  for the severe-weather workspace.
- `/radar` serves `frontend/pages/radar/radar.html`, which owns live site/product
  selection, current and cached-frame playback, NST overlays, legends, and the
  value inspector. The extensionless `/radar` URL is canonical; the broken
  legacy `/radar.html` route has been removed.
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

The retired root page/controller tree and disconnected legacy API render
endpoints are historical; active ownership is the route/page/engine structure
described above.

## Backend Refresh Coordinator and Workers

Task-scheduler-free Phase 1 adds the application-owned coordinator in
`app_core/refresh_coordinator.py`. FastAPI starts and gracefully stops it
through application lifespan. It provides a bounded executor/queue,
actual-resource-key deduplication, provider concurrency and minimum intervals,
90-second request-presence leases, exponential backoff, state pruning, and
credential-safe reporting at `/api/health/coordinator`.
Phase 7 adds dynamic presence jobs: a selected product can repeat at its
source-appropriate interval while its lease is active, then the coordinator
removes the job after expiry.
Phase 8 makes this the only required refresh lifecycle. Health reports
coordinator, provider/source, resource/cache, current-season Tropical, and
cleanup-maintenance state rather than scheduled-task sentinel ages.

Surface observation cold/stale refresh, WPC, SPC outlook, and Tropical
advisory/GTWO refreshes are migrated request paths. Surface JSON uses the
unique-temp atomic publisher in
`app_core/atomic_io.py`. Its coordinator key identifies the regional upstream
observation set, so one fetch publishes every Surface product cache. A cold
response reports `refreshing` and the standalone Surface engine polls local
state until the cache is ready. Surface gradients use a separate
`(WORLD|CONUS, product)` coordinator key, keep the prior complete artifact
visible while rendering, and share the regional observation snapshot for one
minute. Their process-local render semaphore is independent of Radar's
heavy-render slot and Satellite's byte-budgeted admission queue. Daily
AviationWeather station metadata avoids per-request discovery; the rare IEM
fallback acquires the coordinator's
shared provider budget directly. While a server PNG is pending, the Surface
engine displays the prior masked PNG or observations alone; its unmasked
client-canvas interpolation is reserved for a completed server path that
produced no usable image. Presence-only states report `idle`. Six-hour
cache cleanup is coordinator-owned and does not require an open page.

Surface Live also owns a bounded 15-minute-to-24-hour recent-lookback slider.
It loads the latest current response first, then uses the retained synchronous
Surface frame endpoint to populate a recent scrubber ending at the current
quarter-hour. Current data remains visible if history is unavailable. Older
frames are ASOS-only and do not generate historical gradients. The Surface
Archive tab remains a future-tools placeholder.

The current coordinator supports one application process. `WEB_CONCURRENCY` and
`UVICORN_WORKERS` above 1 are rejected, and CLI multi-worker launches are
unsupported. Persistent cross-process leases/provider state are closed as
unnecessary for this deployment; a deployment change requires a new design.
Existing direct-write OS tasks are not safe to overlap with migrated paths.
There is no in-process worker scheduler; `WX_INPROC_WORKERS` no longer restores
the retired fixed schedule.

The post-refactor deployability target is cross-platform:

- Default: the API and application-owned coordinator on Windows, macOS, and Linux.
- Optional: bounded OS-scheduler warmers that call the running localhost API.
- Manual: one-off worker module commands for backfill, troubleshooting, and
  cache priming.

This lets non-technical local users run the dashboard without configuring
Windows Task Scheduler or macOS `launchd`, while preserving OS schedulers for
operator-managed deployments.

Optional Windows profiles in `workers/optional_warmer.py`:

| Profile   | Interval | Scope                                                   |
| --------- | -------- | ------------------------------------------------------- |
| `core`    | 5 min    | Alerts, SPC, WPC, Tropical, and Water index              |
| `surface` | 30 min   | CONUS temperature points and gradient                    |
| `rtma`    | 15 min   | CONUS Hourly and Rapid Update Temperature latest frames  |
| `mrms`    | 5 min    | PrecipRate, LL 60-minute Rotation Track, and Instant MESH |

The profiles expose `warmed`, `current`, `already_running`, `backoff`, or
`failed`. They call the FastAPI routes instead of importing direct writers, so
all work stays inside the application's coordinator/provider/render budgets.
The RTMA and MRMS profiles are explicit opt-ins because they share heavyweight
render capacity with Radar and Satellite. Keep every optional warmer disabled
during performance benchmark capture.

Current default runtime behavior: the coordinator and its cleanup schedule run;
there is no required or opt-in broad APScheduler worker profile. Persistent
cross-process refresh ownership is not planned for the current single-process
deployment and requires a new design only if deployment changes.

### Local Dev Run Profiles

The default local startup path is currently:

```powershell
python main.py
```

`tools/install_tasks.ps1` defaults to a read-only preview. It can explicitly
install disabled optional API warmers and separately unregister known legacy
direct-writer tasks. Actual unregistration is operator-authorized and never an
application-startup side effect.

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
6. Phase 7 history and discovery work runs through a lease-bound coordinator
   key containing site, level, product, elevation, and storm-motion variant.
   Level 2 chunk-prefix listings are cached for 30 seconds when that optional
   source path is enabled.

Satellite v2 tile endpoints:

1. Resolve a platform/provider frame catalog, download/cache required source
   channels, and render missing Web Mercator tiles on demand.
2. Tile paths include a platform render-version namespace so display-recipe
   changes can invalidate old pixels without deleting source downloads.
3. A live tile miss with neighbor rendering enabled performs one bounded canvas
   warp for the requested 3x3 supertile, then crops, validates, and atomically
   publishes each tile through the same helper used by canvas warming. Explicit
   single-tile prefetch remains single-tile.
4. M12 FCI defers source loading until its destination canvas is known, selects
   native windows, and bounds partial limbs using conservative continuous
   ellipsoid/projection intervals plus warp padding. Proven off-disk rectangles
   skip radiance reads/warps and retain the product's exact transparent RGBA
   through normal colorization. Invalid corners alone cannot discard a disk
   inside the canvas. Out-of-stored-grid ambiguity retains full-native fallback
   using actual source dimensions.
   Its byte-bounded cache deduplicates physical channels and keys every source
   file's path/size/mtime plus the native window; tile identity is `products-fci6`.
   Other loaders with an existing source-grid cap key their decoded-raster cache by
   destination zoom: z1–4 cap at 2048, z5–6 at 4096, and z7+ retain the platform
   cap. SEVIRI and GMGSI retain native loader behavior; frame-bound discovery
   omits destination zoom and therefore retains its prior source behavior.
5. Satellite work uses a fair process-local byte budget. Its capacity follows
   the smallest of `WX_SATELLITE_RENDER_BUDGET_MB` (default 16384 MiB), total host
   RAM / 4 and available RAM / 2. Other Satellite paths retain coarse source-grid
   estimates; M12 reserves actual windows, transient/caller/GDAL/output allowances
   and retained cache bytes after planning. M12 additionally checks available
   headroom before native decoding and defers under pressure without reducing
   resolution. Its retained-array cache defaults to a 256-MiB ceiling, further
   limited by total RAM / 128 and available RAM / 32. An oversized queue job
   still runs alone; one M12 render owns native arrays per process. Queued work
   retains selection cancellation. These are allocation estimates, not a hard
   whole-process memory bound. Radar retains its separate `heavy_render_slot`.
6. Filled satellite images own the basemap inside valid coverage (PNG alpha
   255); invalid/off-disk pixels remain transparent. ADP, AOD, and FRP retain
   product-specific sparse-overlay alpha.
7. Selected rapid sectors and Meteosat source/tile warming are delayed optional
   accelerators owned by the application while request presence remains active.
   Meteosat-9/12 warm only the selected product's newest two frames at z1–z6,
   use platform-longitude disk bounds, stop scheduling on selection release or
   new live work, and prune tile-frame caches with the seven-hour source window.
   M12 warming divides work into at most 3x3 canvases and runs inline, sharing
   the live cache/admission and yielding between canvases. M9/M11 retain their
   process pools. They do not replace the live on-demand tile path.
8. Source downloads deduplicate by platform/sector/frame. EUMETSAT acquisition
   follows search pagination, reuses feature metadata for five minutes, and
   bounds FCI download concurrency with a four-worker hard ceiling. Authorized
   requests retry connection/timeout/5xx failures with bounded backoff; completed
   FCI chunks are reusable. An interrupted individual stream discards its partial
   file and raises; byte-range resume is not implemented. Credential/license
   states remain explicit.
9. Accepted source-tile request ceilings are CONUS z9, Full Disk z8, and Meso
   z9. Leaflet can display higher map zooms by scaling the available imagery.
   Shared CSS scopes discrete-pixel scaling to Satellite tiles and Radar PNGs,
   preserving ordinary browser filtering for basemaps and unrelated overlays.

Cache served as static files via `/cache` mount (StaticFiles).

## Frontend Architecture

Every page is a standalone ES-module app under `frontend/pages/{product}/` composed
with shared `frontend/core/` modules. The combined `js/weather.js` monolith,
`js/shared.js`, and `css/dashboard.css` were retired in Phase 27; the `js/` directory
is empty. Pages import only `core/`, vendored `frontend/lib/`, and their own directory.
`/workspace` may import sibling engine modules but never sibling page controllers.

Shared `frontend/core/` modules:

- `api.js` — `apiUrl()`, `fetchCachedJson()`, and versioned browser Cache Storage.
- `branding.js` — canonical Chuck Copeland Weather asset metadata and accessible
  product-header logo rendering.
- `map-core.js` — Leaflet map factory: basemaps, decorative shared logo,
  `REGION_BOUNDS` + `fitRegion`,
  the reset-view (⌂, returns to the page's home region) and numeric-zoom controls,
  lat/lon/state/county/country overlays, cached US/World city-label layers with bounded
  density filtering, and the `mapViewportLog()` dev tool.
- `nav.js` — icon-bearing product navigation.
- `sidebar-tabs.js` — shared standalone sidebar controller (mounted panels, roving focus).
- `legend.js` — legend host lifecycle (alignment, collapse), confined to `.core-map-panel`.
- `status.js` — timestamp/status/reliability surface.
- `scrubber.js` — shared timeline/scrubber controller.
- `settings.js` — persisted per-page settings via `loadPageSettings()`.

Rich pages (Tropical, Radar, Satellite, Alerts) split into an engine (data/layers) and
controller/app (DOM) alongside their entry module; simpler pages use a single entry.
Product colors and other backend-mirrored constants are embedded as JS constants, not
fetched at runtime.

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
| `mrms/publication.py`          | Shared MRMS render and flat-overlay publication contracts                     |
| `rtma/overlay_publication.py`  | Shared RTMA source-to-overlay publication contract                            |
| `tropical/product_data.py`     | Shared Tropical GIS and advisory parsing contracts                            |
| `config/refresh_schedules.py`  | Issuance boundaries and due-window policy for Phase 3 products                  |
| `workers/alerts_worker.py`     | NWS alerts fetch → cache                                                      |
| `workers/spc_worker.py`        | SPC outlook fetch → cache                                                     |
| `workers/rtma_worker.py`       | RTMA points + pre-render overlay refresh                                      |
| `workers/radar_live_worker.py` | Live radar cache renderer for weather radar endpoints                          |
| `satellite_v2/renderer.py`     | Source-raster loading, Web Mercator reprojection, PNG alpha policy, composite dispatch |
| `satellite_v2/composites.py`   | RGB recipes, including solar-aware/Rayleigh-corrected GOES GeoColor                     |
| `satellite_v2/cache.py`        | Versioned catalog/source/tile cache paths and tile validation                            |
| `satellite_v2/worker_support.py` | Shared Satellite worker cache-root, lock, timing, and job parsing contracts            |
| `alerts/alerts_utils.py`       | `fetch_active_alerts_with_source()`                                           |
| `spc/spc_utils.py`             | `fetch_outlook_geojson()`, `fetch_fire_wx_geojson()`                          |
| `radar/radar_nodd_utils.py`    | NODD radar key listing + downloads with race-tolerant retries                 |
| `rtma_utils.py`                | RTMA source resolution, grid extraction, pre-render generation, point caching |
| `app_core/overlay_cache.py`    | Overlay frame paths/index/meta helpers                                        |
| `config/geo_config.py`         | `STATE_BOUNDS` dict (backend region bounds; frontend uses `REGION_BOUNDS` in `map-core.js`) |
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

Phase 2 canvas/zoom-cap render namespaces carrying this contract are
`products-v9` for the default/GOES/SEVIRI path, `products-ahi5` for Himawari-9,
`products-fci5` for Meteosat-12, `products-ami3` for GK2A, and
`products-gmgsi2` for GMGSI. Golden tiles from preceding namespaces remain
historical comparison evidence for the accepted Phase 2 visual gate. Any new
rendering audit needs a baseline identified against the current checkpoint.

## Radar / Satellite Product Pages (Current State)

Both standalone pages are live and on cache-first contracts:

- `/radar` (`frontend/pages/radar/radar.html`) uses the cache-first live overlay
  contract via `/api/radar/live/*` — no synchronous render pipeline for live view.
- `/satellite` (`frontend/pages/satellite/satellite.html`) uses the satellite-v2
  contract via `/api/satellite-v2/*` — cache-first source/channel resolution plus
  on-demand Web Mercator tiles.

The older root `radar.html`/`satellite.html` split (synchronous Lambert render
pipeline and layered PNG scrubber) was not carried forward for the live paths.
Cleanup Phase 2 also removed the disconnected MRMS/SPC archive render-session
and progress workflow. The retained Alerts and Surface archive endpoints use
synchronous vector/data responses with deterministic JSON caching. They remain
backend groundwork, while the standalone Surface and Alerts Archive tabs are
placeholders pending one future unified cross-page workflow.

Alerts remain on the vector GeoJSON workflow. Future rendering changes belong
in the superfile; this architecture section does not authorize more migration.

## Weather Radar Live Notes (2026-05-05)

- Cold-start latest requests now prioritize immediate first frame: newest-first, single-frame synchronous render, then async history backfill.
- History backfill is guarded by a per-site/per-product fallback lock to avoid duplicate warm passes.
- `radar_nodd_utils.py` download loop tolerates expected Windows file races (`FileExistsError`, `PermissionError`) with retry + race-resolved success detection.
- Frontend radar controls now include explicit `Clear` behavior (clear loaded radar overlays only, do not reset map view) and site legend visibility tracks the `Show Radar Sites` toggle.

## MRMS Overlay Cache and History

The standalone `/mrms` page and Workspace use the current frontend engines and
the shared overlay/tile services; retired `js/weather.js` and broad preload
workflows are not part of the runtime.

- `/api/overlay/latest` and `/api/overlay/frames` expose bounded frame history.
- The native-detail tile path is preferred where a frame is preparable, with
  the complete PNG overlay retained as rollback/fallback.
- During a frame swap, the old complete PNG remains visible and its replacement
  starts at opacity 0. Opacity controls do not expose a pending replacement;
  promotion applies the latest selected opacity. Loaded native tiles are opaque
  before promotion, avoiding Leaflet's per-tile fade over the PNG fallback.
- Frame identity comes from source metadata, including `latest_source.json`,
  rather than file modification time.
- The current UI window is approximately 12 hours. Storage and preparation are
  bounded; unbounded retention is not supported.
- A future 24- or 48-hour option requires an explicit measured decision based
  on upstream availability, disk use, cold-start cost, and user value.

Current Radar/Satellite/MRMS proposals and rejected alternatives belong in
`dashboard-change-and-enhancement-superfile.md`, not implemented architecture.
