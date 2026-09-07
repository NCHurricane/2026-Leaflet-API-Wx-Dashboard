# M12 native-window integration — ready for owner smoke

Date: 2026-09-06. The owner authorized application integration after reviewing
the prototype. Changes are in the working tree above `215729e`; nothing is
committed or pushed. This record supersedes the prototype's recommendation-only
status for this selected M12 slice. The wider rendering audit remains open.

## Runtime behavior

- M12 creates a lightweight renderer, then selects native FCI source windows
  when the requested canvas is known. Visible source samples are no longer
  discarded by the 10848/2048/4096 rendering caps. Ambiguous limb geometry uses
  full-native data with dimensions read from the source headers.
- The new M12 tile namespace is `products-fci6`. Existing downloaded sources
  and old versioned tiles are retained; no cache deletion is required. New URLs
  prevent old decimated tiles and their empty markers from satisfying new requests.
- Source reuse keys include every body file's resolved path, size and nanosecond
  modification time, physical channel and native window. Secondary-chunk changes
  invalidate the bundle cache; changes during reading/warping reject publication.
  Alias channels share calibrated arrays. Native strip gaps, overlaps, projection
  disagreements and inconsistent axes fail explicitly.
- One M12 render owns its process's source arrays at a time, with cancellable
  FIFO waiting and the existing serialized NetCDF I/O. Application-owned M12
  warming runs inline in canvases of at most 3x3 tiles, checking live-work/selection
  ownership between canvases. It shares the live cache and admission budget
  instead of keeping extra M12 worker-process caches. M9/M11 keep their existing
  pool behavior.
- PNG encoding, palettes, calibration, warp behavior, request zoom ceilings,
  frontend playback/scrub ownership and Workspace pane order are retained.
  MRMS/SPC remain below Satellite. Radar, MRMS and RTMA renderers were not changed.

## Resource policy

`WX_SATELLITE_V2_FCI_WINDOW_CACHE_MB` is a retained-array ceiling, default 256 MiB.
The effective limit is the smallest of that ceiling, total host RAM / 128 and
currently available RAM / 32. With adequate free memory, example 8/16/128-GiB
hosts therefore retain at most 64/128/256 MiB of M12 arrays. Pressure reduces
residency, never native resolution. Metadata reuse holds four frame identities
and eight compact plans per frame. Large native fallbacks may be decoded again
when they exceed the cache; the prototype's small-window warm timings must not
be generalized to those cases.

M12 admission counts actual selected native float32 dimensions, caller/native
copies, largest-strip conversion/calibration buffers, destination/composite/GDAL
allowances and retained cache bytes. Planning checks available memory before
allocating inverse-projection arrays. Native rendering leaves host headroom of
one eighth of RAM, bounded between 512 MiB and 2 GiB; insufficient available
memory clears retained M12 arrays and defers the request through the existing
cancelled/warming response, rather than producing reduced-detail tiles.

Satellite admission capacity now follows the smallest of the configured
`WX_SATELLITE_RENDER_BUDGET_MB` ceiling (default 16384 MiB), total RAM / 4 and
available RAM / 2. It is rechecked while admitting queued work. The existing
oversized-job-runs-alone rule is retained; M12 additionally checks actual
available headroom before decoding. This queue also serves other Satellite
platforms, whose source-cache policies and coarse estimates remain unchanged.
These are conservative allocation estimates, not a hard whole-application RSS,
commit or GPU-memory guarantee. Browser budgets and other render families still
need their separate audit work. `psutil>=7.0.0` moved from development to runtime
requirements; the current environment already has 7.2.2.

## Evidence

[Final integrated quality checks](fci-integration-quality-final.json) match the
whole decoded RGBA output in all ten preserved native-reference cases exactly:
cloud interior, source-strip boundary, east limb, visible z4–7, IR z5, night
composite z5 and a mixed-grid backend diagnostic. Real service-path checks for
visible interior and limb publish the expected versioned center/neighbor tiles,
match the native center references, and reuse artifacts without another source
download. All variants retain the limb's three empty eastern tiles as negative
markers. These are fixed-input backend checks, not an HTTP/browser or owner smoke.

