import argparse
import json
import os
import shutil
from datetime import datetime, timezone

import shapefile


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


def parse_state_filter(raw):
    if not raw:
        return None
    parts = [x.strip().upper() for x in raw.split(",") if x.strip()]
    return set(parts) if parts else None


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def clean_state_output(root_dir, state_abbr):
    state_dir = os.path.join(root_dir, state_abbr)
    if os.path.isdir(state_dir):
        shutil.rmtree(state_dir, ignore_errors=True)


def build_state_county_shapefiles(source_shp, output_root, state_filter=None, force=False):
    source_shp = os.path.abspath(source_shp)
    output_root = os.path.abspath(output_root)

    if not os.path.exists(source_shp):
        raise FileNotFoundError(f"Source shapefile not found: {source_shp}")

    source_base, _ = os.path.splitext(source_shp)
    source_prj = source_base + ".prj"

    ensure_dir(output_root)

    print(f"Reading source counties: {source_shp}")
    reader = shapefile.Reader(source_shp)

    # Copy field schema exactly (skip DeletionFlag entry)
    fields = reader.fields[1:]
    field_names = [f[0] for f in fields]
    if "STATEFP" not in field_names:
        raise RuntimeError("STATEFP field not found in source shapefile.")
    statefp_idx = field_names.index("STATEFP")

    writers = {}
    counts = {}
    out_bases = {}

    def get_writer_for_state(state_abbr):
        if state_abbr in writers:
            return writers[state_abbr]

        state_dir = os.path.join(output_root, state_abbr)
        ensure_dir(state_dir)
        out_base = os.path.join(state_dir, f"counties_{state_abbr}")

        shp_path = out_base + ".shp"
        if os.path.exists(shp_path) and not force:
            print(
                f"Skipping existing state shapefile (use --force): {shp_path}")
            return None

        if force:
            clean_state_output(output_root, state_abbr)
            ensure_dir(state_dir)

        w = shapefile.Writer(target=out_base, shapeType=reader.shapeType)
        for fld in fields:
            w.field(*fld)

        writers[state_abbr] = w
        counts[state_abbr] = 0
        out_bases[state_abbr] = out_base
        return w

    total = 0
    kept = 0

    for sr in reader.iterShapeRecords():
        total += 1
        rec = list(sr.record)
        statefp = str(rec[statefp_idx]).zfill(2)
        state_abbr = STATEFP_TO_ABBR.get(statefp)
        if not state_abbr:
            continue
        if state_filter and state_abbr not in state_filter:
            continue

        w = get_writer_for_state(state_abbr)
        if w is None:
            # Existing file and no --force; skip writing this state
            continue

        w.shape(sr.shape)
        w.record(*rec)
        counts[state_abbr] += 1
        kept += 1

    # Close writers and copy .prj
    for state_abbr, w in writers.items():
        w.close()
        out_base = out_bases[state_abbr]
        if os.path.exists(source_prj):
            shutil.copy2(source_prj, out_base + ".prj")

    index = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_shp": source_shp,
        "source_total_records": total,
        "written_total_records": kept,
        "states_written": {},
    }

    for state_abbr in sorted(out_bases.keys()):
        out_base = out_bases[state_abbr]
        rel_base = os.path.relpath(out_base, os.getcwd()).replace("\\", "/")
        index["states_written"][state_abbr] = {
            "counties": counts.get(state_abbr, 0),
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
    print(f"Processed source records: {total}")
    print(f"Written county records: {kept}")
    print(f"States written: {len(out_bases)}")
    print(f"Index file: {index_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Split national county shapefile into per-state shapefiles."
    )
    parser.add_argument(
        "--source-shp",
        default="shapefiles/cb_2021_us_county_5m.shp",
        help="Path to national county .shp",
    )
    parser.add_argument(
        "--output-root",
        default="shapefiles/counties",
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

    build_state_county_shapefiles(
        source_shp=args.source_shp,
        output_root=args.output_root,
        state_filter=state_filter,
        force=args.force,
    )


if __name__ == "__main__":
    main()
