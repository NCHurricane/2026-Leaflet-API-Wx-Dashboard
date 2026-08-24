# Meteosat Satellite Pipeline — Latency Overhaul Plan

Prepared 2026-08-11. Scope: the Meteosat (EUMETSAT) path of `satellite_v2` and the
Satellite page frontend. Companion/predecessor:
`docs/archive/satellite-render-optimization-plan.md` (executed 2026-07-22, Phases 0–5
complete).

---

## 1. Context

The Meteosat workflow on the Satellite page is slow from click to imagery on the map.
Measured per-tile latency from the committed baseline
(`docs/perf/2026-07-22-baseline/baseline-summary.md`):

| target | cold p50 | warm p50 | hit p50 |
|---|---:|---:|---:|
| meteosat12 FULLDISK Channel13 z5 | 2996 ms | 661 ms | 1.7 ms |
| meteosat12 FULLDISK NighttimeMicrophysics z5 | 8771 ms | 1338 ms | 2.7 ms |
| meteosat9 FULLDISK Channel13 z5 | 646 ms | 358 ms | 2.0 ms |

Cold stage split for meteosat12 Channel13: `parse 3347 ms` + `warp 516 ms` + `validate 94`
+ `encode 30` + `composite 7` + `write 3`.

A prior six-phase effort already harvested every optimization achievable under a
**byte-identical pixel gate**. That gate is now lifted by explicit user decision, which
reopens the two structural wins it blocked.

**Intended outcome:** Meteosat first paint becomes a cache hit in the common case, and the
underlying render cost drops enough that genuinely cold frames are seconds faster.

## 2. Orientation — how the pipeline works today

```
frontend/pages/satellite/satellite-page.js   selection → reloadFrames()
  └─ satellite-engine.js  GET /api/satellite-v2/catalog        (blocking, serial)
  └─ satellite-anim.js    L.tileLayer → GET /api/satellite-v2/tile/{z}/{x}/{y}

routes/satellite_v2.py
  └─ service.resolve_tile_async
       ├─ (hit)  stat + PNG magic sniff                         ~0.05 ms
       └─ (miss) wait pool (10) → render pool (10) → heavy_render_slot (1!)
            └─ tiler.render_frame_tile
                 ├─ providers.download_product_source_frames
                 │    └─ provider_eumetsat  (OAuth2 → OpenSearch → download)
                 └─ renderer.SatelliteTileRenderer.from_sources
                      ├─ _SOURCE_RASTER_CACHE  (4096 MB byte-budgeted LRU)
                      ├─ seviri_nat.py  (.nat memmap)  |  fci_nc.py  (40 NetCDF chunks)
                      └─ render_zoom_canvas → rio_reproject per channel → colorize → PNG
```

Key characteristics:

- **Source files are whole-bundle, not per-channel.** SEVIRI = one `.nat` (~270 MB) holding
  12 channels. FCI = 40 `CHK-BODY` NetCDF chunks (~574 MB measured on disk) per frame.
  Prefetching any product warms every channel.
- **Tiles** are 256 px PNGs at
  `cache/satellite/tiles/{render_version}/{sat}/{sector}/{product}/{frame_key}/{z}/{x}/{y}.png`,
  published atomically (tmp + `os.replace`), with `.png.empty.json` negative markers for
  blank tiles.
- **Render versions** are per-platform-family strings; bumping one cold-starts that
  family's tile cache.
- **Workers are presence-driven, not scheduled.** `tools/install_tasks.ps1` explicitly
  *unregisters* the old Windows tasks. `service._activate_satellite_accelerator` starts
  background work from the catalog request while the page is open.

## 3. Root causes (all verified in code)

1. **Meteosat-9/12 FULLDISK tiles are never prewarmed.** `meteosat_prefetch_worker.py`
   downloads sources only; `rapid_worker` covers `meteosat11/RSS` but not the two disks
   (`config/satellite_v2_config.py:617-663`). Every new 15-min frame's first viewer pays
   the full cold cost.
