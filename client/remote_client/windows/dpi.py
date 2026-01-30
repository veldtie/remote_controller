"""Windows DPI awareness helpers to align capture and input scaling."""
from __future__ import annotations

import ctypes
import logging
import os
import platform

logger = logging.getLogger(__name__)

_DPI_AWARE = False


def ensure_dpi_awareness() -> bool:
    """Enable per-monitor DPI awareness on Windows to avoid scaling mismatch."""
    global _DPI_AWARE
    if _DPI_AWARE:
        return True
    if platform.system() != "Windows":
        return False
    if _dpi_disabled():
        logger.info("DPI awareness disabled via RC_DISABLE_DPI_AWARE.")
        return False
    _DPI_AWARE = _set_dpi_awareness()
    if _DPI_AWARE:
        logger.info("DPI awareness enabled.")
    return _DPI_AWARE


def _dpi_disabled() -> bool:
    value = os.getenv("RC_DISABLE_DPI_AWARE", "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _set_dpi_awareness() -> bool:
    """Try modern per-monitor awareness, then fall back to system DPI awareness."""
    try:
        user32 = ctypes.windll.user32
        if hasattr(user32, "SetProcessDpiAwarenessContext"):
            # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
            if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
                return True
    except Exception as exc:
        logger.debug("SetProcessDpiAwarenessContext failed: %s", exc)

    try:
        shcore = ctypes.windll.shcore
        # PROCESS_PER_MONITOR_DPI_AWARE = 2
        result = int(shcore.SetProcessDpiAwareness(2))
        if result == 0 or result == 0x80070005:  # S_OK or E_ACCESSDENIED (already set)
            return True
    except Exception as exc:
        logger.debug("SetProcessDpiAwareness failed: %s", exc)

    try:
        user32 = ctypes.windll.user32
        if user32.SetProcessDPIAware():
            return True
    except Exception as exc:
        logger.debug("SetProcessDPIAware failed: %s", exc)

    return False
