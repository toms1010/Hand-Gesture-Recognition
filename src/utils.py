import time
from collections import deque

import cv2


class FPS:
    """Rolling FPS counter (default: average over last 30 frames)."""

    def __init__(self, window=30):
        self.window = max(2, int(window))
        self._times = deque(maxlen=self.window)
        self._start_time = time.time()
        self.frame_count = 0

    def update(self):
        now = time.time()
        self._times.append(now)
        self.frame_count += 1
        return self

    def reset(self):
        self._times.clear()
        self._start_time = time.time()
        self.frame_count = 0

    def get_fps(self):
        if len(self._times) >= 2:
            elapsed = self._times[-1] - self._times[0]
            if elapsed > 0:
                return (len(self._times) - 1) / elapsed
        # Fallback: cumulative average since construction.
        elapsed = time.time() - self._start_time
        if elapsed > 0 and self.frame_count > 0:
            return self.frame_count / elapsed
        return 0.0

    def __str__(self):
        return f"{self.get_fps():.1f} FPS"


def draw_text(frame, text, pos=(10, 30), font_scale=1.0, color=(255, 255, 255),
              thickness=2, font=cv2.FONT_HERSHEY_SIMPLEX):
    """Draw legible text with a black outline; clamps pos inside the frame."""
    h, w = frame.shape[:2]
    x, y = int(pos[0]), int(pos[1])
    (tw, th), baseline = cv2.getTextSize(str(text), font, font_scale, thickness)
    x = min(max(x, 5), max(w - tw - 5, 5))
    y = min(max(y, th + 5), h - 5)
    outline = max(thickness + 2, 3)
    cv2.putText(frame, str(text), (x, y), font, font_scale, (0, 0, 0), outline, cv2.LINE_AA)
    cv2.putText(frame, str(text), (x, y), font, font_scale, color, thickness, cv2.LINE_AA)
    return frame