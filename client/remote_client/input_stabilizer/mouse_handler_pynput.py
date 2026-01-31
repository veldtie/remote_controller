"""Stabilized mouse handling via pynput."""

from __future__ import annotations

import logging
import os
import time
from typing import Optional, TYPE_CHECKING

from .coordinate_normalizer import normalize_coordinates
from .cursor_confinement import snap_back

logger = logging.getLogger(__name__)

_mouse = None
_button_cls = None

_last_x: int | None = None
_last_y: int | None = None
_target_x: int | None = None
_target_y: int | None = None

_CLICK_DELAY_FALLBACK = 0.02


def _click_delay() -> float:
    raw = os.getenv("RC_MOUSE_CLICK_DELAY_MS", "").strip()
    if not raw:
        return _CLICK_DELAY_FALLBACK
    try:
        value = float(raw) / 1000.0
    except ValueError:
        return _CLICK_DELAY_FALLBACK
    return max(0.0, min(value, 0.2))


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
    force: bool = False,
) -> bool:
    """Move cursor with normalization and micro-movement filter."""
    global _last_x, _last_y

    norm_x, norm_y = normalize_coordinates(x, y, source_width, source_height)
    threshold = _movement_threshold()

    global _target_x, _target_y
    _target_x, _target_y = norm_x, norm_y

    if not force and _last_x is not None and _last_y is not None and threshold > 0:
        if abs(norm_x - _last_x) < threshold and abs(norm_y - _last_y) < threshold:
            return True

    if not _ensure_mouse():
        return False

    try:
        _mouse.position = (norm_x, norm_y)
        _last_x, _last_y = norm_x, norm_y
        logger.debug("[Stabilizer] Move to (%s, %s)", norm_x, norm_y)
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

    if not move_mouse(
        x,
        y,
        source_width=source_width,
        source_height=source_height,
        confine_to_window=confine_to_window,
        root=root,
        force=True,
    ):
        return False

    if not _ensure_mouse():
        return False

    try:
        _focus_window(root)
        delay = _click_delay()
        if delay > 0:
            time.sleep(delay)
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
        logger.debug(
            "[Stabilizer] Clicked %s at (%s, %s)",
            button,
            _last_x,
            _last_y,
        )
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


def _focus_window(root: "tk.Tk | None") -> None:
    if root is None:
        return
    for action in ("activateWindow", "raise_", "focus_force", "setFocus"):
        try:
            getattr(root, action)()
        except Exception:
            continue


def scroll_mouse(dx: int = 0, dy: int = 0) -> bool:
    if not _ensure_mouse():
        return False
    try:
        delta_x = _normalize_scroll_delta(dx)
        delta_y = _normalize_scroll_delta(dy)
        if delta_x == 0 and delta_y == 0:
            return True
        _mouse.scroll(delta_x, delta_y)
        logger.debug("[Stabilizer] Scroll dx=%s dy=%s", delta_x, delta_y)
        return True
    except Exception as exc:
        logger.warning("[Stabilizer] Scroll failed: %s", exc)
        return False


def _normalize_scroll_delta(value: int | None) -> int:
    if value is None:
        return 0
    try:
        delta = int(value)
    except (TypeError, ValueError):
        return 0
    if delta == 0:
        return 0
    step = int(round(delta / 120))
    if step == 0:
        step = 1 if delta > 0 else -1
    return step

if TYPE_CHECKING:  # pragma: no cover - type hints only
    import tkinter as tk
