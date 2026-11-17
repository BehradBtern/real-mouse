"""Gesture state machine: clicks, right clicks, scroll, hand loss, coasting."""

from __future__ import annotations

import unittest

from helpers import FRAME_MS, make_hand, rotate
from virtual_mouse.config import Config
from virtual_mouse.gestures import Gesture, GestureEngine, HandCoaster


def engine(**overrides) -> GestureEngine:
    return GestureEngine(Config().with_overrides(**overrides))


def run(engine: GestureEngine, frames, start_ms: float = 0.0):
    """Feed frames, return (actions, last_time)."""
    actions = []
    now = start_ms
    for hand in frames:
        now += FRAME_MS
        intent = engine.update(hand, now)
        actions.extend(intent.actions)
    return actions, now


class TestClicks(unittest.TestCase):
    def test_one_pinch_is_one_click(self) -> None:
        e = engine()
        frames = [make_hand(pinch=1.0)] * 5 + [make_hand(pinch=0.15)] * 8 + [make_hand(pinch=1.0)] * 5
        actions, _ = run(e, frames)
        self.assertEqual(actions, [("click", "left")])

    def test_holding_the_pinch_does_not_drag(self) -> None:
        e = engine()
        # 40 frames of held pinch: a drag would keep the button down for all of it
        actions, _ = run(e, [make_hand(pinch=0.2)] * 40)
        self.assertEqual(actions, [("click", "left")])
        self.assertFalse(any(action[0] in ("down", "up") for action in actions))

    def test_hovering_at_the_threshold_does_not_click(self) -> None:
        e = engine()
        # 0.60 sits between press (0.50) and release (0.72): must stay inert
        actions, _ = run(e, [make_hand(pinch=0.60)] * 30)
        self.assertEqual(actions, [])

    def test_repeated_pinches_are_separate_clicks(self) -> None:
        e = engine()
        frames = []
        for _ in range(3):
            frames += [make_hand(pinch=0.2)] * 6 + [make_hand(pinch=1.0)] * 12
        actions, _ = run(e, frames)
        self.assertEqual(actions.count(("click", "left")), 3)

    def test_click_requires_a_stable_frame(self) -> None:
        e = engine(stable_frames=3)
        actions, _ = run(e, [make_hand(pinch=0.2)] * 2 + [make_hand(pinch=1.0)])
        self.assertEqual(actions, [])

    def test_one_pinch_never_fires_twice(self) -> None:
        e = engine()
        # a long, jittery hold that stays below the release threshold
        frames = [make_hand(pinch=0.2)] * 30 + [make_hand(pinch=0.3)] * 30
        actions, _ = run(e, frames)
        self.assertEqual(actions.count(("click", "left")), 1)


class TestRightClick(unittest.TestCase):
    def test_middle_pinch_clicks_once(self) -> None:
        e = engine()
        actions, _ = run(e, [make_hand(pinch=1.0, middle_pinch=0.2)] * 10)
        self.assertEqual(actions, [("click", "right")])

    def test_index_pinch_is_not_a_right_click(self) -> None:
        e = engine()
        actions, _ = run(e, [make_hand(pinch=0.2, middle_pinch=1.0)] * 10)
        self.assertEqual(actions, [("click", "left")])

    def test_cooldown_blocks_a_second_right_click(self) -> None:
        e = engine()
        actions, now = run(e, [make_hand(pinch=1.0, middle_pinch=0.2)] * 6)
        actions += run(e, [make_hand(pinch=1.0, middle_pinch=1.0)] * 3, now)[0]
        actions += run(e, [make_hand(pinch=1.0, middle_pinch=0.2)] * 6, now + 6 * FRAME_MS)[0]
        self.assertEqual(actions.count(("click", "right")), 1)


