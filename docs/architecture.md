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

## Backend Workers (OS-first, APScheduler fallback)

Cache refresh is OS-first via Windows Task Scheduler. In-process APScheduler
jobs are now fallback-only and are enabled only when
`WX_INPROC_WORKERS=1`.

Current in-process fallback intervals in `workers/scheduler.py`:

| Worker | Interval | Notes |
|---|---|---|
| alerts_worker | 1 min | First run immediate when fallback mode is enabled |
| spc_worker | 30 min | First run immediate |
| mrms_worker | 15 min | First run delayed by 30s |
| surface_worker | 30 min | First run immediate |

Default runtime behavior (no env var): no APScheduler jobs are registered and
cache freshness is delegated to OS tasks.

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

Weather alerts interaction model:

- Clicking an alert polygon opens the immersive alert detail panel.
- Clicking an alert row in the right WWA list opens the same panel for that row.
- The panel closes on outside map click, Escape, or map move/zoom start.
- Storm-track projection controls live in the right-side alerts styling group.

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
