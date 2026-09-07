# M12 first-use contract prototype

Date: 2026-09-07 UTC. The owner requested committing the existing checkpoint and
continuing the reviewed offline slice. Commit `649c5e1` contains the M12 native
renderer, limb correction, previous evidence and first-use design. The new
prototype/results follow that checkpoint. Application runtime, configuration,
routes, frontend, running dashboard and existing caches were unchanged. Nothing
was pushed.

## Result and decision

**14 synthetic contract tests and all 50 retained exact-RGBA cases pass.** Complete
native windows can render from explicit dependency snapshots without reading
unrelated radiance files. Unrelated arrival preserves a snapshot; missing inputs,
changed dependencies/source revision or lost ownership prevent publication in the
model. **Trustworthy cold strip discovery remains unproven; do not activate
partial-source runtime rendering from these results.**

The trusted-index mode deliberately receives an all-header reference oracle.
The cold mode receives headers only as each file arrives. Endpoint headers do
not establish the footprints of all missing entries, so cold mode stays pending
until the complete inventory validates. This is successful fail-closed behavior,
not proof that the provider cannot offer a suitable metadata contract. Matching
geometry from an earlier frame is not current-product authority.

## Artifacts and scope

- [Acquisition/scheduling model](fci_first_use_contract.py): immutable inventory,
  coverage, arrival/source revisions, pinned dependency snapshots, publication
  checks, restart revalidation and bounded shared demand.
- [14 contract tests](test_fci_first_use_contract.py): arrival permutations,
  withheld/composite inputs, gaps/overlaps/projection disagreement, incomplete/
  corrupt transfers, inventory validation, missing-input/negative readiness,
  dependency replacement, source revision, off-disk/full fallback, two-client
  deduplication, surviving ownership, scrub/pan cancellation, pressure, fairness
  and queue caps.
- [Bounded runner/quality adapter](check_fci_first_use.py): network rejection,
  child writes restricted to new scratch (plus the Windows null device), one
  child at a time and a resource watchdog. Each retained case renders once.
- [Successful ledger](fci-first-use-contract-002.json): simulation order, source
  verification, every RGBA result, script/runtime hashes and resource use.
- [Initial failed ledger](fci-first-use-contract-001.json): 14 tests passed, then
  Rasterio's Windows platform discovery hit the write guard at `\\.\NUL`, before
  source hashing, headers or rendering. The retry narrowly permitted `os.devnull`,
  retained the initial ledger/log and charged its 1.343 seconds to the same
  allocation. No failed expensive render was repeated.

The 40 owner-viewport references use **20260906T233000Z** and its 571,931,767-byte
pinned correction fixture. The ten earlier references use **20260906T120000Z**
and its original 1,143,762,592-byte acquisition. Both 40-file sets were SHA-256
verified first. This clarifies the plan's source selection: each reference must
keep its original frame. No reference was regenerated; no source was copied,
hidden, renamed, removed or downloaded.

The adapter reuses the native planner, calibration, warp and colorization with
explicit dependency paths. It retains one native render owner, serialized NetCDF
access, actual-window byte admission and adaptive array-cache limits. It writes
isolated PNGs through a guarded atomic callback. It does not invoke the live tile
route or implement production negative-cache/source-revision handling. All 50
whole-RGBA comparisons matched, including RGB beneath zero alpha; no case needed
full-grid fallback. The small tests separately exercise fallback readiness.

## Scheduling simulation

These are **virtual completion events and completed body-byte counts**, not
network latency, transferred bytes at an instant, first paint or speedup. Four
logical transfers can be active, and each dispatched batch completes in reverse
order. In-flight bytes are not modeled. Discovery demand precedes useful tiles;
unused full-bundle completion stays at the lowest priority.

| Mode, same 23:30Z inventory | First useful/reference tile: completed files / bytes | Complete viewport: completed files / bytes |
| --- | ---: | ---: |
| Whole-bundle readiness | 40 / 571,931,767 | 40 / 571,931,767 |
| Trusted index; initially six tile demands | 12 / 182,071,727 | 35 / 500,521,539 |
| Trusted index; whole viewport announced | 12 / 182,071,727 | 32 / 461,441,822 |
| Cold; no authoritative strip index | 40 / 571,931,767 | 40 / 571,931,767 |

