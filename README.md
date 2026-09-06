# NCHurricane Dashboard 2026

A FastAPI-powered weather visualization dashboard for personal weather
operations, with live products and bounded history across:

- Surface observations
- Alerts
- Radar
- Satellite
- MRMS
- RTMA, SPC, WPC, Tropical, Water, and Drought
- A shared multi-product Workspace

The app combines a Python API backend with static HTML/CSS/JS frontends and generates map images/animations on demand.

## What This Project Is

NCHurricane Dashboard 2026 is an operational weather workstation app designed for local Windows use. It focuses on practical analysis speed:

- A main landing page at `index.html`
- A severe-weather workspace at `/workspace`
- Standalone product pages with clean URLs such as `/radar`, `/satellite`, and
  `/alerts`
- Current and retained Alerts/Surface archive endpoints
- Local caching of downloads and generated products
- Built-in purge tooling for retention control

## Source Control and Recovery

- Private GitHub repository is active for this project as of 2026-04-16.
- Default workflow is commit-first for high-risk refactors so rollback is immediate.
- Recommended checkpoint pattern: commit before large structural edits and keep
  each high-risk change independently revertible.
- Preferred recovery path is now `git restore`/`git revert` instead of manual file recovery.

## Key Capabilities

### Data Workflows

- Surface maps with current observations and bounded recent Live lookback
- Alert maps + active alert polygons (GeoJSON)
- Radar (Level 2 and Level 3, current and archive)
- GOES, Himawari, Meteosat, GK2A, and GMGSI satellite imagery on satellite-v2
- MRMS products from NOAA public data

Surface and Alerts retain archive APIs as backend groundwork; their standalone
Archive tabs are placeholders. A unified cross-page Archive workflow remains
future work, separate from current Live history and Tropical archive features.

### Rendering and Performance

- Cartopy-based map rendering
- Optional pre-rendered basemap caches for surface and radar
- NOAA NODD public-bucket discovery for live Radar Level 2 and Level 3 data

### Ops Features

- Application-owned periodic cache retention and cleanup
- Unified static mounts for generated media under `/img/*`

## Tech Stack

- Backend: FastAPI, Uvicorn
- Data access: requests, boto3 (unsigned public bucket access)
- Geospatial/science: Cartopy, Shapely, PyProj, MetPy, Py-ART, xarray, netCDF4, cfgrib
- Image/video: Matplotlib, Pillow, imageio[ffmpeg]
- Frontend: HTML5, CSS, vanilla JavaScript

## Data Sources (Primary)

- NWS API
- Iowa Environmental Mesonet (IEM)
- NOAA Open Data Dissemination (NODD) via AWS/GCP public buckets
- NOAA MRMS public S3 bucket (`noaa-mrms-pds`)

## Architecture at a Glance

- `main.py` hosts the FastAPI app, endpoint routing, and static mounts.
- `index.html` is the main dashboard landing page served at `/`.
- `/workspace` composes Alerts, Radar, SPC, Satellite, RTMA, MRMS, WPC, and Water
  engines on one Leaflet map, with a shared Radar/MRMS/Satellite/RTMA timeline;
  `/weather.html` redirects there.
- Canonical standalone product pages exist for Alerts, Radar, Satellite, SPC,
  Surface, MRMS, RTMA, Drought, Tropical, WPC, and Water.
- Domain modules (`surface/`, `alerts/`, `radar/`, `satellite_v2/`, `mrms/`, `rtma/`, `spc/`, `workers/`) handle download, cache, and render logic.
- Generated media is stored in workflow-specific directories and served as static content.
- Frontend pages call API endpoints directly and poll progress for long-running jobs.

## Project Layout

```text
dashboard_2026/
  main.py
  requirements.txt
  index.html
  frontend/
  css/
  config/
  surface/
  alerts/
  radar/
  satellite_v2/
  mrms/
  rtma/
  spc/
  workers/
  shapefiles/
  data/
  img/
```

## Getting Started (Windows, Local)

### 1. Prerequisites

- Python 3.10+
- Git
- A working virtual environment (`.venv`) is recommended

Note: Geospatial dependencies (especially Cartopy stack) can require compatible wheels/system libraries on Windows.

