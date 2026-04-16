# Unified Weather Workflow Roadmap

Status: Authoritative implementation roadmap for the weather.html migration.
Date: 2026-04-04

## Objective

Build one unified workflow for surface, alerts, MRMS, and SPC in:

- weather.html
- js/weather.js
- /api/weather
- /api/weather/export-frame
- /api/weather/export-animation

Keep Radar and Satellite as separate workflows and pages.

Legacy product workflows (surface, alerts, mrms, spc) are reference-only during implementation. They are not runtime dependencies for the new weather workflow.

Lightning is out of scope and omitted from this roadmap.

## Locked Product Decisions

1. One frontend page: weather.html.
2. One orchestrating endpoint: /api/weather.
3. Two export endpoints:
   - /api/weather/export-frame
   - /api/weather/export-animation
4. Lambert-only projection policy for unified weather rendering.
5. Current and archive both support layered output.
6. Archive range mode is scrubber-first and export-on-demand.
7. New weather outputs/caches use separate weather-scoped directory trees.
8. Existing surface/alerts/mrms/spc modules can be used as design references only.
9. Basemap generation is land/ocean only with no baked-in features.

## Endpoint Contract

### /api/weather

Method: GET

Required:

- request_id
- product_group
- product
- region OR custom extent (n, s, e, w)

Mode inference:

- Current mode: no date_from/date_to
- Archive mode: both date_from and date_to provided
- Reject half-specified date ranges

Recommended common params:

- request_id
- product_group (surface | alerts | mrms | spc)
- product (group-specific product code/value)
- region (state code or CONUS)
- date_from (optional)
- date_to (optional)
- latest_only (optional)
- frames (optional)
- fps (optional)
- user_tz (optional)
- n,s,e,w (optional custom extent)
- style_config (optional JSON string)
- view_mode (layers | video), default layers for archive and current layered responses

Response requirements:

- success responses follow existing success_payload shape
- include source and data_mode
- include request_id when available
- layered responses include:
  - basemap_url
  - frames[]
  - layers_path
  - output_mode: layers
  - optional static layers map
  - session_expires_utc

Frame object contract:

- index
- timestamp_utc
- timestamp_local
- product layer URL (group-specific key and compatibility image_url)
- hud_right_url

### /api/weather/export-frame

Method: GET

Purpose:

- Export a user-selected scrubber frame as a composited PNG from existing layered artifacts.

Required:

- layers_path
- frame_index

Optional:

- format (default png)
- include layer visibility/opacity settings if UI sends custom composition state

Validation:

- must reject absolute paths and path traversal
- must ensure layers_path resolves under weather output root

Response:

- success_payload with image_url for generated PNG
- warning status if requested frame is unavailable

### /api/weather/export-animation

Method: GET

Purpose:

- Export MP4 by composing existing layered artifacts without re-rendering source data.

Required:

- layers_path

Optional:

- fps
- frame subset/range controls

Validation:

- same safety checks as export-frame

Response:

- success_payload with MP4 image_url
- warning status when no frames available

## Frontend Architecture

Primary files:

- weather.html
- js/weather.js
- js/shared.js (reuse helpers)

Do not duplicate shared utilities from shared.js.

### UI Model

Top-level selection:

- Product Group: Surface, Alerts, MRMS, SPC
- Product/Subproduct: dynamic control set by Product Group
- Region/Extent controls
- Current vs Archive controls via quick-range and date controls

Archive controls:

- quick range presets
- custom date_from/date_to
- single frame toggle
- frames and fps

Layered viewer:

- static basemap
- product layer per frame
- static overlays (cities/counties/states/legend where applicable)
- per-frame HUD right timestamp layer
- scrubber slider
- save frame and export animation actions

### Product Option Inventory (for migration parity)

Surface options to preserve:

- Station Plot
- Temperature
- Temperature Gradient
- Temperature Gradient and Values
- Feels Like
- Feels Like Gradient
- Feels Like Gradient and Values
- Dewpoint
- Relative Humidity
- Wind Speed
- Wind Gust
- Altimeter
- MSLP
- Visibility

Surface rendering config (updated 2026-04-06):

- Temperature/Feels Like products use custom 16-anchor colormap from
  `config/surface_config.py` (TEMPERATURE_COLORMAP, range -60°F to 130°F)
  instead of stock `RdYlBu_r`.
- Wind Speed and Wind Gust colorbars range 0–130 mph (up from 60/80).

Alerts options to preserve:

