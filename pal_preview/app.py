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

app = FastAPI(title="Radar Palette Preview")

_INDEX_HTML = Path(__file__).resolve().parent / "index.html"

# Reflectivity-like field names, preferred when auto-selecting a field.
_PREFERRED_FIELDS = (
    "reflectivity",
    "reflectivity_horizontal",
    "equivalent_reflectivity_factor",
)


def _read_radar(path: str):
    """Read a radar volume, trying the common Py-ART readers then MetPy.

    Returns a Py-ART Radar object. Raises ValueError if nothing can decode it.
    """
    import pyart

    # Auto-detecting reader handles Level II and many Level III files.
    try:
        return pyart.io.read(path)
    except Exception:
        pass

    # Explicit NEXRAD Level III reader.
    try:
        return pyart.io.read_nexrad_level3(path)
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


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return _INDEX_HTML.read_text(encoding="utf-8")


@app.post("/render")
async def render(
    radar_file: UploadFile = File(...),
    pal_file: UploadFile = File(...),
    field: str = Form(""),
    vmin: str = Form(""),
    vmax: str = Form(""),
    sweep: int = Form(0),
) -> StreamingResponse:
    """Render the uploaded radar volume with the uploaded palette."""
    radar_tmp: str | None = None
    pal_tmp: str | None = None
    try:
        radar_bytes = await radar_file.read()
        pal_bytes = await pal_file.read()
        if not radar_bytes:
            raise HTTPException(status_code=400, detail="Empty radar file")
        if not pal_bytes:
            raise HTTPException(status_code=400, detail="Empty palette file")

        radar_suffix = Path(radar_file.filename or "radar").suffix or ".bin"
        with tempfile.NamedTemporaryFile(
            suffix=radar_suffix, delete=False
        ) as fh_radar:
            fh_radar.write(radar_bytes)
            radar_tmp = fh_radar.name
        with tempfile.NamedTemporaryFile(suffix=".pal", delete=False) as fh_pal:
            fh_pal.write(pal_bytes)
            pal_tmp = fh_pal.name

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
            radar = _read_radar(radar_tmp)
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
