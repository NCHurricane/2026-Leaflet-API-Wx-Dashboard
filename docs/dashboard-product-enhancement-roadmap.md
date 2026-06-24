# Dashboard Product Enhancement Roadmap

## Summary

Implement enhancements in bounded phases:

1. Correct and expand domestic NEXRAD.
2. Expose existing satellite products and add GOES lightning.
3. Add a flood-focused Water page.
4. Add global satellite coverage.
5. Add international radar through provider-specific adapters.

Marine and Fire/Smoke remain ranked backlog items.

## Implementation Status

### Phase 1A complete: authoritative live-radar catalog

- The backend catalog now owns the currently supported live product labels,
  fields, palettes, units, ranges, masks, capabilities, and cache IDs.
- The Radar product selector is populated from the backend catalog.
- The unsupported static `L3_DTA` option was removed.
- Live Radar responses now advertise provider, network, product capabilities,
  source timestamp, and elevation metadata placeholders.
- Remaining Phase 1 work: expand the catalog, correct and validate all Level III
  mappings, add Level II elevation selection, and add product-specific
  rendering for the additional product families.

### Phase 1B complete: Level II product catalog expansion

- Added spectrum width, differential reflectivity, correlation coefficient,
  specific differential phase, and differential phase.
- Added reachable product-specific palettes and legends for all Level II
  products.
- Added native-field masking and value scaling, including meters-per-second to
  knots conversion for velocity and spectrum width.
- Remaining Level II work: elevation discovery, `auto` selection, explicit
  nearest-angle selection, and response metadata populated from each volume.

### Phase 1C complete: Level II elevation selection

- Added an `auto`/explicit elevation selector for Level II products.
- Each rendered volume records available angles and the selected angle.
- Explicit requests use the nearest available sweep for each volume.
- Level II cache paths are isolated by requested elevation so products and
  angles cannot overwrite each other.

### Phase 1D1 complete: initial Level III expansion

- Added storm-relative velocity (`N0S`), differential reflectivity (`N0X`),
  correlation coefficient (`N0C`), and specific differential phase (`N0K`).
- Corrected stale Level III mnemonic labels in the repository catalog.
- Verified each product against current NOAA open-data samples and Py-ART field
  decoding before exposing it.
- Remaining Level III work: hydrometeor classification, digital precipitation
  rate, storm-total precipitation, echo tops, and VIL.

### Phase 1D2 complete: storm-relative velocity correction and Level II SRV

- Added the custom `SRRadarLoopsSRvelo.pal` palette and parser support for
  GR-style `SolidColor` palette rows.
- Corrected Level III `N0S` rendering so decoded product-56 velocity bins are
  treated as knots instead of being scaled a second time from meters per second.
- Added cache-version isolation for corrected `N0S` frames so stale pre-fix
  overlays are not reused.
- Added `L2_SRV`, a higher-resolution Level II-derived storm-relative velocity
  product based on Level II velocity.
- `L2_SRV` initially supports a fixed fallback storm motion, with motion values
  carried through product metadata, worker rendering, and cache keys.

### Phase 1E complete: NST storm tracks and selected-cell SRV

- Added a Level III `NST/58` storm-track parser for the alphanumeric Storm
  Tracking Information product.
- Added `/api/radar/live/storm-tracks` to fetch and parse NST cells for a radar
  site and optional target radar-frame timestamp.
- Added a `Storm Tracks (NST)` Radar overlay showing clickable storm-cell
  markers and forecast track lines.
- Clicking an NST cell records its motion vector and, when `L2_SRV` is active,
  reloads SRV using that selected cell's speed and motion direction.
- Selected-cell SRV cache keys are isolated by rounded speed, direction, source,
  cell ID, and elevation, for example
  `L2_SRV__NST_CELL_B0_039KT_TO272_V1__ELEV_0P5`.
- The Radar status line now identifies when SRV is using a selected NST cell.
- Storm-track visibility can be toggled without invalidating the active
  cell-relative SRV animation context.
- Radar image overlay replacement now tracks and removes older radar image
  overlays so cell-relative SRV reloads do not leave stale overlays underneath.

