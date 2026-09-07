# Next Session Startup Prompt

Use this as the bounded handoff for the next dashboard session. It summarizes
current operating truth; archived plans are evidence, not authorization.

Updated 2026-09-07 UTC after the approved offline first-use contract prototype.
The rendering correction and 50 prototype native-quality cases pass; cold source
discovery remains unproven and first-fill owner acceptance remains open.

The owner requested committing all prior work and continuing. `main` is now at
`649c5e1`, containing the M12 integration, limb correction, tests, prior audit
evidence and first-use design. The subsequent offline prototype/findings and
handoff edits remain uncommitted. Preserve the entire tree and all pinned sources;
do not reset to an earlier checkpoint. Nothing was pushed.

## 1. Orient before editing

1. Work only in `F:\Python\dashboard_2026`.
2. Read `AGENTS.md`, this file, `docs/README.md`, and
   `docs/dashboard-change-and-enhancement-superfile.md`.
3. Read `docs/architecture.md` and `docs/patterns.md` only for the selected
   system area.
4. Inspect `git status --short` and recent `git log --oneline`. Preserve all
   unrelated dirty work. Do not commit or push without explicit owner approval.
5. The next focus is already selected: a high-cost rendering-workflow audit of
   Satellite (especially Meteosat), Radar with product-specific WebGL evaluation,
   MRMS, and RTMA. The owner broadened architectural scope and requested
   adaptation to different machines and all three major browser engines.
   The bounded audit/measurement plan is approved and committed in `215729e`.
   The owner subsequently selected and authorized M12 integration. That runtime
   slice and its first-frame correction are in the working tree. Re-smoke still
   reports slow first fill; other renderer changes follow this remaining issue.

## 2. Current checkpoint

The September functional checkpoint `e200f74` records the owner-accepted MRMS
transition and Satellite zoom/sharpness changes, related page/test updates, and the
additional `img/20260831_nchurricane_logo.svg` asset. It follows `3773d47`
(functional) and `c8a4193` (documentation). The owner confirmed acceptance on
2026-09-06:

- Satellite request ceilings are CONUS z9, Full Disk z8, and Meso z9.
- Shared CSS preserves discrete Satellite tile/Radar PNG pixels during scaling
  and removes the native MRMS per-tile fade before promotion.
- MRMS keeps incoming PNGs hidden until display ownership changes; opacity
  controls do not reveal pending images.
- The additional logo is retained as an asset; canonical branding is unchanged.
- MRMS and SPC remain below Satellite in Workspace. The owner deferred the
  older proposals to move them above it.

Fresh verification on 2026-09-06: 77 focused Python tests passed after correcting
three stale CSS-version assertions to match the existing MRMS/Workspace pages.
The full suite passed **662 Python tests plus 42 subtests** and **54 Node tests**;
scoped Ruff, MRMS JavaScript syntax, and the added SVG's XML/embedded-content
checks passed. Diff whitespace checks and all 26 local Markdown links in the
seven active documents passed. Python reported 52 Matplotlib/xarray/NumPy
deprecation warnings.
Owner acceptance is recorded separately; no new controlled-browser run or
rendering benchmark was performed during this reconciliation.

Documentation checkpoint `5096e74` records that acceptance and initial audit
handoff. Subsequent planning edits broaden the brief in superfile section 4.8;
they do not change or newly benchmark the `e200f74` runtime.

`215729e` commits the expanded brief and bounded audit plan. The owner then
approved execution and specified OBS plus a browser, sometimes a document, as
the representative streaming workload. Preparation verified local hardware and
read the supplied second-PC report. The first available-input backend batch is
now recorded separately in `docs/perf/2026-09-06-rendering-audit/findings.md`.

Earlier completed checkpoints remain evidence:

- `3773d47` — Meteosat Phase 5 EUMETSAT acquisition improvements. Search
  pagination, five-minute feature metadata reuse, bounded transient retries, and
  a four-worker hard ceiling were accepted. The full gate passed 662 Python tests
  plus 42 subtests, all 54 Node tests, Ruff, and diff checks. The restarted owner
  smoke passed M12 acquisition, a five-frame catalog, responsive scrubbing, and
  clean terminal/console checks.
- `6020906` — keyless shared Esri basemap catalog and boundary policy. CARTO and
  USGS sources were removed. The four canonical choices are World Dark Gray
  Base, World Light Gray Base, USA Topo Maps, and World Imagery. CONUS-default
  pages keep states visible, show countries below displayed zoom 7, and add
  counties at displayed zoom 8. Tropical/Satellite keep countries visible, add
  states at displayed zoom 5, and counties at displayed zoom 8.
- `0e1eacb` — Meteosat Phase 4 corrections and M11 RSS-tuned selected-product
  workflow. This includes FCI native-read serialization, retained-layer
  generation ownership, delayed-feed catalog anchoring, and accepted RSS
  warming. Restarted M12/M11 owner smokes passed without dashboard lockups or a
  new NetCDF APPCRASH.
- `7bda975`, `7b2d9a5`, and `6759832` — Meteosat render budgeting,
  shared-canvas/zoom-aware rendering, and no-flash/scrub ownership checkpoints.
- `8ffcd14` — alert-only server-session cutoff, notification cadence/audio
  correction, and national Active Warnings rail. Owner smoke notified within 60
  seconds, and rail entries remained national while only the legend followed
  the viewport.

These validation counts describe the completed checkpoints; they are not proof
for later edits. Re-run the narrowest relevant gate after any change.

## 3. Closed work and retained evidence

- Cleanup Waves A through E are complete.
- Worker-free Phases 0–8 and the original Radar WebGL Phases 6–8 are complete.
  The Alerts near-one-second gate passed in its recorded run; older next-phase
  wording is historical. See the superfile section 9.2 closed-gate reference.
- The post-cleanup Satellite cross-page blocking prerequisite is complete.
- The bounded Meteosat latency family is complete through Phase 5. Its execution
  record is
  `docs/archive/meteosat-latency-overhaul-plan-2026-08-26.md`; do not resume it
  as an active plan.
- The superseded handoff that ended before `3773d47` is preserved at
  `docs/archive/next-session-startup-prompt-2026-08-26-pre-reconciliation.md`.
- `docs/perf/` contains phase-specific performance evidence. Preserve its
  recorded environment and validation category; benchmark evidence is not
  browser or owner proof.

## 4. What is active now

`docs/dashboard-change-and-enhancement-superfile.md` is the only active roadmap
for the current dashboard and Version 2 lane. Section 4.8 records the owner's
expanded brief and proposed resource/browser criteria. Audit questions include
stage costs, source-resolution/zoom correctness, first-frame/history behavior,
cache reuse, resource/queue ownership, and standalone/Workspace presentation.
Evaluate alternative architectures; old rendering exclusions do not constrain
recommendations. Section 4.8 now defines the approved 12-cell baseline,
45-minute/10-GiB backend limits, and 20-minute initial browser trace limit.
The first backend batch measured seven available timing cells, with five exact
source gaps remaining. Compare an isolated dashboard condition with the documented
OBS/browser/document condition without expanding the first batch's limits.

The previously named Radar WebGL candidates are `L2_RHO`, `L3_N0C`, `L3_DPR`,
`L3_DAA`, and `L3_DTA`. Evaluate other products for measured benefit too; native
low-resolution products do not automatically need WebGL. No renderer expansion
or activation is implemented by this brief. Other families, including the unified
Archive workflow, remain deferred. Meteosat request-level retries are already
implemented; interrupted individual streamed-transfer resume is still a proposal.

