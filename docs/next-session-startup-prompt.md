# Next Session Startup Prompt

Date prepared: 2026-06-28

Start in:

```text
F:\Python\dashboard_2026
```

Use this prompt:

```text
We are continuing dashboard work in F:\Python\dashboard_2026.

Read first:
- docs/dashboard-change-and-enhancement-superfile.md
- docs/architecture.md when touching system boundaries
- docs/patterns.md when implementing a product/workflow pattern

Current status:
- The fixed map-first dashboard shell is accepted.
- Canonical product routes serve product-only dashboard mode: /surface, /alerts,
  /radar, /satellite, /spc, /rtma, /mrms, /drought, /tropical, /wpc, and /water.
- /weather.html remains the combined workspace and must keep working until it is
  explicitly retired.
- Product engines/pages own product-specific controls, requests, response
  interpretation, and most rendering.
- js/weather.js still owns shared map lifecycle, generic archive orchestration,
  shared scrubber infrastructure, and injected callbacks where cross-product
  state remains coupled.
- Backend route logic should stay in routes/*.py, route-facing cache/response
  behavior should stay in services/*_service.py, and upstream/cache refresh
  behavior should stay in workers/*_worker.py.

Recent completed work:
- Shared categorical legends now wrap whole swatch/label items using
  .legend-flow, labels can wrap without painting into neighboring swatches, and
  the Alerts legend uses the five-column helper. User browser smoke passed on
  2026-06-28.
- Satellite GOES composite products were exposed in the Satellite selector:
  Fire Temperature, Air Mass, Day Cloud Phase, Day Land Cloud/Fire,
  Day Snow/Fog, Nighttime Microphysics, Dust, Ash, and Sulfur Dioxide.
  Renderer-matched interpretive legends were added for these RGB composites,
  with a frontend fallback so legends stay visible when switching
  satellite/sector/product controls without a hard refresh. Scalar satellite
  colorbars remain for brightness-temperature channels only.
- GOES GLM Flash Extent Density is available from Satellite only, with
  one-minute and five-minute rolling aggregations, on-demand GLM tile rendering,
  and a fixed 4 km Web Mercator grid that counts unique flash extents per cell.
  Do not add GLM as a Radar overlay.
- Docs were consolidated into docs/dashboard-change-and-enhancement-superfile.md.
  Superseded planning docs were moved to docs/archive/.
- Storm Tracks (NST) icon accuracy: IEM meso rank threshold raised to ≥ 4
  (constant _MESO_MIN_RANK in services/radar_storm_attributes_service.py).
  Ranks 1–3 are weak shear not shown by professional tools; verified against
  Radarscope on a live event (KRAX, 2026-06-28).
- Storm-cell icon set redesigned: Storm Cell icon is now a small dark square
  with yellow border (was a circle); Probable Hail hollow green triangle has
  no label (question mark removed from both map icon and mini-legend).
- Floating Storm Tracks mini-legend added as a Leaflet topright control
  (NstLegendControl in weather.js), shown/hidden with the Storm Tracks toggle.
  CSS class .wx-mini-legend is reusable for similar legends on other pages.
- Radar site markers now have a black outline on all status variants for
  legibility on dark basemaps. Selected-site highlight rings unchanged.
- Debug endpoint /api/radar/debug/meso-raw?site=KXXX added to routes/radar.py
  for inspecting raw IEM meso/tvs field values during threshold tuning.

Important guardrails:
- Keep API paths stable unless a separate API cleanup is explicitly planned.
- Keep /spc startup ordering intact: normalize SPC controls and report-filter
  state before the first refreshActiveLayers() call.
- Confirm product engine/page script tags when adding a new product module; a
  missing window.NCH*Engine or window.NCH*Page silently prevents engine creation.
- When changing Satellite page control wiring, bump the relevant script query
  strings in weather.html so browser cache does not mask the new behavior.
- Make bounded, reviewable changes and update the superfile when roadmap or
  phase state materially changes.
- Preserve unrelated working-tree changes.

Validation defaults:
- Run the narrowest meaningful static check first, such as node --check for
  touched JavaScript and py_compile for touched Python.
- Browser smoke is user-owned for current dashboard work unless explicitly
  requested. Keep claims limited to static/import validation when no browser
  proof was run.
```
