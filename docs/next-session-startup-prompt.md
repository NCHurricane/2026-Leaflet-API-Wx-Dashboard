# Next Session Startup Prompt

Date prepared: 2026-06-17 (updated 2026-06-18 — Phase 16 extraction complete)

Start in:

```text
F:\Python\dashboard_2026_frontend_pages
```

Use this prompt:

```text
We are continuing the frontend product-page split in F:\Python\dashboard_2026_frontend_pages on branch codex/frontend-product-pages.

Current status:
- The fixed dashboard shell is accepted.
- Tropical reference UI is accepted.
- Route-level standalone candidates are working and accepted for this pass:
  /tropical, /alerts, /spc, /surface, /drought, /satellite, /radar, /mrms, /rtma.
- /surface maps to the existing current product mode.
- All split pages still share weather.html and js/weather.js through product-only route mode.
- Phase 15 product module migration is complete for all 5 products:
  - js/drought-page.js + js/drought-engine.js
  - js/mrms-page.js + js/mrms-engine.js
  - js/rtma-page.js + js/rtma-engine.js
  - js/surface-page.js + js/surface-engine.js
  - js/spc-page.js + js/spc-engine.js
- Phase 15 clean-cut is complete for all 5 products:
  - Drought: loadDroughtLayer delegates to engine; drought-page.js wireControls owns .drought-cat-check handlers; applyDroughtFilter is an in-memory filter in drought-engine.js
  - Surface: loadSurface delegates to engine; surface-page.js wireControls owns .weather-surface-product and .weather-surface-gradient handlers; applyGradientChange is in surface-engine.js
  - MRMS: loadMrms and loadMrmsScrubberFrames delegate to engine; mrms-page.js wireControls owns .mrms-product-check, .mrms-sub-radio, and slider handlers; composeMrmsProductKey fully moved to mrms-page.js
  - RTMA: loadRtma and loadRtmaScrubberFrames delegate to engine; rtma-page.js wireControls owns .weather-rtma-stream, .weather-rtma-product, and slider handlers with full mutual exclusion, wind pair, and temperature_change_24h coercion logic
  - SPC: refreshSpc delegates to engine via _doRefreshSpcInternal; spc-page.js wireControls owns all SPC handlers (convective toggles, watch pairs, reports, MDS, fire toggles, subtab keyboard nav); _wireSpcUiParityHandlers removed
- All 10 engine/page scripts added to weather.html (drought, surface, mrms, rtma, spc - both engine and page for each).
  Previously these scripts were missing, causing engine instances to be null and load functions to silently no-op.
- Option A clean-cut is complete for Alerts, Satellite, and Radar:
  - All inline fallback bodies removed from js/weather.js; every wrapper now delegates directly to its engine/page controller (e.g. loadAlerts -> _alertsEngine.loadLiveAlerts, _wireRadarControls -> _radarPageController.wireControls, _wireSatelliteControls -> _satellitePageController.wireControls).
  - 5 top-level load fallbacks + 11 helper-level fallbacks removed (alert style/layer/in-memory filter/display refresh/active-warnings render+wire/sidebar filter wiring/archive alerts load+slice/radar control wiring/satellite subtab binding).
  - Orphaned helper _canApplyAlertsResponse removed (only the deleted alerts fallbacks used it; the alerts engine has its own canApplyLiveResponse).
  - Shared alerts helpers that engines consume via context (e.g. _buildAlertsUrl, _filterAlertsByCategories, _stripInactiveAlerts, _alertsZoomBucket) were verified still-live and intentionally left in weather.js.
  - node --check js/weather.js clean; zero remaining InlineFallback references.
- Tropical Phase 1 implemented:
  - js/tropical-engine.js owns active-storm list loading and response sequencing.
  - js/tropical-page.js owns active-system select options and storm-card rendering.
  - Card selection still uses the existing detail/map workflow injected from js/weather.js.
- Tropical Phase 2 implemented:
  - js/tropical-engine.js owns live storm-detail/advisory fetching and response sequencing.
  - js/weather.js injects live/archive state reset, summary/floater/layer rendering, status-label, and reliability callbacks.
- Tropical Phase 3 implemented:
  - js/tropical-engine.js owns archive catalog fetching and catalog caching orchestration.
  - js/tropical-page.js owns archive basin/season options, archive-card rendering, selected-card styling, and basin/season change handlers.
- Tropical Phase 4 implemented:
  - js/tropical-engine.js owns per-storm archive base-data and advisory fetching.
  - The engine preserves the shared Tropical request sequence, merges advisory GIS with the storm best track, and dispatches advisory versus best-track mode.
- Tropical Phase 5 implemented:
  - js/tropical-page.js owns archive advisory/fix collections, mode/index state, playback/speed state, scrubber rendering, navigation, mode switching, and all scrubber handlers.
  - js/weather.js still supplies advisory/fix rendering callbacks.
- Tropical Phase 6 implemented:
  - js/tropical-page.js owns whole-storm HURDAT2, per-advisory, and per-fix inspector header/metric rendering.
  - The advisory/fix selectors embedded in the summary grid are also page-owned.
- Tropical Phase 7 implemented:
  - js/tropical-page.js owns forecast track-row/table rendering, official product buttons, and verified graphics-list rendering.
  - Product and graphic detail opening remains callback-driven from js/weather.js.
- Tropical Phase 8 implemented:
  - js/tropical-page.js owns product/graphic detail panel state, creation, replacement, dragging, close/Escape cleanup, content escaping, and missing-product status behavior.
  - Existing weather.js detail entry points are thin delegates so map-layer and floater callers remain stable.
- Tropical Phase 9 implemented:
  - js/tropical-page.js owns floater storm state, NESDIS URL generation, five-minute cache busting, availability probing, stale-probe guards, product labels, modal selection, and pill handlers.
  - Existing weather.js hide/render floater entry points are thin delegates.
  - Archive map/layer rendering and GIS overlays remain in js/weather.js.
- Phase 16 archive extraction is code-complete:
  - Surface: surface-engine.js owns archive requests; surface-page.js owns archived station rendering and legends.
  - MRMS: mrms-engine.js owns archive requests and generic polling handoff; mrms-page.js owns archive image-overlay rendering.
  - SPC: spc-engine.js owns archive requests; spc-page.js owns archived outlook GeoJSON rendering.
  - Radar: radar-engine.js already owned frame-list loading; radar-page.js now owns scrubber frame rendering and crossfade display.
  - weather.js retains generic archive mode, progress, polling, and shared scrubber controls.
  - node --check and targeted stale-reference checks passed for all changed JavaScript files.
  - Manual browser smoke testing passed for Current/Surface, Alerts, Drought, Radar, Satellite, RTMA, MRMS, SPC, Tropical, and /weather.html.
- Phase 17 cleanup is complete:
  - Removed obsolete archive load wrappers from weather.js; generic dispatch now calls product engines directly.
  - Removed unused archive session state and no-op MRMS/Surface context callbacks.
  - Removed the unused weather.js Alerts frame-slicing delegate and its engine export; slicing remains internal to alerts-engine.js.
  - Moved MRMS subtab selection, keyboard navigation, and sub-panel visibility from weather.js into mrms-page.js.
  - Removed the unused leaflet.layergroup.collision CDN script from weather.html; the plugin had no project references and its failed load was the only reported browser console error.
  - Moved Radar and Satellite control wiring into their configured page-controller initialization blocks and removed the obsolete weather.js wiring wrappers.
  - Removed the behavior-free Drought, Surface, and MRMS load wrappers from weather.js; shared orchestration and page contexts now call their engines directly.
  - Removed behavior-free Alerts, Radar, and Satellite load wrappers; callers and page contexts now invoke their engines directly.
  - Kept refreshSpc as the recursion-safe boundary between spc-engine.js and _doRefreshSpcInternal.
  - Removed behavior-free Tropical storm-list, storm-detail, archive-catalog, archive-storm-detail, and archive-advisory load wrappers; callers now invoke tropical-engine.js directly.
  - Kept Tropical presentation delegates that remain shared callback boundaries for map, inspector, floater, and archive rendering.
  - Removed confirmed zero-reference state/helpers: obsolete RTMA grid state, unused SPC request counters and superseded style/CIG helpers, unused Satellite latest-frame/age helpers, and the write-only Radar tab-visited flag.
  - Final orphan audit removed the remaining declaration-only legacy helpers across Alerts, Drought, Radar, SPC, Satellite, Surface/RTMA, plus empty Radar multi-site overlay storage.
  - Repeated symbol-count audit now reports zero declaration-only state and zero declaration-only functions in weather.js.
  - Targeted node syntax and stale-reference checks pass.
  - Final all-page browser smoke testing passed after the ninth cleanup increment.
- Post-Phase 17 RTMA update:
  - Replaced separate Wind Chill and Heat Index selectors with one `apparent_temperature` product labeled Feels Like.
  - The derived grid uses temperature, dew point, and wind speed from the same RTMA frame.
  - Cells show wind chill at <= 50 F with wind >= 3 mph, heat index at >= 80 F, and actual temperature otherwise.
  - Fixed the RTMA PNG renderer so derived products use `_load_rtma_product_grid()` instead of requiring a native `config["var"]`.
- /weather.html still works for the combined workspace.

Important SPC note:
- /spc must show Day 1 Categorical on hard refresh without requiring a checkbox toggle.
- The fix was to normalize SPC controls and run _updateSpcReportFilterState() before the first refreshActiveLayers() call.
- Keep this startup ordering intact.

Key architecture note:
- Each product engine is created in _registerProductAppContexts() via _productAppContexts.registerProductContext().
- Each product page is configured via configureXxxPage({...}) with a context object that exposes weather.js state, then wireControls() binds all UI event handlers.
- _registerProductAppContexts() runs before init(), which calls refreshActiveLayers() — engines are ready before the first data load.
- If window.NCH*Engine or window.NCH*Page is null (script not loaded), the engine is never created and load functions silently return undefined. Always confirm all 10 scripts are in weather.html when adding new product modules.

Relevant files changed in this phase:
- routes/pages.py
- app_core/static_assets.py
- weather.html
- js/product-page-shell.js
- js/product-app-context.js
- js/alerts-engine.js
- js/alerts-page.js
- js/satellite-engine.js
- js/satellite-page.js
- js/radar-engine.js
- js/radar-page.js
- js/drought-engine.js
- js/drought-page.js
- js/mrms-engine.js
- js/mrms-page.js
- js/rtma-engine.js
- js/rtma-page.js
- js/surface-engine.js
- js/surface-page.js
- js/spc-engine.js
- js/spc-page.js
- js/weather.js
- docs/product-page-shell-plan.md
- docs/refactor-playbook.md
- docs/next-session-startup-prompt.md

Verification already run:
- node --check js/weather.js (clean after every clean-cut)
- node --check on all 10 new product module files (clean)
- python py_compile checks for routes/pages.py (clean)
- route smoke checks returned 200 for all standalone routes
- browser testing confirmed /drought, /surface, /mrms loading data after missing scripts were added to weather.html

Known workspace note:
- start_server.txt may appear as untracked. Leave it alone unless explicitly asked.

Smoke test results (2026-06-17):
- /mrms: confirmed working after fixing product key bugs (VIL/Reflectivity/Lightning/Model all used bare family names instead of composed backend keys) and scrubber auto-load (refreshActiveLayers now calls loadMrmsScrubberFrames instead of loadMrms).
- /drought, /surface, /rtma, /spc: all confirmed working. No issues found.

Smoke test results (2026-06-18 — Post Option A + Tropical Phases 1-9):
- /alerts, /satellite, /radar: all confirmed working after Option A clean-cut (inline fallback removal). No parity issues.
- /tropical (live): storm cards, detail panels, floaters (all three products), modal behavior, scrubber modes all confirmed working.
- /weather.html (combined): storm cards, archive tabs, floaters, GIS overlays all confirmed working. No cross-product regressions.

Smoke test results (2026-06-18 — Phase 16 completion):
- Current/Surface, Alerts, Drought, Radar, Satellite, RTMA, MRMS, SPC, Tropical, and /weather.html all passed manual browser smoke testing.

Next agenda:
1. Option A (DONE 2026-06-17): inline fallback bodies removed from weather.js for Alerts, Satellite, and Radar — all wrappers delegate to engine/page controllers; orphaned _canApplyAlertsResponse removed; node --check clean. Smoke tests (2026-06-18) confirmed parity.
2. Tropical Phases 1-9 (DONE): all code-complete and smoke-tested (2026-06-18). Floater, modal, scrubber, detail panels all working on /tropical and /weather.html. GIS overlays (watches, best-track, wind radii, surge zones, peak surge) already owned by tropical-engine.js; weather.js only unpacks response data and injects legend callbacks. Complete and ready.
3. Phase 16 archive extraction (DONE 2026-06-18): Surface, MRMS, SPC, and Radar product-specific archive/scrubber load and render paths moved into their engine/page modules. Generic archive orchestration remains in weather.js. Syntax, reference, and manual browser smoke checks passed.
4. Phase 17 — Cleanup and Optimization (DONE 2026-06-18):
   - First cleanup increment removed obsolete archive load wrappers, unused archive session state/context callbacks, and the unused Alerts frame-slicing delegate/export.
   - Second cleanup increment moved the remaining MRMS-owned subtab and sub-panel UI behavior into mrms-page.js.
   - Third cleanup increment removed the unused failing leaflet.layergroup.collision CDN dependency.
   - Fourth cleanup increment normalized Radar/Satellite page initialization so configure runs before wireControls, matching the other product pages.
   - Fifth cleanup increment removed the behavior-free Drought, Surface, and MRMS load wrappers from weather.js.
   - Sixth cleanup increment removed behavior-free Alerts, Radar, and Satellite load wrappers while preserving SPC's recursion-safe refresh boundary.
   - Seventh cleanup increment removed behavior-free Tropical load wrappers while retaining shared presentation callback boundaries.
   - Eighth cleanup increment removed confirmed zero-reference product state and helpers across RTMA, SPC, Satellite, and Radar.
   - Ninth/final cleanup increment removed the remaining declaration-only legacy helpers and empty Radar multi-site overlay storage.
   - Final symbol-count audit reports no declaration-only state or functions in weather.js.
   - Final all-page browser smoke pass completed successfully.
   - Keep generic archive mode, polling, progress, and shared scrubber infrastructure in weather.js.
   - Re-run node syntax checks and stale-reference searches after cleanup.
5. **Known blocker: Unified Navigation** — Product pages are split but have no cross-product navigation. Users cannot switch between /tropical, /alerts, /surface, etc. Add a consistent nav (top bar or product selector). Deferred pending design decision.

6. **Planned: CSS Extraction** (post-Phase 17) — Extract `<style>` block from weather.html into separate stylesheets:
   - `css/global.css` — dashboard shell, map, common UI (buttons, panels, tabs)
   - `css/tropical.css`, `css/alerts.css`, `css/surface.css`, etc. — product-specific rules
   - Link sheets in weather.html and product pages as needed. Deferred until product code stabilizes.
7. Keep /weather.html working for future product combination plans until explicitly approved for retirement.

Before making code changes, restate the proposed step and ask for confirmation if the request could change scope.
```
