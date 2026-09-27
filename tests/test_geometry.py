"""Unit tests for geometry.py (pure math, no camera)."""
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from geometry import (
    bounding_box,
    center,
    circle_between_tips_px,
    distance,
    joint_angle,
    normalized_bbox,
    sphere_radius_px,
    to_pixel,
    wrist_midpoint,
    wrist_span,
)
from helpers import lm, make_hand


class TestDistanceCenter(unittest.TestCase):
    def test_distance(self):
        self.assertAlmostEqual(distance(lm(0, 0), lm(3, 4)), 5.0)
        self.assertAlmostEqual(distance((0, 0), (1, 0)), 1.0)

    def test_center(self):
        self.assertEqual(center(lm(0, 0), lm(2, 4)), (1.0, 2.0))


class TestJointAngle(unittest.TestCase):
    def test_straight(self):
        self.assertAlmostEqual(joint_angle(lm(0, 0), lm(1, 0), lm(2, 0)), 180.0)

    def test_right_angle(self):
        self.assertAlmostEqual(joint_angle(lm(0, 0), lm(0, 1), lm(1, 1)), 90.0)

    def test_degenerate(self):
        self.assertTrue(math.isnan(joint_angle(lm(1, 1), lm(1, 1), lm(2, 2))))


class TestPixels(unittest.TestCase):
    def test_to_pixel(self):
        self.assertEqual(to_pixel(lm(0.5, 0.25), 640, 480), (320, 120))

    def test_to_pixel_clamps(self):
        self.assertEqual(to_pixel(lm(2.0, -1.0), 640, 480), (639, 0))
        self.assertEqual(to_pixel(lm(-0.5, 1.5), 100, 100), (0, 99))


class TestBoundingBox(unittest.TestCase):
    def test_single_hand(self):
        hand = make_hand()
        box = bounding_box([hand], 640, 480)
        self.assertIsNotNone(box)
        xmin, ymin, xmax, ymax = box
        self.assertLess(xmin, xmax)
        self.assertLess(ymin, ymax)
        self.assertGreaterEqual(xmin, 0)
        self.assertLessEqual(xmax, 639)

    def test_two_hands_wider(self):
        left = make_hand(wrist=(0.2, 0.9))
        right = make_hand(wrist=(0.8, 0.9))
        one = bounding_box([left], 640, 480)
        two = bounding_box([left, right], 640, 480)
        self.assertLessEqual(two[0], one[0])
        self.assertGreaterEqual(two[2], one[2])

    def test_empty(self):
        self.assertIsNone(bounding_box([], 640, 480))
        self.assertIsNone(normalized_bbox([]))


class TestWrists(unittest.TestCase):
    def test_span_and_midpoint(self):
        h1 = make_hand(wrist=(0.3, 0.5))
        h2 = make_hand(wrist=(0.7, 0.5))
        self.assertAlmostEqual(wrist_span(h1, h2), 0.4)
        self.assertEqual(wrist_midpoint(h1, h2), (0.5, 0.5))

    def test_sphere_radius(self):
        h1 = make_hand(wrist=(0.3, 0.5))
        h2 = make_hand(wrist=(0.7, 0.5))
        # 0.4 * 640 = 256 px span -> radius 128.
        self.assertEqual(sphere_radius_px(h1, h2, 640, 480), 128)

    def test_sphere_radius_minimum(self):
        h = make_hand()
        self.assertGreaterEqual(sphere_radius_px(h, h, 640, 480), 5)

    def test_circle_between_tips(self):
        (cx, cy), radius = circle_between_tips_px(lm(0.4, 0.5), lm(0.6, 0.5), 640, 480)
        self.assertEqual((cx, cy), (320, 240))
        self.assertEqual(radius, 64)


if __name__ == "__main__":
    unittest.main()
