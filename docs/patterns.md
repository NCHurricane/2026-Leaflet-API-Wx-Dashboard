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

The application-owned coordinator in `app_core/refresh_coordinator.py` is the
required pattern for migrated request refreshes:

1. Use a key identifying the actual upstream work. Do not include a product
   when one regional provider response can populate every product cache.
2. Record or renew the 90-second request-presence lease.
3. Return the best complete cache immediately.
4. Submit missing/stale work through the bounded coordinator.
5. Report `refreshing` or `backoff` without exposing exception text or
   credentials.
6. Publish through `app_core/atomic_io.py` so readers see the previous or next
   complete generation, never an in-progress write.

For selected work that must continue while a page remains present, use
`activate_presence_job(...)`: key the real product/source scope, choose a
source-appropriate interval, and let the coordinator remove the dynamic job
after the 90-second lease expires. Optional acceleration should use an initial
delay when immediate execution could compete with first paint.

Do not add raw daemon threads or per-service in-flight sets. Provider minimum
intervals, concurrency, retry/backoff, state reporting, periodic cleanup, and
graceful shutdown belong to the coordinator. Phase 1 is explicitly
single-process; persistent coordination is required before multi-worker Uvicorn
or optional OS warmers can safely share ownership.

`workers/scheduler.py` is a compatibility lifecycle hook and does not restore a
broad APScheduler profile. Existing direct-write Windows task definitions are
not coordinator-compatible. Migrated heavy cold paths return an explicit
warming response and let the client poll local cache; Surface uses one
observation key per region and fans one upstream response into all product
cache artifacts.

Supervisor requirements:

- Use existing freshness markers and per-worker skip gates.
- Keep API-only mode available.
- Keep one-off worker module commands available.
- Do not overlap legacy direct-write OS tasks with migrated coordinator paths.
  Optional warmers call the running local API and cannot be a correctness
  dependency.
- Log worker output consistently under `cache/logs/scheduled/` or a replacement
  cross-platform log directory.

The supported runtime is one application process. Do not add multi-worker
ownership or persistent leases unless deployment requirements change and a new
coordination design is approved.

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
- Active Alerts uses one map payload per refresh. Below zoom 8 it requests the
  national `low` payload; zoom 8+ requests `high` with the visible bbox.
- Native NWS polygons are never simplified. Only zone/SAME-derived geometry may
  use the topology-preserving low-detail path.
- Full, low-detail, and compatibility artifacts share one generation ID and
  become API-visible only when `current_generation.json` is atomically replaced.
- Stale active-alert data stays visible while one coordinator refresh observes
  the application-wide 35-second NWS floor. Cold missing cache is warming/error
  state, not a valid empty alert set.
- The page, not parallel loaders, owns the combined footer message so a later
  LSR response cannot overwrite active-alert status.
- The default-on timer explicitly refreshes selected live data every 60 seconds.
- The right rail derives visibility from selected datasets, not response counts.

## Archive Endpoint Pattern

The retained `/api/archive/alerts` and `/api/archive/surface` endpoints return
their results synchronously and use deterministic JSON caching in
`services/archive_service.py`. The disconnected MRMS/SPC render-session and
progress-polling workflow was removed during cleanup Phase 2.

Cache-first endpoints (`/api/data/*`, `/api/overlay/*`, `/api/radar/live/*`,
`/api/satellite-v2/*`) remain lightweight reads or bounded on-demand renders.

## Radar Live Fallback Pattern (Standalone Page)

For `/api/radar/live/latest` and `/api/radar/live/frames`:

1. Read from cache-first radar overlay store (`cache/overlays/radar/{SITE}/{LEVEL}/{PRODUCT}`).
2. If cache miss, run bounded on-demand render path using `run_radar_live_site_product(...)`.
3. For latest endpoint cold start, render newest-first with `max_render_frames=1` for immediate first paint.
4. Activate lease-bound coordinator history fill after first frame so scrubber
   readiness improves without blocking current view.
5. Key activity by site, level, product, elevation, and storm-motion variant;
   retain the per-product fallback lock inside the worker boundary.

Frontend should treat `history_filling=true` as a warm-state hint, not as an error.

For Satellite, keep requested live tiles ahead of optional acceleration.
Selected rapid-sector tile warming and Meteosat source prefetch use delayed
presence jobs, source downloads deduplicate per platform/sector/frame, and
provider capability failures use explicit response states.

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