### Phase 1F complete: Remaining Level III products and standardized products API

- Added 5 remaining Level III products to the catalog:
  - L3_N0H: Hydrometeor Classification (HCA palette, 0–10 categories)
  - L3_DPR: Digital Precipitation Rate (DPA palette, 0–8 in/hr)
  - L3_NRR: Storm Total Precipitation (PRECIP_TOTAL palette, 0–20 in)
  - L3_NET: Echo Tops (ET palette, 0–70 kft)
  - L3_DVL: Vertically Integrated Liquid (VIL palette, 0–80 kg/m²)
- All products integrated with specialized color palettes and Py-ART field mappings.
- Implemented standardized `/api/{service}/products` endpoints across all pages:
  - `/api/radar/products` → 19 Level II & III products
  - `/api/wpc/products` → product groups (QPF, ERO, Winter, etc.)
  - `/api/rtma/products` → UI products + streams
  - `/api/mrms/products` → products + sub-products + groups
  - `/api/satellite/products` → catalog metadata
  - `/api/tropical/products` → data types + basins
  - `/api/spc/products` → hazards + reports + days
  - `/api/drought/products` → USDM + data types
  - `/api/surface/products` → surface observation fields
- Archived manual storm-motion controls for L2_SRV (NST cell selection provides
  sufficient dynamic control).

**Phase 1 complete:** All radar products (19 total), live catalog, elevation
selection, NST storm tracks, selected-cell SRV, and standardized API endpoints
are implemented and ready for browser smoke testing.

## Implementation Changes

### 1. Radar foundation and NEXRAD products

- Replace duplicated static product options with one backend-owned catalog used
  by the UI, API, worker, legends, units, and cache keys.
- Correct existing Level III mappings and remove the unsupported `L3_DTA`
  UI/backend mismatch.
- Support these initial products:
  - Level II: reflectivity, velocity, spectrum width, ZDR, correlation
    coefficient, KDP, differential phase, and Level II-derived storm-relative
    velocity.
  - Level III: reflectivity, velocity, storm-relative velocity, ZDR,
    correlation coefficient, KDP, hydrometeor classification, digital
    precipitation rate, storm-total precipitation, echo tops, and VIL.
- Add an elevation selector for Level II. Use `auto` by default; explicit
  selections request the nearest available elevation angle for each volume.
- Add product-specific color tables, units, value ranges, masking, and legends
  instead of treating every non-velocity product as reflectivity.
- Extend Radar API responses with product capabilities, available elevations,
  selected elevation, provider, network, and source timestamp.
- Use Level III `NST/58` Storm Tracking Information as a clickable storm-motion
  source for `L2_SRV`.
- Keep SRV fallback behavior when NST is unavailable or contains no cells.

### 2. Satellite products and lightning

- Expose existing implemented composites: Fire Temperature, Air Mass, Day Cloud
  Phase, Day Land Cloud/Fire, Day Snow/Fog, Nighttime Microphysics, Ash, and
  Sulfur Dioxide.
- Add GOES GLM Flash Extent Density products using rolling one-minute and
  five-minute aggregations from Level 2 lightning data.
- Keep lightning synchronized with the dashboard scrubber and allow it as a
  Radar overlay.
- Replace flat satellite tabs with:
  - Region: Americas, Pacific, Europe/Africa, Indian Ocean.
  - Platform: only satellites valid for that region.
  - Sector and product controls filtered by platform capability.

### 3. Water page

- Add `/water` to the shared product shell and navigation.
- Use the modern USGS APIs for monitoring locations, continuous values, daily
  history, and time-series metadata.
- Integrate NOAA National Water Prediction Service forecasts and flood
  categories.
- Load stations by map viewport with clustering and color them by observed or
  forecast flood status.
- Provide a station inspector containing current stage, streamflow, trend,
  operational thresholds, forecast hydrograph, flood impacts, data age, and
  source links.
- Include optional WPC Excessive Rainfall Outlook and Real-Time Flood Impact
  overlays.
