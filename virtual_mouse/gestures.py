"""Gesture state machine: hand landmarks -> mouse intents.

Design rules learned from the naive version:

1. Every threshold is *normalized by hand size*, so a hand close to the camera
   behaves like a hand far away.
2. A pinch fires one atomic click and latches until you open your hand. There is
   no drag mode at all, so holding a pinch can never leave a button down.
3. The fist test is rotation-invariant: it measures how close the four
   fingertips are to the wrist, not whether they are "below" their knuckles on
   screen. A sideways hand still scrolls.
4. Scroll takes priority over clicks from the first closed frame, so making a
   fist never fires a click on the way in.
5. Losing the hand never teleports the pointer, and never leaves a button down
   (there is no held button to leave).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .config import Config
from .filters import Hysteresis

# MediaPipe hand landmark indices
WRIST = 0
THUMB_TIP = 4
INDEX_MCP = 5
INDEX_PIP = 6
INDEX_TIP = 8
MIDDLE_MCP = 9
MIDDLE_PIP = 10
MIDDLE_TIP = 12
RING_PIP = 14
RING_TIP = 16
PINKY_PIP = 18
PINKY_TIP = 20

FIST_RATIO = 1.30  # fingertip-to-wrist distance / hand scale below which a finger is curled


class Gesture(str, Enum):
    IDLE = "idle"
    MOVE = "move"
    PRESS = "press"
    DRAG = "drag"  # kept for compatibility; no longer produced
    SCROLL = "scroll"
    RIGHT = "right"


@dataclass
class HandFrame:
    """21 normalized landmarks as produced by MediaPipe."""

    points: list[tuple[float, float]]
    handedness: str = "unknown"

    def pt(self, index: int) -> tuple[float, float]:
        return self.points[index]

    @property
    def valid(self) -> bool:
        return len(self.points) >= 21

    def scale(self) -> float:
        """Hand size proxy: wrist -> middle knuckle. Never zero."""
        return max(dist(self.pt(WRIST), self.pt(MIDDLE_MCP)), 1e-3)

    def pinch(self) -> float:
        return dist(self.pt(INDEX_TIP), self.pt(THUMB_TIP)) / self.scale()

    def middle_pinch(self) -> float:
        return dist(self.pt(MIDDLE_TIP), self.pt(THUMB_TIP)) / self.scale()

    def curled(self, tip: int) -> float:
        """fingertip -> wrist distance, in hand-size units. Small means curled."""
        return dist(self.pt(tip), self.pt(WRIST)) / self.scale()

    def is_fist(self) -> bool:
        """Rotation-invariant fist: all four fingertips close to the wrist.

        Comparing tip.y with pip.y only works for an upright hand; rotate your
        wrist and the same fist reads as "open". Distance to the wrist does not
        care about orientation, and it degrades gracefully when MediaPipe loses
        a curled fingertip behind the palm.
        """
        return all(self.curled(tip) < FIST_RATIO for tip in (INDEX_TIP, MIDDLE_TIP, RING_TIP, PINKY_TIP))

    def pointer(self) -> tuple[float, float]:
        return self.pt(INDEX_TIP)

    def anchor(self) -> tuple[float, float]:
        """A pinch-invariant anchor.

        The fingertip moves towards the thumb while pinching, so using it as
        the pointer drags the cursor every time you click (~480px on a 1080p
        screen). The knuckle and the first joint do not move during a pinch,
        so they track the hand without the click-induced drift.
        """
        mcp = self.pt(INDEX_MCP)
        pip = self.pt(INDEX_PIP)
        return (0.55 * mcp[0] + 0.45 * pip[0], 0.55 * mcp[1] + 0.45 * pip[1])


def dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


@dataclass
class Intent:
    """What the app should do this frame."""

    pointer: tuple[float, float] | None = None
    actions: list[tuple[str, Any]] = field(default_factory=list)
    gesture: Gesture = Gesture.IDLE
    pinch: float = 1.0
    scrolling: bool = False
    hand_lost: bool = False


class HandCoaster:
    """Reuse the last landmarks through a short detection dropout.

    MediaPipe loses the hand for a few frames at a time on ordinary webcams --
    measured at 37% detection in some two-second windows. Treating each miss as
    "hand gone" froze the pointer and forced a re-acquire blend, which read as
    "half my movements do nothing". Coasting keeps the last pose alive for a
    quarter of a second so a dropped frame costs nothing; anything longer is a
    real loss and is reported as such.
    """

    def __init__(self, hold_ms: float = 250.0) -> None:
        self.hold_ms = hold_ms
        self.last: HandFrame | None = None
        self.last_at: float | None = None
        self.coasted = 0

    def reset(self) -> None:
        self.last = None
        self.last_at = None

    def update(self, hand: HandFrame | None, now_ms: float) -> tuple[HandFrame | None, bool]:
        if hand is not None and hand.valid:
            self.last = hand
            self.last_at = now_ms
            return hand, False

        if self.last is not None and self.last_at is not None:
            if now_ms - self.last_at <= self.hold_ms:
                self.coasted += 1
                return self.last, True

        # a real loss: forget the pose so the next detection starts clean
        self.last = None
        self.last_at = None
        return None, False


class GestureEngine:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.left = Hysteresis(config.pinch_press, config.pinch_release)
        self.right = Hysteresis(config.right_pinch_press, config.right_pinch_release)

        self.left_latched = False
        self.right_latched = False
        self.right_cooldown_until = 0.0
        self.guard_until = 0.0
        self.left_stable = 0
        self.right_stable = 0

        self.fist_frames = 0
        self.open_frames = 0
        self.scrolling = False
        self.last_wrist_y: float | None = None
        self.scroll_pending = 0.0
        self.scroll_velocity = 0.0

        self.last_seen_ms: float | None = None
        self.lost = True
        self.gesture = Gesture.IDLE

    # ------------------------------------------------------------------
    def reset(self) -> None:
        self.left.reset()
        self.right.reset()
        self.left_latched = False
        self.right_latched = False
        self.fist_frames = 0
        self.open_frames = 0
        self.scrolling = False
        self.last_wrist_y = None
        self.scroll_pending = 0.0
        self.scroll_velocity = 0.0
        self.left_stable = 0
        self.right_stable = 0
        self.gesture = Gesture.IDLE

    # ------------------------------------------------------------------
    def update(self, hand: HandFrame | None, now_ms: float) -> Intent:
        intent = Intent()

        if hand is None or not hand.valid:
            return self._on_lost(now_ms, intent)

        if self.lost:
            # Re-acquired: don't fire anything until the pinch is clearly open.
            self.lost = False
            self.scroll_pending = 0.0
        self.last_seen_ms = now_ms

        pinch = hand.pinch()
        intent.pinch = pinch

        fist = hand.is_fist()
        self._update_fist(fist, now_ms)

        # --- scroll owns the hand ---------------------------------------
        if self.scrolling:
            intent.gesture = Gesture.SCROLL
            intent.scrolling = True
            # The pointer keeps following the hand while scrolling. Freezing it
            # looks tidy, but then the cursor teleports across the screen the
            # moment the fist opens.
            intent.pointer = hand.anchor()
            self._scroll_step(hand, intent)
            return intent

        # A closing hand is a scroll candidate, never a click: without this the
        # first frames of making a fist fire a click before scroll exists.
        if self.fist_frames > 0:
            intent.gesture = Gesture.SCROLL
            intent.scrolling = True
            intent.pointer = hand.anchor()
            return intent

        # momentum after the fist opens
        self._scroll_momentum(intent)

        # --- clicks ------------------------------------------------------
        self.left.update(pinch)
        self.right.update(hand.middle_pinch())

        self.left_stable = self.left_stable + 1 if self.left.active else 0
        self.right_stable = self.right_stable + 1 if self.right.active else 0

        # A latch clears as soon as the pinch opens, so one pinch = one click
        # no matter how long you hold it.
        if not self.left.active:
            self.left_latched = False
        if not self.right.active:
            self.right_latched = False

        pointer = hand.anchor()
        intent.pointer = pointer

        can_click = now_ms >= self.guard_until

        # Right click first: only when the *middle* finger is the one pinching,
        # which is unambiguous because the index stays extended.
        if (
            self.right.active
            and not self.right_latched
            and pinch > self.config.pinch_press
            and self.right_stable >= self.config.stable_frames
            and now_ms >= self.right_cooldown_until
        ):
            self.right_latched = True
            self.right_cooldown_until = now_ms + self.config.right_click_cooldown_ms
            intent.actions.append(("click", "right"))
            intent.gesture = Gesture.RIGHT
            return intent

        if (
            self.left.active
            and not self.left_latched
            and self.left_stable >= self.config.stable_frames
            and can_click
        ):
            self.left_latched = True
            self.guard_until = now_ms + self.config.click_guard_ms
            intent.actions.append(("click", "left"))
            intent.gesture = Gesture.PRESS
            return intent

        intent.gesture = Gesture.PRESS if self.left.active else Gesture.MOVE
        return intent

    # ------------------------------------------------------------------
    def _on_lost(self, now_ms: float, intent: Intent) -> Intent:
        intent.hand_lost = True
        intent.gesture = Gesture.IDLE

        if self.last_seen_ms is not None and now_ms - self.last_seen_ms < self.config.lost_after_ms:
            return intent  # brief dropout: hold everything, do not twitch

        self.lost = True
        self.left_latched = False
        self.right_latched = False
        self.scrolling = False
        self.scroll_velocity = 0.0
        self.scroll_pending = 0.0
        return intent

    def _update_fist(self, fist: bool, now_ms: float) -> None:
        if fist:
            self.fist_frames += 1
            self.open_frames = 0
        else:
            self.open_frames += 1
            self.fist_frames = 0

        if not self.scrolling and self.fist_frames >= self.config.fist_enter_frames:
            self.scrolling = True
            self.last_wrist_y = None
            self.scroll_pending = 0.0

        if self.scrolling and self.open_frames >= self.config.fist_exit_frames:
            self.scrolling = False
            self.last_wrist_y = None
            self.scroll_velocity = self.scroll_pending * 0.5
            self.scroll_pending = 0.0
            # leaving scroll must not fall straight into a click
            self.guard_until = max(self.guard_until, now_ms + self.config.click_guard_ms)

    def _scroll_step(self, hand: HandFrame, intent: Intent) -> None:
        wrist_y = hand.pt(WRIST)[1]
        if self.last_wrist_y is None:
            self.last_wrist_y = wrist_y
            return

        dy = wrist_y - self.last_wrist_y
        self.last_wrist_y = wrist_y

        if abs(dy) < self.config.scroll_deadband:
            return

        # Moving the hand up (smaller y) scrolls up: positive pyautogui notches.
        self.scroll_pending += -dy * self.config.scroll_gain
        steps = int(self.scroll_pending)
        if steps == 0:
            return
        steps = max(-self.config.scroll_max_step, min(self.config.scroll_max_step, steps))
        self.scroll_pending -= steps
        if steps:
            intent.actions.append(("scroll", steps))

    def _scroll_momentum(self, intent: Intent) -> None:
        if abs(self.scroll_velocity) < 0.25:
            self.scroll_velocity = 0.0
            return
        self.scroll_velocity *= self.config.scroll_momentum
        step = int(round(self.scroll_velocity))
        if step:
            step = max(-self.config.scroll_max_step, min(self.config.scroll_max_step, step))
            intent.actions.append(("scroll", step))
