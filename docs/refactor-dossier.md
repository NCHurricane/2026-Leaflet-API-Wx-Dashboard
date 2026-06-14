# Refactor Dossier

Generated: 2026-06-12

This dossier summarizes the current non-UI wiring needed before writing a
detailed refactor plan. It focuses on backend routes, imports, frontend API
calls, workers, cache ownership, startup behavior, and documentation gaps.

## Source Material

- Route/static mount scan of `main.py` and `routes/`.
- AST-based local Python import scan across 70 source files, excluding virtualenv,
  cache, logs, data, and generated folders.
- Frontend script/API scan across `index.html`, `weather.html`, and `js/*.js`.
- Worker/cache/freshness scan across `workers/`, `satellite_v2/`, and `main.py`.
- Existing architecture docs: `docs/architecture.md` and `docs/patterns.md`.

## Backend Surface

Backend shape after the route/service extraction:

- `main.py` owns FastAPI app assembly, middleware, static mounts, lifecycle
  hooks, router registration, SSL certificate environment setup, and the
  uvicorn launch config.
- Product/page route handlers live under `routes/`.
- Product cache, render, worker-fallback, and serialization behavior lives under
  `services/` or existing domain packages such as `satellite_v2/`.
- Static mounts include `/sounds`, `/cache`, `/css`, `/js`, `/data`, `/img`, and
  `/fonts`.
- `/cache` uses custom cache-control behavior through `CacheStaticFiles`.

Route inventory preserved after extraction:

| Group | Method | Path | Handler |
| --- | --- | --- | --- |
| pages | GET | `/` | `read_root` |
| core | GET | `/api/status` | `read_status` |
| overlays | GET | `/api/overlay/world-borders` | `get_world_borders` |
| overlays | GET | `/api/overlay/us-boundaries` | `get_us_boundaries` |
| alerts | GET | `/api/data/alerts` | `get_data_alerts` |
| spc | GET | `/api/data/spc` | `get_data_spc` |
| spc | GET | `/api/data/spc/reports` | `get_data_spc_reports` |
| spc | GET | `/api/data/spc/active` | `get_data_spc_active` |
| drought | GET | `/api/data/drought/dates` | `get_drought_dates` |
| drought | GET | `/api/data/drought` | `get_drought_geojson` |
| drought | GET | `/api/data/drought/state-stats` | `get_drought_state_stats` |
| surface | GET | `/api/data/surface` | `get_data_surface` |
| surface | GET | `/api/data/surface-gradient` | `get_data_surface_gradient` |
| shared | GET | `/api/data/colormap` | `get_colormap` |
| mrms | GET | `/api/mrms/set-product` | `mrms_set_product` |
| mrms | GET | `/api/data/mrms` | `get_data_mrms` |
| rtma | GET | `/api/data/rtma/points` | `get_data_rtma_points` |
| rtma | GET | `/api/data/rtma/grid` | `get_data_rtma_grid` |
| rtma | GET | `/api/data/rtma` | `get_data_rtma` |
| overlays | GET | `/api/overlay/latest` | `get_overlay_latest` |
| overlays | GET | `/api/overlay/frames` | `get_overlay_frames` |
| rtma | GET | `/api/data/rtma/frames` | `get_data_rtma_frames` |
| archive | GET | `/api/archive/mrms` | `archive_mrms` |
| archive | GET | `/api/archive/result` | `archive_result` |
| archive | GET | `/api/archive/alerts` | `archive_alerts` |
| archive | GET | `/api/archive/surface` | `archive_surface` |
| archive | GET | `/api/archive/spc` | `archive_spc` |
| pages | GET | `/radar.html` | `read_radar_page` |
| pages | GET | `/weather.html` | `read_weather_page` |
| core | GET | `/api/progress/{task_id}` | `get_task_progress` |
| radar | GET | `/api/radar/sites` | `get_radar_sites` |
| radar | GET | `/api/radar/site-locations` | `get_radar_site_locations` |
| tropical | GET | `/api/tropical/storms` | `get_tropical_storms` |
| tropical | GET | `/api/tropical/summary` | `get_tropical_summary` |
| tropical | GET | `/api/tropical/basin/{basin_id}/feeds` | `get_tropical_basin_feeds` |
| tropical | GET | `/api/tropical/storm/{storm_id}` | `get_tropical_storm` |
| tropical | GET | `/api/tropical/archive/catalog` | `get_tropical_archive_catalog` |
| tropical | GET | `/api/tropical/archive/storm/{atcf_id}` | `get_tropical_archive_storm` |
| tropical | GET | `/api/tropical/archive/storm/{atcf_id}/advisory/{step}` | `get_tropical_archive_advisory` |
| radar | GET | `/api/radar/colortable` | `get_radar_colortable` |
| radar | GET | `/api/radar/tiles/{z}/{x}/{y}` | `get_radar_alert_tiles` |
| radar | HEAD | `/api/radar/tiles/{z}/{x}/{y}` | `head_radar_alert_tiles` |
| radar | GET | `/api/radar/tiles/freshness` | `get_radar_tiles_freshness` |
| radar | GET | `/api/radar/status` | `get_radar_status` |
| radar | GET | `/api/radar/live/sites` | `get_radar_live_sites` |
| radar | GET | `/api/radar/live/latest` | `get_radar_live_latest` |
| radar | GET | `/api/radar/live/frames` | `get_radar_live_frames` |
| satellite_v2 | GET | `/api/satellite-v2/catalog` | `get_satellite_v2_catalog` |
| satellite_v2 | GET | `/api/satellite-v2/status` | `get_satellite_v2_status` |
| satellite_v2 | GET | `/api/satellite-v2/legend` | `get_satellite_v2_legend` |
| satellite_v2 | GET | `/api/satellite-v2/tile/{z}/{x}/{y}` | `get_satellite_v2_tile` |

