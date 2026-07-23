# Satellite Render Pipeline — Latency Optimization Plan

Prepared 2026-07-11; execution began 2026-07-22. Companion to
`docs/satellite-radar-render-pipeline-files.md` (file reference). Scope is
`satellite_v2` only; radar is explicitly out of scope for Phases 0–6 (the
Phase 0 harness methodology is reusable there later).

**Goal:** minimize end-to-end tile latency (click → download → parse →
reproject → colorize → PNG → response) at high zoom, with pixel output
**bit-identical** to today. No downsampling, no coordinate-accuracy loss, no
stretch-window changes.

---

## Ground rules (read before touching anything)

1. **Pixel-identical or it doesn't land.** Every phase below except none is
   required to produce byte-identical tiles for the same frame. Golden-tile
   diffs (Phase 0) are the gate. Because output is unchanged,
   `SATELLITE_V2_RENDER_VERSION` / `SATELLITE_V2_RENDER_VERSION_HIMAWARI` are
   **not** bumped — bumping needlessly cold-starts the whole tile cache.
2. **Protected knobs — do not modify** (`config/satellite_v2_config.py`
   unless noted):
   - `SATELLITE_V2_LIVE_TILE_RENDER_WORKERS = 10`
   - `SATELLITE_V2_LIVE_SUPERTILE_RADIUS = 1`
   - `SATELLITE_V2_NETCDF_CACHE_SIZE = 16`
   - `SATELLITE_V2_RENDERER_CACHE_SIZE = 8`
   - `SATELLITE_V2_GOES_FULLDISK_MAX_GRID` / `SATELLITE_V2_AHI_MAX_GRID` /
     `SATELLITE_V2_FCI_MAX_GRID` = 10848 — these stride caps are the guard
     against the 2026-06-05 FULLDISK Channel02 OOM. Never loosen.
   - All `SATELLITE_V2_RAPID_WORKER_*` and `SATELLITE_V2_METEOSAT_PREFETCH_*`
   - `_FCI_DOWNLOAD_WORKERS = 4` in `satellite_v2/provider_eumetsat.py`
     (EUMETSAT fair-use)
   - `Image.MAX_IMAGE_PIXELS = None` in `satellite_v2/composites.py`
     (deliberate, for Black Marble)
3. **Protected state/contracts:**
   - Worker `.lock` files + freshness sentinels (`workers/_freshness`)
   - FCI `manifest.json` format — shared between
     `provider_eumetsat._read_fci_manifest` and
     `meteosat_prefetch_worker._frame_sources_cached` (duplicate logic; a
     format change breaks both sides)
   - Negative-tile marker contract (tiler writes, cache stores, service
     short-circuits)
   - `service.get_frame_bounds` imports the private
     `renderer._load_source_raster` — keep a single-channel entry point alive
   - `tiler._initialize_warm_tile_worker` pickles renderer init args across
     the process boundary — new caches must stay process-local
   - EUMETSAT `_TOKEN` cache, S3 `_PREFIX_LIST_CACHE` TTL
4. **Boundaries:** routes stay in `routes/`, orchestration in
   `satellite_v2/service.py`, render in `renderer.py`/`composites.py`, tile
   planning/warming in `tiler.py`, schedule/loop logic in the worker modules.
   No mixing (per `docs/architecture.md` / `docs/patterns.md`).
5. **Don't touch:** `js/satellite.js` (dead, never loaded — note
   `docs/architecture.md:32` is stale on this point), `radar/radar_chunks_utils.py`
   (disabled but intentionally kept), `LIVE_RADAR_L2_USE_CHUNKS = False`.
6. **Checkpoints:** one commit per phase minimum (small-checkpoint rule in
   `docs/architecture.md`). Each phase leaves the pipeline fully runnable.

---

## Pre-existing bug found during review (fix scheduled in Phase 1)

