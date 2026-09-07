# Restarted M12 owner smoke: first fill still slow

The owner restarted the server, hard-refreshed and reports approximately **115
seconds** for M12 Channel02 to display fully. The existing Chrome tab identifies
the displayed frame as **20260907T001500Z**, Full Disk, Europe/Africa, z4. This
remains an open end-to-end latency issue.

The [sanitized evidence](owner-smoke-restart-0015.json) combines retained browser
Resource Timing with the matching 40-tile filesystem snapshot. Inspection did
not reload/navigate the tab, start another test, download sources, or restart
the server. The current runtime hashes match the validated limb correction.

| Observed stage | Elapsed |
| --- | ---: |
| Catalog request | 5.382 s |
| First tile HTTP request sent to source manifest completion | 61.317 s |
| Source manifest completion to last tile response | 19.550 s |
| Catalog request start to last tile response, including small dispatch gaps | 86.254 s |
| Owner's approximate stopwatch/full-display observation | 115 s |

The 115-second observation and the 86-second browser interval use different
measurement boundaries. Resource Timing records response completion, not final
image paint or the owner's stopwatch start. The roughly 29-second difference is
unlocalized; it must not be assigned to catalog, decoding, or browser paint by
subtraction. In particular, the catalog was only 5.4 seconds, so the earlier
filesystem-only suspicion of a long catalog wait is not supported here.

The provider delivered **587,203,045 bytes in 40 NetCDF files**. Source-file
completions span 58.230 seconds; this is shorter than the acquisition-path interval
because the first file also takes time to arrive. All source files finish before
the first tile. The 35 PNGs and five empty markers are produced over 17.213
seconds, compared with 52.221 seconds in the earlier smoke on a different frame.
Off-disk marker gaps are now about 13–14 ms. These observations support the
corrected rendering behavior; the cross-frame comparison is not another
controlled benchmark.

All 40 browser tile loads were initiated together. Six were sent immediately;
34 waited in the browser before HTTP dispatch, with a maximum initiation-to-send
interval of 78.320 seconds. That queue time overlaps acquisition/rendering and
must not be added to the stage totals. Holding tile requests while the full source
bundle arrives also occupies the initial request slots.

The browser reports Chrome 153 on Windows, with a currently observed 2195×1010
CSS-pixel viewport and DPR 1.75. This is an owner-session diagnostic, not acceptance
of the proposed browser matrix. OBS state and paint timing remain unconfirmed.
Later application warming added other coordinates/zooms independently; the
recorded output snapshot is restricted to the owner's original z4 viewport.

## Next proposed bounded slice

Focus on **first-use source acquisition and scheduling** before other renderers.
Current `provider_eumetsat._download_fci_chunks` waits for all 40 files and writes
a complete-bundle manifest before returning. The native window renderer therefore
cannot display an early tile when only that tile's required strips are present.

A [header-only dependency trace](fci-first-use-dependency-trace.json) of the prior
pinned 23:30Z fixture finds 28 of 40 body files, about 436.6 of 571.9 MB, needed
for the whole owner viewport; its first reference tile needs ten files, about
174.3 MB. This establishes a candidate for earlier useful output, not a promised
speedup. It assumes complete metadata, and the delivered files still bundle all
channels. Cold acquisition of trustworthy geometry is an unresolved dependency.

The next design should compare viewport-prioritized acquisition and rendering
of complete native windows as their strips arrive against the existing whole
bundle path. Specify endpoint/header discovery, expected-file identity, contiguous
coverage, gap/overlap checks, new-chunk arrival during a render, cancellation and
native fallback before implementation. Reuse of HTTP connections is a smaller
transport candidate; raising concurrency alone does not remove the whole-bundle
wait. Preserve current byte budgets and exact output quality.

First validate with local pinned files and simulated out-of-order arrivals,
checking exact RGBA, no premature empty markers, no stale publication after
selection changes, and bounded memory/cache ownership. Any new live acquisition
or timed comparison needs a concrete reviewed allocation; the original 108
samples and the correction's extra two are already used. No new benchmark
allowance is created by this owner smoke report. No further owner repeat is
needed merely to reconfirm that first fill remains slow.
