# Radar render optimization Phase 3

Phase 3 gives flat Level II data one site/volume-owned source spool and renders
the configured product set through a bounded decoded-volume consumer seam.
Scheduled flat-volume runs list/download once per site and decode each source
frame once. Product caches, fields, sweeps, palettes, units, SRV motion
variants, failure state, and retention remain independent. Chunk-backed Level
II and every Level III source path are unchanged.

All four optional warmers remained disabled during capture. Raw JSONL and
rendered files remain under ignored `cache/radar/.bench/`.

## Source identity and storage

The pre-change local KMHX snapshot contained 12 source names common to the
product-owned `REF` and `VEL` directories. All 12 SHA-256 comparisons were
identical, representing 54,026,519 duplicate logical bytes. The source spool is
now `radar_level2_downloads/_VOLUME/<site>`; legacy product directories remain
readable for existing value-inspector frames and expire through the existing
bounded Level II retention policy.

## Decode and wall-time result

Five fresh-process samples rendered all seven configured KGSP Level II products
from the same pinned 6,487,723-byte volume.

| mode | decodes/run | wall p50 | wall p95 | peak RSS p95 | failures |
|---|---:|---:|---:|---:|---:|
| separate product control | 7 | 26.270 s | 26.516 s | 1,302.29 MiB | 0 |
| shared decoded-volume batch | 1 | 16.522 s | 16.558 s | 1,857.16 MiB | 0 |

The shared path removes six decodes per frame and improves wall p50/p95 by
37.1%/37.6%. Peak RSS is higher than the serial control but remains below the
existing Phase 2 backfill p95 envelope of about 2.50 GiB.

## Correctness gates

- All eight Phase 0 golden rows pass byte-identical PNG and decoded-RGBA
  comparison with unchanged metadata.
- The shared batch output for KGSP L2 REF, VEL, SRV, and ZDR matches the four
  corresponding golden PNG SHA-256 values.
- Each product consumer restores its source field after rendering, preventing
  Velocity scaling/masking from contaminating SRV or another consumer.
- Product failures are isolated; a failed field/render does not block sibling
  products from the same decoded volume.
- The focused Radar gate passes 56 tests plus 42 subtests. Full pytest passes
  275 tests plus 42 subtests; its only failure is the pre-existing Workspace
  assertion against removed `WORKSPACE_REGION_BOUNDS`.
- Ruff, Python compilation, JSON parsing, and `git diff --check` pass.