Route split result:

- `routes/core.py`: status, progress, page serving helpers.
- `routes/overlays.py`: world/US boundaries, overlay latest/frames.
- `routes/alerts.py`: alerts endpoint and compatibility polygons endpoint.
- `routes/spc.py`, `routes/drought.py`, `routes/surface.py`, `routes/mrms.py`,
  `routes/rtma.py`, `routes/archive.py`, `routes/radar.py`, `routes/tropical.py`,
  `routes/satellite_v2.py`.

## Python Import Coupling

AST scan summary:

- Python files scanned: 70.
- Local roots found: `alerts`, `config`, `lib`, `main`, `mrms`, `radar`,
  `routes`, `rtma`, `satellite_v2`, `spc`, `surface`, `workers`.
- Most imported local roots: `config` (66), `workers` (63),
  `satellite_v2` (23), `lib` (22), `mrms` (13), `rtma` (11).

Root-level coupling:

| Importer root | Local dependencies |
| --- | --- |
| `main` | `workers`, `config`, `mrms`, `rtma`, `lib`, `radar`, `spc`, `alerts`, `surface`, `satellite_v2`, `routes` |
| `workers` | `workers`, `config`, `rtma`, `mrms`, `satellite_v2`, `surface`, `lib`, `alerts`, `main`, `radar`, `spc` |
| `satellite_v2` | `satellite_v2`, `config`, `workers` |
| `radar` | `lib`, `config`, `alerts` |
| `mrms` | `config`, `lib` |
| `spc` | `lib`, `config` |
| `surface` | `lib`, `config` |
| `rtma` | `config`, `mrms` |
| `alerts` | `config`, `lib`, `alerts` |

Important coupling risk resolved during extraction:

- `workers/alerts_worker.py` now imports shared alert behavior from
  `services.alerts_service` instead of importing `main`.

Refactor implication:

- `main.py` is now composition/orchestration only.
- Route modules should import service/helper modules, not workers where possible.
- Workers and routes should share service/cache modules, avoiding worker -> app
  and service -> route dependencies.

## Frontend Wiring, Excluding UI Layout

