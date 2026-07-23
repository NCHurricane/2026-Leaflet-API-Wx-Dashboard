# Satellite v2 Phase 4 summary

The shared source-raster cache passed the complete nine-row golden matrix:
81/81 PNGs remained byte-identical.

On the pinned Meteosat-12 Full Disk frame, loading Channel13 and then
NighttimeMicrophysics produced four renderer raster references backed by three
unique grids. NighttimeMicrophysics loaded only Channel07 and Channel15; its
Channel13 reference was the exact scalar renderer object and was not reparsed.

| FCI cross-product memory metric | MB |
|---|---:|
| Independent renderer grids | 473.062 |
| Shared unique grids | 354.797 |
| Saved Channel13 grid | 118.266 |

The cache's byte counter matched the 354.797 MB unique-grid total. Focused
Satellite validation passes 33 tests; the full suite passes 105 tests plus 42
subtests. Changed Python compiles and `git diff --check` passes. The only test
output is existing Radar colormap deprecation warnings and the environment's
denied `.pytest_cache` write warning.
