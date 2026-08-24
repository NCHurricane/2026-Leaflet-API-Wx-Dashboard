# NCH Weather Studio Greenfield Rewrite Plan

**Status:** active separate-project plan

**Rewritten:** 2026-08-09

**Supersedes for future planning:** the preserved 2026-06-30 plan at
[`archive/2026-08-07-consolidation-sources/nch-weather-studio-greenfield-plan.md`](archive/2026-08-07-consolidation-sources/nch-weather-studio-greenfield-plan.md)

**Current-dashboard comparison baseline:** repository commit `f994c0a`, plus
the shared non-Workspace alert monitor documented as implemented in the
2026-08-09 working tree. Reconfirm the baseline before implementation because
the operational dashboard may continue to change.

This is the implementation-ready plan for a clean-room standalone desktop
program named `nch-weather-studio`. It replaces the old plan as the active
Greenfield specification without changing the archived historical copy.

The June plan chose a sound general direction, but it described an older
dashboard. Since then, the dashboard gained standalone ES-module product pages,
shared product engines, a multi-product Workspace, a synchronized shared
timeline, application-owned bounded refresh coordination, broader satellite
coverage, native-detail MRMS tiles, improved reliability contracts, and a
shared non-Workspace alert monitor. Those behaviors are now part of the parity
baseline.

Greenfield remains separate from both the current-dashboard backlog and the
Version 2 lane. Work begins only when the owner explicitly authorizes an
implementation phase.

## 1. Owner Decisions Already Made

Treat these as fixed unless the owner explicitly changes them.

- Product name: `nch-weather-studio`.
- Initial location: `F:\Python\dashboard_2026\nch-weather-studio`.
- The directory must be independently extractable into its own repository.
- Supported release targets:
  - Windows 11 x64.
  - Windows 10 22H2 x64 as a compatibility target.
  - macOS on Apple Silicon only.
- Explicitly unsupported in this plan:
  - Intel macOS.
  - Linux.
  - Windows on ARM.
- Windows 10 is past ordinary Microsoft support. The app may run there, but
  release notes and Diagnostics must identify it as a compatibility tier and
  recommend a security-supported Windows configuration. Earlier Windows 10
  releases are not targets.
- Initial macOS floor: macOS 14 or newer on Apple Silicon. At release time,
  test the current macOS major version and the previous two Apple Silicon
  major versions when runners or machines are available. Raise the floor when
  a required runtime or security dependency requires it.
- App type: native desktop app using Tauri v2.
- Runtime: bundled Python sidecar supervised by Tauri.
- Frontend: React, strict TypeScript, and Vite.
- Map runtime: MapLibre GL JS.
- Backend contract: FastAPI, Pydantic v2, and OpenAPI.
- Python environment and lock tool: `uv`.
- JavaScript workspace and lock tool: `pnpm`.
- Primary audience: personal/local use first.
- Updates: manual installation; no v1 auto-updater service.
- No Docker path for v1.
- Sources must be free/public. A free source that requires a user credential or
  acceptance of provider terms is allowed only as an optional adapter.
- No cloud account, app login, or telemetry is required.
- Clean-room rule: use the current dashboard as a behavior specification, but
  do not import or copy its source modules.
- Permitted clean-room inputs include documented behavior, public API
  contracts, independently created test fixtures, expected-output/golden
  artifacts, mathematical formulas, and owner-controlled assets whose license
  and provenance are recorded. They are reference material, not a route for
  copying implementation code.
- The current dashboard remains the operational fallback until cutover.
- Daily cutover requires parity with all 11 dedicated product families and the
  current multi-product Workspace.
- Workspace becomes the primary operational workflow in the new app. Every
  product also keeps a dedicated focused view.
- Preserve useful interaction concepts while redesigning the UX: map-first
  layout, layers, product controls, timeline/scrubber, inspector, legends,
  freshness, last-valid data, and clear loading/empty/error states.
- Redesign history around one capability-aware timeline. Do not pretend every
  provider supports arbitrary historical backfill.
- Use a managed rolling cache whose initial budget is selected from real disk
  capacity and the selected performance profile, not a fixed 100–250 GB value.
- Use an automatic hardware recommendation on first launch, with Conservative,
  Balanced, and Performance profiles plus manual overrides.
- Hardware tuning may change only app-owned limits. It must never alter BIOS,
  OS power plans, drivers, pagefile/swap, process priority, or other system
  settings.
- Initial vertical product slice: Surface plus Alerts.

## 2. Definition Of Done

The rewrite is not daily-driver ready until all applicable items pass.

### Desktop and platform

- A release build installs and launches without a developer shell on Windows
  11 x64.
- The same x64 build is validated on Windows 10 22H2 with current WebView2 and
  shows the compatibility-tier notice in Diagnostics.
- A native `aarch64-apple-darwin` build installs and launches on Apple Silicon.
- No Intel macOS, Linux, Windows ARM, or universal macOS artifact is required.
- Windows and macOS packages are built natively on their target OS; the Python
  sidecar is never assumed to be cross-compiled.
- Tauri starts exactly one bundled sidecar, reads its dynamically selected
  loopback port, waits for authenticated readiness, and stops it cleanly.
- A second app launch focuses the existing instance or exits without starting
  a second sidecar.
- Sidecar crash and failed startup produce a readable recovery screen, bounded
  restart behavior, and access to sanitized diagnostics.
- macOS local development builds are signed appropriately for Apple Silicon.
  Any build distributed to another user is Developer ID signed, hardened, and
  notarized. Windows distribution records whether the installer is signed and
  documents any expected SmartScreen warning for a personal unsigned build.

### Architecture and security

- The installed app does not need the old dashboard, Docker, Node, Python, Rust,
  or a source checkout.
- No old dashboard code is imported or copied.
- The sidecar binds only to `127.0.0.1` on an OS-selected port.
- Every non-health API operation requires the per-launch session credential;
  CORS is restricted to the packaged app origin and development origins that
  are explicitly enabled in development builds.
- The credential is never placed in a URL, persisted to disk, or written to a
  log. Streaming events use authenticated `fetch`, not a tokenized EventSource
  URL.
- Tauri capabilities follow least privilege; shell/sidecar permissions name
  only the bundled executable and approved arguments.
- The WebView uses a restrictive Content Security Policy, no CDN scripts, no
  remote navigation, and vendored production assets.
- Optional provider credentials use the OS credential store. SQLite, settings,
  logs, diagnostics bundles, and crash reports contain no plaintext secrets.
- SQLite migrations are versioned and upgrade/rollback recovery is tested.
- Large artifacts use unique temporary paths, checksum/size validation, and
  atomic publication. Readers see the previous complete generation or the new
  complete generation, never a partial result.

### Product and workflow parity

- Surface, Alerts, Radar, Satellite, SPC, RTMA, MRMS, Drought, WPC, Tropical,
  and Water each pass their parity matrix.
- Workspace passes a separate parity matrix covering its curated composition,
  shared time selection, layer order, legends, notifications, and tools.
- The current standalone/global alert-notification semantics are represented
  inside the desktop app without an OS background service.
- Current/live data works from an empty cache.
- Every product distinguishes loading, warming, legitimate empty,
  source-unavailable, failed, stale-last-valid, and current states where those
  states are meaningful.
- Last-valid data remains visible during a recoverable refresh or source
  failure when a valid artifact exists.
- Frame-capable products use the shared timeline. Issuance-, advisory-, and
  observation-based products keep their real cadence and do not acquire fake
  frames.
- Cache purge cannot remove settings, the database, credentials, user exports,
  or the only retained last-valid artifact unless the owner explicitly chooses
  a destructive purge.

### Hardware adaptation and quality

- Host profiling works on Windows 10/11 x64 and Apple Silicon macOS.
- Missing or unreliable hardware signals fall back to Conservative; they do
  not block startup on a machine that meets the hard minimum.
- The calibration benchmark is offline, repeatable, bounded, cancelable, and
  versioned. It does not benchmark public weather providers.
- Conservative, Balanced, and Performance settings are explainable in the UI,
  stored separately from user overrides, and reproducible from an exported
  diagnostics bundle.
- Runtime memory, disk, thermal/power, and GPU pressure can temporarily
  downshift prefetch/render work without changing the saved user profile.
- PNG/server-rendered fallback remains available for every GPU-accelerated
  weather path required for parity.
- WCAG 2.2 Level AA is the accessibility target for the complete application,
  including keyboard operation, focus, non-color status, reduced motion,
  accessible alert audio controls, and a non-canvas representation of selected
  map features.
- Backend, frontend, contract, renderer, lifecycle, packaging, accessibility,
  and real desktop smoke gates pass on the target matrix.
- The manual cutover checklist is complete and the current dashboard remains
  recoverable until the owner accepts cutover.

## 3. Non-Goals For V1

Do not add these without a new owner decision.

