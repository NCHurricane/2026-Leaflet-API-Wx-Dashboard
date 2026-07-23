# Satellite v2 Phase 5 summary

On an isolated pinned GOES-19 MESO1 Channel02 workload rendering z7 and z8,
reusing the rapid worker's two-process pool reduced steady warm p50 from
3514.710 ms to 832.513 ms, a 76.3% improvement. The first reusable-pool sample
was 3413.370 ms because it still includes the one-time Windows process startup;
later frames/jobs reuse those processes.

| two-zoom warm path | p50 ms |
|---|---:|
| Per-call process pool | 3514.710 |
| Reused process pool | 832.513 |

Cached source parsing measured 12.888 ms p50, and the two zoom canvases benefit
from parallel workers, so Phase 5 retains task-per-zoom granularity. The owned
and reusable pool paths produced 40 SHA-256-identical PNGs and the same 75
negative-marker paths. The complete matrix also passed 81/81 golden tiles.

Focused Satellite validation passes 37 tests; the full suite passes 109 tests
plus 42 subtests. Changed Python compiles and `git diff --check` passes. The
only test output is existing Radar colormap deprecation warnings and the
environment's denied `.pytest_cache` write warning.
