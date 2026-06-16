# Refactor Implementation Playbook

Generated: 2026-06-13

This playbook turns `docs/refactor-dossier.md` into execution phases that can
be handed to a lower-level model or implemented manually. Each phase should be
completed, verified, and committed before the next phase starts.

## Active Worktrees And Branches

- Main repository: `F:\Python\dashboard_2026`.
- Backend refactor worktree: `F:\Python\dashboard_2026_refactor` on
  `codex/backend-product-refactor`.
- Frontend product-page worktree: `F:\Python\dashboard_2026_frontend_pages` on
  `codex/frontend-product-pages`.
- Before editing, confirm the requested work belongs to the current worktree.
- Use the frontend product-page worktree for dashboard shell, product page, and
  `weather.html` / `js/weather.js` UI changes.
- Use the backend refactor worktree for FastAPI route/service/module changes.

## Global Rules

- Do not modify `weather.html`, `js/weather.js`, cache data, imagery, logs, or
  generated products during Phases 1-10.
- Keep `/` serving `index.html`.
- Keep `/weather.html` working as the combined weather workspace.
- Keep `/radar.html` registered during the backend refactor.
- Do not create product pages during Phases 1-10.
- Keep existing API paths stable.
- Add `/api/alerts/polygons` as a compatibility endpoint because exported
  helpers in `js/shared.js` reference it.
- Do not delete old functions until the phase that moved them has passed route
  parity, import checks, and smoke tests.
- If a phase fails import/startup checks, stop and fix that phase before
  continuing.

## Verification Environment

Install runtime dependencies first:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

For linting and in-process FastAPI/Starlette smoke tests, install dev
dependencies too:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

`httpx2` is a dev/test dependency, not a runtime app dependency. Without it,
`fastapi.testclient.TestClient` and `starlette.testclient.TestClient` cannot be
used in this environment; run localhost smoke checks against a started Uvicorn
server instead.

## Phase 1: Baseline Capture

Goal: record current behavior before moving code.

Files to create:

- `docs/refactor-baseline.md`

Files to read only:

- `main.py`
- `routes/health.py`
- `js/shared.js`
- `weather.html`
- `README.md`
- `docs/refactor-dossier.md`

Steps:

1. Record current git status.
2. Capture current route declarations from `main.py` and `routes/health.py`.
3. Capture current static mounts from `main.py`.
4. Capture current root HTML files.
5. Capture current frontend endpoint references from `js/shared.js` and
   `js/weather.js`.
6. Record known gaps:
   - `tools/` is empty.
   - `radar.html` and `satellite.html` are absent.
   - `/api/alerts/polygons` is referenced by `js/shared.js` but not currently
     implemented.

Suggested commands:

```powershell
git status --short
rg -n "@(app|router)\.(get|post|put|delete|patch|head)|app\.mount|include_router|on_event\(" main.py routes
Get-ChildItem -Path . -Filter *.html | Select-Object Name,Length
rg -n "fetch\(|apiUrl\(|/api/" js weather.html index.html
```

Verification:

- `docs/refactor-baseline.md` exists.
- Baseline lists all current route paths before any move.
- No application files changed.

Stop if:

- Git status shows unexpected application-code changes before the refactor
  begins.

## Phase 2: App Core Extraction

Goal: move shared app infrastructure out of `main.py` without changing routes.

Files to create:

- `app_core/__init__.py`
- `app_core/paths.py`
- `app_core/static_assets.py`
- `app_core/progress.py`
- `app_core/http.py`

Files to modify:

- `main.py`

Move these symbols from `main.py`:

- `BASE_DIR` -> `app_core.paths.BASE_DIR`
- `_CACHE_ROOT` -> `app_core.paths.CACHE_ROOT`
- Cache directory creation -> `app_core.paths.ensure_runtime_dirs`
- `CacheStaticFiles` -> `app_core.static_assets.CacheStaticFiles`
- `_serve_page` -> `app_core.static_assets.serve_page`
- `active_tasks` -> `app_core.progress.active_tasks`
- `error_payload` -> `app_core.http.error_payload`
- `parse_utc_datetime` -> `app_core.http.parse_utc_datetime`
- `validate_archive_range` -> `app_core.http.validate_archive_range`
- `success_payload` -> `app_core.http.success_payload`
- `attach_mode_and_source` -> `app_core.http.attach_mode_and_source`

