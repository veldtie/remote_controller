"""Virtual Display management for hidden desktop sessions.

Uses Indirect Display Driver (IDD) to create virtual monitors that can be
captured even without a physical display connected.

Supports:
- Virtual-Display-Driver (https://github.com/itsmikethetech/Virtual-Display-Driver)
- IddSampleDriver
- Parsec Virtual Display (if installed)
"""
from __future__ import annotations

import ctypes
import json
import logging
import os
import platform
import shutil
import subprocess
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Virtual Display Driver download URL and paths
VDD_RELEASE_URL = "https://github.com/itsmikethetech/Virtual-Display-Driver/releases/latest/download/VirtualDisplayDriver.zip"
VDD_DRIVER_NAME = "VirtualDisplayDriver"
VDD_DEVICE_NAME = "Virtual Display"

# Registry paths for display configuration
DISPLAY_REG_PATH = r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers\Configuration"


def _is_admin() -> bool:
    """Check if running with administrator privileges."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def _run_hidden(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run command with hidden window."""
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    return subprocess.run(
        cmd,
        startupinfo=startupinfo,
        capture_output=True,
        text=True,
        **kwargs
    )


def _get_vdd_install_path() -> Path | None:
    """Get Virtual Display Driver installation path."""
    # Check common installation locations
    candidates = [
        Path(os.environ.get("PROGRAMFILES", "")) / "VirtualDisplayDriver",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "VirtualDisplayDriver",
        Path(os.environ.get("LOCALAPPDATA", "")) / "VirtualDisplayDriver",
        Path(os.environ.get("APPDATA", "")) / "VirtualDisplayDriver",
        Path.home() / "VirtualDisplayDriver",
    ]
    
    for path in candidates:
        if path.exists() and (path / "vdd.exe").exists():
            return path
        if path.exists() and (path / "VirtualDisplayDriver.exe").exists():
            return path
    
    return None


def _download_vdd(dest_dir: Path) -> bool:
    """Download Virtual Display Driver from GitHub."""
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        zip_path = dest_dir / "vdd.zip"
        
        logger.info("Downloading Virtual Display Driver...")
        urllib.request.urlretrieve(VDD_RELEASE_URL, zip_path)
        
        logger.info("Extracting Virtual Display Driver...")
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(dest_dir)
        
        zip_path.unlink()
        logger.info("Virtual Display Driver downloaded to %s", dest_dir)
        return True
    except Exception as exc:
        logger.error("Failed to download Virtual Display Driver: %s", exc)
        return False


def _install_vdd_driver(vdd_path: Path) -> bool:
    """Install the Virtual Display Driver using pnputil."""
    if not _is_admin():
        logger.error("Administrator privileges required to install driver")
        return False
    
    # Find the .inf file
    inf_files = list(vdd_path.glob("**/*.inf"))
    if not inf_files:
        logger.error("No .inf file found in %s", vdd_path)
        return False
    
    inf_file = inf_files[0]
    logger.info("Installing driver from %s", inf_file)
    
    try:
        # Install driver using pnputil
        result = _run_hidden([
            "pnputil", "/add-driver", str(inf_file), "/install"
        ])
        
        if result.returncode == 0:
            logger.info("Driver installed successfully")
            return True
        else:
            logger.error("Driver installation failed: %s", result.stderr)
            return False
    except Exception as exc:
        logger.error("Failed to install driver: %s", exc)
        return False


