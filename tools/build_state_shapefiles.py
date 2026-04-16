import argparse
import json
import os
import shutil
from collections import defaultdict
from datetime import datetime, timezone

import shapefile
from shapely.geometry import mapping, shape
from shapely.ops import unary_union


# Census STATEFP -> USPS abbreviation
STATEFP_TO_ABBR = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO",
    "09": "CT", "10": "DE", "11": "DC", "12": "FL", "13": "GA", "15": "HI",
    "16": "ID", "17": "IL", "18": "IN", "19": "IA", "20": "KS", "21": "KY",
    "22": "LA", "23": "ME", "24": "MD", "25": "MA", "26": "MI", "27": "MN",
    "28": "MS", "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
    "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND", "39": "OH",
    "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD",
    "47": "TN", "48": "TX", "49": "UT", "50": "VT", "51": "VA", "53": "WA",
    "54": "WV", "55": "WI", "56": "WY",
    "60": "AS", "66": "GU", "69": "MP", "72": "PR", "78": "VI",
}

ABBR_TO_NAME = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii",
    "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine",
    "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska",
    "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico",
    "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio",
    "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island",
    "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas",
    "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
    "AS": "American Samoa", "GU": "Guam", "MP": "Northern Mariana Islands",
    "PR": "Puerto Rico", "VI": "U.S. Virgin Islands",
}


def parse_state_filter(raw):
    if not raw:
        return None
    parts = [x.strip().upper() for x in raw.split(",") if x.strip()]
    return set(parts) if parts else None


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def shapefile_shape_to_geojson_type(shape_type):
    """Map pyshp shape type int to GeoJSON geometry type string."""
    # 5 = Polygon, 15 = PolygonZ, 25 = PolygonM
    return "Polygon" if shape_type in (5, 15, 25) else "MultiPolygon"


def write_state_shapefile(out_base, dissolved_geom, state_abbr, statefp, source_prj, force):
    """Write a single-feature state outline shapefile."""
    shp_path = out_base + ".shp"
    if os.path.exists(shp_path) and not force:
        print(f"  Skipping existing (use --force): {shp_path}")
        return False

    state_dir = os.path.dirname(out_base)
    if os.path.isdir(state_dir) and force:
        shutil.rmtree(state_dir, ignore_errors=True)
    ensure_dir(state_dir)

    # Determine pyshp shape type: 5=Polygon, 3=Polyline (we always use polygon here)
    geom_type = dissolved_geom.geom_type  # "Polygon" or "MultiPolygon"
    shape_type = 5  # Polygon

    w = shapefile.Writer(target=out_base, shapeType=shape_type)
    w.field("STATEFP", "C", size=2)
    w.field("STATE_ABBR", "C", size=2)
    w.field("STATE_NAME", "C", size=50)

    # Convert dissolved shapely geometry to pyshp __geo_interface__ compatible dict
    geom_dict = mapping(dissolved_geom)

    if geom_type == "Polygon":
        # parts: list of rings
        parts = [list(ring) for ring in [geom_dict["coordinates"]
                                         [0]] + list(geom_dict["coordinates"][1:])]
        w.poly(parts)
    else:
        # MultiPolygon: flatten all rings across all polygons
        all_rings = []
        for poly_coords in geom_dict["coordinates"]:
            for ring in poly_coords:
                all_rings.append(list(ring))
        w.poly(all_rings)

    w.record(statefp, state_abbr, ABBR_TO_NAME.get(state_abbr, ""))
    w.close()

    if source_prj and os.path.exists(source_prj):
        shutil.copy2(source_prj, out_base + ".prj")

    return True