2. **One full-source-grid GDAL warp per 256×256 tile.** `render_tile` is literally a 1×1
   canvas (`satellite_v2/renderer.py:143`), so a 5568² → 256² warp costs ~516 ms and the
   3×3 supertile pays it nine times.
3. **The FCI stride cap is inert.** `state.stride = max(1, end_col // max_grid)` with
   `end_col` 5568 (IR) or 11136 (VIS) and `max_grid` 10848 yields stride 1 in both cases
   (`satellite_v2/fci_nc.py:154`). Full-resolution grids are always materialized — 124 MB
   per IR channel, 496 MB per VIS channel — even at the default preset zoom 4 where they
   are ~3× oversampled.
4. **All renders are serialized to one at a time.** `WX_HEAVY_RENDER_SLOTS` defaults to 1
   and the semaphore is shared with Radar (`app_core/render_budget.py:16`), on a 24-core /
   128 GB machine. The 10-thread render pool is decorative.
5. **The frontend re-requests the whole viewport after 2.5 s** with a cache-busting `t`
   param (`frontend/pages/satellite/satellite-anim.js:289`, `setUrl(..., false)` → full
   `redraw()`). Tiles are served `immutable`, so the bump guarantees a total cache miss —
   and it fires precisely when Meteosat is cold, doubling load at the worst moment.

Secondary waste, same investigation:

- `satellite-anim.js:115` — `minNativeZoomForSector()` returns 5 for `RSS`, whose preset
  opens at zoom 4, so Leaflet clamps `_tileZoom` to 5 and requests ~4× the needed tiles.
- `satellite-anim.js:241` — retained frame layers stay **attached** at opacity 0; with
  `updateWhenIdle: false` every one re-requests tiles on pan (up to 72 layers).
- `service.py:481` — `_catalog_frame_for_tile` re-reads the catalog JSON from disk on
  **every** tile miss.
- `routes/satellite_v2.py:171` — off-disk 1×1 transparent tiles are `no-store`, so they are
  re-fetched on every pan, zoom, and redraw.
- `provider_eumetsat.py:208-224` — OpenSearch sends `c: 100` with no pagination; a 12-hour
  meteosat11/RSS window is ~144 products and silently truncates.
- `provider_eumetsat.py:243-249` — `_fci_feature_for_product` re-runs a full 12-hour search
  per cold FCI download.
- `provider_eumetsat.py:165-172` — no retry for 5xx, timeouts, or connection errors; only a
  single 401 refresh.

## 4. Decisions taken (user-confirmed)

- **Render-version bump is allowed**; pixel output may change.
- **Prewarm tiles while the satellite page is open** (presence-driven), not 24/7.
- **All three Meteosat targets in scope**: meteosat12 FULLDISK, meteosat9 FULLDISK,
  meteosat11 RSS.
- **Raise render concurrency with a memory guard**, respecting the 2026-06-05 OOM history
  (a FULLDISK Channel02 prewarm at 0.5 km resolution exhausted virtual memory and froze the
  host; see `MEMORY.md`).

## 5. Constraints — do not violate

Carried forward from the archived plan and still binding:

- Module boundaries: routes in `routes/`, orchestration in `satellite_v2/service.py`,
  render in `renderer.py`/`composites.py`, tile planning/warming in `tiler.py`, scheduling
  in the worker modules. No mixing (see `docs/architecture.md`, `docs/patterns.md`).
- Do not change: worker `.lock` / freshness sentinel contracts; the FCI `manifest.json`
  format (shared by `provider_eumetsat._read_fci_manifest` and
  `meteosat_prefetch_worker._frame_sources_cached` — a format change breaks both sides);
  the negative-tile-marker contract; the AHI space-noise mask and S01-derived-segment logic;
  `Image.MAX_IMAGE_PIXELS = None` in `composites.py`.
- `service.get_frame_bounds` imports the private `renderer._load_source_raster` — keep a
  single-channel entry point alive.
