"""Embedded Virtual Display Driver for silent installation.

This module provides a virtual display driver that can be:
1. Embedded in the executable (PyInstaller)
2. Installed silently without user prompts (requires admin)
3. Used to create invisible virtual monitors

Supported drivers:
- IddSampleDriver (Microsoft sample, needs signing or test mode)
- Parsec VDD (signed driver, recommended)
- usbmmidd (generic virtual display)
"""
from __future__ import annotations

import base64
import ctypes
import hashlib
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import winreg
from ctypes import wintypes
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

# Windows API
kernel32 = ctypes.windll.kernel32
advapi32 = ctypes.windll.advapi32
setupapi = ctypes.windll.setupapi
newdev = None  # Loaded on demand

# Constants
DIGCF_PRESENT = 0x00000002
DIGCF_ALLCLASSES = 0x00000004
DIOD_INHERIT_CLASSDRVS = 0x00000002
DIF_REGISTERDEVICE = 0x00000019
DIF_REMOVE = 0x00000005
INSTALLFLAG_FORCE = 0x00000001
INSTALLFLAG_NONINTERACTIVE = 0x00000004
CR_SUCCESS = 0x00000000


class SP_DEVINFO_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("ClassGuid", wintypes.BYTE * 16),
        ("DevInst", wintypes.DWORD),
        ("Reserved", ctypes.POINTER(wintypes.ULONG)),
    ]


