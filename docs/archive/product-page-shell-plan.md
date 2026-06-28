# Product Page Shell Plan

Created: 2026-06-13

This plan updates Phase 13 after the backend route/service refactor. The next
frontend step is to replace the current floating/collapsible sidebar layout with
a true map-first dashboard grid, then use the Tropical tab redesign work as the
first product reference inside that shell.

## Active Worktrees And Branches

- Main repository: `F:\Python\dashboard_2026`.
- Backend refactor worktree: `F:\Python\dashboard_2026_refactor` on
  `codex/backend-product-refactor`.
- Frontend product-page worktree: `F:\Python\dashboard_2026_frontend_pages` on
  `codex/frontend-product-pages`.
- Dashboard shell, `weather.html`, and `js/weather.js` UI work belongs in the
  frontend product-page worktree unless the task explicitly says otherwise.
- Backend route/service work belongs in the backend refactor worktree unless the
  task explicitly says otherwise.

## Current Decision

Use a fixed, map-first dashboard shell. Tropical is the first product reference
inside that shell.

Current handoff:

- MRMS and SPC left-dock subtabs are implemented and visually accepted.
- Satellite subtabs are implemented for GOES-18/GOES-19 and Full Disk, CONUS,
  Meso 1, and Meso 2; the Channel Product dropdown remains unchanged. The
  left-sidebar Current/Animate buttons were removed because the scrubber is now
  dashboard-owned and auto-loads with Satellite.
- RTMA remains in the compact grouped left-dock layout; subtabs added too much
  navigation for the amount of control density.
- Dense-product subtabs are complete for this pass: MRMS, SPC, and Satellite.
  Keep other products compact unless their control families materially grow.
- Tropical reference pass is accepted in the fixed dashboard shell:
  basin selection, active-system cards, outlook cards, and the right-side System
  Inspector define the product-specific pattern for the standalone `/tropical`
  page.
- Phase 14 `/tropical` route-level candidate is accepted for this pass. It uses
  canonical `/tropical` routing with the accepted dashboard shell in
  Tropical-only mode and avoids copying the full `weather.js` state model.
- Phase 14 route-level split candidates are working and accepted for this pass:
  `/tropical`, `/alerts`, `/spc`, `/surface`, `/drought`, `/satellite`,
  `/radar`, `/mrms`, and `/rtma` all serve the accepted dashboard shell in
  product-only mode. `/surface` maps to the existing `current` product mode.
- SPC standalone startup required one additional ordering fix: normalize SPC
  controls and report-filter state before the initial `refreshActiveLayers()`
  call, otherwise the first Day 1 Categorical response can be discarded as a
  stale selection and only appear after toggling Categorical.

The existing Tropical tab already has the strongest product-specific shell:

- left Tropical Hub with basin selection plus Active, Outlooks, and Archive
  tabs; Outlooks is the default tab on page load
- center Leaflet map as the primary workspace
- right Tropical Inspector with summary, forecast, layers, products, graphics,
  and floater sections
- alert-style slide-in/modal behavior for official product text
- Tropical-specific layer toggles and legend behavior
- cache-first data flow through the Tropical API and worker cache

The implementation should first make `weather.html` a real dashboard layout:
fixed left controls, bounded center map, fixed right inspector, and docked
timeline/colorbar rows. After that shell is accepted, refine Tropical inside the
combined workspace and use it as the guide for standalone product pages.

## Relationship To Phases 13-15

Phase 13 is course-corrected.

- Build the fixed dashboard grid shell before more product-specific UI polish.
- Treat the current collapsible sidebars as legacy panel chrome.
- Keep existing element ids and product behavior stable during the first grid
  pass.
- Define which shell pieces are reusable and which are product-specific.
- Do not start broad product-page creation until this shell contract is clear.

Phase 14 changes order.

- The old recommended order placed Tropical last.
- The new order starts with the dashboard grid shell, then Tropical as the
  reference UI pass.
