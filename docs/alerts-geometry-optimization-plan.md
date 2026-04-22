# Alerts Geometry Optimization Plan

Status: Planning blueprint
Date: 2026-04-22

## TL;DR
Implement a dual-geometry alerts workflow that keeps one canonical full geometry for correctness and interactions, and one optional simplified display geometry for low-zoom rendering of non-storm events. Excluded storm-based warnings always remain full geometry at every zoom level.

## Goals
1. Preserve precise alert behavior for hover tooltips, click popups, popup pagination, and new-alert banner flows.
2. Improve CONUS/low-zoom rendering performance without changing alert source fidelity.
3. Keep heavy geometry processing in worker/cache path, not request path.
4. Maintain a clean feature-flag rollback path.

## Non-Goals
1. No changes to alert categories, colors, priorities, or banner trigger rules.
2. No change to zone-first enrichment source order.
3. No county-by-zoom substitution behavior.

## Storm Events Excluded From Simplification
These events must always use full geometry for display and interaction:
1. Tornado Warning
2. Severe Thunderstorm Warning
3. Flash Flood Warning
4. Special Marine Warning
5. Snow Squall Warning

## Key Design Principles
1. Single source of truth: each alert keeps canonical full geometry derived by existing enrichment.
2. Display simplification is derived from that same full geometry, never from county substitution by zoom.
3. Interactions always use full geometry.
4. County geometry remains fallback-only when zone geometry is unavailable.

## Current Baseline
1. Worker writes national alerts cache in workers/alerts_worker.py.
2. Geometry enrichment path exists and is worker-driven.
3. Zone geometry cache exists and is persisted to disk for fast restarts.
4. Frontend alert logic is in js/weather.js and currently couples rendering and interaction geometry checks.

## Proposed Architecture
### Geometry variants
1. Full variant (canonical): used for all interaction math and correctness.
2. Display-low variant: used only for low zoom rendering of non-excluded events.

### Zoom behavior
1. Low zoom (CONUS-like): render display-low for non-excluded events.
2. Medium/high zoom: render full geometry for all events.
3. Excluded storm events: always render full, regardless of zoom.

### Interaction behavior
1. Hover hit-testing uses full geometry.
2. Click selection uses full geometry.
3. Tooltip aggregation and popup pager candidate set uses full geometry.
4. Sorting and pager behavior remain unchanged.

## Backend Implementation Plan
### Phase 1: Contract and config (0.5-1 day)
1. Add config constant list for excluded events in config/alerts_config.py.
2. Add simplification settings:
   1. low zoom tolerance
   2. minimum vertex gate
   3. preserve-topology default
3. Define endpoint parameters and defaults:
   1. geometry_mode (full | display)
   2. zoom_bucket (low | high)

### Phase 2: Worker precompute (1.5-2.5 days)
1. Keep current enrichment path for full geometry unchanged.
2. Produce display-low geometry variant from full dataset:
   1. skip excluded events
   2. simplify only Polygon/MultiPolygon for non-excluded events
   3. validate simplified geometry, fallback to full when invalid/empty
3. Write cache artifacts atomically:
   1. cache/alerts/national_full.geojson
   2. cache/alerts/national_display_low.geojson
4. Emit metrics/logs:
   1. total features
   2. simplified features
   3. excluded features
   4. vertex reduction percent
   5. worker runtime delta

### Phase 3: Endpoint serving (0.5-1 day)
1. Extend /api/data/alerts in main.py to select cache artifact by geometry_mode + zoom_bucket.
2. Keep state filtering identical between variants.
3. Include response metadata:
   1. geometry_mode_used
   2. zoom_bucket_used
   3. simplified_feature_count
4. Preserve backward-compatible default if no mode params are supplied.

## Frontend Implementation Plan
### Phase 4: Data-flow split (1-1.5 days)
1. Maintain two collections in js/weather.js:
   1. alertsFullFeatures (interaction)
   2. alertsDisplayFeatures (render)
2. Keep category and cancel/expire filters functionally equivalent on both collections.
3. Fetch full + display datasets in synchronized refresh flow.

### Phase 5: Render/interaction decoupling (1-1.5 days)
1. Render map layer from alertsDisplayFeatures.
2. Move hit-testing path to alertsFullFeatures for hover/click.
3. Keep popup pager generation and sort logic unchanged.
4. Ensure smooth transitions on zoom-bucket changes.

### Phase 6: Performance safeguards (0.5-1 day)
1. Add bbox prefilter before point-in-polygon checks on full features.
2. Throttle hover hit-testing cadence.
3. Keep click hit-testing immediate.

## Testing Strategy
### Backend unit tests
1. Excluded events are never simplified.
2. Non-excluded events simplify only in display-low variant.
3. Invalid simplification falls back to full.
4. State filtering parity between full and display variants.

### Integration tests
1. Worker writes both cache files every cycle.
2. Endpoint returns correct variant by mode.
3. Existing smoke tests remain green.
4. Add assertions for response metadata and simplified counts.

### Frontend behavior tests
1. Hover tooltip event lists match expected alerts at known overlap points.
2. Click popup opens expected alert set and pagination remains stable.
3. New-alert banners remain unchanged (ID/event driven).
4. No regressions in archived mode behavior.

### Manual QA scenarios
1. Cascades Winter Storm Warning comparison at CONUS and state zoom.
2. Tornado and severe polygon fidelity checks.
3. State-filter + category toggle stress test during refresh.

## Observability and Metrics
1. Worker metrics:
   1. simplify elapsed ms
   2. simplified feature count
   3. excluded feature count
   4. vertex reduction percent
2. API metrics:
   1. geometry mode usage
   2. payload bytes
   3. p95 latency by mode
3. Frontend metrics:
   1. fetch-to-render duration
   2. hit-testing duration distribution

## Rollout Plan
1. Introduce feature flag (default off).
2. Deploy backend support first.
3. Deploy frontend mode consumption behind same flag.
4. Run internal soak and compare metrics.
5. Gradually enable broadly if acceptance criteria are met.

## Rollback Plan
1. Disable feature flag to return to legacy full-geometry-only rendering behavior.
2. Keep legacy cache path available during rollout window.
3. Revert endpoint mode selection while preserving full cache artifacts.

## Risks and Mitigations
1. Topology artifacts in simplification:
   1. preserve topology + validity checks + fallback to full
2. Interaction mismatch risk:
   1. enforce full-geometry-only hit-testing
3. Worker runtime increase:
   1. tune tolerance and minimum vertex gates
4. Payload growth from dual datasets:
   1. separate artifacts and mode-based fetch

## Acceptance Criteria
1. Excluded storm events are never simplified at any zoom.
2. County fallback remains fallback-only and not zoom-dependent.
3. Tooltip/click/popup pager behavior is unchanged in correctness.
4. CONUS low-zoom rendering is measurably faster than baseline.
5. Worker and endpoint reliability remains within current operational expectations.

## Estimated Timeline
1. Phase 1: 0.5-1 day
2. Phase 2: 1.5-2.5 days
3. Phase 3: 0.5-1 day
4. Phase 4: 1-1.5 days
5. Phase 5: 1-1.5 days
6. Phase 6 + testing + rollout prep: 2-4 days

Total estimate: about 7-11.5 engineering days depending on tuning depth and QA coverage.

## References
1. docs/patterns.md
2. workers/alerts_worker.py
3. main.py
4. alerts/alerts_utils.py
5. js/weather.js
