"""Unit tests for pointer smoothing and stroke interpolation."""
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from smoothing import (
    PointSmoother,
    catmull_rom,
    interpolate_segment,
    smoothing_to_alpha,
)


class TestAlphaMapping(unittest.TestCase):
    def test_endpoints(self):
        self.assertAlmostEqual(smoothing_to_alpha(0.0), 0.9)
        self.assertAlmostEqual(smoothing_to_alpha(1.0), 0.15)

    def test_default(self):
        alpha = smoothing_to_alpha(0.7)
        self.assertGreater(alpha, 0.15)
        self.assertLess(alpha, 0.9)


class TestPointSmoother(unittest.TestCase):
    def test_first_sample_passthrough(self):
        smoother = PointSmoother()
        self.assertEqual(smoother.update((10.0, 20.0)), (10.0, 20.0))
        self.assertEqual(smoother.position, (10.0, 20.0))

    def test_dead_zone_holds(self):
        smoother = PointSmoother(dead_zone_px=2.0)
        smoother.update((100.0, 100.0))
        held = smoother.update((101.0, 100.5))
        # Leaky hold: mostly held, never the full raw jump.
        self.assertLess(abs(held[0] - 100.0), 1.0)
        self.assertLess(abs(held[1] - 100.0), 1.0)
        self.assertLess(math.hypot(held[0] - 100.0, held[1] - 100.0),
                        math.hypot(1.0, 0.5))

    def test_dead_zone_leaves_no_offset(self):
        smoother = PointSmoother(dead_zone_px=2.0)
        smoother.update((100.0, 100.0))
        pos = (100.0, 100.0)
        for _ in range(60):
            pos = smoother.update((101.5, 100.0))  # constant slow drift
        self.assertAlmostEqual(pos[0], 101.5, delta=0.6)

    def test_converges_to_static_point(self):
        smoother = PointSmoother(smoothing=0.5, dead_zone_px=0.0)
        pos = smoother.update((0.0, 0.0))
        for _ in range(50):
            pos = smoother.update((100.0, 0.0))
        self.assertGreater(pos[0], 99.0)

    def test_fast_adapts_more_than_slow(self):
        slow = PointSmoother(smoothing=0.9, dead_zone_px=0.0)
        fast = PointSmoother(smoothing=0.9, dead_zone_px=0.0)
        slow.update((0.0, 0.0))
        fast.update((0.0, 0.0))
        slow_pos = slow.update((5.0, 0.0))    # small step
        fast_pos = fast.update((200.0, 0.0))  # huge step
        # Fast motion covers proportionally more ground per update.
        self.assertGreater(fast_pos[0] / 200.0, slow_pos[0] / 5.0)

    def test_reset(self):
        smoother = PointSmoother()
        smoother.update((5.0, 5.0))
        smoother.reset()
        self.assertIsNone(smoother.position)
        self.assertEqual(smoother.update((9.0, 9.0)), (9.0, 9.0))


class TestInterpolation(unittest.TestCase):
    def test_short_gap(self):
        self.assertEqual(interpolate_segment((0, 0), (2, 0)),
                         [(0, 0), (2, 0)])

    def test_long_gap_filled(self):
        pts = interpolate_segment((0.0, 0.0), (20.0, 0.0), max_gap=4.0)
        self.assertEqual(pts[0], (0.0, 0.0))
        self.assertEqual(pts[-1], (20.0, 0.0))
        for (x1, _), (x2, _) in zip(pts, pts[1:]):
            self.assertLessEqual(x2 - x1, 4.0 + 1e-9)

    def test_catmull_rom_endpoints(self):
        pts = [(0.0, 0.0), (10.0, 5.0), (20.0, 0.0), (30.0, 5.0)]
        out = catmull_rom(pts, samples_per_span=4)
        self.assertEqual(out[0], pts[0])
        self.assertAlmostEqual(out[-1][0], pts[-1][0])
        self.assertAlmostEqual(out[-1][1], pts[-1][1])
        self.assertGreater(len(out), len(pts))

    def test_catmull_rom_short_fallback(self):
        pts = [(0.0, 0.0), (30.0, 0.0)]
        out = catmull_rom(pts)
        self.assertEqual(out[0], pts[0])
        self.assertEqual(out[-1], pts[-1])
        self.assertGreater(len(out), 2)

    def test_catmull_rom_bounds(self):
        pts = [(0.0, 0.0), (10.0, 30.0), (20.0, 0.0), (30.0, 30.0)]
        out = catmull_rom(pts, bounds=(0.0, 0.0, 30.0, 30.0))
        for x, y in out:
            self.assertGreaterEqual(x, 0.0)
            self.assertLessEqual(x, 30.0)
            self.assertGreaterEqual(y, 0.0)
            self.assertLessEqual(y, 30.0)


if __name__ == "__main__":
    unittest.main()
