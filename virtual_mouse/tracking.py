"""Camera + MediaPipe wrapper.

Heavy imports (`cv2`, `mediapipe`) are confined to this module so the rest of
the project can be imported, unit-tested and simulated on a machine with no
camera and no GUI stack.

Camera switching is lazy: the first time you press `c` the tracker releases the
current device, probes the available indices once, caches them, and reopens on
the next one. Probing up front would add seconds to every start-up.
"""

from __future__ import annotations

import inspect
import sys
import time
from typing import Any

from .cameras import next_camera
from .config import Config
from .gestures import HandFrame

MAX_PROBED_INDEX = 4


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

        self.hands = self._make_hands(config)

        self._backend = self.cv2.CAP_DSHOW if sys.platform.startswith("win") else 0
        self.capture: Any | None = None
        self.index = config.camera_index
        self.available: list[int] = []
        self.notice: tuple[str, float] | None = None

        if not self.open_camera(self.index):
            # The requested index may not exist; look for any working camera
            # before giving up, so a laptop with an external camera still runs.
            found = self.detect_cameras()
            if not found or not self.open_camera(found[0]):
                raise TrackerUnavailable(
                    f"No camera could be opened (tried index {self.index}"
                    + (f" and detected {found}" if found else "")
                    + "). Close other apps using the webcam and try again."
                )

    # ------------------------------------------------------------------
    def _make_hands(self, config: Config):
        """Build the MediaPipe Hands graph with only the keywords this build supports.

        `smooth_landmarks` exists in some mediapipe releases and not others;
        passing it blindly crashed the app on 0.10.21. Feature-detect instead.
        """
        kwargs = {
            "static_image_mode": False,
            "max_num_hands": config.max_num_hands,
            "model_complexity": config.model_complexity,
            "min_detection_confidence": config.min_detection_confidence,
            "min_tracking_confidence": config.min_tracking_confidence,
        }
        try:
            supported = inspect.signature(self.mp_hands.Hands).parameters
        except (TypeError, ValueError):  # pragma: no cover - exotic wrappers
            supported = {}
        if config.smooth_landmarks and "smooth_landmarks" in supported:
            kwargs["smooth_landmarks"] = True
        return self.mp_hands.Hands(**kwargs)

    def open_camera(self, index: int) -> bool:
        """Open `index`, replacing any current device. Never raises."""
        self.release_camera()
        try:
            capture = self.cv2.VideoCapture(index, self._backend)
        except Exception:
            return False

        if not capture.isOpened():
            capture.release()
            return False

        capture.set(self.cv2.CAP_PROP_FRAME_WIDTH, self.config.frame_width)
        capture.set(self.cv2.CAP_PROP_FRAME_HEIGHT, self.config.frame_height)
        capture.set(self.cv2.CAP_PROP_FPS, self.config.target_fps)
        capture.set(self.cv2.CAP_PROP_BUFFERSIZE, 1)

        # A device that opens but delivers no frame is not a usable camera.
        ok, frame = capture.read()
        if not ok or frame is None:
            capture.release()
            return False

        self.capture = capture
        self.index = index
        self.config = self.config.with_overrides(camera_index=index)
        return True

    def release_camera(self) -> None:
        if self.capture is not None:
            try:
                self.capture.release()
            finally:
                self.capture = None

    # ------------------------------------------------------------------
    def detect_cameras(self, max_index: int = MAX_PROBED_INDEX) -> list[int]:
        """Probe indices once and cache the ones that actually deliver frames."""
        found: list[int] = []
        for index in range(max_index + 1):
            try:
                capture = self.cv2.VideoCapture(index, self._backend)
                if capture.isOpened():
                    ok, frame = capture.read()
                    if ok and frame is not None:
                        found.append(index)
                capture.release()
            except Exception:
                continue
        self.available = found
        return found

    def cycle_camera(self) -> int | None:
        """Switch to the next working camera. Returns the new index or None."""
        if not self.available:
            # Probing needs exclusive access, so let go of the current device.
            current = self.index
            self.release_camera()
            self.detect_cameras()
            if current not in self.available:
                # fall back to the camera we had, if it still works
                if self.open_camera(current):
                    self.notice = (f"only camera {current} found", time.perf_counter())
                    return None

        target = next_camera(self.index, self.available)
        if target is None:
            self.notice = ("no cameras detected", time.perf_counter())
            if self.capture is None:
                self.open_camera(self.index)
            return None
        if target == self.index:
            self.notice = (f"only camera {self.index} available", time.perf_counter())
            return None

        if self.open_camera(target):
            self.notice = (f"camera {target}", time.perf_counter())
            return target

        # The next index is busy or gone: drop it from the cache and retry once.
        self.available = [i for i in self.available if i != target]
        if not self.open_camera(self.index):
            self.open_camera(self.available[0] if self.available else 0)
        self.notice = (f"camera {target} unavailable", time.perf_counter())
        return None

    def active_notice(self, ttl: float = 1.6) -> str | None:
        if not self.notice:
            return None
        text, at = self.notice
        if time.perf_counter() - at > ttl:
            self.notice = None
            return None
        return text

    # ------------------------------------------------------------------
    def read(self) -> tuple[Any, HandFrame | None, Any | None]:
        """Return (frame, hand, raw landmarks) for one frame."""
        cv2 = self.cv2
        if self.capture is None:
            return None, None, None

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
        self.release_camera()
        try:
            self.hands.close()
        except Exception:  # pragma: no cover - best effort
            pass
