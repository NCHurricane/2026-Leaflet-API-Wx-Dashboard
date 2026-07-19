# Phases 25-27 Consolidated Manual Smoke Checklist

Prepared: 2026-07-19

This is the deferred browser gate for the no-intermediate-smoke execution of
Phases 25-27. Run the app from `F:\Python\dashboard_2026`, keep DevTools Console
and Network open, and hard-refresh each route before checking it.

Smoke log:

- 2026-07-19 closure: After the iterative KGSP Radar/Alerts smoke-and-fix cycle,
  the user accepted the Workspace Radar/Alerts slice for now and reported all
  tests passed. Remaining naturally occurring-event observations are non-blocking;
  the next session moves to the deferred standalone Water UI issues.

- 2026-07-19: Initial `/workspace` shell check found unsupported core class names
  and a legacy named-grid-area collision. The header/nav, sidebar status card,
  tab/content spacing, map sizing, and map-overlay timestamp were corrected and
  targeted locally with no console errors. User smoke retest remains pending.
- 2026-07-19: Pre-functionality UX review removed the redundant Live Radar
  checkbox, centered the CONUS preset, pinned a four-region selector, limited
  the warning layer to severe-warning pills, added report type/time pills, and
  split Radar/Warnings/Storm Reports into compact collapsible legends. Targeted
  local interaction checks passed; user smoke remains pending.
- 2026-07-19: Workspace gained the Alerts-style split right card rail. Local
  browser verification confirmed equal-height warning/report sections when both
  layers are enabled, a single remaining section when either is disabled, full
  rail removal/map-space recovery when both are disabled, 671 live report cards,
  and a WIND rail filter reducing the rendered list to its 511 matching reports.
  User visual/functionality smoke remains pending.
- 2026-07-19: Rail follow-up locally verified that Workspace `ALL` rendered all
  328 currently selected active alerts, alert-card navigation respected the
  level-9 zoom cap, and a selected report popup closed on layer-off, remained
  closed after layer-on, and closed on a region change. User smoke remains
  pending.
- 2026-07-19: Workspace auto-update is now visibly enabled at 60 seconds. Local
  browser verification confirmed the checked control renders and toggles off/on.
  Static wiring confirms enabled alerts/reports and selected radar frames are
  refreshed while inactive/static layers are skipped. User observation of a
  naturally arriving new-alert notice remains pending.
- 2026-07-19: New-alert notices are restricted to TOR/SVR/FFW warnings and
  watches, auto-close after 15 seconds, and use `sounds/weather_alert.mp3` once
  per notification burst. The audio route returned HTTP 200 as `audio/mpeg`, and
  a rendered initial load with 361 active alerts produced zero false notices.
  User observation of a naturally arriving qualifying alert remains pending.
- 2026-07-19: Local browser verification confirmed 354 Workspace alert cards
  sorted newest-issued first across mixed time-zone offsets. Radar-site tooltips
  now have a Workspace-only 86%-opaque dark backing, light border/text, and
  shadow; user visual smoke remains pending.
- 2026-07-19: Workspace startup defaults changed to TOR+SVR with `All` off and
  Storm Reports set to a disabled 1-hour window. Local browser verification
  confirmed the pill/ARIA states and a five-alert TOR+SVR initial load.
- 2026-07-19: Local browser verification confirmed alert rail cards open the NWS
  draggable detail panel and both report rail cards and report markers open its
  LSR mode with location, time, magnitude, WFO, source, and remarks. No Leaflet
  report popup remained. Alert polygon detail uses the same wired engine callback;
  user click/drag visual smoke remains pending.
- 2026-07-19: Rendered polygon-click verification opened the Severe Thunderstorm
  Warning detail at exactly Z9; the polygon path now shares the card/notice cap.
- 2026-07-19: Workspace overlay focus CSS now suppresses pointer-click rings on
  Leaflet vectors/markers while retaining cyan keyboard `:focus-visible` rings.
  Focused boundary tests pass; user visual smoke remains pending.
- 2026-07-19: LSR markers now bind a compact high-contrast hover tooltip with
  report type, optional magnitude, and location while retaining click-to-detail.
  A follow-up fixes its Workspace width at a responsive 260 px so content no
  longer collapses into one-word lines. Static/automated validation passed;
  user hover smoke remains pending.
- 2026-07-19: KGSP testing with an active SVR exposed four radar-composition
  gaps. The value inspector now uses the accepted single-request/pending-sample
  queue, NST tracks regain their distinct symbols and styled tooltips plus a
  separate legend, Projected Arrival draw clicks bypass alert detail/zoom, and
  loaded radar history now appears in the shared scrubber. Static checks and 11
  focused tests passed; user browser retest remains pending.
