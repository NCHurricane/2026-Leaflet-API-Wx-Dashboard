# Owner smoke: first M12 visible frame

The owner reports approximately **2–3 minutes** for the first frame to fill.
OBS activity was not confirmed. The supplied access log identifies M12 Channel02,
z4, frame `20260906T233000Z`, `products-fci6`, generation 1 and 40 unique tile
requests. All 40 tile responses are HTTP 200; the excerpt has no elapsed times
or request timestamps. HTTP success alone is not visual/performance acceptance.

[Read-only filesystem evidence](owner-smoke-first-frame-2330.json) matches all
40 requested outputs: 35 PNGs and five negative markers in the off-disk x12
column. File publication order matches response order in the attachment.
The 40 source chunks total 571,931,767 bytes.

| Matching file events, UTC 2026-09-06 | Observed span |
| --- | ---: |
| First source-file completion 23:51:06.426 to last completion 23:52:19.122 | 72.697 s |
| Last source-file completion to first tile output 23:52:21.746 | 2.624 s |
| First tile output to last tile/empty marker 23:53:13.967 | 52.221 s |
| First source-file completion to last tile output | 127.541 s |

These are completion timestamps, not instrumented transfer/queue/renderer/browser
durations. They omit work before the first source completion and browser decode,
paint and frame promotion. They are consistent with the owner's approximate
2–3-minute report and establish a material first-frame latency issue.

The browser explicitly sends `render_neighbors=0`; code tracing confirms the
service honors this as individual-tile canvases. Prior equal-quality pilots
used 3x3 canvases. Their reported reductions cannot be generalized to this
40-request whole-view load. Tile completion gaps immediately preceding five
limb-column outputs and five empty-column markers are each about 3.7–3.9 seconds.
The current native-window planner uses full-native fallback whenever a corner
is unprojectable, including wholly off-disk tiles; a full visible array exceeds
the retained-cache ceiling. Repeated fallback reads are therefore a concrete
code-traced candidate, not yet an instrumented per-stage attribution.

Next investigation should separate full-bundle source acquisition from actual
viewport scheduling, repeated limb fallback and unnecessary decoding for provably
empty tiles. Preserve full-native quality and opacity/ownership contracts while
selecting a bounded correction. Owner visual acceptance, OBS condition and other
smoke results remain open. No runtime changes, new downloads, benchmark runs or
server restarts were performed while interpreting this report; the 108-sample
controlled timing allowance remains exhausted.
