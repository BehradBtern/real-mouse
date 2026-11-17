"""End-to-end pipeline: the same code path the live app runs."""

from __future__ import annotations

import unittest

from helpers import FRAME_MS, make_hand, noisy_circle
from virtual_mouse.actions import RecordingBackend
from virtual_mouse.config import Config
from virtual_mouse.mapping import Mapper
from virtual_mouse.pipeline import Pipeline, path_jitter


class TestPipelineSmoothing(unittest.TestCase):
    def test_cursor_is_smoother_than_the_raw_mapping(self) -> None:
        config = Config(dry_run=True)
        backend = RecordingBackend()
        pipeline = Pipeline(config, backend)
        raw_mapper = Mapper(pipeline.mouse.width, pipeline.mouse.height, config)

        raw: list[tuple[float, float]] = []
        cursor: list[tuple[float, float]] = []
        now = 0.0
        for x, y in noisy_circle(180, sigma=0.006):
            now += FRAME_MS
            pipeline.step(make_hand(pinch=1.0, x=x, y=y), now)
            raw.append(raw_mapper.map(x, y))
            cursor.append(pipeline.mouse.last_position or (0.0, 0.0))

        raw_jitter = path_jitter(raw)
        cursor_jitter = path_jitter(cursor)
        self.assertGreater(raw_jitter, 0.0)
        self.assertLess(cursor_jitter, raw_jitter * 0.5)

    def test_deadband_freezes_a_still_hand(self) -> None:
        config = Config(dry_run=True, deadband_px=1.5)
        backend = RecordingBackend()
        pipeline = Pipeline(config, backend)
        now = 0.0
        for _ in range(30):
            now += FRAME_MS
            pipeline.step(make_hand(pinch=1.0, x=0.5, y=0.5), now)
        moves_before = len(backend.of_type("move"))
        for _ in range(30):
            now += FRAME_MS
            pipeline.step(make_hand(pinch=1.0, x=0.5002, y=0.4998), now)
        # the filter may still be settling for a pixel; it must not wander
        self.assertLessEqual(len(backend.of_type("move")) - moves_before, 1)


class TestPipelineClicks(unittest.TestCase):
    def test_three_pinches_produce_three_clicks(self) -> None:
        config = Config(dry_run=True)
        backend = RecordingBackend()
        pipeline = Pipeline(config, backend)
        now = 0.0
        for _ in range(3):
            for _ in range(6):
                now += FRAME_MS
                pipeline.step(make_hand(pinch=0.18), now)
            for _ in range(14):
                now += FRAME_MS
                pipeline.step(make_hand(pinch=1.0), now)

        self.assertEqual(len(backend.of_type("click")), 3)
        # a click is atomic: nothing may be left holding a button down
        self.assertEqual(backend.of_type("down"), [])
        self.assertFalse(pipeline.mouse.pressed)

    def test_hand_loss_never_leaves_the_button_down(self) -> None:
        config = Config(dry_run=True)
        backend = RecordingBackend()
        pipeline = Pipeline(config, backend)
        now = 0.0
        for _ in range(6):
            now += FRAME_MS
            pipeline.step(make_hand(pinch=0.18), now)
        self.assertFalse(pipeline.mouse.pressed)
        pipeline.step(None, now + 900)
        self.assertFalse(pipeline.mouse.pressed)
        self.assertEqual(backend.of_type("up"), [])


class TestReacquire(unittest.TestCase):
    def test_pointer_does_not_teleport_after_a_hand_loss(self) -> None:
        config = Config(dry_run=True, reacquire_frames=8, deadband_px=0.0)
        backend = RecordingBackend()
        pipeline = Pipeline(config, backend)
        now = 0.0
        for _ in range(20):
            now += FRAME_MS
            pipeline.step(make_hand(pinch=1.0, x=0.25, y=0.25), now)

        pipeline.step(None, now + 500)
        now += 520

        jumps: list[float] = []
        previous = pipeline.mouse.last_position
        for _ in range(12):
            now += FRAME_MS
            pipeline.step(make_hand(pinch=1.0, x=0.85, y=0.85), now)
            current = pipeline.mouse.last_position
            if previous and current:
                jumps.append(abs(current[0] - previous[0]))
            previous = current

        self.assertTrue(jumps)
        self.assertLess(max(jumps), pipeline.mouse.width * 0.45)


if __name__ == "__main__":
    unittest.main()
