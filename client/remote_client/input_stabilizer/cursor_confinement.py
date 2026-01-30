"""Constrain the system cursor to a Tkinter window for remote desktop UI."""
from __future__ import annotations

import logging
from typing import Optional

try:
    import tkinter as tk
except Exception:  # pragma: no cover - optional dependency
    tk = None

logger = logging.getLogger(__name__)

_mouse = None


def _ensure_mouse() -> bool:
    global _mouse
    if _mouse is not None:
        return True
    try:
        from pynput.mouse import Controller
    except Exception as exc:  # pragma: no cover - optional dependency
        logger.warning("[Stabilizer] pynput unavailable: %s", exc)
        return False
    _mouse = Controller()
    return True


def snap_back(root: "tk.Tk") -> tuple[int, int] | None:
    """Return the cursor to the center of the given Tk root window."""
    if tk is None or root is None:
        return None
    try:
        root.update_idletasks()
        width = max(1, int(root.winfo_width()))
        height = max(1, int(root.winfo_height()))
        center_x = int(root.winfo_rootx()) + width // 2
        center_y = int(root.winfo_rooty()) + height // 2
        if not _ensure_mouse():
            return None
        _mouse.position = (center_x, center_y)
        return center_x, center_y
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("[Stabilizer] Cursor snap failed: %s", exc)
        return None


def confine_cursor_to_window(root: "tk.Tk", canvas: "tk.Canvas | None" = None) -> None:
    """
    Keep the system cursor inside a Tk window.

    - Hides the system cursor.
    - Draws a virtual cursor on the canvas when provided.
    - Snaps back to center when leaving the window.
    """
    if tk is None or root is None:
        return

    try:
        root.config(cursor="none")
    except Exception:  # pragma: no cover - defensive
        pass

    def _local_pointer() -> Optional[tuple[int, int]]:
        try:
            return (
                int(root.winfo_pointerx()) - int(root.winfo_rootx()),
                int(root.winfo_pointery()) - int(root.winfo_rooty()),
            )
        except Exception:
            return None

    def _snap_if_outside(event=None) -> None:
        pos = _local_pointer()
        if pos is None:
            return
        local_x, local_y = pos
        try:
            width = int(root.winfo_width())
            height = int(root.winfo_height())
        except Exception:
            return
        if width <= 1 or height <= 1:
            return
        if not (0 <= local_x < width and 0 <= local_y < height):
            snap_back(root)

    def _focus_on_enter(event=None) -> None:
        try:
            root.focus_force()
        except Exception:
            pass

    root.bind("<Motion>", _snap_if_outside, add="+")
    root.bind("<Enter>", _focus_on_enter, add="+")
    root.bind("<Leave>", _snap_if_outside, add="+")
    _focus_on_enter()

    if canvas is not None:
        try:
            root.update_idletasks()
            cx = int(canvas.winfo_width() or root.winfo_width()) // 2
            cy = int(canvas.winfo_height() or root.winfo_height()) // 2
            cursor_item = canvas.create_oval(
                cx - 5,
                cy - 5,
                cx + 5,
                cy + 5,
                fill="red",
                outline="white",
                width=2,
            )

            def _update_virtual_cursor(event) -> None:
                canvas.coords(
                    cursor_item,
                    event.x - 5,
                    event.y - 5,
                    event.x + 5,
                    event.y + 5,
                )

            canvas.bind("<Motion>", _update_virtual_cursor, add="+")
        except Exception:  # pragma: no cover - defensive
            pass

    def _periodic_snap() -> None:
        try:
            if not root.winfo_exists():
                return
        except Exception:
            return
        _snap_if_outside()
        root.after(50, _periodic_snap)

    _periodic_snap()

    def _restore_cursor(event=None) -> None:
        try:
            root.config(cursor="")
        except Exception:
            pass

    root.bind("<Destroy>", _restore_cursor, add="+")
