"""Gesture recognition: finger poses, classification, state and smoothing.

Duck-typed landmarks (objects with ``.x``/``.y``) are accepted so this
module can be unit-tested without MediaPipe or a camera. Finger-pose
primitives live in :mod:`finger_detector` and are re-exported here for
backwards compatibility.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, Sequence, Tuple

import config
from finger_detector import (
    count_fingers,
    extended_fingers,
    is_finger_extended,
    is_fist,
    is_index_point,
    is_open_palm,
    is_pinch,
    is_thumb_extended,
    is_thumbs_up,
    pinch_strength,
)

# --- Shape gesture names (preserved original behavior, extensible) ---
LINE = "LINE"
SPHERE = "SPHERE"
RECTANGLE = "RECTANGLE"
CIRCLE = "CIRCLE"
RECT = "RECT"
NONE = "NONE"

# --- Semantic actions (interaction intents for the drawing studio) ---
ACTION_IDLE = "IDLE"
ACTION_DRAW = "DRAW"
ACTION_SHAPE = "SHAPE"
ACTION_PAUSE = "PAUSE"
ACTION_ERASE = "ERASE"
ACTION_CONFIRM = "CONFIRM"
ACTION_PINCH = "PINCH"

MATCH_CONFIDENCE = 0.95


class GestureState(Enum):
    """Lifecycle of a tracked gesture."""

    IDLE = auto()  # no hands / no gesture
    DETECTED = auto()  # seen for a single frame
    CANDIDATE = auto()  # repeating but below the confirm threshold
    STABLE = auto()  # just reached the confirm threshold
    ACTIVE = auto()  # held beyond the confirm threshold
    RELEASED = auto()  # previously stable gesture lost (grace period)


def classify_two_hands(finger_counts: Tuple[int, int]) -> Tuple[str, float]:
    """Map two-hand finger counts to (gesture name, confidence).

    Preserved behavior: 5+5 -> LINE, 2+2 -> SPHERE, 3+/3+ -> RECTANGLE.
    """
    f1, f2 = finger_counts
    if f1 == 5 and f2 == 5:
        return LINE, MATCH_CONFIDENCE
    if f1 == 2 and f2 == 2:
        return SPHERE, MATCH_CONFIDENCE
    if f1 >= 3 and f2 >= 3:
        return RECTANGLE, MATCH_CONFIDENCE
    return NONE, 0.0


def classify_single_hand(finger_count: int) -> Tuple[str, float]:
    """Map a single-hand finger count to (gesture name, confidence).

    Preserved behavior: 1 -> LINE, 2 -> CIRCLE, anything else -> RECT.
    """
    if finger_count == 1:
        return LINE, MATCH_CONFIDENCE
    if finger_count == 2:
        return CIRCLE, MATCH_CONFIDENCE
    return RECT, MATCH_CONFIDENCE


def classify_action_single(hand, handedness=None) -> Tuple[str, float]:
    """Map one hand's pose to a semantic (action, confidence) pair.

    Priority order (deliberate actions first):
    PINCH > ERASE(fist) > CONFIRM(thumbs-up) > DRAW(index) >
    SHAPE(two fingers) > PAUSE(palm) > IDLE.
    """
    if hand is None or len(hand) < 21:
        return ACTION_IDLE, 0.0
    if is_pinch(hand):
        return ACTION_PINCH, 0.90
    if is_fist(hand):
        return ACTION_ERASE, MATCH_CONFIDENCE
    if is_thumbs_up(hand, handedness):
        return ACTION_CONFIRM, MATCH_CONFIDENCE
    if is_index_point(hand, handedness):
        return ACTION_DRAW, MATCH_CONFIDENCE
    fingers = extended_fingers(hand, handedness)
    if fingers == ["index", "middle"] or count_fingers(hand, handedness) == 2:
        # Two-finger pose -> shape mode (kept consistent with the
        # original single-hand CIRCLE overlay for 2 fingers).
        if not is_pinch(hand):
            return ACTION_SHAPE, MATCH_CONFIDENCE
    if is_open_palm(hand, handedness):
        return ACTION_PAUSE, MATCH_CONFIDENCE
    return ACTION_IDLE, 0.0


@dataclass
class GestureResult:
    """Structured result of one classification step."""

    name: str = NONE
    confidence: float = 0.0
    hand_count: int = 0
    finger_counts: Tuple[int, ...] = field(default_factory=tuple)
    is_stable: bool = False
    # Studio fields (default neutral so legacy checks keep working):
    action: str = ACTION_IDLE
    state: "GestureState" = GestureState.IDLE
    pinch: bool = False
    pinch_strength: float = 0.0

    def __str__(self) -> str:
        counts = ", ".join(
            f"Hand {i + 1}: {c} fingers" for i, c in enumerate(self.finger_counts)
        )
        return (
            f"Gesture: {self.name}\n"
            f"Confidence: {self.confidence:.2f}\n"
            f"Hands: {self.hand_count}\n"
            f"{counts}\n"
            f"Stable: {self.is_stable}"
        )


class GestureClassifier:
    """Stateless classifier: hands + handedness -> :class:`GestureResult`."""

    def classify(self, hands: Sequence, handedness: Sequence = ()) -> GestureResult:
        """Classify up to two hands.

        Extra hands beyond the first two are ignored (matches MAX_HANDS).
        """
        hands = list(hands or [])[:2]
        handedness = list(handedness or [])

        def _label(i: int):
            return handedness[i] if i < len(handedness) else None

        counts = tuple(count_fingers(hand, _label(i)) for i, hand in enumerate(hands))
        if len(hands) >= 2:
            name, conf = classify_two_hands((counts[0], counts[1]))
            pinch = any(is_pinch(h) for h in hands)
            strength = max((pinch_strength(h) for h in hands), default=0.0)
            return GestureResult(name=name, confidence=conf, hand_count=2,
                                 finger_counts=counts, action=ACTION_IDLE,
                                 pinch=pinch, pinch_strength=strength)
        if len(hands) == 1:
            name, conf = classify_single_hand(counts[0])
            action, aconf = classify_action_single(hands[0], _label(0))
            pinch = is_pinch(hands[0])
            # A pinch overrides an ambiguous IDLE action but never a
            # deliberate pose (erase/confirm/draw/...).
            if pinch and action == ACTION_IDLE:
                action, aconf = ACTION_PINCH, 0.90
            return GestureResult(name=name, confidence=conf, hand_count=1,
                                 finger_counts=counts, action=action,
                                 pinch=pinch,
                                 pinch_strength=pinch_strength(hands[0]))
        return GestureResult(name=NONE, confidence=0.0, hand_count=0, finger_counts=())


class GestureSmoother:
    """Temporal debouncer with release grace and one-shot cooldowns.

    * A raw gesture must repeat ``confirm_frames`` times to become the
      confirmed gesture (kills single-frame flicker).
    * Losing the gesture for fewer than ``release_frames`` keeps the old
      confirmation (``RELEASED`` grace state).
    * One-shot actions (e.g. CONFIRM) are rate-limited by ``cooldown``.
    """

    def __init__(self, confirm_frames: int = config.GESTURE_CONFIRM_FRAMES,
                 release_frames: int = config.GESTURE_RELEASE_FRAMES,
                 cooldown: float = config.GESTURE_COOLDOWN):
        self.confirm_frames = max(1, int(confirm_frames))
        self.release_frames = max(1, int(release_frames))
        self.cooldown = max(0.0, float(cooldown))
        self._candidate = NONE
        self._streak = 0
        self._confirmed = NONE
        self._missing = 0
        self._state = GestureState.IDLE
        self._last_trigger: dict = {}

    def update(self, raw_name: str) -> Tuple[str, bool]:
        """Feed one raw gesture name; return (confirmed_name, is_stable)."""
        raw_name = raw_name or NONE
        if raw_name == NONE:
            self._missing += 1
            if self._confirmed != NONE and self._missing <= self.release_frames:
                self._state = GestureState.RELEASED
                return self._confirmed, True
            self._candidate = NONE
            self._streak = 0
            self._confirmed = NONE
            self._state = GestureState.IDLE
            return self._confirmed, False
        self._missing = 0
        if raw_name == self._candidate:
            self._streak += 1
        else:
            self._candidate = raw_name
            self._streak = 1
        if self._streak >= self.confirm_frames:
            first = self._confirmed != self._candidate
            self._confirmed = self._candidate
            self._state = GestureState.STABLE if first else GestureState.ACTIVE
            return self._confirmed, True
        self._state = (GestureState.DETECTED if self._streak == 1
                       else GestureState.CANDIDATE)
        return self._confirmed, False

    def update_result(self, result: GestureResult) -> GestureResult:
        """Smooth a :class:`GestureResult`, preserving its current counts.

        Only ``name``, ``is_stable`` and ``state`` come from the
        temporal history; ``confidence``/counts always describe the
        current frame.
        """
        confirmed, is_stable = self.update(result.name)
        result.name = confirmed
        result.is_stable = is_stable
        result.state = self._state
        return result

    def ready(self, action: str, now: Optional[float] = None) -> bool:
        """Rate-limit one-shot actions; returns True and arms cooldown."""
        now = time.monotonic() if now is None else now
        last = self._last_trigger.get(action, float("-inf"))
        if now - last < self.cooldown:
            return False
        self._last_trigger[action] = now
        return True

    def reset(self) -> None:
        """Forget all history (e.g. when the camera drops)."""
        self._candidate = NONE
        self._streak = 0
        self._confirmed = NONE
        self._missing = 0
        self._state = GestureState.IDLE

    @property
    def confirmed(self) -> str:
        """Currently confirmed gesture name."""
        return self._confirmed

    @property
    def state(self) -> GestureState:
        """Current lifecycle state."""
        return self._state
