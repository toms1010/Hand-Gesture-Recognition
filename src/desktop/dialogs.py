"""Settings / Help / About dialogs for the desktop studio."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import config


class SettingsDialog(tk.Toplevel):
    """Live settings editor; Apply writes through to config + disk."""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.title("Settings")
        self.resizable(False, False)
        self.vars: dict = {}
        self._seed_derived_vars()
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=8, pady=8)
        self._camera_tab(notebook)
        self._tracking_tab(notebook)
        self._gesture_tab(notebook)
        self._drawing_tab(notebook)
        self._canvas_perf_tab(notebook)
        self._debug_tab(notebook)
        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(buttons, text="Apply", command=self._apply).pack(side="right")
        ttk.Button(buttons, text="Close", command=self.destroy).pack(side="right", padx=6)
        self.transient(parent)
        self.bind("<Escape>", lambda _e: self.destroy())
        self.grab_set()

    def _var(self, key, value):
        var = tk.BooleanVar(value=bool(value)) if isinstance(value, bool) else None
        if var is None:
            var = tk.StringVar(value=str(value))
        self.vars[key] = var
        return var

    def _seed_derived_vars(self):
        """Pre-populate vars for fields without a direct config counterpart."""
        custom = getattr(config, "CANVAS_BG_CUSTOM", (24, 24, 28))
        seeds = {
            "CAMERA_WIDTH": "" if getattr(config, "CAMERA_WIDTH", None) is None
            else str(config.CAMERA_WIDTH),
            "CAMERA_HEIGHT": "" if getattr(config, "CAMERA_HEIGHT", None) is None
            else str(config.CAMERA_HEIGHT),
            "SMOOTHING_PCT": str(int(round(float(
                getattr(config, "SMOOTHING", 0.7)) * 100))),
            "BRUSH_OPACITY_PCT": str(int(round(float(
                getattr(config, "BRUSH_OPACITY", 1.0)) * 100))),
            "CANVAS_BG_CUSTOM_TXT": ",".join(str(int(v)) for v in custom),
        }
        for key, value in seeds.items():
            self.vars[key] = tk.StringVar(value=value)

    def _row(self, parent, label, key, kind="entry", values=None):
        frame = ttk.Frame(parent)
        frame.pack(fill="x", padx=8, pady=3)
        ttk.Label(frame, text=label, width=22).pack(side="left")
        if key in self.vars:
            var = self.vars[key]
        else:
            var = self._var(key, getattr(config, key))
        if kind == "check":
            ttk.Checkbutton(frame, variable=var).pack(side="left")
        elif kind == "combo":
            ttk.Combobox(frame, textvariable=var,
                         values=values, state="readonly", width=12).pack(side="left")
        else:
            ttk.Entry(frame, textvariable=var, width=14).pack(side="left")

    def _camera_tab(self, notebook):
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="Camera")
        self._row(tab, "Camera ID", "CAMERA_ID")
        self._row(tab, "Width (blank=default)", "CAMERA_WIDTH")
        self._row(tab, "Height (blank=default)", "CAMERA_HEIGHT")
        self._row(tab, "Mirror feed", "MIRROR_FEED", kind="check")

    def _tracking_tab(self, notebook):
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="Hand Tracking")
        self._row(tab, "Maximum hands", "MAX_HANDS", kind="combo", values=["1", "2"])
        self._row(tab, "Detection confidence", "MIN_DETECTION_CONFIDENCE")
        self._row(tab, "Presence confidence", "MIN_HAND_PRESENCE_CONFIDENCE")
        self._row(tab, "Tracking confidence", "MIN_TRACKING_CONFIDENCE")

    def _gesture_tab(self, notebook):
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="Gesture")
        self._row(tab, "Confirm frames", "GESTURE_CONFIRM_FRAMES")
        self._row(tab, "Release frames", "GESTURE_RELEASE_FRAMES")
        self._row(tab, "Cooldown (s)", "GESTURE_COOLDOWN")
        self._row(tab, "Pinch threshold", "PINCH_THRESHOLD")
        self._row(tab, "Smoothing 0-100", "SMOOTHING_PCT")
        self._row(tab, "Dead zone (px)", "DEAD_ZONE_PX")

    def _drawing_tab(self, notebook):
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="Drawing")
        self._row(tab, "Brush size", "BRUSH_SIZE")
        self._row(tab, "Brush opacity 0-100", "BRUSH_OPACITY_PCT")
        self._row(tab, "Glow", "GLOW_ENABLED", kind="check")
        self._row(tab, "Anti-aliasing", "ANTIALIAS", kind="check")
        self._row(tab, "Shape recognition", "SHAPE_RECOGNITION", kind="check")
        self._row(tab, "Eraser size", "ERASER_SIZE")
        self._row(tab, "Soft eraser", "ERASER_SOFT", kind="check")
        self._row(tab, "Canvas background", "CANVAS_BG_MODE", kind="combo",
                  values=["dark", "white", "black", "grid", "custom"])
        self._row(tab, "Custom bg BGR", "CANVAS_BG_CUSTOM_TXT")
        self._row(tab, "Grid size", "GRID_SIZE")
        self._row(tab, "Snap to grid", "SNAP_TO_GRID", kind="check")

    def _canvas_perf_tab(self, notebook):
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="Canvas & Perf")
        self._row(tab, "Animations", "ANIMATIONS", kind="combo",
                  values=["full", "minimal", "off"])
        self._row(tab, "Autosave (s)", "AUTOSAVE_SECONDS")

    def _debug_tab(self, notebook):
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="Debug")
        self._row(tab, "Debug panel", "DEBUG", kind="check")
        self._row(tab, "Show landmarks", "SHOW_LANDMARKS", kind="check")
        self._row(tab, "Show FPS", "SHOW_FPS", kind="check")
        self._row(tab, "Show gesture hints", "SHOW_GESTURE_HINTS", kind="check")

    def _apply(self):
        """Validate, apply live, persist. Vision changes rebuild the tracker."""
        import settings_store
        from gesture_engine import GestureSmoother

        def number(key, kind, minimum=None, maximum=None):
            raw = self.vars[key].get()
            try:
                value = kind(raw)
            except (TypeError, ValueError):
                raise ValueError(f"{key} must be a number (got {raw!r})")
            if minimum is not None and value < minimum:
                raise ValueError(f"{key} must be >= {minimum}")
            if maximum is not None and value > maximum:
                raise ValueError(f"{key} must be <= {maximum}")
            return value

        def optional_number(key, kind, minimum=None, maximum=None):
            raw = str(self.vars[key].get()).strip()
            if raw == "":
                return None
            try:
                value = kind(raw)
            except (TypeError, ValueError):
                raise ValueError(f"{key} must be a number (got {raw!r})")
            if minimum is not None and value < minimum:
                raise ValueError(f"{key} must be >= {minimum}")
            if maximum is not None and value > maximum:
                raise ValueError(f"{key} must be <= {maximum}")
            return value

        def parse_bgr(key):
            parts = str(self.vars[key].get()).replace(";", ",").split(",")
            if len(parts) != 3:
                raise ValueError(f"{key} must look like 24,24,28")
            try:
                values = [int(p) for p in parts]
            except ValueError:
                raise ValueError(f"{key} must look like 24,24,28")
            if any(v < 0 or v > 255 for v in values):
                raise ValueError(f"{key} channels must be 0-255")
            return values

        try:
            overrides = {
                "CAMERA_ID": number("CAMERA_ID", int, 0, 10),
                "CAMERA_WIDTH": optional_number("CAMERA_WIDTH", int, 160, 3840),
                "CAMERA_HEIGHT": optional_number("CAMERA_HEIGHT", int, 120, 2160),
                "MIRROR_FEED": bool(self.vars["MIRROR_FEED"].get()),
                "MAX_HANDS": number("MAX_HANDS", int, 1, 2),
                "MIN_DETECTION_CONFIDENCE": number("MIN_DETECTION_CONFIDENCE", float, 0.05, 1.0),
                "MIN_HAND_PRESENCE_CONFIDENCE": number("MIN_HAND_PRESENCE_CONFIDENCE", float, 0.05, 1.0),
                "MIN_TRACKING_CONFIDENCE": number("MIN_TRACKING_CONFIDENCE", float, 0.05, 1.0),
                "GESTURE_CONFIRM_FRAMES": number("GESTURE_CONFIRM_FRAMES", int, 1, 30),
                "GESTURE_RELEASE_FRAMES": number("GESTURE_RELEASE_FRAMES", int, 1, 30),
                "GESTURE_COOLDOWN": number("GESTURE_COOLDOWN", float, 0.0, 5.0),
                "PINCH_THRESHOLD": number("PINCH_THRESHOLD", float, 0.01, 0.3),
                "SMOOTHING": number("SMOOTHING_PCT", float, 0, 100) / 100.0,
                "DEAD_ZONE_PX": number("DEAD_ZONE_PX", float, 0.0, 20.0),
                "BRUSH_SIZE": number("BRUSH_SIZE", int, 1, 100),
                "BRUSH_OPACITY": number("BRUSH_OPACITY_PCT", float, 1, 100) / 100.0,
                "GLOW_ENABLED": bool(self.vars["GLOW_ENABLED"].get()),
                "ANTIALIAS": bool(self.vars["ANTIALIAS"].get()),
                "SHAPE_RECOGNITION": bool(self.vars["SHAPE_RECOGNITION"].get()),
                "ERASER_SIZE": number("ERASER_SIZE", int, 4, 120),
                "ERASER_SOFT": bool(self.vars["ERASER_SOFT"].get()),
                "CANVAS_BG_MODE": str(self.vars["CANVAS_BG_MODE"].get()),
                "CANVAS_BG_CUSTOM": parse_bgr("CANVAS_BG_CUSTOM_TXT"),
                "GRID_SIZE": number("GRID_SIZE", int, 4, 256),
                "SNAP_TO_GRID": bool(self.vars["SNAP_TO_GRID"].get()),
                "ANIMATIONS": str(self.vars["ANIMATIONS"].get()),
                "AUTOSAVE_SECONDS": number("AUTOSAVE_SECONDS", int, 5, 300),
                "DEBUG": bool(self.vars["DEBUG"].get()),
                "SHOW_LANDMARKS": bool(self.vars["SHOW_LANDMARKS"].get()),
                "SHOW_FPS": bool(self.vars["SHOW_FPS"].get()),
                "SHOW_GESTURE_HINTS": bool(self.vars["SHOW_GESTURE_HINTS"].get()),
            }
        except ValueError as exc:
            self._error(str(exc))
            return
        settings_store.apply(overrides)
        try:
            settings_store.save(overrides)
        except OSError as exc:
            self._error(f"Could not save settings.json: {exc}")
            return
        # Live-apply to the running engine.
        self.app.apply_settings(overrides)
        self.destroy()

    def _error(self, message: str):
        dlg = tk.Toplevel(self)
        dlg.title("Invalid setting")
        ttk.Label(dlg, text=message, wraplength=300, padding=12).pack()
        ttk.Button(dlg, text="OK", command=dlg.destroy).pack(pady=(0, 10))
        dlg.transient(self)
        dlg.grab_set()


class HelpDialog(tk.Toplevel):
    """Closable gesture + keyboard reference."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Help — Gesture Guide")
        self.resizable(False, False)
        text = tk.Text(self, width=52, height=26, relief="flat", padx=10, pady=10)
        text.pack(fill="both", expand=True)
        text.insert("1.0", HELP_TEXT)
        text.configure(state="disabled")
        ttk.Button(self, text="Close", command=self.destroy).pack(pady=(0, 10))
        self.bind("<Escape>", lambda _e: self.destroy())
        self.transient(parent)


