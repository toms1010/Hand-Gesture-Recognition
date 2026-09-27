"""Right sidebar: gesture status card, guide, tool info, debug panel."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

class Sidebar(ttk.Frame):
    """Collapsible right panel bound to app callbacks."""

    def __init__(self, parent, app):
        super().__init__(parent, padding=6, width=220)
        self.app = app
        self.pack_propagate(False)
        self._build_status_card()
        ttk.Separator(self, orient="horizontal").pack(fill="x", pady=6)
        self._build_guide()
        ttk.Separator(self, orient="horizontal").pack(fill="x", pady=6)
        self._build_tool_info()
        ttk.Separator(self, orient="horizontal").pack(fill="x", pady=6)
        self._build_debug()

    def _build_status_card(self):
        card = ttk.LabelFrame(self, text="Gesture Status", padding=6)
        card.pack(fill="x")
        self.dot = tk.Label(card, text="●", font=("TkDefaultFont", 16))
        self.dot.pack(side="left", padx=(0, 6))
        self.gesture_var = tk.StringVar(value="—")
        ttk.Label(card, textvariable=self.gesture_var,
                  font=("TkDefaultFont", 11, "bold")).pack(side="left")
        self.detail_var = tk.StringVar(value="")
        ttk.Label(card, textvariable=self.detail_var, wraplength=180,
                  justify="left").pack(fill="x", pady=(4, 0))

    def _build_guide(self):
        self.guide_frame = ttk.LabelFrame(self, text="Gesture Guide", padding=6)
        self.guide_frame.pack(fill="x")
        try:
            default_bg = ttk.Style(self).lookup("TLabel", "background") or "#d9d9d9"
        except tk.TclError:
            default_bg = "#d9d9d9"
        self._default_row_bg = default_bg
        self.guide_rows: dict = {}
        rows = [
            ("DRAW", "☝ Draw — index finger"),
            ("SHAPE", "✌ Shape — two fingers (N)"),
            ("PAUSE", "✋ Pause — open palm"),
            ("ERASE", "✊ Erase — fist"),
            ("PINCH", "🤏 Select — pinch"),
            ("CONFIRM", "👍 Confirm — thumbs-up"),
        ]
        for key, text in rows:
            label = tk.Label(self.guide_frame, text=text, anchor="w",
                             background=default_bg)
            label.pack(fill="x")
            self.guide_rows[key] = label
        ttk.Label(self.guide_frame, text="TWO HANDS",
                  font=("TkDefaultFont", 9, "bold")).pack(anchor="w", pady=(6, 0))
        two_hand_rows = [
            ("LINE", "5 + 5 → Line overlay"),
            ("SPHERE", "2 + 2 → Sphere overlay"),
            ("RECTANGLE", "3+ + 3+ → Rectangle"),
            ("ZOOM", "Apart/together → Zoom"),
        ]
        for key, text in two_hand_rows:
            label = tk.Label(self.guide_frame, text=text, anchor="w",
                             background=default_bg)
            label.pack(fill="x")
            self.guide_rows[key] = label

    def highlight_gesture(self, action: str, two_hand: str | None) -> None:
        """Highlight the detected gesture row; dim the rest."""
        active = set()
        if action and action != "IDLE":
            active.add(action)
        if two_hand in ("LINE", "SPHERE", "RECTANGLE"):
            active.add(two_hand)
        for key, label in self.guide_rows.items():
            label.configure(background="#3a3a22" if key in active
                            else self._default_row_bg)

    def _build_tool_info(self):
        box = ttk.LabelFrame(self, text="Tool", padding=6)
        box.pack(fill="x")
        self.tool_var = tk.StringVar(value="pencil")
        ttk.Label(box, textvariable=self.tool_var,
                  font=("TkDefaultFont", 10, "bold")).pack(anchor="w")
        self.shape_var = tk.StringVar(value="")
        ttk.Label(box, textvariable=self.shape_var, wraplength=180,
                  justify="left").pack(anchor="w")

    def _build_debug(self):
        self.debug_frame = ttk.LabelFrame(self, text="Debug", padding=6)
        try:
            bg = ttk.Style(self).lookup("TFrame", "background") or "#d9d9d9"
        except tk.TclError:
            bg = "#d9d9d9"
        self.debug_text = tk.Text(self.debug_frame, height=10, width=26,
                                  relief="flat", background=bg)
        self.debug_text.pack(fill="both", expand=True)
        self.debug_text.configure(state="disabled")
        self.debug_visible = False

    def set_debug_visible(self, visible: bool) -> None:
        """Show or hide the debug panel."""
        self.debug_visible = visible
        if visible:
            self.debug_frame.pack(fill="both", expand=True, pady=(0, 0))
        else:
            self.debug_frame.pack_forget()

    def refresh(self, snap: dict) -> None:
        """Update card + tool info + debug text from engine state."""
        gesture = snap.get("gesture", "NONE")
        stable = snap.get("stable", False)
        action = snap.get("action", "IDLE")
        self.dot.configure(foreground="#35c835" if stable else "#c8c8c8")
        self.gesture_var.set(gesture if gesture != "NONE" else "—")
        conf = snap.get("confidence", 0.0)
        counts = ", ".join(str(c) for c in snap.get("finger_counts", ()))
        self.detail_var.set(
            f"Action: {action}\n"
            f"Confidence: {conf * 100:.0f}%   Hands: {snap.get('hands', 0)}\n"
            f"Fingers: {counts or '—'}   State: {snap.get('state', 'IDLE')}")
        tool = snap.get("tool")
        tool_name = tool.value if tool is not None else "—"
        shape = snap.get("shape_tool")
        shape_name = shape.value if shape is not None else ""
        self.tool_var.set(f"{tool_name}   size {snap.get('brush_size', 0)}")
        self.shape_var.set(f"Shape gesture: {shape_name}" if shape_name else "")
        if self.debug_visible:
            lines = [
                f"FPS: {snap.get('fps', 0.0):.1f}",
                f"Latency: {snap.get('latency_ms', 0.0):.1f} ms",
                f"Zoom: {snap.get('zoom', 1.0):.2f}x",
                f"Objects: {snap.get('items', 0)}",
                f"Undo: {snap.get('can_undo')}  Redo: {snap.get('can_redo')}",
                f"Pinch: {snap.get('pinch', 0.0):.2f}",
                f"Fingers: {snap.get('finger_info', '')}",
                f"Transient: {snap.get('transient_error', '') or '—'}",
            ]
            self.debug_text.configure(state="normal")
            self.debug_text.delete("1.0", "end")
            self.debug_text.insert("1.0", "\n".join(lines))
            self.debug_text.configure(state="disabled")
