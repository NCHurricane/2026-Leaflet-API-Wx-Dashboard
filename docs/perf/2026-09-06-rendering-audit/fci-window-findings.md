# M12 native-window prototype — 2026-09-06

This preserves the prototype checkpoint. Subsequent owner-authorized
[application integration](fci-integration-findings.md) is now ready for smoke;
use that record for current runtime status and integrated timing results.

The isolated prototype preserves the full-native reference in the selected cases
and shows enough benefit to recommend a bounded application integration slice.
It is not imported by the dashboard. Runtime settings, rendering code, Workspace
ordering and browser behavior are unchanged. No additional sources were fetched.

## Equal-quality result

All ten 768-square canvas checks passed with **zero RGB difference and zero alpha
mismatches** against the existing full-native calibration/warp output. Cases cover
visible interior clouds, an equatorial source-chunk boundary, the east limb,
visible z4–7, scalar IR z5, NighttimeMicrophysics z5, and a mixed-grid DaySnowFog
diagnostic at z7. DaySnowFog exercises backend channel composition; it is not an
exposed M12 UI product. These are one-frame, selected-footprint checks, not all
locations, independent radiometric truth, or browser acceptance.

The [quality report](fci-window-quality-v2.json) preserves paths to the ignored
PNGs. The [summary](fci-window-summary.json) records output hashes, revalidates all
40 pinned source hashes, and confirms that all four benchmark cases produced
identical whole-canvas RGBA across controls, prototype revisions and repetitions.
The chunk-boundary candidate was also visually inspected. Native-source grid
spacing and calibration remain the reference; no stride is used in the prototype.

## Timing and resource tradeoffs

These are three-sample median seconds, including source loading, the same 3x3
canvas and normal tile publication. Fresh means a new process with local source
files; the operating system file cache was not cleared. Peak RSS is the maximum
20-ms sampled resident memory across the three repetitions, in MiB.

| Case/state | Full native (s) | Revised window (s) | Wall reduction | Full/window peak RSS (MiB) |
| --- | ---: | ---: | ---: | ---: |
| Visible z8, fresh | 4.147 | 2.074 | 50.0% | 1,200 / 275 |
| Visible z8, decoded sources retained | 0.220 | 0.108 | 50.9% | 1,205 / 269 |
| Visible z4, fresh | 4.530 | 3.856 | 14.9% | 1,243 / 559 |
| Night composite z5, fresh | 4.167 | 3.290 | 21.0% | 938 / 326 |
| Night composite z5, decoded sources retained | 0.474 | 0.392 | 17.1% | 748 / 330 |
| Limb visible z8, fresh/full-native fallback | 4.200 | 4.205 | -0.1% | 1,199 / 1,206 |

Fresh CPU medians fall from 4.000 to 2.000 seconds for visible z8, 4.125 to
3.109 for the composite, and 4.406 to 3.812 for visible z4. Limb CPU remains
4.094 seconds. Maximum sampled private commit falls from 2,636 to 1,712 MiB
for fresh visible z8 and 2,392 to 1,760 MiB for the composite; the limb remains
about 2,642 MiB. Private commit and resident memory are different measurements.
Neither these totals nor the cache limit establishes an 8–16-GB-host acceptance.

There is an I/O tradeoff: reported process read bytes for the fresh composite
increase from 283 to 321 MB, and visible z4 from 311 to 367 MB. Indexing all
40 files and then reopening selected strips has a cost even when less radiance
is calibrated. Visible z8 read bytes fall from 311 to 232 MB. These counters
include cached reads/metadata and publication validation, not physical disk
traffic. Fewer selected array bytes must not be advertised as equal disk savings.

The first revision regressed the composite by 6.0% and the limb by 44.6%.
Its [original source](fci_window_prototype_v1.py) and [paired pilot](fci-pilot-batch.json)
are preserved. The revised loader opens selected strips once for all requested
physical channels, caches small window plans, and takes the full-native limb
fallback before indexing every file. The [follow-up](fci-pilot-v2-batch.json)
contains revised candidates only, compared with the earlier controls. It is a
targeted diagnostic follow-up, not a new interleaved control experiment. Ambient
desktop activity was uncontrolled; three samples do not establish p95 or rule
out small regressions. In these cells there is no remaining wall/CPU/RSS
regression above the proposed 5% threshold, while the I/O increases remain explicit.

The pilot and follow-up contain 54 timed samples and 212.30 seconds of child
execution including imports. Combined with the original 48-sample baseline,
**102 of the 108 timed-sample allowance** have been used; six remain. Quality
diagnostics are separately recorded, without treating them as performance
repetitions. Total isolated audit scratch is now 1,473,952,164 bytes (1.37 GiB).
The 36 prototype children completed without exceptions. At the limb, all variants
publish six PNGs and the same three negative markers for fully transparent
eastern tiles; an `invalid` publication status there is the existing empty-tile
contract. Other cases publish all nine PNGs.

## What the prototype does

[`fci_window_prototype.py`](fci_window_prototype.py) uses actual FCI headers to
check contiguous strip coverage and native dimensions. It inverse-projects all
destination pixel vertices for a canvas of at most 3x3 tiles, adds a sampling
halo, and intersects that native window with source strips. Only those radiance
slices are converted/calibrated. The original affine transform is translated to
the window origin. Native reads retain the existing process-wide NetCDF lock.
Ambiguous/non-finite geometry takes the existing full-native loader, with the
11136 limit specific to this pinned normal FDHSI fixture.

