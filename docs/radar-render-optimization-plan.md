# Radar Render Pipeline — Latency Optimization Plan

Prepared 2026-07-22. Companion to
`docs/satellite-radar-render-pipeline-files.md` (shared pipeline reference).
Scope is the domestic NEXRAD live-cache path only. International providers,
Radar UI redesign, shared legend adoption, and the compatibility-only IEM tile
routes are out of scope. Phases 0-5 optimize the existing PNG workflow.
Separately gated Phases 6-8 may add an optional high-zoom WebGL layer without
removing or changing the PNG workflow.

## Goal and non-negotiable contracts

Minimize time from a Radar site/product selection to the first usable newest
PNG frame, then reduce background loop-fill time, without changing the rendered
PNG image, geographic bounds, source timestamp, frame order, palette, mask,
units, elevation selection, storm-motion semantics, or cache identity.

The optional WebGL track is progressive enhancement, not a PNG replacement.
The existing PNG must remain the first usable frame, compatibility fallback,
and one-switch rollback path. Phase 7 may add bounded WebGL playback at high
zoom, but PNG playback remains available for every frame and becomes active
immediately whenever the WebGL buffer is incomplete or disabled.

Preserve these current contracts:

- `/api/radar/live/*` remains the production workflow.
- Flat NODD Level II files remain authoritative;
  `LIVE_RADAR_L2_USE_CHUNKS` stays `False`. The chunks experiment already
  showed no completed-scan latency benefit and is not part of this plan.
- Empty-cache requests return newest frames first and continue filling history
  in the existing background-render deduplication path.
- Lookback remains 0.5–12 hours, with existing retention, cadence, and
  freshness-sentinel behavior.
- Level II default/requested elevation, field-aware split-cut sweep selection,
  non-CONUS Level-II-only filtering, and L2 SRV motion cache variants remain
  unchanged.
- Super-resolution products remain at their configured 22-inch/200-DPI output;
  other products retain their configured 12-inch/200-DPI output unless a later
  pixel-identical candidate proves equivalent.
- Existing product configuration remains authoritative. Do not add hard-coded
  render branches outside `config/radar_config.py`.
- Every phase must be independently revertible and must not require cache-key
  or render-version changes unless its output intentionally changes. Phases
  0-5 reject intentional PNG pixel changes.
- Phase 0 PNG goldens remain permanent regression evidence. WebGL artifacts
  use a separate versioned cache namespace and separate visual/value contracts;
  they never overwrite PNGs, PNG indexes, or processed-source identity.
- WebGL must be guarded by one server/client feature switch. Turning it off
  must restore the original PNG-only behavior immediately, without a cache
  purge, source redownload, API restart dependency beyond normal configuration
  loading, or code rollback.

## Current path and known costs

```text
Radar selection
  -> /api/radar/live/latest or /frames
  -> services/radar_service.py cache lookup
  -> empty/stale cache: run_radar_live_site_product
  -> radar_nodd_utils.py list + download flat NODD file(s)
  -> radar_live_worker.py read/decode + field/derived-field selection
  -> field-aware sweep selection
  -> Py-ART/Cartopy Matplotlib PPI plot
  -> PNG encode to cache/tmp/radar_live
  -> copy + metadata/index update under cache/radar/live
  -> API returns image URL/bounds; background history continues
```

Important pre-measurement observations:

- An empty `/frames` cache currently renders up to
  `OVERLAY_EMPTY_CACHE_SYNC_FRAMES = 3` frames synchronously before returning,
  then starts background history fill.
- `_render_overlay_png(..., profile=True)` already reports figure setup,
  masking, sweep selection, PPI plot, PNG save, and close timing, but parallel
  frame workers do not emit a structured comparable record.
- `multiprocessing.Pool` is created and destroyed per site/product batch.
- Level II NODD volumes contain multiple moments, while current product-owned
  download directories and render loops can download/read the same volume for
  REF, VEL, SW, ZDR, RHO, PHI, and derived SRV work.
- Temporary and final rendered PNGs are on the same cache volume, but final
  placement currently copies the file before deleting the temporary source.
- The discovery index records directory mtime, but both branches still call
  `_discover_radar_files`; any claimed rescan saving must be measured before a
  fix is accepted.

## Phase 0 — Reproducible benchmark and golden baseline

**Behavior change:** none.