class VirtualDisplayManager:
    """Manages virtual displays using IDD driver."""
    
    def __init__(self) -> None:
        if platform.system() != "Windows":
            raise RuntimeError("Virtual Display is only supported on Windows")
        
        self._vdd_path: Path | None = None
        self._vdd_exe: Path | None = None
        self._display_id: int | None = None
        self._monitor_index: int | None = None
        self._resolution = (1920, 1080)
        self._refresh_rate = 60
        
    def is_driver_installed(self) -> bool:
        """Check if Virtual Display Driver is installed."""
        self._vdd_path = _get_vdd_install_path()
        if self._vdd_path:
            # Find the executable
            for name in ["vdd.exe", "VirtualDisplayDriver.exe", "vdd_cli.exe"]:
                exe_path = self._vdd_path / name
                if exe_path.exists():
                    self._vdd_exe = exe_path
                    return True
        
        # Check if driver is in system (via devcon or registry)
        try:
            result = _run_hidden([
                "pnputil", "/enum-drivers"
            ])
            if "VirtualDisplayDriver" in result.stdout or "IddSample" in result.stdout:
                return True
        except Exception:
            pass
        
        return False
    
    def install_driver(self) -> bool:
        """Download and install Virtual Display Driver."""
        if not _is_admin():
            logger.error("Administrator privileges required")
            return False
        
        # Download to local app data
        install_path = Path(os.environ.get("LOCALAPPDATA", "")) / "VirtualDisplayDriver"
        
        if not _download_vdd(install_path):
            return False
        
        if not _install_vdd_driver(install_path):
            return False
        
        self._vdd_path = install_path
        
        # Find executable
        for name in ["vdd.exe", "VirtualDisplayDriver.exe", "vdd_cli.exe"]:
            exe_path = install_path / name
            if exe_path.exists():
                self._vdd_exe = exe_path
                break
        
        return True
    
    def create_display(
        self, 
        width: int = 1920, 
        height: int = 1080, 
        refresh_rate: int = 60
    ) -> bool:
        """Create a new virtual display."""
        self._resolution = (width, height)
        self._refresh_rate = refresh_rate
        
        # Method 1: Try using VDD CLI tool
        if self._vdd_exe and self._vdd_exe.exists():
            return self._create_display_vdd_cli(width, height, refresh_rate)
        
        # Method 2: Try using DevCon
        return self._create_display_devcon()
    
    def _create_display_vdd_cli(
        self, 
        width: int, 
        height: int, 
        refresh_rate: int
    ) -> bool:
        """Create display using VDD CLI tool."""
        try:
            # Different VDD versions have different CLI interfaces
            # Try common command patterns
            commands_to_try = [
                [str(self._vdd_exe), "add", f"{width}x{height}@{refresh_rate}"],
                [str(self._vdd_exe), "create", "-w", str(width), "-h", str(height)],
                [str(self._vdd_exe), "-a", f"{width},{height},{refresh_rate}"],
                [str(self._vdd_exe), "enable"],
            ]
            
            for cmd in commands_to_try:
                try:
                    result = _run_hidden(cmd, timeout=10)
                    if result.returncode == 0:
                        logger.info("Virtual display created: %dx%d@%dHz", 
                                    width, height, refresh_rate)
                        time.sleep(1)  # Wait for display to initialize
                        self._find_virtual_monitor()
                        return True
                except Exception as e:
                    logger.debug("Command %s failed: %s", cmd, e)
                    continue
            
            logger.warning("VDD CLI commands failed, trying alternative method")
            return False
            
        except Exception as exc:
            logger.error("Failed to create display via VDD CLI: %s", exc)
            return False
    
    def _create_display_devcon(self) -> bool:
        """Create display using DevCon (device console)."""
        if not _is_admin():
            return False
        
        try:
            # Try to enable existing virtual display device
            result = _run_hidden([
                "pnputil", "/scan-devices"
            ])
            
            # This is a fallback - may not work without proper driver
            logger.warning("DevCon method not fully implemented")
            return False
            
        except Exception as exc:
            logger.error("Failed to create display via DevCon: %s", exc)
            return False
    
    def _find_virtual_monitor(self) -> None:
        """Find the index of the virtual monitor."""
        try:
            import mss
            with mss.mss() as sct:
                for i, mon in enumerate(sct.monitors):
                    # Virtual displays often have specific characteristics
                    if i > 0:  # Skip the "all monitors" entry
                        # Check if this might be our virtual display
                        if (mon.get("width") == self._resolution[0] and 
                            mon.get("height") == self._resolution[1]):
                            self._monitor_index = i
                            logger.info("Found virtual monitor at index %d", i)
                            return
                
                # If no exact match, use the last monitor (likely the new one)
                if len(sct.monitors) > 2:
                    self._monitor_index = len(sct.monitors) - 1
                    logger.info("Using monitor index %d as virtual display", 
                                self._monitor_index)
        except Exception as exc:
            logger.warning("Failed to find virtual monitor: %s", exc)
    
    def remove_display(self) -> bool:
        """Remove the virtual display."""
        if self._vdd_exe and self._vdd_exe.exists():
            try:
                commands_to_try = [
                    [str(self._vdd_exe), "remove"],
                    [str(self._vdd_exe), "disable"],
                    [str(self._vdd_exe), "-r"],
                ]
                
                for cmd in commands_to_try:
                    try:
                        result = _run_hidden(cmd, timeout=10)
                        if result.returncode == 0:
                            logger.info("Virtual display removed")
                            self._monitor_index = None
                            return True
                    except Exception:
                        continue
                        
            except Exception as exc:
                logger.error("Failed to remove display: %s", exc)
        
        return False
    
    @property
    def monitor_index(self) -> int | None:
        """Get the monitor index for screen capture."""
        return self._monitor_index
    
    @property
    def resolution(self) -> tuple[int, int]:
        """Get the virtual display resolution."""
        return self._resolution
    
    def get_monitor_rect(self) -> dict[str, int] | None:
        """Get the virtual monitor rectangle for mss capture."""
        if self._monitor_index is None:
            return None
        
        try:
            import mss
            with mss.mss() as sct:
                if self._monitor_index < len(sct.monitors):
                    return sct.monitors[self._monitor_index]
        except Exception:
            pass
        
        return None


