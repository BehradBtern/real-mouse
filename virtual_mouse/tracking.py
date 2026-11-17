"""Camera + MediaPipe wrapper.

Heavy imports (`cv2`, `mediapipe`) are confined to this module so the rest of
the project can be imported, unit-tested and simulated on a machine with no
camera and no GUI stack.
"""

from __future__ import annotations

import sys
from typing import Any

from .config import Config
from .gestures import HandFrame


class TrackerUnavailable(RuntimeError):
    """Raised with an actionable message when the vision stack is missing."""


def _import_stack():
    try:
        import cv2  # noqa: PLC0415
        import mediapipe as mp  # noqa: PLC0415
    except Exception as exc:  # pragma: no cover - import environment specific
        raise TrackerUnavailable(
            "The vision stack is not installed.\n"
            "  python -m pip install -r requirements.txt\n"
            f"  (original error: {exc})"
        ) from exc
    return cv2, mp


class HandTracker:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.cv2, self.mp = _import_stack()
        self.mp_hands = self.mp.solutions.hands
        self.draw_utils = self.mp.solutions.drawing_utils

        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=config.max_num_hands,
            model_complexity=config.model_complexity,
            min_detection_confidence=config.min_detection_confidence,
            min_tracking_confidence=config.min_tracking_confidence,
        )

        cv2 = self.cv2
        backend = cv2.CAP_DSHOW if sys.platform.startswith("win") else 0
        self.capture = cv2.VideoCapture(config.camera_index, backend)
        if not self.capture.isOpened():
            raise TrackerUnavailable(
                f"Camera {config.camera_index} could not be opened. "
                "Close other apps using the webcam (Zoom/Teams/Camera) and try again, "
                "or pass --camera 1."
            )

        self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, config.frame_width)
        self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, config.frame_height)
        self.capture.set(cv2.CAP_PROP_FPS, config.target_fps)
        self.capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    # ------------------------------------------------------------------
    def read(self) -> tuple[Any, HandFrame | None, Any | None]:
        """Return (frame, hand, raw landmarks) for one frame."""
        cv2 = self.cv2
        ok, frame = self.capture.read()
        if not ok or frame is None:
            return None, None, None

        if self.config.mirror:
            frame = cv2.flip(frame, 1)

        # Downscale for inference: MediaPipe is much faster at 640 wide and
        # landmark coordinates are normalized, so nothing is lost.
        height, width = frame.shape[:2]
        scale = min(1.0, self.config.inference_width / max(width, 1))
        if scale < 1.0:
            small = cv2.resize(frame, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_AREA)
        else:
            small = frame

        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        results = self.hands.process(rgb)

        hand: HandFrame | None = None
        raw = None
        if results.multi_hand_landmarks:
            raw = results.multi_hand_landmarks[0]
            points = [(lm.x, lm.y) for lm in raw.landmark]
            handedness = "unknown"
            if results.multi_handedness:
                handedness = results.multi_handedness[0].classification[0].label
            hand = HandFrame(points=points, handedness=handedness)

        return frame, hand, raw

    def annotate(self, frame, raw) -> None:
        if raw is None or not self.config.draw_landmarks:
            return
        self.draw_utils.draw_landmarks(
            frame,
            raw,
            self.mp_hands.HAND_CONNECTIONS,
            self.draw_utils.DrawingSpec(color=(60, 60, 60), thickness=1, circle_radius=2),
            self.draw_utils.DrawingSpec(color=(140, 140, 140), thickness=1),
        )

    def close(self) -> None:
        try:
            self.capture.release()
        finally:
            try:
                self.hands.close()
            except Exception:  # pragma: no cover - best effort
                pass
