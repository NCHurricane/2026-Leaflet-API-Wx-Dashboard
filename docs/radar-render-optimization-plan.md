# Radar Render Pipeline — Latency Optimization Plan

Prepared 2026-07-22. Companion to
`docs/satellite-radar-render-pipeline-files.md` (shared pipeline reference).
Scope is the domestic NEXRAD live-cache path only. International providers,
Radar UI redesign, shared legend adoption, and the compatibility-only IEM tile
routes are out of scope.

## Goal and non-negotiable contracts

Minimize time from a Radar site/product selection to the first usable newest
frame, then reduce background loop-fill time, without changing the rendered
image, geographic bounds, source timestamp, frame order, palette, mask, units,
elevation selection, storm-motion semantics, or cache identity.

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
  or render-version changes unless its output intentionally changes. This plan
  rejects intentional pixel changes.

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

## Execution order

1. Commit the Radar planning/reference correction.
2. Implement and commit Phase 0 only; no behavior changes.
3. Review the full baseline and confirm or revise Phases 1–5 from measured stage
   shares before implementation.
4. After every phase, run the complete golden matrix, focused Radar tests, full
   pytest, `py_compile`, JavaScript syntax checks if frontend files changed, and
   `git diff --check`.
5. Keep browser claims separate. User browser smoke owns visible first-load,
   animation continuity, elevation, inspector, and storm-track acceptance.

Rollback remains one phase commit at a time. No phase may depend on deleting
production cache data to restore service.
