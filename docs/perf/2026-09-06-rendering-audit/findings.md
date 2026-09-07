# First available-input backend batch — 2026-09-06

This is dated audit evidence, not a renderer implementation or browser acceptance.
The active roadmap remains superfile section 4.8. Runtime files still match the
accepted baseline at `e200f74`, followed by documentation commits through `215729e`.

This first-batch record is preserved. Later [native-window prototype findings](fci-window-findings.md)
add ten quality cases and 54 timed samples without changing application code.
Use that record for current M12 experiment results and remaining integration gaps;
the counts and unresolved quality questions below describe the first batch.

## Coverage and limits

Seven of twelve timing cells were exercised in 48 samples, three per measured
state. The 21 fresh child processes took 120.71 seconds including imports. New
scratch files, including acquired/pinned sources, total 1,414,230,579 bytes
(1.32 GiB). No render failed or crashed. This stays below the approved
45-minute/10-GiB/108-sample ceilings; it does not complete the broader audit.

All renderer calls used fixed local inputs and an isolated cache at
`cache/rendering-audit-20260906/`; a Python socket audit hook rejected accidental
network connections. The dashboard and its warmers were not started, stopped,
or reconfigured. Ordinary desktop activity was not controlled, so this batch
must not be labeled an isolated-dashboard or OBS workload comparison.

The earlier KMHX candidate disappeared from the live cache before validation.
The retained replacement, `KRAX20260906_005236_V06`, was copied and hashed before
any render. It contains reflectivity and correlation coefficient at sweep zero:
720 rays by 1,832 gates, 250 m gate spacing. The RTMA input is valid at
2026-09-05 22:45 UTC, with wind speed and direction on a 2,345 by 1,597 Lambert
grid with 2,539.703 m spacing. See [native validation](validated-local.json).

Following the owner's instruction to proceed with source-only acquisition,
one M12 FCI bundle and one M11 RSS source were fetched for the fixed September 6
12:00–12:30 UTC window. Exact product IDs were saved before source downloads.
The separate ceilings were 2 GiB, 100 requests and 600 seconds, one transfer at
a time and no retries. The batch completed in 53.125 seconds: 44 requests,
1,246,146,067 received body bytes, 40 FCI chunks and one SEVIRI file. These are
fixture-acquisition measurements using a stricter audit transport, not a
benchmark of the production parallel downloader. Advertised provider size fields
are retained verbatim without assuming their units. See [transfer record](meteosat-acquisition.json).

## Measured costs

Values below are three-sample medians. Satellite values use existing native
instrumentation for one requested center tile plus its normal 3x3 supertile;
Radar and RTMA values cover one whole PNG and the listed publication work.
These different output scopes are not a family-to-family speed ranking.

| Case | Fresh process, local source (s) | Source cache warm, artifact absent (s) | Median fresh CPU seconds | Maximum sampled RSS / private commit (GiB) |
| --- | ---: | ---: | ---: | ---: |
| M12 Channel13 z5 | 2.650 | 0.168 | 2.61 | 0.31 / 1.71 |
| M12 Channel02 z8 | 3.895 | 0.148 | 3.95 | 0.48 / 1.88 |
| M12 NighttimeMicrophysics z5 | 3.558 | 0.324 | 3.56 | 0.38 / 1.80 |
| M11 RSS NighttimeMicrophysics z5 | 0.588 | 0.300 | 0.56 | 0.32 / 1.74 |
| Radar L2_REF, PNG then existing WebGL artifact | 5.010 | Not measured | 5.59 | 1.26 / 2.69 |
| Radar L2_RHO, PNG | 4.951 | Not measured | 5.66 | 1.25 / 2.69 |
| RTMA CONUS rapid Winds | 3.619 | 1.633 | 9.55 | 1.49 / 2.88 |

Memory columns take the largest sampled value across measured states. Private
commit is distinct from resident physical memory. Values include imported native
libraries and the collector; they are not minimum hardware requirements.

Satellite artifact-hit native medians were 0.143–0.178 ms for local service-path
lookup/validation. They exclude HTTP transfer and browser display. The outer
resource wrapper reports about 6–7 ms because starting its sampling thread
dominates such tiny operations; do not mistake that for renderer lookup cost.
Three samples do not establish a reliable p95. [Raw/summary data](baseline-summary.json)
retain ranges, CPU seconds, sampled memory, thread counts and I/O counters.

The current effective settings enable L2_REF WebGL and its animation, but not
velocity/Level III acceleration. Radar still renders its 5.75 MB PNG before
writing the 1.32 MB polar artifact. Median REF decode took 2.399 s, plotting
0.906 s, PNG encoding 1.206 s, and artifact publication 0.025 s. This identifies
a worthwhile scheduling/representation question; it does not prove RHO WebGL
benefits or quality equivalence. RHO PNG decode/plot/encode costs were similar.

