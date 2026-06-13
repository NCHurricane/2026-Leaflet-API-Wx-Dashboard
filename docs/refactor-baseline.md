# Refactor Baseline

Generated: 2026-06-13

This baseline records the current backend and frontend wiring before any Phase 2
application code is moved. It is intended to be used for route parity checks
during the backend/product refactor.

## Git Status

Command:

```powershell
git status --short --branch
```

Result:

```text
## codex/backend-product-refactor
```

Notes:

- Worktree was clean before Phase 1 documentation was created.
- Git emitted a local warning about unreadable global ignore config:
  `C:\Users\ncrac\.config\git\ignore`.

## Route And Static Mount Scan

Source scan command:

```powershell
rg -n "@(app|router)\.(get|post|put|delete|patch|head)|app\.mount|include_router|on_event\(" main.py routes
```

Current router registration and lifecycle hooks:

| File | Line | Item |
| --- | ---: | --- |
| `main.py` | 75 | `app.include_router(health_router)` |
| `main.py` | 171 | `@app.on_event("startup")` |
| `main.py` | 177 | `@app.on_event("shutdown")` |

Current static mounts:

| Mount | Source |
| --- | --- |
| `/sounds` | `StaticFiles(directory="sounds")` |
| `/cache` | `CacheStaticFiles(directory=_CACHE_ROOT)` |
| `/css` | `StaticFiles(directory=os.path.join(BASE_DIR, "css"))` |
| `/js` | `StaticFiles(directory=os.path.join(BASE_DIR, "js"))` |
| `/data` | `StaticFiles(directory=os.path.join(BASE_DIR, "data"))` |
| `/img` | `StaticFiles(directory=os.path.join(BASE_DIR, "img"))` |
| `/fonts` | `StaticFiles(directory=os.path.join(BASE_DIR, "fonts"))` |

## FastAPI Route Table

Route table captured with:

```powershell
.\.venv\Scripts\python.exe -c "from main import app; print(...)"
```

The import prints the Py-ART banner in this environment before route output.

| Methods | Path | Handler |
| --- | --- | --- |
| `GET,HEAD` | `/openapi.json` | `openapi` |
| `GET,HEAD` | `/docs` | `swagger_ui_html` |
| `GET,HEAD` | `/docs/oauth2-redirect` | `swagger_ui_redirect` |
| `GET,HEAD` | `/redoc` | `redoc_html` |
| `GET` | `/health` | `health` |
| static | `/sounds` | `sounds` |
| static | `/cache` | `cache` |
| static | `/css` | `css` |
| static | `/js` | `js` |
| static | `/data` | `data` |
| static | `/img` | `img` |
| static | `/fonts` | `fonts` |
| `GET` | `/` | `read_root` |
| `GET` | `/api/status` | `read_status` |
| `GET` | `/api/overlay/world-borders` | `get_world_borders` |
| `GET` | `/api/overlay/us-boundaries` | `get_us_boundaries` |
| `GET` | `/api/data/alerts` | `get_data_alerts` |
| `GET` | `/api/data/spc` | `get_data_spc` |
| `GET` | `/api/data/spc/reports` | `get_data_spc_reports` |
| `GET` | `/api/data/spc/active` | `get_data_spc_active` |
| `GET` | `/api/data/drought/dates` | `get_drought_dates` |
| `GET` | `/api/data/drought` | `get_drought_geojson` |
| `GET` | `/api/data/drought/state-stats` | `get_drought_state_stats` |
| `GET` | `/api/data/surface` | `get_data_surface` |
| `GET` | `/api/data/surface-gradient` | `get_data_surface_gradient` |
| `GET` | `/api/data/colormap` | `get_colormap` |
| `GET` | `/api/mrms/set-product` | `mrms_set_product` |
| `GET` | `/api/data/mrms` | `get_data_mrms` |
| `GET` | `/api/data/rtma/points` | `get_data_rtma_points` |
| `GET` | `/api/data/rtma/grid` | `get_data_rtma_grid` |
| `GET` | `/api/data/rtma` | `get_data_rtma` |
| `GET` | `/api/overlay/latest` | `get_overlay_latest` |
| `GET` | `/api/overlay/frames` | `get_overlay_frames` |
| `GET` | `/api/data/rtma/frames` | `get_data_rtma_frames` |
| `GET` | `/api/archive/mrms` | `archive_mrms` |
| `GET` | `/api/archive/result` | `archive_result` |
| `GET` | `/api/archive/alerts` | `archive_alerts` |
| `GET` | `/api/archive/surface` | `archive_surface` |
| `GET` | `/api/archive/spc` | `archive_spc` |
| `GET` | `/radar.html` | `read_radar_page` |
| `GET` | `/weather.html` | `read_weather_page` |
| `GET` | `/api/progress/{task_id}` | `get_task_progress` |
| `GET` | `/api/radar/sites` | `get_radar_sites` |
| `GET` | `/api/radar/site-locations` | `get_radar_site_locations` |
| `GET` | `/api/tropical/storms` | `get_tropical_storms` |
| `GET` | `/api/tropical/summary` | `get_tropical_summary` |
| `GET` | `/api/tropical/basin/{basin_id}/feeds` | `get_tropical_basin_feeds` |
| `GET` | `/api/tropical/storm/{storm_id}` | `get_tropical_storm` |
| `GET` | `/api/tropical/archive/catalog` | `get_tropical_archive_catalog` |
| `GET` | `/api/tropical/archive/storm/{atcf_id}` | `get_tropical_archive_storm` |
| `GET` | `/api/tropical/archive/storm/{atcf_id}/advisory/{step}` | `get_tropical_archive_advisory` |
| `GET` | `/api/radar/colortable` | `get_radar_colortable` |
| `GET` | `/api/radar/tiles/{z}/{x}/{y}` | `get_radar_alert_tiles` |
| `HEAD` | `/api/radar/tiles/{z}/{x}/{y}` | `head_radar_alert_tiles` |
| `GET` | `/api/radar/tiles/freshness` | `get_radar_tiles_freshness` |
| `GET` | `/api/radar/status` | `get_radar_status` |
| `GET` | `/api/radar/live/sites` | `get_radar_live_sites` |
| `GET` | `/api/radar/live/latest` | `get_radar_live_latest` |
| `GET` | `/api/radar/live/frames` | `get_radar_live_frames` |
| `GET` | `/api/satellite-v2/catalog` | `get_satellite_v2_catalog` |
| `GET` | `/api/satellite-v2/status` | `get_satellite_v2_status` |
| `GET` | `/api/satellite-v2/legend` | `get_satellite_v2_legend` |
| `GET` | `/api/satellite-v2/tile/{z}/{x}/{y}` | `get_satellite_v2_tile` |