`satellite_v2/renderer.py:43` declares `_NETCDF_CACHE` as a **plain dict**,
but eviction at `renderer.py:309` calls `popitem(last=False)` —
`dict.popitem()` takes no arguments, so inserting the **17th distinct GOES
NetCDF in one process raises `TypeError`** and every subsequent new-file
render 500s until process restart. Additionally, replacing an entry on mtime
change (`renderer.py:305`) never closes the old dataset (HDF5 handle leak).

- Fix: convert to `OrderedDict` LRU (`move_to_end` on hit, `popitem(last=False)`
  on evict), close datasets on evict **and** on same-key replace.
- Lands as **its own commit at the start of Phase 1** — Phase 0 must be
  zero-behavior-change so baselines measure the status quo.
- Phase 0 mitigation: keep any single bench process under 16 distinct GOES
  files, or restart between runs (the cold protocol below restarts per rep
  anyway).

---

## Pipeline map

```
routes/satellite_v2.py
  └─ service.resolve_tile
       ├─ (hit)  cache.is_valid_tile_file        ← full PNG decode EVERY hit  [Phase 1]
       └─ (miss) ThreadPool(10) → tiler.render_frame_tile                     [Phase 2]
            ├─ providers.download_product_source_frames
            │     └─ provider_{aws,himawari,eumetsat} → cache.source_path
            └─ renderer.SatelliteTileRenderer.from_sources                    [Phases 3–4]
                 ├─ _RENDERER_CACHE (8) / _NETCDF_CACHE (16)  — per-process
                 ├─ _load_source_raster → { GOES xr | ahi_hsd | seviri_nat | fci_nc }
                 └─ render_zoom_canvas → rio_reproject per channel → composites/colorize
rapid_worker → catalog.build_catalog + tiler.warm_frame_tiles_from_canvas
               → ProcessPoolExecutor (created PER FRAME today)                 [Phase 5]
meteosat_prefetch_worker → providers download only (no render; no changes)
```

Key measured facts driving the plan:

| Hotspot | Location | Cost today |
|---|---|---|
| Cache-**hit** validation | `service.py:292` → `cache.is_valid_tile_file` | full PNG decode + numpy alpha scan per hit; a high-zoom viewport is 20–40 requests |
| Supertile serial warps | `tiler.py:620` | radius 1 = 9 tiles, each its own 1×1 `render_zoom_canvas` = 9 × N-channel `rio_reproject`, all **before** the HTTP response |
| FCI per-channel chunk opens | `fci_nc.py:123` | ~40 `netCDF4.Dataset` opens × N channels (3-channel composite = ~120 opens of the same files) |
| AHI serial segment decompress | `ahi_hsd.py:227` | sequential read+bz2; all full-res uint16 grids held before decimation (~1.2 GB transient for FULLDISK B03) |
| lon/lat meshgrid always built for RGB | `renderer.py:180` | float64 meshgrid per canvas; current `GeoColor` and `GeoColorBlkMar` consume it |
| Process pool per frame | `tiler.py:549` (called per frame from `rapid_worker.py:175`) | Windows spawn re-imports matplotlib/rasterio/xarray each frame; with zoom-per-task both procs parse the same source |

---

## Phase 0 — Benchmark harness + reproducible baseline (no behavior change)

**Deliverables:** `satellite_v2/bench.py` (new), env-gated timing hooks in
`tiler.py`/`renderer.py`/`service.py`, baseline results committed under
`docs/perf/`.

**Status (2026-07-22):** implementation and the full baseline are complete
and committed at `a6f5f83`. Results are under
`docs/perf/2026-07-22-baseline/`. The matrix produced 27 runs / 135 samples;
all nine 3x3 golden blocks (81 PNGs) matched byte-for-byte.

### 0.1 Stage-timing instrumentation

- Gate: `WX_SATELLITE_V2_BENCH=1` env var. Off = zero overhead beyond an
  `if` (existing `print` timings in tiler/service stay untouched).
- Collector: a per-call timing dict threaded through `render_frame_tile` and
  `SatelliteTileRenderer.from_sources` (optional parameter or contextvar —
  decide at implementation; contextvar avoids touching the pickled
  process-pool initializer signature, prefer it).
