"""Unit tests for the Tkinter desktop studio (display needed for widgets)."""
import sys
import time
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from canvas import Canvas, Stroke
from desktop.view import VIEW_LABELS, ViewMode, compose_view
from tools import Tool


def has_display() -> bool:
    """True when a Tk root window can be created."""
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.update()
        root.destroy()
        return True
    except Exception:
        return False


DISPLAY = has_display()


class FakeCamera:
    """Camera stand-in returning black frames (connected path)."""

    def __init__(self, width=320, height=240):
        self.size = (width, height)
        self.released = False
        self.frames = 0

    def get_frame(self):
        self.frames += 1
        return np.zeros((self.size[1], self.size[0], 3), dtype=np.uint8)

    def release(self):
        self.released = True


class TestComposeView(unittest.TestCase):
    def test_modes_without_camera(self):
        canvas = Canvas()
        canvas.add_stroke(Stroke(points=[(10, 10), (50, 50)],
                                 color=(0, 255, 0), thickness=3))
        for mode in (ViewMode.CAMERA_DRAWING, ViewMode.DRAWING, ViewMode.CAMERA):
            view = compose_view(mode, None, canvas, 320, 240)
            self.assertEqual(view.shape, (240, 320, 3))

    def test_drawing_only_keeps_strokes(self):
        canvas = Canvas()
        canvas.add_stroke(Stroke(points=[(10, 10), (50, 50)],
                                 color=(0, 255, 0), thickness=3))
        view = compose_view(ViewMode.DRAWING, None, canvas, 320, 240)
        self.assertGreater(int((view > 0).sum()), 0)

    def test_camera_passthrough(self):
        frame = np.full((240, 320, 3), 7, dtype=np.uint8)
        view = compose_view(ViewMode.CAMERA, frame, Canvas(), 320, 240)
        self.assertTrue((view == 7).all())
        self.assertIsNot(view, frame)  # never mutates/aliases inputs

class TestFitToPane(unittest.TestCase):
    def test_view_labels(self):
        self.assertEqual(len(VIEW_LABELS), 3)

    def test_letterbox_size_and_content(self):
        from desktop.view import fit_to_pane
        img = np.full((100, 200, 3), 255, dtype=np.uint8)
        out = fit_to_pane(img, 300, 300)
        self.assertEqual(out.shape, (300, 300, 3))
        # Content rows present, letterbox bars keep the background color.
        self.assertGreater(int((out[140:160] > 0).sum()), 0)
        self.assertTrue((out[0:10] == (18, 18, 22)).all())

    def test_empty_input(self):
        from desktop.view import fit_to_pane
        out = fit_to_pane(np.zeros((0, 0, 3), dtype=np.uint8), 64, 48)
        self.assertEqual(out.shape, (48, 64, 3))


class TestEngineWorker(unittest.TestCase):
    def test_worker_processes_frames(self):
        from canvas import Canvas as C
        from desktop.worker import EngineWorker
        from gesture_engine import GestureClassifier, GestureSmoother
        from hand_tracker import HandTracker
        from interaction_controller import InteractionController
        camera = FakeCamera()
        canvas = C()
        worker = EngineWorker(camera, HandTracker(), canvas,
                              InteractionController(canvas),
                              GestureClassifier(), GestureSmoother())
        worker.start()
        try:
            deadline = time.time() + 15.0
            frame, snap = None, {}
            while time.time() < deadline:
                frame, snap = worker.latest()
                if frame is not None and snap.get("fps", 0.0) > 0:
                    break
                time.sleep(0.1)
            self.assertIsNotNone(frame)
            self.assertTrue(snap.get("camera_ok"))
            self.assertEqual(snap.get("hands"), 0)
            self.assertGreater(snap.get("fps", 0.0), 0.0)
        finally:
            worker.stop()
            worker.join(timeout=10.0)
        self.assertFalse(worker.is_alive())


