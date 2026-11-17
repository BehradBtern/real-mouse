"""Filters that make a hand-tracked pointer behave like a mouse.

The original script used `curr = prev + (target - prev) / 5`, which is a fixed
exponential filter: it lags badly on fast flicks and does not remove jitter when
the hand is nearly still. The One-Euro filter fixes both by raising its cutoff
with speed, and a deadband removes the last of the sensor tremor.
"""

from __future__ import annotations

import math

EPS = 1e-9


def _alpha(cutoff: float, dt: float) -> float:
    tau = 1.0 / (2.0 * math.pi * max(cutoff, EPS))
    return 1.0 / (1.0 + tau / max(dt, EPS))


class LowPass:
    """Plain exponential smoother (kept for tests and simple uses)."""

    def __init__(self, cutoff: float = 1.0) -> None:
        self.cutoff = cutoff
        self.value: float | None = None

    def reset(self, value: float | None = None) -> None:
        self.value = value

    def filter(self, x: float, dt: float) -> float:
        if self.value is None:
            self.value = x
            return x
        a = _alpha(self.cutoff, dt)
        self.value += a * (x - self.value)
        return self.value


class OneEuro:
    """One-Euro filter: low lag at speed, strong smoothing at rest.

    Reference: Casiez, Roussel & Vogel (CHI 2012). The speed term `beta`
    is what makes fast hand movement feel direct instead of rubbery.
    """

    def __init__(
        self,
        min_cutoff: float = 1.0,
        beta: float = 0.35,
        d_cutoff: float = 1.0,
    ) -> None:
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self.x_prev: float | None = None
        self.dx_prev = 0.0

    def reset(self, value: float | None = None) -> None:
        self.x_prev = value
        self.dx_prev = 0.0

    def filter(self, x: float, dt: float) -> float:
        dt = max(dt, EPS)
        if self.x_prev is None:
            self.x_prev = x
            return x

        dx = (x - self.x_prev) / dt
        a_d = _alpha(self.d_cutoff, dt)
        self.dx_prev += a_d * (dx - self.dx_prev)

        cutoff = self.min_cutoff + self.beta * abs(self.dx_prev)
        a = _alpha(cutoff, dt)
        self.x_prev += a * (x - self.x_prev)
        return self.x_prev


class OneEuro2D:
    """Two independent One-Euro filters sharing one time step."""

    def __init__(self, min_cutoff: float = 1.0, beta: float = 0.35, d_cutoff: float = 1.0) -> None:
        self.fx = OneEuro(min_cutoff, beta, d_cutoff)
        self.fy = OneEuro(min_cutoff, beta, d_cutoff)
        self.last: tuple[float, float] | None = None

    def reset(self, value: tuple[float, float] | None = None) -> None:
        if value is None:
            self.fx.reset()
            self.fy.reset()
            self.last = None
            return
        self.fx.reset(value[0])
        self.fy.reset(value[1])
        self.last = value

    def filter(self, x: float, y: float, dt: float) -> tuple[float, float]:
        out = (self.fx.filter(x, dt), self.fy.filter(y, dt))
        self.last = out
        return out

    @property
    def velocity(self) -> float:
        return math.hypot(self.fx.dx_prev, self.fy.dx_prev)


class Hysteresis:
    """Schmitt trigger: a gesture must cross `on` to start and `off` to stop.

    This is what stops a pinch from flickering into five clicks when the
    thumb hovers exactly at the threshold.
    """

    def __init__(self, on: float, off: float, invert: bool = False) -> None:
        if off <= on and not invert:
            raise ValueError("release threshold must be greater than press threshold")
        self.on = on
        self.off = off
        self.invert = invert
        self.active = False

    def update(self, value: float) -> bool:
        if self.invert:
            # "greater than on" starts the gesture (used for open-hand tests)
            if not self.active and value >= self.on:
                self.active = True
            elif self.active and value <= self.off:
                self.active = False
        else:
            if not self.active and value <= self.on:
                self.active = True
            elif self.active and value >= self.off:
                self.active = False
        return self.active

    def reset(self) -> None:
        self.active = False


class Deadband:
    """Ignore movements smaller than `threshold` pixels, pass the rest intact."""

    def __init__(self, threshold: float = 0.4) -> None:
        self.threshold = threshold
        self.last: tuple[float, float] | None = None

    def reset(self, value: tuple[float, float] | None = None) -> None:
        self.last = value

    def apply(self, x: float, y: float) -> tuple[float, float]:
        if self.last is None:
            self.last = (x, y)
            return x, y
        lx, ly = self.last
        if math.hypot(x - lx, y - ly) < self.threshold:
            return lx, ly
        self.last = (x, y)
        return x, y


class SubPixelAccumulator:
    """Turn float pointer positions into integer moves without losing motion.

    A slow hand still moves the cursor: fractional pixels accumulate until they
    add up to a whole one. Without this, slow movements either stutter or stick.
    """

    def __init__(self, deadband: int = 1) -> None:
        self.deadband = max(0, deadband)
        self.x: float | None = None
        self.y: float | None = None
        self.emitted: tuple[int, int] | None = None

    def reset(self, x: float | None = None, y: float | None = None) -> None:
        self.x = x
        self.y = y
        self.emitted = None

    def update(self, x: float, y: float) -> tuple[int, int] | None:
        self.x = x
        self.y = y
        ix, iy = int(round(x)), int(round(y))
        if self.emitted is None:
            self.emitted = (ix, iy)
            return self.emitted
        ex, ey = self.emitted
        if abs(ix - ex) >= self.deadband or abs(iy - ey) >= self.deadband:
            self.emitted = (ix, iy)
            return self.emitted
        return None