- Stages recorded per tile/canvas render:
  `download_ms`, `parse_ms{channel}`, `warp_ms{channel}`, `composite_ms`,
  `encode_ms`, `write_ms`, `validate_ms`, `total_ms`, plus context
  (`sat_id, sector, product, frame_key, z, x, y, cache_status, pid`).
- Sink: JSONL appended to `cache/satellite/.bench/{run_id}.jsonl`
  (run_id = UTC timestamp). One line per tile/canvas op.

### 0.2 Bench CLI

`python -m satellite_v2.bench` with:

```
--sat goes19 --sector CONUS --product GeoColor [--frame FRAME_KEY]
--z 7 --tiles 3x3 [--center-lon -95 --center-lat 38]
--scenario cold-parse|warm-parse|hit   --repeat 5
--golden capture|compare --golden-dir <dir>
--summary            # print p50/p95 per stage from the run's JSONL
```

- Drives `service.resolve_tile` / `tiler.render_frame_tile` **in-process**
  (captures everything except HTTP). If `--frame` is omitted, picks the
  newest cataloged frame and **prints the frame_key it pinned** — every
  subsequent scenario/repeat in the run reuses that exact frame.
- Scenario definitions:
  - **cold-parse:** sources already on disk; the target frame's tile dirs
    purged; bench re-executed as a fresh process per repeat (kills the
    in-process renderer/NetCDF caches). Measures parse + warp + colorize +
    encode. *Never purges source dirs* — FCI re-download is ~800 MB and
    network variance would poison the numbers.
  - **warm-parse:** same, but repeats within one process (renderer cache
    hot). Isolates warp + colorize + encode.
  - **hit:** tiles on disk; measures `resolve_tile` hit-path cost
    (`validate_ms` is the Phase 1 target metric).
  - True cold-download is intentionally **not** a scenario (network variance
    + EUMETSAT fair use). `download_ms` still shows up whenever the live
    path happens to fetch.
- Purge safety: bench may delete **only**
  `cache/satellite/tiles/<render-version>/<sat>/<sector>/<product>/<frame_key>/`
  subtrees it targets. Nothing else. No source deletion, ever.
- End-to-end sanity (optional, not part of the recorded baseline): with the
  app running, `curl -s -o NUL -w "%{time_total}\n"` against
  `/api/satellite-v2/tile/...` for one hit and one miss per platform, noted
  in the summary file. (User preference: curl checks, no browser driving.)

### 0.3 Baseline matrix (captured 2026-07-22 before any optimization)

| # | sat | sector | product | z | why |
|---|-----|--------|---------|---|-----|
| 1 | goes19 | CONUS | Channel13 | 7 | single-channel scalar reference |
| 2 | goes19 | CONUS | GeoColor | 7 | 5-channel composite, worst live case |
| 3 | goes19 | FULLDISK | Channel13 | 5 | strided lazy-read path |
| 4 | goes19 | MESO1 | Channel02 | 8 | rapid sector, high zoom |
| 5 | himawari9 | FULLDISK | Channel13 | 5 | AHI multi-segment parse |
| 6 | himawari9 | JAPAN | Channel13 | 8 | AHI single-segment, high zoom |
| 7 | meteosat12 | FULLDISK | Channel13 | 5 | FCI chunk parse, single channel |
| 8 | meteosat12 | FULLDISK | NighttimeMicrophysics | 5 | FCI multi-channel — Phase 3's headline target |
| 9 | meteosat9 | FULLDISK | Channel13 | 5 | SEVIRI .nat parse |

All three scenarios × repeat 5 per row, 3×3 tile block (matches supertile
footprint). Rows 7–9 require Meteosat sources on disk — run while the
prefetch worker's keep-window (7 h) still covers the pinned frame.

### 0.4 Reproducibility rules

