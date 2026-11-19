"""Shared helpers for the tests: synthetic hands, deterministic time."""

from __future__ import annotations

import math
import random

from virtual_mouse.gestures import HandFrame

FRAME_MS = 1000.0 / 60.0
SCALE = 0.28  # wrist -> middle knuckle, in normalized units


def make_hand(
    pinch: float = 1.0,
    middle_pinch: float = 1.0,
    fist: bool = False,
    x: float = 0.5,
    y: float = 0.5,
) -> HandFrame:
    """Build a 21-point hand with a controlled normalized pinch ratio.

    `hand_scale` is the wrist -> middle-knuckle distance, fixed at SCALE here,
    so a pinch ratio of r means the index tip is exactly r * SCALE away from the
    thumb tip. Extending a finger puts its tip ~2 SCALE from the wrist, which is
    what the rotation-invariant fist test looks at.
    """
    points = [(x, y)] * 21

    wrist = (x, y + SCALE)
    points[0] = wrist
    points[9] = (x, y)                      # middle knuckle -> hand scale anchor
    points[4] = (x, y - 0.12)               # thumb tip
    points[8] = (x + pinch * SCALE, y - 0.12)   # index tip
    points[12] = (x + middle_pinch * SCALE, y - 0.105)

    if fist:
        # every fingertip curled back towards the wrist
        for tip_idx, pip_idx, dy in (
            (8, 6, 0.02),
            (12, 10, 0.03),
            (16, 14, 0.04),
            (20, 18, 0.05),
        ):
            points[pip_idx] = (x + 0.02, y - 0.02)
            points[tip_idx] = (x + 0.02, y + dy)
    else:
        # extended fingers: tips roughly 2x hand-scale away from the wrist
        for tip_idx, pip_idx in ((16, 14), (20, 18)):
            points[pip_idx] = (x + 0.02, y - 0.05)
            points[tip_idx] = (x + 0.02, y - 0.32)
        # keep the deliberately positioned index/middle tips for pinch maths
        points[8] = (x + pinch * SCALE, y - 0.12)
        points[12] = (x + middle_pinch * SCALE, y - 0.105)

    return HandFrame(points=points)


def rotate(hand: HandFrame, degrees: float, origin: tuple[float, float] | None = None) -> HandFrame:
    """Rotate every landmark around the wrist. Used to prove the fist test is
    orientation-independent."""
    ox, oy = origin if origin is not None else hand.points[0]
    angle = math.radians(degrees)
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    moved = []
    for px, py in hand.points:
        dx, dy = px - ox, py - oy
        moved.append((ox + dx * cos_a - dy * sin_a, oy + dx * sin_a + dy * cos_a))
    return HandFrame(points=moved, handedness=hand.handedness)


def noisy_circle(frames: int, radius: float = 0.22, sigma: float = 0.004, seed: int = 7):
    """A hand tracing a circle with sensor-level noise."""
    random.seed(seed)
    out = []
    for i in range(frames):
        angle = 2 * math.pi * i / frames
        x = 0.5 + radius * math.cos(angle) + random.gauss(0, sigma)
        y = 0.5 + radius * math.sin(angle) + random.gauss(0, sigma)
        out.append((x, y))
    return out
