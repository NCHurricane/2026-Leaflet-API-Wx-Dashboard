# Radar Palette Preview

Standalone tool for designing radar `.pal` colortables. Upload a local radar
volume and a `.pal` file; see the volume rendered with that palette. Tweak the
`.pal`, re-render, repeat.

Independent of the main dashboard — it reuses only the pure palette parser
(`config/radar_colortable_utils.py`) and runs on its own port. No caching,
worker, frame index, or network download.

## Run

```powershell
powershell -ExecutionPolicy Bypass -File pal_preview\run.ps1
```

Then open http://127.0.0.1:8050

Or directly:

```powershell
cd pal_preview
..\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8050
```

## Use

1. **Radar volume** — a local NEXRAD Level II archive or Level III product file.
2. **Palette (.pal)** — the colortable to preview.
3. Optional: **field** (auto-detects reflectivity), **vmin/vmax** (default to
   the palette's own value range), **sweep** (elevation index, default 0).
4. **Render** — the PPI image appears on the right.

Errors (undecodable file, empty palette, unknown field) surface as a message;
the field error lists the file's available fields.
