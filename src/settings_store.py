"""Local settings persistence (JSON, no database)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import config

#: User-tunable keys persisted to settings.json.
SETTINGS_KEYS = (
    "CAMERA_ID",
    "CAMERA_WIDTH",
    "CAMERA_HEIGHT",
    "MIRROR_FEED",
    "MAX_HANDS",
    "MIN_DETECTION_CONFIDENCE",
    "MIN_HAND_PRESENCE_CONFIDENCE",
    "MIN_TRACKING_CONFIDENCE",
    "GESTURE_CONFIRM_FRAMES",
    "GESTURE_RELEASE_FRAMES",
    "GESTURE_COOLDOWN",
    "PINCH_THRESHOLD",
    "BRUSH_SIZE",
    "BRUSH_COLOR",
    "BRUSH_OPACITY",
    "GLOW_ENABLED",
    "ANTIALIAS",
    "SHAPE_RECOGNITION",
    "ERASER_SIZE",
    "ERASER_SOFT",
    "CANVAS_BG_MODE",
    "CANVAS_BG_CUSTOM",
    "GRID_SIZE",
    "SNAP_TO_GRID",
    "SMOOTHING",
    "DEAD_ZONE_PX",
    "ANIMATIONS",
    "AUTOSAVE_SECONDS",
    "DEBUG",
    "SHOW_LANDMARKS",
    "SHOW_FPS",
    "SHOW_GESTURE_HINTS",
)


def defaults() -> Dict[str, Any]:
    """Factory defaults for all persisted keys."""
    return {key: getattr(config, key) for key in SETTINGS_KEYS}


def load(path: str = config.SETTINGS_PATH) -> Dict[str, Any]:
    """Load overrides from JSON; missing/corrupt file -> {}."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in data.items() if k in SETTINGS_KEYS}


def save(overrides: Dict[str, Any], path: str = config.SETTINGS_PATH) -> Path:
    """Merge ``overrides`` into the settings file (whitelisted keys only)."""
    current = load(path)
    current.update({k: v for k, v in overrides.items() if k in SETTINGS_KEYS})
    dest = Path(path)
    dest.write_text(json.dumps(current, indent=2), encoding="utf-8")
    return dest


def apply(overrides: Dict[str, Any]) -> None:
    """Apply overrides to the live :mod:`config` module."""
    for key, value in overrides.items():
        if key in SETTINGS_KEYS:
            setattr(config, key, value)