- Docker or Docker Desktop.
- Paid data sources or a paid cloud runtime.
- Cloud synchronization, accounts, multi-user access, or remote administration.
- A public web-only replacement for the desktop application.
- Auto-update infrastructure.
- App Store or Microsoft Store distribution.
- A plugin marketplace or third-party executable plugins.
- Multiple independent desktop windows or multiple backend instances.
- OS notifications, a Windows service, `launchd` agent, always-on background
  monitoring, AWS notification infrastructure, or notifications after the app
  closes.
- Linux, Intel macOS, universal macOS binaries, Windows ARM, iOS, or Android.
- Automatic driver installation or any OS/firmware/power-plan tuning.
- Mandatory GPU compute through CUDA, ROCm, DirectML, or Metal compute. GPU use
  is for the WebView/MapLibre rendering path unless a later measured prototype
  earns a broader design.
- Arbitrary historical backfill where the provider or product contract cannot
  support it reliably.
- Worldwide replacement-product expansion before current-dashboard parity.
- Copying current-dashboard modules, page controllers, build files, or hidden
  implementation branches into the new project.
- Mutating the current dashboard as an incidental implementation step.
- Deferring platform packaging until the end. Phase 0 must prove it, although
  public-release signing and distribution automation remain out of scope until
  a distributable release is selected.

## 4. Required Technology Stack

Pin exact versions in lockfiles when Phase 0 starts. Use supported current
releases, not version numbers copied indefinitely from this planning document.

### 4.1 Desktop

- Tauri v2 with Rust stable.
- One primary window and the Tauri single-instance plugin or an equivalent
  tested single-instance contract.
- Tauri owns lifecycle, app data paths, native dialogs, secret-store bridge,
  platform hardware profiling, sidecar supervision, and packaging.
- Tauri contains no meteorological parsing or product business logic.
- Bundle one target-specific Python executable through Tauri `externalBin`:
  - `x86_64-pc-windows-msvc` for Windows.
  - `aarch64-apple-darwin` for Apple Silicon.
- The sidecar binds port `0`, then emits a single machine-readable readiness
  record containing the selected port and API version. Tauri validates the
  record before revealing the connection to the WebView.
- Sidecar shutdown is graceful with a short timeout and process termination as
  the bounded fallback.
- Tauri permissions allow only required filesystem scopes, window operations,
  and the named sidecar. No general shell execution is exposed to the WebView.

### 4.2 Frontend

- React with strict TypeScript.
- Vite for development and production bundling.
- The current Node LTS that satisfies the selected Vite release; pin it in a
  tool-version file and CI.
- `pnpm` workspaces with a committed `pnpm-lock.yaml`.
- React Router for stable dedicated-view and Workspace URLs.
- TanStack Query for server-state fetching, invalidation, caching, retry
  policy, and cancellation. Do not duplicate server state in a second global
  store.
- React state/reducers and URL state for local UI state. Add a new state library
  only after a documented need survives a prototype.
- `openapi-typescript` plus `openapi-fetch`, or a demonstrably equivalent
  generated strict client selected in Phase 0. Handwritten endpoint types are
  prohibited.
- MapLibre GL JS as the one interactive map engine.
- Vendored application assets; no runtime CDN dependency.
- CSS design tokens and small shared components. Do not import a broad UI
  framework until the shell prototype proves that it improves accessibility
  and maintainability without compromising the map layout.
- Vitest and React Testing Library for unit/component behavior.
- Playwright for fast browser-mode renderer flows where a native shell is not
  required.
- WebdriverIO with the Tauri driver/service for real packaged desktop flows.

### 4.3 Backend

- Python 3.14 is the target runtime for the initial packaging spike.
- If a required scientific/geospatial package lacks a reliable wheel or cannot
  be bundled on either target, pin Python 3.13 on both platforms temporarily.
  Record the blocker, owner, and re-evaluation date; do not ship different
  Python feature versions per platform.
- FastAPI and Pydantic v2.
- Uvicorn embedded in the sidecar with one API process. Do not use Uvicorn
  multi-worker mode.
- SQLAlchemy 2 with Alembic migrations for SQLite metadata, settings schema,
  artifact index, jobs, source state, and timeline availability.
- Prefer a synchronous SQLAlchemy repository behind a bounded dedicated DB
  executor. `aiosqlite` is a thread wrapper and is not a reason to spread async
  database semantics throughout the domain model.
- HTTPX for bounded HTTP I/O, explicit timeouts, cancellation, streaming, and
  pooled connections.
- `uv` with a committed `uv.lock`; `ruff`, `mypy`, and `pytest`.
- PyInstaller for the first sidecar packaging prototype. Replace it only if the
  Phase 0 evidence shows an unsolved target-platform problem.
- Keep geospatial/scientific dependencies capability-based. Add NumPy,
  rasterio, pyproj, Shapely, xarray, cfgrib/eccodes, Pillow, or Matplotlib only
  where a named product pipeline needs them; do not reproduce the current
  dashboard's broad environment by default.
- Use structured, credential-safe logs with stable event and diagnostic codes.

### 4.4 Mapping

- Web Mercator is the interactive display projection.
- Every artifact declares projection, bounds, valid time, units, nodata, source,
  renderer version, and checksum.
- Use raster tile sources for satellite and native-detail gridded layers.
- Use bounded raster image sources where a single pre-rendered overlay is the
  reliable parity/fallback path.
- Use GeoJSON or vector tiles for alerts, outlooks, reports, stations, storm
  tracks, gauges, and boundaries. Start with GeoJSON and promote only measured
  high-volume layers to vector tiles.
- One `packages/map-runtime` adapter owns layer IDs, source IDs, ordering,
  teardown, opacity, hit testing, legends, and timeline-frame replacement.
- MapLibre custom WebGL layers are allowed only behind a capability flag,
  parity tests, resource accounting, and the authoritative PNG/tile fallback.
- The frontend probes WebGL2 capabilities and runs the app benchmark; it never
  enables a high-cost path from a marketing GPU name alone.

### 4.5 Runtime Packaging

- Use native packages, never Docker.
- Build and test the Python sidecar on each target OS. PyInstaller is not a
  cross-compiler.
- Windows output: NSIS or MSI selected after Phase 0 install/uninstall tests.
  Use evergreen WebView2 by default and offer an offline bootstrap strategy
  only if the owner needs disconnected installation.
- macOS output: Apple Silicon app bundle and DMG. Local development may use
  ad-hoc signing; distribution outside the development machine requires
  Developer ID signing, hardened runtime, notarization, and stapling.
- Store mutable data only in Tauri-provided app config/data/cache/log paths.
  Never write beside installed binaries.
- Manual update must preserve and migrate settings/database, preserve compatible
  artifacts, and invalidate renderer-versioned artifacts deliberately.
- Install, upgrade, uninstall, and rollback procedures are part of packaging
  acceptance, not afterthoughts.

### 4.6 Dependency And Release Governance

- Commit `uv.lock`, `pnpm-lock.yaml`, and `Cargo.lock`.
- Record the Python, Node, Rust, WebView, and macOS deployment baselines in each
  release manifest.
- Run automated vulnerability and license review, but merge dependency updates
  only after target builds and product tests pass.
- Generate an SBOM for the Python, JavaScript, Rust, and bundled native
  components in every release candidate.
- Keep provider/source adapters isolated so a feed change does not force a UI
  dependency update.
- Build artifacts on clean target runners. Verify checksums and sign after the
  final build; never modify a signed bundle.
- Release dependency updates separately from product-feature changes when
  practical.

## 5. Repository Layout

Create this extractable tree only when implementation is authorized:

```text
nch-weather-studio/
  README.md
  LICENSES.md
  pyproject.toml
  uv.lock
  package.json
  pnpm-lock.yaml
  pnpm-workspace.yaml
  rust-toolchain.toml
  apps/
    api/
      pyproject.toml
      src/nch_api/
        app.py
        auth.py
        lifecycle.py
        routes/
        events/
        errors.py
      tests/
    web/
      package.json
      index.html
      src/
        app/
        workspace/
        products/
        map/
        timeline/
        inspector/
        settings/
        diagnostics/
        generated/
      tests/
    desktop/
      package.json
      src-tauri/
        Cargo.toml
        Cargo.lock
        capabilities/
        src/
          main.rs
          sidecar.rs
          host_profile/
          secrets.rs
  packages/
    contracts/
      openapi/
      src/
    ui/
      src/
    map-runtime/
      src/
    test-fixtures/
  weather_core/
    pyproject.toml
    src/weather_core/
      registry/
      products/
      sources/
      rendering/
      artifacts/
      scheduler/
      storage/
      timeline/
      settings/
      diagnostics/
    tests/
  docs/
    architecture.md
    product-parity-matrix.md
    source-policy.md
    hardware-profiles.md
    packaging.md
    security.md
    test-plan.md
    decisions/
  tests/
    contract/
    integration/
    desktop/
    fixtures/
    golden/
  scripts/
    generate-openapi.*
    verify-locks.*
    build-sidecar.*
```

Rules:

