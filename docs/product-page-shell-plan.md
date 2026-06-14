# Product Page Shell Plan

Created: 2026-06-13

This plan updates Phase 13 after the backend route/service refactor. The next
frontend step is to replace the current floating/collapsible sidebar layout with
a true map-first dashboard grid, then use the Tropical tab redesign work as the
first product reference inside that shell.

## Current Decision

Use a fixed, map-first dashboard shell. Tropical is the first product reference
inside that shell.

The existing Tropical tab already has the strongest product-specific shell:

- left Tropical Hub with system and outlook cards
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
5. Add left-dock subtabs for dense products such as MRMS, SPC, and RTMA after
   the base grid is stable.

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
2. Tropical reference pass inside the grid shell.
3. Tropical standalone page candidate, if the shell is accepted and stable.
4. Alerts.
5. SPC.
6. Surface.
7. Drought.
8. Satellite.
9. Radar.
10. MRMS.
11. RTMA.

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
- product API calls succeed
- map renders nonblank
- product layers can be cleared without affecting other products
- `weather.html` still works until the clean-cut step for that product