Satellite source data ages out (Meteosat keep-hours = 7; upstream buckets
prune), so *cross-day* reruns cannot pin the same frame. Reproducibility is
defined as:

1. **Within a phase:** before/after runs use the **same pinned frame_key**
   (captured in the manifest) on the same machine, same day. This is the
   comparison that gates each phase.
2. **Across days:** rerun the matrix with a fresh frame; compare stage
   *ratios* and p50s, not absolute deltas.
3. **Environment manifest** written next to each run's JSONL and committed
   with the summary: git SHA, dirty-file list, Python version, package
   versions (numpy, rasterio+GDAL, netCDF4, xarray, Pillow, pyproj), CPU
   model, RAM, relevant `WX_SATELLITE_V2_*` env overrides (expect none),
   pinned frame_keys per matrix row.
4. Machine at idle: OS scheduled tasks for the rapid/prefetch workers paused
   for the duration of a baseline run (they compete for CPU/disk), then
   re-enabled. Note in the manifest if any fired mid-run.

### 0.5 Golden tiles

- `--golden capture` renders the full matrix's tile blocks and stores PNGs +
  a SHA-256 index under the scratch golden dir (keyed by frame_key +
  render-version).
- `--golden compare` re-renders and diffs byte-for-byte (SHA match). Any
  mismatch = phase fails, investigate before landing.
- Goldens are frame-pinned and short-lived → **not committed to git**. Only
  the timing summaries and manifests go under `docs/perf/`.

### 0.6 Acceptance

- Matrix runs green end to end; JSONL + manifest + summary md committed under
  `docs/perf/2026-07-22-baseline/`.
- `WX_SATELLITE_V2_BENCH` unset ⇒ zero functional change (spot-check: tile
  responses identical, no new files).

Accepted locally 2026-07-22: all matrix scenarios completed with five samples;
the 135 raw records, matrix manifest, and summaries were consolidated under the
baseline directory. Warm runs contain no parse stages, cold downloads were
disk-cache hits, all 81 golden PNG comparisons passed, and a bench-disabled
MESO render matched its golden block without writing timing data.

---

## Phase 1 — Hit-path + correctness (service.py, renderer.py)

**Status (2026-07-22): complete and committed at `fc534ba`.** The LRU
fix, PNG signature hit path, and meshgrid gate are implemented. Four affected
GOES rows passed the isolated LRU golden rerun, and the final full matrix passed
81/81 byte-exact golden comparisons. Hit `validate_ms` p50 improved from
1.349–2.603 ms to 0.051–0.067 ms. Compact results are under
`docs/perf/2026-07-22-phase1/`.

1. **Commit 1 (standalone): `_NETCDF_CACHE` fix** — `OrderedDict` LRU,
   `move_to_end` on hit, close evicted/replaced datasets. Knob value (16)
   unchanged.
2. **Commit 2: stat + magic-sniff hit validation.** In
   `service.resolve_tile`, replace the per-hit `is_valid_tile_file` full
   decode with: `stat().st_size > 0` **and** first 8 bytes == PNG signature.
   Rationale: write path already guarantees content-validated atomic tiles
   (invariant documented at `cache.py:216`; all writers go through
   `_render_tile_to_target` / the canvas task, both validate-then-rename).
   Fall back to the full deep check (and re-render on failure) only when the
   sniff fails. Keep `is_valid_tile_file` itself unchanged — the miss/render
   paths still use it.
3. **Commit 3: gate the lon/lat meshgrid** (`renderer.py:180`) on products
   that consume it. Introduce a
   `COMPOSITES_REQUIRING_LONLAT` frozenset in `composites.py` next to the
   recipes so renderer doesn't hard-code product names. Implementation review
   found that post-plan ABI GeoColor Rayleigh correction also consumes solar
   geometry, so the set correctly contains `GeoColor` and `GeoColorBlkMar`.

**Verified:** full matrix is byte-identical; `hit` validation collapsed to
0.051–0.067 ms p50. The meshgrid allocation was removed from non-geographic
composites; Meteosat-12 Nighttime Microphysics `composite_ms` p50 moved from
13.893 to 12.280 ms. GeoColor deliberately retains its grid and pixels.

