"""Cursor visibility management for remote control sessions."""
from __future__ import annotations

import ctypes
import platform
import threading


class CursorVisibilityController:
    """Show or hide the system cursor on supported platforms."""

    def __init__(self) -> None:
        self._visible = True
        self._lock = threading.Lock()
        self._supported = platform.system() == "Windows"
        self._user32 = None
        if self._supported:
            try:
                self._user32 = ctypes.windll.user32
            except Exception:
                self._user32 = None
                self._supported = False

    def set_visible(self, visible: bool) -> None:
        target = bool(visible)
        if not self._supported or self._user32 is None:
            self._visible = target
            return
        with self._lock:
            if target == self._visible:
                return
            self._visible = target
            self._apply_locked()

    def reset(self) -> None:
        self.set_visible(True)

    def _apply_locked(self) -> None:
        # ShowCursor returns a display count:
        #  - >= 0 means cursor is visible
        #  - < 0 means cursor is hidden
        if not self._user32:
            return
        max_iters = 16
        if self._visible:
            for _ in range(max_iters):
                if self._user32.ShowCursor(True) >= 0:
                    break
        else:
            for _ in range(max_iters):
                if self._user32.ShowCursor(False) < 0:
                    break
