"""Unit tests for the studio GUI (no camera, no display)."""
import sys
import unittest
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
import ui
from canvas import Canvas, Stroke
from gesture_engine import GestureResult, GestureState
from tools import Tool


def blank(w=640, h=480):
    """Create a black BGR frame."""
    return np.zeros((h, w, 3), dtype=np.uint8)


def studio(**overrides):
    """Build a studio context dict for draw_hud."""
    base = {"tool": Tool.PENCIL, "canvas": Canvas(), "brush_size": 6,
            "hint": "hello", "camera_ok": True, "show_help": False,
            "show_settings": False, "settings_view": {}, "finger_info": ""}
    base.update(overrides)
    return base


DRAW = GestureResult(name="LINE", confidence=0.95, hand_count=1,
                     finger_counts=(1,), is_stable=True, action="DRAW",
                     state=GestureState.ACTIVE)


class TestHudRobustness(unittest.TestCase):
    def test_all_sizes_and_flags(self):
        for w, h in ((80, 60), (320, 240), (640, 480), (1280, 720)):
            for debug in (False, True):
                for help_, settings in ((False, False), (True, False), (False, True)):
                    frame = blank(w, h)
                    out = ui.draw_hud(frame, DRAW, 59.9, debug=debug,
                                      studio=studio(show_help=help_,
                                                    show_settings=settings))
                    self.assertIs(out, frame)

    def test_minimal_context(self):
        frame = blank()
        ui.draw_hud(frame, GestureResult(), 0.0, debug=True, studio=None)
        ui.draw_hud(frame, DRAW, 30.0, debug=False,
                    studio={"tool": None, "canvas": None, "camera_ok": False})

    def test_top_bar_paints(self):
        frame = blank()
        ui.draw_top_bar(frame, camera_ok=True)
        self.assertGreater(int((frame[5] > 0).sum()), 0)  # bar row not black

    def test_narrow_top_bar_no_crash(self):
        frame = blank(160, 120)
        ui.draw_top_bar(frame, camera_ok=False)
        self.assertGreater(int((frame > 0).sum()), 0)


class TestLayout(unittest.TestCase):
    def test_status_text_fits_narrow_frame(self):
        frame = blank(320, 240)
        ui.draw_status_bar(frame, DRAW, 59.9, canvas=Canvas(),
                           tool=Tool.PENCIL, brush_size=6)
        trimmed = ui._trim_to_fit("x" * 110, 300)
        (tw, _), _ = cv2.getTextSize(trimmed, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
        self.assertLessEqual(tw, 300)

    def test_hint_flag_hides_hint(self):
        old = config.SHOW_GESTURE_HINTS
        try:
            frame_on = blank()
            ui.draw_toolbar(frame_on, Tool.PENCIL, hint="hello hint")
            config.SHOW_GESTURE_HINTS = False
            frame_off = blank()
            ui.draw_toolbar(frame_off, Tool.PENCIL, hint="hello hint")
        finally:
            config.SHOW_GESTURE_HINTS = old
        row_on = frame_on[480 - 68]
        row_off = frame_off[480 - 68]
        self.assertGreater(int((row_on > 0).sum()), int((row_off > 0).sum()))

    def test_debug_fits_short_frame(self):
        frame = blank(320, 240)
        ui.draw_debug_panel(frame, DRAW, 59.9, 17.0, Canvas(), "I:1")
        # Debug rows must spread over several rows, not pile on one.
        rows = (frame[40:200, 10:200, :] > 0).any(axis=(1, 2))
        self.assertGreater(int(rows.sum()), 2)

    def test_help_truncates_short_frame(self):
        frame = blank(320, 240)
        ui.draw_help_overlay(frame)  # must not crash or paint below the frame
        self.assertEqual(frame.shape, (240, 320, 3))

    def test_help_leaves_toolbar_visible(self):
        frame = blank()
        ui.draw_hud(frame, DRAW, 60.0, debug=False,
                    studio=studio(show_help=True))
        toolbar_row = frame[480 - 30]
        self.assertGreater(int((toolbar_row > 0).sum()), 0)


if __name__ == "__main__":
    unittest.main()
