"""Stabilized mouse handling via pynput."""

from __future__ import annotations

import logging
import os
from typing import Optional, TYPE_CHECKING

from .coordinate_normalizer import normalize_coordinates
from .cursor_confinement import snap_back

logger = logging.getLogger(__name__)

_mouse = None
_button_cls = None

_last_x: int | None = None
_last_y: int | None = None


def _movement_threshold() -> int:
    raw = os.getenv("RC_MOUSE_STABILIZER_THRESHOLD", "").strip()
    if not raw:
        return 3
    try:
        value = int(raw)
    except ValueError:
        return 3
    return max(0, value)


def _ensure_mouse() -> bool:
    global _mouse, _button_cls
    if _mouse is not None and _button_cls is not None:
        return True
    try:
        from pynput.mouse import Button, Controller
    except Exception as exc:
        logger.warning("[Stabilizer] pynput unavailable: %s", exc)
        return False
    _mouse = Controller()
    _button_cls = Button
    return True


def move_mouse(
    x: int,
    y: int,
    source_width: Optional[int] = None,
    source_height: Optional[int] = None,
    confine_to_window: bool = False,
    root: "tk.Tk | None" = None,
) -> bool:
    """Move cursor with normalization and micro-movement filter."""
    global _last_x, _last_y

    norm_x, norm_y = normalize_coordinates(x, y, source_width, source_height)
    threshold = _movement_threshold()

    if _last_x is not None and _last_y is not None and threshold > 0:
        if abs(norm_x - _last_x) < threshold and abs(norm_y - _last_y) < threshold:
            return True

    if not _ensure_mouse():
        return False

    try:
        _mouse.position = (norm_x, norm_y)
        _last_x, _last_y = norm_x, norm_y
        if confine_to_window and root is not None:
            _schedule_snap_back(root)
        return True
    except Exception as exc:
        logger.warning("[Stabilizer] Mouse move failed: %s", exc)
        return False


def click_mouse(
    x: int,
    y: int,
    button: str = "left",
    source_width: Optional[int] = None,
    source_height: Optional[int] = None,
    confine_to_window: bool = False,
    root: "tk.Tk | None" = None,
) -> bool:
    """Click with normalization and pynput."""
    global _last_x, _last_y

    norm_x, norm_y = normalize_coordinates(x, y, source_width, source_height)

    if not _ensure_mouse():
        return False

    try:
        _mouse.position = (norm_x, norm_y)
        _last_x, _last_y = norm_x, norm_y
        x1_button = getattr(_button_cls, "x1", _button_cls.left)
        x2_button = getattr(_button_cls, "x2", _button_cls.left)
        btn_map = {
            "left": _button_cls.left,
            "right": _button_cls.right,
            "middle": _button_cls.middle,
            "x1": x1_button,
            "x2": x2_button,
        }
        btn = btn_map.get(button.lower(), _button_cls.left)
        _mouse.click(btn)
        if confine_to_window and root is not None:
            _schedule_snap_back(root)
        return True
    except Exception as exc:
        logger.warning("[Stabilizer] Mouse click failed: %s", exc)
        return False


def _schedule_snap_back(root: "tk.Tk") -> None:
    def _do_snap() -> None:
        pos = snap_back(root)
        if pos:
            global _last_x, _last_y
            _last_x, _last_y = pos

    try:
        root.after(0, _do_snap)
    except Exception:
        _do_snap()


if TYPE_CHECKING:  # pragma: no cover - type hints only
    import tkinter as tk
