"""Drawing primitives for hand gestures (OpenCV/NumPy only)."""
from __future__ import annotations

import math
from typing import Iterable, Optional, Sequence

import cv2
import numpy as np

from geometry import (
    bounding_box,
    circle_between_tips_px,
    landmarks_to_pixels,
    sphere_radius_px,
    to_pixel,
    wrist_midpoint,
)

LINE_COLOR = (0, 255, 255)  # BGR yellow
LINE_CORE_COLOR = (255, 255, 200)
SPHERE_EDGE_COLOR = (40, 140, 220)
SPHERE_HIGHLIGHT_COLOR = (200, 255, 255)
CIRCLE_COLOR = (255, 0, 0)  # BGR blue
RECT_COLOR = (0, 255, 0)  # BGR green
SKELETON_LINE_COLOR = (0, 255, 0)
SKELETON_DOT_COLOR = (0, 0, 255)


def draw_line_between_wrists(frame, wrist1, wrist2):
    """Draw a glowing line between two wrist landmarks."""
    height, width = frame.shape[:2]
    x1, y1 = to_pixel(wrist1, width, height)
    x2, y2 = to_pixel(wrist2, width, height)
    cv2.line(frame, (x1, y1), (x2, y2), LINE_COLOR, 5, cv2.LINE_AA)
    cv2.line(frame, (x1, y1), (x2, y2), LINE_CORE_COLOR, 2, cv2.LINE_AA)
    cv2.circle(frame, (x1, y1), 5, LINE_COLOR, -1, cv2.LINE_AA)
    cv2.circle(frame, (x2, y2), 5, LINE_COLOR, -1, cv2.LINE_AA)
    return frame


def draw_wrist_to_tip_line(frame, wrist, tip):
    """Draw a line from the wrist to a fingertip (single-hand LINE)."""
    height, width = frame.shape[:2]
    x1, y1 = to_pixel(wrist, width, height)
    x2, y2 = to_pixel(tip, width, height)
    cv2.line(frame, (x1, y1), (x2, y2), LINE_COLOR, 3, cv2.LINE_AA)
    return frame


