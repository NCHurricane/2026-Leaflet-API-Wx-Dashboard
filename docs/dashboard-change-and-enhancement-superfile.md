# Dashboard Change and Enhancement Superfile

Last updated: 2026-06-28 (water enhancements session)

This file is the canonical planning and status file for dashboard changes,
completed enhancement phases, and future product work. It consolidates the
useful current information from the older roadmap, WPC plan, product-page shell
plan, backend/frontend refactor playbook, and refactor dossier.

Keep separate:

- `docs/architecture.md` for durable system architecture.
- `docs/patterns.md` for coding and implementation patterns.
- `docs/refactor-baseline.md` for the original pre-refactor baseline.
- `docs/next-session-startup-prompt.md` for the short current handoff.

## Current State

- Active repo: `F:\Python\dashboard_2026`.
- The backend route/service refactor is complete enough that product routes and
  services should remain modular. Do not add route logic back to `main.py`.
- The fixed map-first dashboard shell is accepted.
- Canonical product routes serve the shared dashboard shell in product-only mode:
  `/surface`, `/alerts`, `/radar`, `/satellite`, `/spc`, `/rtma`, `/mrms`,
  `/drought`, `/tropical`, `/wpc`, and `/water`.
- `weather.html` remains the combined workspace and should keep working until
  explicitly retired.
- Product engines/pages own product-specific controls, requests, response
  interpretation, and most rendering. `js/weather.js` still owns shared map
  lifecycle, generic archive orchestration, shared scrubber infrastructure, and
  injected callbacks where cross-product state is still coupled.
- Shared categorical legends now wrap whole swatch/label items using
  `.legend-flow`; labels can wrap without painting into neighboring swatches.
  The Alerts legend uses the five-column helper. User browser smoke passed on
  2026-06-28.

## Completed Major Work

### Backend route/service refactor

- `main.py` was split by route family using `APIRouter`.
- Product-facing cache reads, response shaping, and worker fallback logic moved
  into service modules.
- Shared app infrastructure lives under `app_core/`.
- Public/local endpoint URLs were kept stable during the refactor.
- Worker-to-`main` coupling was removed from the alert worker path.
- Product-page routing stays separate from API routing.

Current boundaries:

- `routes/*.py`: FastAPI route declarations.
- `services/*_service.py`: route-facing cache reads, response shaping, and
  fallback calls.
- `workers/*_worker.py`: upstream fetch, parsing, cache generation, and
  scheduled refresh.
- `app_core/*`: shared paths, static serving, runtime, progress, and HTTP
  helpers.

### Product-page shell and frontend split

- The fixed dashboard grid shell replaced the older floating/collapsible panel
  model.
- Top navigation and product-only route metadata are managed through the shared
  product shell.
- Route-level standalone candidates were accepted for Surface, Alerts, Radar,
  Satellite, SPC, RTMA, MRMS, Drought, Tropical, WPC, and Water.
- Phase 15 clean-cut completed for Drought, Surface, MRMS, RTMA, SPC, Alerts,
  Satellite, Radar, and Tropical wrappers that no longer needed fallback bodies.
- Phase 16 archive extraction completed for Tropical, Alerts, Surface, MRMS,
  SPC, and Radar.
- Phase 17 cleanup completed on 2026-06-18. Obsolete wrappers, declaration-only
  helpers, stale state, and unused dependencies were removed from `js/weather.js`
  and `weather.html`.
- All-page browser smoke passed for the Phase 16/17 completion set on
  2026-06-18.

Important retained rules:

- Product page modules must be included before `js/weather.js`; a missing
  `window.NCH*Engine` or `window.NCH*Page` silently prevents engine creation.
- `/spc` startup must normalize SPC controls and report-filter state before the
  initial `refreshActiveLayers()` call.
- Product-specific code should move only after the route/page has browser proof.
- Keep API paths stable unless a separate API cleanup is explicitly planned.

### Tropical migration

- Tropical is the accepted reference UI for rich product pages.
- `js/tropical-engine.js` owns active-storm list, live detail/advisory requests,
  archive catalog requests, per-storm archive base data, advisory requests, and
  response sequencing.