- `weather_core` owns weather-domain behavior and has no FastAPI, React, Tauri,
  or current-dashboard imports.
- `apps/api` assembles transport/auth/lifecycle around `weather_core`; it does
  not contain product algorithms.
- `apps/web` consumes the generated client and product presentation contracts.
- `apps/desktop` owns native lifecycle and hardware/platform integration only.
- `packages/map-runtime` owns shared MapLibre source/layer behavior. Product
  views supply typed layer descriptions, not direct global map mutation.
- Workspace composes the same product services and map-layer contracts used by
  dedicated views; it never imports a dedicated page controller.
- Generated OpenAPI client files are reproducible and checked for drift.
- Test fixtures and golden outputs record their source/provenance and may not
  contain credentials or licensed data that cannot be redistributed.
- No absolute development-machine path appears in runtime code or config.

## 6. Current Dashboard Product Families To Match

The older plan listed 11 product families but omitted the now-material
Workspace. The Greenfield parity baseline is:

| Family/workflow | Current behavior now material to parity |
| --- | --- |
| Surface | Nine observation products, stations/values/wind, gradients, inspector, current-first load, and 15-minute-to-24-hour recent lookback |
| Alerts | Active polygons, zoom-aware geometry, active-warning rail, Local Storm Reports, details, filters, stale-complete refresh, and explicit cold warming/backoff |
| Radar | Broad Level II/III catalog, sites/elevations, cache-first latest/history, value inspection, storm attributes/tracks/hail/meso/TVS, selected-cell SRV, bounded history, and selective WebGL with PNG authority |
| Satellite | GOES-18/19, Himawari-9, Meteosat-9/11/12, GK2A, GMGSI, scalar/RGB/analytical products, tiles, legends, timeline, and product-specific alpha |
| SPC | Convective Days 1–8, fire outlooks, watches, reports, mesoscale discussions, legends, details, and legitimate-empty behavior |
| RTMA | Hourly and rapid-update streams, CONUS/AK/HI/PR, exposed native/derived products, frame-locked points/raster, and approximately 12-hour history |
| MRMS | Current product groups, progressive frames, legends, approximately 12-hour history, native-detail tiles, source identity, and PNG fallback |
| Drought | Available dates/categories, national layer, state statistics, details, and legitimate-empty/source states |
| WPC | ERO Days 1–5, QPF 6-hour/24-hour/multiday, Winter guidance through Days 6–7, FOP, MPDs, Significant Weather Days 1–3, and surface analysis/forecast |
| Tropical | Live storms/basins, advisory and GIS layers, official graphics, archives, forecast track/cone, and floater imagery behavior |
| Water | River, CO-OPS coastal, and NDBC stations; viewport/network/flood filters; detail enrichment; and stage gauge |
| Workspace | Alerts, Radar, SPC, Satellite, RTMA, MRMS, WPC, and Water composition; layer ordering/legends; Projected Arrival Tool; and one Radar/MRMS/Satellite/RTMA shared timeline |

Additional parity boundaries:

- Drought is dedicated-view only in the current Workspace contract. Adding it
  to Greenfield Workspace is an enhancement, not a cutover requirement.
- WPC keeps its issuance/product cadence instead of following the shared frame
  time.
- The current Surface and Alerts Archive tabs are placeholders. Retained
  backend groundwork is not a finished archive UX.
- Surface recent lookback is Live history; Alerts 1/6/12/24-hour LSR pills are
  live filters, not general archive controls.
- Current RTMA/MRMS UI history is bounded near 12 hours. Greenfield must not
  silently reinterpret that as unbounded retention.
- The six-event non-Workspace monitor allowlist is Tornado Warning, Tornado
  Watch, Severe Thunderstorm Warning, Severe Thunderstorm Watch, Flash Flood
  Warning, and Flash Flood Watch.

## 7. Core Architecture

### 7.1 Runtime Startup

Startup sequence:

1. Tauri enforces single-instance behavior and resolves OS app paths.
2. Tauri loads settings needed before the API, creates a random per-launch
   session credential, and starts the target-specific sidecar.
3. The sidecar binds `127.0.0.1:0`, applies database migrations, validates app
   directories, starts the bounded coordinator, and emits one readiness JSON
   record on its inherited stdout channel.
4. Tauri validates protocol version and process identity, then gives the WebView
   an in-memory connection descriptor through a narrow command.
5. React requests `/api/runtime/ready`, loads registry/settings/host profile,
   and renders cached usable state before optional live refresh work.
6. On exit, Tauri requests authenticated graceful shutdown, waits for the
   coordinator to checkpoint/cancel, then terminates the process only if the
   timeout expires.

Rules:

- Never scan a port range or write a port file for discovery.
- Never accept remote interfaces or wildcard CORS.
- Readiness is distinct from liveness and from source availability.
- Automatic crash restart is capped. Repeated crashes enter Recovery Mode with
  no product refresh and a diagnostics/export action.
- Background work belongs to the coordinator. Closing the app ends all refresh
  and alert monitoring.

### 7.2 App Data Locations

Use Tauri-resolved directories and pass explicit paths to the sidecar:

```text
config/
  settings.json
  profile-overrides.json
data/
  weather-studio.sqlite3
cache/
  artifacts/
  sources/
  tiles/
  generations/
  temp/
logs/
exports/
```

Requirements:

- Validate that all configured cache/export paths resolve within explicitly
  selected roots before writing or purging.
- Cache relocation is transactional: stop new jobs, copy/verify or start clean,
  switch the stored root, then retire the old cache only after explicit owner
  confirmation.
- `exports/` is never part of automatic eviction.
- Credentials reside in the OS credential store, not these directories.
- macOS required-reason privacy declarations cover any capacity APIs used by
  the shipped app.

### 7.3 SQLite Storage

SQLite stores metadata, not large raster/source payloads.

Minimum tables:

- `schema_migrations`
- `products`, `layers`, `sources`
- `artifacts`, `artifact_generations`, `artifact_dependencies`
- `timeline_frames`, `timeline_availability`
- `jobs`, `job_attempts`, `provider_state`
- `settings_schema`, `settings_values`
- `host_profiles`, `benchmark_runs`, `profile_recommendations`
- `diagnostic_events`

Rules:

- Enable WAL only after network/removable filesystem checks; local app data is
  the supported database location.
- Use foreign keys and explicit UTC timestamps.
- One repository layer owns transactions. Product code does not execute ad hoc
  SQL.
- Keep job state restart-safe, but do not resume a destructive purge or partial
  publication automatically.
- Migrations back up or checkpoint the database before a non-trivial schema
  change and provide a readable recovery path.
- Rebuildable cache indexes may be reconstructed from artifact metadata if the
  database is repaired; settings and user choices are not treated as
  rebuildable cache.

### 7.4 Product Registry

The registry is typed, versioned, and validated at startup. It declares:

- Product/family/layer identity and navigation placement.
- Dedicated-view and Workspace eligibility.
- Source adapter and provider policy.
- Geometry/raster/tile presentation contract.
- Valid-time, issuance-time, and freshness policy.
- Live/history/backfill capabilities and maximum window.
- Units, legend, inspector schema, bounds, and default view.
- Cache class and retention priority.
- Rendering/decode capability and fallback path.
- Profile cost hints: network, CPU, RAM, GPU, and disk.
- Legitimate-empty semantics.

The registry describes capabilities; it must not turn complex product logic
into untyped configuration. Product-specific code remains appropriate behind a
shared contract.

### 7.5 Source Adapters

Every source adapter owns:

- URL/request construction and user agent.
- Authentication needs and terms/licensing metadata.
- Provider concurrency, minimum interval, timeout, retry, jitter, and
  `Retry-After` behavior.
- Download streaming and size limits.
- Parsing/validation and source identity.
- Distinction among legitimate empty, unavailable, malformed, unauthorized,
  rate-limited, and failed.
- Fixture-based tests and an upstream contract note.

Provider limits are hard ceilings. A hardware profile may lower concurrency but
never raise it above the adapter policy.

### 7.6 Artifact Store

Large payloads live in the filesystem; SQLite holds logical identity and
metadata.

Artifact identity includes the fields that affect output, such as product,
source, valid time, region, site, elevation, platform, sector, channel,
renderer version, palette, bounds, and variant. Publication sequence:

1. Allocate a unique job-owned temporary directory.
2. Stream/download/render with cancellation checks.
3. Validate file type, size, dimensions/bounds, checksum, and metadata.
4. Atomically rename the complete generation.
5. Commit the database pointer to the new generation.
6. Retain or prune the previous generation according to last-valid policy.

Do not use file modification time as meteorological frame identity. Preserve
canonical provider/source identity.

### 7.7 Scheduler And Jobs

Use one application-owned coordinator with:

- Bounded queues and executors by workload class.
- Deduplication by real resource key.
- Provider concurrency/floors/backoff.
- Request/selection presence leases.
- Priority for user-visible current frames over history/prewarm.
- Cooperative cancellation and ownership release on view/layer changes.
- Atomic generation publication.
- Restart-safe job records and bounded state pruning.

