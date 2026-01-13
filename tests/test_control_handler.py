import asyncio
import sys
import types

from remote_client.control.handlers import ControlHandler
from remote_client.control.input_controller import InputController
from remote_client.webrtc.client import WebRTCClient


def install_fake_pyautogui(monkeypatch):
    module = types.ModuleType("pyautogui")
    module.moves: list[tuple[int, int]] = []
    module.clicks: list[tuple[int, int, str]] = []
    module.presses: list[str] = []

    def move_to(x, y):
        module.moves.append((x, y))

    def click(x, y, button="left"):
        module.clicks.append((x, y, button))

    def press(key):
        module.presses.append(key)

    module.moveTo = move_to
    module.click = click
    module.press = press
    monkeypatch.setitem(sys.modules, "pyautogui", module)
    return module


def test_control_handler_executes_commands(monkeypatch):
    fake_pyautogui = install_fake_pyautogui(monkeypatch)
    handler = ControlHandler(InputController())

    handler.handle({"type": "mouse_move", "x": 5, "y": 9})
    handler.handle({"type": "mouse_click", "x": 3, "y": 4})
    handler.handle({"type": "keypress", "key": "enter"})

    assert fake_pyautogui.moves == [(5, 9)]
    assert fake_pyautogui.clicks == [(3, 4, "left")]
    assert fake_pyautogui.presses == ["enter"]


def test_handle_message_control_invokes_input_controller(
    monkeypatch, file_service, channel
):
    fake_pyautogui = install_fake_pyautogui(monkeypatch)
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

    assert fake_pyautogui.clicks == [(11, 12, "right")]