- All Hazards & Warnings
- Severe Weather Alerts
- Severe Weather Warnings
- Tropical Cyclone Alerts
- Hydrology Hazards
- Flash Flood Hazards
- Winter Hazards
- Cold Hazards
- Fire Hazards
- Heat Hazards
- Coastal Hazards
- Marine Hazards
- Non-Precipitation Hazards
- optional WFO filter
- crop_to_alerts

MRMS options (69 products via two-tier dropdown, implemented 2026-04-04):

Primary dropdown selects product family; conditional sub-dropdowns appear
for level, time window, threshold, source, or variant. JS composes the
final product key (e.g. `RotationTrack_LL_60min`) and sends to the API.

Families and sub-selectors:

- PrecipRate (standalone)
- PrecipFlag (standalone)
- RotationTrack → Level (LL/ML) + Time (30min–1440min)
- MESH → Time (Instant, Max 30min–1440min)
- SHI (standalone)
- POSH (standalone)
- AzShear → Level (Low/Mid)
- EchoTop → dBZ Threshold (18/30/50/60)
- VIL → Type (Instant, Density, Max 2hr, Max 24hr)
- QPE → Source (MS2/MS1/RO) + Period (01H–72H; RO adds 15M, Since12Z)
- Reflectivity → Variant (HSR, BaseQC, CompLow, CompHigh, CompSuper, BREF_1HR_MAX, CREF_1HR_MAX)
- Lightning → Window (30min/60min)
- Model → Field (FreezingLevel, SurfaceTemp, WetBulbTemp)
- RadarQualityIndex (standalone)

Config: config/mrms_config.py defines MRMS_PRODUCTS (69 entries),
MRMS_COLORMAPS (14), PRODUCT_GROUPS (11 families), MRMS_SUB_PRODUCTS (9).

Frontend: weather.html two-tier dropdowns + js/weather.js composeMrmsProductKey().
Backend: weather_utils.py PRODUCT_GROUPS["mrms"] lists all 69 composed keys.
main.py endpoint defaults updated to QPE_MS2_01H.
mrms_utils.py MESH checks use product.startswith("MESH").

MRMS lookback logic (updated 2026-04-06):

- QPE*MS2* products: 180-minute lookback window.
- QPE*MS1* products: 120-minute lookback window.
- Model\_ products: 180-minute lookback window.
- All other MRMS products: 60-minute lookback window.

SPC options (implemented):

- cat
- torn
- wind
- hail
- prob (Day 3 only)
- watches
- mds
- reports
- fire_windrh (Fire Weather Wind/RH, Day 1-8)
- fire_dryt (Fire Weather Dry Thunderstorm, Day 1-8)
- day selector (1..8)
- reports filters (day/type/filtered)
- watch and MD selectors

SPC day selector rules:

- When product is torn, wind, or hail: show Day dropdown with Day 1 and Day 2.
- When product is cat: show Day dropdown with Day 1 through Day 8.
- When product is prob: Day 3 only.
- Fire weather products (fire_windrh, fire_dryt): Day 1-8.
- Day dropdown defaults to Day 1.
- API parameter name: `day` (integer).

SPC Fire Weather Outlooks (added 2026-04-06):

- Two product types: Wind/RH (`fire_windrh`) and Dry Thunderstorm (`fire_dryt`).
- Day 1-2: fetched from SPC static GeoJSON
  (`spc.noaa.gov/products/fire_wx/day{1,2}fw_{dryt,windrh}.nolyr.geojson`).
- Day 3-8: fetched from NWS MapServer
  (`mapservices.weather.noaa.gov/vector/rest/services/fire_weather/SPC_firewx/MapServer`).
- GeoJSON structure identical to convective outlooks (fill/stroke properties).
- Day 3-8 MapServer features with `dn=0` ("Probability Too Low") are filtered out.
- Frontend: "Fire Weather Outlooks" dropdown in weather.html SPC controls
  (visible for all days, between convective outlooks and other products).
- Three-way mutual exclusion: convective / fire / other SPC dropdowns.
- Backend: `spc/spc_utils.py` has `_fire_wx_url()`, `fetch_fire_wx_geojson()`,
  and `_FIRE_WX_LAYER_IDS` for MapServer layer mapping.
- Rendering: `weather_utils.py` `_render_spc_product()` routes `fire_*` hazards.

SPC legend (updated 2026-04-06):

- cat: single-row category legend with fill colors.
- torn, wind, hail: two-row legend — probability row + CIG intensity row.
  - CIG 1: dashed diagonal lines, thin border.
  - CIG 2: solid backslash hatching (\\\\), medium border.
  - CIG 3: cross-hatch (xx), thick border.
  - Hail shows CIG 1–2 only; tornado and wind show CIG 1–3.
