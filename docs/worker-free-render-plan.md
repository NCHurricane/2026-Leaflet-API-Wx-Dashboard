# Task-Scheduler-Free Refresh and Rendering Plan

## Status and objective

This plan defines the path to a dashboard that requires **zero Windows Task Scheduler jobs** while retaining access to the full product catalog.

"Task-scheduler-free" does not mean that expensive data and rendering work disappears. It means that the FastAPI application owns that work through request-driven rendering and a bounded in-process refresh coordinator. Windows tasks may remain available as optional cache warmers, but correctness, freshness, history filling, archive updates, and cache cleanup must not depend on them.

Optional Windows tasks are a supported operating mode, not an independent
second refresh system. A task worker must participate in the same persistent
leases, freshness policies, provider budgets, deduplication keys, and atomic
publication path as request-driven work. Unmigrated legacy tasks that bypass
that contract are not safe to run concurrently and must not be described as
compatible.

The full-product contract is:

> Every product exposed by the dashboard can be discovered, fetched, rendered, and progressively filled on demand without an OS-level scheduler. Products do not all need to be pre-rendered. Restricted provider content still requires the credentials or license required by that provider.

The current machine's `Wx-Dashboard-*` task state is not a reliable premise for implementation: task queries were denied during review. Validate task state during final operator-owned smoke testing rather than asserting that all tasks are disabled now.

## Validated current-state gaps

| Domain | Current taskless state | Required correction |
|---|---|---|
| Alerts | Missing cache rebuilds, but stale data does not refresh correctly | Optimize the expensive geometry path, add NWS-safe stale-while-revalidate, and fix zoom/payload selection |
| SPC | Missing outlook data can invoke the worker, but one request launches the broad 49-fetch workload | Fetch only products due or requested; add official issuance-aware gates |
| Tropical live | Existing cache is accepted at any age | Add advisory/GTWO boundary gates plus a conservative active-page safety probe |
| Tropical archive | Historical seasons are lazy/immutable; the mutable current season depends on a scheduled refresh | Refresh the current season on archive presence and when its source has advanced |
| Water | Missing or stale station index returns an empty/warming response but does not start a rebuild | Add background index refresh and client retry |
| Surface observations | Already mostly request-driven | Move its bespoke thread path under the shared coordinator |
| Surface gradients | Missing gradients fail with "Worker may not have run yet" | Render the requested region/product in the background and report progress |
| Radar | Newest-frame on-demand rendering and history backfill already exist | Keep history/chunk assembly alive through an active-page lease instead of `Radar-Live` |
| Satellite | Live rendering already exists | Make all warming optional; bound cold-render memory/concurrency and expose provider capability errors |
| MRMS | Missing/stale paths exist, but the worker can prewarm unrelated products | Make the selected product explicit and remove broad request-path prewarming |
| RTMA | On-demand latest/render paths exist | Preserve progressive scrubber filling and use source cadence |
| WPC | Targeted cold and stale refresh mostly exists | Move dedupe/retry under the coordinator and use product issuance boundaries |
| Drought | Weekly, dated data is already naturally lazy | Retain long-lived immutable caching and check only when a new issue is due |
| Cache cleanup | Runs only through scheduler-owned lifecycle today | Make cleanup an application lifecycle job independent of page presence |

## Source-use contract

All user tabs and clients connected to one dashboard instance must share the same upstream request. A frontend polling interval is not an upstream polling interval: clients may read the local cache more frequently while the coordinator enforces the provider floor.

