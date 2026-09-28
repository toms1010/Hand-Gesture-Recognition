"""Tkinter desktop studio: main window wiring the real CV engine.

Threading: :class:`worker.EngineWorker` runs camera + MediaPipe +
canvas off the GUI thread; this module polls it via ``root.after`` and
owns all widgets. No gesture or drawing logic lives here — widgets call
engine methods and display engine snapshots.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk
from datetime import datetime
from pathlib import Path
import time

import cv2
from PIL import Image as PILImage, ImageTk

import config
import settings_store
import applog
from camera import Camera, CameraError
from canvas import Canvas
from gesture_engine import GestureClassifier, GestureSmoother
from hand_tracker import HandTracker
from interaction_controller import InteractionController
from tools import Tool, tool_from_shortcut
from desktop.dialogs import AboutDialog, HelpDialog, SettingsDialog
from desktop.sidebar import Sidebar
from desktop.statusbar import StatusBar
from desktop.toolbar import Toolbar
from desktop.view import VIEW_LABELS, ViewMode, compose_view
from desktop.worker import EngineWorker

EXPORT_DIR = Path(__file__).resolve().parents[1] / "exports"
WINDOW_TITLE = "AI Gesture Drawing Studio"


class NullCamera:
    """Stand-in when no webcam is available (disconnected path)."""

    def get_frame(self):
        return None

    def release(self):
        pass


class GestureStudioApp(tk.Tk):
    """Main desktop window."""

    def __init__(self, camera_id: int = config.CAMERA_ID, camera=None):
        super().__init__()
        self.title(WINDOW_TITLE)
        self.minsize(800, 550)
        self._fit_to_screen()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.view_mode = ViewMode.CAMERA_DRAWING
        self.split_view = True  # camera preview | drawing canvas panes
        self.show_sidebar = True
        self.show_debug = bool(config.DEBUG)
        self.display_images: dict = {}
        self.camera_id = camera_id
        self._poll_count = 0
        self._last_autosave_revision = -1
        self._last_autosave_time = 0.0
        self._last_camera_ok: bool | None = None
        self._closed = False
        self._after_ids: set = set()
        self._poll_after_id: str | None = None
        self._autosave_after_id: str | None = None
        self._pan_drag: dict = {}
        self._build_style()
        self._build_menubar()
        self._build_topbar()
        self.toolbar = Toolbar(self, self)
        self.toolbar.pack(side="top", fill="x")
        self._build_main_area()
        self.statusbar = StatusBar(self)
        self.statusbar.pack(side="bottom", fill="x")
        self.sidebar.set_debug_visible(self.show_debug)
        self._build_bindings()
        # Engine components (single ownership; worker guards with a lock).
        settings_store.apply(settings_store.load())
        self.canvas = Canvas()
        self.canvas.bg_mode = getattr(config, "CANVAS_BG_MODE", "dark")
        self.canvas.bg_custom = tuple(getattr(config, "CANVAS_BG_CUSTOM", (24, 24, 28)))
        self.canvas.antialias = bool(getattr(config, "ANTIALIAS", True))
        self.controller = InteractionController(self.canvas)
        self.controller.brush_size = config.BRUSH_SIZE
        self.controller.brush_color = tuple(config.BRUSH_COLOR)
        self.controller.brush_opacity = float(getattr(config, "BRUSH_OPACITY", 1.0))
        self.controller.glow = config.GLOW_ENABLED
        self.controller.eraser_size = config.ERASER_SIZE
        self._maybe_recover()
        if camera is not None:
            self.camera = camera
            self.camera_ok = True
        else:
            try:
                self.camera = Camera(camera_id)
                self.camera_ok = True
            except CameraError as exc:
                applog.get_logger().warning("Camera unavailable: %s", exc)
                self.camera = NullCamera()
                self.camera_ok = False
        try:
            self.tracker = HandTracker()
        except FileNotFoundError as exc:
            applog.log_exception("MediaPipe model missing", exc)
            self.destroy()
            raise SystemExit(f"Error: {exc}")
        self.worker = EngineWorker(
            self.camera, self.tracker, self.canvas, self.controller,
            GestureClassifier(), GestureSmoother(),
            mirror=config.MIRROR_FEED, show_landmarks=config.SHOW_LANDMARKS,
            include_canvas=not self.split_view)
        self.worker.start()
        self._poll_after_id = self._schedule(33, self._poll)
        self._autosave_after_id = self._schedule(5000, self._autosave_tick)

    def _schedule(self, delay_ms: int, callback) -> str | None:
        """Schedule a callback and track its after id for clean shutdown."""
        holder: dict = {}
        def _run():
            self._after_ids.discard(holder.get("id"))
            callback()
        try:
            after_id = self.after(delay_ms, _run)
        except tk.TclError:
            return None
        holder["id"] = after_id
        self._after_ids.add(after_id)
        return after_id

    # --- layout ---
    def _fit_to_screen(self) -> None:
        """Fill the available desktop (maximized; geometry fallback)."""
        # Linux WMs usually honour "-zoomed", Windows honours "zoomed".
        for attempt in ("zoomed-attr", "zoomed-state"):
            try:
                if attempt == "zoomed-attr":
                    self.update_idletasks()
                    self.attributes("-zoomed", True)
                else:
                    self.update_idletasks()
                    self.state("zoomed")
                return
            except tk.TclError:
                continue
        try:
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
            self.geometry(f"{sw}x{max(550, sh - 60)}+0+0")
        except tk.TclError:
            self.geometry("1200x750")
    def _build_style(self):
        style = ttk.Style(self)
        for theme in ("clam", "alt", "default"):
            try:
                style.theme_use(theme)
                break
            except tk.TclError:
                continue
        style.configure("TButton", padding=(6, 4))
        style.configure("Accent.TButton", font=("TkDefaultFont", 9, "bold"))

    def _build_menubar(self):
        menubar = tk.Menu(self)
        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="New Canvas", accelerator="Ctrl+N",
                              command=self.new_canvas)
        file_menu.add_command(label="Open Project…", command=self.open_project)
        file_menu.add_command(label="Save Project", accelerator="Ctrl+S",
                              command=self.save_project)
        file_menu.add_separator()
        file_menu.add_command(label="Export PNG", accelerator="X",
                              command=self.export_png)
        file_menu.add_command(label="Export JPG", accelerator="Ctrl+E",
                              command=self.export_jpg)
        file_menu.add_command(label="Export SVG", command=self.export_svg)
        file_menu.add_command(label="Screenshot", command=self.screenshot)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", accelerator="Q", command=self.close)
        menubar.add_cascade(label="File", menu=file_menu)
        edit_menu = tk.Menu(menubar, tearoff=False)
        edit_menu.add_command(label="Undo", accelerator="Ctrl+Z", command=self.undo)
        edit_menu.add_command(label="Redo", accelerator="Ctrl+Y / Ctrl+Shift+Z",
                              command=self.redo)
        edit_menu.add_command(label="Delete Selected", accelerator="Del",
                              command=self.delete_selected)
        edit_menu.add_command(label="Clear", accelerator="C", command=self.clear_canvas)
        menubar.add_cascade(label="Edit", menu=edit_menu)
        view_menu = tk.Menu(menubar, tearoff=False)
        self.split_var = tk.BooleanVar(value=True)
        view_menu.add_checkbutton(label="Split Camera/Canvas", variable=self.split_var,
                                  command=self._toggle_split)
        self.view_var = tk.StringVar(value=VIEW_LABELS[self.view_mode])
        for mode, label in VIEW_LABELS.items():
            view_menu.add_radiobutton(label=label, variable=self.view_var,
                                      value=label,
                                      command=lambda m=mode: self.set_view_mode(m))
        view_menu.add_separator()
        view_menu.add_command(label="Zoom In", accelerator="Ctrl++",
                              command=lambda: self.zoom_step(1.25))
        view_menu.add_command(label="Zoom Out", accelerator="Ctrl+-",
                              command=lambda: self.zoom_step(0.8))
        view_menu.add_command(label="Reset Zoom", command=self.reset_zoom)
        view_menu.add_separator()
        self.landmarks_var = tk.BooleanVar(value=config.SHOW_LANDMARKS)
        view_menu.add_checkbutton(label="Show Landmarks", variable=self.landmarks_var,
                                  command=self._toggle_landmarks)
        self.sidebar_var = tk.BooleanVar(value=True)
        view_menu.add_checkbutton(label="Sidebar", variable=self.sidebar_var,
                                  command=self._toggle_sidebar)
        self.debug_var = tk.BooleanVar(value=self.show_debug)
        view_menu.add_checkbutton(label="Debug Panel", variable=self.debug_var,
                                  command=self._toggle_debug)
        menubar.add_cascade(label="View", menu=view_menu)
        tools_menu = tk.Menu(menubar, tearoff=False)
        from tools import TOOL_CYCLE, get_tool_info
        for tool in TOOL_CYCLE:
            info = get_tool_info(tool)
            label = info.label if info else tool.value
            tools_menu.add_command(label=label, command=lambda t=tool: self.set_tool(t))
        menubar.add_cascade(label="Tools", menu=tools_menu)
        help_menu = tk.Menu(menubar, tearoff=False)
        help_menu.add_command(label="Gesture Guide", accelerator="H",
                              command=self.open_help)
        help_menu.add_command(label="About", command=self.open_about)
        menubar.add_cascade(label="Help", menu=help_menu)
        self.configure(menu=menubar)

    def _build_topbar(self):
        bar = ttk.Frame(self, padding=(8, 4))
        bar.pack(side="top", fill="x")
        ttk.Label(bar, text=WINDOW_TITLE,
                  font=("TkDefaultFont", 12, "bold")).pack(side="left")
        ttk.Button(bar, text="Guide", width=7,
                   command=self._toggle_sidebar).pack(side="right", padx=2)
        ttk.Button(bar, text="Help", width=7,
                   command=self.open_help).pack(side="right", padx=2)
        ttk.Button(bar, text="⚙ Settings", width=10,
                   command=self.open_settings).pack(side="right", padx=2)
        self.reconnect_btn = ttk.Button(bar, text="Reconnect", width=10,
                                        command=self.reconnect_camera)
        self.fps_var = tk.StringVar(value="FPS: —")
        ttk.Label(bar, textvariable=self.fps_var, width=9).pack(side="right", padx=6)
        self.cam_var = tk.StringVar(value="")
        self.cam_label = ttk.Label(bar, textvariable=self.cam_var, width=20)
        self.cam_label.pack(side="right", padx=6)

    def _build_main_area(self):
        self.paned = ttk.PanedWindow(self, orient="horizontal")
        self.paned.pack(side="top", fill="both", expand=True)
        self.view_paned = ttk.PanedWindow(self.paned, orient="horizontal")
        self.paned.add(self.view_paned, weight=1)
        self.camera_label = ttk.Label(self.view_paned, anchor="center",
                                      text="Starting camera…")
        self.view_paned.add(self.camera_label, weight=1)
        self.canvas_label = ttk.Label(self.view_paned, anchor="center",
                                      text="Canvas")
        self.view_paned.add(self.canvas_label, weight=1)
        self.sidebar = Sidebar(self.paned, self)
        self.paned.add(self.sidebar, weight=0)

    def _build_bindings(self):
        guarded = self._guarded
        self.bind("<q>", guarded(self.close))
        self.bind("<Q>", guarded(self.close))
        self.bind("<Escape>", guarded(self.cancel_gesture))
        self.bind("<Control-z>", guarded(self.undo))
        self.bind("<Control-Z>", guarded(self.redo))
        self.bind("<Control-y>", guarded(self.redo))
        self.bind("<Control-Y>", guarded(self.redo))
        self.bind("<Control-s>", guarded(self.save_project))
        self.bind("<Control-S>", guarded(self.save_project))
        self.bind("<Control-e>", guarded(self.export_jpg))
        self.bind("<Control-E>", guarded(self.export_jpg))
        self.bind("<Control-o>", guarded(self.open_project))
        self.bind("<Control-O>", guarded(self.open_project))
        self.bind("<Control-n>", guarded(self.new_canvas))
        self.bind("<Control-N>", guarded(self.new_canvas))
        self.bind("<Control-plus>", guarded(lambda: self.zoom_step(1.25)))
        self.bind("<Control-minus>", guarded(lambda: self.zoom_step(0.8)))
        self.bind("<F11>", guarded(self.toggle_fullscreen))
        self.bind("<Delete>", guarded(self.delete_selected))
        self.bind("<BackSpace>", guarded(self.delete_selected))
        self.bind("<space>", guarded(self.stamp))
        self.bind("<Tab>", guarded(self.cycle_tool))
        for key in ("c", "p", "b", "l", "o", "r", "t", "e", "v", "n", "g",
                    "d", "h", "s", "x", "C", "P", "B", "L", "O", "R", "T",
                    "E", "V", "N", "G", "D", "H", "S", "X"):
            self.bind(f"<{key}>", self._on_letter)
        for digit in "123456":
            self.bind(f"<{digit}>", self._on_palette)
        self.bind("<plus>", guarded(lambda: self.nudge_brush(1)))
        self.bind("<equal>", guarded(lambda: self.nudge_brush(1)))
        self.bind("<minus>", guarded(lambda: self.nudge_brush(-1)))
        self._bind_canvas_mouse()

    def _bind_canvas_mouse(self):
        """Ctrl+wheel zoom, middle-drag pan on both view panes."""
        for widget in (self.camera_label, self.canvas_label):
            widget.bind("<Control-MouseWheel>",
                        lambda e: self.zoom_step(1.15 if e.delta > 0 else 0.87))
            widget.bind("<Control-Button-4>", lambda _e: self.zoom_step(1.15))
            widget.bind("<Control-Button-5>", lambda _e: self.zoom_step(0.87))
            widget.bind("<ButtonPress-2>", self._pan_start)
            widget.bind("<B2-Motion>", self._pan_move)

    def _pan_start(self, event) -> None:
        self._pan_drag = {"x": event.x, "y": event.y}

    def _pan_move(self, event) -> None:
        start = self._pan_drag
        if not start:
            return
        dx, dy = event.x - start["x"], event.y - start["y"]
        if dx or dy:
            # Screen px -> canvas px at the pane's display scale.
            self.worker.apply(lambda: self.canvas.pan_by(dx, dy))
            start["x"], start["y"] = event.x, event.y

    # --- poll loop (GUI thread; throttled widget refresh) ---
    def _poll(self):
        if self._closed:
            return
        try:
            frame, snap = self.worker.latest()
            self._show_frames(frame)
            self.toolbar.refresh(snap)
            self._poll_count += 1
            if self._poll_count % 4 == 0:  # ~8 Hz for expensive widgets
                self.sidebar.refresh(snap)
                self.sidebar.highlight_gesture(
                    snap.get("action", "IDLE"),
                    snap.get("gesture") if snap.get("hands", 0) >= 2 else None)
                self.statusbar.refresh(snap)
            self._refresh_topbar(snap)
        except (RuntimeError, tk.TclError):
            pass  # shutting down / widgets destroyed
        if not self._closed:
            try:
                if self.winfo_exists():
                    self._poll_after_id = self._schedule(33, self._poll)
            except tk.TclError:
                self._poll_after_id = None

    def _fit_label(self, label, img):
        avail_w = max(label.winfo_width(), 320)
        avail_h = max(label.winfo_height(), 240)
        from desktop.view import fit_to_pane
        return fit_to_pane(img, avail_w, avail_h)

    def _set_label_image(self, label, key, bgr):
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        photo = ImageTk.PhotoImage(PILImage.fromarray(rgb))
        self.display_images[key] = photo
        label.configure(image=photo, text="")

    def _show_frames(self, frame):
        if self.split_view:
            if not self._pane_has(self.canvas_label):
                self.view_paned.add(self.canvas_label, weight=1)
            if frame is None:
                cam_view = compose_view(self.view_mode, None, None, 320, 240)
            else:
                cam_view = frame
            self._set_label_image(self.camera_label, "camera",
                                  self._fit_label(self.camera_label, cam_view))
            scene = self.worker.apply(
                lambda: self.canvas.render_scene(640, 480))
            self._set_label_image(self.canvas_label, "canvas",
                                  self._fit_label(self.canvas_label, scene))
            self.display_image = self.display_images.get("camera")
        else:
            if self._pane_has(self.canvas_label):
                self.view_paned.forget(self.canvas_label)
            avail_w = max(self.camera_label.winfo_width(), 320)
            avail_h = max(self.camera_label.winfo_height(), 240)
            if frame is None:
                view = compose_view(self.view_mode, None, self.canvas,
                                    avail_w, avail_h)
            else:
                h, w = frame.shape[:2]
                scale = min(avail_w / w, avail_h / h)
                view = frame if scale >= 0.99 else cv2.resize(
                    frame, (max(1, int(w * scale)), max(1, int(h * scale))))
            self._set_label_image(self.camera_label, "camera", view)
            self.display_image = self.display_images.get("camera")

    @staticmethod
    def _pane_has(widget) -> bool:
        return bool(widget.winfo_manager())

    def _refresh_topbar(self, snap: dict):
        camera_ok = bool(snap.get("camera_ok"))
        if camera_ok != self._last_camera_ok:
            self._last_camera_ok = camera_ok
            if camera_ok:
                self.cam_var.set("● Camera Connected")
                self.cam_label.configure(foreground="#1a7f1a")
                try:
                    self.reconnect_btn.pack_forget()
                except tk.TclError:
                    pass
            else:
                self.cam_var.set("⚠ Camera Disconnected")
                self.cam_label.configure(foreground="#b00000")
                try:
                    if not self.reconnect_btn.winfo_ismapped():
                        self.reconnect_btn.pack(side="right", padx=2)
                except tk.TclError:
                    pass
        try:
            self.fps_var.set(f"FPS: {snap.get('fps', 0.0):.0f}")
        except tk.TclError:
            pass

    # --- toolbar callbacks (real engine actions) ---
    def set_tool(self, tool: Tool) -> None:
        """Switch the drawing tool."""
        self.worker.apply(lambda: self.controller.set_tool(tool))

    def cycle_tool(self) -> None:
        """Cycle to the next tool."""
        from tools import TOOL_CYCLE
        current = self.worker.apply(lambda: self.controller.tool)
        idx = TOOL_CYCLE.index(current) if current in TOOL_CYCLE else -1
        self.set_tool(TOOL_CYCLE[(idx + 1) % len(TOOL_CYCLE)])

    def set_color(self, color) -> None:
        """Set the brush color (BGR tuple)."""
        color = tuple(int(v) for v in color)
        self.worker.apply(lambda: setattr(self.controller, "brush_color", color))

    def choose_color(self) -> None:
        """Custom color via the native chooser."""
        current = self.worker.apply(lambda: self.controller.brush_color)
        b, g, r = (int(v) for v in current)
        picked = colorchooser.askcolor(color=f"#{r:02x}{g:02x}{b:02x}",
                                       title="Brush color")
        if picked[0] is not None:
            r, g, b = (int(v) for v in picked[0])
            self.set_color((b, g, r))

    def set_brush_size(self, size: int) -> None:
        """Set the brush size (1–100 px)."""
        size = min(100, max(1, int(size)))
        self.worker.apply(lambda: setattr(self.controller, "brush_size", size))

    def set_brush_opacity(self, opacity: float) -> None:
        """Set the brush opacity (0.01–1.0)."""
        opacity = min(1.0, max(0.01, float(opacity)))
        self.worker.apply(lambda: setattr(self.controller, "brush_opacity", opacity))

    def nudge_brush(self, delta: int) -> None:
        """Grow/shrink the brush."""
        current = self.worker.apply(lambda: self.controller.brush_size)
        self.set_brush_size(current + delta)

    def set_view_mode(self, mode) -> None:
        """Switch Camera+Drawing / Drawing Only / Camera Only (single view)."""
        if isinstance(mode, str):
            for enum_mode, label in VIEW_LABELS.items():
                if mode in (enum_mode.value, label):
                    mode = enum_mode
                    break
        self.view_mode = mode
        self.view_var.set(VIEW_LABELS.get(mode, str(mode)))
        if self.split_view:  # a concrete mode implies the single view
            self.split_var.set(False)
            self._toggle_split()

    def undo(self) -> None:
        """Undo one canvas command."""
        self.worker.apply(lambda: self.canvas.undo())

    def delete_selected(self) -> None:
        """Delete the dragged/selected item, else the most recent one."""
        def _delete():
            index = self.controller.drag_index
            if index is None and self.canvas.items:
                index = len(self.canvas.items) - 1
            if index is not None:
                return self.canvas.delete_item(index)
            return False
        self.worker.apply(_delete)

    def cancel_gesture(self) -> None:
        """Cancel the in-progress stroke/preview (Esc)."""
        self.worker.apply(lambda: self.controller.cancel_active())

    def toggle_fullscreen(self) -> None:
        """Toggle fullscreen (F11)."""
        self.attributes("-fullscreen", not self.attributes("-fullscreen"))

    def zoom_step(self, factor: float) -> None:
        """Multiply canvas zoom (mouse wheel / menu)."""
        self.worker.apply(
            lambda: self.canvas.set_zoom(self.canvas.zoom * factor))

    def reset_zoom(self) -> None:
        """Reset zoom + pan."""
        self.worker.apply(lambda: self.canvas.reset_view())

    def _toggle_split(self) -> None:
        self.split_view = self.split_var.get()
        self.worker.apply(lambda: setattr(
            self.worker, "include_canvas", not self.split_view))

    def redo(self) -> None:
        """Redo one canvas command."""
        self.worker.apply(lambda: self.canvas.redo())

    def clear_canvas(self) -> None:
        """Clear the canvas (undoable)."""
        self.worker.apply(lambda: self.canvas.clear())

    def new_canvas(self) -> None:
        """Clear the canvas after confirmation."""
        if messagebox.askyesno("New Canvas", "Clear the current drawing?"):
            self.clear_canvas()

    def stamp(self) -> None:
        """Stamp the active preview or stabilized two-hand overlay."""
        self.worker.apply(lambda: self.worker.stamp_active())

    def cycle_shape(self) -> None:
        """Cycle the two-finger shape tool."""
        self.worker.apply(lambda: self.controller.cycle_shape_tool())

    # --- file actions ---
    def _exports(self) -> Path:
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        return EXPORT_DIR

    def export_png(self) -> None:
        """Export the canvas PNG."""
        try:
            path = self.worker.apply(
                lambda: self.canvas.save_png(
                    self._exports() / datetime.now().strftime("canvas_%Y%m%d_%H%M%S.png")))
        except OSError as exc:
            applog.log_exception("Export PNG failed", exc)
            messagebox.showerror("Export PNG", f"Export failed: {exc}")
            return
        messagebox.showinfo("Export PNG", f"Saved:\n{path}")

    def export_jpg(self) -> None:
        """Export the canvas JPG (opaque scene render)."""
        try:
            path = self.worker.apply(
                lambda: self.canvas.save_jpg(
                    self._exports() / datetime.now().strftime("canvas_%Y%m%d_%H%M%S.jpg")))
        except OSError as exc:
            applog.log_exception("Export JPG failed", exc)
            messagebox.showerror("Export JPG", f"Export failed: {exc}")
            return
        messagebox.showinfo("Export JPG", f"Saved:\n{path}")

    def export_svg(self) -> None:
        """Export vector SVG built from stroke/shape data."""
        try:
            path = self.worker.apply(
                lambda: self.canvas.export_svg(
                    self._exports() / datetime.now().strftime("canvas_%Y%m%d_%H%M%S.svg")))
        except OSError as exc:
            applog.log_exception("Export SVG failed", exc)
            messagebox.showerror("Export SVG", f"Export failed: {exc}")
            return
        messagebox.showinfo("Export SVG", f"Saved:\n{path}")

    def screenshot(self) -> None:
        """Save the current camera view."""
        if self.display_images.get("camera") is None:
            return
        path = self._exports() / datetime.now().strftime("shot_%Y%m%d_%H%M%S.png")
        try:
            ImageTk.getimage(self.display_images["camera"]).save(str(path))
        except (OSError, ValueError) as exc:
            messagebox.showerror("Screenshot", f"Screenshot failed: {exc}")
            return
        messagebox.showinfo("Screenshot", f"Saved:\n{path}")

    def save_project(self) -> None:
        """Save the vector project JSON."""
        path = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("Gesture project", "*.json")],
            initialfile=datetime.now().strftime("project_%Y%m%d_%H%M%S.json"))
        if not path:
            return
        try:
            self.worker.apply(lambda: self.canvas.save_project(path))
        except OSError as exc:
            messagebox.showerror("Save Project", f"Save failed: {exc}")

    def open_project(self) -> None:
        """Load a vector project JSON (replaces canvas)."""
        path = filedialog.askopenfilename(filetypes=[("Gesture project", "*.json")])
        if not path:
            return
        try:
            loaded = Canvas.load_project(path)
        except (OSError, ValueError, KeyError) as exc:
            messagebox.showerror("Open Project", f"Open failed: {exc}")
            return
        self.worker.apply(lambda: self.canvas.replace_with(loaded))

    # --- camera / settings ---
    # --- autosave / recovery ---
    def _autosave_path(self) -> Path:
        return Path(config.AUTOSAVE_PATH)

    def _maybe_recover(self) -> None:
        """Offer recovery when a previous session left an autosave behind."""
        path = self._autosave_path()
        try:
            if not path.is_file() or path.stat().st_size == 0:
                return
            probe = Canvas.load_project(path)
        except (OSError, ValueError, KeyError):
            return
        if probe.stroke_count == 0:
            return
        if messagebox.askyesno("Recover Drawing",
                                "Unsaved drawing detected from a previous session.\n"
                                "Recover it?"):
            self.canvas.replace_with(probe)

    def _autosave_tick(self) -> None:
        """Periodically persist the canvas (dirty-check via revision)."""
        if self._closed:
            return
        try:
            interval = max(5, int(getattr(config, "AUTOSAVE_SECONDS", 10)))
            revision = self.worker.apply(lambda: self.canvas.revision)
            now = time.monotonic()
            if (revision != self._last_autosave_revision
                    and now - self._last_autosave_time >= interval):
                self.worker.apply(
                    lambda: self.canvas.save_project(self._autosave_path()))
                self._last_autosave_revision = revision
                self._last_autosave_time = now
        except (OSError, RuntimeError, ValueError) as exc:
            applog.log_exception("Autosave failed", exc)
        except tk.TclError:
            pass
        if not self._closed:
            try:
                if self.winfo_exists():
                    self._autosave_after_id = self._schedule(5000, self._autosave_tick)
            except tk.TclError:
                self._autosave_after_id = None

    def _clear_autosave(self) -> None:
        try:
            self._autosave_path().unlink(missing_ok=True)
        except OSError:
            pass

    def reconnect_camera(self) -> None:
        """Retry opening the webcam (device open stays off the engine lock)."""
        try:
            camera = Camera(self.camera_id)
        except CameraError as exc:
            self._snap_camera_error(str(exc))
            return

        def _swap():
            old = self.camera
            self.camera = camera
            self.worker.camera = camera
            return True

        try:
            old_camera = self.camera
        except AttributeError:
            old_camera = None
        if self.worker.apply(_swap):
            self.camera_ok = True
            if old_camera is not None and old_camera is not camera:
                try:
                    old_camera.release()
                except Exception:
                    pass

    def _snap_camera_error(self, message: str) -> None:
        with self.worker._lock:
            self.worker._snap["camera_ok"] = False
            self.worker._snap["camera_error"] = message

    def apply_settings(self, overrides: dict) -> None:
        """Live-apply settings dialog output to the running engine."""
        def _apply():
            self.controller.brush_size = int(overrides.get(
                "BRUSH_SIZE", self.controller.brush_size))
            self.controller.brush_opacity = min(1.0, max(0.01, float(overrides.get(
                "BRUSH_OPACITY", self.controller.brush_opacity))))
            self.controller.glow = bool(overrides.get(
                "GLOW_ENABLED", self.controller.glow))
            self.controller.eraser_size = int(overrides.get(
                "ERASER_SIZE", self.controller.eraser_size))
            self.controller.snap_to_grid = bool(overrides.get(
                "SNAP_TO_GRID", self.controller.snap_to_grid))
            self.controller.pointer.smoothing = min(1.0, max(0.0, float(overrides.get(
                "SMOOTHING", self.controller.pointer.smoothing))))
            self.controller.pointer.dead_zone_px = max(0.0, float(overrides.get(
                "DEAD_ZONE_PX", self.controller.pointer.dead_zone_px)))
            self.canvas.antialias = bool(overrides.get(
                "ANTIALIAS", self.canvas.antialias))
            self.canvas.bg_mode = str(overrides.get("CANVAS_BG_MODE", self.canvas.bg_mode))
            custom = overrides.get("CANVAS_BG_CUSTOM", self.canvas.bg_custom)
            try:
                self.canvas.bg_custom = tuple(int(v) for v in custom)
            except (TypeError, ValueError):
                pass
            self.canvas.grid_size = max(4, int(overrides.get(
                "GRID_SIZE", self.canvas.grid_size)))
            self.canvas._dirty = True
            self.worker.mirror = bool(overrides.get(
                "MIRROR_FEED", self.worker.mirror))
            self.worker.show_landmarks = bool(overrides.get(
                "SHOW_LANDMARKS", self.worker.show_landmarks))
            smoother = self.worker.smoother
            smoother.confirm_frames = max(1, int(overrides.get(
                "GESTURE_CONFIRM_FRAMES", smoother.confirm_frames)))
            smoother.release_frames = max(1, int(overrides.get(
                "GESTURE_RELEASE_FRAMES", smoother.release_frames)))
            smoother.cooldown = max(0.0, float(overrides.get(
                "GESTURE_COOLDOWN", smoother.cooldown)))
            import config as live_config
            live_config.PINCH_THRESHOLD = float(overrides.get(
                "PINCH_THRESHOLD", live_config.PINCH_THRESHOLD))
            live_config.SMOOTHING = self.controller.pointer.smoothing
            live_config.DEAD_ZONE_PX = self.controller.pointer.dead_zone_px
            live_config.BRUSH_OPACITY = self.controller.brush_opacity
            live_config.ANIMATIONS = str(overrides.get(
                "ANIMATIONS", live_config.ANIMATIONS))
            live_config.AUTOSAVE_SECONDS = int(overrides.get(
                "AUTOSAVE_SECONDS", live_config.AUTOSAVE_SECONDS))
            # Vision changes need a tracker rebuild.
            try:
                rebuilt = HandTracker(
                    num_hands=int(overrides.get("MAX_HANDS", config.MAX_HANDS)),
                    min_detection_confidence=float(overrides.get(
                        "MIN_DETECTION_CONFIDENCE",
                        config.MIN_DETECTION_CONFIDENCE)),
                    min_presence_confidence=float(overrides.get(
                        "MIN_HAND_PRESENCE_CONFIDENCE",
                        config.MIN_HAND_PRESENCE_CONFIDENCE)),
                    min_tracking_confidence=float(overrides.get(
                        "MIN_TRACKING_CONFIDENCE",
                        config.MIN_TRACKING_CONFIDENCE)))
            except (FileNotFoundError, RuntimeError) as exc:
                applog.log_exception("Tracker rebuild failed", exc)
                self._snap_camera_error(f"Tracker rebuild failed: {exc}")
                return
            try:
                self.tracker.close()
            except Exception:
                pass
            self.tracker = rebuilt
            self.worker.tracker = rebuilt
            new_camera_id = int(overrides.get("CAMERA_ID", self.camera_id))
            new_width = overrides.get("CAMERA_WIDTH", config.CAMERA_WIDTH)
            new_height = overrides.get("CAMERA_HEIGHT", config.CAMERA_HEIGHT)
            if (new_camera_id != self.camera_id or new_width is not None
                    or new_height is not None):
                try:
                    self.worker.recreate_camera(new_camera_id, width=new_width,
                                                height=new_height)
                    self.camera = self.worker.camera
                    self.camera_id = new_camera_id
                except CameraError as exc:
                    applog.log_exception("Camera switch failed", exc)
                    self._snap_camera_error(str(exc))
        self.worker.apply(_apply)
        self.show_debug = bool(overrides.get("DEBUG", self.show_debug))
        self.debug_var.set(self.show_debug)
        self.sidebar.set_debug_visible(self.show_debug)
        self.landmarks_var.set(bool(overrides.get("SHOW_LANDMARKS",
                                                  self.landmarks_var.get())))

    def open_settings(self) -> None:
        """Open the settings dialog."""
        SettingsDialog(self, self)

    def open_help(self) -> None:
        """Open the help dialog."""
        HelpDialog(self)

    def open_about(self) -> None:
        """Open the about box."""
        AboutDialog(self)

    # --- view toggles ---
    def _toggle_landmarks(self) -> None:
        value = self.landmarks_var.get()
        self.worker.apply(lambda: setattr(self.worker, "show_landmarks", value))

    def _toggle_sidebar(self) -> None:
        self.show_sidebar = not self.show_sidebar
        try:
            self.sidebar_var.set(self.show_sidebar)
        except tk.TclError:
            pass
        try:
            if self.show_sidebar:
                if not bool(self.sidebar.winfo_manager()):
                    self.paned.add(self.sidebar, weight=0)
            else:
                if bool(self.sidebar.winfo_manager()):
                    self.paned.forget(self.sidebar)
        except tk.TclError:
            pass

    def _toggle_debug(self) -> None:
        self.show_debug = self.debug_var.get()
        self.sidebar.set_debug_visible(self.show_debug)

    # --- keyboard helpers ---
    def _in_entry(self, event) -> bool:
        """True when the keypress targets a text-entry widget."""
        widget = getattr(event, "widget", None)
        try:
            return isinstance(widget, (tk.Entry, tk.Text, ttk.Entry,
                                       ttk.Combobox, ttk.Spinbox))
        except Exception:
            return False

    def _guarded(self, fn):
        """Wrap a shortcut so typing in dialogs never triggers actions."""
        def _handler(event=None):
            if event is not None and self._in_entry(event):
                return None
            try:
                return fn()
            except tk.TclError:
                return None
        return _handler

    def _on_letter(self, event) -> None:
        if self._in_entry(event):
            return  # let settings fields / dialogs receive keystrokes
        key = event.char
        if not key:
            return
        actions = {
            "c": self.clear_canvas, "C": self.clear_canvas,
            "e": lambda: self.set_tool(Tool.ERASER),
            "E": lambda: self.set_tool(Tool.ERASER),
            "p": lambda: self.set_tool(Tool.PENCIL),
            "P": lambda: self.set_tool(Tool.PENCIL),
            "b": lambda: self.set_tool(Tool.BRUSH),
            "B": lambda: self.set_tool(Tool.BRUSH),
            "l": lambda: self.set_tool(Tool.LINE),
            "L": lambda: self.set_tool(Tool.LINE),
            "o": lambda: self.set_tool(Tool.CIRCLE),
            "O": lambda: self.set_tool(Tool.CIRCLE),
            "r": lambda: self.set_tool(Tool.RECTANGLE),
            "R": lambda: self.set_tool(Tool.RECTANGLE),
            "t": lambda: self.set_tool(Tool.TRIANGLE),
            "T": lambda: self.set_tool(Tool.TRIANGLE),
            "v": lambda: self.set_tool(Tool.SELECT),
            "V": lambda: self.set_tool(Tool.SELECT),
            "n": self.cycle_shape, "N": self.cycle_shape,
            "g": self._toggle_glow, "G": self._toggle_glow,
            "d": self._toggle_debug_key, "D": self._toggle_debug_key,
            "h": self.open_help, "H": self.open_help,
            "s": self.open_settings, "S": self.open_settings,
            "x": self.export_png, "X": self.export_png,
        }
        action = actions.get(key)
        if action is not None:
            action()
        else:
            tool = tool_from_shortcut(key.lower())
            if tool is not None:
                self.set_tool(tool)

    def _on_palette(self, event) -> None:
        if self._in_entry(event):
            return
        from ui import PALETTE
        try:
            idx = int(event.char) - 1
        except (TypeError, ValueError):
            return
        if 0 <= idx < len(PALETTE):
            self.set_color(PALETTE[idx])

    def _toggle_glow(self) -> None:
        current = self.worker.apply(lambda: self.controller.glow)
        self.worker.apply(lambda: setattr(self.controller, "glow", not current))

    def _toggle_debug_key(self) -> None:
        self.debug_var.set(not self.debug_var.get())
        self._toggle_debug()

    # --- shutdown: stop thread, release camera + MediaPipe, destroy ---
    def close(self) -> None:
        """Stop processing, free resources, close the window (idempotent)."""
        if self._closed:
            return
        self._closed = True
        for after_id in list(getattr(self, "_after_ids", set())):
            try:
                self.after_cancel(after_id)
            except (tk.TclError, RuntimeError, ValueError):
                pass
        self._after_ids.clear()
        self._poll_after_id = self._autosave_after_id = None
        try:
            self.worker.stop()
            self.worker.join(timeout=3.0)
        except RuntimeError:
            pass
        for resource in (getattr(self, "camera", None), getattr(self, "tracker", None)):
            if resource is None:
                continue
            try:
                resource.release() if hasattr(resource, "release") else resource.close()
            except Exception:
                pass
        try:
            settings_store.save({
                "BRUSH_SIZE": self.controller.brush_size,
                "BRUSH_COLOR": list(self.controller.brush_color),
                "BRUSH_OPACITY": float(self.controller.brush_opacity),
                "DEBUG": self.show_debug,
            })
        except (OSError, AttributeError):
            pass
        self._clear_autosave()  # clean exit: no recovery needed next launch
        try:
            self.destroy()
        except tk.TclError:
            pass


def main(camera_id: int = config.CAMERA_ID, camera=None) -> int:
    """Entry point for GUI mode (injectable camera for tests)."""
    app = GestureStudioApp(camera_id=camera_id, camera=camera)
    app.mainloop()
    return 0
