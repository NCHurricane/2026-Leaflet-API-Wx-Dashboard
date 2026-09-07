# M12 visible native-detail reference — 2026-09-06

This is a bounded quality check using the pinned 12:00 UTC FCI source and the
existing calibration, bilinear warp and color pipeline. It is not an architecture
performance comparison or an independent geolocation reference.

The collector read and verified all 40 source hashes, then generated six 768 by
768 canvases: three z8 scenes at the current 10,848 cap and the same scenes with
the full 11,136 grid retained. The current interior center tile exactly matches
the earlier baseline hash. No existing baseline artifacts, runtime settings,
source files or application processes were changed.

| Sample | Pixels differing by more than 1 grayscale level, mutually opaque region | 95th-percentile absolute difference | Alpha mismatches across the full canvas |
| --- | ---: | ---: | ---: |
| Interior clouds, center lon 0 / lat 5 | 43.16% | 8 / 255 | 0 |
| Equatorial source-chunk boundary, center lon 0 / lat 0 | 29.15% | 6 / 255 | 0 |
| East limb, center lon 80 / lat 0 | 7.46% | 2 / 255 | 47,697 / 589,824 (8.09%) |

These are numerical differences, not a perceptual score or an acceptance
tolerance. The limb images were visually inspected: their projected discrete
coverage edges differ, and the current result has 334,460 opaque pixels versus
307,013 in the full-resolution reference. Which edge best represents the source
footprint still requires an independent geometry/mask check. Do not assume that
lifting the cap alone validates coverage.

The source arrays occupy 124,010,496 bytes at stride two and 496,041,984 bytes
at native resolution. Their affine transforms correctly differ with the selected
sample centers and spacing; windowed access must translate the original native
transform rather than rebuild it from rounded geographic bounds.

Reference construction and image comparison took 8.438 seconds after source
hashing. Sampled process RSS peaked at 1,265,291,264 bytes and private commit at
2,771,070,976 bytes. These combined diagnostic costs include both variants, imports
and retained library state; they are not per-variant benchmark numbers. The
collector imposed a 180-second ceiling, a 6-GiB RSS ceiling and a 4-GiB minimum
host-available-memory guard. Native-reference loading deliberately bypassed
production admission in this single diagnostic process; no production budget
was increased.

An additional metadata read of source chunks 1 and 21 found `vis_06` radiance
stored as zlib-compressed chunks of 300 by 11,136 values. Each selected source
file contains 278 rows in this frame. Narrow column requests therefore do not
avoid decompressing a full-width storage chunk. The most plausible immediate
I/O reduction comes from skipping unneeded source strips; calibrated/windowed
arrays can still avoid retaining the full disk. This is a storage-layout finding,
not measured proof that a new implementation is faster.

The concrete candidate scope and its acceptance checks are in active superfile
section 4.8. Remaining reference coverage includes other zoom transitions,
channels/composites, the opposite limb, independent geolocation and actual browser
presentation. No production change is accepted by this diagnostic.

Reproduction: `m12_detail_reference.py` refuses to overwrite an existing run.
The full metrics and artifact paths are in
[`m12-detail-reference.json`](m12-detail-reference.json). PNGs remain in the
ignored isolated cache; the comparison data and collector are tracked candidates.
