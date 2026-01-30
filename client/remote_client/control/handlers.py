"""Handlers for control messages arriving via the data channel."""
from __future__ import annotations

import importlib.util
import logging
import platform
from typing import Any

from .input_controller import InputController, KeyPress, MouseClick, MouseMove, TextInput


class ControlMessageParser:
    """Parses incoming control messages into command objects."""

    def parse(self, payload: dict[str, Any]) -> MouseMove | MouseClick | KeyPress | TextInput:
        message_type = payload.get("type")
        source_width = payload.get("source_width")
        source_height = payload.get("source_height")
        try:
            source_width_value = int(source_width) if source_width is not None else None
        except (TypeError, ValueError):
            source_width_value = None
        try:
            source_height_value = int(source_height) if source_height is not None else None
        except (TypeError, ValueError):
            source_height_value = None
        if message_type == "mouse_move":
            return MouseMove(
                x=int(payload["x"]),
                y=int(payload["y"]),
                source_width=source_width_value,
                source_height=source_height_value,
            )
        if message_type == "mouse_click":
            return MouseClick(
                x=int(payload["x"]),
                y=int(payload["y"]),
                button=payload.get("button", "left"),
                source_width=source_width_value,
                source_height=source_height_value,
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


class StabilizedControlHandler(ControlHandler):
    """Control handler that routes mouse input through the stabilizer."""

    def __init__(self, controller: InputController) -> None:
        super().__init__(controller)
        self._stabilizer = None
        if platform.system() != "Windows":
            return
        if importlib.util.find_spec("pynput") is None:
            logging.getLogger(__name__).warning(
                "pynput is not installed; stabilized input disabled."
            )
            return
        try:
            from remote_client.input_stabilizer.control_adapter import (
                StabilizedControlAdapter,
            )
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "Input stabilizer unavailable; using basic input handling: %s", exc
            )
        else:
            self._stabilizer = StabilizedControlAdapter()

    def handle(self, payload: dict[str, Any]) -> None:
        message_type = payload.get("type")
        if message_type in {"mouse_move", "mouse_click"} and self._stabilizer:
            self._stabilizer.handle(payload)
            return
        super().handle(payload)