Plan separate backend-host and browser-client resource budgets, conservative
defaults/calibration, and overrides that preserve final quality. Treat hardware
hints as approximate; do not size every installation for the owner's rig.
Browser targets cover Blink/Chromium, WebKit, and Gecko. The proposed policy is a
rolling 30-month release-compatibility window plus a Baseline Widely available
feature floor, with optional acceleration and quality-equivalent fallbacks.
Pin actual browser/OS builds in the execution manifest. Available hardware is
the verified high-end i9/128-GiB/4070 Ti SUPER host, an older i7-8700/32-GB/RTX
2060 OMEN described by an October 2025 report, an owner-reported M1 MacBook Pro
with 16 GB and Tahoe 26.6, and older Windows PCs awaiting inventory. Refresh
remote-machine details before testing; a Mac browser run against Windows does
not test a Mac backend or an 8-GB host. See section 4.8 for sources and gaps.

`docs/nch-weather-studio-greenfield-plan.md` is a separate parked design, not a
dashboard phase. Its documented comparison was refreshed on 2026-09-06; exact
per-family parity, provider/dependency currency, and desktop feasibility still
need verification before any implementation. Greenfield is not the selected
next focus.

## 5. Operating boundaries

- Preserve application-owned refresh coordination and the single-process
  deployment contract unless a new design is explicitly approved.
- Preserve Satellite ready-layer/no-flash ownership, scrub debounce/generation
  cancellation, render budgeting, and FCI native-read serialization; preserve
  the accepted MRMS pending-image/native-tile promotion behavior.
- Keep current Workspace pane ordering. Preserve current runtime fallbacks
  while auditing; alternatives to PNG and existing rendering internals may be
  recommended with quality, correctness, resource, and compatibility evidence.
- Keep Alerts rail entries national; viewport filtering belongs only to the
  legend.
- Keep basemap and boundary behavior shared through `frontend/core/map-core.js`.
- Do not treat archived proposals, directory-audit findings, or evidence files
  as deletion or implementation orders.
- Distinguish static checks, automated tests, runtime probes, controlled-browser
  checks, owner smoke, and deployment proof in every handoff.

## 6. Exact next action

Read the [offline first-use findings](perf/2026-09-06-rendering-audit/fci-first-use-findings.md)
and review the next scope: authoritative cold-discovery investigation or the
narrower complete-bundle transport/shared-scheduling candidate. Partial-source
runtime integration is not supported by the available cold metadata. The
prototype is isolated audit code, not an application implementation. No new
provider/timing allocation or another owner repeat is implied.

Confirm Git state and read the [restarted owner-smoke diagnosis and next bounded slice](perf/2026-09-06-rendering-audit/owner-smoke-restart-0015.md),
then the [first-frame correction](perf/2026-09-06-rendering-audit/fci-limb-correction.md),
then the [M12 integration findings and broader smoke checklist](perf/2026-09-06-rendering-audit/fci-integration-findings.md).
The owner authorized integration after prototype review. The working tree now
contains M12 native windows, source/cache invalidation, actual-allocation memory
admission, adaptive retained-cache limits and `products-fci6` tile identity.
M12 background warming shares the live process and yields between small canvases;
M9/M11 retain their pools. Satellite's shared admission ceiling also responds to
host available/total memory. `psutil` is now a runtime dependency (already present
locally). No frontend renderer or Workspace ordering change was made.

The owner completed the restart/hard-refresh smoke and reports approximately
115 seconds for M12 Channel02. Read-only inspection of the existing Chrome tab
and 00:15Z frame artifacts separates catalog (5.382 s), the acquisition path
(61.317 s), and source-complete to last tile response (19.550 s). Browser response
completion is 86.254 seconds after selection; it does not localize the difference
from the owner's stopwatch/full-display observation. No repeat, navigation,
reload or new provider download was initiated by the agent.

