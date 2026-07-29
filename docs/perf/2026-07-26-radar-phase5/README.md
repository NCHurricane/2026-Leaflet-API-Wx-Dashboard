# Radar render optimization Phase 5 evidence

Phase 5 reuses one Matplotlib QuadMesh for same-volume Level II products that
select the same sweep. Geometry, projection, bounds, figure size, DPI, and
sweep remain unchanged; each consumer replaces only the masked field data,
colormap, and configured limits. The cache is bounded to one decoded-volume
consumer call and is closed before the worker returns.

All four optional warmers remained disabled according to the canonical
handoff. The live Task Scheduler query exposed no readable task state. Raw
JSONL and rendered files remain under ignored `cache/radar/.bench/`.

## Measure-first result

The initial encoder and construction candidates were rejected. Direct canvas
PNG output, rasterization, omitted edge colors, and a direct `pcolormesh` path
all passed the representative byte-identical golden but produced no meaningful
fresh-process end-to-end saving.

The same-sweep QuadMesh candidate passed and was promoted. Five fresh-process
samples rendered all seven configured KGSP Level II products from the same
pinned 6,487,723-byte volume:

| mode | wall p50 | wall p95 | peak RSS p95 | failures |
|---|---:|---:|---:|---:|
| Phase 3 one-decode batch | 16.522 s | 16.558 s | 1,857.16 MiB | 0 |
| Phase 5 same-sweep reuse | 11.814 s | 11.995 s | 1,609.20 MiB | 0 |

Phase 5 reduces p50/p95 wall time by 28.5%/27.6% and p95 peak working set by
13.4%. Every run retained one decode, seven rendered products, and zero failed
products.

## Correctness and validation

- All 35 batch PNGs across the five samples match the seven-product Phase 3
  control byte-for-byte: REF, VEL, SRV, SW, ZDR, RHO, and PHI.
- All eight permanent Phase 0 golden rows pass byte-identical PNG,
  decoded-RGBA, and metadata comparison.
- Focused validation passes 64 tests plus 42 subtests.
- Full pytest passes 283 tests plus 42 subtests and retains only the
  pre-existing Workspace assertion against removed
  `WORKSPACE_REGION_BOUNDS`.
- Ruff with the file's existing E402 allowance, Python compilation, JSON
  parsing, and `git diff --check` pass.
- No frontend or API behavior changed. Browser smoke was not required or
  performed.
