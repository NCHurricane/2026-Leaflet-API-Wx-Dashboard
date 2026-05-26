# Design Doc — Unified Scrubber Mode (Radar, MRMS, RTMA)

> **Status:** Phase 2 (Radar) COMPLETE. Phase 3 (MRMS) ready to start.
> **Scope:** `weather.html` Radar, MRMS, and RTMA tabs. Satellite and Archive modes are out of scope.

---

## Concise intro (for a new session)

> **Phase 2 (Radar refactor) is complete and tested.** The Radar tab now uses unified scrubber mode: site selection immediately shows the latest frame + scrubber with 1-hour lookback slider. Current/Animate buttons are removed. Playback is controlled via Play/Pause button. The scrubber UI (frame count, timestamp) now updates correctly. Auto-refresh appends new frames to the scrubber and auto-advances the thumb if the user is on the latest frame.
>
> **Next:** Phase 3 applies the same pattern to MRMS (remove `_mrmsScrubMode`, add lookback slider, wire auto-update checkbox). Then Phase 4 for RTMA. Then Phase 5 cleanup.

---

## 1. Problem

The Radar, MRMS, and RTMA tabs each have a **Current / Animate** two-mode toggle:
- **Current** shows a single live latest image
- **Animate** shows a scrubber backed by an array of historical frames

This dual-mode structure has created several intractable issues:

- Two separate code paths for auto-refresh, leading to inconsistent behavior (e.g., the long-running mystery where new frames appeared to be missed in Animate mode but picked up after a Current→Animate switch)
- Complex state cleanup on mode transitions (`_radarScrubMode`, `_rtmaScrubMode`, `_mrmsScrubMode` flags, `_radarScrubFrames = []` resets, scrub frame index resets, play-timer cleanup)
- Mode-exit side effects that fire `_flashAnimateNewFrame()` in unexpected contexts
- Duplicate logic in `loadRadarLiveLatest` vs `loadRadarScrubberFrames` that fetches similar data through different paths
- Cognitive friction for users — "Current" and "Animate" are not obviously distinct concepts
- Three modes' worth of edge cases triple every time we add a feature like jump-to-latest or capped frame retention

## 2. Goals

- One unified state per tab where the latest image and the scrubber coexist
- Simpler auto-refresh logic with one code path per tab
- Playback becomes an explicit user action (Play button) rather than a mode
- Lookback slider becomes the single source of truth for "how much history to load"
- Adjusting the lookback slider dynamically expands or trims the loaded history
- New auto-update behavior (jump-to-latest, caps, MRMS/RTMA checkboxes) folds into the unified path instead of being bolted on top of the old two-mode system

## 3. Non-Goals

- **Satellite tab stays unchanged.** It already has a working unified scrubber with `Auto` toggle.
- **Archive mode stays separate.** Archive deals with arbitrary date ranges, snapshots, and pre-recorded windows — keeps its own state and entry/exit.
- **No backend API changes.** `/api/radar/live/frames`, `/api/overlay/frames`, and the underlying workers stay as they are.
- **No new tab structure.** Radar, MRMS, RTMA remain three distinct tabs.

## 4. Proposed UX

### On tab/site/product/region selection

1. **Immediately** show the latest frame as a single visible overlay (no loading state needed for the visible image)
2. **In parallel, background-load** the scrubber frames within the current lookback window
3. Once frames are loaded, the scrubber bar becomes interactive
4. The latest frame in the scrubber is what's currently visible — they are the same image

### Sidebar controls (per tab)

- **Lookback slider** — default 1H. Range 1H to 12H. Adjusting it triggers a fetch.
- **Auto-update checkbox** — default ON. Controls whether the slider thumb auto-advances to new frames as they arrive.
- *(Existing per-tab product/site/region controls — no change)*

### Bottom scrubber bar

- **Play/Pause button** — toggles auto-advance through the loaded frames
- **Step backward / step forward** — already exists
- **Speed controls** — already exists
- **Frame slider** — already exists, scrubs through the loaded array
- **Timestamp display** — already exists

### Things being removed

- The **Current / Animate** mode buttons inside each tab's sidebar mode-controls block
- `_radarScrubMode`, `_rtmaScrubMode`, `_mrmsScrubMode` flags (or their meaning collapses to "is this tab active")
- Per-tab Animate button behavior (separate `_flashAnimateNewFrame`, mode-entry flows)

## 5. State Model

For each of {Radar, MRMS, RTMA}:

