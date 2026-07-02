# NCH Weather Studio Greenfield Rewrite Plan

Created: 2026-06-30

This document is the implementation-ready plan for a clean-room rewrite of the
current dashboard as a new standalone program named `nch-weather-studio`.

The current dashboard remains the operational fallback. The rewrite must be
built in a new subdirectory under this repository first, then extracted later as
its own standalone unit when ready.

## 1. Owner Decisions Already Made

Use these decisions as fixed requirements. Do not re-litigate them during
implementation unless the owner explicitly changes direction.

- New app name: `nch-weather-studio`.
- Initial location: `F:\Python\dashboard_2026\nch-weather-studio`.
- The new directory must be extractable as a standalone app/repo later.
- Target platforms: Windows and macOS.
- macOS targets: Apple Silicon and Intel.
- Primary app type: native desktop app.
- Desktop shell: Tauri.
- Backend/runtime: bundled Python sidecar launched by Tauri.
- Frontend: React, TypeScript, and Vite.
- Map engine: MapLibre GL JS.
- Backend API: FastAPI with Pydantic models and OpenAPI.
- Python dependency/runtime tool: `uv`.
- Distribution audience: personal use first.
- Updates: manual updates.
- Docker: no Docker path for v1.
- Data source policy: free/public sources only.
- Code reuse policy: clean-room rewrite. Use the current app as the behavior
  spec, but do not copy old code or import old modules.
- Product parity bar: full parity with all current product families before
  daily cutover.
- UI policy: full UX rethink.
- Keep useful workflow concepts: map-first layout, product workspaces,
  scrubber/timeline, inspectors, legends, freshness status, cache-first
  behavior.
- Archive/history policy: redesign around a unified timeline instead of copying
  old per-product archive forms.
- Cache policy: managed rolling cache.
- Default cache budget: 100 GB to 250 GB.
- Offline/source-failure behavior: last-valid cache with explicit stale/source
  failure labels.
- Geographic policy: global-capable architecture from the start, but parity
  first. Do not delay current-dashboard parity to add worldwide replacement
  products.
- First product slice: Surface plus Alerts.

## 2. Definition Of Done

The rewrite is not daily-driver ready until every item below is true.

- The app installs and launches without a developer shell on Windows.
- The app installs and launches without a developer shell on macOS Apple
  Silicon.
- The app installs and launches without a developer shell on macOS Intel, or
  has an equivalent validated build artifact if no Intel test machine is
  available.
- The Tauri app starts the bundled Python API sidecar.
- The Tauri app stops the Python API sidecar cleanly on exit.
- The app recovers from backend crash with a readable recovery state.
- The API selects an available localhost port automatically.
- All frontend API calls use the generated TypeScript client.
- The old dashboard is not required at runtime.
- No code imports from the old dashboard.
- No product code is copied from the old dashboard.
- All public API models are typed with Pydantic.
- OpenAPI generation succeeds.
- The TypeScript API client is generated from OpenAPI.
- Surface parity is complete.
- Alerts parity is complete.
- Radar parity is complete.
- Satellite parity is complete.
- SPC parity is complete.
- RTMA parity is complete.
- MRMS parity is complete.
- Drought parity is complete.
- Tropical parity is complete.
- WPC parity is complete.
- Water parity is complete.
- Live/current products work from a cold start.
- Last-valid cache behavior works when sources fail.
- Managed cache purge works without deleting settings or the database.
- Unified timeline works for all frame/history capable products.
- Playwright smoke tests pass for all product families.
- Backend contract tests pass.
- Renderer golden-image tests pass where raster output is deterministic enough
  to compare.
- Manual cutover checklist is complete.

## 3. Non-Goals For V1

Do not implement these unless the owner explicitly revises this plan.

- Do not add Docker files.
- Do not require Docker Desktop.
- Do not require paid data sources.
- Do not require cloud hosting.
- Do not require user login.
- Do not build public-release licensing, signing, notarization, or auto-update
  infrastructure before parity.
- Do not hard-code Windows paths.
- Do not build a web-only app instead of the desktop app.
- Do not mutate the existing dashboard app while implementing the new one.
- Do not copy old dashboard modules into the new app.
- Do not create one-off frontend polling loops per product.
- Do not let any product bypass the shared product registry, scheduler,
  artifact store, or timeline unless this document is updated.

## 4. Required Technology Stack

### 4.1 Desktop

- Use Tauri v2.
- Tauri owns desktop lifecycle only.
- Tauri launches the Python backend sidecar.
- Tauri opens the React UI in the native WebView.
- Tauri provides platform packaging.
- Tauri does not contain weather-domain logic.

Reference:

- https://v2.tauri.app/develop/sidecar/

### 4.2 Frontend

- Use React.
- Use TypeScript in strict mode.
- Use Vite for development and build.
- Use MapLibre GL JS for map rendering.
- Use generated API client code only.
- Use component-level tests for shared UI.
- Use Playwright for app smoke tests.

References:

- https://vite.dev/guide/
- https://maplibre.org/maplibre-gl-js/docs/

### 4.3 Backend

- Use Python 3.12 or newer unless a scientific dependency forces 3.11.
- Use FastAPI.
- Use Pydantic v2.
- Use SQLite for local metadata and job state.
- Use filesystem artifact cache for large files.
- Use `uv` for dependency and environment management.
- Use `ruff` for lint/format checks.
- Use `pytest` for tests.

References:

- https://fastapi.tiangolo.com/features/
- https://docs.astral.sh/uv/

### 4.4 Mapping

