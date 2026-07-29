# Radar benchmark phase4-backfill-12

- Target: `KGSP/L3_N0B`
- Scenario: `backfill-12`
- Samples: 5

| metric | p50 ms | p95 ms | samples |
|---|---:|---:|---:|
| `download_check_ms` | 0.039 | 0.044 | 5 |
| `list_ms` | 0.179 | 0.204 | 5 |
| `pool_startup_ms` | 18.238 | 25.520 | 5 |
| `pool_warm_ms` | 456.629 | 472.690 | 5 |
| `total_ms` | 7572.654 | 7705.209 | 5 |

| working set | p50 MiB | p95 MiB | samples |
|---|---:|---:|---:|
| `working_set_before` | 205.543 | 205.585 | 5 |
| `working_set_peak` | 2468.359 | 2556.966 | 5 |
| `working_set_after` | 251.805 | 251.852 | 5 |
