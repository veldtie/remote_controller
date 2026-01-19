"""Input controller that applies mouse/keyboard actions."""
from __future__ import annotations

from dataclasses import dataclass
import importlib
import importlib.util
import os
import platform
import sys
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
        self._pyautogui = None
        if platform.system() != "Windows" and not os.getenv("DISPLAY"):
            return

        try:
            spec = importlib.util.find_spec("pyautogui")
        except ValueError:
            spec = None

        if spec is None and "pyautogui" not in sys.modules:  # pragma: no cover
            raise RuntimeError("Missing optional dependency: pyautogui")

        self._pyautogui = importlib.import_module("pyautogui")

    def execute(self, command: ControlCommand) -> None:
        if self._pyautogui is None:
            return
        if isinstance(command, MouseMove):
            self._pyautogui.moveTo(command.x, command.y)
        elif isinstance(command, MouseClick):
            self._pyautogui.click(command.x, command.y, button=command.button)
        elif isinstance(command, KeyPress):
            self._pyautogui.press(command.key)


class NullInputController(InputController):
    """No-op controller for view-only sessions."""

    def __init__(self) -> None:
        self._pyautogui = None

    def execute(self, command: ControlCommand) -> None:
        return