| Provider/source | Application budget and behavior | Basis |
|---|---|---|
| NWS Alerts API | One national/index refresh per instance no more often than every **30-35 seconds**; descriptive `User-Agent`; conditional requests where supported; exponential backoff for `429` and `5xx` | NWS recommends requests no more than every 30 seconds: <https://www.weather.gov/documentation/services-web-alerts> |
| AviationWeather | Prefer `metars.cache.csv.gz`; refresh no more than once per minute while Surface is active; station metadata no more than daily | The API documents a 100 requests/minute maximum and no more than one request/minute per endpoint/thread: <https://aviationweather.gov/data/api/> |
| IEM | Treat as cached secondary/enrichment/archive source; never query per tab; use at least a 1-5 minute application TTL for small current-data calls and long/immutable caching for archive/CGI results | IEM says API v1 is geared to small requests and older ad-hoc CGI services are resource-heavy: <https://mesonet.agron.iastate.edu/api/> |
| NOAA AWS/NODD | Poll no faster than publication cadence; cache prefix listings; dedupe `LIST`/`HEAD`/object downloads by source key; optionally support SNS/SQS without requiring an AWS account | MRMS is on a 2-minute cycle, RTMA is hourly, and NEXRAD/GOES notifications are available: <https://registry.opendata.aws/noaa-mrms-pds/>, <https://registry.opendata.aws/noaa-rtma/>, <https://registry.opendata.aws/noaa-nexrad/>, <https://registry.opendata.aws/noaa-goes/> |
| EUMETSAT | Cache discovery manifests; use only 1-2 download connections; dedupe large downloads; stop early with a capability message when credentials/license are missing | Current fair-use guidance is much higher than this proposed use, but download authentication and collection licenses apply: <https://user.eumetsat.int/resources/user-guides/frequently-asked-questions-for-data-store> |
| NHC | Refresh near official issuance boundaries; use a 10-minute active-page safety check for unscheduled special products; do not apply a blind hourly loop | Routine advisories are 03/09/15/21Z, intermediate advisories are normally three-hourly when required, and special advisories may occur anytime: <https://www.nhc.noaa.gov/pdf/NHC_Product_Description.pdf> |
| SPC/WPC | Fetch only products due after their own official issuance boundary; retry briefly after the boundary until the product timestamp advances | Official product schedules: <https://www.spc.noaa.gov/misc/about.html>, <https://www.wpc.ncep.noaa.gov/html/WPC_QPF_Product_Information.mht> |
| NWPS/NDBC/CO-OPS | Rebuild the shared station index every 20-30 minutes while Water is active; cache station details 5-10 minutes; serialize/back off detail calls; use NDBC bulk products | NWPS GIS downloads are generated every 15 minutes and NOAA guidance asks clients to respect update frequency and avoid heavy repeated calls: <https://water.noaa.gov/about/downloads>, <https://www.ndbc.noaa.gov/docs/ndbc_web_data_guide.pdf>, <https://api.tidesandcurrents.noaa.gov/api/uat/> |
| U.S. Drought Monitor | Check only when a new weekly issue is due; retain dated results as immutable | Official REST service: <https://www.droughtmonitor.unl.edu/DmData/DataDownload/WebServiceInfo.aspx> |

For providers without a published numeric limit, the values above are conservative application budgets, not claims about an official limit. A large public/multi-instance deployment must review aggregate traffic separately; in particular, IEM should not become the primary high-frequency feed for many independent installations.

## Target architecture

### Application-owned refresh coordinator

Create one coordinator, started and stopped through the FastAPI lifespan, with this contract:

```text
API request
  -> validate product and record/renew a short presence lease
  -> read and return the best complete cache immediately
  -> if missing, stale, or an expected source boundary passed:
       enqueue one deduped refresh by (provider, resource, product, region)
  -> coordinator applies provider floor, concurrency, retry, and backoff
  -> worker writes temporary output and atomically publishes the completed cache
  -> subsequent client poll observes fresh data/history
```

Requirements:

- Use a bounded executor/queue; do not create an unbounded daemon thread per request.
- Dedupe by the actual upstream/render key, not merely by endpoint name.
- Enforce provider-level concurrency and minimum intervals globally within the application.
- Track `queued`, `running`, `backoff`, `succeeded`, and `failed` state plus last source timestamp.
- Apply exponential backoff with jitter after provider or render failure while continuing to serve the last complete cache.
- Publish JSON, GeoJSON, imagery, metadata, and frame catalogs atomically so readers never observe partial work.
- Give active product/page keys a short lease, initially **90 seconds**, renewed by ordinary client polling. Heavy history/prefetch work continues only while the lease is active.
- Allow small cold paths to remain synchronous only when their measured worst-case latency is acceptable; large downloads, geometry work, gradients, and history fills stay background-only.
- Run cache cleanup and coordinator-state cleanup from application lifecycle schedules even when no page is open.
- Use a small SQLite/file lease and persisted provider-budget state under
  `cache/` whenever multiple Uvicorn processes or optional Windows task workers
  are enabled. Cross-process coordination may be deferred only for a documented
  single-process, task-free configuration.

