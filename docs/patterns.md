# Coding Patterns

## Cache-First Data Pattern

All weather data endpoints read from a local GeoJSON cache before hitting external APIs.

Pattern:
1. Check if cache file exists and is fresh.
2. If missing: trigger synchronous worker run inline, then read.
3. Return GeoJSON + `count` metadata field.

Used by: `/api/data/alerts`, `/api/data/spc`.

## Worker / Scheduler Pattern

Background workers run on APScheduler `BackgroundScheduler`. Each worker:
- Has a fixed interval (alerts: 2 min, SPC: 30 min).
- Writes a single cache file per product per run.
- Is called synchronously on cold-cache miss from an endpoint.

Startup: `start_scheduler()` registers jobs and triggers an immediate first run.
Shutdown: `stop_scheduler()` shuts down gracefully.

Guard pattern — import is wrapped in try/except so app starts without APScheduler if it is not installed:

```python
try:
    from workers.scheduler import start_scheduler, stop_scheduler
    _SCHEDULER_AVAILABLE = True
except ImportError:
    _SCHEDULER_AVAILABLE = False
```

## Endpoint Progress Pattern

Progress tracking (`active_tasks`, `/api/progress/{request_id}`) applies only to Radar and Satellite render endpoints.

Weather data endpoints (`/api/data/*`) are lightweight reads — no progress tracking needed.

Archive and export endpoints retain progress tracking where render time is non-trivial.

## Two-Tier Dropdown Pattern

SPC controls use a three-way dropdown (convective / fire / other). Track which was last changed with `_spcLastTouched` to determine which product to load:

```js
let _spcLastTouched = 'convective';

convectiveSelect.addEventListener('change', () => {
    _spcLastTouched = 'convective';
    fireSelect.value = '';
    refreshSpc();
});

fireSelect.addEventListener('change', () => {
    _spcLastTouched = 'fire';
    convectiveSelect.value = '';
    refreshSpc();
});
```

## Leaflet Layer Pattern

All weather vector data is rendered via `L.geoJSON`. Layer lifecycle:

1. Remove old layer from map (`map.removeLayer(layer); layer = null`).
2. Fetch fresh GeoJSON from `/api/data/*`.
3. Create new `L.geoJSON` with `style` and `onEachFeature` callbacks.
4. Add to map if visibility checkbox is checked.
5. Update legend control via `setLegend(html)`.

Opacity is applied via `layer.setStyle(styleFn)` — not a CSS filter.

## Region Bounds Pattern

`STATE_BOUNDS` in `js/weather.js` stores `[west, east, south, north]` for each state (matching Python `geo_config.py` layout).

Convert to Leaflet before calling `fitBounds`:

```js
// geo_config format: [west, east, south, north]
// Leaflet fitBounds: [[south, west], [north, east]]
function leafletBounds(code) {
    const b = STATE_BOUNDS[code];
    return [[b[2], b[0]], [b[3], b[1]]];
}
```

## Projection Pattern

- Weather page (Leaflet): Web Mercator (EPSG:3857), tile-based, vector overlays
- Radar / Satellite (server-side): Lambert conformal conic, Matplotlib, PNG output

Do not mix projections. GeoJSON overlays on the Leaflet map must use WGS-84 coordinates (EPSG:4326). SPC and NWS GeoJSON from the API natively provides WGS-84.

## Response Shape Pattern

Use `success_payload()` / `error_payload()` helpers for render endpoints.

Data endpoints (`/api/data/*`) return raw GeoJSON with an extra `count` top-level field. No wrapper envelope needed for client-side Leaflet consumption.

## Animation Encoding Pattern

Animation encoding applies to Radar and Satellite export endpoints only. Weather page does not produce animations.

Radar/Satellite: H.264 via FFmpeg, `/api/radar/export-animation`, `/api/satellite/export-animation`.

## Date Validation Pattern

For archive endpoints: `date_from`/`date_to` must both be provided or both omitted. Single-date requests return HTTP 400.

Not applicable to `/api/data/*` (current data only in Phase 1).

## Style Config Pattern

Color values for alerts and SPC risk categories are defined as constants in the frontend JS (`ALERT_COLORS`, `SPC_CAT_COLORS`, `SPC_FIRE_COLORS` in `js/weather.js`). These mirror the Python-side `config/alerts_config.py` values.

Do not fetch color config from the backend at runtime — embed as JS constants.