Leave these in `main.py` during this phase:

- FastAPI app creation.
- Middleware registration.
- Route declarations.
- Startup/shutdown event handlers.
- All product route handlers.
- SSL certificate environment setup at top of file.

Implementation details:

- `app_core.paths` should expose `BASE_DIR: str`, `CACHE_ROOT: str`, and
  `ensure_runtime_dirs() -> None`.
- `ensure_runtime_dirs()` should create the same cache subdirectories currently
  created by `main.py`.
- `app_core.static_assets.serve_page(filename: str)` should preserve current
  missing-page behavior by raising `HTTPException(404, detail=...)`.
- Update `main.py` imports to use the new modules.
- Call `ensure_runtime_dirs()` before mounting `/cache`.

Verification:

```powershell
.\.venv\Scripts\python.exe -m py_compile main.py app_core\*.py
.\.venv\Scripts\python.exe -c "from main import app; print(len(app.routes))"
```

Smoke checks after starting app:

- `/`
- `/weather.html`
- `/radar.html`
- `/api/status`
- `/health`

Stop if:

- `from main import app` fails.
- `/radar.html` behavior changes from current missing-page behavior.
- Any route path disappears.

## Phase 3: Lifecycle Extraction

Goal: move startup/shutdown orchestration out of `main.py`.

Files to create:

- `app_core/runtime.py`

Files to modify:

- `main.py`

Move these responsibilities:

- Optional NODD radar module initialization.
- Scheduler import and startup.
- Cache freshness check.
- Startup summary printing.
- Shutdown of scheduler.
- Shutdown of Satellite v2 live tile pool.

Keep these behaviors unchanged:

- SSL cert setup remains at top of `main.py`.
- Py-ART stderr suppression around `radar_utils` import remains functionally
  equivalent.
- `WX_INPROC_WORKERS` behavior remains controlled by existing
  `workers.scheduler` logic.
- Satellite v2 shutdown still calls `satellite_v2_service.shutdown_live_tile_pool`.

Suggested API:

```python
from app_core.runtime import initialize_runtime, shutdown_runtime
```

`main.py` should use:

```python
@app.on_event("startup")
def _run_startup_sequence():
    initialize_runtime()

@app.on_event("shutdown")
def _stop_background_workers():
    shutdown_runtime()
```

Verification:

```powershell
.\.venv\Scripts\python.exe -m py_compile main.py app_core\*.py
.\.venv\Scripts\python.exe -c "from main import app; print(len(app.routes))"
```

Start app once and confirm startup summary still prints.

Stop if:

- Startup summary disappears unexpectedly.
- Scheduler import errors become fatal.
- Satellite shutdown import creates a startup failure.

## Phase 4: Pages And Core Routers

Goal: move low-risk pages/core routes out of `main.py`.

Files to create:

- `routes/__init__.py`
- `routes/pages.py`
- `routes/core.py`

Files to modify:

- `main.py`

Move these route handlers:

- `/` -> `routes.pages`
- `/weather.html` -> `routes.pages`
- `/radar.html` -> `routes.pages`
- `/api/status` -> `routes.core`
- `/api/progress/{task_id}` -> `routes.core`

Keep:

- `routes/health.py` as-is.
- `read_index_page()` behavior should be resolved. It is currently not
  decorated as a route and can remain omitted unless a current route uses it.

Implementation details:

- `routes.pages.router = APIRouter()`.
- `routes.core.router = APIRouter()`.
- `routes.pages` should import `serve_page` from `app_core.static_assets`.
- `routes.core` should import `active_tasks` from `app_core.progress`.
- `main.py` should include the new routers.

Verification:

```powershell
.\.venv\Scripts\python.exe -m py_compile main.py app_core\*.py routes\*.py
.\.venv\Scripts\python.exe -c "from main import app; print(sorted([getattr(r, 'path', '') for r in app.routes]))"
```

Smoke:

- `/`
- `/weather.html`
- `/radar.html`
- `/api/status`
- `/api/progress/test`
- `/health`

Stop if:

- Route paths change.
- Root `/` no longer serves `index.html`.

## Phase 5: Alerts Service And Compatibility Route

