"""Pointer smoothing + stroke interpolation (camera-free, unit-tested).

Pipeline per raw fingertip sample::

    raw point
      ↓ dead-zone filter (ignore micro-jitter)
      ↓ exponential smoothing (configurable alpha)
      ↓ adaptive alpha from velocity (slow = smooth, fast = responsive)
      ↓ linear / Catmull-Rom gap interpolation for the stroke engine
"""
from __future__ import annotations

import math
from typing import List, Optional, Tuple

Point = Tuple[float, float]


def clamp_alpha(alpha: float) -> float:
    """Clamp a smoothing alpha to the valid (0, 1] range."""
    return min(1.0, max(1e-3, float(alpha)))


def smoothing_to_alpha(smoothing: float, min_alpha: float = 0.15,
                       max_alpha: float = 0.9) -> float:
    """Map a 0..1 smoothing setting to a base exponential alpha.

    0% smoothing -> max_alpha (near-raw), 100% -> min_alpha (heavy).
    """
    smoothing = min(1.0, max(0.0, float(smoothing)))
    return max_alpha + (min_alpha - max_alpha) * smoothing


class PointSmoother:
    """Exponential pointer smoother with dead-zone + velocity adaptation."""

    def __init__(self, smoothing: float = 0.7, dead_zone_px: float = 2.0,
                 min_alpha: float = 0.15, max_alpha: float = 0.9):
        self.smoothing = smoothing
        self.dead_zone_px = max(0.0, float(dead_zone_px))
        self.min_alpha = min_alpha
        self.max_alpha = max_alpha
        self._pos: Optional[Point] = None
        self._speed = 0.0  # px per update (exponentially averaged)

    def reset(self) -> None:
        """Forget state (call when the pointer leaves / tool changes)."""
        self._pos = None
        self._speed = 0.0

    @property
    def position(self) -> Optional[Point]:
        """Current smoothed position (None before the first sample)."""
        return self._pos

    @property
    def speed(self) -> float:
        """Averaged pointer speed in px/update."""
        return self._speed

    def _adaptive_alpha(self, distance_px: float) -> float:
        base = smoothing_to_alpha(self.smoothing, self.min_alpha, self.max_alpha)
        # Fast motion -> push alpha toward max (responsive);
        # slow motion -> keep base (smooth). ~32 px/update ≈ full speed.
        energy = min(1.0, distance_px / 32.0)
        return base + (self.max_alpha - base) * energy * energy

    def update(self, raw: Point) -> Point:
        """Feed one raw point; return the smoothed point."""
        raw = (float(raw[0]), float(raw[1]))
        if self._pos is None:
            self._pos = raw
            return raw
        dx, dy = raw[0] - self._pos[0], raw[1] - self._pos[1]
        dist = math.hypot(dx, dy)
        if dist <= self.dead_zone_px:
            # Leaky dead zone: creep a quarter of the way instead of a
            # hard hold, so slow drifts never accumulate a static offset.
            self._pos = (self._pos[0] + dx * 0.25, self._pos[1] + dy * 0.25)
            return self._pos
        alpha = clamp_alpha(self._adaptive_alpha(dist))
        self._pos = (self._pos[0] + dx * alpha, self._pos[1] + dy * alpha)
        self._speed += 0.3 * (dist - self._speed)
        return self._pos


def interpolate_segment(p1: Point, p2: Point, max_gap: float = 4.0) -> List[Point]:
    """Linear gap fill between two points (endpoints inclusive)."""
    dist = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
    if dist <= max_gap:
        return [p1, p2]
    steps = max(2, int(math.ceil(dist / max_gap)))
    return [(p1[0] + (p2[0] - p1[0]) * i / steps,
             p1[1] + (p2[1] - p1[1]) * i / steps) for i in range(steps + 1)]


def catmull_rom(points: List[Point], samples_per_span: int = 8,
                bounds: Optional[Tuple[float, float, float, float]] = None) -> List[Point]:
    """Catmull-Rom resampling for silky freehand strokes.

    Returns the original endpoints plus interpolated samples. Needs at
    least 4 points; shorter inputs fall back to linear gap fill.
    ``bounds`` (xmin, ymin, xmax, ymax) clamps overshoot at sharp corners.
    """
    if len(points) < 4:
        out: List[Point] = [points[0]]
        for nxt in points[1:]:
            out.extend(interpolate_segment(out[-1], nxt)[1:])
        return _clamp_points(out, bounds)
    ext = [points[0]] + list(points) + [points[-1]]
    out = [points[0]]
    for i in range(1, len(ext) - 2):
        p0, p1, p2, p3 = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]
        for j in range(1, samples_per_span + 1):
            t = j / samples_per_span
            t2, t3 = t * t, t * t * t
            x = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t
                       + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                       + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
            y = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t
                       + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                       + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
            out.append((x, y))
    return _clamp_points(out, bounds)


def _clamp_points(points: List[Point],
                  bounds: Optional[Tuple[float, float, float, float]]) -> List[Point]:
    if bounds is None:
        return points
    xmin, ymin, xmax, ymax = bounds
    return [(min(max(x, xmin), xmax), min(max(y, ymin), ymax)) for x, y in points]
