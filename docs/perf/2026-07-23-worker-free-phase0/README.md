# Worker-free Phase 0 measurement ledger

Status: Phase 0 measurements complete; Alerts gate failed and Phase 1 is
blocked.

## Upstream request ledger

`app_core/upstream_ledger.py` writes credential-safe JSONL rows to
`logs/metrics/upstream_requests.jsonl` by default. Set
`WX_UPSTREAM_LEDGER_PATH` to isolate a run or `WX_UPSTREAM_LEDGER=0` to disable
temporary Phase 0 collection. Rows include process identity, provider,
credential-free resource key (with only a hashed non-sensitive query
fingerprint), method, status, bytes, duration, cache result,
retry/backoff state, and outcome.

Static transport coverage:

| Transport | Covered request surfaces |
|---|---|
| `requests` | Alerts/IEM, Surface, SPC, RTMA, Radar/GCP/IEM, Satellite EUMETSAT, and shared geometry downloads |
| `urllib` | Alerts LSR, Drought, Radar, Tropical/live archive, Water, WPC, and archive services |
| S3 | Shared NODD Radar/MRMS/archive clients plus GOES/Himawari listing and downloads |

The repository scan found no remaining application-owned direct `requests`,
`urlopen`, or unwrapped S3 client call outside the ledger transport itself.
Library-internal network activity is not claimed as covered.

## Alerts gate

Run with:

```powershell
.\.venv\Scripts\python.exe -m workers.alerts_worker --measure-twice
```

The valid post-decision live-NWS result is in `alerts-two-pass.json`. Phase 0
removed `enriched_geom_cache.json` from the worker read/write path and replaced
it with a 1,024-entry process-local LRU keyed only by `affectedZones` and SAME
codes. The pre-existing disk artifact was not deleted.

Warm enrichment fell to 0.024 seconds with 453 cache hits, zero misses, and zero
zone unions. Peak RSS fell from 3.291 GB in the disk-cache baseline to 1.022 GB.
The complete warm pass was still 5.306 seconds, or 4.992 seconds after the NWS
response. Low-detail simplification took 3.853 seconds and full-cache
serialization/write took 0.997 seconds. Those stages still process the full
alert set, so the refresh path is not changed-alert proportional and misses the
near-one-second gate. The plan assigns changed-alert simplification and
generation publishing to Phase 2; Phase 1 must not start.

## Cold-render measurements

`tools/measure_phase0_command.py` records wall time, peak process-tree RSS,
upstream request count, and downloaded bytes for an isolated command. The
caller used a temporary cache/output root; the wrapper never deleted the
operator cache. All six scratch roots were removed after successful capture and
can be reproduced from upstream.

| Scenario | Wall time | Peak RSS | Requests | Downloaded |
|---|---:|---:|---:|---:|
| Surface WORLD temperature, 4,873 stations | 15.566 s | 5.717 GB | 2 | 603,295 B |
| Surface CONUS temperature, 2,307 stations | 24.588 s | 8.833 GB | 130 | 7,394,494 B |
| Radar KFCX `L3_N0B`, one-hour history, 18 frames | 22.631 s | 3.596 GB | 33 | 5,488,886 B |
| GOES-19 CONUS Channel 13 tile | 4.402 s | 298 MB | 27 | 5,255,883 B |
| Himawari-9 Full Disk Channel 13 tile | 10.008 s | 854 MB | 36 | 30,944,550 B |
| Meteosat-12 FCI Full Disk Channel 13 tile | 40.996 s | 428 MB | 43 | 675,721,065 B |

The CONUS Surface path's 130 upstream requests and the EUMETSAT tile's 676 MB
download are recorded Phase 0 budget concerns; no cadence or render behavior
was changed.

These are runtime measurements only. No browser smoke was performed.

Static validation: full pytest passes 117 tests plus 42 subtests; the only
warnings are the existing Radar colormap deprecations and denied
`.pytest_cache` write. Focused geometry-cache and ledger tests pass 8/8,
changed Python compiles, focused Ruff checks pass, the measurement JSON parses,
and `git diff --check` passes.
