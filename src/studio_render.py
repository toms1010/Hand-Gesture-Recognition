"""Shared per-frame rendering used by both the OpenCV and desktop UIs.

Keeps overlay logic in one place so the Tkinter GUI cannot drift from
the OpenCV behavior: canvas compositing, skeletons, two-hand overlays,
single-hand overlays, cursor, pinch line, selection.
"""
from __future__ import annotations

import config
from gesture_engine import ACTION_DRAW, ACTION_SHAPE, CIRCLE, LINE, RECT, RECTANGLE, SPHERE
from hand_tracker import HAND_CONNECTIONS, INDEX_TIP, THUMB_TIP


def render_overlays(frame, hands, stable, controller, canvas,
                    show_landmarks: bool = True, include_canvas: bool = True):
    """Composite canvas + live gesture overlays onto a BGR frame (in place).

    ``include_canvas=False`` renders camera + gesture overlays only (used
    for the desktop split camera pane); the drawing lives on the canvas.
    """
    import renderer
    from geometry import to_pixel

    if include_canvas:
        canvas.composite(frame)
    if show_landmarks:
        for hand in hands:
            renderer.draw_hand_skeleton(frame, hand, HAND_CONNECTIONS)
    animations_on = getattr(config, "ANIMATIONS", "full") != "off"
    if len(hands) >= 2 and stable.is_stable:
        h1, h2 = hands[0], hands[1]
        if stable.name == LINE:
            renderer.draw_line_between_wrists(frame, h1[0], h2[0])
        elif stable.name == SPHERE:
            renderer.draw_sphere_between_hands(frame, h1, h2, glow=True)
        elif stable.name == RECTANGLE:
            renderer.draw_rectangle_for_hands(frame, (h1, h2))
    elif len(hands) == 1:
        hand = hands[0]
        # Prefer the controller's smoothed cursor; fall back to raw tip.
        tip = controller.cursor_px
        if tip is None:
            height, width = frame.shape[:2]
            tip = to_pixel(hand[INDEX_TIP], width, height)
        pulse = 0.0
        if animations_on:
            for key in ("pinch", "stamp", "draw_start"):
                pulse = max(pulse, controller.animations.pulse_value(key))
        renderer.draw_cursor(frame, tip,
                             active=stable.action not in (ACTION_DRAW, "IDLE"),
                             pinch=stable.pinch,
                             state=controller.cursor_state,
                             pulse=pulse)
        if stable.pinch:
            try:
                height, width = frame.shape[:2]
                thumb = to_pixel(hand[THUMB_TIP], width, height)
                renderer.draw_pinch_line(frame, thumb, tip)
            except (IndexError, AttributeError):
                pass
        if stable.action == ACTION_DRAW and stable.is_stable:
            try:
                renderer.draw_wrist_to_tip_line(frame, hand[0], hand[INDEX_TIP])
            except (IndexError, AttributeError):
                pass
        elif stable.action == ACTION_SHAPE and controller.preview is not None:
            renderer.draw_shape_preview(frame, controller.preview)
        elif stable.name == CIRCLE and stable.is_stable:
            try:
                renderer.draw_circle_between_tips(frame, hand[8], hand[12])
            except (IndexError, AttributeError):
                pass
        elif stable.name == RECT and stable.is_stable:
            renderer.draw_rectangle_for_hands(frame, [hand])
        from tools import Tool
        if controller.tool == Tool.SELECT and controller.drag_index is not None:
            renderer.draw_selection(frame, canvas, controller.drag_index)
    _ = config  # config read by callers (mirror/landmarks toggles)
    return frame
