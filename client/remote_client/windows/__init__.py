# windows/__init__.py
"""Windows-specific functionality including Virtual Display Driver"""

from .vdd_driver import VDDDriver, get_driver, is_available, ensure_installed
from .virtual_display import VirtualDisplay, create_virtual_display, check_virtual_display_available

__all__ = [
    "VDDDriver",
    "get_driver", 
    "is_available",
    "ensure_installed",
    "VirtualDisplay",
    "create_virtual_display",
    "check_virtual_display_available",
]