Job classes:

- Network I/O.
- Decode/transform.
- Heavy raster render.
- Tile render.
- Lightweight metadata/index.
- Cleanup/eviction.

Hardware profiles set app-owned queue sizes, executor limits, prewarm scope, and
memory/GPU budgets. They do not change source cadence or provider policy.

### 7.8 Event Stream

Expose an authenticated fetch-stream endpoint for typed events:

- Runtime/sidecar health.
- Job queued/started/progress/completed/failed/canceled.
- Product generation published.
- Timeline availability changed.
- Source state changed.
- Cache pressure/eviction.
- Temporary hardware downshift/recovery.

Events carry stable IDs and sequence numbers. Reconnect requests a bounded
replay window, then refetches authoritative REST state. The event stream is an
acceleration mechanism, not the source of truth.

### 7.9 Security Boundary

- Loopback binding is necessary but not sufficient; use a session credential.
- Only Tauri can reveal the connection descriptor to the packaged WebView.
- Development-origin exceptions are compiled/configured only in development.
- Reject unknown `Origin` and `Host` values.
- Apply request/body/download size limits.
- Sanitize filenames and keep all writes within validated app roots.
- Treat provider payloads as untrusted input.
- Never execute downloaded content.

## 8. Public API Contract

Prefix all endpoints with `/api/v1`. Generate the frontend types and client from
the OpenAPI document; CI fails on uncommitted schema/client drift.

### 8.1 Runtime

```text
GET  /api/v1/runtime/health
GET  /api/v1/runtime/ready
GET  /api/v1/runtime/version
POST /api/v1/runtime/shutdown
GET  /api/v1/runtime/events
```

`health` is cheap liveness. `ready` includes database/coordinator/cache status.
Neither performs provider downloads.

### 8.2 Products

```text
GET  /api/v1/products
GET  /api/v1/products/{product_id}
GET  /api/v1/products/{product_id}/layers
GET  /api/v1/products/{product_id}/state
POST /api/v1/products/{product_id}/refresh
GET  /api/v1/products/{product_id}/timeline
POST /api/v1/products/{product_id}/backfill
GET  /api/v1/workspace/presets
```

Generic endpoints cover shared behavior. Typed family endpoints are allowed for
domain operations that do not fit honestly—for example Radar sites/storm cells,
Tropical advisories, Water station enrichment, or alert detail lookup. They
must still use shared error, job, source, artifact, and timeline models.

### 8.3 Artifacts

```text
GET /api/v1/artifacts/{artifact_id}/metadata
GET /api/v1/artifacts/{artifact_id}/content
GET /api/v1/tiles/{artifact_id}/{z}/{x}/{y}.png
```

Use immutable cache headers for content-addressed/versioned artifacts and no
stale mutable alias without generation metadata. Range requests are allowed
where beneficial and tested.

### 8.4 Jobs

```text
GET  /api/v1/jobs
GET  /api/v1/jobs/{job_id}
POST /api/v1/jobs/{job_id}/cancel
POST /api/v1/jobs/{job_id}/retry
```

Job responses include owner, resource key, priority, timestamps, progress,
attempt, diagnostic code, and whether cancellation remains possible.

### 8.5 Settings And Cache

```text
GET   /api/v1/settings/schema
GET   /api/v1/settings
PATCH /api/v1/settings
POST  /api/v1/settings/reset
GET   /api/v1/cache/status
POST  /api/v1/cache/evict
POST  /api/v1/cache/verify
POST  /api/v1/diagnostics/export
```

Destructive cache actions require a typed scope and preview. Settings use a
versioned schema and return validation errors without partial application.

### 8.6 Host Profile And Tuner

```text
GET  /api/v1/host/profile
GET  /api/v1/host/recommendation
POST /api/v1/host/benchmark
POST /api/v1/host/profile
POST /api/v1/host/profile/reset-overrides
GET  /api/v1/host/runtime-pressure
```

Native platform facts enter through a Tauri command and are validated by a
versioned model before the API stores a profile. Raw serial numbers, device
identifiers, and other fingerprinting data are neither requested nor stored.

## 9. Frontend UX Plan

The app is an operational workstation, not a visual copy of the current pages.

### 9.1 Main Layout

```text
top: app status, current workflow, source/freshness summary
left: Workspace presets, product/layer controls, navigation
center: MapLibre map
right: inspector, active hazards, jobs, diagnostics context
bottom: capability-aware shared timeline
floating within map: legends, layer order, coordinates, map tools
```

Required behavior:

- Start in Workspace unless the user restores a prior dedicated view.
- Product/view switches do not reload the app or recreate the map.
- Preserve viewport unless the user chooses Home or a product explicitly
  requires an initial view that has not yet been established.
- Layer visibility, opacity, order, source, valid time, and freshness are one
  action away.
- Long work is cancelable and never blocks navigation.
- Provide keyboard access and a list/table alternative for selectable map
  features.
- Honor reduced motion. Radar/satellite animation and alert flashes must not be
  the only way to convey information.

### 9.2 Product Navigation

Primary entries:

- Workspace
- Surface
- Alerts
- Radar
- Satellite
- SPC
- RTMA
- MRMS
- Drought
- WPC
- Tropical
- Water

The registry supplies availability and status, but navigation labels/order are
versioned UX configuration rather than uncontrolled provider data. URLs encode
the selected view and safe shareable state; credentials and session tokens
never enter URLs.

### 9.3 Unified Timeline

Timeline modes are capability-driven:

- `live`: newest valid artifact.
- `recent`: bounded cached/provider-supported window.
- `archive`: issuance/date/advisory catalog where the family supports it.
- `backfill`: explicit bounded request where the source supports it.

Required controls:

- First/previous/play-pause/next/latest.
- Speed and hold-at-end.
- Valid time, issue/source time, source, and stale state.
- Availability/gap markers.
- Active layer participation and follower status.
- Cancelable backfill with supported-range explanation.

Workspace uses a master time with latest-at-or-before selection for Radar,
MRMS, Satellite, and RTMA. A predecessor may fill the opening visual gap
without moving the visible scrubber time. WPC and other issuance-based layers
remain independent and display their issuance explicitly.

Never show `0/0` as a normal state. Use named empty/loading/rendering/source
states.

### 9.4 Inspector

- One stable inspector host displays typed product cards.
- Click selects; optional hover previews never replace a committed selection.
- Cards include valid time/source/provenance and unit definitions.
- Overlapping features use an accessible paged/list context rather than hidden
  click-order behavior.
- Inspector loading, empty, stale, unsupported, and failed states do not block
  the map.

### 9.5 Legends

Support categorical, continuous, interpretive RGB, symbol, and mixed legends.
Legends are attached to active layer identity and appear in layer order. They
must be readable at 200% zoom, not rely on color alone, and preserve custom
Radar `.pal` behavior. API metadata is authoritative; a frontend fallback must
be versioned and tested against the same contract.

### 9.6 Settings UI

Sections:

- Performance profile and benchmark.
- Cache and storage.
- Products and sources.
- Map/display/accessibility.
- Alerts and sound.
- Credentials.
- Diagnostics and data reset.

Show recommended values, effective values, and user overrides separately.
Every reset previews its scope. Hardware recommendations explain why a profile
was chosen without exposing serial numbers or pretending that a raw GPU model
name guarantees performance.

### 9.7 Notifications

- While a dedicated non-Workspace view is open, one app-owned monitor preserves
  the fixed six-event allowlist, baselines existing alerts, and presents one
  in-app banner/sound/border cue per new alert.
- Alerts owns the persisted On/Off setting. Clicking in Alerts selects and
  zooms in place; clicking elsewhere navigates to Alerts and selects/zooms.
- Workspace retains its separate Workspace warning behavior and Projected
  Arrival context.
- The app is single-instance, so browser-tab leader election is unnecessary.
  A bounded app event ledger still prevents duplicate presentation after view
  changes.
- No monitoring or notification continues after app exit.

## 10. Product Implementation Details

The parity matrix must enumerate exact current controls, products, sources,
legends, inspector fields, states, and owner-smoke evidence before each family
starts. The lists below are the updated minimum, not an excuse to skip that
inventory.

### 10.1 Surface

- Temperature, Feels Like, Dew Point, Relative Humidity, Wind Speed, Wind Gust,
  Altimeter, MSLP, and Visibility.
- Station/value/wind presentation, product legends, gradient where currently
  supported, station inspector, region views, and last-valid state.
- Latest current observations load first.
- Live recent history supports the current 15-minute-to-24-hour window; older
  frames retain their current ASOS-only/no-historical-gradient limitation until
  a new source strategy is explicitly designed.
- Normalize units and missing values before derivation. Preserve raw-source
  provenance separately from display artifacts.
- Acceptance covers integer input types, partial fields, current fallback when
  recent history fails, and explicit provider limitations.

### 10.2 Alerts

