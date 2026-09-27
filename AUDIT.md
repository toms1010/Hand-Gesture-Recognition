# Project Audit

## 1. Project Information

- Project: AI Gesture Drawing Studio (redesign of HandGestureRecognition)
- Version: 4.1.0 (detection watchdog + drawing accuracy + maximized GUI)
- Date: 2026-09-26
- Python version: 3.14.4
- OpenCV version: 5.0.0
- MediaPipe version: 1.0.0
- NumPy version: 2.5.1
- Tkinter version: 8.6 / Pillow: 12.3.0

---

## 2. Original Project Summary

The original prototype (`src/main.py` ~170 lines plus helpers) opened the webcam,
mirrored the frame, ran MediaPipe Tasks `HandLandmarker` (IMAGE mode,
`models/gesture_recognizer.task`, max 2 hands), counted fingers with
`landmarks[tip].y < landmarks[pip].y` (thumb ignored, so the count could never
reach 5 and the "both open → LINE" gesture could never fire), and drew ephemeral
shape overlays directly on the camera feed:

- Original architecture: flat `src/` (`main.py`, `camera.py`, `gesture.py`,
  `geometry.py`, `utils.py`, `train.py` stub) with all gesture/drawing/UI logic
  inline in `main.py`.
- Existing files: `src/main.py`, `src/camera.py`, `src/gesture.py`,
  `src/geometry.py`, `src/utils.py`, `src/train.py`, `models/gesture_recognizer.task`,
  `start` shell line, `requirements.txt`.
- Existing gestures: two-hand 5+5 LINE / 2+2 SPHERE / 3+3 RECTANGLE; single-hand
  1-finger LINE, 2-finger CIRCLE, else RECT.
- Existing dependencies: `mediapipe`, `opencv-python`, `numpy`.
- Existing limitations: no thumb detection; `y`-comparison broke on rotated hands;
  dead `else` branch made "No hands detected" unreachable; FPS was a cumulative
  average; sphere colors were blue-tinted instead of yellow-orange; detector and
  camera never cleaned up on errors; no smoothing (single noisy frame flickered
  the UI); no canvas, undo, settings, tests or docs.

---

## 3. Major Changes

| Area | Before | After |
|------|--------|-------|
| Architecture | Gesture/drawing/UI logic inline in `main.py` | Layered pipeline: Camera → HandTracker → GestureClassifier → GestureSmoother → InteractionController → Canvas → Renderer → UI |
| Finger detection | `tip.y < pip.y`, thumb ignored (max count 4) | Wrist-relative distances + PIP joint angles + palm-relative thumb check; left/right tolerant; count reaches 5 |
| Gesture stability | None (raw per-frame output) | State machine (IDLE/DETECTED/CANDIDATE/STABLE/ACTIVE/RELEASED) + confirm frames + release grace + cooldowns |
| Gesture output | Bare finger-count ints | `GestureResult` dataclass: name, confidence, hand_count, finger_counts, is_stable, action, state, pinch |
| Drawing | Ephemeral overlays on the camera frame | Persistent vector canvas (strokes/shapes survive hand movement) + original overlays kept as live previews |
| Shape rendering | Flat circles/rects, blue-tinted "sphere" | Radial-shaded sphere with highlight/rim/glow, neon strokes, cursor ring, shape previews, selection outline |
| Tools | Hardcoded if/elif chain | Extensible `tools.py` registry (`register_tool`) + keyboard shortcuts |
| UI | Bare `putText` labels | Dark studio UI: title bar, tool strip, status line, debug panel, help + settings overlays |
| History | None | Vector undo/redo/clear, coalesced drag moves |
| Export | None | Canvas PNG export, vector project JSON save/load, frame screenshots |
| Settings | Hardcoded constants | `config.py` defaults + `settings.json` local persistence |
| Shape intelligence | None | Optional auto shape recognition (rough → perfect line/circle/rect/triangle) |
| Tests | None | 130 unit tests, camera-free (synthetic landmarks) |
| Desktop UI | OpenCV-only window | Tkinter studio sharing the same engine |
| Drawing input | Raw fingertip points | Smoothed + interpolated canvas-space points |
| Canvas view | Zoom-about-center render (misaligned input) | Zoom/pan with inverse-mapped input |
| Docs | None | README, AUDIT.md, CHANGELOG.md, `.gitignore` |

