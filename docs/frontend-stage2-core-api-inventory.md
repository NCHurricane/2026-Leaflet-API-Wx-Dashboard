# Frontend True Split Stage 2 — Phase 18 Core API Inventory

Status: completed 2026-07-16. This is the interface contract for Phases 19-27
of the Frontend True Split and Severe Weather Workspace track.

## Scope and method

The audit covered every object supplied by `js/weather.js` to:

- `configure*Page()` / `configureWarningsPanel()`; and
- `registerProductContext()` / `create*Engine()`.

The counts below are injected object-literal entries. They measure the current
coupling surface, not only the properties exercised in one runtime path.

| Product | Page entries | Engine entries | Unique within product | Migration phase |
| --- | ---: | ---: | ---: | --- |
| Alerts | 26 | 60 | 79 | 25 |
| Drought | 4 | 23 | 26 | 19 |
| MRMS | 12 | 44 | 49 | 22 |
| Radar | 44 | 62 | 90 | 24 |
| RTMA | 10 | 49 | 56 | 22 |
| Satellite | 9 | 52 | 58 | 23 |
| SPC | 18 | 15 | 32 | 21 |
| Surface | 9 | 31 | 35 | 20 |
| Tropical | 32 | 53 | 75 | 26 |
| WPC | 3 | 22 | 24 | 21 |
| Water | n/a | n/a | n/a | 26, after Tropical |

Current total: 578 injected entries, comprising 390 unique names. Of those,
411 entries (291 unique names) are engine-context entries and 167 entries
(145 unique names) configure page controllers. The earlier roadmap estimate of
about 206 members understated the current surface. Water has no page/engine
boundary yet; it remains implemented directly in `js/weather.js`.

## Phase 18 decisions

### Core is capability-based, not a replacement global context

There will be no new all-purpose `context` object. A page imports only the core
modules it uses and passes narrow capabilities to its engine. Product state,
DOM access, layer construction, timers, catalogs, and product-specific legends
remain in `frontend/pages/{product}/`.

`frontend/core/*` accepts a function only after at least two migrated pages require the
same behavior. Similar names alone do not make behavior shared.

The browser hierarchy lives under `frontend/` because root `lib/` is already a
Python helper package. `main.py` exposes the browser tree at `/frontend` rather
than mounting or exposing backend Python files.

### Core module contracts

| Module | Owned surface | Explicitly does not own |
| --- | --- | --- |
| `frontend/core/api.js` | Base-path-safe `apiUrl`, JSON/response fetch helpers, request cancellation/sequence helper, reusable progress polling | Product endpoints, catalogs, lookback rules, worker selection |
| `frontend/core/map-core.js` | Leaflet initialization, basemap selection, region bounds, current bounds, shared panes, map disposal | Product layers, product z-order decisions, product view presets |
| `frontend/core/scrubber.js` | `createScrubber()` instances with frames, index, play/pause, speed, enabled/progress/status state, and frame callback | Global modes or knowledge of Radar, Satellite, MRMS, or RTMA |
| `frontend/core/legend.js` | Per-page legend host with set/clear, map-panel alignment, and accessible collapse operations | Product thresholds, colors, labels, values, or HTML generation |
| `frontend/core/status.js` | Status message, viewer timestamp, reliability/source metadata, valid-time formatting, staleness helpers | Product freshness thresholds or product wording |
| `frontend/core/nav.js` | Product navigation and active-page state | Product controls or layer state |
| `frontend/core/settings.js` | Namespaced load/save and change notification | Product defaults that belong in a page config |
| `frontend/core/core.css` | Application chrome, self-hosted Montserrat typography, shared structural primitives, and reusable categorical/continuous legend presentation | Product thresholds, legend copy/data, markers, or product-specific tool styling |

The initial exports may be smaller than this table. Phase 19 creates only the
parts Drought actually consumes; later phases extend a core module only when a
second real consumer proves the shared behavior.

### Page and engine ownership

Each `frontend/pages/{product}/{product}-page.js` owns:

- DOM queries, controls, selected values, and page-local persistence;
- creation of core map/status/legend/scrubber instances;
- the full standalone catalog/config passed to its engine; and
- translating user actions into engine calls.

Each `{product}-engine.js` owns:

- endpoint calls and response validation;
- product caches, Leaflet layers, render operations, and request sequencing;
- product-specific legends and freshness rules; and
- a public capability API usable without the product's page controller.

An engine must not query product-control DOM or call another product engine.
The standalone page and workspace may instantiate the same engine with
different catalogs.

### Minimum engine capability contract

Every migrated engine exposes lifecycle capabilities equivalent to:

- `loadCurrent(options)` or the product-specific current-data operation;
- `setVisible(visible)`;
- `clear()`; and
- `destroy()` for listeners, timers, requests, and layers it owns.

