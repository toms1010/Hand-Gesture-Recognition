"""Central configuration for the AI Hand Gesture Drawing Studio.

All tunable values live here so behaviour can be changed without
editing the application modules. Runtime overrides are persisted to
``settings.json`` (see :mod:`settings_store`); values below are the
factory defaults.
"""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SETTINGS_PATH = str(PROJECT_ROOT / "settings.json")

# --- Camera ---
CAMERA_ID = 0
CAMERA_WIDTH = None  # e.g. 1280 (None = driver default)
CAMERA_HEIGHT = None  # e.g. 720 (None = driver default)
CAMERA_FPS = None
MIRROR_FEED = True  # selfie view

# --- MediaPipe hand detection ---
MAX_HANDS = 2
MIN_DETECTION_CONFIDENCE = 0.5
MIN_HAND_PRESENCE_CONFIDENCE = 0.5
MIN_TRACKING_CONFIDENCE = 0.5
MODEL_PATH = str(PROJECT_ROOT / "models" / "gesture_recognizer.task")
DETECT_TIMEOUT = 8.0  # watchdog budget per MediaPipe detect call (seconds)
DETECT_MAX_WIDTH = 960  # downscale wider frames before detection
DETECT_SLOW_WARN = 1.5  # log a warning when detect exceeds this (seconds)

# --- Gesture engine / state machine ---
GESTURE_CONFIRM_FRAMES = 5  # stable frames before a gesture is confirmed
GESTURE_RELEASE_FRAMES = 3  # missing frames before a gesture is released
GESTURE_COOLDOWN = 0.25  # seconds after a one-shot action (e.g. CONFIRM)
FINGER_ANGLE_THRESHOLD_DEG = 130.0  # PIP joint angle for an extended finger
THUMB_ANGLE_THRESHOLD_DEG = 120.0
PINCH_THRESHOLD = 0.05  # normalized thumb-index distance for a pinch
ZOOM_SMOOTHING = 0.15  # exponential smoothing factor for two-hand span
ZOOM_DEADZONE = 0.01  # ignore smaller span changes (normalized units)

# --- Drawing defaults ---
BRUSH_SIZE = 6
BRUSH_COLOR = (43, 255, 255)  # BGR warm yellow, visible on dark canvas
BRUSH_OPACITY = 1.0  # 0.0-1.0 stroke opacity
GLOW_ENABLED = True
ANTIALIAS = True
SHAPE_RECOGNITION = False  # auto-perfect rough shapes (optional)
CANVAS_BACKGROUND = (24, 24, 28)  # dark studio backdrop
CANVAS_BG_MODE = "dark"  # dark|white|black|grid|custom
CANVAS_BG_CUSTOM = (24, 24, 28)
GRID_SIZE = 32
SNAP_TO_GRID = False
ERASER_SIZE = 28
ERASER_SOFT = True
UNDO_LIMIT = 100

# --- Pointer smoothing (0.0-1.0; higher = smoother, default ~= 70%) ---
SMOOTHING = 0.7
DEAD_ZONE_PX = 2.0  # ignore fingertip jitter below this radius
SMOOTHING_MIN_ALPHA = 0.15  # slow movement: heavy smoothing
SMOOTHING_MAX_ALPHA = 0.9  # fast movement: responsive

# --- Animation ---
ANIMATIONS = "full"  # full|minimal|off

# --- Autosave / recovery ---
AUTOSAVE_SECONDS = 10
AUTOSAVE_PATH = str(PROJECT_ROOT / "autosave.json")

# --- UI ---
DEBUG = True
SHOW_LANDMARKS = True
SHOW_FPS = True
SHOW_GESTURE_HINTS = True
WINDOW_NAME = "AI Gesture Drawing Studio"
FONT_SCALE = 1.0
TEXT_THICKNESS = 2