| State | Lifecycle | Notes |
|-------|-----------|-------|
| `_<tab>Frames[]` | Populated on tab/selection entry, mutated by auto-refresh and lookback changes | Always reflects current loaded window |
| `_<tab>FrameIndex` | Set to last frame on initial load; user can scrub | Survives auto-refresh appends via cap-shift logic |
| `_<tab>PlayTimer` | null when paused, timer ID when playing | User-controlled via Play button |
| `_<tab>AutoUpdateEnabled` | Reads from checkbox | Gates slider auto-advance, not polling |
| `_<tab>LookbackHours` | Reads from slider | Source of truth for fetch window |

**Removed:** the boolean mode flags. There is no longer a "scrub mode" — the tab is always in scrubber-capable state once frames are loaded.

## 6. Behavior Specifications

### Initial entry to a tab (or selection change)

1. Cancel any in-flight loads from a prior selection (existing `_<tab>LoadSeq` pattern handles this)
2. Fetch latest single frame → render immediately
3. Fetch `lookbackHours` worth of frames → populate scrubber
4. Set frame index to last (latest)
5. Enable scrubber controls
6. Start auto-refresh polling

### Auto-refresh tick fires

1. Fetch latest `lookbackHours` worth of frames
2. Dedupe by `frame_key`; identify new frames
3. If no new frames → no-op
4. If new frames:
   - Capture `wasOnLatest = (index === frames.length - 1)` **before** mutating the array
   - Append new frames to the tail (preserve chronological order)
   - If `frames.length > cap` → trim oldest down to cap; shift `frameIndex` back by the number trimmed so the user's wall-clock position is preserved
   - Refresh scrubber UI (`_updateRtmaScrubberUi()` or equivalent — same call MRMS append is currently missing)
   - If `wasOnLatest && autoUpdateEnabled` → advance `frameIndex` to the new last frame, re-render the visible overlay
   - Flash the "+N new" indicator near the auto-update checkbox

### User adjusts the lookback slider

- **Increase** (e.g., 1H → 3H):
  - Fetch the new wider window
  - Merge new frames with existing (dedupe), prepend the older ones at the head
  - Apply cap if needed
  - Keep user's frame index pointing at the same wall-clock timestamp (shift index forward by the count of frames inserted before the old position)
- **Decrease** (e.g., 3H → 1H):
  - Trim frames older than `now - lookbackHours` from the head
  - If `frameIndex` now points outside the trimmed window, clamp it to the new oldest frame
  - If playback was running, allow it to continue from the new clamped position

### User clicks Play

- Start `_<tab>PlayTimer` advancing through frames at the current playback speed
- At end of array, loop back to start (existing behavior)
- New frames arriving via auto-refresh while playing → still get appended at the tail; play loop notices the new length on its next tick

### User clicks Pause

- Clear `_<tab>PlayTimer`
- Frame stays visible at current index

### User scrubs the slider manually

- Move thumb → re-render frame at that index
- Sets `frameIndex` to the manual position
- Subsequent auto-refresh appends do NOT auto-advance the thumb unless the user is on the latest frame at the time the new frame arrives

### Caps (recap from prior agreement)

| Tab | Cap |
|-----|-----|
| Radar | 300 frames |
| MRMS | 400 frames |
| RTMA | 150 frames |

## 7. UI Changes Summary

### What gets deleted

- "Current" button in each tab's `wx-mode-controls` block
- "Animate" button in each tab's `wx-mode-controls` block (or repurposed — see below)
- The `wx-mode-tabs` container that holds those two buttons

### What gets added or repurposed

- **Auto-update checkbox** appears for all three tabs (Radar already has one — MRMS/RTMA need new checkboxes in matching style)
- The lookback slider stays where it is, but becomes visible by default (no longer gated behind Animate-mode entry)
- The bottom scrubber bar (`#archive-scrubber-row`) becomes visible by default when a site/product/region is loaded, not gated behind mode entry

### What stays the same

- All per-tab product/site/region selectors
- Archive mode button — still toggles a separate archive flow
- Right sidebar layer toggles
- Map controls

## 8. Migration Plan

### Phase 1 — Design alignment *(this doc)*

User reviews and approves the design. Open questions resolved.

### Phase 2 — Radar refactor ✅ COMPLETE

**Status:** Tested and working. Radar now uses unified scrubber mode.

