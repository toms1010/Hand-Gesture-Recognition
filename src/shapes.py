"""Optional auto shape recognition: rough strokes -> perfect shapes.

Pure NumPy/OpenCV, no camera needed. Disabled by default (see
``config.SHAPE_RECOGNITION``); when enabled, freehand strokes released
in a shape tool snap to the recognized perfect shape.
"""
from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np

Point = Tuple[float, float]

LINE = "line"
CIRCLE = "circle"
RECTANGLE = "rectangle"
TRIANGLE = "triangle"
UNKNOWN = "unknown"


def _resample(points: Sequence[Point], n: int = 32) -> np.ndarray:
    pts = np.asarray([(float(x), float(y)) for x, y in points], dtype=np.float64)
    if len(pts) < 2:
        return pts
    seg = np.hypot(np.diff(pts[:, 0]), np.diff(pts[:, 1]))
    total = float(seg.sum())
    if total == 0.0:
        return np.repeat(pts[:1], n, axis=0)
    target = np.linspace(0.0, total, n)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    out = []
    j = 0
    for t in target:
        while j < len(cum) - 2 and cum[j + 1] < t:
            j += 1
        span = cum[j + 1] - cum[j]
        f = 0.0 if span == 0 else (t - cum[j]) / span
        out.append(pts[j] * (1 - f) + pts[j + 1] * f)
    return np.asarray(out)


def _is_line(pts: np.ndarray) -> Tuple[bool, float]:
    a, b = pts[0], pts[-1]
    length = float(np.hypot(b[0] - a[0], b[1] - a[1]))
    if length < 1e-6:
        return False, 0.0
    direction = (b - a) / length
    deviations = np.abs((pts - a)[:, 0] * -direction[1] + (pts - a)[:, 1] * direction[0])
    score = 1.0 - float(deviations.max()) / length
    return bool(deviations.max() / length < 0.06), score


def _is_circle(pts: np.ndarray) -> Tuple[bool, float]:
    centroid = pts.mean(axis=0)
    radii = np.hypot(pts[:, 0] - centroid[0], pts[:, 1] - centroid[1])
    mean_r = float(radii.mean())
    if mean_r < 1e-6:
        return False, 0.0
    spread = float(radii.std()) / mean_r
    perimeter = float(np.hypot(np.diff(pts[:, 0]), np.diff(pts[:, 1])).sum())
    closure = float(np.hypot(*(pts[0] - pts[-1]))) / max(perimeter, 1e-6)
    score = max(0.0, 1.0 - spread * 3.0) * (1.0 - min(1.0, closure * 3.0))
    return bool(spread < 0.18 and closure < 0.25), score


def _poly_corners(pts: np.ndarray) -> np.ndarray:
    contour = pts.astype(np.float32).reshape(-1, 1, 2)
    perimeter = cv2.arcLength(contour, True)
    approx = cv2.approxPolyDP(contour, 0.04 * perimeter, True)
    return approx.reshape(-1, 2)


def recognize(points: Sequence[Point]) -> Tuple[str, float]:
    """Classify a stroke as line/circle/rectangle/triangle/unknown.

    Returns (shape_name, confidence 0..1). Needs >= 8 points; shorter
    strokes are ``unknown`` with 0.0 confidence.
    """
    if points is None or len(points) < 8:
        return UNKNOWN, 0.0
    pts = _resample(points)
    line, line_score = _is_line(pts)
    if line:
        return LINE, min(1.0, 0.6 + line_score * 0.4)
    # Polygonal shapes before circle: a rectangle outline can look
    # "circle-ish" by radial spread, but never the reverse (a rough
    # circle approximates to many more than 4 corners).
    try:
        corners = _poly_corners(pts)
    except cv2.error:
        return UNKNOWN, 0.0
    if len(corners) == 3:
        return TRIANGLE, 0.80
    if len(corners) == 4:
        return RECTANGLE, 0.85
    circle, circle_score = _is_circle(pts)
    if circle:
        return CIRCLE, min(1.0, 0.6 + circle_score * 0.4)
    return UNKNOWN, 0.0


def perfect_line(points: Sequence[Point]) -> List[Point]:
    """Idealize a stroke as a straight segment (endpoints)."""
    pts = list(points)
    return [tuple(pts[0]), tuple(pts[-1])]


def perfect_circle_points(center: Point, radius: float, n: int = 64) -> List[Point]:
    """Polygon approximating a perfect circle."""
    cx, cy = center
    return [(cx + radius * math.cos(2 * math.pi * i / n),
             cy + radius * math.sin(2 * math.pi * i / n)) for i in range(n)]


def perfect_rectangle(p1: Point, p2: Point) -> List[Point]:
    """Axis-aligned rectangle corners from two diagonal points."""
    (x1, y1), (x2, y2) = p1, p2
    return [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]


def perfect_triangle(p1: Point, p2: Point) -> List[Point]:
    """Isoceles triangle: apex at top-center of the p1-p2 bounding box."""
    (x1, y1), (x2, y2) = p1, p2
    top = min(y1, y2)
    bottom = max(y1, y2)
    cx = (x1 + x2) / 2.0
    return [(cx, top), (x2, bottom), (x1, bottom)]


def stroke_endpoints(points: Sequence[Point]) -> Tuple[Optional[Point], Optional[Point]]:
    """First/last point of a stroke (None, None when empty)."""
    if not points:
        return None, None
    return tuple(points[0]), tuple(points[-1])