- Active NWS polygons with full/display geometry, bbox/zoom behavior, official
  event colors, severity/event filters, active-warning list, detail selection,
  live Local Storm Reports, and last-valid immutable generations.
- Cold missing cache reports warming/backoff, never false empty success.
- Stale complete data remains visible while one deduplicated refresh runs.
- Preserve severe warning visual prominence, with reduced-motion/non-color
  alternatives.
- LSR 1/6/12/24-hour filters remain live filters.
- Preserve the dedicated-view alert monitor behavior in Section 9.7.
- The Projected Arrival Tool belongs to Workspace, not dedicated Alerts.

### 10.3 Radar

- Site catalog/markers, Level II and Level III products exposed by the current
  catalog, elevations, custom color tables, legends, value inspector, current
  frame, bounded history up to the current 12-hour UI option, and newest-frame
  first cold behavior.
- Preserve storm attributes/tracks, hail, mesocyclone, TVS/storm-cell symbols,
  and selected-cell storm-relative velocity.
- Selected-cell SRV identity includes site, product, elevation, cell identity,
  motion speed/direction/source, and source frame.
- Start with authoritative generated PNG/image artifacts. Add native/WebGL paths
  only for products that pass value/color/nodata/legend and performance gates;
  fallback remains available.
- Current named WebGL comparison candidates include `L2_RHO`, `L3_N0C`,
  `L3_DPR`, `L3_DAA`, and `L3_DTA`, but Greenfield is free to prototype a
  broader tile architecture if parity evidence remains product-specific.
- History fills asynchronously and yields to current user-visible work.

### 10.4 Satellite

- Treat current international support as parity, not an extension point:
  GOES-18/19, Himawari-9, Meteosat-9/11/12, GK2A, and GMGSI where the current
  dashboard exposes them.
- Inventory every reachable platform/sector/channel/composite. Do not resurrect
  cleaned unreachable recipes merely because the old plan named them.
- Preserve scalar products, reachable RGB composites, analytical sparse
  products, platform-specific bounds/projection, scalar/interpretive legends,
  timeline, and cache-first on-demand Web Mercator tiles.
- Filled imagery is opaque within valid coverage and transparent outside it;
  sparse ADP/AOD/FRP-style products keep their semantic alpha behavior.
- Platform adapters own channel mapping, source cadence, credentials/license
  states, solar/viewing geometry, and renderer versions.
- Source download, decode, warp, and tile render timings are measured separately.
- Page/workspace ownership cancels queued heavy work after selection/navigation
  changes; an already-publishing reusable artifact may finish atomically.

### 10.5 SPC

- Convective outlooks Days 1–8, fire outlooks, hazard/day selection, active
  watches, storm reports, mesoscale discussions, legends, detail inspection,
  and product-specific legitimate-empty states.
- Model outlooks, watches, reports, and discussions as separate layer families
  with shared source/provenance contracts.
- Preserve issuance-aware refresh and avoid launching a broad matrix refresh
  for one missing selected product.
- Overlapping features use the accessible context carousel/list contract.

### 10.6 RTMA

- Hourly and Rapid Update streams for CONUS, Alaska, Hawaii, and Puerto Rico.
- Temperature, Feels Like, Dew Point, Surface Pressure, Wind Speed, Wind Gust,
  Wind Direction, Visibility, Total Cloud Cover, and 24-hour Temperature Change
  where the current region/stream supports them.
- Feels Like derives from synchronized temperature/dew point/wind fields.
- Raster and value points must reference the same `source_data_key`.
- Preserve bounded approximately 12-hour recent history initially.
- Wind direction/value marker behavior, legends, units, nodata, and unsupported
  region/product combinations are explicit registry data.

### 10.7 MRMS

- Inventory the current product groups and defaults from the current registry,
  not the older plan's generic placeholder.
- Preserve current-first load, progressive actual-frame history, approximately
  12-hour initial window, legends/units, source identity, and clear missing
  states.
- Native-detail viewport tiles are preferred where the frame can be prepared;
  the complete PNG overlay remains rollback/fallback.
- Canonical source metadata wins over filesystem modification time.
- Product/statistic inspectors must report underlying data, not a legend maximum.

### 10.8 Drought

- Available issue dates, drought categories, national layer, state statistics,
  selection/details, source/freshness, and last-valid behavior.
- Use issue-date timeline semantics, not animation-frame semantics.
- Keep state statistics separately typed from display geometry.
- Drought remains dedicated-view only for parity; Workspace inclusion requires
  a separate enhancement decision.

### 10.9 WPC

- Excessive Rainfall Outlook Days 1–5.
- QPF 6-hour, 24-hour, and multiday ranges currently exposed.
- Winter guidance through the current Days 6–7 range.
- Five-Day River Flood Outlook, active MPDs, Significant Weather Days 1–3,
  Surface Analysis, and Surface Forecast.
- Preserve explicit no-significant-weather/no-area issuance separately from
  source failure.
- Convert KML/KMZ/PNG/provider payloads into typed internal vector/raster
  artifacts with source bounds and issuance metadata.
- WPC controls should be day-first where that matches the product, and WPC
  cadence remains independent of the Workspace master frame time.

### 10.10 Tropical

- Global basin-capable live storm list, outlook/summary, storm details,
  advisory/fix time, official forecast track/cone/GIS layers and graphics,
  archive catalog/storm/advisory browsing, and floater imagery behavior.
- Stable official graphics URLs and missing-language/product states remain
  explicit; never fabricate unavailable graphics.
- Rich storm panels may be product-specific, but layers, artifacts, source
  state, and time selection use shared contracts.
- Active storms have higher refresh priority than archive browsing; archive
  work is cancelable and bounded.

### 10.11 Water

- NOAA river, CO-OPS coastal, and NDBC buoy/station networks.
- Viewport/bbox and network filtering.
- River flood thresholds: All, Action+, Minor+, Moderate+, and Major.
- Typed detail enrichment for each network, grouped NDBC readings, distinct
  marker styles, and stage gauge bar.
- Prevent invalid world-wrap bbox requests and control density at wide views.
- Preserve stale-while-refresh and last-valid station/detail behavior with a
  bounded cache.

### 10.12 Workspace

- Workspace is a first-class tested workflow, not merely a navigation page.
- Compose Alerts, Radar, SPC, Satellite, RTMA, MRMS, WPC, and Water through the
  same engines/contracts used by dedicated views.
- Preserve meaningful layer order, combined tabbed legends, product controls,
  active warning/LSR context, overlapping SPC context, and the Projected
  Arrival Tool.
- One master timeline synchronizes Radar, MRMS, Satellite, and RTMA using
  latest-at-or-before logic. WPC remains issuance-driven.
- Region/Home own viewport reset. Satellite sector changes select imagery
  without unexpectedly replacing the Workspace viewport.
- Workspace retains its separate warning-notification semantics.
- Performance-profile degradation must be graceful: fewer preloaded frames or
  lower concurrent preparation, never missing controls or incorrect layer time.

## 11. Unified Timeline And Archive Design

Store three distinct times when applicable:

- `valid_time`: meteorological valid/observation time.
- `source_time`: provider issuance/publication time.
- `created_at`: local artifact publication time.

Availability states:

- `available`
- `queued`
- `downloading`
- `decoding`
- `rendering`
- `missing`
- `legitimate_empty`
- `unsupported`
- `source_unavailable`
- `failed`
- `stale_last_valid`

Rules:

- Timeline entries reference immutable artifact generations.
- Use real provider frames only; never increment a clock without data.
- A Workspace follower chooses the newest compatible frame at or before the
  master time and exposes the delta.
- Backfill validates product maximum span, oldest supported date, request cost,
  credentials, and disk headroom before queueing.
- Backfill priority is below live/current work and can be canceled.
- Drought issues, Tropical advisories, WPC issuances, Surface observations, and
  Alerts/LSR windows retain domain-specific labels within the shared component.
- A future unified Archive UX may extend current Surface/Alerts groundwork, but
  it must first prove source coverage and bounded request multiplication.

## 12. Cache And Retention Plan

Use one global budget plus per-class priorities. Initial cache budget is
calculated by the tuner:

```text
reserve = max(20 GiB, min(50 GiB, 10% of cache-volume capacity))
usable = max(0, available-to-user - reserve)
recommended cache = min(profile ceiling, profile fraction * usable)
```

Profile defaults:

| Profile | Fraction of usable | Ceiling | Behavior |
| --- | ---: | ---: | --- |
| Conservative | 25% | 25 GiB | Current/last-valid first; minimal prewarm |
| Balanced | 50% | 100 GiB | Current plus bounded recent history |
| Performance | 60% | 250 GiB | Broader recent/prepared artifacts within provider limits |

If less than 5 GiB remains after the reserve, the app enters storage-limited
mode and asks the user to choose another cache location or free space. A user
may always choose a smaller budget. A larger override is accepted only if the
reserve still remains.

Eviction classes, lowest retention first:

