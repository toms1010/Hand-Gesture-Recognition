# Changelog

## [4.1.0] - 2026-09-27 — Detection watchdog + drawing accuracy + maximized GUI

Fixes a real field crash (MediaPipe `detect()` wedging inside its native
executor, previously only escapable via an ugly Ctrl+C traceback), tightens
drawing accuracy, and opens the desktop studio maximized.

### Added

- `detect_with_timeout` watchdog: native detect runs in a daemon thread with
  a budget (`DETECT_TIMEOUT`, 8 s); wedged calls raise `DetectionTimeout`
  (a `RuntimeError`, so existing transient handling applies) and repeated
  wedges rebuild the graph automatically.
- `HandTracker.close(timeout)` never blocks shutdown; oversized frames are
  downscaled for detection (`DETECT_MAX_WIDTH`, landmarks stay normalized);
  slow detects are logged (`DETECT_SLOW_WARN`).
- 10 watchdog/interrupt tests (`tests/test_watchdog.py`): timeout, error
  forwarding, auto-rebuild, frame cap, clean Ctrl+C exit (code 130).

### Changed

- Drawing accuracy: leaky dead zone (no static offset on slow drifts),
  faster high-speed adaptation, Catmull-Rom overshoot clamping.
- Desktop window opens maximized (geometry fallback); new fills-screen test.
- Ctrl+C in OpenCV mode now prints "Interrupted - closing." and exits 130
  with camera released instead of a traceback.

### Fixed

- App freeze when MediaPipe stalled (the reported traceback).
- Total: 143 tests passing.

## [4.0.0] - 2026-09-26 — Smooth animated canvas + split desktop panes

Pointer smoothing, zoom-aligned drawing, autosave, and a two-pane desktop.
Engine behavior for gestures is unchanged; drawing input path reworked.

### Added

- `src/smoothing.py`: dead-zone + exponential + velocity-adaptive
  `PointSmoother`, linear gap interpolation, Catmull-Rom resampling
  (`SMOOTHING`, `DEAD_ZONE_PX` configurable, settings slider).
- `src/animation.py`: lightweight pulse-envelope manager (100–300 ms,
  `ANIMATIONS=full|minimal|off`).
- Pressure-like velocity brush widths, per-stroke/shape opacity, brush
  opacity slider (1–100%), brush size range extended to 1–100 px.
- Canvas backgrounds (dark/white/black/grid/custom), grid overlay,
  snap-to-grid for shape previews, soft + hard erasers, `Canvas.delete_item`.
- Canvas pan (`pan_by`, `reset_view`) + `to_canvas`/`to_view` mapping so
  drawing stays aligned under zoom/pan; zoom now invalidates render cache.
- JPG + vector SVG export; project format v2 (widths/opacity/timestamp/pan,
  backward-compatible loader).
- Desktop split panes (camera preview | drawing canvas) with toggle;
  Ctrl+wheel zoom, middle-drag pan, zoom menu (in/out/reset).
- Autosave (`autosave.json`, revision-keyed) + crash-recovery dialog.
- Sidebar live gesture highlight; status bar Smooth + Canvas-size fields
  with throttled refresh (~8 Hz).
- Shortcuts: Delete, F11 fullscreen, Ctrl+Shift+Z, Ctrl+Shift+S, Ctrl+E,
  Ctrl+O, Esc cancels the active stroke (Q quits in desktop mode).
- `src/applog.py` rotating file logging (`app.log`) for camera/export/
  tracker failures.
- Settings dialog: smoothing, dead zone, opacity, anti-aliasing, backgrounds,
  grid, snap, animations, autosave, camera resolution, eraser softness.
- 37 new tests (smoothing, animation, mapping, delete, exports, backgrounds,
  cursor/cancel/zoom-stamp, split/autosave/recovery); total 130 passing.

### Changed

- Controller draws smoothed, interpolated, canvas-space points (was raw tips).
- Cursor follows the smoothed pointer with states
  (idle/hover/drawing/pinch/erasing) + pulse envelopes.
- `render_overlays` supports `include_canvas=False` for the camera pane.
- `erase_at` gained a `soft` mode (gentler effective radius).

### Fixed

- Strokes/shapes misaligned with the fingertip whenever canvas zoom ≠ 1.0.
- Zoom changes left a stale render cache (now invalidated via `set_zoom`).
- Erase undo dropped per-point velocity widths.
- Desktop: every toolbar button rendered as pressed (`tool == tool`);
  only the active tool highlights now (ttk `!pressed` clearing).
- Desktop: pressing Space re-triggered the focused button (buttons opt out
  of keyboard focus).
- Desktop: typing in settings fields fired global shortcuts (entry-focus guard).
- Desktop: single-row toolbar clipped at small widths (two stacked rows).
- Desktop: view-mode selector showed raw enum values (human labels now) and
  had no effect while split panes were on (selecting a mode opens it solo).
- Desktop: status bar overflowed 800 px minimum width (compact fields).
- Desktop: shutdown-time `TclError` could kill the final poll (now swallowed).
- Desktop: brush slider fought the refresh loop while dragging (0.4 s grace).
- `--debug`/`--no-debug`/`--no-mirror` ignored by `--gui` (now applied).
- `C` stays Clear and `O` stays Circle (master spec §39 asks C=Circle;
  kept for backward compatibility — documented here).

## [3.0.0] - 2026-09-26 — Tkinter desktop studio

The studio is now a real desktop application. OpenCV keeps doing camera /
vision / canvas rendering; all application UI moved to Tkinter + Pillow.
The CV engine is untouched in behavior and shared by both UIs.