The geometric dependency union is still 28 files. Discovery, four-transfer batches
and speculative completion explain why the illustrated viewport becomes ready
after 32 files. The first reference tile needs ten radiance files, rising to 12
with discovery. These counts do not predict seconds saved from the owner smoke.
Every simulated mode ultimately completes the bundle; earlier readiness is not
a claim of fewer total downloaded bytes.

The six-request case optimistically admits a queued demand immediately when a
response is ready. It uses the retained reference list as a deterministic demand
order, not Chrome's actual dispatch order. First useful/reference tile counts
happen to agree here. No browser scheduling or paint was measured.

The model caps records at four bundles, demands at 64 per client/256 total and
transfers at the configured 1–4. Overflow is explicit backpressure. Shared files
deduplicate; pressure/unknown capacity selects one transfer and pauses speculation.
Cancellation happens at a logical streamed-block boundary and preserves another
owner's demand. These are model checks, not real socket/retry/thread behavior or
production resource acceptance. No render admission occurs in source dispatch;
the native adapter reserves bytes after readiness. The acquisition model has no
native arrays or actual stream buffers.

## Bounds and evidence limits

The guarded attempts consumed **37.921 / 900 child seconds**, including the
failed import, small test retry, hashing, metadata and the single quality pass.
Peak sampled child RSS was **559,898,624 bytes (534 MiB)**; minimum sampled host
availability was **100,044,865,536 bytes (93.2 GiB)**, above the host-dependent
one-eighth-RAM floor. Sampling at 50 ms can miss brief peaks. Ledger scratch
values are sampled and omit tail writes; the final validation record totals
both run directories. New scratch remained far below 2 GiB. No provider request,
download or timing sample occurred; the prior **108+2** samples remain exhausted.

Scoped Ruff passed. Runtime hashes match the validated correction and checkpoint.
Prior 694-Python/54-Node results remain prior evidence, not rerun gates. This is
offline prototype/correctness evidence, not HTTP cancellation, browser promotion,
multi-frame native quality, OBS coexistence, cross-browser or secondary-machine
acceptance. The 115-second owner first-fill issue remains open.

## Next concrete review

Keep partial ingestion disabled. Cold readiness needs an authoritative
current-product entry-to-strip map or a verified format rule checked against
arriving headers. Do not infer that rule from two matching fixtures. A provider
metadata investigation/live header probe requires its own reviewed scope; this
run creates no live-acquisition or timing allowance.

The bounded fallback recommendation is a **complete-bundle transport/scheduling
slice**: worker-owned persistent HTTP connections, one configured M12 transfer
ceiling shared by foreground/prefetch frames, cancellable queue/stream boundaries
and coalesced shared demand. Keep the complete-manifest gate, native rendering
and PNG URLs. Fake-transport tests can precede any live trial. Its speed benefit
is unmeasured; review ownership/retry details before implementation and evaluate
connection reuse separately from scheduling in any later live comparison.

Expected transport seams are `satellite_v2/provider_eumetsat.py`,
`satellite_v2/providers.py`, `satellite_v2/service.py`, `satellite_v2/tiler.py`,
`satellite_v2/meteosat_prefetch_worker.py` and focused provider/service tests.
The narrower recommendation requires no native pixel algorithm, viewport route
or frontend change. If cold readiness is later supported, partial integration
also needs explicit snapshots through `fci_windows.py`/`renderer.py`, source
revision in artifact/URL identity, atomic ownership checks and a separately
reviewed viewport-registration contract in the satellite route/shared animator.
The prototype is not a drop-in application module.

Preserve the dashboard, caches, native quality, adaptive budgets, generation
cancellation, ready layers and Workspace order. No repeat owner smoke is needed
merely to reconfirm the delay. Other renderers and Greenfield remain deferred;
nothing here authorizes a push or new live/timed work.
