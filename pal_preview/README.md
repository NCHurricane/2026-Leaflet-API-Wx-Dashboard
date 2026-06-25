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

1. **Radar source** — either:
   - **Fetch sample data**: type a site (e.g. `KTWX`) and click *Fetch*. This
     downloads the latest Level II volume plus one file for each Level III
     product from AWS into `samples/`, then offers them in the dropdown. Some
     products are storm-dependent and may come back empty on a quiet day.
   - **Upload** a local NEXRAD Level II archive or Level III product file.
2. **Palette (.pal)** — the colortable to preview.
3. Optional: **field** (auto-detects reflectivity), **vmin/vmax** (default to
   the palette's own value range), **sweep** (elevation index, default 0).
4. **Render** — the PPI image appears on the right.

Errors (undecodable file, empty palette, unknown field) surface as a message;
the field error lists the file's available fields.

### Fetch from the command line

```powershell
cd pal_preview
..\.venv\Scripts\python.exe fetch_samples.py --site KTWX --out samples
```

Downloaded `samples/` is transient (git-ignored) and is not touched by the
dashboard's radar worker.

## Notes

- Level II is a single volume containing every moment, so one Level II file
  covers all the `L2_*` products; only the 11 Level III products are separate
  files.
- Digital Level III products (Echo Tops, VIL) are decoded via a MetPy fallback,
  mirroring the dashboard; their render title shows `reflectivity` (the field
  slot used) but the colorbar units come from the palette.
