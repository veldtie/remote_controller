"""Control message handlers for remote input."""
from __future__ import annotations

from typing import Any, Mapping

from remote_client.control.input_controller import (
    InputController,
    KeyPress,
    MouseClick,
    MouseMove,
    MouseScroll,
    TextInput,
)


def _require_int(payload: Mapping[str, Any], key: str) -> int:
    value = payload[key]
    if isinstance(value, bool):
        raise ValueError(f"{key} must be an integer.")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be an integer.") from exc


def _optional_int(payload: Mapping[str, Any], key: str) -> int | None:
    if key not in payload:
        return None
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{key} must be an integer.")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be an integer.") from exc


def _normalize_button(value: Any) -> str:
    if value is None:
        return "left"
    if isinstance(value, int):
        if value == 2:
            return "right"
        if value == 1:
            return "middle"
        if value == 3:
            return "x1"
        if value == 4:
            return "x2"
        return "left"
    text = str(value).strip().lower()
    if text in {"left", "right", "middle", "x1", "x2"}:
        return text
    return "left"


class ControlHandler:
    """Translate incoming control payloads into input controller commands."""

    def __init__(self, controller: InputController) -> None:
        self._controller = controller

    def handle(self, payload: Mapping[str, Any]) -> None:
        message_type = payload["type"]
        if message_type == "mouse_move":
            command = MouseMove(
                x=_require_int(payload, "x"),
                y=_require_int(payload, "y"),
                source_width=_optional_int(payload, "source_width"),
                source_height=_optional_int(payload, "source_height"),
            )
        elif message_type == "mouse_click":
            command = MouseClick(
                x=_require_int(payload, "x"),
                y=_require_int(payload, "y"),
                button=_normalize_button(payload.get("button", "left")),
                source_width=_optional_int(payload, "source_width"),
                source_height=_optional_int(payload, "source_height"),
            )
        elif message_type == "mouse_scroll":
            delta_x = _optional_int(payload, "delta_x")
            delta_y = _optional_int(payload, "delta_y")
            command = MouseScroll(
                x=_require_int(payload, "x"),
                y=_require_int(payload, "y"),
                delta_x=0 if delta_x is None else delta_x,
                delta_y=0 if delta_y is None else delta_y,
                source_width=_optional_int(payload, "source_width"),
                source_height=_optional_int(payload, "source_height"),
            )
        elif message_type == "keypress":
            key = payload.get("key")
            if key is None:
                raise ValueError("Missing key for keypress.")
            command = KeyPress(key=str(key))
        elif message_type in {"text", "text_input"}:
            text = payload.get("text")
            if text is None:
                raise ValueError("Missing text input.")
            command = TextInput(text=str(text))
        else:
            raise ValueError(f"Unknown control type '{message_type}'.")
        self._controller.execute(command)


class StabilizedControlHandler(ControlHandler):
    """Drop repeated mouse-move events with unchanged coordinates."""

    def __init__(self, controller: InputController) -> None:
        super().__init__(controller)
        self._last_move: tuple[int, int] | None = None

    def handle(self, payload: Mapping[str, Any]) -> None:
        if payload.get("type") != "mouse_move":
            super().handle(payload)
            return
        x = _require_int(payload, "x")
        y = _require_int(payload, "y")
        if self._last_move == (x, y):
            return
        self._last_move = (x, y)
        command = MouseMove(
            x=x,
            y=y,
            source_width=_optional_int(payload, "source_width"),
            source_height=_optional_int(payload, "source_height"),
        )
        self._controller.execute(command)