`REGION_BOUNDS` in `frontend/core/map-core.js` defines the default map view for every
region (WORLD, CONUS, the 50 states, PR). `fitRegion(code)` applies it, and the reset
(⌂) button returns to the page's home region (fixed at init, ignores the dropdown).

Each entry is **one of two forms**, and `fitRegion` dispatches on the shape
(`Array.isArray` → box; otherwise curated):

- **Box** — `[west, east, south, north]` (matching Python `geo_config.py` order),
  applied with `fitBounds`. Good for whole states/basins: the box adapts to each map's
  aspect ratio. **Container-dependent** — the same box can snap to a different zoom on
  pages whose map area differs in size (NC fits at z8 on most pages but z7 on the
  shorter alerts/water maps).
- **Curated** — `{ center: [lat, lng], zoom }`, applied with `setView`.
  **Container-independent**: frames identically on every page. Use this for hand-picked
  defaults where a fitted box would drift after Leaflet's integer zoom-snap. WORLD and
  CONUS use this form.

Box → Leaflet conversion (box form only):

```js
// geo_config order: [west, east, south, north]
// Leaflet fitBounds:  [[south, west], [north, east]]
map.fitBounds([[b[2], b[0]], [b[3], b[1]]]);
```

### Tuning a curated default view (dev workflow)

Any region can be a curated `{ center, zoom }` instead of a box. To dial one in:

1. In the browser console on any map page, run **`mapViewportLog(true)`** (defined in
   `map-core.js`; persists across pages/reloads via localStorage, `mapViewportLog(false)`
   to stop).
2. Pan/zoom to frame the view. Each `moveend` logs, e.g.:
   `[viewport] CONUS  [W, E, S, N] = [...]  center [37.58, -96.42]  zoom 5`
3. Drop the logged `center` + `zoom` straight into the region's `REGION_BOUNDS` entry.

Current curated defaults: `WORLD { center: [17.9, 1.48], zoom: 3 }`,
`CONUS { center: [37.58, -96.42], zoom: 5 }`.

The satellite platform views in `NAMED_VIEW_PRESETS`
(`frontend/pages/satellite/satellite-page.js`) use the same two forms and the same
`setView`-vs-`fitBounds` dispatch — retune the GOES full-disk or CONUS presets the same
way (capture with `mapViewportLog`, paste the center/zoom).

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
3. Mirror the interpretive metadata in `frontend/pages/satellite/satellite-engine.js`
   as a frontend fallback so static composite legends render immediately and do not
   disappear during satellite/sector/product switches or transient API/catalog failures.
4. Call the Satellite legend updater directly from the satellite page's
   control-change handlers before frame reloads.
5. Bump the `satellite.html` script query string when changing Satellite frontend
   wiring.

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

Live Radar and Satellite playback is frame scrub/poll playback from cached overlays and
tiles — not encoded video export. The previously-referenced
`/api/radar/export-animation` and `/api/satellite/export-animation` endpoints do not
exist in the current codebase.

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

Canonical product URLs are extensionless (all live, served by `routes/pages.py`):

- `/alerts`
- `/radar`
- `/satellite`
- `/spc`
- `/surface`
- `/mrms`
- `/rtma`
- `/drought`
- `/tropical`
- `/wpc`
- `/water`
- `/workspace`

`/weather.html` 307-redirects to `/workspace`.

### Standalone sidebar control pattern

Use Workspace as the visual reference for titles, labels, pills, and checkbox
rows while retaining each standalone page's own IDs and event ownership.

1. Use `Live / Settings / Archive` when a page exposes all three concepts.
   Archive may be an explicit placeholder until the workflow exists. Drought,
   WPC, and Water intentionally use `Live / Settings`; Tropical intentionally
   keeps `Live / Archive / Settings`.
2. Order Settings sections as Basemap, product opacity control(s), Cities, Map
   Overlays, then page-specific settings. Omit controls the product does not own;
   Water, for example, has no opacity control.
3. Use `.core-settings-panel`, `.core-settings-section`, `.core-check-list`, and
   `.core-check-row` rather than page-specific copies of the same typography and
   checkbox alignment.
4. Keep controls mounted and move their existing DOM nodes between panels. This
   preserves listeners and state while `sidebar-tabs.js` toggles panels.
