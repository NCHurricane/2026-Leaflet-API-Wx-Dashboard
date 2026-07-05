"""Native Meteosat SEVIRI Level 1.5 ``.nat`` parser.

Parses the MSG native format directly with numpy and returns the same
SourceRaster-compatible geostationary grid used by GOES/AHI render paths.
The implementation intentionally handles the dashboard's SEVIRI use case:
VIS/IR 3712 px full-disk channels from HRSEVIRI-IODC products.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from rasterio.crs import CRS as RioCRS
from rasterio.transform import from_bounds as rio_from_bounds

from config.satellite_v2_config import seviri_channel_for_source_channel

VISIR_NUM_COLUMNS = 3712
VISIR_NUM_LINES = 3712
VISIR_LINE_BYTES = int(VISIR_NUM_COLUMNS * 1.25)
VISIR_RECORD_BYTES = 4705
VISIR_LINE_DATA_OFFSET = 65
LINE_RECORD_BYTES = 72830

ARCHIVE_HEADER_BYTES = 450400
NO_ARCHIVE_HEADER_BYTES = 445286
ARCHIVE_DATA_HEADER_OFFSET = 5152
NO_ARCHIVE_DATA_HEADER_OFFSET = 38

CHANNEL_INDEX = {
    "VIS006": 0,
    "VIS008": 1,
    "IR_016": 2,
    "IR_039": 3,
    "WV_062": 4,
    "WV_073": 5,
    "IR_087": 6,
    "IR_097": 7,
    "IR_108": 8,
    "IR_120": 9,
    "IR_134": 10,
}

VISIBLE_CHANNELS = frozenset({"VIS006", "VIS008", "IR_016"})

C1 = 1.19104273e-5
C2 = 1.43877523

# Meteosat platform calibration constants for effective radiance -> BT and
# visible-channel solar irradiance. Platform id 322 is Meteosat-9 / MSG2.
SEVIRI_CALIB = {
    321: {
        "VIS006": {"F": 65.2296},
        "VIS008": {"F": 73.0127},
        "IR_016": {"F": 62.3715},
        "IR_039": {"VC": 2567.33, "ALPHA": 0.9956, "BETA": 3.41},
        "WV_062": {"VC": 1598.103, "ALPHA": 0.9962, "BETA": 2.218},
        "WV_073": {"VC": 1362.081, "ALPHA": 0.9991, "BETA": 0.478},
        "IR_087": {"VC": 1149.069, "ALPHA": 0.9996, "BETA": 0.179},
        "IR_097": {"VC": 1034.343, "ALPHA": 0.9999, "BETA": 0.06},
        "IR_108": {"VC": 930.647, "ALPHA": 0.9983, "BETA": 0.625},
        "IR_120": {"VC": 839.66, "ALPHA": 0.9988, "BETA": 0.397},
        "IR_134": {"VC": 752.387, "ALPHA": 0.9981, "BETA": 0.578},
    },
    322: {
        "VIS006": {"F": 65.2065},
        "VIS008": {"F": 73.1869},
        "IR_016": {"F": 61.9923},
        "IR_039": {"VC": 2568.832, "ALPHA": 0.9954, "BETA": 3.438},
        "WV_062": {"VC": 1600.548, "ALPHA": 0.9963, "BETA": 2.185},
        "WV_073": {"VC": 1360.330, "ALPHA": 0.9991, "BETA": 0.47},
        "IR_087": {"VC": 1148.620, "ALPHA": 0.9996, "BETA": 0.179},
        "IR_097": {"VC": 1035.289, "ALPHA": 0.9999, "BETA": 0.056},
        "IR_108": {"VC": 931.7, "ALPHA": 0.9983, "BETA": 0.64},
        "IR_120": {"VC": 836.445, "ALPHA": 0.9988, "BETA": 0.408},
        "IR_134": {"VC": 751.792, "ALPHA": 0.9981, "BETA": 0.561},
    },
    323: {
        "VIS006": {"F": 65.5148},
        "VIS008": {"F": 73.1807},
        "IR_016": {"F": 62.0208},
        "IR_039": {"VC": 2547.771, "ALPHA": 0.9915, "BETA": 2.9002},
        "WV_062": {"VC": 1595.621, "ALPHA": 0.9960, "BETA": 2.0337},
        "WV_073": {"VC": 1360.337, "ALPHA": 0.9991, "BETA": 0.4340},
        "IR_087": {"VC": 1148.130, "ALPHA": 0.9996, "BETA": 0.1714},
        "IR_097": {"VC": 1034.715, "ALPHA": 0.9999, "BETA": 0.0527},
        "IR_108": {"VC": 929.842, "ALPHA": 0.9983, "BETA": 0.6084},
        "IR_120": {"VC": 838.659, "ALPHA": 0.9988, "BETA": 0.3882},
        "IR_134": {"VC": 750.653, "ALPHA": 0.9982, "BETA": 0.5390},
    },
    324: {
        "VIS006": {"F": 65.2656},
        "VIS008": {"F": 73.1692},
        "IR_016": {"F": 61.9416},
        "IR_039": {"VC": 2555.280, "ALPHA": 0.9916, "BETA": 2.9438},
        "WV_062": {"VC": 1596.080, "ALPHA": 0.9959, "BETA": 2.0780},
        "WV_073": {"VC": 1361.748, "ALPHA": 0.9990, "BETA": 0.4929},
        "IR_087": {"VC": 1147.433, "ALPHA": 0.9996, "BETA": 0.1731},
        "IR_097": {"VC": 1034.851, "ALPHA": 0.9998, "BETA": 0.0597},
        "IR_108": {"VC": 931.122, "ALPHA": 0.9983, "BETA": 0.6256},
        "IR_120": {"VC": 839.113, "ALPHA": 0.9988, "BETA": 0.4002},
        "IR_134": {"VC": 748.585, "ALPHA": 0.9981, "BETA": 0.5635},
    },
}


@dataclass(frozen=True)
class SeviriHeader:
    satellite_id: int
    sub_lon: float
    n_lines: int
    n_cols: int
    line_step_km: float
    column_step_km: float
    earth_model: int
    earth_eq_radius_km: float
    earth_polar_radius_km: float
    cal_slopes: np.ndarray
    cal_offsets: np.ndarray
    header_bytes: int
    # 1-based full-disk reference-grid line/column bounds this product's grid
    # occupies. Full-disk products cover the whole 1..3712 range; the Rapid
    # Scan Service is a cropped northern strip (e.g. south=2321, north=3712),
    # so these are needed to place the crop correctly instead of assuming the
    # grid is centered on the sub-satellite point.
    south_line: int
    north_line: int
    east_column: int
    west_column: int


@dataclass(frozen=True)
class SeviriRaster:
    values: np.ndarray
    src_transform: object
    src_crs: object
    header: SeviriHeader
    channel_name: str


def _read_ascii_value(buf: bytes, offset: int) -> str:
    raw = buf[offset + 30 : offset + 80].split(b"\x00", 1)[0]
    return raw.decode("ascii", "replace").strip()


def _has_archive_header(buf: bytes) -> bool:
    return buf.startswith(b"FormatName")


def _read_header(path: str | Path) -> SeviriHeader:
    with open(path, "rb") as handle:
        prefix = handle.read(ARCHIVE_HEADER_BYTES)

    archive = _has_archive_header(prefix)
    header_bytes = ARCHIVE_HEADER_BYTES if archive else NO_ARCHIVE_HEADER_BYTES
    data_off = ARCHIVE_DATA_HEADER_OFFSET if archive else NO_ARCHIVE_DATA_HEADER_OFFSET

    def u1(rel: int) -> int:
        return int(prefix[data_off + rel])

    def be_u2(rel: int) -> int:
        return int(np.frombuffer(prefix, dtype=">u2", count=1, offset=data_off + rel)[0])

    def be_i4(rel: int) -> int:
        return int(np.frombuffer(prefix, dtype=">i4", count=1, offset=data_off + rel)[0])

    def be_f4(rel: int) -> float:
        return float(np.frombuffer(prefix, dtype=">f4", count=1, offset=data_off + rel)[0])

    def be_f8(rel: int) -> float:
        return float(np.frombuffer(prefix, dtype=">f8", count=1, offset=data_off + rel)[0])

    n_lines = VISIR_NUM_LINES
    n_cols = VISIR_NUM_COLUMNS
    south_line = 1
    north_line = VISIR_NUM_LINES
    east_column = 1
    west_column = VISIR_NUM_COLUMNS
    if archive:
        n_lines = int(_read_ascii_value(prefix, 4794))
        n_cols = int(_read_ascii_value(prefix, 4874))
        south_line = int(_read_ascii_value(prefix, 4474))
        north_line = int(_read_ascii_value(prefix, 4554))
        east_column = int(_read_ascii_value(prefix, 4634))
        west_column = int(_read_ascii_value(prefix, 4714))

    slopes = np.empty(12, dtype=np.float64)
    offsets = np.empty(12, dtype=np.float64)
    cal_rel = 392218 - ARCHIVE_DATA_HEADER_OFFSET
    for idx in range(12):
        slopes[idx] = be_f8(cal_rel + idx * 16)
        offsets[idx] = be_f8(cal_rel + idx * 16 + 8)

    earth_eq = be_f8(413298 - ARCHIVE_DATA_HEADER_OFFSET)
    north_polar = be_f8(413306 - ARCHIVE_DATA_HEADER_OFFSET)
    south_polar = be_f8(413314 - ARCHIVE_DATA_HEADER_OFFSET)
    return SeviriHeader(
        satellite_id=be_u2(5153 - ARCHIVE_DATA_HEADER_OFFSET),
        sub_lon=be_f4(392046 - ARCHIVE_DATA_HEADER_OFFSET),
        n_lines=n_lines,
        n_cols=n_cols,
        line_step_km=be_f4(392058 - ARCHIVE_DATA_HEADER_OFFSET),
        column_step_km=be_f4(392062 - ARCHIVE_DATA_HEADER_OFFSET),
        earth_model=u1(413297 - ARCHIVE_DATA_HEADER_OFFSET),
        earth_eq_radius_km=earth_eq,
        earth_polar_radius_km=(north_polar + south_polar) * 0.5,
        cal_slopes=slopes,
        cal_offsets=offsets,
        header_bytes=header_bytes,
        south_line=south_line,
        north_line=north_line,
        east_column=east_column,
        west_column=west_column,
    )


def _normalize_seviri_channel(channel: str) -> str:
    value = str(channel or "").strip().upper()
    if value in CHANNEL_INDEX:
        return value
    return seviri_channel_for_source_channel(channel)


def _unpack_10bit(raw: np.ndarray) -> np.ndarray:
    packed = raw.astype(np.uint16, copy=False)
    out = np.empty((packed.shape[0], VISIR_NUM_COLUMNS), dtype=np.uint16)
    out[:, 0::4] = (packed[:, 0::5] << 2) + (packed[:, 1::5] >> 6)
    out[:, 1::4] = ((packed[:, 1::5] & 0x3F) << 4) + (packed[:, 2::5] >> 4)
    out[:, 2::4] = ((packed[:, 2::5] & 0x0F) << 6) + (packed[:, 3::5] >> 2)
    out[:, 3::4] = ((packed[:, 3::5] & 0x03) << 8) + packed[:, 4::5]
    return out


def _read_channel_counts(path: str | Path, header: SeviriHeader, channel_name: str) -> np.ndarray:
    if header.n_cols != VISIR_NUM_COLUMNS:
        raise ValueError(
            "Only 3712-column SEVIRI VIS/IR grids are supported "
            f"(got {header.n_cols}x{header.n_lines})."
        )
    channel_index = CHANNEL_INDEX[channel_name]
    mm = np.memmap(
        path,
        dtype="u1",
        mode="r",
        offset=header.header_bytes,
        shape=(header.n_lines, LINE_RECORD_BYTES),
    )
    start = channel_index * VISIR_RECORD_BYTES + VISIR_LINE_DATA_OFFSET
    raw = np.asarray(mm[:, start : start + VISIR_LINE_BYTES])
    # MSG native full-disk lines/pixels are stored south-to-north and
    # east-to-west for the SE grid origin. Flip to north-up, west-to-east.
    return _unpack_10bit(raw)[::-1, ::-1]


def _calibrate(counts: np.ndarray, header: SeviriHeader, channel_name: str) -> np.ndarray:
    channel_index = CHANNEL_INDEX[channel_name]
    radiance = (
        counts.astype(np.float32) * np.float32(header.cal_slopes[channel_index])
        + np.float32(header.cal_offsets[channel_index])
    )
    radiance = np.clip(radiance, 0.0, None)
    invalid = counts == 0
    calib = SEVIRI_CALIB.get(header.satellite_id)
    if calib is None or channel_name not in calib:
        raise ValueError(
            f"No SEVIRI calibration constants for satellite {header.satellite_id} "
            f"channel {channel_name}."
        )

    if channel_name in VISIBLE_CHANNELS:
        solar_irradiance = np.float32(calib[channel_name]["F"])
        values = (np.pi * radiance / solar_irradiance).astype(np.float32)
    else:
        info = calib[channel_name]
        vc = np.float32(info["VC"])
        alpha = np.float32(info["ALPHA"])
        beta = np.float32(info["BETA"])
        with np.errstate(divide="ignore", invalid="ignore"):
            effective_t = (C2 * vc) / np.log((C1 * vc**3 / radiance) + 1.0)
            values = ((effective_t - beta) / alpha).astype(np.float32)
        invalid |= (radiance <= 0.0) | ~np.isfinite(values)

    values[invalid] = np.nan
    return values


def _source_georef(header: SeviriHeader) -> tuple[object, object]:
    width = header.n_cols
    height = header.n_lines
    col_step_m = header.column_step_km * 1000.0
    line_step_m = header.line_step_km * 1000.0

    # Full-disk reference grid is centered on the sub-satellite point, with
    # 1-based line/column bounds 1..VISIR_NUM_LINES/COLUMNS. A cropped grid
    # (e.g. Rapid Scan Service) reports its actual reference-grid bounds via
    # south/north_line and east/west_column, so its real position relative to
    # that shared center can be recovered even though the crop itself isn't
    # disk-centered.
    west = (header.west_column - VISIR_NUM_COLUMNS / 2.0) * col_step_m
    east = (header.east_column - VISIR_NUM_COLUMNS / 2.0) * col_step_m
    south = (header.south_line - VISIR_NUM_LINES / 2.0) * line_step_m
    north = (header.north_line - VISIR_NUM_LINES / 2.0) * line_step_m

    src_transform = rio_from_bounds(
        min(west, east),
        south,
        max(west, east),
        north,
        width,
        height,
    )
    perspective_height_m = 35785831.0
    proj4 = (
        f"+proj=geos +h={perspective_height_m:.3f} +lon_0={header.sub_lon} "
        f"+sweep=y +a={header.earth_eq_radius_km * 1000.0:.3f} "
        f"+b={header.earth_polar_radius_km * 1000.0:.3f} +units=m +no_defs"
    )
    return src_transform, RioCRS.from_proj4(proj4)


def load_seviri_raster(path: str | Path, channel: str) -> SeviriRaster:
    """Load one SEVIRI channel from an MSG native ``.nat`` bundle."""
    channel_name = _normalize_seviri_channel(channel)
    header = _read_header(path)
    counts = _read_channel_counts(path, header, channel_name)
    values = _calibrate(counts, header, channel_name)
    src_transform, src_crs = _source_georef(header)
    return SeviriRaster(
        values=values,
        src_transform=src_transform,
        src_crs=src_crs,
        header=header,
        channel_name=channel_name,
    )