RTMA's fresh extraction took 1.903 s. Its intermediate four-neighbor geographic
interpolation took 1.237 s fresh and 1.247 s warm, followed by a Mercator warp.
The warm render used 7.53 CPU seconds in 1.63 wall seconds, with up to 86 process
threads observed. That supports evaluating reuse or a direct native-grid warp;
the wind field's valid Lambert metadata supplies a concrete test case.

## Confirmed source-detail finding

The complete FCI headers verify a visible `vis_06` grid of **11,136 by 11,136**
and approximately 1,000 m spacing in geostationary projection coordinates.
The current high-zoom cap is **10,848**, so the loader's power-of-two stride
selects every second row and column: **5,568 by 5,568**, or one quarter of the
native samples. The current render successfully exercised that path. IR `ir_105`
is natively 5,568 by 5,568 at approximately 2,000 projection metres and remains
unstrided at high zoom. These spacings are not limb ground-resolution claims.

At z1–4/z5–6 the cap transitions retain 1,392/2,784 samples per axis for both
channels, using different strides. At z8 and latitude 5 degrees, a 256-pixel
Mercator tile samples roughly 609 ground metres per output pixel: it cannot
recover the visible samples already discarded by the loader. Raising a map
zoom or changing CSS alone cannot address this. Simply lifting the cap is also
insufficient: the current admission estimate assumes at most 5,568 FCI samples
per axis and would undercount a full 11,136 visible array by four times.

Full chunk radiance reads precede FCI subsampling. Source windows, suitable
lossless native blocks and reusable geometry are therefore stronger first
experiment candidates than increasing whole-frame memory. A native-resolution
reference and detail/alpha/alignment comparison are still required before
choosing or accepting a replacement. See [all FCI headers](meteosat-headers.json).

M11 RSS verifies a 1,392 by 3,712 cropped grid, approximately 3 km projection
spacing and a 9.5-degree sub-satellite longitude. Its lower cost in this batch
does not justify forcing it into the same representation as M12.

## Quality evidence and remaining work

The selected Satellite center tiles and whole Radar/RTMA PNGs produced one
identical decoded RGBA hash per case across their measured repetitions/states.
The M12 visible tile and RTMA PNG were also visually inspected as standalone
artifacts. This establishes repeatability, not native-detail preservation,
geographic overlay alignment, all nine tile seams, or browser acceptance.

[Policy inventory](policy-inventory.json) captures exposed Satellite recipes for
all eight platforms, request floors/ceilings and warming zoom settings; all 19
configured Radar products; 69 MRMS variants; and ten RTMA product definitions.
This is configuration coverage, not source validation of every product. Current
Satellite admission remains 16 GiB with a separate 4 GiB source cache, ten tile
workers and two Meteosat warming workers; other heavy families share one slot.
No adaptive resource policy has been implemented.

Five exact timing cells still lack pinned sources: GOES Full Disk visible,
GMGSI IR, MRMS MESH, MRMS RotationTrack and RTMA hourly temperature. No automatic
additional acquisition was performed. Radar/RTMA service-hit timing, full-frame
history and cross-product cache reuse remain gaps as well.

Next evidence priorities are fixed-input browser presentation/OBS contention,
native detail/limb/seam samples, the missing-source families and actual
lower-resource machines. Browser runs must pin source sequences before starting
live warmers; the single Meteosat frame acquired here cannot prove 12-frame
playback. Preserve the rolling Chromium/WebKit/Gecko matrix in section 4.8 and
require real Safari on the M1 Mac. No compatibility or streaming claim is made
by this backend batch.

The first two architecture candidates for review are (1) M12 source access that
preserves native visible detail with corrected memory accounting and (2) RTMA
native-grid warp or reusable mapping. Radar remains in scope for measured,
product-specific WebGL expansion and PNG/artifact scheduling. MRMS needs its
selected source evidence before a representation change is justified. These
are recommendations for bounded experiments, not completed implementation.

## Reproduction and limitations

- `validate_local.py` copies/hashes local inputs, then decodes selected fields.
- `acquire_meteosat.py` is the completed, non-repeating source-only batch.
- `inspect_meteosat.py` validates native headers and calculates current strides.
- `baseline.py --phase local` and `--phase meteosat` call existing renderers in
  fresh children. Existing run IDs/results are deliberately refused; preserve
  evidence and choose a separately bounded run before repeating.
- `policy_inventory.py` reads configuration and frontend exposure.
- `summarize.py` recalculates summaries and checks selected-pixel repeatability.

Process memory is sampled every 50 ms and can miss short peaks. No GPU residency,
hard-page-fault/commit-pressure telemetry, browser process memory, HTTP latency,
queue contention or OBS statistics were collected. Host available memory stayed
above 97 GiB during samples; that says nothing about behavior on an 8–16 GiB
machine. Fresh processes reused the operating system's file cache. Native stage
timings and aggregate CPU are reported separately; overlapping work is not added
to manufacture an elapsed-time result.
