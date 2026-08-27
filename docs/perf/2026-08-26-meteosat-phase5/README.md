# Meteosat latency Phase 5 evidence

Phase 5 changes only the EUMETSAT acquisition path. It adds complete OpenSearch pagination,
reuses FCI feature metadata between catalog listing and download lookup, adds bounded transient
retry/backoff, and raises the FCI download default from two to a hard project ceiling of four.
No render code, pixels, or render version changed.

## Live provider probes

Run on 2026-08-26 against the production EUMETSAT APIs from the owner machine:

| probe | result |
|---|---|
| M11 RSS, 12-hour search | 156 unique features, two requests, offsets 0 and 100, 4.182 s |
| M12 Channel13, one-hour catalog | five frames, one search request |
| M12 immediate FCI feature lookup | matched the catalog product with zero additional requests |

The paging fields were verified from the live JSON response: `totalResults`, `itemsPerPage`,
`startIndex`, and the zero-based `si` next-page offset.

## Duplicate-search benchmark

Five alternating live samples compared the former catalog-plus-12-hour-search behavior with
the Phase 5 carried-feature path. Every sample matched the requested product.

| scenario | requests per sample | p50 | p95 |
|---|---:|---:|---:|
| duplicate-search baseline | 2 | 3.871 s | 4.537 s |
| Phase 5 feature reuse | 1 | 1.341 s | 1.505 s |

Phase 5 halves the request count and improves observed p50/p95 by 65.4%/66.8% in this bounded
sample. These are upstream search timings, not render timings.

## Validation

- Focused provider/Satellite gate: 117 Python tests passed.
- Satellite animator gate: 8 tests passed.
- Full Python gate: 662 tests plus 42 subtests passed.
- Full Node gate: 54 tests passed.
- Repo-wide Ruff and `git diff --check` passed.
- Live pagination and feature-reuse probes passed.

Render goldens and a pixel comparison were not repeated because this phase does not reach the
decode, render, tile, frontend, or render-version paths. The restarted owner smoke passed a
newly available uncached M12 frame, a five-frame catalog, responsive scrubbing, and clean
terminal/console checks. Phase 5 is accepted.