Add `python -m radar.bench` with structured JSONL timing gated by
`WX_RADAR_BENCH=1`. The harness must use pinned disk-resident NODD files and a
dedicated scratch root below `cache/radar/.bench/<run_id>/`; it must never purge
or rewrite production Radar source, overlay, or index files.

Required scenarios:

1. `api-hit`: latest and frames metadata from an already valid overlay cache.
2. `render-one`: one pinned local source file through read, field preparation,
   sweep selection, plot, encode, and finalize.
3. `empty-cache-response`: service-equivalent first response with the current
   synchronous-frame count and background fill disabled for measurement.
4. `backfill-12`: twelve disk-resident frames through current multiprocessing
   ownership and serial finalization.
5. `no-op-worker`: unchanged source directory and fully processed overlay cache.

Record at least five fresh-process samples for cold decode/render scenarios and
ten in-process samples for cache-hit/no-op scenarios. Emit:

- `list_ms`, `download_check_ms`, `read_ms`, `field_ms`, `derive_ms`,
  `sweep_ms`, `figure_ms`, `plot_ms`, `encode_ms`, `finalize_ms`, `index_ms`,
  `response_ms`, and `total_ms` where applicable;
- source file size/SHA-256/mtime, output PNG size/SHA-256/dimensions, selected
  field/sweep/elevation, frame key, bounds, cache key, Python/package versions,
  CPU/RAM, configured worker count, and scheduled-worker state;
- process working-set before/peak/after for `render-one` and `backfill-12`.

### Baseline matrix

Use the newest complete locally pinned files available at capture time. Prefer
KGSP for cross-product comparability and KFCX for a second-site control.

| Row | Site | Product | Elevation/motion | Purpose |
|---:|---|---|---|---|
| 1 | KGSP | L2_REF | 0.5° | 22-inch reflectivity control |
| 2 | KGSP | L2_VEL | 0.5° | split-cut Doppler sweep selection |
| 3 | KGSP | L2_SRV | fixed 25 kt toward 045° | derived-field and motion-key cost |
| 4 | KGSP | L2_ZDR | 0.5° | dual-pol Level II control |
| 5 | KGSP | L3_N0B | fixed product sweep | 22-inch Level III reflectivity |
| 6 | KGSP | L3_N0G | fixed product sweep | Level III velocity control |
| 7 | KFCX | L3_DPR | fixed product sweep | 12-inch digital/MetPy-fallback class |
| 8 | KFCX | L2_REF | 0.5° | second-site geometry/cache control |

Capture golden evidence for every row:

- byte SHA-256 of the PNG and decoded RGBA SHA-256;
- exact width/height, geographic bounds, frame timestamp/key, source key,
  selected elevation, available elevations, units, and cache-product key;
- nontransparent-pixel count and RGBA bounding box as a fast diagnostic.

A phase fails if any golden PNG or metadata contract changes. If PNG container
bytes differ but decoded RGBA is identical, stop and review before accepting;
do not silently weaken the gate.

Commit compact summaries/manifests under `docs/perf/<date>-radar-baseline/`.
Keep raw timings and golden PNGs ignored under `cache/radar/.bench/`.

Implementation status (2026-07-25): complete and behavior-neutral.
`python -m radar.bench` provides the five required scenarios, structured stage
timing, working-set sampling, scratch confinement, environment/source
manifests, and capture/compare golden contracts. All eight matrix rows passed
five fresh-process byte-identical PNG and decoded-RGBA comparisons. API-hit and
no-op have ten in-process samples; empty-cache response and backfill have five
fresh-process samples. Compact evidence is in
`docs/perf/2026-07-25-radar-baseline/`; raw JSONL, pinned inputs, and rendered
PNGs remain under ignored `cache/radar/.bench/`. The focused Radar gate passes
36 tests plus 42 subtests; full pytest passes 261 tests plus 42 subtests with
only the pre-existing Workspace assertion against removed
`WORKSPACE_REGION_BOUNDS`. Stop for review before Phase 1.

## Phase 1 — Newest-frame response first

The empty-cache `/frames` path currently performs up to three synchronous
renders before returning. Retain the three-frame warm intent, but render only
the newest frame synchronously; queue the remaining initial/history work through
the existing keyed background-render path.

Do not change `OVERLAY_EMPTY_CACHE_SYNC_FRAMES` until the baseline separates
the first-response contract from total warm depth. Prefer a service-level split
between one response-critical frame and the existing background batch over a
global knob change.