### 2. Install Dependencies

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
```

For refactor verification and local test tooling, also install the dev
dependencies:

```powershell
pip install -r requirements-dev.txt
```

`requirements-dev.txt` includes `ruff`, `pytest`, and `httpx2`. The app does
not need `httpx2` at runtime, but Starlette/FastAPI `TestClient` requires it in
the current dependency stack.

### 3. Run the App

```powershell
python main.py
```

### 4. Application-Owned Refresh and Optional Warmers

The default local startup path is:

```powershell
python main.py
```

The app-owned refresh coordinator always starts with the API. Requests own
refresh, rendering, history filling, and current-season Tropical archive
updates; application lifecycle owns six-hour cache cleanup. `WX_INPROC_WORKERS`
no longer enables a broad fixed worker schedule. The supported runtime has one
application process. Do not launch Uvicorn with multiple workers or set
`WEB_CONCURRENCY` / `UVICORN_WORKERS` above 1. Persistent cross-process leases
are closed as unnecessary for this deployment; a deployment change requires a
new coordination design. Optional warmers below delegate to the local API.

Windows scheduled tasks are optional. Preview existing tasks and the bounded
localhost warmer profiles without changing anything:

```powershell
pwsh -File tools\install_tasks.ps1
```

Register the optional API-delegating profiles in a disabled state:

```powershell
pwsh -File tools\install_tasks.ps1 -InstallOptionalWarmers
```

The default selection is `core,surface`. Register the heavier RTMA/MRMS
profiles separately so they remain independently controllable:

```powershell
pwsh -File tools\install_tasks.ps1 -Profile rtma,mrms -InstallOptionalWarmers
```

Add `-EnableOptionalWarmers` only when scheduled prewarming is wanted. Legacy
direct-writer removal requires the separate explicit
`-UnregisterLegacyTasks` switch. The application remains fully functional when
all tasks are absent or disabled. Disable every optional warmer while capturing
Radar or Satellite performance benchmarks.

Server starts on:

- `http://127.0.0.1:8000`

Open in browser:

- `http://127.0.0.1:8000/`
- `http://127.0.0.1:8000/workspace`

## API Quick Reference

### Health and status

- `GET /api/status`
- `GET /health`
- `GET /api/health/coordinator`

### Surface

- `GET /api/surface/products`
- `GET /api/data/surface`
- `GET /api/data/surface-gradient`
- `GET /api/archive/surface`

### Alerts

- `GET /api/data/alerts`
- `GET /api/data/alerts/lsr`
- `GET /api/archive/alerts`

### Radar

- `GET /api/radar/products`
- `GET /api/radar/live/sites`
- `GET /api/radar/status`
- `GET /api/radar/colortable?product=L3_N0B`
- `GET /api/radar/live/latest?site=KMHX&product=L3_N0B`
- `GET /api/radar/live/frames?site=KMHX&product=L3_N0B&hours=2`
- `GET /api/radar/live/value`
- `GET /api/radar/live/storm-tracks`

Notes:

- Endpoints are cache-first and read from `cache/overlays/radar/...`.
- On cold cache miss, latest endpoint prioritizes first frame availability, then warms additional history asynchronously.
- Frontend radar controls include `Refresh`, `Clear` (clear overlays without resetting map extent), and multi-site/time-mode animation workflow.

### Satellite

- `GET /api/satellite/products`
- `GET /api/satellite-v2/catalog`
- `GET /api/satellite-v2/frame-bounds`
- `GET /api/satellite-v2/legend`
- `GET /api/satellite-v2/tile/{z}/{x}/{y}`

### Satellite v2 Rapid Worker

Satellite v2 Full Disk and CONUS imagery are live-rendered on demand with
tile-cache reuse and supertiles. Application-owned selection/presence workflows
also perform bounded Meteosat warming: Meteosat-9/12 Full Disk selected products
warm the newest two frames incrementally at z1-z6, while non-rapid Meteosat-11
RSS selections warm the newest four frames at z4-z7 from a two-frame source
tail. Both yield to foreground requests, honor selection ownership, and enter
the shared Satellite byte budget.

