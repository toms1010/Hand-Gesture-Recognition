"""Modern dark studio interface: bars, toolbar, debug, help, settings."""
from __future__ import annotations

import cv2
import numpy as np

import config
from gesture_engine import CIRCLE, LINE, NONE, RECT, RECTANGLE, SPHERE, GestureResult
from tools import available_tools
from utils import draw_text

GESTURE_COLORS = {
    LINE: (0, 255, 255),
    SPHERE: (0, 255, 255),
    CIRCLE: (255, 0, 0),
    RECTANGLE: (0, 255, 0),
    RECT: (0, 255, 0),
    NONE: (0, 0, 255),
}

BAR_BG = (32, 32, 38)
BAR_TEXT = (235, 235, 240)
BAR_DIM = (150, 150, 160)
ACCENT = (43, 255, 255)
ACTIVE_BG = (70, 60, 20)

PALETTE = [
    (43, 255, 255),   # yellow
    (0, 255, 0),      # green
    (255, 0, 0),      # blue
    (255, 0, 255),    # magenta
    (0, 165, 255),    # orange
    (255, 255, 255),  # white
]


def gesture_display_label(result: GestureResult) -> str:
    """Human-readable label preserving the original application's wording."""
    if result.hand_count >= 2:
        if result.name == LINE:
            return "LINE (both open)"
        if result.name == SPHERE:
            return "SPHERE"
        if result.name == RECTANGLE:
            return "RECTANGLE"
        return "No matching two-hand gesture"
    if result.hand_count == 1:
        if result.name == LINE:
            return "LINE (single)"
        if result.name == CIRCLE:
            return "CIRCLE (single)"
        return "RECT (single)"
    return "No hands detected"


def _bar(frame, y0: int, height: int):
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, y0), (frame.shape[1], y0 + height), BAR_BG, -1)
    frame[:] = cv2.addWeighted(overlay, 0.85, frame, 0.15, 0)
    return frame


def _trim_to_fit(text: str, max_width: int, font_scale: float = 0.5,
                 thickness: int = 2) -> str:
    """Trim text with an ellipsis until it fits max_width pixels."""
    if max_width <= 20:
        return ""
    (tw, _), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX,
                                 font_scale, thickness)
    while tw > max_width and len(text) > 10:
        text = text[:-2]
        (tw, _), _ = cv2.getTextSize(text + "…", cv2.FONT_HERSHEY_SIMPLEX,
                                     font_scale, thickness)
    return text + ("…" if tw > max_width else "")


def draw_top_bar(frame, camera_ok: bool = True):
    """Title bar: app name + camera status dot."""
    _bar(frame, 0, 34)
    width = frame.shape[1]
    title = "AI GESTURE DRAWING STUDIO" if width >= 480 else "STUDIO"
    draw_text(frame, title, (10, 24), font_scale=0.65, color=BAR_TEXT)
    status = "CAMERA" if camera_ok else "NO CAMERA"
    color = (0, 220, 0) if camera_ok else (0, 0, 255)
    (tw, _), _ = cv2.getTextSize(status, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
    x = width - tw - 28
    if x > 10 + len(title) * 9:  # avoid overlapping the title on narrow frames
        cv2.circle(frame, (x, 17), 6, color, -1, cv2.LINE_AA)
        draw_text(frame, status, (x + 12, 24), font_scale=0.55, color=BAR_TEXT)
    else:  # narrow frame: dot only, no text
        cv2.circle(frame, (width - 16, 17), 6, color, -1, cv2.LINE_AA)
    return frame


def draw_toolbar(frame, current_tool, hint: str = ""):
    """Bottom tool strip with the active tool highlighted."""
    height, width = frame.shape[:2]
    tools = available_tools()
    _bar(frame, height - 60, 60)
    x = 10
    for info in tools:
        label = f"{info.label}"
        active = info.tool == current_tool
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
        if active:
            cv2.rectangle(frame, (x - 6, height - 52), (x + tw + 6, height - 14),
                          ACTIVE_BG, -1, cv2.LINE_AA)
            cv2.rectangle(frame, (x - 6, height - 52), (x + tw + 6, height - 14),
                          ACCENT, 1, cv2.LINE_AA)
        draw_text(frame, label, (x, height - 26), font_scale=0.5,
                  color=ACCENT if active else BAR_DIM)
        x += tw + 22
        if x > width - 120:
            break
    if hint and config.SHOW_GESTURE_HINTS:
        draw_text(frame, _trim_to_fit(hint[:64], width - 20),
                  (10, height - 68), font_scale=0.5, color=BAR_DIM)
    return frame


def draw_status_bar(frame, result: GestureResult, fps: float, canvas=None,
                    tool=None, brush_size: int = 0):
    """One-line status above the toolbar: gesture/FPS/hands/tool."""
    height, width = frame.shape[:2]
    label = gesture_display_label(result)
    action = f" {result.action}" if result.action and result.action != "IDLE" else ""
    strokes = f" items:{canvas.stroke_count}" if canvas is not None else ""
    tool_name = f" {tool.value}" if tool is not None else ""
    text = (f"Gesture:{label}{action}  FPS:{fps:.0f}  "
            f"Hands:{result.hand_count}{tool_name}  size:{brush_size}{strokes}")
    color = GESTURE_COLORS.get(result.name, BAR_TEXT)
    draw_text(frame, _trim_to_fit(text[:110], width - 20),
              (10, height - 90), font_scale=0.5, color=color)
    return frame


def draw_fps(frame, fps: float):
    """FPS counter pinned to the top-right (below the title bar)."""
    height, width = frame.shape[:2]
    text = f"FPS: {fps:.1f}"
    (text_w, _), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX,
                                     config.FONT_SCALE, config.TEXT_THICKNESS)
    draw_text(frame, text, (max(width - text_w - 10, 5), 60), color=(0, 255, 0))
    return frame