Goal: remove `workers/alerts_worker.py -> main` dependency and add the missing
selector compatibility endpoint.

Files to create:

- `services/__init__.py`
- `services/alerts_service.py`
- `routes/alerts.py`

Files to modify:

- `main.py`
- `workers/alerts_worker.py`

Move these symbols from `main.py`:

- `_enrich_alert_features_geometry`
- Any helper used only by alert enrichment, including alert geometry cache
  support.

Move or wrap route behavior:

- `/api/data/alerts`
- `/api/alerts/polygons`

Implementation details:

- `workers/alerts_worker.py` must import `_enrich_alert_features_geometry` from
  `services.alerts_service`, not `main`.
- `/api/data/alerts` should preserve the existing response shape.
- `/api/alerts/polygons` should support the selector helper contract in
  `js/shared.js`:
  - Query params: `region`, `hazard`, optional `wfo`.
  - Response should include `feature_collection`.
  - It may reuse the same alert cache/filtering logic as `/api/data/alerts`.
- Do not modify `js/shared.js` in this phase.

Verification:

```powershell
.\.venv\Scripts\python.exe -m py_compile main.py services\*.py routes\*.py workers\alerts_worker.py
.\.venv\Scripts\python.exe -c "import workers.alerts_worker; print('alerts worker import ok')"
.\.venv\Scripts\python.exe -c "from main import app; print(len(app.routes))"
```

Smoke:

- `/api/data/alerts`
- `/api/alerts/polygons?region=CONUS&hazard=All%20Alerts`

Stop if:

- Importing `workers.alerts_worker` imports `main`.
- Alert response shape changes unexpectedly.

## Phase 6: Low-Coupling Product Routers

Goal: move simpler product route groups before high-state services.

Files to create:

- `routes/spc.py`
- `routes/drought.py`
- `routes/satellite_v2.py`
- `services/spc_service.py`
- `services/drought_service.py`

Files to modify:

- `main.py`

Move these routes:

- `/api/data/spc`
- `/api/data/spc/reports`
- `/api/data/spc/active`
- `/api/data/drought/dates`
- `/api/data/drought`
- `/api/data/drought/state-stats`
- `/api/satellite-v2/catalog`
- `/api/satellite-v2/status`
- `/api/satellite-v2/legend`
- `/api/satellite-v2/tile/{z}/{x}/{y}`

Move these helper(s):

- `_satellite_v2_tile_source_label` -> `routes/satellite_v2.py` or a service
  helper.

Implementation details:

- Satellite v2 routes can stay thin and call existing `satellite_v2.service`.
- Drought cache logic should move into `services.drought_service`.
- SPC cache/fallback behavior should move into `services.spc_service` if it
  reduces route complexity; otherwise keep a thin route wrapper with unchanged
  logic.

Verification:

```powershell
.\.venv\Scripts\python.exe -m py_compile main.py services\*.py routes\*.py
.\.venv\Scripts\python.exe -c "from main import app; print(len(app.routes))"
```

Smoke:

- `/api/data/spc?day=1&hazard=cat`
- `/api/data/spc/reports?day=today`
- `/api/data/drought/dates`
- `/api/satellite-v2/status`
- `/api/satellite-v2/legend`

Stop if:

- Satellite v2 tile route loses cache-control/source-label behavior.
- Drought endpoints stop returning cached data when cache files exist.

## Phase 7: Boundary And Overlay Services

Goal: move shared overlay/boundary infrastructure.

Files to create:

- `services/boundary_service.py`
- `services/overlay_service.py`
- `routes/overlays.py`

Files to modify:

- `main.py`

Move these routes:

- `/api/overlay/world-borders`
- `/api/overlay/us-boundaries`
- `/api/overlay/latest`
- `/api/overlay/frames`

Move these helpers:

- `_iter_line_geometries`
- `_build_world_borders_geojson`
- `_get_world_borders_geojson`
- `_build_us_boundaries_geojson`
- `_get_us_boundaries_geojson`
- `_spawn_live_render_thread`
- overlay latest/frames helper logic currently embedded in route handlers.

Implementation details:

- Keep `cache/overlays` contract unchanged.
- Keep RTMA/MRMS/radar overlay family behavior unchanged.
- If `get_overlay_latest` currently calls `get_data_rtma`, replace that direct
  route-call coupling with a service call.

