"""Real Mouse — webcam hand tracking that drives the OS pointer like hardware."""

from __future__ import annotations

from .config import Config
from .gestures import Gesture, GestureEngine, HandFrame, Intent
from .mapping import Mapper
from .pipeline import Pipeline

__version__ = "2.0.0"

__all__ = [
    "Config",
    "Gesture",
    "GestureEngine",
    "HandFrame",
    "Intent",
    "Mapper",
    "Pipeline",
    "__version__",
]