- 2026-07-19: Workspace Layers now uses collapsible Radar, Active Alerts, and
  Storm Reports groups plus placeholders for SPC, Satellite, RTMA, MRMS, WPC,
  and Water. Radar starts open; every other group starts collapsed.
- 2026-07-19: Removed the empty Elevation selector from Workspace. Workspace now
  requests the explicit 0.5-degree Level II default; elevation choice remains on
  standalone Radar, which also starts at 0.5 degrees.
- 2026-07-19: Added a default-on Radar header switch and Level 2/Level 3 pills
  below Site. Product is API-catalog-filtered by level, with Level 3 disabled for
  non-CONUS sites. The level pills and Product field remain hidden until a site
  is selected.
- 2026-07-19: Moved Projected Arrival and Radar Speed Estimator below the Active
  Alerts filter pills and removed the redundant Tools tab. This intermediate
  layout was superseded by the separate conditional Projected Arrival group.
- 2026-07-19: Removed both tools' inline help paragraphs to reduce panel height;
  the exact guidance is retained in the superfile for a future FAQ/Wiki.
- 2026-07-19: Removed the Radar Speed Estimator UI, fixed-loop calculation,
  map-click draw mode, autofill wiring, stale styles, and tests. Its assumed
  four-frame, five-minute loop no longer matches the current radar frame model.
  Projected Arrival and its manual Speed Override remain unchanged.
- 2026-07-19: Moved Projected Arrival into its own collapsible group directly
  below Active Alerts. It is hidden until an alert polygon, warning card, or
  new-alert notice is selected, opens automatically on selection, and hides on
  Alerts disable or region change.
- 2026-07-19: Wired the shared map Home control to a full Workspace context
  reset. It clears selected-site radar frames/scrubber and Projected Arrival,
  restores Level 2 Base Reflectivity, resets Region to CONUS, and retains layer
  visibility preferences before the map refits the default view.

## Workspace and asset boundary

- Open `/workspace`; confirm the fixed header, Layers/Map sidebar, map,
  sidebar data-status card, map-overlay timestamp, and Refresh footer render
  without overlap.
- Open `/weather.html`; confirm it redirects to `/workspace`.
- In Network, confirm Leaflet loads from `/frontend/lib/leaflet/` and no request
  goes to `unpkg.com` or the removed `js/weather.js`, `weather.html`, or
  `css/dashboard.css` assets.
- Confirm the Home navigation item on product pages opens `/workspace`.
- Confirm there are no uncaught console errors during startup or tab changes.

## Workspace Alerts and Radar

- Confirm TOR and SVR are selected initially while `All`, FFW, and SMW are off.
  Confirm the four severe pills support any combination and selecting `All`
  clears that combination and shows every active NWS alert category.
  Confirm the map, count, and alert legend update. Hover long alert polygons
  and confirm the tooltip wraps within a bounded card.
- Confirm Storm Reports type pills and 1/6/12/24-hour pills update markers,
  count, and the separate Storm Reports legend. Confirm report markers and
  legend rows use the same category icons as standalone Alerts. Storm Reports
  should be off on initial page load with 1 hour selected as its time window.
- Use the header switches to turn Active Warnings and Storm Reports off and on
  independently; confirm the layer, count, legend, and associated pills follow
  the switch while each `All` pill continues to mean all types.
- Confirm the right card rail is visible for Active Warnings on initial load and
  its warning cards/counts/ALL-TOR-SVR-FFW-SMW filters match standalone Alerts.
  Enable Storm Reports and confirm the rail splits into warning and report
  sections; disable either layer and confirm only its section disappears, then
  disable both and confirm the entire rail closes and the map reclaims the space.
  Confirm clicking a warning card selects/zooms the alert for Workspace tools,
  with zoom capped at level 9. Confirm rail `ALL` lists all active alerts rather
  than only the four severe-warning types. Confirm clicking a report card zooms
  to and opens that report marker, then verify its popup closes and does not
  return after disabling/re-enabling reports or changing region/radar context.
- Expand/collapse the Radar, Active Warnings, and Storm Reports legends; confirm
  they remain compact and do not obscure the center of the map.
- Select a radar site by dropdown and by map marker; confirm selection loads
  live radar and the blank site clears it. Test Level II and Level III products,
  elevation selection, Radar Sites, Storm Tracks, and Value Inspector. Storm
  Tracks and Value Inspector should remain hidden without a selected site and
  hide/reset after region changes or returning Home.
