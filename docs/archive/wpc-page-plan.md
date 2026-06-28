# WPC Product Page Plan

Created: 2026-06-18
Status: **Complete — 2026-06-18**

Multi-session plan to add a **WPC** product page (`/wpc`) for QPF, Excessive
Rainfall Outlook (ERO), and Winter Weather products. Mirrors the existing
SPC/Tropical data-endpoint + cache-first patterns. Anchor by symbol name, not
line numbers.

## Source Decision (locked)

**Primary source: WPC KML/KMZ feed** — `https://www.wpc.ncep.noaa.gov/kml/kmlproducts.php`

Rationale vs. alternatives:

- **KML/KMZ (chosen)** — reuses the KMZ/KML parsing already proven in
  `workers/tropical_worker.py` (`zipfile` + namespace-stripped `ElementTree`).
  Stable `*_latest.kmz` URLs mean no forecast-cycle/day URL math and a simple
  freshness-gated refresh, like the Tropical "latest" pattern. KMZ is just a
  zipped KML, so existing zip handling applies. Polygons are categorical/contour
  — a direct fit for the SPC-style "GeoJSON data endpoint + Leaflet `L.geoJSON`
  + legend" workflow.
- **WPC shapefiles** (`about_gis.shtml`) — rejected as primary. They are `.tar`
  archives; the current shapefile reader (`_shapefile_feature_collection_from_zip`)
  only opens `.zip`, and the URLs require composing cycle+day. Cleaner attribute
  tables, but not worth the extra plumbing for these products. Keep as a fallback
  only if we later want fully custom legends.
- **NWS Cloud GIS (OGC WMS/WFS)** (`cloudgiswebservices`) — rejected. Does not
  enumerate WPC QPF/ERO/winter products; mainly radar via GeoServer. Wrong
  paradigm (image tiles / OGC) for our vector workflow.

## Products & Source URLs

Base: `https://www.wpc.ncep.noaa.gov`

| Group  | Product                         | URL pattern                                              | Geometry           |
| ------ | ------------------------------- | ------------------------------------------------------- | ------------------ |
| ERO    | Excessive Rainfall Outlook D1-3 | `/kml/ero/Day_{1-3}_Excessive_Rainfall_Outlook.kmz`     | Categorical polys  |
| QPF    | 6hr / 24hr accum, Days 1-3      | `/kml/qpf/QPF{dur}_{day}_latest.kmz`                     | Contour polys      |
| QPF    | Multi-day accum, Days 1-7       | `/kml/qpf/QPF{hours}hr_Day{range}_latest.kmz`           | Contour polys      |
| Winter | Winter weather package D1-3     | `/kml/winwx/Day{1-3}_winter_weather.kml`                | Prob polys         |
| Winter | Per-threshold snow/ice prob     | `/kml/winwx/Day{1-3}_p{snow,icez}_gt_{threshold}.kml`   | Prob polys         |
| Bonus  | River Flood Outlook (5-day)     | `/kml/fop/fop_v2.kmz`                                    | Categorical polys  |
| Bonus  | SigWx Days 1-3                  | `/kml/noaa_chart/WPC_Day{1-3}_SigWx_latest.kml`         | Mixed              |

All groups remain visible year-round. Winter products are less common outside
the primary cold season but can still be issued.

**Session-1 task:** download one sample of each group and inspect Placemark
`<name>` / `ExtendedData` / `<description>` to confirm the exact attribute keys
used for category/threshold and color. Do not assume field names until verified.

## Cache Layout

```
cache/wpc/
  summary.json                      # index: products, updated, freshness
  ero/day{1,2,3}.geojson
  qpf/{product_key}.geojson
  winter/day{1,2,3}.geojson
  fop/fop.geojson                   # if enabled
  .meta/*.meta.json                 # ETag/Last-Modified per source URL
```

Each `.geojson` payload mirrors the tropical layer shape:
`{updated, product, source_url, geojson: FeatureCollection}` with category/color
folded into each feature's `properties`.

