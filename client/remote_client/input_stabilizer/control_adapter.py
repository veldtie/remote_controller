"""Adapter to apply stabilized input handling to raw control payloads."""

from __future__ import annotations

import logging
from typing import Any, Dict

from .mouse_handler_pynput import click_mouse, move_mouse

logger = logging.getLogger(__name__)


class StabilizedControlAdapter:
    """Handle control messages with pynput-based stabilization."""

    def handle(self, payload: Dict[str, Any]) -> None:
        message_type = payload.get("type")

        if message_type == "mouse_move":
            move_mouse(
                int(payload.get("x", 0)),
                int(payload.get("y", 0)),
                payload.get("source_width"),
                payload.get("source_height"),
            )
            return

        if message_type == "mouse_click":
            click_mouse(
                int(payload.get("x", 0)),
                int(payload.get("y", 0)),
                button=payload.get("button", "left"),
                source_width=payload.get("source_width"),
                source_height=payload.get("source_height"),
            )
            return

        if message_type in {"keypress", "text"}:
            logger.info("[Stabilizer] Keyboard input not handled: %s", payload)
            return

        logger.warning("[Stabilizer] Unknown control type: %s", message_type)