Radar and Satellite additionally expose a timeline adapter for the workspace:

- `listFrames({ startMs, endMs })`; and
- `showAtOrBefore(timeMs)`.

The workspace owns the master clock. Timeline engines never exit or update a
sibling product's scrubber. Snapshot products expose refresh/load operations
and do not participate in the master-clock index.

## Coupling that must not cross into the new pages

The following current members are migration signals, not future core APIs:

- `exitMrmsScrubMode`, `exitRtmaScrubMode`;
- `hasMrmsScrubFrames`, `hasRtmaScrubFrames`;
- `setRtmaScrubberStatus`, `updateRtmaScrubberUi` when called by other products;
- `refreshActiveLayers`, `clearAllMapLayers`, and global `isTypeEnabled`;
- Satellite's `setArchiveModeButtonInactive`; and
- WPC/SPC/Tropical reuse of another product's alert-detail helpers.

Standalone pages replace these with page-local state. The workspace coordinates
visibility and time through engine capabilities; engines do not coordinate one
another.

## Product migration boundary

A product phase is complete only when all of the following are true:

1. Its canonical route serves `frontend/pages/{product}/{product}.html`.
2. That HTML loads only third-party libraries, required `frontend/core/*`, and
   its own directory. Shared third-party assets are vendored into
   `frontend/lib/` before final monolith retirement.
3. Its engine has no sibling-product calls and no product-control DOM queries.
4. Standalone behavior reaches parity and receives a focused browser smoke.
5. The migrated implementation is removed from `js/weather.js` without
   changing the remaining legacy products.
6. Static syntax/search checks and browser proof are recorded separately.

`weather.html` remains operational throughout Phases 19-26. Phase 27 may delete
it only after Water also has a standalone boundary.

## Phase 19 starting contract: Drought

Drought is the proof-of-pattern because it has the smallest existing combined
surface (26 unique names) and no animation workflow.

The Drought page owns date/category/region/opacity controls and all DOM updates.
The Drought engine owns date/state-stat requests, the state-stat cache, the
GeoJSON layer, and filtering. Its injected shared dependencies are limited to
the API client, map capability, legend host, and status reporter.

Phase 19 must preserve the legacy `weather.html` Drought path until the new
`/drought` page passes parity. It should not pre-create unused core modules or
move a second product in the same slice.

Phase 19 completed 2026-07-16. Browser parity passed before the old Drought
modules and monolith implementation were removed. The shared shell retained
its `/drought` navigation link and passed a post-extraction browser smoke.
Follow-up parity review moved the legend from a constrained sidebar to a
map-panel overlay, restored the shared logo and global updated-time
HUD, added Lat/Lon/state/country/county controls to `map-core.js`, and made the
highlighted latest release auto-load. A second parity correction added the
Off/US/World city source, source/zoom-bounded density filtering, and city font
size to the same shared map capability. This establishes those shell behaviors
as reusable core capabilities for the later product migrations. Final UI
comparison against the pre-split shell also restored shared navigation icons,
Data Age, reset view, numeric zoom, USGS/no-label basemaps, and attribution;
cross-product warning panes and developer-only controls remain outside the
standalone product boundary by design. Boundary payloads use versioned browser
Cache Storage plus long-lived HTTP caching; state and county responses are
separate so default state borders do not pull county geometry. The generated
source files remain reusable under the gitignored runtime `cache/overlays/`
directory rather than adding about 53 MB of generated data to version control.

The final Phase 19 shell refinement adopted the high-fidelity Option 1A tabbed
sidebar. `frontend/core/sidebar-tabs.js` keeps every panel mounted and toggles
`hidden`, `aria-selected`, and roving tab focus; it supports click plus
Left/Right/Home/End keyboard navigation and any page-supplied optional fourth
tab. Shared sidebar structure and tab styling live in `core.css`; Drought owns
only its panel contents and product-specific spacing. Automated browser smoke
passed all three tabs, retained input state, pinned header/footer geometry, and
latest-release display.

The final legend refinement established `frontend/core/legend.js` as a confined
map-panel host rather than a product-specific floating card. It owns alignment
(left, center, or right), collapse state, and lifecycle cleanup. Shared CSS owns
the dark glass shell plus categorical-item and continuous-colorbar/tick
primitives; each product engine still supplies its own HTML, labels, colors,
thresholds, and values. Drought defaults the tray to bottom-left, renders all
five USDM classes, and adds cumulative/individual state statistics and DSCI when
a state is selected. Browser smoke verified the expanded national, collapsed,
and NC-stat layouts remained completely inside the map panel.

Shared typography is also part of the accepted shell boundary. `core.css`
registers the existing normal and italic Montserrat variable files from the
root `/fonts` static mount, applies Montserrat through `:root`, and lets page CSS
inherit it. Pages should not register duplicate product-local font families.
