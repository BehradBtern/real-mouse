"""Camera selection helpers (pure — no OpenCV import, so they are testable).

The tracker owns the hardware; this module only decides *which* camera comes
next, so the cycling rule can be unit-tested without a webcam.
"""

from __future__ import annotations


def normalise(indices) -> list[int]:
    """Sorted, de-duplicated, non-negative camera indices."""
    clean = {int(i) for i in indices if int(i) >= 0}
    return sorted(clean)


def next_camera(current: int, available, step: int = 1) -> int | None:
    """Return the next camera index to use.

    * no cameras at all -> None
    * current camera is gone -> the first available one
    * otherwise -> wrap around the sorted list
    """
    ordered = normalise(available)
    if not ordered:
        return None
    if current not in ordered:
        return ordered[0]
    index = ordered.index(current)
    return ordered[(index + step) % len(ordered)]
