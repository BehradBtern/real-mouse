"""Mapping: corners, monotonicity, edge gain and relative movement."""

from __future__ import annotations

import unittest

from virtual_mouse.config import Config
from virtual_mouse.mapping import Mapper, shape_edge


def mapper(**overrides) -> Mapper:
    config = Config().with_overrides(**overrides)
    return Mapper(1920, 1080, config)


class TestAbsoluteMapping(unittest.TestCase):
    def test_box_corners_hit_screen_corners(self) -> None:
        m = mapper()
        left, right, top, bottom = m.config.region
        self.assertEqual(m.map(left, top), (0.0, 0.0))
        self.assertEqual(m.map(right, bottom), (1919.0, 1079.0))

    def test_centre_maps_to_centre(self) -> None:
        m = mapper()
        x, y = m.map(0.5, 0.5)
        self.assertAlmostEqual(x, 959.5, delta=2.0)
        self.assertAlmostEqual(y, 539.5, delta=2.0)

    def test_monotonic_in_both_axes(self) -> None:
        m = mapper()
        last_x = -1.0
        for i in range(21):
            x, _ = m.map(0.18 + i * 0.032, 0.5)
            self.assertGreaterEqual(x, last_x)
            last_x = x

    def test_outside_the_box_is_clamped(self) -> None:
        m = mapper()
        self.assertEqual(m.map(-1.0, -1.0), (0.0, 0.0))
        self.assertEqual(m.map(2.0, 2.0), (1919.0, 1079.0))

    def test_invert_y_flips_the_axis(self) -> None:
        m = mapper(invert_y=True)
        _, top_y = m.map(0.5, 0.16)
        _, bottom_y = m.map(0.5, 0.84)
        self.assertGreater(top_y, bottom_y)


class TestEdgeGain(unittest.TestCase):
    def test_gamma_below_one_pushes_towards_the_edges(self) -> None:
        self.assertGreater(shape_edge(0.75, 0.82), 0.75)
        self.assertLess(shape_edge(0.25, 0.82), 0.25)

    def test_identity_when_gamma_is_one(self) -> None:
        for t in (0.0, 0.1, 0.5, 0.9, 1.0):
            self.assertAlmostEqual(shape_edge(t, 1.0), t, places=6)

    def test_centre_is_fixed(self) -> None:
        self.assertAlmostEqual(shape_edge(0.5, 0.7), 0.5, places=6)

    def test_gain_is_monotonic(self) -> None:
        values = [shape_edge(i / 20, 0.8) for i in range(21)]
        self.assertEqual(values, sorted(values))


class TestRelativeMapping(unittest.TestCase):
    def test_first_frame_does_not_move_the_pointer(self) -> None:
        m = mapper(mode="relative")
        start = (m.x, m.y)
        self.assertEqual(m.map_relative(0.6, 0.4), start)

    def test_movement_scales_with_gain(self) -> None:
        m = mapper(mode="relative", relative_gain=2.0)
        m.map_relative(0.5, 0.5)
        x0, y0 = m.map_relative(0.5, 0.5)
        x1, _ = m.map_relative(0.55, 0.5)
        # du = 0.05 over a box width of 0.64 -> 0.078 * gain 2 * 1920 px
        self.assertGreater(x1 - x0, 200.0)

    def test_stays_on_screen(self) -> None:
        m = mapper(mode="relative", relative_gain=6.0)
        m.map_relative(0.5, 0.5)
        for _ in range(50):
            x, y = m.map_relative(0.9, 0.1)
        self.assertLessEqual(x, 1919.0)
        self.assertGreaterEqual(y, 0.0)


if __name__ == "__main__":
    unittest.main()