---

## 4. New Features

### Persistent vector canvas

**Status:** Implemented

**Description:** Strokes and stamped shapes persist after the hand moves away.
History stores commands (add/clear/erase-moves), never full-frame copies.

**Implementation:** `src/canvas.py` (`Canvas`, `Stroke`, `ShapeItem`).

**User Interaction:** Draw with the index finger; `CTRL+Z` / `CTRL+Y` undo/redo;
`C` clears.

### Semantic gesture actions

**Status:** Implemented

**Description:** Single-hand poses map to intents: DRAW (index), SHAPE (two
fingers), PAUSE (palm), ERASE (fist), CONFIRM (thumbs-up), PINCH (pinch).

**Implementation:** `src/finger_detector.py` poses + `GestureClassifier` in
`src/gesture_engine.py`.

**User Interaction:** Show the pose; the status bar names the action.

### Gesture state machine + smoothing

**Status:** Implemented

**Description:** `GESTURE_CONFIRM_FRAMES=5` frames to confirm, 3-frame release
grace, 0.25 s one-shot cooldown. Sequence SPHERE, SPHERE, NONE, SPHERE, SPHERE
never flickers.

**Implementation:** `GestureSmoother` / `GestureState` in `src/gesture_engine.py`.

**User Interaction:** Automatic; `Stable: True/False` shown in debug mode.

### Two-hand zoom

**Status:** Implemented

**Description:** Smoothed wrist-span drives canvas zoom 0.5x–3x (hands apart =
zoom in).

**Implementation:** `InteractionController._update_two_hands` (`ZOOM_SMOOTHING`,
`ZOOM_DEADZONE` in `src/config.py`).

**User Interaction:** Show two hands and spread/close them.

### Two-hand overlays + stamping

**Status:** Implemented

**Description:** Original 5+5 LINE / 2+2 SPHERE / 3+3 RECTANGLE overlays kept,
stampable to the canvas.

**Implementation:** `src/renderer.py` overlays + `InteractionController.stamp_two_hand`.

**User Interaction:** Hold the pose, press `SPACE`.

### Select / move

**Status:** Implemented

**Description:** Select tool + pinch grabs the nearest stroke; drag moves it
(one undo step per grab).

**Implementation:** `InteractionController` + `Canvas.move_item`.

**User Interaction:** `V`, pinch near a stroke, drag, release.

### Auto shape recognition (optional)

**Status:** Implemented (off by default)

**Description:** Released freehand strokes snap to perfect line/circle/rectangle/
triangle when recognized with ≥ 0.6 confidence.

**Implementation:** `src/shapes.py` + `Canvas.snap_last_stroke`.

**User Interaction:** Enable `SHAPE_RECOGNITION` in `src/config.py`.

### Studio UI + help + settings + debug

**Status:** Implemented

**Description:** Dark title bar with camera dot, tool strip, status line, debug
panel (gesture/state/confidence/pinch/canvas/FPS/latency), first-run help
overlay, settings overlay, fingertip cursor with pinch pulse.

**Implementation:** `src/ui.py`, `src/renderer.py` cursor/preview/selection.

**User Interaction:** `H` help, `S` settings, `D` debug.

### Save / export

**Status:** Implemented

**Description:** `X` exports canvas PNG, `CTRL+S` saves vector project JSON
(`exports/`), screenshots via `StudioApp.screenshot`.

**Implementation:** `Canvas.save_png/save_project/load_project`, `src/main.py`.

**User Interaction:** Keyboard as above; projects reload via `Canvas.load_project`.

### Custom-gesture readiness (stub)

**Status:** Partial (architecture only)

**Description:** `src/train.py` landmark feature helpers + dataset stub remain;
new actions plug into `gesture_engine.py` + `interaction_controller.py`
without touching `main.py`.

---

## 5. Removed Features

Nothing user-facing was removed. Specifically preserved:

- All six original shape overlays and their trigger counts.
- `models/gesture_recognizer.task` and the MediaPipe Tasks API.
- `gesture.GestureDetector` (now a `HandTracker` subclass), `geometry.draw_*`
  helpers (deprecated wrappers delegating to `renderer`), `utils.FPS/draw_text`.
- `train.py` (untouched), `start` launcher (untouched, still works).

---

## 6. Modified Files

| File | Action | Description |
|------|--------|-------------|
| `src/main.py` | Rewritten | Slim `StudioApp` controller + `--gui` desktop entry |
| `src/studio_render.py` | Added | Overlays shared by OpenCV + Tkinter UIs |
| `src/config.py` | Extended | All tunable constants (camera/vision/gesture/drawing/UI) |
| `src/camera.py` | Modified | Config defaults, `CameraError(RuntimeError)`, docstrings |
| `src/hand_tracker.py` | Added | Canonical vision layer: `HandTracker`, `HandFrame`, model resolution |
| `src/gesture.py` | Rewritten | Thin compat shim over `hand_tracker` + `finger_detector` |
| `src/finger_detector.py` | Added | Angle/distance finger poses, pinch, fist, palm, thumbs-up |
| `src/gesture_engine.py` | Rewritten | Shape + semantic classification, `GestureResult`, state machine, smoother |
| `src/geometry.py` | Rewritten | Pure math (no cv2); deprecated `draw_*` wrappers kept |
| `src/renderer.py` | Extended | Sphere shading/glow, cursor, pinch line, previews, selection |
| `src/canvas.py` | Added | Vector canvas, undo/redo, PNG + project JSON |
| `src/desktop/app.py` | Added | Tkinter window, menus, bindings, shutdown |
| `src/smoothing.py` | Added | PointSmoother, interpolation, Catmull-Rom |
| `src/animation.py` | Added | Pulse-envelope manager |
| `src/applog.py` | Added | Rotating file logging |
| `src/desktop/worker.py` | Added | Engine thread (camera+MediaPipe off GUI thread) |
| `src/desktop/view.py` | Added | Pure view-mode composition (tested Tk-free) |
| `src/desktop/toolbar.py` | Added | Tools/history/color/size/mode controls |
| `src/desktop/sidebar.py` | Added | Status card, gesture guide, tool info, debug |
| `src/desktop/statusbar.py` | Added | 7-field live status bar |
| `src/desktop/dialogs.py` | Added | Settings (live-apply), help, about |
| `src/tools.py` | Added | Extensible tool registry + shortcuts |
| `src/shapes.py` | Added | Optional auto shape recognition |
| `src/interaction_controller.py` | Added | Gestures → canvas actions, zoom, select/drag, stamping |
| `src/ui.py` | Rewritten | Dark studio UI: bars, toolbar, debug, help, settings |
| `src/settings_store.py` | Added | `settings.json` load/save/apply |
| `src/utils.py` | Kept | Rolling FPS + outlined text (unchanged behavior) |
| `src/train.py` | Kept | Training stub (unchanged) |
| `tests/helpers.py` | Added | Synthetic 21-landmark builders |
| `tests/test_geometry.py` | Added | 13 tests: distances, angles, boxes, pixels |
| `tests/test_gesture.py` | Added | 24 tests: fingers, classification, actions, smoother |
| `tests/test_canvas.py` | Added | 13 tests: history, erase/move, render, persistence |
| `tests/test_shapes.py` | Added | 10 tests: recognition + perfect shapes |
| `tests/test_interaction.py` | Added | 12 tests: draw/erase/stamp/zoom flows |
| `tests/test_ui.py` | Added | 9 tests: HUD robustness, layout, hints flag |
| `tests/test_watchdog.py` | Added | 10 tests: timeout, rebuild, frame cap, Ctrl+C |
| `tests/test_desktop.py` | Added | 23 tests: view modes, worker, live widgets, GUI fixes |
| `tests/test_smoothing.py` | Added | 11 tests: smoother, interpolation, curves |
| `tests/test_animation.py` | Added | 4 tests: envelopes, expiry, clear |
| `requirements.txt` | Updated | Pinned, commented, same 3 dependencies |
| `README.md` | Added | Full studio documentation |
| `AUDIT.md` | Added | This file |
| `CHANGELOG.md` | Added | Release changelog |
| `.gitignore` | Added | venv, caches, exports, settings.json |
| `start` | Kept | Launcher still valid (`./start`) |