1. Job-owned temp/failed partials.
2. Regenerable source files with validated published artifacts.
3. Prepared tiles outside the active viewport/time window.
4. Timeline history outside selected retention.
5. Live-recent frames beyond product policy.
6. Superseded generations.
7. Critical last-valid artifacts only through an explicit destructive action.

Never auto-delete settings, SQLite, credentials, logs within their separate log
retention policy, exports, or the only last-valid artifact. Cache accounting
must include filesystem size, database index state, orphan detection, and
renderer-version invalidation.

Initial product windows preserve current behavior: RTMA/MRMS around 12 hours,
Radar up to the current bounded 12-hour selection, Surface recent observations
up to 24 hours, and source-appropriate issuance/advisory retention for the
remaining families. Expanding a window requires measured disk, cold-start,
provider, and UX evidence.

## 13. Error Handling And Diagnostics

Every user-visible failure includes a short message, affected product/source,
whether cached data remains usable, recommended action, stable diagnostic code,
and correlated log event.

Core codes include:

- `BACKEND_NOT_READY`, `BACKEND_CRASHED`, `API_VERSION_MISMATCH`
- `SOURCE_TIMEOUT`, `SOURCE_RATE_LIMITED`, `SOURCE_HTTP_ERROR`
- `SOURCE_AUTH_REQUIRED`, `SOURCE_LICENSE_REQUIRED`, `SOURCE_PARSE_ERROR`
- `LEGITIMATE_EMPTY`, `UNSUPPORTED_RANGE`
- `ARTIFACT_MISSING`, `ARTIFACT_INVALID`, `RENDER_FAILED`
- `JOB_CANCELED`, `JOB_DEDUPED`, `JOB_BACKOFF`
- `CACHE_BUDGET_EXCEEDED`, `CACHE_VOLUME_LOW`, `CACHE_READ_ONLY`
- `HOST_PROFILE_INCOMPLETE`, `BENCHMARK_FAILED`, `GPU_FALLBACK_ACTIVE`
- `DATABASE_MIGRATION_FAILED`

Diagnostics shows:

- App/API/schema/build versions and target triple.
- OS/WebView versions and Windows 10 compatibility status.
- Coordinator queues, provider backoff, active leases, and recent jobs.
- Source health and last successful valid time.
- Cache budget/usage/reserve/orphans and database health.
- Sanitized host facts, benchmark version/result, selected profile, effective
  limits, overrides, and current pressure downshift.
- GPU fallback reason and renderer timing stages.
- Exportable, previewed, credential-safe support bundle.

Diagnostics must not claim browser, desktop, source, or renderer success from a
different validation category.

## 14. Testing Strategy

### 14.1 Backend Tests

- Registry schema and capability validation.
- Source request construction, fixtures, legitimate-empty/error distinctions,
  retry/backoff, and provider floors.
- Artifact identity, atomic generation publication, checksums, last-valid, and
  failure injection.
- Timeline actual-frame selection, latest-at-or-before following, and backfill
  bounds.
- Job priority, dedupe, cancellation, restart recovery, leases, and pruning.
- SQLite migrations, backup/recovery, settings schema, and cache accounting.
- API auth/origin/host/body limits, endpoint contracts, OpenAPI generation, and
  generated-client drift.
- Hardware recommendation formulas and safe fallback from missing signals.

### 14.2 Frontend Tests

- Workspace/dedicated navigation and URL state.
- TanStack Query cancellation and stale/current transitions.
- Map adapter source/layer add, replace, order, opacity, teardown, and fallback.
- Timeline states, gaps, follower deltas, first/latest controls, and cancellation.
- Legends and inspectors across all schemas/states.
- Settings recommendation/effective/override behavior.
- Notification allowlist, baseline, priority, dedupe, On/Off, and destination.
- Keyboard/focus/reduced-motion/non-color behavior and automated accessibility
  checks, backed by manual screen-reader/keyboard testing for critical flows.

### 14.3 Browser And Desktop Smoke Tests

- Use Playwright against the web renderer for rapid product-shell and API-stub
  flows.
- Use WebdriverIO/Tauri for packaged desktop lifecycle and native integration on
  Windows and Apple Silicon macOS.
- Each product smoke proves map/control/layer/legend/inspector/freshness and
  timeline or named non-frame state.
- Workspace smoke proves concurrent layers, ordering, legends, time followers,
  notifications, Projected Arrival Tool, and navigation away during work.
- Browser-mode success is not desktop success; static DOM tests are neither.

### 14.4 Renderer Tests

- Deterministic fixtures, output type/dimensions/bounds/nodata/alpha/legend,
  value probes, and tolerant golden images.
- Platform-independent meteorological values with explicitly reviewed
  pixel-level differences caused by graphics backends.
- PNG fallback and accelerated path parity for every accelerated product.
- Separate timings for source, decode, transform, render, encode, and publish.

### 14.5 Offline And Failure Tests

Simulate no network, timeout, rate limit/`Retry-After`, malformed/empty payload,
missing credential/license, empty/stale cache, corrupt database/artifact,
low/read-only disk, sidecar crash, cancellation during each pipeline stage, and
GPU/WebGL loss. The app must retain an explained usable state or Recovery Mode.

### 14.6 Desktop Lifecycle And Packaging Tests

- Single instance, sidecar startup/readiness/auth, port collision avoidance,
  crash cap, clean shutdown, and orphan-process check.
- Fresh install, upgrade with migration, uninstall, and rollback on Windows 11,
  Windows 10 22H2 compatibility, and Apple Silicon macOS.
- WebView2 bootstrap/current-runtime behavior.
- macOS nested sidecar signing, hardened runtime, notarization/stapling, and
  Gatekeeper launch for any distributed build.
- Paths containing spaces/non-ASCII, standard user permissions, sleep/wake,
  network change, low power, and thermal downshift.

### 14.7 Hardware Tuner Tests

- Synthetic profiles at/below/above every tier boundary.
- Windows integrated/discrete/multi-GPU and unavailable DXGI budget.
- Apple unified memory and Metal working-set limits.
- DIMM/WMI failure without startup failure.
- Benchmark cancellation, version invalidation, noisy-run rejection, and
  Conservative fallback.
- Disk reserve invariants and override rejection.
- Dynamic downshift/recovery hysteresis without losing current/last-valid data.

## 15. Implementation Phases

Every phase is a vertical, reviewable gate. After Phase 0, each phase produces
Windows x64 and Apple Silicon development packages and runs the applicable
smokes; packaging is not postponed to the end.

### Phase 0: Risk Retirement And Empty App

- Create the extractable project skeleton.
- Prove Tauri sidecar start/readiness/auth/shutdown and single instance.
- Bundle a minimal Python 3.14 sidecar with PyInstaller on both targets; decide
  whether Python 3.13 fallback is needed.
- Render MapLibre raster/image and alert-style GeoJSON layers.
- Prove restrictive CSP/capabilities and no remote assets.
- Prototype Windows/macOS host profiling and offline calibration.
- Build/install development packages on Windows 11, Windows 10 22H2, and Apple
  Silicon macOS.
- Record Windows installer and macOS signing/notarization decisions.

Gate: all feasibility risks have evidence and the plan is updated for any
failed assumption.

### Phase 1: Contracts, Storage, Security, And Coordinator

- Pydantic/OpenAPI models and generated TypeScript client.
- Authenticated loopback API/event stream.
- SQLite/Alembic, artifact generations, settings, jobs, registry, coordinator,
  source policies, and diagnostics skeleton.
- Lockfiles, CI matrix, SBOM/license pipeline, and fixture provenance rules.

Gate: demo product publishes atomically, survives restart, streams events, and
fails safely.

### Phase 2: Shell, Map Runtime, Workspace Skeleton, And Tuner

- Accessible shell, navigation, inspector, legends, layer manager, timeline,
  URL state, and MapLibre adapter.
- Host profile UI, benchmark, three profiles, overrides, disk reserve, and
  runtime downshift.
- Demo Workspace with raster/vector layers and time followers.

Gate: Conservative/Balanced/Performance behavior is reproducible on both
platforms and does not change meteorological output.

### Phase 3: Surface Plus Alerts

- Full updated Surface and Alerts contracts, source fixtures, current-first and
  last-valid behavior, dedicated views, legends/inspectors, and alert monitor.
- Prove immutable alert generations and current Surface lookback boundary.

Gate: first real vertical slice is daily-usable from cold, stale, offline, and
failed-source states.

### Phase 4: Timeline And Archive Foundation

- Persistent timeline availability, capability model, real-frame playback,
  issuance/advisory/date modes, bounded backfill, gaps, cancellation, and
  Workspace latest-at-or-before following.

Gate: no fake frames or false-empty archive states; live work wins over
backfill.

### Phase 5: Radar

- Catalog/sites/elevations, latest-first rendering, history, legends/inspector,
  storm attributes and selected-cell SRV, PNG authority, accelerated prototype,
  and hardware-profile resource gates.

Gate: Radar parity and fallback pass on all target tiers.