**Completed sub-steps:**
1. ✅ Created `_loadRadarUnified()` that calls both `loadRadarLiveLatest()` and `loadRadarScrubberFrames()` in parallel
2. ✅ Deleted Current/Animate mode buttons from HTML
3. ✅ Removed all `_radarScrubMode`, `_radarScrubIsTimeMode`, `_radarScrubTimelineMs`, `_radarScrubFramesBySite` variable declarations and 100+ references
4. ✅ Simplified `_radarAutoRefreshTick()` to single code path (always appends new frames)
5. ✅ Added lookback slider to Radar section: `#radar-animate-window` with slider `#radar-animate-slider`
6. ✅ Wired slider event listeners (input → display update, change → reload frames)
7. ✅ Fixed `_updateRtmaScrubberUi()` to recognize unified Radar frames
8. ✅ Updated all scrubber control handlers (play, step-back, step-fwd, slider) to use `_activeRadarSite()` check
9. ✅ Removed multi-site time-mode rendering block (60+ lines)
10. ✅ Verified scrubber UI displays correct frame count and timestamps
11. ✅ Tested playback, scrubbing, and frame stepping

**Key implementation notes:**
- Lookback slider uses same styling as MRMS/RTMA sliders
- Default value: 1 hour (matches design)
- Frame capping: 300 frames for Radar (enforced by `_tryAppendNewRadarFrames()`)
- Auto-refresh now always appends frames; thumb auto-advances if user is on latest
- `_updateRtmaScrubberUi()` now checks `_radarScrubFrames.length` to recognize unified Radar mode

### Phase 3 — MRMS refactor 🔄 READY TO START

Apply the same pattern as Radar. Smaller change because MRMS has fewer sub-modes.

**Sub-steps:**
1. Create `_loadMrmsUnified()` that calls both latest and scrubber loads in parallel
2. Delete MRMS Current/Animate mode buttons from HTML
3. Remove `_mrmsScrubMode` references (estimate 20-30 occurrences)
4. Add lookback slider to MRMS section (copy from Radar pattern)
5. Update `_mrmsAutoRefreshTick()` to single code path (always append)
6. Wire slider event listeners (input → display, change → reload)
7. Update scrubber control handlers to check for MRMS frames
8. Test with different products and lookback values

### Phase 4 — RTMA refactor 🔄 READY TO START

Same pattern as MRMS. RTMA has region+stream+product selection.

**Sub-steps:**
1. Create `_loadRtmaUnified()` that calls both latest and scrubber loads
2. Delete RTMA Current/Animate mode buttons from HTML
3. Remove `_rtmaScrubMode` references
4. Add lookback slider to RTMA section
5. Update `_rtmaAutoRefreshTick()` to single code path
6. Wire slider event listeners
7. Update scrubber control handlers for RTMA frames
8. Test across different regions, streams, and products

### Phase 5 — Cleanup

- Delete dead code: `_exitRadarScrubMode`, `_exitMrmsScrubMode`, `_exitRtmaScrubMode` callers/bodies where they only existed for the toggle
- Remove `_radarScrubLoadSeq` only if no longer needed (probably keep — still useful for canceling in-flight loads on selection change)
- Update any stale comments referencing "scrub mode"
- Verify deep links / URL params still work

## 9. Risks and Open Questions

### Risks

- **Refactor scope is large.** Dozens of files and hundreds of references touch these mode flags. Each phase is a meaningful commit, not a one-shot patch.
- **Initial load cost rises.** Always loading 1H of history on tab entry = ~10 PNG renders. Need to confirm performance is acceptable on slower connections.
- **The `_startRadarHistoryPoll` warm-up (which uses hardcoded `hours=3`)** needs reconciliation. Either delete it or align with the lookback slider.
- **Per-tab quirks may surface.** MRMS has product-key composition; RTMA has region+stream+product combos. Each may need tab-specific handling within the unified pattern.
- **The lingering "auto-update missed frames" mystery** — if it's a real backend or worker issue (not just upstream radar lag), the refactor won't fix it. We may discover it again on the other side.

### Open questions to resolve before implementation

1. **Lookback slider default:** confirmed 1H for all three tabs?
2. **Lookback slider max:** currently 12H — keep, or adjust per tab?
3. **Should the lookback slider increase trigger an immediate fetch, or only on slider-release?** (Debounce while dragging.)
4. **What happens to playback when lookback decrease clamps the user's frame index?** Continue from new clamped position, or pause?
5. **Auto-update checkbox default:** ON for all three? (Radar is currently ON.)
6. **Do we keep a "jump to latest" button anywhere as a manual control?** Useful if user has scrubbed back and wants to snap to the live frame.
7. **The `_startRadarHistoryPoll` warm-up loop with hardcoded `hours=3`** — delete it, or align it to the lookback slider value?
8. **Multi-site radar time-mode** — does this UX still make sense in a unified model, or does multi-site need its own thinking?
9. **National Composite radar (no site selected)** — currently shows MRMS overlay refresh via `_mrmsRadarOverlayRefresh`. How does this behave in the unified model when there's no scrubber to populate?

