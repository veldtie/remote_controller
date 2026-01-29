"""Input controller that applies mouse/keyboard actions."""
from __future__ import annotations

from dataclasses import dataclass
import importlib
import importlib.util
import logging
import os
import platform
import sys
from typing import Literal


MouseButton = Literal["left", "right", "middle"]


@dataclass(frozen=True)
class MouseMove:
    x: int
    y: int
    source_width: int | None = None
    source_height: int | None = None


@dataclass(frozen=True)
class MouseClick:
    x: int
    y: int
    button: MouseButton
    source_width: int | None = None
    source_height: int | None = None


@dataclass(frozen=True)
class KeyPress:
    key: str


@dataclass(frozen=True)
class TextInput:
    text: str


ControlCommand = MouseMove | MouseClick | KeyPress | TextInput


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
            logging.getLogger(__name__).warning(
                "pyautogui is unavailable; control commands will be ignored."
            )
            return

        try:
            self._pyautogui = importlib.import_module("pyautogui")
        except Exception:  # pragma: no cover
            logging.getLogger(__name__).warning(
                "Failed to import pyautogui; control commands will be ignored."
            )
            self._pyautogui = None

    def execute(self, command: ControlCommand) -> None:
        if self._pyautogui is None:
            return
        if isinstance(command, MouseMove):
            x, y = self._scale_coordinates(
                command.x, command.y, command.source_width, command.source_height
            )
            self._pyautogui.moveTo(x, y)
        elif isinstance(command, MouseClick):
            x, y = self._scale_coordinates(
                command.x, command.y, command.source_width, command.source_height
            )
            self._pyautogui.click(x, y, button=command.button)
        elif isinstance(command, KeyPress):
            self._pyautogui.press(command.key)
        elif isinstance(command, TextInput):
            text = command.text
            if not text:
                return
            writer = getattr(self._pyautogui, "write", None)
            if writer is None:
                writer = getattr(self._pyautogui, "typewrite", None)
            if writer is None:
                return
            writer(text, interval=0)

    def _scale_coordinates(
        self,
        x: int,
        y: int,
        source_width: int | None,
        source_height: int | None,
    ) -> tuple[int, int]:
        if not source_width or not source_height:
            return x, y
        try:
            screen_width, screen_height = self._pyautogui.size()
        except Exception:
            return x, y
        if not screen_width or not screen_height:
            return x, y
        scaled_x = int(round(x * screen_width / source_width))
        scaled_y = int(round(y * screen_height / source_height))
        scaled_x = max(0, min(screen_width - 1, scaled_x))
        scaled_y = max(0, min(screen_height - 1, scaled_y))
        return scaled_x, scaled_y


class NullInputController(InputController):
    """No-op controller for view-only sessions."""

    def __init__(self) -> None:
        self._pyautogui = None

    def execute(self, command: ControlCommand) -> None:
        return