---

## 7. Architecture Changes

Old:

```text
Camera
 ↓
MediaPipe
 ↓
Finger Count (main.py inline)
 ↓
Ephemeral drawing on camera frame
```

New:

```text
Camera (camera.py)
 ↓
Hand Tracking — HandTracker/HandFrame (hand_tracker.py)
 ↓
Gesture Engine — classifier + GestureResult (gesture_engine.py, finger_detector.py)
 ↓
Gesture State — smoother/state machine (gesture_engine.py)
 ↓
Interaction Controller (interaction_controller.py + smoothing.py,
  animation.py: dead-zone/expo/adaptive smoothing, interpolation,
  canvas-space mapping)
 ↓
Canvas — vector strokes + history (canvas.py, tools.py, shapes.py)
 ↓
Renderer (renderer.py)  [+ studio_render.py shared overlays]
 ↓
UI: OpenCV HUD (ui.py)  OR  Tkinter desktop (desktop/*, worker thread)
```

Why: each stage has one responsibility and one seam for testing. Vision needs a
camera but everything below `HandFrame` runs on synthetic landmarks (hence
143 camera-free tests, incl. watchdog, accuracy, maximized GUI). New tools/gestures
register in `tools.py` /
`gesture_engine.py` without editing `main.py`. Flat `src/` (instead of nested
packages) was chosen deliberately to preserve both entry points
(`python src/main.py`, `python -m src.main`) and the `start` script.

---

## 8. Gesture Audit

| Gesture | Action | Hands | Status |
|---|---|---|---|
| Index point | Draw freehand | 1 | Implemented + tested |
| Two fingers | Shape preview | 1 | Implemented + tested |
| Open palm | Pause | 1 | Implemented + tested |
| Fist | Erase | 1 | Implemented + tested |
| Thumbs-up | Confirm / stamp | 1 | Implemented + tested |
| Pinch | Stamp / select-drag | 1 | Implemented + tested |
| 5 + 5 fingers | LINE overlay (+ stamp) | 2 | Implemented + tested |
| 2 + 2 fingers | SPHERE overlay (+ stamp) | 2 | Implemented + tested |
| 3+ + 3+ fingers | RECTANGLE overlay (+ stamp) | 2 | Implemented + tested |
| Hands apart/together | Zoom canvas | 2 | Implemented + tested |
| Single 1-finger LINE overlay | Live overlay | 1 | Preserved |
| Single 2-finger CIRCLE overlay | Live overlay | 1 | Preserved |
| Single 3+ RECT overlay | Live overlay | 1 | Preserved |
| Rotation / two-hand move | Rotate/move object | 2 | Not implemented (unreliable without stable angle tracking; see README roadmap) |

---

## 9. Keyboard Controls

| Key | Action | Verified |
|---|---|---|
| `Q` | Quit (desktop; `Q`/`ESC` in OpenCV mode) | Code reviewed |
| `ESC` | Cancel stroke/preview (desktop) | `cancel_active` tested |
| `CTRL+Z` / `CTRL+Y` / `CTRL+SHIFT+Z` | Undo / redo | Logic unit-tested |
| `C` | Clear canvas (`O` stays Circle — kept over master §39) | Logic tested |
| `Delete` | Delete selected / most recent | `delete_item` tested |
| `F11` | Fullscreen | Code reviewed |
| `CTRL+E` / `CTRL+SHIFT+S` / `CTRL+O` / `CTRL+N` | Export JPG / save / open / new | I/O tested |
| `CTRL+wheel` / middle-drag | Zoom / pan | Mapping tested |
| `P` / `B` | Pencil / brush | Registry tested |
| `L` / `O` / `R` / `T` | Line / circle / rect / triangle | Registry tested |
| `E` / `V` | Eraser / select | Flow tested |
| `N` | Cycle shape tool | Unit-tested |
| `SPACE` | Stamp preview / overlay | `stamp_*` unit-tested |
| `S` / `D` / `H` | Settings / debug / help | Code reviewed |
| `G` | Glow toggle | Code reviewed |
| `+` / `-` | Brush size | Code reviewed |
| `1`–`6` | Brush color | Palette defined |
| `X` | Export canvas PNG | `save_png` tested |
| `CTRL+S` | Save project | `save_project` tested |
| `TAB` | Cycle tools | Registry tested |