- fire_windrh: Elevated (#FFBF80), Critical (#FF8080), Extremely Critical (#FF80FF).
- fire_dryt: Isolated Dry T-Storm (#FFBF80), Scattered Dry T-Storm (#FF8080).
- Map hatching in spc_utils.py uses matching patterns.

## Projection Contract (Lambert-only)

Lambert policy:

1. Use Lambert Conformal for all unified weather outputs.
2. Full extent uses fixed CONUS Lambert framing.
3. State/custom extent recenters Lambert around selected extent center.
4. Basemap and product overlays must share the exact same computed extent and projection parameters per frame.
5. Preserve map aspect to avoid layer drift/stretch.

## Rendering and Layer Contract

### Basemap Generation Rule (Strict)

Basemap images must include only:

- land color
- ocean color

Basemap images must not include:

- borders or outlines of any kind
- country/state/county lines
- coastlines
- lakes or rivers
- roads or highways
- cities or text labels
- gridlines
- legends or logos
- HUD overlays
- any other features

If a feature is needed for display, it must be rendered as a separate overlay layer and never baked into the basemap.

Rendering stages:

- fetch/download
- cache
- parse/prepare
- render split layers
- optional compose/export

Layering requirements:

- deterministic layer ordering controlled by backend
- no drag-and-drop z-order UI
- static overlays rendered once per session whenever possible
- per-frame overlays only for data layer and timestamp/right HUD

### Legend Contract

Legends are rendered as separate server-generated PNGs in the session directory
(e.g. `legend/frame_0000.png` or `legend/legend.png`). They are displayed as
HTML `<img>` elements below the layered map container, never overlaid on the map.

Export endpoints must composite the legend image below the map frame when
generating flat PNG or MP4 output.

Per-product legend rules:

- **Surface / Station Plot**: Display static `img/station_plot_legend.png` as-is.
- **Surface / Other products**: Server-rendered colorbar PNG. Number values
  rendered over point circles on the product layer.
- **Alerts**: Per-frame legend showing active alert types and colors drawn for
  that frame. Legend changes each frame in animation sequences.
- **MRMS (general)**: Product-specific colorbar with level boundaries, adapted
  from legacy MRMS rendering logic.
- **MRMS / MESH products**: Per-frame legend with max-value indicator
  (hail size reference). Triggered by `product.startswith("MESH")`.
- **MRMS / RotationTrack products**: Per-frame legend with severity labels.
  Triggered by `"Rotation" in product`.
- **MRMS / Other products**: Colorbar with `full_name` and `units` from
  product_info dict.
- **SPC**: Two-row legend for torn/wind/hail (probability + CIG intensity);
  single-row category legend for cat.

## Caching and Output Strategy

Create weather-scoped roots (example):

- weather/weather_downloads/
- weather/weather_cache/
- weather/weather_images/
- weather/weather_archive/
- weather/weather_archive/weather_images/
- weather/weather_archive/archive_layers/

Session-scoped layered directories under weather archive root should include sibling paths such as:

- layers/
- product/
- cities/
- counties/
- states/
- static_overlay/
- hud_right/
- legend/
- exports/

Manifest metadata per layered session:

- created_utc
- updated_utc
- last_access_utc
- expires_utc
- frame_count
- product_group
- product
- extent signature

Lifecycle:

- TTL cleanup
- max-session cap pruning
- touch/update access time on export requests

## Style Configuration

Canonical style module target:

- config/style_config.py

Requirements:

- endpoint accepts style_config as Optional[str]
- parse with existing style parsing helper
- pass parsed dict into weather renderer
- resolver pattern for workflow defaults and override merge

Migration note:

- The repository currently has config/style_config-old.py and imports expect config.style_config in several modules.
- Creating/normalizing config/style_config.py should be handled in Phase 0 before weather workflow coding starts.

## Progress and Execution Model

Keep synchronous endpoint execution model:

- frontend starts polling /api/progress/{request_id}
- endpoint runs inline
- endpoint updates active_tasks[request_id]
- endpoint removes task entry on completion/failure

Do not use BackgroundTasks or asyncio for these render jobs.

## Safety and Validation Rules

1. Validate paired archive dates.
2. Enforce per-group max archive span limits.
3. Validate extent bounds ordering and numeric types.
4. Validate path parameters for export endpoints.
5. Return warning payloads when no output is produced, not hard failures unless needed.

## Implementation Phases

### Phase 0 - Foundation and Spec Lock

Deliverables:

- Add weather endpoint contract comments/docs in main.py planning notes.
- Create config/style_config.py from current style baseline.
- Define weather directory constants and static mounts plan.
- Define weather product map and parameter normalization table.

Exit criteria:

- No unresolved contract decisions.
- style_config module path is normalized.

### Phase 1 - Backend Skeleton

Deliverables:

- Add /api/weather route with validation and mode inference.
- Add progress callbacks and active_tasks lifecycle.
- Return success/error payloads with stable response shape.
- Stub layered response assembly and layers_path creation.

Exit criteria:

- /api/weather responds for all product groups in current mode with placeholder or minimal valid output.

### Phase 2 - Product Render Integration (Reference-only Translation)

Deliverables:

- Implement dedicated weather rendering pipeline using translated logic from legacy modules.
- No runtime imports or endpoint chaining into surface/alerts/mrms/spc workflows.
- Implement product-group-specific frame layer generation.
- Surface station plots must use full MetPy StationPlot glyph model (temp NW, dewpoint SW, pressure NE, sky cover center, wind barbs, wx symbols).
- Surface non-station-plot products must render number values over point circles.
- Implement per-product legend generation per the Legend Contract.
- Add SPC day selector dropdown logic to frontend (Day 1-2 for torn/wind/hail, Day 1-7 for cat).
- MRMS legend rendering must follow legacy colorbar logic, especially for MESH Tracks.

Exit criteria:

- Current mode works for each product group with real data.
- Layer alignment and Lambert framing are stable.
- Legends render correctly for each product group.
- SPC day selector appears conditionally based on product selection.

### Phase 3 - Archive Layered Sessions

Deliverables:

- Archive date-range generation for all weather product groups.
- Layered session manifest and cleanup lifecycle.
- Scrubber-ready frames payload and static layers map.

Exit criteria:

- Archive layered output works with quick range and custom dates.

### Phase 4 - Export Endpoints

Deliverables:

- /api/weather/export-frame
- /api/weather/export-animation
- Session touch-on-export behavior

Exit criteria:

- Frame PNG export and MP4 export succeed without rerendering source data.

### Phase 5 - Frontend Unification ✅ COMPLETE

Completed:

- weather.html built with product group switching (Surface/Alerts/MRMS/SPC).
- js/weather.js orchestration, polling, scrubber, export actions working.
- MRMS two-tier dropdown system implemented (composeMrmsProductKey).
- SPC day-driven convective filtering, watch/MD item selectors.
- Extent modal and custom extent controls integrated.

### Phase 6 - Cutover and Cleanup ✅ COMPLETE

Completed (2026-04-04):

- Legacy pages (surface/alerts/mrms/spc/spc-archive .html + .js) archived to legacy/.
- Legacy page routes removed from main.py.
- Navigation updated: Weather, Radar, Satellite, Satellite Archive only.
- index.html updated: cards for Weather, Satellite, Radar, Satellite Archive.
- Legacy API endpoints retained in main.py (can be removed later).
- Radar and Satellite workflows remain intact and separate.
- Lightning remains omitted from active UX paths.
- Radar and Satellite unaffected.

## Test Matrix

Current mode tests:

1. Surface station plot, CONUS
2. Surface gradient with smoothing
3. Alerts with WFO filter and crop toggle
4. MRMS QPE and severe product sample
5. SPC categorical and reports modes

Archive tests:

1. Quick range generation for each product group
2. Custom date range generation for each product group
3. Single-frame archive mode
4. Layered scrubber frame stepping and timestamp correctness

Export tests:

1. Export frame for mid-sequence frame index
2. Export animation full range
3. Export animation subset range

Extent tests:

1. Full CONUS
2. State extent
3. Custom extent via modal bounds

Failure tests:

1. Missing date_to with date_from
2. Invalid extent bounds
3. Invalid layers_path traversal
4. Empty frame generation warning path

## Risks and Mitigations

Risk: Scope creep from legacy parity requirements.
Mitigation: enforce product-map contract and phase gates.

Risk: Layer misalignment under custom extents.
Mitigation: single shared extent/projection function and image-size consistency checks.

Risk: Disk growth from layered sessions.
Mitigation: strict TTL + max-session pruning and manifest-based cleanup.

Risk: Style config drift.
Mitigation: central resolver in config/style_config.py only.

## Handoff Prompt Checklist

When asking another model to implement, include:

1. Use docs/weather-unified-roadmap.md as canonical implementation plan.
2. Keep radar/satellite workflows separate.
3. Do not wire runtime dependencies to legacy surface/alerts/mrms/spc workflows.
4. Build /api/weather plus /api/weather/export-frame and /api/weather/export-animation.
5. Normalize style config module to config/style_config.py before endpoint integration.
6. Preserve synchronous progress model with active_tasks.