HTML asset wiring:

- `weather.html` links `css/shared.css`, Leaflet CSS, Font Awesome CSS, and
  favicon.
- `weather.html` loads Leaflet, leaflet collision plugin, topojson-client,
  tz-lookup, `js/shared.js`, `js/radar-site-locations.js`, and `js/weather.js`.
- `index.html` links `css/shared.css`.

API consumer counts:

- `js/weather.js`: 75 `fetch(` calls.
- `js/shared.js`: 3 `fetch(` calls.
- `js/satellite.js`: 1 `fetch(` call.
- `index.html`: 1 `fetch(` call.

Endpoint references detected from frontend:

- Overlay: `/api/overlay/latest`, `/api/overlay/frames`,
  `/api/overlay/us-boundaries`, `/api/overlay/world-borders`.
- Alerts/SPC/drought/surface/MRMS/RTMA:
  `/api/data/alerts`, `/api/data/spc`, `/api/data/spc/reports`,
  `/api/data/spc/active`, `/api/data/drought*`, `/api/data/surface`,
  `/api/data/surface-gradient`, `/api/data/mrms`, `/api/mrms/set-product`,
  `/api/data/rtma*`.
- Radar: `/api/radar/tiles/*`, `/api/radar/tiles/freshness`,
  `/api/radar/colortable`, `/api/radar/status`, `/api/radar/live/*`.
- Satellite v2: `/api/satellite-v2/catalog`, `/api/satellite-v2/status`,
  `/api/satellite-v2/legend`, `/api/satellite-v2/tile/{z}/{x}/{y}`.
- Tropical: `/api/tropical/*`.
- Archive/progress: `/api/archive/*`, `/api/archive/result`,
  `/api/progress/{task_id}`.

Potential stale frontend/backend mismatch:

- `js/shared.js` references `/api/alerts/polygons`, but this route was not found
  in the current `main.py` route scan. Confirm whether this is dead legacy code
  before refactor.

## Worker, Cache, And Runtime Topology

Runtime pattern from existing docs and source:

- Default cache refresh is OS-first via Windows Task Scheduler.
- In-process APScheduler fallback is opt-in with `WX_INPROC_WORKERS=1`.
- `main.py` starts the scheduler only when fallback is enabled and shuts it down
  on app shutdown.
- `main.py` also shuts down the Satellite v2 live tile render pool.
- `workers/_freshness.py` owns `cache/.workers/*.last_run` freshness markers and
  `logs/scheduled/*.log` redirection.

Workers and CLI entrypoints found:

- Alerts: `workers/alerts_worker.py`
- SPC: `workers/spc_worker.py`
- MRMS: `workers/mrms_worker.py`, `workers/mrms_live_worker.py`,
  `workers/mrms_preload.py`
- RTMA: `workers/rtma_worker.py`, hourly/rapid wrappers, preload wrappers
- Radar live: `workers/radar_live_worker.py`
- Surface: `workers/surface_worker.py`, `workers/surface_preload.py`
- Tropical live/archive: `workers/tropical_worker.py`,
  `workers/tropical_archive_worker.py`
- Satellite v2: `satellite_v2/worker.py`, `workers/satellite_v2_*_worker.py`
- Cache cleanup: `workers/cache_cleanup_worker.py`

In-process fallback jobs from `workers/scheduler.py` include:

- alerts: 1 minute
- spc: 30 minutes
- tropical: 30 minutes
- mrms: 15 minutes
- radar live: 5 minutes
- rtma hourly: 60 minutes
- rtma rapid: 15 minutes
- surface: 30 minutes
- satellite v2 primary/meso/light/geocolor profiles: 5 to 15 minutes
- cache cleanup: 6 hours

Cache/data ownership observations:

- `services/*` now owns the route-facing cache reads/writes, render sidecars,
  archive sessions, tropical cache reads, and bounded worker fallbacks that were
  previously embedded in `main.py`.
