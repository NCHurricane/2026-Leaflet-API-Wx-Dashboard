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

Status: implemented after explicit approval; user-owned browser acceptance is
pending.

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
- The focused gate passes 68 tests. The full-suite run has 320 passing tests
  plus 42 passing subtests; only the two known stale Workspace assertions
  fail.

Browser acceptance must confirm the ten-product filter and sample Channel 02,
Channel 07 Fire, both water-vapor products, and Channel 14. With playback
active, zoom to z9 and confirm the scrubber continues while new tiles fill.
Channel 02 deserves particular attention because every native source is
roughly 451 MiB and a multi-frame history can require several large downloads.
Do not close Phase 1 or enter Phase 2 until this browser gate passes.

## Phase 2 — GK2A composites

Enter only after the direct channels they require pass. Reuse existing composite
recipes only where AMI spectral mappings are physically valid and prove each
result before UI exposure.

## Phase 3 — GMGSI global mosaic

Treat GMGSI as a separate hourly global mosaic, not as another AMI instrument.
Add its regular lon/lat NetCDF path and four direct products (visible,
shortwave IR, longwave IR, and water vapor) behind an independent platform and
render version. Do not mix GMGSI parsing or cadence into GK2A phases.
