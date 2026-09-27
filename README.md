# AI Hand Gesture Drawing Studio

Control a digital drawing workspace naturally with your hands in front of a camera.
Built with Python, OpenCV, MediaPipe Tasks and NumPy — no heavy frameworks.

## Features

- **Real-time hand tracking** (up to 2 hands) via MediaPipe Tasks
- **Robust finger detection** using joint angles + relative distances (rotation/scale tolerant)
- **Gesture state machine** (`DETECTED → CANDIDATE → STABLE → ACTIVE → RELEASED`) with
  frame-based confirmation, release grace and action cooldowns — no UI flicker
- **Persistent vector canvas**: pencil/brush freehand, line, circle, rectangle, triangle,
  sphere objects, eraser, undo/redo, zoom, glow/neon strokes
- **Shape tools**: live preview + stamp via pinch or thumbs-up; optional auto shape
  recognition (rough stroke → perfect shape)
- **Two-hand interaction**: LINE / SPHERE / RECTANGLE overlays (stamped with `SPACE`),
  smooth pinch-zoom via wrist span
- **Modern dark UI**: title bar, tool strip, status line, debug panel, help screen,
  settings overlay, fingertip cursor with pinch animation
- **Persistence**: export canvas PNG/JPG, vector SVG export, save/load vector
  project JSON, screenshots, autosave with crash recovery
- **Settings** saved locally to `settings.json`
- **Unit tested** without a camera (143 tests)
- **Smooth animated drawing**: dead-zone + exponential + velocity-adaptive
  fingertip smoothing (configurable 0–100%), gap interpolation, Catmull-Rom
  brush strokes, pressure-like velocity widths, animated cursor with states
  (idle/hover/drawing/pinch/erasing) and confirm pulses
- **Split desktop panes**: live camera preview beside the persistent drawing
  canvas; zoom (Ctrl+wheel, gesture, menu) and middle-drag pan stay aligned
  with the fingertip via canvas-space mapping
- **Canvas backgrounds**: dark / white / black / grid / custom, optional
  snap-to-grid; per-stroke opacity; soft + hard erasers
- **Desktop GUI** (Tkinter + Pillow): toolbar with real tools, color/size/opacity
  controls, collapsible gesture sidebar with live highlight, status bar,
  settings dialog, help, file menu (new/open/save/export/screenshot),
  camera status with reconnect — all wired to the same MediaPipe engine
  running in a background thread

## Architecture

```text
Camera (camera.py)
  ↓
HandTracker (hand_tracker.py)
  ↓
GestureClassifier → GestureResult (gesture_engine.py + finger_detector.py)
  ↓
GestureSmoother (state machine + debounce)
  ↓
InteractionController (interaction_controller.py)
  ↓
Canvas — vector strokes/shapes + undo/redo (canvas.py)
  ↓
Renderer (renderer.py) + UI (ui.py)
  ↓
Final frame
```

The code lives flat under `src/` (one module per layer) so both
`python src/main.py` and `python -m src.main` keep working:

| Module | Responsibility |
|---|---|
| `camera.py` | Camera init / capture / release / errors |
| `hand_tracker.py` | MediaPipe detection, `HandFrame`, handedness |
| `finger_detector.py` | Finger poses: angles, distances, pinch, fist, palm |
| `gesture_engine.py` | Shape + semantic classification, state machine, smoother, `GestureResult` |
| `gesture.py` | Legacy shim (re-exports `hand_tracker` / `finger_detector`) |
| `geometry.py` | Pure math: distances, angles, centers, boxes, pixel mapping |
| `canvas.py` | Vector canvas, undo/redo, PNG + project JSON I/O |
| `tools.py` | Extensible tool registry (`register_tool`) |
| `shapes.py` | Optional auto shape recognition |
| `interaction_controller.py` | Gestures → canvas actions, zoom, select/drag |
| `renderer.py` | Shape drawing, sphere shading, cursor, previews |
| `ui.py` | Dark studio bars, toolbar, debug, help, settings |
| `desktop/` | Tkinter app: window, threaded engine, toolbar, sidebar, status, dialogs |
| `config.py` / `settings_store.py` | Defaults + local `settings.json` persistence |
| `utils.py` | Rolling FPS + outlined text |

Future gestures (`CLEAR`, `MOVE`, `ROTATE`, `ZOOM`, `CONFIRM`) plug into
`gesture_engine.py` (new action constant + classifier branch) and
`interaction_controller.py` (new handler) without touching `main.py`.
Custom ML classification can reuse `train.py`'s landmark feature helpers.

## Installation

Prerequisites: Python 3.10+, a webcam, and the MediaPipe model at
`models/gesture_recognizer.task` (already included in this repo).

Linux/macOS:

```bash
git clone <repository>
cd HandGestureRecognition

python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
pip install -r requirements.txt
```

Windows PowerShell:

```powershell
git clone <repository>
cd HandGestureRecognition

py -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Running the application

Desktop GUI (recommended):

```bash
python src/main.py --gui
# or:
python -m src.main --gui
```

Classic OpenCV window:

```bash
./start
# or:
python src/main.py
# or:
python -m src.main
```

Options: `--camera ID`, `--debug` / `--no-debug`, `--no-mirror`.

## Gesture controls

| Gesture | Hands | Action |
|---|---|---|
| Index finger (☝) | 1 | Draw with the pencil |
| Two fingers (✌) | 1 | Shape mode (`N` cycles circle/rect/line/triangle) |
| Open palm (✋) | 1 | Pause (lift the pen) |
| Fist (✊) | 1 | Erase under the fingertip |
| Thumbs-up (👍) | 1 | Confirm / stamp shape preview |
| Pinch (🤏) | 1 | Stamp preview; grab + drag in Select mode |
| 5 + 5 fingers | 2 | LINE overlay between wrists (`SPACE` stamps) |
| 2 + 2 fingers | 2 | SPHERE overlay (`SPACE` stamps) |
| 3+ + 3+ fingers | 2 | RECTANGLE overlay (`SPACE` stamps) |
| Hands apart / together | 2 | Zoom canvas in / out |

Single-hand shape overlays from the original demo are preserved
(LINE wrist→tip, CIRCLE between tips, RECT around hand).

## Keyboard controls

| Key | Action |
|---|---|
| `Q` | Quit (desktop) / `Q`·`ESC` quit (OpenCV mode) |
| `ESC` | Cancel current stroke/preview (desktop) |
| `CTRL+Z` / `CTRL+Y` (`CTRL+SHIFT+Z`) | Undo / redo |
| `C` | Clear canvas |
| `Delete` | Delete selected / most recent item |
| `P` / `B` | Pencil / brush |
| `L` / `O` / `R` / `T` | Line / circle / rectangle / triangle tool |
| `E` / `V` | Eraser / select |
| `N` | Cycle shape-gesture tool |
| `SPACE` | Stamp preview / two-hand overlay |
| `S` / `D` / `H` | Settings / debug / help |
| `G` | Toggle glow |
| `+` / `-` | Brush size (1–100 px) |
| `1`–`6` | Brush color |
| `X` | Export canvas PNG |
| `CTRL+E` / `CTRL+S` / `CTRL+O` | Export JPG / save / open project |
| `CTRL+N` | New canvas |
| `CTRL+wheel` / `CTRL+plus/minus` | Zoom (desktop) |
| Middle-drag | Pan canvas (desktop) |
| `F11` | Fullscreen (desktop) |
| `TAB` | Cycle tools |

## Configuration

Tune `src/config.py` (camera, vision, gesture timing, drawing defaults, UI).
A subset persists automatically to `settings.json`:

```python
CAMERA_ID = 0
MAX_HANDS = 2
MIN_DETECTION_CONFIDENCE = 0.5
MIN_HAND_PRESENCE_CONFIDENCE = 0.5
MIN_TRACKING_CONFIDENCE = 0.5
GESTURE_CONFIRM_FRAMES = 5
GESTURE_RELEASE_FRAMES = 3
GESTURE_COOLDOWN = 0.25
SMOOTHING = 0.7            # pointer smoothing 0.0-1.0
DEAD_ZONE_PX = 2.0         # fingertip jitter filter
BRUSH_OPACITY = 1.0
CANVAS_BG_MODE = "dark"    # dark|white|black|grid|custom
AUTOSAVE_SECONDS = 10
ANIMATIONS = "full"        # full|minimal|off
DEBUG = True
```

## Troubleshooting

- **Camera won't open**: try `--camera 1` (or 2); close video-call apps; check OS permissions.
- **No hands detected**: improve lighting, keep hands inside the frame, face the palm to the camera.
- **Flickering gestures**: raise `GESTURE_CONFIRM_FRAMES` in `src/config.py`.
- **Pinch too sensitive/insensitive**: tune `PINCH_THRESHOLD` (normalized units, default 0.05).
- **Shaky drawing**: raise `SMOOTHING` (0–100 in Gesture settings); laggy cursor:
  lower it. `DEAD_ZONE_PX` filters micro-jitter without permanent offset.
- **App froze during detection**: the watchdog (8 s budget) recovers
  automatically and rebuilds a wedged graph; Ctrl+C always exits cleanly.
  Oversized frames are downscaled before detection — landmarks unaffected.
- **Strokes misaligned when zoomed**: fixed via canvas-space mapping; if seen,
  report window size + zoom (status bar shows both).
- **Lost work after a crash**: restart offers recovery from `autosave.json`
  (cleared on clean exit); projects save via `CTRL+S`.
- **Low FPS**: lower camera resolution, disable glow (`G`), set animations to
  `minimal`, close other apps.
- **Model missing**: ensure `models/gesture_recognizer.task` exists (see `AUDIT.md`).

## Development & testing

```bash
# Run tests (no camera needed)
python -m unittest discover -s tests

# Syntax check
python -m py_compile src/*.py

# CLI check (no camera needed)
python src/main.py --help
```

GUI needs Tkinter (standard library) and Pillow (`requirements.txt`); the
camera loop stays off the GUI thread via a worker thread polled with
`root.after`.

Gesture training groundwork lives in `src/train.py`
(landmark feature extraction + dataset stub).

## Future roadmap

- Rotate gesture (two-hand angle tracking)
- Canvas pan via two-hand movement
- More shape tools (arrow, star, polygon)
- Custom gesture recording + classifier training
- Multi-canvas tabs / layers panel
