"""Standalone radar palette (.pal) preview tool.

A self-contained FastAPI app — independent of the dashboard's caching, worker,
and frame-index machinery. Upload a local radar volume plus a .pal colortable
and see the volume rendered with that palette. Iterate on a palette by
re-uploading and re-rendering.

Reuses only the dashboard's pure palette parser/colormap builder
(config.radar_colortable_utils); everything else here is fresh.

Run with run.ps1, or from this folder:
    ../.venv/Scripts/python.exe -m uvicorn app:app --host 127.0.0.1 --port 8050
"""

from __future__ import annotations

import io
import sys
import tempfile
import zlib
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse

# Make the dashboard's pure palette utilities importable when run from this dir.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config.radar_colortable_utils import _build_colormap, _parse_pal
from fetch_samples import fetch_samples

app = FastAPI(title="Radar Palette Preview")

_HERE = Path(__file__).resolve().parent
_INDEX_HTML = _HERE / "index.html"
_SAMPLES_DIR = _HERE / "samples"

# Reflectivity-like field names, preferred when auto-selecting a field.
_PREFERRED_FIELDS = (
    "reflectivity",
    "reflectivity_horizontal",
    "equivalent_reflectivity_factor",
)


# Per-product max range (km) for MetPy-decoded digital Level III products that
# Py-ART cannot read natively. Sourced from MetPy's prod_spec_map.
_METPY_PRODUCT_MAX_RANGE_KM = {
    134: 460.0,  # High Resolution VIL (DVL)
    135: 345.0,  # Enhanced Echo Tops (EET)
}


def _pyart_has_fields(radar) -> bool:
    """Py-ART can 'succeed' on some digital Level III products yet return no
    fields; treat that as a decode miss."""
    return bool(getattr(radar, "fields", None))


def _read_level3_with_metpy(file_path: str):
    """Decode a digital Level III product (VIL/Echo Tops) with MetPy and wrap it
    in a Py-ART Radar object so the render path is unchanged."""
    import numpy as np
    import pyart
    from metpy.io import Level3File

    level3 = Level3File(file_path)
    prod_code = int(getattr(level3.prod_desc, "prod_code", 0))
    if prod_code not in _METPY_PRODUCT_MAX_RANGE_KM:
        raise ValueError(f"MetPy decode unsupported for Level III product {prod_code}")

    block = level3.sym_block[0][0]
    raw = np.array(block["data"])
    mapped = level3.map_data(raw)
    if isinstance(mapped, tuple):  # Echo Tops returns (data, topped_flag)
        mapped = mapped[0]
    data = np.ma.masked_invalid(np.asarray(mapped, dtype=float))

    nrays, ngates = data.shape
    gate_width_m = (_METPY_PRODUCT_MAX_RANGE_KM[prod_code] * 1000.0) / ngates
    azimuths = np.asarray(block["start_az"], dtype=float)

    radar = pyart.testing.make_empty_ppi_radar(ngates, nrays, 1)
    radar.range["data"] = np.arange(ngates, dtype=float) * gate_width_m
    radar.azimuth["data"] = azimuths
    radar.elevation["data"] = np.zeros(nrays, dtype=float)
    radar.fixed_angle["data"] = np.array([0.0])
    radar.latitude["data"] = np.array([float(level3.lat)])
    radar.longitude["data"] = np.array([float(level3.lon)])
    radar.altitude["data"] = np.array([float(getattr(level3, "height", 0.0) or 0.0)])
    radar.sweep_start_ray_index["data"] = np.array([0])
    radar.sweep_end_ray_index["data"] = np.array([nrays - 1])
    radar.fields["reflectivity"] = {
        "data": data,
        "units": "",
        "long_name": f"Level III product {prod_code}",
    }
    return radar


