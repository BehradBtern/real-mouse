"""Filter behaviour: the difference between a shaky dot and a pointer."""

from __future__ import annotations

import math
import random
import unittest

from virtual_mouse.filters import (
    Deadband,
    Hysteresis,
    OneEuro,
    SubPixelAccumulator,
)


class TestOneEuro(unittest.TestCase):
    def test_converges_to_a_step(self) -> None:
        f = OneEuro(min_cutoff=2.0, beta=0.5)
        value = 0.0
        for _ in range(120):
            value = f.filter(10.0, 1 / 60)
        self.assertAlmostEqual(value, 10.0, delta=0.05)

    def test_reduces_noise_more_than_a_raw_signal(self) -> None:
        random.seed(3)
        raw = [0.5 + random.gauss(0, 0.01) for _ in range(240)]
        f = OneEuro(min_cutoff=1.0, beta=0.3)
        filtered = [f.filter(v, 1 / 60) for v in raw]

        def variance(values: list[float]) -> float:
            mean = sum(values) / len(values)
            return sum((v - mean) ** 2 for v in values) / len(values)

        self.assertLess(variance(filtered), variance(raw) * 0.35)

    def test_follows_fast_motion_without_lagging_behind(self) -> None:
        f = OneEuro(min_cutoff=1.0, beta=0.9)
        f.filter(0.0, 1 / 60)
        for i in range(1, 30):
            out = f.filter(i * 2.0, 1 / 60)
        # after 0.5s of constant velocity the filtered value must be close
        self.assertLess(abs(out - 58.0), 12.0)


class TestHysteresis(unittest.TestCase):
    def test_does_not_chatter_around_the_threshold(self) -> None:
        trigger = Hysteresis(on=10.0, off=14.0)
        values = [9.0, 9.5, 10.5, 11.0, 10.2, 12.0, 13.5, 13.9, 10.0, 11.0]
        states = [trigger.update(v) for v in values]
        # one press, no release until 14.0 is crossed
        self.assertEqual(states, [True] * 10)

    def test_release_requires_the_upper_threshold(self) -> None:
        trigger = Hysteresis(on=10.0, off=14.0)
        self.assertTrue(trigger.update(9.0))
        self.assertTrue(trigger.update(13.0))
        self.assertFalse(trigger.update(14.1))


class TestDeadband(unittest.TestCase):
    def test_ignores_sub_threshold_movement(self) -> None:
        band = Deadband(threshold=1.0)
        band.apply(100.0, 100.0)
        self.assertEqual(band.apply(100.4, 100.2), (100.0, 100.0))

    def test_passes_larger_movement_through(self) -> None:
        band = Deadband(threshold=1.0)
        band.apply(100.0, 100.0)
        self.assertEqual(band.apply(103.0, 100.0), (103.0, 100.0))

    def test_threshold_is_clamped(self) -> None:
        band = Deadband(0.4)
        self.assertEqual(band.set_threshold(9.0), Deadband.MAX)
        self.assertEqual(band.set_threshold(-3.0), Deadband.MIN)

    def test_raising_the_threshold_suppresses_more(self) -> None:
        band = Deadband(threshold=0.0)
        band.apply(100.0, 100.0)
        band.set_threshold(2.0)
        self.assertEqual(band.apply(101.0, 100.0), (100.0, 100.0))
        self.assertEqual(band.apply(102.5, 100.0), (102.5, 100.0))


class TestSubPixelAccumulator(unittest.TestCase):
    def test_slow_motion_still_produces_a_move(self) -> None:
        acc = SubPixelAccumulator(deadband=1)
        acc.update(100.0, 100.0)
        self.assertIsNone(acc.update(100.4, 100.0))
        self.assertEqual(acc.update(101.0, 100.0), (101, 100))

    def test_no_duplicate_moves(self) -> None:
        acc = SubPixelAccumulator(deadband=1)
        acc.update(10.0, 10.0)
        acc.update(10.2, 10.2)
        self.assertIsNone(acc.update(10.4, 10.4))

    def test_diagonal_accumulation(self) -> None:
        acc = SubPixelAccumulator(deadband=1)
        acc.update(0.0, 0.0)
        acc.update(1.4, 1.4)
        self.assertEqual(acc.update(1.6, 1.6), (2, 2))


class TestMonotonicFiltering(unittest.TestCase):
    def test_filter_output_is_never_ahead_of_a_monotonic_input(self) -> None:
        f = OneEuro(min_cutoff=1.4, beta=0.3)
        previous = -math.inf
        for i in range(60):
            out = f.filter(i * 1.0, 1 / 60)
            self.assertGreaterEqual(out + 1e-9, previous)
            previous = out


if __name__ == "__main__":
    unittest.main()