- Standalone product pages should then be created one product at a time using
  the accepted shell pattern.

Phase 15 remains valid.

- Clean-cut removal from `weather.html` and `js/weather.js` still happens only
  after a standalone product page is verified.
- Avoid keeping duplicated product code indefinitely.
- Phase 15A prep has begun by extracting standalone route/bootstrap ownership
  into `js/product-page-shell.js` and registering `/alerts` metadata through
  `js/alerts-page.js`. This is not yet a removal pass; `/alerts` still runs on
  the accepted `weather.html` and `js/weather.js` shell for verification.
- Phase 15B prep routes `/alerts` through a generated product shell response
  that injects product metadata into the shared shell. This avoids duplicating
  `weather.html` while allowing Alerts-specific page-controller code to move
  into `js/alerts-page.js`. The Alerts map/rendering engine remains in
  `js/weather.js` until a shared app context exists.
- Phase 15C prep added `js/product-app-context.js` and registers an Alerts app
  context from `js/weather.js`. This defines the dependency boundary for the
  later Alerts engine extraction without moving `loadAlerts()` yet.
- `js/alerts-engine.js` now owns the first context-backed Alerts engine facade:
  live-response eligibility. Keep moving similarly small engine slices before
  attempting to move `loadAlerts()`.
- `js/alerts-engine.js` now also owns the live Alerts loading orchestration,
  in-memory category refiltering, display-geometry refresh, Leaflet alert
  style/layer construction, and archive Alerts loading/frame slicing.
  `js/alerts-page.js` owns Alerts category controls and active-warning panel
  rendering/wiring. Popup/detail presentation and new-alert notification
  banners remain injected from `js/weather.js` because they still share broader
  dashboard/map interaction state.
- Phase 16 archive extraction is code-complete: Surface, MRMS, SPC, and Radar
  archive/frame loading and rendering now follow the same engine/page ownership
  boundary. `js/weather.js` retains generic archive mode, progress, polling,
  and shared scrubber controls. Manual browser smoke verification passed for
  all standalone products and `/weather.html`.
- Phase 17 cleanup is complete. The first increment removed obsolete
  archive load wrappers, unused archive session state/context callbacks, and
  the unused Alerts frame-slicing delegate/export.
- The second Phase 17 increment moved MRMS subtab selection, keyboard
  navigation, and product sub-panel visibility into `js/mrms-page.js`.
- The third Phase 17 increment removed the unused
  `leaflet.layergroup.collision` CDN dependency from `weather.html`.
- The fourth Phase 17 increment normalized Radar and Satellite page startup so
  each controller is configured before `wireControls()` runs.
- The fifth Phase 17 increment removed behavior-free Drought, Surface, and MRMS
  load wrappers from `js/weather.js`; callers now use their engines directly.
- The sixth Phase 17 increment removed behavior-free Alerts, Radar, and
  Satellite load wrappers. SPC retains its refresh boundary to prevent
  engine/context recursion.
- The seventh Phase 17 increment removed behavior-free Tropical load wrappers.
  Tropical presentation delegates remain where shared map and inspector code
  uses them as callback boundaries.
- The eighth Phase 17 increment removed confirmed zero-reference product state
  and helpers across RTMA, SPC, Satellite, and Radar.
- The ninth/final Phase 17 cleanup increment removed the remaining
  declaration-only legacy helpers and empty Radar multi-site overlay storage.
  Repeated symbol-count audits report no declaration-only state or functions
  in `js/weather.js`. Final all-page browser smoke verification passed, so
  Phase 17 is complete.
- Post-Phase 17, RTMA now exposes one Feels Like derived product instead of
  separate Wind Chill and Heat Index controls. It derives the displayed value
  from temperature, dew point, and wind speed in the same RTMA frame.
