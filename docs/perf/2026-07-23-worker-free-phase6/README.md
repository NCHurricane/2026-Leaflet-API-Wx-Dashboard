# Worker-Free Phase 6 Evidence

Date: 2026-07-23, browser follow-up 2026-07-24

Scope: targeted on-demand Surface gradients, last-complete serving, shared
observation snapshots, daily station metadata, provider budgets, and bounded
gradient rendering.

## Implementation status

Phase 6 is complete. Its automated gate passes. The first user-owned
browser smoke otherwise passed but exposed an unmasked client-canvas fallback
while the masked PNG rendered. The correction was implemented, and the
user-owned re-smoke passed for every CONUS and WORLD product on 2026-07-24.
Phase 6 is closed and Phase 7 is authorized next.

- `/api/data/surface-gradient` submits only
  `("surface", "gradient", region, product)` for `CONUS` or `WORLD`.
- A stale complete image and metadata remain available while observations warm
  or the selected gradient renders. Cold responses report explicit warming
  state instead of returning the former cache-only 404.
- Surface observation refresh and gradient work reuse one process snapshot per
  region inside one minute.
- AviationWeather station metadata is cached for one day on disk and in
  process. IEM discovery/data fallbacks acquire the coordinator's shared IEM
  provider budget.
- Surface gradients use `WX_SURFACE_GRADIENT_SLOTS` with a one-slot default,
  independently of the Radar/Satellite `WX_HEAVY_RENDER_SLOTS` budget.
- The Surface client polls `refreshing` responses and replaces its cached
  gradient metadata when the requested artifact completes.

## Automated validation

- `tests/test_worker_free_phase6_surface.py` passes 24/24.
- The test covers stale serving, observation-stage warming, exact
  region/product submission, shared concurrent snapshots, direct provider
  budgeting, separate render-slot serialization, and every one of the 18
  supported product/region artifact paths.
- The 18 artifact-path cases execute the real interpolation, RGBA conversion,
  and atomic PNG/metadata publication on isolated reduced scratch grids. They
  do not claim full-resolution performance.
- The broader Phase 6, Surface migration, and coordinator run passes 37/37.
- Correction-focused validation passes 46/46, including the contract that
  warming suppresses the unmasked client-canvas fallback.
- Focused Ruff, changed-Python compilation, Surface JavaScript syntax, and
  `git diff --check` pass.
- Full pytest reaches 214 passing tests plus 42 subtests. Its only failure is
  the pre-existing Workspace assertion that still expects the concurrently
  removed `WORKSPACE_REGION_BOUNDS`.

## Browser finding and remaining gate

The user found no product failures and reported similar generation time for
each product. A representative CONUS `wind_speed` render used 2,246 stations
and completed in 4.2 seconds. Similar timing is expected because every product
uses the same output grid, interpolation, land mask, and PNG encoding path.

During warming, the page first displayed the unmasked client-canvas
interpolation, then changed to the masked server PNG about three seconds later.
The mask was not being applied in a second server stage: it was already baked
into the atomically published PNG. The first image came from the older browser
fallback because the polling promise did not repaint the last-complete metadata
until the new PNG finished.

The client now marks a server gradient as pending, suppresses the canvas
fallback during that state, and repaints immediately when the first
last-complete masked metadata response arrives. A truly cold request shows
observations alone until the masked PNG is ready. The corrected user-owned
browser re-smoke passed for every product in both CONUS and WORLD. No unmasked
warming gradient or other regression was observed; the Phase 6 browser gate
passed.
