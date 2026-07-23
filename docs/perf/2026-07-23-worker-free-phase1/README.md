# Worker-free Phase 1 coordinator gate

Status: passed 2026-07-23.

Implemented:

- bounded executor and queue with actual-key deduplication;
- provider concurrency and minimum-request intervals;
- 90-second request-presence leases;
- exponential backoff with credential-safe state reporting;
- periodic state pruning and six-hour application-owned cache cleanup;
- unique-temp atomic JSON/text publication;
- FastAPI lifespan startup and graceful shutdown;
- cold/stale Surface and stale WPC coordinator migration;
- one region-level Surface observation fetch publishing every product cache;
- truthful `idle` state for presence-only coordinator records;
- explicit single-process enforcement until persistent leases exist.

Gate evidence:

- ten simultaneous direct submissions executed one refresh;
- simultaneous mixed-product Surface requests for one region executed one
  refresh, which published every product cache;
- a failed refresh entered backoff and polls did not rerun it;
- provider jobs honored concurrency and minimum spacing;
- the previous cache remained readable during graceful atomic publication;
- periodic work ran without request/page presence;
- `/api/health/coordinator` reflected lifespan start/stop.

Validation:

- focused Phase 1 tests: 13 passed;
- full pytest: 135 passed plus 42 subtests;
- focused Ruff, Python compilation, Surface `node --check`, and
  `git diff --check`: passed;
- runtime startup smoke: coordinator running in `single_process` mode with
  `maintenance/cache-cleanup` registered.

Browser follow-up:

- the first coordinator snapshot exposed separate queued Surface jobs for each
  CONUS product behind the shared provider interval;
- it also exposed presence-only records labeled `succeeded` without execution
  timestamps;
- the implementation and regression tests now correct both findings;
- browser re-verification confirmed one Surface state per region, truthful
  `idle` presence states, zero remaining active jobs, and maintenance execution
  during the Surface provider wait;
- the cached gradient PNG and its embedded mask no longer depend on marker rows
  being available before the renderer adds the overlay;
- browser re-smoke confirmed masked gradients for every Surface product;
  Altimeter took about five seconds on its first load, which was accepted as a
  cosmetic delay requiring no further change.