`app_core/background_render.py` may remain as a low-level render helper during migration, but its process-local in-flight set and raw daemon threads are not the system-wide coordinator. Reuse the existing APScheduler dependency for coordinator ticks/lifecycle jobs if helpful; do not enable the current broad fixed worker schedule as the new default.

### Optional Windows task compatibility contract

Keep task workers available for operators who prefer scheduled prewarming, with
these requirements:

1. Prefer a thin task entry point that submits a targeted warm request through
   the running application's coordinator. If a standalone CLI must work while
   the application is stopped, it must call the same shared coordination,
   freshness, rendering, and publication modules rather than maintaining a
   separate worker implementation.
2. Before discovery, download, or rendering, both the application and task
   process must acquire the same persistent lease keyed by provider, resource,
   product, region, and render variant. A process-local lock or freshness check
   alone is insufficient.
3. Provider minimum intervals, backoff, retry state, and last-source keys must
   be shared across task and application processes. A task launch must not
   reset those budgets.
4. A task finding a fresh key or a lease already owned by another producer must
   exit successfully as `current` or `already_running`; it must not start a
   duplicate fallback fetch.
5. Every producer must write a unique temporary artifact and use the common
   atomic publisher. Tasks must never write directly over a cache file or frame
   catalog that the application may be reading or publishing.
6. Optional warmers must use bounded, explicit product sets. Retain broad
   prewarming only as an operator-selected profile whose aggregate provider,
   memory, and disk budgets have been validated.
7. Task sentinels must not suppress request-driven recovery. Coordinator
   source/cache state is authoritative; task history is diagnostic only.
8. Cache cleanup must respect active leases and temporary-artifact ownership so
   it cannot remove an application or task render in progress.
9. The optional-task installer, status output, and documentation must
   distinguish migrated coordinator-compatible warmers from incompatible
   legacy task definitions.

### Shared freshness policy

Add a shared policy registry that returns both source expectations and request budgets, rather than a single age-only helper:

```python
RefreshPolicy(
    provider="nws-alerts",
    min_request_interval=35,
    max_concurrency=1,
    next_expected_update=...,
    presence_required=True,
    stale_if_error=True,
)
```

The policy must distinguish:

- publication cadence from product accumulation duration;
- client cache polls from upstream requests;
- immutable archive keys from a mutable current-season/latest key;
- a selected product from broad catalog prewarming;
- restricted/unconfigured providers from transient failures.

### Response contract

SWR endpoints should return a common status block:

```json
{
  "cache_state": "fresh | stale | missing | refreshing | backoff | unavailable",
  "refreshing": true,
  "source_timestamp": "...",
  "cache_age_seconds": 12,
  "retry_after_seconds": 8,
  "capability": "available | credentials_required | license_required"
}
```

Clients continue displaying the last complete cache while clearly showing stale, warming, unavailable-provider, and retry states. A missing cold cache must not be presented as a successful empty dataset.

## Implementation phases

### Phase 0 - Measurement and request ledger

Implementation status (2026-07-23): Phase 0 measurements complete; gate failed.
The credential-safe JSONL
request ledger now covers application-owned `requests`, `urllib`, and NODD S3
transports, and Alerts emits structured timings for every stage listed below.
A valid post-decision two-pass live-NWS run and all required isolated cold
renders are recorded under `docs/perf/2026-07-23-worker-free-phase0/`.
`enriched_geom_cache.json` is no longer read or written; a bounded 1,024-entry
process-local geometry LRU reduced warm enrichment to 0.024 seconds and sampled
peak RSS from 3.291 GB to 1.022 GB. The complete warm path still took 5.306
seconds, or 4.992 seconds after the NWS response, including 3.853 seconds of
full-set low-detail simplification and 0.997 seconds serializing/writing the
full cache. The path is therefore not yet changed-alert proportional and the
near-one-second gate is not met. Phase 1 remains blocked. No browser proof has
been performed.

Do this before changing cadence.

1. Instrument every upstream request with provider, resource key, status, bytes, duration, cache result, and retry/backoff state. Never log credentials or signed URLs.
2. Instrument `run_alerts_worker` stages separately:
   - `enriched_geom_cache.json` parse;
   - `zone_geometry_cache.json` parse;
   - per-alert zone union;
   - low-detail simplification;
   - enriched-cache serialization/write.
3. Run Alerts twice in one process to separate cold-start and warm-process cost.
4. Record cold render time, peak memory, and downloaded bytes for Surface gradients, Radar history, representative GOES/Himawari tiles, and one EUMETSAT frame.

