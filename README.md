# NCHurricane Dashboard 2026

A FastAPI-powered weather visualization dashboard for personal weather operations, with isolated workflows for current and archive views across:

- Surface observations
- Alerts
- Radar
- Satellite
- MRMS
- Lightning

The app combines a Python API backend with static HTML/CSS/JS frontends and generates map images/animations on demand.

## What This Project Is

NCHurricane Dashboard 2026 is an operational weather workstation app designed for local Windows use. It focuses on practical analysis speed:

- A main landing page at `index.html`
- A current combined weather workspace at `weather.html`
- A planned product-page direction where each major product gets its own clean
  URL, such as `/radar`, `/satellite`, and `/alerts`
- Current and archive rendering endpoints
- Progress tracking for long-running jobs
- Local caching of downloads and generated products
- Built-in purge tooling for retention control

## Source Control and Recovery

- Private GitHub repository is active for this project as of 2026-04-16.
- Default workflow is commit-first for high-risk refactors so rollback is immediate.
- Recommended checkpoint pattern:
  - Commit before large structural edits
  - Use short-lived feature branches for refactors
  - Tag known-good milestones when major phases complete
- Preferred recovery path is now `git restore`/`git revert` instead of manual file recovery.

Suggested branch protections on `main`:

- Require pull request before merge
- Require at least one passing check for merge
- Block force-pushes and branch deletion

## Key Capabilities

### Data Workflows

- Surface maps (current and archive animation)
- Alert maps + active alert polygons (GeoJSON)
- Radar (Level 2 and Level 3, current and archive)
- GOES satellite imagery (current and archive)
- MRMS products from NOAA public data
- Lightning visualizations (heatmap, points, animation)

### Rendering and Performance

- Cartopy-based map rendering
- Optional pre-rendered basemap caches for surface and radar
- Data source fallback logic for radar/satellite:
  - NODD (AWS/GCP) when available
  - THREDDS fallback for robustness

### Ops Features

- Per-request progress endpoint: `/api/progress/{task_id}`
- File retention purge endpoint: `/api/purge`
- Unified static mounts for generated media under `/img/*`

## Tech Stack

- Backend: FastAPI, Uvicorn
- Data access: requests, boto3 (unsigned public bucket access), Siphon
- Geospatial/science: Cartopy, Shapely, PyProj, MetPy, Py-ART, xarray, netCDF4, cfgrib
- Image/video: Matplotlib, Pillow, imageio[ffmpeg]
- Frontend: HTML5, CSS, vanilla JavaScript

## Data Sources (Primary)

- NWS API
- Iowa Environmental Mesonet (IEM)
- NOAA Open Data Dissemination (NODD) via AWS/GCP public buckets
- UCAR THREDDS
- NOAA MRMS public S3 bucket (`noaa-mrms-pds`)

## Architecture at a Glance

- `main.py` hosts the FastAPI app, endpoint routing, static mounts, and task progress state.
- `index.html` is the main dashboard landing page served at `/`.
- `weather.html` and `js/weather.js` currently host the combined Leaflet weather workspace.
- Planned canonical product pages include `/alerts`, `/radar`, `/satellite`,
  `/spc`, `/surface`, `/mrms`, `/rtma`, `/drought`, and `/tropical`; these are
  not all present in this checkout yet. Legacy `.html` product URLs may remain
  as redirects or compatibility routes during migration.
- Domain modules (`surface/`, `alerts/`, `radar/`, `satellite_v2/`, `mrms/`, `rtma/`, `spc/`, `workers/`) handle download, cache, and render logic.
- Generated media is stored in workflow-specific directories and served as static content.
- Frontend pages call API endpoints directly and poll progress for long-running jobs.

## Project Layout

