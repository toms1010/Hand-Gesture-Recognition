"""Unit tests for the animation envelope manager."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from animation import AnimationManager


class FakeClock:
    """Manual clock (seconds)."""

    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance_ms(self, ms: float):
        """Move time forward."""
        self.now += ms / 1000.0


class TestAnimationManager(unittest.TestCase):
    def test_idle_zero(self):
        manager = AnimationManager(clock=FakeClock())
        self.assertEqual(manager.pulse_value("x"), 0.0)
        self.assertFalse(manager.active("x"))

    def test_pulse_envelope(self):
        clock = FakeClock()
        manager = AnimationManager(duration_ms=200.0, clock=clock)
        manager.pulse("x")
        clock.advance_ms(100)
        mid = manager.pulse_value("x")
        self.assertGreater(mid, 0.9)  # peak at mid-duration
        clock.advance_ms(150)
        self.assertEqual(manager.pulse_value("x"), 0.0)
        self.assertFalse(manager.active("x"))

    def test_retrigger(self):
        clock = FakeClock()
        manager = AnimationManager(duration_ms=200.0, clock=clock)
        manager.pulse("x")
        clock.advance_ms(190)
        first = manager.pulse_value("x")
        manager.pulse("x")  # restart near the end
        clock.advance_ms(100)
        self.assertGreater(manager.pulse_value("x"), first)

    def test_clear(self):
        clock = FakeClock()
        manager = AnimationManager(clock=clock)
        manager.pulse("a")
        manager.pulse("b")
        manager.clear("a")
        clock.advance_ms(50)
        self.assertEqual(manager.pulse_value("a"), 0.0)
        self.assertGreater(manager.pulse_value("b"), 0.0)
        manager.clear()
        self.assertEqual(manager.pulse_value("b"), 0.0)


if __name__ == "__main__":
    unittest.main()
