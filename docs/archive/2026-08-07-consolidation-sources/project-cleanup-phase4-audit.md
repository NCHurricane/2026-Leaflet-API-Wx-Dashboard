# Project Cleanup Phase 4 Audit

Date: 2026-08-05

Status: complete in the current Phase 4 checkpoint.

## Scope and result

This audit inspected every root directory, including ignored content, to find
material that could be removed without changing dashboard behavior. The final
approved cleanup separates tracked source from generated state, removes proven
dead tracked files, clears bounded generated diagnostics, and prevents the
largest diagnostic accumulators from recurring.

## Removed tracked content

- `instructions.md`, superseded by the repository `AGENTS.md` instructions.
- `tools/check_level3_sites.py`, `tools/measure_phase0_command.py`, and
  `tools/phase0_render_probe.py`; all were unreferenced one-off probes.
- Eight `shapefiles/*.shp.iso.xml` and `*.shp.ea.iso.xml` Census/TIGER metadata
  sidecars. Runtime readers use the retained SHP/DBF/SHX/PRJ components.

The 12 tracked removals total 284,967 bytes. The separately relocated overlay
cache module was 16,313 bytes and remains tracked at its new path.

## Generated content cleanup

After a controlled shutdown of the two verified dashboard listeners, the
following ignored content was permanently removed with the user's explicit
backup acknowledgement:

- `cache/logs/`: 24 files, 191.16 MiB.
- `cache/metrics/`: one 53.85 MiB upstream-request ledger.
- `cache/archive/json/`: two regenerable files, 16.79 MiB.
- 18 non-venv `__pycache__` directories containing about 4.00 MiB.
- `.ruff_cache/`, `.pytest_cache/`, empty `.agents/`, empty `.codex/`, and the
  empty `cache/tmp/radar_live/` directory.
- 79 ignored files under `docs/perf/`, about 0.15 MiB. Tracked benchmark and
  golden evidence remains.

The cleared generated set was approximately 266 MiB. Normal imports and app
startup recreate some ignored `__pycache__` directories and may recreate
current archive directories; this is expected runtime state, not retained
source junk.

## Structural and retention corrections

- Moved `cache/overlay_cache_utils.py` to `app_core/overlay_cache.py` and
  updated all production, worker, test, benchmark, and architecture references.
  `.gitignore` can now ignore `cache/` without a source exception.
- Changed the observational upstream ledger from default-on to opt-in. Setting
  `WX_UPSTREAM_LEDGER_PATH` still enables an explicit measurement run; an
  explicit false `WX_UPSTREAM_LEDGER` value disables it.
- Added scheduled-worker log rollover at 5 MiB, retaining one `.1` backup. The
  limit can be overridden with `WX_WORKER_LOG_MAX_BYTES`.
- Added seven-day retention policies for `cache/archive`, `cache/logs`, and
  `cache/metrics` to the existing application-owned six-hour cleanup cycle.
  Existing product-cache retention periods were not changed.

## Retained after review

- `cache/satellite`, `cache/rtma`, `cache/mrms`, `cache/radar`, and
  `cache/overlays`: active warm data, fresh and already governed by product
  retention. Reducing it would trade disk space for cold-start/render cost.
- `.venv`: the configured local runtime and dependencies.
- `.git`: repository history; no meaningful Git garbage was found.
- `pal_preview/`: explicitly excluded, including ignored samples.
- `fonts/`: dynamically registered by `lib/font_utils.py`; removing individual
  files could alter Matplotlib output.
- `.claude`, tests, task tooling/definitions, required application data,
  static assets, shapefile components, and retained operator validation tools.

## Validation

- Focused gate: 58 tests passed plus 42 subtests.
- Complete gate: 393 tests passed plus 42 subtests; 31 existing dependency
  deprecation warnings.
- `git diff --check` passes.
- After cleanup, the dashboard was restarted as one application on port 8000.
  `/api/status`, `/radar`, `/workspace`, and `/api/radar/live/sites` all
  returned HTTP 200. This is API/runtime validation; no browser proof was
  performed or claimed.

## Boundary for any later cleanup

The remaining large disk footprint is overwhelmingly active product warm
cache plus the local virtual environment. Deleting or shortening either is not
junk cleanup: it changes cold-start readiness or reproducibility. Any future
reduction of those areas, fonts, task tooling, or palette-preview content needs
a separately bounded decision.
