"""View composition for the desktop studio (pure, Tk-free, unit-tested).

Modes:

* ``camera_drawing`` — camera frame with canvas composited (default)
* ``drawing`` — studio background with canvas only
* ``camera`` — raw camera frame only
"""
from __future__ import annotations

from enum import Enum

import numpy as np

import config


def fit_to_pane(img: np.ndarray, width: int, height: int,
                background: tuple = (18, 18, 22)) -> np.ndarray:
    """Aspect-fit ``img`` into (width, height) with letterbox bars."""
    import cv2
    ih, iw = img.shape[:2]
    if iw == 0 or ih == 0:
        return np.full((height, width, 3), background, dtype=np.uint8)
    scale = min(width / iw, height / ih)
    nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
    resized = cv2.resize(img, (nw, nh))
    out = np.full((height, width, 3), background, dtype=np.uint8)
    y0, x0 = (height - nh) // 2, (width - nw) // 2
    out[y0:y0 + nh, x0:x0 + nw] = resized
    return out


class ViewMode(str, Enum):
    """Available main-view modes."""

    CAMERA_DRAWING = "camera_drawing"
    DRAWING = "drawing"
    CAMERA = "camera"


VIEW_MODES = [ViewMode.CAMERA_DRAWING, ViewMode.DRAWING, ViewMode.CAMERA]

VIEW_LABELS = {
    ViewMode.CAMERA_DRAWING: "Camera + Drawing",
    ViewMode.DRAWING: "Drawing Only",
    ViewMode.CAMERA: "Camera Only",
}


def compose_view(mode: ViewMode, camera_frame, canvas, width: int, height: int,
                 background: tuple = config.CANVAS_BACKGROUND) -> np.ndarray:
    """Build the display BGR image for ``mode`` (never mutates inputs).

    ``camera_frame`` may be None (camera disconnected) — the drawing
    canvas remains usable via the background fallback.
    """
    if mode == ViewMode.CAMERA and camera_frame is not None:
        return camera_frame.copy()
    if mode == ViewMode.CAMERA_DRAWING and camera_frame is not None:
        # Caller passes the already-composited annotated frame.
        return camera_frame.copy()
    base = np.full((height, width, 3), background, dtype=np.uint8)
    if canvas is not None:
        overlay = canvas.render(width, height)
        if overlay.shape[:2] != (height, width):
            import cv2
            overlay = cv2.resize(overlay, (width, height))
        mask = overlay.max(axis=2) > 0
        base[mask] = overlay[mask]
    return base
