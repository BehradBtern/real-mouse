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
    min_detection_confidence: float = 0.45
    min_tracking_confidence: float = 0.45
    smooth_landmarks: bool = True
    coast_ms: float = 250.0             # reuse the last landmarks through short dropouts
    mirror: bool = True
    target_fps: int = 60

    # ---- active region ---------------------------------------------------
    # Hand positions are read inside this box (fractions of the frame) so you
    # never have to reach the edge of the camera image.
    region_left: float = 0.10
    region_right: float = 0.90
    region_top: float = 0.10
    region_bottom: float = 0.90
    edge_gamma: float = 1.0             # 1.0 = linear, predictable; <1 = faster near the edges
    edge_gain: bool = True

    # ---- smoothing -------------------------------------------------------
    min_cutoff: float = 1.0             # One-Euro base frequency (Hz)
    beta: float = 0.60                  # 0..1 responsiveness dial (speed term)
    d_cutoff: float = 1.0
    deadband_px: float = 0.35           # ignore sub-pixel tremor (bigger = steadier)
    reacquire_frames: int = 3           # soft re-acquire instead of a teleport
    lost_after_ms: float = 500.0

    # ---- gestures --------------------------------------------------------
    pinch_press: float = 0.50           # normalized index-thumb distance
    pinch_release: float = 0.72
    right_pinch_press: float = 0.45
    right_pinch_release: float = 0.65
    stable_frames: int = 1              # frames a pinch must hold before it counts
    right_click_cooldown_ms: float = 350.0
    click_guard_ms: float = 150.0       # ignore a second click right after one fires

    # ---- scroll ----------------------------------------------------------
    fist_enter_frames: int = 2
    fist_exit_frames: int = 2
    # Tilt-to-scroll: once the fist is held, its height relative to where the
    # fist was formed controls direction and speed. Holding still scrolls
    # nothing; raising the hand scrolls up; lowering scrolls down.
    scroll_deadband: float = 0.030      # normalised wrist offset ignored
    scroll_full_deflection: float = 0.12  # offset that reaches full speed
    scroll_rate: float = 9.0            # notches per second at full deflection
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
    debug: bool = False                # print detection / clamp statistics every 2s
    dry_run: bool = False               # never touch the real pointer (tests/demo)
    failsafe: bool = True

    def with_overrides(self, **kwargs) -> "Config":
        clean = {k: v for k, v in kwargs.items() if v is not None}
        return replace(self, **clean)

    @property
    def region(self) -> tuple[float, float, float, float]:
        return (self.region_left, self.region_right, self.region_top, self.region_bottom)