- `/satellite` now follows the same generated product-shell route pattern as
  `/alerts`. `js/satellite-page.js` owns Satellite platform/sector subtabs,
  active selection reads, lookback controls, and frame-window calculations.
  `js/satellite-engine.js` owns context-backed current-frame and animation-loop
  loading orchestration. Tile-layer pooling, crossfade, prefetch, and scrubber
  playback remain injected from `js/weather.js` because they are still shared
  with the dashboard map/scrubber lifecycle.
- `/radar` now follows the generated product-shell route pattern too.
  `js/radar-page.js` owns Radar site/product selection reads, status updates,
  lookback display, and control wiring. `js/radar-engine.js` owns
  context-backed latest-image and scrubber-frame loading orchestration. Leaflet
  overlay rendering, crossfade, site-marker layers, and radar speed-calibrator
  interactions remain injected from `js/weather.js`.
- Phase 15 clean-cut is complete for Drought, Surface, MRMS, RTMA, and SPC.
  All inline fallback implementations, combined-workspace event handlers, and
  inline product key composers have been removed from `js/weather.js`. Each
  product's load functions now delegate entirely to their engine instance; each
  product's `wireControls()` in the page module owns all UI event binding. The
  configure context for each product exposes the specific weather.js state and
  helpers the page/engine needs rather than sharing a global object.
  `_doRefreshSpcInternal()` was extracted from `refreshSpc()` to break the
  SPC engine → context → refreshSpc → engine recursion loop.
  `_wireSpcUiParityHandlers()` was removed after spc-page.js wireControls took
  full ownership of day/fire-day selects and all SPC toggle handlers.
- All 10 product engine/page scripts (drought, surface, mrms, rtma, spc — both
  engine and page for each) are now included in `weather.html`. Omitting these
  script tags caused engine instances to be null and all delegated load calls to
  silently return undefined with no console errors.
- Tropical Phase 1 migration is implemented: `js/tropical-engine.js` owns the
  active-storm list request and response sequencing, while
  `js/tropical-page.js` owns active-system option/card rendering. Card selection
  still calls the existing detail/map workflow in `js/weather.js`.
- Tropical Phase 2 migration is implemented: live storm-detail/advisory fetching
  and response sequencing now run through `js/tropical-engine.js`.
  `js/weather.js` supplies focused callbacks for live/archive state reset,
  summary/floater/layer rendering, status labels, and reliability metadata.
- Tropical Phase 3 migration is implemented: archive catalog fetching now runs
  through `js/tropical-engine.js`; basin/season options, archive cards, selected
  card styling, and archive browse-control handlers are owned by
  `js/tropical-page.js`.
- Tropical Phase 4 migration is implemented: per-storm archive base-data and
  advisory requests, response sequencing, and advisory/best-track mode
  dispatch now run through `js/tropical-engine.js`.
- Tropical Phase 5 migration is implemented: archive advisory/fix collections,
  mode/index/playback state, scrubber rendering, navigation, mode switching,
  speed controls, and all scrubber event handlers are owned by
  `js/tropical-page.js`.
- Tropical Phase 6 migration is implemented: whole-storm HURDAT2, per-advisory,
  and per-fix inspector header/metric rendering is owned by
  `js/tropical-page.js`, including the in-summary advisory/fix selectors.
- Tropical Phase 7 migration is implemented: forecast track-row/table
  rendering, official product buttons, and verified storm-graphics lists are
  owned by `js/tropical-page.js`. Product and graphic detail opening remains an
  injected callback.
- Tropical Phase 8 migration is implemented: product/graphic detail panel
  creation, active panel state, replacement, dragging, close-button and Escape
  cleanup, content escaping, and missing-product status behavior are owned by
  `js/tropical-page.js`.
- Tropical Phase 9 migration is implemented: floater storm state, NESDIS URL
  generation, five-minute cache busting, availability probing, stale-probe
  guards, product labels, modal selection, and pill handlers are owned by
  `js/tropical-page.js`.
- Archive map/layer rendering callbacks and GIS overlays remain in
  `js/weather.js`.

