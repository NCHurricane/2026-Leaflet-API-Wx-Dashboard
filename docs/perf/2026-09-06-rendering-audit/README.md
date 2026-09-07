# Rendering audit and M12 integration evidence

Date: 2026-09-06. Runtime baseline: `e200f74`; committed audit plan: `215729e`.
The active superfile remains the roadmap. This directory contains dated evidence.

Current outcome: [M12 native-window integration](fci-integration-findings.md) is
implemented in the working tree and ready for owner smoke. Ten integrated quality
cases match full-native RGBA exactly; the final visible timing uses 40.7% less
elapsed time and 77.5% less sampled peak RSS than the prior native control. The
full gate passed 676 Python tests plus 42 subtests and 54 Node tests. All 108
timing samples are now used. Browser/OBS and secondary-machine acceptance remain
pending; the records below retain earlier checkpoint scope and limitations.

The [first available-input backend findings](findings.md) now cover seven of
twelve timing cells: 48 samples, 120.71 seconds of child-process time and 1.32
GiB of isolated scratch files. The separately authorized two-frame Meteosat
acquisition completed within its limits. This is backend evidence, not browser,
OBS or renderer-implementation acceptance. The initial inventory below is
preserved as the record of what was available before execution.

A subsequent [M12 native-detail comparison](m12-detail-reference.md) generated
six small canvases and quantified both cloud-detail and limb-alpha changes.
Its metrics are separate from the 48-sample performance baseline.

The subsequent [native-window prototype](fci-window-findings.md) matches all ten
selected native-quality cases exactly. Its 54 timed samples bring the combined
audit to 102/108; the revised candidate shows about 50% less fresh visible-z8
wall time and 77% lower sampled peak RSS against full-native controls. Review
the recorded I/O tradeoffs, earlier regressions and follow-up limitations before
application integration. Runtime files and browser behavior remain unchanged.

## Evidence category

The first run is a **read-only file inventory and dependency metadata capture**,
not a rendering benchmark or browser acceptance. No renderer was imported, no
weather arrays decoded, no provider contacted, and no source cache modified.
The three existing documentation edits were preserved.

Reproduction from the repository root:

```powershell
.\.venv\Scripts\python.exe docs/perf/2026-09-06-rendering-audit/preflight.py
```

[`preflight.json`](preflight.json) records cache groups, byte counts, file
samples, dependency versions, Git state and hashes of two candidate input files.
[`preflight.py`](preflight.py) is the exact collector. Re-running it refreshes
the inventory JSON; preserve this snapshot before a later dated comparison.

## First findings

Three of the twelve planned timing cells have local source candidates:

- Radar `L2_REF` and `L2_RHO` can share a selected KMHX Level II volume, pending
  verification of the actual fields/sweep. The selected file is
  `KMHX20260905_023747_V06` (10,586,058 bytes).
- RTMA rapid-update Winds has a candidate from 23 retained rapid-update GRIB
  files. The selected file name includes `rtma2p5_ru.t2245z.2dvaranl_ndfd.grb2`
  (84,732,284 bytes). Valid date, grid and wind components need header checks;
  selection is deterministic by filename, not a claim that it is the latest.

The other nine exact cells lack local source inputs in their selected cache
locations: three M12 cases, M11 RSS composite, GOES Full Disk visible, GMGSI IR,
MRMS MESH, MRMS RotationTrack and RTMA hourly temperature. All five distinct
Radar source paths referenced by the older Phase 5 matrix are also absent.
No claim is made about when or why those files disappeared.

Other source data remain, including GOES CONUS/Meso and MRMS reflectivity.
Those are not automatic substitutes for Full Disk, MESH or finer-grid rotation
cases. Derived PNG/tile caches also cannot stand in for source-decode inputs.

## Initial inventory boundary and subsequent execution

The initial pass required validation without network acquisition. The Satellite benchmark CLI can fall
back to a provider lookup when a pinned local frame cannot be resolved, so it
must not be invoked blindly for a missing case. Any eventual run needs verified
local inputs, isolated scratch paths and explicit source identities.

The owner subsequently authorized proceeding with isolated Meteosat source
acquisition. [The transfer record](meteosat-acquisition.json) pins one M12 and
one M11 frame; [native headers](meteosat-headers.json) verify dimensions.
The earlier KMHX candidate was absent before validation, so a retained KRAX
volume was pinned instead. [Local validation](validated-local.json) records that
change, hashes and actual Radar/RTMA fields. No comparison mixed those scenes.

The inventory itself produced no performance measurements. Subsequent
[baseline results](baseline-summary.json) and [policy inventory](policy-inventory.json)
are separate evidence categories. Five selected timing cells still lack sources;
real browser/OBS, lower-resource and Safari checks remain outstanding. See
`findings.md` for limitations, reproduction commands and the next evidence needs.
