"""Audit-only native FCI window loader. Not imported by the application.

The first prototype bounds inverse-projected destination pixel vertices, adds a
sampling halo, and reads intersecting native strips. Ambiguous geometry uses a
full-native fallback, never a lower-detail array. NetCDF reads retain the existing
process-wide serialization lock. The cache limit accounts for retained arrays,
not all native-library or caller-held memory.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import math
from pathlib import Path
import time

import netCDF4
import numpy as np
from pyproj import Transformer
from rasterio.crs import CRS
from rasterio.transform import Affine, from_bounds

from config.satellite_v2_config import fci_channel_for_source_channel
from satellite_v2.fci_nc import _FCI_NETCDF_ACCESS_LOCK, _calibrate_radiance, _scaled_axis
from satellite_v2.renderer import SourceRaster


@dataclass(frozen=True)
class Grid:
    rows: int
    cols: int
    transform: Affine
    crs: CRS
    strips: tuple
    storage_chunk_bytes: int


def scan_index(paths, source_channels):
    """Read genuine source metadata; do not use audit header JSON to hide cost."""
    native_channels = tuple(dict.fromkeys(fci_channel_for_source_channel(ch) for ch in source_channels))
    rows = {ch: [] for ch in native_channels}
    definitions = {}
    with _FCI_NETCDF_ACCESS_LOCK:
        for path in paths:
            with netCDF4.Dataset(path) as ds:
                group = ds.groups["data"]
                projection = group.variables["mtg_geos_projection"]
                attrs = {k: getattr(projection, k) for k in projection.ncattrs()}
                for ch in native_channels:
                    measured = group.groups[ch].groups["measured"]
                    position = [int(np.asarray(measured.variables[k][:])) for k in
                                ("start_position_row", "end_position_row", "start_position_column", "end_position_column")]
                    first, last, left, right = position
                    assert left == 1 and first <= last
                    variable = measured.variables["effective_radiance"]
                    assert variable.shape == (last - first + 1, right)
                    chunking = variable.chunking()
                    chunk_bytes = (math.prod(chunking) if isinstance(chunking, list) else math.prod(variable.shape)) * variable.dtype.itemsize
                    axes = {axis: {k: getattr(measured.variables[axis], k) for k in measured.variables[axis].ncattrs()}
                            for axis in ("x", "y")}
                    if ch in definitions:
                        assert definitions[ch]["cols"] == right
                        assert definitions[ch]["projection"] == attrs
                    else:
                        definitions[ch] = {"cols": right, "projection": attrs, "axes": axes, "chunk_bytes": 0}
                    definitions[ch]["chunk_bytes"] = max(definitions[ch]["chunk_bytes"], chunk_bytes)
                    rows[ch].append((first - 1, last, Path(path)))
    index = {}
    for ch, strips in rows.items():
        strips.sort()
        assert strips[0][0] == 0
        assert all(a[1] == b[0] for a, b in zip(strips, strips[1:]))
        definition = definitions[ch]
        count_rows, count_cols = strips[-1][1], definition["cols"]
        attrs = definition["projection"]
        height = float(attrs["perspective_point_height"])
        x = -_scaled_axis(definition["axes"]["x"], count_cols) * height
        y = _scaled_axis(definition["axes"]["y"], count_rows)[::-1] * height
        dx, dy = float(np.median(np.diff(x))), abs(float(np.median(np.diff(y))))
        transform = from_bounds(float(x[0] - dx / 2), float(y[-1] - dy / 2),
                                float(x[-1] + dx / 2), float(y[0] + dy / 2), count_cols, count_rows)
        crs = CRS.from_proj4(
            f"+proj=geos +h={height:.3f} +lon_0={float(attrs['longitude_of_projection_origin'])} "
            f"+sweep={attrs.get('sweep_angle_axis', 'y')} +a={float(attrs['semi_major_axis']):.3f} "
            f"+b={float(attrs['semi_minor_axis']):.3f} +units=m +no_defs")
        index[ch] = Grid(count_rows, count_cols, transform, crs, tuple(strips), definition["chunk_bytes"])
    return index


def destination_vertices(crs, z, x_min, y_min, x_max, y_max):
    """Project all destination pixel vertices, not only a few tile corners."""
    width, height = (x_max - x_min + 1) * 256, (y_max - y_min + 1) * 256
    assert width <= 768 and height <= 768, "Prototype geometry allocation is bounded to 3x3"
    x = (x_min + np.arange(width + 1) / 256) / 2**z * 360 - 180
    merc = math.pi * (1 - 2 * (y_min + np.arange(height + 1) / 256) / 2**z)
    y = np.degrees(np.arctan(np.sinh(merc)))
    lon, lat = np.meshgrid(x, y)
    return Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform(lon, lat)


def selected_window(grid, xy):
    """Integer native window with a derivative-scaled bilinear halo."""
    x, y = xy
    cols = (x - grid.transform.c) / grid.transform.a
    rows = (y - grid.transform.f) / grid.transform.e
    finite = np.isfinite(cols) & np.isfinite(rows)
    if not finite.any():
        return (0, 0, grid.cols, grid.rows), "full_native_no_finite_vertex", 0
    # Nonlinear limbs require separate quality evidence. Keep this first version
    # conservative there instead of assuming finite edge samples fully bound it.
    if not finite.all():
        return (0, 0, grid.cols, grid.rows), "full_native_partial_projection", 0
    delta = max(float(np.abs(np.diff(v, axis=axis)).max())
                for v in (cols, rows) for axis in (0, 1))
    halo = max(4, math.ceil(delta * 4) + 2)
    x0 = max(0, math.floor(float(cols.min())) - halo)
    x1 = min(grid.cols, math.ceil(float(cols.max())) + halo)
    y0 = max(0, math.floor(float(rows.min())) - halo)
    y1 = min(grid.rows, math.ceil(float(rows.max())) + halo)
    if x1 <= x0 or y1 <= y0:
        return (0, 0, grid.cols, grid.rows), "full_native_empty_bound", halo
    return (x0, y0, x1, y1), "window", halo


class WindowLoader:
    def __init__(self, paths, source_channels, cache_bytes=64 * 1024**2):
        self.paths = tuple(Path(p) for p in paths)
        self.signature = tuple((str(p.resolve()), p.stat().st_size, p.stat().st_mtime_ns) for p in self.paths)
        started = time.perf_counter()
        self.index = scan_index(self.paths, source_channels)
        self.index_seconds = time.perf_counter() - started
        self.cache_limit = cache_bytes
        self.cache = OrderedDict()
        self.cache_bytes = 0

    def load(self, source_channels, z, x_min, y_min, x_max, y_max):
        grids = self.index
        geometry = destination_vertices(next(iter(grids.values())).crs, z, x_min, y_min, x_max, y_max)
        result, records = {}, []
        native_results = {}
        for source_channel in source_channels:
            native = fci_channel_for_source_channel(source_channel)
            if native in native_results:
                result[source_channel] = native_results[native]
                continue
            grid = grids[native]
            window, mode, halo = selected_window(grid, geometry)
            x0, y0, x1, y1 = window
            key = (self.signature, native, window)
            row = {"native_channel": native, "window": list(window), "mode": mode, "halo": halo,
                   "full_array_bytes": grid.rows * grid.cols * 4,
                   "selected_array_bytes": (y1 - y0) * (x1 - x0) * 4, "cache_hit": key in self.cache,
                   "strips_read": 0, "decompressed_storage_bytes_estimate": 0}
            if key in self.cache:
                raster = self.cache.pop(key)
                self.cache[key] = raster
            else:
                # Storage rows run south to north; source raster rows run north to south.
                raw_y0, raw_y1 = grid.rows - y1, grid.rows - y0
                values = np.full((y1 - y0, x1 - x0), np.nan, dtype=np.float32)
                with _FCI_NETCDF_ACCESS_LOCK:
                    for start, end, path in grid.strips:
                        lo, hi = max(start, raw_y0), min(end, raw_y1)
                        if hi <= lo:
                            continue
                        with netCDF4.Dataset(path) as ds:
                            measured = ds.groups["data"].groups[native].groups["measured"]
                            variable = measured.variables["effective_radiance"]
                            radiance = np.ma.filled(variable[lo - start:hi - start, x0:x1], np.nan).astype(np.float32)
                            calibrated = _calibrate_radiance(radiance, measured, native)
                            values[lo - raw_y0:hi - raw_y0] = calibrated
                            row["strips_read"] += 1
                            row["decompressed_storage_bytes_estimate"] += grid.storage_chunk_bytes
                raster = SourceRaster(values[::-1], grid.transform * Affine.translation(x0, y0), grid.crs)
                if values.nbytes <= self.cache_limit:
                    while self.cache and self.cache_bytes + values.nbytes > self.cache_limit:
                        _, old = self.cache.popitem(last=False)
                        self.cache_bytes -= old.cmi.nbytes
                    self.cache[key] = raster
                    self.cache_bytes += values.nbytes
            assert self.cache_bytes <= self.cache_limit
            native_results[native] = raster
            result[source_channel] = raster
            records.append(row)
        return result, {"channels": records, "cache_bytes": self.cache_bytes, "cache_limit": self.cache_limit}