5. Styled wrappers that must be conditionally absent need an explicit page CSS
   `[hidden] { display: none; }` rule when another display declaration would
   otherwise override the native hidden attribute.
6. Bump page CSS/JavaScript query versions when control structure, wiring, or
   visibility rules change so cached assets cannot present a mixed UI.

Radar is the intentional stateful exception within Live: Site selection reveals
Level 2/3 pills and a level-filtered Product selector. Level 3 is U.S.-only, and
elevation, storm tracks, and value inspection remain site-dependent. Satellite
uses Satellite -> Sector -> Product enablement; View appears after Sector as an
independent named map preset. Satellite changes, region changes, and Home/reset
must clear the dependent chain.

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

The Phase 27 migration removed the combined `weather.js`; do not reintroduce a shared
global state model. Common behavior lives in `frontend/core/`; each product page has a
narrow entry module (plus an engine/controller when the product is rich).

Tropical demonstrates the boundary: reuse `frontend/core/` for API helpers,
map setup, navigation, sidebar tabs, status, and legend lifecycle, while keeping
storm/archive domain behavior in `frontend/pages/tropical/`.

Tropical also uses an adaptive master-map-detail layout: Live/Archive/Settings
stay in the left sidebar, the map remains central, and one canonical System inspector
opens on the right for live or archived selections. Preserve the left subtab,
filters, list, and scroll state when opening details; collapse the inspector to
an overlay drawer on narrower viewports and invalidate the Leaflet map after
open/close layout changes.

For Tropical Live filtering, fetch the worker-cached World summary once and
filter storms locally for the selected basin. World, ATL, E PAC, and C PAC are
single-select views: choosing a pill replaces the prior selection, re-clicking
the active pill is a no-op, and the selection is never empty. Basin outlook
reads need their own response sequence so rapid pill
changes cannot render an older selection. Never auto-select the first storm;
preserve an explicitly selected storm only while its basin remains visible.
Render lightweight active-system overview markers from the same summary so
basin views do not require eager storm-detail requests; load the full
cone/track/radii package only after explicit storm selection.

Tropical Archive advisory warming is server-side and bounded. Load the selected
advisory in the foreground, then warm a five-frame neighborhood. Upgrade to a
full-storm warm only when Play expresses user intent. Run one missing advisory
at a time through the shared NHC provider budget, skip immutable cache hits,
publish JSON atomically, and coalesce rapid browser scrub actions to the latest
requested frame. Keep only the displayed advisory in the browser; expose cache
progress through a lightweight status read.

Water follows the same boundary with a single page entry module: viewport-aware
station requests, flood filtering, markers, and the station detail panel remain
page-local while map overlays, navigation, status, sidebar tabs, and legend
hosting come from `frontend/core/`.

Map-level detail panels should be children of the page's `.core-map-panel`, not
Leaflet popups or sidebar content. Match the Alerts interaction: disable map
click/scroll propagation inside the panel, support close-button and Escape
dismissal, constrain dragging to the map viewport, close on map navigation, and
invalidate outstanding detail requests when the panel closes. Retained legacy
product CSS may have higher-specificity label rules; use narrow page-scoped
selectors instead of changing shared semantics globally.

Pages using `createLegendHost()` must supply `.core-legend-header` and
`.core-legend-body` content, including a provider badge and title. A flat
`.legend-title` body bypasses the shared collapse control and is not an accepted
standalone-page legend shape.

For Tropical backend changes, follow the post-refactor ownership boundaries:

- API route declarations belong in `routes/tropical.py`.
- Route-facing cache and response behavior belongs in
  `services/tropical_service.py`.
- NHC ingestion, GTWO parsing, GIS parsing, and cache generation belong in
  `workers/tropical_worker.py`.
- Page, basin, overlay/vector, and storm-detail reads serve the most recent
  complete worker-written artifact immediately. While Tropical/Workspace is
  active, reads renew coordinator presence; the issuance registry permits only
  due advisory/GTWO checks and a conservative ten-minute special-product probe.
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
5. Product controls stay hidden until a site is selected. Level 2/3 pills filter
   the Product selector, and Level 3 is disabled outside U.S. radar sites.
6. Elevation, Storm Tracks, and Value Inspector remain hidden until a site is
   selected; Elevation is additionally hidden for Level 3 products.
