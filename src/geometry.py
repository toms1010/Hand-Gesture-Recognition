"""Geometric calculations on normalized hand landmarks.

This module is intentionally pure math: no OpenCV, no NumPy, no
MediaPipe. All drawing lives in :mod:`renderer`.
"""
from __future__ import annotations

import math
from typing import Iterable, Optional, Sequence, Tuple

Point = Tuple[float, float]  # normalized (x, y) coordinates
Pixel = Tuple[int, int]
Box = Tuple[int, int, int, int]  # (xmin, ymin, xmax, ymax) in pixels


def _xy(point) -> Point:
    """Accept duck-typed landmarks (``.x``/``.y``) or ``(x, y)`` tuples."""
    if isinstance(point, (tuple, list)):
        return float(point[0]), float(point[1])
    return float(point.x), float(point.y)


def distance(a, b) -> float:
    """Euclidean distance between two normalized points/landmarks."""
    ax, ay = _xy(a)
    bx, by = _xy(b)
    return math.hypot(ax - bx, ay - by)


def center(a, b) -> Point:
    """Midpoint between two normalized points/landmarks."""
    ax, ay = _xy(a)
    bx, by = _xy(b)
    return ((ax + bx) / 2.0, (ay + by) / 2.0)


def joint_angle(a, b, c) -> float:
    """Angle (degrees) at point ``b`` formed by segments b->a and b->c.

    Returns 180.0 for a perfectly straight joint. Returns ``nan`` when
    either segment has zero length (degenerate input).
    """
    ax, ay = _xy(a)
    bx, by = _xy(b)
    cx, cy = _xy(c)
    v1x, v1y = ax - bx, ay - by
    v2x, v2y = cx - bx, cy - by
    n1 = math.hypot(v1x, v1y)
    n2 = math.hypot(v2x, v2y)
    if n1 == 0.0 or n2 == 0.0:
        return float("nan")
    cos_angle = (v1x * v2x + v1y * v2y) / (n1 * n2)
    cos_angle = min(1.0, max(-1.0, cos_angle))
    return math.degrees(math.acos(cos_angle))


def to_pixel(landmark, width: int, height: int) -> Pixel:
    """Convert a normalized landmark to clamped pixel coordinates."""
    x, y = _xy(landmark)
    px = min(max(int(x * width), 0), max(width - 1, 0))
    py = min(max(int(y * height), 0), max(height - 1, 0))
    return px, py


def landmarks_to_pixels(hand, width: int, height: int) -> list:
    """Convert one hand's landmarks to clamped pixel coordinates."""
    return [to_pixel(lm, width, height) for lm in hand]


def normalized_bbox(hands: Iterable[Sequence]) -> Optional[Tuple[float, float, float, float]]:
    """Bounding box over hands in normalized coords: (xmin, ymin, xmax, ymax)."""
    xs = [float(lm.x) for hand in hands if hand for lm in hand]
    ys = [float(lm.y) for hand in hands if hand for lm in hand]
    if not xs or not ys:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


def bounding_box(hands: Iterable[Sequence], width: int, height: int,
                 margin: int = 0) -> Optional[Box]:
    """Pixel bounding box around all landmarks of the given hands.

    Returns ``None`` when there are no landmarks or the box is degenerate.
    """
    box = normalized_bbox(hands)
    if box is None:
        return None
    xmin, ymin, xmax, ymax = box
    x0 = min(max(int(xmin * width) - margin, 0), width - 1)
    y0 = min(max(int(ymin * height) - margin, 0), height - 1)
    x1 = min(max(int(xmax * width) + margin, 0), width - 1)
    y1 = min(max(int(ymax * height) + margin, 0), height - 1)
    if x1 <= x0 or y1 <= y0:
        return None
    return (x0, y0, x1, y1)


def wrist_midpoint(hand1, hand2) -> Point:
    """Normalized midpoint between two hands' wrists (landmark 0)."""
    return center(hand1[0], hand2[0])


def wrist_span(hand1, hand2) -> float:
    """Normalized distance between two hands' wrists."""
    return distance(hand1[0], hand2[0])


def sphere_radius_px(hand1, hand2, width: int, height: int, min_radius: int = 5) -> int:
    """Sphere radius in pixels: half the wrist-to-wrist pixel distance."""
    x1, y1 = to_pixel(hand1[0], width, height)
    x2, y2 = to_pixel(hand2[0], width, height)
    return max(int(math.hypot(x1 - x2, y1 - y2) / 2), min_radius)


def circle_between_tips_px(tip1, tip2, width: int, height: int) -> Tuple[Pixel, int]:
    """Circle center/radius in pixels spanning two fingertip landmarks."""
    (x1, y1), (x2, y2) = to_pixel(tip1, width, height), to_pixel(tip2, width, height)
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    radius = int(math.hypot(x1 - x2, y1 - y2) / 2)
    return (cx, cy), radius


# ---------------------------------------------------------------------------
# Backwards-compatible drawing wrappers.
#
# Older code imported ``draw_*`` helpers from this module. The canonical
# implementations now live in :mod:`renderer`; these thin wrappers delegate
# to them (lazily, to avoid a renderer -> geometry import cycle).
# ---------------------------------------------------------------------------

def draw_line_between_wrists(frame, wrist1, wrist2):
    """Deprecated: use :func:`renderer.draw_line_between_wrists`."""
    from renderer import draw_line_between_wrists as _impl
    return _impl(frame, wrist1, wrist2)


def draw_sphere_between_hands(frame, hand1, hand2):
    """Deprecated: use :func:`renderer.draw_sphere_between_hands`."""
    from renderer import draw_sphere_between_hands as _impl
    return _impl(frame, hand1, hand2)


def draw_rectangle_both_hands(frame, hand1, hand2):
    """Deprecated: use :func:`renderer.draw_rectangle_for_hands`."""
    from renderer import draw_rectangle_for_hands as _impl
    return _impl(frame, (hand1, hand2))
