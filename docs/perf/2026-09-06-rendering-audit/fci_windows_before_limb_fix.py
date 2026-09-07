"""Native FCI source windows, byte-bounded reuse, and render admission.

M12 renderers are lightweight until the destination canvas is known. All native
I/O retains the existing NetCDF lock; one FCI render owns this process's working
arrays at a time. Cache eviction never substitutes a lower-resolution source.
"""

from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import math
from pathlib import Path

import netCDF4
import numpy as np
import psutil
from pyproj import Transformer
from rasterio.crs import CRS
from rasterio.transform import Affine, from_bounds

from app_core.render_budget import _ByteBudget, satellite_render_slot
from config.satellite_v2_config import (
    SATELLITE_V2_FCI_WINDOW_CACHE_MB,
    fci_channel_for_source_channel,
)
from satellite_v2.fci_nc import _FCI_NETCDF_ACCESS_LOCK, _calibrate_radiance, _scaled_axis


_MIB = 1024**2
_OWNER = _ByteBudget(1)
_CONTEXT = ContextVar("fci_render_context", default=None)
_FRAMES = OrderedDict()
_ARRAYS = OrderedDict()
_ARRAY_BYTES = 0


class FciRenderCancelled(RuntimeError):
    """The request lost ownership or native-quality work needs more memory."""


@contextmanager
def render_context(should_continue=None):
    state = {"should_continue": should_continue, "estimated_memory_bytes": 0}
    token = _CONTEXT.set(state)
    try:
        yield state
    finally:
        _CONTEXT.reset(token)


@dataclass(frozen=True)
class Grid:
    rows: int
    cols: int
    transform: Affine
    crs: CRS
    strips: tuple
    storage_bytes: int


def _signature(paths):
    return tuple((str(path.resolve()), stat.st_size, stat.st_mtime_ns)
                 for path in paths for stat in (path.stat(),))


def _metadata(path, natives):
    result = {}
    with _FCI_NETCDF_ACCESS_LOCK, netCDF4.Dataset(path) as ds:
        data = ds.groups["data"]
        projection = data.variables["mtg_geos_projection"]
        attrs = {key: getattr(projection, key) for key in projection.ncattrs()}
        for native in natives:
            measured = data.groups[native].groups["measured"]
            first, last, left, right = (int(np.asarray(measured.variables[key][:])) for key in
                                       ("start_position_row", "end_position_row", "start_position_column", "end_position_column"))
            variable = measured.variables["effective_radiance"]
            if left != 1 or first < 1 or last < first or variable.shape != (last - first + 1, right):
                raise ValueError(f"Invalid FCI strip geometry: {path}")
            axes = {axis: {key: getattr(measured.variables[axis], key) for key in ("scale_factor", "add_offset")}
                    for axis in ("x", "y")}
            chunks = variable.chunking()
            # A conservative whole-strip bound also covers contiguous storage.
            storage = max(math.prod(variable.shape), math.prod(chunks) if isinstance(chunks, list) else 0) * variable.dtype.itemsize
            result[native] = (first - 1, last, right, attrs, axes, storage)
    return result


def _grid(first, last, strips=(), storage_bytes=0):
    start, _, cols, attrs, axes, storage = first
    _, rows, end_cols, end_attrs, end_axes, end_storage = last
    if start != 0 or not 2 <= rows <= 22272 or not 2 <= cols <= 22272 or cols != end_cols or attrs != end_attrs or axes != end_axes:
        raise ValueError("Inconsistent FCI native grid endpoints")
    height = float(attrs["perspective_point_height"])
    x = -_scaled_axis(axes["x"], cols) * height
    y = _scaled_axis(axes["y"], rows)[::-1] * height
    dx, dy = float(np.median(np.diff(x))), abs(float(np.median(np.diff(y))))
    if not np.isfinite([dx, dy]).all() or dx <= 0 or dy <= 0:
        raise ValueError("Invalid FCI native axis spacing")
    transform = from_bounds(x[0] - dx / 2, y[-1] - dy / 2, x[-1] + dx / 2, y[0] + dy / 2, cols, rows)
    crs = CRS.from_proj4(
        f"+proj=geos +h={height:.3f} +lon_0={float(attrs['longitude_of_projection_origin'])} "
        f"+sweep={attrs.get('sweep_angle_axis', 'y')} +a={float(attrs['semi_major_axis']):.3f} "
        f"+b={float(attrs['semi_minor_axis']):.3f} +units=m +no_defs")
    return Grid(rows, cols, transform, crs, tuple(strips), max(storage, end_storage, storage_bytes))