- `js/tropical-page.js` owns active-system cards, archive selectors/cards,
  advisory/fix scrubber state and controls, inspector rendering, forecast table
  rendering, official product/graphics panels, floater state, NESDIS URL
  generation, availability probing, and modal/pill handlers.
- `js/weather.js` still supplies shared map/layer callbacks and GIS overlay
  rendering where those are tied to the common map lifecycle.

### RTMA Feels Like

- Separate Wind Chill and Heat Index selectors were replaced by one
  `apparent_temperature` product labeled Feels Like.
- The derived value uses temperature, dew point, and wind speed from the same
  RTMA frame.
- The derived-product PNG path uses the shared RTMA grid loader rather than a
  native GRIB variable path.

### CSS extraction and navigation

- The large inline `weather.html` style block was lifted into
  `css/dashboard.css`.
- A later per-product CSS split was intentionally deferred because many
  selectors are shared or interleaved across product families.
- The prominent top navigation uses canonical product routes and preserves the
  hidden `weather-type-*` inputs because existing dashboard event listeners
  still depend on them.

## Product Enhancement Roadmap

### Domestic NEXRAD radar

Phase 1 is complete.

- The backend catalog owns live product labels, fields, palettes, units, ranges,
  masks, capabilities, and cache IDs.
- The Radar selector is populated from the backend catalog.
- Unsupported or stale static product options were removed or corrected.
- Level II products include reflectivity, velocity, spectrum width, ZDR,
  correlation coefficient, differential phase, and Level II-derived
  storm-relative velocity.
- Level II elevation selection supports `auto` and explicit nearest-angle
  requests, with cache isolation by requested elevation.
- Level III expansion includes storm-relative velocity, ZDR, correlation
  coefficient, KDP, hydrometeor classification, digital precipitation rate,
  one-hour accumulation, storm-total precipitation, echo tops, and VIL.
- MetPy fallback decoding is available for digital Level III products Py-ART
  cannot read reliably.
- Standardized `/api/{service}/products` endpoints exist across product families.

Completed radar enhancements:

- Radar loop blink reduction.
- Radar Inspector hover values through `/api/radar/live/value`.
- Live `.pal` upload and preview in the standalone `pal_preview/` tool.
- IEM-backed Level III storm-attribute overlays with storm tracking, hail,
  mesocyclone, TVS, and structure attributes.
- Storm-cell icon set: TVS = red triangle (T), Meso = orange circle (M),
  Confirmed Hail = solid green triangle (H), Probable Hail = hollow green
  triangle (no label), Storm Cell = small dark square with yellow border.
- Floating Storm Tracks mini-legend (`.wx-mini-legend`) appears in the
  topright map corner below the logo when Storm Tracks are enabled; hidden
  when disabled. The `.wx-mini-legend` CSS class is global and reusable on
  other pages.
- Radar site markers now use a black (`#020617`) outline on all status colors
  for legibility against the dark basemap. Selected-site highlight rings are
  unchanged.
- IEM `meso` rank threshold: only cells with rank ≥ 4 (out of 1–25) receive
  the Meso icon. Ranks 1–3 are weak rotational shear; below this threshold
  the cell falls back to its hail/default icon. Constant `_MESO_MIN_RANK`
  in `services/radar_storm_attributes_service.py`.
- Debug endpoint `/api/radar/debug/meso-raw?site=KXXX` returns raw IEM
  `meso`/`tvs` field values for every cell at a site — use this when tuning
  the rank threshold.

Current radar notes:

- IEM storm attributes replaced the earlier AWS-NST/AWS-NMD/TGFTP approach.
- `radar_nst_service.py` was removed after the storm-attribute service replaced
  its remaining role.
- Selected-cell SRV and storm-track overlay visibility must remain decoupled so
  hiding tracks does not invalidate the active SRV animation context.
- IEM meso rank 1–3 = weak shear only; do not lower `_MESO_MIN_RANK` below 4
  without comparing against a reference tool (e.g. Radarscope) on a live event.

### Satellite and lightning