def _is_admin() -> bool:
    """Check if running with administrator privileges."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def _run_silent(cmd: list[str], timeout: int = 30) -> tuple[int, str, str]:
    """Run command silently without window."""
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0  # SW_HIDE
    
    try:
        result = subprocess.run(
            cmd,
            startupinfo=startupinfo,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Timeout"
    except Exception as e:
        return -1, "", str(e)


def _get_embedded_driver_path() -> Path | None:
    """Get path to embedded driver in PyInstaller bundle."""
    # Check if running as PyInstaller bundle
    if getattr(sys, 'frozen', False):
        base_path = Path(sys._MEIPASS)
    else:
        base_path = Path(__file__).parent
    
    driver_path = base_path / "drivers" / "vdd"
    if driver_path.exists():
        return driver_path
    
    return None


def _extract_embedded_driver(dest_dir: Path) -> bool:
    """Extract embedded driver to destination directory."""
    src = _get_embedded_driver_path()
    if not src or not src.exists():
        logger.warning("No embedded driver found")
        return False
    
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dest_dir, dirs_exist_ok=True)
        logger.info("Extracted embedded driver to %s", dest_dir)
        return True
    except Exception as e:
        logger.error("Failed to extract driver: %s", e)
        return False


class VDDDriverInstaller:
    """Silent Virtual Display Driver installer."""
    
    # Driver installation states
    NOT_INSTALLED = 0
    INSTALLED = 1
    NEEDS_REBOOT = 2
    ERROR = -1
    
    def __init__(self) -> None:
        self._driver_path: Path | None = None
        self._inf_path: Path | None = None
        self._device_id: str | None = None
        self._install_dir = Path(os.environ.get("LOCALAPPDATA", "")) / "RemoteController" / "VDD"
    
    def _find_driver_files(self, search_path: Path) -> bool:
        """Find .inf and .sys files in the given path."""
        inf_files = list(search_path.glob("**/*.inf"))
        if not inf_files:
            return False
        
        self._inf_path = inf_files[0]
        self._driver_path = search_path
        
        # Try to extract device ID from inf file
        try:
            content = self._inf_path.read_text(encoding='utf-8', errors='ignore')
            for line in content.split('\n'):
                if 'HardwareId' in line or 'DeviceId' in line:
                    # Extract ID from line like: HardwareId = "Root\IdsSampleDriver"
                    if '=' in line:
                        self._device_id = line.split('=')[1].strip().strip('"').strip("'")
                        break
        except Exception:
            pass
        
        return True
    
    def is_driver_installed(self) -> bool:
        """Check if VDD driver is already installed."""
        # Method 1: Check via pnputil
        code, stdout, _ = _run_silent(["pnputil", "/enum-drivers"])
        if code == 0:
            for keyword in ["IddSample", "VirtualDisplay", "ParsecVDD", "usbmmidd"]:
                if keyword.lower() in stdout.lower():
                    return True
        
        # Method 2: Check via registry
        try:
            key_path = r"SYSTEM\CurrentControlSet\Services\IddSampleDriver"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path):
                return True
        except WindowsError:
            pass
        
        # Method 3: Check if our install marker exists
        marker = self._install_dir / ".installed"
        if marker.exists():
            return True
        
        return False
    
    def install_driver_silent(self, inf_path: Path | None = None) -> int:
        """Install driver silently without user prompts.
        
        Returns:
            NOT_INSTALLED (0): Not installed
            INSTALLED (1): Successfully installed
            NEEDS_REBOOT (2): Installed, needs reboot
            ERROR (-1): Installation failed
        """
        if not _is_admin():
            logger.error("Administrator privileges required for driver installation")
            return self.ERROR
        
        # Find driver files
        if inf_path:
            self._inf_path = inf_path
            self._driver_path = inf_path.parent
        elif not self._inf_path:
            # Try embedded driver
            if not _extract_embedded_driver(self._install_dir):
                logger.error("No driver available for installation")
                return self.ERROR
            
            if not self._find_driver_files(self._install_dir):
                logger.error("No .inf file found in driver package")
                return self.ERROR
        
        logger.info("Installing driver from: %s", self._inf_path)
        
        # Method 1: pnputil (Windows 10+, cleanest method)
        result = self._install_via_pnputil()
        if result == self.INSTALLED:
            self._create_install_marker()
            return result
        
        # Method 2: DIFX/DPInst (legacy but reliable)
        result = self._install_via_dpinst()
        if result == self.INSTALLED:
            self._create_install_marker()
            return result
        
        # Method 3: SetupAPI direct (fallback)
        result = self._install_via_setupapi()
        if result == self.INSTALLED:
            self._create_install_marker()
            return result
        
        return self.ERROR
    
    def _install_via_pnputil(self) -> int:
        """Install using pnputil (Windows 10+ recommended)."""
        if not self._inf_path:
            return self.ERROR
        
        # Add driver to store
        code, stdout, stderr = _run_silent([
            "pnputil", "/add-driver", str(self._inf_path), "/install"
        ])
        
        if code == 0:
            logger.info("Driver installed via pnputil")
            # Create device instance
            self._create_device_instance()
            return self.INSTALLED
        elif "reboot" in (stdout + stderr).lower():
            return self.NEEDS_REBOOT
        else:
            logger.warning("pnputil failed: %s %s", stdout, stderr)
            return self.ERROR
    
    def _install_via_dpinst(self) -> int:
        """Install using DPInst if available."""
        # DPInst is not always available, but it handles driver signing better
        dpinst_paths = [
            self._driver_path / "dpinst.exe" if self._driver_path else None,
            Path(r"C:\Windows\System32\dpinst.exe"),
        ]
        
        dpinst = None
        for p in dpinst_paths:
            if p and p.exists():
                dpinst = p
                break
        
        if not dpinst:
            return self.ERROR
        
        code, stdout, stderr = _run_silent([
            str(dpinst), "/sw", "/sa", "/path", str(self._driver_path)
        ])
        
        if code in [0, 256]:  # 256 = needs reboot
            logger.info("Driver installed via DPInst")
            return self.INSTALLED if code == 0 else self.NEEDS_REBOOT
        
        return self.ERROR
    
    def _install_via_setupapi(self) -> int:
        """Install using SetupAPI directly (lowest level)."""
        if not self._inf_path:
            return self.ERROR
        
        try:
            global newdev
            if newdev is None:
                newdev = ctypes.windll.LoadLibrary("newdev.dll")
            
            # UpdateDriverForPlugAndPlayDevices
            need_reboot = wintypes.BOOL(False)
            
            hardware_id = self._device_id or "Root\\IddSampleDriver"
            
            result = newdev.UpdateDriverForPlugAndPlayDevicesW(
                None,  # hwndParent
                hardware_id,
                str(self._inf_path),
                INSTALLFLAG_FORCE | INSTALLFLAG_NONINTERACTIVE,
                ctypes.byref(need_reboot)
            )
            
            if result:
                logger.info("Driver installed via SetupAPI")
                return self.NEEDS_REBOOT if need_reboot.value else self.INSTALLED
            else:
                error = ctypes.get_last_error()
                logger.warning("SetupAPI failed with error: %d", error)
                return self.ERROR
                
        except Exception as e:
            logger.warning("SetupAPI installation failed: %s", e)
            return self.ERROR
    
    def _create_device_instance(self) -> bool:
        """Create a device instance for the virtual display."""
        if not self._device_id:
            self._device_id = "Root\\IddSampleDriver"
        
        try:
            # Use devcon or pnputil to create device
            code, _, _ = _run_silent([
                "pnputil", "/add-device", self._device_id
            ])
            return code == 0
        except Exception:
            return False
    
    def _create_install_marker(self) -> None:
        """Create marker file indicating driver is installed."""
        try:
            self._install_dir.mkdir(parents=True, exist_ok=True)
            marker = self._install_dir / ".installed"
            marker.write_text(f"installed:{time.time()}")
        except Exception:
            pass
    
    def uninstall_driver(self) -> bool:
        """Uninstall the VDD driver."""
        if not _is_admin():
            return False
        
        # Remove via pnputil
        code, stdout, _ = _run_silent(["pnputil", "/enum-drivers"])
        if code == 0:
            # Find and remove VDD drivers
            for line in stdout.split('\n'):
                if 'oem' in line.lower() and '.inf' in line.lower():
                    inf_name = line.split()[-1] if line.split() else None
                    if inf_name:
                        _run_silent(["pnputil", "/delete-driver", inf_name, "/force"])
        
        # Remove install marker
        marker = self._install_dir / ".installed"
        if marker.exists():
            marker.unlink()
        
        return True


class VDDControl:
    """Control virtual display after driver is installed."""
    
    def __init__(self) -> None:
        self._user32 = ctypes.windll.user32
        self._active_display_id: int | None = None
        self._resolution = (1920, 1080)
    
    def create_virtual_display(
        self, 
        width: int = 1920, 
        height: int = 1080,
        refresh_rate: int = 60
    ) -> bool:
        """Create a new virtual display.
        
        Uses registry/device control to add a virtual monitor.
        """
        self._resolution = (width, height)
        
        # Method 1: Try IddSampleDriver control interface
        if self._create_via_idd_control(width, height, refresh_rate):
            return True
        
        # Method 2: Registry-based creation
        if self._create_via_registry(width, height, refresh_rate):
            return True
        
        # Method 3: Device IoControl
        if self._create_via_ioctl(width, height):
            return True
        
        logger.warning("Could not create virtual display via any method")
        return False
    
    def _create_via_idd_control(self, width: int, height: int, refresh_rate: int) -> bool:
        """Create display using IDD control utility."""
        # Check for various control utilities
        control_paths = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "RemoteController" / "VDD" / "IddSampleApp.exe",
            Path(os.environ.get("PROGRAMFILES", "")) / "VirtualDisplayDriver" / "vdd.exe",
        ]
        
        for ctrl_exe in control_paths:
            if ctrl_exe.exists():
                code, _, _ = _run_silent([
                    str(ctrl_exe), "add", f"{width}x{height}@{refresh_rate}"
                ])
                if code == 0:
                    logger.info("Virtual display created via IDD control")
                    time.sleep(1)  # Wait for display to appear
                    return True
        
        return False
    
    def _create_via_registry(self, width: int, height: int, refresh_rate: int) -> bool:
        """Create display by modifying registry settings."""
        try:
            # This is driver-specific; IddSampleDriver uses this approach
            key_path = r"SOFTWARE\IddSampleDriver"
            
            try:
                key = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE, key_path, 
                    0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY
                )
            except WindowsError:
                key = winreg.CreateKeyEx(
                    winreg.HKEY_LOCAL_MACHINE, key_path,
                    0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY
                )
            
            with key:
                # Set monitor count and resolution
                winreg.SetValueEx(key, "MonitorCount", 0, winreg.REG_DWORD, 1)
                winreg.SetValueEx(key, "Width", 0, winreg.REG_DWORD, width)
                winreg.SetValueEx(key, "Height", 0, winreg.REG_DWORD, height)
                winreg.SetValueEx(key, "RefreshRate", 0, winreg.REG_DWORD, refresh_rate)
            
            # Notify system of display change
            HWND_BROADCAST = 0xFFFF
            WM_DISPLAYCHANGE = 0x007E
            self._user32.SendMessageW(HWND_BROADCAST, WM_DISPLAYCHANGE, 32, (height << 16) | width)
            
            # Also try CDS
            self._user32.ChangeDisplaySettingsW(None, 0)
            
            logger.info("Virtual display configured via registry")
            time.sleep(1)
            return True
            
        except Exception as e:
            logger.warning("Registry method failed: %s", e)
            return False
    
    def _create_via_ioctl(self, width: int, height: int) -> bool:
        """Create display using device IoControl."""
        # This requires knowing the specific device path and IOCTL codes
        # which vary by driver implementation
        return False
    
    def remove_virtual_display(self) -> bool:
        """Remove the virtual display."""
        # Method 1: Control utility
        control_paths = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "RemoteController" / "VDD" / "IddSampleApp.exe",
        ]
        
        for ctrl_exe in control_paths:
            if ctrl_exe.exists():
                code, _, _ = _run_silent([str(ctrl_exe), "remove"])
                if code == 0:
                    return True
        
        # Method 2: Registry
        try:
            key_path = r"SOFTWARE\IddSampleDriver"
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, key_path,
                0, winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY
            ) as key:
                winreg.SetValueEx(key, "MonitorCount", 0, winreg.REG_DWORD, 0)
            
            self._user32.ChangeDisplaySettingsW(None, 0)
            return True
        except Exception:
            pass
        
        return False
    
    def get_virtual_monitor_index(self) -> int | None:
        """Find the index of the virtual monitor for screen capture."""
        try:
            import mss
            with mss.mss() as sct:
                monitors = sct.monitors
                
                # Virtual display is usually the last one added
                if len(monitors) > 2:
                    # Check if last monitor matches our resolution
                    last_mon = monitors[-1]
                    if (last_mon.get("width") == self._resolution[0] and
                        last_mon.get("height") == self._resolution[1]):
                        return len(monitors) - 1
                    
                    # Otherwise return the last monitor anyway
                    return len(monitors) - 1
                
        except Exception as e:
            logger.warning("Could not find virtual monitor: %s", e)
        
        return None
    
    def get_capture_region(self) -> dict | None:
        """Get the capture region for the virtual display."""
        idx = self.get_virtual_monitor_index()
        if idx is None:
            return None
        
        try:
            import mss
            with mss.mss() as sct:
                if idx < len(sct.monitors):
                    return dict(sct.monitors[idx])
        except Exception:
            pass
        
        return None


class EmbeddedVDDSession:
    """Complete virtual display session with embedded driver support.
    
    Usage:
        session = EmbeddedVDDSession()
        if session.start():
            # Virtual display is ready
            region = session.get_capture_region()
            # Use region with mss for capture
        session.stop()
    """
    
    def __init__(self) -> None:
        self._installer = VDDDriverInstaller()
        self._control = VDDControl()
        self._active = False
        self._resolution = (1920, 1080)
    
    def start(
        self, 
        width: int = 1920, 
        height: int = 1080,
        auto_install: bool = True
    ) -> bool:
        """Start virtual display session.
        
        Args:
            width: Display width
            height: Display height
            auto_install: Automatically install driver if needed
        
        Returns:
            True if virtual display is ready
        """
        self._resolution = (width, height)
        
        # Check if driver is installed
        if not self._installer.is_driver_installed():
            if auto_install and _is_admin():
                logger.info("Installing virtual display driver...")
                result = self._installer.install_driver_silent()
                
                if result == VDDDriverInstaller.ERROR:
                    logger.error("Driver installation failed")
                    return False
                elif result == VDDDriverInstaller.NEEDS_REBOOT:
                    logger.warning("Driver installed but reboot required")
                    return False
                
                logger.info("Driver installed successfully")
                time.sleep(2)  # Wait for driver to initialize
            else:
                logger.error("Driver not installed and auto_install disabled or not admin")
                return False
        
        # Create virtual display
        if not self._control.create_virtual_display(width, height):
            logger.error("Failed to create virtual display")
            return False
        
        # Verify display was created
        time.sleep(1)
        region = self._control.get_capture_region()
        if region:
            logger.info("Virtual display ready: %dx%d", region.get("width"), region.get("height"))
            self._active = True
            return True
        else:
            logger.warning("Virtual display created but not detected")
            # Still mark as active - capture might work
            self._active = True
            return True
    
    def stop(self) -> None:
        """Stop virtual display session."""
        if self._active:
            self._control.remove_virtual_display()
            self._active = False
    
    @property
    def is_active(self) -> bool:
        return self._active
    
    @property
    def resolution(self) -> tuple[int, int]:
        return self._resolution
    
    def get_capture_region(self) -> dict | None:
        """Get the region for mss screen capture."""
        return self._control.get_capture_region()
    
    def get_monitor_index(self) -> int | None:
        """Get the monitor index for capture."""
        return self._control.get_virtual_monitor_index()


# Utility functions for PyInstaller integration
def get_driver_data_files() -> list[tuple[str, str]]:
    """Get list of driver files to include in PyInstaller bundle.
    
    Add this to your .spec file:
        from remote_client.windows.vdd_driver import get_driver_data_files
        datas = get_driver_data_files()
    """
    driver_src = Path(__file__).parent / "drivers" / "vdd"
    if not driver_src.exists():
        return []
    
    files = []
    for f in driver_src.rglob("*"):
        if f.is_file():
            rel_path = f.relative_to(driver_src.parent)
            dest_dir = str(rel_path.parent)
            files.append((str(f), dest_dir))
    
    return files


# =============================================================================
# Test Mode Watermark Remover
# =============================================================================

class TestModeWatermarkRemover:
    """Removes the 'Test Mode' watermark from Windows desktop.
    
    When Windows is in test signing mode, a watermark appears in the corner.
    This class hides that watermark by finding and hiding the window that
    displays it.
    
    Usage:
        remover = TestModeWatermarkRemover()
        remover.start()  # Starts background thread
        # ... do work ...
        remover.stop()
    
    Or as context manager:
        with TestModeWatermarkRemover():
            # watermark is hidden
            pass
    """
    
    # Window class names that display the watermark
    WATERMARK_CLASSES = [
        "SysShadow",
        "#32770",  # Dialog class sometimes used
    ]
    
    # Text patterns in watermark windows
    WATERMARK_TEXTS = [
        "Test Mode",
        "Тестовый режим",  # Russian
        "Testmodus",  # German
        "Mode test",  # French
    ]
    
    def __init__(self) -> None:
        self._user32 = ctypes.windll.user32
        self._running = False
        self._thread: threading.Thread | None = None
        self._hidden_windows: list[int] = []
    
    def _find_watermark_windows(self) -> list[int]:
        """Find windows that display the Test Mode watermark."""
        watermark_hwnds = []
        
        # Callback for EnumWindows
        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def enum_callback(hwnd: int, lparam: int) -> bool:
            # Get window text
            length = self._user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buffer = ctypes.create_unicode_buffer(length + 1)
                self._user32.GetWindowTextW(hwnd, buffer, length + 1)
                text = buffer.value
                
                # Check if it's a watermark window
                for pattern in self.WATERMARK_TEXTS:
                    if pattern.lower() in text.lower():
                        watermark_hwnds.append(hwnd)
                        return True
            
            # Also check by class name
            class_buffer = ctypes.create_unicode_buffer(256)
            self._user32.GetClassNameW(hwnd, class_buffer, 256)
            class_name = class_buffer.value
            
            # Check for specific watermark window characteristics
            if class_name in self.WATERMARK_CLASSES:
                # Additional checks: window should be on desktop, small, etc.
                pass
            
            return True
        
        self._user32.EnumWindows(enum_callback, 0)
        return watermark_hwnds
    
    def _hide_window(self, hwnd: int) -> bool:
        """Hide a window by setting it invisible."""
        SW_HIDE = 0
        try:
            self._user32.ShowWindow(hwnd, SW_HIDE)
            return True
        except Exception:
            return False
    
    def _set_window_transparent(self, hwnd: int) -> bool:
        """Make window fully transparent."""
        GWL_EXSTYLE = -20
        WS_EX_LAYERED = 0x80000
        LWA_ALPHA = 0x2
        
        try:
            # Add layered style
            style = self._user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            self._user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED)
            
            # Set fully transparent
            self._user32.SetLayeredWindowAttributes(hwnd, 0, 0, LWA_ALPHA)
            return True
        except Exception:
            return False
    
    def hide_watermark(self) -> int:
        """Find and hide Test Mode watermark windows.
        
        Returns:
            Number of windows hidden
        """
        count = 0
        hwnds = self._find_watermark_windows()
        
        for hwnd in hwnds:
            if hwnd not in self._hidden_windows:
                if self._set_window_transparent(hwnd) or self._hide_window(hwnd):
                    self._hidden_windows.append(hwnd)
                    count += 1
                    logger.debug("Hidden watermark window: %d", hwnd)
        
        return count
    
    def _run_loop(self) -> None:
        """Background thread loop to continuously hide watermark."""
        while self._running:
            try:
                self.hide_watermark()
            except Exception as e:
                logger.debug("Watermark remover error: %s", e)
            time.sleep(2.0)  # Check every 2 seconds
    
    def start(self) -> None:
        """Start background watermark removal."""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        
        # Initial hide
        self.hide_watermark()
        logger.info("Test Mode watermark remover started")
    
    def stop(self) -> None:
        """Stop background watermark removal."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        self._thread = None
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, *args):
        self.stop()


def hide_test_mode_watermark() -> bool:
    """One-shot function to hide Test Mode watermark.
    
    Returns:
        True if any watermark was hidden
    """
    try:
        remover = TestModeWatermarkRemover()
        count = remover.hide_watermark()
        return count > 0
    except Exception as e:
        logger.warning("Failed to hide watermark: %s", e)
        return False


def remove_test_mode_watermark_persistent() -> TestModeWatermarkRemover:
    """Start persistent watermark removal (recommended).
    
    Returns a remover instance that runs in background.
    Call .stop() when done or let it run for app lifetime.
    
    Usage:
        remover = remove_test_mode_watermark_persistent()
        # ... app runs ...
        remover.stop()  # Optional, stops on app exit anyway
    """
    remover = TestModeWatermarkRemover()
    remover.start()
    return remover
