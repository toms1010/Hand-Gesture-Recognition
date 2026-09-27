"""Unit tests for finger detection, classification and smoothing."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
from finger_detector import (
    count_fingers,
    extended_fingers,
    is_fist,
    is_index_point,
    is_open_palm,
    is_pinch,
    is_thumbs_up,
)
from gesture_engine import (
    ACTION_CONFIRM,
    ACTION_DRAW,
    ACTION_ERASE,
    ACTION_IDLE,
    ACTION_PAUSE,
    ACTION_PINCH,
    ACTION_SHAPE,
    CIRCLE,
    LINE,
    NONE,
    RECT,
    RECTANGLE,
    SPHERE,
    GestureClassifier,
    GestureResult,
    GestureSmoother,
    GestureState,
    classify_action_single,
    classify_single_hand,
    classify_two_hands,
)
from helpers import make_hand, make_pinch_hand

ALL = ("index", "middle", "ring", "pinky")


class TestFingerCounting(unittest.TestCase):
    def test_open_palm_is_five(self):
        hand = make_hand(fingers_open=ALL, thumb_open=True)
        self.assertEqual(count_fingers(hand), 5)
        self.assertTrue(is_open_palm(hand))

    def test_fist_is_zero(self):
        hand = make_hand(fingers_open=(), thumb_open=False)
        self.assertEqual(count_fingers(hand), 0)
        self.assertTrue(is_fist(hand))

    def test_two_fingers(self):
        hand = make_hand(fingers_open=("index", "middle"), thumb_open=False)
        self.assertEqual(count_fingers(hand), 2)

    def test_index_only(self):
        hand = make_hand(fingers_open=("index",), thumb_open=False)
        self.assertTrue(is_index_point(hand))
        self.assertEqual(count_fingers(hand), 1)

    def test_thumb_only(self):
        hand = make_hand(fingers_open=(), thumb_open=True)
        self.assertTrue(is_thumbs_up(hand))
        self.assertEqual(count_fingers(hand), 1)

    def test_missing_landmarks(self):
        self.assertEqual(count_fingers(None), 0)
        self.assertEqual(count_fingers([]), 0)
        self.assertEqual(extended_fingers([1, 2]), [])

    def test_pinch(self):
        hand = make_pinch_hand()
        self.assertTrue(is_pinch(hand))
        plain = make_hand(fingers_open=("index",), thumb_open=False)
        self.assertFalse(is_pinch(plain))


class TestShapeClassification(unittest.TestCase):
    def test_two_hands_line(self):
        self.assertEqual(classify_two_hands((5, 5)), (LINE, 0.95))

    def test_two_hands_sphere(self):
        self.assertEqual(classify_two_hands((2, 2)), (SPHERE, 0.95))

    def test_two_hands_rectangle(self):
        self.assertEqual(classify_two_hands((3, 4)), (RECTANGLE, 0.95))
        self.assertEqual(classify_two_hands((4, 3)), (RECTANGLE, 0.95))

    def test_two_hands_none(self):
        self.assertEqual(classify_two_hands((1, 1))[0], NONE)
        self.assertEqual(classify_two_hands((0, 5))[0], NONE)

    def test_single_hand(self):
        self.assertEqual(classify_single_hand(1)[0], LINE)
        self.assertEqual(classify_single_hand(2)[0], CIRCLE)
        for count in (0, 3, 4, 5):
            self.assertEqual(classify_single_hand(count)[0], RECT)


class TestSemanticActions(unittest.TestCase):
    def test_draw(self):
        hand = make_hand(fingers_open=("index",), thumb_open=False)
        self.assertEqual(classify_action_single(hand)[0], ACTION_DRAW)

    def test_shape(self):
        hand = make_hand(fingers_open=("index", "middle"), thumb_open=False)
        self.assertEqual(classify_action_single(hand)[0], ACTION_SHAPE)

    def test_erase(self):
        hand = make_hand(fingers_open=(), thumb_open=False)
        self.assertEqual(classify_action_single(hand)[0], ACTION_ERASE)

    def test_pause(self):
        hand = make_hand(fingers_open=ALL, thumb_open=True)
        self.assertEqual(classify_action_single(hand)[0], ACTION_PAUSE)

    def test_confirm(self):
        hand = make_hand(fingers_open=(), thumb_open=True)
        self.assertEqual(classify_action_single(hand)[0], ACTION_CONFIRM)

    def test_pinch(self):
        self.assertEqual(classify_action_single(make_pinch_hand())[0], ACTION_PINCH)

    def test_no_hand(self):
        self.assertEqual(classify_action_single(None)[0], ACTION_IDLE)


class TestClassifierResult(unittest.TestCase):
    def setUp(self):
        self.classifier = GestureClassifier()

    def test_two_open_hands(self):
        result = self.classifier.classify(
            [make_hand(ALL, True), make_hand(ALL, True)])
        self.assertEqual(result.name, LINE)
        self.assertEqual(result.hand_count, 2)
        self.assertEqual(result.finger_counts, (5, 5))
        self.assertAlmostEqual(result.confidence, 0.95)

    def test_no_hands(self):
        result = self.classifier.classify([])
        self.assertEqual(result.name, NONE)
        self.assertEqual(result.hand_count, 0)
        self.assertFalse(result.is_stable)

    def test_result_fields(self):
        result = GestureResult(name=SPHERE, confidence=0.94, hand_count=2,
                               finger_counts=(2, 2), is_stable=True)
        text = str(result)
        self.assertIn("SPHERE", text)
        self.assertIn("0.94", text)


class TestSmoother(unittest.TestCase):
    def test_confirm_threshold(self):
        smoother = GestureSmoother(confirm_frames=3, release_frames=2)
        self.assertEqual(smoother.update(SPHERE), (NONE, False))
        self.assertEqual(smoother.update(SPHERE), (NONE, False))
        self.assertEqual(smoother.update(SPHERE), (SPHERE, True))

    def test_flicker_ignored(self):
        """SPHERE, SPHERE, NONE, SPHERE, SPHERE must not flicker."""
        smoother = GestureSmoother(confirm_frames=3, release_frames=3)
        smoother.update(SPHERE)
        smoother.update(SPHERE)
        smoother.update(SPHERE)  # confirmed now
        confirmed, stable = smoother.update(NONE)  # single noisy frame
        self.assertEqual(confirmed, SPHERE)
        self.assertTrue(stable)
        confirmed, _ = smoother.update(SPHERE)
        self.assertEqual(confirmed, SPHERE)

    def test_release_after_sustained_loss(self):
        smoother = GestureSmoother(confirm_frames=2, release_frames=2)
        smoother.update(SPHERE)
        smoother.update(SPHERE)
        smoother.update(NONE)  # grace (1 <= 2)
        self.assertEqual(smoother.confirmed, SPHERE)
        smoother.update(NONE)
        smoother.update(NONE)  # exceeded grace
        self.assertEqual(smoother.confirmed, NONE)

    def test_state_transitions(self):
        smoother = GestureSmoother(confirm_frames=3, release_frames=2)
        smoother.update(SPHERE)
        self.assertEqual(smoother.state, GestureState.DETECTED)
        smoother.update(SPHERE)
        self.assertEqual(smoother.state, GestureState.CANDIDATE)
        smoother.update(SPHERE)
        self.assertEqual(smoother.state, GestureState.STABLE)
        smoother.update(SPHERE)
        self.assertEqual(smoother.state, GestureState.ACTIVE)

    def test_cooldown(self):
        smoother = GestureSmoother()
        self.assertTrue(smoother.ready("CONFIRM", now=100.0))
        self.assertFalse(smoother.ready("CONFIRM", now=100.1))
        self.assertTrue(smoother.ready("CONFIRM", now=100.0 + config.GESTURE_COOLDOWN + 0.01))

    def test_update_result_preserves_counts(self):
        smoother = GestureSmoother(confirm_frames=2)
        result = GestureResult(name=SPHERE, confidence=0.95, hand_count=2,
                               finger_counts=(2, 2))
        out = smoother.update_result(result)
        self.assertEqual(out.finger_counts, (2, 2))
        self.assertEqual(out.hand_count, 2)


if __name__ == "__main__":
    unittest.main()
