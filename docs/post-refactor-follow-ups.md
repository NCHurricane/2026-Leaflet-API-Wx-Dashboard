# Post-Refactor Follow-Ups

Use this file to collect issues and improvement ideas found during testing.
Do not begin these items until the current refactor and cleanup validation is
complete and the user authorizes the next work.

## Testing Observations

1. Alert loading time on workspace page concerns
   - Status: To investigate after current testing and refactor validation.
2. Scrubber: add first-frame and last-frame buttons, including wiring, to all
   project scrubbers.
   - Status: Deferred until explicitly authorized after the current refactor.

## Testing Batch — 2026-08-05

Status: Collected during post-refactor testing. Investigation and implementation
are deferred until explicitly authorized.

1. Workspace — Home does not turn off Storm Reports when Storm Reports is
   selected.
2. Workspace — Place SPC products and SPC Mesoscale Discussion layers above the
   Satellite layer in the layer stack.
3. Workspace/WPC — Move the Day pills above the four product-family pills and
   correct their labels. Rewire the workflow so the user selects a day first,
   after which the available product pills become active.
4. Workspace/WPC — Products do not load and the Day pills never activate. Fix
   this as part of item 3.
5. Workspace — Ensure MRMS product layers appear above Satellite layers.
6. Workspace — Ensure every enabled layer with an active product has a legend
   in the combined tabbed legend.
7. Satellite — When a Target Area, Mesoscale Sector, or Rapid Scan sector is
   selected, move the map to that element's extent as Workspace does.
8. Satellite — Diagnose these Meteosat download failures and determine whether
   retry/resume behavior should handle them:

   ```text
   [app-meteosat-meteosat12-fulldisk] meteosat12/FULLDISK: cataloged=23 already_cached=13 missing=10 downloading=['20260805T204500Z', '20260805T203000Z', '20260805T183000Z']
   [app-meteosat-meteosat12-fulldisk] meteosat12/FULLDISK/20260805T204500Z failed: ChunkedEncodingError: ('Connection broken: IncompleteRead(2977236 bytes read, 16827170 more expected)', IncompleteRead(2977236 bytes read, 16827170 more expected))
   [app-meteosat-meteosat12-fulldisk] meteosat12/FULLDISK/20260805T203000Z: downloaded elapsed=0h 1m 43s
   [app-meteosat-meteosat12-fulldisk] meteosat12/FULLDISK/20260805T183000Z failed: HTTPError: 503 EUMETSAT download failed for W_XX-EUMETSAT-Darmstadt,IMG+SAT,MTI1+FCI-1C-RRAD-FDHSI-FD--CHK-BODY---NC4E_C_EUMT_20260805183506_IDPFI_OPE_20260805183045_20260805183124_N__O_0112_0006.nc: <html><body><h1>503 Service Unavailable</h1>
   No server is available to handle this request.
   </body></html>
   [app-meteosat-meteosat12-fulldisk] complete jobs=1 downloaded=1 errors=2 pruned=0 elapsed=0h 3m 6s
   ```

9. Satellite — When GMGSI > Full Disk is selected, use a viewport derived from:
   `[W, E, S, N] = [-228.69, 103.01, -69.35, 62.27]`,
   `center = [-8.67, -62.84]`, `zoom = 3`.
10. Satellite — Investigate why GMGSI > Global generates much smaller Z3 tiles
    than other satellites' Full Disk sectors.
11. Global workflow — Investigate extending SPC's stale-product workflow to
    other applicable pages: show `Loading [Product]` rather than a stale
    overlay, and show `No [Selected Product] for [timeframe]` for legitimate
    empty results. Ask the user to expand on the intended behavior before work,
    including whether the current product should turn off before a new product
    loads. Consider replacing `Warming` with `Loading` for user clarity.
12. SPC — Selecting Mesoscale Discussions should automatically load the latest
    data after any required warming/loading finishes.
13. SPC — Separate the Mesoscale Discussion and Storm Report pills.
14. RTMA — Selecting Wind Speed should automatically select Wind Direction,
    while still allowing Wind Direction to be turned off independently. Move
    Wind Direction to the field immediately after Wind Speed.
15. RTMA/global lifecycle — When switching pages, rendering for a product on the
    previous page continues and slows rendering requested by the new page.
    Diagnose cancellation and ownership behavior.
16. MRMS — Verify whether selecting a product causes the backend to load and
    render every animation frame before displaying the current frame.
17. MRMS/MESH — Research whether the map can zoom to the location associated
    with the `Largest Hail` value shown in the legend.
18. MRMS — Inspect whether `mrms-legend-units` can display useful unit
    conversions together, such as meters and feet.
19. MRMS/Rotation Track — Verify whether `mrms-legend-stat` reports the maximum
    value in the underlying data or only the maximum value represented by the
    legend scale.
20. Drought — Investigate whether gaps in lower overlays can be filled where
    higher overlays currently cover them. Ask the user for screenshots when
    this item is ready for investigation.
21. Tropical — When multiple Tropical Outlook cards are present, investigate
    making a card click display only that card's element on the map.
22. Tropical/Atlantic — Default viewport:
    `[W, E, S, N] = [-98.48, -17.36, 8.02, 46.35]`,
    `center = [28.92, -57.92]`, `zoom = 5`.
23. Tropical/Eastern Pacific — Default viewport:
    `[W, E, S, N] = [-155.74, -74.62, -1.85, 39.1]`,
    `center = [19.93, -115.18]`, `zoom = 5`.
24. Tropical/Central Pacific — Default viewport:
    `[W, E, S, N] = [-225.06, -110.33, -11.89, 45.21]`,
    `center = [19.05, -167.69]`, `zoom = 4.5`.
25. WPC/QPF — Replace subproduct selectors with pills. For example, 6HR should
    expose F06–F12, F12–F18, and the other time ranges as pills without
    repeating the product name in every option.
26. Global animation workflow — Assess loading only the current product frame
    initially and providing a user-triggered way to load lookback frames, such
    as a button near the Lookback slider. Measure time savings, UX impact, and
    implementation scope before deciding.
