# Radar render optimization Phase 4 evidence

Phase 4 remains PNG-only and behavior-neutral. All four optional warmers were
disabled during benchmark and golden capture.

## Results

| Gate | Baseline p50/p95 | Phase 4 p50/p95 | Result |
|---|---:|---:|---|
| KGSP L3 N0B no-op worker, 10 in-process samples | 8.602/13.490 ms | 7.687/11.890 ms | 10.6%/11.9% lower; 10/10 reused persisted discovery with zero rescans |
| KGSP L3 N0B backfill-12, 5 fresh processes | 7,988.633/8,271.204 ms | 7,572.654/7,705.209 ms | 5.2%/6.8% lower; 12 frames and one retained-pool batch in every sample |
| Eight-row render-one finalization | 6.930 ms median of baseline row p50s | 0.860 ms median | 87.6% lower |

All eight Phase 0 golden comparisons passed byte-identically. Phase 4 tests
also prove unchanged-directory reuse, changed/missing-file rediscovery,
interrupted finalization recovery, temporary-file cleanup, immediate PNG
visibility before index persistence, unchanged chronological ordering, and
newest-frame pruning.

Processed-key and frame-index writes remain per-frame. Phase 0 measured them at
only about 0.4-0.8 ms, so batching was not justified against its larger crash
consistency surface.

## Validation

- Focused Radar gate: 63 tests plus 42 subtests passed.
- Full pytest: 282 tests plus 42 subtests passed; only the pre-existing
  Workspace assertion against removed `WORKSPACE_REGION_BOUNDS` failed.
- Ruff and Python compilation passed for the touched Python files.
- No frontend behavior changed. Browser smoke was not required or performed.