The owner approved the [concrete first-use acquisition/scheduling
proposal](dashboard-change-and-enhancement-superfile.md#m12-first-use-acquisition-and-scheduling--proposed-slice-for-review)
in section 4.8 for an offline contract prototype before integration:
explicit expected-file identity, trustworthy cold geometry, complete native-window
coverage, immutable dependency snapshots, shared acquisition scheduling and
per-client cancellation. Endpoint headers alone cannot replace an authoritative
strip map. The prior all-header trace's 28 required files are an opportunity,
not proof that cold partial ingestion is safe. The proposed prototype keeps
unknown geometry on the complete-bundle path.

The proposal distinguishes the first six server-visible tile requests from the
whole viewport queued in the browser. A later viewport-registration contract
could prioritize all visible dependencies, but neither that frontend/API work
nor renderer integration is authorized yet. The approved offline allocation is
zero provider requests/bytes and zero timing samples, 15 minutes
combined child execution, 2 GiB scratch, 6 GiB sampled child RSS and at least
max(4 GiB, host RAM / 8) available memory. The completed prototype passed 14 small
contract tests and all 50 native-quality cases, consuming 37.921/900 combined
child seconds and peaking at 534 MiB sampled RSS. An initial Windows null-device
guard failure occurred before source work and remains recorded. The 40 owner
references use 23:30Z; the ten earlier references use their original 12:00Z
sources. No new downloads or timing samples were used. The 108+2 timing allocation
stays exhausted. Cold mode correctly waits for the complete bundle; the early
window mode uses an explicitly labeled all-header oracle, not proven live discovery.
Preserve caches and the current owner session. Broader M12 IR/composite,
playback/scrub, Workspace and other-satellite smoke remain open; another owner
repeat is not needed merely to reconfirm the delay.

The earlier, pre-correction smoke reported a 2–3-minute M12 visible first frame.
Read the [first-frame evidence](perf/2026-09-06-rendering-audit/owner-smoke-first-frame.md)
before proceeding: source-file completions span 72.7 seconds, followed by a
52.2-second tile-output span. This browser requests individual tiles rather than
the pilot's 3x3 canvases. The authorized correction now uses conservative native
limb windows and skips radiance reads for proven empty tiles. All 40 exact
owner-frame outputs match full-native references. Full-bundle acquisition remains
a separate first-fill cost; owner smoke is not accepted. OBS condition and other
smoke observations are still pending. Any further restart remains owner-controlled.

The correction gate passed **694 Python tests plus 42 subtests** and scoped Ruff;
the unchanged frontend retains its prior **54 Node tests**. Python reported 52
existing dependency deprecation warnings. All ten
integrated native-quality references match exact whole RGBA, and two service
cases verify center/neighbor publication and cache hits without source downloads.
These are automated/backend results, not owner, HTTP/browser or OBS acceptance.

The final six samples measured integrated visible-z8 at 2.461 s versus a 4.147 s
native control (40.7% less elapsed time, 77.5% lower maximum sampled RSS). Limb
was 4.318 s versus 4.200 s, a 2.8% slowdown. The **108/108** timing allowance is
used. The correction's additional **2/2** viewport samples are also consumed:
the same 40 individual local-source service calls took 56.969 seconds before
and 20.522 seconds after, with sampled peak RSS 1,502 versus 571 MiB. This single
pair has uncontrolled desktop/OS-cache conditions, including focused tests
overlapping the control; it is not browser/OBS or cross-machine acceptance.
Its 81.75 seconds of combined child execution stayed inside the new 240-second
bound. Further campaigns need a recorded allocation. Preserve the original 48
baseline samples, 54 prototype samples, final six integration samples, both
prototype revisions, correction control and pinned sources. Earlier candidates used prior controls;
three samples do not establish p95 or cross-machine speed claims.

Remaining gaps include source validity inside the limb, geographic overlay
alignment, multi-frame history/navigation, browser/OBS and secondary machines,
five exact missing source cells, and Radar/MRMS/RTMA alternatives. The proposed
Chromium/WebKit/Gecko policy still requires real Safari on the M1 and dated
browser/OS builds. Record isolated and realistic workload conditions separately;
OBS settings remain provisional until captured. Do not silently expand source
acquisition or reopen completed phases. Greenfield remains deferred; the requested
checkpoint commit is complete and no push is authorized.