- Use MapLibre GL JS as the main map runtime.
- Use Web Mercator for interactive map display.
- Keep product artifact metadata explicit about projection and bounds.
- Use raster image/tile layers for pre-rendered weather imagery.
- Use GeoJSON/vector layers for alerts, outlooks, stations, tracks, gauges, and
  polygons.
- Use one layer adapter API in `packages/map-runtime`.

### 4.5 Runtime Packaging

- Use native bundled runtime, not Docker.
- The Python sidecar must be bundled into the desktop app.
- App data must live in OS app-data locations, not beside installed binaries.
- Manual update means the owner installs a new version intentionally.

## 5. Repository Layout

Create this directory tree when implementation starts:

```text
nch-weather-studio/
  README.md
  pyproject.toml
  package.json
  pnpm-workspace.yaml or npm workspaces config
  apps/
    api/
      pyproject.toml
      src/
        nch_api/
          __init__.py
          main.py
          app.py
          settings.py
          routes/
          events/
          errors.py
      tests/
    web/
      package.json
      index.html
      src/
        main.tsx
        app/
        products/
        map/
        timeline/
        settings/
        generated/
      tests/
    desktop/
      package.json
      src-tauri/
        tauri.conf.json
        Cargo.toml
        src/
  packages/
    contracts/
      package.json
      openapi/
      src/
    ui/
      package.json
      src/
    map-runtime/
      package.json
      src/
  weather_core/
    pyproject.toml
    src/
      weather_core/
        __init__.py
        registry/
        products/
        sources/
        rendering/
        artifacts/
        scheduler/
        storage/
        settings/
        diagnostics/
    tests/
  docs/
    architecture.md
    implementation-plan.md
    product-parity-matrix.md
    source-policy.md
    packaging.md
    test-plan.md
  tests/
    fixtures/
    contract/
    integration/
```

Rules:

- `apps/api` assembles the API but does not contain product algorithms.
- `weather_core` contains source adapters, product modules, registry,
  rendering, scheduler, artifacts, and storage.
- `apps/web` contains app UI only.
- `packages/contracts` owns generated TypeScript API types and client code.
- `packages/map-runtime` owns all MapLibre layer add/update/remove behavior.
- `packages/ui` owns reusable React controls.
- `apps/desktop` owns Tauri lifecycle and packaging only.

## 6. Current Dashboard Product Families To Match

The new app must support these product families before daily cutover:

- Surface
- Alerts
- Radar
- Satellite
- SPC
- RTMA
- MRMS
- Drought
- Tropical
- WPC
- Water

Each family must have:

- Product registry entries.
- Source adapter or source adapters.
- Live/current behavior.
- Cache behavior.
- Last-valid fallback where meaningful.
- Legend support.
- Inspector support where meaningful.
- Timeline support where meaningful.
- Playwright smoke test.
- API contract test.
- Product parity checklist.

## 7. Core Architecture

### 7.1 Runtime Startup

Startup sequence:

1. User launches the Tauri app.
2. Tauri finds an available localhost port.
3. Tauri starts the bundled Python sidecar with the selected port and app-data
   path.
4. Python API initializes settings, SQLite, artifact paths, product registry,
   scheduler, and event bus.
5. Python API exposes `/api/health`.
6. Python API exposes `/api/runtime/ready`.
7. Tauri waits until `/api/runtime/ready` returns ready.
8. Tauri loads the frontend.
9. Frontend requests `/api/products`.
10. Frontend connects to `/api/events`.
11. Frontend renders the map-first workspace.

Shutdown sequence:

1. User closes app.
2. Tauri sends graceful shutdown request to API.
3. API cancels or pauses running background jobs.
4. API flushes SQLite writes.
5. API closes event streams.
6. API exits.
7. Tauri kills the sidecar only if graceful shutdown times out.

### 7.2 App Data Locations

Do not write runtime cache into the install directory.

Use a platform app-data resolver.

Expected layout:

```text
NCH Weather Studio app data/
  settings.json
  nch-weather-studio.sqlite3
  logs/
  cache/
    artifacts/
    source/
    temp/
  exports/
  diagnostics/
```

The app-data resolver must support:

- Windows user app data.
- macOS application support.
- Override path for development.
- Override path for tests.

### 7.3 SQLite Storage

Use SQLite in WAL mode.

Minimum tables:

```text
settings
  key text primary key
  value_json text not null
  updated_at text not null

products
  product_id text primary key
  family text not null
  label text not null
  enabled integer not null
  updated_at text not null

sources
  source_id text primary key
  label text not null
  base_url text
  last_success_at text
  last_failure_at text
  last_error_code text
  last_error_message text

artifacts
  artifact_id text primary key
  product_id text not null
  layer_id text not null
  valid_time text
  created_at text not null
  source_time text
  source_id text
  stale_state text not null
  media_type text not null
  local_path text not null
  public_url text not null
  bounds_west real
  bounds_south real
  bounds_east real
  bounds_north real
  projection text
  size_bytes integer not null
  cache_key text not null
  metadata_json text not null

timeline_frames
  frame_id text primary key
  product_id text not null
  layer_id text not null
  valid_time text not null
  artifact_id text
  source_id text
  status text not null
  metadata_json text not null

jobs
  job_id text primary key
  job_type text not null
  product_id text
  status text not null
  priority integer not null
  dedupe_key text
  progress_current integer
  progress_total integer
  message text
  error_code text
  error_message text
  created_at text not null
  started_at text
  finished_at text
  payload_json text not null

job_events
  event_id text primary key
  job_id text not null
  event_type text not null
  created_at text not null
  message text
  payload_json text not null

cache_entries
  cache_key text primary key
  artifact_id text
  product_id text
  cache_class text not null
  size_bytes integer not null
  last_accessed_at text not null
  created_at text not null
  expires_at text
```