## Backend Alignment

The old Tropical plan predates the backend refactor and references `main.py` for
Tropical API work. That is now obsolete.

Current backend ownership:

- `routes/tropical.py`: FastAPI route declarations.
- `services/tropical_service.py`: route-facing cache reads, archive reads,
  worker fallback calls, advisory parsing, and response shaping.
- `workers/tropical_worker.py`: NHC discovery, RSS/CurrentStorms ingestion,
  GTWO KMZ parsing, GIS ZIP/KML parsing, and cache generation.
- `workers/tropical_archive_worker.py`: Tropical archive cache generation and
  advisory payload support.

Future Tropical API or cache behavior should follow those boundaries instead of
adding route logic back to `main.py`.

## Reference Layout

Use this desktop-first dashboard shell as the reference:

1. Top navigation/status
   - product navigation
   - global online/status/error indicators
   - product refresh state
   - do not make product-specific selectors, such as `#weather-region`, truly
     global unless every product uses them
2. Left controls dock
   - product-specific discovery and selection
   - cards for active items, outlook/development areas, reports, or other
     product entities
   - compact controls that support browsing without hiding the map
   - compact cards by default; keep long discussion/body text in the inspector
     or modal instead of embedding snippets in left-hub cards
3. Center map
   - primary presentation surface
   - bounded grid cell, not full-viewport background with panels floating over
     it
   - product-owned map layers and selected-feature highlighting
   - no decorative cards around the map
4. Right inspector
   - selected item summary
   - product layers and legend
   - official products or source details
   - optional graphics/detail sections
5. Bottom timeline/scrubber
   - present only when the product has time navigation
   - controls animation, archive, or frame selection
   - dock under the map cell instead of overlaying the map
6. Shared status/error surface
   - product-specific loading, stale data, empty state, and error messages
   - should not leak between products or tabs

## Dashboard Grid Target

Replace the current absolute-positioning model with a grid shell:

- command/header row
- product tab row
- main dashboard grid

The main grid should use:

- left controls dock: approximately `320px`
- center map/workspace: flexible `minmax(0, 1fr)`
- right inspector dock: approximately `340px`
- optional timeline row under the center map
- optional colorbar/legend row under the timeline

Every grid ancestor of the Leaflet map must allow shrinking with `min-height: 0`
and `min-width: 0`, otherwise the map cell can overflow or collapse.

Default desktop behavior:

- panels are fixed dashboard docks, not collapsible overlays
- left and right docks scroll internally
- the page itself should not become a long-scrolling document
- map controls, attribution, alert overlays, toasts, and Tropical outlook detail
  panels remain scoped to the map cell

Responsive behavior:

- below roughly `1100px`, stack controls, map, timeline/colorbar, and inspector
  vertically
- keep an explicit map height in stacked mode so Leaflet remains visible

Implementation order:

1. Land the grid shell while preserving existing ids and behavior.
2. Call `map.invalidateSize()` after the grid lands and after product/tab
   switches that affect panel visibility.
3. Verify all current product tabs before deleting legacy collapse behavior.
4. Remove the side collapse toggles and handlers only after the grid shell is
   accepted.
5. Add left-dock subtabs only for dense products after the base grid is stable.
   MRMS and SPC are visually accepted, Satellite uses platform/sector subtabs,
   and RTMA should stay compact unless its control set grows. Dense-product
   subtab work is complete for this pass.

## Reusable Shell Pieces

These should become shared utilities before multiple standalone pages are built:

- API URL/client helpers
- page init and teardown hooks
- Leaflet map factory and base-layer setup
- layer lifecycle cleanup helpers
- timer and AbortController registry
- status/error rendering helpers
- timestamp/freshness formatting helpers
- legend helpers
- selected-feature inspector helpers
- timeline/scrubber controller

Do not copy the full `weather.js` state model into product-specific files.
Extract shared utilities only when they are needed by at least two products or
when they reduce meaningful duplication during the first standalone page split.

