# Worker-Free Phase 7 Automated Evidence

Date: 2026-07-24

Scope: Radar and Satellite without required warmers.

Status: **closed 2026-07-24** after the corrected user-owned Radar and
Satellite browser/live-provider re-smokes passed.

- Focused gate:
  `python -m pytest tests/test_refresh_coordinator.py tests/test_radar_product_catalog.py tests/test_worker_free_phase7_radar_satellite.py tests/test_satellite_rapid_worker.py tests/test_satellite_reflectance.py -q`
  currently passes **53 tests plus 42 subtests**.
- Full suite: **222 tests plus 42 subtests passed**. The only failure is the
  pre-existing Workspace assertion for the concurrently removed
  `WORKSPACE_REGION_BOUNDS`.
- Changed Python compiles; Phase 7 files pass Ruff. `radar_service.py` passes
  with its two pre-existing unused-import findings excluded.
- Changed Satellite JavaScript passes `node --check`.
- `git diff --check` passed.

Covered contracts:

- Presence jobs repeat at their configured provider/source interval only while
  the 90-second lease is active, then are removed.
- Radar keys include site, level, product, elevation, and storm-motion variant;
  responses expose `history_filling`.
- Level 2 chunk prefix discovery uses a 30-second process cache.
- Satellite source downloads deduplicate per platform/sector/frame.
- Selected rapid-sector and Meteosat accelerators are application-owned,
  delayed behind first view, and stop after presence expires.
- A page selection supersedes its prior Satellite accelerator cooperatively:
  the in-progress frame may finish, but another abandoned frame cannot start.
  Other page instances viewing the prior selection can still keep it active.
- The application accelerator's one-worker path renders in-process instead of
  spawning a Windows child that re-imports `main.py` and prints Py-ART startup
  output.
- EUMETSAT FCI download concurrency is limited to one or two.
- Missing EUMETSAT credentials return `credentials_required` without attempting
  provider catalog access; licence failures map to `license_required`.

The automated results above are not browser proof. The user-owned browser and
live-provider evidence below separately closes that gate.

First Radar browser smoke (2026-07-24):

- Newest KMHX Level 2 reflectivity appeared first, but a six-hour request
  stopped after the initial one-hour/12-frame batch. Incomplete history now
  bypasses the normal five-minute success cadence so later bounded batches can
  continue, and a succeeded job is no longer reported as still filling.
- The apparent cross-page hang persisted across a terminal restart because an
  older localhost-only server was still listening on port 8000 alongside the
  restarted server. The stale listener was removed; Workspace, Radar, Surface,
  and Satellite then rendered in a focused browser smoke.
- Regression gates pass: Radar/Phase 7 tests pass **27 tests plus 42
  subtests**; coordinator/Phase 7 tests pass **24 tests**. A server restart and
  user Radar/Satellite re-smoke are still required before Phase 7 closes.

Radar re-smoke passed. First Satellite browser/live-provider smoke:

- GOES-19 CONUS Channel 13 passed: newest frame in about five seconds and a
  12-frame loop filled in another two to four seconds.
- GOES-19 MESO1 rendered and cataloged tiles, but the CONUS-scale initial view
  forced zoom-7 tiles into thousands of mostly offscreen elements and showed no
  imagery. Meso sectors now fit their live frame bounds and warm/display zooms
  5-6 instead of the much larger 7-8 full-sector tile set.
- Himawari Japan exposed accelerator priority inversion: the delayed full-sector
  warmer could acquire the heavy-render slot before live viewport tiles.
  Accelerators now wait for current live tile work to become idle.
- Meteosat-12 Full Disk exposed cold fanout across all six catalog frames.
  Neighboring layers now prime only when their catalog reports cached tiles;
  a cold selection requests the newest frame first instead of beginning several
  FCI frame downloads at once.
- Satellite correction tests pass **21 tests**; JavaScript syntax and focused
  Ruff pass. Focused local browser verification loaded the corrected MESO1
  view at zoom 5 with nine active tiles and visible imagery; Meteosat startup
  primed only the newest frame plus one already-cached neighbor instead of all
  six frames. The Python accelerator-priority change still requires a clean
  server restart and Satellite re-smoke.
- Follow-up user testing exposed stronger selection carryover: after switching
  from Meteosat-11 RSS to Meteosat-9 Full Disk, RSS completed at least eight
  additional frames at roughly 23-26 seconds each. Page-instance selection
  identity and between-frame continuation checks now stop the abandoned job
  after its current frame. The same log's Py-ART banner came from the
  single-worker rapid accelerator spawning a Windows process; that path now
  runs in-process. The focused Phase 7 gate passes **53 tests plus 42
  subtests**. A clean restart/hard refresh and this exact switch re-smoke were
  required.

Final user-owned closure result:

- Radar re-smoke passed after the incomplete-history cadence correction and
  stale port-8000 listener removal.
- GOES-19 CONUS, GOES-19 Meso, Himawari-9 Japan, and configured Meteosat
  Full Disk/RSS paths loaded with the corrected viewport, priority, and cold
  frame behavior.
- The final Meteosat-11 RSS to Meteosat-9 Full Disk switch stopped RSS after
  its in-progress frame instead of starting more abandoned frames.
- The one-worker Satellite accelerator no longer emitted the mid-session
  Py-ART subprocess banner.
- The user reported the corrected final switch worked. Phase 7 is closed and
  Phase 8 is authorized next.