Alerts currently parses approximately 298 MiB of enriched geometry and 109 MiB of zone geometry, and the observed worker run was approximately 32 seconds. The gate to continue is a measured Alerts refresh path proportional to changed alerts, with a target near one second after the NWS response is available.

If module-resident zone geometry makes enrichment cheap, remove `enriched_geom_cache.json`. Otherwise replace it with bounded per-alert/per-key entries. Add Alerts artifacts to cache-retention policy in either case.

### Phase 1 - Coordinator foundation

1. Implement the coordinator, provider policies, state reporting, bounded executor, backoff, and graceful shutdown.
2. Add atomic-write utilities and migrate a small low-risk endpoint first.
3. Replace the duplicate WPC and Surface thread/lock implementations with coordinator calls.
4. Add an application-owned cleanup job. Do not require page presence for cleanup.
5. Add cross-process lease support or explicitly constrain the supported server configuration to one process until it exists.

Phase gate: ten simultaneous requests for the same cold key produce exactly one upstream fetch/render, shutdown leaves the prior cache readable, and a failed request enters bounded backoff rather than retrying on every client poll.

### Phase 2 - Alerts optimization and NWS-safe SWR

1. Apply the Phase 0 geometry-cache decision and process only new/changed alert IDs.
2. Base simplification on geometry provenance:
   - native NWS polygon: never simplify;
   - zone/SAME-derived geometry: simplify below the zoom threshold while preserving topology.
3. Fix the zoom vocabulary mismatch: the backend expects `low/high`, while the frontend currently sends `local/regional/national` and falls through to the full payload.
4. Use simplified national geometry below zoom 8 and bbox-filtered full geometry at zoom 8 or above.
5. Set the upstream NWS refresh floor to **35 seconds**. Workspace/Alerts clients may poll local cache at 20/30 seconds without creating additional NWS traffic.
6. Atomically publish the full, low-detail, and compatibility outputs as one generation so mixed versions are not served.

Do not implement the prior approximately 20-second NWS refresh proposal; it conflicts with NWS guidance.

### Phase 3 - SPC, Tropical, WPC, and Drought schedules

#### SPC

- Move official issuance boundaries into a tested configuration registry. Use `zoneinfo("America/Chicago")` for schedules specified in local CST/CDT rather than storing a fixed UTC conversion.
- At a boundary, request only the specific due or selected product. Do not run all 49 fetch tasks because one product is missing.
- During an approximately 20-minute post-boundary grace window, retry about every two minutes until the product's own issuance timestamp advances; do not poll outside due windows.
- Keep watches and mesoscale discussions on a shared 60-120 second active-page TTL.
- Ensure a worker sentinel cannot suppress a legitimate request-path recovery of a missing product.

#### Tropical

- Use 03/09/15/21Z routine advisory boundaries.
- Use three-hour intermediate boundaries when watches/warnings require them; do not use the previous two-hour assumption.
- Treat special advisories as unscheduled and use a conservative ten-minute safety probe only while Tropical/Workspace is active.
- Give GTWO its own 00/06/12/18Z boundaries.
- Compare payload issuance/advisory identifiers, not cache mtime alone.
- Keep completed HURDAT seasons immutable. Refresh current-season b-decks/catalog on archive presence and at their source boundary.

#### WPC and Drought

- Give WPC products their own issuance schedules; replace the universal 12-hour stale threshold.
- Keep targeted `product_ids={requested}` behavior and migrate its bespoke thread path to the coordinator.
- Keep dated Drought products immutable and check the latest weekly key only when the new issue is due.

### Phase 4 - MRMS and RTMA

- Treat the MRMS accumulation window as product meaning, not update cadence. NOAA's AWS registry states that MRMS data follows a two-minute update cycle, including accumulation products.
- Pass the selected MRMS product explicitly through discovery, download, conversion, rendering, and frame-catalog update.
- Remove request-path prewarming of unrelated MRMS products.
- Allow the selected MRMS product to check for a new source key every two minutes while its page lease is active; no-op when the source timestamp/key has not advanced.
- Keep RTMA on its approximately hourly source cadence. Preserve its on-demand latest path and progressive scrubber history fill.
- Bound conversion/render concurrency so MRMS, RTMA, Radar, and Satellite cannot simultaneously exhaust memory.

### Phase 5 - Water

