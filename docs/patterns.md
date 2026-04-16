# Coding Patterns

This document defines active implementation patterns for the unified weather migration.

## Endpoint and Progress Pattern

Endpoints are synchronous and block until completion.

Do not use BackgroundTasks or asyncio for rendering jobs.

Pattern:

1. Frontend generates request_id.
2. Frontend polls /api/progress/{request_id} before invoking endpoint.
3. Endpoint writes progress into active_tasks[request_id].
4. Endpoint removes task entry in finally blocks.

## Response Shape Pattern

Prefer success_payload()/error_payload() for new endpoints.

Typical success fields:

- status
- message
- image_url
- source
- data_mode
- request_id (when available)

No-output archive outcomes should return warning success payloads where appropriate.

## Unified Weather Endpoint Pattern

Use /api/weather for both current and archive.

Mode inference:

- no date_from/date_to => current
- paired date_from/date_to => archive
- single date provided => 400 validation error

Archive output default should be layered and scrubber-ready.

## Layered Session Pattern

Layered responses should include:

- basemap_url
- frames[]
- layers_path
- session_expires_utc
- optional static layer URLs

Each frame should include:

- index
- timestamp_utc
- timestamp_local
- product layer URL
- hud_right_url
- legend_url (when legend varies per frame, e.g. alerts, MRMS MESH/RotationTrack products)
- compatibility image_url

Static legend (when legend does not change per frame):

- legend_url at top level of response (surface colorbar, static MRMS colorbar, SPC)
- For station plots: legend_url points to static img/station_plot_legend.png

Session lifecycle:

1. Persist manifest metadata (created/updated/last_access/expires).
2. Apply TTL cleanup.
3. Enforce max-session cap.
4. Refresh last_access on export endpoints.

## Export Pattern

Use dedicated endpoints:

- /api/weather/export-frame
- /api/weather/export-animation

Both export paths must validate layers_path and reject traversal/absolute paths.

Animation export composes existing layers into MP4 and should avoid source rerendering when possible.

Export compositing must append the legend image below the map composite when
generating flat PNG or MP4 output (increasing canvas height to fit).

## Projection Pattern

Unified weather uses Lambert-only rendering.

Rules:

1. Compute one extent/projection contract per frame.
2. Keep basemap and overlay layers geospatially locked.
3. Preserve projection aspect to prevent distortion.

## Style Config Pattern

Use config/style_config.py as canonical style source.

Endpoint behavior:

- accept style_config as Optional[str]
- parse and normalize with shared helper
- pass dict to renderer/utilities

Renderer behavior:

- read values via style_config.get(key, default)

## Cache-First Pattern

Before network fetch:

- return cached artifact when valid
- otherwise download and cache

Avoid duplicate downloads and duplicate frame rendering.

## Animation Encoding Pattern

All workflows must use video_utils.save_animation().

Do not add new direct imageio.mimsave() calls.

## Two-Tier Dropdown Pattern (MRMS)

Used for product families with multiple sub-parameters (level, time, source, etc.).

HTML structure:

- Primary `<select>` with family-level `<option>` values.
- Multiple `<div>` groups (one per family) with `style="display:none;"`.
- Each group contains family-specific sub-dropdowns.

JS pattern:

- `SUB_PRODUCT_GROUPS` map: family key → array of group div IDs.
- `updateSubControls()`: hides all groups, shows active family's groups.
- `composeProductKey()`: switch on family, concatenates sub-values.
- Event listeners on primary dropdown and source-dependent sub-dropdowns.
- Initial call to `updateSubControls()` on page load.

See js/weather.js `composeMrmsProductKey()` and `updateMrmsSubControls()`.

## Legacy Migration Pattern

For unified weather implementation:

- legacy surface/alerts/mrms/spc HTML and JS are archived in legacy/
- legacy Python backend modules remain in use for data fetching
- do not chain runtime calls into legacy workflow endpoints
- retain Radar/Satellite workflows as separate exceptions

## SPC Legend Pattern

SPC torn/wind/hail products use a two-row legend:

- Row 1: probability swatches with category labels.
- Row 2: CIG (Conditional Intensity Group) intensity swatches.
  CIG 1 = dashed diagonals, CIG 2 = solid backslash, CIG 3 = cross-hatch.
  Hail shows CIG 1-2 only; tornado/wind show CIG 1-3.
- cat product keeps single-row layout (no CIG row).

Map hatching in spc_utils.py uses matching patterns for consistency.

## SPC Fire Weather Legend Pattern (2026-04-06)

Fire weather products have dedicated legends distinct from convective outlooks:

- fire_windrh: Elevated (#FFBF80/#FF7F00), Critical (#FF8080/#FF0000),
  Extremely Critical (#FF80FF/#FF00FF). Matches SPC wind/RH risk categories.
- fire_dryt: Isolated Dry T-Storm (#FFBF80/#FF7F00),
  Scattered Dry T-Storm (#FF8080/#FF0000). Matches SPC dry thunderstorm
  risk categories.

Both use swatch + label layout in the legend footer, same structure as
convective categorical legend but with fire-specific risk levels and colors.

## SPC Three-Way Dropdown Pattern (2026-04-06)

SPC product group uses three mutually exclusive dropdowns in the frontend:

1. Convective Outlooks (cat/torn/wind/hail/prob) — filtered by day.
2. Fire Weather Outlooks (fire_windrh/fire_dryt) — visible for all days (1-8).
3. Other Products (watches/mds/reports) — visible Day 1 only.

`_spcLastTouched` tracks which was last selected (`'convective'`, `'fire'`,
`'other'`). Selecting one resets the other two to placeholder. Fire weather
data: Day 1-2 from SPC static GeoJSON, Day 3-8 from NWS MapServer query.

## Date Validation Pattern

Use shared datetime parsing/range validation helpers from main.py for archive logic.

Enforce category-specific archive span limits.