Migration rules:

- Use explicit migrations.
- Never delete user settings during migration.
- Tests must verify migration from empty database.

### 7.4 Product Registry

Every product must be declared through a registry.

Minimum product definition:

```text
ProductDefinition
  id
  family
  label
  description
  geographic_scope
  default_view
  layer_types
  supported_modes
  source_adapters
  polling_policy
  retention_policy
  render_recipes
  legend_schema
  inspector_schema
  timeline_policy
  settings_schema
```

Allowed `layer_types`:

- `raster-image`
- `raster-tile`
- `vector-geojson`
- `point-markers`
- `track-lines`
- `symbol-layer`
- `heatmap`

Allowed `supported_modes`:

- `live`
- `timeline`
- `archive`
- `inspect`
- `export`

Rules:

- The frontend product navigation is populated from registry data.
- Product UI controls are driven by registry metadata where practical.
- Product modules may define custom UI panels, but must still use shared
  registry, layer, artifact, timeline, and event contracts.
- Product families may not create private cache systems outside the artifact
  store.

### 7.5 Source Adapters

Use source adapters for public weather data providers.

Source adapter responsibilities:

- Build request URLs.
- Send requests with app user agent.
- Parse response.
- Normalize response into internal models.
- Record source success/failure.
- Return typed source payloads.
- Never write UI-specific artifacts.

Required source adapter behavior:

- Timeout.
- Retry policy.
- Rate-conscious scheduling.
- User-agent string.
- Clear error codes.
- Fixture capture support for tests.
- Last-success metadata update.

Free/public source categories expected:

- NWS API.
- NOAA public buckets.
- NOAA/NODD sources.
- IEM sources.
- NDBC.
- CO-OPS.
- WPC public feeds.
- SPC public feeds.
- NHC/NWS tropical public feeds.
- US Drought Monitor public data where applicable.

### 7.6 Artifact Store

All generated or downloaded display files must be artifacts.

Artifact types:

- GeoJSON.
- JSON metadata.
- PNG.
- WebP.
- JPEG.
- Vector tile if added later.
- Animation export if added later.

Artifact path shape:

```text
cache/artifacts/
  {family}/
    {product_id}/
      {layer_id}/
        {yyyy}/
          {mm}/
            {dd}/
              {cache_key}/
                artifact.ext
                metadata.json
```

Artifact metadata must include:

- Product id.
- Layer id.
- Valid time.
- Created time.
- Source id.
- Source time if known.
- Bounds in west/south/east/north.
- Projection.
- Media type.
- Units if applicable.
- Legend id if applicable.
- Stale state.
- Cache key.
- Source URLs or source identifiers where safe to store.

### 7.7 Scheduler And Jobs

The app owns scheduling. Do not depend on Windows Task Scheduler, launchd, cron,
or Docker.

Job types:

- `poll-source`
- `render-artifact`
- `warm-cache`
- `backfill-timeline`
- `export-animation`
- `purge-cache`
- `diagnostics`

Job status:

- `queued`
- `running`
- `succeeded`
- `failed`
- `canceled`
- `skipped`

Scheduler requirements:

- Run only inside the Python sidecar.
- Pause cleanly on shutdown.
- Resume pending jobs on startup.
- Dedupe jobs by `dedupe_key`.
- Limit concurrent CPU-heavy render jobs.
- Limit concurrent network-heavy poll jobs.
- Emit job events over `/api/events`.
- Keep logs per job.
- Support manual job trigger from the UI.

### 7.8 Event Stream

Use Server-Sent Events for v1.

Endpoint:

```text
GET /api/events
```

Events:

```text
runtime.ready
runtime.warning
source.updated
source.failed
product.updated
artifact.ready
timeline.updated
job.updated
cache.purged
settings.updated
```

Rules:

- Events are hints, not the source of truth.
- UI should refetch affected resources after receiving an event.
- Event payloads must be small.
- The API must tolerate disconnected clients.

## 8. Public API Contract

Implement generic product APIs first.

### 8.1 Runtime

```text
GET /api/health
GET /api/runtime/ready
GET /api/runtime/diagnostics
```

`/api/health` returns:

```json
{
  "ok": true,
  "service": "nch-weather-studio-api",
  "version": "0.1.0"
}
```

`/api/runtime/ready` returns:

```json
{
  "ready": true,
  "database": "ready",
  "artifact_store": "ready",
  "scheduler": "ready",
  "products_loaded": 11
}
```

### 8.2 Products

```text
GET /api/products
GET /api/products/{product_id}
GET /api/products/{product_id}/layers
GET /api/products/{product_id}/legend
GET /api/products/{product_id}/frames
GET /api/products/{product_id}/timeline
GET /api/products/{product_id}/inspect?lat={lat}&lon={lon}
```

Rules:

- `GET /api/products` returns all enabled product definitions.
- Product definitions must be stable enough for frontend navigation.
- `frames` returns the current frame list for the active timeline window.
- `timeline` returns availability metadata for the selected product/layers.
- `inspect` returns the best product-specific information for a map location.

### 8.3 Artifacts

```text
GET /api/artifacts/{artifact_id}
GET /api/artifacts/{artifact_id}/metadata
```

Rules:

- Large files stream from disk.
- Metadata endpoint returns JSON.
- Missing artifact returns 404 with diagnostic code.
- Stale artifact still returns 200 if it is the last valid artifact and the
  caller requested last-valid behavior.

