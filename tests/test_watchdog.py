"""Unit tests for the MediaPipe watchdog, rebuild and clean interrupt."""
import sys
import time
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))


class FastFake:
    """Detector stand-in returning immediately."""

    def __init__(self):
        self.calls = 0

    def detect(self, _mp_image):
        self.calls += 1
        return "ok"


class SlowFake:
    """Detector stand-in wedging longer than any test timeout."""

    def __init__(self, delay=5.0):
        self.delay = delay
        self.calls = 0

    def detect(self, _mp_image):
        self.calls += 1
        time.sleep(self.delay)
        return "late"


class TestDetectWithTimeout(unittest.TestCase):
    def test_fast_detector(self):
        from hand_tracker import DetectionTimeout, detect_with_timeout
        fake = FastFake()
        self.assertEqual(detect_with_timeout(fake, None, timeout=2.0), "ok")
        self.assertEqual(fake.calls, 1)

    def test_slow_detector_times_out(self):
        from hand_tracker import DetectionTimeout, detect_with_timeout
        with self.assertRaises(DetectionTimeout):
            detect_with_timeout(SlowFake(), None, timeout=0.1)

    def test_timeout_is_runtime_error(self):
        from hand_tracker import DetectionTimeout
        self.assertTrue(issubclass(DetectionTimeout, RuntimeError))

    def test_detector_error_forwarded(self):
        from hand_tracker import detect_with_timeout

        class Broken:
            def detect(self, _mp_image):
                raise ValueError("bad image")

        with self.assertRaisesRegex(ValueError, "bad image"):
            detect_with_timeout(Broken(), None, timeout=2.0)


class TestTrackerRecovery(unittest.TestCase):
    def test_repeated_timeouts_rebuild(self):
        from hand_tracker import HandTracker
        tracker = HandTracker(detect_timeout=0.1, max_timeouts=1)
        fake = SlowFake()
        tracker.detector = fake
        builds = []
        original_build = tracker._build

        def counting_build():
            builds.append(True)
            return original_build()

        tracker._build = counting_build
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        from hand_tracker import DetectionTimeout
        with self.assertRaises(DetectionTimeout):
            tracker.detect(frame)
        with self.assertRaises(DetectionTimeout):
            tracker.detect(frame)
        self.assertEqual(len(builds), 1)  # rebuilt after exceeding budget
        self.assertIsNot(tracker.detector, fake)

    def test_frame_cap_for_detection(self):
        from hand_tracker import HandTracker
        big = np.zeros((1000, 2000, 3), dtype=np.uint8)
        small = HandTracker._detection_frame(big)
        self.assertLessEqual(small.shape[1], 960)
        untouched = np.zeros((240, 320, 3), dtype=np.uint8)
        self.assertIs(HandTracker._detection_frame(untouched), untouched)


class TestCleanInterrupt(unittest.TestCase):
    def test_keyboard_interrupt_exits_130(self):
        import main as main_module
        from main import StudioApp

        class FakeCamera:
            def __init__(self):
                self.released = False

            def get_frame(self):
                return np.zeros((240, 320, 3), dtype=np.uint8)

            def release(self):
                self.released = True

        class InterruptApp(StudioApp):
            def _display(self, _frame):
                raise KeyboardInterrupt

        saved_camera = main_module.Camera
        saved_save = main_module.settings_store.save
        main_module.Camera = lambda _id: FakeCamera()  # noqa: E731
        main_module.settings_store.save = lambda *a, **k: None
        try:
            app = InterruptApp(main_module.parse_args([]))
            code = app.run()
        finally:
            main_module.Camera = saved_camera
            main_module.settings_store.save = saved_save
        self.assertEqual(code, 130)
        self.assertTrue(app.camera.released)


if __name__ == "__main__":
    unittest.main()
