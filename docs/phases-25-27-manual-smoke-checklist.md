# Phases 25-27 Consolidated Manual Smoke Checklist

Prepared: 2026-07-19

This is the deferred browser gate for the no-intermediate-smoke execution of
Phases 25-27. Run the app from `F:\Python\dashboard_2026`, keep DevTools Console
and Network open, and hard-refresh each route before checking it.

## Workspace and asset boundary

- Open `/workspace`; confirm the fixed header, Layers/Tools/Map sidebar, map,
  reliability row, and Refresh footer render without overlap.
- Open `/weather.html`; confirm it redirects to `/workspace`.
- In Network, confirm Leaflet loads from `/frontend/lib/leaflet/` and no request
  goes to `unpkg.com` or the removed `js/weather.js`, `weather.html`, or
  `css/dashboard.css` assets.
- Confirm the Home navigation item on product pages opens `/workspace`.
- Confirm there are no uncaught console errors during startup or tab changes.

## Workspace Alerts and Radar

- Confirm Active Warnings and 24-hour Storm Reports load, counts update, alert
  polygons/LSR markers render, and their stacked legends remain readable.
- Toggle Active Warnings and Storm Reports independently; confirm only the
  selected layer clears/reloads.
- Select a radar site by dropdown and by map marker. Enable Live Radar and test
  Level II and Level III products, elevation selection, Radar Sites, Storm
  Tracks, and Value Inspector.
- Change region/basemap and toggle graticule, states, countries, and counties.
- Pan/zoom and press Refresh Active Layers; confirm alerts refetch for the new
  viewport and the selected radar context remains coherent.

## Preserved radar-dependent tools

- Click an active alert polygon, open Tools, choose Start Line, draw at least two
  points in the storm-motion direction, and choose Finish Line.
- Confirm the projected corridor/intervals appear. Drag the projection handle;
  hold Shift to test the bounded pivot and confirm projected place-arrival rows
  update. Test the city/town/village/hamlet filters and close control.
- Enter a Speed Override and repeat the projection; clear it and confirm the
  motion-vector fallback is used when the selected alert supplies valid motion.
- Use Draw Speed Line to mark the same radar feature at the start/end of the
  assumed four-frame, five-minute-step loop. Confirm a knot/km-h estimate is
  shown and auto-fills Speed Override. Clear the estimator and projection.

## Phase 25 Alerts page

- Open `/alerts`; verify default TOR/SVR/FFW/SMW severe warnings, 60-second
  auto-update, pulse toggle, category/subtype filtering, 1-hour and longer LSR
  windows, LSR rail filters, warning detail, threat chips, and official NWS
  links.
- Confirm Alerts archive remains hidden and the Projected Arrival/Radar Speed
  tools appear only in `/workspace`.

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
