"""Adapter to apply stabilized input handling to raw control payloads."""

from __future__ import annotations

import logging
from typing import Any, Dict, TYPE_CHECKING

from .cursor_confinement import confine_cursor_to_window
from .mouse_handler_pynput import click_mouse, move_mouse, scroll_mouse

logger = logging.getLogger(__name__)


class StabilizedControlAdapter:
    """Handle control messages with pynput-based stabilization."""

    def __init__(
        self,
        root: "tk.Tk | None" = None,
        confine_cursor: bool = False,
        canvas: "tk.Canvas | None" = None,
    ) -> None:
        self.root = root
        self.confine_cursor = confine_cursor
        self.canvas = canvas
        self._confinement_ready = False
        if self.confine_cursor and self.root:
            try:
                confine_cursor_to_window(self.root, self.canvas)
                self._confinement_ready = True
            except Exception as exc:
                logger.warning("[Stabilizer] Cursor confinement setup failed: %s", exc)

    def handle(self, payload: Dict[str, Any]) -> bool:
        message_type = payload.get("type")

        if message_type == "mouse_move":
            return move_mouse(
                int(payload.get("x", 0)),
                int(payload.get("y", 0)),
                payload.get("source_width"),
                payload.get("source_height"),
                confine_to_window=self.confine_cursor,
                root=self.root,
            )

        if message_type == "mouse_click":
            return click_mouse(
                int(payload.get("x", 0)),
                int(payload.get("y", 0)),
                button=payload.get("button", "left"),
                source_width=payload.get("source_width"),
                source_height=payload.get("source_height"),
                confine_to_window=self.confine_cursor,
                root=self.root,
            )
        if message_type == "mouse_scroll":
            dx = payload.get("delta_x", payload.get("dx", 0))
            dy = payload.get("delta_y", payload.get("dy", 0))
            return scroll_mouse(int(dx or 0), int(dy or 0))

        if message_type in {"keypress", "text"}:
            logger.info("[Stabilizer] Keyboard input not handled: %s", payload)
            return False

        logger.warning("[Stabilizer] Unknown control type: %s", message_type)
        return False


if TYPE_CHECKING:  # pragma: no cover - type hints only
    import tkinter as tk
