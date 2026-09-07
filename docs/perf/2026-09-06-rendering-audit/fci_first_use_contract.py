"""Offline-only FCI acquisition model; never imported by the application.

The trusted index mode is an explicit oracle experiment, not cold discovery.
No sockets, NetCDF reads, background threads or application caches live here.
"""

from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import PureWindowsPath
from threading import RLock


class Pending(RuntimeError):
    pass


@dataclass(frozen=True)
class Strip:
    channel: str
    start: int
    end: int
    cols: int
    geometry: str


@dataclass(frozen=True)
class File:
    name: str
    digest: str
    size: int
    strips: tuple[Strip, ...]


@dataclass(frozen=True)
class Index:
    entries: tuple[tuple[str, tuple[Strip, ...]], ...]

    def __post_init__(self):
        names = [name for name, _ in self.entries]
        if not names or len(names) != len(set(names)):
            raise ValueError("Duplicate or missing expected entries")
        channels = {s.channel for s in self.entries[0][1]}
        if not channels:
            raise ValueError("No requested native channels")
        for _, strips in self.entries:
            if len(strips) != len(channels) or {s.channel for s in strips} != channels:
                raise ValueError("Missing or duplicate composite channel")
        for channel in channels:
            strips = sorted((s for _, row in self.entries for s in row if s.channel == channel),
                            key=lambda s: s.start)
            next_row = 0
            for s in strips:
                if s.start != next_row or s.end <= s.start or s.cols <= 0:
                    raise ValueError("Native coverage gap or overlap")
                if (s.cols, s.geometry) != (strips[0].cols, strips[0].geometry):
                    raise ValueError("Native projection or axis disagreement")
                next_row = s.end

    def dependencies(self, windows, *, offdisk=False):
        if not windows and not offdisk:
            raise ValueError("Empty windows require a geometric off-disk proof")
        result = set()
        for channel, (x0, y0, x1, y1) in windows.items():
            strips = [(name, s) for name, row in self.entries for s in row if s.channel == channel]
            if not strips:
                raise ValueError("Unknown native channel")
            rows = max(s.end for _, s in strips)
            if not (0 <= x0 < x1 <= strips[0][1].cols and 0 <= y0 < y1 <= rows):
                raise ValueError("Window outside native grid")
            lo, hi = rows - y1, rows - y0
            result.update(name for name, s in strips if s.start < hi and s.end > lo)
        return frozenset(result)


@dataclass(frozen=True)
class Snapshot:
    source_revision: str
    index: Index
    files: tuple[File, ...]
    windows: tuple
    offdisk: bool


class Bundle:
    def __init__(self, revision, expected, trusted_index=None):
        expected = tuple(expected)
        if not revision or not expected or len(expected) != len(set(expected)):
            raise ValueError("Missing identity or duplicate inventory")
        for name in expected:
            if not name or PureWindowsPath(name).name != name or name in {".", ".."} or ":" in name:
                raise ValueError("Unsafe source basename")
        if trusted_index is not None and set(dict(trusted_index.entries)) != set(expected):
            raise ValueError("Index belongs to another inventory")
        self.revision, self.expected, self.index = revision, expected, trusted_index
        self.files = {}
        self.arrivals = 0
        self.failed = set()
        self.pins = Counter()
        self.lock = RLock()

    def arrive(self, file, *, revision, completed=True, expected_size=None, expected_digest=None):
        with self.lock:
            if revision != self.revision or file.name not in self.expected:
                raise ValueError("Wrong product/frame/inventory")
            if (not completed or file.size <= 0 or not file.digest
                    or (expected_size is not None and file.size != expected_size)
                    or (expected_digest is not None and file.digest != expected_digest)):
                self.failed.add(file.name)
                raise ValueError("Incomplete or corrupt transfer")
            if self.index is not None and dict(self.index.entries)[file.name] != file.strips:
                raise ValueError("Arriving header disagrees with trusted geometry")
            candidate = {**self.files, file.name: file}
            index = self.index
            if index is None and len(candidate) == len(self.expected):
                index = Index(tuple((name, candidate[name].strips) for name in self.expected))
            self.files, self.index = candidate, index
            self.failed.discard(file.name)
            self.arrivals += 1

    @property
    def complete(self):
        return self.index is not None and len(self.files) == len(self.expected)

    def snapshot(self, windows, *, offdisk=False, full=False):
        with self.lock:
            if self.index is None or (full and not self.complete):
                raise Pending("Trustworthy geometry or full-native fallback still pending")
            dependencies = self.index.dependencies(windows, offdisk=offdisk)
            if full:
                dependencies = frozenset(self.expected)
            if not dependencies <= self.files.keys():
                raise Pending("Required native strips still pending")
            return Snapshot(self.revision, self.index,
                            tuple(self.files[name] for name in sorted(dependencies)),
                            tuple(sorted(windows.items())), offdisk)

    def valid(self, snapshot):
        return (snapshot.source_revision == self.revision and snapshot.index == self.index
                and all(self.files.get(f.name) == f for f in snapshot.files))

    @contextmanager
    def pin(self, snapshot):
        with self.lock:
            if not self.valid(snapshot):
                raise Pending("Snapshot changed before native reading")
            self.pins.update(snapshot.files)
        try:
            yield snapshot
        finally:
            with self.lock:
                self.pins.subtract(snapshot.files)
                self.pins += Counter()

    def publish(self, snapshot, owns, emit):
        # Logical atomic publication. Integration must share the owner's lock too.
        with self.lock:
            if not self.valid(snapshot) or not owns():
                raise Pending("Dependency/source revision or ownership changed")
            return emit()

    def record(self):
        # An acquisition record deliberately has no legacy manifest `chunks` key.
        return {"schema": 1, "revision": self.revision, "expected": self.expected,
                "validated": {name: f.digest for name, f in self.files.items()},
                "complete": self.complete}

    @classmethod
    def restore(cls, record, revalidate):
        result = cls(record["revision"], record["expected"])
        for name, digest in record["validated"].items():
            file = revalidate(name)
            if file is not None:
                result.arrive(file, revision=result.revision, expected_digest=digest)
        return result