- `tiler._initialize_warm_tile_worker` pickles renderer init args across the process
  boundary — new caches must stay process-local.
- **Grid caps may only ever shrink, never grow.** They are the OOM guard.
- EUMETSAT fair use: FCI download workers must not exceed 4.
- The user tests manually in the browser. Verify with syntax checks, pytest, bench, and
  `curl` — do not drive a browser.

---

## Phase 0 — Re-baseline and replace the golden gate

The existing harness (`satellite_v2/bench.py`, `satellite_v2/_bench_timing.py`) is reused
as-is; only the comparison mode changes.

- Capture a fresh baseline for matrix rows 7/8/9 plus a new `meteosat11/RSS/Channel13 z6`
  row, all three scenarios × 5 repeats.
- Add a **tolerance mode** to `--golden compare`: instead of SHA equality, report max
  per-channel absolute delta and the fraction of differing pixels. SHA compare stays the
  default so GOES/Himawari rows keep their strict gate where output is unchanged.
- Gate thresholds for later phases: canvas rendering must stay ≤2/255 max delta (pure
  resampling difference); decimation is reviewed visually instead.

Commit baseline JSONL + manifest + summary under `docs/perf/<date>-meteosat-phase0/`.

**Note:** Meteosat sources age out (`KEEP_HOURS` = 7). Rows 7–9 require sources on disk, so
run the baseline while the prefetch keep-window still covers the pinned frame. Cross-day
reruns compare *ratios*, not absolute deltas.

## Phase 1 — Remove pure waste (no pixel change, no version bump)

Independent of everything else and individually landable.

**`frontend/pages/satellite/satellite-anim.js`:**
- Drop the `tileRefreshToken` bump from the progressive redraw (`:284-292`). Keep the retry
  if genuinely needed, but reuse the same URL so browser-cached tiles and in-flight requests
  survive. Same for the `tileerror` retry path (`:207-221`).
- Fix `minNativeZoomForSector` (`:115`) — derive the floor from the frame's own min zoom
  rather than the hardcoded per-sector table that mismatches RSS.
- Pass `bounds` to the tile layer from the platform's disk extent so off-disk tiles are
  never requested.
- **Rejected after owner smoke:** do not detach completed inactive frame layers.
  That optimization reintroduced the repeated all-platform animation flash, and
  a full replacement-readiness gate alone did not fix it. Preserve the mounted
  opacity-0 layer pool and transfer visible ownership only after replacement
  readiness. Any later pan-request optimization must retain that visual
  contract and pass owner browser smoke before landing. The restored pool passed
  owner re-smoke.
- Coalesce manual slider drag events to the resting frame. Each displayed
  foreground frame also carries a page-local generation through tile requests;
  when a newer frame is selected, queued work from the superseded frame loses
  ownership before entering the heavy render slot. Already-started renders may
  finish and keep their immutable cache artifacts.

**`frontend/pages/satellite/satellite-page.js`:**
- Suppress the redundant `selection/release` POSTs fired by `clearFrames()` during a
  platform → sector → product click-through (`:416`); the second releases a selection about
  to be re-acquired milliseconds later.
- Don't flip the sidebar to the success message (`:508-512`) while the map is still blank —
  hold the loading state until `onFrameVisible` fires.

**Backend:**
- Memoize `_catalog_frame_for_tile` (`service.py:481`). Key on
  `(sat, sector, channel, render_version, catalog mtime_ns)`.
- Make the 1×1 transparent off-disk response cacheable (`routes/satellite_v2.py:171`) — it
  is stable for a given `frame_key`.

## Phase 2 — Canvas rendering + zoom-aware decimation (pixel change; version bump)

The core of the overhaul. Both changes land together because both alter pixels and share one
version bump.

