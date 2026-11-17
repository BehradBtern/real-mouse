"""Shared helpers for the tests: synthetic hands, deterministic time."""

from __future__ import annotations

import math
import random

from virtual_mouse.gestures import HandFrame

FRAME_MS = 1000.0 / 60.0


def make_hand(
    pinch: float = 1.0,
    middle_pinch: float = 1.0,
    fist: bool = False,
    x: float = 0.5,
    y: float = 0.5,
) -> HandFrame:
    """Build a 21-point hand with a controlled normalized pinch ratio.

    `hand_scale` is the wrist -> middle-knuckle distance, fixed at 0.28 here, so
    a pinch ratio of r means the index tip is exactly r * 0.28 away from the
    thumb tip. That makes the threshold tests exact instead of approximate.
    """
    scale = 0.28
    points = [(x, y)] * 21

    wrist = (x, y + scale)
    middle_mcp = (x, y)
    thumb_tip = (x, y)
    index_tip = (x + pinch * scale, y)
    middle_tip = (x + middle_pinch * scale, y + 0.015)

    points[0] = wrist
    points[9] = middle_mcp
    points[4] = thumb_tip
    points[8] = index_tip
    points[12] = middle_tip

    if fist:
        # every fingertip below its own PIP joint -> fist
        for tip_idx, pip_idx, offset in (
            (8, 6, 0.02),
            (12, 10, 0.03),
            (16, 14, 0.04),
            (20, 18, 0.05),
        ):
            points[pip_idx] = (x + 0.02 * (tip_idx % 3), y - 0.02)
            points[tip_idx] = (x + 0.02 * (tip_idx % 3), y + offset)
    else:
        for tip_idx, pip_idx, offset in (
            (8, 6, 0.10),
            (12, 10, 0.11),
            (16, 14, 0.12),
            (20, 18, 0.13),
        ):
            points[pip_idx] = (x + 0.02, y + 0.03)
            points[tip_idx] = (points[pip_idx][0], points[pip_idx][1] - offset)

        # keep the deliberately positioned tips for the gesture maths
        points[8] = index_tip
        points[12] = middle_tip

    return HandFrame(points=points)


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