Verification:

```powershell
.\.venv\Scripts\python.exe -m py_compile main.py services\*.py routes\*.py
```

Smoke:

- `/api/overlay/world-borders`
- `/api/overlay/us-boundaries`
- `/api/overlay/latest?family=rtma&region=CONUS&stream=rtma_hourly&product=temperature`
- `/api/overlay/frames?family=rtma&region=CONUS&stream=rtma_hourly&product=temperature`

Stop if:

- Overlay response shape changes.
- Boundary cache files are written to a different location.

## Phase 8: Surface, MRMS, And RTMA Services

Goal: move route groups with cache/render/frame-lock behavior.

Files to create:

- `services/surface_service.py`
- `services/mrms_service.py`
- `services/rtma_service.py`
- `routes/surface.py`
- `routes/mrms.py`
- `routes/rtma.py`

Files to modify:

- `main.py`

Move surface routes:

- `/api/data/surface`
- `/api/data/surface-gradient`
- `/api/data/colormap`

Move surface helpers:

- `_interpolate_color`
- `_build_surface_stations`
- `_refresh_surface_cache_async`
- `_kickoff_surface_refresh_if_needed`
- `_safe_float`
- `_surface_source_timestamp_iso`
- surface product constants and refresh state.

Move MRMS routes:

- `/api/mrms/set-product`
- `/api/data/mrms`

Move MRMS helpers:

- `_load_mrms_render_meta`
- `_write_mrms_render_meta`
- `_normalize_mrms_data_timestamp`
- `_build_mrms_meta_from_grib`
- `_render_mrms_png`
- `_active_mrms_product`

Move RTMA routes:

- `/api/data/rtma/points`
- `/api/data/rtma/grid`
- `/api/data/rtma`
- `/api/data/rtma/frames`

Implementation details:

- Keep existing cache paths and image URLs stable.
- Preserve stale-while-revalidate behavior for surface data.
- Preserve MRMS cold-cache worker fallback behavior.
- Preserve RTMA `source_data_key` frame-lock behavior.

Verification:

```powershell
.\.venv\Scripts\python.exe -m py_compile main.py services\*.py routes\*.py
```

Smoke:

- `/api/data/surface?region=NC&product=temperature`
- `/api/data/surface-gradient?region=CONUS&product=temperature`
- `/api/data/colormap?product=temperature`
- `/api/data/mrms?product=Refl_BaseQC`
- `/api/data/rtma?region=CONUS&stream=rtma_hourly&product=temperature`
- `/api/data/rtma/points?region=CONUS&stream=rtma_hourly&product=temperature`

Stop if:

- Surface timestamp/source fields change.
- MRMS image URL or bounds shape changes.
- RTMA points are no longer frame-locked.

## Phase 9: Archive Services

Goal: move archive session state and archive endpoints.

Files to create:

- `services/archive_service.py`
- `routes/archive.py`

Files to modify:

- `main.py`

Move routes:

- `/api/archive/mrms`
- `/api/archive/result`
- `/api/archive/alerts`
- `/api/archive/surface`
- `/api/archive/spc`

Move helpers/state:

- `_ARCHIVE_ROOT`
- `_ARCHIVE_SESSION_TTL_HOURS`
- `_ARCHIVE_MAX_SESSIONS`
- `_archive_sessions`
- `_archive_lock`
- `_archive_session_key`
- `_cleanup_archive_sessions`
- `_evict_session`
- `_new_archive_session`
- `_parse_archive_dt`
- `_archive_cache_path`
- `_read_archive_cache`
- `_write_archive_cache`
- `_fetch_iem_alerts_range`
- `_SURFACE_ARCHIVE_PRODUCT_MAP`

Implementation details:

- Archive session state should live in `services.archive_service`.
- Preserve session id behavior and archive result response shape.
- Preserve archive cache paths.
- Preserve max range validation.

Verification:

```powershell
.\.venv\Scripts\python.exe -m py_compile main.py services\*.py routes\*.py
```

Smoke:

- `/api/archive/result?session_id=missing`
- Archive endpoints with invalid single-date params should still return 400.

Stop if:

- Existing archive session polling contract changes.
- Archive cache files move.

## Phase 10: Radar And Tropical Services

Goal: move the remaining stateful route groups.

Files to create:

- `services/radar_service.py`
- `services/tropical_service.py`
- `routes/radar.py`
- `routes/tropical.py`

Files to modify:

- `main.py`

Move radar routes:

- `/api/radar/sites`
- `/api/radar/site-locations`
- `/api/radar/colortable`
- `/api/radar/tiles/{z}/{x}/{y}`
- `HEAD /api/radar/tiles/{z}/{x}/{y}`
- `/api/radar/tiles/freshness`
- `/api/radar/status`
- `/api/radar/live/sites`
- `/api/radar/live/latest`
- `/api/radar/live/frames`

Move radar helpers/state:

- `normalize_radar_site_id`
- `_radar_live_catalog`
- `_radar_live_sites`
- `_fetch_nws_radar_status`
- `_radar_live_site_supported`
- `_radar_live_product_supported`
- `_radar_live_fallback_lock`
- `_radar_live_render_on_demand`
- `_spawn_live_render_thread` if not already moved to overlay service.
- `_radar_live_render_in_background`
- `_radar_live_is_configured`
- `_radar_live_latest_meta_dt`
- `_radar_live_filter_stale_latest_meta`
- `_RADAR_LIVE_FALLBACK_LOCKS`
- `_NWS_RADAR_STATUS_CACHE*`
- `_LIVE_RENDER_BG_*`
- `_RADAR_COLORTABLE_PRODUCTS`
- `_RADAR_FRAME_LAYERS`

Move tropical routes:

- `/api/tropical/storms`
- `/api/tropical/summary`
- `/api/tropical/basin/{basin_id}/feeds`
- `/api/tropical/storm/{storm_id}`
- `/api/tropical/archive/catalog`
- `/api/tropical/archive/storm/{atcf_id}`
- `/api/tropical/archive/storm/{atcf_id}/advisory/{step}`

Move tropical helpers/state:

- `_run_tropical_worker_once`
- `_run_tropical_archive_worker_once`
- `_read_tropical_archive_cache`
- `_read_tropical_cache`
- `_fetch_text_url`
- `_tropical_wallet`
- `_tropical_xml_basin_code`
- `_extract_xml_item_text`
- `_parse_tropical_coord`
- `_tropical_product_url`
- `_TROPICAL_*` constants.

Leave uncalled legacy tropical helpers for a separate cleanup phase unless tests
prove they are required.

Verification:

```powershell
.\.venv\Scripts\python.exe -m py_compile main.py services\*.py routes\*.py
```

Smoke:

- `/api/radar/status`
- `/api/radar/live/sites`
- `/api/radar/live/latest?site=KMHX&product=L3_N0B`
- `/api/tropical/storms?basin=WORLD`
- `/api/tropical/summary`
- `/api/tropical/archive/catalog`

Stop if:

- Radar fallback locks are no longer per site/product.
- Tropical endpoints trigger network calls when fresh cache exists.

## Phase 11: Route Parity And Main.py Cleanup

Goal: confirm the backend split is behavior-preserving and `main.py` is thin.

Files to modify:

- `main.py`
- `docs/refactor-dossier.md`
- `docs/architecture.md`

Steps:

1. Remove route/helper code from `main.py` only after each route group exists in
   a router/service module and passes smoke tests.
2. Leave `main.py` responsible for:
   - SSL cert setup.
   - FastAPI app creation.
   - Middleware.
   - Static mounts.
   - Router registration.
   - Startup/shutdown event registration.
   - Uvicorn launch config.
3. Generate route list before/after and compare.
4. Update docs with actual final module map.

Verification:

```powershell
.\.venv\Scripts\python.exe -m py_compile main.py app_core\*.py services\*.py routes\*.py workers\alerts_worker.py
ruff check .
.\.venv\Scripts\python.exe -c "from main import app; print('\\n'.join(sorted(getattr(r, 'path', '') for r in app.routes)))"
```

Stop if:

- `main.py` still contains product route handlers.
- Route parity fails unexpectedly.

## Phase 12: Worker Supervisor Design

Goal: design the cross-platform worker supervisor before implementation.

Files to create:

- `docs/worker-supervisor-plan.md`

