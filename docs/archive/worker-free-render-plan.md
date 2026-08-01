# Task-Scheduler-Free Refresh and Rendering Plan

Archived 2026-07-31 after Phases 0-8 and the current-dashboard stabilization
acceptance completed. Current operational contracts live in `docs/architecture.md`.

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

Implementation status (2026-07-23): Phase 0 complete; continuation gate passed.
The credential-safe JSONL
request ledger now covers application-owned `requests`, `urllib`, and NODD S3
transports, and Alerts emits structured timings for every stage listed below.
A valid post-decision two-pass live-NWS run and all required isolated cold
renders are recorded under `docs/perf/2026-07-23-worker-free-phase0/`.
`enriched_geom_cache.json` is no longer read or written; a bounded 1,024-entry
process-local geometry LRU reduced warm enrichment to 0.024 seconds and sampled
peak RSS from 3.291 GB to 1.022 GB. A second bounded process-local LRU now
reuses per-alert enriched and simplified serialization by stable alert ID, raw
feature digest, and display-policy digest; unresolved geometries are retried.
The remediation run reused all 471 unchanged alerts and completed in 0.504
seconds total, or 0.082 seconds after the NWS response. The unchanged
near-one-second gate is met and Phase 1 is authorized. No browser proof has
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

Implementation status (2026-07-23): complete. `app_core/refresh_coordinator.py`
provides a bounded executor/queue, actual-key deduplication, 90-second presence
leases, provider concurrency/minimum-interval policies, exponential
backoff-with-jitter, credential-safe state reporting, periodic state pruning,
and graceful shutdown. FastAPI owns the coordinator through its lifespan and
exposes `/api/health/coordinator`. `app_core/atomic_io.py` provides unique-temp
atomic JSON/text publication; Surface observations are the first migrated
publisher and now return `refreshing` on a cold cache while the client retries.
Surface uses one region-level observation key and fans a single upstream fetch
into every product cache. Surface and stale WPC refreshes no longer create
bespoke daemon threads. Presence-only coordinator records report `idle`, not a
successful execution.
Six-hour cache cleanup is registered with the coordinator independently of page
presence and was removed from the optional legacy APScheduler profile.

This phase explicitly supports one application process. Startup rejects
`WEB_CONCURRENCY` or `UVICORN_WORKERS` values above 1; CLI worker-count settings
are also unsupported until persistent cross-process leases and provider-budget
state exist. Existing direct-write Windows tasks remain incompatible with
migrated refresh paths.

1. Implement the coordinator, provider policies, state reporting, bounded executor, backoff, and graceful shutdown.
2. Add atomic-write utilities and migrate a small low-risk endpoint first.
3. Replace the duplicate WPC and Surface thread/lock implementations with coordinator calls.
4. Add an application-owned cleanup job. Do not require page presence for cleanup.
5. Add cross-process lease support or explicitly constrain the supported server configuration to one process until it exists.

Phase gate: ten simultaneous requests for the same cold key produce exactly one upstream fetch/render, shutdown leaves the prior cache readable, and a failed request enters bounded backoff rather than retrying on every client poll.

Phase 1 gate result: passed. Focused tests prove mixed-product simultaneous
Surface requests for one region and ten direct coordinator submissions each
execute one refresh, and that one Surface fetch publishes every product cache,
bounded queue rejection, provider serialization/minimum spacing, request-lease
expiry, periodic work without page presence, credential-safe backoff,
atomic-file readability during graceful shutdown, lifespan start/stop, and the
Surface/WPC migrations. The full suite passes 135 tests plus 42 subtests.
A browser coordinator snapshot found product-level Surface queue fanout and
misleading success states for presence-only records; both are corrected.
Browser re-verification confirmed one successful Surface state per region,
truthful `idle` presence states, zero remaining active jobs, and maintenance
execution during the provider wait. Browser re-smoke also confirmed that every
Surface product loads its masked gradient; Altimeter took about five seconds on
its first load, which was accepted as cosmetic and needs no further change.

### Phase 2 - Alerts optimization and NWS-safe SWR

