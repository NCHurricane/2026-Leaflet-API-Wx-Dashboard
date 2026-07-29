# Radar render optimization Phase 7 evidence

Phase 7 extends the default-off L2 Reflectivity WebGL pilot to bounded
animation. PNG remains the immediate complete loop and per-frame fallback.
`LIVE_RADAR_WEBGL_ANIMATION_ENABLED` is separately gated and is effective only
when `LIVE_RADAR_WEBGL_ENABLED` is also enabled.

## Bounded client window

- Resident textures: current, two upcoming, and one prior; maximum four.
- Representative R8 texture storage: 4 x 1,322,314 bytes, or 5,289,256 bytes
  (about 5.04 MiB), using the Phase 6 KGGW artifact.
- Artifact fetches in flight: maximum two.
- Playback activates only after the active texture and two forward textures
  are ready. An unavailable texture leaves that frame on PNG without changing
  the timer or scrubber.
- Selection, elevation, lookback, motion, page teardown, context loss, and
  feature disablement abort stale work. Below zoom 10, the grace timer releases
  all textures; below zoom 11, PNG returns immediately.

## Automated gates

- Focused Radar validation passes 70 tests plus 42 subtests.
- Three JavaScript window/cadence tests pass.
- All eight permanent Phase 0 PNG golden rows pass with WebGL enabled in
  scratch-only `cache/radar/.bench/phase7-golden-01` through `-08`.
- Full pytest passes 292 tests plus 42 subtests and retains only the
  pre-existing Workspace assertion against removed `WORKSPACE_REGION_BOUNDS`.
- JavaScript syntax, Ruff, Python compilation, and `git diff --check` pass.

## Browser acceptance

Codex in-app browser checks used a restarted current API with both WebGL
switches enabled:

- `/radar`: a KAMX loop advanced continuously with four or fewer textures.
  Zoom 9 returned to PNG and released the window. A direct return to zoom 11
  showed PNG at entry, WebGL plus PNG during crossfade at 80 ms, and WebGL
  active with four textures by 430 ms without moving the scrubber.
- `/radar`: changing KAMX to KBYX during playback immediately paused the
  scrubber, removed all KAMX textures, and later activated one paused KBYX
  texture; no KAMX identity reappeared.
- `/workspace`: an 11-frame KAMX loop remained continuous across the
  30-second auto-refresh. Every sampled frame kept WebGL active with three or
  four textures; the refresh did not jump the scrubber or restart playback.

Phase 7 is closed. Phase 8 core-product expansion remains separately gated.
