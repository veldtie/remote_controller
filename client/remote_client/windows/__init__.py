# windows/__init__.py
"""Windows-specific functionality including Virtual Display Driver and hVNC"""

from .vdd_driver import VDDDriver, get_driver, is_available, ensure_installed
from .virtual_display import VirtualDisplay, create_virtual_display, check_virtual_display_available

# hVNC exports (only available on Windows)
import platform
if platform.system() == "Windows":
    try:
        from .hvnc import HVNCSession, HiddenDesktop, create_hvnc_session
        from .hvnc_track import HVNCSessionWrapper, HVNCVideoTrack, HVNC_AVAILABLE
    except ImportError:
        HVNC_AVAILABLE = False
        HVNCSession = None
        HiddenDesktop = None
        create_hvnc_session = None
        HVNCSessionWrapper = None
        HVNCVideoTrack = None
else:
    HVNC_AVAILABLE = False
    HVNCSession = None
    HiddenDesktop = None
    create_hvnc_session = None
    HVNCSessionWrapper = None
    HVNCVideoTrack = None

__all__ = [
    # VDD exports
    "VDDDriver",
    "get_driver", 
    "is_available",
    "ensure_installed",
    "VirtualDisplay",
    "create_virtual_display",
    "check_virtual_display_available",
    # hVNC exports
    "HVNC_AVAILABLE",
    "HVNCSession",
    "HiddenDesktop",
    "create_hvnc_session",
    "HVNCSessionWrapper",
    "HVNCVideoTrack",
]