**Verify:** first usable newest-frame response p50/p95, exactly one synchronous
new frame on an empty cache, `refreshing=true` while history continues, eventual
frame sequence parity, background deduplication, and all eight golden rows.

Implementation status (2026-07-25): implemented; automated, benchmark, and
golden gates pass. The service keeps `OVERLAY_EMPTY_CACHE_SYNC_FRAMES = 3` as
the warm-depth intent but synchronously renders only one newest frame. The
existing keyed background path fills the remainder. KGSP L3 N0B improved from
3.804/4.114 seconds p50/p95 to 2.012/2.017 seconds, a 47.1%/51.0% reduction.
All eight Phase 0 golden comparisons pass. Focused Radar validation passes 38
tests plus 42 subtests; full pytest passes 263 tests plus 42 subtests with only
the pre-existing Workspace assertion. Evidence is in
`docs/perf/2026-07-25-radar-phase1/`. User-owned browser acceptance passed on
three Radar sites: the scrubber stayed on newest while history grew, and
playback remained continuous from the initial two frames through the completed
roughly 14-16-frame loops.

## Phase 2 — Reuse render processes for scheduled/backfill batches

Current multi-frame work creates a fresh `multiprocessing.Pool` per
site/product batch. Add optional externally owned pool plumbing to
`_render_site_product`; the scheduled worker and one background backfill job
may reuse a bounded pool for their run, while single-frame response-critical
work keeps its lowest-latency path.

Do not change `LIVE_RADAR_PARALLEL_WORKERS` in this phase. Measure Windows
spawn/import removal separately from plot/encode time, and record retained
working set because Py-ART/Matplotlib workers are heavier than Satellite tile
workers.

**Verify:** `backfill-12` wall p50/p95, one pool creation per owning run,
unchanged lock/freshness behavior, bounded post-run process lifetime, peak RSS,
and all golden rows.

Implementation status (2026-07-25): implemented; automated, retained-pool
benchmark, and golden gates pass. Scheduled runs share one lazily started,
bounded pool across site/product batches. Selected-product background runs own
one pool for their batch, while the response-critical single-frame path starts
no multiprocessing workers. Normal completion closes/joins the pool and
exceptional completion terminates/joins it. `LIVE_RADAR_PARALLEL_WORKERS`
remains unchanged.

KGSP L3 N0B retained-pool `backfill-12` measured 7.989/8.271 seconds p50/p95
versus the Phase 0 8.230/8.352 seconds, a 2.9%/1.0% reduction. Pool
construction and worker-readiness/import were recorded separately at
16.760/18.075 ms and 458.285/459.916 ms p50/p95. Every sample created exactly
one four-process pool; p95 peak working set was about 2.50 GiB. All eight Phase
0 golden comparisons pass. The focused Radar gate passes 49 tests plus 42
subtests; full pytest passes 268 tests plus 42 subtests with only the
pre-existing Workspace assertion. Evidence is in
`docs/perf/2026-07-25-radar-phase2/`.

User-owned browser acceptance subsequently passed on both `/radar` and
`/workspace`. KGGW and KTFX newest frames appeared before their eight- and
ten-frame four-process background fills, history requests returned HTTP 200,
playback and newest-frame scrubber position remained continuous, and the
terminal showed no pool, render, worker, or Radar API exceptions. Phase 2 is
closed.

## Phase 3 — Level II source and decode deduplication

Measure before combining anything:

1. Prove that REF/VEL/SW/ZDR/RHO/PHI requests for the same site/timestamp resolve
   to the same flat Level II NODD volume by source key and SHA-256.
2. Quantify duplicate listing, download storage, file reads, and Py-ART decode
   time across the configured Level II product set.

If confirmed, introduce a site/frame-owned Level II source spool rather than
product-owned duplicate files. Then evaluate a worker task that reads one volume
once and renders a bounded set of requested products, retaining per-product
field preparation, sweep selection, palette, output, cache key, and metadata.
Dynamic L2 SRV motion variants may reuse the canonical VEL source but remain
separate render/cache products.

Design the decoded-sweep ownership with a bounded consumer seam so the same
decoded sweep could later feed the existing PNG renderer and an optional
compact polar-artifact writer. Phase 3 does not create WebGL artifacts, add an
endpoint, change the frontend, or permit a second Py-ART decode for a future
detail layer.

