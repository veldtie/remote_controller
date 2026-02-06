# windows/virtual_display.py
"""
Virtual Display API for hidden screen capture.
Compatible with hidden_desktop.py expectations.
"""

import logging
from typing import Optional, Tuple

from .vdd_driver import VDDDriver, get_driver, is_available, ensure_installed

logger = logging.getLogger(__name__)


def check_virtual_display_support() -> bool:
    """
    Check if virtual display is supported and available.
    
    Returns:
        True if virtual display driver is installed and ready
    """
    try:
        driver = get_driver()
        return driver.is_driver_installed()
    except Exception as e:
        logger.debug(f"Virtual display support check failed: {e}")
        return False


class VirtualDisplaySession:
    """
    Virtual display session for hidden screen capture.
    
    This class manages a virtual display that can be used for
    remote desktop sessions without showing content on the physical monitor.
    
    Usage:
        session = VirtualDisplaySession()
        if session.start(width=1920, height=1080):
            # Use session.monitor_index for capture
            # session.resolution gives (width, height)
        session.stop()
    """
    
    def __init__(self):
        self._driver: Optional[VDDDriver] = None
        self._width: int = 1920
        self._height: int = 1080
        self._active: bool = False
        self._monitor_index: int = -1
    
    def start(
        self,
        width: int = 1920,
        height: int = 1080,
        auto_install: bool = False
    ) -> bool:
        """
        Start the virtual display session.
        
        Args:
            width: Display width in pixels
            height: Display height in pixels
            auto_install: Whether to auto-install driver (requires admin)
            
        Returns:
            True if virtual display started successfully
        """
        self._width = width
        self._height = height
        
        logger.info("Trying embedded VDD driver...")
        
        try:
            self._driver = get_driver()
            
            # Check if driver is installed
            if not self._driver.is_driver_installed():
                if auto_install:
                    logger.info("Attempting to install VDD driver...")
                    if not self._driver.install():
                        logger.error("Failed to install VDD driver")
                        return False
                else:
                    logger.error("Driver not installed and auto_install disabled or not admin")
                    return False
            
            # Create the virtual display
            if self._driver.create_display():
                self._active = True
                self._monitor_index = self._find_virtual_monitor()
                logger.info(f"Virtual display started: {width}x{height}, monitor index: {self._monitor_index}")
                return True
            else:
                logger.error("Failed to create virtual display")
                return False
                
        except Exception as e:
            logger.error(f"Virtual display start failed: {e}")
            return False
    
    def _find_virtual_monitor(self) -> int:
        """Find the index of the virtual monitor."""
        # Virtual display is usually the last monitor added
        # For now, return 1 (second monitor) as default
        # TODO: Actually enumerate monitors to find the virtual one
        try:
            import ctypes
            user32 = ctypes.windll.user32
            num_monitors = user32.GetSystemMetrics(80)  # SM_CMONITORS
            if num_monitors > 1:
                return num_monitors - 1  # Last monitor (0-indexed would be num-1)
            return 1
        except:
            return 1
    
    def stop(self):
        """Stop the virtual display session."""
        if self._driver and self._active:
            self._driver.remove_display()
        self._active = False
        self._monitor_index = -1
        logger.info("Virtual display stopped")
    
    @property
    def is_active(self) -> bool:
        """Whether the virtual display is active."""
        return self._active
    
    @property
    def resolution(self) -> Tuple[int, int]:
        """Current resolution as (width, height)."""
        return (self._width, self._height)
    
    @property
    def width(self) -> int:
        """Display width in pixels."""
        return self._width
    
    @property
    def height(self) -> int:
        """Display height in pixels."""
        return self._height
    
    @property
    def monitor_index(self) -> int:
        """
        Index of the virtual monitor for screen capture.
        Returns -1 if not active.
        """
        return self._monitor_index if self._active else -1
    
    def get_capture_region(self) -> dict:
        """
        Get the capture region for the virtual display.
        
        Returns:
            Dict with keys: left, top, width, height (for mss compatibility)
        """
        # mss expects dict with these keys
        return {
            "left": 0,
            "top": 0, 
            "width": self._width,
            "height": self._height,
            "mon": self._monitor_index,
        }
    
    def get_capture_region_tuple(self) -> Tuple[int, int, int, int]:
        """
        Get the capture region as tuple.
        
        Returns:
            Tuple of (left, top, width, height)
        """
        return (0, 0, self._width, self._height)
    
    def get_monitor_info(self) -> dict:
        """
        Get information about the virtual monitor.
        
        Returns:
            Dictionary with monitor details.
        """
        return {
            "index": self._monitor_index,
            "width": self._width,
            "height": self._height,
            "active": self._active,
            "left": 0,
            "top": 0,
        }
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        return False


# ==========================================
# Aliases for compatibility
# ==========================================

# For backward compatibility with other code
VirtualDisplay = VirtualDisplaySession
check_virtual_display_available = check_virtual_display_support


def create_virtual_display(
    width: int = 1920,
    height: int = 1080,
    auto_install: bool = True
) -> VirtualDisplaySession:
    """
    Create and start a virtual display session.
    
    Args:
        width: Width in pixels
        height: Height in pixels
        auto_install: Auto-install driver if missing (requires admin)
        
    Returns:
        VirtualDisplaySession instance
    """
    session = VirtualDisplaySession()
    session.start(width, height, auto_install=auto_install)
    return session