def build_state_outline_shapefiles(source_shp, output_root, state_filter=None, force=False):
    source_shp = os.path.abspath(source_shp)
    output_root = os.path.abspath(output_root)

    if not os.path.exists(source_shp):
        raise FileNotFoundError(f"Source shapefile not found: {source_shp}")

    source_base, _ = os.path.splitext(source_shp)
    source_prj = source_base + ".prj"

    ensure_dir(output_root)

    print(f"Reading source counties: {source_shp}")
    reader = shapefile.Reader(source_shp)

    fields = reader.fields[1:]
    field_names = [f[0] for f in fields]
    if "STATEFP" not in field_names:
        raise RuntimeError("STATEFP field not found in source shapefile.")
    statefp_idx = field_names.index("STATEFP")

    # Accumulate county geometries per state
    state_geoms = defaultdict(list)   # state_abbr -> [shapely geom, ...]
    state_fps = {}                     # state_abbr -> statefp string
    total = 0

    print("Collecting county geometries by state...")
    for sr in reader.iterShapeRecords():
        total += 1
        rec = list(sr.record)
        statefp = str(rec[statefp_idx]).zfill(2)
        state_abbr = STATEFP_TO_ABBR.get(statefp)
        if not state_abbr:
            continue
        if state_filter and state_abbr not in state_filter:
            continue

        try:
            geom = shape(sr.shape.__geo_interface__)
            if not geom.is_valid:
                geom = geom.buffer(0)
            state_geoms[state_abbr].append(geom)
            state_fps[state_abbr] = statefp
        except Exception as exc:
            print(
                f"  Warning: skipping invalid geometry in {state_abbr}: {exc}")

    print(f"Dissolving and writing state outlines...")
    written = 0
    skipped = 0
    out_bases = {}

    for state_abbr in sorted(state_geoms.keys()):
        geoms = state_geoms[state_abbr]
        statefp = state_fps[state_abbr]

        print(f"  {state_abbr}: dissolving {len(geoms)} counties...",
              end=" ", flush=True)
        try:
            dissolved = unary_union(geoms)
        except Exception as exc:
            print(f"FAILED ({exc}), skipping.")
            continue

        state_dir = os.path.join(output_root, state_abbr)
        out_base = os.path.join(state_dir, f"state_{state_abbr}")
        out_bases[state_abbr] = out_base

        ok = write_state_shapefile(
            out_base, dissolved, state_abbr, statefp, source_prj, force)
        if ok:
            written += 1
            print("done.")
        else:
            skipped += 1

    index = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_shp": source_shp,
        "source_county_records": total,
        "states_written": written,
        "states_skipped": skipped,
        "states": {},
    }

    for state_abbr in sorted(out_bases.keys()):
        out_base = out_bases[state_abbr]
        rel_base = os.path.relpath(out_base, os.getcwd()).replace("\\", "/")
        index["states"][state_abbr] = {
            "name": ABBR_TO_NAME.get(state_abbr, ""),
            "statefp": state_fps.get(state_abbr, ""),
            "base_path": rel_base,
            "files": {
                "shp": rel_base + ".shp",
                "shx": rel_base + ".shx",
                "dbf": rel_base + ".dbf",
                "prj": rel_base + ".prj",
            },
        }

    index_path = os.path.join(output_root, "index.json")
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)

    print("")
    print(f"Source county records read : {total}")
    print(f"State outline files written: {written}")
    print(f"State outline files skipped: {skipped}")
    print(f"Index file                 : {index_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Dissolve national county shapefile into per-state outline shapefiles."
    )
    parser.add_argument(
        "--source-shp",
        default="shapefiles/cb_2021_us_county_5m.shp",
        help="Path to national county .shp (used as dissolve source)",
    )
    parser.add_argument(
        "--output-root",
        default="shapefiles/states",
        help="Output root folder (state folders created underneath)",
    )
    parser.add_argument(
        "--states",
        default="",
        help="Optional comma-separated state abbreviations, e.g. NC,SC,VA",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing per-state outputs",
    )

    args = parser.parse_args()
    state_filter = parse_state_filter(args.states)

    build_state_outline_shapefiles(
        source_shp=args.source_shp,
        output_root=args.output_root,
        state_filter=state_filter,
        force=args.force,
    )


if __name__ == "__main__":
    main()
