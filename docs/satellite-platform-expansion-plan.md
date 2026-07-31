# Satellite Platform Expansion Plan

Prepared 2026-07-29. This is the active plan for the GK2A + GMGSI track.

## Contracts

- Add platforms without changing GOES, Himawari, or Meteosat behavior.
- Keep live on-demand rendering authoritative; do not add scheduled warming in
  this track unless separately approved.
- Give each new source its own render-version namespace and rollback boundary.
- Prove calibration, georeferencing, and a live source before expanding the
  visible product set.
- Treat tests, provider/API probes, direct renders, and browser proof as
  separate evidence.

## Phase 0 — GK2A Channel 13 proof

Status: closed.

- Add anonymous NOAA `noaa-gk2a-pds` discovery/download for 10-minute AMI full
  disk Level 1B frames.
- Add AMI packed-pixel quality masking, file-coefficient IR calibration, and
  native geostationary georeferencing.
- Expose only `GK2A -> Full Disk -> Asia-Pacific -> Channel 13`.
- Keep GK2A live-on-demand only and isolate its tiles under `products-ami1`.

Acceptance:

- Synthetic calibration/georeferencing and provider-dispatch tests pass.
- A current anonymous bucket listing returns Channel 13 frames.
- A real AMI source renders a nonblank, correctly oriented PNG.
- The Satellite page loads GK2A Channel 13, keeps playback continuous while
  new zoom tiles fill, and the focused regression gate preserves existing
  platform contracts.

User-owned browser acceptance passed 2026-07-29. Asia-Pacific Channel 13 and
its full default-zoom history loaded quickly. With playback active, zooming to
z9 did not interrupt the scrubber, and the new z9 frames also loaded quickly.

## Phase 1 — GK2A direct-channel expansion

Status: closed.

- Added calibrated direct visible/near-IR products `Channel01`, `Channel02`,
  `Channel03`, and `Channel05`.
- Added shortwave-IR products `Channel07` and `Channel07Fire`, water-vapor
  products `Channel08RAMSDIS` and `Channel09RAMSDIS`, and longwave-IR
  `Channel14`. Channel 13 remains available from Phase 0.
- Product filtering exposes only those ten physically mapped direct products;
  no GK2A composites are exposed.
- High-resolution AMI inputs are read with bounded grid decimation before
  calibration. The worst-case live Channel 02 proof used a 473,301,589-byte
  source, produced a 7333 x 7333 working raster in 5.538 seconds, rendered the
  proof tile in 0.182 seconds, and peaked at about 735.5 MiB working set.
- Current live sources from every added calibrated family rendered nonblank,
  plausibly oriented proof PNGs.
- The focused gate passes 68 tests. The latest full-suite run has 321 passing
  tests plus 42 passing subtests; the two known stale Workspace assertions and
  one unrelated concurrent shared-border-default assertion fail.

User-owned default-zoom acceptance passed 2026-07-29. The first Channel 02 z8
test exposed two shared animator defects: a fractional Leaflet zoom such as
`7.5` could reach the integer-only tile route as a 422, and retained invisible
frame layers could request historical live tiles during a zoom before the
selected newest frame finished. The correction now snaps/sanitizes Satellite
zooms to integers and detaches inactive pooled layers at zoom start. A focused
correction gate passes 27 tests and JavaScript syntax checks. Codex browser
regression on a 12-frame GOES-19 loop reached z8 with only the selected newest
frame attached, 16 integer-z8 tile requests, and no fractional URLs. The
user-owned GK2A Channel 02 z8/playback re-smoke then passed: no fractional-zoom
422s recurred, the newest frame generated first, and playback continued.
Phase 1 is closed.

## Phase 2 — GK2A composites

**Status:** closed 2026-07-31.

- Exposes only the six existing recipes whose source bands map physically to
  AMI: `GeoColor`, `GeoColorBlkMar`, `TrueColor`, `NaturalColor`,
  `DayCloudPhase`, and `DaySnowFog`.
- Keeps recipes needing unmapped AMI bands hidden, including Fire Temperature,
  Air Mass, Day Land Cloud/Fire, Nighttime Microphysics, Dust, Ash, and SO2.
- Uses the existing multi-channel provider intersection so a composite frame is
  advertised only when every required source band has the same timestamp.
- Restores the existing GeoColor Black Marble recipe by pointing its loader to
  the tracked `BlackMarble_2016_3km_geo.png`; the former `.tif` target never
  existed in repository history.
- Isolates the expanded product set under `products-ami2`; GOES, Himawari, and
  Meteosat render namespaces are unchanged.
- Synthetic AMI render proofs for all six recipes, common-timestamp discovery,
  capability-boundary coverage, JavaScript syntax, and the focused Satellite
  gate pass. No live API or browser claim is made because the listener was not
  running during final validation.

User-owned browser acceptance passed 2026-07-31. All six new products rendered
quickly. GeoColor Black Marble animation passed without flicker or blinking
between frames, and neither the API terminal nor browser console reported
errors. Phase 2 is closed.

## Phase 3 — GMGSI global mosaic

Treat GMGSI as a separate hourly global mosaic, not as another AMI instrument.
Add its regular lon/lat NetCDF path and four direct products (visible,
shortwave IR, longwave IR, and water vapor) behind an independent platform and
render version. Do not mix GMGSI parsing or cadence into GK2A phases.

Implementation status 2026-07-31: complete; user-owned browser acceptance
passed. Phase 3 is closed.

- Adds anonymous hourly discovery/download from `noaa-gmgsi-pds` through a
  separate `aws_gmgsi` provider and exposes only `Channel02`, `Channel07`,
  `Channel09RAMSDIS`, and `Channel13` on the `gmgsi/GLOBAL` platform path.
- Adds a dedicated NetCDF loader for the 4,999 x 3,000 global grid. It sorts the
  International Date Line wrap, derives the regular Web Mercator affine from
  the published lon/lat coordinates, masks nonzero `dqf`, scales visible
  display counts to 0-1, and converts the operational IR/WV mode-A counts to
  Kelvin.
- Isolates tiles under `products-gmgsi1`; no GK2A, GOES, Himawari, or Meteosat
  render namespace or cadence changes.
- A current live provider/download/render proof passed for all four products at
  `20260731T200000Z`; object sizes were 7,293,164 bytes (visible), 7,399,384
  bytes (shortwave IR), 3,451,446 bytes (water vapor), and 7,374,067 bytes
  (longwave IR). Each proof tile was nonblank and visually inspected.
- Ruff, Python compilation, JavaScript syntax, and the 63-test focused
  Satellite gate pass. The full suite has 336 passing tests plus 42 passing
  subtests. Its three stable failures remain the unrelated shared-border
  default and two stale Workspace assertions; one coordinator timing failure
  from the full run passed immediately in isolation. No API/browser claim is
  made.

The first user-owned page acceptance on 2026-07-31 confirmed that all four
current frames render, but exposed a catalog-budget defect: the hourly Global
path capped a one-hour request at one frame, so the scrubber had no animation
loop. The correction includes the frame at the start of the lookback interval
(`hours + 1`), giving the default one-hour selection two frames while retaining
the same bounded hourly cadence. `satellite-page.js?v=20260731f` carries the
cachebuster. A live corrected-window probe returned chronological 19Z and 20Z
frames for all four products. The corrected user-owned re-smoke generated and
played a three-hour Channel 13 animation. Because all four products had already
rendered their current frames and use the same GMGSI catalog/playback path, the
user accepted that representative animation result without separately looping
Channels 02, 07, and 09. GMGSI animation acceptance passed and Phase 3 is
closed.
