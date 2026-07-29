# Radar render optimization Phase 6 evidence

Phase 6 implements the feature-flagged, paused-frame L2 Reflectivity WebGL
pilot. The switch defaults off. PNG remains the first image, complete playback
path, compatibility fallback, and configuration-first rollback at every zoom.
No PNG image, source cache, or index schema is replaced.

The worker writes a separate `v1` polar artifact while it still owns the
already-decoded sweep. The browser uploads one `R8UI` texture containing sorted
native rays, native gates, encoded azimuths, and the server-derived RGBA lookup
table. The API exposes an artifact only while the switch is enabled and the
matching versioned file exists.

## Automated gates

Five fresh-process KGGW render-one samples used the same pinned
8,563,916-byte source with the switch disabled and enabled:

| mode | total p50 | total p95 | artifact p50/p95 | PNG hash variants |
|---|---:|---:|---:|---:|
| PNG control | 4,034.155 ms | 4,174.683 ms | n/a | 1 |
| Phase 6 enabled | 4,045.126 ms | 4,106.774 ms | 8.824/12.785 ms | 1 |

The enabled path changes p50 by +0.27% and p95 by -1.63%, passing the
no-more-than-5% first-PNG regression gate. Raw results remain in ignored
`cache/radar/.bench/phase6-png-control/` and
`cache/radar/.bench/phase6-webgl-candidate-02/`.

The representative KGGW artifact contains 720 rays by 1,832 gates with
250-meter spacing. It is 1,322,700 bytes including its JSON header and
1,322,314-byte texture, below the 2 MB gate. The retained gate values have
zero quantization error for this source.

- All five control and five enabled PNGs are byte-identical.
- All eight permanent Phase 0 golden rows pass with the feature enabled in
  scratch. Only the two L2 Reflectivity rows publish artifacts.
- Focused Radar validation passes 69 tests plus 42 subtests.
- Full pytest passes 288 tests plus 42 subtests and retains only the
  pre-existing Workspace assertion that still expects removed
  `WORKSPACE_REGION_BOUNDS`. A coordinator timing assertion that missed once
  by 4 ms passed twice immediately and passed in the final full run.
- Python compilation, edited JavaScript syntax checks, and `git diff --check`
  pass. Ruff passes the new Phase 6 modules/tests; the broader touched-file run
  still reports two pre-existing unused imports in `radar_service.py`.

## Browser acceptance

User-owned checks pass on `/radar` and `/workspace` for zoom-11+ activation,
a recorded 0.100 ms cached draw, same-frame visible color/mask/geometry parity,
and PNG-only behavior with the switch disabled. At extreme zoom, WebGL
correctly exposes native bins oriented with the radial scan, while the enlarged
legacy PNG exposes axis-aligned Web-Mercator raster pixels. No constant
horizontal or vertical displacement was found.

Active-playback and context-loss fallback passed. Under browser network
throttling, a KBYX-to-KAMX change canceled the stale KBYX fetches; that overlay
never reappeared after the selection changed. Phase 6 is closed. Phase 7 is
not authorized.
