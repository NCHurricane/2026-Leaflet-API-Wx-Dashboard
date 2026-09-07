"""Validate the two pinned retained inputs; no provider or rendering calls."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]


def main() -> None:
    import eccodes
    import pyart

    records = json.loads((OUT / "preflight.json").read_text())[
        "selected_input_candidates"
    ]
    provenance = []
    if not (ROOT / records[0]["path"]).is_file():
        previous = records[0]["path"]
        candidates = sorted((ROOT / "cache/radar/live/radar_level2_downloads/_VOLUME/KRAX").glob("KRAX*_V06"))
        assert candidates, "No retained replacement Radar volume"
        path = candidates[-1]
        with path.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        records[0] = {"path": path.relative_to(ROOT).as_posix(),
                      "bytes": path.stat().st_size, "sha256": digest}
        provenance.append({"missing_previous_candidate": previous,
                           "replacement": records[0]["path"],
                           "reason": "Previous candidate absent before first native validation or timing."})
    paths = []
    for record in records:
        path = ROOT / record["path"]
        with path.open("rb") as handle:
            assert hashlib.file_digest(handle, "sha256").hexdigest() == record["sha256"]
        pinned = ROOT / "cache/rendering-audit-20260906/pinned" / path.name
        pinned.parent.mkdir(parents=True, exist_ok=True)
        if not pinned.exists():
            shutil.copyfile(path, pinned)
        with pinned.open("rb") as handle:
            assert hashlib.file_digest(handle, "sha256").hexdigest() == record["sha256"]
        record["pinned_path"] = pinned.relative_to(ROOT).as_posix()
        paths.append(pinned)

    radar = pyart.io.read_nexrad_archive(str(paths[0]))
    fields = {}
    for key in ("reflectivity", "cross_correlation_ratio"):
        data = radar.get_field(0, key)
        fields[key] = {
            "shape": list(data.shape), "dtype": str(data.dtype),
            "valid_samples": int(data.count()),
            "minimum": float(data.min()), "maximum": float(data.max()),
            "units": radar.fields[key].get("units"),
        }
        assert data.count() > 0
    radar_record = {
        "source": records[0], "time_units": radar.time["units"],
        "sweeps": int(radar.nsweeps), "rays": int(radar.nrays),
        "gates": int(radar.ngates),
        "sweep0_elevation_degrees": float(radar.fixed_angle["data"][0]),
        "gate_spacing_m": float(np.diff(radar.range["data"])[0]),
        "latitude": float(radar.latitude["data"][0]),
        "longitude": float(radar.longitude["data"][0]), "fields": fields,
    }
    del radar

    messages = []
    keys = (
        "shortName", "cfVarName", "name", "units", "dataDate", "dataTime",
        "validityDate", "validityTime", "gridType", "Nx", "Ny",
        "DxInMetres", "DyInMetres", "latitudeOfFirstGridPointInDegrees",
        "longitudeOfFirstGridPointInDegrees", "Latin1InDegrees",
        "Latin2InDegrees", "LoVInDegrees", "iScansNegatively",
        "jScansPositively", "uvRelativeToGrid", "numberOfDataPoints",
    )
    with paths[1].open("rb") as handle:
        while (gid := eccodes.codes_grib_new_from_file(handle)) is not None:
            try:
                row = {}
                for key in keys:
                    try:
                        row[key] = eccodes.codes_get(gid, key)
                    except eccodes.CodesInternalError:
                        pass
                if row.get("cfVarName") in {"si10", "wdir10"}:
                    values = eccodes.codes_get_values(gid)
                    row["decoded_values"] = {
                        "count": int(values.size),
                        "finite_count": int(np.isfinite(values).sum()),
                        "minimum": float(values.min()), "maximum": float(values.max()),
                        "missing_value": float(eccodes.codes_get(gid, "missingValue")),
                    }
                messages.append(row)
            finally:
                eccodes.codes_release(gid)
    assert any(row.get("cfVarName") == "si10" for row in messages)
    result = {
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "evidence_category": "native_source_content_validation_not_render_timing",
        "candidate_changes": provenance,
        "radar": radar_record,
        "rtma": {"source": records[1], "messages": messages},
        "limitations": [
            "Radar field checks cover sweep zero only; no visual quality comparison.",
            "RTMA wind values decoded; other messages inspected as headers only.",
            "Source copies pinned in isolated audit cache; live sources only read.",
            "No provider requests, rendered artifacts or browser run.",
        ],
    }
    (OUT / "validated-local.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"radar": radar_record, "rtma_message_count": len(messages),
                      "rtma_wind": [r for r in messages if "decoded_values" in r]}, indent=2))


if __name__ == "__main__":
    main()
