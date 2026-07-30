# Radar render optimization Phase 8 Level III evidence

This is the second and final core-product Phase 8 family. It extends the
default-off hybrid WebGL path to `L3_N0B` and `L3_N0G`. PNG remains the
immediate complete loop, authoritative output, and per-frame fallback.

## Artifact and client contract

- Separate default-off switches gate the Level III family and its animation.
- Artifact `v2` retains product-scoped disk, URL, metadata, client-validation,
  pruning, and stale-work identities.
- L3 N0B uses the existing exact one-byte reflectivity encoding. Its
  representative 720-ray by 1,840-gate artifact is 1,328,499 bytes; a
  four-texture window is about 5.07 MiB.
- L3 N0G uses the two-byte velocity encoding and 512-entry palette. Its
  representative 720-ray by 1,200-gate artifact is 1,732,297 bytes; a
  four-texture window is about 6.61 MiB.
- Maximum measured reconstruction error is zero for N0B and 0.001633 mph for
  N0G. Both retain the Phase 7 limits of four resident textures, two forward
  textures before activation, and two concurrent artifact loads.

## Five-sample fresh-process benchmark

The control and candidate used the exact permanent Phase 0 KGSP inputs.

| product | control total p50/p95 | candidate total p50/p95 | regression | artifact p50/p95 | artifact bytes |
|---|---:|---:|---:|---:|---:|
| L3 N0B | 2,254.490 / 2,412.133 ms | 2,215.835 / 2,243.371 ms | −1.71% / −7.00% | 15.336 / 15.571 ms | 1,328,499 |
| L3 N0G | 1,510.356 / 1,521.616 ms | 1,529.814 / 1,556.063 ms | +1.29% / +2.26% | 16.982 / 17.705 ms | 1,732,297 |

Both remain below the approved 5% first-PNG regression ceiling. Control and
candidate PNGs are byte-identical:

- N0B:
  `e48da975dd9babec3e377ffffe92eba573970255cac3bc3adf6d5958964dc8f6`
- N0G:
  `81a81db9374d83330e92fefabfef029ff259ad6ee6ca32102940b36f84b7d203`

## Golden and automated validation

- All eight permanent Phase 0 PNG golden rows pass with every WebGL family
  enabled in scratch runs `phase8-level3-golden-01` through
  `phase8-level3-golden-08`.
- Focused Radar validation passes 85 tests plus 42 subtests.
- Five JavaScript rolling-window and family tests pass.
- Full pytest passes 310 tests plus 42 subtests. Its only two failures are
  pre-existing Workspace assertions against the removed
  `WORKSPACE_REGION_BOUNDS` constant and the replaced watch-only `all` control.
- Python compilation, scoped Ruff, JavaScript syntax, and diff checks pass.
  `workers/radar_live_worker.py` retains its pre-existing module-bootstrap
  Ruff E402 exceptions.

## Browser acceptance

Codex in-app browser validation used ignored, current-time aliases of the
benchmark PNG/artifact pairs because a bounded live provider refresh did not
finish within four minutes. The aliases and both test listeners were removed
after validation.

- `/radar` and `/workspace` passed for both N0B and N0G.
- PNG remained authoritative below the WebGL threshold and while textures
  warmed; WebGL activated only at high zoom.
- Playback advanced through all four frames with four resident textures,
  two-load concurrency, the matching product/frame identity, and PNG opacity
  zero only after activation.
- N0B-to-N0G changes removed the old product identity before N0G activation.
- With the Level III family switches disabled, high-zoom playback remained
  PNG-only with no WebGL canvas on either page.
- Cached active draws observed during acceptance ranged from 0.000 to 3.400 ms.

The L3 N0B/N0G family is closed. Both approved Phase 8 core-product families
are now complete. Other dual-pol, categorical, accumulation, Echo Tops, and
VIL products remain on PNG; all-product conversion, tiles, and PNG retirement
remain outside this plan.
