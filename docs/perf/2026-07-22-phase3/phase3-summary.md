# Satellite v2 Phase 3 summary

Five-repeat response-first cold-path results:

| target | Phase 2 p50 ms | Phase 3 p50 ms | Phase 3 improvement |
|---|---:|---:|---:|
| Himawari Full Disk Channel13 | 2392.322 | 1206.521 | 49.6% |
| Meteosat-12 Nighttime Microphysics | 7462.566 | 4236.806 | 43.2% |

AHI parse p50 fell from 2314.232 to 1120.945 ms. FCI Nighttime
Microphysics parse p50 fell from 7279.744 ms across three independent passes
to 4047.660 ms in one multi-channel pass. The FCI Channel13 scalar control was
2656.927 ms total versus the original 2996.476 ms baseline; it intentionally
retains the single-channel wrapper path.

All nine matrix rows passed warm-render comparison against the Phase 0
goldens: 81/81 PNGs were byte-identical. The AHI change structurally limits
full segment buffer residency to four workers and stitches already-decimated
calibrated strips; a comparable Phase 2 working-set baseline was not captured,
so no numeric memory reduction is claimed.

Focused Satellite tests and Python compilation pass. The repository-wide run
reached 101 passing tests plus 40 passing subtests, but two Radar catalog
subtests failed because concurrent manual Radar work references a missing
`RadarScopeBR.pal`; those unrelated files were not modified by Phase 3.