Implementation status (2026-07-23): complete. The Phase 0 processed-feature
LRU remains the changed-alert boundary. Geometry enrichment now records native
versus zone/SAME-derived provenance; low zoom simplifies only derived geometry
with topology preservation, while native NWS polygons remain exact. The
frontend and backend now share `low/high` zoom buckets: below zoom 8 one
national low-detail generation is used, and zoom 8+ reads bbox-filtered full
geometry. Alerts stale reads return the prior complete cache and submit one
coordinator refresh under a 35-second `nws-alerts` provider floor. Cold missing
cache returns an explicit 503 warming/backoff state rather than a successful
empty collection. Full, low-detail, and compatibility artifacts publish behind
one atomic generation manifest; interrupted/failing refreshes leave the prior
manifest readable.

The focused Phase 2 and retained Phase 0 geometry/cache tests pass. The full
suite passes 145 tests plus 42 subtests. A live 489-alert generation contained
36 native polygons with zero geometry changes and 453 simplified derived
polygons, reducing vertices by 94.54%. A forced upstream-failure run preserved
the prior generation. The running port-8000 process was not restarted and
still served pre-change endpoint behavior during the implementation pass.
After the operator disabled scheduled workers and restarted the terminal/API,
port 8000 returned 489 fresh national low-detail features and 25 fresh
bbox-filtered full features from the same generation. This is API/runtime
proof, not browser proof. Compact evidence is in
`docs/perf/2026-07-23-worker-free-phase2/`.

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

Implementation status (2026-07-23): complete. The tested registry in
`config/refresh_schedules.py` owns SPC local/UTC issuance boundaries, NHC
routine/intermediate and GTWO boundaries, product-specific WPC schedules, and
the Thursday 08:30 ET USDM release boundary. SPC request recovery now fetches
only the selected product and bypasses the legacy global sentinel; watches and
MDs share a 90-second application TTL. Tropical live reads renew coordinator
presence and submit separate advisory/GTWO scopes, using payload issue values,
two-minute post-boundary retries, warning-driven three-hour intermediates, and
a ten-minute active-page special probe. Only current-season b-decks are mutable.
WPC uses its existing targeted worker through the coordinator without the
universal 12-hour threshold; active MPDs use a 90-second TTL. Dated USDM
artifacts remain immutable and `latest` does not advance before publication.

Phase gate result: passed. Boundary tests cover every registered SPC and WPC
rule, including SPC CST/CDT conversion, plus NHC, GTWO, and USDM transitions.
Scratch-cache tests prove one selected SPC product is the only fetch even with a
fresh legacy sentinel, GTWO-only work does not fetch storm advisories, and a
dated USDM key is fetched once and then reused. Focused Phase 3 tests pass
13/13. After the first user browser smoke, focused corrections covered SPC
empty-watch timestamps/messages and valid Day 3-8 Fire products, WPC empty
selection/direct-load behavior, Drought selected-date styling, and current NHC
standard cone URLs. The focused browser-smoke regression set passes 18/18 and
the full suite passes 162 tests plus 42 subtests. Changed JavaScript syntax and
Python compilation, focused Ruff, and `git diff --check` pass. Local browser
proof covers those reported UI paths; issuance-boundary live-upstream proof was
not performed.

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

Implementation status (2026-07-23): complete. MRMS request paths now carry the
selected product through coordinator keys, discovery, download, conversion,
rendering, and overlay-catalog publication. The request worker no longer
prewarms an unrelated product set. A persisted latest-source key makes the
two-minute selected-product check a download/render no-op when the source has
not advanced. RTMA latest checks use an hourly success interval, retain a
two-hour discovery window for publication delay, and leave the existing
on-demand latest and progressive history paths intact. Overlay history fill now
uses the bounded coordinator instead of a raw daemon thread.

`app_core/render_budget.py` supplies one process-wide heavy-render slot by
default (`WX_HEAVY_RENDER_SLOTS` is the explicit override). MRMS, RTMA, live
Radar, and on-demand Satellite tile renders all acquire it, preventing those
families from materializing large render inputs concurrently.

Automated/API gate result: passed. The original focused Phase 4/coordinator
tests passed 14/14,
including selected-product keys, 120/3600-second success intervals, unchanged
MRMS source download/render no-op behavior, and cross-family render
serialization. Live isolated-port validation queued only `PrecipRate`, rendered
that MRMS source and one 17Z RTMA hourly frame, and then returned `current` with
about 107 and 3,590 seconds remaining on immediate repeats. The log contained
no unrelated MRMS product discovery. The complete suite reached 176 passing
tests plus 42 subtests; one unrelated Workspace assertion was
concurrently stale against user-owned `fitRegion` changes.

