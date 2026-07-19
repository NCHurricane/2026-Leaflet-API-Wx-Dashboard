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

Current weather-radar live endpoints:

- `/api/radar/live/sites`
- `/api/radar/live/latest`
- `/api/radar/live/frames`

## Worker / Scheduler Pattern

Current mode is OS-scheduled cache refresh (Windows Task Scheduler). In-process
APScheduler is fallback-only and opt-in via `WX_INPROC_WORKERS=1`.

Refactor target: make an app-managed Python worker supervisor the default
runtime path so the dashboard can run consistently on Windows, macOS, and Linux.
OS schedulers should become optional advanced deployment integrations, not the
only comfortable way to keep caches fresh.

When fallback mode is enabled, `workers/scheduler.py` registers:

- alerts: 1 min
- spc: 30 min
- mrms: 15 min (first tick delayed 30s)
- surface: 30 min

Workers write cache artifacts that API endpoints read directly. Cold-cache
endpoint fallbacks can still run workers synchronously when needed.

Supervisor requirements:

- Use existing freshness markers and per-worker skip gates.
- Keep API-only mode available.
- Keep one-off worker module commands available.
- Avoid duplicate refresh work when an OS scheduler is also enabled.
- Log worker output consistently under `logs/scheduled/` or a replacement
  cross-platform log directory.

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

Current implementation: `frontend/pages/workspace/workspace-tools.js`
(`_activateStormTrackDragProjection`, `_installStormTrackDragHandle`,
`_pivotedBearingDeg`). These controls are intentionally excluded from the
standalone Alerts page because its former IEM radar overlay was removed. Treat
them as workspace-owned capabilities for the severe-weather workspace. The
former fixed-loop Radar Speed Estimator was removed after its timing dependency
ceased to match the current radar frame model.

## Alert Detail Open/Close Pattern

Standalone alert polygon clicks and Active Warnings cards open the immersive
alert detail panel owned by `frontend/pages/alerts/alerts-detail.js`.

- The panel is draggable by its header and height-bounded with internal scroll.
- Map click outside the panel closes it.
- Map move/zoom start closes the panel.
- Escape closes the panel.
- Product links are derived from the alert event and issuing office so an update
  product code such as SVS does not replace the owning warning code such as SVR.

Leaflet click/scroll propagation is disabled on the detail root so interaction
with the panel does not also manipulate or close the map view.

## Standalone Alerts Live-State Pattern

- Alert and LSR payloads remain cached in the engine when their selectors are
  turned off; empty selection removes layers without discarding good data.
- Category re-selection filters cached data immediately. LSR cache identity is
  viewport plus time window; scope changes or explicit refresh fetch new data.
- The page, not parallel loaders, owns the combined footer message so a later
  LSR response cannot overwrite active-alert status.
- The default-on timer explicitly refreshes selected live data every 60 seconds.
- The right rail derives visibility from selected datasets, not response counts.

## Endpoint Progress Pattern

Progress tracking (`active_tasks`, `/api/progress/{request_id}`) applies only to Radar and Satellite render endpoints.

Weather cache-first endpoints (`/api/data/*`, `/api/overlay/*`) are lightweight reads — no progress tracking needed.

Archive and export endpoints retain progress tracking where render time is non-trivial.

## Radar Live Fallback Pattern (Standalone Page)

For `/api/radar/live/latest` and `/api/radar/live/frames`:

1. Read from cache-first radar overlay store (`cache/overlays/radar/{SITE}/{LEVEL}/{PRODUCT}`).
2. If cache miss, run bounded on-demand render path using `run_radar_live_site_product(...)`.
3. For latest endpoint cold start, render newest-first with `max_render_frames=1` for immediate first paint.
4. Start background history backfill after first frame so scrubber readiness improves without blocking current view.
5. Guard fallback with per-site/per-product locks to avoid duplicate warm runs.

Frontend should treat `history_filling=true` as a warm-state hint, not as an error.

## Radar Download Race-Tolerance Pattern (Windows)

`radar/radar_nodd_utils.py` download loop intentionally tolerates concurrent write races:

1. Retry on `FileExistsError` and `PermissionError`.
2. After each retry delay, accept a non-empty local file as race-resolved success.
3. Emit warning only after retries are exhausted and no valid file exists.

This prevents false hard-failures when worker/API warm paths overlap on Windows.

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

## Satellite Legend Pattern

Satellite scalar brightness-temperature products use `/api/satellite-v2/legend`
to return continuous colorbar anchors and ticks. RGB composite products do not
use numeric colorbars because their colors come from multi-channel recipes.

For RGB composites:

1. Keep renderer-matched interpretive legend metadata in
   `config/satellite_v2_config.py`.
