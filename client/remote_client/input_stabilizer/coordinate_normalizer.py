"""Normalize coordinates from the remote screen into local screen space."""

from __future__ import annotations

import logging
import platform
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


def normalize_coordinates(
    x: int,
    y: int,
    source_width: Optional[int],
    source_height: Optional[int],
) -> Tuple[int, int]:
    """Scale remote coordinates to the local screen and clamp to bounds."""
    if (
        source_width is None
        or source_height is None
        or source_width <= 0
        or source_height <= 0
    ):
        return x, y

    screen_size = _get_screen_size()
    if not screen_size:
        return x, y
    local_width, local_height = screen_size

    scale_x = local_width / source_width
    scale_y = local_height / source_height

    new_x = int(x * scale_x)
    new_y = int(y * scale_y)

    new_x = max(0, min(new_x, local_width - 1))
    new_y = max(0, min(new_y, local_height - 1))

    return new_x, new_y


def _get_screen_size() -> Tuple[int, int] | None:
    if platform.system() == "Windows":
        try:
            import ctypes

            user32 = ctypes.windll.user32
            return int(user32.GetSystemMetrics(0)), int(user32.GetSystemMetrics(1))
        except Exception as exc:
            logger.warning("[Stabilizer] Failed to read screen size: %s", exc)
            return None
    try:
        import tkinter

        root = tkinter.Tk()
        root.withdraw()
        width = root.winfo_screenwidth()
        height = root.winfo_screenheight()
        root.destroy()
        return int(width), int(height)
    except Exception as exc:
        logger.warning("[Stabilizer] Failed to read screen size: %s", exc)
        return None