The first user browser smoke found incomplete scrubber horizons: partial MRMS
and RTMA caches suppressed history fill, and an initially empty RTMA-RU frame
response was never polled after six frames rendered in the background. The
correction keys history by requested hours, fills missing MRMS objects from
NODD, uses the newest end of newest-first RTMA discovery, gives RTMA-RU a
15-minute cadence, and polls/merges progressive frames chronologically. The
corrected Phase 4/coordinator suite passes 19/19 and Node syntax checks pass.
The corrected user browser re-smoke passed for MRMS, RTMA Hourly, and RTMA-RU
after a server restart/hard refresh, with no other issues found. Phase 4 is
closed and Phase 5 Water is authorized next. Evidence is in
`docs/perf/2026-07-23-worker-free-phase4/`.

- Treat the MRMS accumulation window as product meaning, not update cadence. NOAA's AWS registry states that MRMS data follows a two-minute update cycle, including accumulation products.
- Pass the selected MRMS product explicitly through discovery, download, conversion, rendering, and frame-catalog update.
- Remove request-path prewarming of unrelated MRMS products.
- Allow the selected MRMS product to check for a new source key every two minutes while its page lease is active; no-op when the source timestamp/key has not advanced.
- Keep RTMA on its approximately hourly source cadence. Preserve its on-demand latest path and progressive scrubber history fill.
- Bound conversion/render concurrency so MRMS, RTMA, Radar, and Satellite cannot simultaneously exhaust memory.

### Phase 5 - Water

Implementation status: automated gate passed on 2026-07-23. The first user
browser smoke exposed a partial index with zero river stations. Publication now
rejects missing or sharply reduced required networks; a corrected live rebuild
restored 12,761 river stations and the running CONUS API returned 12,162. The
request path now also treats a fresh-but-incomplete index as rebuild-worthy,
automatically queues recovery, and returns retry timing. The corrected
user-owned browser re-smoke passed on 2026-07-23. Phase 5 is closed and Phase 6
is authorized next. Evidence is in
`docs/perf/2026-07-23-worker-free-phase5/`.

- When the station index is missing or older than 20-30 minutes, enqueue `run_water_worker` once and return an explicit warming/stale response.
- Keep the prior complete index available while a rebuild runs.
- Have the client retry after the response's `retry_after_seconds` instead of treating zero stations as current truth.
- Fetch NWPS/CO-OPS layers and NDBC `latest_obs.txt` once per shared rebuild, never per viewport or user.
- Cache CO-OPS/NWPS station-detail requests for 5-10 minutes and serialize/back off provider requests.
- Preserve the existing atomic index write and validate network balancing after refresh.

### Phase 6 - Surface gradients

Implementation status (updated 2026-07-24): implemented and automated gate
passed. The first user-owned browser smoke found no product failures and
recorded similar full-resolution render times across products; a representative
CONUS `wind_speed` render used 2,246 points and completed in 4.2 seconds. That
timing parity is expected because every product interpolates and masks the same
grid. The smoke did expose one visual handoff defect: the browser displayed its
unmasked client-canvas fallback until the baked-mask PNG completed. The client
now suppresses that fallback while server work is pending, immediately adopts
the prior masked PNG returned by stale-while-refresh, and shows observations
alone when no prior PNG exists. The fallback remains available only after the
server path finishes without an image. The corrected user-owned re-smoke passed
for every CONUS and WORLD product on 2026-07-24. Phase 6 is closed and Phase 7
is authorized next.
`/api/data/surface-gradient` now serves the last complete artifact while it
warms observations or renders exactly one `(WORLD|CONUS, product)` key. Surface
observations share one process snapshot per region/minute, AviationWeather
station metadata is cached daily, IEM fallbacks use the coordinator's shared
provider budget, and gradients have a separate bounded render slot. The client
polls explicit warming state until the requested artifact is ready. The Phase 6
suite passes 24/24, including all 18 product/region artifact paths on isolated
reduced scratch grids; broader Surface/coordinator tests pass 37/37 and
correction-focused validation passes 46/46. Full pytest reaches 214 passing
tests plus 42 subtests, with only the pre-existing
Workspace assertion against the concurrently removed
`WORKSPACE_REGION_BOUNDS`. Evidence is in
`docs/perf/2026-07-23-worker-free-phase6/`.