Completed enhancements (2026-06-28):

- Implemented GOES composites were exposed in the Satellite product selector:
  Fire Temperature, Air Mass, Day Cloud Phase, Day Land Cloud/Fire,
  Day Snow/Fog, Nighttime Microphysics, Dust, Ash, and Sulfur Dioxide.
- Renderer-matched interpretive legends were added for those RGB composites,
  with frontend fallback metadata so legends remain visible through
  satellite/sector/product switches without requiring a hard refresh. Scalar
  colorbars remain limited to brightness-temperature channels.
- GOES GLM Flash Extent Density was added as Satellite-only products with
  one-minute and five-minute rolling aggregations, on-demand tile rendering,
  and a fixed 4 km Web Mercator grid that counts unique flash extents per cell
  from LCFA group-to-flash relationships.

Planned/enhancement direction:

- Keep Satellite GLM synchronized with the shared scrubber. Do not add GLM as a
  Radar overlay.
- Replace flat satellite tabs with filtered Region, Platform, Sector, and
  Product controls.

### Water page

V1 is active implementation.

- `/water` is registered in the shared product shell and navigation.
- `workers/water_worker.py` builds a local marker cache from:
  - NWS ArcGIS river gauges.
  - NOS CO-OPS active water-level stations.
  - NDBC latest observations.
- `/api/water/stations?bbox=...&max_sites=...&networks=...` filters the local
  marker cache by viewport and selected networks.
- `/api/water/stations/{site_id}` enriches river gauges through NOAA NWPS on
  click; CO-OPS stations now also receive a live CO-OPS API fetch (water level
  or current speed/direction) with a 3-minute in-memory cache; NDBC stations
  resolve from the local cache.
- River gauge colors are observed flood stage only: Major, Moderate, Minor,
  Action, or default no-flood/not-given.
- Coastal and NDBC stations have distinct marker styles and render in the
  dedicated `water-markers` Leaflet pane.
- The sidebar `Networks` selector follows the Surface page pattern.
- Leaflet world-wrap bbox edge cases are normalized/clamped instead of returning
  422s at world view.
- Map is constrained to a single world copy: `noWrap: true` on all basemap tile
  layers, `maxBounds` set to the world extent, `maxBoundsViscosity: 1.0`, and
  `minZoom: 2`.

Completed enhancements (2026-06-28):

- River Flood Filter pills (All / Action+ / Minor+ / Moderate+ / Major) added to
  the water sidebar. Client-side filter; coastal and NDBC markers always remain
  visible. Pills are hidden when the River network is unchecked and the filter
  resets to All automatically.
- Stage gauge bar added to river gauge popups when flood threshold data is
  available. Shows color-coded zones (normal / action / minor / moderate / major)
  with a white current-stage marker and a threshold summary line.
- CO-OPS click enrichment: on-click live fetch from the CO-OPS API populates
  Water Level (or Current Speed / Direction) in the coastal station popup.
- NDBC buoy popup replaced flat reading rows with a grouped card layout:
  Wind / Waves / Atmos / Temp / Other.
- Removed `impacts`, `historic_crests`, and `recent_crests` parsing from the
  NWPS detail fetch path (`_parse_nwps_gauge`); the `_nwps_crests` helper was
  deleted.

Future Water enhancements, possibly V2:

These are deferred from the active V1 agenda unless a separate Water V2 slice is
started.

- Clustering or density controls if full-cache rendering is heavy.
- Optional WPC Excessive Rainfall Outlook and Real-Time Flood Impact overlays.
- USGS streamflow percentile context (WaterWatch API) on river gauge click.
- Interactive NWPS hydrograph chart replacing the static image.

### WPC page

Base WPC product page is complete.

- Source decision: WPC KML/KMZ feed is the primary source.
- Completed product groups:
  - Excessive Rainfall Outlook, Days 1-3.
  - QPF: 6-hour, 24-hour, and multi-day products through Day 7.
  - Winter Weather: snow greater than 4, 8, and 12 inches plus ice greater than
    0.25 inches, Days 1-3.
  - Five-Day River Flood Outlook.
