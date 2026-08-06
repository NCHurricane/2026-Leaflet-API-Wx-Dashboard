# Project Cleanup Phase 2 Audit

Date: 2026-08-05

Status: Read-only audit complete. Batches A, B1, B2, and C are implemented
locally and uncommitted. No scheduled tasks were changed.

## Scope and evidence

- Phase 1 is committed at `628c3cf` and the working tree was clean when this
  audit began.
- `tools/install_tasks.ps1` was run in its default preview-only mode. The
  current machine has no registered `Wx-Dashboard-*` tasks.
- The installer retains 13 legacy direct-writer task names solely as an
  explicit removal allowlist and exposes four optional API-warmer profiles:
  `core`, `surface`, `rtma`, and `mrms`.
- Static inspection found 89 FastAPI route decorators. Route definitions were
  compared with production frontend, application/worker, test, and current
  documentation references.
- Deployment constraint confirmed by the user: this is currently a single-user
  application and there are no external API consumers. Compatibility decisions
  therefore need to preserve only current repository workflows and any manual
  operator tools the user elects to retain.

## Retain

- All routes called by current product pages, Workspace engines, optional
  warmers, or runtime health checks.
- MRMS native tile prepare/tile routes. Their URLs are returned in frame
  metadata and consumed dynamically rather than appearing as fixed frontend
  strings.
- The standardized `/api/{service}/products` catalog routes. They are a
  documented API contract even where a current page uses a shared configuration
  registry directly.
- `/weather.html` as the documented compatibility redirect to `/workspace`.
- `workers/scheduler.py` lifecycle hooks. `app_core/runtime.py` still imports
  them; they intentionally register no broad jobs.
- The optional-warmer installer and its legacy-name allowlist. With no matching
  registered tasks, removing the allowlist would reduce migration safety without
  cleaning current machine state.

## Proposed implementation batches

### Batch A — isolated legacy Radar tile API — implemented 2026-08-05

Removed:

- `GET|HEAD /api/radar/tiles/{z}/{x}/{y}`
- `GET /api/radar/tiles/freshness`
- Their route-only helpers in `services/radar_service.py`

The production Radar and Workspace engines continue to use
`/api/radar/live/*`. Current documentation already labeled the older tile
family compatibility-only, the repository had no production or test caller for
it, and the user confirmed there are no external API consumers. A focused route
contract test asserts that the legacy routes are absent and the five core live
routes remain registered.

Validation: Ruff and Python compilation pass for the changed Python files. The
focused automated Radar/Workspace gate passes 61 tests plus 42 subtests. Its 28
Matplotlib pending-deprecation warnings and denied `.pytest_cache` write are
existing/environment-only. `git diff --check` passes. The user-owned focused
browser smoke passed on both `/radar` and `/workspace`, including current Radar
loading and playback. Batch A is closed.

### Batch B1 — unused non-debug endpoints — implemented 2026-08-05

Removed after confirming there are no production frontend/runtime or external
API consumers:

- `/api/alerts/polygons`
- `/api/data/colormap`
- `/api/data/rtma/grid`
- `/api/satellite-v2/status`
- `/api/tropical/summary`
- `/api/radar/sites`
- `/api/radar/site-locations`

Their route-only service implementations were removed as well, including the
obsolete Alerts selector helpers, RTMA grid-JSON generation path, and Satellite
catalog-status wrapper. Current page endpoints and replacement routes remain
registered. The README API quick reference now reflects the current route
families instead of advertising removed legacy multiplexers and `/api/purge`.

Validation: changed-file Ruff and Python compilation pass. The focused
cross-product gate passes 112 tests. The complete Python suite passes 387 tests
plus 42 subtests with 52 existing dependency deprecation warnings. Pytest's
cache plugin was disabled for the full run to avoid the known repository cache
permission warning. The route inventory is reduced from 89 to 79 decorators
across Batches A and B1. No live browser check was performed because the
removed routes had no current frontend callers.

### Batch B2 — Radar diagnostic endpoint — implemented 2026-08-05

Removed `/api/radar/debug/meso-raw` and its route-local response shaping. The
underlying `_fetch_iem()` and `_radar_3letter()` helpers remain because the
current storm-track service uses them. `/api/radar/live/storm-tracks` remains
registered. Ruff and compilation pass; the focused Radar/Workspace gate passes
70 tests plus 42 subtests, and the full Python suite remains at 387 tests plus
42 subtests with the same 52 existing warnings. The route inventory is now 78
decorators. No browser check was needed because the removed debug route had no
frontend caller.

### Batch C — disconnected archive/progress workflow — implemented 2026-08-05

Removed after confirming that the current frontend and repository runtime do
not call:

- `/api/archive/mrms`
- `/api/archive/result`
- `/api/archive/spc`
- `/api/progress/{task_id}`

The associated MRMS/SPC render-session, result, and task-progress implementation
was removed from `services/archive_service.py`; the now-unused
`app_core/progress.py` state module was deleted. The active
`/api/archive/alerts` and `/api/archive/surface` routes and their shared parsing
and JSON-cache helpers remain unchanged.

Validation: changed-file Ruff and Python compilation pass. A 66-test focused
gate covers the route contract plus retained Alerts, Surface, and Workspace
behavior. The complete Python suite passes 389 tests with 31 existing dependency
deprecation warnings. The route inventory is now 74 decorators. No browser check
is required because the removed workflow had no frontend caller; this is backed
by static caller inspection and automated route/retention coverage.

## Documentation finding

The README API list contains historical endpoints that are no longer registered,
including `/api/purge` and older current/archive multiplexers. Reconcile that
list with the live route inventory in the implementation batch that changes API
compatibility; do not use the current README list as proof that an endpoint is
live.

## Recommended next action

Batches A, B1, B2, and C are complete locally. Review and commit the bounded
Phase 2 API cleanup before considering any separately gated cleanup family.
Task tooling/definitions and palette-preview code remain out of scope.
