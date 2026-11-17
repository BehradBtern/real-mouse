"""Pointer mapping: normalized hand coordinates -> screen pixels.

Two modes, because they feel completely different:

* absolute - the cursor is where your finger points inside an active box.
  Predictable, but every bit of hand tremor becomes cursor tremor.
* relative - the cursor moves by the hand delta times a gain, like a trackpad in
  the air. Much steadier on cheap webcams, and it can reach any corner without
  contorting your arm.

Both keep the cursor inside the screen and never lose sub-pixel motion.
"""

from __future__ import annotations

import math

from .config import Config


def clamp(value: float, low: float, high: float) -> float:
    return low if value < low else high if value > high else value


def shape_edge(t: float, gamma: float) -> float:
    """Symmetric edge-weighted curve.

    gamma < 1 gives extra gain towards the borders (so the far corners are
    reachable) while leaving the centre linear. gamma == 1 is identity.
    """
    t = clamp(t, 0.0, 1.0)
    if abs(gamma - 1.0) < 1e-6:
        return t
    signed = 2.0 * t - 1.0
    magnitude = abs(signed) ** gamma
    return 0.5 + math.copysign(0.5 * magnitude, signed)


class Mapper:
    """Maps a normalized hand position to screen coordinates."""

    def __init__(self, width: int, height: int, config: Config) -> None:
        self.width = max(1, width)
        self.height = max(1, height)
        self.config = config
        self.x = self.width / 2.0
        self.y = self.height / 2.0
        self._initialized = False
        self._last_raw: tuple[float, float] | None = None

    # -- helpers ---------------------------------------------------------
    def _normalize(self, u: float, v: float) -> tuple[float, float]:
        left, right, top, bottom = self.config.region
        nu = clamp((u - left) / max(right - left, 1e-6), 0.0, 1.0)
        nv = clamp((v - top) / max(bottom - top, 1e-6), 0.0, 1.0)
        if self.config.invert_y:
            nv = 1.0 - nv
        if self.config.edge_gain:
            nu = shape_edge(nu, self.config.edge_gamma)
            nv = shape_edge(nv, self.config.edge_gamma)
        return nu, nv

    def _clamp_screen(self, x: float, y: float) -> tuple[float, float]:
        return clamp(x, 0.0, self.width - 1.0), clamp(y, 0.0, self.height - 1.0)

    def reset(self) -> None:
        self.x = self.width / 2.0
        self.y = self.height / 2.0
        self._initialized = False
        self._last_raw = None

    # -- mapping ---------------------------------------------------------
    def map(self, u: float, v: float) -> tuple[float, float]:
        """Absolute mapping: finger position inside the box -> screen position."""
        nu, nv = self._normalize(u, v)
        x = nu * (self.width - 1.0)
        y = nv * (self.height - 1.0)
        self.x, self.y = self._clamp_screen(x, y)
        self._initialized = True
        self._last_raw = (u, v)
        return self.x, self.y

    def map_relative(self, u: float, v: float) -> tuple[float, float]:
        """Relative mapping: hand movement -> cursor movement."""
        if not self._initialized or self._last_raw is None:
            self._last_raw = (u, v)
            self._initialized = True
            return self.x, self.y

        du = u - self._last_raw[0]
        dv = v - self._last_raw[1]
        self._last_raw = (u, v)

        left, right, top, bottom = self.config.region
        # Normalize the delta by the active box so gain is resolution independent.
        du /= max(right - left, 1e-6)
        dv /= max(bottom - top, 1e-6)
        if self.config.invert_y:
            dv = -dv

        gain = self.config.relative_gain
        x = self.x + du * gain * self.width
        y = self.y + dv * gain * self.height
        self.x, self.y = self._clamp_screen(x, y)
        return self.x, self.y
