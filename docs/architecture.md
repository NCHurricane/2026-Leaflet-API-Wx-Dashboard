# System Architecture

## Source Control (2026-04-16)

Private GitHub repository. Rollback via `git restore`/`git revert`. High-risk refactors should be committed in small checkpoints. PR-based merges to `main` are the preferred gate for structural backend changes.

## Phase 1+ State (Leaflet Map)

Unified weather page serves a live Leaflet map with mixed layer types:

- Vector GeoJSON overlays (alerts, SPC)
- Pre-rendered raster overlays + frame-locked value points (RTMA)

Active pages and their JS:

- `weather.html` / `js/weather.js` — Leaflet map, alerts + SPC GeoJSON layers, RTMA pre-rendered overlays, RTMA scrubber
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

Default runtime behavior (no env var): no APScheduler jobs are registered and
cache freshness is delegated to OS tasks.

### Local Dev Run Profiles

Use these helper launchers for consistent startup behavior:

- `tools/run_api_only.ps1` - API-only mode. Clears `WX_INPROC_WORKERS` for the current process and starts `main.py`.
- `tools/run_inproc_workers.ps1` - in-process mode. Sets `WX_INPROC_WORKERS=1` and starts `main.py`.
- `tools/run_dual_mode.ps1` - dual mode. Sets `WX_INPROC_WORKERS=1` and starts `main.py` (Windows Task Scheduler jobs must also be enabled).

PowerShell examples from repository root:

```powershell
.\tools\run_api_only.ps1
.\tools\run_inproc_workers.ps1
.\tools\run_dual_mode.ps1
```

Dual mode is intended for validation and stress testing only. It can duplicate refresh work and increase network/disk activity.

## Data Endpoints

```
GET /api/data/alerts?state={STATE}   # optional state filter
GET /api/data/spc?day={1-8}&hazard={cat|torn|wind|hail|prob|windrh|dryt}
GET /api/overlay/latest?family=rtma&region={REGION}&stream={STREAM}&product={PRODUCT}[&frame_key=YYYY_MM_DD_HH_MM_SS]
GET /api/overlay/frames?family=rtma&region={REGION}&stream={STREAM}&product={PRODUCT}
GET /api/data/rtma/points?region={REGION}&stream={STREAM}&product={PRODUCT}[&source_data_key=...]
```

Alerts/SPC endpoints:

1. Read from the corresponding cache file.
2. If cache is missing (cold start), trigger a synchronous worker run inline.
3. Return GeoJSON with an added `count` field.

RTMA overlay endpoints:

1. Read pre-rendered frame metadata from overlay cache index/frame directories.
2. Return overlay metadata (`render.image_url`, `bounds`, `legend`, `timestamp`, `source_data_key`).
3. Frontend requests points with matching `source_data_key` to avoid frame drift.

Cache served as static files via `/cache` mount (StaticFiles).

## Frontend Architecture

`js/weather.js` — IIFE, no framework, ES6+, async/await.

Responsibilities:

- Leaflet map init with CartoDB Dark/Light basemap toggle
- `loadAlerts(category)` — fetches `/api/data/alerts`, renders `L.geoJSON`, builds legend
- `loadSpc(day, hazard)` — fetches `/api/data/spc`, renders `L.geoJSON`, builds legend
- `loadRtma()` — fetches `/api/overlay/latest` first, applies `L.imageOverlay`, then fetches frame-locked points
- `loadRtmaScrubberFrames()` — fetches `/api/overlay/frames` for instant frame list
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

Weather workflow is mixed by product family:

- Alerts/SPC: data-only endpoints, Leaflet vector rendering
- RTMA: server-side pre-rendered PNG overlays + cached points, Leaflet imageOverlay + markers

Radar/Satellite workflows: unchanged — synchronous render pipeline, Lambert projection, server-side image generation, layered PNG scrubber.

## Cache Layout

```
cache/
  alerts/
    national.geojson
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
    rtma/
      {REGION}/{stream}/{product}/{frame_key}/
        overlay.png
        meta.json
        bounds.json
  .workers/
    rtma.last_run
```

## Python Module Map

| Module                         | Role                                                                          |
| ------------------------------ | ----------------------------------------------------------------------------- |
| `main.py`                      | FastAPI app, routing, lifecycle events                                        |
| `workers/scheduler.py`         | APScheduler setup and lifecycle                                               |
| `workers/alerts_worker.py`     | NWS alerts fetch → cache                                                      |
| `workers/spc_worker.py`        | SPC outlook fetch → cache                                                     |
| `workers/rtma_worker.py`       | RTMA points + pre-render overlay refresh                                      |
| `workers/rtma_preload.py`      | One-time RTMA backfill/preload                                                |
| `alerts/alerts_utils.py`       | `fetch_active_alerts_with_source()`                                           |
| `spc/spc_utils.py`             | `fetch_outlook_geojson()`, `fetch_fire_wx_geojson()`                          |
| `rtma_utils.py`                | RTMA source resolution, grid extraction, pre-render generation, point caching |
| `cache/overlay_cache_utils.py` | Overlay frame paths/index/meta helpers                                        |
| `config/geo_config.py`         | `STATE_BOUNDS` dict (used in weather.js)                                      |
| `config/alerts_config.py`      | `ALERT_COLORS` dict                                                           |

## Radar / Satellite Exception (Current)

Radar and Satellite are not yet on the RTMA overlay-cache contract. They currently retain:

- Synchronous render pipeline
- Lambert conformal conic projection
- Layered PNG scrubber
- `/api/radar`, `/api/satellite` endpoints
- `active_tasks` progress tracking

Planned direction:

- Migrate relevant tabs (Surface, MRMS, Radar, Satellite) toward the RTMA-style cache-first pre-render contract.
- Alerts remain on the existing vector GeoJSON workflow.

## MRMS Overlay Cache — Rollout Status (2026-05-01)

Backend infrastructure complete; frontend scrubber not yet built.

**Completed:**

- `workers/mrms_worker.py` writes each rendered CONUS PNG to the overlay cache after every 15-min cycle. Accepts `keep_n: int | None` to defer pruning during batch writes.
- `workers/mrms_preload.py` backfills all 14 products across their full lookback windows using `list_mrms_files`. Per-product pruning happens once at the end of each batch.
- `main.py` — `mrms` added to the `allowed_families` allowlist on both `/api/overlay/latest` and `/api/overlay/frames`.
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