### Phase 6: Satellite

- Global platform/sector/product registry and all currently reachable GOES,
  Himawari, Meteosat, GK2A, and GMGSI parity.
- Scalar/RGB/sparse alpha, tiles, timeline, cancellation, stage timings,
  credentials/license states, and bounded prefetch profiles.

Gate: Satellite parity and cross-view responsiveness pass on Windows/macOS and
Conservative/Balanced profiles.

### Phase 7: RTMA And MRMS

- RTMA streams/regions/derived products/frame-locked points.
- MRMS current registry/native-detail tiles/PNG fallback/source identity.
- Shared timeline and initial approximately 12-hour windows.

Gate: both families and Workspace followers pass time/value/source parity.

### Phase 8: SPC, WPC, And Drought

- SPC outlook/fire/watch/report/MD layers.
- Expanded current WPC parity and issuance/no-area semantics.
- Drought issue dates/categories/state statistics.

Gate: legitimate-empty, issuance, context, legends, and details pass.

### Phase 9: Tropical

- Live global basins/storms, advisories, GIS/graphics, archives, cone/track, and
  floater behavior.

Gate: active and archive flows remain bounded and navigable while work runs.

### Phase 10: Water

- River/coastal/buoy networks, filters, viewport density, typed enrichment,
  stage gauge, and last-valid behavior.

Gate: network-specific parity and wide-view request safety pass.

### Phase 11: Full Workspace Parity

- Replace demo composition with all current Workspace families, exact layer
  order/legends, shared time, warnings/LSRs, Projected Arrival Tool, and
  performance-profile degradation tests.

Gate: Workspace is the primary daily workflow without breaking dedicated views.

### Phase 12: Release Hardening

- Install/upgrade/uninstall/rollback, database migrations, cache relocation,
  Recovery Mode, sanitized diagnostics, SBOM/licenses, signing decisions, and
  target platform matrices.
- Developer ID sign/notarize/staple any externally distributed macOS build.

Gate: clean-machine release candidates pass with no developer toolchain.

### Phase 13: Cutover Readiness

- Freeze/reconfirm parity baseline.
- Complete all product and Workspace matrices.
- Run automated suites and distinct real desktop, source, offline, performance,
  accessibility, owner-smoke, and rollback gates.
- Document limitations and preserve the current dashboard rollback path.

Gate: owner explicitly accepts NCH Weather Studio as the daily dashboard.

## 16. Product Parity Matrix Template

Create one entry for each dedicated product and Workspace:

```text
Family/workflow:
Baseline date and current-dashboard commit:
Current source/provider behavior:
Current controls and defaults:
Current layers/products:
Current valid-time/issuance/history behavior:
Current inspector/details:
Current legends/units:
Current cache/refresh/last-valid behavior:
Current loading/empty/stale/error states:
Current Workspace participation:
Greenfield implementation:
Clean-room evidence/fixture provenance:
Backend tests:
Frontend tests:
Renderer/value tests:
Windows 11 desktop smoke:
Windows 10 22H2 compatibility smoke:
Apple Silicon desktop smoke:
Conservative-profile smoke:
Accessibility/manual smoke:
Known differences and owner decision:
Cutover status: not-started | partial | blocked | passed
```

A visual resemblance is not parity. Exact values, times, sources, interactions,
failure behavior, and ownership/cancellation matter.

## 17. AI Implementer Rules

1. Work only in `nch-weather-studio/` unless the owner explicitly authorizes a
   separate current-dashboard documentation or comparison change.
2. Do not mutate the operational dashboard while implementing Greenfield.
3. Read this plan, the selected phase, current parity entry, and current Git
   state before editing.
4. Reconfirm drift-prone current-dashboard behavior before implementing its
   parity slice.
5. Do not import or copy old implementation code.
6. Record provenance for reusable owner-controlled assets and fixtures.
7. Keep Windows x64 and Apple Silicon behavior in the same contract; do not
   solve one platform by silently disabling parity on the other.
8. Maintain all three lockfiles and generated-client drift checks.
9. Use the smallest coherent vertical slice and validate it before advancing.
10. Do not add a product-specific polling loop, cache, timeline, map global, or
    job system that bypasses the shared contracts.
11. Provider policies are safety ceilings and are not loosened by a fast host.
12. Never remove the PNG/compatible fallback when adding accelerated rendering
    without a new owner decision and parity evidence.
13. Never label provider failure as legitimate empty or success.
14. Never make a browser/desktop/source/renderer claim from another validation
    category.
15. Preserve unrelated dirty work and do not commit/push unless explicitly
    requested.
16. Stop development listeners and sidecars at session end unless the owner
    asks to keep them running.

## 18. First Implementation Session Checklist

1. Confirm `F:\Python\dashboard_2026` and inspect `git status`.
2. Read this active plan and the current superfile Greenfield boundary.
3. Reconfirm the current parity baseline and record drift.
4. Confirm the selected work is Phase 0 only.
5. Create `nch-weather-studio/` and its README/decision records.
6. Initialize pnpm, uv, and Cargo workspaces with committed lockfiles.
7. Create minimal FastAPI health/readiness and generated-client pipeline.
8. Create minimal Tauri React/TypeScript app with restrictive permissions/CSP.
9. Implement sidecar bind-to-zero readiness/auth/shutdown prototype.
10. Render one transparent raster and one clickable alert-style vector in
    MapLibre.
11. Implement sanitized host fact collection stubs for both target platforms.
12. Package natively on Windows x64 and Apple Silicon.
13. Record exact pass/fail evidence and update Phase 0 assumptions.
14. Stop all listeners/processes.
15. Do not begin a real weather product until Phase 0 is accepted.

## 19. Open Risks

- Windows 10 22H2 is an owner-required target after ordinary OS support ended.
  WebView2 remains updated for a limited bridge period, but that does not make
  the underlying OS fully supported.
- Windows WebView2 and macOS WebKit differ; MapLibre, accessibility, media/audio,
  fetch streaming, and WebGL resource behavior need real target tests.
- Scientific/geospatial wheels and PyInstaller bundling may differ between
  Windows x64 and Apple Silicon, especially cfgrib/eccodes/GDAL-family stacks.
- Signing nested Python/native libraries and notarizing a Tauri macOS bundle
  can expose packaging issues late unless Phase 0 uses a realistic dependency.
- Apple unified memory and Windows integrated/discrete GPU budgets are not
  comparable by advertised VRAM. The benchmark and runtime budgets must remain
  authoritative.
- WMI DIMM data may be missing or misleading; it cannot be a startup gate.
- Public feeds, formats, licensing, credentials, rate limits, and availability
  can change.
- Full clean-room parity across 12 views/workflows is substantially larger than
  the June plan implied.
- A generic registry can become an untyped framework if product-specific logic
  is forced into configuration.
- Broad prewarm can overwhelm providers, disk, RAM, or thermal limits even on a
  fast machine; current user-visible work must retain priority.
- Arbitrary archive promises are constrained by provider history and request
  multiplication, not only by local storage.
- Accessibility for a WebGL map requires deliberate alternate feature access,
  not only automated DOM checks.
- Direct distribution on macOS requires an Apple Developer ID and notarization;
  personal local development signing is not an equivalent release path.

Each risk gets an owner, test, decision record, and expiry/revisit condition
before it can be marked closed.

## 20. Recommended Early Prototypes

Phase 0 must complete these with recorded Windows and Apple Silicon evidence:

1. Target-specific Tauri sidecar start/readiness/auth/shutdown and crash cap.
2. PyInstaller bundle containing at least one representative native/scientific
   dependency, not only pure Python.
3. MapLibre transparent bounded raster plus clickable alert polygons under the
   production CSP.
4. Local immutable artifact/tile serving with generated OpenAPI client.
5. SQLite migration/restart and atomic generation swap under failure injection.
6. Shared timeline with gaps, actual-frame playback, and latest-at-or-before
   followers.
7. Windows DXGI GPU budget and memory/core/disk profiling with missing-WMI
   fallback.
8. Apple ProcessInfo/Metal/unified-memory/disk profiling plus thermal/low-power
   observation.
9. Offline CPU/decode/disk/WebGL calibration, cancellation, versioning, and
   Conservative fallback.
10. Cache eviction preview that preserves database/settings/exports/last-valid.
11. Browser-mode and real Tauri smoke automation on both platforms.
12. macOS nested sidecar signing and a notarization feasibility run before any
   distribution promise.

If a prototype fails, revise the affected decision and acceptance criteria
before product work begins.

## 21. Host Requirements And Adaptive Tuner

### 21.1 Required And Recommended Specifications

The tiers are support policy, not a claim that every provider/product will meet
the same latency.

