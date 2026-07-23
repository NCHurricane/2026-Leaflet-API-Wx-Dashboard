# Satellite v2 Phase 2 summary

Five-repeat response-first cold-path results for the three headline rows:

| target | Phase 0 p50 ms | Phase 2 p50 ms | reduction |
|---|---:|---:|---:|
| GOES CONUS GeoColor | 6494.148 | 5721.277 | 11.9% |
| Himawari Full Disk Channel13 | 2779.930 | 2392.322 | 13.9% |
| Meteosat-12 Nighttime Microphysics | 8771.128 | 7462.566 | 14.9% |

Source parsing still dominates these cold requests; Phase 2 removes the eight
neighbor warps from response latency without changing their output. A live
full-matrix exercise returned each requested tile first, settled all neighbors
within 0.5 seconds on this machine, and matched all 81 Phase 0 golden PNGs.

The single-canvas proposal failed its first golden gate and was not retained.
The accepted fallback adds per-path in-flight deduplication, asynchronous
neighbor submission, explicit partial/asynchronous supertile stats, and bench
support for `--respond-first --settle-ms`.

Validation: 15 focused tests passed; full pytest passed 100 tests plus 42
subtests; Python compilation and scoped `git diff --check` passed. Browser
smoke is not required for this backend-only phase.

