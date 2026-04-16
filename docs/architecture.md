# System Architecture

This repository is transitioning to a unified weather workflow while preserving separate Radar and Satellite workflows.

Canonical unified target:

- weather.html
- js/weather.js
- /api/weather
- /api/weather/export-frame
- /api/weather/export-animation

Retained independent workflows:

- Radar (radar.html + js/radar.js)
- Satellite (satellite.html + js/satellite.js)
- Satellite Archive (satellite-archive.html + js/satellite-archive.js)

## Legacy Archival (2026-04-04)

Legacy frontend pages and JS have been moved to `legacy/`:

- surface.html, alerts.html, mrms.html, spc.html, spc-archive.html
- js/surface.js, js/alerts.js, js/mrms.js, js/spc.js, js/spc-archive.js

Legacy page routes removed from main.py. Legacy API endpoints retained.

Python backend modules (surface/, alerts/, mrms/, spc/) remain in use —
weather_utils.py imports data-fetching functions from them at render time.

Navigation: Weather, Radar, Satellite, Satellite Archive only.

Lightning is omitted from active roadmap direction.

## Request Flow

Frontend UI -> FastAPI endpoint -> synchronous render pipeline -> output image/video

Progress model:

1. Frontend creates request_id.
2. Frontend starts polling /api/progress/{request_id}.
3. Endpoint runs synchronously and updates active_tasks[request_id].
4. Endpoint returns payload and removes active_tasks entry.

Do not use BackgroundTasks or asyncio for rendering jobs.

## Pipeline Separation

All workflows follow:

download -> cache -> parse -> render -> output

Keep network I/O out of rendering functions.

Keep encoding out of per-frame rendering functions.

## Unified Weather Contract

### Endpoint

- /api/weather handles current and archive modes.
- Mode inferred from paired date_from/date_to values.

### Export

- /api/weather/export-frame exports selected scrubber frame as PNG.
- /api/weather/export-animation exports MP4 from existing layered artifacts.

### Layered Archive

Layered responses should include:

- basemap_url
- frames[]
- layers_path
- session_expires_utc
- optional static layer URLs

Exports must compose from layered artifacts and avoid rerendering source data when possible.

## Projection

Unified weather rendering uses Lambert-only policy.

Rules:

1. Use one computed extent/projection contract per frame for all layers.
2. Preserve aspect ratio and avoid layer drift/stretch.
3. Apply identical framing assumptions to basemap and overlays.

## Caching

Use cache-first behavior for all downloads.

Layered sessions should include manifest metadata with TTL and max-session cleanup.

Touch session access metadata on export calls.

## Shared Utilities

Prefer existing shared modules:

- video_utils.py
- geo_utils.py
- city_utils.py
- font_utils.py
- listing_cache.py
- s3_utils.py

## MRMS Two-Tier Dropdown Architecture (2026-04-04)

MRMS product selection uses a two-tier dropdown pattern:

1. Primary dropdown selects product family (RotationTrack, MESH, QPE, etc.).
2. Conditional sub-dropdowns appear for family-specific parameters
   (level, time window, threshold, source, variant).
3. JS `composeMrmsProductKey()` composes the final API product key
   (e.g. `RotationTrack_LL_60min`, `QPE_MS2_01H`).

Config: `config/mrms_config.py` defines 69 products across 11 families.
Backend: `weather_utils.py` PRODUCT_GROUPS["mrms"] lists all 69 keys.
Backend: `mrms_utils.py` uses `product.startswith("MESH")` for MESH checks.
Defaults: main.py endpoints default to `QPE_MS2_01H`.

## SPC Legend Architecture (2026-04-04)

SPC torn/wind/hail legends render two rows: probability + CIG intensity.
CIG patterns match map hatching in spc_utils.py:

- CIG 1: dashed diagonals
- CIG 2: solid backslash hatching
- CIG 3: cross-hatch
  Hail shows CIG 1-2 only.

## SPC Fire Weather Outlook Architecture (2026-04-06)

Fire Weather Outlooks added as SPC sub-products (`fire_windrh`, `fire_dryt`).

Data sources:

- Day 1-2: SPC static GeoJSON (`spc.noaa.gov/products/fire_wx/day{1,2}fw_{dryt,windrh}.nolyr.geojson`)
- Day 3-8: NWS MapServer GeoJSON query
  (`mapservices.weather.noaa.gov/.../SPC_firewx/MapServer/{layer_id}/query?where=1%3D1&outFields=*&f=geojson`)

Layer ID mapping in `spc/spc_utils.py` `_FIRE_WX_LAYER_IDS`:
Day 3 DryT=7/WindRH=8, Day 4 DryT=10/WindRH=11, ... Day 8 DryT=22/WindRH=23.

Features with `dn=0` ("Probability Too Low") are filtered out during rendering.

Frontend: Three-way mutual exclusion across convective / fire / other SPC dropdowns.
Fire dropdown visible for all days (1-8).

Legends:

- Wind/RH: Elevated (#FFBF80), Critical (#FF8080), Extremely Critical (#FF80FF)
- Dry Thunderstorm: Isolated (#FFBF80), Scattered (#FF8080)

## Radar and Satellite Exception

Radar and Satellite remain separate from unified weather migration.

Keep existing Radar/Satellite source fallback and endpoint behavior intact unless explicitly requested.

## Static Output Serving

Generated outputs are served via /img/... static mounts.

Use mapped output roots from main.py constants; avoid hardcoded ad-hoc directories.

## Basemap Cache Protection

Purge behavior must continue protecting basemap_cache/.