### 8.4 Jobs

```text
POST /api/jobs
GET /api/jobs/{job_id}
POST /api/jobs/{job_id}/cancel
GET /api/jobs?product_id={product_id}&status={status}
```

Allowed job request shape:

```json
{
  "job_type": "poll-source",
  "product_id": "surface.current",
  "priority": 50,
  "payload": {}
}
```

Rules:

- Job creation must validate job type and product support.
- Duplicate active jobs with the same `dedupe_key` should return the existing
  active job rather than enqueueing duplicates.
- Long-running jobs must update progress.

### 8.5 Settings And Cache

```text
GET /api/settings
PATCH /api/settings
GET /api/cache/status
POST /api/cache/purge
POST /api/cache/recalculate
```

Settings must include:

- App-data path.
- Cache budget.
- Per-product cache policy overrides.
- Enabled products.
- Default region.
- Default map theme.
- Timeline default lookback.
- Concurrency limits.

Cache purge modes:

- `expired-only`
- `product`
- `all-artifacts`
- `temporary`

Never purge:

- Settings.
- SQLite database.
- Logs unless user explicitly requests log purge.
- User exports.

## 9. Frontend UX Plan

The UI should be a redesigned operational workstation, not a copy of the
current page.

### 9.1 Main Layout

Use a map-first interface:

```text
top app bar
left product/workflow panel
center MapLibre map
right inspector/details panel
bottom unified timeline
floating legend/freshness controls
```

Required behaviors:

- Product switching does not reload the whole app.
- Map stays stable when switching products unless the product has an explicit
  default-view action.
- Layer visibility and opacity are always visible or one click away.
- Freshness/source state is always visible for active layers.
- Timeline remains available for products with frame history.
- Inspector updates on map click or hover depending on product settings.

### 9.2 Product Navigation

Navigation groups:

- Current Conditions
- Hazards
- Radar
- Satellite
- Analysis
- Forecast
- Tropical
- Water

Product entries:

- Surface
- Alerts
- Radar
- Satellite
- SPC
- RTMA
- MRMS
- Drought
- Tropical
- WPC
- Water

Rules:

- Navigation data comes from `/api/products`.
- Product entries show status: live, stale, source failing, disabled.
- Product route state is reflected in the URL inside the desktop WebView.

### 9.3 Unified Timeline

Timeline modes:

- `live`: newest valid frame.
- `history`: browse cached timeline frames.
- `backfill`: request missing time range where supported.

Timeline controls:

- Play/pause.
- Step back.
- Step forward.
- Speed.
- Time range.
- Frame count.
- Valid time label.
- Source/freshness label.
- Product/layer availability markers.

Rules:

- Do not show `0/0` as a normal state.
- Show "No cached frames", "Loading frames", "Rendering frame", or "Source
  unavailable" instead.
- Timeline gaps must be visible.
- Product-specific scrubbers are not allowed unless they wrap the shared
  timeline component.

### 9.4 Inspector

Inspector behavior:

- Map click opens or updates inspector.
- Inspector content is product-specific but schema-driven.
- Inspector shows source and valid time when relevant.
- Inspector supports loading, empty, stale, and error states.
- Inspector should not block map interaction.

### 9.5 Legends

Legend types:

- Categorical.
- Continuous colorbar.
- Interpretive.
- Symbol/icon.
- Mixed.

Rules:

- Legends come from API where possible.
- Frontend may include fallback static legends only if documented in product
  registry.
- RGB satellite composites use interpretive legends.
- Legends must handle wrapping without overlapping swatches or labels.

### 9.6 Settings UI

Settings sections:

- Runtime.
- Cache.
- Products.
- Sources.
- Map.
- Diagnostics.

Minimum settings:

- Cache budget.
- Cache location.
- Product enable/disable.
- Default region/view.
- Polling intensity: conservative, normal, aggressive.
- Render concurrency.
- Clear expired cache.
- Export diagnostics bundle.

## 10. Product Implementation Details

### 10.1 Surface

Parity requirements:

- Current station observations.
- Products:
  - Temperature.
  - Feels Like.
  - Dew Point.
  - Relative Humidity.
  - Wind Speed.
  - Wind Gust.
  - Altimeter.
  - MSLP.
  - Visibility.
- Station markers.
- Value labels.
- Wind barbs or wind direction indicator where parity requires.
- Gradient/raster surface overlay where parity requires.
- Region/default view support.
- Station inspector.
- Legends for colored values/gradients.
- Last-valid cache.

Implementation notes:

- Use source adapters for public station data.
- Normalize units immediately.
- Store raw source payload separately from display artifacts.
- Surface product selection must not require page reload.

Acceptance:

- Cold start fetches and renders stations.
- Source failure shows last-valid station set with stale label.
- Product switch updates marker styling and legend.
- Inspector shows station details and valid time.

### 10.2 Alerts

Parity requirements:

- Active NWS alert polygons.
- Alert category filtering.
- Alert detail inspector.
- WWA/list equivalent if redesigned UI includes alert list.
- Local storm reports if current parity matrix includes them.
- Alert styling by severity/event category.
- Last-valid alert cache.

Implementation notes:

- Keep full-geometry and display-geometry concepts if needed for performance.
- Do not close alert detail immediately after opening from map click.
- Alert layer should be vector GeoJSON in MapLibre.

Acceptance:

- Active alerts render by polygon.
- Clicking polygon opens details.
- Filters update visible alerts.
- Source failure keeps last-valid alerts with stale/source-failure label.

### 10.3 Radar

Parity requirements:

- Radar site catalog.
- Site markers.
- Live radar products.
- Level II products:
  - Reflectivity.
  - Velocity.
  - Spectrum width.
  - ZDR.
  - Correlation coefficient.
  - Differential phase.
  - Storm-relative velocity.
- Level III products:
  - Reflectivity.
  - Velocity.
  - Storm-relative velocity.
  - ZDR.
  - Correlation coefficient.
  - KDP.
  - Hydrometeor classification.
  - Digital precipitation rate.
  - One-hour accumulation.
  - Storm-total precipitation.
  - Echo tops.
  - VIL.
- Elevation selection.
- Radar color tables and legends.
- Radar value inspector.
- Storm attributes/tracks.
- Hail/mesocyclone/TVS/storm-cell symbology.
- Selected-cell SRV.
- Timeline playback.
- Latest-frame first cold start.
- History warmup.

Implementation notes:

- Product catalog must drive available products and metadata.
- Cache key for selected-cell SRV must include site, product, elevation, storm
  cell identity, motion speed, motion direction, and motion source.
- Hiding storm-track overlay must not clear selected-cell SRV state.
- On cold cache, render newest frame first, then backfill history.
- Use golden-image tests for stable render paths.

Acceptance:

- Radar latest frame appears quickly on cold cache.
- Timeline playback works without stale counters.
- Value inspector returns product-appropriate value.
- Storm track toggle does not break selected-cell SRV animation.
- Legends match product metadata.

### 10.4 Satellite

Parity requirements:

- GOES platform support needed for current parity.
- Product/sector/platform controls redesigned around:
  - Region.
  - Platform.
  - Sector.
  - Product.
- Visible products.
- IR products.
- Water vapor products.
- RGB composites currently exposed in the dashboard:
  - Fire Temperature.
  - Air Mass.
  - Day Cloud Phase.
  - Day Land Cloud/Fire.
  - Day Snow/Fog.
  - Nighttime Microphysics.
  - Dust.
  - Ash.
  - Sulfur Dioxide.
- Scalar legends for scalar products.
- Interpretive legends for RGB products.
- Tile or image artifact serving.
- Timeline playback.
- On-demand render.
- Managed prewarm.

Implementation notes:

- Build a global-capable platform/sector/product registry from the start.
- Do not make GOES assumptions impossible to replace later.
- Keep runtime request max zoom/extent separate from worker prewarm scopes.
- Full Disk, CONUS, and mesoscale sectors must have explicit bounds and
  projection metadata.
- Add Himawari/Meteosat extension points but do not delay parity to implement
  them.

Acceptance:

- GOES products render in MapLibre.
- Composite legends do not disappear on product switches.
- Cache miss can render on demand.
- Timeline can play cached frames.
- Tile cache purge does not remove source catalogs or settings.

### 10.5 SPC

Parity requirements:

- Convective outlooks.
- Fire outlooks.
- Other SPC products currently supported.
- Day selection.
- Hazard selection.
- Reports.
- Active products.
- Legends.
- Inspector/details.
- Last-valid cache.

Implementation notes:

- Replace old multi-dropdown quirks with a clean product-group model.
- Preserve product availability and no-area states.

Acceptance:

- Day 1 categorical renders.
- Fire products render.
- Reports render/filter.
- Empty/no-area states are clear.

### 10.6 RTMA

Parity requirements:

- Hourly stream.
- Rapid-update stream.
- Regions equivalent to current dashboard:
  - CONUS.
  - AK.
  - HI.
  - PR.
- Products:
  - Temperature.
  - Feels Like.
  - Dew Point.
  - Surface Pressure.
  - Wind Speed.
  - Wind Gust.
  - Wind Direction.
  - Visibility.
  - Total Cloud Cover.
  - 24-hour Temperature Change where supported.
- Frame-locked points.
- Raster overlays.
- Timeline playback.
- Last-valid cache.

Implementation notes:

- Feels Like is one derived product.
- Derived products must compute from synchronized frame-level fields.
- Do not assume derived products map to one native source variable.
- 24-hour temperature change constraints must be explicit.

Acceptance:

- Feels Like works live and in timeline playback.
- Worker/prewarm coverage includes UI-exposed products.
- Points and raster are locked to the same source frame.
- Source failure shows last-valid frame where available.

### 10.7 MRMS

Parity requirements:

- MRMS product registry.
- Product groups equivalent to current dashboard.
- Live/on-demand rendering.
- Timeline playback.
- Archive/backfill through unified timeline.
- Legends and color maps.
- Last-valid cache.

Implementation notes:

- Follow radar-like progressive frame loading.
- Do not time-step without actual frames.
- Store product, valid time, bounds, units, and source in every frame metadata.

Acceptance:

- Default MRMS product renders on cold start.
- Product group switches work.
- Timeline appends frames progressively.
- Missing source data has a clear state.

### 10.8 Drought

Parity requirements:

- Drought product catalog.
- Available dates.
- Drought map layer.
- State statistics.
- Inspector/details where current parity requires.
- Last-valid cache.

Implementation notes:

- Store date availability in timeline model where practical.
- Keep state stats separate from display layer artifacts.

Acceptance:

- Latest drought layer renders.
- Date selection works through timeline/history.
- State stats load and show source/freshness.

### 10.9 WPC

Parity requirements:

- Excessive Rainfall Outlook Days 1-3.
- QPF 6-hour products.
- QPF 24-hour products.
- QPF multi-day products through Day 7.
- Winter weather products.
- Five-Day River Flood Outlook.
- Active MPDs if current parity matrix requires.
- Surface Analysis.
- Surface Forecast.
- Significant Weather products if currently accepted.
- WPC-authored no-significant-area overlays.
- Legends.
- Last-valid cache.

