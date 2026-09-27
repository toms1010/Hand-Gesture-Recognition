"""Finger-pose detection from normalized hand landmarks.

Uses joint angles + wrist-relative distances + palm-relative thumb
checks so poses survive rotation, tilt and scale changes. All functions
accept duck-typed landmarks (``.x``/``.y``) and need no camera.
"""
from __future__ import annotations

import math
from typing import Dict, List

from geometry import distance, joint_angle
from hand_tracker import (
    INDEX_MCP,
    INDEX_PIP,
    INDEX_TIP,
    MIDDLE_MCP,
    MIDDLE_PIP,
    MIDDLE_TIP,
    PINKY_MCP,
    PINKY_PIP,
    PINKY_TIP,
    RING_MCP,
    RING_PIP,
    RING_TIP,
    THUMB_IP,
    THUMB_MCP,
    THUMB_TIP,
    WRIST,
    handedness_label,
)

import config

# (name, tip, pip, mcp) for the four fingers.
FOUR_FINGERS = (
    ("index", INDEX_TIP, INDEX_PIP, INDEX_MCP),
    ("middle", MIDDLE_TIP, MIDDLE_PIP, MIDDLE_MCP),
    ("ring", RING_TIP, RING_PIP, RING_MCP),
    ("pinky", PINKY_TIP, PINKY_PIP, PINKY_MCP),
)

PALM_REF = MIDDLE_MCP  # near the palm center


def _valid(hand) -> bool:
    return hand is not None and len(hand) >= 21


def is_finger_extended(hand, tip_idx: int, pip_idx: int, mcp_idx: int,
                       angle_threshold_deg: float = config.FINGER_ANGLE_THRESHOLD_DEG) -> bool:
    """Check one finger via distance + PIP joint angle.

    Distance (tip farther from wrist than PIP) is scale/rotation
    invariant; the joint angle confirms straightness. Degenerate angles
    fall back to the distance check alone.
    """
    if not _valid(hand):
        return False
    try:
        wrist, mcp, pip, tip = hand[WRIST], hand[mcp_idx], hand[pip_idx], hand[tip_idx]
        if distance(tip, wrist) <= distance(pip, wrist):
            return False
    except (IndexError, TypeError, AttributeError):
        return False
    angle = joint_angle(mcp, pip, tip)
    if math.isnan(angle):
        return True
    return angle >= angle_threshold_deg


def is_thumb_extended(hand, handedness=None,
                      angle_threshold_deg: float = config.THUMB_ANGLE_THRESHOLD_DEG) -> bool:
    """Check the thumb independent of handedness/mirroring."""
    if not _valid(hand):
        return False
    try:
        tip, ip, mcp = hand[THUMB_TIP], hand[THUMB_IP], hand[THUMB_MCP]
        palm = hand[PALM_REF]
        if distance(tip, palm) <= distance(ip, palm):
            return False
        if distance(tip, mcp) < 0.5 * distance(ip, mcp):
            return False
    except (IndexError, TypeError, AttributeError):
        return False
    angle = joint_angle(mcp, ip, tip)
    if not math.isnan(angle) and angle < angle_threshold_deg:
        return False
    label = handedness if isinstance(handedness, str) else handedness_label(handedness)
    if label in ("Left", "Right"):
        try:
            if abs(float(tip.x) - float(ip.x)) < 0.01:
                return False
        except (AttributeError, TypeError, ValueError):
            pass
    return True


def extended_fingers(hand, handedness=None) -> List[str]:
    """Names of extended fingers, e.g. ``['thumb', 'index']``."""
    if not _valid(hand):
        return []
    result = [name for name, tip, pip, mcp in FOUR_FINGERS
              if is_finger_extended(hand, tip, pip, mcp)]
    if is_thumb_extended(hand, handedness):
        result.append("thumb")
    return result


def count_fingers(hand, handedness=None) -> int:
    """Count extended fingers (0-5), including the thumb."""
    return len(extended_fingers(hand, handedness))


def fingertip_gap(hand, tip_a: int, tip_b: int, scale_ref: float = 0.0) -> float:
    """Normalized distance between two fingertips (raw, for pinch)."""
    if not _valid(hand):
        return float("inf")
    try:
        return distance(hand[tip_a], hand[tip_b])
    except (IndexError, AttributeError):
        return float("inf")


def is_pinch(hand, threshold: float = config.PINCH_THRESHOLD) -> bool:
    """True when thumb tip and index tip are close (normalized units)."""
    if not _valid(hand):
        return False
    return fingertip_gap(hand, THUMB_TIP, INDEX_TIP) < threshold


def pinch_strength(hand, threshold: float = config.PINCH_THRESHOLD) -> float:
    """0.0 (apart) .. 1.0 (touching) pinch measure."""
    if not _valid(hand):
        return 0.0
    gap = fingertip_gap(hand, THUMB_TIP, INDEX_TIP)
    return min(1.0, max(0.0, 1.0 - gap / max(threshold * 2.0, 1e-6)))


def is_fist(hand, handedness=None) -> bool:
    """True when no fingers are extended."""
    return _valid(hand) and count_fingers(hand, handedness) == 0


def is_open_palm(hand, handedness=None) -> bool:
    """True when all five fingers are extended."""
    return _valid(hand) and count_fingers(hand, handedness) == 5


def is_index_point(hand, handedness=None) -> bool:
    """True for index-only pointing (drawing pointer)."""
    fingers = extended_fingers(hand, handedness)
    return fingers == ["index"]


def is_thumbs_up(hand, handedness=None) -> bool:
    """True for thumb-only extension (confirm gesture)."""
    fingers = extended_fingers(hand, handedness)
    return fingers == ["thumb"]


def finger_states(hand, handedness=None) -> Dict[str, bool]:
    """Mapping of finger name -> extended flag (for debug UI)."""
    if not _valid(hand):
        return {name: False for name, _, _, _ in FOUR_FINGERS} | {"thumb": False}
    states = {name: is_finger_extended(hand, tip, pip, mcp)
              for name, tip, pip, mcp in FOUR_FINGERS}
    states["thumb"] = is_thumb_extended(hand, handedness)
    return states