**Risk:** stat-only hits could serve a corrupt-on-disk PNG that a crashed
process… cannot actually produce (tmp+atomic-rename means partial files never
land on the final path). Residual risk is filesystem-level corruption; the
magic sniff catches the common truncation case. Accepted.

---

## Phase 2 — Live cold path: supertile canvas + respond-first (tiler.py, service.py)

**Status (2026-07-22): complete and committed at `8ee3a4b`.** The
single-canvas candidate failed its first golden comparison and was reverted:
all nine GOES Channel13 hashes changed, with real pixel differences. Per the
documented fallback, individual byte-stable warps remain, but only the
requested tile blocks the response. Eight neighbors run asynchronously through
the existing pool with per-path in-flight deduplication. The full live matrix
matched 81/81 goldens; headline cold p50 improved 11.9–14.9%. Results are under
`docs/perf/2026-07-22-phase2/`.

1. **Supertile as one canvas.** In `render_frame_tile`, replace the per-tile
   loop over `_live_supertile_coords` (9 × 1×1 canvases) with **one**
   `render_zoom_canvas` covering the supertile bounding box, then crop/save
   per tile (reuse the crop/validate/negative-marker logic from
   `_render_warm_zoom_canvas_task` — extract a shared helper rather than
   duplicating). `rio_reproject` computes each destination pixel
   independently on the same dst grid, so output must be byte-identical —
   golden compare is the proof; if any LSB diff appears, stop and
   investigate before landing (fallback: keep per-tile warps, still land
   step 2).
2. **Respond-first.** Render + persist the *requested* tile, return it, and
   submit the remaining supertile work to the existing
   `_ON_DEMAND_TILE_RENDER_POOL` without awaiting. Add a module-level
   in-flight set (`{tile_path}` + lock) in `service.py` so concurrent
   requests for neighbors don't duplicate renders (atomic writes already
   make duplicates *safe*, the set just avoids wasted work). Preserve the
   negative-marker and stats contracts; `supertile_*` stats fields may
   become asynchronous/partial — keep the keys, document the semantics in
   the docstring.

**Verify:** golden compare; `cold-parse` scenario p50 for rows 2/5/8 —
expect first-tile latency ≈ 1/(supertile count) of baseline plus one canvas
warp; confirm neighbors appear as hits within ~1 s after (bench gets a
`--settle-ms` flag to poll for them).

**Sequencing note:** step 1 and step 2 are independently landable commits;
step 1 alone already cuts N-channel warps 9× per supertile.

**Outcome:** step 1 was rejected by the golden gate and is not present. Step 2
landed using the explicit per-tile fallback. `bench.py` now supports
`--respond-first --settle-ms` so requested latency and eventual neighbor
identity remain reproducible.

---

## Phase 3 — Parse layer: multi-channel single pass + AHI threading (fci_nc.py, seviri_nat.py, ahi_hsd.py, renderer.py)

**Status (2026-07-22): committed at `29b83b6`.** FCI now
loads multiple requested channels in one chunk pass while retaining independent
grid metadata. AHI uses four decode workers and stitches decimated calibrated
strips instead of retaining all full segment buffers. The full matrix passed
81/81 golden comparisons. AHI cold p50 improved 49.6% from Phase 2; FCI
Nighttime Microphysics improved 43.2%. Compact results are under
`docs/perf/2026-07-22-phase3/`.

1. **FCI:** add `load_fci_rasters(chunk_files, channels: Sequence[str]) ->
   dict[str, FciRaster]` — one pass over the CHK-BODY files, extracting all
   requested channels per open. Keep `load_fci_raster` as a one-channel
   wrapper (used by `service.get_frame_bounds` via `_load_source_raster`).
   Renderer `_load_renderer_uncached` groups required channels by loader
   type and calls the batch loader once for FCI.