def draw_sphere(frame, center_px, radius: int, glow: bool = True, alpha: float = 0.7):
    """Draw a shaded 3D-looking sphere disc.

    Args:
        frame: BGR image modified in place and returned.
        center_px: (x, y) pixel center.
        radius: sphere radius in pixels.
        glow: draw a soft outer glow ring.
        alpha: blend factor of the sphere overlay over the frame.
    """
    height, width = frame.shape[:2]
    cx = min(max(int(center_px[0]), 0), width - 1)
    cy = min(max(int(center_px[1]), 0), height - 1)
    radius = max(int(radius), 5)

    overlay = frame.copy()
    if glow:
        cv2.circle(overlay, (cx, cy), radius + 6, (30, 90, 160), 3, cv2.LINE_AA)
    # Base disc (dark brown, BGR).
    cv2.circle(overlay, (cx, cy), radius, (30, 80, 160), -1, cv2.LINE_AA)
    # Radial gradient: dark edge -> bright yellow center.
    step = max(1, radius // 20)
    for r in range(radius, 0, -step):
        t = 1.0 - (r / radius)
        color = (int(30 + 30 * t), int(80 + 150 * t), int(160 + 95 * t))
        cv2.circle(overlay, (cx, cy), r, color, -1, cv2.LINE_AA)
    # Offset specular highlight.
    highlight_center = (cx - radius // 4, cy - radius // 4)
    highlight_axes = (max(1, radius // 3), max(1, radius // 4))
    cv2.ellipse(overlay, highlight_center, highlight_axes, -45, 0, 360,
                SPHERE_HIGHLIGHT_COLOR, -1, cv2.LINE_AA)
    # Subtle dark rim + bright inner edge for depth.
    cv2.circle(overlay, (cx, cy), radius, (20, 60, 120), 3, cv2.LINE_AA)
    cv2.circle(overlay, (cx, cy), radius, SPHERE_EDGE_COLOR, 2, cv2.LINE_AA)

    blended = cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0)
    np.copyto(frame, blended)
    return frame


def draw_sphere_between_hands(frame, hand1, hand2, glow: bool = True):
    """Draw a sphere whose diameter spans the two wrists."""
    if not hand1 or not hand2:
        return frame
    height, width = frame.shape[:2]
    mx, my = wrist_midpoint(hand1, hand2)
    center_px = (min(max(int(mx * width), 0), width - 1),
                 min(max(int(my * height), 0), height - 1))
    radius = sphere_radius_px(hand1, hand2, width, height)
    return draw_sphere(frame, center_px, radius, glow=glow)


def draw_circle_between_tips(frame, tip1, tip2):
    """Draw a circle spanning two fingertip landmarks (single-hand CIRCLE)."""
    height, width = frame.shape[:2]
    (cx, cy), radius = circle_between_tips_px(tip1, tip2, width, height)
    if radius > 5:
        cv2.circle(frame, (cx, cy), radius, CIRCLE_COLOR, 3, cv2.LINE_AA)
    return frame


def draw_rectangle_for_hands(frame, hands: Iterable[Sequence], margin: int = 0):
    """Draw a bounding rectangle around all landmarks of the given hands."""
    height, width = frame.shape[:2]
    box = bounding_box(hands, width, height, margin=margin)
    if box is None:
        return frame
    xmin, ymin, xmax, ymax = box
    cv2.rectangle(frame, (xmin, ymin), (xmax, ymax), RECT_COLOR, 3)
    return frame


def draw_rectangle_both_hands(frame, hand1, hand2):
    """Draw a bounding rectangle around two hands (legacy two-arg form)."""
    return draw_rectangle_for_hands(frame, (hand1, hand2))


def draw_hand_skeleton(frame, landmarks, connections: Optional[Sequence] = None):
    """Draw a hand skeleton (joints + bones) for one hand."""
    height, width = frame.shape[:2]
    if landmarks is None or len(landmarks) < 21:
        return frame
    points = landmarks_to_pixels(landmarks, width, height)
    if connections:
        for i, j in connections:
            if 0 <= i < len(points) and 0 <= j < len(points):
                cv2.line(frame, points[i], points[j], SKELETON_LINE_COLOR, 2)
    for pt in points:
        cv2.circle(frame, pt, 3, SKELETON_DOT_COLOR, -1)
    return frame


# --- Studio additions: cursor, previews, selection ---

CURSOR_COLOR = (0, 255, 255)
CURSOR_ACTIVE_COLOR = (0, 200, 0)
PREVIEW_COLOR = (255, 255, 255)
SELECT_COLOR = (255, 0, 255)


def draw_cursor(frame, pos, active: bool = False, pinch: bool = False,
                state: str = "hover", pulse: float = 0.0):
    """Draw the fingertip cursor ring with state styling + pulse envelope.

    States: idle (dim), hover (yellow), drawing (green), pinch (green+pulse),
    erasing (red). ``pulse`` 0..1 expands a fading outer ring (gesture
    confirm / stroke-start feedback).
    """
    x = min(max(int(pos[0]), 0), frame.shape[1] - 1)
    y = min(max(int(pos[1]), 0), frame.shape[0] - 1)
    colors = {"idle": (90, 90, 90), "hover": CURSOR_COLOR,
              "drawing": CURSOR_ACTIVE_COLOR, "pinch": CURSOR_ACTIVE_COLOR,
              "erasing": (60, 60, 255)}
    color = colors.get(state, CURSOR_COLOR)
    if active and state == "hover":
        color = CURSOR_ACTIVE_COLOR
    radius = 14 if state == "drawing" else 12
    cv2.circle(frame, (x, y), radius, color, 2, cv2.LINE_AA)
    cv2.circle(frame, (x, y), 3, color, -1, cv2.LINE_AA)
    if pinch or pulse > 0:  # activation pulse: expanding fading ring
        extra = int(6 + 14 * pulse) if pulse > 0 else 6
        cv2.circle(frame, (x, y), radius + extra, color, 1, cv2.LINE_AA)
    return frame


def draw_pinch_line(frame, thumb_px, index_px):
    """Draw the pinch connector between thumb and index fingertips."""
    cv2.line(frame, thumb_px, index_px, CURSOR_COLOR, 2, cv2.LINE_AA)
    for pt in (thumb_px, index_px):
        cv2.circle(frame, pt, 4, CURSOR_COLOR, -1, cv2.LINE_AA)
    return frame


def draw_shape_preview(frame, preview, color=PREVIEW_COLOR):
    """Draw an uncommitted shape preview with corner handles."""
    if preview is None:
        return frame
    (x1, y1), (x2, y2) = preview.p1, preview.p2
    if preview.shape == "line":
        cv2.line(frame, (x1, y1), (x2, y2), color, 2, cv2.LINE_AA)
    elif preview.shape == "rectangle":
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2, cv2.LINE_AA)
    elif preview.shape == "triangle":
        from shapes import perfect_triangle
        tri = np.array(perfect_triangle((x1, y1), (x2, y2)), dtype=np.int32)
        cv2.polylines(frame, [tri], True, color, 2, cv2.LINE_AA)
    else:  # circle / sphere
        radius = max(int(math.hypot(x1 - x2, y1 - y2) / 2), 3)
        cv2.circle(frame, ((x1 + x2) // 2, (y1 + y2) // 2), radius, color, 2,
                   cv2.LINE_AA)
    for pt in ((x1, y1), (x2, y2)):
        cv2.circle(frame, pt, 4, color, -1, cv2.LINE_AA)
    return frame


def draw_selection(frame, canvas, index: int):
    """Highlight the selected canvas item with a magenta outline."""
    if index is None or not (0 <= index < len(canvas.items)):
        return frame
    item = canvas.items[index]
    from canvas import ShapeItem, Stroke
    if isinstance(item, Stroke) and item.points:
        xs = [p[0] for p in item.points]
        ys = [p[1] for p in item.points]
        pad = 8
        cv2.rectangle(frame, (min(xs) - pad, min(ys) - pad),
                      (max(xs) + pad, max(ys) + pad), SELECT_COLOR, 2, cv2.LINE_AA)
    elif isinstance(item, ShapeItem):
        (x1, y1), (x2, y2) = item.p1, item.p2
        pad = 8
        cv2.rectangle(frame, (min(x1, x2) - pad, min(y1, y2) - pad),
                      (max(x1, x2) + pad, max(y1, y2) + pad), SELECT_COLOR, 2,
                      cv2.LINE_AA)
    return frame
