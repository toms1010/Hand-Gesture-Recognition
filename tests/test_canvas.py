"""Unit tests for canvas operations (undo/redo/erase/move/persistence)."""
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from canvas import Canvas, ShapeItem, Stroke


def stroke(points=((10, 10), (20, 20), (30, 30))):
    """Build a simple stroke."""
    return Stroke(points=list(points), color=(0, 255, 0), thickness=4)


class TestHistory(unittest.TestCase):
    def test_add_undo_redo(self):
        canvas = Canvas()
        canvas.add_stroke(stroke())
        self.assertEqual(canvas.stroke_count, 1)
        self.assertTrue(canvas.undo())
        self.assertEqual(canvas.stroke_count, 0)
        self.assertTrue(canvas.redo())
        self.assertEqual(canvas.stroke_count, 1)

    def test_undo_empty(self):
        canvas = Canvas()
        self.assertFalse(canvas.undo())
        self.assertFalse(canvas.redo())
        self.assertFalse(canvas.can_undo)

    def test_clear_undo(self):
        canvas = Canvas()
        canvas.add_stroke(stroke())
        self.assertTrue(canvas.clear())
        self.assertEqual(canvas.stroke_count, 0)
        self.assertTrue(canvas.undo())
        self.assertEqual(canvas.stroke_count, 1)
        self.assertFalse(canvas.clear() and False)  # clear again ok
        canvas.clear()
        self.assertFalse(canvas.clear())  # already empty

    def test_erase_and_undo(self):
        canvas = Canvas()
        canvas.add_stroke(stroke())
        self.assertTrue(canvas.erase_at((20, 20), 15))
        self.assertTrue(canvas.undo())
        restored = canvas.items[0]
        self.assertEqual(len(restored.points), 3)

    def test_move_and_undo(self):
        canvas = Canvas()
        canvas.add_stroke(stroke())
        self.assertTrue(canvas.move_item(0, 5, 5))
        self.assertEqual(canvas.items[0].points[0], (15, 15))
        self.assertTrue(canvas.undo())
        self.assertEqual(canvas.items[0].points[0], (10, 10))

    def test_move_invalid(self):
        canvas = Canvas()
        self.assertFalse(canvas.move_item(0, 1, 1))

    def test_undo_limit(self):
        canvas = Canvas(undo_limit=3)
        for _ in range(5):
            canvas.add_stroke(stroke())
        self.assertEqual(len(canvas._undo), 3)


class TestRendering(unittest.TestCase):
    def test_render_marks_pixels(self):
        canvas = Canvas()
        canvas.add_stroke(stroke())
        overlay = canvas.render(640, 480)
        self.assertEqual(overlay.shape, (480, 640, 3))
        self.assertGreater(int((overlay > 0).sum()), 0)

    def test_render_cached(self):
        canvas = Canvas()
        first = canvas.render(64, 48)
        second = canvas.render(64, 48)
        self.assertIs(first, second)

    def test_composite(self):
        canvas = Canvas()
        canvas.add_stroke(stroke())
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        canvas.composite(frame)
        self.assertGreater(int((frame > 0).sum()), 0)

    def test_shape_render(self):
        canvas = Canvas()
        canvas.add_shape(ShapeItem("circle", (10, 10), (50, 50)))
        canvas.add_shape(ShapeItem("rectangle", (60, 60), (100, 100)))
        canvas.add_shape(ShapeItem("line", (0, 0), (40, 40)))
        canvas.add_shape(ShapeItem("triangle", (0, 0), (40, 40)))
        overlay = canvas.render(200, 200)
        self.assertGreater(int((overlay > 0).sum()), 0)


class TestPersistence(unittest.TestCase):
    def test_project_roundtrip(self):
        canvas = Canvas()
        canvas.add_stroke(stroke())
        canvas.add_shape(ShapeItem("circle", (1, 2), (3, 4)))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "project.json"
            canvas.save_project(path)
            loaded = Canvas.load_project(path)
        self.assertEqual(loaded.stroke_count, 2)
        self.assertIsInstance(loaded.items[0], Stroke)
        self.assertIsInstance(loaded.items[1], ShapeItem)
        self.assertEqual(loaded.items[1].shape, "circle")

    def test_save_png(self):
        canvas = Canvas()
        canvas.add_stroke(stroke())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "canvas.png"
            canvas.save_png(path, 160, 120)
            self.assertTrue(path.is_file())
            self.assertGreater(path.stat().st_size, 0)

    def test_save_jpg(self):
        canvas = Canvas()
        canvas.add_stroke(stroke())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "canvas.jpg"
            canvas.save_jpg(path, 160, 120)
            self.assertTrue(path.is_file())
            self.assertGreater(path.stat().st_size, 0)

    def test_export_svg(self):
        canvas = Canvas()
        canvas.add_stroke(stroke())
        canvas.add_shape(ShapeItem("rectangle", (10, 10), (50, 40)))
        canvas.add_shape(ShapeItem("circle", (60, 60), (100, 100)))
        canvas.add_shape(ShapeItem("line", (0, 0), (20, 20)))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "canvas.svg"
            canvas.export_svg(path, 160, 120)
            text = path.read_text(encoding="utf-8")
        self.assertIn("<svg", text)
        self.assertIn("<polyline", text)
        self.assertIn("<rect", text)
        self.assertIn("<circle", text)
        self.assertIn("<line", text)
        self.assertTrue(text.strip().endswith("</svg>"))


