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


MouseButton = Literal["left", "right", "middle", "x1", "x2"]


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
class MouseScroll:
    x: int
    y: int
    delta_x: int
    delta_y: int
    source_width: int | None = None
    source_height: int | None = None


@dataclass(frozen=True)
class KeyPress:
    key: str


@dataclass(frozen=True)
class TextInput:
    text: str


ControlCommand = MouseMove | MouseClick | MouseScroll | KeyPress | TextInput


class _SendInputFallback:
    def __init__(self) -> None:
        import ctypes

        self._ctypes = ctypes
        self._user32 = ctypes.windll.user32
        self._ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong

        class MOUSEINPUT(ctypes.Structure):
            _fields_ = [
                ("dx", ctypes.c_long),
                ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", self._ULONG_PTR),
            ]

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ("wVk", ctypes.c_ushort),
                ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", self._ULONG_PTR),
            ]

        class _INPUT_UNION(ctypes.Union):
            _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]

        class INPUT(ctypes.Structure):
            _fields_ = [("type", ctypes.c_ulong), ("ii", _INPUT_UNION)]

        self._INPUT = INPUT
        self._INPUT_UNION = _INPUT_UNION
        self._MOUSEINPUT = MOUSEINPUT
        self._KEYBDINPUT = KEYBDINPUT

        self.INPUT_MOUSE = 0
        self.INPUT_KEYBOARD = 1
        self.MOUSEEVENTF_MOVE = 0x0001
        self.MOUSEEVENTF_ABSOLUTE = 0x8000
        self.MOUSEEVENTF_LEFTDOWN = 0x0002
        self.MOUSEEVENTF_LEFTUP = 0x0004
        self.MOUSEEVENTF_RIGHTDOWN = 0x0008
        self.MOUSEEVENTF_RIGHTUP = 0x0010
        self.MOUSEEVENTF_MIDDLEDOWN = 0x0020
        self.MOUSEEVENTF_MIDDLEUP = 0x0040
        self.MOUSEEVENTF_XDOWN = 0x0080
        self.MOUSEEVENTF_XUP = 0x0100
        self.MOUSEEVENTF_WHEEL = 0x0800
        self.MOUSEEVENTF_HWHEEL = 0x01000
        self.KEYEVENTF_KEYUP = 0x0002
        self.KEYEVENTF_UNICODE = 0x0004
        self.WHEEL_DELTA = 120

        self._vk_map = {
            "enter": 0x0D,
            "return": 0x0D,
            "backspace": 0x08,
            "tab": 0x09,
            "esc": 0x1B,
            "escape": 0x1B,
            "space": 0x20,
            "left": 0x25,
            "up": 0x26,
            "right": 0x27,
            "down": 0x28,
            "delete": 0x2E,
            "home": 0x24,
            "end": 0x23,
            "pageup": 0x21,
            "pagedown": 0x22,
            "insert": 0x2D,
        }
        for i in range(1, 13):
            self._vk_map[f"f{i}"] = 0x6F + i

    def _send(self, inputs: list) -> None:
        if not inputs:
            return
        arr = (self._INPUT * len(inputs))(*inputs)
        self._user32.SendInput(len(inputs), arr, self._ctypes.sizeof(self._INPUT))

    def _mouse_input(self, dx: int, dy: int, data: int, flags: int):
        mi = self._MOUSEINPUT(dx=dx, dy=dy, mouseData=data, dwFlags=flags, time=0, dwExtraInfo=0)
        return self._INPUT(type=self.INPUT_MOUSE, ii=self._INPUT_UNION(mi=mi))

    def _keyboard_input(self, vk: int, scan: int, flags: int):
        ki = self._KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=0)
        return self._INPUT(type=self.INPUT_KEYBOARD, ii=self._INPUT_UNION(ki=ki))

    def _abs_coord(self, value: int, max_value: int) -> int:
        if max_value <= 1:
            return 0
        return int(value * 65535 / (max_value - 1))

    def move(self, x: int, y: int, screen_width: int, screen_height: int) -> None:
        dx = self._abs_coord(x, screen_width)
        dy = self._abs_coord(y, screen_height)
        self._send([self._mouse_input(dx, dy, 0, self.MOUSEEVENTF_MOVE | self.MOUSEEVENTF_ABSOLUTE)])

    def click(self, button: str, screen_width: int, screen_height: int, x: int, y: int) -> None:
        self.move(x, y, screen_width, screen_height)
        if button == "right":
            down, up, data = self.MOUSEEVENTF_RIGHTDOWN, self.MOUSEEVENTF_RIGHTUP, 0
        elif button == "middle":
            down, up, data = self.MOUSEEVENTF_MIDDLEDOWN, self.MOUSEEVENTF_MIDDLEUP, 0
        elif button == "x1":
            down, up, data = self.MOUSEEVENTF_XDOWN, self.MOUSEEVENTF_XUP, 1
        elif button == "x2":
            down, up, data = self.MOUSEEVENTF_XDOWN, self.MOUSEEVENTF_XUP, 2
        else:
            down, up, data = self.MOUSEEVENTF_LEFTDOWN, self.MOUSEEVENTF_LEFTUP, 0
        self._send(
            [
                self._mouse_input(0, 0, data, down),
                self._mouse_input(0, 0, data, up),
            ]
        )

    def scroll(
        self,
        delta_x: int,
        delta_y: int,
        screen_width: int,
        screen_height: int,
        x: int,
        y: int,
    ) -> None:
        self.move(x, y, screen_width, screen_height)
        inputs = []
        if delta_y:
            inputs.append(
                self._mouse_input(0, 0, delta_y * self.WHEEL_DELTA, self.MOUSEEVENTF_WHEEL)
            )
        if delta_x:
            inputs.append(
                self._mouse_input(0, 0, delta_x * self.WHEEL_DELTA, self.MOUSEEVENTF_HWHEEL)
            )
        self._send(inputs)

    def keypress(self, key: str) -> None:
        if not key:
            return
        lowered = key.lower()
        if lowered in self._vk_map:
            vk = self._vk_map[lowered]
            self._send(
                [
                    self._keyboard_input(vk, 0, 0),
                    self._keyboard_input(vk, 0, self.KEYEVENTF_KEYUP),
                ]
            )
            return
        if len(key) == 1:
            self.text(key)

    def text(self, text: str) -> None:
        if not text:
            return
        inputs = []
        for ch in text:
            code = ord(ch)
            inputs.append(self._keyboard_input(0, code, self.KEYEVENTF_UNICODE))
            inputs.append(
                self._keyboard_input(0, code, self.KEYEVENTF_UNICODE | self.KEYEVENTF_KEYUP)
            )
        self._send(inputs)


