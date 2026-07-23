# Worker-Free Phase 4 Evidence

Date: 2026-07-23

Scope: selected-product MRMS refresh, hourly RTMA latest refresh, coordinator
cadence, unchanged-source no-op behavior, progressive overlay history
ownership, and shared heavy-render concurrency.

## Browser findings and remediation

The first user browser smoke after a server restart/hard refresh found that
normal MRMS and RTMA product loads were fast, with a slower first decode for
MRMS Rotation Track and Azimuthal Shear. It also exposed three scrubber defects:

- a three-hour MRMS request mixed a few older cached frames with recent frames
  instead of filling the requested horizon;
- a three-hour RTMA Hourly request returned only the partial cached hours; and
- RTMA Rapid Update rendered six 15-minute frames server-side, but the browser
  stayed on the current frame after its first empty history response.

The correction makes partial caches enqueue a horizon-specific selected-product
fill, lists/downloads missing MRMS history from NODD, selects the newest end of
newest-first RTMA sources, uses a 15-minute RTMA-RU refresh cadence, and polls
every five seconds while a history fill is active. Newly discovered frames are
merged chronologically.

The corrected user browser re-smoke passed on 2026-07-23 after a server restart
and hard refresh. MRMS, RTMA Hourly, and RTMA-RU showed the corrected history
behavior, and no other issues were found. Phase 4's browser gate is closed.

## Automated validation

- The original focused Phase 4/coordinator run passed 14/14.
- The corrected `tests/test_phase4_mrms_rtma_refresh.py` passes 10/10, including
  partial-cache fill, upstream MRMS history, newest-source selection, and
  RTMA-RU cadence/current-cache coverage.
- The combined corrected Phase 4/coordinator suite passes 19/19.
- Node syntax checks pass for both MRMS and RTMA engines/pages.
- Focused Ruff passed for all changed Phase 4 Python files (retained Radar
  module-level import exceptions were excluded).
- Changed Python compiled successfully.
- `git diff --check` passed.
- The final complete run reached 176 passing tests plus 42 subtests. One
  unrelated Workspace assertion expected the removed local
  `WORKSPACE_REGION_BOUNDS` constant while concurrent user-owned code had moved
  that behavior to `mapCore.fitRegion`.

## Isolated runtime validation

The updated application ran on temporary port 8003 with legacy in-process
workers disabled.

- Coordinator health exposed `noaa-mrms` and `noaa-rtma`, each at concurrency
  one.
- Selecting `PrecipRate` queued key
  `("mrms", "latest", "PrecipRate")`.
- The worker log showed only the `PrecipRate` S3 prefix, source, PNG render,
  and overlay-catalog publication; no unrelated MRMS product was discovered.
- The MRMS coordinator state succeeded with source timestamp
  `2026-07-23T18:34:00Z`. An immediate repeat returned `current` with about
  107 seconds remaining.
- RTMA queued key
  `("rtma", "latest", "CONUS", "rtma_hourly", "temperature")`, rendered one
  `2026-07-23T17:00:00Z` frame, and succeeded. An immediate repeat returned
  `current` with about 3,590 seconds remaining.
- Temporary validation servers were stopped after the checks.

The isolated checks remain API/runtime evidence. The user-owned browser proof
first identified the history defects above and then confirmed their correction.