Key handling itself requires a live feed and was not pressed end-to-end
(no webcam in this environment); all underlying operations are tested.
The Tkinter equivalents (menus, toolbar, bindings) were exercised live
against a fake camera (see `tests/test_desktop.py`).

---

## 10. How to Run

Prerequisites:

```text
Python 3.10+
Webcam
models/gesture_recognizer.task (included, 7.5 MB)
opencv-python, mediapipe, numpy (see requirements.txt)
```

Installation, Linux/macOS:

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

Model location (mandatory, already present):

```text
models/gesture_recognizer.task
```

`HandTracker` resolves it via `src/config.py:MODEL_PATH` with a
current-directory fallback; missing file raises `FileNotFoundError` with the
tried paths instead of crashing inside MediaPipe.

## Start the Application

Desktop GUI (recommended):

```bash
python src/main.py --gui
```

Classic OpenCV window:

```bash
./start
```

(Every variant below was syntax/import verified; live run needs a webcam.)

```bash
python src/main.py
python -m src.main
python src/main.py --camera 1 --debug
```

---

## 11. Development Commands

```bash
# Run application (needs webcam)
./start

# Run tests (no camera needed) — 143 tests, all passing
python -m unittest discover -s tests

# Syntax check
python -m py_compile src/*.py tests/*.py

# CLI check (no camera needed)
python src/main.py --help
```

Lint (optional, not configured): no ruff/flake8 config ships with the repo;
`py_compile` + unit tests are the supported checks.

---

## 12. Test Audit

| Test | Result | Notes |
|---|---|---|
| Import check (all 17 modules) | PASS | `import` of every `src` module incl. `main` |
| Unit tests (143) | PASS | `python -m unittest discover -s tests` → OK |
| GUI layout (9) | PASS | HUD/sizes/trim/hints-flag covered in `test_ui.py` |
| Desktop widgets (19) | PASS | Live Tk smoke tests in `test_desktop.py` |
| Smoothing/animation (15) | PASS | `test_smoothing.py` + `test_animation.py` |
| Canvas mapping/exports (13 new) | PASS | Zoom/pan roundtrip, delete, SVG/JPG, bg, opacity |
| GUI startup/close | PASS | Real 3 s mainloop, clean shutdown, worker joined |
| Geometry (13) | PASS | distances, angles, boxes, pixel clamp |
| Finger/classification/smoothing (24) | PASS | incl. spec flicker sequence |
| Canvas incl. undo/redo (13) | PASS | add/clear/erase/move + PNG + JSON roundtrip |
| Shape recognition (10) | PASS | line/circle/rect/triangle/unknown |
| Interaction flows (12) | PASS | draw/pause/erase/stamp/zoom |
| MediaPipe blank-frame track | PASS | zeros image → 0 hands, no exception |
| Detection watchdog | PASS | Timeout/rebuild/frame-cap tested; wedged native call contained |
| Clean Ctrl+C | PASS | Exit 130, camera released, no traceback |
| CLI `--help` | PASS | exit 0, lists all flags |
| Camera initialization | SKIPPED | No webcam in this environment |
| GUI startup on display | PASS | 1920×1080 display; disconnected path live |
| Live one-hand gestures | SKIPPED | Needs webcam (display available) |
| Live two-hand gestures | SKIPPED | Needs webcam (display available) |
| Live keypress handling | SKIPPED | Needs webcam feed + window focus |
| FPS/latency benchmark | NOT MEASURED | Stated, not invented (see §14) |

---

## 13. Environment Audit

