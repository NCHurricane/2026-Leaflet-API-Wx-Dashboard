# M12 first-frame rendering correction

The owner authorized correcting the 2–3-minute first-frame problem before
continuing the rendering plan. The [first smoke evidence](owner-smoke-first-frame.md)
separates the source-file completion interval from repeated native rendering.

This correction removes repeated whole-grid reads for limb/off-disk tiles. It
keeps the native source samples, output palette/alpha, individual browser tile
requests, foreground ownership, adaptive byte limits and existing PNG cache
identity. No source download, server restart, browser automation or warmer run
is part of this offline work.

Geometry uses interval bounds on the continuous ellipsoidal footprint. In
Earth-radius units the visibility condition reduces to `R*X >= 1`; the bounds
enclose both geos sweep-axis projection forms. This is derived from the
[PROJ geostationary implementation](https://raw.githubusercontent.com/OSGeo/PROJ/master/src/projections/geos.cpp).
Wholly off-disk rectangles skip radiance reads. Partial limbs use conservative
native windows with extra warp-kernel padding. Invalid corners alone never
justify an empty tile; a world canvas can surround the entire visible disk.

Validation allocation for this explicitly requested correction: at most **two
timed viewport runs** (one frozen pre-correction control and one candidate),
**240 seconds combined child execution**, **6 GiB sampled child RSS**, at least
**4 GiB host available memory**, **2 GiB new scratch**, and **zero downloads**.
Use the owner's 40 individual z4 tiles in observed completion order, with
`render_neighbors=false`, pinned local sources and separate output directories.
This is a bounded regression diagnosis, not repeated performance acceptance.
The previous **108/108** samples remain consumed and preserved. Quality/reference
checks and focused automated tests are separately identified, not extra timing
repetitions. Stop on mismatch or resource-bound failure and inspect before retry.

Success requires exact full-native RGBA for all 40 tiles and existing ten
quality cases, no radiance reads for the five proven empty tiles, no whole-grid
fallback for the five partially visible limb tiles, materially less elapsed
time/memory in this local-source viewport, and passing ownership, invalidation,
memory-pressure and publication checks. Fresh-source acquisition and actual
browser/OBS responsiveness remain separate owner-smoke observations.

## Results

The correction is implemented in `satellite_v2/fci_windows.py` with regression
coverage in `tests/test_fci_windows.py`. The [final viewport quality check](fci-limb-viewport-quality-final.json)
compares all 40 normal single-tile service publications against independently
decoded full-native references for the exact 23:30Z owner frame. All match whole
RGBA, including transparent RGB bytes, with 35 PNGs and five negative markers.
No tile invokes full-grid loading. The five x12 tiles skip source-array loading
entirely; the five x11 limb tiles use native windows. Normal artifact identity,
palette, PNG publication and single-tile browser requests are retained.

The first quality attempt stopped on invisible RGB under alpha zero: the native
visible palette returned white-transparent pixels, while the initial shortcut
returned black-transparent pixels. The corrected shortcut uses normal product
colorization without radiance decoding or warping. The [failed gate](fci-limb-viewport-quality.json)
is preserved; no timing pair started until exact quality passed. The [ten-case
final integration check](fci-limb-correction-quality-final.json) also passes all
prior whole-native references and both service publication/cache-reuse cases.

The [bounded pair ledger](fci-limb-viewport-pair.json) records one fresh process
for each variant using the same isolated source copy and observed tile completion
order. The control substitutes the frozen pre-correction `Frame.plan`; all other
runtime code is shared, and the newly added empty-output branch is unreachable
under that plan. Runtime/control hashes are recorded in both result files.

| Local-source 40-tile workload | [Before](fci-limb-viewport-control.json) | [Corrected](fci-limb-viewport-candidate.json) |
| --- | ---: | ---: |
| Elapsed render/publication/check time | 56.969 s | 20.522 s |
| Process CPU time | 55.828 s | 19.953 s |
| Sampled peak RSS | 1,502 MiB | 571 MiB |
| Sampled peak private bytes | 2,935 MiB | 2,001 MiB |
| Process read bytes (not physical disk traffic) | 3,781,643,504 | 1,753,295,612 |
| Summed time for the ten x11/x12 tiles | 39.122 s | 2.617 s |
| Remaining 30 tiles, approximately | 17.847 s | 17.905 s |
| Whole-grid loads | 10 | 0 |
| Tiles with no source-array load | 0 | 5 |

Elapsed time fell 64.0% and sampled peak RSS 62.0% in this single diagnostic pair.
Both variants passed exact whole-RGBA checks and wrote identical PNG byte totals.
The unchanged interior work remained about 18 seconds; the gain is concentrated
in the repeated limb/off-disk reads targeted by this correction.
Combined child execution was **81.75 seconds** within the new 240-second limit;
**2/2 additional samples** are used, for 110 total including the preserved
108-sample original allocation. The [fixture manifest](fci-limb-correction-fixture.json)
pins the 571,931,767-byte local source copy by SHA-256. No new sources were
downloaded. All new writes are in audit scratch/reports, never the live cache.

These are sequential service calls, not concurrent HTTP or browser paint. The
OS file cache and other desktop activity were uncontrolled; a focused 117-test
suite overlapped part of the control run. This is enough to diagnose the ten
eliminated whole-grid loads, but the percentages are not a matched-workload
acceptance claim. Memory was sampled every 20 ms and can miss brief peaks.
OBS load, p95, multi-frame behavior and lower-resource machines remain untested.

The final automated gate passed **694 Python tests plus 42 subtests** and scoped
Ruff, with 52 existing dependency deprecation warnings. The frontend is unchanged;
its preceding 54-test Node gate is prior evidence, not a new browser check.
[Validation metadata](fci-limb-correction-validation.json) ties these results to
the current runtime hashes.

## Next owner smoke

Restart the dashboard normally to load the correction. Keep downloaded sources
and existing tiles. Use M12 visible at the z4 opening view on a newly available
frame or previously unrendered view; revisiting cached tiles does not exercise
the fix. Look for faster filling near the eastern disk edge, unchanged detail,
transparent space, and responsive pan/zoom. Continue the broader Satellite and
Workspace smoke checklist with IR/composite, playback/scrub and the usual OBS
workload after this targeted check.

Fresh-source acquisition still waits for the FCI bundle before rendering. The
observed 72.7-second source-file completion interval was not a full download
duration and is not removed by this correction. Total first-frame latency is
therefore still an owner acceptance question. Record source acquisition separately
from rendering before deciding whether a bounded acquisition/first-use scheduling
change is needed. Do not resume other rendering-family implementation or claim
the original 2–3-minute end-to-end issue is closed on backend evidence alone.