## Backend (refactor worktree: `codex/backend-product-refactor`)

Follow the established boundaries (see `docs/architecture.md` Module Map):

1. **`config/wpc_config.py`** — product registry (id → URL, group, label,
   season window) + color tables (`ERO_COLORS` MRGL/SLGT/MDT/HIGH, QPF accum bins,
   winter prob ramp), mirroring `config/alerts_config.py` `ALERT_COLORS`.
2. **`workers/wpc_worker.py`** — fetch each enabled product KMZ/KML →
   parse to GeoJSON → write `cache/wpc/...`. Reuse the tropical helpers'
   approach: `_request_url` w/ ETag/If-Modified-Since, `_fetch_binary`,
   namespace-stripped KML walk (`_kml_local`/`_kml_geometry`), category→color
   mapping. Freshness via `workers/_freshness.py` (`is_cache_fresh` /
   `mark_run_complete`, key `"wpc"`). Support `--force` and a `--raw-dir` test
   mode like the tropical worker.
3. **`services/wpc_service.py`** — cache reads + cold-start inline worker
   fallback + response shaping (add `count`), mirroring SPC/alerts services.
4. **`routes/wpc.py`** — `APIRouter`:
   - `GET /api/data/wpc?group={ero|qpf|winter|fop}&day={1-3}[&product={key}]`
     → GeoJSON FeatureCollection (+`count`).
   - `GET /api/data/wpc/catalog` → available products/days for control population.
   Register in `main.py` router list.
5. **`workers/scheduler.py`** — add `wpc_worker` to the in-process fallback table.
   Suggested interval: 30 min (matches SPC; WPC products update a few times/day).
6. **Canonical page route** — add `/wpc` to the generated product-shell route
   set (same mechanism as `/spc`, `/alerts`).

## Frontend (this worktree: `codex/frontend-product-pages`)

Follow the page/engine split now standard for products
(see `docs/product-page-shell-plan.md`):

1. **`js/wpc-config.js`** (or fold into page) — group/day/product menu metadata +
   legend color tables matching `config/wpc_config.py`.
2. **`js/wpc-engine.js`** — context-backed fetch + response sequencing for
   `/api/data/wpc` (model on `js/spc-engine.js`).
3. **`js/wpc-page.js`** — control wiring (group selector, day selector, product
   dropdown for QPF/winter thresholds), `L.geoJSON` render styled by
   `properties.color`, legend build, layer cleanup on tab switch.
4. **`weather.html`** — include both new script tags (the shell breaks silently
   if engine/page scripts are omitted — see Phase-15 note in shell plan), and add
   the WPC tab to the product tab row + left controls dock.
5. Call `map.invalidateSize()` after the WPC tab becomes visible.

Control model (mirrors the SPC day/hazard dropdowns):

- Group: ERO / QPF / Winter (/ Flood).
- Day: 1–3 (QPF extends to 7 for multi-day).
- Product: only shown for QPF (duration/accum window) and Winter (threshold).
- Opacity slider + show/hide toggle like other vector layers.

## Session Breakdown

**Session 1 — Source recon + ERO vertical slice (backend)**
- Confirm KML attribute keys from real samples (per above).
- `config/wpc_config.py` with ERO entries + `ERO_COLORS`.
- `workers/wpc_worker.py` minimal: ERO Days 1-3 only → `cache/wpc/ero/*.geojson`.
- `services/wpc_service.py` + `routes/wpc.py` for `group=ero`.
- Verify: run worker `--force`, hit `/api/data/wpc?group=ero&day=1`, check count.

**Session 2 — ERO frontend slice**
- `/wpc` route + tab + `js/wpc-engine.js` + `js/wpc-page.js` (ERO only).
- Render + legend + layer cleanup; browser smoke.

**Session 3 — QPF**
- Add QPF products (6/24hr D1-3, multi-day D1-7) to config + worker.
- Frontend product dropdown for accumulation window; contour-bin legend.