- With radar loaded and Projected Arrival visible, press Home. Confirm radar and
  the scrubber clear, Site returns to `Select site`, Level 2 Base Reflectivity is
  restored, Projected Arrival disappears, Region reads CONUS, and the default
  CONUS extent is fitted.
- Confirm CONUS is centered. Test CONUS, Alaska, Hawaii, and Puerto Rico, then
  change basemap and toggle graticule, states, countries, and counties.
- Pan/zoom and press Refresh Active Layers; confirm alerts refetch for the new
  viewport and the selected radar context remains coherent.
- Confirm Auto-Update (60 sec) is enabled initially and can be disabled/re-enabled.
  Leave it enabled across a refresh boundary and confirm enabled Alerts/Storm
  Reports update; with a radar site selected, confirm its frames update without
  resetting the chosen site/product/elevation. When a genuinely new selected
  TOR/SVR/FFW warning or watch arrives, confirm a colored `NEW` notice appears
  over the map, `/sounds/weather_alert.mp3` plays once for the notification
  burst, the notice dismisses manually or after about 15 seconds, and opening it
  selects the alert at no more than zoom level 9. Confirm SMW/other alert types,
  initial load, and region/filter changes do not produce notices or sound.
- Confirm alert cards are ordered newest-issued first rather than next-expiring.
  Hover radar-site markers over both dark land and bright alert/radar polygons;
  confirm the translucent tooltip remains readable and its pointer is visible.
- Click an alert polygon and an alert rail card; confirm both open the draggable
  NWS detail panel and its close/Escape/drag behavior works. Click an LSR marker
  and report rail card; confirm both open the same panel in Local Storm Report
  mode with location, reported time, magnitude, WFO, source, and remarks, without
  also opening a Leaflet popup. Confirm report layer/filter/time/region changes
  close an open LSR detail.
- Click alert polygons and map markers with the pointer; confirm no white focus
  rectangle remains. Tab to focusable map overlays and confirm the cyan keyboard
  focus indicator still appears only during keyboard navigation.
- Hover multiple LSR icons and confirm a compact tooltip shows report type,
  magnitude when available, and location; move away and confirm it closes, then
  click the icon and confirm the full LSR detail panel still opens.

## Projected Arrival Tool

- Confirm the Projected Arrival group is absent before selecting an alert.
- Expand Active Alerts, click an active alert polygon, choose Start Line, draw at
  least two points in the storm-motion direction, and choose Finish Line.
- Confirm selection reveals and expands the separate Projected Arrival group and
  identifies the chosen alert. Disable Alerts or change region and confirm the
  group and existing projection are cleared and hidden.
- Confirm the projected corridor/intervals appear. Drag the projection handle;
  hold Shift to test the bounded pivot and confirm projected place-arrival rows
  update. Test the city/town/village/hamlet filters and close control.
- Enter a Speed Override and repeat the projection; clear it and confirm the
  motion-vector fallback is used when the selected alert supplies valid motion.

## Phase 25 Alerts page

- Open `/alerts`; verify default TOR/SVR/FFW/SMW severe warnings, 60-second
  auto-update, pulse toggle, category/subtype filtering, 1-hour and longer LSR
  windows, LSR rail filters, warning detail, threat chips, and official NWS
  links.
- Confirm Alerts archive remains hidden and Projected Arrival appears only in
  `/workspace`.

## Phase 26 Tropical and Water pages

- Open `/tropical`; test World/AL/EP/CP basin changes, active storms, outlooks,
  archive season/storm selection, advisory and best-track scrubbers, inspector
  accordions/layer pills, products/graphics, floater controls, refresh, and
  map overlays/basemap.
- Open `/water`; verify River/Coastal/NDBC loading, viewport reload, flood-stage
  pills, marker/legend colors, river stage gauge, CO-OPS details, NDBC grouped
  readings, Refresh/Clear, overlays, and basemap.

## Regression sweep

- Hard-refresh `/surface`, `/spc`, `/wpc`, `/mrms`, `/rtma`, `/satellite`,
  `/radar`, `/drought`, `/alerts`, `/tropical`, and `/water`.
- On each page, load one representative product, change one map/style control,
  and confirm the legend/status surface updates with no console errors.
- Confirm `/radar.html` compatibility behavior remains unchanged.

Record pass/fail details in `docs/dashboard-change-and-enhancement-superfile.md`.
The current repository-wide automated baseline has five unrelated Radar
expectation failures; do not treat those as Phase 25-27 browser failures unless
runtime behavior exposes the same issue.
