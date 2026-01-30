"""Input controller that applies mouse/keyboard actions using pynput."""
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
    """Executes input commands using pynput."""

    def __init__(self) -> None:
        self._mouse = None
        self._keyboard = None
        self._mouse_button = None
        self._keyboard_key = None
        if platform.system() != "Windows" and not os.getenv("DISPLAY"):
            return

        try:
            spec = importlib.util.find_spec("pynput")
        except ValueError:
            spec = None

        if spec is None and "pynput" not in sys.modules:  # pragma: no cover
            logging.getLogger(__name__).warning(
                "pynput is unavailable; control commands will be ignored."
            )
            return

        try:
            mouse_module = importlib.import_module("pynput.mouse")
            keyboard_module = importlib.import_module("pynput.keyboard")
            self._mouse = mouse_module.Controller()
            self._keyboard = keyboard_module.Controller()
            self._mouse_button = mouse_module.Button
            self._keyboard_key = keyboard_module.Key
        except Exception:  # pragma: no cover
            logging.getLogger(__name__).warning(
                "Failed to import pynput; control commands will be ignored."
            )
            self._mouse = None
            self._keyboard = None
            self._mouse_button = None
            self._keyboard_key = None

    def execute(self, command: ControlCommand) -> None:
        if self._mouse is None or self._keyboard is None:
            return
        if isinstance(command, MouseMove):
            x, y = self._scale_coordinates(
                command.x, command.y, command.source_width, command.source_height
            )
            try:
                self._mouse.position = (x, y)
            except Exception:
                return
        elif isinstance(command, MouseClick):
            x, y = self._scale_coordinates(
                command.x, command.y, command.source_width, command.source_height
            )
            try:
                self._mouse.position = (x, y)
                button = self._map_mouse_button(command.button)
                if button is None:
                    return
                self._mouse.click(button)
            except Exception:
                return
        elif isinstance(command, KeyPress):
            self._send_keypress(command.key)
        elif isinstance(command, TextInput):
            text = command.text
            if not text:
                return
            try:
                self._keyboard.type(text)
            except Exception:
                return

    def _send_keypress(self, key: str) -> None:
        if self._keyboard is None or self._keyboard_key is None:
            return
        key_value = self._map_key(key)
        if key_value is None:
            return
        try:
            self._keyboard.press(key_value)
            self._keyboard.release(key_value)
        except Exception:
            return

    def _map_key(self, key: str) -> object | None:
        if not key:
            return None
        raw = str(key)
        lowered = raw.lower()
        key_map = {
            "enter": self._keyboard_key.enter,
            "return": self._keyboard_key.enter,
            "backspace": self._keyboard_key.backspace,
            "tab": self._keyboard_key.tab,
            "esc": self._keyboard_key.esc,
            "escape": self._keyboard_key.esc,
            "space": self._keyboard_key.space,
            "left": self._keyboard_key.left,
            "right": self._keyboard_key.right,
            "up": self._keyboard_key.up,
            "down": self._keyboard_key.down,
            "delete": self._keyboard_key.delete,
            "home": self._keyboard_key.home,
            "end": self._keyboard_key.end,
            "pageup": self._keyboard_key.page_up,
            "pagedown": self._keyboard_key.page_down,
            "insert": self._keyboard_key.insert,
        }
        if lowered in key_map:
            return key_map[lowered]
        if len(raw) == 1:
            return raw
        candidate = getattr(self._keyboard_key, lowered, None)
        return candidate

    def _map_mouse_button(self, button: MouseButton) -> object:
        if self._mouse_button is None:
            return None
        if button == "right":
            return self._mouse_button.right
        if button == "middle":
            return self._mouse_button.middle
        return self._mouse_button.left

    def _scale_coordinates(
        self,
        x: int,
        y: int,
        source_width: int | None,
        source_height: int | None,
    ) -> tuple[int, int]:
        if not source_width or not source_height:
            return x, y
        screen_size = self._get_screen_size()
        if not screen_size:
            return x, y
        screen_width, screen_height = screen_size
        if not screen_width or not screen_height:
            return x, y
        scaled_x = int(round(x * screen_width / source_width))
        scaled_y = int(round(y * screen_height / source_height))
        scaled_x = max(0, min(screen_width - 1, scaled_x))
        scaled_y = max(0, min(screen_height - 1, scaled_y))
        return scaled_x, scaled_y

    @staticmethod
    def _get_screen_size() -> tuple[int, int] | None:
        if platform.system() == "Windows":
            try:
                import ctypes

                user32 = ctypes.windll.user32
                return int(user32.GetSystemMetrics(0)), int(user32.GetSystemMetrics(1))
            except Exception:
                return None
        try:
            import tkinter  # standard lib

            root = tkinter.Tk()
            root.withdraw()
            width = root.winfo_screenwidth()
            height = root.winfo_screenheight()
            root.destroy()
            return int(width), int(height)
        except Exception:
            return None


class NullInputController(InputController):
    """No-op controller for view-only sessions."""

    def __init__(self) -> None:
        self._mouse = None
        self._keyboard = None
        self._mouse_button = None
        self._keyboard_key = None

    def execute(self, command: ControlCommand) -> None:
        return