Do not implement supervisor code in this phase.

Design decisions to record:

- Default mode: API plus app-managed workers.
- API-only mode flag/env var.
- Optional OS scheduler mode.
- Worker interval table.
- Freshness marker reuse.
- Duplicate-run prevention.
- Logging path.
- Shutdown behavior.
- Error reporting in `/api/status`.
- Windows/macOS/Linux launcher expectations.

Verification:

- Plan names every worker and interval.
- Plan explains how to avoid duplicate work with OS scheduler.
- Plan defines how a non-technical user starts the app.

## Phase 13: Shared Frontend Shell And Utility Design

Goal: design the map-first dashboard shell before creating product pages, then
use the Tropical tab redesign as the reference product pattern inside that
shell.

Files to create:

- `docs/product-page-shell-plan.md`

Do not modify frontend code in this phase.

Current direction:

- Replace the current floating/collapsible sidebars with a fixed dashboard grid:
  left controls dock, bounded center map, right inspector dock, and docked
  timeline/colorbar rows.
- Tropical is the first product reference pass after the grid shell, not the
  last product.
- Refine and verify Tropical inside the existing combined `weather.html`
  workspace after the grid shell is stable.
- After the Tropical layout is accepted, use its hub/map/inspector pattern to
  guide standalone product pages.
- The recovered Tropical plan is still valid as design source material, but its
  old backend anchors must be updated for the route/service split:
  `routes/tropical.py`, `services/tropical_service.py`, and
  `workers/tropical_worker.py` now own Tropical backend behavior.

Design decisions to record:

- Shared shell regions:
  - top nav/status
  - map canvas
  - fixed left controls dock
  - fixed right inspector/legend dock
  - docked bottom timeline/colorbar rows
  - refresh/error/status area
- Shared utilities:
  - API client
  - map factory
  - page init
  - timestamp/status helpers
  - layer lifecycle helpers
  - cleanup/timer registry
  - legend helpers
  - timeline/scrubber controller
- Canonical route policy:
  - `/radar`, `/satellite`, etc.
  - `.html` routes as redirects or compatibility routes.
- Product page creation order.

Verification:

- Plan prevents copy-pasting the full `weather.js` state model.
- Plan replaces the collapsible sidebar assumption with a fixed dashboard grid.
- Plan defines which code remains shared and which code belongs to each product.
- Plan identifies what is Tropical-specific versus reusable for other products.

## Phase 14: Product Page Split

Goal: create product pages one at a time after backend split and shell design.

Do not start this phase until Phases 1-13 are complete.

Recommended order:

1. Fixed dashboard grid shell in the combined workspace.
2. Tropical reference pass in the combined workspace.
3. `/tropical` standalone page candidate, if the reference layout is accepted.
4. `/alerts`
5. `/spc`
6. `/surface`
7. `/drought`
8. `/satellite`
9. `/radar`
10. `/mrms`
11. `/rtma`

Current frontend shell status:

- MRMS and SPC left-dock subtabs are implemented and visually accepted in
  `F:\Python\dashboard_2026_frontend_pages`.
- Satellite subtabs are implemented for platform and sector selection while
  preserving the existing Channel Product dropdown. Satellite left-sidebar
  Current/Animate buttons were removed because the dashboard scrubber auto-loads
  and owns playback.
- RTMA remains in the compact grouped left-dock layout; avoid adding subtabs to
  compact products unless the controls become materially denser.
- Dense-product subtabs are complete for this pass: MRMS, SPC, and Satellite.
- Tropical reference pass is accepted in the fixed dashboard shell:
  the left hub uses basin selection plus Active, Outlooks, and Archive tabs.
  Outlooks is the default on page load. The right System Inspector remains the
  selected storm detail surface and stays hidden until an active or archived
  storm is selected.
- The right Archive tab is removed for Tropical; archive browsing belongs in the
  left Tropical tab set while Styling/System remain right-side concerns.
- Phase 14 `/tropical` route-level candidate is accepted for this pass. It
  serves the accepted dashboard shell in Tropical-only mode, keeps
  `/weather.html` unchanged for the combined workspace, and avoids duplicating
  the full `weather.js` state model before shared utilities are extracted.