- `satellite_v2/*` owns satellite source/cache/catalog/render/tile artifacts.
- `workers/*` own most scheduled refresh artifacts and freshness markers.
- `cache/overlays/*` is the shared overlay contract for RTMA, MRMS, and radar
  live workflows.
- `cache/tropical/*` is owned by tropical live/archive workers and read by
  tropical services/routes.
- `cache/.workers/*` is the shared freshness contract.

Refactor implication:

- Product route extraction is complete for the backend route surface.
- Routes now read through service modules rather than reaching directly into
  cache paths and worker functions throughout `main.py`.

## Documentation And Runtime Gaps

Gaps found during inventory:

- `docs/architecture.md` and `README.md` reference `tools/run_api_only.ps1`,
  `tools/run_inproc_workers.ps1`, and `tools/run_dual_mode.ps1`, but the
  `tools/` folder is empty in this checkout.
- `main.py` has a `/radar.html` route, and docs reference `radar.html` and
  `satellite.html`, but those HTML files were not found at the repository root
  during this inventory.
- `docs/architecture.md` mentions independent satellite/radar workflows that
  should be treated as planned product-page targets until those pages are
  reintroduced and verified.
- Existing docs are useful, but should be refreshed before they are treated as
  authoritative planning input.

Questions to confirm before the detailed refactor plan:

- Are missing launcher scripts intentionally untracked, deleted, or replaced?
- Which planned product page should be created first after the backend/wiring
  refactor: alerts, radar, satellite, SPC, surface, MRMS, RTMA, drought, or
  tropical?
- Is `/api/alerts/polygons` legacy/dead, or should that route be restored?
- Which caches are allowed to be regenerated during testing?
- Which OS Task Scheduler jobs currently exist outside the repo?

Cross-platform runtime decision:

- The current OS-first scheduler model should not remain the only comfortable
  runtime path.
- Add an app-managed Python worker supervisor as the default deployable runtime
  target so the dashboard can run on Windows, macOS, and Linux without requiring
  Windows Task Scheduler.
- Keep OS schedulers as optional advanced/headless deployment integrations.
- Keep API-only and one-off worker module commands available.

Current decisions for the refactor plan:

- Treat `index.html` as the main page. The root route `/` should continue to
  serve `index.html`; `weather.html` is the current weather workspace, not the
  application landing page.
- Preserve the existing `/radar.html` route during the first backend refactor
  because each product is intended to have its own page after this refactor.
- Treat `/alerts.html`, `/radar.html`, `/satellite.html`, `/spc.html`,
  `/surface.html`, `/mrms.html`, `/rtma.html`, `/drought.html`, and
  `/tropical.html` as planned product-page routes for the later UI/page split.
- Canonical product URLs should be extensionless: `/alerts`, `/radar`,
  `/satellite`, `/spc`, `/surface`, `/mrms`, `/rtma`, `/drought`, and
  `/tropical`. Legacy `.html` URLs can redirect or remain as compatibility
  routes during migration.
- Do not create or restore those product pages as part of the non-UI
  backend/wiring refactor.
- Add or preserve a compatibility endpoint for `/api/alerts/polygons` unless
  the extent-selector helpers exported from `js/shared.js` are intentionally
  retired in a separate frontend cleanup.

## Refactor Planning Conclusions

Sufficient information now exists to write a backend/wiring refactor plan with
these defaults:

- Keep endpoint URLs stable during the first refactor.
- Keep `/` mapped to `index.html`; do not promote `weather.html` to the main
  page.
- Keep product-page routing separate from API routing so the later UI split can
  add product pages without disturbing product API modules.
- Add a shared page shell and shared frontend utility layer before creating many
  product pages.
- Use the existing Tropical redesign work as the first reference shell before
  broad product-page extraction.
- After product pages are verified, perform a clean-cut cleanup from the old
  combined workspace instead of keeping duplicated product code indefinitely.
- Split `main.py` by route family using `APIRouter`.
- Introduce product service/cache modules before moving routes that currently
  depend on inline cache logic or worker fallbacks.
