# Worker-Free Phase 2 Alerts Evidence

Captured 2026-07-23. Scope: Alerts optimization and NWS-safe
stale-while-revalidate only.

## Automated gate

- Focused Phase 2, Phase 0 Alerts cache, coordinator, standalone Alerts, and
  Workspace tests pass.
- Full suite: 145 tests passed, 42 subtests passed.
- Changed Python compiles; focused Ruff checks pass.
- Alerts/Workspace JavaScript passes `node --check`.
- Focused `git diff --check` passes.

The Phase 2 tests cover native-versus-derived provenance, national low-detail
selection, zoom-8 bbox-filtered full selection, stale serving with coordinator
submission, explicit cold warming, one-generation publication, interrupted
publication preserving the prior manifest, and the 35-second provider policy.

## Runtime cache evidence

Observed immutable generation `9f363d0006674f0586528a8ae37a467f`:

- full features: 489;
- low-detail features: 489;
- native polygons: 36;
- native geometry changes: 0;
- native features marked simplified: 0;
- zone-derived polygons: 453;
- derived features marked simplified: 453;
- vertices: 968,836 before and 52,894 after;
- vertex reduction: 94.54%.

A forced refresh from the sandbox could not reach either NWS or IEM. After the
strict empty-fallback correction, the failed run left the prior generation
manifest unchanged. This is failure-preservation runtime evidence, not a live
upstream success measurement.

During implementation, port 8000 had not yet been restarted and exposed the
pre-change Alerts endpoint. The operator subsequently disabled the scheduled
workers and restarted the terminal/API. Restarted-API verification returned:

- low request: 489 features, `display`, `low`, `fresh`;
- high NC-area bbox request: 25 features, `full`, `high`, `fresh`;
- both responses and the manifest used generation
  `ec279e92eb804fc3bf4a80b8e9a3bab6`.

This is API/runtime proof. No browser proof is claimed.