class TestScroll(unittest.TestCase):
    def test_fist_enters_scroll_and_never_clicks(self) -> None:
        e = engine()
        actions, _ = run(e, [make_hand(fist=True, pinch=0.1)] * 8)
        self.assertNotIn(("click", "left"), actions)
        self.assertTrue(e.scrolling)

    def test_fist_test_is_orientation_independent(self) -> None:
        e = engine()
        for degrees in (0, 45, 90, 180, 270):
            fist = rotate(make_hand(fist=True), degrees)
            self.assertTrue(fist.is_fist(), f"fist lost at {degrees} degrees")
            open_hand = rotate(make_hand(pinch=1.0), degrees)
            self.assertFalse(open_hand.is_fist(), f"open hand read as a fist at {degrees} degrees")

    def test_wrist_travel_produces_notches(self) -> None:
        e = engine()
        actions, _ = run(e, [make_hand(fist=True)] * 4)
        now = 4 * FRAME_MS
        for i in range(12):
            now += FRAME_MS
            intent = e.update(make_hand(fist=True, y=0.5 - i * 0.02), now)
            actions.extend(intent.actions)
        scrolls = [a for a in actions if a[0] == "scroll"]
        self.assertTrue(scrolls, "expected scroll actions")
        self.assertTrue(all(value > 0 for _, value in scrolls), "hand up must scroll up")

    def test_scroll_mode_keeps_the_pointer(self) -> None:
        e = engine()
        run(e, [make_hand(fist=True)] * 5)
        intent = e.update(make_hand(fist=True, x=0.9), 5 * FRAME_MS + FRAME_MS)
        self.assertIsNotNone(intent.pointer)
        self.assertFalse(any(action[0] == "click" for action in intent.actions))


class TestHandLoss(unittest.TestCase):
    def test_short_dropout_keeps_state(self) -> None:
        e = engine()
        run(e, [make_hand(pinch=0.2)] * 6)
        now = 6 * FRAME_MS + 40
        intent = e.update(None, now)
        self.assertFalse(any(a[0] in ("down", "up") for a in intent.actions))
        self.assertTrue(intent.hand_lost)

    def test_long_loss_clears_the_latch(self) -> None:
        e = engine()
        run(e, [make_hand(pinch=0.2)] * 6)
        self.assertTrue(e.left_latched)
        e.update(None, 6 * FRAME_MS + 900)
        self.assertFalse(e.left_latched)

    def test_loss_never_emits_a_click(self) -> None:
        e = engine()
        actions, now = run(e, [make_hand(pinch=1.0)] * 5)
        actions += e.update(None, now + 900).actions
        self.assertEqual(actions, [])


class TestCoaster(unittest.TestCase):
    def test_holds_the_last_pose_through_a_short_dropout(self) -> None:
        coaster = HandCoaster(hold_ms=200)
        hand = make_hand()
        handed, coasted = coaster.update(hand, 1000.0)
        self.assertIs(handed, hand)
        self.assertFalse(coasted)

        same, coasted = coaster.update(None, 1100.0)
        self.assertIs(same, hand)
        self.assertTrue(coasted)

    def test_gives_up_after_the_window(self) -> None:
        coaster = HandCoaster(hold_ms=200)
        coaster.update(make_hand(), 1000.0)
        lost, coasted = coaster.update(None, 1400.0)
        self.assertIsNone(lost)
        self.assertFalse(coasted)

    def test_no_pose_means_no_coast(self) -> None:
        coaster = HandCoaster(hold_ms=200)
        lost, coasted = coaster.update(None, 1000.0)
        self.assertIsNone(lost)
        self.assertFalse(coasted)

    def test_a_fresh_detection_resets_the_window(self) -> None:
        coaster = HandCoaster(hold_ms=200)
        coaster.update(make_hand(), 1000.0)
        coaster.update(None, 1150.0)
        coaster.update(make_hand(), 1160.0)
        same, coasted = coaster.update(None, 1300.0)
        self.assertIsNotNone(same)
        self.assertTrue(coasted)


if __name__ == "__main__":
    unittest.main()