- Remove worker -> `main` dependency before or during alerts extraction.
- Treat `workers/_freshness.py` and the overlay cache contract as shared
  infrastructure that should not be moved casually.
- Use existing `docs/architecture.md` and `docs/patterns.md` as references, but
  correct stale entries as part of the refactor preparation.

Recommended next artifact:

- A decision-complete refactor plan that defines router boundaries, service
  boundaries, migration order, endpoint compatibility rules, and verification
  checks for each extracted product family.
- Phase-by-phase execution details now live in `docs/refactor-playbook.md`.

## Implementation-Ready Refactor Plan

Scope:

- This plan covers backend/wiring refactor only.
- It does not redesign UI, split `weather.html`, or modularize `js/weather.js`.
- It keeps current public/local endpoint URLs stable.
- It keeps `/` serving `index.html`.
- It preserves planned product-page routes separately from API routers.
- It records later UI architecture requirements: clean product URLs, shared page
  shell, shared frontend utilities, and clean-cut removal from the combined
  workspace after verification.
- For the frontend phase, Tropical is the reference UI pass and should guide the
  shared shell before other products are split out.

Why preserve `/radar.html`:

- `main.py` currently exposes `/radar.html`.
- The intended post-refactor direction is one HTML page per product.
- `radar.html` is therefore a planned product-page route even though the file is
  absent in this checkout.
- Removing the route during the backend refactor would work against the planned
  page split and would change route-table behavior for no refactor benefit.

Existing files to modify:

- `main.py`
- `workers/alerts_worker.py`
- `docs/refactor-dossier.md`
- `docs/architecture.md`
- `docs/patterns.md`
- `README.md`

New files to create:

- `app_core/__init__.py`
- `app_core/paths.py`
- `app_core/static_assets.py`
- `app_core/runtime.py`
- `app_core/progress.py`
- `app_core/http.py`
- `services/__init__.py`
- `services/alerts_service.py`
- `services/archive_service.py`
- `services/boundary_service.py`
- `services/drought_service.py`
- `services/mrms_service.py`
- `services/overlay_service.py`
- `services/radar_service.py`
- `services/rtma_service.py`
- `services/spc_service.py`
- `services/surface_service.py`
- `services/tropical_service.py`
- `routes/__init__.py`
- `routes/pages.py`
- `routes/core.py`
- `routes/alerts.py`
- `routes/archive.py`
- `routes/drought.py`
- `routes/mrms.py`
- `routes/overlays.py`
- `routes/radar.py`
- `routes/rtma.py`
- `routes/satellite_v2.py`
- `routes/spc.py`
- `routes/surface.py`
- `routes/tropical.py`

Later UI/page-split files to plan, but not create in this backend phase:

- Shared shell CSS/JS for product pages.
- Shared frontend utility modules for API, map setup, status/timestamps, layer
  lifecycle, legends, timeline/scrubber behavior, and cleanup.
- Product pages and page entry modules for alerts, radar, satellite, SPC,
  surface, MRMS, RTMA, drought, and tropical.
- Cross-platform launcher/supervisor files for app-managed workers.

Implementation sequence:

1. Extract app infrastructure:
   - Move `BASE_DIR`, `_CACHE_ROOT`, cache directory setup, `_serve_page`, and
     `CacheStaticFiles` into `app_core`.
   - Move `active_tasks` into `app_core/progress.py`.
   - Move `error_payload`, date parsing/validation, and shared response helpers
     into `app_core/http.py`.
   - Keep SSL certificate environment setup at the top of `main.py`.

2. Extract lifecycle:
   - Move startup/shutdown orchestration into `app_core/runtime.py`.
   - Preserve NODD fallback behavior.
   - Preserve APScheduler fallback behavior gated by `WX_INPROC_WORKERS`.
   - Preserve Satellite v2 live tile pool shutdown.
   - Do not make Windows Task Scheduler a hard requirement for the future
     deployable runtime; leave room for an app-managed worker supervisor.