- Add a targeted on-demand gradient entry point for `(WORLD|CONUS, product)` rather than invoking the broad Surface worker.
- Serve existing observation points and the last complete gradient while the requested gradient is rendering.
- Use the shared AviationWeather bulk observation snapshot for all requested Surface products within the same minute.
- Cache station metadata daily and keep IEM fallbacks behind a shared provider budget.
- Bound gradient rendering separately from satellite/radar rendering because it is CPU/memory-heavy.

### Phase 7 - Radar and Satellite without required warmers

Implementation status (2026-07-24): complete. The automated gate and corrected
user-owned browser/live-provider re-smokes passed. The coordinator now owns
lease-bound recurring jobs that run at a source/provider interval only while
the 90-second presence lease is active. Radar activity keys include site,
level, product, elevation, and storm-motion variant; newest-frame synchronous
fallback remains intact, progressive fills report `history_filling`, and Level
2 chunk-prefix listings have a 30-second process cache. Satellite keeps live
on-demand tiles as first priority, then starts selected rapid-sector or
Meteosat source acceleration after a five-second delay while presence remains
active. Source downloads deduplicate per platform/sector/frame, EUMETSAT FCI
downloads are limited to one or two, and unavailable account state returns
`credentials_required` or `license_required`. The focused suite passes 53
tests plus 42 subtests. Evidence is in
`docs/perf/2026-07-24-worker-free-phase7/`. Phase 7 is closed and Phase 8 is
authorized next. The first Radar browser smoke
found that the normal five-minute success cadence prevented a longer lookback
from continuing after its initial one-hour batch. Incomplete history now
bypasses that cadence and only queued/running work reports as filling. The same
smoke also found two simultaneous port-8000 listeners; removing the stale
localhost-only listener restored cross-page navigation. A clean server restart
and Radar/Satellite re-smoke were required. Radar re-smoke passed. Satellite
passed GOES-19 CONUS but exposed three ordering/fanout defects: MESO used a
CONUS-scale view with zoom-7/8 full-sector warming, Himawari's accelerator could
overtake live viewport tiles, and cold Meteosat primed all six FCI frames at
once. Meso now fits current frame bounds and warms zooms 5-6, accelerators wait
for live tiles to become idle, and uncached neighboring frames are not primed.
Follow-up testing showed an abandoned Meteosat-11 RSS accelerator rendering at
least eight more frames after a switch to Meteosat-9 Full Disk. Page-instance
selection identity now cooperatively stops the old accelerator before its next
frame while preserving another page's legitimate interest in that selection.
The one-worker application accelerator also runs in-process so Windows does not
spawn a child that re-imports Radar/Py-ART during Satellite work. The corrected
RSS-to-Full-Disk user re-smoke passed: the old RSS accelerator stopped without
starting more abandoned frames, and the mid-session Py-ART banner did not
recur.

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

