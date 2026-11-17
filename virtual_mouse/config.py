"""Tunable configuration for the virtual mouse.

Every constant that changes how the pointer *feels* lives here, so the whole
feel can be adjusted in one place (or from the command line) without touching
the control logic.
"""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Config:
    # ---- camera / vision -------------------------------------------------
    camera_index: int = 0
    frame_width: int = 640
    frame_height: int = 480
    inference_width: int = 640          # frames are downscaled to this before MediaPipe
    max_num_hands: int = 1
    model_complexity: int = 0           # 0 = lite (fast), 1 = full (precise)
    min_detection_confidence: float = 0.7
    min_tracking_confidence: float = 0.7
    mirror: bool = True
    target_fps: int = 60

    # ---- active region ---------------------------------------------------
    # Hand positions are read inside this box (fractions of the frame) so you
    # never have to reach the edge of the camera image.
    region_left: float = 0.18
    region_right: float = 0.82
    region_top: float = 0.16
    region_bottom: float = 0.84
    edge_gamma: float = 0.82            # <1 = more gain near the edges
    edge_gain: bool = True

    # ---- smoothing -------------------------------------------------------
    min_cutoff: float = 1.0             # One-Euro base frequency (Hz)
    beta: float = 0.35                  # 0..1 responsiveness dial (speed term)
    d_cutoff: float = 1.0
    deadband_px: float = 0.40           # ignore sub-pixel tremor
    reacquire_frames: int = 6           # soft re-acquire instead of a teleport
    lost_after_ms: float = 320.0

    # ---- gestures --------------------------------------------------------
    pinch_press: float = 0.38           # normalized index-thumb distance
    pinch_release: float = 0.56
    right_pinch_press: float = 0.32
    right_pinch_release: float = 0.48
    stable_frames: int = 2              # frames a pinch must hold before it counts
    right_click_cooldown_ms: float = 350.0
    drag_hold_ms: float = 0.0           # 0 = press stays until released
    click_guard_ms: float = 120.0       # ignore new gestures right after a release

    # ---- scroll ----------------------------------------------------------
    fist_enter_frames: int = 3
    fist_exit_frames: int = 2
    scroll_deadband: float = 0.004      # normalized wrist movement ignored
    scroll_gain: float = 46.0           # notches per frame-height of wrist travel
    scroll_momentum: float = 0.86
    scroll_max_step: int = 4

    # ---- pointer ---------------------------------------------------------
    mode: str = "absolute"              # "absolute" | "relative"
    relative_gain: float = 2.2
    invert_y: bool = False
    move_deadband: int = 1              # emit a move only when the integer pixel changes

    # ---- runtime ---------------------------------------------------------
    show_preview: bool = True
    draw_landmarks: bool = True
    dry_run: bool = False               # never touch the real pointer (tests/demo)
    failsafe: bool = True

    def with_overrides(self, **kwargs) -> "Config":
        clean = {k: v for k, v in kwargs.items() if v is not None}
        return replace(self, **clean)

    @property
    def region(self) -> tuple[float, float, float, float]:
        return (self.region_left, self.region_right, self.region_top, self.region_bottom)
