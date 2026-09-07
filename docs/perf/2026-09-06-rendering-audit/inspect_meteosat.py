"""Read acquired native source headers; do not decode full radiance arrays."""

import dataclasses
import json
import math
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
sys.path.insert(0, str(ROOT))


def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    import netCDF4
    import numpy as np
    from config.satellite_v2_config import SATELLITE_V2_FCI_MAX_GRID
    from satellite_v2.seviri_nat import _read_header

    acquisition = json.loads((OUT / "meteosat-acquisition.json").read_text())
    assert acquisition["status"] == "complete"
    channels = {}
    for transfer in acquisition["transfers"]:
        path = ROOT / transfer["path"]
        assert path.stat().st_size == transfer["bytes"]
        if path.suffix == ".nat":
            seviri = dataclasses.asdict(_read_header(path))
            continue
        with netCDF4.Dataset(path) as ds:
            group = ds.groups["data"]
            projection = group.variables["mtg_geos_projection"]
            height = float(projection.perspective_point_height)
            for name, ch in group.groups.items():
                measured = ch.groups["measured"]
                positions = {key: int(np.asarray(measured.variables[key][:])) for key in (
                    "start_position_row", "end_position_row",
                    "start_position_column", "end_position_column")}
                radiance = measured.variables["effective_radiance"]
                row = channels.setdefault(name, {
                    "dtype": str(radiance.dtype), "chunks": [],
                    "projection": {k: getattr(projection, k) for k in projection.ncattrs()},
                    "source_step_geos_m": {axis: abs(float(measured.variables[axis].scale_factor) * height)
                                           for axis in ("x", "y")},
                    "radiance_attributes": {k: getattr(radiance, k) for k in radiance.ncattrs()},
                })
                row["chunks"].append({**positions, "radiance_shape": list(radiance.shape)})
    for row in channels.values():
        chunks = sorted(row["chunks"], key=lambda c: c["start_position_row"])
        assert chunks[0]["start_position_row"] == 1
        for left, right in zip(chunks, chunks[1:]):
            assert left["end_position_row"] + 1 == right["start_position_row"]
        columns = chunks[0]["end_position_column"]
        assert all(c["start_position_column"] == 1 and c["end_position_column"] == columns for c in chunks)
        rows = chunks[-1]["end_position_row"]
        row["native_shape"] = [rows, columns]
        row["loader_policy_by_cap"] = []
        for cap in (2048, 4096, SATELLITE_V2_FCI_MAX_GRID):
            stride = 1
            while math.ceil(columns / stride) > cap:
                stride *= 2
            offset = stride // 2
            row["loader_policy_by_cap"].append({
                "cap": cap, "stride": stride, "offset": offset,
                "retained_shape": [len(range(offset, rows, stride)), len(range(offset, columns, stride))],
            })
    def convert(value):
        return value.tolist() if hasattr(value, "tolist") else str(value)
    result = {"category": "native_header_and_static_loader_policy_validation",
              "fci_effective_high_zoom_cap": SATELLITE_V2_FCI_MAX_GRID,
              "fci_channels": channels, "seviri_header": seviri,
              "limitations": ["Source step in projection metres is not local ground resolution near the limb.",
                              "Retained shapes calculated from executed loader policy; full array validation follows rendering."]}
    (OUT / "meteosat-headers.json").write_text(json.dumps(result, indent=2, default=convert) + "\n")
    print(json.dumps({"fci": {k: {p: v[p] for p in ("native_shape", "source_step_geos_m", "loader_policy_by_cap")}
                               for k, v in channels.items() if k in {"vis_06", "ir_105"}},
                      "seviri_header": seviri}, indent=2, default=convert))


if __name__ == "__main__":
    main()
