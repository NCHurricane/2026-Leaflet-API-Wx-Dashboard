"""Small, offline state-transition tests; no application renderer imports."""

from dataclasses import replace
import unittest

from fci_first_use_contract import Bundle, Demand, File, Index, Owner, Pending, Scheduler, Strip


def fixture():
    files = tuple(File(f"{n}.nc", f"hash{n}", 10,
                       (Strip("vis", n * 2, n * 2 + 2, 4, "grid"),
                        Strip("ir", n, n + 1, 2, "ir-grid"))) for n in range(4))
    return files, Index(tuple((f.name, f.strips) for f in files))


class Contracts(unittest.TestCase):
    def setUp(self):
        self.files, self.index = fixture()
        self.names = tuple(f.name for f in self.files)
        self.window = {"vis": (0, 2, 4, 4)}  # Raw rows 4..6; file 2 only.

    def bundle(self, trusted=True):
        return Bundle("product/frame/inventory1", self.names, self.index if trusted else None)

    def arrive(self, bundle, n):
        bundle.arrive(self.files[n], revision=bundle.revision)

    def test_arrival_permutations_never_publish_missing_coverage(self):
        for order in ((0, 1, 2, 3), (3, 2, 1, 0), (1, 3, 0, 2)):
            b = self.bundle()
            for n in order:
                self.arrive(b, n)
                if 2 in order[:order.index(n) + 1]:
                    self.assertEqual(len(b.snapshot(self.window).files), 1)
                else:
                    with self.assertRaises(Pending):
                        b.snapshot(self.window)

    def test_cold_endpoints_and_required_strip_are_not_an_index(self):
        b = self.bundle(False)
        for n in (0, 3, 2):
            self.arrive(b, n)
            with self.assertRaises(Pending):
                b.snapshot(self.window)
            with self.assertRaises(Pending):
                b.snapshot({}, offdisk=True)
        self.arrive(b, 1)
        self.assertTrue(b.complete)
        self.assertEqual(len(b.snapshot(self.window).files), 1)

    def test_unrelated_arrival_does_not_invalidate_pinned_snapshot(self):
        b = self.bundle()
        self.arrive(b, 2)
        snap = b.snapshot(self.window)
        with b.pin(snap):
            self.arrive(b, 1)
            self.assertEqual(snap, b.snapshot(self.window))
            self.assertEqual(b.publish(snap, lambda: True, lambda: "PNG"), "PNG")
            self.assertTrue(b.pins)
        self.assertFalse(b.pins)

    def test_dependency_replacement_invalidates_read_and_publication(self):
        b = self.bundle()
        self.arrive(b, 2)
        snap = b.snapshot(self.window)
        with b.pin(snap):
            b.arrive(replace(self.files[2], digest="new-content"), revision=b.revision)
            self.assertEqual(snap.files[0].digest, "hash2")
            with self.assertRaises(Pending):
                b.publish(snap, lambda: True, lambda: self.fail("stale PNG"))
        with self.assertRaises(Pending), b.pin(snap):
            pass

    def test_source_revision_and_owner_checked_at_publication(self):
        b = self.bundle()
        self.arrive(b, 2)
        snap = b.snapshot(self.window)
        for mutate in (False, True):
            if mutate:
                b.revision = "replacement-provider-product"
            with self.assertRaises(Pending):
                b.publish(snap, lambda: mutate, lambda: self.fail("stale publication"))

    def test_bad_geometry_and_composite_coverage(self):
        b = self.bundle()
        self.arrive(b, 2)
        mixed = {**self.window, "ir": (0, 3, 2, 4)}
        with self.assertRaises(Pending):
            b.snapshot(mixed)
        self.arrive(b, 0)
        self.assertEqual(len(b.snapshot(mixed).files), 2)
        for altered in (replace(self.files[1].strips[0], start=1),
                        replace(self.files[1].strips[0], start=3),
                        replace(self.files[1].strips[0], geometry="wrong")):
            rows = list(self.index.entries)
            rows[1] = ("1.nc", (altered, self.files[1].strips[1]))
            with self.assertRaises(ValueError):
                Index(tuple(rows))
        with self.assertRaises(ValueError):
            Index((("0.nc", self.files[0].strips), ("1.nc", (self.files[1].strips[0],))))

    def test_bad_arrival_cannot_create_complete_or_negative_marker(self):
        for kwargs in ({"completed": False}, {"expected_size": 11}, {"expected_digest": "bad"}):
            b = self.bundle()
            with self.assertRaises(ValueError):
                b.arrive(self.files[2], revision=b.revision, **kwargs)
            self.assertFalse(b.files)
            self.assertFalse(b.complete)
            self.assertNotIn("chunks", b.record())
        with self.assertRaises(ValueError):
            self.bundle().arrive(self.files[0], revision="different-frame")
        with self.assertRaises(ValueError):
            self.bundle().arrive(replace(self.files[0], strips=()), revision="product/frame/inventory1")

    def test_restart_revalidates_partial_record(self):
        b = self.bundle()
        self.arrive(b, 2)
        record = b.record()
        record["complete"] = True  # This claim must not confer complete readiness.
        restored = Bundle.restore(record, lambda name: self.files[2])
        self.assertFalse(restored.complete)
        with self.assertRaises(Pending):
            restored.snapshot(self.window)
        self.assertFalse(Bundle.restore(record, lambda name: None).files)

    def test_offdisk_and_native_fallback_require_correct_readiness(self):
        b = self.bundle()
        with self.assertRaises(ValueError):
            b.snapshot({})
        self.assertFalse(b.snapshot({}, offdisk=True).files)
        for n in (2, 0, 1):
            self.arrive(b, n)
            with self.assertRaises(Pending):
                b.snapshot(self.window, full=True)
        self.arrive(b, 3)
        self.assertEqual(len(b.snapshot(self.window, full=True).files), 4)

    def test_inventory_validation(self):
        for names in (("../x.nc",), ("C:\\x.nc",), ("a.nc", "a.nc"), ("a:b",)):
            with self.assertRaises(ValueError):
                Bundle("revision", names)

    def demand(self, client="a", generation=1, viewport=1, names=("2.nc",), priority=1, tile="center"):
        return Demand(Owner(client, "visible", generation, viewport), "b", tile, frozenset(names), priority)

    def test_multi_client_dedup_and_surviving_owner(self):
        b = self.bundle()
        s = Scheduler({"b": b})
        a, other = self.demand(), self.demand("other")
        self.assertTrue(s.register(a))
        self.assertTrue(s.register(a))
        s.register(other)
        self.assertFalse(s.ready(a))
        jobs = s.dispatch(available=10**10)
        self.assertEqual(jobs, [("b", "2.nc")])
        s.release("a")
        self.assertTrue(s.block_boundary(jobs[0]))
        s.finish(jobs[0], self.files[2])
        self.assertTrue(s.ready(other))
        self.assertFalse(s.ready(a))
        self.assertFalse(s.dispatch(available=10**10))

    def test_generation_viewport_and_stream_boundary_cancel(self):
        s = Scheduler({"b": self.bundle()})
        old = self.demand()
        s.register(old)
        job = s.dispatch()[0]
        current = self.demand(viewport=2, names=("1.nc",))
        s.register(current)
        self.assertFalse(s.block_boundary(job))
        self.assertFalse(s.register(old))
        s.register(self.demand(generation=2, viewport=0, names=("3.nc",)))
        self.assertFalse(s.owns(current))
        self.assertEqual(s.dispatch(), [("b", "3.nc")])
        s.release("a")
        self.assertFalse(s.block_boundary(("b", "3.nc")))

    def test_pressure_priority_fairness_and_history_retention(self):
        s = Scheduler({"b": self.bundle()}, workers=99)
        for client in ("a", "b"):
            s.register(self.demand(client, names=("0.nc", "1.nc") if client == "a" else ("2.nc", "3.nc")))
        self.assertEqual(len(s.dispatch(available=10**10)), 4)
        self.assertEqual([r[2] for r in s.trace], ["0.nc", "2.nc", "1.nc", "3.nc"])
        s = Scheduler({"b": self.bundle()})
        s.register(self.demand(names=("0.nc",), priority=4, tile="warm"))
        history = self.demand(names=("1.nc",), priority=3, tile="history")
        s.register(history)
        self.assertEqual(s.dispatch(), [("b", "1.nc")])
        self.assertIn(history, s.demands.values())
        s.finish(("b", "1.nc"), self.files[1])
        self.assertFalse(s.dispatch())
        self.assertEqual(s.dispatch(available=10**10), [("b", "0.nc")])

    def test_queue_caps_and_coalescing_have_no_hidden_overflow(self):
        s = Scheduler({"b": self.bundle()})
        for client in "abcd":
            for n in range(64):
                self.assertTrue(s.register(self.demand(client, tile=str(n))))
        self.assertFalse(s.register(self.demand("a", tile="overflow")))
        self.assertFalse(s.register(self.demand("e")))
        self.assertNotIn("e", s.owners)
        self.assertEqual(len(s.demands), 256)
        self.assertTrue(s.register(self.demand("a", generation=2)))
        self.assertEqual(len(s.demands), 193)
        with self.assertRaises(ValueError):
            Scheduler({str(n): self.bundle() for n in range(5)})


if __name__ == "__main__":
    unittest.main()