**Session 4 — Winter weather**
- Add the per-threshold products referenced by each day package. Keep Winter
  controls visible year-round because meaningful warm-season products can occur;
  use source/cache availability and clean no-area responses instead of calendar
  gating.
- Threshold dropdown + prob ramp legend.

**Session 5 — Polish / bonus**
- FOP completed. SigWx remains optional. Scheduler interval tuning,
  empty/stale/source-unavailable states, and final cross-product smoke.
- Availability/freshness hardening completed: per-product source status,
  last-valid-cache preservation, stale metadata, cold-source-unavailable state,
  startup freshness monitoring, and a 30-minute Windows task definition.
- Dashboard legend audit started on 2026-06-28. Shared categorical legends now
  wrap whole swatch/label items using `.legend-flow`, labels can wrap without
  painting into neighboring swatches, and the Alerts legend moved from the
  six-column helper to the five-column helper after the larger label-size pass.
  User browser smoke passed on 2026-06-28.

## Completion Summary

Completed product groups:

- Excessive Rainfall Outlook, Days 1–3.
- QPF: 6-hour, 24-hour, and multi-day products through Day 7.
- Winter Weather: snow >4", >8", >12", and ice >0.25" probabilities,
  Days 1–3, available year-round.
- Five-Day River Flood Outlook.

Completed operational behavior:

- Cache-first worker, API, catalog, and 30-minute Windows scheduled task.
- Per-product source availability, stale metadata, and last-valid-cache
  preservation.
- WPC-authored no-significant-area map overlays for ERO and Winter products,
  with a reusable empty-message path for future products.
- Responsive WPC legends, opacity control, request sequencing, and tab cleanup.

Manual browser smoke completed by the user on 2026-06-18. All implemented
products rendered correctly, and products with no significant areas displayed
the map no-data overlay.

Deferred:

- SigWx mixed-geometry products remain an optional future enhancement.
- Dashboard-wide legend audit pass is complete for the shared categorical
  legend wrapping and Alerts five-column adjustment; user browser smoke passed
  on 2026-06-28.

## Product Expansion — 2026-06-18

Planned increments:

1. Mesoscale Precipitation Discussions (MPDs).
2. Probabilistic QPF (PQPF).
3. Expanded Days 1–3 winter guidance.
4. Day 4–7 winter outlook.
5. Day 1–3 Significant Weather.
6. Day 3–7 Heat Index.
7. Surface fronts and pressure centers.

### Increment 1 — Active MPDs

Status: **Code complete; manual browser smoke pending**

- Added the WPC MetWatch active-page index as the authoritative list of current
  MPDs. `MPD_latest.kmz` is not sufficient because it contains only the newest
  discussion.
- The worker downloads each active MPD KMZ, aggregates its polygon, and exposes
  MPD number/type, issue time, UTC start/end validity, WFO/RFC lists, area, and
  official discussion URL.
- Expired MPDs are filtered both during cache generation and at API response
  time.
- Added likely/possible/unlikely map styling, legend entries, tooltips, and
  the shared draggable SPC/NWS detail panel.
- Each active MPD now caches its complete WPC bulletin text. The panel renders
  the Summary and Discussion sections, validity countdown, WFO/RFC chips,
  official WPC source link, and previous/next navigation across active MPDs.
- ERO polygons use one shared modal per forecast day containing the official
  day-specific Excessive Rainfall Discussion, regardless of which risk polygon
  is clicked.
- Winter Weather polygons use the official Winter Weather Forecast Discussion.
- MPD polygons open only their own discussion without active-MPD pagination.
- QPF and River Flood Outlook remain tooltip-only and do not open modals.
- Every WPC modal links to its authoritative discussion page rather than its
  KML/KMZ source file.
- The existing WPC no-data overlay reports when no MPDs are active.
- Live worker verification on 2026-06-18 returned three active MPDs with valid
  metadata and discussion links.

