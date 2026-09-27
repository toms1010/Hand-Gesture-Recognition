"""Lightweight animation envelopes (no retained scene graph).

 Immediate-mode renderer helper: :class:`AnimationManager` tracks
 pulse start times per key; :meth:`pulse_value` returns a 0..1 envelope
 (fast attack, smooth decay) the renderer maps to ring radius/alpha.
 Durations stay in the 100–300 ms band; mode ``off`` disables all.
"""
from __future__ import annotations

import math
import time
from typing import Callable, Dict, Optional


class AnimationManager:
    """Trigger-and-query pulse envelopes with an injectable clock."""

    def __init__(self, duration_ms: float = 220.0,
                 clock: Optional[Callable[[], float]] = None):
        self.duration_ms = max(1.0, float(duration_ms))
        self._clock = clock or time.monotonic
        self._starts: Dict[str, float] = {}

    def pulse(self, key: str) -> None:
        """(Re)start the pulse envelope for ``key``."""
        self._starts[key] = self._clock()

    def pulse_value(self, key: str) -> float:
        """Current envelope 0..1 (0 = idle/expired)."""
        start = self._starts.get(key)
        if start is None:
            return 0.0
        age_ms = (self._clock() - start) * 1000.0
        if age_ms < 0 or age_ms >= self.duration_ms:
            self._starts.pop(key, None)
            return 0.0
        t = age_ms / self.duration_ms
        return math.sin(math.pi * min(1.0, t))  # smooth in-out blip

    def active(self, key: str) -> bool:
        """Whether ``key`` currently has a live envelope."""
        return self.pulse_value(key) > 0.0

    def clear(self, key: Optional[str] = None) -> None:
        """Clear one key, or all envelopes when ``key`` is None."""
        if key is None:
            self._starts.clear()
        else:
            self._starts.pop(key, None)
