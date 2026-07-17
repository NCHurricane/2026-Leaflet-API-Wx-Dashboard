# Dashboard Change and Enhancement Superfile

Last updated: 2026-07-17 (Frontend Split Stage 2 Phase 20 Surface migration
completed: /surface is a true standalone page, all surface code was deleted
from js/weather.js and weather.html, and surface archive support was retired
with the old archive scrubber rather than rebuilt)

This file is the canonical planning and status file for dashboard changes,
completed enhancement phases, and future product work. It consolidates the
useful current information from the older roadmap, WPC plan, product-page shell
plan, backend/frontend refactor playbook, and refactor dossier.

Keep separate:

- `docs/architecture.md` for durable system architecture.
- `docs/patterns.md` for coding and implementation patterns.
- `docs/refactor-baseline.md` for the original pre-refactor baseline.
- `docs/next-session-startup-prompt.md` for the short current handoff.
- `docs/satellite-render-optimization-plan.md` for the active satellite
  latency execution plan (archive to `docs/archive/` when its phases
  complete).
- `docs/satellite-radar-render-pipeline-files.md` for the satellite/radar
  render pipeline file reference (companion to the optimization plan).

## Active Tracks (2026-07-17)

Priority order for upcoming work. Track 1 goes first because it may alter
the plan for some future items; re-evaluate later tracks against the
post-split structure, not the monolith.

1. Frontend True Split (Stage 2) + Severe Weather Workspace — planned in
   this file (section below). Phases 18-20 are complete; Phase 21 (SPC, WPC)
   is next.
2. Satellite render pipeline latency optimization — standalone execution
   plan in `docs/satellite-render-optimization-plan.md`, registered in the
   satellite roadmap section below. Backend-only (`satellite_v2/*`), so it
   may interleave with track 1; the two touch disjoint files.
3. GK2A + GMGSI new platforms. Adds `PLATFORM_*` entries to
   `js/satellite-page.js`; if started mid-split those entries must be
   ported to `pages/satellite/`, so prefer starting it before the split
   reaches satellite or after that page migration completes.

## Current State

- Active repo: `F:\Python\dashboard_2026`.
- The backend route/service refactor is complete enough that product routes and
  services should remain modular. Do not add route logic back to `main.py`.
- The fixed map-first dashboard shell is accepted.
- `/drought` and `/surface` serve true standalone pages from
  `frontend/pages/`. The remaining canonical product routes serve the shared
  dashboard shell in product-only mode: `/alerts`, `/radar`, `/satellite`,
  `/spc`, `/rtma`, `/mrms`, `/tropical`, `/wpc`, and `/water`.
- `weather.html` remains the combined workspace and should keep working until
  explicitly retired.
- Product engines/pages own product-specific controls, requests, response
  interpretation, and most rendering. `js/weather.js` still owns shared map
  lifecycle, generic archive orchestration, shared scrubber infrastructure, and
  injected callbacks where cross-product state is still coupled.
- City labels are controlled from the Layers pane with an `Off | US | World`
  segmented control. `US` loads `data/us-cities-all.json`; `World` loads
  `data/world-cities.json`. Both sources share the same density slider, mapped
  through source/zoom-specific bounded min/max km ranges in `js/weather.js`.
- `config/user_settings.default.json` is the tracked baseline for user-facing
  dashboard preferences. `GET /api/user-settings/defaults` serves this file,
  and `js/weather.js` reads it during startup before the first map-default fit
  and product refresh. It separates global preferences such as home region and
  city labels from per-page defaults such as Satellite, Tropical, WPC, and
  Drought map views. A future writable user settings file should merge over
  this baseline rather than replacing built-in fallbacks.
- Most per-page `autoLoad` defaults are `false`, so product routes open to the
  configured map view with controls/background metadata initialized but no
  rendered product overlay. Current exceptions are Alerts, which renders Severe
  Weather Warnings with TOR/SVR/FFW filters enabled, and Tropical, which starts
  in the Atlantic basin and features the first active storm when present or the
  Tropical Outlook when no active storm exists. Drought is also an exception:
  its standalone page selects and draws the latest available release on load.
- Startup controls now reflect intentional always/default-on context: state and
  country borders are checked by default but remain user-selectable; Surface
  networks start all-on with no selected surface product; Radar Sites start on;
  WPC group pills are navigation only and clear any previous WPC overlay until
  the user selects a day/product.
- Surface and RTMA support true empty product states. Unchecking the selected
  Surface product or the selected RTMA stream/field clears stale values and
  invalidates in-flight layer responses instead of forcing a fallback product.
  Selecting a Surface product auto-enables its matching Gradient toggle, which
  can still be turned off independently. RTMA field checkboxes stay disabled
  until a stream is selected; 24-hour temperature change remains Hourly-only
  and clears when switching to Rapid Update.
- Surface gradient overlays are worker-generated at stable cache paths, so the
  frontend refreshes cached gradient metadata after 5 minutes and appends the
  worker timestamp as an image URL version query. This prevents open `/surface`
  pages from retaining stale gradient PNGs after the worker replaces files.
- SPC probabilistic hazards auto-enable their matching Significant/CIG hatch
  layer when selected, while Significant toggles remain unavailable on their
  own. Drought selects the latest release week on startup and turns on all five
  drought categories; selecting another week resets all five categories on.
- User browser smoke passed on 2026-07-04 for the startup/default-control
  changes above.
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
  (Retires with Frontend Split Stage 2 when the monolith is deleted.)
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
  (Superseded 2026-07-16: un-deferred as part of Frontend Split Stage 2.)
- The prominent top navigation uses canonical product routes and preserves the
  hidden `weather-type-*` inputs because existing dashboard event listeners
  still depend on them. (Retires with Frontend Split Stage 2 along with the
  shared shell.)

## Frontend True Split (Stage 2) and Severe Weather Workspace

Planned 2026-07-16. Active track 1. This continues the completed Phase 15-17
product-page shell work and is recorded here before implementation so the
plan survives between sessions.

### Why Stage 2 exists

Phases 15-17 produced per-product files but not per-product boundaries:

- `js/weather.js` is ~16,000 lines — roughly 68% of all frontend JS.
- Every canonical product route serves the same `weather.html` (via
  `serve_product_shell_page()` meta injection, other products' controls
  disabled), so every page loads all ~25 scripts including the monolith.
- Engines receive `context` objects built inside `js/weather.js`; across all
  engines that surface is ~206 distinct members — a porthole into the
  monolith, not an interface.
- The scrubber is a global mode with cross-product coupling (for example,
  `mrms-engine.js` calls `context.exitRtmaScrubMode()` and
  `context.updateRtmaScrubberUi()`).

Stage 2 finishes the separation: each page owns its directory, shared code
shrinks to a small explicit core, and the combined view is rebuilt at the
end as a composition of the same modules.

### Target structure

```text
frontend/              browser-only assets; avoids the existing Python lib/
  core/                the ONLY shared frontend code
    api.js             apiUrl(), fetch wrappers, progress polling
    map-core.js        Leaflet init, basemap toggle, region fitBounds
    scrubber.js        generic single-product frame scrubber COMPONENT
                       (per-page instances; no global modes)
    legend.js          legend builder
    status.js          status line + staleness/timestamp helpers
    nav.js             product nav (absorbs product-page-shell.js)
    settings.js        user settings load/save
    core.css           app chrome (shared.css + shared dashboard CSS)
  pages/
    alerts/            alerts.html, alerts-page.js, alerts-engine.js,
                       alerts-tools.js, alerts-panel.js, alerts.css
    radar/ satellite/ spc/ surface/ mrms/ rtma/ drought/ tropical/ wpc/ water/
                       same pattern: {page}.html, {page}-page.js,
                       {page}-engine.js, {page}.css
    workspace/         combined severe-weather view; built LAST
  lib/                 vendored Leaflet, topojson-client, tz-lookup
```

Deleted at completion: `js/weather.js`, `weather.html`,
`js/product-page-shell.js`, `js/product-app-context.js`, `css/dashboard.css`
(split into `core/core.css` + per-page CSS), and the `js/` directory itself.
The dead `js/satellite.js` is deleted early (never loaded by any page).
Backend layout is unchanged — `routes/`, `services/`, and `workers/` are
already split; `serve_product_shell_page()` meta injection is replaced by
serving each page's own HTML. The display side stays a pure cache/API
reader, so a future feeder/display split (workers on another machine)
remains compatible without changes to this plan.

### Ownership rules

1. A page's HTML loads exactly `frontend/lib/*`, `frontend/core/*`, and its
   own `frontend/pages/{product}/` directory — never a sibling page's files.
