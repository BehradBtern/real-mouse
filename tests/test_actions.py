"""Controller behaviour: guards, sub-pixel moves and action dispatch."""

from __future__ import annotations

import unittest

from virtual_mouse.actions import MouseController, RecordingBackend
from virtual_mouse.config import Config
from virtual_mouse.gestures import Gesture, Intent


class TestController(unittest.TestCase):
    def setUp(self) -> None:
        self.backend = RecordingBackend()
        self.controller = MouseController(Config(dry_run=True), self.backend)

    def test_double_press_is_ignored(self) -> None:
        self.controller.press("left")
        self.controller.press("left")
        self.assertEqual(self.backend.of_type("down"), [("down", "left")])

    def test_release_without_press_is_ignored(self) -> None:
        self.controller.release("left")
        self.assertEqual(self.backend.of_type("up"), [])

    def test_scroll_zero_is_a_noop(self) -> None:
        self.controller.scroll(0)
        self.assertEqual(self.backend.of_type("scroll"), [])

    def test_scroll_accumulates_the_total(self) -> None:
        self.controller.scroll(3)
        self.controller.scroll(-2)
        self.assertEqual(self.controller.scroll_notches, 5)

    def test_move_is_deduplicated(self) -> None:
        self.controller.move(100.2, 100.2)
        self.controller.move(100.4, 100.4)
        self.assertEqual(len(self.backend.of_type("move")), 1)

    def test_apply_dispatches_in_order(self) -> None:
        intent = Intent(
            pointer=(500.0, 400.0),
            actions=[("down", "left"), ("scroll", 2), ("up", "left")],
            gesture=Gesture.MOVE,
        )
        self.controller.apply(intent)
        kinds = [event[0] for event in self.backend.events]
        self.assertEqual(kinds, ["move", "down", "scroll", "up"])

    def test_close_releases_a_held_button(self) -> None:
        self.controller.press("left")
        self.controller.close()
        self.assertEqual(self.backend.of_type("up"), [("up", "left")])

    def test_moves_are_clamped_by_the_accumulator_not_the_controller(self) -> None:
        # the controller trusts the mapper to clamp; it must not invent positions
        self.controller.move(1919.0, 1079.0)
        self.assertEqual(self.backend.of_type("move")[-1], ("move", 1919, 1079))


if __name__ == "__main__":
    unittest.main()
