"""Native Himawari AHI HSD (Himawari Standard Data) segment parser.

Parses JMA HSD binary segments directly (header blocks 1/2/3/5/7 plus the
uint16 data section) with numpy only — no satpy/pyresample/dask. Output is a
calibrated, north-up grid with a rasterio geostationary transform and CRS
matching the SourceRaster contract in satellite_v2.renderer, so AHI frames
reuse the existing GOES GDAL-warp tile path.

Format reference: JMA "Himawari Standard Data User's Guide". All header and
data values are little-endian. Blocks 8-11 are variable length and unused
here; the data section offset comes from block 1's total_header_length.

Calibration semantics match GOES CMI so downstream colorize/composites work
unchanged: bands 1-6 produce reflectance factor (0-1), bands 7-16 produce
brightness temperature in kelvin via the inverse Planck function with JMA's
quadratic correction, using the physical constants stored in block 5.
"""

from __future__ import annotations

import bz2
import math
import struct
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np
from rasterio.crs import CRS as RioCRS
from rasterio.transform import from_bounds as rio_from_bounds

from config.satellite_v2_config import SATELLITE_V2_AHI_MAX_GRID

_VNIR_BANDS = frozenset(range(1, 7))
_AHI_SEGMENT_WORKERS = 4


@dataclass(frozen=True)
class AhiHeader:
    """Fields from HSD header blocks 1, 2, 3, 5, and 7."""

    observation_area: str
    total_header_length: int
    n_cols: int
    n_lines: int
    compression_flag: int
    sub_lon: float
    cfac: int
    lfac: int
    coff: float
    loff: float
    distance_km: float
    earth_eq_radius_km: float
    earth_polar_radius_km: float
    band_number: int
    central_wavelength_um: float
    count_error: int
    count_outside: int
    rad_gain: float
    rad_offset: float
    albedo_coeff: float
    bt_c0: float
    bt_c1: float
    bt_c2: float
    speed_of_light: float
    planck_constant: float
    boltzmann_constant: float
    total_segments: int
    segment_number: int
    first_line: int


@dataclass(frozen=True)
class AhiRaster:
    """Calibrated north-up AHI grid plus geostationary georeferencing.

    Field names mirror satellite_v2.renderer.SourceRaster so callers can
    construct one directly from these values.
    """

    values: np.ndarray  # float32 (rows, cols)
    src_transform: object  # rasterio Affine in geostationary metres
    src_crs: object  # rasterio CRS (+proj=geos)
    header: AhiHeader  # header of the northernmost parsed segment
    stride: int


def read_hsd_bytes(path: str | Path) -> bytes:
    """Read an HSD segment file, transparently decompressing bz2."""
    raw = Path(path).read_bytes()
    if raw[:3] == b"BZh":
        raw = bz2.decompress(raw)
    return raw


def parse_ahi_header(buf: bytes) -> AhiHeader:
    """Walk header blocks 1..7 and extract the fields this parser needs."""
    fields: dict[str, object] = {}
    pos = 0
    while True:
        if pos + 3 > len(buf):
            raise ValueError("Truncated AHI HSD header.")
        block_no = buf[pos]
        block_len = struct.unpack_from("<H", buf, pos + 1)[0]
        if block_len <= 0 or block_no < 1 or block_no > 7:
            raise ValueError(
                f"Unexpected AHI HSD header block {block_no} (len {block_len})."
            )
        if block_no == 1:
            fields["observation_area"] = (
                buf[pos + 38 : pos + 42].decode("ascii", "replace").strip()
            )
            fields["total_header_length"] = struct.unpack_from("<I", buf, pos + 70)[0]
        elif block_no == 2:
            bits_per_pixel, n_cols, n_lines = struct.unpack_from("<HHH", buf, pos + 3)
            if bits_per_pixel != 16:
                raise ValueError(
                    f"Unsupported AHI HSD bit depth: {bits_per_pixel} (expected 16)."
                )
            fields["n_cols"] = n_cols
            fields["n_lines"] = n_lines
            fields["compression_flag"] = buf[pos + 9]
        elif block_no == 3:
            fields["sub_lon"] = struct.unpack_from("<d", buf, pos + 3)[0]
            fields["cfac"], fields["lfac"] = struct.unpack_from("<II", buf, pos + 11)
            fields["coff"], fields["loff"] = struct.unpack_from("<ff", buf, pos + 19)
            (
                fields["distance_km"],
                fields["earth_eq_radius_km"],
                fields["earth_polar_radius_km"],
            ) = struct.unpack_from("<ddd", buf, pos + 27)
        elif block_no == 5:
            band = struct.unpack_from("<H", buf, pos + 3)[0]
            fields["band_number"] = band
            fields["central_wavelength_um"] = struct.unpack_from("<d", buf, pos + 5)[0]
            fields["count_error"], fields["count_outside"] = struct.unpack_from(
                "<HH", buf, pos + 15
            )
            fields["rad_gain"], fields["rad_offset"] = struct.unpack_from(
                "<dd", buf, pos + 19
            )
            if band in _VNIR_BANDS:
                fields["albedo_coeff"] = struct.unpack_from("<d", buf, pos + 35)[0]
                fields["bt_c0"] = fields["bt_c1"] = fields["bt_c2"] = 0.0
                fields["speed_of_light"] = 0.0
                fields["planck_constant"] = 0.0
                fields["boltzmann_constant"] = 0.0
            else:
                (
                    fields["bt_c0"],
                    fields["bt_c1"],
                    fields["bt_c2"],
                ) = struct.unpack_from("<ddd", buf, pos + 35)
                (
                    fields["speed_of_light"],
                    fields["planck_constant"],
                    fields["boltzmann_constant"],
                ) = struct.unpack_from("<ddd", buf, pos + 83)
                fields["albedo_coeff"] = 0.0
        elif block_no == 7:
            fields["total_segments"] = buf[pos + 3]
            fields["segment_number"] = buf[pos + 4]
            fields["first_line"] = struct.unpack_from("<H", buf, pos + 5)[0]
            break
        pos += block_len
    return AhiHeader(**fields)  # type: ignore[arg-type]


