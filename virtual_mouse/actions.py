"""OS pointer actions.

The controller is deliberately thin and testable: it can drive `pyautogui`, or a
recording backend in tests and in the headless simulator. All the interesting
logic (when to press, where to move) stays in the gesture engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from .config import Config
from .filters import SubPixelAccumulator
from .gestures import Intent


class Backend(Protocol):
    def size(self) -> tuple[int, int]: ...
    def move_to(self, x: int, y: int) -> None: ...
    def press(self, button: str = "left") -> None: ...
    def release(self, button: str = "left") -> None: ...
    def click(self, button: str = "left") -> None: ...
    def scroll(self, notches: int) -> None: ...
    def close(self) -> None: ...


class PyAutoGuiBackend:
    """Real pointer control. Imported lazily so tests need no GUI stack."""

    def __init__(self, failsafe: bool = True) -> None:
        import pyautogui  # noqa: PLC0415 - deliberate lazy import

        pyautogui.FAILSAFE = failsafe
        pyautogui.PAUSE = 0
        self._gui = pyautogui

    def size(self) -> tuple[int, int]:
        return self._gui.size()

    def move_to(self, x: int, y: int) -> None:
        self._gui.moveTo(x, y, duration=0)

    def press(self, button: str = "left") -> None:
        self._gui.mouseDown(button=button)

    def release(self, button: str = "left") -> None:
        self._gui.mouseUp(button=button)

    def click(self, button: str = "left") -> None:
        self._gui.click(button=button)

    def scroll(self, notches: int) -> None:
        self._gui.scroll(notches)

    def close(self) -> None:  # pragma: no cover - nothing to release
        return None


@dataclass
class RecordingBackend:
    """Captures every event. Used by the tests and the simulator."""

    width: int = 1920
    height: int = 1080
    events: list[tuple[Any, ...]] = field(default_factory=list)

    def size(self) -> tuple[int, int]:
        return self.width, self.height

    def move_to(self, x: int, y: int) -> None:
        self.events.append(("move", x, y))

    def press(self, button: str = "left") -> None:
        self.events.append(("down", button))

    def release(self, button: str = "left") -> None:
        self.events.append(("up", button))

    def click(self, button: str = "left") -> None:
        self.events.append(("click", button))

    def scroll(self, notches: int) -> None:
        self.events.append(("scroll", notches))

    def close(self) -> None:
        return None

    # -- helpers for assertions -----------------------------------------
    def of_type(self, kind: str) -> list[tuple[Any, ...]]:
        return [e for e in self.events if e[0] == kind]

    def clear(self) -> None:
        self.events.clear()


class MouseController:
    def __init__(self, config: Config, backend: Backend | None = None) -> None:
        self.config = config
        self.backend = backend or (RecordingBackend() if config.dry_run else PyAutoGuiBackend(config.failsafe))
        self.width, self.height = self.backend.size()
        self.accumulator = SubPixelAccumulator(config.move_deadband)
        self.pressed = False
        self.moves = 0
        self.clicks = 0
        self.scroll_notches = 0
        self.last_position: tuple[int, int] | None = None

    # ------------------------------------------------------------------
    def move(self, x: float, y: float) -> tuple[int, int] | None:
        point = self.accumulator.update(x, y)
        if point is None:
            return None
        if point != self.last_position:
            self.backend.move_to(*point)
            self.last_position = point
            self.moves += 1
        return point

    def press(self, button: str = "left") -> None:
        if button == "left":
            if self.pressed:
                return
            self.pressed = True
        self.backend.press(button)

    def release(self, button: str = "left") -> None:
        if button == "left":
            if not self.pressed:
                return
            self.pressed = False
        self.backend.release(button)

    def click(self, button: str = "right") -> None:
        self.backend.click(button)
        self.clicks += 1

    def scroll(self, notches: int) -> None:
        if not notches:
            return
        self.backend.scroll(notches)
        self.scroll_notches += abs(notches)

    # ------------------------------------------------------------------
    def apply(self, intent: Intent) -> None:
        if intent.pointer is not None:
            self.move(*intent.pointer)

        for action, value in intent.actions:
            if action == "down":
                self.press(value)
            elif action == "up":
                self.release(value)
            elif action == "click":
                self.click(value)
            elif action == "scroll":
                self.scroll(int(value))

    def close(self) -> None:
        if self.pressed:
            self.release("left")
        self.backend.close()


class RelativeMapperAdapter:
    """Small adapter so the controller can drive either mapping mode."""

    def __init__(self, mapper) -> None:  # noqa: ANN001 - avoids a circular import
        self.mapper = mapper

    def position(self, u: float, v: float, mode: str) -> tuple[float, float]:
        if mode == "relative":
            return self.mapper.map_relative(u, v)
        return self.mapper.map(u, v)