2. Core only accepts code that two or more pages already use (not "might
   use someday" — that is how `weather.js` happened).
3. Workspace exception: `frontend/pages/workspace/` may import sibling pages'
   `*-engine.js` files (and engine-side tool modules), never their
   `*-page.js` controllers. It is the single sanctioned cross-page consumer.

Anything the workspace needs must therefore live on the engine side of a
product's page/engine boundary.

### Config-driven engines

Engines take their product catalog as an instantiation option instead of
hardcoding it. A standalone page passes the full catalog; the workspace
passes a trimmed one:

```js
createSatelliteEngine(map, {
    satellites: ['goes18', 'goes19'],
    sectors: ['CONUS'],
    channels: ['Channel02', 'Channel08', 'Channel13'],
});
```

### Migration order (strangler-fig)

`weather.html` stays untouched and working until the end. Per product:
build the real standalone page (own HTML/scripts/CSS) -> reach parity ->
delete that product's code from `js/weather.js`. Each step is independently
shippable, so an interrupted session still leaves the repo better than it
found it.

- Phase 18: **COMPLETE 2026-07-16.** Core API inventory and interface contract
  are in `docs/frontend-stage2-core-api-inventory.md`. The audit found 578
  injected entries / 390 unique names, defined the `core/*`, page, engine, and
  workspace boundaries, and identified the cross-product scrubber coupling
  that must not survive migration.
- Phase 19: **COMPLETE 2026-07-16.** Drought is the proof-of-pattern at
  `frontend/pages/drought/`. `/drought` now serves its own HTML, ES-module page
  controller, DOM-free engine, and Drought CSS with only the minimum shared
  API/settings/map/nav/legend/status core. The old Drought controller/engine,
  HTML controls, and `js/weather.js` implementation were removed after parity.
  Browser smoke proved date loading, NC statistics, category filtering,
  opacity, basemap changes, five rendered GeoJSON paths, and no console errors;
  the remaining `weather.html` shell also loaded without errors. Follow-up
  parity corrections added shared Lat/Lon, state, country, and county overlay
  controls; restored the map logo and global last-updated HUD; moved Data
  Status into the controls sidebar; moved the expandable legend onto the map;
  restored the Off/US/World city source, bounded density, and font-size controls
  through the shared map core; and made the initially highlighted latest release
  load automatically. A final pre-split UI audit restored the Data Age row,
  reset-view control, numeric zoom indicator, USGS and no-label basemap choices,
  dashboard attribution, and product-navigation icons. Unrelated WWA/product
  panes and the developer-only test-alert button are intentionally not part of
  the standalone Drought page. Boundary startup was then corrected after a
  hard-refresh regression exposed ~53 MB of repeated GeoJSON downloads:
  generated boundary files remain in the gitignored `cache/overlays/` runtime
  cache, the server now retains decoded payloads in memory and serves week-long
  immutable cache headers, and `frontend/core/api.js` persists versioned map
  payloads in browser Cache Storage. State startup requests no longer include
  county geometry; counties download only when enabled. The client also filters
  returned U.S. features by their declared layer and uses boundary cache version
  4, preventing a response cached from an older unfiltered API process from
  crossing state and county toggle behavior. Dark (No Labels) is the standalone
  page and shared map-core default basemap, matching the pre-split shell.
  Option 1A from the Drought sidebar design handoff is now the accepted shared
  sidebar reference: a 300px shell with pinned Data Status/Region header,
  accessible Data/Overlays/Style tabs, a scrollable mounted-panel area, and a
  pinned message/Refresh footer. `frontend/core/sidebar-tabs.js` owns stable-DOM
  switching plus click and keyboard navigation; pages may add an opt-in fourth
  tab without changing the controller. Drought keeps Release Week/categories
  under Data, cities/map layers under Overlays, and opacity/basemap under Style.
  Browser smoke passed tab switching, keyboard Home navigation, retained control
  state, default Dark basemap, automatic latest-release data, and pinned layout
  geometry. The accepted legend treatment is now a shared, map-panel-confined
  dark glass tray in `frontend/core/legend.js` and `core.css`. It supports
  left/center/right alignment, an accessible collapse control, compact
  categorical entries, and reusable continuous-colorbar/tick primitives while
  leaving product labels, thresholds, and values with the product engine.
  Drought uses the bottom-left alignment, keeps all five official USDM classes
  visible, and expands in place for state cumulative/individual percentages and
  DSCI. Browser smoke verified national, collapsed, and NC-stat states and proved
  the tray remained wholly inside the map panel without crossing the sidebar.
  The standalone core shell also retains the dashboard's original Montserrat
  typography through the existing self-hosted normal and italic variable fonts;
  `core.css` owns the shared family declaration and product CSS inherits it.
  The corrected wiring passed module syntax, focused lint, eleven standalone and
  boundary-cache tests, and live local API payload checks.
- Phase 20: **COMPLETE 2026-07-17.** Surface is the second consumer of the
  accepted shells at `frontend/pages/surface/` (Option 1A tabbed sidebar,
  ES-module page controller, DOM-free engine, page-local renderer module,
  per-page CSS). Ported from the monolith with parity: colored value markers
  with zoom scaling and station popups, ASOS/COOP/DCP/RWIS network filters
  (hidden on CONUS/WORLD), zoom-aware station-density thinning with a km
  readout, worker-PNG gradient overlays with 5-minute metadata TTL and URL
  cache-busting, the IDW client-canvas gradient fallback with the 32F
  isotherm diagnostic, and a continuous-colorbar legend on the shared
  core-legend primitives with a Stations count. The Gradient Blur control was
  intentionally dropped after user review: worker PNGs never blurred, so the
  slider only affected the rarely-seen canvas fallback, which now uses a
  fixed `FALLBACK_BLUR_SCALE = 1.0`. Decision (Option B): the surface archive
  mode was NOT rebuilt on the standalone page — surface support was removed
  from the shared archive scrubber entirely (product type list, archive load
  branch, frame rendering); the scrubber-as-component rewrite remains
  Phase 22. After user parity smoke, ~1,000 lines of surface implementation
  were deleted from `js/weather.js` (shared helpers kept because RTMA,
  cities, and satellite legends use them: `windDirectionBarbIcon`,
  `surfaceColoredTextIcon`, `_filterByMinDistKm`, `_haversineKm`,
  `renderContinuousLegend`, `_formatSurfaceTick`), the `wx-section-current`
  controls and `wx-side-group-current` styling blocks were removed from
  `weather.html`, and `js/surface-engine.js` + `js/surface-page.js` were
  deleted. `weather.js?v=20260717a`.
- Phase 21: spc, wpc.
- Phase 22: mrms + rtma, including the scrubber-as-component rewrite.
- Phase 23: satellite.
- Phase 24: radar.
- Phase 25: alerts (immersive panel plus Arrival Tool / Speed Estimator
  move to engine-side modules).
- Phase 26: tropical (already closest to the target pattern), then Water as a
  separate independently shippable migration. Water stays excluded from the
  initial workspace, but must leave `js/weather.js` before Phase 27.
- Phase 27: workspace assembly; retire `weather.html`; delete the monolith.

Definition of done (mechanically checkable): each product route loads only
third-party libraries plus `frontend/core/* + frontend/pages/{product}/*`;
no engine references another product's functions; `js/weather.js` no longer
exists. The currently pinned Leaflet CDN asset must move to `frontend/lib/`
before Phase 27 completes.

### Severe Weather Workspace spec

Purpose: a one-stop severe-weather visualization page (US only) able to
show multiple products at once during extreme weather events. Not all
dashboard products — a curated subset:

- Radar: Level 2/3, per site.
- Satellite: GOES-18/19 CONUS only; Channel02, Channel07 or Channel08,
  Channel13.
- RTMA-RU: temperature, dew point, wind (speed/gust/direction), visibility,
  Feels Like.
- Alerts: active alerts with storm reports, Arrival Tool, and Speed
  Estimator.
- SPC: outlooks, MDs, watches.
- MRMS: rotational tracks, MESH, lightning (instant or 30-min variants
  only).
- Drought: latest only.
- WPC: excessive rain, QPF, meso discussions, winter weather.

Excluded: Tropical (stays a separate page). Deferred: Water (all-or-nothing
as currently built; adding it later is one engine instantiation plus a
config entry, so the decision can wait indefinitely).

### Workspace time-sync design (two-tier layer model)

Timeline tier — radar and satellite only:

- One time-based master clock (not frame-index): a continuous slider over a
  rolling ~60-minute window.
- At scrub time T each timeline layer independently shows its last frame at
  or before T — never a frame newer than T.
- Right edge = live mode; new frames auto-advance the display. Scrubbed
  back, the view freezes at T while ingest continues in the background.
- Prominent state indicator: LIVE vs -N MIN.

Live tier — everything else, including alerts:

- Always latest available. Alerts are ACTIVE ONLY and never scrubbed
  (decision 2026-07-16): expired warning polygons redrawn during an event
  read as current no matter how they are labeled — misleading in exactly
  the situations the workspace exists for. This also removes any need for
  alert-history retention in the workers.
- Refresh: poll each product's lightweight index/latest metadata at its
  natural cadence; swap the overlay only when its timestamp or
  `source_data_key` changed; swap on image load (no flicker). No
  client-side persistence — memory plus browser HTTP cache only.
- Every live layer displays its valid time using the existing staleness
  helpers; silent refresh must never hide staleness.

New workspace-local components: a layer manager (z-order, per-layer
opacity/toggles), compact stacked legends, and `timeline.js` (the master
clock). These live in `pages/workspace/` and may graduate to `core/` only
under ownership rule 2.

### Supersessions (2026-07-16)

- The per-product CSS split deferral (CSS extraction section above) is
  un-deferred; per-page CSS is part of Stage 2.
- Retained rule "product page modules must be included before
  `js/weather.js`" retires when the monolith is deleted.
- Retained rule "preserve hidden `weather-type-*` inputs" retires with the
  shared shell.
- Backlog item "cross-product severe-weather workspace" is promoted into
  this section.

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
- Radar scrubber auto-update now triggers an on-demand backend render on each
  tick via `?refresh=true` on `/api/radar/live/frames`, then restarts the warm
  poll (~3 s interval) to pick up the new frame as soon as the render completes.
  `RADAR_AUTO_REFRESH_MS` is 90 s (was 3 min).
- DONE 2026-07-16: Live radar lookback requests now propagate from
  `/api/radar/live/frames?hours=` into the NODD worker instead of only filtering
  its fixed one-hour cache. The scheduled worker still defaults to one hour;
  a 0.5-12 h UI request starts a coverage-aware background fill when needed,
  downloads and renders missing scans newest-to-oldest in bounded 12-frame
  batches, and preserves the expanded rolling history up to the bounded target.
  Manual history polling continues even when Radar Auto-update is off. The
  slider includes `30M` and preserves fractional hours through route, service,
  and worker wiring. This remains the live-cache path; do not route expanded
  lookback through the archive renderer or restore the old archive logic.
- The "Next Update" countdown element (`wx-radar-next-update-status`) was
  removed; the reliability row "Last Update" timestamp serves as the freshness
  indicator instead.
- The legacy IEM alert-radar loop was removed from the product shell. The
  `weather-alert-radar-enable` checkbox, `weather-opacity-alert-radar` slider,
  and `_alertRadar*` frontend tile/timer/freshness path were deleted from
  `weather.html`, `js/weather.js`, and alert UI test fixtures. `/radar` now
  uses the cache-first `/api/radar/live/*` workflow only; do not reintroduce
  the IEM overlay as a fallback for site/product radar.
- BR.pal reflectivity colormap rewritten with a Radarscope-inspired green scale:
  dark green (5–10 dBZ) → medium green (10–20) → lime (20–25) → yellow (25–30)
  → golden yellow/orange (30–45) → dark-to-bright red (45–55) → pink/mauve
  (55–65) → magenta (65–70) → white (70–75+). `cache_variant` bumped to
  `br_min5dbz_v4` to invalidate stale cached frames.
- Reflectivity legend colorbar now honors the `min_value` floor: products with
  `min_value` defined in the catalog report `legend_vmin` from
  `/api/radar/colortable`, and the colorbar starts at that value (5 dBZ for
  L2_REF / L3_N0B) rather than `vmin` (−30). Logic lives in
  `config/radar_colortable_utils.py` (`_build_legend`, `get_radar_colortable`,
  `get_legend_json`) and `services/radar_service.py` (`get_radar_colortable_data`).
- Super-Res render resolution: Level 2 and L3 Super-Res products (L2_REF,
  L2_VEL, L2_SRV, L2_SW, L2_ZDR, L2_RHO, L2_PHI, L3_N0B, L3_N0G) use
  `figure_size_inches: 22` → ~4400×4400 px at DPI 200, matching their 0.25 km
  gate spacing. All other L3 derived products stay at 12 in (2400 px), which
  already oversamples their 1 km gate spacing. Configured via `figure_size_inches`
  per product in `LIVE_RADAR_PRODUCTS` in `config/radar_config.py`.
- Elevation selection: `_select_sweep` always picks the lowest available tilt
  (`min(fixed_angles)`) as default. The "Auto" option was removed from the UI —
  the seed `<option>` in `weather.html` is `value=""` with no label. L3 products
  have a single fixed sweep and never show elevation pills; that is correct
  behavior (was previously a display bug where the Auto pill appeared for L3).
- L2 chunks workflow (`radar/radar_chunks_utils.py`, `unidata-nexrad-level2-chunks`
  bucket) was **reverted 2026-07-04** — see dated entry below. `LIVE_RADAR_L2_USE_CHUNKS`
  is `False`; the module is left in place but unused should the flag ever flip back.
- `Wx-Dashboard-Radar-Live` scheduled task is now ENABLED at 1-minute intervals
  (changed from 5 min; was previously disabled). L2 runs every invocation; L3
  is gated by `radar_live_l3` freshness sentinel (~5 min effective cadence).
  Freshness sentinels `radar_live` (3 min) and `radar_live_l3` (15 min) are
  registered in `_HEALTH_THRESHOLDS` in `workers/_freshness.py`. Re-run
  `tools/install_tasks.ps1` after any Task Scheduler reset.

#### L2 chunks bucket: bugs, latency benchmark, and revert — 2026-07-04

L2 live radar stopped loading (`unidata-nexrad-level2-chunks` discovery
returning "no recent scans" for sites with heavy chunk history). Root-caused
and fixed a chain of issues in `radar/radar_chunks_utils.py`, then benchmarked
the chunks approach against the flat bucket and reverted:

- **Discovery bug**: `_list_site_chunks` listed the flat `SITE/` prefix with
  `MaxItems=1000`; S3 returns keys in lexicographic order across every VCP
  subfolder a site has ever had, so once a site accumulates enough historical
  subfolders the newest chunks never made it into the capped page. Fixed by
  discovering VCP subfolder names first (cheap `Delimiter="/"` listing) and
  walking them newest-first (`_list_recent_site_chunks`).
- **Poll-performance regression**: the newest-first walk re-listed every
  folder in the lookback window from S3 on every single poll (~30+ calls for
  a 3h window). Fixed with an in-process memo (`_COMPLETE_VCP_CACHE`,
  `_VCP_SCAN_TIME_CACHE`) so folders already confirmed complete are served
  from memory; only the front of the walk (in-progress folders) hits S3.
- **Orphan-folder edge case**: the VCP counter is not perfectly monotonic
  with time — an isolated stray folder (e.g. one leftover chunk from days
  earlier) can sort numerically after the true newest folder and halt the
  newest-first walk immediately. Fixed by requiring 3 consecutive stale
  folders (not 1) before giving up, with a final cutoff filter for safety.
- **Sequential chunk downloads**: `_download_new_chunks` issued one
  `s3_client.get_object` per chunk sequentially; a cold backfill (~10 scans,
  ~700+ chunks) took 50+ seconds. Parallelized with a 16-worker
  `ThreadPoolExecutor` (`_download_one_chunk`) — same backfill dropped to
  ~13s.
- **Latency benchmark, then revert**: compared chunk-completion timestamps
  against the flat bucket's `LastModified` for the same scans — they matched
  to the second. The flat `unidata-nexrad-level2` file is generated by the
  same upstream pipeline the moment the chunk stream finishes, so chunks buy
  **zero** latency benefit for any completed scan. The only real benefit is
  up to one volume-interval (~5-6 min) of early visibility into the
  *currently in-progress* scan. Given that plus the bug history above, L2 was
  reverted to the flat-bucket path (`radar/radar_nodd_utils.py`, same code L3
  already uses) via `LIVE_RADAR_L2_USE_CHUNKS = False` in `radar_config.py`.
  `_resolve_radar_data_utils` in `workers/radar_live_worker.py` is the single
  routing switch; no other code assumes chunks-specific behavior.
- **Scrubber warm-poll bug (separate, frontend-only)**: after the bucket
  revert, Level 2 Play still required a manual Refresh click to pick up
  backfilled frames (L3 worked fine). Two causes, both fixed:
  1. Backend render batches write to `index.json` atomically at the end of
     the whole batch, so a poll mid-render sees zero progress. The frontend
     warm-poll (`_startRadarScrubWarmPoll` in `js/weather.js`) gave up after
     4 consecutive "nothing changed" polls (~12s) — well before a 15-50s
     batch finishes. Added `is_live_render_inflight()` in
     `app_core/background_render.py` (read-only check of the existing dedup
     set) so `get_radar_live_frames_data` in `services/radar_service.py`
     reports an accurate `refreshing` flag on *every* poll, not just the one
     that happened to trigger the render; the frontend now resets its
     stable-poll counter whenever `refreshing` is true.
  2. The real blocker: L2 products have `elevation_selection: True`, so the
     very first `/frames` response calls `updateElevationOptions()`, which
     snaps the elevation `<select>` from `''` (auto) to a concrete value
     (e.g. `"0.5"`). The warm-poll's stale-context guard
     (`_tryAppendNewRadarFrames` in `js/weather.js`) recomputes its context
     key from that same live DOM element on every tick and silently bails
     out once it no longer matches the key captured before the dropdown
     changed — so L2 never auto-polled at all, while L3 (no elevation
     dropdown change) was unaffected. Fixed in `js/radar-engine.js`
     (`loadScrubberFrames`) by re-syncing the stored context key immediately
     after `updateElevationOptions()` runs.
- Cache-busted `js/radar-engine.js` (was stale at `?v=20260623c`) and
  `js/weather.js` in `weather.html`.

2026-07-04 — L2 blank velocity/SRV/SW fix + auto-elevation removal:

- L2 Velocity, Storm-Relative Velocity, and Spectrum Width rendered blank PNGs
  at every site while reflectivity worked. Root cause: NEXRAD split-cut VCPs
  scan the low tilts twice at the same fixed angle — a surveillance sweep
  (reflectivity only) and a Doppler sweep (velocity/spectrum width).
  `_select_sweep` in `workers/radar_live_worker.py` picked purely by fixed
  angle and always landed on the first (surveillance) sweep, where Doppler
  moments are 100% masked. Fixed by making sweep selection field-aware: among
  sweeps within 0.1° of the matched angle, pick the one with the most valid
  data for the field being rendered (`_sweep_valid_count`). Verified on live
  KMPX and PGUA volumes.
- The scheduled worker rendered L2 at `elevation="auto"` (`ELEV_AUTO` dirs)
  while the UI requested `0.5` (`ELEV_0P5` dirs) — a cache-key mismatch that
  made every UI request a miss and triggered a second full on-demand render
  pass per site/product. Added `LIVE_RADAR_L2_DEFAULT_ELEVATION = "0.5"` in
  `config/radar_config.py`; `run_radar_live_worker` now passes it for L2 so
  worker and UI share one cache key. `auto` is no longer used by the UI or
  the worker; stale `*__ELEV_AUTO` directories are orphaned and safe to
  delete.
- Gotcha: blank frames stay listed in `processed_keys.json`, so a fix like
  this does not re-render them — delete the affected product folders or wait
  for new scans.

Current radar notes:

- IEM storm attributes replaced the earlier AWS-NST/AWS-NMD/TGFTP approach.
- `radar_nst_service.py` was removed after the storm-attribute service replaced
  its remaining role.
- Selected-cell SRV and storm-track overlay visibility must remain decoupled so
  hiding tracks does not invalidate the active SRV animation context.
- IEM meso rank 1–3 = weak shear only; do not lower `_MESO_MIN_RANK` below 4
  without comparing against a reference tool (e.g. Radarscope) on a live event.
- The `Wx-Dashboard-Radar-Live` scheduled task runs every 1 minute. L2 products
  use the flat `unidata-nexrad-level2` NODD path; L3 products are internally
  gated by the `radar_live_l3` sentinel and only re-download/render every
  ~5 minutes. On-demand rendering via `?refresh=true` still works as a full
  fallback when the task is not running.
- Do not bump `cache_variant` for BR products without also updating the comment
  in `radar_config.py` and confirming the pal file change is intentional; stale
  frames from the old variant accumulate on disk but are ignored automatically.
- Legacy `/api/radar/tiles/{z}/{x}/{y}` and `/api/radar/tiles/freshness`
  endpoints still exist in `routes/radar.py` / `services/radar_service.py` for
  API compatibility, but the production frontend no longer calls them.

### Satellite and lightning

Completed enhancements (2026-06-28):

- Implemented GOES composites were exposed in the Satellite product selector:
  Fire Temperature, Air Mass, Day Cloud Phase, Day Land Cloud/Fire,
  Day Snow/Fog, Nighttime Microphysics, Dust, Ash, and Sulfur Dioxide.
- Renderer-matched interpretive legends were added for those RGB composites,
  with frontend fallback metadata so legends remain visible through
  satellite/sector/product switches without requiring a hard refresh. Scalar
  colorbars remain limited to brightness-temperature channels.

Completed display updates (2026-07-16):

- GOES `GeoColor` and `GeoColorBlkMar` daytime rendering now uses a CIRA
  logarithmic visible stretch after a bounded ABI Rayleigh-scattering
  correction. GOES frame observation time and projection longitude/height are
  carried through `SourceRaster` into the composite so the day/night blend is
  based on solar zenith (day through 80 degrees, transition to night by
  95 degrees) instead of treating dark ocean/land as nighttime. The established
  CIMSS/Kaba simulated-green coefficients remain in place; NOAA's AHI-derived
  green LUT is not bundled.
- The corrected daytime RGB receives a small saturation adjustment (`1.08`)
  and a GeoColor-only display white point (`0.85`) after the CIRA stretch. The
  latter raises the product into the full display luminance range without
  changing the deep-ocean black point or affecting nighttime RGB/other
  products. User confirmed the corrected hues; final browser confirmation of
  the last white-point lift is pending.
- Filled satellite imagery now renders with PNG alpha 255 and Leaflet layer
  opacity 1.0. Pixels outside valid coverage remain transparent. Sparse
  analytical products retain product-owned transparency: ADP uses
  confidence-graded alpha, AOD keeps its value-driven ramp, and FRP remains a
  translucent sparse overlay. Black Marble city lights are composited into the
  generated RGB before PNG alpha is assigned, so full tile opacity preserves
  rather than hides them. User confirmed the opacity correction.
- Current satellite tile namespaces are `products-v5` (GOES plus the default
  platform path), `products-ahi3` (Himawari-9), and `products-fci3`
  (Meteosat-12). These bumps prevent older partially transparent/corrected
  tiles from masking the new output. `weather.js?v=20260716d` forces the
  matching frontend opacity policy to load.

Completed enhancements (2026-07-16, GOES aerosol/fire products):

- Three new single-instant GOES ABI L2 products added for GOES-18/19:
  **AerosolDetection** (ABI-L2-ADP smoke & dust mask, confidence-graded),
  **AerosolOpticalDepth** (ABI-L2-AOD, high/medium DQF quality, with a discrete
  "No Data" legend swatch), and **FireRadiativePower** (ABI-L2-FDC). Gated
  GOES-only in `js/satellite-page.js`. See the dated "GOES aerosol and fire
  products: ADP, AOD, FRP" section below for the full implementation.

Planned/enhancement direction:

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
- Basemap tile layers may wrap horizontally (`noWrap: false`) to avoid empty
  side gutters at low/world zooms. Weather overlays, vectors, value/place
  markers, and country borders remain single-instance overlays; dateline bbox
  edge cases are still normalized/clamped instead of duplicating data layers.

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

### Satellite tab UX: blank-default / no-auto-load — completed 2026-06-30

Previously the satellite tab defaulted to GOES-19 CONUS and began loading tiles
immediately on page load or tab entry, wasting resources when the user intended
to view a different platform.

Changes:

- **`weather.html`**: both `#weather-satellite-sat-id` and
  `#weather-satellite-sector` selects now have a `<option value="" selected>—
  Select —</option>` as their first option. The GOES-19 and CONUS buttons have
  `aria-selected="false"` by default. Browser native form restoration persists
  the blank selection across hard refreshes — no `localStorage` code needed.
- **`js/satellite-page.js`**:
  - `activeSatId()` and `activeSector()` return `''` when nothing is selected
    (fallbacks to `'goes19'`/`'CONUS'` removed).
  - `syncSectorVisibility()` returns early when `satId` is blank.
  - `syncChannelVisibility()` skips the channel fallback reset when `satId` is
    blank (channel stays at its last value).
  - The `change` event handler on all three selects returns early (after calling
    `clearSatelliteLayerPool`) when either `satId` or `sector` is blank.
- **`js/weather.js`**:
  - `_fetchSatelliteFrameSet` throws `'No satellite or sector selected.'` before
    making any API call when either `_activeSatelliteSatId()` or
    `_activeSatelliteSector()` is blank. This is the single choke point that
    prevents tile requests with `sat_id=&sector=` (which returned 500s).
  - Tab-activation site (satellite tab entry): `loadCurrentFrame` and
    `loadScrubberFrames` are skipped when sat or sector is blank.
  - `_startSatelliteAutoRefresh` and the visibility-change handler already
    guarded on `_satelliteFrames.length > 0`; the `_fetchSatelliteFrameSet`
    throw provides defense-in-depth for any other path.

User experience: on page load, the satellite tab shows the map with no tiles
and both selects at `— Select —`. Selecting a satellite AND a sector triggers a
normal frame load. Deselecting either (returning to `— Select —`) clears the
tile pool. Channel 13 remains the default and does not need a blank option.

### Satellite warm/render lifecycle note — added 2026-07-01

Satellite tile generation can appear to continue after a Ctrl+C and server
restart because the work is cache-backed and restart-triggered:

- `/api/satellite-v2/tile/{z}/{x}/{y}` calls
  `satellite_v2.service.resolve_tile(..., allow_render=True)`. Missing or
  invalid tiles submit an on-demand render to the satellite live tile thread
  pool, so reopening the same product after restart can resume filling missing
  tiles from existing source/catalog cache.
- `app_core.runtime.shutdown_runtime()` calls
  `satellite_v2_service.shutdown_live_tile_pool()` and `stop_scheduler()`.
  These stop server-owned live tile threads and in-process scheduler work on
  app shutdown, but they do not delete cache artifacts.
- OS Task Scheduler workers are separate from the Uvicorn/web process. Stopping
  the server does not stop enabled scheduled tasks such as satellite cache
  refresh jobs. To prove all work is stopped, inspect/stop matching dashboard
  Python processes and relevant Windows scheduled tasks.

### Satellite runtime config consolidation — added 2026-07-04

Satellite backend runtime policy is now centralized in
`config/satellite_v2_config.py`:

- `SATELLITE_V2_LIVE_TILE_RENDER_WORKERS` replaces the hardcoded live tile
  thread count in `satellite_v2/service.py`.
- `SATELLITE_V2_LIVE_SUPERTILE_RADIUS` controls live on-demand neighbor fill.
  The default radius is `1`, so one visible cache miss renders a 3x3 tile
  neighborhood after the requested tile has rendered, skipping already-valid
  tiles and negative-cache markers.
- `SATELLITE_V2_ON_DEMAND_CATALOG_HOURS`,
  `SATELLITE_V2_ON_DEMAND_CATALOG_MAX_FRAMES`,
  `SATELLITE_V2_LEGEND_ANCHOR_COUNT`, and
  `SATELLITE_V2_LEGEND_TICK_COUNT` replace local service constants.
- `SATELLITE_V2_NETCDF_CACHE_SIZE` and
  `SATELLITE_V2_RENDERER_CACHE_SIZE` replace renderer-local env parsing.
- `SATELLITE_V2_GOES_FULLDISK_MAX_GRID`, `SATELLITE_V2_AHI_MAX_GRID`, and
  `SATELLITE_V2_FCI_MAX_GRID` are the provider-specific Full Disk source-grid
  caps for GOES, Himawari AHI, and Meteosat FCI. Provider/parser modules import
  these values directly, so future high-resolution tuning should start in this
  config file.
- Frontend satellite animation prefetch is cache-only as of 2026-07-04. The
  active Leaflet layer still live-renders visible tile misses, but background
  prefetch requests use `render_live=0` so Himawari/Meteosat Full Disk frame
  setup does not compete with the first visible static image.
- Live supertile testing passed for Himawari Full Disk, GOES CONUS, and GOES
  Meso1 Channel02. A bug found during testing where requested invalid/off-disk
  tiles could keep filling neighbors and produce a 500 was fixed; requested
  invalid tiles now return the normal transparent invalid response, and neighbor
  fill errors are counted as `supertile_errors` without poisoning the visible
  tile request.

### Satellite rapid-sector worker — added 2026-07-04

A new isolated rapid warmer replaced the broad Satellite v2 scheduled workers:

- Entry points: `satellite_v2/rapid_worker.py` and
  `workers/satellite_v2_rapid_worker.py`.
- Default jobs: GOES-19/18 `MESO1`/`MESO2`, Himawari-9 `JAPAN`, and
  Meteosat-11 `RSS`.
- Default products: `Channel02` and `Channel13`.
- Default policy: latest 12 frames, low tile-worker count (`2`), cache-first
  canvas warming, and small per-sector zoom targets (`MESO` 7/8, `JAPAN` and
  `RSS` 6/7).
- Himawari `TARGET` is intentionally not warmed by default because it is
  dynamically retasked and the catalog does not yet publish per-frame bounds.
  Add it only after implementing target-frame bounds or accepting a broad
  guessed warm box.
- Full Disk and broad CONUS prewarming remain excluded; those paths should use
  live rendering, supertiles, and cross-session cache reuse.
- Removed old broad-worker modules/launchers and old worker config profiles:
  `satellite_v2/worker.py`, `satellite_v2/worker_new.py`,
  `workers/satellite_v2_worker.py`, `workers/satellite_v2_meso_worker.py`,
  `workers/satellite_v2_light_composites_worker.py`, and
  `workers/satellite_v2_geocolor_worker.py`.
- `workers/scheduler.py` now registers only the rapid worker in the optional
  in-process fallback scheduler. `workers/_freshness.py` now expects only the
  `satellite_v2_rapid` sentinel for Satellite v2. `tools/install_tasks.ps1`
  registers `Wx-Dashboard-Satellite_v2_rapid` and unregisters legacy
  `Wx-Dashboard-Satellite_v2*` broad-worker task names when run.

### Meteosat source-prefetch worker — added 2026-07-04

Cold Meteosat loads took 3-4 minutes because the first product on a frame
pays the full EUMETSAT download (~790 MB FCI chunk set per Meteosat-12 frame,
~270 MB SEVIRI `.nat` per Meteosat-9 frame). EUMETSAT frames are all-channel
bundles, so one prefetched frame warms every product — switching channels on
a warm frame is near-instant (parse + warp only).

- New `satellite_v2/meteosat_prefetch_worker.py` +
  `workers/satellite_v2_meteosat_prefetch_worker.py` entrypoint. Download-only:
  fills the shared source cache via `providers.download_product_source_frames`;
  renders nothing.
- Per run: downloads the newest N missing frames (default 2 = current + 1),
  then up to 1 oldest missing frame inside the lookback window (default 6 h),
  so animation depth backfills gradually across runs. Completeness checks use
  the FCI `manifest.json` (all chunks present) or the SEVIRI `.nat` size.
- Prunes source frame dirs older than the keep window (default 7 h). ~6 h of
  both platforms ≈ 35 GB of source cache at steady state.
- Config in `config/satellite_v2_config.py`
  (`SATELLITE_V2_METEOSAT_PREFETCH_*`): jobs (meteosat12/meteosat9 FULLDISK),
  frames/backfill per run, lookback, keep hours, fresh window. All
  env-overridable.
- Scheduled task `Wx-Dashboard-Satellite_v2_meteosat_prefetch` (10 min cadence,
  25-min ExecutionTimeLimit — `install_tasks.ps1` now supports per-task
  `TimeLimit`). Registered ENABLED by default. Also added to the in-process
  fallback scheduler and `_freshness.py` health thresholds (45 min, generous
  because a cold backfill run legitimately downloads for 15+ min).
- Interrupted runs are safe: per-file atomic downloads (tmp + rename) and the
  FCI manifest is only written after all chunks land, so a killed run resumes
  where it left off.
- Himawari-9 deliberately excluded: AHI segments are per-band files (no
  all-channel bundle bonus) and per-band downloads are small; revisit only if
  Himawari cold loads become a complaint.
- Validated against the live EUMETSAT catalog: frames downloaded during the
  2026-07-04 browser session report cached=True; missing frames report False.
- User browser smoke passed 2026-07-04 (late evening): Meteosat-12 Channel02
  FULLDISK on a prefetched frame rendered at ~250 ms/tile ("faster by
  minutes" vs the cold-download flow). Off-disk tiles at low zoom correctly
  return the negative-cached invalid/transparent response — `result=invalid`
  in the tile log for space-only tiles is expected, not an error.
- Post-install fix: the EUMETSAT catalog search returns frames older than the
  requested lookback window, so the backfill was repeatedly downloading
  frames the keep-window prune deleted on the same run (~790 MB wasted per
  run). The worker now filters the frame list to the lookback window before
  selecting downloads.

Optional future CONUS light-warm plan:

- Keep it separate from the rapid default. CONUS currently works well with live
  rendering, supertiles, and cache reuse.
- If first-load latency becomes worth the background cost, add a disabled/opt-in
  light worker for GOES-19/18 `CONUS` only, latest 1-2 frames, `Channel02` and
  `Channel13`, zooms `(5, 6)`, and `tile_workers=1-2`.
- Do not reintroduce broad CONUS product/profile warming; the light worker
  should remain cache-first, current-frame biased, and easy to disable.

### Global satellite coverage

#### Himawari-9 — removed 2026-07-01

The Himawari-9 pipeline (built 2026-06-29/30) was fully removed. It relied on
satpy/pyresample to ingest raw AHI HSD segments and resample them to an
intermediate equirectangular lat/lon npz grid before tiling. Two problems
drove the removal rather than an incremental fix:

- `dask`'s default threaded scheduler grabs all CPU cores (32 on this host)
  for every single satpy `Scene.load()`/`.resample()` call, with no cap
  configured. Ingest calls already ran inside our own on-demand
  `ThreadPoolExecutor`, so concurrent new-frame requests (e.g. scrubber
  prefetch) caused massive thread oversubscription — tens to 100+ threads
  fighting over 32 physical cores — which stalled the entire dashboard
  process, not just the satellite tab.
- More fundamentally, satpy's resample-to-lat/lon-grid approach was
  architecturally heavier than necessary: AHI HSD files are natively
  geostationary with a fixed pixel grid (COFF/CFAC/LOFF/LFAC), the same way
  GOES ABI NetCDF is, so the ingest could instead parse the raw format
  directly and reuse the existing fast GOES `SourceRaster`/GDAL-warp render
  path with no satpy/pyresample/dask involved at all.

Removed: `satellite_v2/provider_himawari.py`, `satellite_v2/latlon_grid.py`,
`satellite_v2/worker_himawari.py`, `workers/satellite_v2_himawari_worker.py`,
the `SatelliteTileRenderer.from_latlon_npz` classmethod and
`render_frame_tile_himawari`/`warm_himawari_frame_tiles`/
`_get_or_load_himawari_renderer` in `satellite_v2/tiler.py`, all Himawari/AHI
config in `config/satellite_v2_config.py` and `config/satellite_platforms.py`
(including the `JAPAN` sector), the `Satellite_v2_himawari` scheduled task
entry in `tools/install_tasks.ps1`, and all frontend Himawari references in
`js/satellite-page.js` / `js/weather.js` / `weather.html`. Himawari cache
directories under `cache/satellite/{catalog,source,tiles}/**himawari9**` were
deleted. GOES (`goes18`/`goes19`) is unaffected — it never used the
lat/lon-grid path.

A native-AHI-format rewrite (no satpy) remains a real option if Himawari
coverage is revisited, but has not been started.

#### Himawari-9 — rebuilt on native AHI HSD parser 2026-07-02

Himawari-9 FULLDISK is live again on a clean-sheet native pipeline with zero
satpy/pyresample/dask involvement:

- `satellite_v2/ahi_hsd.py` (new): pure-numpy JMA HSD parser. Reads header
  blocks 1/2/3/5/7 (basic/data/projection/calibration/segment), decompresses
  bz2 transparently, calibrates counts to GOES-CMI-equivalent semantics
  (reflectance factor for bands 1-6 via the c' coefficient, brightness
  temperature for bands 7-16 via inverse Planck + JMA quadratic correction
  using constants stored in block 5), stitches the 10 FLDK segments, and
  returns a north-up grid + rasterio geos transform/CRS
  (`+proj=geos +h=35785863 +lon_0=140.7 +sweep=y`). Two hard guards:
  - 1 km/0.5 km bands are strided to the 2 km 5500-px grid on load
    (`AHI_MAX_GRID`) — the 484 MP FULLDISK visible OOM class is
    structurally impossible.
  - A geostationary Earth-visibility mask (ray-ellipsoid discriminant) NaNs
    deep-space pixels; JMA leaves instrument noise counts (~60-165 K after
    calibration) off-Earth instead of flagging them like GOES CMI does.
- `satellite_v2/provider_himawari.py` (new): `noaa-himawari9` S3 listing
  (`AHI-L1b-FLDK/YYYY/MM/DD/HHMM/`, 10-minute timeslots), complete-slot
  detection (all 10 segments present), FULLDISK-only validation. A frame's
  `source_keys` store the S01 segment key per source channel; the other
  segment keys are derived from the filename `SnnNN` token at download time.
- `satellite_v2/providers.py` (new): provider dispatch by platform
  descriptor (`config/satellite_platforms.py`, first real consumer of the
  Phase-1 abstraction). `catalog.py`/`service.py`/`tiler.py` now import
  `list_recent_frames`/`download_product_source_frames` from here.
- `satellite_v2/renderer.py`: `_load_source_raster` dispatches on `.DAT`/
  `.DAT.bz2` to an AHI loader that globs sibling segments from the frame's
  source-cache dir and wraps them in the same `SourceRaster`; the GDAL-warp
  `render_zoom_canvas` path is untouched and shared with GOES. The renderer
  LRU keyed on the S01 file signature keeps the parsed 121 MB grid in memory
  across tiles of the same frame (~3.8 s cold incl. download, ~65 ms after).
- Config: `himawari9` added to `SATELLITE_V2_SUPPORTED_SATELLITES` and
  `satellite_platforms.py` (implemented, FULLDISK only, lon_0 140.7,
  provider `aws_himawari`); `AHI_BAND_FOR_ABI_CHANNEL` maps ABI-named
  product keys to AHI bands (C02→B03 red visible, C03→B04 veggie, others
  1:1) so all product keys stay ABI-named everywhere; render version for
  himawari9 is `products-ahi1`.
- Frontend: Himawari-9 platform button + select option restored in
  `weather.html`, `himawari9` added to `PLATFORM_SECTORS` (FullDisk only) and
  `IMPLEMENTED_SATELLITES` in `js/satellite-page.js` (`?v=20260702c`). All
  channels/composites are enabled — every ABI source channel used by the
  dashboard products has an AHI equivalent. Dead `Japan` sector option
  removed from the sector select.
- Operational model: on-demand rendering only (same as GOES FULLDISK — no
  scheduled warm task, no worker profile). Warm paths are unreachable for
  himawari9, so the GOES-centric FULLDISK sector bounds are never consulted
  for it.

Validation (2026-07-02, live data): header fields match the JMA spec across
2 km and 0.5 km grids; B13 BT range 185.9-300.6 K after the Earth mask; B03
reflectance 0-1.19 with the sunlit crescent on the correct (east) limb;
geolocation checked against basemap coastlines (Australia, Timor, PNG) with
no flip/mirror/offset; end-to-end catalog→download→tile through
`service.resolve_tile` with disk-cache hit on repeat; GOES listing regression
passed through the new dispatch layer. Standalone validator:
`tools/validate_ahi_native.py --band N --out DIR`. Browser smoke is
user-owned and still pending.

Planned:

- Add Meteosat platforms by operational role:
  - Meteosat-12: Europe/Africa full disk.
  - Meteosat-11: rapid-scan Europe and North Africa.
  - Meteosat-9: Indian Ocean.
- Do not expose Meteosat-10 initially.
- Generalize the GOES-specific provider/channel/projection/sector/cache model
  into platform descriptors and capability matrices.
- Use optional server-side EUMETSAT credentials and hide unavailable platforms
  cleanly when credentials are absent.

Current international-satellite product direction:

- Finish the current non-GOES platforms before adding more sources:
  Himawari-9, Meteosat-9, and Meteosat-12 should expose a small standard
  product set rather than every possible raw channel/RGB.
- Standard non-GOES product set, in priority order: Visible, Enhanced IR,
  Water Vapor, Shortwave IR/Fire, Night Microphysics, Dust, Ash, and SO2.
  Each product must have explicit per-instrument channel mapping and at least
  one proof render before appearing in the UI.
  Status 2026-07-10: 7 of 8 complete for Meteosat-9/11/12 (see the
  "Meteosat standard composites" section below). SO2 is intentionally
  dropped for Meteosat: the recipe's red beam is `C09 − C10`, SEVIRI aliases
  both to WV_073 (red ≡ constant), and FCI cannot map C09/C10 faithfully
  without corrupting the exposed Channel09 WV scalar. Doing SO2 right needs
  per-instrument recipe-level channel overrides — V2 if ever.
- Defer CIRA GeoColor / True Color / Natural Color / other RGB parity to V2.
  Full-disk RGB source loading can be expensive, especially for FCI and
  high-resolution visible channels, so RGB should wait until standard products,
  auto-centering, and named extent presets are stable.
- DONE 2026-07-02: Added frontend named view presets for satellite
  platform/sector switches. `js/satellite-page.js` now maps platform+sector
  pairs to fitted map bounds for GOES Full Disk/CONUS/Meso defaults,
  Himawari-9 Full Disk, Meteosat-12 Full Disk, and Meteosat-9 Full Disk.
  `js/weather.js` exposes the existing Leaflet map through
  `fitSatelliteViewPreset(...)`, and `weather.html` bumps
  `satellite-page.js` to `?v=20260702e`. Satellite platform changes now clear
  the sector selection first, so moving between platforms such as Himawari-9
  and GOES-18 does not start catalog/tile work until the user explicitly picks
  a sector. The auto-fit runs only after a sector is selected; product/channel
  changes preserve user pan/zoom while browsing products.
- DONE 2026-07-02: Added a user-facing `View` select separate from data
  sectors. The control is filtered by selected platform and fits named extents
  without triggering catalog or tile generation. Sector selection still
  auto-selects the matching default view. `weather.html` now loads
  `satellite-page.js?v=20260702h`. Browser testing tightened the Meteosat-12
  Europe/Africa view from the full disk footprint to a practical
  `[-38,-35]`-to-`[62,48]` inspection extent so it does not zoom out to a
  near-world view. Browser smoke passed for Himawari-9, Meteosat-9, and
  Meteosat-12 platform selection, sector clearing, view presets, and first
  tile load.
- DONE 2026-07-03: Warm/prefetch planning is viewport-aware without blocking
  direct tile requests. Frontend animation prefetch uses current map bounds
  plus an explicit one-tile buffer and reschedules on `moveend`/`zoomend`.
  Direct Leaflet `/api/satellite-v2/tile/{z}/{x}/{y}` requests still render
  normally if requested. Backend warm planning now has an opt-in bounds filter:
  `satellite_v2.tiler.planning_tile_coords(...)` keeps existing sector-wide
  behavior by default, while `warm_frame_tiles(...)` /
  `warm_frame_tiles_from_canvas(...)` accept `tile_bounds` + `tile_buffer`.
  Explicit worker runs can pass named-view bounds with
  `--bounds west,south,east,north --tile-buffer 1`; scheduled runs pass no
  bounds and are unchanged until intentionally configured.
- Possible current-plan or V2 enhancement: reuse the same viewport-aware
  satellite bounds logic from the Tropical page. When a user opens an active
  system, Tropical could derive a storm-centered extent from the latest
  reported fix (or track/cone bounds), fit the map there, and let live
  on-demand satellite rendering plus animation prefetch fill only that
  viewport+buffer. If first-frame readiness proves too slow, add a thin async
  bounded warm helper later that accepts storm bounds, selected satellite,
  sector, product, and frame count. Prefer the live-on-demand version first
  because it needs less orchestration and cannot warm stale or wrong storm
  locations.
- After the current platforms, auto-center, standard products, and extent
  presets are complete, add these future sources:
  - GK2A from `arn:aws:s3:::noaa-gk2a-pds`.
  - NOAA GMGSI Meteosat composite from `noaa-gmgsi-pds`.

#### Meteosat-9 — native SEVIRI `.nat` validation completed 2026-07-02

Meteosat-9 IODC is live on the native Satellite v2 path:

- `satellite_v2/provider_eumetsat.py`: EUMETSAT OAuth/search/download works
  with credentials loaded explicitly from `F:\Python\dashboard_2026\.env`
  (supports `EUMETSAT_CONSUMER_*` and `WX_EUMETSAT_CONSUMER_*`). The provider
  downloads the HRSEVIRI-IODC `.nat` entry and stores one shared SEVIRI source
  bundle per frame.
- `satellite_v2/seviri_nat.py` (new): pure-numpy MSG native parser for 3712 px
  VIS/IR full disk. It reads the archive/header fields needed for Meteosat-9,
  unpacks 10-bit channel lines, flips the native south/east grid to north-up
  west-east, calibrates IR channels to brightness temperature and visible
  channels to GOES-like reflectance factors, and returns a rasterio geos
  transform/CRS (`+proj=geos +h=35785831 +lon_0=45.5 +sweep=y`).
- `config/satellite_platforms.py` and `js/satellite-page.js`: Meteosat-9 is
  marked implemented. The frontend product select is filtered to
  SEVIRI-compatible products only.
- `satellite_v2/service.py`: tile diagnostics now report the platform provider
  (`eumetsat`) instead of the old hardcoded `aws` label.

Validation (2026-07-02, live data): downloaded
`MSG2-SEVI-MSG15-0100-NA-20260702185739.917000000Z-NA.nat` (271,175,723 bytes)
and parsed Channel 13/IR_108 with BT range 182.70-307.55 K, mean 278.52 K,
74.0% finite disk coverage. Native unpack/calibration was numerically checked
against Satpy for the same file before removing Satpy from the parser path.
Standalone proof command:
`tools/validate_seviri_native.py --nat cache\satellite\validation\eumetsat\satellite\source\meteosat9\FULLDISK\SEVIRI\20260702T184500Z\MSG2-SEVI-MSG15-0100-NA-20260702185739.917000000Z-NA.nat --out cache\satellite\validation\seviri_proofs`.
Proof images show correct disk/India coastline alignment with no flip or
offset. End-to-end backend smoke passed through
`service.get_catalog_payload(...)` and `service.resolve_tile(...)`, rendering
tile `meteosat9/FULLDISK/Channel13/20260702T190000Z/5/21/15.png` (97,803
bytes) and then cache-hitting it with provider `eumetsat`.

#### Meteosat-12 — FCI Full Disk direct products validated 2026-07-02

Meteosat-12 Full Disk is live for the first direct FCI scalar products:

- `satellite_v2/provider_eumetsat.py`: `meteosat12` uses collection
  `EO:EUM:DAT:0662`. Unlike Meteosat-9, each frame is a set of numbered
  NetCDF `CHK-BODY` chunks; the provider downloads all body chunks for the
  selected full-disk frame into a shared `FCI` source-cache directory.
- `satellite_v2/fci_nc.py` (new): stitches FCI body chunks for one requested
  channel, calibrates IR radiance to brightness temperature using per-file
  conversion constants, flips the native grid to north-up west-east, and
  returns a rasterio geos transform/CRS (`+proj=geos +h=35786400 +lon_0=0
  +sweep=y`).
- FCI source-channel mapping now covers direct IR/WV channels needed for the
  standard scalar product set: ABI `Channel07` -> FCI `ir_38`, `Channel08` ->
  `wv_63`, `Channel09` -> `wv_73`, `Channel10` -> `ir_97`, `Channel11` ->
  `ir_87`, `Channel13` -> `ir_105`, `Channel14` -> `ir_123`, and
  `Channel15` -> `ir_133`. `js/satellite-page.js` exposes Meteosat-12
  `Channel07`, `Channel07Fire`, `Channel08RAMSDIS`, `Channel09RAMSDIS`, and
  `Channel13` only. Composite products that become technically source-mapped
  (AirMass, Night Microphysics, Dust, Ash, SO2, etc.) stay hidden from the UI
  until each has a proof render. RSS remains deferred.
- `config/satellite_platforms.py`: Meteosat-12 is marked implemented with
  instrument `FCI`, provider `eumetsat`, sector `FULLDISK`.

Validation (2026-07-02, live data): cataloged
`EO:EUM:DAT:0662` frame `20260702T190000Z` and downloaded 40 FCI body chunks
totaling 791,937,141 bytes. The assembled `ir_105` grid is 5568x5568 with BT
range 182.94-308.11 K, mean 280.61 K, 74.5% finite disk coverage. End-to-end
backend smoke passed through `service.resolve_tile(...)`, rendering
`meteosat12/FULLDISK/Channel13/20260702T190000Z/4/8/6.png` (82,043 bytes)
and cache-hitting it with provider `eumetsat`. Coastline proof image:
`cache\satellite\validation\fci_proofs\fci_channel13_20260702T190000Z_disk_z3.png`;
visual check shows Europe/Africa alignment with no obvious flip or offset.
Cached extraction smoke (2026-07-02 frame `20260702T174500Z`) confirmed
`Channel07`/`ir_38`, `Channel08`/`wv_63`, `Channel09`/`wv_73`, and
`Channel13`/`ir_105` all load as 5568x5568 grids with 74.5% finite disk
coverage before UI exposure.
Browser smoke passed for selecting Meteosat-12 in the Satellite tab.

#### Meteosat pipeline efficiency pass + FCI orientation fix — 2026-07-03

Efficiency changes mirroring the Himawari optimizations:

- `satellite_v2/provider_eumetsat.py`: `_download_fci_chunks` now writes a
  `manifest.json` (chunk filename list) into the frame's `FCI` source dir
  after all chunks are verified on disk. When the manifest is present and
  every listed chunk exists, the loader returns immediately (~2 ms) instead
  of re-running the EUMETSAT OpenSearch on every renderer load — previously
  every FCI renderer construction made a live API call even on full cache
  hit. An incomplete manifest or missing chunk falls through to the normal
  search+download path, so interrupted downloads can never render partial
  strips. Missing chunks download in parallel (`_FCI_DOWNLOAD_WORKERS = 4`),
  cutting the ~792 MB / 40-chunk cold-frame download several-fold. SEVIRI
  (.nat) needed no changes: single file, exists-check before download.
- `satellite_v2/fci_nc.py`: `FCI_MAX_GRID = 5500` stride cap, mirroring
  `AHI_MAX_GRID` and the GOES FULLDISK stride. Strips are strided on load,
  so FDHSI 1 km channels (vis_06 = 11136² ≈ 500 MB float32) assemble at
  5568² and the full-resolution array is never materialised. 2 km IR
  channels are unaffected (stride 1). Strided sampling verified bit-exact
  against full-resolution assembly + decimation on live cached vis_06 data.
  This unblocks the planned `Channel02` → `vis_06` exposure memory-wise.

Correctness bug found during verification — FCI disk was east-west MIRRORED:

- The original loader flipped both axes (`[::-1, ::-1]`) assuming the MSG
  SEVIRI south-east origin. FCI L1c actually stores columns already
  west→east; the x coordinate variable's positive fixed-grid scan angle
  points WEST (opposite PROJ geos +x=east), so the descending x axis had
  masked the mirror. All Meteosat-12 tiles rendered before 2026-07-03 were
  east-west mirrored (the 2026-07-02 coastline proof was misjudged).
- Fix in `load_fci_raster`: flip rows only (`[::-1, :]`) and negate the x
  axis (`-(x_raw * height)`) instead of reversing it — negation is also
  exact for strided offset-center sampling where reversal would shift the
  grid by one source pixel.
- Verified: Meteosat-12 ir_105 vs Satpy-validated Meteosat-9 IR_108 for the
  same 17:45 UTC slot warped to one lon/lat grid correlates 0.933 as-is
  (0.188 mirrored; the pre-fix code scored the reverse). Solar terminator
  checks on 17:45/19:45/00:45 UTC frames put the lit side west+north as
  physics requires; the 00:45 disk is fully dark.
- `config/satellite_v2_config.py`: `SATELLITE_V2_RENDER_VERSION_METEOSAT12 =
  "products-fci1"` orphans all mirrored cached tiles; GOES/Himawari/
  Meteosat-9 tile caches are untouched (SEVIRI orientation was validated
  numerically against Satpy and is correct).

Browser smoke for Meteosat-12 after the mirror fix completed 2026-07-03.
Initial animation load (6 frames over Africa, zoom 5) takes ~60 sec because
each frame requires an independent EUMETSAT catalog search + 40-chunk download
(~10–15 sec per frame); GOES/Himawari benefit from AWS S3 edge caching that
EUMETSAT lacks. Manifest cache accelerates repeat plays of the same timeslot
and manual scrubbing. Tiles persist and render correctly post-fix.

#### Meteosat standard composites: Night Microphysics, Dust, Ash — 2026-07-10

The last three implementable products of the standard non-GOES set are live
on Meteosat-9, Meteosat-11, and Meteosat-12. All three are IR-only, so they
work day and night and add **no download cost** — every source channel
already ships inside the frame's single `.nat` (SEVIRI) or shared FCI chunk
set; only the extra channel extraction and composite math are new.

- `config/satellite_v2_config.py`: FCI aliases corrected — `Channel14 →
  ir_105` (was `ir_123`) and `Channel15 → ir_123` (was `ir_133`, the 13.3 µm
  CO2 band, physically wrong for split-window recipes). With the aliases,
  the goes2go Night Microphysics / Dust / Ash recipes reduce exactly to the
  canonical EUMETSAT MTG RGBs, mirroring the SEVIRI table's `C13/C14 →
  IR_108` trick. Nothing exposed or prefetched used FCI C14/C15, so no
  render-version bump was needed.
- `js/satellite-page.js` (`?v=20260710b`): `NighttimeMicrophysics`, `Dust`,
  `Ash` added to `PLATFORM_CHANNELS` for `meteosat9`, `meteosat11`, and
  `meteosat12`.
- SO2 is intentionally skipped for Meteosat (see the standard-set note in
  the planning section above): SEVIRI's alias table makes the recipe's red
  beam a constant, and FCI can't map it without breaking the exposed C09 WV
  scalar. Requires recipe-level per-instrument overrides — deferred.
- Proofs (2026-07-11T0100Z-ish cached frames, night over Africa): all 3
  composites × both instruments render 100% opaque with healthy variance in
  every band; palette behavior matches a GOES-19 CONUS Night Microphysics
  reference rendered through the same recipe, and M9 Dust shows the
  canonical look (warm land pink, convective cores dark red, cold Southern
  Ocean olive). Proof PNGs in `cache\satellite\validation\fci_proofs\`
  (`meteosat{9,12}_{NighttimeMicrophysics,Dust,Ash}_proof_z3.png` plus the
  GOES reference). Meteosat-11 has no cached RSS source to proof against,
  but it shares the SEVIRI parser and composite path with Meteosat-9
  end-to-end; browser spot-check of one RSS composite is user-owned.
- Legends: interpretive RGB legends are keyed by product, so the existing
  GOES legends for these three composites apply to Meteosat automatically
  (verified via `get_legend_payload`).

Browser smoke passed 2026-07-10: user tested the three RGB composites on
the Meteosat platforms and confirmed the output, and separately confirmed
satisfaction with visible-channel reflectance rendering (the shared
scalar-reflectance stretch), closing out that follow-up.

#### Satellite UI dependency chain + Meteosat visible channel — 2026-07-03

UI dependency chain: **Satellite → Sector → View → Product**

All selections must be explicit; tiles do not load until all four are chosen.

- `weather.html`: Added "Full Disk" as default view option; added
  "— Choose Product —" placeholder as default Product option (prevents
  auto-load with fallback channel).
- `js/satellite-page.js`: View dropdown disabled until Sector selected;
  Product dropdown disabled until View selected. New functions
  `syncViewPresetEnabled()` and `syncChannelEnabled()` manage the
  disabled state. `activeChannel()` now returns empty string when no
  product selected (was defaulting to Channel13). Tile-loading check
  requires all four selections non-empty. Verified: correct enable/disable
  sequence and no auto-load until product explicitly chosen.

Meteosat-12 `Channel02` → FCI `vis_06` visible scalar added:

- `config/satellite_v2_config.py`: Added `"Channel02": "vis_06"` to
  `FCI_CHANNEL_FOR_ABI_CHANNEL` mapping.
- `js/satellite-page.js`: Exposed `Channel02` in Meteosat-12 product list;
  pruned composites from Meteosat-9 and Meteosat-12 (deferred to V2).
  Himawari-9 retained full GOES product list (identical ABI).
- Proof validation (2026-07-03T194500Z frame): reflectance range 0–0.7633 K,
  68.8% disk coverage, 9.7% bright pixels (correct for 19:45 UTC sunset);
  cloud detail over West Africa coast visible; calibration verified.
- Product dropdown now correctly filters by satellite:
  - Himawari-9: All GOES products (ABI-identical rendering speed)
  - Meteosat-12: Channel02, 07, 07Fire, 08RAMSDIS, 09RAMSDIS, 13 only
  - Meteosat-9: Channel02, 03, 07, 07Fire, 08RAMSDIS, 09RAMSDIS, 13 only
  - GOES: Full product list (unchanged)

Next visible-products sequence for non-NOAA satellites:

1. ✅ Meteosat-12 `Channel02` → `vis_06` proof completed and exposed.
   Daylight browser smoke passed 2026-07-04; night full-disk smoke passed the
   same evening on a prefetched frame (~250 ms/tile).
2. ✅ Reflectance display stretch completed 2026-07-10. User evaluation
   confirmed that visible imagery from Meteosat had the same flat appearance
   as the other providers, with too little distinction between darker and
   lighter image areas. The renderer already applied a power-law stretch to
   Channels 01-03, so the missing step was contrast-range expansion rather
   than a second gamma adjustment. All scalar reflectance products
   (Channels 01-06) now use one provider-independent display transform: clip
   linear reflectance to a fixed 0.02-0.90 window, normalize it to 0-1, then
   apply `sqrt`. Fixed bounds avoid tile seams and animation flicker; RGB
   recipes remain unchanged. Render namespaces advanced to `products-v3`,
   `products-ahi2`, and `products-fci2` so old tiles do not mask the change.
   Focused tests passed, and a direct browser smoke against the new local
   server returned a valid 256x256 GOES-18 Channel02 tile. On the same tile,
   the grayscale p5-p95 span increased from 141 to 178 levels. Full-page user
   comparison remains the final visual acceptance step. Optional later:
   solar-zenith normalization.
3. Continue with Meteosat-9 visible channels if `Channel02`/`Channel03` mapping
   is needed; otherwise defer to next visible band (Shortwave IR/Fire) in
   the standard product set.
4. Expand cautiously after the first visible proof. Candidate mappings:
   `Channel01` -> FCI `vis_04`, `Channel03` -> FCI `vis_08` or `vis_09`,
   `Channel05` -> FCI `nir_16`, and `Channel06` -> FCI `nir_22`.
5. Revisit composites only after their source mappings have individual scalar
   proof renders. Candidate follow-ups include Day Cloud Phase, Fire
   Temperature, Natural/True Color, and related RGB products. Meteosat-9
   already has SEVIRI visible-equivalent support, so Meteosat-12 FCI visible
   exposure is the larger near-term gap.

Himawari (deferred): checked the `AHI-L1b-Target` S3 prefix for rapid-scan
target areas — `R301`-`R304` are a single persistent ~1000km volcanic-watch
box near 142°E/26.6°N (Izu/Bonin arc), not a general-purpose movable sector,
so it was not worth adding even before the pipeline itself was removed.

#### Meteosat-11 Rapid Scan Service (RSS) — validated 2026-07-03

Meteosat-11 RSS is live, giving the dashboard a 5-minute-cadence
Europe/North Africa product alongside the 15-minute Meteosat-9/12 full disks:

- EUMETSAT collection `EO:EUM:DAT:MSG:MSG15-RSS`. Product IDs use the
  `MSG4` prefix (satellite_id 324 in the native header) — EUMETSAT's
  currently-operating RSS satellite, publicly branded Meteosat-11.
  Calibration constants for platform 324 already existed in
  `satellite_v2/seviri_nat.py` (reused from the Meteosat-9 work), so no new
  calibration table was needed.
- `satellite_v2/provider_eumetsat.py`: `_SLOT_MINUTES` changed from a single
  module constant to a per-satellite dict (5 min for RSS vs 15 min for full
  disk); `_require_fulldisk` generalized to `_require_supported_sector` so
  each platform can declare its own allowed sector (`RSS` for Meteosat-11).
  New `RSS` sector key added to `SATELLITE_V2_SUPPORTED_SECTORS`.
- Real bug found and fixed during validation: RSS products are a cropped
  northern strip (3712 columns x 1392 lines, not the full 3712x3712 disk).
  `seviri_nat.py`'s `_source_georef` assumed the grid is always centered on
  the sub-satellite point, which is true for full disk but placed the RSS
  strip incorrectly near the equator instead of its actual ~13-68N position
  at 9.5E. Fixed by reading the native header's
  `SouthLineSelectedRectangle`/`NorthLineSelectedRectangle`/`East`/
  `WestColumnSelectedRectangle` fields and computing bounds relative to the
  full 3712-line/column reference grid rather than the cropped array's own
  dimensions. Verified with a coastline ghost-overlay proof render over
  Europe before wiring the UI.
- `config/satellite_platforms.py`: new `meteosat11` descriptor (instrument
  SEVIRI, provider eumetsat, sectors `["RSS"]`, lon_0 9.5).
- Frontend: platform button, `PLATFORM_SECTORS.meteosat11 = ['RSS']`,
  `PLATFORM_CHANNELS.meteosat11` (same scalar set as Meteosat-9), and a new
  `europe-rss` named view preset. The RSS sector toggle button and native
  `<option value="RSS">` already existed pre-hidden in `weather.html` from
  earlier scaffolding; only needed un-hiding via the existing
  `PLATFORM_SECTORS`-driven visibility logic. `weather.html` bumped to
  `satellite-page.js?v=20260703a`.
- User browser-tested and confirmed working 2026-07-03.

#### Himawari-9 Japan Area and Target Area sectors — added 2026-07-03

Investigated after confirming Himawari-9's `AHI-L1b-Target` prefix is not
always the fixed Izu/Bonin volcanic-watch box noted earlier: JMA dynamically
retasks it (observed pointed at a typhoon near the Vietnam/Hainan coast,
`ObsMode=TY`, center ~109.7E/18.5N). A second prefix, `AHI-L1b-Japan`, had
not been examined before and turned out to be a genuine fixed-box rapid-scan
product.

- S3 bucket structure: `noaa-himawari9` has exactly three top-level AHI-L1b
  prefixes — `FLDK` (full disk, already implemented), `Japan`, and `Target`.
- Both `Japan` (`JP01`..`JP04`) and `Target` (`R301`..`R304`) are **repeat
  scans of one fixed grid**, not spatial quadrants: parsing all 4 headers
  for the same 10-min timeslot showed identical `coff`/`loff`/`n_cols`/
  `n_lines` across all 4 scenes, each `total_segments=1`. This gives ~2.5-min
  effective cadence (JMA scans the box 4x within each 10-min block).
  Difference between the two: Japan's box is permanently fixed over
  Japan/nearby seas; Target's box changes per JMA tasking and can be a
  storm, a volcano, or empty.
- No parser bug this time (unlike Meteosat RSS): AHI's `coff`/`loff` are
  self-describing per-file/per-crop (small values matching that crop's own
  local grid, e.g. Target's `coff=1755.5, loff=1220.5` on a 500x500 grid),
  not full-disk-relative like MSG's line/column numbering. `ahi_hsd.py`'s
  existing `load_ahi_raster` worked unmodified. Verified with a coastline
  ghost-overlay proof: a live Target frame (2026-07-03) showed a very cold
  BT core (183-190K, consistent with overshooting convective tops) correctly
  positioned over the Vietnam coast near Hue, matching JMA's published
  target coordinates.
- `satellite_v2/provider_himawari.py`: generalized from FULLDISK-only to a
  `_SECTOR_INFO` dict (`FULLDISK`/`JAPAN`/`TARGET` → S3 root + whether the
  sector is "multi-scene" i.e. each scene within a 10-min slot is its own
  frame rather than being segment-stitched). `_SEGMENT_RE` widened to match
  the `FLDK|JP0[1-4]|R30[1-4]` scene token. Frame keys for multi-scene
  sectors embed the scene suffix (e.g. `20260703T235000Z_R304`) since 4
  distinct frames exist per 10-min slot. The exact per-scene scan time isn't
  in the S3 filename (only the 10-min slot); frame `timestamp_utc` uses a
  150s-per-scene-index approximation for scrubber ordering/display, not
  JMA's true `ObsStartTime`.
- `config/satellite_v2_config.py`: `JAPAN`/`TARGET` added to
  `SATELLITE_V2_SUPPORTED_SECTORS`. `config/satellite_platforms.py`:
  himawari9 `sectors` expanded to `["FULLDISK", "JAPAN", "TARGET"]`.
- Frontend: new sector toggle buttons (`#satellite-sector-japan`,
  `#satellite-sector-target`) and native `<option>`s in `weather.html`;
  `PLATFORM_SECTORS.himawari9` includes `Japan`/`Target`. Japan gets a real
  computed named view preset `himawari-japan` (bounds derived from the
  JP01 header's actual geolocated corners, `[[18,100],[55,157]]`). Target's
  box moves per JMA tasking, so V1 reuses the existing wide `west-pacific`
  full-disk preset as a fallback rather than auto-centering — user pans
  manually to find the current target. Auto-centering on the live target
  box is a possible V2 follow-up. `weather.html` bumped to
  `satellite-page.js?v=20260703b`.
- Verified end-to-end (catalog + live tile render, both sectors) via direct
  API calls against an isolated test server; the app's normal dev workflow
  always proxies API calls to the long-running `main.py` on port 8000
  (see `js/shared.js`'s `resolveApiOrigin`), so a manual restart of that
  process is needed before this is testable in the live dashboard.
- User confirmed both Japan and Target sectors working live 2026-07-04.

#### Himawari-9 "Current Target Area" auto-fit view — added 2026-07-04

Because JMA retasks the Target Area dynamically, the static named view
presets used elsewhere don't work for it (the box moves). Added a
dynamic-fit alternative instead of requiring the user to manually pan from
the wide West Pacific fallback:

- New endpoint `GET /api/satellite-v2/frame-bounds?sat_id=&sector=&channel=`
  (`routes/satellite_v2.py` → `satellite_v2.service.get_frame_bounds`)
  returns the real-world lon/lat bounds of the most recent frame, or
  `{"bounds": null}` if no frame currently exists for that sector (nothing
  tasked). Implementation: lists the latest frame, downloads its single
  small source file, loads it through the existing generic
  `renderer._load_source_raster` dispatch (same one used for tile
  rendering, so no per-format special-casing), then samples a 9x9 interior
  pixel grid through the raster's `src_transform`/`src_crs` with
  `pyproj.Transformer`, keeping only finite lon/lat results before taking
  min/max. Interior sampling (not just the 4 corners) matters because
  full-disk-shaped sectors have off-Earth corners that transform to
  infinity, while cropped regional sectors are fully on-Earth — the same
  function needs to handle both without extra branching.
- Frontend: new View option "Current Target Area"
  (`himawari-target-current`) in `weather.html`. Unlike the static presets
  in `SATELLITE_NAMED_VIEW_PRESETS`, this entry has `bounds: null` and
  `dynamic: true`; `js/satellite-page.js`'s `setActiveViewPreset` checks
  for that flag and calls the new async `fitDynamicViewPreset`, which
  fetches `/api/satellite-v2/frame-bounds` via the shared `window.apiUrl`
  helper and fits the map to the returned box, or shows a status message
  if nothing is currently tasked or the request fails.
  `weather.html` bumped to `satellite-page.js?v=20260703c`.
- Verified end-to-end in-browser: temporarily pointed `window.apiUrl` at
  the isolated test server (since the real port-8000 process wasn't
  restarted yet for this addition either) and confirmed selecting "Current
  Target Area" re-tiled the map to a tight z5 cluster bracketing the
  target's actual longitude/latitude box, instead of the wide West Pacific
  fallback extent.

#### GOES GeoColor recipe and satellite opacity policy — updated 2026-07-16

The former GeoColor path was a gamma-stretched synthetic true-color RGB whose
red reflectance also doubled as the day/night mask. That made dark daytime
water and land blend toward the synthetic night palette, while the missing
Rayleigh correction left the result flatter than the NOAA/CIRA reference.

- `satellite_v2/renderer.py` now reads the GOES observation time from NetCDF
  metadata (ABI filename fallback) and retains the projection origin/height on
  `SourceRaster`. The renderer passes those values plus the existing canvas
  lon/lat grid to `render_composite_rgb`.
- `satellite_v2/composites.py` computes local solar and geostationary viewing
  geometry, applies a bounded wavelength-dependent Rayleigh path-reflectance
  correction to Channels 1/2/3, constructs the established simulated green,
  and applies the CIRA log stretch. Solar geometry owns the day/night mask;
  surface brightness is used only as a legacy fallback for sources without
  frame-time metadata.
- A GeoColor-only `0.85` display white point and `1.08` saturation adjustment
  finish the daytime RGB. Both `GeoColor` and `GeoColorBlkMar` share this path.
  The Black Marble background remains an internal RGB input, not a basemap
  layer.
- Filled RGB/scalar satellite products use alpha 255. ADP/AOD/FRP retain
  specialized sparse-overlay transparency, and invalid/off-disk pixels stay
  alpha 0. The main dashboard and the retained standalone satellite JS path
  use Leaflet opacity 1.0, leaving per-pixel PNG alpha as the sole transparency
  authority.
- Focused validation: 13 satellite tests pass (GeoColor geometry/stretch/tone,
  timestamp parsing, scalar reflectance, and filled-vs-sparse opacity), plus
  Ruff, Python compilation, and `node --check` for both satellite viewer paths.
  Browser visual proof is user-owned; corrected colors and opacity are
  user-confirmed, while the final white-point lift awaits confirmation.

#### GOES aerosol and fire products: ADP, AOD, FRP — added 2026-07-16

Three new single-instant GOES ABI L2 products for GOES-18/19, added to support a
live Canadian-wildfire smoke event. All three reuse the existing GOES
geostationary georeferencing (`goes_imager_projection` + `x`/`y` scan coords,
2 km grid) — identical to CMIP imagery — so no new projection code was needed.
They are GOES-only: NOAA publishes no AHI/SEVIRI/FCI aerosol or fire equivalent
(the `noaa-himawari9` bucket has only AHI-L2 Clouds/ISatSS/Winds), so
`js/satellite-page.js` gates all three behind a `GOES_ONLY_CHANNELS` set
(visible for goes18/goes19, hidden for every other platform).

- **AerosolDetection (ABI-L2-ADP, "Smoke & Dust")** — categorical smoke/dust
  mask. `_load_adp_source_raster` folds the binary Smoke and Dust flags plus
  their DQF confidence into one code band (`category*10 + confidence`; category
  1/2/3 = smoke/dust/both, confidence 0/1/2 = high/medium/low decoded from DQF
  bit-fields — smoke `(DQF>>2)&3`, dust `(DQF>>4)&3`; a DQF field == 3 "bad" is
  treated as no detection). `_colorize_categorical` maps category → hue (smoke
  teal `#39d0d8`, dust amber `#e8a33d`, both purple `#c44dff`) and confidence →
  opacity (`_ADP_CONFIDENCE_ALPHA = (210, 140, 80)`). Categorical products
  render with `Resampling.nearest` so the integer codes never blend into
  fractional values. Interpretive legend in `SATELLITE_V2_INTERPRETIVE_LEGENDS`
  (config) and its JS mirror `_SATELLITE_INTERPRETIVE_LEGENDS` (js/weather.js).
- **AerosolOpticalDepth (ABI-L2-AOD, "AOD")** — continuous 550 nm field, turbo
  colormap, norm 0–1.0. `_load_aod_source_raster` filters to high+medium DQF
  quality (drops `DQF > 1` to NaN — low-quality was the main clear-sky speckle
  source, matching NESDIS AerosolWatch imagery). `_colorize_aod` applies a
  value-driven alpha ramp (transparent at/below 0.10, opaque at/above 0.40 AOD)
  so clear air stays see-through and plumes read opaque as an overlay. Scalar
  legend (kind `aod`) with numeric ticks and axis label. The AOD legend also
  renders a discrete black "No Data" swatch left of the gradient (NESDIS
  convention) via a new optional `leadingSwatch` param on
  `renderContinuousLegend` in js/weather.js plus `.legend-colorbar-*` CSS —
  no-retrieval pixels render transparent on the map, not black.
- **FireRadiativePower (ABI-L2-FDC, "FRP")** — sparse fire field (MW). Not an
  aerosol product, but the same single-instant architecture and directly
  relevant as the smoke's source fires. `_load_frp_source_raster` reads the
  `Power` variable (finite only at fire pixels) and `_dilate_sparse(radius=1)`
  grows each 2 km fire to a ~6 km block so it is visible at CONUS zoom. Flows
  through the default `_colorize_scalar` (valid mask = fire pixels), YlOrRd
  colormap, norm 0–150 MW, scalar legend kind `frp` (MW ticks).

Shared plumbing (all inside the existing single-instant render path — no new
render model was introduced):

- Pseudo source-channels `ADP`/`AOD`/`FRP` (the same trick SEVIRI/FCI bundle
  tokens use) registered in `normalize_source_channel`; each product's `req`
  list points at its pseudo-channel. `_product_kind` returns
  `categorical`/`aod`/`frp` *before* calling `channel_number_from_key`, which
  would otherwise throw on a numberless key.
- `provider_aws._aws_family_prefix` maps the pseudo-channel to its ABI-L2
  family prefix (`ADPC/ADPF/ADPM`, `AODC/AODF`, `FDCC/FDCF`); these products
  skip the `C##` imagery token filter, and `_filename_matches_sector` was
  generalized from `CMIPM1/CMIPM2` to `M1-M`/`M2-M` so it matches both CMIP and
  ADP mesoscale files. AOD has no mesoscale on AWS (AODM 404s); ADP and FDC do.
- `renderer._load_source_raster` dispatches on the pseudo-channel to the new
  loaders; the shared `_geos_scan_source_raster` helper builds the SourceRaster
  (deliberately duplicating ~25 lines of georef rather than refactoring the hot
  CMIP path).
- The aerosol/fire products themselves needed no render-version bump: the tile
  cache path keys on channel, so changed AOD/ADP output was cleared surgically
  by deleting `tiles/products-v3/goes*/{AerosolDetection,AerosolOpticalDepth}`.
  The same-day GeoColor recipe change (above) separately re-namespaced all GOES
  tiles to `products-v5`, so current aerosol/fire tiles live under that
  namespace.
- Skipped as not worth it: the AOD file's Angstrom Exponent (particle size,
  fine smoke vs coarse dust) is over-water only (~24% coverage), useless over
  CONUS land smoke.

Verified (static + backend render, per project convention — browser smoke is
user-owned): all four Python modules `py_compile`; `node --check` on
js/weather.js passes; catalog → download → render for ADP/AOD/FRP on both
GOES-18 and GOES-19 returns non-blank tiles. Live values 2026-07-16 (GOES-19):
ADP 26k smoke / 106k dust pixels, AOD max 5.0 with ~405k px > 0.5, FDC 41 fires
up to 552 MW in the Pacific NW. Frontend cachebusters at add time:
`weather.js?v=20260716c`, `satellite-page.js?v=20260716b`,
`dashboard.css?v=20260716a` (weather.js later advanced to `v=20260716d` by the
GeoColor opacity work).

### Satellite render pipeline latency optimization — registered 2026-07-16

Active track 2 (see Active Tracks). Status: not started. The standalone
execution plan is `docs/satellite-render-optimization-plan.md` (prepared
2026-07-11), with the file-reference companion
`docs/satellite-radar-render-pipeline-files.md`. Both stay standalone while
the work is active (they carry execution-grade protocol: bench CLI, golden
tiles, baseline matrix); archive them per the Archived Source Docs pattern
when the phases complete.

- Goal: minimize end-to-end tile latency at high zoom with **bit-identical**
  pixel output; no render-version bumps; protected knobs untouched.
- Phase 0 golden tiles and the committed baseline must be captured from the
  post-GeoColor/opacity renderer, using `products-v5` for the GOES/default
  namespace. Do not compare optimized output against pre-v5 translucent or
  pre-Rayleigh tiles.
- Phases: 0 benchmark harness + committed baseline; 1 hit-path validation
  cheapening + `_NETCDF_CACHE` LRU bugfix; 2 supertile single-canvas +
  respond-first; 3 multi-channel single-pass parse + AHI threaded segment
  decompress; 4 shared source-raster cache; 5 warm-path process-pool reuse;
  6 (optional, measure-first) GDAL warp threads.
- Pre-identified correctness bug rides along: `_NETCDF_CACHE` is a plain
  dict but eviction calls `popitem(last=False)` — the 17th distinct GOES
  NetCDF in one process raises TypeError. Fix is the first commit of
  Phase 1.
- Open decisions before implementation reaches them: the Phase 4
  byte-budget cache knob (new config knob yes/no) and whether Phase 6
  stays in scope.

### International radar

Deferred to V2. Keep the US dashboard enhancement path focused on NEXRAD,
satellite, Water, WPC, SPC, alerts, and storm reports before adding
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
3. Cross-product severe-weather workspace — promoted 2026-07-16 to the
   "Frontend True Split (Stage 2) and Severe Weather Workspace" section,
   which fully specifies it (product curation, two-tier time-sync, engine
   composition).
4. User preference persistence:
   - Add backend read/patch endpoints that merge a writable user settings file
     over `config/user_settings.default.json` with validation and safe fallback
     behavior.
   - Add frontend page actions such as "Use this as default for this page" and
     "Reset page defaults" after the initial map-default behavior is stable.
   - Save stable product concepts only: map view, Satellite platform/sector/
     product/lookback, Tropical basin, city label source/density, and similar
     UI preferences. Keep provider names, cache namespaces, render versions,
     function names, and implementation internals in code or operator config.

### Radar: All NWS NEXRAD Sites + L2-Only Filtering

**Context:** NOAA NEXRAD documentation confirms Level III products are only generated
for CONUS sites. Non-CONUS/remote sites (Alaska, Hawaii, Puerto Rico, US territories,
overseas military bases) have Level II base data on AWS but no Level III in standard
LDM feeds due to satellite-routing latency isolation from CONUS internet relays.

**Changes (2026-07-04):**

- **Backend (`services/radar_service.py`)**:
  - Added `_is_conus_site(site)` function to identify CONUS (lat 21–52°N, lon −140 to −65°W)
    vs non-CONUS sites using their coordinates.
  - Updated `get_radar_live_sites_data()` to include a `"conus": bool` flag for each
    site in the `/api/radar/live/sites` response.
  - Fixed `_radar_live_site_supported()` to recognize all non-CONUS sites via fallback
    coordinates from the new `radar/nexrad_coordinates.py` module.
  - Created `radar/__init__.py` to make the radar directory a Python package.

- **Frontend (`js/weather.js`)**:
  - Added `_radarSiteConusMap` to track CONUS status for each site.
  - Changed default product from `L3_N0B` to `L2_REF` in two locations:
    `_activeRadarProduct()` fallback and `_loadRadarSites()` initial selection logic.
  - Disabled Level 3 products in dropdown for non-CONUS sites (greyed out with note).
  - Site selection change handler auto-switches to L2 when non-CONUS site selected.

- **Data (`radar/nexrad_coordinates.py`)**:
  - New comprehensive NEXRAD site coordinate mapping for all 164 NWS WSR-88D sites,
    including 121 CONUS, 7 Alaska, 4 Hawaii, Puerto Rico, Guam, and 3 overseas military.
  - Serves as fallback when Py-ART's NEXRAD_LOCATIONS lacks a site's coordinates.

**Result:**
- Radar site selector now shows all 164 NWS sites (vs. previous 7 CONUS-only).
- Non-CONUS sites (PGUA/Guam, RKSG/South Korea, RODN/Japan, etc.) render **Level 2 data**
  on-demand from AWS; Level 3 options are disabled to reflect unavailability.
- Default product `L2_REF` works universally across all sites.
- No 404 errors or confusion about missing Level 3 data for remote sites.

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
