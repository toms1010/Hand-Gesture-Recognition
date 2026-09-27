"""Unit tests for the interaction controller (no camera)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from canvas import Canvas
from gesture_engine import (
    ACTION_DRAW,
    ACTION_ERASE,
    ACTION_PAUSE,
    ACTION_SHAPE,
    LINE,
    SPHERE,
    GestureResult,
)
from helpers import lm, make_hand
from interaction_controller import InteractionController
from tools import Tool

W, H = 640, 480


def draw_result():
    """Stabilized DRAW result."""
    return GestureResult(name=LINE, confidence=0.95, hand_count=1,
                         finger_counts=(1,), is_stable=True, action=ACTION_DRAW)


def hand_with_tip(nx: float, ny: float):
    hand = make_hand(fingers_open=("index",), thumb_open=False)
    hand[8] = lm(nx, ny)  # move the index fingertip
    return hand


class TestDrawing(unittest.TestCase):
    def test_stroke_committed_on_pause(self):
        canvas = Canvas()
        controller = InteractionController(canvas)
        for x in (0.3, 0.4, 0.5):
            controller.update([hand_with_tip(x, 0.5)], draw_result(), W, H)
        self.assertEqual(canvas.stroke_count, 0)  # still in progress
        paused = GestureResult(name="RECT", confidence=0.95, hand_count=1,
                               finger_counts=(5,), is_stable=True, action=ACTION_PAUSE)
        controller.update([make_hand()], paused, W, H)
        self.assertEqual(canvas.stroke_count, 1)
        # Gap interpolation fills long jumps: endpoints preserved, densely filled.
        # (Smoothing may lag the final raw tip by a few px — allow tolerance.)
        pts = canvas.items[0].points
        self.assertGreaterEqual(len(pts), 3)
        self.assertEqual(pts[0], (int(0.3 * W), int(0.5 * H)))
        self.assertLess(abs(pts[-1][0] - int(0.5 * W)), 20)
        xs = [p[0] for p in pts]
        self.assertEqual(xs, sorted(xs))

    def test_no_hand_ends_stroke(self):
        canvas = Canvas()
        controller = InteractionController(canvas)
        controller.update([hand_with_tip(0.3, 0.5)], draw_result(), W, H)
        controller.update([], GestureResult(), W, H)
        self.assertEqual(canvas.stroke_count, 1)

    def test_unstable_action_pauses(self):
        canvas = Canvas()
        controller = InteractionController(canvas)
        wobbly = GestureResult(name=LINE, confidence=0.9, hand_count=1,
                               finger_counts=(1,), is_stable=False, action=ACTION_DRAW)
        controller.update([hand_with_tip(0.3, 0.5)], wobbly, W, H)
        self.assertEqual(canvas.stroke_count, 0)


class TestEraseAndShapes(unittest.TestCase):
    def test_erase_removes_points(self):
        canvas = Canvas()
        controller = InteractionController(canvas)  # pencil draws first
        controller.update([hand_with_tip(0.3, 0.5)], draw_result(), W, H)
        controller.update([], GestureResult(), W, H)
        self.assertEqual(canvas.stroke_count, 1)
        controller.set_tool(Tool.ERASER)
        erasing = GestureResult(name="RECT", confidence=0.95, hand_count=1,
                                finger_counts=(0,), is_stable=True, action=ACTION_ERASE)
        controller.update([hand_with_tip(0.31, 0.5)], erasing, W, H)
        remaining = sum(len(item.points) for item in canvas.items)
        self.assertLess(remaining, 3)

    def test_shape_preview_and_stamp(self):
        canvas = Canvas()
        controller = InteractionController(canvas)
        shaping = GestureResult(name="CIRCLE", confidence=0.95, hand_count=1,
                                finger_counts=(2,), is_stable=True, action=ACTION_SHAPE)
        controller.update([make_hand(fingers_open=("index", "middle"),
                                     thumb_open=False)], shaping, W, H)
        self.assertIsNotNone(controller.preview)
        self.assertTrue(controller.stamp_preview())
        self.assertEqual(canvas.stroke_count, 1)
        self.assertFalse(controller.stamp_preview())  # preview consumed

    def test_two_hand_stamp(self):
        canvas = Canvas()
        controller = InteractionController(canvas)
        hands = [make_hand(wrist=(0.3, 0.5)), make_hand(wrist=(0.7, 0.5))]
        self.assertTrue(controller.stamp_two_hand(hands, SPHERE, W, H))
        self.assertEqual(canvas.items[0].shape, "sphere")
        self.assertFalse(controller.stamp_two_hand(hands[:1], SPHERE, W, H))
        self.assertFalse(controller.stamp_two_hand(hands, "NONE", W, H))

    def test_two_hand_zoom(self):
        canvas = Canvas()
        controller = InteractionController(canvas)
        zoomed = GestureResult(name=LINE, confidence=0.95, hand_count=2,
                               finger_counts=(5, 5), is_stable=True)
        wide = [make_hand(wrist=(0.05, 0.5)), make_hand(wrist=(0.95, 0.5))]
        controller.update(wide, zoomed, W, H)
        controller.update(wide, zoomed, W, H)
        self.assertGreater(canvas.zoom, 1.0)


class TestCursorAndCancel(unittest.TestCase):
    def test_cursor_follows_and_states(self):
        canvas = Canvas()
        controller = InteractionController(canvas)
        self.assertIsNone(controller.cursor_px)
        controller.update([hand_with_tip(0.3, 0.5)], draw_result(), W, H)
        self.assertIsNotNone(controller.cursor_px)
        self.assertEqual(controller.cursor_state, "drawing")
        x0, _y0 = controller.cursor_px
        controller.update([hand_with_tip(0.6, 0.5)], draw_result(), W, H)
        x1, _y1 = controller.cursor_px
        self.assertGreater(x1, x0)  # smoothed cursor tracks rightward motion

    def test_cancel_discards_stroke(self):
        canvas = Canvas()
        controller = InteractionController(canvas)
        controller.update([hand_with_tip(0.3, 0.5)], draw_result(), W, H)
        controller.cancel_active()
        controller.update([], GestureResult(), W, H)
        self.assertEqual(canvas.stroke_count, 0)
        self.assertIsNone(controller.cursor_px)

    def test_stamp_maps_into_canvas_space(self):
        canvas = Canvas()
        canvas.set_zoom(2.0)
        controller = InteractionController(canvas)
        shaping = GestureResult(name="CIRCLE", confidence=0.95, hand_count=1,
                                finger_counts=(2,), is_stable=True, action=ACTION_SHAPE)
        controller.update([make_hand(fingers_open=("index", "middle"),
                                     thumb_open=False)], shaping, W, H)
        self.assertIsNotNone(controller.preview)
        view_p1 = controller.preview.p1
        self.assertTrue(controller.stamp_preview(W, H))
        item = canvas.items[0]
        expected = canvas.to_canvas(view_p1, W, H)
        self.assertEqual(item.p1, expected)
        # With zoom 2 the stored point differs from raw view pixels.
        self.assertNotEqual(item.p1, view_p1)


if __name__ == "__main__":
    unittest.main()
