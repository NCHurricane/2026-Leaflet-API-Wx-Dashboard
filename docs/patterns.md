# Coding Patterns

## Cache-First Data Pattern

Weather uses a cache-first pattern with multiple cache artifact shapes (not GeoJSON-only).

Pattern:

1. Resolve requested product/frame against local cache indexes/files.
2. Return cached artifact metadata and URLs when available.
3. Fall back to bounded regeneration path only when cache is missing.

Current shapes:

- Vector cache (GeoJSON): alerts, SPC, RTMA points.
- Raster overlay cache (PNG + meta + bounds): RTMA overlays.
- Index cache (JSON manifests): pre-render frame discovery for scrubber.

Current RTMA endpoints:

- `/api/overlay/latest`
- `/api/overlay/frames`
- `/api/data/rtma/points`

## Worker / Scheduler Pattern

Default mode is OS-scheduled cache refresh (Windows Task Scheduler). In-process
APScheduler is fallback-only and opt-in via `WX_INPROC_WORKERS=1`.

When fallback mode is enabled, `workers/scheduler.py` registers:

- alerts: 1 min
- spc: 30 min
- mrms: 15 min (first tick delayed 30s)
- surface: 30 min

Workers write cache artifacts that API endpoints read directly. Cold-cache
endpoint fallbacks can still run workers synchronously when needed.

Guard pattern — import is wrapped in try/except so app starts without APScheduler if it is not installed:

```python
try:
    from workers.scheduler import start_scheduler, stop_scheduler
    _SCHEDULER_AVAILABLE = True
except ImportError:
    _SCHEDULER_AVAILABLE = False
```

## Storm Track Projection Pattern

Storm-track base line is point-driven (map clicks append points), then a drag
handle projects movement intervals from alert-derived motion vectors.

- Hold Shift while dragging to pivot the projection bearing.
- Pivot is clamped by `_STORM_TRACK_PIVOT_MAX_DEG` (currently 45 degrees).
- Place-arrival overlay rows are sorted by arrival time and capped.

Core implementation: `js/weather.js` (`_activateStormTrackDragProjection`,
`_installStormTrackDragHandle`, `_pivotedBearingDeg`).

## Alert Detail Open/Close Pattern

Alert polygon clicks and WWA list row clicks open the immersive alert detail
panel (`_openNewAlertDetail`).

- Map click closes the panel.
- Map move/zoom start closes the panel.
- Escape closes the panel.

To avoid immediate close on the opening click, map-level close handlers are
bound after panel mount (deferred registration).

## Endpoint Progress Pattern

Progress tracking (`active_tasks`, `/api/progress/{request_id}`) applies only to Radar and Satellite render endpoints.

Weather cache-first endpoints (`/api/data/*`, `/api/overlay/*`) are lightweight reads — no progress tracking needed.

Archive and export endpoints retain progress tracking where render time is non-trivial.

## Two-Tier Dropdown Pattern

SPC controls use a three-way dropdown (convective / fire / other). Track which was last changed with `_spcLastTouched` to determine which product to load:

```js
let _spcLastTouched = "convective";

convectiveSelect.addEventListener("change", () => {
  _spcLastTouched = "convective";
  fireSelect.value = "";
  refreshSpc();
});

fireSelect.addEventListener("change", () => {
  _spcLastTouched = "fire";
  convectiveSelect.value = "";
  refreshSpc();
});
```

## Leaflet Layer Pattern

Weather uses both vector and raster layer lifecycles.

Vector lifecycle (`L.geoJSON`):

1. Remove old layer from map (`map.removeLayer(layer); layer = null`).
2. Fetch fresh GeoJSON from `/api/data/*`.
3. Create new `L.geoJSON` with `style` and `onEachFeature` callbacks.
4. Add to map if visibility checkbox is checked.
5. Update legend control via `setLegend(html)`.

Opacity is applied via `layer.setStyle(styleFn)` — not a CSS filter.

Raster overlay lifecycle (`L.imageOverlay`):

1. Fetch overlay meta from `/api/overlay/latest` or `/api/overlay/frames`.
2. Remove prior image overlay layer.
3. Convert `[west, east, south, north]` to Leaflet bounds `[[south, west], [north, east]]`.
4. Add `L.imageOverlay(image_url, leafletBounds, { opacity })`.
5. Fetch value points with matching `source_data_key` to keep markers frame-locked.

## Region Bounds Pattern

`STATE_BOUNDS` in `js/weather.js` stores `[west, east, south, north]` for each state (matching Python `geo_config.py` layout).

Convert to Leaflet before calling `fitBounds`:

```js
// geo_config format: [west, east, south, north]
// Leaflet fitBounds: [[south, west], [north, east]]
function leafletBounds(code) {
  const b = STATE_BOUNDS[code];
  return [
    [b[2], b[0]],
    [b[3], b[1]],
  ];
}
```

## Projection Pattern

- Weather page (Leaflet): Web Mercator (EPSG:3857), tile-based, vector overlays
- Radar / Satellite (server-side): Lambert conformal conic, Matplotlib, PNG output

Do not mix projections. GeoJSON overlays on the Leaflet map must use WGS-84 coordinates (EPSG:4326). SPC and NWS GeoJSON from the API natively provides WGS-84.

## Response Shape Pattern

Use `success_payload()` / `error_payload()` helpers for render endpoints.

Vector data endpoints (`/api/data/*`) return raw GeoJSON/point payloads suitable for Leaflet consumption.

Overlay endpoints (`/api/overlay/*`) return metadata envelopes with:

- `render.image_url`
- `bounds` (`[west, east, south, north]`)
- `legend`
- `timestamp`
- `source_data_key`

Frontend should treat `source_data_key` as the frame-lock token for follow-up point requests.

## Animation Encoding Pattern

Animation encoding applies to Radar and Satellite export endpoints only. Weather page does not produce animations.

Radar/Satellite: H.264 via FFmpeg, `/api/radar/export-animation`, `/api/satellite/export-animation`.

## Date Validation Pattern

For archive endpoints: `date_from`/`date_to` must both be provided or both omitted. Single-date requests return HTTP 400.

Not applicable to `/api/data/*` (current data only in Phase 1).

Frame-based overlay endpoints use `frame_key` (`YYYY_MM_DD_HH_MM_SS`) for direct historical frame access.

## Style Config Pattern

Color values for alerts and SPC risk categories are defined as constants in the frontend JS (`ALERT_COLORS`, `SPC_CAT_COLORS`, `SPC_FIRE_COLORS` in `js/weather.js`). These mirror the Python-side `config/alerts_config.py` values.

Do not fetch color config from the backend at runtime — embed as JS constants.

## Pre-render Overlay Pattern (RTMA Baseline)

RTMA establishes the baseline pre-render pattern for other tabs:

1. Worker/preload renders frame PNGs to cache and writes per-frame `meta.json` + `bounds.json`.
2. Index manifest provides fast frame enumeration without remote probing.
3. UI requests overlay first, then value points locked by `source_data_key`.
4. Scrubber frame list reads cache index first; remote fallback is secondary.
5. Retention/prune policy keeps rolling window bounded by stream cadence.

## Cross-Tab Migration Pattern (Excluding Alerts)

Migration target for Surface, MRMS, Radar, and Satellite:

1. Adopt shared overlay contract (`latest`, `frames`, per-frame metadata).
2. Keep product-specific workers/renderers, but normalize response shape.
3. Frame-lock any value/point layers to overlay `source_data_key`.
4. Preserve product-specific projection/render details under a common cache/index API.

Alerts intentionally remains on vector GeoJSON workflow.