3. Extract low-risk routers first:
   - `routes/pages.py`: `/`, `/weather.html`, `/radar.html`.
   - Leave additional product-page routes for the later UI/page split unless the
     corresponding HTML files are created in that separate phase.
   - When product pages are created later, prefer extensionless canonical routes
     such as `/radar`, with `.html` routes handled as redirects or compatibility
     aliases.
   - `routes/core.py`: `/api/status`, `/api/progress/{task_id}`.
   - Keep `routes/health.py` registered.

4. Extract alert compatibility before moving alerts route:
   - Move `_enrich_alert_features_geometry` and related geometry helpers into
     `services/alerts_service.py`.
   - Update `workers/alerts_worker.py` to import from `services.alerts_service`,
     not `main`.
   - Move `/api/data/alerts` into `routes/alerts.py`.
   - Add or preserve `/api/alerts/polygons` for `js/shared.js` selector helpers.

5. Extract product routers and services:
   - `boundary_service.py` + `routes/overlays.py`: world/US boundaries.
   - `overlay_service.py` + `routes/overlays.py`: `/api/overlay/latest` and
     `/api/overlay/frames`.
   - `surface_service.py` + `routes/surface.py`: surface current, gradient, and
     colormap behavior.
   - `mrms_service.py` + `routes/mrms.py`: MRMS product state, metadata, and
     render helpers.
   - `rtma_service.py` + `routes/rtma.py`: RTMA points/grid/current/frames.
   - `archive_service.py` + `routes/archive.py`: archive sessions, cache files,
     and archive endpoints.
   - `radar_service.py` + `routes/radar.py`: radar sites, alert tiles, status,
     and live frame endpoints.
   - `tropical_service.py` + `routes/tropical.py`: tropical live/archive cache
     reads and worker fallbacks.
   - `routes/satellite_v2.py`: thin router around existing `satellite_v2.service`.
   - `routes/spc.py` and `routes/drought.py`: move current route behavior
     unchanged, with service extraction only where it reduces direct cache logic.

6. Thin `main.py`:
   - Create the FastAPI app.
   - Register middleware.
   - Mount static assets.
   - Include all routers.
   - Register startup/shutdown events.
   - Keep uvicorn launch config.

7. Update documentation:
   - Keep `index.html` documented as the main page.
   - Keep `weather.html` documented as the current weather workspace.
   - Mark root product pages as planned migration targets, not dead code.
   - Keep notes about missing `tools/*.ps1` launchers current.

8. Later UI/page-split architecture requirements:
   - Define a shared page shell before creating product pages.
   - Define shared frontend utilities before copying product code out of
     `weather.js`.
   - Keep `weather.html` working as the combined/classic workspace until product
     pages are verified.
   - After each product page is verified, remove that product's duplicated code
     from the combined workspace and update docs/tests to make the product page
     canonical.
   - Keep API modules product-aligned so product pages consume their matching
     routers naturally.

9. Later deployability/runtime requirements:
   - Add an app-managed Python worker supervisor as the default local runtime.
   - Keep API-only mode.
   - Keep OS scheduler support optional.
   - Keep one-off worker commands for backfill and troubleshooting.

Verification plan:

- `.\.venv\Scripts\python.exe -m py_compile main.py app_core/*.py services/*.py routes/*.py workers/alerts_worker.py`
- `ruff check .`
- `.\.venv\Scripts\python.exe -c "from main import app; print(len(app.routes))"`
- Compare route paths before/after; the route set should remain stable except
  for the added compatibility route `/api/alerts/polygons`.
- Start the API and smoke-test:
  - `/`
  - `/health`
  - `/api/status`
  - `/weather.html`
  - `/radar.html` remains registered as a planned product-page route and returns
    the same missing-page behavior until the page is created separately.
  - `/api/data/alerts`
  - `/api/alerts/polygons`
  - `/api/satellite-v2/status`
  - `/api/radar/status`
- Confirm `workers.alerts_worker` can import without importing `main`.