- Completed operational behavior:
  - Cache-first worker, API, catalog, and 30-minute scheduled task.
  - Per-product source availability, stale metadata, and last-valid-cache
    preservation.
  - WPC-authored no-significant-area overlays for ERO and Winter products.
  - Responsive WPC legends, opacity control, request sequencing, and tab cleanup.
- Manual browser smoke completed by the user on 2026-06-18.

WPC expansion status:

- Active MPDs are code-complete; the prior note still marked manual browser
  smoke pending.
- WPC UI polish is complete: group pills, day pills, sub-tabs, reliability bar,
  default sub-tab selection, and shared bottom scrubber.
- Surface Analysis and Forecast overlays are complete using WPC transparent PNG
  products and KML bounds.

Future WPC increments:

1. Probabilistic QPF.
2. Expanded Days 1-3 winter guidance.
3. Day 4-7 winter outlook.
4. Day 1-3 Significant Weather.
5. Day 3-7 Heat Index.

Deferred:

- SigWx mixed-geometry products remain optional.

### Global satellite coverage

Planned:

- Add Himawari-9 as the operational Pacific platform using NOAA open AWS data.
- Keep Himawari-8 for historical/archive use only.
- Add Meteosat platforms by operational role:
  - Meteosat-12: Europe/Africa full disk.
  - Meteosat-11: rapid-scan Europe and North Africa.
  - Meteosat-9: Indian Ocean.
- Do not expose Meteosat-10 initially.
- Generalize the GOES-specific provider/channel/projection/sector/cache model
  into platform descriptors and capability matrices.
- Use optional server-side EUMETSAT credentials and hide unavailable platforms
  cleanly when credentials are absent.

### International radar

Deferred to V2. Keep the US dashboard enhancement path focused on NEXRAD,
satellite/GLM, Water, WPC, SPC, alerts, and storm reports before adding
provider-specific radar adapters.

Preferred rollout order:

1. Canada through ECCC GeoMet radar services.
2. Germany through DWD open radar composites and supported site data.
3. Australia through Bureau of Meteorology five-minute rendered radar imagery.

Each provider should declare supported products, animation interval, projection,
attribution, archive depth, and whether data are native grids or rendered
imagery.

## Backlog

1. Dedicated Marine workspace building on the Water page's NDBC and CO-OPS
   inventory with marine-specific products, trends, and forecast context.
2. Fire/Smoke page using NASA FIRMS detections and NOAA smoke analysis.
3. Cross-product severe-weather workspace combining Radar, GLM, warnings, SPC
   outlooks, storm reports, and possibly a broader current-weather workspace.

## Verification Expectations

- Use narrow syntax checks first, such as `node --check` for touched JavaScript
  files and targeted `py_compile` for touched Python modules.
- Browser smoke is user-owned for current dashboard work; keep automated
  validation to narrow syntax/import checks unless the user asks otherwise.
- For map label/value placement, preserve source coordinates and move rendered
  anchors when the goal is visual offset.
- Keep scrubber continuity and worker/preloader coverage as acceptance criteria
  for derived or replacement UI behavior.
- When browser proof is unavailable, keep claims scoped to static validation.

Representative checks:

```powershell
node --check js\weather.js
node --check js\wpc-page.js
node --check js\wpc-engine.js
.\.venv\Scripts\python.exe -m py_compile main.py routes\*.py services\*.py workers\*.py
```

Representative browser smoke:

- `/weather.html` combined workspace still loads.
- Canonical product routes return 200 and render nonblank maps.
- Product controls populate and trigger the expected API calls.
- Layers clear on tab/product switch without leaking stale overlays.
- Legends render without swatch/label overlap.
- Archive/scrubber workflows keep frame continuity where applicable.

## Archived Source Docs

These superseded planning files were consolidated into this superfile and moved
to `docs/archive/`:

- `dashboard-product-enhancement-roadmap.md`
- `wpc-page-plan.md`
- `product-page-shell-plan.md`
- `refactor-playbook.md`
- `refactor-dossier.md`

Keep archived files for historical detail. Prefer this superfile for current
planning and status.
