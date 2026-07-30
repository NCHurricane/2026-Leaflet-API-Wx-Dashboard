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

Phase 0 browser acceptance has passed. Enter Phase 1 only after explicit
approval. Add direct visible, shortwave IR, water-vapor, and longwave IR
products one calibrated family at a time. Each family needs a live proof
render and product filtering; do not expose unsupported composites.

## Phase 2 — GK2A composites

Enter only after the direct channels they require pass. Reuse existing composite
recipes only where AMI spectral mappings are physically valid and prove each
result before UI exposure.

## Phase 3 — GMGSI global mosaic

Treat GMGSI as a separate hourly global mosaic, not as another AMI instrument.
Add its regular lon/lat NetCDF path and four direct products (visible,
shortwave IR, longwave IR, and water vapor) behind an independent platform and
render version. Do not mix GMGSI parsing or cadence into GK2A phases.