class VirtualDisplaySession:
    """Manages a complete virtual display session for hidden desktop."""
    
    def __init__(self) -> None:
        self._manager = VirtualDisplayManager()
        self._active = False
    
    def start(
        self, 
        width: int = 1920, 
        height: int = 1080,
        auto_install: bool = True
    ) -> bool:
        """Start a virtual display session."""
        # Check if driver is installed
        if not self._manager.is_driver_installed():
            logger.info("Virtual Display Driver not found")
            if auto_install and _is_admin():
                logger.info("Attempting to install driver...")
                if not self._manager.install_driver():
                    logger.error("Failed to install Virtual Display Driver")
                    return False
            else:
                logger.warning(
                    "Virtual Display Driver not installed. "
                    "Run as administrator to auto-install, or install manually from: "
                    "https://github.com/itsmikethetech/Virtual-Display-Driver"
                )
                return False
        
        # Create virtual display
        if not self._manager.create_display(width, height):
            logger.error("Failed to create virtual display")
            return False
        
        self._active = True
        return True
    
    def stop(self) -> None:
        """Stop the virtual display session."""
        if self._active:
            self._manager.remove_display()
            self._active = False
    
    @property
    def is_active(self) -> bool:
        return self._active
    
    @property
    def monitor_index(self) -> int | None:
        return self._manager.monitor_index
    
    @property
    def resolution(self) -> tuple[int, int]:
        return self._manager.resolution
    
    def get_capture_region(self) -> dict[str, int] | None:
        """Get the region to capture for mss."""
        return self._manager.get_monitor_rect()


# Alternative: Use Windows Display API directly
class DisplayConfigManager:
    """Manage displays using Windows SetupAPI and CCD API."""
    
    # Constants for display configuration
    QDC_ALL_PATHS = 0x00000001
    QDC_ONLY_ACTIVE_PATHS = 0x00000002
    
    def __init__(self) -> None:
        if platform.system() != "Windows":
            raise RuntimeError("Windows only")
        self._user32 = ctypes.windll.user32
    
    def get_display_count(self) -> int:
        """Get the number of active displays."""
        try:
            import mss
            with mss.mss() as sct:
                # Subtract 1 for the "all monitors" virtual screen
                return max(0, len(sct.monitors) - 1)
        except Exception:
            return 1
    
    def get_display_info(self) -> list[dict[str, Any]]:
        """Get information about all displays."""
        displays = []
        try:
            import mss
            with mss.mss() as sct:
                for i, mon in enumerate(sct.monitors):
                    if i == 0:
                        continue  # Skip "all monitors" entry
                    displays.append({
                        "index": i,
                        "left": mon.get("left", 0),
                        "top": mon.get("top", 0),
                        "width": mon.get("width", 0),
                        "height": mon.get("height", 0),
                    })
        except Exception as exc:
            logger.warning("Failed to get display info: %s", exc)
        
        return displays


def check_virtual_display_support() -> dict[str, Any]:
    """Check system support for virtual displays."""
    result = {
        "supported": platform.system() == "Windows",
        "is_admin": _is_admin(),
        "driver_installed": False,
        "driver_path": None,
        "displays": [],
    }
    
    if not result["supported"]:
        return result
    
    try:
        mgr = VirtualDisplayManager()
        result["driver_installed"] = mgr.is_driver_installed()
        if mgr._vdd_path:
            result["driver_path"] = str(mgr._vdd_path)
        
        dcm = DisplayConfigManager()
        result["displays"] = dcm.get_display_info()
    except Exception as exc:
        logger.warning("Error checking virtual display support: %s", exc)
    
    return result