def _read_level3_file(file_path: str):
    """Read a Level III product, falling back to MetPy (and a zlib-decompress
    pass) for digital products Py-ART cannot decode."""
    import pyart

    try:
        radar = pyart.io.read_nexrad_level3(file_path)
        if _pyart_has_fields(radar):
            return radar
        return _read_level3_with_metpy(file_path)
    except (NotImplementedError, ValueError, AssertionError):
        with open(file_path, "rb") as fh:
            raw = fh.read()
        zlib_start = -1
        for magic in (b"\x78\xda", b"\x78\x9c", b"\x78\x01"):
            zlib_start = raw.find(magic, 0, 128)
            if zlib_start != -1:
                break
        if zlib_start == -1:
            return _read_level3_with_metpy(file_path)
        decompressor = zlib.decompressobj()
        header_block = decompressor.decompress(raw[zlib_start:])
        full_nids = header_block + decompressor.unused_data
        temp_path = Path(file_path).with_suffix(".nids")
        temp_path.write_bytes(full_nids)
        try:
            radar = pyart.io.read_nexrad_level3(str(temp_path))
            if _pyart_has_fields(radar):
                return radar
            return _read_level3_with_metpy(file_path)
        except (NotImplementedError, ValueError, AssertionError):
            return _read_level3_with_metpy(file_path)
        finally:
            temp_path.unlink(missing_ok=True)


def _read_radar(path: str):
    """Read a radar volume (Level II or III), trying Py-ART then a MetPy
    fallback for digital Level III products.

    Returns a Py-ART Radar object. Raises ValueError if nothing can decode it.
    """
    import pyart

    # Auto-detecting reader handles Level II and many Level III files.
    try:
        radar = pyart.io.read(path)
        if _pyart_has_fields(radar):
            return radar
    except Exception:
        pass

    # Level III path with MetPy + zlib fallbacks (VIL, Echo Tops, etc.).
    try:
        return _read_level3_file(path)
    except Exception:
        pass

    # Explicit NEXRAD Level II archive reader.
    try:
        return pyart.io.read_nexrad_archive(path)
    except Exception as exc:
        raise ValueError(f"Could not decode radar file: {exc}") from exc


def _select_field(radar, requested: str) -> str:
    """Pick the field to render: the requested one, else a reflectivity-like
    field, else the first available."""
    fields = list(getattr(radar, "fields", {}).keys())
    if not fields:
        raise ValueError("Radar file contains no fields")

    requested = (requested or "").strip()
    if requested:
        if requested in fields:
            return requested
        raise ValueError(
            f"Field {requested!r} not in file. Available: {', '.join(fields)}"
        )

    for preferred in _PREFERRED_FIELDS:
        if preferred in fields:
            return preferred
    return fields[0]


def _palette_range(parsed: dict) -> tuple[float, float]:
    """Min/max value across the palette's color entries."""
    values = [float(entry["value"]) for entry in parsed["color_entries"]]
    return min(values), max(values)


def _list_samples() -> list[str]:
    """Filenames currently in the samples folder, newest first."""
    if not _SAMPLES_DIR.exists():
        return []
    files = [p for p in _SAMPLES_DIR.iterdir() if p.is_file() and p.name != "_work"]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [p.name for p in files]


def _resolve_sample(name: str) -> Path:
    """Resolve a sample filename to a path inside the samples dir (no traversal)."""
    safe = Path(name).name  # strip any directory components
    path = _SAMPLES_DIR / safe
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"Sample not found: {safe}")
    return path


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return _INDEX_HTML.read_text(encoding="utf-8")


@app.get("/samples")
def samples() -> dict:
    return {"samples": _list_samples()}


@app.post("/fetch")
def fetch(site: str = Form("KTWX"), lookback: float = Form(3.0)) -> dict:
    """Download a fresh sample set (1 Level II volume + each Level III product)."""
    site = (site or "").strip().upper()
    if not site:
        raise HTTPException(status_code=400, detail="Site is required")
    try:
        results = fetch_samples(site, _SAMPLES_DIR, lookback_hours=lookback)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - report provider failures to the UI
        raise HTTPException(status_code=502, detail=f"Fetch failed: {exc}") from exc
    return {"results": results, "samples": _list_samples()}