- When the station index is missing or older than 20-30 minutes, enqueue `run_water_worker` once and return an explicit warming/stale response.
- Keep the prior complete index available while a rebuild runs.
- Have the client retry after the response's `retry_after_seconds` instead of treating zero stations as current truth.
- Fetch NWPS/CO-OPS layers and NDBC `latest_obs.txt` once per shared rebuild, never per viewport or user.
- Cache CO-OPS/NWPS station-detail requests for 5-10 minutes and serialize/back off provider requests.
- Preserve the existing atomic index write and validate network balancing after refresh.

### Phase 6 - Surface gradients

- Add a targeted on-demand gradient entry point for `(WORLD|CONUS, product)` rather than invoking the broad Surface worker.
- Serve existing observation points and the last complete gradient while the requested gradient is rendering.
- Use the shared AviationWeather bulk observation snapshot for all requested Surface products within the same minute.
- Cache station metadata daily and keep IEM fallbacks behind a shared provider budget.
- Bound gradient rendering separately from satellite/radar rendering because it is CPU/memory-heavy.

### Phase 7 - Radar and Satellite without required warmers

#### Radar

- Preserve the existing newest-frame-first on-demand path.
- When Radar/Workspace renews a lease, continue L2 chunk discovery/assembly and history backfill at a source-appropriate interval until the lease expires.
- Dedupe by site, level, product, elevation, and storm-motion parameters.
- Cache NODD prefix listings and optionally consume AWS notifications when configured; notifications must not be required.
- Return the newest usable frame quickly and report `history_filling` until the requested lookback is complete.

#### Satellite

- Keep live tile rendering, cache reuse, and bounded supertile behavior as the default full-product path.
- Make rapid-sector and Meteosat prefetch optional accelerators owned by the application while a relevant lease is active, not Windows tasks.
- Limit EUMETSAT discovery/download concurrency to 1-2 and dedupe the large source-grid download/materialization step.
- Report `credentials_required` or `license_required` immediately when appropriate.
- Preserve conservative Full Disk memory limits. Full-product availability permits a slower cold first view; it does not permit unbounded pre-rendering.

### Phase 8 - Zero-task cutover, health, and documentation

1. Change `workers/scheduler.py` from "OS tasks are the source of truth" to application-owned coordination and lifecycle maintenance.
2. Make `tools/install_tasks.ps1` explicitly optional. Its default behavior must not be required by startup documentation or health checks. Refactor retained tasks into clearly named optional-warmer profiles that satisfy the compatibility contract above; do not install or advertise legacy direct writers.
3. Remove task-sentinel freshness as the application health model. Report source/cache/coordinator health instead.
4. Ensure current-season Tropical refresh and cache cleanup are covered before retiring their scheduled paths.
5. Update `README.md`, `docs/architecture.md`, `docs/dashboard-change-and-enhancement-superfile.md`, and `docs/next-session-startup-prompt.md` in the cutover slice.
6. Provide a preview/list step before unregistering existing OS tasks. Actual unregistration is an operator-authorized migration action, not an incidental application startup side effect.
7. Expose optional-warmer outcomes (`warmed`, `current`, `already_running`,
   `backoff`, and `failed`) without treating task presence as an application
   health requirement.

## Verification and acceptance gates

### Automated policy tests

- Freeze time across every SPC, NHC, GTWO, WPC, Drought, MRMS, and RTMA boundary.
- Test SPC local-clock products in both CST and CDT.
- Assert NWS Alerts never performs more than one upstream request inside 35 seconds, even with multiple pages and users polling.
- Assert AviationWeather endpoint/cache downloads do not exceed their one-minute floor.
- Assert MRMS checks only the active product and no more frequently than every two minutes.
- Assert retryable failures use increasing backoff with jitter and continue serving stale cache.
- Assert ten concurrent callers and, if supported, two server processes produce one refresh for a key.
- Assert one optional task worker plus ten application callers for the same cold
  key produce exactly one upstream fetch/render and one published generation.
- Assert two simultaneous task launches for the same key dedupe through the
  persistent lease and share provider-floor/backoff state with the application.
- Kill the application during a write and confirm the previous cache remains complete/readable.
- Kill a task worker during a write and confirm the previous cache remains
  readable, the abandoned lease expires safely, and a later application request
  can recover the key.

### Isolated cold-cache tests

Use a temporary `CACHE_ROOT`; do not delete the operator's real cache as part of automated testing.