**2a. One warp per supertile.** In `render_frame_tile` (`tiler.py:530-590`), replace the
loop of nine 1×1 `render_zoom_canvas` calls with a single `render_zoom_canvas` over the
supertile bounding box, then crop per tile. **Reuse the existing crop / content-check /
negative-marker / atomic-publish logic** already in `_render_warm_zoom_canvas_task`
(`tiler.py:250-330`) by extracting it into a shared helper rather than duplicating it.

> This exact idea was implemented and reverted on 2026-07-22 *solely* because it failed a
> byte-identical golden gate ("all nine GOES Channel13 hashes changed, with real pixel
> differences"). The cause is GDAL's approximate warp transformer being fit over a different
> destination grid size. It is now permitted.

**2b. Zoom-aware source grid cap.** Extend `_source_raster_grid_cap` (`renderer.py:297`) to
take the destination zoom and return `min(platform_cap, zoom_derived_cap)` — it can only
ever shrink the grid, never grow it, so the OOM guard is strengthened rather than loosened.
Choose the stride as a power of two that keeps ~2× oversampling relative to the destination
pixel scale, so z1–4, z5–6, and z7+ resolve to distinct caps.

The source-raster cache key already includes the grid cap (`renderer.py:307-315`), so the
levels coexist as separate LRU entries with no key redesign. Worst-case memory is ~1.33×
native (native + ¼ + ¹⁄₁₆), while the common low-zoom path holds a fraction of today's
footprint.

Keep `_load_source_raster`'s current signature working (new arg defaults to `None` =
today's behavior) so `service.get_frame_bounds` is unaffected.

**2c. FCI hyperslab pushdown.** In `load_fci_rasters` (`fci_nc.py:178-185`), read the
strided slice directly from `measured.variables["effective_radiance"]` instead of
materializing the full chunk and then slicing. The GOES loader already does this
(`renderer.py:982-990`) — follow that pattern. Measure first; land only if it moves
`parse_ms`.

**2d. Version bump.** `SATELLITE_V2_RENDER_VERSION_METEOSAT12` (`products-fci4` →
`products-fci5`) plus the shared `SATELLITE_V2_RENDER_VERSION` and the GK2A/GMGSI/Himawari
versions, since 2a/2b touch the shared render path for every platform. **This is nearly free
today** — the entire tile cache is 21 MB and the `goes19`/`himawari9` directories are empty,
so a global bump discards almost nothing. Re-measure before assuming this still holds.

### Phase 2 implementation status — 2026-08-24

Phase 2a, 2b, and 2d are implemented in the current uncommitted working tree. Live
neighbor rendering now performs one bounded canvas warp and uses the same crop,
content-check, negative-marker, validation, and atomic-publication helper as canvas
warming. Source raster cache keys include the destination-zoom cap: z1–4 use 2048,
z5–6 use 4096, and z7+ retain the existing platform cap. SEVIRI and GMGSI retain their
native loader behavior. The global platform namespaces advance to `products-v9`,
`products-ami3`, `products-gmgsi2`, `products-ahi5`, and `products-fci5`. Immediately
before the bump, the retained tile namespaces measured 2488 files / 111.62 MB; source
downloads are outside those render-version namespaces and remain reusable.

Phase 2c was measured and deliberately not retained. Direct strided FCI hyperslab reads
did not improve parse time and were slower on the pinned three-channel frame than reading
each chunk contiguously and decimating in memory. The final pinned z5 cold p50s without
the hyperslab change are 2915 ms for Meteosat-12 Channel13 and 3856 ms for
NighttimeMicrophysics, versus 3401 ms and 5750 ms in the archived `d1451f9` tree.
Warm p50s fall from 546 ms to 179 ms and from 1423 ms to 375 ms. Meteosat-9 Channel13
cold/warm p50s fall from 606/327 ms to 469/179 ms.

The no-decimation Meteosat-12 z7 golden comparison stays within max channel delta 2 for
all nine tiles. Low-zoom decimation intentionally changes more pixels and remains an
owner visual gate. Shared-canvas rendering can also move thin colored reference-overlay
pixels by a pixel even where the imagery delta is small; this is why the known
byte-identical gate cannot apply to Phase 2. The automated gate passes 631 Python tests
plus 42 subtests, all 48 Node tests, repo-wide Ruff/compile, and diff checks. Owner smoke
passed on 2026-08-24 for Meteosat-12 Channel13 and NighttimeMicrophysics at
z3/z4/z5/z7, including the requested current/past-frame, seam, detail, transition, and
console checks. Phase 2 is accepted and ready for its independent commit; Phase 3 remains
separately gated.

## Phase 3 — Memory-guarded render concurrency

Replace the satellite side of the single global slot with **byte-budgeted admission**, in
`app_core/render_budget.py` alongside the existing `heavy_render_slot`:

- New `satellite_render_slot(estimated_bytes)` admits concurrent renders while the sum of
  in-flight estimates stays under `WX_SATELLITE_RENDER_BUDGET_MB` (default sized well under
  the 128 GB available, e.g. 16–24 GB).
- The estimate comes from source grid dimensions × dtype × channel count — data the renderer
  already has before it allocates.
- A single render larger than the budget still runs alone, so a full-resolution FULLDISK
  visible channel can never be co-scheduled. This is a **stronger** guarantee than a slot
  count, which is what actually failed in June 2026.
- Radar keeps `heavy_render_slot` at its current value; the two stop contending.

## Phase 4 — Presence-driven Meteosat tile warming

Turn the cold path into a cache hit for the frames a user is actually looking at.

- **Per-platform disk bounds.** `SATELLITE_V2_SECTOR_BOUNDS["FULLDISK"]` is `-180..+20`
  (`config/satellite_v2_config.py:719`) — GOES-East-centric. Meteosat-9's disk
  (`lon_0` 45.5°E) lies almost entirely outside it, and Meteosat-12 (`lon_0` 0.0) only
  partly inside. Derive warm bounds per platform from the existing `lon_0` field
  (`config/satellite_platforms.py:70-97`) rather than the shared sector box. This bug is
  latent today only because Meteosat is never warmed.
- **Chain the accelerators.** `_activate_satellite_accelerator` (`service.py:279-338`)
  returns after the first matching branch, so Meteosat FULLDISK only ever gets
  `meteosat-source`. Add a `meteosat-tiles` stage that runs after the source prefetch for the
  *currently selected product*, warming z1–z6 over the platform's disk bounds.
- **Reuse existing machinery**: `warm_frame_tiles_from_canvas` (`tiler.py:334`) with a reused
  `ProcessPoolExecutor` (the archived Phase 5 added `pool` passthrough and measured a 76%
  win from reuse). One canvas warp per zoom replaces ~1000 per-tile warps per frame.
- New `SATELLITE_V2_METEOSAT_TILE_WARM_*` config block (frames, zooms, workers, fresh
  window), kept separate from the rapid-worker knobs, matching how the source-prefetch block
  is already separated.
- Warming must respect `should_continue` / selection ownership so it stops when the user
  navigates away, and must yield to live tiles via the existing `_wait_for_live_tile_idle`
  (`service.py:138`).
- Prune warmed tiles alongside sources; `SATELLITE_V2_METEOSAT_PREFETCH_KEEP_HOURS` (7 h)
  currently prunes sources only.

## Phase 5 — EUMETSAT fetch path

Addresses the "obtain" half of the request; largely independent of Phases 2–4.

- **Pagination.** `_search_products` sends `c: 100` with no paging
  (`provider_eumetsat.py:208-224`). Page until the requested window is covered.
- **Kill the duplicate search.** `_fci_feature_for_product` (`:243-249`) re-runs a full
  12-hour search per cold FCI download. Carry the feature forward from `list_recent_frames`,
  or cache the search response per `(collection, hours)` with a short TTL.
- **Retry/backoff.** Add bounded exponential backoff for 5xx, timeouts, and connection
  errors (`:165-172` currently handles only a single 401 refresh).
- **Download parallelism.** `_FCI_DOWNLOAD_WORKERS` is 2 (`:85-90`) for a 574 MB / 40-chunk
  frame. Raise the default to 4 — the documented EUMETSAT fair-use ceiling — via the existing
  `WX_EUMETSAT_DOWNLOAD_WORKERS` override. No higher.

---

## Files to be modified

| Area | Files |
|---|---|
| Render core | `satellite_v2/renderer.py`, `satellite_v2/tiler.py`, `satellite_v2/fci_nc.py` |
| Orchestration | `satellite_v2/service.py` |
| Fetch | `satellite_v2/provider_eumetsat.py` |
| Warming | `satellite_v2/meteosat_prefetch_worker.py` (or a new tile-warm entry point) |
| Concurrency | `app_core/render_budget.py` |
| Config | `config/satellite_v2_config.py`, `config/satellite_platforms.py` |
| Frontend | `frontend/pages/satellite/satellite-anim.js`, `frontend/pages/satellite/satellite-page.js` |
| Bench | `satellite_v2/bench.py` |

## Verification

Per phase, before moving on:

1. **Bench** — rerun the Meteosat rows against the same pinned `frame_key`, same day, same
   machine; record p50/p95 per stage:
   ```bash
   python -m satellite_v2.bench --sat meteosat12 --sector FULLDISK --product Channel13 --z 5 --scenario cold-parse --repeat 5 --summary
   ```
2. **Golden compare** — SHA-strict for the GOES/Himawari rows (must stay byte-identical),
   tolerance mode for the Meteosat rows in Phase 2.
3. **Tests** — focused first, then the full suite (last known green: 109 tests + 42 subtests):
   ```bash
   python -m pytest tests/test_satellite_meteosat.py tests/test_satellite_rapid_worker.py tests/test_satellite_bench.py tests/test_satellite_product_registry.py -q
   ```
   ```bash
   node --test tests/satellite_animator.test.mjs
   ```
4. **Live timing headers** — with the app running, confirm the stage split via response
   headers rather than browser driving:
   ```bash
   curl -s -o NUL -D - "http://127.0.0.1:8000/api/satellite-v2/tile/5/17/11?sat_id=meteosat12&sector=FULLDISK&channel=Channel13&frame_key=<KEY>"
   ```
   Check `X-Satellite-V2-Cache`, `-Download-Ms`, `-Decode-Ms`, `-Render-Ms`.
5. **Manual visual review (user)** — Himawari-9 Target and the retained no-flash
   animation pool passed. Before Phase 2, repeat the GOES-19 Meso 2 scrub-ahead
   reproduction in Satellite and Workspace: while cold frames animate, drag across
   unrendered frames and release; the resting frame must resume rendering without a
   Play-button nudge and Workspace must retain no-flash transitions.
   After Phase 2, compare Meteosat-12 Channel13 and NighttimeMicrophysics at z3 / z4 / z5 /
   z7 to confirm the decimation is invisible at the zooms it applies to.
6. **Memory watch** — during Phase 3 and the first Phase 4 warm run, watch the Python process
   working set to confirm the byte budget holds. This is the OOM-history guardrail.

One commit per phase minimum, each leaving the pipeline fully runnable, so any phase can be
reverted independently. Update `docs/perf/` with before/after p50s as each lands.

## Risks

- **Phase 2 changes pixels for every platform**, not just Meteosat, because the warp path is
  shared. Mitigated by the near-empty tile cache making a global version bump cheap, and by
  the tolerance gate bounding the difference to sub-pixel resampling.
- **Phase 3 touches the exact mechanism implicated in the June 2026 freeze.** Mitigated by
  budgeting bytes rather than slots, so an oversized render still runs alone.
- **Phase 4 adds background CPU while the satellite page is open.** Bounded by the existing
  presence lease and live-tile-idle gating; it stops when the user leaves the page.
- **Phase 5 touches EUMETSAT fair use.** Download workers stay at the documented ceiling of 4.