class InputController:
    """Executes input commands using pynput."""

    def __init__(self) -> None:
        self._mouse = None
        self._keyboard = None
        self._mouse_button = None
        self._keyboard_key = None
        self._fallback = None
        if platform.system() == "Windows":
            try:
                self._fallback = _SendInputFallback()
            except Exception as exc:  # pragma: no cover
                logging.getLogger(__name__).warning(
                    "SendInput fallback unavailable: %s", exc
                )
                self._fallback = None
        if platform.system() != "Windows" and not os.getenv("DISPLAY"):
            return

        try:
            spec = importlib.util.find_spec("pynput")
        except ValueError:
            spec = None

        if spec is None and "pynput" not in sys.modules:  # pragma: no cover
            if self._fallback is not None:
                logging.getLogger(__name__).warning(
                    "pynput is unavailable; falling back to SendInput."
                )
            else:
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
            if self._fallback is None:
                return
            self._execute_fallback(command)
            return
        if self._fallback is not None and platform.system() == "Windows":
            if isinstance(command, (MouseMove, MouseClick, MouseScroll)):
                self._execute_fallback(command)
                return
        if isinstance(command, MouseMove):
            x, y = self._scale_coordinates(
                command.x, command.y, command.source_width, command.source_height
            )
            try:
                self._mouse.position = (x, y)
            except Exception:
                if self._fallback:
                    self._execute_fallback(command)
                return
        elif isinstance(command, MouseClick):
            x, y = self._scale_coordinates(
                command.x, command.y, command.source_width, command.source_height
            )
            try:
                self._mouse.position = (x, y)
                button = self._map_mouse_button(command.button)
                if button is None:
                    raise RuntimeError("Mouse button unavailable")
                self._mouse.click(button)
            except Exception:
                if self._fallback:
                    self._execute_fallback(command)
                return
        elif isinstance(command, MouseScroll):
            x, y = self._scale_coordinates(
                command.x, command.y, command.source_width, command.source_height
            )
            try:
                self._mouse.position = (x, y)
                delta_x = self._normalize_scroll_delta(command.delta_x)
                delta_y = self._normalize_scroll_delta(command.delta_y)
                if delta_x == 0 and delta_y == 0:
                    return
                # pynput: positive dy scrolls up; browser deltaY is usually down.
                self._mouse.scroll(delta_x, -delta_y)
            except Exception:
                if self._fallback:
                    self._execute_fallback(command)
                return
        elif isinstance(command, KeyPress):
            try:
                self._send_keypress(command.key)
            except Exception:
                if self._fallback:
                    self._execute_fallback(command)
        elif isinstance(command, TextInput):
            text = command.text
            if not text:
                return
            try:
                self._keyboard.type(text)
            except Exception:
                if self._fallback:
                    self._execute_fallback(command)
                return

    def _execute_fallback(self, command: ControlCommand) -> None:
        screen_size = self._get_screen_size()
        if not screen_size:
            return
        screen_width, screen_height = screen_size
        if isinstance(command, MouseMove):
            x, y = self._scale_coordinates(
                command.x, command.y, command.source_width, command.source_height
            )
            self._fallback.move(x, y, screen_width, screen_height)
        elif isinstance(command, MouseClick):
            x, y = self._scale_coordinates(
                command.x, command.y, command.source_width, command.source_height
            )
            self._fallback.click(command.button, screen_width, screen_height, x, y)
        elif isinstance(command, MouseScroll):
            x, y = self._scale_coordinates(
                command.x, command.y, command.source_width, command.source_height
            )
            delta_x = self._normalize_scroll_delta(command.delta_x)
            delta_y = self._normalize_scroll_delta(command.delta_y)
            if delta_x or delta_y:
                self._fallback.scroll(delta_x, delta_y, screen_width, screen_height, x, y)
        elif isinstance(command, KeyPress):
            self._fallback.keypress(command.key)
        elif isinstance(command, TextInput):
            if command.text:
                self._fallback.text(command.text)

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
        if button == "x1":
            return getattr(self._mouse_button, "x1", self._mouse_button.left)
        if button == "x2":
            return getattr(self._mouse_button, "x2", self._mouse_button.left)
        return self._mouse_button.left

    @staticmethod
    def _normalize_scroll_delta(value: int | None) -> int:
        if value is None:
            return 0
        try:
            delta = int(value)
        except (TypeError, ValueError):
            return 0
        if delta == 0:
            return 0
        # Convert pixel deltas to notches (~120 px per wheel step).
        step = int(round(delta / 120))
        if step == 0:
            step = 1 if delta > 0 else -1
        return step

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