def segment_counts(buf: bytes, header: AhiHeader) -> np.ndarray:
    """Return the segment's raw uint16 count grid (n_lines, n_cols)."""
    if header.compression_flag != 0:
        raise ValueError(
            "AHI HSD internal data compression is not supported "
            f"(compression_flag={header.compression_flag})."
        )
    n = header.n_cols * header.n_lines
    expected_end = header.total_header_length + 2 * n
    if len(buf) < expected_end:
        raise ValueError(
            f"AHI HSD data section truncated: have {len(buf)} bytes, "
            f"need {expected_end}."
        )
    counts = np.frombuffer(
        buf, dtype="<u2", count=n, offset=header.total_header_length
    )
    return counts.reshape(header.n_lines, header.n_cols)


def calibrate(counts: np.ndarray, header: AhiHeader) -> np.ndarray:
    """Counts → reflectance factor (bands 1-6) or brightness temperature K."""
    radiance = (
        header.rad_gain * counts.astype(np.float32) + header.rad_offset
    )  # W/(m2 sr µm)
    invalid = (counts == header.count_error) | (counts == header.count_outside)

    if header.band_number in _VNIR_BANDS:
        values = (radiance * header.albedo_coeff).astype(np.float32)
    else:
        wavelength_m = header.central_wavelength_um * 1.0e-6
        planck_a = (header.planck_constant * header.speed_of_light) / (
            header.boltzmann_constant * wavelength_m
        )
        planck_b_num = 2.0 * header.planck_constant * header.speed_of_light**2
        rad_per_m = radiance.astype(np.float64) * 1.0e6
        with np.errstate(divide="ignore", invalid="ignore"):
            effective_t = planck_a / np.log(
                planck_b_num / (wavelength_m**5 * rad_per_m) + 1.0
            )
            values = (
                header.bt_c0
                + header.bt_c1 * effective_t
                + header.bt_c2 * effective_t**2
            ).astype(np.float32)
        invalid |= (radiance <= 0.0) | ~np.isfinite(values)

    values[invalid] = np.nan
    return values


