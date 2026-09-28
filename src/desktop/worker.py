"""Background engine thread: camera + MediaPipe + canvas pipeline.

Runs the real CV pipeline off the Tkinter GUI thread so the window never
freezes. The GUI polls :meth:`EngineWorker.latest` via ``root.after``.
All shared state is guarded by one lock; GUI-initiated mutations go
through :meth:`EngineWorker.apply`.
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Optional

import cv2

import config
from gesture_engine import GestureClassifier, GestureResult, GestureSmoother
from studio_render import render_overlays
from utils import FPS


class EngineWorker(threading.Thread):
    """Owns camera, tracker, classifier, smoother, canvas and controller."""

    def __init__(self, camera, tracker, canvas, controller,
                 classifier: Optional[GestureClassifier] = None,
                 smoother: Optional[GestureSmoother] = None,
                 mirror: bool = True, show_landmarks: bool = True,
                 include_canvas: bool = True):
        super().__init__(daemon=True, name="gesture-engine")
        self.camera = camera
        self.tracker = tracker
        self.canvas = canvas
        self.controller = controller
        self.classifier = classifier or GestureClassifier()
        self.smoother = smoother or GestureSmoother()
        self.mirror = mirror
        self.show_landmarks = show_landmarks
        self.include_canvas = include_canvas
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._frame: Optional[object] = None
        self._last_hands: list = []
        self._last_size: tuple = (640, 480)
        self._last_two_hand: Optional[str] = None
        self._snap: dict = {
            "tool": controller.tool, "shape_tool": controller.shape_tool,
            "brush_size": controller.brush_size, "brush_color": controller.brush_color,
            "glow": controller.glow, "gesture": "NONE", "action": "IDLE",
            "state": "IDLE", "confidence": 0.0, "hands": 0,
            "finger_counts": (), "stable": False, "pinch": 0.0,
            "fps": 0.0, "latency_ms": 0.0, "zoom": canvas.zoom,
            "items": 0, "can_undo": False, "can_redo": False,
            "hint": "", "camera_ok": True, "camera_error": "",
            "transient_error": "", "finger_info": "",
            "view_w": 0, "view_h": 0, "smoothing": 0.7, "revision": 0,
            "brush_opacity": 1.0,
        }

    def stop(self) -> None:
        """Signal the loop to exit (non-blocking)."""
        self._stop.set()

    def apply(self, fn: Callable):
        """Run ``fn`` under the engine lock; returns its result."""
        with self._lock:
            return fn()

    def stamp_active(self) -> bool:
        """Stamp the preview, else the stabilized two-hand overlay."""
        width, height = self._last_size
        if self.controller.stamp_preview(width, height):
            return True
        from gesture_engine import LINE, RECTANGLE, SPHERE
        if (len(self._last_hands) >= 2
                and self._last_two_hand in (LINE, SPHERE, RECTANGLE)):
            width, height = self._last_size
            return self.controller.stamp_two_hand(
                self._last_hands, self._last_two_hand, width, height)
        return False

    def recreate_camera(self, camera_id: int, width=None, height=None,
                        fps=None) -> None:
        """Swap the camera device (GUI thread; runs under the engine lock).

        Raises CameraError on failure; the old camera is kept.
        The device is opened *outside* the lock so a slow driver never
        stalls the engine loop; only the pointer swap is locked.
        """
        from camera import Camera
        camera = Camera(camera_id, width=width, height=height, fps=fps)
        with self._lock:
            old = self.camera
            self.camera = camera
        try:
            old.release()
        except Exception:
            pass

    def latest(self):
        """Return (annotated_frame_or_None, snapshot_dict_copy)."""
        with self._lock:
            frame = None if self._frame is None else self._frame.copy()
            return frame, dict(self._snap)

    def run(self) -> None:
        fps = FPS()
        hands: list = []
        stable = GestureResult()
        while not self._stop.is_set():
            with self._lock:
                camera = self.camera
                mirror = self.mirror
            try:
                frame = camera.get_frame() if camera is not None else None
            except Exception:
                frame = None
            if frame is None:
                with self._lock:
                    self._snap["camera_ok"] = False
                    self._snap["camera_error"] = "No frame (disconnected?)"
                    self._frame = None
                self._stop.wait(0.25)
                continue
            if mirror:
                frame = cv2.flip(frame, 1)
            height, width = frame.shape[:2]
            started = time.perf_counter()
            try:
                tracked = self.tracker.track(frame)
                transient = ""
            except ValueError as exc:
                transient = str(exc)
                tracked = None
            except RuntimeError as exc:
                transient = str(exc)
                tracked = None
            if tracked is not None:
                hands = tracked.hands
                raw = self.classifier.classify(tracked.hands, tracked.handedness)
                stable = self.smoother.update_result(raw)
                with self._lock:
                    self.controller.update(tracked.hands, stable, width, height)
                    render_overlays(frame, tracked.hands, stable, self.controller,
                                    self.canvas, show_landmarks=self.show_landmarks,
                                    include_canvas=self.include_canvas)
                    self._last_hands = list(tracked.hands)
                    self._last_size = (width, height)
                    self._last_two_hand = (stable.name
                                           if stable.is_stable and stable.hand_count >= 2
                                           else None)
            latency_ms = (time.perf_counter() - started) * 1000.0
            fps.update()
            with self._lock:
                snap = self._snap
                snap["gesture"] = stable.name
                snap["action"] = stable.action
                snap["state"] = stable.state.name
                snap["confidence"] = stable.confidence
                snap["hands"] = stable.hand_count
                snap["finger_counts"] = tuple(stable.finger_counts)
                snap["stable"] = stable.is_stable
                snap["pinch"] = stable.pinch_strength
                snap["fps"] = fps.get_fps()
                snap["latency_ms"] = latency_ms
                snap["zoom"] = self.canvas.zoom
                snap["items"] = self.canvas.stroke_count
                snap["can_undo"] = self.canvas.can_undo
                snap["can_redo"] = self.canvas.can_redo
                snap["hint"] = self.controller.hint.text
                snap["tool"] = self.controller.tool
                snap["shape_tool"] = self.controller.shape_tool
                snap["brush_size"] = self.controller.brush_size
                snap["brush_opacity"] = self.controller.brush_opacity
                snap["brush_color"] = tuple(self.controller.brush_color)
                snap["glow"] = self.controller.glow
                snap["camera_ok"] = True
                snap["camera_error"] = ""
                snap["transient_error"] = transient
                snap["finger_info"] = self._finger_info(hands)
                snap["view_w"], snap["view_h"] = width, height
                snap["smoothing"] = float(getattr(config, "SMOOTHING", 0.7))
                snap["revision"] = self.canvas.revision
                self._frame = frame

    @staticmethod
    def _finger_info(hands) -> str:
        if not hands:
            return ""
        try:
            from finger_detector import finger_states
            states = finger_states(hands[0])
            return " ".join(f"{name[0].upper()}:{'1' if on else '0'}"
                            for name, on in states.items())
        except (IndexError, AttributeError):
            return ""