Implementation notes:

- Treat KML/KMZ/PNG products as source payloads converted into internal
  artifacts.
- Preserve source-unavailable versus no-area-issued distinction.
- Surface PNG products need bounds metadata.

Acceptance:

- ERO renders.
- QPF products render.
- Winter products render.
- Surface analysis/forecast renders.
- Source unavailable state can display last-valid WPC data.

### 10.10 Tropical

Parity requirements:

- Active storms.
- Basins.
- Summary.
- Storm detail.
- Advisory/fix timeline.
- Forecast track/cone/GIS overlays.
- Official products/graphics.
- Archive catalog.
- Archive storm detail.
- Advisory browsing.
- Floater/imagery behavior where current app supports it.
- Inspector.

Implementation notes:

- Architecture must support global tropical basins.
- Rich Tropical UI is allowed, but map layers and timeline must still use
  shared runtime contracts.
- Missing upstream graphics must show unavailable state.
- Do not break map lifecycle with product-specific global state.

Acceptance:

- Active storms load by basin.
- Storm click opens detail.
- Archive storm can be browsed.
- GIS layers toggle independently.
- Advisory timeline works.

### 10.11 Water

Parity requirements:

- River gauges.
- CO-OPS coastal stations.
- NDBC stations.
- Viewport/bbox filtering.
- Network filters.
- River flood filter:
  - All.
  - Action+.
  - Minor+.
  - Moderate+.
  - Major.
- Gauge detail enrichment.
- CO-OPS live enrichment.
- NDBC grouped readings.
- Stage gauge bar.
- Distinct station styles.
- Last-valid cache.

Implementation notes:

- Prevent invalid bbox behavior at world view.
- Manage marker density for global-capable map views.
- Keep river, coastal, and buoy station details typed separately.

Acceptance:

- Stations render for current viewport.
- Network filters work.
- River flood filter works.
- Gauge click enriches details.
- Source failure keeps last-valid station cache.

## 11. Unified Timeline And Archive Design

The old archive model is not copied. Replace it with a unified timeline.

### 11.1 Timeline Concepts

Definitions:

- `valid_time`: the meteorological valid time.
- `source_time`: when upstream data was issued or observed.
- `created_at`: when the app created the artifact.
- `frame`: one product/layer display state at one valid time.
- `timeline window`: selected time range shown to the user.

Timeline states:

- `available`: artifact exists.
- `missing`: no known artifact.
- `rendering`: job is running.
- `source-unavailable`: source was checked and unavailable.
- `stale`: last-valid artifact is older than freshness policy.

### 11.2 Timeline UI Requirements

The bottom timeline must show:

- Current selected valid time.
- Frame count for active product/layer.
- Availability markers.
- Play/pause.
- Step controls.
- Speed control.
- Time range selector.
- Backfill/request button where supported.
- Stale/source status.

### 11.3 Backfill

Backfill request:

```json
{
  "job_type": "backfill-timeline",
  "product_id": "radar.live",
  "payload": {
    "start_time": "2026-06-30T00:00:00Z",
    "end_time": "2026-06-30T03:00:00Z",
    "layers": ["reflectivity"]
  }
}
```

Rules:

- Validate max backfill span by product.
- Backfill must not freeze the UI.
- Backfill emits job events.
- Backfill writes timeline availability as it progresses.

## 12. Cache And Retention Plan

Default total budget:

- Minimum default: 100 GB.
- Maximum default: 250 GB.
- Setup/settings UI may let owner choose exact value.

Retention classes:

- `critical-last-valid`: keep newest usable artifact for each active layer.
- `live-recent`: recent operational frames.
- `timeline-history`: cached history frames.
- `source-raw`: downloaded raw source files.
- `temp`: safe to delete anytime.
- `exports`: never delete automatically.

Default priority order when purging:

1. Delete temp files.
2. Delete failed partial artifacts.
3. Delete oldest source-raw files that have rendered artifacts.
4. Delete oldest timeline-history frames outside active retention.
5. Delete live-recent frames beyond product retention.
6. Preserve critical-last-valid unless owner explicitly purges all artifacts.

Product-specific initial retention targets:

- Surface: keep last-valid plus 24-72 hours of recent station snapshots.
- Alerts: keep last-valid plus recent alert history.
- Radar: keep recent frames by site/product, product-tuned by size.
- Satellite: keep recent frames/tiles by platform/sector/product, product-tuned
  by size.
- RTMA: keep recent hourly and rapid-update frames within product policy.
- MRMS: keep recent frames within product policy.
- SPC/WPC/Drought: keep current products and useful recent history.
- Tropical: keep active storm data, current graphics, and selected archive
  artifacts.
- Water: keep station cache and last-valid detail enrichments.

## 13. Error Handling And Diagnostics

Every user-visible error must have:

- Short message.
- Product/source context.
- Recommended user action if available.
- Diagnostic code.
- Log entry.

Diagnostic code examples:

- `SOURCE_TIMEOUT`
- `SOURCE_HTTP_ERROR`
- `SOURCE_PARSE_ERROR`
- `ARTIFACT_MISSING`
- `RENDER_FAILED`
- `JOB_CANCELED`
- `CACHE_BUDGET_EXCEEDED`
- `BACKEND_NOT_READY`

Diagnostics UI must include:

- API status.
- Scheduler status.
- Database status.
- Cache usage.
- Recent source failures.
- Recent failed jobs.
- Export diagnostics bundle.

## 14. Testing Strategy