The [final six timing samples](fci-integrated-pilot.json) use three fresh processes
per case with the same native output and nine publication attempts as the prior
full-native controls. Process startup is separate from these render timings.

| Fresh-process case | Prior full-native median | Integrated median | Maximum sampled RSS, full/integrated |
| --- | ---: | ---: | ---: |
| Visible z8 | 4.147 s | 2.461 s | 1,200 / 270 MiB |
| Limb visible z8 | 4.200 s | 4.318 s | 1,199 / 1,207 MiB |

Visible elapsed time fell **40.7%**, CPU time from 4.000 to 2.344 seconds, and
maximum sampled RSS by **77.5%**. Limb elapsed time rose **2.8%**, CPU from 4.094
to 4.219 seconds and maximum sampled RSS by 0.7%. This retains a useful visible
gain without a measured critical regression above 5% in these selected metrics.
The integrated visible result supersedes the prototype's approximately 50%
timing reduction when describing application code. Night-composite integrated
quality passed, but its prototype timing result is not a new integration timing.

These were later candidate-only samples against earlier controls, on the
high-end Windows host with uncontrolled desktop activity and warm OS file cache.
They do not establish p95, first display over HTTP, playback, OBS performance or
lower-resource hardware acceptance. Sampling every 20 ms can miss brief peaks.
The six child processes used 31.78 seconds. Together with baseline and prototype
timing, the **108/108 sample allowance is exhausted**. Total audit scratch after
integration is 1,487,652,340 bytes (about 1.39 GiB). No source downloads, dashboard
launch or live warming occurred during these checks. The ten-case final quality
diagnostic is separately recorded, not counted as repeated benchmark samples.

The full gate passed **676 Python tests plus 42 subtests**, **54 Node tests** and
scoped Ruff. Python retained 52 dependency deprecation warnings. New regressions
cover native window/affine parity, cache eviction and aliases, secondary-file
invalidation, source changes during reading, malformed full fallback, memory
pressure, cancellation, versioned service publication and bounded warming that
yields to live work. Existing pool tests still cover M9 behavior. Earlier quality
reports and the failed first prototype remain preserved as dated evidence.

## Owner smoke on the running dashboard

1. Restart the dashboard normally to load the backend changes. No manual cache
   clearing is needed. The first visit generates tiles in the new M12 namespace;
   separate that initial acquisition/rendering from subsequent warm navigation.
2. On Satellite, choose Meteosat-12 and exercise visible Channel02, IR Channel13
   and NighttimeMicrophysics. Zoom from the opening view through z4–8, pan across
   cloud detail and toward the disk edge, and return to the same view. Look for
   persistent missing tiles, new seams, geographic displacement or controls that
   stop responding. Native limb transparency can differ from the former strided
   output; report conspicuous interior gaps or misplaced coverage rather than
   assuming every changed edge pixel is a failure.
3. Play available frames, scrub rapidly, switch products and switch away/back.
   The resting selection must win; watch for blank flashes, old-product returns,
   prolonged warming or activity that continues after leaving M12.
4. Repeat in Workspace with your usual OBS/browser workload and optional document.
   Check map/control responsiveness, retained MRMS/SPC ordering and OBS lag.
   Include a quick M11/M9 or GOES regression check because Satellite admission is
   shared, although their renderer/source-cache paths were not replaced.

For an issue, record page, product, frame/time, displayed zoom, browser, whether
OBS was active, and terminal/browser errors. This first owner smoke can establish
usability on the primary machine; real Safari on the M1, Chromium/Gecko matrix,
secondary Windows systems, fixed history sequences and controlled OBS comparisons
remain separate evidence. Do not interpret automated Node checks as browser proof.

## Reproduction

- `check_fci_integration.py --run-id fci-integration-quality-final` exercises
  the final native renderer and service publication against the pinned fixture.
- `bench_fci_integrated.py` performed the final six samples and refuses to
  overwrite its ledger. A further timing campaign needs a new recorded bound.
- Both collectors reject network connections and use only the isolated audit
  cache; their original run IDs must be preserved.

The live dashboard has not been restarted by the agent. Owner smoke, cross-browser
and secondary-machine acceptance remain pending. Greenfield is deferred; no
additional Radar WebGL activation or MRMS/RTMA architecture change is implied.
