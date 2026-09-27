"""Top toolbar: tools, history, color, brush size, view mode.

Two stacked rows keep every control reachable at the 800 px minimum
window width. Buttons opt out of keyboard focus so Space always means
"stamp", and slider feedback carries a timestamp so the 30 Hz refresh
never fights an active drag.
"""
from __future__ import annotations

import time
import tkinter as tk
from tkinter import ttk

from tools import TOOL_CYCLE, Tool, available_tools
from desktop.view import VIEW_LABELS, VIEW_MODES


class Tooltip:
    """Minimal hover tooltip for toolbar buttons."""

    def __init__(self, widget, text: str):
        self.widget = widget
        self.text = text
        self.tip = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, _event=None):
        if self.tip is not None:
            return
        x = self.widget.winfo_rootx() + 10
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        ttk.Label(self.tip, text=self.text, relief="solid", borderwidth=1,
                  padding=(4, 2)).pack()

    def _hide(self, _event=None):
        if self.tip is not None:
            self.tip.destroy()
            self.tip = None


class Toolbar(ttk.Frame):
    """Toolbar bound to app callbacks (no engine logic here)."""

    def __init__(self, parent, app):
        super().__init__(parent, padding=(6, 2))
        self.app = app
        self.tool_buttons: dict = {}
        self.color_buttons: dict = {}
        self._user_set: dict = {}  # control -> monotonic time of last drag
        row1 = ttk.Frame(self)
        row1.pack(side="top", fill="x")
        self._build_tools(row1)
        ttk.Separator(row1, orient="vertical").pack(side="left", fill="y", padx=6)
        self._build_history(row1)
        row2 = ttk.Frame(self)
        row2.pack(side="top", fill="x", pady=(2, 0))
        self._build_color_size(row2)
        ttk.Separator(row2, orient="vertical").pack(side="left", fill="y", padx=6)
        self._build_mode(row2)

    def _no_focus(self, widget):
        """Keep Space/letters for global shortcuts, not widget activation."""
        try:
            widget.configure(takefocus=False)
        except tk.TclError:
            pass
        return widget

    def _build_tools(self, parent):
        for info in available_tools():
            if info.tool not in TOOL_CYCLE:
                continue
            btn = ttk.Button(parent, text=info.label, width=9,
                             command=lambda t=info.tool: self.app.set_tool(t))
            btn.pack(side="left", padx=2)
            self._no_focus(btn)
            Tooltip(btn, f"{info.label}  (shortcut: {info.shortcut.upper()})")
            self.tool_buttons[info.tool] = btn

    def _build_history(self, parent):
        self.undo_btn = ttk.Button(parent, text="↶ Undo", width=8,
                                   command=self.app.undo)
        self.redo_btn = ttk.Button(parent, text="↷ Redo", width=8,
                                   command=self.app.redo)
        self.clear_btn = ttk.Button(parent, text="🗑 Clear", width=8,
                                    command=self.app.clear_canvas)
        for btn, tip in ((self.undo_btn, "Undo (Ctrl+Z)"),
                         (self.redo_btn, "Redo (Ctrl+Y)"),
                         (self.clear_btn, "Clear canvas (C)")):
            btn.pack(side="left", padx=2)
            self._no_focus(btn)
            Tooltip(btn, tip)

    def _slider_command(self, name, fn):
        def _on_change(value):
            self._user_set[name] = time.monotonic()
            fn(value)
        return _on_change

    def _build_color_size(self, parent):
        ttk.Label(parent, text="Color:").pack(side="left", padx=(2, 4))
        self.swatch = tk.Label(parent, width=3, relief="sunken", borderwidth=2)
        self.swatch.pack(side="left", padx=2)
        Tooltip(self.swatch, "Current brush color")
        for color in app_palette():
            btn = tk.Button(parent, width=2, relief="raised", borderwidth=2,
                            background=_tk_color(color),
                            activebackground=_tk_color(color),
                            takefocus=False,
                            command=lambda c=color: self.app.set_color(c))
            btn.pack(side="left", padx=1)
            self.color_buttons[tuple(color)] = btn
        custom = ttk.Button(parent, text="More…", width=7,
                            command=self.app.choose_color)
        custom.pack(side="left", padx=4)
        self._no_focus(custom)
        Tooltip(custom, "Custom color…")
        ttk.Label(parent, text="Size:").pack(side="left", padx=(6, 2))
        self.size_var = tk.IntVar(value=6)
        self.size_scale = ttk.Scale(parent, from_=1, to=100, orient="horizontal",
                                    length=90, variable=self.size_var,
                                    command=self._slider_command(
                                        "size", lambda v: self.app.set_brush_size(
                                            int(float(v)))))
        self.size_scale.pack(side="left")
        self._no_focus(self.size_scale)
        Tooltip(self.size_scale, "Brush size 1–100 px (+/-)")
        self.size_label = ttk.Label(parent, text="6 px", width=6)
        self.size_label.pack(side="left")
        ttk.Label(parent, text="Opacity:").pack(side="left", padx=(6, 2))
        self.opacity_var = tk.IntVar(value=100)
        self.opacity_scale = ttk.Scale(parent, from_=1, to=100,
                                       orient="horizontal", length=70,
                                       variable=self.opacity_var,
                                       command=self._slider_command(
                                           "opacity",
                                           lambda v: self.app.set_brush_opacity(
                                               int(float(v)) / 100.0)))
        self.opacity_scale.pack(side="left")
        self._no_focus(self.opacity_scale)
        Tooltip(self.opacity_scale, "Brush opacity 1–100%")
        self.opacity_label = ttk.Label(parent, text="100%", width=5)
        self.opacity_label.pack(side="left")

    def _build_mode(self, parent):
        ttk.Label(parent, text="View:").pack(side="left", padx=(2, 4))
        self.mode_var = tk.StringVar(value=VIEW_LABELS[VIEW_MODES[0]])
        self.mode_box = ttk.Combobox(parent, textvariable=self.mode_var,
                                     values=[VIEW_LABELS[m] for m in VIEW_MODES],
                                     state="readonly", width=16)
        self.mode_box.pack(side="left")
        self._no_focus(self.mode_box)
        Tooltip(self.mode_box, "Camera + Drawing / Drawing Only / Camera Only")
        self.mode_box.bind("<<ComboboxSelected>>",
                           lambda _e: self.app.set_view_mode(self.mode_var.get()))

    def _recently_dragged(self, name: str) -> bool:
        return time.monotonic() - self._user_set.get(name, 0.0) < 0.4

    # --- state refresh (called from the GUI poll loop) ---
    def refresh(self, snap: dict) -> None:
        """Sync selected states + Undo/Redo availability from engine state."""
        current = snap.get("tool")
        for tool, btn in self.tool_buttons.items():
            btn.state(["pressed"] if tool is not None and tool == current
                      else ["!pressed"])
        self.undo_btn.state(["!disabled"] if snap.get("can_undo") else ["disabled"])
        self.redo_btn.state(["!disabled"] if snap.get("can_redo") else ["disabled"])
        color = tuple(snap.get("brush_color", (0, 0, 0)))
        self.swatch.configure(background=_tk_color(color))
        size = min(100, max(1, int(snap.get("brush_size", 6))))
        if not self._recently_dragged("size") and int(self.size_var.get()) != size:
            self.size_var.set(size)
        self.size_label.configure(text=f"{size} px")
        opacity = int(round(min(1.0, max(0.01, float(
            snap.get("brush_opacity", 1.0)))) * 100))
        if not self._recently_dragged("opacity") and int(self.opacity_var.get()) != opacity:
            self.opacity_var.set(opacity)
        self.opacity_label.configure(text=f"{opacity}%")
        for known, btn in self.color_buttons.items():
            btn.configure(relief="sunken" if known == color else "raised")


def app_palette():
    """Brush color presets (BGR, shared with the OpenCV UI)."""
    from ui import PALETTE
    return list(PALETTE)


def _tk_color(bgr) -> str:
    """BGR tuple -> Tk hex color string."""
    b, g, r = (int(max(0, min(255, v))) for v in bgr)
    return f"#{r:02x}{g:02x}{b:02x}"