- Phase 14 route-level candidates for `/alerts`, `/spc`, `/surface`,
  `/drought`, `/satellite`, `/radar`, `/mrms`, and `/rtma` are accepted for
  this pass. They serve the accepted dashboard shell in product-only mode and
  keep `/weather.html` unchanged for the combined workspace. `/surface` maps
  to the existing `current` product mode.
- SPC standalone startup has one important guard: reset SPC controls and run
  `_updateSpcReportFilterState()` before the initial `refreshActiveLayers()`
  call. Without that ordering, the first Day 1 Categorical response can be
  rejected as stale and the layer only appears after toggling the Categorical
  checkbox.

Per-product steps:

1. Create canonical route.
2. Create page HTML or template.
3. Create product JS entry module.
4. Use shared shell and utilities.
5. Smoke-test product API calls.
6. Verify map/layers render.
7. Keep `weather.html` behavior unchanged until the product page is verified.

Stop if:

- Product page duplicates large sections of `weather.js` without extracting a
  shared utility first.
- Product-page work starts before the fixed dashboard grid is accepted.
- Standalone page work starts before the Tropical reference shell is accepted.

## Phase 15: Clean Cut

Goal: remove duplicated legacy behavior after product pages are verified.

Status: ready to plan next. The route-level split candidates are working and
accepted, but they still share `weather.html` and `js/weather.js`. Do not begin
removing combined-workspace product code until the user confirms the Phase 15
clean-cut strategy.

Phase 15A prep has started with a minimal frontend bootstrap extraction:
`js/product-page-shell.js` owns canonical product route detection and
standalone product checkbox/title setup, and `js/alerts-page.js` registers the
Alerts standalone entry metadata. `/alerts` still uses the accepted
`weather.html` shell and `js/weather.js` behavior for this step; no combined
workspace Alerts code has been removed yet.

Phase 15B prep now serves `/alerts` through a generated product shell response
instead of a static `weather.html` file response. `serve_product_shell_page()`
injects product-page metadata into the shared shell without copying
`weather.html`, and `js/alerts-page.js` owns the first Alerts page-controller
helpers for category defaults, master checkbox sync, checked-category reads,
warning-filter visibility, and active-warning panel rendering/wiring.

Phase 15C prep added `js/product-app-context.js`, a small registry for product
engine dependencies. `js/weather.js` registers the Alerts app context before
init, exposing the Leaflet map, API URL helper, status/legend setters,
timestamp/reliability setters, archive/scrubber guards, and shared formatting
hooks for the extracted Alerts modules.

`js/alerts-engine.js` now owns the context-backed Alerts live-response
eligibility check, live Alerts loading orchestration, in-memory category
refiltering, display-geometry refresh, Leaflet alert style/layer construction,
and archive Alerts loading/frame slicing. `js/weather.js` keeps inline fallback
implementations for combined-workspace safety and still injects popup/detail
presentation and new-alert notification banners because those flows share
broader dashboard/map interaction state.

Files to modify:

- `weather.html`
- `js/weather.js`
- Shared frontend utility files created in Phase 13/14.
- Relevant docs.

Rules:

- Remove one product's old combined-workspace code only after its standalone
  page passes smoke and visual checks.
- Remove stale exported JS helpers only after search confirms no references.
- Convert `.html` compatibility routes to redirects only after canonical routes
  are stable.
- Keep API paths stable unless a separate API cleanup plan exists.

Verification:

- Product page still works.
- Combined workspace either still works for remaining products or is formally
  retired.
- No stale references to removed JS symbols.
- Docs identify canonical product URLs.

## Post-Refactor: Archive Mode Redesign

Goal: rethink archive mode as a product workflow after the structural refactor
is complete.

Current decision:

- Leave existing non-tropical archive endpoints in place during this refactor.
- Do not redesign, remove, or build frontend archive mode as part of the current
  backend/frontend split.
- Treat non-tropical archive workflows as dormant backend capabilities unless a
  current page explicitly depends on them.
- Revisit archive mode per product page after the refactor, potentially using
  Tropical archive behavior as a reference guide.

Future archive work should decide, product by product, whether to:

- keep and modernize the existing endpoint behavior,
- replace it with a newer archive API and UI workflow,
- or remove/archive-disable unsupported legacy behavior.
