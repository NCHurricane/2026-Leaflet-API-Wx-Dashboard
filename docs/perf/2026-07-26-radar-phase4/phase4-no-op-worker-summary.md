# Radar benchmark phase4-no-op-worker

- Target: `KGSP/L3_N0B`
- Scenario: `no-op-worker`
- Samples: 10

| metric | p50 ms | p95 ms | samples |
|---|---:|---:|---:|
| `download_check_ms` | 0.011 | 0.018 | 10 |
| `list_ms` | 0.063 | 0.067 | 10 |
| `total_ms` | 7.687 | 11.890 | 10 |

| working set | p50 MiB | p95 MiB | samples |
|---|---:|---:|---:|
| `working_set_before` | 219.414 | 238.367 | 10 |
| `working_set_peak` | 1417.305 | 1476.327 | 10 |
| `working_set_after` | 228.898 | 238.393 | 10 |
