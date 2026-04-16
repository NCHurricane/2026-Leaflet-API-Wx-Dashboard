# System Architecture

## Source Control (2026-04-16)

Private GitHub repository. Rollback via `git restore`/`git revert`. High-risk refactors should be committed in small checkpoints. PR-based merges to `main` are the preferred gate for structural backend changes.

## Phase 1 State (Leaflet Map)

Unified weather page now serves a live Leaflet map with vector GeoJSON overlays. No image rendering or scrubber in weather.html.

Active pages and their JS:
- `weather.html` / `js/weather.js` — Leaflet map, alerts + SPC GeoJSON layers
- `radar.html` / `js/radar.js` — independent radar workflow (unchanged)
- `satellite.html` / `js/satellite.js` — independent satellite workflow (unchanged)

Removed in Phase 0:
- `legacy/` pages and JS are retained but unrouted
- Legacy API render endpoints removed from main.py

## Backend Workers (APScheduler)

Two background workers poll external APIs and write GeoJSON cache files:

| Worker | Interval | Cache Path |
|---|---|---|
| alerts_worker | 2 min | `cache/alerts/national.geojson` |
| spc_worker | 30 min | `cache/spc/{day}_{hazard}.geojson`, `cache/spc/fire_{day}_{hazard}.geojson` |

Workers start on `startup` event and stop on `shutdown`. First run is triggered immediately at startup to warm the cache. Implemented in `workers/scheduler.py`, `workers/alerts_worker.py`, `workers/spc_worker.py`.

If APScheduler import fails, the app starts with `_SCHEDULER_AVAILABLE = False` and workers are simply skipped (cache files are populated on first request via cold-cache fallback).

## Data Endpoints

```
GET /api/data/alerts?state={STATE}   # optional state filter
GET /api/data/spc?day={1-8}&hazard={cat|torn|wind|hail|prob|windrh|dryt}
```

Both endpoints:
1. Read from the corresponding cache file.
2. If cache is missing (cold start), trigger a synchronous worker run inline.
3. Return GeoJSON with an added `count` field.

Cache served as static files via `/cache` mount (StaticFiles).

## Frontend Architecture

`js/weather.js` — IIFE, no framework, ES6+, async/await.

Responsibilities:
- Leaflet map init with CartoDB Dark/Light basemap toggle
- `loadAlerts(category)` — fetches `/api/data/alerts`, renders `L.geoJSON`, builds legend
- `loadSpc(day, hazard)` — fetches `/api/data/spc`, renders `L.geoJSON`, builds legend
- Region → `fitBounds` mapping (all 50 states + CONUS)
- Layer visibility and opacity sliders (no page reload)
- SPC three-way dropdown: convective / fire / other (tracks `_spcLastTouched`)
- Alert category filter applied client-side against `properties.event`

`js/shared.js` — exports `window.apiUrl`, `window.initNav`, and progress/output helpers (progress helpers are no-ops for the weather page since weather no longer uses the render pipeline).

## Pipeline Separation

Weather workflow: data-only endpoints, Leaflet client rendering, no server-side image generation.

Radar/Satellite workflows: unchanged — synchronous render pipeline, Lambert projection, server-side image generation, layered PNG scrubber.

## Cache Layout

```
cache/
  alerts/
    national.geojson
  spc/
    1_cat.geojson
    1_torn.geojson
    ...
    fire_1_windrh.geojson
    fire_1_dryt.geojson
    ...
```

## Python Module Map

| Module | Role |
|---|---|
| `main.py` | FastAPI app, routing, lifecycle events |
| `workers/scheduler.py` | APScheduler setup and lifecycle |
| `workers/alerts_worker.py` | NWS alerts fetch → cache |
| `workers/spc_worker.py` | SPC outlook fetch → cache |
| `alerts/alerts_utils.py` | `fetch_active_alerts_with_source()` |
| `spc/spc_utils.py` | `fetch_outlook_geojson()`, `fetch_fire_wx_geojson()` |
| `config/geo_config.py` | `STATE_BOUNDS` dict (used in weather.js) |
| `config/alerts_config.py` | `ALERT_COLORS` dict |

## Radar / Satellite Exception

Radar and Satellite workflows are not affected by Phase 1 changes. They retain:
- Synchronous render pipeline
- Lambert conformal conic projection
- Layered PNG scrubber
- `/api/radar`, `/api/satellite` endpoints
- `active_tasks` progress tracking
