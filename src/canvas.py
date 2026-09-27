"""Persistent vector drawing canvas with undo/redo and PNG/project I/O.

Strokes are stored as vectors (never full-frame copies), so history is
cheap. Rendering rasterizes onto a transparent overlay composited over
the camera feed each frame; re-rendering happens only when dirty.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np

import config
from tools import Tool

Color = Tuple[int, int, int]
PixelPoint = Tuple[int, int]


@dataclass
class Stroke:
    """One freehand stroke (vector data; rendering never mutates it)."""

    points: List[PixelPoint] = field(default_factory=list)
    color: Color = (43, 255, 255)
    thickness: int = 6
    glow: bool = True
    tool: str = Tool.PENCIL.value
    is_eraser: bool = False
    widths: List[float] = field(default_factory=list)  # per-point px (velocity)
    opacity: float = 1.0  # 0.0-1.0
    timestamp: float = 0.0  # seconds since epoch (creation time)


@dataclass
class ShapeItem:
    """One stamped geometric shape."""

    shape: str = "circle"  # circle|rectangle|line|triangle|sphere
    p1: PixelPoint = (0, 0)
    p2: PixelPoint = (0, 0)
    color: Color = (43, 255, 255)
    thickness: int = 3
    glow: bool = True
    opacity: float = 1.0


def _dist_point_to_segment(px: float, py: float, ax: float, ay: float,
                           bx: float, by: float) -> float:
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_sq))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


class Canvas:
    """Vector canvas: items + command history + cached raster overlay."""

    def __init__(self, undo_limit: int = config.UNDO_LIMIT):
        self.items: List[object] = []
        self._undo: List[tuple] = []
        self._redo: List[tuple] = []
        self.undo_limit = max(1, int(undo_limit))
        self.zoom: float = 1.0
        self.pan_x: int = 0
        self.pan_y: int = 0
        self.brush_size: int = config.BRUSH_SIZE
        self.brush_color: Color = tuple(config.BRUSH_COLOR)
        self.glow: bool = config.GLOW_ENABLED
        self.antialias: bool = config.ANTIALIAS
        self.bg_mode: str = getattr(config, "CANVAS_BG_MODE", "dark")
        self.bg_custom: Color = tuple(getattr(config, "CANVAS_BG_CUSTOM",
                                              config.CANVAS_BACKGROUND))
        self.grid_size: int = getattr(config, "GRID_SIZE", 32)
        self._dirty = True
        self._cached_overlay: Optional[np.ndarray] = None
        self._cached_key: tuple = ()
        self.revision: int = 0  # increments on every mutation (autosave key)

    # --- mutation (each pushes one undo command) ---
    def _push_undo(self, command: tuple) -> None:
        self._undo.append(command)
        del self._undo[:-self.undo_limit]
        self._redo.clear()
        self._dirty = True
        self.revision += 1

    # --- view mapping (keeps fingertip aligned while zoomed/panned) ---
    def _view_params(self, width: int, height: int) -> Tuple[int, int]:
        return width // 2 + self.pan_x, height // 2 + self.pan_y

    def to_view(self, point: PixelPoint, width: int, height: int) -> PixelPoint:
        """Canvas coords -> displayed pixel coords (zoom + pan about center)."""
        cx, cy = self._view_params(width, height)
        x, y = point
        return (int(cx + (x - width // 2) * self.zoom),
                int(cy + (y - height // 2) * self.zoom))

    def to_canvas(self, point: PixelPoint, width: int, height: int) -> PixelPoint:
        """Displayed pixel coords -> canvas coords (inverse of to_view)."""
        cx, cy = self._view_params(width, height)
        x, y = point
        zoom = self.zoom if self.zoom != 0 else 1.0
        return (int(width // 2 + (x - cx) / zoom),
                int(height // 2 + (y - cy) / zoom))

    def set_zoom(self, zoom: float) -> None:
        """Set zoom (0.25-4.0) and invalidate the render cache."""
        zoom = min(4.0, max(0.25, float(zoom)))
        if abs(zoom - self.zoom) > 1e-9:
            self.zoom = zoom
            self._dirty = True

    def pan_by(self, dx: int, dy: int) -> None:
        """Translate the view and invalidate the render cache."""
        if dx or dy:
            self.pan_x += int(dx)
            self.pan_y += int(dy)
            self._dirty = True

    def reset_view(self) -> None:
        """Reset zoom + pan."""
        self.zoom, self.pan_x, self.pan_y = 1.0, 0, 0
        self._dirty = True

    # --- mutation (each pushes one undo command) ---
    def _push_undo(self, command: tuple) -> None:
        self._undo.append(command)
        del self._undo[:-self.undo_limit]
        self._redo.clear()
        self._dirty = True

    def add_stroke(self, stroke: Stroke) -> int:
        """Append a finished stroke; returns its index. Ignores empties."""
        if not stroke.points:
            return -1
        self.items.append(stroke)
        self._push_undo(("add", stroke))
        return len(self.items) - 1

    def add_shape(self, item: ShapeItem) -> int:
        """Stamp a shape; returns its index."""
        self.items.append(item)
        self._push_undo(("add", item))
        return len(self.items) - 1

    def erase_at(self, point: PixelPoint, radius: int, soft: bool = True) -> bool:
        """Erase stroke points within ``radius`` px. Returns True if changed.

        Soft mode uses a gentler effective radius; hard mode removes the
        full radius at once.
        """
        if radius <= 0:
            return False
        effective = int(radius * 0.6) if soft else radius
        backup, removed = self._erase_no_history(point, max(1, effective))
        if backup is None:
            return False
        self._push_undo(("erase", (point, effective, backup, removed)))
        return True

    def _erase_no_history(self, point: PixelPoint, radius: int):
        """Erase without touching history; returns (backup, removed) or (None, None)."""
        backup = [(item, list(item.points), list(item.widths)) for item in self.items
                  if isinstance(item, Stroke)]
        removed: List[object] = []
        changed = False
        for item in self.items:
            if isinstance(item, Stroke):
                before = len(item.points)
                has_widths = bool(item.widths) and len(item.widths) == before
                pairs = list(zip(item.points,
                                 item.widths if has_widths else [None] * before))
                kept = [(p, w) for p, w in pairs
                        if math.hypot(p[0] - point[0], p[1] - point[1]) > radius]
                if len(kept) != before:
                    changed = True
                item.points = [p for p, _ in kept]
                if has_widths:
                    item.widths = [w for _, w in kept]
                if not item.points:
                    removed.append(item)
            elif isinstance(item, ShapeItem):
                corners = self.shape_corners(item)
                if any(math.hypot(c[0] - point[0], c[1] - point[1]) <= radius + item.thickness
                       for c in corners):
                    removed.append(item)
                    changed = True
        for item in removed:
            self.items.remove(item)
        if not changed:
            return None, None
        self._dirty = True
        return backup, removed

    def move_item(self, index: int, dx: int, dy: int) -> bool:
        """Translate item ``index`` by (dx, dy) pixels."""
        if not (0 <= index < len(self.items)):
            return False
        item = self.items[index]
        if isinstance(item, Stroke):
            item.points = [(x + dx, y + dy) for x, y in item.points]
        elif isinstance(item, ShapeItem):
            item.p1 = (item.p1[0] + dx, item.p1[1] + dy)
            item.p2 = (item.p2[0] + dx, item.p2[1] + dy)
        else:
            return False
        self._push_undo(("move", (item, -dx, -dy)))
        return True

    def clear(self) -> bool:
        """Remove everything (undoable). Returns False when already empty."""
        if not self.items:
            return False
        snapshot = list(self.items)
        self.items.clear()
        self._push_undo(("clear", snapshot))
        return True

    def delete_item(self, index: int) -> bool:
        """Delete one item (undoable). Returns False for bad indices."""
        if not (0 <= index < len(self.items)):
            return False
        item = self.items.pop(index)
        self._push_undo(("delete", (index, item)))
        return True

    # --- undo / redo (snapshot-light: re-apply inverse ops) ---
    def undo(self) -> bool:
        """Undo one command. Returns False when history is empty."""
        if not self._undo:
            return False
        command = self._undo.pop()
        kind, payload = command
        if kind == "add":
            if payload in self.items:
                self.items.remove(payload)
            self._redo.append(command)
        elif kind == "clear":
            self.items.extend(payload)
            self._redo.append(command)
        elif kind == "delete":
            index, item = payload
            self.items.insert(min(index, len(self.items)), item)
            self._redo.append(command)
        elif kind == "erase":
            _point, _radius, backup, removed = payload
            for entry in backup:
                item, old_points = entry[0], entry[1]
                old_widths = entry[2] if len(entry) > 2 else []
                if isinstance(item, Stroke):
                    item.points = list(old_points)
                    if old_widths:
                        item.widths = list(old_widths)
            for item in removed:
                if item not in self.items:
                    self.items.append(item)
            self._redo.append(command)
        elif kind == "move":
            item, (dx, dy) = payload[0], (payload[1], payload[2])
            self._translate_no_history(item, dx, dy)
            self._redo.append(("move", (item, -dx, -dy)))
        self._dirty = True
        self.revision += 1
        return True

    def redo(self) -> bool:
        """Redo one undone command. Returns False when empty."""
        if not self._redo:
            return False
        command = self._redo.pop()
        kind, payload = command
        if kind == "add":
            self.items.append(payload)
            self._undo.append(command)
        elif kind == "clear":
            self.items.clear()
            self._undo.append(command)
        elif kind == "delete":
            index, _item = payload
            if 0 <= index < len(self.items):
                del self.items[index]
            self._undo.append(command)
        elif kind == "erase":
            point, radius, _backup, _removed = payload
            backup, removed = self._erase_no_history(point, radius)
            if backup is not None:
                self._undo.append(("erase", (point, radius, backup, removed)))
            else:
                self._undo.append(command)
        elif kind == "move":
            item, (dx, dy) = payload[0], (payload[1], payload[2])
            self._translate_no_history(item, dx, dy)
            self._undo.append(("move", (item, -dx, -dy)))
        self._dirty = True
        self.revision += 1
        return True

    @staticmethod
    def _translate_no_history(item: object, dx: int, dy: int) -> None:
        if isinstance(item, Stroke):
            item.points = [(x + dx, y + dy) for x, y in item.points]
        elif isinstance(item, ShapeItem):
            item.p1 = (item.p1[0] + dx, item.p1[1] + dy)
            item.p2 = (item.p2[0] + dx, item.p2[1] + dy)

    @property
    def can_undo(self) -> bool:
        """Whether undo history is non-empty."""
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        """Whether redo history is non-empty."""
        return bool(self._redo)

    @property
    def stroke_count(self) -> int:
        """Number of items on the canvas."""
        return len(self.items)

    def replace_with(self, other: "Canvas") -> None:
        """Replace contents with another canvas (for project loading)."""
        self.items = list(other.items)
        self.zoom = other.zoom
        self._undo.clear()
        self._redo.clear()
        self._dirty = True
        self.revision += 1

    # --- rendering ---
    def shape_corners(self, item: ShapeItem) -> List[PixelPoint]:
        """Corner points of a shape item (public helper for hit-testing)."""
        return self._shape_corners(item)

    def coalesce_last_move(self) -> None:
        """Merge the last two same-item move commands into one undo step."""
        if len(self._undo) < 2:
            return
        last = self._undo.pop()
        prev = self._undo.pop()
        if (last[0] == "move" and prev[0] == "move" and last[1][0] is prev[1][0]):
            merged = ("move", (last[1][0], last[1][1] + prev[1][1],
                               last[1][2] + prev[1][2]))
            self._undo.append(merged)
        else:
            self._undo.extend([prev, last])

    def snap_last_stroke(self, min_confidence: float = 0.6) -> bool:
        """Replace the last stroke with its recognized perfect shape.

        Used when shape recognition is enabled. Returns True on success.
        """
        from shapes import UNKNOWN, recognize
        if not self.items or not isinstance(self.items[-1], Stroke):
            return False
        stroke = self.items[-1]
        if len(stroke.points) < 8:
            return False
        name, confidence = recognize([(float(x), float(y)) for x, y in stroke.points])
        if name == UNKNOWN or confidence < min_confidence:
            return False
        xs = [p[0] for p in stroke.points]
        ys = [p[1] for p in stroke.points]
        self.items.pop()
        if self._undo and self._undo[-1][0] == "add":
            self._undo.pop()
        self.add_shape(ShapeItem(shape=name, p1=(min(xs), min(ys)),
                                 p2=(max(xs), max(ys)), color=stroke.color,
                                 thickness=stroke.thickness, glow=stroke.glow,
                                 opacity=stroke.opacity))
        return True
    def _shape_corners(self, item: ShapeItem) -> List[PixelPoint]:
        (x1, y1), (x2, y2) = item.p1, item.p2
        return [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]

    def _line_type(self) -> int:
        return cv2.LINE_AA if self.antialias else cv2.LINE_8

    def _blend(self, overlay: np.ndarray, opacity: float):
        """Per-item opacity: None when opaque, else (copy, (target, alpha))."""
        opacity = min(1.0, max(0.0, float(opacity)))
        if opacity >= 1.0:
            return overlay, None
        return overlay.copy(), (overlay, opacity)

    @staticmethod
    def _commit(layer: np.ndarray, token) -> None:
        if token is not None:
            target, opacity = token
            cv2.addWeighted(layer, opacity, target, 1.0 - opacity, 0, target)

    def render(self, width: int, height: int) -> np.ndarray:
        """Rasterize items to a transparent BGR overlay (black = see-through)."""
        key = (width, height, self.zoom, self.pan_x, self.pan_y,
               self.antialias)
        if (not self._dirty and self._cached_overlay is not None
                and self._cached_key == key):
            return self._cached_overlay
        overlay = np.zeros((height, width, 3), dtype=np.uint8)
        for item in self.items:
            if isinstance(item, Stroke):
                self._render_stroke(overlay, item, width, height)
            elif isinstance(item, ShapeItem):
                self._render_shape(overlay, item, width, height)
        self._cached_overlay = overlay
        self._cached_key = key
        self._dirty = False
        return overlay

    def background_color(self) -> Color:
        """Resolve the configured canvas background color."""
        modes = {"dark": (24, 24, 28), "white": (245, 245, 245),
                 "black": (8, 8, 10)}
        if self.bg_mode == "custom":
            return self.bg_custom
        if self.bg_mode == "grid":
            return (24, 24, 28)
        return modes.get(self.bg_mode, (24, 24, 28))

    def render_scene(self, width: int, height: int) -> np.ndarray:
        """Full scene: background (+grid) with items composited on top."""
        scene = np.full((height, width, 3), self.background_color(), dtype=np.uint8)
        if self.bg_mode == "grid":
            step = max(4, int(self.grid_size))
            for x in range(0, width, step):
                cv2.line(scene, (x, 0), (x, height), (45, 45, 52), 1)
            for y in range(0, height, step):
                cv2.line(scene, (0, y), (width, y), (45, 45, 52), 1)
        overlay = self.render(width, height)
        mask = overlay.max(axis=2) > 0
        scene[mask] = overlay[mask]
        return scene

    def _render_stroke(self, overlay: np.ndarray, stroke: Stroke,
                       width: int, height: int) -> None:
        pts = [self.to_view((int(x), int(y)), width, height) for x, y in stroke.points]
        if not pts:
            return
        layer, token = self._blend(overlay, stroke.opacity)
        lt = self._line_type()
        widths = (list(stroke.widths) if stroke.widths and len(stroke.widths) == len(pts)
                  else [float(stroke.thickness)] * len(pts))
        if len(pts) == 1:
            cv2.circle(layer, pts[0], max(int(widths[0] // 2), 1), stroke.color, -1, lt)
        else:
            for i in range(1, len(pts)):
                w = max(int((widths[i - 1] + widths[i]) / 2), 1)
                if stroke.glow:
                    cv2.line(layer, pts[i - 1], pts[i], stroke.color, w * 3, lt)
                cv2.line(layer, pts[i - 1], pts[i], stroke.color, w, lt)
                cv2.circle(layer, pts[i], max(w // 2, 1), stroke.color, -1, lt)
        if token is not None:
            self._commit(layer, token)

    def _render_shape(self, overlay: np.ndarray, item: ShapeItem,
                      width: int, height: int) -> None:
        p1 = self.to_view((int(item.p1[0]), int(item.p1[1])), width, height)
        p2 = self.to_view((int(item.p2[0]), int(item.p2[1])), width, height)
        layer, token = self._blend(overlay, item.opacity)
        lt = self._line_type()
        from shapes import perfect_triangle  # local import: cheap, avoids cycles
        if item.shape == "line":
            if item.glow:
                cv2.line(layer, p1, p2, item.color, item.thickness * 3, lt)
            cv2.line(layer, p1, p2, item.color, item.thickness, lt)
        elif item.shape == "rectangle":
            if item.glow:
                cv2.rectangle(layer, p1, p2, item.color, item.thickness * 3, lt)
            cv2.rectangle(layer, p1, p2, item.color, item.thickness, lt)
        elif item.shape == "triangle":
            tri = np.array(perfect_triangle(p1, p2), dtype=np.int32)
            if item.glow:
                cv2.polylines(layer, [tri], True, item.color, item.thickness * 3, lt)
            cv2.polylines(layer, [tri], True, item.color, item.thickness, lt)
        else:  # circle / sphere
            radius = max(int(math.hypot(p1[0] - p2[0], p1[1] - p2[1]) / 2), 3)
            center = ((p1[0] + p2[0]) // 2, (p1[1] + p2[1]) // 2)
            if item.shape == "sphere":
                from renderer import draw_sphere
                draw_sphere(layer, center, radius, glow=item.glow, alpha=1.0)
            else:
                if item.glow:
                    cv2.circle(layer, center, radius, item.color, item.thickness * 3, lt)
                cv2.circle(layer, center, radius, item.color, item.thickness, lt)
        if token is not None:
            self._commit(layer, token)

    def composite(self, frame: np.ndarray) -> np.ndarray:
        """Alpha-composite the canvas over a BGR frame (same size)."""
        height, width = frame.shape[:2]
        overlay = self.render(width, height)
        mask = cv2.cvtColor(overlay, cv2.COLOR_BGR2GRAY) > 0
        frame[mask] = overlay[mask]
        return frame

    # --- persistence ---
    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dict (documented format)."""
        serialized = []
        for item in self.items:
            if isinstance(item, Stroke):
                serialized.append({"type": "stroke", "points": [list(p) for p in item.points],
                                   "color": list(item.color), "thickness": item.thickness,
                                   "glow": item.glow, "tool": item.tool})
            elif isinstance(item, ShapeItem):
                serialized.append({"type": "shape", "shape": item.shape,
                                   "p1": list(item.p1), "p2": list(item.p2),
                                   "color": list(item.color), "thickness": item.thickness,
                                   "glow": item.glow})
        return {"version": 1, "zoom": self.zoom, "items": serialized}

    def save_project(self, path: str | Path) -> Path:
        """Save the vector project as JSON."""
        path = Path(path)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return path

    @classmethod
    def load_project(cls, path: str | Path) -> "Canvas":
        """Load a project saved with :meth:`save_project`."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        canvas = cls()
        canvas.zoom = float(data.get("zoom", 1.0))
        pan = data.get("pan", [0, 0])
        canvas.pan_x, canvas.pan_y = int(pan[0]), int(pan[1])
        for entry in data.get("items", []):
            if entry.get("type") == "stroke":
                points = [tuple(p) for p in entry.get("points", [])]
                widths = [float(w) for w in entry.get("widths", [])]
                canvas.items.append(Stroke(
                    points=points,
                    color=tuple(entry.get("color", (43, 255, 255))),
                    thickness=int(entry.get("thickness", 6)),
                    glow=bool(entry.get("glow", True)),
                    tool=entry.get("tool", Tool.PENCIL.value),
                    widths=widths if len(widths) == len(points) else [],
                    opacity=float(entry.get("opacity", 1.0)),
                    timestamp=float(entry.get("timestamp", 0.0))))
            elif entry.get("type") == "shape":
                canvas.items.append(ShapeItem(
                    shape=entry.get("shape", "circle"),
                    p1=tuple(entry.get("p1", (0, 0))), p2=tuple(entry.get("p2", (0, 0))),
                    color=tuple(entry.get("color", (43, 255, 255))),
                    thickness=int(entry.get("thickness", 3)),
                    glow=bool(entry.get("glow", True)),
                    opacity=float(entry.get("opacity", 1.0))))
        canvas._dirty = True
        return canvas

    def save_png(self, path: str | Path, width: int = 1280, height: int = 720,
                 background: Optional[Color] = None) -> Path:
        """Export a PNG of the canvas scene."""
        path = Path(path)
        image = self.render_scene(width, height) if background is None else None
        if image is None:
            image = np.full((height, width, 3), background, dtype=np.uint8)
            self.composite(image)
        cv2.imwrite(str(path), image)
        return path

    def save_jpg(self, path: str | Path, width: int = 1280, height: int = 720,
                 quality: int = 92) -> Path:
        """Export a JPG (opaque scene render) of the canvas."""
        path = Path(path)
        cv2.imwrite(str(path), self.render_scene(width, height),
                    [cv2.IMWRITE_JPEG_QUALITY, max(1, min(100, int(quality)))])
        return path

    @staticmethod
    def _svg_color(color: Color) -> str:
        b, g, r = (int(v) for v in color)
        return f"#{r:02x}{g:02x}{b:02x}"

    def export_svg(self, path: str | Path, width: int = 1280,
                   height: int = 720) -> Path:
        """Export vector SVG built from stroke/shape data (no rasterization)."""
        path = Path(path)
        parts = [f'<svg xmlns="http://www.w3.org/2000/svg" '
                 f'width="{width}" height="{height}" viewBox="0 0 {width} {height}">']
        bg = self._svg_color(self.background_color())
        parts.append(f'<rect width="100%" height="100%" fill="{bg}"/>')
        for item in self.items:
            if isinstance(item, Stroke) and item.points:
                pts = " ".join(f"{x},{y}" for x, y in item.points)
                parts.append(
                    f'<polyline points="{pts}" fill="none" '
                    f'stroke="{self._svg_color(item.color)}" '
                    f'stroke-width="{item.thickness}" stroke-linecap="round" '
                    f'stroke-linejoin="round" opacity="{item.opacity:.2f}"/>')
            elif isinstance(item, ShapeItem):
                (x1, y1), (x2, y2) = item.p1, item.p2
                color, w, op = (self._svg_color(item.color), item.thickness,
                                f"{item.opacity:.2f}")
                if item.shape == "line":
                    parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
                                 f'stroke="{color}" stroke-width="{w}" opacity="{op}"/>')
                elif item.shape == "rectangle":
                    parts.append(f'<rect x="{min(x1, x2)}" y="{min(y1, y2)}" '
                                 f'width="{abs(x2 - x1)}" height="{abs(y2 - y1)}" '
                                 f'fill="none" stroke="{color}" stroke-width="{w}" '
                                 f'opacity="{op}"/>')
                else:  # circle / sphere / triangle
                    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
                    radius = max(math.hypot(x1 - x2, y1 - y2) / 2, 1)
                    parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{radius:.1f}" '
                                 f'fill="none" stroke="{color}" stroke-width="{w}" '
                                 f'opacity="{op}"/>')
        parts.append("</svg>")
        path.write_text("\n".join(parts), encoding="utf-8")
        return path
