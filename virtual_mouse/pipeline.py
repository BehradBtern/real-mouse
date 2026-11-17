"""The pipeline that both the live app and the headless simulator run.

    landmarks -> gesture engine -> mapper -> filter -> deadband -> controller

Keeping this in one place is what makes the feel testable: the exact code that
drives your real pointer is the code the tests exercise.
"""

from __future__ import annotations

import math

from .actions import Backend, MouseController
from .config import Config
from .filters import Deadband, OneEuro2D
from .gestures import Gesture, GestureEngine, HandFrame, Intent
from .mapping import Mapper

MAX_DT = 0.10
MIN_DT = 1.0 / 240.0

# The user-facing `beta` is a 0..1 responsiveness dial. Inside the filter the
# speed term works in screen pixels/second, so it is scaled to the range the
# One-Euro paper uses for pointer tracking (~0.01). Without this the filter
# would open up at the smallest jitter and stop smoothing anything.
BETA_SCALE = 0.03


def make_smoother(config: Config) -> OneEuro2D:
    return OneEuro2D(config.min_cutoff, config.beta * BETA_SCALE, config.d_cutoff)


class Pipeline:
    def __init__(self, config: Config, backend: Backend | None = None) -> None:
        self.config = config
        self.gestures = GestureEngine(config)
        self.mouse = MouseController(config, backend)
        self.mapper = Mapper(self.mouse.width, self.mouse.height, config)
        self.smoother = make_smoother(config)
        self.deadband = Deadband(config.deadband_px)

        self.last_ts_ms: float | None = None
        self.last_position: tuple[float, float] | None = None
        self.was_lost = True
        self.reacquire_left = 0
        self.reacquire_from: tuple[float, float] = (0.0, 0.0)
        self.frames = 0
        self.last_pinch = 1.0

    # ------------------------------------------------------------------
    def reset(self) -> None:
        self.gestures.reset()
        self.smoother.reset()
        self.deadband.reset()
        self.mapper.reset()
        self.last_ts_ms = None
        self.last_position = None
        self.reacquire_left = 0
        self.was_lost = True

    def _dt(self, now_ms: float) -> float:
        if self.last_ts_ms is None:
            self.last_ts_ms = now_ms
            return 1.0 / 60.0
        dt = (now_ms - self.last_ts_ms) / 1000.0
        self.last_ts_ms = now_ms
        return max(MIN_DT, min(MAX_DT, dt))

    # ------------------------------------------------------------------
    def step(self, hand: HandFrame | None, now_ms: float) -> Intent:
        self.frames += 1
        dt = self._dt(now_ms)

        intent = self.gestures.update(hand, now_ms)
        self.last_pinch = intent.pinch

        if intent.hand_lost and self.gestures.lost:
            # Safety: whatever the engine asked for (usually releasing a held
            # button) must still reach the OS before we stop tracking.
            if intent.actions:
                self.mouse.apply(Intent(pointer=None, actions=intent.actions))
            self.was_lost = True
            self.reacquire_left = 0
            self.last_position = None
            self.smoother.reset()
            self.deadband.reset()
            return intent

        if intent.pointer is None:
            # Frames without a pointer can still carry actions (a safety
            # release, or scroll notches from momentum).
            if intent.actions:
                self.mouse.apply(
                    Intent(
                        pointer=None,
                        actions=intent.actions,
                        gesture=intent.gesture,
                        pinch=intent.pinch,
                        scrolling=intent.scrolling,
                        hand_lost=intent.hand_lost,
                    )
                )
            return intent

        u, v = intent.pointer
        if self.config.mode == "relative":
            raw_x, raw_y = self.mapper.map_relative(u, v)
        else:
            raw_x, raw_y = self.mapper.map(u, v)

        smooth_x, smooth_y = self.smoother.filter(raw_x, raw_y, dt)
        smooth_x, smooth_y = self.deadband.apply(smooth_x, smooth_y)

        # Soft re-acquire: never teleport the pointer when the hand comes back.
        if self.was_lost:
            self.was_lost = False
            self.reacquire_left = self.config.reacquire_frames
            self.reacquire_from = self.last_position or (
                self.mouse.width / 2.0,
                self.mouse.height / 2.0,
            )

        if self.reacquire_left > 0:
            steps = max(1, self.config.reacquire_frames)
            t = 1.0 - (self.reacquire_left / steps)
            smooth_x = self.reacquire_from[0] + (smooth_x - self.reacquire_from[0]) * t
            smooth_y = self.reacquire_from[1] + (smooth_y - self.reacquire_from[1]) * t
            self.reacquire_left -= 1

        self.last_position = (smooth_x, smooth_y)
        self.mouse.apply(
            Intent(
                pointer=(smooth_x, smooth_y),
                actions=intent.actions,
                gesture=intent.gesture,
                pinch=intent.pinch,
                scrolling=intent.scrolling,
                hand_lost=False,
            )
        )
        return intent

    # ------------------------------------------------------------------
    def metrics(self) -> dict[str, float | int | str | tuple[int, int]]:
        m = self.mouse
        return {
            "frames": self.frames,
            "moves": m.moves,
            "clicks": m.clicks,
            "scroll_notches": m.scroll_notches,
            "position": m.last_position or (0, 0),
            "gesture": self.gestures.gesture.value,
            "pinch": round(self.last_pinch, 3),
        }


def distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def path_jitter(points: list[tuple[float, float]]) -> float:
    """Mean absolute second difference: a cheap smoothness metric.

    Lower is smoother. Used by the simulator to prove the filter is doing its
    job instead of just asserting that a constant exists.
    """
    if len(points) < 3:
        return 0.0
    total = 0.0
    for i in range(1, len(points) - 1):
        ax = points[i - 1][0] - 2 * points[i][0] + points[i + 1][0]
        ay = points[i - 1][1] - 2 * points[i][1] + points[i + 1][1]
        total += math.hypot(ax, ay)
    return total / (len(points) - 2)


__all__ = ["Pipeline", "Gesture", "distance", "path_jitter"]