- Cache upstream responses and show stale data with an explicit timestamp
  rather than removing stations.
- Exclude groundwater exploration, water quality, coastal tides, buoys, and
  gauge cameras from v1.

Proposed internal endpoints:

- `GET /api/water/stations?bbox=...`
- `GET /api/water/stations/{site_id}`
- `GET /api/water/stations/{site_id}/observations`
- `GET /api/water/stations/{site_id}/forecast`

### 4. Global satellite coverage

- Add Himawari-9 as the operational Pacific platform using NOAA's open AWS
  archive. Keep Himawari-8 available for historical/archive use only.
- Add Meteosat platforms by operational role:
  - Meteosat-12: Europe/Africa full disk.
  - Meteosat-11: rapid-scan Europe and North Africa.
  - Meteosat-9: Indian Ocean.
- Do not expose Meteosat-10 initially because the selected platforms already
  provide the distinct operational coverage needed.
- Generalize the current GOES-specific provider, channel, projection, sector,
  and cache model into platform descriptors and capability matrices.
- Use optional server-side EUMETSAT credentials; hide unavailable platforms
  cleanly when credentials are absent.

### 5. International radar

Use a provider-neutral radar site model without pretending every network offers
NEXRAD product parity.

Rollout order:

1. Canada through ECCC GeoMet radar services.
2. Germany through DWD open radar composites and supported site data.
3. Australia through Bureau of Meteorology five-minute rendered radar imagery.

Each provider declares supported products, animation interval, projection,
attribution, archive depth, and whether data are native grids or rendered
imagery.

## Test Plan

- Unit-test every radar code, label, unit, palette, field mapping, and elevation
  selection.
- Unit-test SRV storm-motion validation, selected-cell cache keys, and NST table
  parsing.
- Render fixture volumes for each supported Level II and III family.
- Verify no product appears in the UI unless the backend advertises it.
- Verify NST markers/tracks align with radar-relative azimuth/range on real
  samples.
- Verify `L2_SRV` selected-cell animation keeps playing when the Storm Tracks
  overlay is toggled off.
- Test satellite platform/product compatibility and GLM one-/five-minute
  aggregation.
- Use recorded provider fixtures for Himawari, Meteosat, ECCC, DWD, BOM, USGS,
  and NOAA NWPS.
- Browser-smoke `/radar`, `/satellite`, `/water`, and `/weather.html`, including
  scrubbers, source switching, stale states, and map cleanup.
- Confirm cache retention, worker runtime, upstream throttling, attribution, and
  missing-credential behavior.

## Backlog

1. Marine page using NDBC buoys and NOAA CO-OPS tides, currents, and coastal
   water levels.
2. Fire/Smoke page using NASA FIRMS detections and NOAA smoke analysis.
3. Cross-product severe-weather workspace combining Radar, GLM, warnings, SPC
   outlooks, and storm reports.
3. [Alternative] Cross-product weather page, taking the basics from each page (Current observations, radar, satellite, alerts, spc categorical, storm reports) to build a one-stop shop for current weather. Could use the existing weather.html page.

## Assumptions

- API credentials are optional server-side environment secrets and are never
  sent to browsers.
- Existing dashboard shell and scrubber ownership remain intact.
- Each phase updates the handoff documentation and is independently reviewable.
- Upstream licensing and attribution are displayed per provider.

## Official References

- [NEXRAD](https://www.ncei.noaa.gov/products/radar/next-generation-weather-radar)
- [Himawari](https://registry.opendata.aws/noaa-himawari/)
- [GOES/GLM](https://www.goes-r.gov/spacesegment/glm.html)
- [Meteosat](https://www.eumetsat.int/our-satellites/meteosat-series)
- [Canadian GeoMet](https://eccc-msc.github.io/open-data/msc-geomet/readme_en/)
- [Australian radar feeds](https://www.bom.gov.au/catalogue/data-feeds.shtml)
- [USGS Water APIs](https://api.waterdata.usgs.gov/)
- [NOAA NWPS API](https://api.water.noaa.gov/nwps/v1/docs/)
