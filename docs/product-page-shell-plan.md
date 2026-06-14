# Product Page Shell Plan

Created: 2026-06-13

This plan updates Phase 13 after the backend route/service refactor. The next
frontend step is to use the existing Tropical tab redesign work as the reference
layout before splitting products into standalone pages.

## Current Decision

Tropical is the first UI reference pass.

The existing Tropical tab already has the strongest product-specific shell:

- left Tropical Hub with system and outlook cards
- center Leaflet map as the primary workspace
- right Tropical Inspector with summary, forecast, layers, products, graphics,
  and floater sections
- alert-style slide-in/modal behavior for official product text
- Tropical-specific layer toggles and legend behavior
- cache-first data flow through the Tropical API and worker cache

The implementation should refine and verify Tropical inside the current
combined `weather.html` workspace first. After the Tropical layout is accepted,
use it as the guide for standalone product pages.

## Relationship To Phases 13-15

Phase 13 is enhanced, not replaced.

- Capture the Tropical layout as the reference product shell.
- Define which shell pieces are reusable and which are product-specific.
- Do not start broad product-page creation until this shell contract is clear.

Phase 14 changes order.

- The old recommended order placed Tropical last.
- The new order starts with Tropical as the reference UI pass.
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

Use this desktop-first shell as the reference:

1. Top navigation/status
   - product navigation
   - global online/status/error indicators
   - product refresh state
2. Left product hub
   - product-specific discovery and selection
   - cards for active items, outlook/development areas, reports, or other
     product entities
   - compact controls that support browsing without hiding the map
3. Center map
   - primary presentation surface
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
6. Shared status/error surface
   - product-specific loading, stale data, empty state, and error messages
   - should not leak between products or tabs

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

1. Tropical reference pass in the combined workspace.
2. Tropical standalone page candidate, if the shell is accepted and stable.
3. Alerts.
4. SPC.
5. Surface.
6. Drought.
7. Satellite.
8. Radar.
9. MRMS.
10. RTMA.

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
- open the Tropical tab
- verify Region is hidden only for Tropical
- verify basin/outlook cards render
- verify active storm cards render when cache/test data exists
- select a storm and confirm the right Inspector opens
- toggle Tropical layers and confirm map cleanup on tab switch
- open official product text and confirm the slide-in/modal closes cleanly

For future standalone product pages:

- canonical route returns 200
- product API calls succeed
- map renders nonblank
- product layers can be cleared without affecting other products
- `weather.html` still works until the clean-cut step for that product
