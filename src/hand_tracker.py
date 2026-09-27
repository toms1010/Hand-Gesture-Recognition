"""Hand tracking layer: MediaPipe Tasks wrapper + landmark helpers.

This is the canonical vision module. :mod:`gesture` re-exports the
public names for backwards compatibility.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import threading
import time
from typing import Optional

import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

import config
from applog import get_logger

# Standard hand connections (MediaPipe hand topology).
HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (0, 9), (9, 10), (10, 11), (11, 12),
    (0, 13), (13, 14), (14, 15), (15, 16),
    (0, 17), (17, 18), (18, 19), (19, 20),
    (5, 9), (9, 13), (13, 17),
]

# Landmark indices of interest.
WRIST = 0
THUMB_TIP, THUMB_IP, THUMB_MCP = 4, 3, 2
INDEX_TIP, INDEX_PIP, INDEX_MCP = 8, 6, 5
MIDDLE_TIP, MIDDLE_PIP, MIDDLE_MCP = 12, 10, 9
RING_TIP, RING_PIP, RING_MCP = 16, 14, 13
PINKY_TIP, PINKY_PIP, PINKY_MCP = 20, 18, 17
FINGERTIPS = (4, 8, 12, 16, 20)


def resolve_model_path(model_path: Optional[str] = None) -> str:
    """Resolve the ``.task`` model path, trying sensible fallbacks."""
    candidates = []
    if model_path:
        candidates.append(Path(model_path))
    candidates.append(Path(config.MODEL_PATH))
    candidates.append(Path.cwd() / "models" / "gesture_recognizer.task")
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    raise FileNotFoundError(
        "Hand landmarker model not found. Tried: "
        + ", ".join(str(c) for c in candidates)
    )


def handedness_label(handedness) -> Optional[str]:
    """Extract ``'Left'``/``'Right'``/``None`` from a handedness entry."""
    if not handedness:
        return None
    first = handedness[0] if isinstance(handedness, (list, tuple)) else handedness
    if isinstance(first, (list, tuple)):
        if not first:
            return None
        first = first[0]
    if isinstance(first, str):
        return first if first in ("Left", "Right") else None
    label = getattr(first, "category_name", None)
    return label if label in ("Left", "Right") else None


def handedness_score(handedness) -> float:
    """Return the handedness classification score, or 0.0 if unknown."""
    try:
        first = handedness[0] if isinstance(handedness, (list, tuple)) else handedness
        if isinstance(first, (list, tuple)):
            first = first[0]
        score = getattr(first, "score", None)
        return float(score) if score is not None else 0.0
    except (IndexError, TypeError, ValueError):
        return 0.0


class DetectionTimeout(RuntimeError):
    """Raised when a MediaPipe detect call exceeds its watchdog budget."""


def detect_with_timeout(detector, mp_image, timeout: float):
    """Run ``detector.detect`` in a daemon thread with a timeout.

    The native call can wedge indefinitely (busy executor, driver stall);
    the daemon thread never blocks interpreter shutdown, and a wedged
    call surfaces as :class:`DetectionTimeout` instead of a frozen app.
    """
    box: dict = {}
    done = threading.Event()

    def _target():
        try:
            box["result"] = detector.detect(mp_image)
        except Exception as exc:  # noqa: BLE001 - forwarded to caller
            box["error"] = exc
        finally:
            done.set()

    worker = threading.Thread(target=_target, daemon=True,
                              name="mp-detect-watchdog")
    worker.start()
    if not done.wait(timeout=timeout):
        raise DetectionTimeout(
            f"MediaPipe detect exceeded {timeout:.1f}s budget")
    if "error" in box:
        raise box["error"]
    return box.get("result")


@dataclass
class HandFrame:
    """One frame of hand-tracking output (camera-independent)."""

    hands: list = field(default_factory=list)
    handedness: list = field(default_factory=list)
    scores: list = field(default_factory=list)

    @property
    def hand_count(self) -> int:
        """Number of detected hands."""
        return len(self.hands)

    def label(self, index: int) -> Optional[str]:
        """Handedness label for hand ``index``."""
        if 0 <= index < len(self.handedness):
            return handedness_label(self.handedness[index])
        return None


class HandTracker:
    """Wraps MediaPipe's HandLandmarker (IMAGE running mode).

    The native ``detect`` call runs under a watchdog: a wedged call
    raises :class:`DetectionTimeout` (a ``RuntimeError``, so existing
    transient-failure handling applies) and repeated wedges rebuild the
    graph automatically.
    """

    def __init__(self, model_path: Optional[str] = None,
                 num_hands: int = config.MAX_HANDS,
                 min_detection_confidence: float = config.MIN_DETECTION_CONFIDENCE,
                 min_presence_confidence: float = config.MIN_HAND_PRESENCE_CONFIDENCE,
                 min_tracking_confidence: float = config.MIN_TRACKING_CONFIDENCE,
                 detect_timeout: float = getattr(config, "DETECT_TIMEOUT", 8.0),
                 max_timeouts: int = 2):
        self._params = dict(model_path=model_path, num_hands=num_hands,
                            min_detection_confidence=min_detection_confidence,
                            min_presence_confidence=min_presence_confidence,
                            min_tracking_confidence=min_tracking_confidence)
        self.detect_timeout = max(1.0, float(detect_timeout))
        self.max_timeouts = max(1, int(max_timeouts))
        self.detector = self._build()
        self._timeouts = 0
        self._warmed_up = False

    def _build(self):
        resolved = resolve_model_path(self._params["model_path"])
        base_options = python.BaseOptions(model_asset_path=resolved)
        options = vision.HandLandmarkerOptions(
            base_options=base_options,
            num_hands=self._params["num_hands"],
            min_hand_detection_confidence=self._params["min_detection_confidence"],
            min_hand_presence_confidence=self._params["min_presence_confidence"],
            min_tracking_confidence=self._params["min_tracking_confidence"],
        )
        return vision.HandLandmarker.create_from_options(options)

    def _rebuild(self) -> None:
        """Abandon a wedged graph and build a fresh one (best effort)."""
        get_logger().warning("Rebuilding wedged MediaPipe graph")
        try:
            self.detector.close()
        except Exception as exc:  # noqa: BLE001 - old graph may be wedged
            get_logger().debug("Old graph close failed (abandoned): %r", exc)
        self.detector = self._build()
        self._timeouts = 0

    @staticmethod
    def _detection_frame(frame):
        """Downscale oversized frames for detection (landmarks stay normalized)."""
        max_width = int(getattr(config, "DETECT_MAX_WIDTH", 960))
        height, width = frame.shape[:2]
        if width <= max_width:
            return frame
        scale = max_width / width
        return cv2.resize(frame, (max_width, max(1, int(height * scale))))

    def detect(self, frame):
        """Detect hands in a BGR frame.

        Raises:
            ValueError: on None/empty/malformed frames (caller fault).
            RuntimeError: transient MediaPipe failure or watchdog timeout.
        """
        if frame is None:
            raise ValueError("detect() got None frame")
        if frame.size == 0:
            raise ValueError("detect() got empty frame")
        if frame.ndim != 3 or frame.shape[2] != 3:
            raise ValueError(f"detect() needs a BGR image, got shape {frame.shape}")
        rgb = cv2.cvtColor(self._detection_frame(frame), cv2.COLOR_BGR2RGB)
        if not rgb.flags["C_CONTIGUOUS"]:
            rgb = rgb.copy()
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        if not self._warmed_up:
            self._warmed_up = True
            get_logger().debug("First MediaPipe detect (delegate warm-up)")
        started = time.monotonic()
        try:
            result = detect_with_timeout(self.detector, mp_image,
                                         self.detect_timeout)
        except DetectionTimeout:
            self._timeouts += 1
            get_logger().warning("MediaPipe detect timed out (%d in a row)",
                                 self._timeouts)
            if self._timeouts > self.max_timeouts:
                try:
                    self._rebuild()
                except Exception as exc:
                    raise RuntimeError(
                        f"MediaPipe wedged and rebuild failed: {exc}") from exc
            raise
        except Exception as exc:
            raise RuntimeError(f"MediaPipe detection failed: {exc}") from exc
        elapsed = time.monotonic() - started
        slow = float(getattr(config, "DETECT_SLOW_WARN", 1.5))
        if elapsed > slow:
            get_logger().warning("Slow MediaPipe detect: %.2fs", elapsed)
        else:
            self._timeouts = 0
        return result

    def track(self, frame) -> HandFrame:
        """Detect and return a camera-independent :class:`HandFrame`."""
        result = self.detect(frame)
        hands = list(result.hand_landmarks or [])[:]
        raw_handed = list(result.handedness or [])
        return HandFrame(
            hands=hands,
            handedness=raw_handed,
            scores=[handedness_score(h) for h in raw_handed],
        )

    def close(self, timeout: float = 2.0):
        """Release the MediaPipe graph (never blocks longer than timeout)."""
        detector, self.detector = self.detector, None

        def _close():
            try:
                if detector is not None:
                    detector.close()
            except AttributeError:
                pass
            except Exception as exc:  # noqa: BLE001 - best effort
                get_logger().debug("Detector close failed: %r", exc)

        done = threading.Event()

        def _guarded():
            _close()
            done.set()

        threading.Thread(target=_guarded, daemon=True).start()
        done.wait(timeout=timeout)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False

    def __del__(self):  # best-effort cleanup
        try:
            self.close()
        except Exception:
            pass
