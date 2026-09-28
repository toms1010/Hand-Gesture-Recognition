"""Interaction controller: gestures + pointers -> canvas actions.

Single-hand intents (from :mod:`gesture_engine` actions):

* DRAW ............ freehand stroke follows the index fingertip
* SHAPE ........... live shape preview follows the hand; PINCH or
  CONFIRM (thumbs-up) stamps it to the canvas
* ERASE ........... fist erases under the index fingertip
* PAUSE ........... open palm: lift the pen, keep everything
* PINCH ........... in SELECT tool: grab/drag nearest stroke;
  otherwise stamp the active preview (or draw a dot)
* CONFIRM ......... stamp the active preview

Two hands (preserved original overlays + studio extras):

* 5+5 / 2+2 / 3+3 . live LINE / SPHERE / RECTANGLE overlay; ``stamp_special()``
  commits the current special to the canvas
* wrist-span change .. smooth canvas zoom
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

import config
from animation import AnimationManager
from canvas import Canvas, ShapeItem, Stroke
from finger_detector import is_pinch
from geometry import to_pixel, wrist_span
from gesture_engine import (
    ACTION_CONFIRM,
    ACTION_DRAW,
    ACTION_ERASE,
    ACTION_PAUSE,
    ACTION_PINCH,
    ACTION_SHAPE,
    LINE,
    RECTANGLE,
    SPHERE,
    GestureResult,
)
from hand_tracker import INDEX_TIP
from smoothing import PointSmoother, catmull_rom, interpolate_segment
from tools import SHAPE_TOOLS, Tool


@dataclass
class ShapePreview:
    """Ephemeral (not yet committed) shape."""

    shape: str  # circle|rectangle|line|triangle|sphere
    p1: Tuple[int, int] = (0, 0)
    p2: Tuple[int, int] = (0, 0)


@dataclass
class ControllerHint:
    """One-line status for the UI status bar."""

    text: str = ""
    sticky: str = ""


class InteractionController:
    """Turns per-frame hands + gesture results into canvas edits."""

    def __init__(self, canvas: Canvas, tool: Tool = Tool.PENCIL):
        self.canvas = canvas
        self.tool = tool
        self.shape_tool: Tool = Tool.CIRCLE
        self.brush_size = config.BRUSH_SIZE
        self.brush_color = tuple(config.BRUSH_COLOR)
        self.brush_opacity = float(getattr(config, "BRUSH_OPACITY", 1.0))
        self.glow = config.GLOW_ENABLED
        self.eraser_size = config.ERASER_SIZE
        self.snap_to_grid = bool(getattr(config, "SNAP_TO_GRID", False))
        self.animations = AnimationManager()
        self.pointer = PointSmoother(
            smoothing=float(getattr(config, "SMOOTHING", 0.7)),
            dead_zone_px=float(getattr(config, "DEAD_ZONE_PX", 2.0)))
        self.preview: Optional[ShapePreview] = None
        self.hint = ControllerHint()
        # Active freehand stroke (built incrementally, committed on lift).
        self._active_points: List[Tuple[int, int]] = []
        self._active_widths: List[float] = []
        self._drawing = False
        # Smoothed cursor in view pixels for the renderer (None = hidden).
        self.cursor_px: Optional[Tuple[int, int]] = None
        self.cursor_state: str = "idle"  # idle|hover|drawing|pinch|erasing
        # Pinch edge detection (press vs hold).
        self._pinch_held = False
        # Confirm edge detection.
        self._confirm_held = False
        # SELECT drag state.
        self._drag_index: Optional[int] = None
        self._drag_last: Optional[Tuple[int, int]] = None
        # Two-hand zoom smoothing.
        self._smooth_span: Optional[float] = None
        self._last_zoom: float = canvas.zoom

    def _animations_on(self) -> bool:
        return getattr(config, "ANIMATIONS", "full") != "off"

    # --- tool management ---
    def set_tool(self, tool: Tool) -> None:
        """Switch tool; ends any in-progress stroke/preview/drag."""
        self.tool = tool
        self._end_active_stroke(commit=True)
        self.preview = None
        self.pointer.reset()
        self.cursor_state = "idle"
        self._drag_index = None
        self._pinch_held = False

    def cycle_shape_tool(self) -> Tool:
        """Cycle the shape used by the two-finger SHAPE gesture."""
        idx = SHAPE_TOOLS.index(self.shape_tool) if self.shape_tool in SHAPE_TOOLS else -1
        self.shape_tool = SHAPE_TOOLS[(idx + 1) % len(SHAPE_TOOLS)]
        return self.shape_tool

    def cancel_active(self) -> None:
        """Cancel the in-progress stroke/preview (Esc): nothing is committed."""
        self._drawing = False
        self._active_points = []
        self._active_widths = []
        self.preview = None
        self.pointer.reset()
        self.cursor_px = None
        self.cursor_state = "idle"
        self._drag_index = None
        self.hint.text = "Cancelled"

    # --- per-frame update ---
    def update(self, hands: list, result: GestureResult,
               width: int, height: int) -> ControllerHint:
        """Apply one frame of hands + stabilized result to the canvas."""
        self.hint = ControllerHint()
        if result.hand_count >= 2 and len(hands) >= 2:
            self._update_two_hands(hands, result, width, height)
        elif result.hand_count == 1 and hands:
            self._update_single_hand(hands[0], result, width, height)
        else:
            self._end_active_stroke(commit=True)
            self.preview = None
            self._drag_index = None
            self._pinch_held = False
            self._confirm_held = False
            self._smooth_span = None
            self.pointer.reset()
            self.cursor_px = None
            self.cursor_state = "idle"
        return self.hint

    # --- single hand ---
    def _tip_px(self, hand, width: int, height: int) -> Tuple[int, int]:
        return to_pixel(hand[INDEX_TIP], width, height)

    def _smooth_tip(self, tip: Tuple[int, int]) -> Tuple[int, int]:
        """Dead-zone + adaptive-exponential smoothing of the raw tip."""
        sx, sy = self.pointer.update((float(tip[0]), float(tip[1])))
        return (int(round(sx)), int(round(sy)))

    def _to_canvas_px(self, view_tip: Tuple[int, int],
                      width: int, height: int) -> Tuple[int, int]:
        """Map a view-space tip into canvas space (zoom/pan aligned)."""
        return self.canvas.to_canvas(view_tip, width, height)

    def _cursor(self, view_tip: Tuple[int, int], state: str,
                pinch: bool = False) -> None:
        self.cursor_px = view_tip
        self.cursor_state = state
        if pinch and self._animations_on():
            self.animations.pulse("pinch")

    def _update_single_hand(self, hand, result: GestureResult,
                            width: int, height: int) -> None:
        raw_tip = self._tip_px(hand, width, height)
        tip = self._smooth_tip(raw_tip)
        canvas_tip = self._to_canvas_px(tip, width, height)
        action = result.action if result.is_stable else ACTION_PAUSE
        pinch_now = result.pinch or is_pinch(hand)

        # Confirm edge (thumbs-up): stamp preview.
        if action == ACTION_CONFIRM and result.is_stable:
            self._cursor(tip, "pinch", pinch=True)
            if not self._confirm_held:
                self._confirm_held = True
                if not self.stamp_preview(width, height):
                    self.hint.text = "Nothing to confirm"
                else:
                    self.hint.text = "Stamped"
            self._end_active_stroke(commit=True)
            return
        if action != ACTION_CONFIRM:
            self._confirm_held = False

        if action == ACTION_DRAW and self.tool in (Tool.PENCIL, Tool.BRUSH):
            self._drag_index = None
            self._cursor(tip, "drawing", pinch=pinch_now)
            self._draw_point(tip, canvas_tip)
            self.hint.text = "Drawing - lift hand or show palm to pause"
        elif action == ACTION_SHAPE:
            self._end_active_stroke(commit=True)
            self._update_shape_preview(hand, tip, width, height)
            self._cursor(tip, "pinch" if pinch_now else "hover", pinch=pinch_now)
            if pinch_now and not self._pinch_held:
                self._pinch_held = True
                if self.stamp_preview(width, height):
                    self.hint.text = "Shape stamped (pinch)"
            elif not pinch_now:
                self._pinch_held = False
                self.hint.text = "Pinch or thumbs-up to stamp"
        elif action == ACTION_ERASE or self.tool == Tool.ERASER:
            self._end_active_stroke(commit=True)
            self.preview = None
            self._cursor(tip, "erasing")
            self.canvas.erase_at(canvas_tip, self.eraser_size,
                                 soft=bool(getattr(config, "ERASER_SOFT", True)))
            self.hint.text = "Erasing"
        elif action == ACTION_PINCH:
            if self.tool == Tool.SELECT:
                self._cursor(tip, "pinch", pinch=pinch_now)
                self._update_select_drag(canvas_tip, pinch_now)
            else:
                self._end_active_stroke(commit=True)
                self._cursor(tip, "pinch", pinch=pinch_now)
                if pinch_now and not self._pinch_held:
                    self._pinch_held = True
                    if self.preview:
                        self.stamp_preview(width, height)
                    else:
                        self._draw_point(tip, canvas_tip, commit_now=True)
                elif not pinch_now:
                    self._pinch_held = False
        else:  # PAUSE / IDLE / unstable
            self._end_active_stroke(commit=True)
            self._drag_index = None
            self._cursor(tip, "hover")
            if action == ACTION_PAUSE:
                self.hint.text = "Paused (open palm)"

    def _pressure_width(self, speed_px: float) -> float:
        """Velocity-based brush width: fast = thinner, slow = fuller."""
        base = float(self.brush_size if self.tool != Tool.BRUSH
                     else self.brush_size + 4)
        factor = 1.15 - min(1.0, max(0.0, speed_px / 45.0)) * 0.5
        return max(1.0, base * factor)

    def _draw_point(self, tip: Tuple[int, int], canvas_tip: Tuple[int, int],
                    commit_now: bool = False) -> None:
        import time
        if not self._drawing:
            self._drawing = True
            self._active_points = []
            self._active_widths = []
            if self._animations_on():
                self.animations.pulse("draw_start")
        if not self._active_points or self._active_points[-1] != canvas_tip:
            if self._active_points:
                for ix, iy in interpolate_segment(
                        tuple(float(v) for v in self._active_points[-1]),
                        tuple(float(v) for v in canvas_tip))[1:]:
                    self._active_points.append((int(round(ix)), int(round(iy))))
                    self._active_widths.append(
                        self._pressure_width(self.pointer.speed))
            else:
                self._active_points.append(canvas_tip)
                self._active_widths.append(
                    self._pressure_width(self.pointer.speed))
        if commit_now:
            self._end_active_stroke(commit=True)

    def _end_active_stroke(self, commit: bool) -> None:
        import time
        if self._drawing and commit and len(self._active_points) >= 1:
            tool_value = self.tool.value if self.tool in (Tool.PENCIL, Tool.BRUSH) \
                else Tool.PENCIL.value
            points = list(self._active_points)
            widths = list(self._active_widths)
            if self.tool == Tool.BRUSH and len(points) >= 4:
                xs = [p[0] for p in points]
                ys = [p[1] for p in points]
                bounds = (min(xs) - 2.0, min(ys) - 2.0,
                          max(xs) + 2.0, max(ys) + 2.0)
                resampled = catmull_rom(
                    [(float(x), float(y)) for x, y in points], bounds=bounds)
                points = [(int(round(x)), int(round(y))) for x, y in resampled]
                widths = []  # resampled geometry: fall back to base width
            self.canvas.add_stroke(Stroke(
                points=points, color=self.brush_color,
                thickness=self.brush_size if self.tool != Tool.BRUSH else self.brush_size + 4,
                glow=self.glow, tool=tool_value, widths=widths,
                opacity=self.brush_opacity, timestamp=time.time()))
            if config.SHAPE_RECOGNITION:
                self.canvas.snap_last_stroke()
        self._drawing = False
        self._active_points = []
        self._active_widths = []
        self.pointer.reset()

    def _snap_grid(self, point: Tuple[int, int]) -> Tuple[int, int]:
        step = max(4, int(self.canvas.grid_size))
        return (int(round(point[0] / step) * step),
                int(round(point[1] / step) * step))

    def _update_shape_preview(self, hand, tip: Tuple[int, int],
                              width: int, height: int) -> None:
        from geometry import bounding_box
        box = bounding_box([hand], width, height)
        if box is None:
            self.preview = None
            return
        xmin, ymin, xmax, ymax = box
        shape = self.shape_tool.value if self.shape_tool in SHAPE_TOOLS else "circle"
        if shape == "line":
            self.preview = ShapePreview("line", (xmin, (ymin + ymax) // 2),
                                        (xmax, (ymin + ymax) // 2))
        elif shape == "triangle":
            self.preview = ShapePreview("triangle", (xmin, ymin), (xmax, ymax))
        elif shape == "rectangle":
            self.preview = ShapePreview("rectangle", (xmin, ymin), (xmax, ymax))
        else:
            self.preview = ShapePreview("circle", (xmin, ymin), (xmax, ymax))
        if self.snap_to_grid and self.canvas.bg_mode == "grid":
            self.preview.p1 = self._snap_grid(self.preview.p1)
            self.preview.p2 = self._snap_grid(self.preview.p2)
        _ = tip

    # --- select / move ---
    @property
    def drag_index(self) -> Optional[int]:
        """Index of the canvas item currently being dragged (if any)."""
        return self._drag_index

    def _nearest_item(self, point: Tuple[int, int], max_dist: float = 40.0) -> Optional[int]:
        best, best_d = None, max_dist
        for i, item in enumerate(self.canvas.items):
            if isinstance(item, Stroke) and item.points:
                d = min(math.hypot(x - point[0], y - point[1]) for x, y in item.points)
            else:
                corners = self.canvas.shape_corners(item)
                d = min(math.hypot(x - point[0], y - point[1]) for x, y in corners)
            if d < best_d:
                best, best_d = i, d
        return best

    def _update_select_drag(self, tip: Tuple[int, int], pinch_now: bool) -> None:
        if pinch_now and not self._pinch_held:
            self._pinch_held = True
            self._drag_index = self._nearest_item(tip)
            self._drag_last = tip
            self.hint.text = ("Grabbed item" if self._drag_index is not None
                              else "Pinch near a stroke to grab")
        elif pinch_now and self._pinch_held:
            if self._drag_index is not None and self._drag_last is not None:
                dx, dy = tip[0] - self._drag_last[0], tip[1] - self._drag_last[1]
                if dx or dy:
                    self.canvas.move_item(self._drag_index, dx, dy)
                    # Collapse consecutive drag moves into one undo step.
                    self.canvas.coalesce_last_move()
                self._drag_last = tip
                self.hint.text = "Moving - release pinch to drop"
        else:
            self._pinch_held = False
            self._drag_index = None
            self._drag_last = None

    # --- two hands ---
    def _update_two_hands(self, hands: list, result: GestureResult,
                          width: int, height: int) -> None:
        self._end_active_stroke(commit=True)
        self.preview = None
        try:
            span = wrist_span(hands[0], hands[1])
        except (IndexError, AttributeError):
            return
        if self._smooth_span is None:
            self._smooth_span = span
        elif abs(span - self._smooth_span) > config.ZOOM_DEADZONE:
            alpha = config.ZOOM_SMOOTHING
            self._smooth_span += alpha * (span - self._smooth_span)
        # Zoom follows the smoothed span relative to a neutral reference:
        # hands far apart -> zoom in, together -> zoom out.
        target = 1.0 + (self._smooth_span - 0.35) * 2.0
        target = min(3.0, max(0.5, target))
        if abs(target - self.canvas.zoom) > 0.01:
            self.canvas.set_zoom(round(target, 2))
        if result.name in (LINE, SPHERE, RECTANGLE) and result.is_stable:
            self.hint.text = f"Two-hand {result.name} - press SPACE to stamp"
        else:
            self.hint.text = f"Zoom {self.canvas.zoom:.2f}x"

    # --- stamping ---
    def stamp_preview(self, width: int = 0, height: int = 0) -> bool:
        """Commit the single-hand shape preview to the canvas.

        Preview corners live in view pixels; they are mapped into canvas
        space so the stamp lands where the preview was shown.
        """
        if not self.preview:
            return False
        p1, p2 = self.preview.p1, self.preview.p2
        if width > 0 and height > 0:
            p1 = self.canvas.to_canvas(p1, width, height)
            p2 = self.canvas.to_canvas(p2, width, height)
        self.canvas.add_shape(ShapeItem(
            shape=self.preview.shape, p1=p1, p2=p2,
            color=self.brush_color, thickness=max(self.brush_size, 3),
            glow=self.glow, opacity=self.brush_opacity))
        self.preview = None
        if self._animations_on():
            self.animations.pulse("stamp")
        return True

    def stamp_two_hand(self, hands: list, name: str,
                       width: int, height: int) -> bool:
        """Commit a stabilized two-hand gesture as a canvas shape.

        Landmarks are mapped into canvas space (zoom/pan aligned).
        """
        if hands is None or len(hands) < 2 or name not in (LINE, SPHERE, RECTANGLE):
            return False
        from geometry import bounding_box, to_pixel
        to_canvas = lambda p: self.canvas.to_canvas(p, width, height)
        thick = max(self.brush_size, 3)
        if name == LINE:
            try:
                p1 = to_canvas(to_pixel(hands[0][0], width, height))
                p2 = to_canvas(to_pixel(hands[1][0], width, height))
            except (IndexError, AttributeError):
                return False
            self.canvas.add_shape(ShapeItem(
                "line", p1, p2, self.brush_color, thick, self.glow,
                opacity=self.brush_opacity))
        elif name == SPHERE:
            box = bounding_box(hands, width, height)
            if box is None:
                return False
            xmin, ymin, xmax, ymax = box
            self.canvas.add_shape(ShapeItem(
                "sphere", to_canvas((xmin, ymin)), to_canvas((xmax, ymax)),
                self.brush_color, thick, self.glow, opacity=self.brush_opacity))
        else:
            box = bounding_box(hands, width, height)
            if box is None:
                return False
            xmin, ymin, xmax, ymax = box
            self.canvas.add_shape(ShapeItem(
                "rectangle", to_canvas((xmin, ymin)), to_canvas((xmax, ymax)),
                self.brush_color, thick, self.glow, opacity=self.brush_opacity))
        self.hint.text = f"{name} stamped"
        if self._animations_on():
            self.animations.pulse("stamp")
        return True