```text
OS: Linux (7.0.0-34-generic x86_64)
Python: 3.14.4
CPU: not recorded (headless container)
GPU: none
OpenCV: 5.0.0
MediaPipe: 1.0.0
NumPy: 2.5.1
Tkinter: 8.6 / Pillow: 12.3.0 / Display: 1920×1080
Camera: none available (disconnected path tested live)
```

---

## 14. Known Limitations

- Gesture recognition degrades under poor lighting; heavy occlusion reduces accuracy.
- `PINCH_THRESHOLD` (0.05 normalized units) may need per-user tuning.
- Zoom uses a fixed neutral span reference (0.35); extreme camera distances shift feel.
- Rotation and two-hand pan are not implemented (roadmap).
- Shape recognition is conservative and off by default; rough freehand may stay freehand.
- SVG export approximates triangles/spheres as circles (documented simplification).
- Fill / color-picker-from-canvas / resize-shape tools not implemented
  (Select moves whole items; documented as future work).
- Key handling needs a focused window; terminal emulators may swallow CTRL combos.
- Webcam feed was not exercised live (no webcam); all camera paths use the
  tested disconnected/fake-camera flows, but real-device tracking is NOT VERIFIED.

---

## 15. Performance Audit

```text
Average FPS: not measured (no live feed in this environment)
Minimum FPS: not measured
Camera resolution: driver default (configurable via CAMERA_WIDTH/HEIGHT)
Processing latency: debug panel reports per-frame vision latency live
Number of tracked hands: max 2 (configurable MAX_HANDS)
Performance benchmark: Not measured.
```

Design notes (not benchmarks): canvas re-renders only when dirty; history is
vector-based (no frame copies); overlays blend in place; per-frame allocations
are limited to small lists/tuples outside MediaPipe/OpenCV calls.

---

## 16. Security / Safety Audit

Checked: file I/O, serialization, command execution, secrets, network use.

- No network access, no credentials/secrets in the repo.
- No `eval`/`exec`/shell invocation; `start` only execs the local venv python.
- Settings/project JSON parsed with `json` (no pickle); corrupt files fall back
  to defaults (`settings_store.load`) — project loads of malformed files raise
  standard `json`/`KeyError` errors, no silent corruption.
- Writes are confined to `exports/` and `settings.json`; export filenames are
  timestamp-generated (no user-controlled path traversal).
- Camera frames are validated (None/empty/channel checks) before MediaPipe.
- No issue found; this is a local-only desktop app with a minimal attack surface.

---

## 17. Dependency Audit

```text
mediapipe → hand tracking (HandLandmarker Tasks API, models/gesture_recognizer.task)
opencv-python → camera capture, all rendering, UI overlays, PNG export
numpy → geometry/image math, shape resampling, canvas compositing
Pillow → Tkinter desktop display only (ImageTk PhotoImage conversion)
```

No other runtime dependencies. Tests use only the standard library
(`unittest`, `tempfile`). Previous `requirements.txt` listed the same three
packages unpinned; they are now pinned with minimum versions and comments.

---

## 18. Before vs After

### Before

- Finger count maxed at 4; LINE gesture unreachable; rotation broke detection
- All logic inline in `main.py`; bare `putText` UI; cumulative-average FPS
- Ephemeral overlays only; nothing persisted; no undo; no settings
- Crashed or misbehaved on camera loss, bad frames, missing model
- Zero tests, zero docs

### After

- 5-finger + rotation-robust detection; semantic actions + pinch + thumbs-up
- Layered, tested pipeline with state-machine smoothing and structured results
- Persistent vector canvas with tools, undo/redo, zoom, glow, export, settings
- Graceful errors (typed exceptions, transient-failure tolerance, fallbacks)
- 143 passing camera-free tests; README + AUDIT + CHANGELOG

### Main Improvements

1. Reliable gesture recognition (angles + distances + thumb + handedness tolerance).
2. No-flicker UX via confirm/release/cooldown state machine.
3. Real creative tool: persistent canvas, tools, undo/redo, export, settings.
4. Original demo behavior fully preserved (overlays, counts, model, launcher).
5. Verifiable quality: 143 tests, documented gaps, honest limitations.
