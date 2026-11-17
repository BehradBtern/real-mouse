"""Camera cycling rules — pure logic, no hardware."""

from __future__ import annotations

import unittest

from virtual_mouse.cameras import next_camera, normalise


class TestNormalise(unittest.TestCase):
    def test_sorts_and_deduplicates(self) -> None:
        self.assertEqual(normalise([2, 0, 2, 1]), [0, 1, 2])

    def test_drops_negatives(self) -> None:
        self.assertEqual(normalise([-1, 0, -3]), [0])

    def test_empty(self) -> None:
        self.assertEqual(normalise([]), [])


class TestNextCamera(unittest.TestCase):
    def test_single_camera_stays_put(self) -> None:
        self.assertEqual(next_camera(0, [0]), 0)

    def test_wraps_around(self) -> None:
        self.assertEqual(next_camera(0, [0, 1]), 1)
        self.assertEqual(next_camera(1, [0, 1]), 0)

    def test_three_cameras(self) -> None:
        self.assertEqual(next_camera(0, [0, 1, 2]), 1)
        self.assertEqual(next_camera(1, [0, 1, 2]), 2)
        self.assertEqual(next_camera(2, [0, 1, 2]), 0)

    def test_current_missing_falls_back_to_first(self) -> None:
        self.assertEqual(next_camera(3, [0, 1]), 0)

    def test_no_cameras_returns_none(self) -> None:
        self.assertIsNone(next_camera(0, []))
        self.assertIsNone(next_camera(0, [-1]))

    def test_step_backwards(self) -> None:
        self.assertEqual(next_camera(0, [0, 1, 2], step=-1), 2)


if __name__ == "__main__":
    unittest.main()
