# Satellite v2 Phase 0 baseline

Phase 0 captured the unoptimized post-GeoColor/opacity renderer before any
latency changes. The benchmark used the nine-row matrix from
`docs/archive/satellite-render-optimization-plan.md`, all three scenarios, five samples
per scenario, and one 3x3 live-supertile footprint per sample.

- Results: `baseline-summary.md` plus the consolidated 135-record
  `baseline-results.jsonl`; each record retains its run ID, scenario, stage
  timings, and tile context.
- Reproducibility: `matrix-manifest.json` records the environment, dirty files,
  nine pinned frame keys, and every run definition.
- Worker state: the Satellite rapid and Meteosat prefetch scheduled tasks were
  not registered, so no scheduled Satellite work competed with the run.
- Sources: all cold/warm samples used disk-resident sources. Network access was
  used only before the baseline to stage the missing GOES Full Disk and
  Himawari Full Disk/Japan source bundles.
- Golden gate: 81 scratch PNGs (nine rows x nine tiles) were captured from the
  cold runs and matched byte-for-byte after the warm runs. Goldens remain under
  ignored `cache/satellite/.bench/` storage and are not committed.
- Bench-disabled spot check: an uninstrumented MESO1 render matched its captured
  golden block byte-for-byte and created no benchmark record.
- Validation: 21 focused Satellite tests and the full 93-test / 42-subtest suite
  pass.

Baseline headline p50s:

| target | cold parse | warm parse | hit |
|---|---:|---:|---:|
| GOES CONUS Channel13 | 1079.820 ms | 165.616 ms | 1.409 ms |
| GOES CONUS GeoColor | 6494.148 ms | 1181.766 ms | 2.642 ms |
| Himawari Full Disk Channel13 | 2779.930 ms | 556.315 ms | 2.059 ms |
| Meteosat-12 NighttimeMicrophysics | 8771.128 ms | 1338.319 ms | 2.678 ms |

The per-stage data confirms the planned targets: GeoColor cold parse is
5378.747 ms p50; Meteosat-12 NighttimeMicrophysics cold parse is 7408.230 ms
p50; cache-hit validation ranges from 1.349 to 2.603 ms p50 across the matrix.

Phase 1 starts with the isolated `_NETCDF_CACHE` LRU correctness fix, followed
by hit-path validation and the renderer meshgrid gate. Every change remains
gated on the scratch goldens and affected baseline rows.
