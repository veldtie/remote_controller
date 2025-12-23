"""Input controller that applies mouse/keyboard actions."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


MouseButton = Literal["left", "right", "middle"]


@dataclass(frozen=True)
class MouseMove:
    x: int
    y: int


@dataclass(frozen=True)
class MouseClick:
    x: int
    y: int
    button: MouseButton


@dataclass(frozen=True)
class KeyPress:
    key: str


ControlCommand = MouseMove | MouseClick | KeyPress


class InputController:
    """Executes input commands using pyautogui."""

    def __init__(self) -> None:
        try:
            import pyautogui
        except ImportError as exc:  # pragma: no cover - optional runtime dependency
            raise RuntimeError("Missing optional dependency: pyautogui") from exc
        self._pyautogui = pyautogui

    def execute(self, command: ControlCommand) -> None:
        if isinstance(command, MouseMove):
            self._pyautogui.moveTo(command.x, command.y)
        elif isinstance(command, MouseClick):
            self._pyautogui.click(command.x, command.y, button=command.button)
        elif isinstance(command, KeyPress):
            self._pyautogui.press(command.key)