def draw_debug_panel(frame, result: GestureResult, fps: float, latency_ms: float = 0.0,
                     canvas=None, finger_info: str = ""):
    """Verbose debug block (bottom-left, above the status bar)."""
    lines = [
        f"Gesture: {result.name} [{result.state.name}]",
        f"Confidence: {result.confidence * 100:.0f}%",
        f"Action: {result.action}  pinch:{result.pinch_strength:.2f}",
        f"Hands: {result.hand_count}",
    ]
    for i, count in enumerate(result.finger_counts):
        lines.append(f"Hand {i + 1}: {count} fingers")
    lines.append(f"Stable: {result.is_stable}")
    if canvas is not None:
        lines.append(f"Canvas: {canvas.stroke_count} items  zoom:{canvas.zoom:.2f}x "
                     f"undo:{canvas.can_undo} redo:{canvas.can_redo}")
    lines.append(f"FPS: {fps:.1f}  Latency: {latency_ms:.0f} ms")
    if finger_info:
        lines.append(finger_info[:72])
    # Fit short frames: keep the tail (most actionable) lines only.
    height = frame.shape[0]
    max_lines = max(1, (height - 170) // 22)
    lines = lines[-max_lines:]
    y = height - 120 - (len(lines) - 1) * 22
    for line in lines:
        draw_text(frame, line, (10, max(int(y), 44)),
                  font_scale=0.55, color=(200, 200, 200))
        y += 22
    return frame


HELP_LINES = [
    "HAND GESTURE GUIDE  (H to close)",
    "",
    "  Show INDEX finger ... Draw / pencil",
    "  TWO fingers ......... Shape mode (N cycles shape)",
    "  OPEN palm ........... Pause",
    "  FIST ................ Erase",
    "  THUMBS-UP ........... Confirm / stamp shape",
    "  PINCH ............... Select-drag / stamp",
    "  TWO hands 5+5 ....... LINE overlay (SPACE stamps)",
    "  TWO hands 2+2 ....... SPHERE overlay (SPACE stamps)",
    "  TWO hands 3+3 ....... RECTANGLE overlay (SPACE stamps)",
    "  Hands apart/together  Zoom canvas",
    "",
    "  Q/ESC quit  CTRL+Z/Y undo/redo  C clear",
    "  P/B/L/O/R/T/V tools  SPACE stamp  D debug",
]


def draw_help_overlay(frame):
    """First-run help screen (semi-transparent panel)."""
    height = frame.shape[0]
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 34), (frame.shape[1], height - 60), (18, 18, 24), -1)
    np.copyto(frame, cv2.addWeighted(overlay, 0.88, frame, 0.12, 0))
    lines = list(HELP_LINES)
    max_lines = max(2, (height - 140) // 26)
    truncated = len(lines) > max_lines
    lines = lines[:max_lines]
    if truncated:
        lines.append("  ... (larger window shows more)")
    y = 80
    for i, line in enumerate(lines):
        scale = 0.7 if i == 0 else 0.55
        color = ACCENT if i == 0 else BAR_TEXT
        draw_text(frame, line, (40, y), font_scale=scale, color=color)
        y += 30 if i == 0 else 26
    return frame


def draw_settings_overlay(frame, settings: dict):
    """Simple settings list overlay."""
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 34), (frame.shape[1], frame.shape[0] - 60), (18, 18, 24), -1)
    np.copyto(frame, cv2.addWeighted(overlay, 0.88, frame, 0.12, 0))
    draw_text(frame, "SETTINGS  (S to close, edits in settings.json)",
              (40, 80), font_scale=0.7, color=ACCENT)
    y = 120
    for key, value in settings.items():
        draw_text(frame, f"{key} = {value}", (40, y), font_scale=0.55, color=BAR_TEXT)
        y += 26
        if y > frame.shape[0] - 100:
            break
    return frame


def draw_hud(frame, result: GestureResult, fps: float, debug: bool = config.DEBUG,
             studio=None, latency_ms: float = 0.0):
    """Compose the full HUD.

    ``studio`` is an optional namespace/dict with toolbar context:
    tool, canvas, brush_size, hint, camera_ok, help/show flags.
    """
    info = studio or {}
    tool = info.get("tool") if isinstance(info, dict) else getattr(info, "tool", None)
    canvas = info.get("canvas") if isinstance(info, dict) else getattr(info, "canvas", None)
    hint = ""
    if isinstance(info, dict):
        h = info.get("hint")
        hint = h.text if hasattr(h, "text") else (h or "")
    camera_ok = info.get("camera_ok", True) if isinstance(info, dict) else True
    brush_size = info.get("brush_size", 0) if isinstance(info, dict) else 0

    draw_top_bar(frame, camera_ok=camera_ok)
    # Full-frame panels first so the bars stay readable on top of them.
    show_help = isinstance(info, dict) and info.get("show_help")
    show_settings = isinstance(info, dict) and info.get("show_settings")
    if show_help:
        draw_help_overlay(frame)
    elif show_settings:
        draw_settings_overlay(frame, info.get("settings_view", {}))
    if config.SHOW_FPS:
        draw_fps(frame, fps)
    draw_status_bar(frame, result, fps, canvas=canvas, tool=tool, brush_size=brush_size)
    draw_toolbar(frame, tool, hint=hint)
    if debug and not show_help:
        finger_info = info.get("finger_info", "") if isinstance(info, dict) else ""
        draw_debug_panel(frame, result, fps, latency_ms, canvas, finger_info)
    return frame