For the visible z8 interior, the selected 480x473 float32 array is 908,160 bytes,
versus 496,041,984 bytes for the full native grid, and intersects 2 of 40 strips.
The z5 night composite retains 39,983,856 bytes across three native channels.
A 64-MiB LRU accounts for actual retained arrays, deduplicating aliases. Visible
z4's 133-MB window and the full-native limb exceed this cache and are not retained.
Warm results apply only to the two small-window cases; large-window/fallback
repeated access may decode again. The cache is not an admission or process limit.

The [invariant checks](fci-window-invariants.json) verify 2-MiB LRU eviction and
reload, exact source values after eviction, validity of caller-held references,
an eight-entry window-plan limit, shared Channel13/14 allocation, and a zero
cache limit. Caller-held arrays remain allocated after eviction and must be
included separately in future admission accounting. Immutable pinned files and
serial caller ownership are assumptions here, not an implemented production
invalidation/concurrency policy.

Storage chunking limits the saving: inspected radiance chunks span 300 rows by
11,136 columns, so selecting a few columns still decompresses a full-width
storage chunk. See the primary [netCDF compression explanation](https://www.unidata.ucar.edu/blogs/developer/entry/netcdf_compression).
The halo is validated only in the recorded cases. GDAL documents automatic
per-chunk resampling scale choices and nonlinear source-window limitations;
crop equivalence must continue to be tested rather than assumed. See
[GDAL warp options](https://gdal.org/en/stable/doxygen/structGDALWarpOptions.html).

## Limb evidence and integration boundary

An independent ellipsoid surface-normal/line-of-sight calculation, using the
source header's Earth axes and satellite height, marks 552,706 destination pixel
centres geometrically visible in the limb canvas. Both old strided and native
outputs have **zero opaque pixels outside that visible ellipsoid**. They leave
218,246 and 245,693 visible pixels transparent respectively. This rules out an
outside-Earth opacity leak in this footprint; it does not decide the correct
source-validity mask inside the limb, validate all coast/overlay alignment, or
resolve the previously measured 47,697 old/native alpha differences. Formula,
parameters and counts are in the invariant report. The prototype preserves the
native mask exactly and uses full-native data for this footprint.

The recommended application slice is M12 source access plus honest memory
accounting, retaining PNG/calibration/warp and existing foreground ownership:

1. Integrate frame/channel/window planning with source identity and invalidation,
   reuse metadata safely, and bound cache entries by bytes. The audit loader's
   declared channel subset and frozen file signatures are insufficient as a
   general multi-product service cache.
2. Account for native dimensions, storage-decode/calibration temporaries, caller
   references, output/GDAL buffers and worker processes before admission. Test
   the full-native fallback under conservative budgets. Reduce concurrency,
   prefetch and residency under pressure while preserving final quality.
3. Keep cache identity distinct from old decimated tile/source results; preserve
   frame/generation cancellation, serialized native I/O, atomic publication and
   negative-tile behavior. Exercise repeated pan/zoom and channel/frame changes,
   especially large windows that cannot stay cached.
4. Add focused native/window, failure, cache and admission regressions, then
   validate standalone/Workspace presentation on the documented browser matrix
   and actual secondary hardware. Owner OBS/browser/document checks remain a
   separate acceptance condition. Retain a quality-preserving fallback and do
   not infer all-channel or all-platform acceptance from this one frame.

The prototype is sufficient to select that slice for review. It does not justify
a cap-only production change, global default-budget increase, or a claim that
the full rendering audit is complete. The five missing timing cells, fixed
history sequences, Radar/MRMS/RTMA alternatives and real browser/hardware
measurements remain separate work. A further timing campaign needs a recorded
allocation; do not quietly restart the 108-sample allowance.

## Reproduction

The quality and timing collectors preserve existing run IDs and refuse to
overwrite them. Original evidence remains the authority; a new run needs a
separately recorded bound and ID. All rendering uses pinned local source paths
and a Python audit hook rejecting network connections.

- `check_fci_window.py --run-id fci-window-quality-v1 --revision v1` generated the
  first three checks; `--run-id fci-window-quality-transitions-v1 --revision v1
  --all-cases --start-index 3` generated the other seven.
- `check_fci_window.py --run-id fci-window-quality-v2 --all-cases --revision v2`
  checked the revision using preserved full-native references. Older JSONs
  predate the explicit revision argument; pilot manifests and preserved source
  SHA256 values tie the revisions to their measurements.
- `bench_fci_window.py` is the original 36-sample interleaved full/window pilot;
  `bench_fci_window.py --followup-v2` is the 18-sample candidate follow-up.
- `check_fci_invariants.py` generated the cache/geometry report.
- `summarize_fci_window.py` recalculates the summary, checks artifact/publication
  parity and revalidates source hashes without rendering or fetching inputs.

Scoped Ruff checks passed for all six new prototype/check/benchmark/summary
Python files, and all six compile. Fifty local links across the updated active
and evidence documents resolve; tracked diff whitespace checks passed. These are
audit-script/document validations; the application test suite and browser/owner
smoke were not rerun because application code was not changed.
