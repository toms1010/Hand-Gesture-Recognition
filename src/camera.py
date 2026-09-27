"""Camera layer: initialization, frame capture, release and errors."""
from __future__ import annotations

import cv2

import config


class CameraError(RuntimeError):
    """Raised when the camera cannot be opened or is lost."""


class Camera:
    """Thin wrapper around :class:`cv2.VideoCapture`."""

    def __init__(self, camera_id: int = config.CAMERA_ID,
                 width=None, height=None, fps=None):
        if width is None:
            width = config.CAMERA_WIDTH
        if height is None:
            height = config.CAMERA_HEIGHT
        if fps is None:
            fps = config.CAMERA_FPS
        self.camera_id = camera_id
        self.cap = cv2.VideoCapture(camera_id)
        if not self.cap.isOpened():
            raise CameraError(
                f"Cannot open camera {camera_id!r}. "
                "Check the device index, permissions, or close other apps using it.")
        # Reduce latency: always deliver the newest frame.
        try:
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except cv2.error:
            pass
        if width is not None:
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(width))
        if height is not None:
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(height))
        if fps is not None:
            self.cap.set(cv2.CAP_PROP_FPS, float(fps))

    def is_opened(self):
        return self.cap is not None and self.cap.isOpened()

    def get_frame(self):
        if self.cap is None or not self.cap.isOpened():
            return None
        ret, frame = self.cap.read()
        if not ret or frame is None or frame.size == 0:
            return None
        return frame

    def release(self):
        try:
            if self.cap is not None:
                if self.cap.isOpened():
                    self.cap.release()
        finally:
            self.cap = None
            try:
                cv2.destroyAllWindows()
            except Exception:
                pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.release()
        return False

    def __del__(self):  # best-effort cleanup
        try:
            self.release()
        except Exception:
            pass