"""On-camera heads-up display.

The overlay is how you *see* what the engine believes: the active box, the
current gesture, the pinch value and where the pointer actually is. Without it,
tuning the feel is guesswork.
"""

from __future__ import annotations

from typing import Any

from .config import Config
from .gestures import Gesture, Intent

INK = (28, 24, 20)
PAPER = (240, 236, 228)
MUTED = (150, 144, 136)
ACCENT = (28, 70, 168)
OK = (70, 140, 70)
WARN = (40, 40, 200)


def _rounded(cv2: Any, img, x: int, y: int, w: int, h: int, r: int, color, alpha: float = 0.55):
    overlay = img.copy()
    cv2.rectangle(overlay, (x, y), (x + w, y + h), color, -1)
    cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0, img)


def draw(
    cv2: Any,
    frame,
    config: Config,
    intent: Intent,
    position: tuple[float, float],
    fps: float,
    paused: bool = False,
) -> None:
    height, width = frame.shape[:2]

    # ---- active region -------------------------------------------------
    left = int(config.region_left * width)
    right = int(config.region_right * width)
    top = int(config.region_top * height)
    bottom = int(config.region_bottom * height)
    cv2.rectangle(frame, (left, top), (right, bottom), MUTED, 1)

    # corner ticks, so the box reads as a viewfinder rather than a crop
    tick = 14
    for cx, cy, dx, dy in (
        (left, top, 1, 1),
        (right, top, -1, 1),
        (left, bottom, 1, -1),
        (right, bottom, -1, -1),
    ):
        cv2.line(frame, (cx, cy), (cx + dx * tick, cy), ACCENT, 2)
        cv2.line(frame, (cx, cy), (cx, cy + dy * tick), ACCENT, 2)

    # ---- pointer crosshair ---------------------------------------------
    px_ratio = position[0] / max(1, (frame.shape[1] - 1))
    py_ratio = position[1] / max(1, (frame.shape[0] - 1))
    hand_x = int(left + px_ratio * (right - left))
    hand_y = int(top + py_ratio * (bottom - top))
    colour = OK if intent.gesture in (Gesture.PRESS, Gesture.DRAG) else ACCENT
    if intent.gesture is Gesture.SCROLL:
        colour = WARN
    cv2.circle(frame, (hand_x, hand_y), 9, colour, 2)
    cv2.line(frame, (hand_x - 14, hand_y), (hand_x - 5, hand_y), colour, 1)
    cv2.line(frame, (hand_x + 5, hand_y), (hand_x + 14, hand_y), colour, 1)
    cv2.line(frame, (hand_x, hand_y - 14), (hand_x, hand_y - 5), colour, 1)
    cv2.line(frame, (hand_x, hand_y + 5), (hand_x, hand_y + 14), colour, 1)

    # ---- status panel ---------------------------------------------------
    _rounded(cv2, frame, 10, 10, 250, 92, 8, INK, 0.62)
    cv2.putText(frame, "REAL MOUSE", (22, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.45, PAPER, 1, cv2.LINE_AA)
    cv2.putText(
        frame,
        f"{fps:5.1f} fps   {config.mode[:3]}",
        (22, 52),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.38,
        MUTED,
        1,
        cv2.LINE_AA,
    )

    gesture = "PAUSED" if paused else intent.gesture.value.upper()
    cv2.putText(frame, gesture, (22, 74), cv2.FONT_HERSHEY_SIMPLEX, 0.5, PAPER, 1, cv2.LINE_AA)

    # pinch meter
    meter_x, meter_y, meter_w = 130, 84, 108
    cv2.rectangle(frame, (meter_x, meter_y), (meter_x + meter_w, meter_y + 3), (90, 88, 84), -1)
    level = max(0.0, min(1.0, 1.0 - (intent.pinch / 1.4)))
    cv2.rectangle(
        frame,
        (meter_x, meter_y),
        (meter_x + int(meter_w * level), meter_y + 3),
        OK if intent.gesture in (Gesture.PRESS, Gesture.DRAG) else ACCENT,
        -1,
    )

    # ---- hint line -------------------------------------------------------
    hints = "q quit   r reset   m mirror   p pause   +/- gain   1/2/3 presets"
    cv2.putText(frame, hints, (14, height - 14), cv2.FONT_HERSHEY_SIMPLEX, 0.34, MUTED, 1, cv2.LINE_AA)

    if intent.scrolling:
        cv2.putText(
            frame,
            "SCROLL",
            (width // 2 - 34, 38),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            WARN,
            2,
            cv2.LINE_AA,
        )