HELP_TEXT = """HAND GESTURES
  Index finger .... Draw / pencil
  Two fingers ..... Shape mode (N cycles shape)
  Open palm ....... Pause
  Fist ............ Erase
  Thumbs-up ....... Confirm / stamp shape
  Pinch ........... Select-drag / stamp

TWO HANDS
  5 + 5 fingers ... LINE overlay (Space stamps)
  2 + 2 fingers ... SPHERE overlay (Space stamps)
  3+ + 3+ fingers . RECTANGLE overlay (Space stamps)
  Apart / together  Zoom canvas

KEYBOARD
  Q ......... Quit            Esc ............... Cancel gesture
  Ctrl+Z .... Undo            Ctrl+Y / Ctrl+Shift+Z . Redo
  Ctrl+S .... Save project    Ctrl+O ............ Open project
  Ctrl+E .... Export JPG      Ctrl+N ............ New canvas
  C ......... Clear           Del / Backspace ... Delete selected
  P / B ..... Pencil/Brush    L / O / R / T ..... Shapes
  E / V ..... Eraser/Select   N ................. Cycle shape
  Space ..... Stamp           D / H / S ......... Debug/Help/Settings
  G ......... Glow            + / - ............. Brush size
  1-6 ....... Colors          X ................. Export PNG
  Tab ....... Cycle tools     F11 ............... Fullscreen
  Ctrl+Wheel  Zoom            Middle-drag ....... Pan
"""
APP_VERSION = "4.1.0"


class AboutDialog(tk.Toplevel):
    """About box."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("About")
        self.resizable(False, False)
        ttk.Label(self, padding=16, justify="center", text=(
            f"AI Gesture Drawing Studio  {APP_VERSION}\n\n"
            "Real-time hand-gesture drawing with\n"
            "OpenCV + MediaPipe Tasks + NumPy + Tkinter.")).pack()
        ttk.Button(self, text="Close", command=self.destroy).pack(pady=(0, 12))
        self.bind("<Escape>", lambda _e: self.destroy())
        self.transient(parent)
