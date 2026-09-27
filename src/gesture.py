"""Backwards-compatible hand-detection module.

The canonical vision implementation lives in :mod:`hand_tracker` and
finger-pose logic in :mod:`finger_detector`. This module re-exports the
original names so existing imports keep working.
"""
from __future__ import annotations

from hand_tracker import (  # noqa: F401
    HAND_CONNECTIONS,
    HandFrame,
    HandTracker,
    handedness_label,
    handedness_score,
    resolve_model_path,
)

from finger_detector import (  # noqa: F401
    count_fingers,
    extended_fingers,
    is_finger_extended,
    is_thumb_extended,
)


class GestureDetector(HandTracker):
    """Legacy name for :class:`hand_tracker.HandTracker`."""

    def draw_landmarks(self, frame, landmarks):
        """Draw the skeleton for one hand; returns the frame."""
        from renderer import draw_hand_skeleton
        return draw_hand_skeleton(frame, landmarks, HAND_CONNECTIONS)
