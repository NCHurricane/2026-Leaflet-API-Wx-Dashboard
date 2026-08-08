"""
Test the Level 2 chunk assembler and verify Py-ART can read the result.

Usage:
    python tools/test_l2_chunks.py [SITE]
    python tools/test_l2_chunks.py KRAX
"""

import argparse
import sys
import tempfile
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

def probe_with_pyart(path: Path) -> dict:
    import numpy as np
    import pyart

    result = {}
    try:
        radar = pyart.io.read_nexrad_archive(str(path))
        result["success"] = True
        result["nsweeps"] = int(getattr(radar, "nsweeps", 0))
        result["fields"] = list(getattr(radar, "fields", {}).keys())
        result["nrays"] = int(radar.nrays)
        result["ngates"] = int(radar.ngates)

        ranges = np.asarray(radar.range["data"])
        result["gate_spacing_m"] = float(np.diff(ranges).mean()) if len(ranges) > 1 else None
        result["max_range_km"] = float(ranges.max() / 1000) if len(ranges) else None
        result["elevations"] = [
            round(float(a), 1)
            for a in getattr(radar, "fixed_angle", {}).get("data", [])
        ]
        try:
            dts = pyart.util.datetimes_from_radar(radar)
            result["scan_time"] = str(dts[0]) if len(dts) else None
        except Exception:
            result["scan_time"] = None
    except Exception as exc:
        result["success"] = False
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def render_png(path: Path, out_png: Path, site: str) -> bool:
    import cartopy.crs as ccrs
    import matplotlib
    import pyart

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    try:
        radar = pyart.io.read_nexrad_archive(str(path))
        field = next(
            (f for f in ["reflectivity", "velocity"] if f in radar.fields), None
        )
        if not field:
            print("  No renderable field found.")
            return False

        from pyart.io.nexrad_common import NEXRAD_LOCATIONS

        info = NEXRAD_LOCATIONS.get(site, {})
        site_lat = float(info.get("lat", 35.0))
        site_lon = float(info.get("lon", -80.0))
        pad = 5.0

        projection = ccrs.epsg(3857)
        fig = plt.figure(figsize=(10, 10), dpi=150)
        ax = fig.add_axes([0, 0, 1, 1], projection=projection)
        ax.patch.set_alpha(0)
        ax.set_axis_off()
        ax.set_extent(
            [site_lon - pad, site_lon + pad, site_lat - pad, site_lat + pad],
            crs=ccrs.PlateCarree(),
        )

        display = pyart.graph.RadarMapDisplay(radar)
        vmin, vmax = (-30, 90) if field == "reflectivity" else (-30, 30)
        display.plot_ppi_map(
            field,
            sweep=0,
            ax=ax,
            projection=projection,
            min_lon=site_lon - pad,
            max_lon=site_lon + pad,
            min_lat=site_lat - pad,
            max_lat=site_lat + pad,
            embellish=False,
            colorbar_flag=False,
            title_flag=False,
            vmin=vmin,
            vmax=vmax,
        )
        fig.savefig(str(out_png), format="png", transparent=True, dpi=150)
        plt.close(fig)
        size_kb = out_png.stat().st_size / 1024
        print(f"  Rendered: {out_png.name} ({size_kb:.1f} KB)")
        return True
    except Exception as exc:
        print(f"  Render failed: {type(exc).__name__}: {exc}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site", nargs="?", default="KRAX", help="Four-letter NEXRAD site")
    args = parser.parse_args()
    site = args.site.strip().upper()
    if len(site) != 4 or not site.isalpha():
        parser.error("site must be a four-letter NEXRAD identifier")

    from radar.radar_chunks_utils import (
        assembled_scan_filename,
        assemble_scan,
        group_chunks_by_scan,
        list_site_chunks,
        scan_is_complete,
    )
    from lib.s3_utils import get_s3_client

    print(f"\n=== Level 2 Chunks Assembly Test — {site} ===\n")

    s3 = get_s3_client()

    print(f"Listing chunks for {site}...")
    all_chunks = list_site_chunks(s3, site)
    if not all_chunks:
        print("  No chunks found.")
        return 1

    scans = group_chunks_by_scan(all_chunks)
    sorted_prefixes = sorted(scans.keys(), key=lambda p: scans[p][0]["scan_dt"])

    print(f"  Found {len(all_chunks)} chunks across {len(scans)} scans:")
    for prefix in sorted_prefixes[-3:]:
        chunks = scans[prefix]
        complete = scan_is_complete(chunks)
        total_kb = sum(c["size"] for c in chunks) / 1024
        print(
            f"    {prefix}  {len(chunks)} chunks  "
            f"{'COMPLETE' if complete else 'partial'}  {total_kb:.1f} KB total"
        )

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        # Test most recent scan
        test_prefix = sorted_prefixes[-1]
        test_chunks = scans[test_prefix]
        filename = assembled_scan_filename(test_prefix)
        out_path = tmp_path / filename

        print(f"\n--- Assembling: {filename} ({len(test_chunks)} chunks) ---")
        ok = assemble_scan(s3, test_chunks, out_path)
        if not ok:
            print("  Assembly failed.")
            return 1

        size_kb = out_path.stat().st_size / 1024
        print(f"  Assembled file: {size_kb:.1f} KB")

        print("\n--- Probing with Py-ART ---")
        result = probe_with_pyart(out_path)
        if result.get("success"):
            print("  Py-ART read:    OK")
            print(f"  Scan time:      {result.get('scan_time')}")
            print(f"  Sweeps:         {result.get('nsweeps')}")
            print(f"  Elevations:     {result.get('elevations')}")
            print(f"  Rays:           {result.get('nrays')}")
            print(f"  Gates:          {result.get('ngates')}")
            if result.get("gate_spacing_m"):
                print(f"  Gate spacing:   {result['gate_spacing_m']:.0f} m")
            if result.get("max_range_km"):
                print(f"  Max range:      {result['max_range_km']:.1f} km")
            print(f"  Fields:         {result.get('fields')}")

            out_png = tmp_path / f"{site}_chunk_assembled.png"
            print("\n--- Rendering PNG ---")
            rendered = render_png(out_path, out_png, site)
            if rendered:
                import shutil

                diagnostic_dir = project_root / "cache" / "diagnostics" / "radar"
                diagnostic_dir.mkdir(parents=True, exist_ok=True)
                dest = diagnostic_dir / f"{site}_chunk_assembled.png"
                shutil.copy(str(out_png), str(dest))
                print(f"  Saved to {dest.relative_to(project_root)}")
        else:
            print(f"  Py-ART FAILED: {result.get('error')}")

    print("\n=== Done ===\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