@app.post("/render")
async def render(
    pal_file: UploadFile = File(...),
    radar_file: UploadFile | None = File(None),
    radar_sample: str = Form(""),
    field: str = Form(""),
    vmin: str = Form(""),
    vmax: str = Form(""),
    sweep: int = Form(0),
) -> StreamingResponse:
    """Render a radar volume (uploaded or a fetched sample) with the palette."""
    radar_tmp: str | None = None
    pal_tmp: str | None = None
    try:
        pal_bytes = await pal_file.read()
        if not pal_bytes:
            raise HTTPException(status_code=400, detail="Empty palette file")
        with tempfile.NamedTemporaryFile(suffix=".pal", delete=False) as fh_pal:
            fh_pal.write(pal_bytes)
            pal_tmp = fh_pal.name

        # Radar source: a fetched sample takes precedence over an upload.
        if radar_sample.strip():
            radar_path = str(_resolve_sample(radar_sample))
        elif radar_file is not None:
            radar_bytes = await radar_file.read()
            if not radar_bytes:
                raise HTTPException(status_code=400, detail="Empty radar file")
            radar_suffix = Path(radar_file.filename or "radar").suffix or ".bin"
            with tempfile.NamedTemporaryFile(
                suffix=radar_suffix, delete=False
            ) as fh_radar:
                fh_radar.write(radar_bytes)
                radar_tmp = fh_radar.name
            radar_path = radar_tmp
        else:
            raise HTTPException(
                status_code=400,
                detail="Provide a radar file upload or choose a fetched sample",
            )

        parsed = _parse_pal(Path(pal_tmp))
        if not parsed.get("color_entries"):
            raise HTTPException(
                status_code=400, detail="Palette has no color entries"
            )

        # Default the data range to the palette's own range so the colors map
        # exactly across it; allow explicit overrides.
        pal_min, pal_max = _palette_range(parsed)
        try:
            v_lo = float(vmin) if vmin.strip() else pal_min
            v_hi = float(vmax) if vmax.strip() else pal_max
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail=f"Invalid vmin/vmax: {exc}"
            ) from exc
        if v_hi <= v_lo:
            raise HTTPException(status_code=400, detail="vmax must exceed vmin")

        try:
            radar = _read_radar(radar_path)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        try:
            field_name = _select_field(radar, field)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        cmap = _build_colormap(
            parsed, v_lo, v_hi, name="pal_preview", own_range=False
        )
        cmap.set_bad((0, 0, 0, 0))
        cmap.set_under((0, 0, 0, 0))

        png = _render_png(radar, field_name, int(sweep), cmap, v_lo, v_hi, parsed)
        return StreamingResponse(
            io.BytesIO(png),
            media_type="image/png",
            headers={"Cache-Control": "no-store"},
        )
    finally:
        for tmp in (radar_tmp, pal_tmp):
            if tmp:
                try:
                    Path(tmp).unlink(missing_ok=True)
                except OSError:
                    pass


def _render_png(
    radar,
    field_name: str,
    sweep: int,
    cmap,
    vmin: float,
    vmax: float,
    parsed: dict,
) -> bytes:
    """Render a single PPI sweep to PNG bytes (plain plot, no map projection)."""
    import pyart

    n_sweeps = int(getattr(radar, "nsweeps", 1) or 1)
    sweep = max(0, min(sweep, n_sweeps - 1))

    fig = plt.figure(figsize=(9, 8), dpi=110)
    ax = fig.add_subplot(111)
    try:
        display = pyart.graph.RadarDisplay(radar)
        units = parsed.get("units", "") or ""
        display.plot(
            field_name,
            sweep=sweep,
            ax=ax,
            cmap=cmap,
            vmin=vmin,
            vmax=vmax,
            colorbar_flag=True,
            colorbar_label=units,
            title=f"{field_name}  (sweep {sweep})",
        )
        display.set_limits(ax=ax)
        ax.set_aspect("equal")
        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight")
        return buf.getvalue()
    finally:
        plt.close(fig)