```text
2026-Dashboard/
  main.py
  requirements.txt
  index.html
  weather.html
  js/
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

### 4. Run Profiles (Worker Modes)

The default local startup path is:

```powershell
python main.py
```

The app supports explicit worker behavior through `WX_INPROC_WORKERS`, but the
previously documented `tools/*.ps1` launcher scripts are not present in this
checkout. The refactor target is a cross-platform app-managed worker supervisor
so Windows Task Scheduler is not required for normal local use.

- API-only mode (no in-process APScheduler):

```powershell
Remove `WX_INPROC_WORKERS` from the current shell, then run `python main.py`.
```

- In-process mode (enable `WX_INPROC_WORKERS=1`):

```powershell
$env:WX_INPROC_WORKERS = "1"
python main.py
```

- Dual mode (Task Scheduler + in-process workers):

```powershell
$env:WX_INPROC_WORKERS = "1"
python main.py
```

Dual mode is intended for validation/stress testing because it can duplicate refresh work.

Server starts on:

- `http://127.0.0.1:8000`

Open in browser:

- `http://127.0.0.1:8000/`
- `http://127.0.0.1:8000/weather.html`

## API Quick Reference

### Health and status

- `GET /api/status`

### Surface

- `GET /api/surface/current`
- `GET /api/surface/archive`
- `GET /api/surface` (legacy multiplexer)

### Alerts

- `GET /api/alerts/current`
- `GET /api/alerts/archive`
- `GET /api/alerts/polygons`
- `GET /api/alerts` (legacy multiplexer)

### Radar

- `GET /api/radar/sites`
- `GET /api/radar/current`
- `GET /api/radar/archive`
- `GET /api/radar` (legacy multiplexer)

### Weather Radar Live (Leaflet weather tab)

- `GET /api/radar/live/sites`
- `GET /api/radar/live/latest?site=KMHX&product=L3_N0B`
- `GET /api/radar/live/frames?site=KMHX&product=L3_N0B&hours=2`

Notes:

- Endpoints are cache-first and read from `cache/overlays/radar/...`.
- On cold cache miss, latest endpoint prioritizes first frame availability, then warms additional history asynchronously.
- Frontend radar controls include `Refresh`, `Clear` (clear overlays without resetting map extent), and multi-site/time-mode animation workflow.

### Satellite

- `GET /api/satellite/current`
- `GET /api/satellite/archive`
- `GET /api/satellite` (legacy multiplexer)

### Satellite v2 Rapid Worker

Satellite v2 Full Disk and CONUS imagery are live-rendered on demand with
tile-cache reuse and supertiles. The only scheduled Satellite v2 warmer is the
narrow rapid-sector worker, which targets high-cadence sectors where animation
latency matters.

Default rapid worker scope:

- GOES-19/18 `MESO1` and `MESO2`
- Himawari-9 `JAPAN`
- Meteosat-11 `RSS`
- Products: `Channel02` and `Channel13`
- Latest 12 frames, low worker count, cache-first tile warming

One-off examples:

```powershell
python -m workers.satellite_v2_rapid_worker --force
python -m workers.satellite_v2_rapid_worker --force --jobs goes19:MESO1 --products Channel02 --frames 2 --tile-workers 1
```

Tune rapid warming with environment variables:

```powershell
$env:WX_SATELLITE_V2_RAPID_WORKER_FRAMES = "12"
$env:WX_SATELLITE_V2_RAPID_TILE_WORKERS = "2"
```

### MRMS

- `GET /api/mrms/current`
- `GET /api/mrms/archive`
- `GET /api/mrms` (legacy multiplexer)

### Lightning

- `GET /api/lightning/latest`

### Task progress and cache maintenance

- `GET /api/progress/{task_id}`
- `POST /api/purge`

## Example Requests

```bash
# System status
curl "http://127.0.0.1:8000/api/status"

# Current radar image (auto source)
curl "http://127.0.0.1:8000/api/radar/current?request_id=test123&site=KMHX&product=N0B&level=Level%203&source=auto"

# Satellite archive animation
curl "http://127.0.0.1:8000/api/satellite/archive?request_id=sat1&sat_id=goes19&sector=CONUS&channel=Channel13&date_from=2026-03-10%2012:00&date_to=2026-03-10%2018:00&source=aws"

# Poll task progress
curl "http://127.0.0.1:8000/api/progress/test123"
```

## Basemap Cache Pre-Rendering (Optional but Recommended)

Pre-render static basemaps to reduce first-render latency:

```powershell
python surface/generate_basemaps.py
python radar/generate_radar_basemaps.py
```

Use `--force` to rebuild cache artifacts.

## Configuration Notes

- Product and style defaults live under `config/` and domain modules.
- Most endpoints accept display/style controls through a `style_config` JSON payload (stringified query param).
- Archive endpoints require paired `date_from` and `date_to`.
- Maximum archive spans are enforced in API logic per category.

## Data Retention and Purging

The dashboard includes retention controls on the landing page and via API:

- Endpoint: `POST /api/purge?hours=<N>&categories=radar,satellite,...`
- `hours=0` purges all selected categories
- Purge skips protected basemap cache directories

## Known Operational Considerations

- This repo is optimized for local execution, not hardened production deployment.
- CORS is currently open (`allow_origins=["*"]`).
- For large archive ranges, rendering and network time can be significant.
- Radar/Satellite source availability can vary by provider/time window.

## Roadmap (Concise)

- Add reproducible environment setup for geospatial dependencies (Windows-first lockfile strategy)
- Expand endpoint docs into OpenAPI-focused usage examples per workflow
- Add automated tests for API validation and renderer regression checks
- Improve observability with structured logging and task metrics
- Add optional auth and tighter CORS profiles for non-local deployments

## Contributing

This project currently supports personal operations first. If you contribute:

- Keep changes scoped by workflow (`surface`, `alerts`, `radar`, etc.)
- Preserve backward compatibility for legacy multiplexer endpoints where practical
- Include clear reproduction steps for rendering/data-source bugs

## License Recommendation

Recommended: MIT License.

Reasoning:

- Best fit for a practical tooling repository that may benefit from broad reuse
- Minimal friction for weather/dev contributors
- Compatible with mixed Python + frontend utility projects

If you adopt this recommendation, add a `LICENSE` file with MIT text and update this section to a final license statement.