## Root HTML Files

Command:

```powershell
Get-ChildItem -Path . -Filter *.html | Select-Object Name,Length
```

| File | Length |
| --- | ---: |
| `index.html` | 9716 |
| `weather.html` | 218663 |

Absent root HTML files:

- `radar.html`
- `satellite.html`

## Frontend API References

Scan command:

```powershell
rg -n "fetch\(|apiUrl\(|/api/" js\shared.js js\weather.js weather.html index.html
```

Current frontend consumers:

| File | Observed API usage |
| --- | --- |
| `index.html` | Calls `/api/purge` from the landing page purge control. No matching backend route was seen in the route table. |
| `js/shared.js` | Defines `apiUrl()`, polls `/api/progress/{requestId}`, reads `/api/data/mrms`, and references `/api/alerts/polygons`. |
| `js/weather.js` | Calls current weather/product APIs for alerts, SPC, drought, surface, MRMS, RTMA, radar live/tiles/status, satellite v2, tropical, overlays, archive, and progress. |
| `weather.html` | No direct API calls found by the scan. API usage is in loaded scripts. |

Endpoint families referenced by frontend scripts:

- `/api/progress/{request_id}`
- `/api/data/alerts`
- `/api/alerts/polygons`
- `/api/data/spc`
- `/api/data/spc/reports`
- `/api/data/spc/active`
- `/api/data/drought/dates`
- `/api/data/drought`
- `/api/data/drought/state-stats`
- `/api/data/surface`
- `/api/data/surface-gradient`
- `/api/data/mrms`
- `/api/mrms/set-product`
- `/api/data/rtma`
- `/api/data/rtma/points`
- `/api/data/rtma/frames`
- `/api/radar/colortable`
- `/api/radar/tiles/{z}/{x}/{y}`
- `/api/radar/tiles/freshness`
- `/api/radar/status`
- `/api/radar/live/sites`
- `/api/radar/live/latest`
- `/api/radar/live/frames`
- `/api/satellite-v2/catalog`
- `/api/satellite-v2/status`
- `/api/satellite-v2/legend`
- `/api/satellite-v2/tile/{z}/{x}/{y}`
- `/api/tropical/storms`
- `/api/tropical/basin/{basin_id}/feeds`
- `/api/tropical/storm/{storm_id}`
- `/api/tropical/archive/catalog`
- `/api/tropical/archive/storm/{atcf_id}`
- `/api/tropical/archive/storm/{atcf_id}/advisory/{step}`
- `/api/overlay/latest`
- `/api/overlay/frames`
- `/api/overlay/us-boundaries`
- `/api/overlay/world-borders`
- `/api/archive/mrms`
- `/api/archive/alerts`
- `/api/archive/surface`
- `/api/archive/spc`
- `/api/archive/result`
- `/api/purge`

## Known Gaps Before Refactor

- `tools/` is absent in this checkout.
- `radar.html` is absent, but `/radar.html` is currently registered and should
  remain registered during the backend refactor.
- `satellite.html` is absent.
- `/api/alerts/polygons` is referenced by `js/shared.js` but is not currently
  registered in the backend route table.
- `/api/purge` is referenced by `index.html` but is not currently registered in
  the backend route table.

## Phase 1 Verification

- Baseline route list was captured before moving any application code.
- Static mounts were captured from `main.py`.
- Root HTML files were captured.
- Frontend API references were captured from the playbook-specified files.
- No application files were changed in this phase.