### 14.1 Backend Tests

Required:

- Product registry loading.
- Product registry validation.
- Source adapter URL construction.
- Source adapter fixture parsing.
- Artifact metadata creation.
- Cache key stability.
- Cache purge behavior.
- Last-valid lookup.
- SQLite migrations.
- Job dedupe.
- Scheduler resume.
- API endpoint contract tests.
- OpenAPI generation.

### 14.2 Frontend Tests

Required:

- Product navigation renders from API data.
- Map runtime adds/removes raster layer.
- Map runtime adds/removes vector layer.
- Timeline state transitions.
- Legend rendering for categorical, continuous, interpretive, and symbol
  legends.
- Inspector loading/empty/error/success states.
- Settings cache budget form.

### 14.3 Playwright Smoke Tests

For each product family:

1. Launch app.
2. Open product.
3. Confirm map renders.
4. Confirm product controls render.
5. Enable default layer.
6. Confirm layer appears.
7. Confirm legend appears where applicable.
8. Click map or feature.
9. Confirm inspector updates.
10. Confirm freshness/source status appears.
11. If timeline-supported, play at least three frames or verify no-frame state.

### 14.4 Renderer Tests

Use fixture data for deterministic rendering.

Required checks:

- Output file exists.
- Output dimensions are correct.
- Bounds metadata is correct.
- Transparent background behavior is correct where expected.
- Legend metadata matches product.
- Pixel comparison passes tolerance where stable.

### 14.5 Offline And Failure Tests

Simulate:

- No internet.
- Source timeout.
- Source returns invalid payload.
- Source returns no data.
- Cache empty.
- Cache contains stale last-valid data.
- Disk budget exceeded.
- Backend restart during job.

Acceptance:

- App never shows a blank unexplained state.
- Last-valid data appears when available.
- Stale labels are visible.
- User can recover without editing files manually.

### 14.6 Desktop Lifecycle Tests

Required:

- Tauri launches sidecar.
- Tauri detects readiness.
- Tauri handles port conflict.
- Tauri shuts down sidecar.
- Tauri shows recovery state if sidecar crashes.
- App restart preserves settings.
- App restart preserves artifact database.

## 15. Implementation Phases

Do phases in order. Do not begin a later product family until the acceptance
checks for the current phase are satisfied.

### Phase 0: Toolchain And Empty App

Tasks:

1. Create `nch-weather-studio/`.
2. Initialize `apps/web` with Vite React TypeScript.
3. Initialize `apps/api` with FastAPI.
4. Initialize `weather_core` as a Python package.
5. Initialize `apps/desktop` with Tauri.
6. Add workspace scripts.
7. Add basic README.
8. Add architecture docs.

Acceptance:

- API starts.
- Web app starts.
- Desktop app launches.
- Desktop app can connect to API.
- Blank MapLibre map renders.

### Phase 1: Core Contracts And Storage

Tasks:

1. Define Pydantic API models.
2. Define OpenAPI generation command.
3. Generate TypeScript client.
4. Add SQLite connection and migrations.
5. Add settings storage.
6. Add artifact store.
7. Add product registry skeleton.
8. Add job model.
9. Add event stream skeleton.

Acceptance:

- `/api/health` works.
- `/api/runtime/ready` works.
- `/api/products` returns demo product.
- TypeScript client builds.
- SQLite database initializes.

### Phase 2: UI Shell And Map Runtime

Tasks:

1. Build map-first shell.
2. Add product navigation.
3. Add left product panel.
4. Add right inspector panel.
5. Add bottom timeline.
6. Add legend panel.
7. Add freshness/status display.
8. Add MapLibre layer adapter.
9. Add demo vector and raster layers.

Acceptance:

- Demo vector layer renders.
- Demo raster layer renders.
- Layer visibility works.
- Layer opacity works.
- Timeline demo frames work.
- Inspector demo works.

### Phase 3: Surface Plus Alerts

Tasks:

1. Implement Surface source adapter.
2. Implement Surface product registry.
3. Implement Surface artifacts.
4. Implement Surface inspector.
5. Implement Surface legends.
6. Implement Alerts source adapter.
7. Implement Alerts product registry.
8. Implement Alerts vector artifacts.
9. Implement Alerts inspector.
10. Implement first real product Playwright tests.

Acceptance:

- Surface and Alerts are usable from cold start.
- Last-valid cache works for both.
- This phase proves the new architecture with real data.

### Phase 4: Timeline And Archive Foundation

Tasks:

1. Implement timeline database table.
2. Implement timeline API.
3. Implement backfill job API.
4. Implement timeline UI states.
5. Add frame availability markers.
6. Add no-frame, loading, rendering, stale, and source-failed states.

Acceptance:

- Surface/Alerts or demo product can use timeline where applicable.
- Timeline does not show misleading `0/0`.
- Backfill job events update UI.

### Phase 5: Radar

Tasks:

1. Implement radar source adapters.
2. Implement site catalog.
3. Implement product catalog.
4. Implement render pipeline.
5. Implement latest-frame first behavior.
6. Implement timeline playback.
7. Implement inspector.
8. Implement storm tracks/attributes.
9. Implement selected-cell SRV.
10. Implement radar tests.

Acceptance:

- Radar parity checklist passes.

### Phase 6: Satellite

Tasks:

1. Implement global-capable satellite registry.
2. Implement GOES parity.
3. Implement sectors.
4. Implement products.
5. Implement scalar legends.
6. Implement interpretive RGB legends.
7. Implement tile/image artifacts.
8. Implement timeline playback.
9. Implement cache/prewarm policy.