Next increment: **Probabilistic QPF (PQPF)**.

### UI Polish — 2026-06-19

Status: **Complete**

- Sidebar controls redesigned: group pills in a 4-column grid, day pills in a
  no-wrap flex row, QPF/winter sub-tabs in a flex row (no wrapping).
- ERO group pill renamed "Excess Rain"; FOP renamed "River Flood"; MPD renamed
  "Meso Disc".
- Radio selectors styled to match SPC: `appearance:none` square checkbox,
  cyan checked state with SVG checkmark, label left / control right via CSS
  grid. CSS specificity rule: `.wpc-radio-list .wpc-radio-item label` to
  override the `.wx-block label` default.
- Surface analysis split into two separate group pills: **Surface** (single
  latest-analysis PNG, no scrubber) and **Forecast** (F06–F60 scrubber-driven).
  Backend: `SURFACE_ANALYSIS_PRODUCTS` + `SURFACE_FORECAST_PRODUCTS` in
  `config/wpc_config.py`; `WPC_PRODUCTS["forecast"]` added.
- Shared bottom scrubber (`js/scrubber.js` factory, single `wpcScrubber`
  instance) replaces per-product scrubbers. Drives Forecast and QPF-6hr;
  sidebar radio lists for direct-jump navigation, kept in sync via
  `_syncSidebarRadio`. Scrubber hidden for groups that don't need it.
- ERO Days 4 and 5 were returning HTTP 400 — fixed by expanding `ERO_DAYS`
  from `(1, 2, 3)` to `(1, 2, 3, 4, 5)` in `config/wpc_config.py`.
- Clicking the QPF group pill auto-selects the 6hr sub-tab (and shows its
  radio list); clicking Winter auto-selects Snow. Implemented via `.click()`
  on the default sub-tab button inside the group-pill handler so all existing
  wiring runs.
- Reliability bar wired: `_activeReliabilityType()` in `weather.js` now returns
  `'wpc'` when WPC is the active layer. The engine already called
  `context.setReliability('wpc', ...)` and `context.setTimestampSource('wpc', ...)`
  after every successful load (both image and GeoJSON paths).

### Surface Analysis and Short-Range Forecast Overlays

Status: **Complete**

- Added the latest WPC CONUS surface analysis and F06/F12/F18/F24/F30/F36/F48/F60
  short-range PMSL/surface-front forecasts.
- Uses WPC's transparent-background PNG products from the official KML catalog.
- Images are worker-cached under `cache/wpc/surface/` and served locally rather
  than loaded directly by the browser.
- All overlays use the WPC KML bounds: north 58.79, south 14.88, west -130.08,
  east -64.06.
- The frontend renders these products with `L.imageOverlay`, uses the existing
  WPC opacity control, and intentionally displays no legend or detail modal.

## Verification

```powershell
node --check js\wpc-page.js
node --check js\wpc-engine.js
.\.venv\Scripts\python.exe -m py_compile main.py routes\wpc.py services\wpc_service.py workers\wpc_worker.py config\wpc_config.py
```

Browser smoke (per session):
- `/wpc` returns 200; tab renders in the dashboard shell.
- Group/day/product controls populate from `/api/data/wpc/catalog`.
- Selecting a product renders polygons with correct category colors + legend.
- Layer clears on tab switch without affecting other products.
- Out-of-season winter products hide gracefully (no error spam).

## Open Questions / Risks

- **Attribute keys unknown until sampled** — Session 1 must confirm before
  finalizing color mapping. KML carries embedded styling we can fall back to if
  attributes are thin.
- **QPF contour density** — multi-day QPF polygons can be large; watch payload
  size and consider simplification if render is slow.
- **Source availability** — treat 404/network failures as temporary source
  unavailability, preserve the last valid cache, and reflect source/cache state
  separately in the catalog.
- **Worktree split** — backend files land in the backend refactor worktree;
  frontend files in this worktree. Keep config color tables in sync across both.