2. Return the same metadata from `satellite_v2.service.get_legend_payload()` as
   `legend_type: "interpretive"`.
3. Mirror the interpretive metadata in `js/weather.js` as a frontend fallback so
   static composite legends render immediately and do not disappear during
   satellite/sector/product switches or transient API/catalog failures.
4. Call the Satellite legend updater directly from `js/satellite-page.js`
   control-change handlers before frame reloads.
5. Bump affected `weather.html` script query strings when changing Satellite
   frontend wiring.

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

Standalone Radar playback is frame scrub/poll playback from cached overlays,
not encoded export animation.

## Date Validation Pattern

For archive endpoints: `date_from`/`date_to` must both be provided or both omitted. Single-date requests return HTTP 400.

Not applicable to `/api/data/*` (current data only in Phase 1).

Frame-based overlay endpoints use `frame_key` (`YYYY_MM_DD_HH_MM_SS`) for direct historical frame access.

## Style Config Pattern

Standalone Alerts colors live in
`frontend/pages/alerts/alerts-config.js`; legacy workspace and SPC colors remain
in their owning frontend modules. Official alert colors mirror
`config/alerts_config.py` and remain the source for polygons, borders, and
legends. A separate `ALERT_TEXT_COLORS` map may provide contrast-only text
overrides on dark UI surfaces without changing the official core color.

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

## Product Page Shell Pattern

Product pages share the same map-first dashboard shell. The standalone Tropical
page is the reference rich product implementation because it has the clearest
product-specific hub/map/inspector workflow.

1. Top navigation/status bar.
2. Fixed left product hub or controls dock.
3. Bounded center map canvas owned by that product page.
4. Fixed right inspector, legend, products, and selected-feature details dock.
5. Docked bottom timeline/archive/scrubber area when the product supports time.
6. Shared refresh/error/status surface.

The default desktop shell should use docked dashboard panels rather than
collapsible sidebars floating over the map. Collapse or stacking behavior is a
responsive/mobile concern, not the primary desktop model.

Keep product-specific selectors in product controls unless they truly apply to
every product. For example, region selection should not become a global command
bar control while Tropical uses basin selection instead.

Canonical product URLs should be extensionless:

- `/alerts`
- `/radar`
- `/satellite`
- `/spc`
- `/surface`
- `/mrms`
- `/rtma`
- `/drought`
- `/tropical`

Legacy `.html` URLs may redirect to canonical routes or remain as temporary
compatibility routes during migration.

## Shared Frontend Utility Pattern

Each product page should own its entry file, but common behavior should live in
shared utilities:

- API client and URL helpers.
- Map factory/base-layer setup.
- Page shell initialization.
- Timestamp/status/reliability helpers.
- Layer lifecycle and cleanup helpers.
- Timer/AbortController cleanup registry.
- Legend helpers.
- Timeline/scrubber controller.
- Shared constants that are intentionally duplicated from backend config.

Do not create product pages by copy-pasting the current combined `weather.js`
state model into separate files. Split shared utilities first, then give each
product page a narrow entry module.

Tropical now demonstrates the boundary: reuse `frontend/core/` for API helpers,
map setup, navigation, sidebar tabs, status, and legend lifecycle, while keeping
storm/archive domain behavior in `frontend/pages/tropical/`.

Water follows the same boundary with a single page entry module: viewport-aware
station requests, flood filtering, markers, and popups remain page-local while
map overlays, navigation, status, sidebar tabs, and legend hosting come from
`frontend/core/`.

For Tropical backend changes, follow the post-refactor ownership boundaries:

- API route declarations belong in `routes/tropical.py`.
- Route-facing cache and response behavior belongs in
  `services/tropical_service.py`.
- NHC ingestion, GTWO parsing, GIS parsing, and cache generation belong in
  `workers/tropical_worker.py`.
- Do not add Tropical route logic back to `main.py`.

## Clean-Cut Migration Pattern

The clean-cut migration completed in Phase 27. The retained rules are:

1. Product pages import only `frontend/core/`, vendored libraries, and their own
   directory.
2. `/workspace` may import sibling engine modules, never sibling page controllers.
3. Keep `/weather.html` only as a redirect to `/workspace`.
4. Keep API endpoint compatibility unless a separate API cleanup is planned.

## Radar UX State Pattern (Standalone Page)

Radar controls in `frontend/pages/radar/` follow these state rules:

1. Site dropdown selection collapses multi-site mode into a single-site context.
2. If site/product selection changes during time-mode scrub, context is invalidated and user is prompted to press Animate again.
3. `Clear` removes loaded radar overlays and exits animate-to-current state, while preserving current map extent.
4. `Show Radar Sites` controls both marker visibility and the radar-sites legend visibility when no specific site is selected.