## 10. Out of Scope (intentionally deferred)

- Satellite tab unification (already works fine)
- Backend caching or worker cadence investigation (the 10-min MRMS lag, the radar pipeline latency — separate diagnostic tasks)
- AWS vs GCP data source switching (separate optimization task)
- Earth Engine integration for RTMA
- The duplicate PNG fetches during playback (cosmetic, not blocking)

## 10.5. Phase 2 Implementation Notes (for future sessions)

**Key changes made to `js/weather.js`:**
- Removed variable declarations: `_radarScrubMode`, `_radarScrubIsTimeMode`, `_radarScrubTimelineMs`, `_radarScrubFramesBySite`
- Deleted `_exitRadarScrubMode()` function entirely
- Created `_loadRadarUnified()` function combining latest + scrubber loads
- Simplified `_radarAutoRefreshTick()` - removed branching on scrub mode, always appends frames
- Simplified `_renderRadarScrubFrame()` - removed 60-line multi-site time-mode rendering block
- Simplified `_tryAppendNewRadarFrames()` - removed time-mode logic, uses `#radar-animate-slider` for hours
- Updated `_updateRtmaScrubberUi()` to check `_radarScrubFrames.length` as 4th condition (unified Radar)
- Updated 4 scrubber control handlers (play, step-back, step-fwd, slider input) to use `_activeRadarSite() && _radarScrubFrames.length` check

**Key changes made to `weather.html`:**
- Added `#radar-animate-window` div after Radar action buttons
- Added `#radar-animate-slider` with ID, min/max, and event listeners
- Removed "Current" and "Animate" mode button markup

**Lessons learned for Phase 3/4:**
1. The `_updateRtmaScrubberUi()` function must check ALL active tab modes (MRMS, Satellite, RTMA, **Radar**) — it defaults to the last else clause, so order matters
2. Lookback slider uses standard `.wx-animate-slider` styling — reusable across tabs
3. All scrubber control handlers (play button, step buttons, slider) need to recognize the unified mode by checking for active frames, not mode flags
4. Auto-refresh tick simplification is straightforward — just remove the mode check and always append
5. The 0/0 frame display issue was caused by `_updateRtmaScrubberUi()` not recognizing unified Radar frames

## 11. Success Criteria

We'll know the refactor is done when:

1. ✅ **Phase 2 (Radar) complete:**
   - ✅ No `_radarScrubMode` flag remains in `js/weather.js`
   - ✅ Radar shows latest image + scrubber on site selection without mode toggle
   - ✅ Lookback slider visible and working (tested: 1H → 3H update works)
   - ✅ Auto-refresh appends new frames and auto-advances thumb
   - ✅ Playback, scrubbing, and frame stepping all work
   - ✅ Scrubber UI shows correct frame count and timestamps

2. **Phase 3 (MRMS) complete:**
   - No `_mrmsScrubMode` flag remains
   - MRMS shows latest image + scrubber without mode toggle
   - Lookback slider working
   - Auto-update checkbox functional

3. **Phase 4 (RTMA) complete:**
   - No `_rtmaScrubMode` flag remains
   - RTMA shows latest image + scrubber without mode toggle
   - Lookback slider working
   - Auto-update checkbox functional

4. **Overall completion:**
   - No `_<tab>ScrubMode` flags remain anywhere in `js/weather.js`
   - Archive mode still functions independently
   - No regression in Satellite behavior
   - Deep links / URL params still work

---

## Appendix A — Background context from prior session

The session that produced this design doc started with the user asking why the radar auto-update wasn't appending new frames to the scrubber even after waiting 25 minutes. Investigation revealed:

- Radar polls every 3 minutes (matches upstream VCP cadence)
- The backend (`radar_list_frames`) reads the filesystem fresh each call — no caching layer
- New PNG files were appearing in the cache directory but auto-refresh ticks were not picking them up in Animate mode
- Switching Current→Animate (which calls `loadRadarScrubberFrames`) DID pick them up
- Both paths hit the same `/api/radar/live/frames` endpoint with the same params

The conclusion was that the dual-mode architecture was creating subtle bugs that resisted point-fixes, and a unification was the cleaner path forward. The original plan (add jump-to-latest, caps, MRMS/RTMA checkboxes on top of the two-mode system) is being folded into this larger refactor.

## Appendix B — Files most affected

- `weather.html` — mode buttons, sidebar blocks, scrubber bar
- `js/weather.js` — bulk of the state and logic
- `js/satellite.js` — unaffected, reference implementation of unified scrubber

No backend Python file changes are anticipated unless a backend-side bug is discovered during Phase 2.
