"""Shared synthetic-landmark builders for unit tests (no camera needed)."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def lm(x: float, y: float, z: float = 0.0):
    """Create a duck-typed normalized landmark."""
    return SimpleNamespace(x=x, y=y, z=z)


# Finger joint layout: (tip, pip, dip, mcp, base_x).
_FINGERS = {
    "index": (8, 6, 7, 5, 0.35),
    "middle": (12, 10, 11, 9, 0.45),
    "ring": (16, 14, 15, 13, 0.55),
    "pinky": (20, 18, 19, 17, 0.65),
}

_WRIST = (0.5, 0.9)


def make_hand(fingers_open=("index", "middle", "ring", "pinky"),
              thumb_open=True, wrist=_WRIST):
    """Build 21 landmarks with deterministic open/folded poses.

    Extended fingers are straight vertical segments (PIP angle 180);
    folded fingers curl back toward the wrist (acute angle + tip nearer
    the wrist than the PIP joint).
    """
    fingers_open = set(fingers_open)
    points = [lm(*wrist)] + [lm(0.5, 0.5) for _ in range(20)]
    for name, (tip, pip, dip, mcp, bx) in _FINGERS.items():
        if name in fingers_open:
            points[mcp] = lm(bx, 0.60)
            points[pip] = lm(bx, 0.45)
            points[dip] = lm(bx, 0.30)
            points[tip] = lm(bx, 0.15)
        else:
            points[mcp] = lm(bx, 0.60)
            points[pip] = lm(bx, 0.50)
            points[dip] = lm(bx, 0.55)
            points[tip] = lm(bx, 0.52)
    # Middle MCP doubles as the palm reference (0.45, 0.60).
    if thumb_open:
        points[2] = lm(0.35, 0.70)  # thumb MCP
        points[3] = lm(0.28, 0.62)  # thumb IP
        points[4] = lm(0.18, 0.50)  # thumb tip (far from palm)
    else:
        points[2] = lm(0.35, 0.70)
        points[3] = lm(0.40, 0.64)
        points[4] = lm(0.44, 0.62)  # tucked near the palm
    return points


def make_pinch_hand():
    """Index extended with the thumb tip touching the index tip."""
    hand = make_hand(fingers_open=("index",), thumb_open=False)
    hand[4] = lm(hand[8].x + 0.01, hand[8].y + 0.01)
    # Re-anchor thumb IP/MCP so the thumb still reads as extended.
    hand[3] = lm(0.30, 0.40)
    hand[2] = lm(0.33, 0.60)
    return hand
