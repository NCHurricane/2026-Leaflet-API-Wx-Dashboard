# Meteosat latency overhaul — Phase 2 evidence

Captured 2026-08-24 UTC on the same host and same pinned source frames. The
pre-change runner is an immutable archive of commit `d1451f9`; the post-change
runner is the Phase 2 working tree. The app was idle during the runs.

## Pinned z5 results (p50 ms)

| target | pre cold | post cold | change | pre warm | post warm | change | post hit |
|---|---:|---:|---:|---:|---:|---:|---:|
| Meteosat-12 Channel13 | 3401 | 2915 | -14% | 546 | 179 | -67% | 0.082 |
| Meteosat-12 NighttimeMicrophysics | 5750 | 3856 | -33% | 1423 | 375 | -74% | 0.096 |
| Meteosat-9 Channel13 | 606 | 469 | -23% | 327 | 179 | -45% | 0.090 |

The retained implementation reads FCI chunks contiguously and decimates in
memory. A candidate direct-strided hyperslab read did not move the single-channel
parse stage and increased the pinned three-channel parse p50 from 3445 ms to
4451 ms, so Phase 2c was rejected as required by the plan's measurement gate.

## Pixel comparisons

- Meteosat-12 Channel13 at z7 has no zoom-derived decimation. All nine tiles
  remain within max per-channel delta 2; mean deltas are 0.005–0.033.
- At z5, the intentional decimation changes more pixels. Channel13 tile means
  are 0.067–0.661 with isolated max deltas up to 193;
  NighttimeMicrophysics means are 0.661–1.030 with isolated max deltas up to
  255. These rows are the required owner visual gate, not a SHA gate.
- Meteosat-9 z5 and GOES-19 CONUS z7 show the known shared-canvas effect on thin
  colored reference overlays. Mean tile deltas stay at or below 0.159, while
  a shifted overlay pixel can produce a max delta of 193. Inspection of one
  GOES maximum found unchanged alpha and a grayscale-to-cyan reference-line
  relocation, rather than a broad imagery or transparency change.

## Automated gate

- 63 focused Satellite tests pass.
- 631 repository Python tests plus 42 subtests pass.
- All 48 Node behavior tests pass.
- Repo-wide Ruff, Python compilation, and `git diff --check` pass.

## Owner gate

Owner smoke passed on 2026-08-24 for Meteosat-12 Full Disk Channel13 and
NighttimeMicrophysics at z3, z4, z5, and z7. The requested tile-seam,
coast/reference-line, cloud-detail, current/past-frame, transition, and clean
console checks all passed. Phase 2 is accepted and ready for its independent
commit.