The narrow rapid-sector implementation remains available as an optional manual
cache primer for high-cadence Channel02/Channel13 sectors where animation
latency matters.

Default rapid worker scope:

- GOES-19/18 `MESO1` and `MESO2`
- Himawari-9 `JAPAN`
- Meteosat-11 `RSS`
- Products: `Channel02` and `Channel13`
- Latest 12 frames, low worker count, cache-first tile warming

One-off examples:

```powershell
python -m satellite_v2.rapid_worker --force
python -m satellite_v2.rapid_worker --force --jobs goes19:MESO1 --products Channel02 --frames 2 --tile-workers 1
```

Tune rapid warming with environment variables:

```powershell
$env:WX_SATELLITE_V2_RAPID_WORKER_FRAMES = "12"
$env:WX_SATELLITE_V2_RAPID_TILE_WORKERS = "2"
```

### MRMS

- `GET /api/mrms/products`
- `GET /api/mrms/set-product`
- `GET /api/data/mrms`
- `POST /api/mrms/tiles/prepare`
- `GET /api/mrms/tiles/{render_version}/{product}/{frame_key}/{z}/{x}/{y}.png`

### Other product APIs

- RTMA: `/api/rtma/products`, `/api/data/rtma`,
  `/api/data/rtma/points`, `/api/data/rtma/frames`
- SPC: `/api/spc/products`, `/api/data/spc`, `/api/data/spc/reports`,
  `/api/data/spc/active`
- WPC: `/api/wpc/products`, `/api/data/wpc`, `/api/data/wpc/catalog`
- Drought: `/api/drought/products`, `/api/data/drought/dates`,
  `/api/data/drought`, `/api/data/drought/state-stats`
- Tropical and Water routes are defined in `routes/tropical.py` and
  `routes/water.py`.

## Example Requests

```bash
# System status
curl "http://127.0.0.1:8000/api/status"

# Current radar metadata
curl "http://127.0.0.1:8000/api/radar/live/latest?site=KMHX&product=L3_N0B"

# Current Satellite catalog
curl "http://127.0.0.1:8000/api/satellite-v2/catalog?sat_id=goes19&sector=CONUS&channel=Channel13"

```

## Configuration Notes

- Product and style defaults live under `config/` and domain modules.
- Most endpoints accept display/style controls through a `style_config` JSON payload (stringified query param).
- Archive endpoints require paired `date_from` and `date_to`.
- Maximum archive spans are enforced in API logic per category.

## Data Retention and Cleanup

The FastAPI lifecycle registers `workers/cache_cleanup_worker.py` with the
application refresh coordinator. Cleanup runs every six hours without requiring
an open page or a scheduled task. There is no public purge endpoint.

## Known Operational Considerations

- This repo is optimized for local execution, not hardened production deployment.
- CORS is currently open (`allow_origins=["*"]`).
- For large archive ranges, rendering and network time can be significant.
- Radar/Satellite source availability can vary by provider/time window.

## Planning and Documentation

- Start with [`docs/README.md`](docs/README.md).
- [`docs/dashboard-change-and-enhancement-superfile.md`](docs/dashboard-change-and-enhancement-superfile.md)
  is the only active roadmap for the current dashboard and Version 2 lane.
- [`docs/architecture.md`](docs/architecture.md) records implemented ownership;
  [`docs/patterns.md`](docs/patterns.md) records established reusable patterns.
- Completed/superseded plans live under [`docs/archive/`](docs/archive/), and
  benchmark evidence lives under [`docs/perf/`](docs/perf/).
- As of 2026-09-06, the owner selected a high-cost rendering-workflow audit for
  Satellite (especially Meteosat), Radar with product-specific WebGL evaluation,
  MRMS, and RTMA. The expanded brief includes alternative architectures,
  hardware-adaptive budgets, and compatibility across modern Chromium, WebKit,
  and Gecko browsers. See superfile section 4.8; renderer implementation remains
  deferred pending the audit and plan review.

## Contributing

This project currently supports personal operations first. If you contribute:

- Keep changes scoped by workflow (`surface`, `alerts`, `radar`, etc.)
- Preserve current route contracts unless a cleanup batch explicitly retires them
- Include clear reproduction steps for rendering/data-source bugs