- Alerts: cold build, stale refresh, simplified national response, bbox-filtered full response, and native-polygon exactness.
- SPC: one requested product fetches only its due assets.
- Tropical: live feeds, GTWO, one storm, completed archive season, and mutable current season.
- Water: missing index returns warming, starts exactly one build, and later returns stations.
- Surface: observations plus every gradient product/region path.
- Radar: newest frame becomes available first and the requested history fills while the lease remains active.
- Satellite: representative GOES, Himawari, and configured EUMETSAT products; missing credentials produce a capability response rather than a hang.
- MRMS/RTMA: selected latest frame and progressive scrubber history.
- WPC/Drought: targeted current product and immutable dated cache.

### Whole-system zero-task acceptance

1. Confirm the application starts with no `WX_INPROC_WORKERS` opt-in and no required `Wx-Dashboard-*` tasks.
2. Start with an isolated empty cache and open every dashboard page/product family.
3. Confirm every cataloged product either renders/fills or reports a legitimate provider capability requirement.
4. Keep multiple Workspace and standalone tabs open; confirm request-ledger counts remain per provider/resource, not per tab.
5. Close pages and wait beyond the 90-second lease; confirm provider activity stops except application-owned cleanup/maintenance.
6. Confirm Radar and Satellite history/prefetch stop when their leases expire and resume on a later request.
7. Confirm disk-retention policies bound Alerts geometry, radar/satellite frames, temporary downloads, and coordinator state.
8. Perform user-owned browser smoke after static/API validation; do not describe curl, unit tests, or syntax checks as browser proof.

### Optional-warmer acceptance

1. Install only the migrated optional-warmer profile and confirm the dashboard
   remains fully functional when every task is disabled.
2. Enable the warmers and overlap a scheduled launch with cold browser/API
   requests for the same products. Confirm the request ledger shows one
   discovery/download/render per deduplication key and provider budgets remain
   global across processes.
3. Confirm task and application processes never publish mixed-generation JSON,
   imagery, metadata, or frame catalogs.
4. Confirm `current` and `already_running` task exits are successful no-ops, not
   warnings that trigger a second worker.
5. Exercise task/application crashes and cleanup overlap; confirm the prior
   complete cache survives and abandoned work is safely recoverable.
6. Run the full product and user-owned browser-smoke matrix with warmers both
   disabled and enabled.

## Risks and mitigations

- **Cold-start latency:** Radar history, Surface gradients, and large satellite products may take seconds or minutes. Return newest/last-complete data first, expose progress, and fill history progressively.
- **Memory contention:** Satellite source-grid materialization, radar decoding, and gradients can overlap. Use a shared weighted concurrency budget and measure peak memory before raising limits.
- **Multiple processes or task workers:** An in-memory set is insufficient
  across processes. Use the persistent lease and shared provider-budget state
  before enabling optional tasks or multi-process serving. Separate
  installations still generate separate provider traffic.
- **Daemon shutdown:** Raw daemon threads can vanish mid-write. Use graceful coordinator shutdown and atomic publication so interruption loses only unfinished work.
- **Provider outage/throttling:** Serve stale cache, honor `Retry-After`, and use jittered backoff. Never retry on every frontend poll.
- **IEM aggregate load:** Keep it secondary and heavily cached. Reassess or contact IEM before operating a high-volume public deployment.
- **EUMETSAT access:** Credentials, licensing, download size, and memory can limit a user's available catalog. Make capability state explicit rather than treating access failure as a renderer bug.
- **No open page means no live refresh:** This is intentional for data products. If future requirements include alarms while the UI is closed, that is a separate always-on monitoring feature, not part of this task-scheduler-free rendering plan.
- **Task migration uncertainty:** Current registered-task state could not be
  read during planning. Inventory and removal require an operator-visible
  verification step. Treat existing direct-write task definitions as
  incompatible until each is mapped to the shared coordination contract.

## Implementation completion definition

The plan is complete only when a fresh installation can run the dashboard with
no Task Scheduler setup, reach every supported product through
on-demand/progressive rendering, remain within the provider budgets above,
survive concurrent tabs and application restarts without corrupting caches, and
clearly distinguish temporary failure from credentials/license limitations. If
optional Windows warmers are shipped, completion also requires that they pass
the mixed task/application acceptance tests and can be enabled or disabled
without changing correctness or application health.
