# Meteosat latency overhaul — Phase 3 evidence

Captured 2026-08-24 on the application host. Phase 3 changes process-local
admission only; render versions and pixel code are unchanged.

## Admission contract

- `WX_SATELLITE_RENDER_BUDGET_MB` defaults to 16384 MB.
- Reservations use conservative float32 source-grid bytes multiplied by the
  product's unique source channel count.
- Concurrent reservations run while their sum fits the budget.
- A reservation larger than the budget still runs, but only by itself.
- The queue is fair and selection cancellation removes a waiting reservation.
- Radar retains `heavy_render_slot`; Satellite uses its independent byte queue.

## Real-source concurrency and memory probe

Four cached-source renders were started together:

| target | estimate MB | decode ms | render ms |
|---|---:|---:|---:|
| Meteosat-12 Full Disk Channel13 z5 | 64 | 3776 | 186 |
| Meteosat-12 Full Disk NighttimeMicrophysics z5 | 192 | 6727 | 380 |
| Meteosat-9 Full Disk Channel13 z5 | 53 | 264 | 250 |
| GOES-19 CONUS Channel13 z7 | 449 | 1266 | 197 |

- Peak active reservations: 4.
- Peak estimated in flight: 757 MB of 16384 MB.
- Process RSS: 205.9 MB start, 503.6 MB peak, 451.1 MB end.
- Final budget state: 0 active, 0 queued, 0 reserved bytes.

## Pixel and automated gates

- Sequential committed-Phase-2 (`7b2d9a5`) and Phase-3 renders used the exact
  same source files. All nine GOES-19 Channel13 and all nine Meteosat-12
  NighttimeMicrophysics PNG SHA-256 hashes matched.
- 82 focused Radar/Satellite budget tests pass.
- 639 repository Python tests plus 42 subtests pass.
- All 48 Node behavior tests pass.
- Repo-wide Ruff, Python compilation, and `git diff --check` pass.

## Owner gate — passed

After restarting the app on 2026-08-24, Satellite and Radar loaded products in
separate tabs and remained responsive. Satellite scrub-ahead did not freeze or
flash, and the browser console stayed clean. A direct response probe of the
tested Meteosat-9 tile returned `200 image/png`, `X-Satellite-V2-Cache: HIT`,
and `X-Satellite-V2-Estimated-Memory-MB: 0`; zero is expected because the cache
hit required no new render reservation. Phase 3 is accepted and remains
uncommitted pending its independent checkpoint.