class Frame:
    def __init__(self, paths, signature):
        self.paths = paths
        self.signature = signature
        self.grids = {}
        self.plans = OrderedDict()

    def grids_for(self, natives, complete=False):
        missing = [ch for ch in natives if ch not in self.grids or (complete and not self.grids[ch].strips)]
        if missing:
            if complete:
                metadata = [(path, _metadata(path, missing)) for path in self.paths]
                for ch in missing:
                    ordered = sorted((values[ch][0], values[ch][1], path, values[ch]) for path, values in metadata)
                    if any(a[1] != b[0] for a, b in zip(ordered, ordered[1:])):
                        raise ValueError("FCI source strips contain a gap or overlap")
                    first, last = ordered[0][3], ordered[-1][3]
                    for _, _, _, value in ordered:
                        if value[2:5] != first[2:5]:
                            raise ValueError("FCI source strips disagree on projection or axes")
                    self.grids[ch] = _grid(first, last, [(a, b, path) for a, b, path, _ in ordered],
                                           max(value[5] for _, _, _, value in ordered))
            else:
                first = _metadata(self.paths[0], missing)
                last = first if len(self.paths) == 1 else _metadata(self.paths[-1], missing)
                for ch in missing:
                    self.grids[ch] = _grid(first[ch], last[ch])
        return {ch: self.grids[ch] for ch in natives}

    def plan(self, natives, target, tile_size):
        key = (natives, target, tile_size)
        if key in self.plans:
            result = self.plans.pop(key)
            self.plans[key] = result
            return result
        grids = self.grids_for(natives)
        crs = next(iter(grids.values())).crs
        if any(grid.crs != crs for grid in grids.values()):
            raise ValueError("FCI channels disagree on projection")
        z, x0, y0, x1, y1 = target
        width, height = (x1 - x0 + 1) * tile_size, (y1 - y0 + 1) * tile_size
        if width <= 0 or height <= 0 or width > 1792 or height > 1792:
            raise ValueError("FCI canvases must be bounded to at most 1792 pixels per axis")

        def project(corners):
            px = np.array([0, width]) if corners else np.arange(width + 1)
            py = np.array([0, height]) if corners else np.arange(height + 1)
            lon = (x0 + px / tile_size) / 2**z * 360 - 180
            lat = np.degrees(np.arctan(np.sinh(np.pi * (1 - 2 * (y0 + py / tile_size) / 2**z))))
            return Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform(*np.meshgrid(lon, lat))

        corners = project(True)
        full = not all(np.isfinite(value).all() for value in corners)
        windows = {}
        if not full:
            x, y = project(False)
            full = not (np.isfinite(x).all() and np.isfinite(y).all())
            if not full:
                for ch, grid in grids.items():
                    cols = (x - grid.transform.c) / grid.transform.a
                    rows = (y - grid.transform.f) / grid.transform.e
                    delta = max(float(np.abs(np.diff(value, axis=axis)).max()) for value in (cols, rows) for axis in (0, 1))
                    halo = max(4, math.ceil(delta * 4) + 2)
                    window = (max(0, math.floor(cols.min()) - halo), max(0, math.floor(rows.min()) - halo),
                              min(grid.cols, math.ceil(cols.max()) + halo), min(grid.rows, math.ceil(rows.max()) + halo))
                    if window[2] <= window[0] or window[3] <= window[1]:
                        full = True
                        break
                    windows[ch] = window
        if full:
            windows = {ch: (0, 0, grid.cols, grid.rows) for ch, grid in grids.items()}
        else:
            grids = self.grids_for(natives, complete=True)
        result = (grids, windows, full)
        self.plans[key] = result
        while len(self.plans) > 8:
            self.plans.popitem(last=False)
        return result