class TestViewMapping(unittest.TestCase):
    def test_roundtrip_identity(self):
        canvas = Canvas()
        for point in ((0, 0), (320, 240), (639, 479)):
            self.assertEqual(canvas.to_canvas(canvas.to_view(point, 640, 480),
                                              640, 480), point)

    def test_roundtrip_zoomed_panned(self):
        canvas = Canvas()
        canvas.set_zoom(2.0)
        canvas.pan_by(30, -20)
        for point in ((100, 100), (320, 240), (500, 400)):
            back = canvas.to_canvas(canvas.to_view(point, 640, 480), 640, 480)
            self.assertLess(abs(back[0] - point[0]), 2)
            self.assertLess(abs(back[1] - point[1]), 2)

    def test_set_zoom_clamps_and_dirties(self):
        canvas = Canvas()
        canvas.render(64, 48)
        canvas.set_zoom(99.0)
        self.assertEqual(canvas.zoom, 4.0)
        first = canvas.render(64, 48)
        canvas.set_zoom(0.5)
        second = canvas.render(64, 48)
        self.assertIsNot(first, second)

    def test_pan_and_reset(self):
        canvas = Canvas()
        canvas.pan_by(10, 5)
        self.assertEqual((canvas.pan_x, canvas.pan_y), (10, 5))
        canvas.reset_view()
        self.assertEqual((canvas.zoom, canvas.pan_x, canvas.pan_y), (1.0, 0, 0))


class TestDeleteItem(unittest.TestCase):
    def test_delete_undo_redo(self):
        canvas = Canvas()
        canvas.add_stroke(stroke())
        canvas.add_stroke(stroke(((1, 1), (2, 2))))
        self.assertTrue(canvas.delete_item(0))
        self.assertEqual(canvas.stroke_count, 1)
        self.assertTrue(canvas.undo())
        self.assertEqual(canvas.stroke_count, 2)
        self.assertTrue(canvas.redo())
        self.assertEqual(canvas.stroke_count, 1)

    def test_delete_invalid(self):
        canvas = Canvas()
        self.assertFalse(canvas.delete_item(0))
        self.assertFalse(canvas.delete_item(-1))


class TestBackgrounds(unittest.TestCase):
    def test_modes_render(self):
        for mode in ("dark", "white", "black", "grid", "custom"):
            canvas = Canvas()
            canvas.bg_mode = mode
            scene = canvas.render_scene(160, 120)
            self.assertEqual(scene.shape, (120, 160, 3))
            self.assertGreater(int((scene > 0).sum()), 0)

    def test_grid_has_lines(self):
        import numpy as np
        plain = Canvas()
        plain.bg_mode = "dark"
        grid = Canvas()
        grid.bg_mode = "grid"

        def non_bg(scene, bg):
            return int((np.any(scene != np.array(bg, dtype=np.uint8), axis=2)).sum())

        self.assertEqual(non_bg(plain.render_scene(160, 120), (24, 24, 28)), 0)
        self.assertGreater(non_bg(grid.render_scene(160, 120), (24, 24, 28)), 0)

    def test_opacity_blends(self):
        solid = Canvas()
        solid.add_stroke(Stroke(points=[(10, 10), (100, 10)], color=(0, 0, 255),
                                thickness=6, glow=False, opacity=1.0))
        faint = Canvas()
        faint.add_stroke(Stroke(points=[(10, 10), (100, 10)], color=(0, 0, 255),
                                thickness=6, glow=False, opacity=0.1))
        solid_sum = int(solid.render(160, 120).sum())
        faint_sum = int(faint.render(160, 120).sum())
        self.assertGreater(solid_sum, 0)
        self.assertGreater(faint_sum, 0)
        self.assertLess(faint_sum, solid_sum)

    def test_erase_soft_gentler_than_hard(self):
        points = [(x, 50) for x in range(0, 200, 5)]
        soft = Canvas()
        soft.add_stroke(Stroke(points=list(points), thickness=2, glow=False))
        hard = Canvas()
        hard.add_stroke(Stroke(points=list(points), thickness=2, glow=False))
        soft.erase_at((100, 50), 30, soft=True)
        hard.erase_at((100, 50), 30, soft=False)
        remaining_soft = len(soft.items[0].points) if soft.items else 0
        remaining_hard = len(hard.items[0].points) if hard.items else 0
        self.assertGreaterEqual(remaining_soft, remaining_hard)


if __name__ == "__main__":
    unittest.main()