### Added

- `src/desktop/` package: main window (1200×750, resizable, min 800×550),
  toolbar, collapsible gesture sidebar, 7-field status bar, settings dialog
  (camera/tracking/gesture/drawing/debug), help + about dialogs, file/edit/
  view/tools/help menus.
- Background engine thread (`EngineWorker`): camera + MediaPipe + canvas run
  off the GUI thread, polled via `root.after`; clean shutdown releases camera
  and MediaPipe resources.
- Real controls: tool buttons with selected state + tooltips, color presets +
  native chooser, brush-size slider with value, view modes
  (Camera+Drawing / Drawing Only / Camera Only), reconnect button, gesture
  status card, debug panel, camera ●/⚠ indicator.
- `python src/main.py --gui` entry point (OpenCV window remains default).
- `Canvas.replace_with` for project loading; `studio_render.render_overlays`
  shared by both UIs so overlays cannot drift.
- 12 desktop tests (`tests/test_desktop.py`): view composition, worker
  pipeline with fake camera, live widget smoke tests (tool/color/brush,
  undo-button states, view modes, help, disconnected status).
- Pillow dependency for `ImageTk` display.

### Changed

- `main.py` overlay code extracted to `src/studio_render.py` (thin wrapper kept).
- Docs updated for the GUI (README, AUDIT, CHANGELOG); test count 81 → 93.

### Fixed

- `ttk.Frame` has no `-background` option (debug Text background via style lookup).
- Test hygiene: single Tk root per test; ttk state-tuple assertions.

## [2.0.0] - 2026-09-26 — AI Hand Gesture Drawing Studio

Full redesign of the finger-counting demo into a real-time drawing studio.
MediaPipe Tasks + OpenCV remain the vision foundation; all original shape
overlays and triggers are preserved.

### Added

- Persistent vector canvas (`src/canvas.py`): strokes, shapes, undo/redo,
  erase, move, zoom, canvas PNG export, project JSON save/load, screenshots.
- Tool system (`src/tools.py`): pencil, brush, line, circle, rectangle,
  triangle, eraser, select; extensible via `register_tool`.
- Semantic gesture actions (`src/gesture_engine.py`, `src/finger_detector.py`):
  DRAW, SHAPE, PAUSE, ERASE, CONFIRM, PINCH (index / two-finger / palm /
  fist / thumbs-up / pinch).
- Gesture state machine (`GestureState`, `GestureSmoother`): confirm frames,
  release grace, one-shot cooldowns; structured `GestureResult`.
- Two-hand extras: smoothed wrist-span zoom, stampable LINE/SPHERE/RECTANGLE.
- Select/move via pinch-drag with coalesced undo steps.
- Optional auto shape recognition (`src/shapes.py`, off by default).
- Studio UI (`src/ui.py`, `src/renderer.py`): dark theme, toolbar, status bar,
  debug panel with latency, help + settings overlays, fingertip cursor.
- Local settings (`src/config.py`, `src/settings_store.py`, `settings.json`).
- 81 camera-free unit tests (`tests/`: geometry, gesture, canvas, shapes,
  interaction).
- Docs: `README.md`, `AUDIT.md`, `CHANGELOG.md`, `.gitignore`.

### Changed

- Finger detection now uses joint angles + relative distances (rotation/scale
  tolerant) and includes the thumb (counts reach 5).
- `gesture.py` is a backwards-compatible shim over `hand_tracker.py` /
  `finger_detector.py`; `geometry.py` is pure math with deprecated `draw_*`
  wrappers delegating to `renderer.py`.
- `main.py` is a slim `StudioApp` controller owning the
  Camera → Tracker → Classifier → Smoother → Controller → Canvas →
  Renderer → UI pipeline.
- `requirements.txt` pinned with usage comments; `README.md` rewritten.

### Fixed

- Help overlay dimmed the status bar (panels now render under the bars).
- Title/camera status overlapped on narrow frames (short title + dot fallback).
- Debug lines piled up on short frames (visible-line capping).
- Status/toolbar text overflowed narrow frames (ellipsis trimming).
- Help screen said "T stamps"; stamping is `SPACE` (T is the triangle tool).
- `SHOW_GESTURE_HINTS` flag was ignored; status line regained gesture colors.
- In-place `addWeighted` blending replaced with out-of-place composites.
- Pointer cursor now follows any visible single hand, not only draw actions.

- Thumb never counted (LINE-on-two-open-palms unreachable) — now counts to 5.
- Tilted/rotated hands broke the `tip.y < pip.y` check — distance/angle logic.
- Unreachable "No hands detected" branch — restructured.
- Cumulative-average FPS — rolling-window FPS.
- Blue-tinted sphere — true yellow-orange radial shading + highlight/rim/glow.
- Missing cleanup on errors — `try/finally`, context managers, typed errors
  (`CameraError`, `ValueError` on bad frames, `RuntimeError` on transient
  MediaPipe failures, `FileNotFoundError` with tried model paths).
- `train.py` executing code on import — guarded + documented stub.

### Removed

- Nothing user-facing. Obsolete inline logic was refactored into modules;
  all legacy imports keep working through shims/wrappers.

## [1.0.0] - Original prototype

- Webcam loop with mirrored feed and MediaPipe hand skeletons.
- Finger counting (`tip.y < pip.y`, no thumb) mapped to ephemeral LINE /
  SPHERE / CIRCLE / RECTANGLE overlays for one/two hands.
- Minimal `camera.py`, `gesture.py`, `geometry.py`, `utils.py`, `train.py` stub.
