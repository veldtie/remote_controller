"""Handlers for control messages arriving via the data channel."""
from __future__ import annotations

from typing import Any

from .input_controller import InputController, KeyPress, MouseClick, MouseMove, TextInput


class ControlMessageParser:
    """Parses incoming control messages into command objects."""

    def parse(self, payload: dict[str, Any]) -> MouseMove | MouseClick | KeyPress | TextInput:
        message_type = payload.get("type")
        if message_type == "mouse_move":
            return MouseMove(x=int(payload["x"]), y=int(payload["y"]))
        if message_type == "mouse_click":
            return MouseClick(
                x=int(payload["x"]),
                y=int(payload["y"]),
                button=payload.get("button", "left"),
            )
        if message_type == "keypress":
            return KeyPress(key=str(payload["key"]))
        if message_type == "text":
            return TextInput(text=str(payload.get("text", "")))
        raise ValueError(f"Unknown control message type: {message_type}")


class ControlHandler:
    """Coordinates message parsing and input execution."""

    def __init__(self, controller: InputController) -> None:
        self._controller = controller
        self._parser = ControlMessageParser()

    def handle(self, payload: dict[str, Any]) -> None:
        command = self._parser.parse(payload)
        self._controller.execute(command)