Use references/hard links only if Windows/filesystem support and cleanup
semantics are proven; otherwise use one canonical source path. Do not alter the
Level III product-specific source layout.

**Verify:** source hashes, disk bytes, decode count/time, batch wall time, peak
RSS, per-product failure isolation, retention cleanup, value-inspector results,
and all golden rows.

## Phase 4 — Discovery and finalize I/O

Implement only the substeps supported by Phase 0 timings:

- persist/reuse the discovered filename list when directory mtime is unchanged,
  instead of rescanning while merely updating the mtime token;
- replace same-volume temporary PNG copies with an atomic move into the final
  cache path, preserving cleanup and failure recovery;
- batch processed-key/index writes only if crash-safe visibility and newest
  frame ordering remain unchanged.

**Verify:** `no-op-worker` and `backfill-12` I/O/stage timings, interrupted
finalization recovery, no orphan temp files, correct pruning, immediate newest
frame visibility, and all golden rows.

## Phase 5 — Optional renderer internals, measure first

Only enter this phase if `plot_ms` or `encode_ms` remains the dominant cost
after Phases 1–4. Candidate experiments must be isolated and rejected on the
first output mismatch:

- cache immutable site/projection/bounds preparation;
- avoid duplicate field masking/copies where masked-array ownership permits;
- test a lower-overhead Py-ART/Matplotlib construction path with identical
  pcolormesh geometry;
- test PNG encoder settings only if both container bytes and decoded RGBA meet
  the approved gate.

Do not introduce downsampling, smaller figures, changed DPI, relaxed geographic
extent, approximate gate geometry, altered colormaps, or lossy encoding.

Phase 5 is a decision gate, not a prerequisite for WebGL. Defer it if the
remaining PNG `plot_ms`/`encode_ms` cost does not justify more work or if the
candidate would optimize code that the high-zoom pilot does not use.

## Phase 6 — Optional high-zoom WebGL L2 Reflectivity pilot

**Behavior change:** additive and feature-flagged. The PNG workflow remains
authoritative and unchanged.

The measured KGGW control sweep contains 720 radials, 1,832 gates, 250-meter
range spacing, and approximately 0.486-degree azimuth spacing. Its
4,380-by-4,400 PNG covers roughly 1,110 km, so at Leaflet zoom 11 one PNG pixel
is enlarged to about five screen pixels. Do not increase full-site DPI: a
zoom-11-equivalent full-site image would be roughly 22,000 pixels square and
about 25 times the current pixel workload.

Add a compact, versioned polar artifact for L2 Reflectivity only, produced from
the same decoded sweep used by the PNG renderer. Artifact serialization may
occur as a bounded byproduct of that existing decode, but browsers perform no
artifact request, texture upload, or WebGL work below the configurable prefetch
threshold.

Use two separately configurable thresholds:

- below zoom 10: PNG only; no client WebGL request, texture, or GPU work;
- zoom 10: keep displaying PNG and quietly request/upload the active paused
  frame's polar artifact;
- zoom 11+: keep the PNG visible until the texture is ready, then crossfade to
  native-gate WebGL rendering without changing the selected frame.

If the user jumps directly from below zoom 10 to zoom 11+, the PNG remains
visible while the WebGL layer warms. Returning below zoom 11 restores PNG;
returning below zoom 10 cancels pending WebGL work and releases the texture
after a short bounded grace period so rapid 10/11 zoom changes do not thrash.
Failure, unsupported WebGL, playback, product/frame change, or feature-switch
disablement also restores PNG immediately in Phase 6.

Initial scope:

- domestic L2 Reflectivity only;
- `/radar` and `/workspace` through the shared `radar-engine.js`;
- active paused frame only, with one retained GPU texture;
- configurable prefetch at zoom 10 and activation at zoom 11;
- no WebGL animation, tile pyramid, server viewport render, all-product
  conversion, inspector rewrite, or PNG retirement;
- no second source read or Py-ART decode;
- exact site, frame, elevation, mask, palette, units, bounds, and value parity;
- pan/zoom redraws are client-local and submit no new render job.

Required acceptance gates:

- first-usable PNG p95 regresses no more than 5%;
- compact artifact payload is no larger than 2 MB for the representative
  KGGW control unless a measured alternative is approved;
- cached high-zoom redraw completes within 100 ms on the reference system;
- artifact creation adds no second Py-ART decode and does not delay background
  history beyond the approved Phase 2 envelope;