Acceptance:

- Satellite parity checklist passes.

### Phase 7: RTMA And MRMS

Tasks:

1. Implement RTMA source and render pipeline.
2. Implement RTMA derived products.
3. Implement RTMA points and overlays.
4. Implement RTMA timeline playback.
5. Implement MRMS source and render pipeline.
6. Implement MRMS product groups.
7. Implement MRMS timeline playback.

Acceptance:

- RTMA parity checklist passes.
- MRMS parity checklist passes.

### Phase 8: SPC, WPC, Drought

Tasks:

1. Implement SPC products and reports.
2. Implement WPC products.
3. Implement Drought products.
4. Add legends and inspectors.
5. Add timeline/history where applicable.

Acceptance:

- SPC parity checklist passes.
- WPC parity checklist passes.
- Drought parity checklist passes.

### Phase 9: Tropical

Tasks:

1. Implement tropical basin registry.
2. Implement active storms.
3. Implement storm details.
4. Implement advisory/fix timeline.
5. Implement GIS layers.
6. Implement official products/graphics.
7. Implement archive catalog.
8. Implement floater/imagery parity where supported.

Acceptance:

- Tropical parity checklist passes.

### Phase 10: Water

Tasks:

1. Implement river gauges.
2. Implement CO-OPS stations.
3. Implement NDBC stations.
4. Implement viewport filtering.
5. Implement network filters.
6. Implement flood filters.
7. Implement gauge/detail enrichment.
8. Implement stage gauge bar.

Acceptance:

- Water parity checklist passes.

### Phase 11: Packaging

Tasks:

1. Bundle Python sidecar.
2. Build Windows installer.
3. Build macOS Apple Silicon installer.
4. Build macOS Intel installer.
5. Add startup diagnostics.
6. Add logs viewer/export.
7. Add reset cache action.
8. Add reset app state action.

Acceptance:

- Fresh install works on all target platforms.
- No developer shell is required.
- No Docker is required.

### Phase 12: Cutover Readiness

Tasks:

1. Complete product parity matrix.
2. Run all automated tests.
3. Run manual product smoke.
4. Run offline/source-failure smoke.
5. Run cache purge smoke.
6. Run restart smoke.
7. Document known limitations.
8. Decide whether to retire or keep current dashboard.

Acceptance:

- Owner can use `nch-weather-studio` as daily dashboard.

## 16. Product Parity Matrix Template

Create `nch-weather-studio/docs/product-parity-matrix.md` with this shape:

```text
Product family:
Current dashboard behavior:
New app behavior:
Live/current:
Timeline/history:
Inspector:
Legend:
Cache:
Last-valid fallback:
Tests:
Manual smoke:
Known gaps:
Cutover status:
```

Every product family must be marked `Cutover status: passed` before daily
cutover.

## 17. AI Implementer Rules

Any AI or engineer implementing this plan must follow these rules:

1. Work only in `F:\Python\dashboard_2026\nch-weather-studio` unless the owner
   explicitly says otherwise.
2. Do not edit the old dashboard while implementing the rewrite.
3. Read this document before starting each session.
4. Read the current dashboard docs only as behavior reference.
5. Do not import from the old dashboard.
6. Do not copy old code.
7. Create small, reviewable phases.
8. Validate each phase before moving on.
9. Keep product parity matrix updated.
10. Keep architecture docs updated.
11. Do not invent a private API for one product if the generic product API can
    handle it.
12. Do not add Docker.
13. Do not add paid-source dependencies.
14. Do not hard-code machine-specific paths.
15. Do not make browser-visible claims without browser or Playwright evidence.
16. If browser/desktop validation is blocked, state exactly what was validated
    and what remains pending.

## 18. First Implementation Session Checklist

When implementation begins, do exactly this:

1. Confirm current working directory is `F:\Python\dashboard_2026`.
2. Confirm `docs/nch-weather-studio-greenfield-plan.md` exists.
3. Create a new branch if requested by the owner.
4. Create `nch-weather-studio/`.
5. Add `nch-weather-studio/README.md`.
6. Add `nch-weather-studio/docs/architecture.md`.
7. Add `nch-weather-studio/docs/product-parity-matrix.md`.
8. Initialize the empty API app.
9. Initialize the empty web app.
10. Initialize the empty desktop app.
11. Add a blank MapLibre map.
12. Add a minimal `/api/health`.
13. Add a minimal desktop sidecar launch.
14. Validate local API start.
15. Validate local web start.
16. Validate desktop launch.
17. Stop all dev servers before ending the session unless the owner asks to
    keep them running.

## 19. Open Risks

- Scientific/geospatial dependencies may complicate bundled Python packaging on
  macOS and Windows.
- MapLibre raster overlay behavior must be proven early for radar/satellite
  parity.
- Clean-room rewrite will take longer than porting stable old modules.
- Global-capable architecture increases upfront design work.
- Full parity across all products is large; phases must stay narrow and
  validated.
- Public-source availability and feed shape can change over time.
- Tauri sidecar packaging must be tested on real target machines.

## 20. Recommended Early Prototypes

Do these before committing to deeper product implementation:

1. Tauri launches Python sidecar and shuts it down cleanly.
2. MapLibre displays a transparent raster weather overlay with bounds.
3. MapLibre displays alert-style polygons with click inspector.
4. Unified timeline displays fake frame availability and plays frames.
5. Artifact store serves local PNG and GeoJSON files through FastAPI.
6. SQLite survives restart and stores artifact metadata.
7. Cache purge deletes only safe artifacts.

If any prototype fails, update this plan before continuing.