@dataclass(frozen=True)
class Owner:
    client: str
    selection: str
    generation: int
    viewport: int


@dataclass(frozen=True)
class Demand:
    owner: Owner
    bundle: str
    tile: str
    dependencies: frozenset
    priority: int  # 0 discovery, 1 center, 2 visible, 3 history, 4 speculative


class Scheduler:
    """Deterministic dispatcher. Active transfers advance only via explicit events."""

    def __init__(self, bundles, workers=4):
        if len(bundles) > 4:
            raise ValueError("Four active bundle records maximum")
        self.bundles = bundles
        self.workers = max(1, min(4, workers))
        self.owners, self.demands, self.active = {}, {}, set()
        self.turn = 0
        self.last_served = {}
        self.trace = []

    def register(self, demand):
        owner = demand.owner
        previous = self.owners.get(owner.client)
        if previous is not None and (owner.generation, owner.viewport) < (previous.generation, previous.viewport):
            return False
        if previous is not None and previous != owner and (owner.generation, owner.viewport) == (previous.generation, previous.viewport):
            return False
        if demand.bundle not in self.bundles or not demand.dependencies <= set(self.bundles[demand.bundle].expected):
            raise ValueError("Unknown source demand")
        if previous != owner:
            self.release(owner.client)
        key = (owner.client, demand.bundle, demand.tile)
        if key not in self.demands and (len(self.demands) >= 256 or sum(k[0] == owner.client for k in self.demands) >= 64):
            return False  # Explicit caller backpressure, no hidden overflow queue.
        self.owners[owner.client] = owner
        self.demands[key] = demand
        return True

    def release(self, client):
        self.owners.pop(client, None)
        self.demands = {k: d for k, d in self.demands.items() if k[0] != client}
        self.last_served.pop(client, None)

    def owns(self, demand):
        return self.owners.get(demand.owner.client) == demand.owner and demand in self.demands.values()

    def block_boundary(self, transfer):
        live = any(d.bundle == transfer[0] and transfer[1] in d.dependencies and self.owns(d)
                   for d in self.demands.values())
        if not live:
            self.active.discard(transfer)
            self.trace.append(("cancel-at-block-boundary", *transfer))
        return live

    def dispatch(self, available=None, headroom=0, render_bytes=0):
        pressure = available is None or available < headroom + render_bytes + self.workers * 1024**2
        limit = 1 if pressure else self.workers
        for job in tuple(self.active):
            self.block_boundary(job)
        selected = []
        while len(self.active) < limit:
            candidates = []
            for d in self.demands.values():
                if pressure and d.priority >= 4:
                    continue
                for name in d.dependencies - self.bundles[d.bundle].files.keys():
                    job = (d.bundle, name)
                    if job in self.active:
                        continue
                    reuse = sum(other.bundle == d.bundle and name in other.dependencies and other.priority == d.priority
                                for other in self.demands.values())
                    candidates.append((d.priority, self.last_served.get(d.owner.client, -1), -reuse,
                                       d.owner.client, name, d.bundle))
            if not candidates:
                break
            _, _, _, client, name, bundle = min(candidates)
            job = (bundle, name)
            self.turn += 1
            self.last_served[client] = self.turn
            self.active.add(job)
            selected.append(job)
            self.trace.append(("start", *job))
        return selected

    def finish(self, job, file):
        if job not in self.active:
            raise ValueError("No owned active transfer")
        if self.block_boundary(job):
            self.bundles[job[0]].arrive(file, revision=self.bundles[job[0]].revision)
            self.trace.append(("complete", *job))
        self.active.discard(job)

    def ready(self, demand):
        bundle = self.bundles[demand.bundle]
        return self.owns(demand) and bundle.index is not None and demand.dependencies <= bundle.files.keys()