- GPU memory is bounded to the active texture and released on layer teardown,
  page departure, context loss, or feature disablement;
- shader colors/masks and sampled values match server-owned product rules;
- both pages pass newest-first, scrubber, playback fallback, pan/zoom,
  direct-low-to-zoom-11, zoom-threshold reversal, selection-change,
  WebGL-context-loss, and PNG-only browser acceptance;
- the complete Phase 0 PNG golden matrix and focused/full regression gates pass.

Phase 6 fails if it materially delays the PNG path, cannot preserve value/color
semantics, behaves inconsistently across the two pages, or requires the WebGL
layer for ordinary Radar correctness.

### Phase 6 rollback

Rollback is configuration-first:

1. Disable the WebGL feature switch. Both pages must immediately use the
   existing PNG layer for every zoom and frame.
2. Stop publishing new polar artifacts. Existing versioned artifacts become
   unreachable and may expire through their own bounded cleanup policy.
3. Do not delete or rewrite PNG/source caches, indexes, golden evidence, or
   product configuration.
4. If the experiment is rejected, remove the WebGL endpoint/layer/artifact
   code in its own phase commit. No Phase 0-5 commit is reverted.

## Phase 7 — Optional bounded L2 Reflectivity WebGL animation

Enter only after Phase 6 passes and receives explicit approval. Preserve the
same thresholds while extending L2 Reflectivity:

- below zoom 10: PNG-only playback and no client WebGL work;
- at zoom 10: PNG playback continues while a bounded rolling WebGL texture
  window warms in the background;
- at zoom 11+: PNG playback continues until the active texture and a minimum
  forward buffer are ready, then crossfade to WebGL without restarting,
  jumping, or changing scrubber position;
- retain at most the current frame, one prior frame, and two or three upcoming
  frames, with the exact budget chosen from Phase 6 payload/GPU measurements;
- when a texture is unavailable, show that frame's PNG and continue playback
  rather than pausing or skipping it;
- on zoom below 11, immediately return to PNG playback while retaining the
  small buffer for a bounded grace period; below zoom 10, cancel pending loads
  and release textures after that grace period;
- selection, elevation, lookback, motion variant, page departure, context loss,
  and feature disablement cancel stale work and restore PNG.

Phase 7 must prove stable frame order/cadence, bounded network/GPU memory,
cooperative cancellation, no additional server render request from pan/zoom,
and both-page animation acceptance. PNG remains the complete one-hour loop and
authoritative fallback; WebGL readiness never delays initial playback.

## Phase 8 — Optional core-product WebGL expansion

Enter only after Phase 7 passes and receives explicit approval. Expand in
bounded product families, beginning with L2 Velocity/SRV and L3 N0B/N0G.
Every family needs its own artifact encoding, palette/mask/value parity,
payload/GPU budget, animation gate, and browser matrix. The other Level II
dual-pol and special Level III accumulation, categorical, Echo Tops, and VIL
products remain PNG unless separately justified.

All-product WebGL conversion, PNG retirement, and server-rendered tiles remain
outside this plan. Any of those requires a new approved migration plan and
retains PNG fallback until its own closure gate.

## Execution order

1. Phases 0-2 are complete; keep their commits/evidence independently
   revertible.
2. Implement Phase 3 only after explicit authorization, preserving PNG output
   while establishing canonical Level II source/decode ownership.
3. Complete Phase 4 and then decide from measurements whether Phase 5 is worth
   entering or should be deferred.
4. Authorize Phase 6 separately. Its first implementation is L2 Reflectivity
   only and feature-flagged off until automated gates pass.
5. Authorize Phase 7 separately for bounded high-zoom L2 Reflectivity animation.
6. Authorize each Phase 8 product family separately; do not infer approval for
   all-product conversion.
7. After every phase, run the complete PNG golden matrix, focused Radar tests, full
   pytest, `py_compile`, JavaScript syntax checks if frontend files changed, and
   `git diff --check`.
8. Keep browser claims separate. User browser smoke owns visible first-load,
   animation continuity, elevation, inspector, and storm-track acceptance.

Rollback remains one phase commit at a time. No phase may depend on deleting
production cache data to restore service. Phases 6-8 additionally require the
configuration-first PNG-only rollback above; experimental artifact cleanup is
never a prerequisite for restoring the original workflow.
