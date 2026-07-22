# Satellite v2 Phase 1 summary

Normal cache-hit validation no longer decodes the whole PNG. Across the nine
matrix rows, `validate_ms` p50 fell from 1.349–2.603 ms to 0.051–0.067 ms,
a 22.4–45.8x improvement.

| target | Phase 0 p50 ms | Phase 1 p50 ms | speedup |
|---|---:|---:|---:|
| GOES CONUS Channel13 | 1.349 | 0.060 | 22.4x |
| GOES CONUS GeoColor | 2.566 | 0.056 | 45.8x |
| GOES Full Disk Channel13 | 2.210 | 0.058 | 38.1x |
| GOES MESO1 Channel02 | 2.051 | 0.056 | 36.6x |
| Himawari Full Disk Channel13 | 1.983 | 0.051 | 38.9x |
| Himawari Japan Channel13 | 1.425 | 0.053 | 26.8x |
| Meteosat-12 Full Disk Channel13 | 1.660 | 0.053 | 31.5x |
| Meteosat-12 Nighttime Microphysics | 2.579 | 0.059 | 43.7x |
| Meteosat-9 Full Disk Channel13 | 1.930 | 0.067 | 28.8x |

The lon/lat gate preserves both `GeoColor` and `GeoColorBlkMar`: the current
ABI GeoColor recipe uses solar geometry for Rayleigh correction, superseding
the plan's earlier assumption that only Black Marble consumed the grid.
Non-geographic composites skip the allocation; Meteosat-12 Nighttime
Microphysics `composite_ms` p50 moved from 13.893 to 12.280 ms (11.6%).

Validation: 81/81 golden PNGs byte-identical; 14 focused tests passed; full
pytest passed 99 tests plus 42 subtests. Python compilation and
`git diff --check` passed. The only test output was existing Radar colormap
deprecation warnings and the environment's denied `.pytest_cache` write.