def load_ahi_raster(
    segment_files: Sequence[str | Path],
    max_grid: int = SATELLITE_V2_AHI_MAX_GRID,
) -> AhiRaster:
    """Parse, calibrate, decimate, and stitch HSD segments into one grid."""
    if not segment_files:
        raise ValueError("No AHI HSD segment files given.")

    paths = [Path(path) for path in segment_files]
    first_buf = read_hsd_bytes(paths[0])
    first_header = parse_ahi_header(first_buf)
    stride = 1
    while math.ceil(first_header.n_cols / stride) > max(1, int(max_grid)):
        stride *= 2

    def _validate_header(header: AhiHeader) -> None:
        if (
            header.band_number != first_header.band_number
            or header.n_cols != first_header.n_cols
            or header.total_segments != first_header.total_segments
        ):
            raise ValueError(
                "AHI HSD segments are from mismatched bands or grids."
            )
    offset = stride // 2

    def _calibrated_segment(
        header: AhiHeader, buf: bytes
    ) -> tuple[AhiHeader, int, np.ndarray]:
        _validate_header(header)
        counts = segment_counts(buf, header)
        start_row = header.first_line - 1
        first_sampled = start_row + ((offset - start_row) % stride)
        local_first = first_sampled - start_row
        values = calibrate(
            counts[local_first::stride, offset::stride], header
        )
        return header, first_sampled, values

    segments = [_calibrated_segment(first_header, first_buf)]
    del first_buf

    def _load_segment(path: Path) -> tuple[AhiHeader, int, np.ndarray]:
        buf = read_hsd_bytes(path)
        header = parse_ahi_header(buf)
        return _calibrated_segment(header, buf)

    if len(paths) > 1:
        worker_count = min(_AHI_SEGMENT_WORKERS, len(paths) - 1)
        with ThreadPoolExecutor(max_workers=worker_count) as pool:
            futures = [pool.submit(_load_segment, path) for path in paths[1:]]
            for future in as_completed(futures):
                segments.append(future.result())

    segments.sort(key=lambda item: item[0].first_line)
    ref = segments[0][0]
    total_lines = max(h.first_line + h.n_lines - 1 for h, _, _ in segments)

    out_cols = len(range(offset, ref.n_cols, stride))
    out_rows = len(range(offset, total_lines, stride))
    values = np.full((out_rows, out_cols), np.nan, dtype=np.float32)
    for _, first_sampled, calibrated in segments:
        row0 = (first_sampled - offset) // stride
        values[row0 : row0 + calibrated.shape[0], :] = calibrated

    # --- geostationary georeferencing from block 3 fixed-grid scaling ---
    # Column c / line l (1-based full-grid) → scan angle (degrees) →
    # geostationary metres at perspective height. Line numbers increase
    # southward while +proj=geos y increases northward, hence the negation.
    height_m = (ref.distance_km - ref.earth_eq_radius_km) * 1000.0
    deg_per_col = 65536.0 / ref.cfac
    deg_per_line = 65536.0 / ref.lfac

    # --- mask deep-space pixels ---
    # JMA leaves instrument noise counts (~60-165 K after calibration) in
    # off-Earth pixels instead of flagging them, unlike GOES CMI which NaNs
    # them. Mask by the geostationary visibility condition (GOES PUG /
    # CGMS ray-ellipsoid discriminant) so the warp never samples noise at
    # the limb.
    col_centres = offset + 1 + stride * np.arange(out_cols, dtype=np.float64)
    row_centres = offset + 1 + stride * np.arange(out_rows, dtype=np.float64)
    scan_x = np.radians((col_centres - ref.coff) * deg_per_col)
    scan_y = np.radians((row_centres - ref.loff) * deg_per_line)
    rs_m = ref.distance_km * 1000.0
    req_m = ref.earth_eq_radius_km * 1000.0
    rpol_m = ref.earth_polar_radius_km * 1000.0
    sin2_x = (np.sin(scan_x) ** 2).astype(np.float32)[np.newaxis, :]
    cos2_x = (np.cos(scan_x) ** 2).astype(np.float32)[np.newaxis, :]
    sin2_y = (np.sin(scan_y) ** 2).astype(np.float32)[:, np.newaxis]
    cos2_y = (np.cos(scan_y) ** 2).astype(np.float32)[:, np.newaxis]
    quad_a = sin2_x + cos2_x * (cos2_y + (req_m**2 / rpol_m**2) * sin2_y)
    on_earth = rs_m**2 * cos2_x * cos2_y >= quad_a * (rs_m**2 - req_m**2)
    values[~on_earth] = np.nan

    def _x_m(col: float) -> float:
        return math.radians((col - ref.coff) * deg_per_col) * height_m

    def _y_m(line: float) -> float:
        return -math.radians((line - ref.loff) * deg_per_line) * height_m

    c_first = float(offset + 1)
    c_last = float(offset + 1 + (out_cols - 1) * stride)
    l_first = float(offset + 1)
    l_last = float(offset + 1 + (out_rows - 1) * stride)
    x_first, x_last = _x_m(c_first), _x_m(c_last)
    y_first, y_last = _y_m(l_first), _y_m(l_last)

    x_half = (x_last - x_first) / (2 * (out_cols - 1))
    y_half = (y_first - y_last) / (2 * (out_rows - 1))
    src_transform = rio_from_bounds(
        x_first - x_half,
        y_last - y_half,
        x_last + x_half,
        y_first + y_half,
        out_cols,
        out_rows,
    )
    proj4 = (
        f"+proj=geos +h={height_m:.3f} +lon_0={ref.sub_lon} +sweep=y "
        f"+a={ref.earth_eq_radius_km * 1000.0:.3f} "
        f"+b={ref.earth_polar_radius_km * 1000.0:.3f} +units=m +no_defs"
    )
    src_crs = RioCRS.from_proj4(proj4)

    return AhiRaster(
        values=values,
        src_transform=src_transform,
        src_crs=src_crs,
        header=ref,
        stride=stride,
    )