## Product-Specific Ownership

Each product page should own:

- product controls and labels
- product layer configuration
- product API calls and response interpretation
- selected-item inspector content
- product-specific legend entries
- product-specific archive/timeline behavior

The shared shell should provide structure and lifecycle tools, not hide product
domain behavior behind a generic abstraction.

## Updated Product Order

Recommended order after Tropical reference acceptance:

1. Fixed dashboard grid shell in the combined workspace.
2. Tropical reference pass inside the grid shell. Accepted.
3. Tropical standalone route-level candidate. Accepted for this pass.
4. Alerts route-level candidate. Accepted for this pass.
5. SPC route-level candidate. Accepted for this pass after the standalone
   startup/default Day 1 Categorical fix.
6. Surface route-level candidate. Accepted for this pass as `/surface` mapped
   to existing `current` product mode.
7. Drought route-level candidate. Accepted for this pass.
8. Satellite route-level candidate. Accepted for this pass.
9. Radar route-level candidate. Accepted for this pass.
10. MRMS route-level candidate. Accepted for this pass.
11. RTMA route-level candidate. Accepted for this pass.

This order can change if browser testing shows another product is lower-risk,
but Tropical should remain the reference design source.

## Tropical Plan Adjustments

The recovered Tropical plan remains useful, with these changes:

- Replace `main.py` API anchors with `routes/tropical.py` and
  `services/tropical_service.py`.
- Treat old line-number anchors as stale; search by symbol name instead.
- Keep the removed Focus/Broadcast work out unless explicitly requested.
- Keep the parked mini-map/radar-loop work out unless explicitly requested.
- Preserve the cache-first strategy; the browser should not poll NHC directly.
- Keep official NHC text products in the existing slide-in/modal pattern.
- Keep Tropical Outlook cards compact: show basin/name and probability chips,
  but do not include discussion snippets in the left hub because they consume
  too much space when active storms are present.
- Keep Tropical compact rather than adding another subtab layer: storm cards and
  outlook cards are the browsing UI, archive browsing lives in the left Tropical
  tab set, and the hidden native System select remains only as synced selection
  state for existing JavaScript.
- Keep the right Archive tab removed. Styling and System remain right-side tabs,
  and System stays hidden until an active or archived storm is selected.
- Treat Tropical archive behavior as a reference for future archive workflows,
  but do not redesign all archive workflows during this phase.

## Verification

For Tropical UI work:

```powershell
node --check js\weather.js
.\.venv\Scripts\python.exe -m py_compile main.py routes\tropical.py services\tropical_service.py workers\tropical_worker.py
```

For browser smoke:

- hard-refresh `weather.html`
- verify the map sits in a bounded center cell with no left/right panel overlap
- verify left and right docks scroll internally
- open the Tropical tab
- verify Region is hidden only for Tropical
- verify basin/outlook cards render
- verify active storm cards render when cache/test data exists
- select a storm and confirm the right Inspector opens
- toggle Tropical layers and confirm map cleanup on tab switch
- open official product text and confirm the slide-in/modal closes cleanly
- switch through all product tabs and confirm controls, timeline/colorbar, and
  right inspector panes still swap correctly
- resize below the responsive breakpoint and confirm panels stack without
  clipping the map

For future standalone product pages:

- canonical route returns 200
- `/tropical`, `/alerts`, `/spc`, `/surface`, `/drought`, `/satellite`,
  `/radar`, `/mrms`, and `/rtma` currently serve the accepted shell with
  route-level standalone mode hooks; do not remove their combined-workspace
  code until a clean-cut phase is explicitly started and confirmed
- `/spc` must show Day 1 Categorical on hard refresh without requiring a
  checkbox toggle
- product API calls succeed
- map renders nonblank
- product layers can be cleared without affecting other products
- `weather.html` still works until the clean-cut step for that product
