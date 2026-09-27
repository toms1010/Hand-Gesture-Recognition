"""Unit tests for auto shape recognition."""
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from shapes import (
    UNKNOWN,
    perfect_circle_points,
    perfect_line,
    perfect_rectangle,
    perfect_triangle,
    recognize,
    stroke_endpoints,
)


def noisy_line(n=24):
    """Rough diagonal line with small deterministic jitter."""
    return [(float(i), float(i) + (0.3 if i % 3 == 0 else -0.3)) for i in range(n)]


def rough_circle(n=40):
    """Closed rough circle."""
    pts = []
    for i in range(n):
        angle = 2 * math.pi * i / (n - 1)
        wobble = 1.5 if i % 2 == 0 else -1.5
        pts.append((50 + (20 + wobble) * math.cos(angle),
                    50 + (20 + wobble) * math.sin(angle)))
    return pts


def poly_outline(corners, per_edge=10):
    """Closed polygon outline through corner points."""
    pts = []
    ring = corners + [corners[0]]
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        for i in range(per_edge):
            f = i / per_edge
            pts.append((x1 + (x2 - x1) * f, y1 + (y2 - y1) * f))
    return pts


class TestRecognize(unittest.TestCase):
    def test_line(self):
        name, confidence = recognize(noisy_line())
        self.assertEqual(name, "line")
        self.assertGreater(confidence, 0.5)

    def test_circle(self):
        name, confidence = recognize(rough_circle())
        self.assertEqual(name, "circle")
        self.assertGreater(confidence, 0.5)

    def test_rectangle(self):
        pts = poly_outline([(10, 10), (80, 10), (80, 60), (10, 60)])
        name, _ = recognize(pts)
        self.assertEqual(name, "rectangle")

    def test_triangle(self):
        pts = poly_outline([(50, 5), (95, 80), (5, 80)])
        name, _ = recognize(pts)
        self.assertEqual(name, "triangle")

    def test_too_short(self):
        self.assertEqual(recognize([(0, 0), (1, 1)]), (UNKNOWN, 0.0))
        self.assertEqual(recognize([]), (UNKNOWN, 0.0))


class TestPerfectShapes(unittest.TestCase):
    def test_line_endpoints(self):
        self.assertEqual(perfect_line([(0, 0), (5, 5), (10, 10)]), [(0, 0), (10, 10)])

    def test_circle_closed(self):
        pts = perfect_circle_points((0, 0), 10, n=8)
        self.assertEqual(len(pts), 8)
        for x, y in pts:
            self.assertAlmostEqual(math.hypot(x, y), 10.0, places=5)

    def test_rectangle_corners(self):
        corners = perfect_rectangle((0, 0), (4, 2))
        self.assertEqual(len(corners), 4)
        self.assertIn((0, 0), corners)
        self.assertIn((4, 2), corners)

    def test_triangle_vertices(self):
        tri = perfect_triangle((0, 0), (10, 10))
        self.assertEqual(len(tri), 3)
        self.assertEqual(tri[0], (5.0, 0))

    def test_endpoints(self):
        self.assertEqual(stroke_endpoints([]), (None, None))
        self.assertEqual(stroke_endpoints([(1, 2), (3, 4)]), ((1, 2), (3, 4)))


if __name__ == "__main__":
    unittest.main()
