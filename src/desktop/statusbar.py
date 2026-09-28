"""Bottom status bar with live fields from engine state."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class StatusBar(ttk.Frame):
    """Nine-field status bar; all values come from the engine snapshot."""

    FIELDS = (("Tool", 10), ("Gesture", 13), ("Hands", 5), ("Conf", 6),
              ("FPS", 5), ("Brush", 8), ("Smooth", 5), ("Canvas", 11),
              ("Objects", 6))

    def __init__(self, parent):
        super().__init__(parent, padding=(4, 2))
        self.vars: dict = {}
        for name, width in self.FIELDS:
            cell = ttk.Frame(self)
            cell.pack(side="left", padx=2)
            ttk.Label(cell, text=f"{name}:").pack(side="left")
            var = tk.StringVar(value="—")
            ttk.Label(cell, textvariable=var, width=width,
                      relief="sunken", padding=(3, 1)).pack(side="left")
            self.vars[name] = var

    def refresh(self, snap: dict) -> None:
        """Update every field from the snapshot."""
        tool = snap.get("tool")
        self.vars["Tool"].set(tool.value if tool is not None else "—")
        gesture = snap.get("gesture", "NONE")
        action = snap.get("action", "IDLE")
        label = gesture if gesture != "NONE" else "—"
        if action and action != "IDLE":
            label = f"{label} ({action})"
        self.vars["Gesture"].set(label)
        self.vars["Hands"].set(str(snap.get("hands", 0)))
        self.vars["Conf"].set(f"{snap.get('confidence', 0.0) * 100:.0f}%")
        self.vars["FPS"].set(f"{snap.get('fps', 0.0):.0f}")
        self.vars["Brush"].set(f"{snap.get('brush_size', 0)} px")
        self.vars["Smooth"].set(f"{snap.get('smoothing', 0.0) * 100:.0f}%")
        view = f"{snap.get('view_w', 0)}×{snap.get('view_h', 0)}"
        self.vars["Canvas"].set(view if snap.get('view_w') else "—")
        self.vars["Objects"].set(str(snap.get("items", 0)))
