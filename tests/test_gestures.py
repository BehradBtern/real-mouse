"""Gesture state machine: clicks, drags, right clicks, scroll, hand loss."""

from __future__ import annotations

import unittest

from helpers import FRAME_MS, make_hand
from virtual_mouse.config import Config
from virtual_mouse.gestures import Gesture, GestureEngine


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
        self.assertEqual(actions, [("down", "left"), ("up", "left")])

    def test_hovering_at_the_threshold_does_not_click(self) -> None:
        e = engine()
        # 0.47 sits between press (0.38) and release (0.56): must stay inert
        frames = [make_hand(pinch=0.47)] * 30
        actions, _ = run(e, frames)
        self.assertEqual(actions, [])

    def test_repeated_pinches_are_separate_clicks(self) -> None:
        e = engine()
        frames = []
        for _ in range(3):
            frames += [make_hand(pinch=0.2)] * 6 + [make_hand(pinch=1.0)] * 12
        actions, _ = run(e, frames)
        self.assertEqual(actions.count(("down", "left")), 3)
        self.assertEqual(actions.count(("up", "left")), 3)

    def test_press_requires_stable_frames(self) -> None:
        e = engine(stable_frames=3)
        actions, _ = run(e, [make_hand(pinch=0.2)] * 2 + [make_hand(pinch=1.0)])
        self.assertEqual(actions, [])


class TestDrag(unittest.TestCase):
    def test_holding_the_pinch_keeps_the_button_down(self) -> None:
        e = engine()
        frames = [make_hand(pinch=0.2, x=0.4)] * 10
        frames += [make_hand(pinch=0.2, x=0.4 + i * 0.01) for i in range(10)]
        actions, _ = run(e, frames)
        self.assertEqual(actions.count(("down", "left")), 1)
        self.assertEqual(actions.count(("up", "left")), 0)
        self.assertTrue(e.pressed)

    def test_drag_gesture_is_reported(self) -> None:
        e = engine()
        run(e, [make_hand(pinch=0.2, x=0.4)] * 6)
        now = 6 * FRAME_MS
        for i in range(8):
            now += FRAME_MS
            intent = e.update(make_hand(pinch=0.2, x=0.4 + 0.01 * i), now)
        self.assertEqual(intent.gesture, Gesture.DRAG)


class TestRightClick(unittest.TestCase):
    def test_middle_pinch_clicks_once_with_cooldown(self) -> None:
        e = engine()
        frames = [make_hand(pinch=1.0, middle_pinch=0.2)] * 10
        actions, _ = run(e, frames)
        self.assertEqual(actions, [("click", "right")])

    def test_right_click_never_fires_while_left_is_held(self) -> None:
        e = engine()
        frames = [make_hand(pinch=0.2, middle_pinch=0.2)] * 12
        actions, _ = run(e, frames)
        self.assertNotIn(("click", "right"), actions)
        self.assertIn(("down", "left"), actions)


class TestScroll(unittest.TestCase):
    def test_fist_enters_scroll_and_suppresses_clicks(self) -> None:
        e = engine()
        frames = [make_hand(fist=True, pinch=0.1)] * 8
        actions, _ = run(e, frames)
        self.assertNotIn(("down", "left"), actions)
        self.assertTrue(e.scrolling)

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

    def test_scroll_mode_keeps_the_pointer_and_suppresses_clicks(self) -> None:
        e = engine()
        run(e, [make_hand(fist=True)] * 5)
        intent = e.update(make_hand(fist=True, x=0.9), 5 * FRAME_MS + FRAME_MS)
        # the pointer keeps tracking (no teleport when the fist opens) ...
        self.assertIsNotNone(intent.pointer)
        # ... but nothing may be clicked in scroll mode
        self.assertFalse(any(action[0] == "down" for action in intent.actions))


class TestHandLoss(unittest.TestCase):
    def test_short_dropout_holds_state(self) -> None:
        e = engine()
        run(e, [make_hand(pinch=0.2)] * 6)
        now = 6 * FRAME_MS + 40
        intent = e.update(None, now)
        self.assertFalse(any(a[0] == "up" for a in intent.actions))
        self.assertTrue(e.pressed)

    def test_long_loss_releases_the_button(self) -> None:
        e = engine()
        run(e, [make_hand(pinch=0.2)] * 6)
        now = 6 * FRAME_MS
        intent = e.update(None, now + 500)
        self.assertIn(("up", "left"), intent.actions)
        self.assertFalse(e.pressed)


if __name__ == "__main__":
    unittest.main()