Implementation status (2026-07-25): complete; the focused automated gate,
whole-system browser smoke, and optional-warmer enabled/disabled acceptance
pass. `workers/scheduler.py`
registers no broad schedule, startup no longer treats task sentinels as health,
and `/api/health/coordinator` reports application-owned source/cache/coordinator
plus lifecycle-maintenance state. Current-season Tropical archive refresh stays
request-driven and six-hour cleanup remains coordinator-owned. The task tool
defaults to a mutation-free preview and offers bounded `core` and `surface`
profiles through `workers.optional_warmer`; these call the running localhost API
and expose `warmed`, `current`, `already_running`, `backoff`, or `failed`.
The preview found 13 existing `Wx-Dashboard-*` legacy tasks, all disabled. No
tasks were registered, enabled, disabled, or unregistered. Phase 8 focused tests
pass 6/6; the combined cutover/lifecycle/schedule run passes 18/18. Ruff,
Python compilation, PowerShell parsing, and the real read-only task preview
pass. Full pytest reaches 240 passing tests plus 42 subtests; its only failure
is the pre-existing Workspace assertion against the concurrently removed
`WORKSPACE_REGION_BOUNDS`. A temporary port-8011 runtime probe returned
application-owned health, a running single-process coordinator, registered
cleanup, and no task-health dependency. The first user-owned zero-task/browser
smoke found three UI/data-selection defects: unchanged WPC image URLs could
leave yesterday's chart in the browser cache, MRMS initialized at the oldest
frame, and Satellite's aggregate cached-tile count obscured on-demand viewport
rendering while neighbor priming made newest-first behavior harder to prove.
WPC image URLs now include the payload update token, MRMS initializes and
continues progressive filling at the newest frame, and Satellite displays the
newest frame before any neighbor priming and reports that visible tiles load
from cache or render on demand. A separate second timestamp line reports
Loading, Fresh, Stale, or Ready state without moving or repurposing page message
elements. The correction suite passed 39/39 plus Node syntax, Ruff, Python
compilation, and diff checks. A local in-app browser re-smoke confirmed the
versioned WPC URL and Fresh state, MRMS at 28/28 with its slider at maximum, and
Meteosat-12 Channel 13 requesting the 02:00Z newest frame before 01:45Z.
The next user-owned re-smoke passed WPC chart/timestamp parity and newest-first
MRMS/Satellite behavior, with no other product errors, but exposed Channel 14
being offered by the UI while omitted from the backend registry and showed that
the timestamp state was limited to the three corrected pages. Channel 14 is now
registered across GOES, Himawari, SEVIRI, and FCI mappings. The shared reporter
now supplies Loading/Ready state to every standalone page, while SPC and Surface
also pass their computed stale state. Satellite no longer derives Ready from
catalog/layer acceptance: it remains `Loading visible tiles...` until a
successful tile-load event belongs to the active layer. The expanded correction
suite passes 42/42 plus 16 Node syntax checks and Python compilation. Browser
proof held Loading with 0/40 rendered Satellite tiles, changed to Ready only at
23/40 loaded tiles, and confirmed the new Ready line on Drought. A fresh
temporary server accepted the Channel 14 legend/catalog path; the catalog probe
then stopped only at unavailable outbound NOAA S3 access, not channel
validation. The continuing user-owned re-smoke now passes Surface, Satellite,
Alerts, MRMS, Drought, WPC, and Water. RTMA also passes the `Stale` to `Ready`
state transition; its observed cold fresh-data load took about 60-75 seconds,
consistent with source download/render and possible shared heavy-render-slot
queueing. Repeated RTMA testing exposed the latest refresh and request render
concurrently downloading the same GRIB through one fixed `.part` path. GRIB
acquisition is now serialized per destination and rechecks the completed cache
after waiting; the focused Phase 4 suite passes 11/11 plus Ruff and compilation.
The corrected RTMA user re-smoke passed without the collision recurring, and
Radar also passes. Leaving MRMS stopped page polling while the already-submitted
bounded selected-product history batch finished, which is expected; it must not
launch new batches after departure. SPC and Workspace also pass. Tropical
initial refresh exposed a missing `setTimeoutFn` dependency in the engine
context; the dependency is now wired and the focused Tropical/browser gate
passes 23/23 plus Node syntax and Ruff. The corrected Tropical user re-smoke
passes, completing the user-owned whole-system browser smoke. The installed
`core` and `surface` optional warmers then passed enabled runs through the
localhost API. With both profiles disabled, their logs did not advance across
the Core five-minute interval, coordinator health remained application-owned,
and the user-owned browser matrix passed Surface, Alerts, Radar, SPC, Tropical,
and Water. The final re-smoke corrected SPC's false universal 90-minute stale
classification by using issuance-aware API state and the outlook issue time.
Surface now honors coordinator retry timing instead of downloading the full
observation payload every second during backoff. SPC Days 1-5 recovered stale
products to Ready with current vectors/overlays, and Surface reached Ready with
bounded polling. Phase 8 is closed.

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

Acceptance result (2026-07-25): passed. The bounded `core` and `surface`
profiles were installed and exercised while enabled, including `current` and
`warmed` outcomes. They remained API-only clients; cache work and publication
stayed inside the application coordinator. Both profiles were then disabled.
The Core log missed its next scheduled five-minute run, the Surface log did not
advance, `/api/health/coordinator` remained healthy, and the user-owned
browser-facing matrix continued to return 200 and Ready/display states. Focused
post-correction validation passed 42 tests plus JavaScript syntax and diff
checks. No legacy-task unregistration was performed.

Post-closure extension (2026-07-25): bounded `rtma` and `mrms` profiles were
added and registered disabled. RTMA targets only CONUS Hourly/Rapid Update
Temperature latest frames; MRMS targets PrecipRate, LL 60-minute Rotation
Track, and Instant MESH. These profiles have not yet undergone their own
enabled browser acceptance and must remain disabled during Radar performance
benchmarking because RTMA/MRMS share heavyweight render capacity with Radar.

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
