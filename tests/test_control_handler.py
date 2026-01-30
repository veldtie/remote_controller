import asyncio
import sys
import types

from remote_client.control.handlers import ControlHandler
from remote_client.control.input_controller import InputController
from remote_client.webrtc.client import WebRTCClient


def install_fake_pynput(monkeypatch):
    pynput_module = types.ModuleType("pynput")
    mouse_module = types.ModuleType("pynput.mouse")
    keyboard_module = types.ModuleType("pynput.keyboard")

    class FakeButton:
        left = "left"
        right = "right"
        middle = "middle"

    class FakeMouseController:
        def __init__(self):
            self.moves: list[tuple[int, int]] = []
            self.clicks: list[tuple[int, int, str]] = []
            self._pos = (0, 0)

        @property
        def position(self):
            return self._pos

        @position.setter
        def position(self, value):
            self._pos = value
            self.moves.append(value)

        def click(self, button):
            self.clicks.append((self._pos[0], self._pos[1], button))

    class FakeKey:
        enter = "enter"
        backspace = "backspace"
        tab = "tab"
        esc = "esc"
        space = "space"
        left = "left"
        right = "right"
        up = "up"
        down = "down"
        delete = "delete"
        home = "home"
        end = "end"
        page_up = "page_up"
        page_down = "page_down"
        insert = "insert"

    class FakeKeyboardController:
        def __init__(self):
            self.presses: list[object] = []
            self.releases: list[object] = []
            self.typed: list[str] = []

        def press(self, key):
            self.presses.append(key)

        def release(self, key):
            self.releases.append(key)

        def type(self, text):
            self.typed.append(text)

    mouse_module.Controller = FakeMouseController
    mouse_module.Button = FakeButton
    keyboard_module.Controller = FakeKeyboardController
    keyboard_module.Key = FakeKey

    monkeypatch.setitem(sys.modules, "pynput", pynput_module)
    monkeypatch.setitem(sys.modules, "pynput.mouse", mouse_module)
    monkeypatch.setitem(sys.modules, "pynput.keyboard", keyboard_module)
    return mouse_module, keyboard_module


def test_control_handler_executes_commands(monkeypatch):
    fake_mouse, fake_keyboard = install_fake_pynput(monkeypatch)
    handler = ControlHandler(InputController())

    handler.handle({"type": "mouse_move", "x": 5, "y": 9})
    handler.handle({"type": "mouse_click", "x": 3, "y": 4})
    handler.handle({"type": "keypress", "key": "enter"})

    mouse_instance = handler._controller._mouse
    keyboard_instance = handler._controller._keyboard
    assert mouse_instance.moves == [(5, 9), (3, 4)]
    assert mouse_instance.clicks == [(3, 4, fake_mouse.Button.left)]
    assert keyboard_instance.presses == [fake_keyboard.Key.enter]


def test_handle_message_control_invokes_input_controller(
    monkeypatch, file_service, channel
):
    fake_mouse, _ = install_fake_pynput(monkeypatch)
    handler = ControlHandler(InputController())
    client = WebRTCClient(
        session_id="test-session",
        signaling=None,
        session_factory=lambda _mode: (handler, []),
        file_service=file_service,
    )

    payload = {
        "action": "control",
        "type": "mouse_click",
        "x": 11,
        "y": 12,
        "button": "right",
    }
    asyncio.run(client._handle_message(channel, payload, handler))

    mouse_instance = handler._controller._mouse
    assert mouse_instance.clicks == [(11, 12, fake_mouse.Button.right)]