def cache_limit_bytes(memory=None):
    memory = memory or psutil.virtual_memory()
    return max(0, min(SATELLITE_V2_FCI_WINDOW_CACHE_MB * _MIB, memory.total // 128, memory.available // 32))


def _trim(limit):
    global _ARRAY_BYTES
    while _ARRAYS and _ARRAY_BYTES > limit:
        _, raster = _ARRAYS.popitem(last=False)
        _ARRAY_BYTES -= raster.cmi.nbytes


def _put(key, raster, limit):
    global _ARRAY_BYTES
    if raster.cmi.nbytes > limit:
        return
    old = _ARRAYS.pop(key, None)
    if old is not None:
        _ARRAY_BYTES -= old.cmi.nbytes
    _ARRAYS[key] = raster
    _ARRAY_BYTES += raster.cmi.nbytes
    _trim(limit)


def estimate_working_bytes(grids, windows, pixels, source_count):
    selected = sum((x1 - x0) * (y1 - y0) * 4 for x0, y0, x1, y1 in windows.values())
    # Caller-held sources plus native/GDAL copies; packed/float/mask/calibration
    # intermediates for the largest strip; destination, palette and warp buffers.
    strip = max(grid.storage_bytes for grid in grids.values())
    return 2 * selected + 12 * strip + pixels * (32 * source_count + 128) + 128 * _MIB


def _load(frame, natives, grids, windows, full, limit):
    from satellite_v2.renderer import SourceRaster, _load_fci_source_rasters

    result, missing = {}, []
    keys = {ch: (frame.signature, ch, windows[ch]) for ch in natives}
    for ch, key in keys.items():
        if key in _ARRAYS:
            result[ch] = _ARRAYS.pop(key)
            _ARRAYS[key] = result[ch]
        else:
            missing.append(ch)
    if full and missing:
        cap = max(max(grids[ch].rows, grids[ch].cols) for ch in missing)
        result.update(_load_fci_source_rasters(frame.paths[0], missing, max_grid=cap))
        for ch in missing:
            if result[ch].cmi.shape != (grids[ch].rows, grids[ch].cols):
                raise ValueError("FCI full-native fallback dimensions changed")
    elif missing:
        pending = {}
        for ch in missing:
            grid = grids[ch]
            x0, y0, x1, y1 = windows[ch]
            raw0, raw1 = grid.rows - y1, grid.rows - y0
            selections = {path: (start, max(start, raw0), min(end, raw1)) for start, end, path in grid.strips
                          if min(end, raw1) > max(start, raw0)}
            pending[ch] = (np.full((y1 - y0, x1 - x0), np.nan, dtype=np.float32), raw0, selections)
        with _FCI_NETCDF_ACCESS_LOCK:
            for path in frame.paths:
                selected = [ch for ch in missing if path in pending[ch][2]]
                if not selected:
                    continue
                with netCDF4.Dataset(path) as ds:
                    for ch in selected:
                        values, raw0, selections = pending[ch]
                        start, lo, hi = selections[path]
                        x0, _, x1, _ = windows[ch]
                        measured = ds.groups["data"].groups[ch].groups["measured"]
                        radiance = np.ma.filled(measured.variables["effective_radiance"][lo - start:hi - start, x0:x1], np.nan).astype(np.float32)
                        values[lo - raw0:hi - raw0] = _calibrate_radiance(radiance, measured, ch)
        for ch, (values, _, _) in pending.items():
            x0, y0, _, _ = windows[ch]
            result[ch] = SourceRaster(values[::-1], grids[ch].transform * Affine.translation(x0, y0), grids[ch].crs)
    if _signature(frame.paths) != frame.signature:
        raise ValueError("FCI source changed during native read")
    for ch in missing:
        _put(keys[ch], result[ch], limit)
    return result


def render_native_canvas(renderer, target, tile_size):
    from satellite_v2.renderer import SatelliteTileRenderer, _is_fci_chunk_file

    global _ARRAY_BYTES
    state = _CONTEXT.get() or {}
    should_continue = state.get("should_continue")
    acquired, weight = _OWNER.acquire(1, should_continue=should_continue)
    if not acquired:
        raise FciRenderCancelled("M12 render ownership ended")
    try:
        sources = tuple(renderer.source_files)
        natives = tuple(dict.fromkeys(fci_channel_for_source_channel(ch) for ch in sources))
        parents = {path.parent.resolve() for path in renderer.source_files.values()}
        if len(parents) != 1:
            raise ValueError("FCI product channels must share one source bundle")
        paths = tuple(sorted(path for path in next(iter(parents)).iterdir() if _is_fci_chunk_file(path)))
        if not paths:
            raise ValueError("No FCI body chunks found")
        signature = _signature(paths)
        # Evict superseded bundle identities before reusing any metadata/arrays.
        for old in list(_FRAMES):
            if Path(old[0][0]).parent == paths[0].parent and old != signature:
                _FRAMES.pop(old)
        for key in list(_ARRAYS):
            if key[0] not in _FRAMES:
                _ARRAY_BYTES -= _ARRAYS.pop(key).cmi.nbytes
        frame = _FRAMES.pop(signature, None) or Frame(paths, signature)
        _FRAMES[signature] = frame
        while len(_FRAMES) > 4:
            _FRAMES.popitem(last=False)
        memory = psutil.virtual_memory()
        limit = cache_limit_bytes(memory)
        _trim(limit)
        headroom = min(2 * 1024**3, max(512 * _MIB, memory.total // 8))
        # Bound the inverse-projection arrays before constructing the plan.
        vertices = ((target[3] - target[1] + 1) * tile_size + 1) * ((target[4] - target[2] + 1) * tile_size + 1)
        if memory.available < headroom + vertices * 96:
            _trim(0)
            if psutil.virtual_memory().available < headroom + vertices * 96:
                raise FciRenderCancelled("M12 geometry planning deferred for available memory")
        grids, windows, full = frame.plan(natives, target, tile_size)
        pixels = (target[3] - target[1] + 1) * (target[4] - target[2] + 1) * tile_size**2
        estimate = estimate_working_bytes(grids, windows, pixels, len(sources))
        state["estimated_memory_bytes"] = estimate
        # Cached arrays and their caller-held references are included separately
        # from prospective allocations. Only one M12 caller owns arrays here.
        with satellite_render_slot(estimate + _ARRAY_BYTES, should_continue=should_continue) as admitted:
            if not admitted:
                raise FciRenderCancelled("M12 render ownership ended")
            memory = psutil.virtual_memory()
            headroom = min(2 * 1024**3, max(512 * _MIB, memory.total // 8))
            if memory.available < estimate + headroom:
                _trim(0)
                memory = psutil.virtual_memory()
                if memory.available < estimate + headroom:
                    raise FciRenderCancelled("M12 native render deferred for available memory")
            if should_continue is not None and not should_continue():
                raise FciRenderCancelled("M12 render ownership ended")
            native = _load(frame, natives, grids, windows, full, cache_limit_bytes(memory))
            rasters = {ch: native[fci_channel_for_source_channel(ch)] for ch in sources}
            concrete = SatelliteTileRenderer(renderer.product_key, rasters, renderer.source_files, "FCI")
            image = concrete.render_zoom_canvas(*target, tile_size=tile_size)
            if _signature(paths) != signature or (should_continue is not None and not should_continue()):
                image.close()
                raise FciRenderCancelled("M12 source or render ownership changed")
            return image
    finally:
        _OWNER.release(weight)