@unittest.skipUnless(DISPLAY, "no display for Tkinter widgets")
class TestDesktopApp(unittest.TestCase):
    def setUp(self):
        from desktop.app import GestureStudioApp
        self.camera = FakeCamera()
        self.app = GestureStudioApp(camera=self.camera)
        self._pump(1.5)

    def tearDown(self):
        try:
            if self.app is not None:
                self.app.close()
        except Exception:
            pass
        self.app = None

    def _pump(self, seconds: float):
        end = time.time() + seconds
        while time.time() < end:
            self.app.update()
            time.sleep(0.05)
        self.app.update_idletasks()
        self.app.update()

    def test_startup_and_snapshot(self):
        frame, snap = self.app.worker.latest()
        self.assertIsNotNone(frame)
        self.assertTrue(snap.get("camera_ok"))
        self.assertEqual(self.app.statusbar.vars["Hands"].get(), "0")
        self.assertIn("pencil", self.app.statusbar.vars["Tool"].get())

    def test_window_fills_desktop(self):
        self.app.update_idletasks()
        screen_w = self.app.winfo_screenwidth()
        screen_h = self.app.winfo_screenheight()
        self.assertGreaterEqual(self.app.winfo_width(), screen_w * 0.6)
        self.assertGreaterEqual(self.app.winfo_height(), screen_h * 0.6)

    def test_tool_selection_updates_state(self):
        self.app.set_tool(Tool.ERASER)
        self._pump(0.6)
        _frame, snap = self.app.worker.latest()
        self.assertEqual(snap.get("tool"), Tool.ERASER)
        self.assertIn("eraser", self.app.statusbar.vars["Tool"].get())

    def test_brush_and_color(self):
        self.app.set_brush_size(17)
        self.app.set_color((255, 0, 0))
        self._pump(0.6)
        _frame, snap = self.app.worker.latest()
        self.assertEqual(snap.get("brush_size"), 17)
        self.assertEqual(tuple(snap.get("brush_color")), (255, 0, 0))
        self.assertIn("17 px", self.app.statusbar.vars["Brush"].get())

    def test_undo_redo_buttons_follow_state(self):
        self.assertEqual(tuple(self.app.toolbar.undo_btn.state()), ("disabled",))
        self.app.worker.apply(lambda: self.app.canvas.add_stroke(
            Stroke(points=[(1, 1), (9, 9)], color=(0, 255, 0), thickness=2)))
        self._pump(0.6)
        self.assertEqual(tuple(self.app.toolbar.undo_btn.state()), ())

    def test_view_modes(self):
        from desktop.view import ViewMode as VM
        self.app.set_view_mode(VM.DRAWING)
        self.assertEqual(self.app.view_mode, VM.DRAWING)
        self.app.set_view_mode("Camera Only")
        self.assertEqual(self.app.view_mode, VM.CAMERA)

    def test_help_dialog_opens(self):
        from desktop.dialogs import HelpDialog
        dlg = HelpDialog(self.app)
        self.app.update()
        dlg.destroy()

    def test_disconnected_status(self):
        # Single Tk root at a time: close this app before opening another.
        self.app.close()
        self.app = None
        from desktop.app import GestureStudioApp, NullCamera
        app2 = GestureStudioApp(camera=NullCamera())
        try:
            for _ in range(20):
                app2.update()
                time.sleep(0.05)
            _frame, snap = app2.worker.latest()
            self.assertFalse(snap.get("camera_ok"))
            self.assertIn("Disconnected", app2.cam_var.get())
        finally:
            app2.close()

    def test_split_toggle(self):
        self.assertTrue(self.app.split_view)
        self.app.split_var.set(False)
        self.app._toggle_split()
        self.assertFalse(self.app.split_view)
        self.assertTrue(self.app.worker.apply(lambda: self.app.worker.include_canvas))
        self.app.split_var.set(True)
        self.app._toggle_split()
        self.assertTrue(self.app.split_view)

    def test_tool_pressed_state(self):
        from tools import Tool
        self.app.set_tool(Tool.BRUSH)
        self._pump(0.6)
        pressed = [t for t, b in self.app.toolbar.tool_buttons.items()
                   if "pressed" in b.state()]
        self.assertEqual(pressed, [Tool.BRUSH])

    def test_view_mode_disables_split(self):
        from desktop.view import ViewMode
        self.assertTrue(self.app.split_view)
        self.app.set_view_mode(ViewMode.DRAWING)
        self.assertFalse(self.app.split_view)

    def test_shortcuts_ignored_in_entries(self):
        import tkinter as tk
        entry = tk.Entry(self.app)
        entry.pack()
        event = type("E", (), {"widget": entry, "char": "e"})()
        self.assertTrue(self.app._in_entry(event))
        before = self.app.worker.apply(lambda: self.app.controller.tool)
        self.app._on_letter(event)
        after = self.app.worker.apply(lambda: self.app.controller.tool)
        self.assertEqual(before, after)
        entry.destroy()
        plain = type("E", (), {"widget": self.app, "char": "e"})()
        self.assertFalse(self.app._in_entry(plain))

    def test_delete_selected(self):
        self.app.worker.apply(lambda: self.app.canvas.add_stroke(
            Stroke(points=[(1, 1), (9, 9)], color=(0, 255, 0), thickness=2)))
        self.app.delete_selected()
        self.assertEqual(self.app.canvas.stroke_count, 0)
        self.app.undo()
        self.assertEqual(self.app.canvas.stroke_count, 1)

    def test_zoom_controls(self):
        self.app.zoom_step(2.0)
        self.assertAlmostEqual(self.app.canvas.zoom, 2.0)
        self.app.worker.apply(lambda: self.app.canvas.pan_by(5, 5))
        self.app.reset_zoom()
        self.assertEqual((self.app.canvas.zoom, self.app.canvas.pan_x,
                          self.app.canvas.pan_y), (1.0, 0, 0))

    def test_cancel_gesture(self):
        self.app.worker.apply(lambda: self.app.controller._draw_point((5, 5), (5, 5)))
        self.app.cancel_gesture()
        state = self.app.worker.apply(
            lambda: (self.app.controller._drawing, self.app.controller.cursor_state))
        self.assertEqual(state, (False, "idle"))
        self.assertEqual(self.app.canvas.stroke_count, 0)

    def test_autosave_and_recovery(self):
        import tempfile
        import config
        from tkinter import messagebox
        old_path = config.AUTOSAVE_PATH
        with tempfile.TemporaryDirectory() as tmp:
            config.AUTOSAVE_PATH = str(Path(tmp) / "autosave.json")
            try:
                self.app.worker.apply(lambda: self.app.canvas.add_stroke(
                    Stroke(points=[(1, 1), (9, 9)], color=(0, 255, 0),
                           thickness=2)))
                self.app._last_autosave_revision = -1
                self.app._last_autosave_time = 0.0
                self.app._autosave_tick()
                saved = Path(config.AUTOSAVE_PATH)
                self.assertTrue(saved.is_file())
                # Recovery restores into a fresh canvas when accepted.
                from canvas import Canvas
                fresh = Canvas()
                real_ask = messagebox.askyesno
                messagebox.askyesno = lambda *a, **k: True
                try:
                    probe = Canvas.load_project(saved)
                    fresh.replace_with(probe)
                finally:
                    messagebox.askyesno = real_ask
                self.assertEqual(fresh.stroke_count, 1)
                # Second tick without changes writes nothing new.
                mtime = saved.stat().st_mtime_ns
                self.app._autosave_tick()
                self.assertEqual(saved.stat().st_mtime_ns, mtime)
            finally:
                config.AUTOSAVE_PATH = old_path


if __name__ == "__main__":
    unittest.main()