2. **SEVIRI:** inspect `seviri_nat.py` first (not yet read this session). If
   per-channel loads re-read/parse the whole `.nat`, add the same batch API;
   if it already seeks per-channel records cheaply, leave it (the Phase 0
   `parse_ms{channel}` numbers decide — don't refactor what isn't hot).
3. **AHI:** parallelize segment read + bz2 decompress across a small thread
   pool (bz2 releases the GIL), and restructure `load_ahi_raster` to
   decimate+calibrate each segment as it completes and place it into the
   output grid immediately, dropping the full-res counts array — instead of
   holding all 10 segments' full-res grids until stitching. Stride comes
   from the first parsed segment's `n_cols` (all segments share it;
   mismatch still raises as today). Pool size: hardcode a small constant
   (e.g. 4) in `ahi_hsd.py` with a comment — it is a parse-internal detail,
   not a config knob. **Do not** touch the space-noise mask, the stride cap,
   or the S01-derived-segment logic (2026-07-02 rebuild — see memory).
4. GOES loader unchanged (lazy hyperslab already correct).

**Verify:** golden compare (calibration math untouched ⇒ byte-identical);
`cold-parse` rows 5/7/8: expect row 8 (`NighttimeMicrophysics` on FCI)
`parse_ms` ≈ ⅓ of baseline, row 5 (AHI FULLDISK) parse improved and peak
memory (log `tracemalloc`/working-set in bench) reduced.

**Verified:** calibration output remained byte-identical across all 81 golden
tiles. AHI parse p50 moved from 2314.232 to 1120.945 ms; FCI multi-channel
parse p50 moved from 7279.744 to 4047.660 ms. The implementation structurally
bounds AHI full segment buffers to four workers, but no numeric memory claim is
made because Phase 2 did not capture a comparable working-set baseline.

---

## Phase 4 — Shared source-raster cache (renderer.py)

**Status (2026-07-22): complete locally, checkpoint commit pending.** The
approved byte-budgeted LRU is implemented with a 4096 MB default and
`WX_SATELLITE_V2_SOURCE_RASTER_CACHE_MB` override. Source eviction also removes
dependent renderer entries, so inactive renderer references cannot bypass the
byte ceiling. The full matrix passed 81/81 golden comparisons. On the pinned
Meteosat-12 frame, Channel13 followed by NighttimeMicrophysics reused Channel13
by identity and held 354.797 MB across three unique rasters instead of 473.062
MB across four independent references, saving 118.266 MB and one parse.
Compact results are under `docs/perf/2026-07-22-phase4/`.

Today, products sharing a channel (GeoColor/TrueColor share C01–C03;
Channel13 scalar / NighttimeMicrophysics share C13) each hold their own copy
of the same channel grid inside separate `_RENDERER_CACHE` entries, and
re-parse it on renderer-cache miss.

1. Introduce a per-process LRU keyed
   `(resolved_path, mtime_ns, size, source_channel, max_grid)` →
   `SourceRaster`, sitting **under** the renderer cache.
   `SatelliteTileRenderer` entries become thin (dict of refs), so
   `SATELLITE_V2_RENDERER_CACHE_SIZE = 8` keeps its meaning and value.
2. **Budget the raster LRU in bytes, not entries** (`nbytes` of held grids),
   because entries span 55 MB (SEVIRI) to ~470 MB (strided GOES/AHI
   FULLDISK vis). Sizing so worst-case total ≤ what today's 8 renderer
   entries could hold ⇒ memory strictly not-worse, dedup makes typical usage
   better.
3. **Decision resolved:** the user approved the new byte-budget config knob.
   `SATELLITE_V2_SOURCE_RASTER_CACHE_MB` defaults to 4096 MB and is overridden
   with `WX_SATELLITE_V2_SOURCE_RASTER_CACHE_MB`; `0` disables source caching.