| | Minimum / Conservative | Recommended / Balanced | High / Performance |
| --- | --- | --- | --- |
| OS | Windows 10 22H2 x64 with current WebView2; Windows 11 x64; or macOS 14+ on Apple Silicon | Windows 11 x64 or supported macOS on Apple Silicon | Current Windows 11 x64 or current macOS on Apple Silicon |
| CPU | 4 physical cores (8 logical threads where SMT is available), or Apple M1-class | 6+ physical x64 cores / 12 threads, or 8-core Apple Silicon | 8+ physical x64 cores / 16 threads, or higher-tier Apple Silicon |
| Memory | 8 GiB usable system/unified memory | 16 GiB | 32 GiB or more |
| GPU | WebGL2 and benchmark pass; integrated/unified allowed; at least 1 GiB reported app budget when measurable | 3 GiB effective app budget or Apple unified-memory benchmark pass | 6 GiB effective app budget or higher-tier Apple unified-memory benchmark pass |
| Storage | SSD with the safety reserve plus 5 GiB available (normally 25–55 GiB under the default rule) | SSD/NVMe and at least 100 GiB available | NVMe and at least 250 GiB available |
| Display | 1366×768 effective pixels | 1920×1080 | 2560×1440 or larger |

Minimum behavior is intentionally reduced: one heavy render, small recent
windows, no broad prewarm, fewer GPU-resident frames, and earlier eviction. It
must retain every product and correct output.

### 21.2 Hardware Facts

Collect only facts needed for resource decisions.

Windows:

- Core/logical topology through `GetLogicalProcessorInformationEx`.
- Total/available physical memory through `GlobalMemoryStatusEx`.
- Optional DIMM capacity/count/configured clock through `Win32_PhysicalMemory`.
  Failure is diagnostic only.
- Per-process local/non-local GPU budget and current usage through
  `IDXGIAdapter3::QueryVideoMemoryInfo`; record the active WebView adapter where
  it can be correlated safely.
- Cache-volume capacity/available-to-user through `GetDiskFreeSpaceEx`.

Apple Silicon:

- Processor/active processor count, physical memory, thermal state, and Low
  Power Mode through `ProcessInfo`.
- Unified-memory status, current allocation, and recommended maximum working
  set through `MTLDevice`.
- Volume capacity through Foundation URL resource keys with the required
  privacy manifest reason.

Do not collect hardware serial numbers, MAC addresses, account names, or stable
fingerprinting identifiers.

### 21.3 Calibration Benchmark

Run after first install, after benchmark-version changes, after a meaningful
hardware/driver change, or on user request. Target 15–30 seconds on a
recommended machine; provide Skip and Cancel.

Offline fixture stages:

- CPU decompression and representative numeric transform.
- One representative raster decode/reprojection/render.
- Cache-volume sequential write/read plus small-file metadata operations, with
  temporary data removed afterward.
- MapLibre/WebGL raster upload, pan, layer replacement, and short animation
  frame-time/long-task measurement.
- Memory-pressure-safe allocation probe bounded far below available memory.

Repeat short stages, reject obvious outliers, store median/p95 and benchmark
version. Provider network latency is reported separately from real requests and
never changes the hardware tier.

### 21.4 Profile Outputs

Initial effective limits, subject to benchmark adjustment:

| Setting | Conservative | Balanced | Performance |
| --- | ---: | ---: | ---: |
| Heavy raster/decode slots | 1 | 2 | 4 maximum |
| Tile preparation slots | 1 | 2 | 4 maximum |
| In-memory decoded/artifact cache | up to 0.75 GiB | up to 1.5 GiB | up to 3 GiB |
| GPU-resident animation target | 3–4 frames | 6–8 frames | 10–12 frames |
| Neighbor-frame prefetch | Off | Current layer, nearest frames | Bounded active Workspace set |
| Satellite broad prewarm | Off | Selected platform/sector only | Selected plus measured adjacent scope |
| Cache ceiling | 25 GiB | 100 GiB | 250 GiB |

The in-memory cache is also capped near 9% of physical/unified memory, so the
table's ceiling is not allocated blindly. Formulas reserve CPU capacity for the
WebView/API and cap workers by physical cores. Provider connection limits and
minimum intervals remain lower hard ceilings where applicable. A benchmark may
recommend a lower profile than the specification tier; it never silently
promotes above the tier without a passing result.

### 21.5 Overrides And Runtime Guardrails

- Store detected facts, benchmark recommendation, selected profile, and manual
  overrides separately.
- Show the effective value and why it differs from the profile default.
- Allow lower limits freely. Warn and enforce safety invariants for higher
  limits.
- If available memory falls below the configured reserve, pause prewarm, trim
  decoded caches, then reduce new heavy jobs.
- If disk reaches its reserve, stop non-critical downloads, evict safe classes,
  and preserve current/last-valid artifacts.
- If DXGI/Metal reports budget pressure or WebGL frame timing degrades, reduce
  resident frames and switch costly layers to fallback.
- On macOS serious/critical thermal state or Low Power Mode, pause prewarm and
  reduce heavy slots. Apply analogous app-observable power/pressure signals on
  Windows when reliable.
- Use hysteresis/cooldown before restoring capacity to avoid oscillation.
- A temporary downshift does not overwrite the saved profile.
- If the app crashes repeatedly during accelerated rendering, Recovery Mode
  starts Conservative with GPU acceleration disabled for weather layers until
  the user reruns the benchmark.

### 21.6 Why DIMM And GPU Names Are Not Primary Tuning Inputs

Windows DIMM topology is helpful for support diagnostics, but clock/channel
configuration does not directly predict the Python decode, memory-copy, WebView,
and disk pipeline. Apple Silicon exposes unified memory rather than replaceable
DIMMs. Likewise, advertised VRAM is not the process's current GPU memory budget.
Usable memory, native budget APIs, measured stage throughput, and runtime
pressure are the cross-platform decision inputs.

## 22. Security, Privacy, And Accessibility

- Local-first and no telemetry by default.
- No analytics ID, crash upload, or diagnostics upload without a new owner
  decision and explicit opt-in.
- Network requests go only to documented providers selected by enabled
  products. Diagnostics lists current destinations by adapter, not secret URLs.
- Provider credentials use the OS credential store and are requested only when
  the selected product requires them.
- Logs redact headers, tokens, query secrets, local usernames/paths where
  practical, and provider payload content not needed for diagnosis.
- Diagnostics export has a preview and an additional redaction pass.
- CSP, Tauri capabilities, API auth, path validation, download limits, archive
  extraction limits, and dependency review are release gates.
- Target WCAG 2.2 AA for the full app. Maps provide keyboard-operable controls,
  focus-visible selection, textual feature results, status text beyond color,
  and reduced-motion behavior.
- Alert sound is user-controlled, never the sole cue, and does not become an OS
  notification.

## 23. Research Basis And Decision Log

Official references reviewed for this rewrite:

- Tauri sidecars, capabilities, CSP, WebDriver testing, Windows installers, and
  macOS signing/distribution:
  - https://v2.tauri.app/develop/sidecar/
  - https://v2.tauri.app/security/capabilities/
  - https://v2.tauri.app/security/csp/
  - https://v2.tauri.app/develop/tests/webdriver/
  - https://v2.tauri.app/distribute/windows-installer/
  - https://tauri.app/distribute/sign/macos/
- Frontend/map/client/accessibility:
  - https://vite.dev/guide/
  - https://react.dev/learn/typescript
  - https://maplibre.org/maplibre-gl-js/docs/
  - https://tanstack.com/query/latest/docs/framework/react/overview
  - https://openapi-ts.dev/openapi-fetch/
  - https://www.w3.org/TR/WCAG22/
- Backend/build tooling:
  - https://fastapi.tiangolo.com/features/
  - https://docs.astral.sh/uv/concepts/projects/sync/
  - https://pyinstaller.org/en/stable/index.html
  - https://docs.python.org/3.14/whatsnew/
- Windows lifecycle/WebView/hardware:
  - https://learn.microsoft.com/en-us/lifecycle/faq/windows
  - https://learn.microsoft.com/en-us/microsoft-edge/webview2/
  - https://learn.microsoft.com/en-us/deployedge/microsoft-edge-supported-operating-systems
  - https://learn.microsoft.com/en-us/windows/win32/api/dxgi1_4/nf-dxgi1_4-idxgiadapter3-queryvideomemoryinfo
  - https://learn.microsoft.com/en-us/windows/win32/api/sysinfoapi/ns-sysinfoapi-memorystatusex
  - https://learn.microsoft.com/en-us/windows/win32/api/sysinfoapi/nf-sysinfoapi-getlogicalprocessorinformationex
  - https://learn.microsoft.com/en-us/windows/win32/cimwin32prov/win32-physicalmemory
- Apple hardware/distribution:
  - https://developer.apple.com/documentation/foundation/processinfo
  - https://developer.apple.com/documentation/metal/mtldevice/hasunifiedmemory
  - https://developer.apple.com/documentation/foundation/urlresourcekey/volumeavailablecapacityforimportantusagekey
  - https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution

When implementation starts, create an architecture decision record for every
material departure from this plan. Recheck drift-prone version, platform,
lifecycle, security, and distribution guidance rather than treating this
research date as permanent truth.
