"""AI Hand Gesture Drawing Studio - application controller.

Pipeline per frame::

    Camera -> HandTracker -> GestureClassifier -> GestureSmoother
        -> InteractionController -> Canvas -> Renderer -> UI
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2

# Make imports work both as `python src/main.py` and `python -m src.main`.
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import config
    import settings_store
    from camera import Camera, CameraError
    from canvas import Canvas
    from finger_detector import finger_states
    from gesture_engine import (
        LINE,
        RECTANGLE,
        SPHERE,
        GestureClassifier,
        GestureResult,
        GestureSmoother,
    )
    from hand_tracker import HandTracker
    from interaction_controller import InteractionController
    from tools import tool_from_shortcut
    from ui import PALETTE, draw_hud
    from utils import FPS
except ImportError:  # pragma: no cover - package-style fallback
    from src import config
    from src import settings_store
    from src.camera import Camera, CameraError
    from src.canvas import Canvas
    from src.finger_detector import finger_states
    from src.gesture_engine import (
        LINE,
        RECTANGLE,
        SPHERE,
        GestureClassifier,
        GestureResult,
        GestureSmoother,
    )
    from src.hand_tracker import HandTracker
    from src.interaction_controller import InteractionController
    from src.tools import tool_from_shortcut
    from src.ui import PALETTE, draw_hud
    from src.utils import FPS

EXPORT_DIR = Path(__file__).resolve().parents[1] / "exports"


def parse_args(argv=None):
    """Parse command-line options."""
    parser = argparse.ArgumentParser(description="AI Hand Gesture Drawing Studio")
    parser.add_argument("--camera", type=int, default=None, help="Camera device id")
    parser.add_argument("--debug", action="store_true", default=None,
                        help="Enable debug overlay")
    parser.add_argument("--no-debug", action="store_true", help="Disable debug overlay")
    parser.add_argument("--no-mirror", action="store_true", help="Disable selfie mirror")
    parser.add_argument("--gui", action="store_true",
                        help="Launch the Tkinter desktop studio (recommended)")
    return parser.parse_args(argv)


class StudioApp:
    """Owns camera, vision, canvas and the main loop."""

    def __init__(self, args):
        settings_store.apply(settings_store.load())
        if args.debug:
            config.DEBUG = True
        if args.no_debug:
            config.DEBUG = False
        if args.no_mirror:
            config.MIRROR_FEED = False
        camera_id = args.camera if args.camera is not None else config.CAMERA_ID

        self.canvas = Canvas()
        self.controller = InteractionController(self.canvas)
        self.controller.brush_size = config.BRUSH_SIZE
        self.controller.brush_color = tuple(config.BRUSH_COLOR)
        self.controller.glow = config.GLOW_ENABLED
        self.classifier = GestureClassifier()
        self.smoother = GestureSmoother()
        self.fps = FPS()
        self.camera_ok = True
        self.camera_error = ""
        self.transient_error = ""
        self.latency_ms = 0.0
        self.show_help = not Path(config.SETTINGS_PATH).is_file()
        self.show_settings = False
        self.stable = GestureResult()
        self.hands: list = []
        try:
            self.camera = Camera(camera_id)
        except CameraError as exc:
            self.camera = None
            self.camera_ok = False
            self.camera_error = str(exc)
        try:
            self.tracker = HandTracker()
        except FileNotFoundError as exc:
            if self.camera is not None:
                self.camera.release()
            raise SystemExit(f"Error: {exc}")

    # --- frame processing ---
    def process_frame(self, frame):
        """Run vision + interaction for one frame; returns annotated frame."""
        height, width = frame.shape[:2]
        started = time.perf_counter()
        try:
            tracked = self.tracker.track(frame)
            self.transient_error = ""
        except ValueError as exc:
            self.transient_error = str(exc)
            return frame
        except RuntimeError as exc:  # transient MediaPipe failure: keep going
            self.transient_error = str(exc)
            return frame
        self.hands = tracked.hands
        raw = self.classifier.classify(tracked.hands, tracked.handedness)
        self.stable = self.smoother.update_result(raw)
        self.controller.update(tracked.hands, self.stable, width, height)
        self.latency_ms = (time.perf_counter() - started) * 1000.0
        return self.render_overlays(frame, tracked)

    def render_overlays(self, frame, tracked):
        """Composite canvas + live gesture overlays onto the frame."""
        from studio_render import render_overlays as _render
        return _render(frame, tracked.hands, self.stable, self.controller,
                       self.canvas, show_landmarks=config.SHOW_LANDMARKS)

    def finger_info(self) -> str:
        """Compact finger-state string for the debug panel."""
        if not self.hands:
            return ""
        try:
            states = finger_states(self.hands[0])
            return " ".join(f"{name[0].upper()}:{'1' if on else '0'}"
                            for name, on in states.items())
        except (IndexError, AttributeError):
            return ""

    # --- actions ---
    def export_png(self) -> Path:
        """Export the canvas PNG to exports/."""
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        path = EXPORT_DIR / datetime.now().strftime("canvas_%Y%m%d_%H%M%S.png")
        height, width = 720, 1280
        return self.canvas.save_png(path, width, height)

    def screenshot(self, frame) -> Path:
        """Save the current annotated frame to exports/."""
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        path = EXPORT_DIR / datetime.now().strftime("shot_%Y%m%d_%H%M%S.png")
        cv2.imwrite(str(path), frame)
        return path

    def save_project(self) -> Path:
        """Save the vector project JSON to exports/."""
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        path = EXPORT_DIR / datetime.now().strftime("project_%Y%m%d_%H%M%S.json")
        return self.canvas.save_project(path)

    # --- keyboard ---
    def handle_key(self, key: int, frame=None) -> bool:
        """Handle one keypress. Returns False to quit. CTRL combos use raw codes."""
        if key == 255 or key < 0:
            return True
        if key in (ord('q'), 27):  # Q / ESC
            return False
        if key == 26:  # CTRL+Z
            self.canvas.undo()
        elif key == 25:  # CTRL+Y
            self.canvas.redo()
        elif key == 19:  # CTRL+S
            self.save_project()
        elif key == 9:  # TAB: cycle tools
            from tools import TOOL_CYCLE
            idx = TOOL_CYCLE.index(self.controller.tool) if self.controller.tool in TOOL_CYCLE else -1
            self.controller.set_tool(TOOL_CYCLE[(idx + 1) % len(TOOL_CYCLE)])
        elif key == ord(' '):  # SPACE/ENTER: stamp
            if self.hands and len(self.hands) >= 2 and self.stable.name in (LINE, SPHERE, RECTANGLE):
                h, w = frame.shape[:2] if frame is not None else (480, 640)
                self.controller.stamp_two_hand(self.hands, self.stable.name, w, h)
            else:
                h, w = frame.shape[:2] if frame is not None else (480, 640)
                self.controller.stamp_preview(w, h)
        elif key in (ord('c'), ord('C')):
            self.canvas.clear()
        elif key in (ord('d'), ord('D')):
            config.DEBUG = not config.DEBUG
        elif key in (ord('h'), ord('H')):
            self.show_help = not self.show_help
        elif key in (ord('s'), ord('S')):
            self.show_settings = not self.show_settings
        elif key in (ord('g'), ord('G')):
            self.controller.glow = not self.controller.glow
        elif key in (ord('n'), ord('N')):
            self.controller.cycle_shape_tool()
        elif key in (ord('x'), ord('X')):
            self.export_png()
        elif key in (ord('+'), ord('=')):
            self.controller.brush_size = min(100, self.controller.brush_size + 1)
        elif key in (ord('-'), ord('_')):
            self.controller.brush_size = max(1, self.controller.brush_size - 1)
        elif key in (127, 8):  # Delete / Backspace: drop most recent item
            if self.canvas.items:
                self.canvas.delete_item(len(self.canvas.items) - 1)
        elif ord('1') <= key <= ord('6'):
            self.controller.brush_color = PALETTE[key - ord('1')]
        else:
            tool = tool_from_shortcut(chr(key)) if key < 256 else None
            if tool is not None:
                self.controller.set_tool(tool)
        return True

    # --- main loop ---
    def _display(self, frame) -> bool:
        """Show one frame; return False to quit. Overridable for tests."""
        cv2.imshow(config.WINDOW_NAME, frame)
        return self.handle_key(cv2.waitKey(1) & 0xFF, frame)

    def run(self) -> int:
        """Run the studio until quit. Returns an exit code."""
        if self.camera is None:
            print(f"Error: {self.camera_error}", file=sys.stderr)
            print("Tip: connect a webcam or pass --camera <id>.", file=sys.stderr)
            return 1
        print("AI Gesture Drawing Studio - press H for help, Q to quit")
        exit_code = 0
        try:
            while True:
                frame = self.camera.get_frame()
                if frame is None:
                    print("Warning: failed to read frame from camera.")
                    break
                if config.MIRROR_FEED:
                    frame = cv2.flip(frame, 1)
                frame = self.process_frame(frame)
                self.fps.update()
                studio = {
                    "tool": self.controller.tool,
                    "canvas": self.canvas,
                    "brush_size": self.controller.brush_size,
                    "hint": self.controller.hint,
                    "camera_ok": self.camera_ok,
                    "show_help": self.show_help,
                    "show_settings": self.show_settings,
                    "settings_view": settings_store.defaults(),
                    "finger_info": self.finger_info(),
                }
                if self.transient_error:
                    studio["hint"] = self.transient_error
                draw_hud(frame, self.stable, self.fps.get_fps(),
                         debug=config.DEBUG, studio=studio, latency_ms=self.latency_ms)
                if not self._display(frame):
                    break
        except KeyboardInterrupt:
            # Ctrl+C anywhere (even inside a blocking detect call) lands
            # here: release hardware and exit quietly with code 130.
            print("\nInterrupted - closing.")
            exit_code = 130
        finally:
            try:
                self.tracker.close()
            except Exception:
                pass
            self.camera.release()
        # Persist a few preferences for next launch.
        try:
            settings_store.save({
                "BRUSH_SIZE": self.controller.brush_size,
                "BRUSH_COLOR": list(self.controller.brush_color),
                "DEBUG": config.DEBUG,
            })
        except OSError:
            pass
        return exit_code


def main(argv=None) -> int:
    """Entry point (OpenCV window default; --gui for the desktop studio)."""
    args = parse_args(argv)
    if args.gui:
        if args.debug:
            config.DEBUG = True
        if args.no_debug:
            config.DEBUG = False
        if args.no_mirror:
            config.MIRROR_FEED = False
        try:
            from desktop.app import main as gui_main
        except ImportError as exc:
            print(f"Error: GUI mode needs Tkinter + Pillow ({exc})", file=sys.stderr)
            return 2
        return gui_main(camera_id=args.camera if args.camera is not None
                        else config.CAMERA_ID)
    return StudioApp(args).run()


if __name__ == "__main__":
    raise SystemExit(main())