**Memory accounting (for the review):** `_NETCDF_CACHE` holds lazy handles
(MB-scale, unaffected). The byte weight lives here: GOES FULLDISK C02
strided → 10848² float32 ≈ 470 MB; a GeoColor FULLDISK renderer ≈ 1.6 GB
today in one entry. Phase 4 stores each channel once.

**Verify:** golden compare; `warm-parse` scenario after browsing
Channel13 → NighttimeMicrophysics on the same frame shows zero re-parse;
working-set comparison in the bench summary.

**Verified:** all 81 golden tiles are byte-identical. The pinned FCI sequence
made one scalar Channel13 batch call, then loaded only Channel07/Channel15 for
NighttimeMicrophysics. Four renderer references resolve to three unique
rasters; measured grid weight fell from 473.062 MB without deduplication to
354.797 MB with the shared cache. Focused Satellite tests pass 33/33 and the
full suite passes 105 tests plus 42 subtests.

---

## Phase 5 — Warm-path pool efficiency (rapid_worker.py, tiler.py)

1. **Pool reuse:** add an optional `pool` parameter to
   `warm_frame_tiles_from_canvas` (default `None` = current per-call pool,
   so other callers are untouched). `rapid_worker` creates **one**
   `ProcessPoolExecutor(max_workers=SATELLITE_V2_RAPID_WORKER_TILE_WORKERS)`
   per run and passes it through all frames/jobs; owns shutdown. Kills the
   per-frame Windows spawn+import cost. Worker-count knob untouched;
   ownership stays in the worker module (boundary rule).
2. **Skip the trailing catalog rebuild** in `_warm_one_job`
   (`rapid_worker.py:198`) when the job rendered 0 tiles and had 0 errors —
   nothing changed on disk, the pre-warm catalog is still accurate.
3. **Measured decision — task granularity:** today's task-per-zoom means
   both pool processes parse the same frame's source in parallel (duplicate
   parse; per-process renderer caches don't help). If Phase 0/3 numbers show
   parse still dominating warm runs, merge a frame's zooms into one task
   (one process parses once, renders both canvases) and let parallelism come
   from consecutive frames pipelining through the reused pool. Implement
   only if the duplicate parse is visible in `parse_ms` totals.

**Verify:** rapid worker wall-clock per run (its own log already prints
elapsed) before/after on the same warmed-cache state; tiles byte-identical
(golden on a MESO/JAPAN frame); `.lock`/sentinel behavior unchanged.

---

## Phase 6 (optional, measure-first) — GDAL warp threads

`rio_reproject(num_threads=N)` chunks the destination internally; output is
deterministic. Candidate **only** for the big warm-path canvases (rapid
worker: ~7000×5600 px for JAPAN z8), never the live per-tile path (would
oversubscribe against the 10-thread live pool). Gate behind
`WX_SATELLITE_V2_WARP_THREADS` (new env-only flag, default 1 = today).
Implement only if Phase 5's numbers show warp dominating warm runs.

---

## Execution order & session checklist

1. Phase 4 byte-budget knob approved; decide whether Phase 6 stays in scope
   only after Phase 5 measurements.
2. Phase 0 complete and committed at `a6f5f83`; baseline is under
   `docs/perf/2026-07-22-baseline/`.
3. Phase 1 committed at `fc534ba`; results are under
   `docs/perf/2026-07-22-phase1/`.
4. Phase 2 committed at `8ee3a4b`; results are under
   `docs/perf/2026-07-22-phase2/`.
5. Phase 3 committed at `29b83b6`; results are under
   `docs/perf/2026-07-22-phase3/`.
6. Phase 4 complete locally; commit the shared raster-cache slice and results
   under `docs/perf/2026-07-22-phase4/`, then begin Phase 5. Each is gated on: golden byte-identity, the
   phase's target metric moving, and a clean run of the full matrix.
5. After each phase: commit with the phase number in the message; update the
   `docs/perf/` summary table with before/after p50s.

Rollback: every phase is a small commit on top of a green baseline —
`git revert` the phase commit; no cache invalidation needed since tiles are
never format- or pixel-changed.
